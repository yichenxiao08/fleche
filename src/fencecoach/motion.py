"""Visibility-gated image-plane measurements. Never a technique correctness score."""

from __future__ import annotations

import math
from statistics import median


def joint_angle(a, b, c):
    u, v = (a[0] - b[0], a[1] - b[1]), (c[0] - b[0], c[1] - b[1])
    norm = math.hypot(*u) * math.hypot(*v)
    return (
        round(math.degrees(math.acos(max(-1, min(1, sum(x * y for x, y in zip(u, v)) / norm)))), 1)
        if norm > 1e-8
        else None
    )


def frame_features(landmarks, width, height):
    points = [(p[0] * width, p[1] * height) for p in landmarks]

    def quality(ids):
        return min(min(landmarks[i][3:5]) for i in ids)

    torso = (math.dist(points[11], points[23]) + math.dist(points[12], points[24])) / 2
    if torso <= 5 or quality((11, 12, 23, 24, 25, 26, 27, 28)) < 0.5:
        return None
    features = {
        "stance_ratio": round(abs(points[27][0] - points[28][0]) / torso, 4),
        "hip_x_torso": round((points[23][0] + points[24][0]) / 2 / torso, 4),
        "torso_pixels": round(torso, 2),
    }
    shoulder = ((points[11][0] + points[12][0]) / 2, (points[11][1] + points[12][1]) / 2)
    hip = ((points[23][0] + points[24][0]) / 2, (points[23][1] + points[24][1]) / 2)
    features["torso_tilt"] = round(
        math.degrees(math.atan2(abs(shoulder[0] - hip[0]), hip[1] - shoulder[1])), 1
    )
    qualities = {
        "stance_ratio": quality((11, 12, 23, 24, 27, 28)),
        "torso_tilt": quality((11, 12, 23, 24)),
    }
    for side, s, elbow, wrist, pelvis, knee, ankle in [
        ("left", 11, 13, 15, 23, 25, 27),
        ("right", 12, 14, 16, 24, 26, 28),
    ]:
        features[f"{side}_knee_angle"] = joint_angle(points[pelvis], points[knee], points[ankle])
        qualities[f"{side}_knee_angle"] = quality((pelvis, knee, ankle))
        if quality((s, elbow, wrist, pelvis)) >= 0.5:
            arm_length = math.dist(points[s], points[elbow]) + math.dist(
                points[elbow], points[wrist]
            )
            features[f"{side}_elbow_angle"] = joint_angle(points[s], points[elbow], points[wrist])
            features[f"{side}_arm_extension"] = (
                round(math.dist(points[s], points[wrist]) / arm_length, 4)
                if arm_length > 5
                else None
            )
            features[f"{side}_wrist_height"] = round(
                (points[pelvis][1] - points[wrist][1]) / torso, 4
            )
            for key in ("elbow_angle", "arm_extension", "wrist_height"):
                qualities[f"{side}_{key}"] = quality((s, elbow, wrist, pelvis))
    features["quality_by_feature"] = {k: round(v, 4) for k, v in qualities.items()}
    return features


