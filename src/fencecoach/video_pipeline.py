"""Timestamped 2D pose evidence and deliberately conservative recovery proposals."""

from __future__ import annotations

import hashlib
import json
import math
import time
from pathlib import Path
from statistics import median

from fencecoach.athlete_tracking import AthleteTracker
from fencecoach.footwork import enrich_frames, movement_summary
from fencecoach.gestures import classify_windows
from fencecoach.motion import clip_summary, enrich_candidates, footwork_proposals, frame_features
from fencecoach.movement_timeline import build_movement_timeline
from fencecoach.quality import CameraCheck, assess_quality
from fencecoach.settings import settings
from fencecoach.video_jobs import MAX_SECONDS, METHOD, MODEL_SHA
from fencecoach.video_preview import build_preview, upright_frame

PIPELINE_VERSION = "video-v12-camera-translation"
PROPOSAL_VERSION = "guard-cycles-v5-camera-compensated-drive"

SAMPLE_INTERVAL_MS = 1000 / 12
KEYPOINTS = (23, 24, 25, 26, 27, 28)


def angle(a, b, c):
    u, v = (a[0] - b[0], a[1] - b[1]), (c[0] - b[0], c[1] - b[1])
    denominator = math.hypot(*u) * math.hypot(*v)
    return (
        round(
            math.degrees(math.acos(max(-1, min(1, (u[0] * v[0] + u[1] * v[1]) / denominator)))), 1
        )
        if denominator > 1e-8
        else None
    )


def find_guard_baseline(frames, initial_guard_confirmed=False):
    """Find a quiet en-garde window so a walk-in cannot seed rep detection."""
    valid = [f for f in frames if f.get("features")]
    # Look for eight consecutive tracked samples (~0.6 s) with a steady stance
    # and little torso translation relative to body size. This can occur after
    # the athlete walks into frame, so pre-action movement is left outside.
    window_size = 8
    for start in range(max(0, len(valid) - window_size + 1)):
        window = valid[start : start + window_size]
        if window[-1]["time_ms"] - window[0]["time_ms"] < 500:
            continue
        if any(b["time_ms"] - a["time_ms"] > 250 for a, b in zip(window, window[1:])):
            continue
        features = [f["features"] for f in window]
        if len({f.get("track_epoch", 0) for f in window}) != 1:
            continue
        stance = [f["stance_ratio"] for f in features]
        knees = [
            min(f.get("left_knee_angle") or 180, f.get("right_knee_angle") or 180) for f in features
        ]
        # A quiet upright stand is not enough to establish a practice baseline.
        # These permissive image-plane gates are development heuristics, not
        # ideal knee angles or fencing technique standards.
        if median(stance) < 0.45 or median(knees) > 165:
            continue
        # Reconstruct hip position using one fixed scale: per-frame torso
        # foreshortening should not look like walking through the image.
        scales = [f.get("torso_pixels", 0) for f in features]
        fixed_scale = median(scales)
        hip = [
            f.get("hip_x_torso") * f.get("torso_pixels", 0) / fixed_scale
            if fixed_scale > 5 and f.get("hip_x_torso") is not None
            else f.get("hip_x_torso")
            for f in features
        ]
        torso = [f.get("torso_tilt") for f in features]
        hip_stable = not all(value is not None for value in hip) or max(hip) - min(hip) <= 0.20
        visible_torso = [value for value in torso if value is not None]
        torso_stable = not visible_torso or max(visible_torso) - min(visible_torso) <= 24
        if max(stance) - min(stance) <= 0.24 and hip_stable and torso_stable:
            return {
                "stance_ratio": median(stance),
                "start_ms": window[0]["time_ms"],
                "end_ms": window[-1]["time_ms"],
                "method": "athlete_confirmed_initial_guard"
                if initial_guard_confirmed and window[-1]["time_ms"] <= 1500
                else "auto_detected_stable_guard",
            }
    return None


