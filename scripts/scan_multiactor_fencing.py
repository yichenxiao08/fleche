"""Preserve timestamped multi-person pose evidence for long fencing-bout sources.

This corpus scan is not the single-athlete app pipeline: it has no athlete IDs,
activity phases or ground-truth gesture labels. Detections are stored per sampled
frame so that later review can resolve identities and action boundaries.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import av
import mediapipe as mp
from mediapipe.tasks.python import BaseOptions
from mediapipe.tasks.python.vision import PoseLandmarker, PoseLandmarkerOptions, RunningMode

from fencecoach.motion import frame_features
from fencecoach.settings import settings
from fencecoach.video_jobs import MODEL_SHA
from fencecoach.video_preview import upright_frame

SAMPLE_INTERVAL_MS = 1000 / 12
KEYPOINTS = (23, 24, 25, 26, 27, 28)


def scan(folder: Path, refresh: bool = False) -> None:
    source = json.loads((folder / "source.json").read_text(encoding="utf-8"))
    media = folder / "source.mp4"
    if not media.is_file():
        raise ValueError("Expected the curated master recording at source.mp4.")
    with media.open("rb") as handle:
        digest = hashlib.file_digest(handle, "sha256").hexdigest()
    if digest != source["sha256"]:
        raise ValueError("Source bytes no longer match the curated checksum.")

    model = settings.fencecoach_pose_model
    if not model.is_file() or hashlib.sha256(model.read_bytes()).hexdigest() != MODEL_SHA:
        raise ValueError("Pinned pose model is missing or has the wrong checksum.")

    output = folder / "prepared" / "multi-pose-scan.jsonl"
    summary_path = folder / "prepared" / "multi-pose-scan-summary.json"
    if output.exists() and summary_path.exists() and not refresh:
        previous = json.loads(summary_path.read_text(encoding="utf-8"))
        if previous.get("source_sha256") == digest and previous.get("model_sha256") == MODEL_SHA:
            reusable = {
                key: previous[key]
                for key in (
                    "sampled_frames",
                    "frames_with_pose",
                    "pose_detections",
                    "multiple_pose_frames",
                )
            }
            print(json.dumps({"reused": True, **reusable}), flush=True)
            return

    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(".jsonl.partial")
    counts = {
        "sampled_frames": 0,
        "frames_with_pose": 0,
        "pose_detections": 0,
        "multiple_pose_frames": 0,
        "no_pose_frames": 0,
    }
    first_timestamp = None
    previous_timestamp = -1
    next_sample = 0.0
    last_reported_second = -30

    with av.open(str(media)) as container:
        if not container.streams.video:
            raise ValueError("The source file has no video stream.")
        stream = container.streams.video[0]
        if stream.width * stream.height > 3840 * 2160:
            raise ValueError("Use footage at 4K resolution or below.")
        duration_hint = container.duration / av.time_base if container.duration else 0
        if duration_hint > 3600:
            raise ValueError("Offline bout scans are limited to one hour.")

        metadata = {
            "record_type": "metadata",
            "schema": "fencecoach-multipose-scan-v1",
            "source_clip_id": source["clip_id"],
            "source_sha256": digest,
            "source_credit": source["attribution"],
            "license": source["license"],
            "split_group": source["split_group"],
            "model_sha256": MODEL_SHA,
            "sample_interval_ms": round(SAMPLE_INTERVAL_MS, 3),
            "maximum_people_per_frame": 2,
            "coordinates": "upright full-frame normalized x/y; z relative to image plane",
            "identity_tracking": "none; detection_index is local to one frame",
            "labels": "none; pose detections and geometry are not action ground truth",
        }

        options = PoseLandmarkerOptions(
            base_options=BaseOptions(model_asset_path=str(model)),
            running_mode=RunningMode.VIDEO,
            num_poses=2,
            min_pose_detection_confidence=0.6,
            min_pose_presence_confidence=0.6,
            min_tracking_confidence=0.6,
        )
        with temporary.open("w", encoding="utf-8", newline="\n") as out:
            out.write(json.dumps(metadata, separators=(",", ":")) + "\n")
            with PoseLandmarker.create_from_options(options) as landmarker:
                for count, frame in enumerate(container.decode(stream)):
                    if count > 1_000_000:
                        raise ValueError("Too many decoded frames for the offline scan.")
                    if frame.pts is None or frame.time_base is None:
                        raise ValueError("Video timestamps are missing from the source.")
                    timestamp = float(frame.pts * frame.time_base)
                    if first_timestamp is None:
                        first_timestamp = timestamp
                    time_ms = round((timestamp - first_timestamp) * 1000)
                    if time_ms < previous_timestamp:
                        raise ValueError("Video timestamps went backwards.")
                    previous_timestamp = time_ms
                    if time_ms + 0.5 < next_sample:
                        continue
                    while next_sample <= time_ms + 0.5:
                        next_sample += SAMPLE_INTERVAL_MS

                    upright = upright_frame(frame)
                    rgb = upright.to_ndarray(format="rgb24")
                    height, width = rgb.shape[:2]
                    result = landmarker.detect_for_video(
                        mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb), time_ms
                    )
                    poses = []
                    for detection_index, pose in enumerate(result.pose_landmarks):
                        landmarks = [
                            [
                                round(p.x, 5),
                                round(p.y, 5),
                                round(p.z, 5),
                                round(p.visibility, 4),
                                round(p.presence, 4),
                            ]
                            for p in pose
                        ]
                        features = frame_features(landmarks, width, height)
                        lower_quality = min(
                            min(pose[index].visibility, pose[index].presence) for index in KEYPOINTS
                        )
                        hip_center = [
                            round((pose[23].x + pose[24].x) / 2, 5),
                            round((pose[23].y + pose[24].y) / 2, 5),
                        ]
                        poses.append(
                            {
                                "detection_index": detection_index,
                                "hip_center_xy": hip_center,
                                "lower_body_visibility_min": round(lower_quality, 4),
                                "landmarks": landmarks,
                                "features": features,
                            }
                        )

                    counts["sampled_frames"] += 1
                    counts["pose_detections"] += len(poses)
                    counts["frames_with_pose"] += bool(poses)
                    counts["multiple_pose_frames"] += len(poses) > 1
                    counts["no_pose_frames"] += not poses
                    out.write(
                        json.dumps(
                            {
                                "record_type": "frame",
                                "time_ms": time_ms,
                                "pose_count": len(poses),
                                "poses": poses,
                            },
                            separators=(",", ":"),
                        )
                        + "\n"
                    )
                    if counts["sampled_frames"] % 180 == 0:
                        out.flush()
                    if time_ms // 1000 >= last_reported_second + 30:
                        last_reported_second = time_ms // 1000
                        print(
                            f"  Scanned {time_ms / 1000:.0f}/{duration_hint:.0f}s · "
                            f"{counts['sampled_frames']} samples · "
                            f"{counts['frames_with_pose']} frames with poses",
                            flush=True,
                        )

    temporary.replace(output)
    summary = {
        "schema": "fencecoach-multipose-scan-summary-v1",
        "source_clip_id": source["clip_id"],
        "source_sha256": digest,
        "model_sha256": MODEL_SHA,
        "sample_interval_ms": round(SAMPLE_INTERVAL_MS, 3),
        "duration_ms": source["duration_ms"],
        "frame_width": source["width"],
        "frame_height": source["height"],
        **counts,
        "identity_tracking": "none",
        "gesture_labels": "none",
        "training_ground_truth": False,
        "scan_file": output.name,
        "limitations": [
            "Pose detection is sampled at 12 fps, not every native 30 fps frame.",
            "At most two poses are retained; detection order is not a stable athlete ID.",
            "The wide 640x360 broadcast includes other piste activity, occlusion and camera reframing.",
            "2D joint geometry is evidence for review, not a technique verdict or action label.",
        ],
    }
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2), flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--folder",
        type=Path,
        default=Path("data/training/youtube-cc/rigin-meinhardt-2016-t8"),
    )
    parser.add_argument("--refresh", action="store_true")
    args = parser.parse_args()
    scan(args.folder.resolve(), args.refresh)


if __name__ == "__main__":
    main()