def enrich_candidates(frames, candidates, baseline, profile=None):
    for candidate in candidates:
        peak = min(
            (f for f in frames if f.get("features")),
            key=lambda f: abs(f["time_ms"] - candidate["start_ms"]),
        )
        proposed_onset = candidate.get("movement_onset_ms")
        preceding = [
            f
            for f in frames
            if f.get("features")
            and candidate["start_ms"] - 4000 <= f["time_ms"] <= candidate["start_ms"]
        ]
        if proposed_onset is not None:
            onset = min(preceding, key=lambda f: abs(f["time_ms"] - proposed_onset))
        else:
            # Last low-stance sample before expansion; a movement onset proposal, not attack intent.
            guarded = [f for f in preceding if f["features"]["stance_ratio"] <= baseline + 0.20]
            onset = guarded[-1] if guarded else preceding[0]
        candidate["onset_ms"] = onset["time_ms"]
        candidate["peak_features"] = peak["features"]
        candidate["onset_features"] = onset["features"]
        action_frames = [
            f
            for f in frames
            if onset["time_ms"] <= f["time_ms"] <= candidate["end_ms"] and f.get("features")
        ]
        knee_pairs = [
            (f["features"].get("left_knee_angle"), f["features"].get("right_knee_angle"))
            for f in action_frames
        ]
        knee_pairs = [
            (left, right) for left, right in knee_pairs if left is not None and right is not None
        ]
        onset_left = onset["features"].get("left_knee_angle")
        onset_right = onset["features"].get("right_knee_angle")
        if knee_pairs and onset_left is not None and onset_right is not None:
            min_left = min(pair[0] for pair in knee_pairs)
            min_right = min(pair[1] for pair in knee_pairs)
            peak_left = peak["features"].get("left_knee_angle")
            peak_right = peak["features"].get("right_knee_angle")
            peak_angles = [value for value in (peak_left, peak_right) if value is not None]
            asymmetry = abs(peak_left - peak_right) if len(peak_angles) == 2 else 0
            flexion_change = max(onset_left - min_left, onset_right - min_right)
            cues = {
                "knee_asymmetry_at_peak": round(asymmetry, 1),
                "knee_flexion_from_onset": round(flexion_change, 1),
                "bent_knee_at_peak": round(min(peak_angles), 1) if peak_angles else None,
            }
            cue_count = sum(
                (
                    asymmetry >= 18,
                    flexion_change >= 10,
                    bool(peak_angles and 55 <= min(peak_angles) <= 145),
                )
            )
        else:
            cues, cue_count = {}, 0
        candidate["lunge_cues"] = cues
        candidate["lunge_cue_count"] = cue_count
        candidate["movement_label"] = "lunge" if cue_count >= 2 else "stance_expansion"
        candidate["classification"] = (
            "lunge_like_stance_expansion" if cue_count >= 2 else "stance_expansion_and_return"
        )
        candidate["classification_source"] = "heuristic"
        candidate["camera_motion"] = (profile or {}).get("camera_motion", "unknown")
        candidate["measurements"] = window_measurements(
            frames, candidate["start_ms"], candidate["end_ms"], candidate
        )


def window_measurements(frames, start_ms, end_ms, candidate=None, profile=None):
    selected = [f for f in frames if start_ms <= f["time_ms"] <= end_ms and f.get("features")]
    if not selected:
        return []
    output = []

    def add(name, value, unit, quality, timestamp=None):
        if value is not None:
            output.append(
                dict(
                    name=name,
                    value=round(value, 3),
                    unit=unit,
                    confidence=round(quality, 3),
                    start_ms=start_ms if timestamp is None else timestamp,
                    end_ms=end_ms if timestamp is None else timestamp,
                )
            )

    peak = min(selected, key=lambda f: abs(f["time_ms"] - start_ms))
    for key in (
        "left_knee_angle",
        "right_knee_angle",
        "torso_tilt",
        "left_elbow_angle",
        "right_elbow_angle",
    ):
        add(
            key + "_at_peak",
            peak["features"].get(key),
            "deg",
            peak["features"].get("quality_by_feature", {}).get(key, peak["quality"]),
            peak["time_ms"],
        )
    speeds = []
    for a, b in zip(selected, selected[1:]):
        dt = (b["time_ms"] - a["time_ms"]) / 1000
        if 0 < dt <= 0.3 and a.get("landmarks") and b.get("landmarks"):
            # Fix scale to the first frame in the interval to avoid motion from changing normalization.
            dx = abs(
                (
                    b["landmarks"][23][0]
                    + b["landmarks"][24][0]
                    - a["landmarks"][23][0]
                    - a["landmarks"][24][0]
                )
                / 2
            )
            # hip_x_torso is only used to recover the image width / fixed torso scale.
            hipx = (peak["landmarks"][23][0] + peak["landmarks"][24][0]) / 2
            hip_scale = peak["features"].get("hip_x_torso")
            if hipx and hip_scale is not None:
                speeds.append(dx * hip_scale / hipx / dt)
    if speeds:
        camera = (profile or {}).get("camera_motion", (candidate or {}).get("camera_motion"))
        add(
            "recovery_hip_speed" if camera == "fixed" else "recovery_image_hip_speed",
            median(speeds),
            "torso/s",
            min(f["quality"] for f in selected),
        )
    if candidate and candidate.get("onset_features"):
        onset = candidate["onset_features"]
        for side in ("left", "right"):
            knee_key = f"{side}_knee_angle"
            onset_knee = onset.get(knee_key)
            peak_knee = peak["features"].get(knee_key)
            if onset_knee is not None and peak_knee is not None:
                onset_quality = onset.get("quality_by_feature", {}).get(knee_key, 0)
                peak_quality = (
                    peak["features"]
                    .get("quality_by_feature", {})
                    .get(knee_key, peak.get("quality", 0))
                )
                add(
                    f"{side}_knee_flexion_from_onset",
                    onset_knee - peak_knee,
                    "deg",
                    min(onset_quality, peak_quality),
                    candidate["onset_ms"],
                )
            key = f"{side}_arm_extension"
            onset_extension = onset.get(key)
            peak_extension = peak["features"].get(key)
            onset_quality = onset.get("quality_by_feature", {}).get(key, 0)
            peak_quality = (
                peak["features"].get("quality_by_feature", {}).get(key, peak.get("quality", 0))
            )
            add(
                key + "_at_onset",
                onset_extension,
                "ratio",
                onset_quality,
                candidate["onset_ms"],
            )
            add(
                key + "_at_peak",
                peak_extension,
                "ratio",
                peak_quality,
                peak["time_ms"],
            )
            if onset_extension is not None and peak_extension is not None:
                add(
                    key + "_change_to_peak",
                    peak_extension - onset_extension,
                    "ratio",
                    min(onset_quality, peak_quality),
                    candidate["onset_ms"],
                )
        add("movement_to_peak_time", start_ms - candidate["onset_ms"], "ms", candidate["quality"])
    return output