def proposals(frames, baseline=None, start_after_ms=0, width=None, profile=None):
    """Guard -> meaningful leg separation/forward drive -> return, using a local fixed scale.

    Detection gates distinguish movement cycles; they never grade lunge technique.
    Knee depth/asymmetry are not required: an imperfect lunge is still a rep.
    """
    valid = [f for f in frames if f.get("features")]
    if len(valid) < 10 or baseline is None:
        return [], None
    profile = profile or {}
    configured_direction = (
        -1 if profile.get("facing") == "left" else 1 if profile.get("facing") == "right" else None
    )
    candidates, active, quiet, guard = [], None, [], None
    previous, previous_epoch = None, None

    def separation(frame, scale):
        f = frame["features"]
        return f["stance_ratio"] * f.get("torso_pixels", scale) / scale

    def hip(frame, scale):
        f = frame["features"]
        value = f.get("hip_x_torso")
        return value * f.get("torso_pixels", scale) / scale if value is not None else None

    def finish(returned_at):
        start = active["peak"]["time_ms"]
        scale = active["scale"]
        expansion = separation(active["peak"], scale) - active["guard_width"]
        # A threshold crossing alone can be caused by a tiny reset or a changing
        # torso estimate. Require sustained separation and a forward foot drive.
        wide = [f for f in active["frames"] if separation(f, scale) - active["guard_width"] >= 0.4]
        supported = len(wide) >= 3 and wide[-1]["time_ms"] - wide[0]["time_ms"] >= 100
        evidence = {
            "stance_expansion_torso_lengths": round(expansion, 3),
            "sustained_expansion": supported,
            "local_guard_width": round(active["guard_width"], 3),
        }
        direction = configured_direction
        if width and active["guard_frame"].get("landmarks") and active["peak"].get("landmarks"):
            origin = active["guard_frame"]
            ids = (27, 28)

            def seen(f):
                pts = f.get("landmarks", [])
                return len(pts) == 33 and all(
                    min(pts[i][3:5]) >= 0.6 and 0.01 <= pts[i][0] <= 0.99 for i in ids
                )

            if not seen(origin) or not seen(active["peak"]):
                return
            drive_by_direction = {}
            for candidate_direction in (-1, 1):
                leading = max(
                    ids,
                    key=lambda i: (
                        candidate_direction
                        * active["peak"].get("motion_landmarks", active["peak"]["landmarks"])[i][0]
                    ),
                )
                origin_points = origin.get("motion_landmarks", origin["landmarks"])
                drives = [
                    candidate_direction
                    * (
                        f.get("motion_landmarks", f["landmarks"])[leading][0]
                        - origin_points[leading][0]
                    )
                    * width
                    / scale
                    for f in wide
                    if seen(f)
                ]
                if drives:
                    drive_by_direction[candidate_direction] = {
                        "travel": median(drives),
                        "samples": len(drives),
                    }

            observed_direction = max(
                drive_by_direction,
                key=lambda d: drive_by_direction[d]["travel"],
                default=None,
            )
            usable_observed = (
                (
                    profile.get("camera_motion") != "moving"
                    or profile.get("camera_translation_compensated")
                )
                and observed_direction is not None
                and drive_by_direction[observed_direction]["samples"] >= 3
                and drive_by_direction[observed_direction]["travel"] >= 0.35
            )
            direction_source = "profile" if direction is not None else None
            if usable_observed and (
                direction is None
                or drive_by_direction.get(direction, {}).get("samples", 0) < 3
                or drive_by_direction.get(direction, {}).get("travel", -math.inf) < 0.35
                or (
                    observed_direction != direction
                    and drive_by_direction[observed_direction]["travel"]
                    >= drive_by_direction.get(direction, {}).get("travel", -math.inf)
                    + max(0.25, abs(drive_by_direction.get(direction, {}).get("travel", 0)) * 0.5)
                )
            ):
                direction = observed_direction
                direction_source = "observed_foot_drive"

            if direction is not None:
                travel = drive_by_direction.get(direction, {}).get("travel")
                samples = drive_by_direction.get(direction, {}).get("samples", 0)
                supported = supported and samples >= 3 and travel is not None and travel >= 0.35
                evidence["front_foot_forward_travel_torso_lengths"] = (
                    round(travel, 3) if travel is not None else None
                )
                evidence["detected_drive_direction"] = "left" if direction < 0 else "right"
                evidence["drive_direction_source"] = direction_source
                evidence["facing_metadata_conflict"] = (
                    configured_direction is not None and direction != configured_direction
                )
                if observed_direction is not None:
                    evidence["strongest_observed_direction_travel_torso_lengths"] = round(
                        drive_by_direction[observed_direction]["travel"], 3
                    )
            elif configured_direction is None:
                evidence["front_foot_forward_travel_torso_lengths"] = None

            if direction is not None:

                def motion_hip(frame):
                    pts = frame.get("motion_landmarks", frame.get("landmarks", []))
                    return (
                        (pts[23][0] + pts[24][0]) / 2 * width / scale
                        if len(pts) == 33
                        else hip(frame, scale)
                    )

                hips = [
                    direction * motion_hip(f) for f in active["frames"] if motion_hip(f) is not None
                ]
                returned_hip = (
                    direction * motion_hip(active["last_frame"])
                    if motion_hip(active["last_frame"]) is not None
                    else None
                )
                if hips and returned_hip is not None:
                    back = max(hips) - returned_hip
                    evidence["backward_hip_return_torso_lengths"] = round(back, 3)
                    supported = supported and back >= 0.1
        if (
            supported
            and expansion >= 0.45
            and 250 <= returned_at - active["started"] <= 20000
            and returned_at > start
        ):
            candidates.append(
                dict(
                    candidate_id=f"recovery-{len(candidates) + 1:02}",
                    start_ms=start,
                    end_ms=returned_at,
                    movement_onset_ms=active["started"],
                    quality=round(median(active["quality"]), 3),
                    peak_stance_ratio=active["peak"]["features"]["stance_ratio"],
                    label="Forward leg separation -> return to this rep's starting guard",
                    detection_evidence=evidence,
                    detection_method="local-guard-drive-return-v3",
                    return_observed_through_tracking_gap=False,
                )
            )

    for frame in frames:
        features, t = frame.get("features"), frame["time_ms"]
        epoch = frame.get("track_epoch", 0)
        if (previous_epoch is not None and epoch != previous_epoch) or (
            previous is not None and t - previous > 300
        ):
            active, quiet, guard = None, [], None
        previous, previous_epoch = t, epoch
        if not features:
            quiet = []
            if active and t - active["last_feature_time"] > 300:
                active, guard = None, None
            continue
        if active:
            active["frames"].append(frame)
            active["quality"].append(frame.get("quality", 0))
            active["last_feature_time"], active["last_frame"] = t, frame
            stance = separation(frame, active["scale"])
            if stance > separation(active["peak"], active["scale"]):
                active["peak"] = frame
            return_band = active["guard_width"] + max(0.2, active["guard_width"] * 0.2)
            if stance <= return_band:
                active["return_start"] = active.get("return_start") or t
                if t - active["return_start"] >= 200:
                    finish(active["return_start"])
                    active, quiet, guard = None, [frame], None
            else:
                active["return_start"] = None
            if active and t - active["started"] > 20000:
                active, quiet, guard = None, [], None
            continue
        if guard and t > start_after_ms:
            stance = separation(frame, guard["scale"])
            if t - guard["frame"]["time_ms"] <= 1500 and stance - guard["width"] >= max(
                0.35, guard["width"] * 0.25
            ):
                active = dict(
                    peak=frame,
                    frames=[guard["frame"], frame],
                    quality=[frame.get("quality", 0)],
                    started=guard["frame"]["time_ms"],
                    scale=guard["scale"],
                    guard_width=guard["width"],
                    guard_frame=guard["frame"],
                    last_feature_time=t,
                    last_frame=frame,
                    return_start=None,
                )
                quiet = []
                continue
        quiet.append(frame)
        quiet = [f for f in quiet if t - f["time_ms"] <= 350]
        if len(quiet) < 3 or quiet[-1]["time_ms"] - quiet[0]["time_ms"] < 180:
            continue
        scale = median(f["features"].get("torso_pixels", 0) for f in quiet)
        if scale <= 5:
            continue
        widths = [separation(f, scale) for f in quiet]
        hips = [hip(f, scale) for f in quiet if hip(f, scale) is not None]
        if (
            median(widths) >= max(0.4, baseline * 0.6)
            and max(widths) - min(widths) <= 0.15
            and (not hips or max(hips) - min(hips) <= 0.15)
        ):
            guard = {"frame": frame, "width": median(widths), "scale": scale}
    return candidates, round(baseline, 4)


