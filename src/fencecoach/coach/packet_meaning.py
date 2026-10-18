"""Measurement semantics and source-backed assessment, without invented targets."""

from decimal import ROUND_HALF_UP, Decimal

DEFINITIONS = {
    "weapon_elbow_angle": (
        "Included angle at the weapon elbow; larger is straighter.",
        "Extension timing, arm direction, blade position, or technique quality.",
    ),
    "non_weapon_elbow_angle": (
        "Included angle at the non-weapon elbow; larger is straighter.",
        "Weapon-arm extension or technique quality.",
    ),
    "weapon_arm_direction": (
        "Weapon shoulder-to-wrist direction against image horizontal.",
        "Elbow bend, target alignment without a known target, or right of way.",
    ),
    "non_weapon_arm_direction": (
        "Non-weapon shoulder-to-wrist direction against image horizontal.",
        "Weapon-arm direction or elbow bend.",
    ),
    "front_knee_angle": (
        "Included image-plane hip-knee-ankle angle; smaller is more bent.",
        "Knee-over-toe position, force, safety, or a universal correctness score.",
    ),
    "rear_knee_angle": (
        "Included image-plane rear-knee angle; larger is straighter.",
        "Rear-leg drive, power, ground contact, or a universal ideal angle.",
    ),
    "front_knee_ahead_of_toe": (
        "Projected front-knee position relative to the front toe.",
        "Included knee angle, force, or injury risk.",
    ),
    "projected_torso_tilt": (
        "Magnitude of shoulder-midpoint to hip-midpoint tilt against image vertical.",
        "Spinal curvature, forward direction, balance, or a straight back.",
    ),
    "forward_torso_pitch_change": (
        "Change in signed image-plane torso pitch from the initial guard anchor.",
        "Absolute torso tilt at the finish, spinal shape, or back correctness.",
    ),
    "action_to_lunge_time": (
        "Elapsed interval from action anchor to the lunge bookmark.",
        "Attack correctness, touch time, or calibrated speed.",
    ),
    "action_projected_hip_speed": (
        "Image-plane horizontal hip speed normalized by initial torso length.",
        "Metres per second, sword speed, force, or power.",
    ),
    "estimated_active_recovery_time": (
        "Elapsed interval from estimated backward hip-motion onset to guard-return bookmark; preceding hold excluded.",
        "An onset timestamp, whole finish-to-guard duration, balance, or readiness.",
    ),
    "finish_to_guard_time": (
        "Elapsed lunge-finish to guard-return interval, including any hold.",
        "Active recovery duration alone, onset timestamp, or technique quality.",
    ),
    "feet_separation": (
        "Projected separation between tracked feet.",
        "Calibrated distance, balance, or a preferred stance width.",
    ),
    "feet_separation_leg_lengths": (
        "Projected feet separation normalized by tracked leg length.",
        "Metres or a universal stride target.",
    ),
}


def describe(measurement):
    feature = measurement["feature"]
    definition, limits = DEFINITIONS.get(
        feature,
        (
            "Projected shoulder-to-wrist reach divided by upper-arm plus forearm length."
            if "arm_extension" in feature
            else "Image-plane geometric measurement.",
            "Calibrated physical quantity, timing, blade control, or technique quality.",
        ),
    )
    unit = measurement.get("unit") or "dimensionless"
    precision = (
        0
        if unit == "ms"
        else 3
        if unit in {"s", "seconds", "second"}
        else 1
        if unit in {"deg", "degrees"}
        else 2
    )
    value = Decimal(str(measurement["value"])).quantize(
        Decimal(1).scaleb(-precision), rounding=ROUND_HALF_UP
    )
    return {
        **measurement,
        "value": float(value),
        "display": f"{value:.{precision}f} {unit}",
        "unit": unit,
        "definition": definition,
        "does_not_indicate": limits,
    }


