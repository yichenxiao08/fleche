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

PIPELINE_VERSION = "video-v10-input-qa"

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
    if initial_guard_confirmed:
        initial = [f for f in valid if f["time_ms"] <= 1500]
        if len(initial) >= 5:
            return {
                "stance_ratio": median(f["features"]["stance_ratio"] for f in initial),
                "start_ms": initial[0]["time_ms"],
                "end_ms": initial[-1]["time_ms"],
                "method": "athlete_confirmed_initial_guard",
            }

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
        hip = [f.get("hip_x_torso") for f in features]
        torso = [f.get("torso_tilt") for f in features]
        hip_stable = not all(value is not None for value in hip) or max(hip) - min(hip) <= 0.20
        visible_torso = [value for value in torso if value is not None]
        torso_stable = not visible_torso or max(visible_torso) - min(visible_torso) <= 24
        if max(stance) - min(stance) <= 0.24 and hip_stable and torso_stable:
            return {
                "stance_ratio": median(stance),
                "start_ms": window[0]["time_ms"],
                "end_ms": window[-1]["time_ms"],
                "method": "auto_detected_stable_guard",
            }
    return None


def proposals(frames, baseline=None, start_after_ms=0):
    valid = [f for f in frames if f.get("features")]
    if len(valid) < 10 or baseline is None:
        return [], None
    threshold = max(baseline * 1.3, baseline + 0.3)
    return_band = baseline + 0.20
    candidates, active, stable, previous = [], None, None, None
    last_guard = None
    previous_epoch = None

    def finish(returned_at, through_tracking_gap=False):
        start = active["peak"]["time_ms"]
        if 250 <= returned_at - active["started"] <= 6000:
            candidates.append(
                dict(
                    candidate_id=f"recovery-{len(candidates) + 1:02}",
                    start_ms=start,
                    end_ms=returned_at,
                    movement_onset_ms=active["started"],
                    quality=round(sum(active["quality"]) / len(active["quality"]), 3),
                    peak_stance_ratio=active["peak"]["features"]["stance_ratio"],
                    label="Peak stance → return to calibrated guard band",
                    return_observed_through_tracking_gap=through_tracking_gap,
                )
            )

    for frame in frames:
        features = frame.get("features")
        t = frame["time_ms"]
        epoch = frame.get("track_epoch", 0)
        if previous_epoch is not None and epoch != previous_epoch:
            active, stable, last_guard = None, None, None
        previous_epoch = epoch
        gap = previous is not None and t - previous > 300
        if gap:
            active, stable, last_guard = None, None, None
        if active:
            since_pose = t - active["last_feature_time"]
            if stable is not None and t - stable >= 333 and (not features or gap):
                finish(stable, through_tracking_gap=True)
                active, stable = None, None
            elif since_pose > 500:
                active, stable = None, None
        previous = t
        if not features:
            continue
        stance = features["stance_ratio"]
        if active is None:
            if stance <= return_band:
                last_guard = frame
            if t > start_after_ms and stance > threshold:
                active = dict(
                    peak=frame,
                    quality=[frame["quality"]],
                    started=last_guard["time_ms"]
                    if last_guard and t - last_guard["time_ms"] <= 1500
                    else t,
                    last_feature_time=t,
                )
            continue
        active["quality"].append(frame["quality"])
        active["last_feature_time"] = t
        if stance > active["peak"]["features"]["stance_ratio"]:
            active["peak"] = frame
            stable = None
        if stance <= return_band:
            stable = t if stable is None else stable
            if t - stable >= 333:
                finish(stable)
                active, stable = None, None
        else:
            stable = None
        if active and t - active["started"] > 8000:
            active, stable = None, None
    return candidates, round(baseline, 4)


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
                if len(frames) % 6 == 0:
                    thumbnail = (
                        av.VideoFrame.from_ndarray(rgb, format="rgb24")
                        .reformat(64, 36)
                        .to_ndarray(format="rgb24")
                    )
                    camera_check.observe(thumbnail)
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
                item = dict(time_ms=t, landmarks=[], quality=0, features=None)
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
    guard = find_guard_baseline(
        frames, job.get("capture_profile", {}).get("initial_guard_confirmed", False)
    )
    candidates, baseline = proposals(
        frames,
        baseline=guard["stance_ratio"] if guard else None,
        start_after_ms=guard["end_ms"] if guard else 0,
    )
    if baseline is not None:
        enrich_candidates(frames, candidates, baseline, job.get("capture_profile", {}))
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
    if not candidates:
        warnings.append(
            "No complete stance-expansion-and-return cycles were proposed. Mark intervals manually, or try clearer side-view footage."
        )
    if any(candidate.get("return_observed_through_tracking_gap") for candidate in candidates):
        warnings.append(
            "A return timestamp was completed after pose tracking became unavailable; review those return points closely."
        )
    enrich_frames(frames, w, h, job.get("capture_profile", {}))
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
        camera_evidence=camera_check.summary(),
        performance=dict(
            pose_inference_ms=round(inference_ms),
            total_ms=round((time.perf_counter() - started) * 1000),
        ),
        frames=frames,
        clip_measurements=clip_summary(frames),
        initial_guard_measurements=clip_summary([f for f in frames if f["time_ms"] <= 1500])
        if job.get("capture_profile", {}).get("initial_guard_confirmed")
        else [],
        capture_profile=job.get("capture_profile", {}),
        footwork_events=footwork_proposals(frames, baseline, job.get("capture_profile", {})),
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

    payload["fleche_events"] = detect_fleche(frames, w, h, job.get("capture_profile", {}), guard)
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