def refresh_cached_proposals(result, profile=None):
    """Recompute proposals from cached poses without changing saved review anchors."""
    profile = {**result.get("capture_profile", {}), **(profile or {})}
    camera = result.get("camera_evidence", {})
    if camera.get("moving"):
        profile["camera_motion"] = "moving"
    elif camera.get("assessed") and profile.get("camera_motion") == "unknown":
        profile["camera_motion"] = "fixed"
    profile["camera_translation_compensated"] = result.get("camera_evidence", {}).get(
        "translation_compensated", False
    )
    frames = result.get("frames", [])
    guard = find_guard_baseline(frames, profile.get("initial_guard_confirmed", False))
    candidates, baseline = proposals(
        frames,
        baseline=guard["stance_ratio"] if guard else None,
        start_after_ms=guard["end_ms"] if guard else 0,
        width=result["width"],
        profile=profile,
    )
    if baseline is not None:
        enrich_candidates(frames, candidates, baseline, profile)
    sets, segments = build_activity_regions(candidates, result["duration_ms"])
    updated = {
        **result,
        "proposal_version": PROPOSAL_VERSION,
        "capture_profile": profile,
        "candidates": candidates,
        "guard_calibration": guard,
        "baseline_stance_ratio": baseline,
        "exercise_sets": sets,
        "activity_segments": segments,
        "footwork_events": footwork_proposals(frames, baseline, profile),
        "initial_guard_measurements": clip_summary(
            [f for f in frames if guard and guard["start_ms"] <= f["time_ms"] <= guard["end_ms"]]
        ),
    }
    warnings = [
        warning
        for warning in result.get("warnings", [])
        if not warning.startswith("No complete stance-expansion-and-return cycles were proposed.")
        and not warning.startswith("Facing metadata disagreed with tracked foot travel")
    ]
    if not candidates:
        warnings.append(
            "No complete stance-expansion-and-return cycles were proposed. Mark intervals manually, or try clearer side-view footage."
        )
    if any(
        candidate.get("detection_evidence", {}).get("facing_metadata_conflict")
        for candidate in candidates
    ):
        warnings.append(
            "Facing metadata disagreed with tracked foot travel for at least one rep; the detector used observed foot movement for that interval. Check the facing setting if the suggestions look wrong."
        )
    updated["warnings"] = warnings
    updated["movement_timeline"] = build_movement_timeline(updated)
    updated["quality_gate"] = assess_quality(updated)
    updated["proposal_refinement"] = {
        "previous_count": len(result.get("candidates", [])),
        "current_count": len(candidates),
        "pose_inference_rerun": False,
        "note": "Recomputed guard and movement proposals using the existing pose samples. Reviewed intervals remain unchanged.",
    }
    return updated


