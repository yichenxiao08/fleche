"""Turn temporal classifications into reviewable movements and measured phases.

No labels are generated for training here. Model windows and pose proposals remain
distinct, and neither establishes technique correctness or foot contact.
"""

from __future__ import annotations

from statistics import mean

VERSION = "movement-timeline-v1"


def decode_gestures(windows, duration_ms, minimum_ms=200):
    """Resolve overlapping windows by duration-local agreement, preserving gaps.

    2/3 agreement and minimum duration are development settings, not calibrated
    accuracy thresholds. Abstentions participate in the denominator.
    """
    windows = [w for w in windows if 0 <= w["start_ms"] < w["end_ms"] <= duration_ms]
    boundaries = sorted({t for w in windows for t in (w["start_ms"], w["end_ms"])})
    segments = []
    for start, end in zip(boundaries, boundaries[1:]):
        active = [w for w in windows if w["start_ms"] <= start and w["end_ms"] >= end]
        if not active:
            continue
        labels = {w["label"] for w in active} - {"uncertain", "other"}
        counts = {label: sum(w["label"] == label for w in active) for label in labels}
        winner = max(counts, key=counts.get) if counts else None
        agreement = counts[winner] / len(active) if winner else 0
        if agreement < 2 / 3:
            continue
        score = mean(w["model_score"] for w in active if w["label"] == winner)
        if segments and segments[-1]["label"] == winner and segments[-1]["end_ms"] == start:
            previous = segments[-1]
            previous["end_ms"] = end
            previous["minimum_agreement"] = min(previous["minimum_agreement"], agreement)
            previous["model_score"] = min(previous["model_score"], score)
        else:
            segments.append(
                dict(
                    start_ms=start,
                    end_ms=end,
                    label=winner,
                    minimum_agreement=agreement,
                    model_score=score,
                    source="trained_temporal_classifier",
                    review_required=True,
                )
            )
    return [s for s in segments if s["end_ms"] - s["start_ms"] >= minimum_ms]


def _covered(frames, start, end):
    """Require continuous usable pose before showing an interval as a phase."""
    samples = [f for f in frames if start <= f["time_ms"] <= end]
    valid = [f for f in samples if f.get("features")]
    return bool(
        len(valid) >= 2
        and len(valid) >= 0.8 * len(samples)
        and valid[0]["time_ms"] - start <= 150
        and end - valid[-1]["time_ms"] <= 150
        and all(b["time_ms"] - a["time_ms"] <= 250 for a, b in zip(valid, valid[1:]))
    )


def build_movement_timeline(result):
    frames = result.get("frames", [])
    duration = result.get("duration_ms", 0)
    model = result.get("gesture_model", {})
    movements = decode_gestures(result.get("gestures", []), duration) if model.get("ready") else []
    phases, cycles = [], []
    for candidate in result.get("candidates", []):
        onset = candidate.get("onset_ms", candidate["start_ms"])
        peak, end = candidate["start_ms"], candidate["end_ms"]
        if not 0 <= onset < peak < end <= duration:
            continue
        matching = [m for m in movements if m["start_ms"] < peak and m["end_ms"] > onset]
        recognized_lunge = any(m["label"] == "lunge" for m in matching)
        conflict = bool(matching) and not recognized_lunge
        label = "lunge" if recognized_lunge else candidate.get("movement_label", "stance_expansion")
        cycle = dict(
            candidate_id=candidate["candidate_id"],
            label=label,
            start_ms=onset,
            peak_ms=peak,
            end_ms=end,
            source="model_and_pose" if recognized_lunge else "pose_heuristic",
            recognition_conflict=conflict,
            review_required=True,
        )
        cycles.append(cycle)
        if not matching:
            movements.append(
                dict(
                    start_ms=onset,
                    end_ms=peak,
                    label=label,
                    source="pose_heuristic",
                    review_required=True,
                    candidate_id=candidate["candidate_id"],
                )
            )
        for name, start, finish in (
            ("stance_expansion", onset, peak),
            ("return_to_guard", peak, end),
        ):
            if _covered(frames, start, finish) and not (
                name == "return_to_guard" and candidate.get("return_observed_through_tracking_gap")
            ):
                phases.append(
                    dict(
                        label=name,
                        start_ms=start,
                        end_ms=finish,
                        candidate_id=candidate["candidate_id"],
                        source="pose_heuristic",
                        review_required=True,
                    )
                )

    # Translation proposals require a fixed camera. Restrict them to detected
    # practice sets so walk-in footage is not relabeled as fencing footwork.
    if result.get("capture_profile", {}).get("camera_motion") == "fixed":
        for event in result.get("footwork_events", []):
            start, end = event["start_ms"], event["end_ms"]
            inside = any(
                s["start_ms"] <= start and end <= s["end_ms"]
                for s in result.get("exercise_sets", [])
            )
            overlaps = any(m["start_ms"] < end and m["end_ms"] > start for m in movements)
            if inside and not overlaps and _covered(frames, start, end):
                movements.append(
                    dict(
                        start_ms=start,
                        end_ms=end,
                        label=event["label"].removesuffix("_proposal"),
                        source="pose_heuristic",
                        review_required=True,
                    )
                )
    return dict(
        version=VERSION,
        movements=sorted(movements, key=lambda m: (m["start_ms"], m["end_ms"])),
        phases=sorted(phases, key=lambda p: (p["start_ms"], p["end_ms"])),
        cycles=cycles,
        model_ready=bool(model.get("ready")),
        note="Movement suggestions need review. Phase peaks measure stance expansion, not landing or touch. Model scores are uncalibrated.",
    )
