"""Athlete-supplied drill comparisons, separate from automatic technique faults."""

import json
import math
from pathlib import Path
from statistics import median


def evaluate_benchmarks(frames, window, phases, profile, width, height):
    config = json.loads(Path(__file__).with_suffix(".json").read_text())
    config = {**config, **profile.get("lunge_benchmarks", {})}
    out = {
        "source": config["source"],
        "status": "custom_drill_comparison",
        "timing": {},
        "reach": {},
        "rear_foot": {},
        "policy": "These are athlete-supplied drill targets, not validated universal technique or power thresholds.",
    }
    front = profile.get("front_leg")
    if profile.get("camera_view") != "side" or front not in {"left", "right"}:
        out.update(status="unavailable", reason="Needs a side view and identified front leg.")
        return out
    onset = window.get("onset_ms", window.get("movement_onset_ms"))
    finish = window["start_ms"]
    if onset is None:
        out.update(
            status="unavailable", reason="No action-start neighborhood for the foot-lift search."
        )
        return out
    front_ids = (27, 29, 31) if front == "left" else (28, 30, 32)
    rear_ids = (24, 26, 28, 30, 32) if front == "left" else (23, 25, 27, 29, 31)

    def point(f, i):
        return (f["landmarks"][i][0] * width, f["landmarks"][i][1] * height)

    def visible(f, ids):
        p = f.get("landmarks", [])
        return (
            len(p) == 33
            and bool(f.get("features"))
            and all(
                len(p[i]) >= 5
                and min(p[i][3:5]) >= 0.7
                and 0.01 <= p[i][0] <= 0.99
                and 0.01 <= p[i][1] <= 0.99
                for i in ids
            )
        )

    def foot(f, ids):
        a, b = point(f, ids[-2]), point(f, ids[-1])
        return ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)

    samples = sorted(frames, key=lambda f: f["time_ms"])
    guard = [
        f
        for f in samples
        if onset - 400 <= f["time_ms"] <= onset
        and visible(f, (*front_ids, *rear_ids, 11, 12, 23, 24))
    ]
    if len(guard) < 3:
        out.update(status="unavailable", reason="Too few visible starting-guard samples.")
        return out
    scale = median(f["features"].get("torso_pixels", 0) for f in guard)
    if scale <= 5:
        out.update(status="unavailable", reason="Starting body scale unavailable.")
        return out
    # Timestamp search uses foot lift, never the old hip-motion anchor as a substitute.
    baseline_y = median(foot(f, front_ids)[1] for f in guard)
    moving = [f for f in samples if onset - 125 <= f["time_ms"] <= finish and visible(f, front_ids)]
    raised = None
    for a, b in zip(moving, moving[1:]):
        if (
            0 < b["time_ms"] - a["time_ms"] <= 125
            and a.get("track_epoch", 0) == b.get("track_epoch", 0)
            and min(baseline_y - foot(f, front_ids)[1] for f in (a, b)) > 0.04 * scale
        ):
            raised = a
            break
    hold = phases.get("lunge_hold")
    timing = out["timing"]
    timing.update(
        definition="front-foot lift to observed stable lunge finish", thresholds=config["timing"]
    )
    if raised and hold and hold["start_ms"] > raised["time_ms"]:
        duration = (hold["start_ms"] - raised["time_ms"]) / 1000
        gaps = [
            b["time_ms"] - a["time_ms"]
            for a, b in zip(moving, moving[1:])
            if 0 < b["time_ms"] - a["time_ms"] <= 125
        ]
        error = 2 * max(gaps, default=125) / 1000
        low, high = max(0, duration - error), duration + error
        fast, normal = (
            config["timing"]["fast_below_seconds"],
            config["timing"]["normal_through_seconds"],
        )
        category = (
            "fast"
            if high < fast
            else "normal"
            if low >= fast and high <= normal
            else "slow"
            if low > normal
            else "borderline"
        )
        timing.update(
            status="estimated",
            duration_seconds=duration,
            category=category,
            front_foot_lift_ms=raised["time_ms"],
            stable_finish_ms=hold["start_ms"],
            sampling_range_seconds=[low, high],
            note="Lift uses two visible raised-foot samples; stability uses the observed held-lunge phase. Sampling range is a conservative timing allowance, not a statistical confidence interval.",
        )
    else:
        timing.update(
            status="unavailable",
            reason="Front-foot lift or sustained lunge stability was not established; action-anchor timing is a different measurement.",
        )
    finish_window = hold or phases.get("lunge_finish")
    landed = [
        f
        for f in samples
        if finish_window
        and finish_window["start_ms"] <= f["time_ms"] <= finish_window["end_ms"]
        and visible(f, (*front_ids, *rear_ids))
    ]
    if len(landed) < 3:
        out["reach"] = {"status": "unavailable", "reason": "Too few visible finish samples."}
        out["rear_foot"] = {"status": "unavailable", "reason": "Too few visible finish samples."}
        return out
    if len({f.get("track_epoch", 0) for f in guard + landed + moving}) > 1:
        out.update(
            status="unavailable", reason="Tracking identity changed across the measurement windows."
        )
        for key in ("timing", "reach", "rear_foot"):
            out[key] = {"status": "unavailable", "reason": out["reason"]}
        return out
    leg = median(
        math.dist(point(f, rear_ids[0]), point(f, rear_ids[1]))
        + math.dist(point(f, rear_ids[1]), point(f, rear_ids[2]))
        for f in guard
    )
    ratios = (
        [abs(foot(f, front_ids)[0] - foot(f, rear_ids)[0]) / leg for f in landed] if leg > 5 else []
    )
    if ratios:
        target = config["reach"]["target_feet_separation_leg_lengths"]
        out["reach"] = {
            "status": "estimated",
            "feet_separation_leg_lengths": median(ratios),
            "sample_range": [min(ratios), max(ratios)],
            "target_leg_lengths": target,
            "category": "comparison_only",
            "sample_count": len(ratios),
            "note": "Projected side-view foot-centre separation / starting rear-leg segment length; not calibrated metres or a universal correctness score.",
        }
    direction = (
        -1 if profile.get("facing") == "left" else 1 if profile.get("facing") == "right" else None
    )
    rear = out["rear_foot"]
    rear.update(
        criterion=config["rear_foot"],
        note="Rear-foot translation is separate from force and power; foot landmarks cannot prove ground contact.",
    )
    if direction is None:
        rear.update(status="unavailable", reason="Forward direction unknown.")
    else:
        displacement = direction * (
            median(foot(f, rear_ids)[0] for f in landed)
            - median(foot(f, rear_ids)[0] for f in guard)
        )
        rear.update(
            status="relative_only",
            forward_pixels=displacement,
            forward_torso_lengths=displacement / scale,
            benchmark_status="needs_distance_calibration",
            reason="12-inch criterion needs a known real-world distance in the same image plane.",
        )
    return out
