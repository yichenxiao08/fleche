"""Per-repetition phase summaries from visible, timestamped pose samples."""

import math
from statistics import median


def rep_phases(frames, window, profile, width, height):
    start, end = window["start_ms"], window["end_ms"]
    onset = window.get("onset_ms", window.get("movement_onset_ms"))
    front = profile.get("front_leg")
    arm = profile.get("weapon_arm")
    facing = profile.get("facing")
    front_ids = (23, 25, 27, 31) if front == "left" else (24, 26, 28, 32)
    rear = "right" if front == "left" else "left"

    def visible(frame, ids):
        p = frame.get("landmarks", [])
        return (
            len(p) == 33
            and bool(frame.get("features"))
            and all(
                len(p[i]) >= 5
                and min(p[i][3:5]) >= 0.7
                and 0.01 <= p[i][0] <= 0.99
                and 0.01 <= p[i][1] <= 0.99
                for i in ids
            )
        )

    def point(frame, index):
        p = frame["landmarks"][index]
        return p[0] * width, p[1] * height

    def hip(frame):
        return sum(point(frame, i)[0] for i in (23, 24)) / 2

    def measures(frame):
        f = frame["features"]
        values = {}
        if visible(frame, (11, 12, 23, 24)):
            values["projected_torso_tilt"] = f.get("torso_tilt")
            dx = sum(point(frame, i)[0] for i in (11, 12)) / 2 - hip(frame)
            dy = (
                sum(point(frame, i)[1] for i in (23, 24)) / 2
                - sum(point(frame, i)[1] for i in (11, 12)) / 2
            )
            values["signed_torso_tilt"] = math.degrees(math.atan2(dx, dy))
        if visible(frame, (11, 12, 23, 24, 27, 28)):
            values["stance_width"] = f.get("stance_ratio")
        if front in {"left", "right"}:
            if visible(frame, front_ids[:3]):
                values["front_knee_angle"] = f.get(f"{front}_knee_angle")
            if (
                facing in {"left", "right"}
                and visible(frame, front_ids)
                and f.get("torso_pixels", 0) > 5
            ):
                values["front_knee_ahead_of_toe"] = (
                    (point(frame, front_ids[1])[0] - point(frame, front_ids[3])[0])
                    * (-1 if facing == "left" else 1)
                    / f["torso_pixels"]
                )
            rear_ids = (23, 25, 27) if rear == "left" else (24, 26, 28)
            if visible(frame, rear_ids):
                values["rear_knee_angle"] = f.get(f"{rear}_knee_angle")
        if arm in {"left", "right"}:
            shoulder, elbow, wrist = (11, 13, 15) if arm == "left" else (12, 14, 16)
            if visible(frame, (shoulder, elbow, wrist)):
                a, b = point(frame, shoulder), point(frame, wrist)
                values["weapon_arm_direction"] = math.degrees(
                    math.atan2(a[1] - b[1], abs(b[0] - a[0]))
                )
                values["weapon_elbow_angle"] = f.get(f"{arm}_elbow_angle")
        return {k: v for k, v in values.items() if v is not None and math.isfinite(v)}

    samples = sorted((f for f in frames if f.get("features")), key=lambda f: f["time_ms"])
    local = [f for f in samples if start <= f["time_ms"] <= end]
    finish = min(
        (f for f in samples if abs(f["time_ms"] - start) <= 125 and visible(f, (11, 12, 23, 24))),
        key=lambda f: abs(f["time_ms"] - start),
        default=None,
    )
    recovery_onset = None
    if finish and facing in {"left", "right"}:
        scale = finish["features"].get("torso_pixels", 0)
        eligible = [f for f in local if visible(f, (11, 12, 23, 24))]
        for a, b in zip(eligible, eligible[1:]):
            if not 0 < b["time_ms"] - a["time_ms"] <= 125 or scale <= 5:
                continue
            backwards = [
                (hip(f) - hip(finish)) * (1 if facing == "left" else -1) / scale for f in (a, b)
            ]
            if min(backwards) > 0.06:
                recovery_onset = a["time_ms"]
                break

    phases = {}

    def summarize(name, chosen, method):
        if not chosen:
            return
        rows = [(f["time_ms"], measures(f)) for f in chosen]
        result = {}
        keys = {k for _, values in rows for k in values}
        for key in sorted(keys):
            values = [(t, row[key]) for t, row in rows if key in row]
            value = median(v for _, v in values)
            result[key] = {
                "value": round(value, 3),
                "unit": "torso" if key in {"stance_width", "front_knee_ahead_of_toe"} else "deg",
                "sample_count": len(values),
                "range": [round(min(v for _, v in values), 3), round(max(v for _, v in values), 3)],
                "representative_ms": min(values, key=lambda pair: abs(pair[1] - value))[0],
            }
        phases[name] = {
            "start_ms": chosen[0]["time_ms"],
            "end_ms": chosen[-1]["time_ms"],
            "sample_count": len(chosen),
            "representative_ms": chosen[len(chosen) // 2]["time_ms"],
            "method": method,
            "measurements": result,
            "note": "Median within this phase only. A pose visibility or consistency check does not establish measurement accuracy.",
        }

    if onset is not None:
        summarize(
            "starting_guard",
            [f for f in samples if onset - 250 <= f["time_ms"] <= onset],
            "review/proposal action-start neighborhood",
        )
        summarize(
            "lunge_drive",
            [f for f in samples if onset <= f["time_ms"] < start],
            "action-start to lunge bookmark",
        )
    # A stable hold must be observed, rather than filling a fixed second after
    # every bookmark. The athlete may recover immediately with no held finish.
    hold = []
    if finish and recovery_onset is not None and front in {"left", "right"}:
        eligible = [
            f
            for f in local
            if f["time_ms"] < recovery_onset and visible(f, (11, 12, 23, 24, front_ids[2]))
        ]
        run, runs = [], []
        scale = finish["features"].get("torso_pixels", 0)
        for a, b in zip(eligible, eligible[1:]):
            stable = (
                0 < b["time_ms"] - a["time_ms"] <= 125
                and scale > 5
                and a.get("track_epoch", 0) == b.get("track_epoch", 0)
                and abs(hip(b) - hip(a)) / scale <= 0.025
                and abs(point(b, front_ids[2])[0] - point(a, front_ids[2])[0]) / scale <= 0.025
            )
            if stable:
                if not run:
                    run = [a]
                run.append(b)
            elif run:
                runs.append(run)
                run = []
        if run:
            runs.append(run)
        eligible_runs = [
            r for r in runs if len(r) >= 3 and r[-1]["time_ms"] - r[0]["time_ms"] >= 150
        ]
        if eligible_runs:
            hold = max(eligible_runs, key=lambda r: r[-1]["time_ms"] - r[0]["time_ms"])
    if hold:
        summarize(
            "lunge_hold",
            hold,
            "observed stable hip/front-ankle interval before estimated backward recovery",
        )
    else:
        summarize(
            "lunge_finish",
            [f for f in samples if abs(f["time_ms"] - start) <= 125],
            "finish-bookmark neighborhood; no sustained hold established",
        )
    if recovery_onset is not None:
        recovery = [f for f in samples if recovery_onset <= f["time_ms"] <= end]
        summarize(
            "active_recovery", recovery, "estimated backward hip-motion onset to return bookmark"
        )
        knees = [(f, measures(f).get("rear_knee_angle")) for f in recovery]
        knees = [(f, value) for f, value in knees if value is not None]
        if knees:
            # A single misplaced knee should not select the recovery peak.
            neighborhoods = [
                (
                    f["time_ms"],
                    [
                        value
                        for other, value in knees
                        if abs(other["time_ms"] - f["time_ms"]) <= 125
                    ],
                )
                for f, _ in knees
            ]
            supported = [(t, values) for t, values in neighborhoods if len(values) >= 3]
            peak = (
                min(supported, key=lambda pair: median(pair[1]))[0]
                if supported
                else min(knees, key=lambda pair: pair[1])[0]["time_ms"]
            )
            summarize(
                "recovery_peak",
                [f for f in recovery if abs(f["time_ms"] - peak) <= 125],
                "neighborhood of deepest rear-knee bend selected by local medians; not independently reviewed"
                if supported
                else "too few samples for a robust recovery peak; provisional neighborhood only",
            )
    summarize(
        "returned_guard",
        [f for f in samples if abs(f["time_ms"] - end) <= 125],
        "return-to-guard bookmark neighborhood",
    )
    return {
        "phases": phases,
        "recovery_onset_ms": recovery_onset,
        "hold_detected": bool(hold),
        "limitations": [
            "Phases use reviewed/proposed anchors and sampled 2D motion. There is no independently trained phase detector.",
            "The deepest sampled rear-knee bend is a recovery landmark, not a universal optimal posture.",
        ],
    }
