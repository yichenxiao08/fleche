"""Conservative comparisons: the same measurement name is not the same camera setup."""

from statistics import mean


def comparable_capture(a, b):
    required = (
        "camera_setup_id",
        "weapon",
        "weapon_arm",
        "front_leg",
        "facing",
        "camera_motion",
        "scene_type",
    )
    if any(
        a.get(k) in (None, "", "unknown") or b.get(k) in (None, "", "unknown") for k in required
    ):
        return (
            False,
            "Not comparable: record a camera setup name and confirm the same view, weapon arm, front leg, and facing direction.",
        )
    if (
        any(a[k] != b[k] for k in required)
        or a["camera_motion"] != "fixed"
        or a["scene_type"] != "solo"
    ):
        return False, "Not comparable: camera setup or capture conditions differ."
    if a.get("inference_crop") != b.get("inference_crop"):
        return False, "Not comparable: framing crops differ."
    return (
        True,
        "Matching declared setup; this does not independently prove equal camera distance or movement quality.",
    )


def compare_sessions(current, baseline, metric_name=""):
    ok, reason = comparable_capture(current.capture_profile, baseline.capture_profile)
    rows = []
    if ok:
        keys = {
            (m.name, m.unit)
            for m in current.metrics
            if not metric_name or metric_name.lower() in m.name.lower()
        }
        for name, unit in sorted(keys):
            now = [
                m.value
                for m in current.metrics
                if (m.name, m.unit) == (name, unit) and m.confidence >= 0.65
            ]
            before = [
                m.value
                for m in baseline.metrics
                if (m.name, m.unit) == (name, unit) and m.confidence >= 0.65
            ]
            if now and before:
                rows.append(
                    {
                        "name": name,
                        "unit": unit,
                        "current_mean": mean(now),
                        "baseline_mean": mean(before),
                        "delta": mean(now) - mean(before),
                        "current_samples": len(now),
                        "baseline_samples": len(before),
                    }
                )
    return {
        "comparable": ok,
        "reason": reason,
        "session_id": current.session_id,
        "baseline_session_id": baseline.session_id,
        "measurements": rows,
        "limit": "Change is not improvement; counts describe reviewed intervals, not verified action recognition.",
    }