def build_activity_regions(candidates, duration_ms, set_gap_ms=8000):
    """Group complete movement cycles into reviewable set and transition spans."""
    ordered = sorted(candidates, key=lambda item: item.get("onset_ms", item["start_ms"]))
    sets, current = [], []
    for candidate in ordered:
        onset = candidate.get("onset_ms", candidate["start_ms"])
        if current and onset - current[-1]["end_ms"] > set_gap_ms:
            sets.append(current)
            current = []
        current.append(candidate)
    if current:
        sets.append(current)

    output_sets, phases = [], []
    for set_number, group in enumerate(sets, 1):
        start_ms = min(c.get("onset_ms", c["start_ms"]) for c in group)
        end_ms = max(c["end_ms"] for c in group)
        candidate_ids = []
        likely_lunges = 0
        for rep_number, candidate in enumerate(group, 1):
            candidate["set_number"] = set_number
            candidate["rep_number"] = rep_number
            candidate_ids.append(candidate["candidate_id"])
            likely_lunges += candidate.get("movement_label") == "lunge"
        output_sets.append(
            {
                "set_number": set_number,
                "start_ms": start_ms,
                "end_ms": end_ms,
                "candidate_ids": candidate_ids,
                "movement_count": len(group),
                "lunge_count": likely_lunges,
                "source": "complete_stance_expansion_cycles",
                "review_required": True,
            }
        )
        for candidate in group:
            phases.append(
                {
                    "label": "exercise",
                    "start_ms": candidate.get("onset_ms", candidate["start_ms"]),
                    "end_ms": candidate["end_ms"],
                    "set_number": set_number,
                    "candidate_ids": [candidate["candidate_id"]],
                    "source": "heuristic_suggestion",
                }
            )
        for left, right in zip(group, group[1:]):
            gap_start = left["end_ms"]
            gap_end = right.get("onset_ms", right["start_ms"])
            if gap_end - gap_start >= 1000:
                phases.append(
                    {
                        "label": "between_reps",
                        "start_ms": gap_start,
                        "end_ms": gap_end,
                        "set_number": set_number,
                        "source": "gap_between_complete_cycles",
                    }
                )

    if output_sets:
        if output_sets[0]["start_ms"] > 500:
            phases.append(
                {
                    "label": "setup",
                    "start_ms": 0,
                    "end_ms": output_sets[0]["start_ms"],
                    "source": "outside_detected_cycles",
                }
            )
        for left, right in zip(output_sets, output_sets[1:]):
            phases.append(
                {
                    "label": "rest",
                    "start_ms": left["end_ms"],
                    "end_ms": right["start_ms"],
                    "source": "long_gap_between_sets",
                }
            )
        if duration_ms - output_sets[-1]["end_ms"] > 500:
            phases.append(
                {
                    "label": "exit",
                    "start_ms": output_sets[-1]["end_ms"],
                    "end_ms": duration_ms,
                    "source": "outside_detected_cycles",
                }
            )
    return output_sets, sorted(phases, key=lambda item: (item["start_ms"], item["end_ms"]))


