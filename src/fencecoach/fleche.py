"""Fixed-camera solo flèche drill proposals. Thresholds are unvalidated beta settings."""

import math


def detect_fleche(frames, width, height, profile, guard):
    direction = {"left": -1, "right": 1}.get(profile.get("facing"))
    if not direction or profile.get("camera_motion") != "fixed" or not guard:
        return []
    valid = [f for f in frames if f.get("features") and len(f.get("landmarks", [])) == 33]
    guarded = [f for f in valid if guard["start_ms"] <= f["time_ms"] <= guard["end_ms"]]
    if not guarded:
        return []
    ref = guarded[-1]
    p = ref["landmarks"]
    body_height = abs((p[27][1] + p[28][1]) / 2 - p[0][1]) * height
    if body_height < 30:
        return []
    front = 27 if p[27][0] * direction > p[28][0] * direction else 28
    rear = 28 if front == 27 else 27
    samples = []
    for f in valid:
        if f["time_ms"] <= guard["end_ms"]:
            continue
        q = f["landmarks"]
        required = (0, 11, 12, 23, 24, 27, 28)
        if any(
            not (0.02 <= q[j][0] <= 0.98 and 0.02 <= q[j][1] <= 0.98) or q[j][3] < 0.5
            for j in required
        ):
            continue
        hip = (q[23][0] + q[24][0]) / 2 * width
        sx = (q[11][0] + q[12][0]) / 2 * width
        sy = (q[11][1] + q[12][1]) / 2 * height
        hy = (q[23][1] + q[24][1]) / 2 * height
        lean = math.degrees(math.atan2((sx - hip) * direction, hy - sy))
        crossing = (q[rear][0] - q[front][0]) * width * direction / body_height
        samples.append({"frame": f, "hip": hip, "lean": lean, "crossing": crossing})
    events = []
    for i in range(2, len(samples) - 1):
        a, b, c, following = samples[i - 2 : i + 2]
        times = [s["frame"]["time_ms"] for s in (a, b, c, following)]
        original_window = [f for f in frames if times[0] <= f["time_ms"] <= times[-1]]
        if len(original_window) != 4:
            continue  # Do not bridge a missed or clipped frame into a crossing event.
        if max(y - x for x, y in zip(times, times[1:])) > 250:
            continue
        if len({s["frame"].get("track_epoch", 0) for s in (a, b, c, following)}) != 1:
            continue
        dt1, dt2 = (times[1] - times[0]) / 1000, (times[2] - times[1]) / 1000
        if min(dt1, dt2) <= 0:
            continue
        v1 = (b["hip"] - a["hip"]) * direction / body_height / dt1
        v2 = (c["hip"] - b["hip"]) * direction / body_height / dt2
        acceleration = (v2 - v1) / ((dt1 + dt2) / 2)
        if not (
            b["crossing"] <= 0.05 < c["crossing"]
            and following["crossing"] > 0.05
            and v2 >= 0.5
            and acceleration >= 0.5
            and c["lean"] >= 8
            and c["lean"] - a["lean"] >= 3
        ):
            continue
        start = times[0]
        end = min(times[2] + 1200, frames[-1]["time_ms"])
        tail = [s for s in samples if times[2] <= s["frame"]["time_ms"] <= end]
        if any(
            s["frame"]["features"]["stance_ratio"] <= guard["stance_ratio"] + 0.20
            and s["crossing"] < 0
            for s in tail
        ):
            continue  # A visible guard recovery contradicts the no-recovery rule.
        if events and start - events[-1]["end_ms"] < 500:
            continue
        arm = profile.get("weapon_arm", "unknown")
        extension = a["frame"]["features"].get(arm + "_arm_extension") if arm != "unknown" else None
        measurements = [
            {
                "name": "fleche_peak_forward_lean",
                "value": max(s["lean"] for s in tail),
                "unit": "deg",
            },
            {"name": "fleche_forward_image_speed", "value": v2, "unit": "reference-heights/s"},
            {
                "name": "fleche_forward_image_travel",
                "value": (tail[-1]["hip"] - a["hip"]) * direction / body_height,
                "unit": "reference-heights",
            },
        ]
        if extension is not None:
            measurements.append(
                {
                    "name": "fleche_weapon_arm_extension_at_drive",
                    "value": extension,
                    "unit": "ratio",
                }
            )
            # First observed sustained near-extension relative to image hip-drive onset.
            # The ratio cutoff is a beta event rule, not an ideal technique threshold.
            before = [
                f
                for f in valid
                if guard["start_ms"] <= f["time_ms"] <= times[2]
                and f.get("track_epoch", 0) == a["frame"].get("track_epoch", 0)
            ]
            arm_onset = next(
                (
                    f["time_ms"]
                    for f, following_frame in zip(before, before[1:])
                    if f["features"].get(arm + "_arm_extension", 0) >= 0.90
                    and following_frame["features"].get(arm + "_arm_extension", 0) >= 0.90
                    and following_frame["time_ms"] - f["time_ms"] <= 250
                ),
                None,
            )
            if arm_onset is not None:
                measurements.append(
                    {
                        "name": "fleche_arm_extension_before_image_drive",
                        "value": start - arm_onset,
                        "unit": "ms",
                    }
                )
        quality = min(s["frame"]["quality"] for s in (a, b, c, following))
        for m in measurements:
            m.update(value=round(m["value"], 3), confidence=quality, start_ms=start, end_ms=end)
        events.append(
            {
                "start_ms": start,
                "end_ms": end,
                "crossing_ms": times[2],
                "label": "fleche",
                "status": "beta",
                "source": "fixed_side_view_rules_v1",
                "measurements": measurements,
                "limits": [
                    "Not validated recognition.",
                    "No balance verdict or weapon-contact timing is measured.",
                    "Reference height is visible head-to-ankle span in guard, not real-world stature.",
                    "Arm timing uses a sustained 0.90 extension-ratio crossing and image hip acceleration, not verified foot-force onset.",
                ],
            }
        )
    return events