# These directions describe geometry or elapsed time, never overall correctness.
RELATIVE_AXES = {
    "weapon_elbow_angle": (True, "straighter weapon elbow"),
    "non_weapon_elbow_angle": (True, "straighter non-weapon elbow"),
    "rear_knee_angle": (True, "straighter rear knee"),
    "front_knee_angle": (False, "more front-knee bend"),
    "projected_torso_tilt": (False, "closer to image upright"),
    "estimated_active_recovery_time": (False, "shorter measured active recovery interval"),
    "finish_to_guard_time": (False, "shorter finish-to-guard interval"),
    "action_to_lunge_time": (False, "shorter action-to-lunge interval"),
    "action_projected_hip_speed": (True, "higher projected hip speed"),
}


def assessments(topics, measurements, guidance, previous=None):
    """Compute relative observations, never infer a pass/fail threshold.

    Draft standards are intentionally not loaded here. Best/worst only describe
    the named measured axis, not the best/worst fencing technique.
    """
    from collections import defaultdict
    from statistics import mean

    result = []
    for topic in topics:
        rows = [m for m in measurements if m.get("topic") == topic]
        grouped = defaultdict(list)
        for row in rows:
            grouped[(row["feature"], row.get("phase"), row.get("unit"))].append(row)
        comparisons = []
        for (feature, phase, unit), group in grouped.items():
            values = sorted(group, key=lambda m: (m["value"], m.get("rep") or 0))
            low, high = values[0], values[-1]
            higher, axis = RELATIVE_AXES.get(
                feature, (True, "higher measured value; no preferred direction established")
            )
            preferred = feature in RELATIVE_AXES
            span = describe(
                {"feature": feature, "value": high["value"] - low["value"], "unit": unit}
            )
            item = {
                "evidence_id": f"relative:{topic}:{feature}:{phase}",
                "feature": feature,
                "phase": phase,
                "unit": unit,
                "rep_count": len({m.get("rep") for m in group}),
                "minimum": low,
                "maximum": high,
                "spread": span["display"],
                "spread_value": span["value"],
                "best": (high if higher else low) if preferred else None,
                "worst": (low if higher else high) if preferred else None,
                "relative_axis": axis,
                "meaning": "Best/worst refer ONLY to this measured aspect, not technique quality. Equal values tie; spread alone has no good/bad cutoff.",
            }
            prior = (previous or {}).get("measurements", [])
            matches = [
                m
                for m in prior
                if (m["feature"], m.get("phase"), m.get("unit")) == (feature, phase, unit)
            ]
            item["previous_session"] = {
                "status": (previous or {}).get("status", "not_comparable"),
                "reason": (previous or {}).get(
                    "reason", "No verified matching capture conditions."
                ),
            }
            if matches:
                delta = describe(
                    {
                        "feature": feature,
                        "unit": unit,
                        "value": mean(m["value"] for m in group)
                        - mean(m["value"] for m in matches),
                    }
                )
                item["previous_session"] = {
                    "status": "comparable",
                    "session_id": previous["session_id"],
                    "change_in_mean": delta["display"],
                    "change_value": delta["value"],
                    "previous_mean": describe(
                        {
                            "feature": feature,
                            "unit": unit,
                            "value": mean(m["value"] for m in matches),
                        }
                    )["display"],
                    "current_mean": describe(
                        {"feature": feature, "unit": unit, "value": mean(m["value"] for m in group)}
                    )["display"],
                    "evidence": matches,
                    "meaning": "Change in the same measured aspect, not proof of improvement.",
                }
            comparisons.append(item)
        result.append(
            {
                "topic": topic,
                "status": "relative_only" if rows else "no_measurements",
                "measured": rows[:2],
                "relative": comparisons,
                "library_cues": [
                    {"source_id": g["source_id"], "text": g["text"]} for g in guidance
                ],
                "basis": [],
                "reason": "The library gives teaching cues, not an approved pass/fail number. Compare the named measured aspect across reps without inventing a target.",
                "needed": "Confirm the intended drill and review its cue alongside these relative measurements.",
            }
        )
    return result