def analyze(jobs, job_id: str, model: Path):
    import av
    import mediapipe as mp
    import numpy as np
    from mediapipe.tasks.python import BaseOptions
    from mediapipe.tasks.python.vision import (
        PoseLandmarker,
        PoseLandmarkerOptions,
        RunningMode,
    )

    if not model.is_file():
        raise ValueError("Pose model missing. Run scripts/setup_video.py before analysis.")
    sha = hashlib.sha256(model.read_bytes()).hexdigest()
    if sha != MODEL_SHA:
        raise ValueError("Pose model checksum differs from the pinned model. Run setup_video.py.")
    job = jobs.get(job_id)
    started = time.perf_counter()
    directory = jobs.directory / job_id
    crop = job["crop"]
    inference_crop = dict(crop)
    # When a reviewed description explicitly names a foreground athlete,
    # suppress upper background rows before detection. Coordinates below still
    # map back into the original full frame; accepted crop/labels are untouched.
    if job.get("athlete_foreground") and crop == {"x": 0.0, "y": 0.0, "width": 1.0, "height": 1.0}:
        inference_crop.update(y=0.2, height=0.8)
        if job.get("athlete_selection_hint") == "right":
            inference_crop.update(x=0.4, width=0.6)
        elif job.get("athlete_selection_hint") == "left":
            inference_crop.update(width=0.6)
    frames, ambiguous, missing, jumps = [], 0, 0, 0
    start_time = None
    previous_timestamp = -1
    next_sample = 0
    tracker = None
    multiperson_selected = 0
    jobs.update(job_id, stage="Preparing smooth video playback", progress=5)
    preview = build_preview(
        directory / "source.video",
        directory,
        lambda fraction: jobs.update(job_id, progress=5 + round(25 * fraction)),
    )
    inference_ms = 0
    camera_check = CameraCheck()
    options = PoseLandmarkerOptions(
        base_options=BaseOptions(model_asset_path=str(model)),
        running_mode=RunningMode.VIDEO,
        num_poses=4,
        min_pose_detection_confidence=0.6,
        min_pose_presence_confidence=0.6,
        min_tracking_confidence=0.6,
    )
    jobs.update(job_id, stage="Tracking body landmarks", progress=30)
    with av.open(str(directory / "source.video")) as container:
        if not container.streams.video:
            raise ValueError("The uploaded file has no video stream.")
        stream = container.streams.video[0]
        if stream.width * stream.height > 3840 * 2160:
            raise ValueError("Use footage at 4K resolution or below.")
        if container.duration and container.duration / av.time_base > MAX_SECONDS + 1:
            raise ValueError(f"Use a clip of {MAX_SECONDS} seconds or less.")
        duration_hint = container.duration / av.time_base if container.duration else MAX_SECONDS
        with PoseLandmarker.create_from_options(options) as landmarker:
            for count, frame in enumerate(container.decode(stream)):
                if frame.width * frame.height > 3840 * 2160:
                    raise ValueError("Use footage at 4K resolution or below.")
                if count > 18000:
                    raise ValueError("Too many decoded frames. Export a shorter clip.")
                if frame.pts is None or frame.time_base is None:
                    raise ValueError(
                        "Video timestamps are missing. Export it as MP4 and try again."
                    )
                timestamp = float(frame.pts * frame.time_base)
                if start_time is None:
                    start_time = timestamp
                t = round((timestamp - start_time) * 1000)
                if t > MAX_SECONDS * 1000:
                    raise ValueError(f"Use a clip of {MAX_SECONDS} seconds or less.")
                if t < previous_timestamp:
                    raise ValueError("Video timestamps went backwards. Export a fresh MP4.")
                previous_timestamp = t
                if t + 0.5 < next_sample:
                    continue
                while next_sample <= t + 0.5:
                    next_sample += SAMPLE_INTERVAL_MS
                rgb = upright_frame(frame).to_ndarray(format="rgb24")
                h, w = rgb.shape[:2]
                camera_translation = None
                if len(frames) % 3 == 0:
                    thumbnail = (
                        av.VideoFrame.from_ndarray(rgb, format="rgb24")
                        .reformat(64, 36)
                        .to_ndarray(format="rgb24")
                    )
                    camera_translation = camera_check.observe(thumbnail)
                x, y = int(inference_crop["x"] * w), int(inference_crop["y"] * h)
                cw, ch = int(inference_crop["width"] * w), int(inference_crop["height"] * h)
                roi = np.ascontiguousarray(rgb[y : y + ch, x : x + cw])
                if max(cw, ch) > 960:
                    scale = 960 / max(cw, ch)
                    roi = (
                        av.VideoFrame.from_ndarray(roi, format="rgb24")
                        .reformat(max(1, round(cw * scale)), max(1, round(ch * scale)))
                        .to_ndarray(format="rgb24")
                    )
                inference_started = time.perf_counter()
                result = landmarker.detect_for_video(
                    mp.Image(image_format=mp.ImageFormat.SRGB, data=roi), t
                )
                inference_ms += (time.perf_counter() - inference_started) * 1000
                item = dict(
                    time_ms=t,
                    landmarks=[],
                    quality=0,
                    features=None,
                    camera_background_translation=camera_translation,
                )
                poses = [
                    [
                        [
                            round((p.x * cw + x) / w, 5),
                            round((p.y * ch + y) / h, 5),
                            round(p.z, 5),
                            round(p.visibility, 4),
                            round(p.presence, 4),
                        ]
                        for p in pose
                    ]
                    for pose in result.pose_landmarks
                ]
                if tracker is None:
                    tracker = AthleteTracker(
                        crop,
                        w,
                        h,
                        job.get("athlete_selection_hint")
                        or job.get("capture_profile", {}).get("target_side"),
                        job.get("athlete_foreground", False),
                    )
                landmarks, tracking = tracker.select(poses, t)
                item["tracking"] = tracking
                item["track_epoch"] = tracking["epoch"]
                if landmarks is None:
                    if not poses:
                        missing += 1
                    elif tracking["reason"] == "identity_discontinuity":
                        jumps += 1
                    elif len(poses) > 1:
                        ambiguous += 1
                else:
                    multiperson_selected += tracking.get("selected_from_multiple", False)
                    item["landmarks"] = landmarks
                    quality = min(min(landmarks[i][3:5]) for i in KEYPOINTS)
                    if quality >= 0.5:
                        item["features"] = frame_features(landmarks, w, h)
                        if item["features"]:
                            item["quality"] = round(quality, 4)
                frames.append(item)
                if len(frames) % 12 == 0:
                    jobs.update(
                        job_id,
                        progress=min(94, round(30 + 64 * t / (duration_hint * 1000))),
                        stage="Tracking body landmarks",
                        sampled_frames=len(frames),
                    )
    if len(frames) < 6:
        raise ValueError("Use at least one second of decodable video.")
    camera_evidence = camera_check.summary()
    camera_compensated = camera_evidence.get("translation_compensated", False)
    if camera_compensated:
        anchors = [
            (frame["time_ms"], frame["camera_background_translation"])
            for frame in frames
            if frame.get("camera_background_translation") is not None
        ]
        next_anchor = 1
        for frame in frames:
            while next_anchor < len(anchors) and anchors[next_anchor][0] < frame["time_ms"]:
                next_anchor += 1
            before = anchors[min(max(0, next_anchor - 1), len(anchors) - 1)]
            after = anchors[min(next_anchor, len(anchors) - 1)]
            fraction = (
                (frame["time_ms"] - before[0]) / (after[0] - before[0])
                if after[0] > before[0]
                else 0
            )
            shift = {
                "cumulative_dx": before[1]["cumulative_dx"]
                + (after[1]["cumulative_dx"] - before[1]["cumulative_dx"]) * fraction,
                "cumulative_dy": before[1]["cumulative_dy"]
                + (after[1]["cumulative_dy"] - before[1]["cumulative_dy"]) * fraction,
            }
            frame["motion_landmarks"] = [
                [
                    round(point[0] - shift.get("cumulative_dx", 0), 6),
                    round(point[1] - shift.get("cumulative_dy", 0), 6),
                    *point[2:],
                ]
                for point in frame.get("landmarks", [])
            ]
    analysis_profile = {
        **job.get("capture_profile", {}),
        "camera_motion": (
            "moving"
            if camera_evidence.get("moving")
            or job.get("capture_profile", {}).get("camera_motion") == "moving"
            else "fixed"
            if camera_evidence.get("assessed")
            else job.get("capture_profile", {}).get("camera_motion", "unknown")
        ),
        "camera_translation_compensated": camera_compensated,
    }
    guard = find_guard_baseline(
        frames, job.get("capture_profile", {}).get("initial_guard_confirmed", False)
    )
    candidates, baseline = proposals(
        frames,
        baseline=guard["stance_ratio"] if guard else None,
        start_after_ms=guard["end_ms"] if guard else 0,
        width=w,
        profile=analysis_profile,
    )
    if baseline is not None:
        enrich_candidates(frames, candidates, baseline, analysis_profile)
    exercise_sets, activity_segments = build_activity_regions(candidates, preview["duration_ms"])
    warnings = [
        "Angles and torso tilt are 2D estimates, not spinal straightness or a technique verdict.",
        "Arm extension is measured at a proposed movement onset, not weapon contact or attack intent.",
        "Exercise regions and lunge-like reps are unvalidated pose-based suggestions. Review every interval.",
        "The pipeline searches for a steady en-garde stance anywhere in the clip. Earlier walk-in footage is excluded from rep proposals.",
        "Tracking quality is a visibility/presence proxy, not probability of correctness.",
    ]
    if not guard:
        warnings.append(
            "No stable en-garde interval was found, so automatic movement counting was withheld. Confirm the first 1.5 seconds show a stationary en-garde stance or use manual intervals."
        )
    if ambiguous:
        warnings.append(
            f"Athlete selection was ambiguous in {ambiguous} sampled frames; those frames were excluded."
        )
    if missing:
        warnings.append(f"No pose detected in {missing} sampled frames.")
    if jumps:
        warnings.append(f"Excluded {jumps} frames with possible athlete identity changes.")
    if any(
        candidate.get("detection_evidence", {}).get("facing_metadata_conflict")
        for candidate in candidates
    ):
        warnings.append(
            "Facing metadata disagreed with tracked foot travel for at least one rep; the detector used observed foot movement for that interval. Check the facing setting if the suggestions look wrong."
        )
    if not candidates:
        warnings.append(
            "No complete stance-expansion-and-return cycles were proposed. Mark intervals manually, or try clearer side-view footage."
        )
    if any(candidate.get("return_observed_through_tracking_gap") for candidate in candidates):
        warnings.append(
            "A return timestamp was completed after pose tracking became unavailable; review those return points closely."
        )
    enrich_frames(frames, w, h, analysis_profile)
    gestures, gesture_model = classify_windows(frames, settings.fencecoach_gesture_model)
    activity_predictions, activity_model = classify_windows(
        frames, settings.fencecoach_activity_model, task="activity"
    )
    duration = preview["duration_ms"]
    payload = dict(
        job_id=job_id,
        method=METHOD,
        model_sha256=sha,
        duration_ms=duration,
        width=w,
        height=h,
        sample_interval_ms=SAMPLE_INTERVAL_MS,
        preview=preview,
        pipeline_version=PIPELINE_VERSION,
        proposal_version=PROPOSAL_VERSION,
        athlete_tracking=dict(
            method="geometry_continuity",
            selected_multiperson_frames=multiperson_selected,
            ambiguous_frames=ambiguous,
            identity_discontinuities=jumps,
            epochs=tracker.epoch,
        ),
        footwork_summary=movement_summary(frames),
        pose_input_max_dimension=960,
        inference_crop=inference_crop,
        camera_evidence=camera_evidence,
        performance=dict(
            pose_inference_ms=round(inference_ms),
            total_ms=round((time.perf_counter() - started) * 1000),
        ),
        frames=frames,
        clip_measurements=clip_summary(frames),
        initial_guard_measurements=clip_summary(
            [f for f in frames if guard and guard["start_ms"] <= f["time_ms"] <= guard["end_ms"]]
        ),
        capture_profile=job.get("capture_profile", {}),
        footwork_events=footwork_proposals(frames, baseline, analysis_profile),
        gestures=gestures,
        gesture_model=gesture_model,
        activity_predictions=activity_predictions,
        activity_model=activity_model,
        candidates=candidates,
        exercise_sets=exercise_sets,
        activity_segments=activity_segments,
        guard_calibration=guard,
        baseline_stance_ratio=baseline,
        warnings=warnings,
        tracked_frames=sum(bool(f["features"]) for f in frames),
        sampled_frames=len(frames),
        source=job["source"],
        source_credit="MIT OpenCourseWare · PE.740 Fencing (Spring 2007) · Prof. Jaroslav Koniusz"
        if job["source"] == "mit_ocw"
        else None,
    )
    payload["movement_timeline"] = build_movement_timeline(payload)
    payload["quality_gate"] = assess_quality(payload)
    from fencecoach.fleche import detect_fleche

    payload["fleche_events"] = detect_fleche(frames, w, h, analysis_profile, guard)
    from fencecoach.evidence_cache import prepare_evidence

    evidence = prepare_evidence(payload)
    (directory / "evidence.json").write_text(
        json.dumps(evidence, allow_nan=False), encoding="utf-8"
    )
    payload["evidence_cache"] = "evidence.json"
    from fencecoach.contact_sheets import generate_contact_sheet

    generate_contact_sheet(payload, directory)
    payload["contact_sheet"] = "contact-sheet.jpg"
    temporary = directory / "result.tmp"
    temporary.write_text(json.dumps(payload, allow_nan=False), encoding="utf-8")
    temporary.replace(directory / "result.json")
    jobs.update(
        job_id,
        duration_ms=duration,
        sampled_frames=len(frames),
        tracked_frames=payload["tracked_frames"],
        candidate_count=len(candidates),
        preview_revision=preview["revision"],
        preview_version=preview["version"],
    )