def clip_summary(frames):
    valid = [f for f in frames if f.get("features")]
    output = []
    for key, unit in [
        ("left_knee_angle", "deg"),
        ("right_knee_angle", "deg"),
        ("torso_tilt", "deg"),
        ("left_elbow_angle", "deg"),
        ("right_elbow_angle", "deg"),
        ("left_wrist_height", "torso"),
        ("right_wrist_height", "torso"),
    ]:
        values = [(f, f["features"].get(key)) for f in valid if f["features"].get(key) is not None]
        if values:
            output.append(
                dict(
                    name=key + "_median",
                    value=round(median(v for _, v in values), 3),
                    unit=unit,
                    confidence=round(
                        min(
                            f["features"].get("quality_by_feature", {}).get(key, f["quality"])
                            for f, _ in values
                        ),
                        3,
                    ),
                    start_ms=values[0][0]["time_ms"],
                    end_ms=values[-1][0]["time_ms"],
                    coverage=round(len(values) / max(1, len(frames)), 3),
                )
            )
    return output


def footwork_proposals(frames, baseline, profile):
    """Translation intervals near initial stance; direction requires athlete-supplied facing."""
    if baseline is None:
        return []
    valid = [f for f in frames if f.get("features") and f.get("landmarks")]
    events, active = [], None
    for a, b in zip(valid, valid[1:]):
        dt = (b["time_ms"] - a["time_ms"]) / 1000
        hip_x = (a["landmarks"][23][0] + a["landmarks"][24][0]) / 2
        dx = (b["landmarks"][23][0] + b["landmarks"][24][0]) / 2 - hip_x
        speed = dx * a["features"]["hip_x_torso"] / hip_x / dt if hip_x and dt else 0
        direction = "right" if speed > 0 else "left"
        moving = (
            0 < dt <= 0.3
            and abs(speed) >= 0.15
            and b["features"]["stance_ratio"] <= baseline + 0.25
        )
        if active and (not moving or active["direction"] != direction):
            if active["end_ms"] - active["start_ms"] >= 250:
                facing = profile.get("facing", "unknown")
                active["label"] = (
                    "translation"
                    if facing == "unknown"
                    else "advance_proposal"
                    if facing == active["direction"]
                    else "retreat_proposal"
                )
                active["source"] = "unvalidated_2d_heuristic"
                active["quality"] = round(min(active.pop("qualities")), 3)
                events.append(active)
            active = None
        if moving:
            if active is None:
                active = dict(
                    start_ms=a["time_ms"], end_ms=b["time_ms"], direction=direction, qualities=[]
                )
            active["end_ms"] = b["time_ms"]
            active["qualities"].append(min(a["quality"], b["quality"]))
    if active and active["end_ms"] - active["start_ms"] >= 250:
        active["quality"] = round(min(active.pop("qualities")), 3)
        facing = profile.get("facing", "unknown")
        active.update(
            label="translation"
            if facing == "unknown"
            else "advance_proposal"
            if facing == active["direction"]
            else "retreat_proposal",
            source="unvalidated_2d_heuristic",
        )
        events.append(active)
    return events
