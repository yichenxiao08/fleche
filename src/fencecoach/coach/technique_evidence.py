"""Expose automatic per-rep rubric findings to the conversational coach."""

import json
import re
from statistics import median

from fencecoach.coach.analysis import _rep_key, build_coaching_brief
from fencecoach.coach.intent import (
    arm_roles,
    arm_sides,
    classify_coach_question,
    question_phases,
    question_topics,
    wants_rep_comparison,
)
from fencecoach.coach.policy import MOTION_POLICY
from fencecoach.coach.turns import motion_question
from fencecoach.schemas import KnowledgeSource


def motion_context(request):
    selected = selected_evaluation(request)
    return {
        "policy": MOTION_POLICY,
        "selected_reps": [r["rep_number"] for r in selected["rep_measurements"]],
        "reference_comparisons": reference_context(request, selected),
        "within_clip_motion": [
            {
                "rep": r["rep_number"],
                "drill_benchmarks": r.get("drill_benchmarks", {}),
                "measurements": {
                    k: {
                        "value": round(m["value"] / 1000, 1) if m["unit"] == "ms" else m["value"],
                        "unit": "seconds" if m["unit"] == "ms" else m["unit"],
                        "meaning": m["note"],
                    }
                    for k, m in r["measurements"].items()
                    if k
                    in {
                        "action_projected_hip_speed",
                        "action_to_lunge_time",
                        "estimated_active_recovery_time",
                    }
                },
            }
            for r in selected["rep_measurements"]
        ],
    }


def reference_context(request, selected):
    """Keep the primary coaching context focused; full comparisons stay in evidence."""
    intent = classify_coach_question(request.question)
    question = request.question.lower()
    requested_metrics = requested_feature_names(request)
    requested_phases = question_phases(request.question)

    def phase_matches(phase):
        return (
            not requested_phases
            or phase in requested_phases
            or phase == "finish"
            and bool(requested_phases & {"lunge_finish", "lunge_hold"})
        )

    rows = []
    for rep in selected["rep_measurements"]:
        comparison = rep.get("reference_comparison", {})
        candidates = comparison.get("rows", [])
        if requested_metrics:
            candidates = [
                row
                for row in candidates
                if row["metric"] in requested_metrics and phase_matches(row.get("phase"))
            ]
        elif re.search(r"\b(?:speed|fast|slow|power|explosive)\b", question):
            candidates = [r for r in candidates if r["phase"] in {"action", "active_recovery"}]
        elif re.search(r"\b(?:distance|disatnce|reach|stride|long|far)\b", question):
            candidates = [r for r in candidates if r["metric"] == "feet_separation_leg_lengths"]
        elif re.search(r"\b(?:recover|recovery|return)\b", question):
            candidates = [
                r for r in candidates if "recover" in r["phase"] or r["phase"] == "returned_guard"
            ]
        elif intent.topic in {None, "lunge"}:
            candidates = [r for r in candidates if r["phase"] == "finish"]
        else:
            candidates = []
        rows.append(
            {
                "rep": rep["rep_number"],
                "status": comparison.get("status"),
                "policy": comparison.get("policy"),
                "references": comparison.get("references", []),
                "coaching_priorities": [
                    p
                    for p in comparison.get("coaching_priorities", [])
                    if (not requested_metrics or p.get("metric") in requested_metrics)
                    and phase_matches(p.get("phase", "finish"))
                ],
                "comparisons": candidates[:6],
            }
        )
    return rows


def plain_observation(finding):
    if finding.get("rule") == "arm_direction":
        direction = "above" if finding["measurement"]["value"] > 0 else "below"
        return f"Your sword hand finishes {direction} shoulder level."
    return finding["observation"]


def selected_evaluation(request):
    evaluation = request.technique_evaluation
    reps = evaluation.get("reps", [])
    intent = classify_coach_question(request.question)
    if intent.kind == "specific_rep" and intent.rep_number is not None:
        reps = [r for r in reps if r["rep_number"] == intent.rep_number]
    elif intent.kind == "specific_reps" and intent.rep_numbers:
        requested = set(intent.rep_numbers)
        reps = [r for r in reps if r["rep_number"] in requested]
    elif intent.kind == "last_rep":
        reps = reps[-1:]
    elif intent.kind == "first_rep":
        reps = reps[:1]
    words = set(re.findall(r"[a-z]+", request.question.lower()))
    words.update(
        {"arms": "arm", "hands": "hand", "legs": "leg", "knees": "knee"}[word]
        for word in list(words)
        if word in {"arms", "hands", "legs", "knees"}
    )
    phase_names = question_phases(request.question)
    if not phase_names:
        phase_names = (
            {"active_recovery", "recovery_peak", "returned_guard"}
            if words & {"recover", "recovery", "return"}
            else {"lunge_hold", "lunge_finish", "starting_guard"}
        )
    findings = (
        []
        if evaluation.get("coaching_mode") == "reference_comparison"
        else [f for r in reps for f in r["findings"]]
    )
    findings.sort(key=lambda f: -len(words & set(re.findall(r"[a-z]+", f["observation"].lower()))))
    return {
        "version": evaluation.get("version"),
        "measurement_policy": "Compare matching rep-phase medians. A held lunge is summarized separately from drive, active recovery, and returned guard. A whole-clip median is not lunge posture.",
        "status": evaluation.get("status"),
        "findings": findings[:3],
        "rep_measurements": [
            {
                "rep_number": r["rep_number"],
                "selected_frame_ms": r.get("selected_frame_ms"),
                "measurements": r["measurements"],
                "unavailable": r["unavailable"],
                "status": r.get("status"),
                "drill_benchmarks": r.get("drill_benchmarks", {}),
                "reference_comparison": r.get("reference_comparison", {}),
                "suppressed_findings": r.get("suppressed_findings", []),
                "phase_medians": {
                    name: {
                        "start_ms": phase["start_ms"],
                        "end_ms": phase["end_ms"],
                        "method": phase["method"],
                        "medians": {
                            key: {
                                "value": m["value"],
                                "unit": m["unit"],
                                "sample_count": m["sample_count"],
                                "range": m["range"],
                            }
                            for key, m in phase["measurements"].items()
                            if key != "signed_torso_tilt"
                        },
                    }
                    for name, phase in r.get("phases", {}).items()
                    if name in phase_names
                },
            }
            for r in reps
        ],
        "timing_summary": evaluation.get("timing_summary"),
        "capture": evaluation.get("capture_requirements"),
        "limits": evaluation.get("limitations", []),
    }


_TOPIC_MEASUREMENTS = {
    "arm": {"weapon_arm_direction", "weapon_elbow_angle", "arm_extension_timing"},
    "front_leg": {
        "front_knee_angle",
        "front_knee_ahead_of_toe",
        "front_foot_lift_to_stable_finish",
    },
    "rear_leg": {
        "rear_knee_angle",
        "rear_foot_displacement_inches",
        "rear_foot_displacement_leg_lengths",
        "rear_heel_grounded",
    },
    "torso": {"projected_torso_tilt", "forward_torso_pitch_change"},
    "recovery": {
        "estimated_active_recovery_time",
        "estimated_recovery_onset",
        "finish_to_guard_time",
        "rear_knee_angle",
    },
    "speed": {
        "action_projected_hip_speed",
        "action_to_lunge_time",
        "estimated_active_recovery_time",
    },
    "distance": {
        "feet_separation_leg_lengths",
        "rear_foot_displacement_inches",
        "rear_foot_displacement_leg_lengths",
    },
    "lunge": {
        "front_knee_angle",
        "rear_knee_angle",
        "projected_torso_tilt",
        "weapon_arm_direction",
        "feet_separation_leg_lengths",
    },
}

_TOPIC_BENCHMARKS = {
    "rear_leg": {"rear_foot"},
    "distance": {"reach", "rear_foot"},
    "speed": {"timing"},
    "recovery": {"timing"},
}

_TOPIC_LIMITS = {
    "arm": "Arm position is measured, but the exact instant of extension relative to front-foot landing is not directly measured.",
    "rear_leg": "Image-plane rear-foot movement does not establish real-world inches or prove that the heel stayed grounded.",
    "distance": "Relative stance length is an estimate; there is no physical-distance calibration in this clip.",
    "speed": "Projected hip speed is relative image-plane motion, not calibrated metres per second, force or power. Use the supplied drill timing category only when available.",
    "recovery": "The active-recovery interval is distinct from finish-to-guard time, which can include a hold.",
    "torso": "Projected torso tilt describes the image plane and does not measure spinal curvature.",
}


def requested_feature_names(request):
    """One body-role resolver shared by evidence selection and answer verification."""
    topics = question_topics(request.question)
    features = set().union(*(_TOPIC_MEASUREMENTS.get(topic, set()) for topic in topics))
    if "arm" not in topics:
        return features
    features -= _TOPIC_MEASUREMENTS["arm"]
    roles = arm_roles(request.question)
    weapon = request.capture_profile.get("weapon_arm")
    for role in roles:
        if role in {"weapon", "non_weapon"}:
            prefix = role
        elif weapon in {"left", "right"}:
            prefix = "weapon" if role == weapon else "non_weapon"
        else:
            continue
        features.update({f"{prefix}_arm_direction", f"{prefix}_elbow_angle"})
        if prefix == "weapon":
            features.add("arm_extension_timing")
    sides = arm_sides(request.question, request.capture_profile)
    features.update(
        metric.name
        for metric in request.metrics
        if metric.name.startswith(tuple(side + "_" for side in sides))
        and any(term in metric.name for term in ("arm_extension", "elbow_angle", "wrist_height"))
    )
    return features


def _metric_phase(name):
    if "initial_guard" in name:
        return "starting_guard"
    if name.endswith("_at_peak"):
        return "lunge_finish"
    if name.endswith("_at_onset"):
        return "lunge_drive"
    return None


def question_scoped_session_context(request, snapshot=None):
    """Return only the active-session records relevant to this turn's subject.

    Keep the complete feature inventory in the packet so the agent can see when
    the requested evidence is unavailable. Measurements, phase medians, and
    reference comparisons are narrowed to the explicit subject and phase; broad
    unscoped coaching priorities are removed because they can hijack follow-ups.
    """
    intent = classify_coach_question(request.question)
    topics = question_topics(request.question) or ([intent.topic] if intent.topic else [])
    features = requested_feature_names(request)
    phases = question_phases(request.question)
    selected = selected_evaluation(request)
    reps = [row.get("rep_number") for row in selected["rep_measurements"]]

    packet = session_evidence_context(
        request,
        sorted(features),
        sorted(phases),
        reps if intent.kind in {"first_rep", "last_rep", "specific_rep", "specific_reps"} else (),
        snapshot=snapshot,
    )
    if features or phases:
        # These fields summarize the whole clip and can refer to a different
        # movement feature than the question. The exact per-rep comparison rows
        # below already include relevant supported changes and reference ranges.
        packet["per_rep_reference_findings"] = []
        packet["recurring_reference_comparison"] = None
        packet["question_relevant_focus"] = None
        packet["reference_baselines"] = None
        # Conversation construction separately adds human feedback selected for
        # this corrected subject and rep scope. Do not also leak the full review
        # form here, where an unrelated cue could pull the answer off topic.
        packet["submitted_feedback"] = None
        packet["requested_scope"] = {
            **packet.get("requested_scope", {}),
            "topics": topics,
            "arm_roles": list(arm_roles(request.question)) if "arm" in topics else [],
            "anatomical_arm_sides": sorted(arm_sides(request.question, request.capture_profile))
            if "arm" in topics
            else [],
            "instruction": "Only these requested features and phases are in scope for personal feedback. Retrieve other evidence with a tool only if the question requires it.",
        }
    comparisons = [
        row
        for rep in packet["per_rep_measurements"]
        for row in rep["reference_comparisons"]
        if isinstance(row.get("current"), (int, float))
        and isinstance(row.get("reference_range"), list)
        and len(row["reference_range"]) == 2
        and all(isinstance(value, (int, float)) for value in row["reference_range"])
    ]
    if comparisons:

        def reference_deviation(row):
            lower, upper = sorted(row["reference_range"])
            return max(lower - row["current"], row["current"] - upper, 0) / max(upper - lower, 1e-6)

        packet["representative_support"] = {
            "record": max(comparisons, key=reference_deviation),
            "selection_policy": "An available example of the largest relative reference difference in the requested scope, or a matching example when all overlap. This is evidence selection, not a technique score or corrective verdict. Assess the full set, then illustrate the same pattern with one relevant record.",
        }
    packet["answer_affordances"] = {
        "observed_features": sorted(
            {record["feature"] for record in packet["session_measurements"]}
            | {name for rep in packet["per_rep_measurements"] for name in rep["measures"]}
            | {
                name
                for rep in packet["per_rep_measurements"]
                for phase in rep["phases"].values()
                for name in phase["values"]
            }
        ),
        "reference_features": sorted(
            {
                row["metric"]
                for rep in packet["per_rep_measurements"]
                for row in rep["reference_comparisons"]
            }
        ),
        "supported_corrections": [
            {
                "evidence_id": row["evidence_id"],
                "feature": row["metric"],
                "phase": row.get("phase"),
                "cue": row["supported_change"],
            }
            for rep in packet["per_rep_measurements"]
            for row in rep["reference_comparisons"]
            if row.get("supported_change")
        ],
        "instruction": "Use observations to describe what happened, matching references to assess differences, and only supported corrections or matching submitted feedback to identify a fault to fix. If no correction is established, a useful observation or positive comparison is a complete answer. Do not invent a correction merely because the athlete asks how something was. If the requested evidence is absent, explain that precise gap naturally and offer relevant general guidance.",
    }
    return json.dumps(packet, separators=(",", ":"))


def requested_topic_evidence(request, selected):
    """Keep all relevant per-rep values available for non-ranking questions."""
    intent = classify_coach_question(request.question)
    topics = question_topics(request.question) or ([intent.topic] if intent.topic else [])
    names = requested_feature_names(request)
    if not names:
        return None
    reps = []
    benchmark_names = set().union(*(_TOPIC_BENCHMARKS.get(topic, set()) for topic in topics))
    phases_requested = question_phases(request.question)
    phased_features = {
        "front_knee_angle",
        "front_knee_ahead_of_toe",
        "rear_knee_angle",
        "projected_torso_tilt",
        "weapon_arm_direction",
        "weapon_elbow_angle",
    }
    for rep in selected["rep_measurements"]:
        values = {}
        for name, measurement in rep.get("measurements", {}).items():
            if name in names:
                # Posture values on a rep-wide record usually refer to the finish.
                # Use explicit phase medians instead so a recovery question cannot
                # accidentally receive the lunge-finish knee or torso value.
                if name in phased_features:
                    measurement_phase = measurement.get("phase")
                    if not measurement_phase or (
                        phases_requested and measurement_phase not in phases_requested
                    ):
                        continue
                value = measurement.get("value")
                unit = measurement.get("unit")
                if unit == "ms" and isinstance(value, (int, float)):
                    value, unit = round(value / 1000, 1), "seconds"
                values[name] = {"value": value, "unit": unit}
        phases = {}
        for phase_name, phase in rep.get("phase_medians", {}).items():
            if phases_requested and phase_name not in phases_requested:
                continue
            phase_values = {}
            for name, measurement in phase.get("medians", {}).items():
                if name not in names:
                    continue
                value, unit = measurement.get("value"), measurement.get("unit")
                if unit == "ms" and isinstance(value, (int, float)):
                    value, unit = round(value / 1000, 1), "seconds"
                phase_values[name] = {"value": value, "unit": unit}
            if phase_values:
                phases[phase_name] = phase_values
        reps.append(
            {
                "rep": rep["rep_number"],
                "selected_time_seconds": round(rep["selected_frame_ms"] / 1000, 1)
                if isinstance(rep.get("selected_frame_ms"), (int, float))
                else None,
                "measurements": values,
                "phase_medians": phases,
                "drill_benchmarks": {
                    name: rep.get("drill_benchmarks", {}).get(name)
                    for name in benchmark_names
                    if rep.get("drill_benchmarks", {}).get(name) is not None
                },
            }
        )
    return (
        {
            "topic": topics[0] if len(topics) == 1 else topics,
            "measurement_limits": _TOPIC_LIMITS.get(intent.topic),
            "reps": reps,
        }
        if reps
        else None
    )


def current_session_context(request):
    """Build a question-aware snapshot of the active session for every chat turn."""
    evaluation = request.technique_evaluation
    reps = evaluation.get("reps", [])
    brief = build_coaching_brief(request)
    available = {metric.name for metric in request.metrics}
    patterns = {}
    per_rep_findings = []
    for rep in reps:
        available.update(rep.get("measurements", {}).keys())
        for phase in rep.get("phases", {}).values():
            available.update(phase.get("measurements", {}))
        priorities = rep.get("reference_comparison", {}).get("coaching_priorities", [])
        if priorities:
            priority = priorities[0]
            per_rep_findings.append(
                {
                    "rep": rep.get("rep_number"),
                    "timestamp_seconds": round(priority["watch_at_seconds"], 1)
                    if isinstance(priority.get("watch_at_seconds"), (int, float))
                    else None,
                    "observed_difference": priority.get("reason"),
                    "practice_cue": priority.get("what_to_try"),
                }
            )
        for priority in priorities[:1]:
            key = (priority.get("reason", ""), priority.get("what_to_try", ""))
            if not all(key):
                continue
            row = patterns.setdefault(key, {"reps": [], "timestamps_seconds": []})
            row["reps"].append(rep.get("rep_number"))
            time = priority.get("watch_at_seconds")
            if isinstance(time, (int, float)):
                row["timestamps_seconds"].append(round(time, 1))
    top_key, top_pattern = (
        max(patterns.items(), key=lambda item: len(item[1]["reps"])) if patterns else (None, None)
    )
    selected_focus = brief.get("selected_focus") or {}
    observations = [
        item.get("observation") for item in brief.get("patterns", []) if item.get("observation")
    ][:2]
    summary = {
        "current_session_id": request.session_id,
        "session_notes": request.session_notes[:1500],
        "current_clip_reps_detected": len(reps) or brief.get("reviewed_repetition_count", 0),
        "session_measurement_count": len(request.metrics),
        "reference_baselines": evaluation.get("reference_comparison", {}),
        "measured_features_available": sorted(available),
        "capture_context": {
            "evidence_id": f"capture:{request.session_id}",
            **brief.get("capture_context", {}),
        },
        "submitted_feedback": {
            "evidence_id": f"review:{request.session_id}:{request.reviewed_feedback.get('revision', 'submitted')}",
            "feedback": request.reviewed_feedback,
        }
        if request.reviewed_feedback
        else None,
        "supported_current_observations": observations if not reps else [],
        "session_measurements": [
            {
                "evidence_id": metric.metric_id,
                **metric.model_dump(
                    mode="json",
                    include={
                        "metric_id",
                        "name",
                        "value",
                        "unit",
                        "confidence",
                        "start_ms",
                        "end_ms",
                    },
                ),
            }
            for metric in request.metrics
        ],
        "per_rep_reference_findings": per_rep_findings,
        "per_rep_measurements": [
            {
                "rep": rep.get("rep_number"),
                "reference_context": {
                    key: value
                    for key, value in rep.get("reference_comparison", {}).items()
                    if key not in {"rows", "coaching_priorities"}
                },
                "drill_benchmarks": rep.get("drill_benchmarks", {}),
                "finish_seconds": round(rep["lunge_ms"] / 1000, 1)
                if isinstance(rep.get("lunge_ms"), (int, float))
                else None,
                "measures": {
                    name: {
                        "evidence_id": f"rep:{rep.get('rep_number')}:measurement:{name}",
                        "feature": name,
                        "rep": rep.get("rep_number"),
                        "value": m["value"] / 1000
                        if m.get("unit") == "ms" and isinstance(m.get("value"), (int, float))
                        else m.get("value"),
                        "unit": "seconds" if m.get("unit") == "ms" else m.get("unit"),
                        "phase": m.get("phase"),
                        "meaning": m.get("note", ""),
                    }
                    for name, m in rep.get("measurements", {}).items()
                    if isinstance(m, dict) and m.get("value") is not None
                },
                "phases": {
                    name: {
                        "evidence_id": f"rep:{rep.get('rep_number')}:phase:{name}",
                        "phase": name,
                        "rep": rep.get("rep_number"),
                        "interval_seconds": [
                            round(phase["start_ms"] / 1000, 1),
                            round(phase["end_ms"] / 1000, 1),
                        ],
                        "samples": phase.get("sample_count"),
                        "method": phase.get("method"),
                        "units": {
                            key: m.get("unit") for key, m in phase.get("measurements", {}).items()
                        },
                        "ranges": {
                            key: m.get("range")
                            for key, m in phase.get("measurements", {}).items()
                            if m.get("range") is not None
                        },
                        "values": {
                            key: m.get("value") for key, m in phase.get("measurements", {}).items()
                        },
                    }
                    for name, phase in rep.get("phases", {}).items()
                },
                "reference_comparisons": [
                    {
                        "evidence_id": f"rep:{rep.get('rep_number')}:reference:{row.get('phase')}:{row.get('metric')}",
                        "rep": rep.get("rep_number"),
                        **{
                            key: row[key]
                            for key in (
                                "metric",
                                "phase",
                                "unit",
                                "current",
                                "reference_range",
                                "current_range",
                                "direction",
                                "watch_at_seconds",
                            )
                            if key in row
                        },
                        "supported_change": next(
                            (
                                p.get("what_to_try")
                                for p in rep.get("reference_comparison", {}).get(
                                    "coaching_priorities", []
                                )
                                if p.get("phase", "finish") == row.get("phase")
                                and (
                                    p.get("metric") == row.get("metric")
                                    or row.get("metric", "").replace("_", " ")
                                    in p.get("reason", "").lower()
                                )
                            ),
                            None,
                        ),
                    }
                    for row in rep.get("reference_comparison", {}).get("rows", [])
                ],
                "review_checks": rep.get("unavailable", []),
            }
            for rep in reps
        ],
        "question_relevant_focus": {
            key: selected_focus[key]
            for key in ("topic", "observation", "practice_focus", "evidence_ids")
            if selected_focus.get(key) is not None
        }
        if not reps
        else None,
        "recurring_reference_comparison": (
            {
                "observed_difference": top_key[0],
                "practice_cue": top_key[1],
                **top_pattern,
            }
            if top_pattern
            else None
        ),
        "evidence_gap": request.evidence_unavailable_reason[:300] or None,
        "instruction": "Inspect this complete active-session snapshot against the request and recent conversation. Choose the relevant records and matching approved references yourself. Answer with a supported useful cue or qualitative observation, followed by its evidence; general guidance fills remaining gaps.",
    }
    summary["measurement_policy"] = (
        "Phase values are medians in that phase, not whole-clip values. Main measures include their units and phase. Use only matching reference feature and phase; do not confuse front/rear knee or arm direction/elbow bend. Reference overlap supports a matching observed shape, not a perfect whole action. A finish reading does not establish posture at onset or balance."
    )
    summary["feature_meanings"] = {
        "projected_torso_tilt": "Magnitude of lean away from upright in the image plane: SMALLER means MORE upright. A lower value than the reference does not justify telling the athlete to become more upright. It does not identify forward/backward direction or balance.",
        "rear_knee_angle": "Included rear-knee angle: larger/nearer 180 degrees means straighter. This describes rear-leg extension, not pushing force, power or drive completeness.",
        "front_knee_angle": "Included front-knee angle: smaller means more bend. Compare only the matching phase with accepted reference reps; a different angle alone does not grade the whole lunge.",
        "weapon_arm_direction": "Whole sword-arm direction relative to the image horizontal. This is not elbow bend and does not measure extension onset relative to foot movement.",
        "weapon_elbow_angle": "Included sword-elbow bend: larger means straighter. This does not determine whether arm extension started before the front foot.",
        "non_weapon_arm_direction": "Non-sword shoulder-to-wrist direction relative to image horizontal. Do not compare with sword-arm targets.",
        "non_weapon_elbow_angle": "Non-sword elbow bend: larger means straighter. This is not sword-arm extension.",
    }
    # Preserve sided observations even when the phase evaluator supplies other
    # features. Previously all raw metrics disappeared as soon as reps existed.
    for metric, record in zip(request.metrics, summary["session_measurements"], strict=True):
        key = _rep_key(metric)
        record["rep"] = int(key.rsplit(":", 1)[-1]) if key else None
        record["feature"] = metric.name
        record["phase"] = _metric_phase(metric.name)
        if "elbow_angle" in metric.name:
            record["meaning"] = (
                "Included elbow angle on the named anatomical side; larger means straighter. An at_peak reading describes the detected peak, not a phase median or a technique verdict."
            )
        elif "arm_extension" in metric.name:
            record["meaning"] = (
                "Shoulder-to-wrist reach on the named anatomical side in torso lengths; this is not an angle or extension-onset timing."
            )
    return json.dumps(summary, separators=(",", ":"))


def session_evidence_context(
    request, feature_names=(), phase_names=(), rep_numbers=(), snapshot=None
):
    """Select exact records requested by the agent, independent of question categories."""
    packet = json.loads(snapshot if snapshot is not None else current_session_context(request))
    features, phases, numbers = set(feature_names), set(phase_names), set(rep_numbers)
    reference_phases = phases | ({"finish"} if phases & {"lunge_finish", "lunge_hold"} else set())
    selected = []
    for rep in packet["per_rep_measurements"]:
        if numbers and rep["rep"] not in numbers:
            continue
        rep["measures"] = {
            name: record
            for name, record in rep["measures"].items()
            if (not features or name in features) and (not phases or record.get("phase") in phases)
        }
        rep["phases"] = {
            name: {
                **record,
                "values": {
                    feature: value
                    for feature, value in record["values"].items()
                    if not features or feature in features
                },
                "units": {
                    feature: value
                    for feature, value in record.get("units", {}).items()
                    if not features or feature in features
                },
                "ranges": {
                    feature: value
                    for feature, value in record.get("ranges", {}).items()
                    if not features or feature in features
                },
            }
            for name, record in rep["phases"].items()
            if not phases or name in phases
        }
        rep["reference_comparisons"] = [
            record
            for record in rep["reference_comparisons"]
            if (not features or record.get("metric") in features)
            and (not reference_phases or record.get("phase") in reference_phases)
        ]
        selected.append(rep)
    packet["per_rep_measurements"] = selected
    packet["session_measurements"] = [
        record
        for record in packet["session_measurements"]
        if (not features or record["feature"] in features)
        and (not phases or record["phase"] in reference_phases)
        and (not numbers or record["rep"] in numbers)
    ]
    packet["requested_scope"] = {
        "feature_names": list(feature_names),
        "phase_names": list(phase_names),
        "rep_numbers": list(rep_numbers),
    }
    return packet


def baseline_context(request, metric_name="", phase="", rep_number=0):
    """Expose approved reference comparisons without keyword-based question routing."""
    packet = json.loads(current_session_context(request))
    needle = metric_name.strip().lower()
    rows = [
        {**row, "reference_context": rep.get("reference_context", {})}
        for rep in packet["per_rep_measurements"]
        if not rep_number or rep["rep"] == rep_number
        for row in rep["reference_comparisons"]
        if (not needle or needle in row.get("metric", "").lower())
        and (not phase or row.get("phase") == phase)
    ]
    return {
        "current_session_id": request.session_id,
        "reference_baselines": packet["reference_baselines"],
        "comparisons": rows,
        "matching_count": len(rows),
        "measurement_policy": packet["measurement_policy"],
        "feature_meanings": packet["feature_meanings"],
    }


def evaluation_source(request):
    return KnowledgeSource(
        source_id=f"technique:{request.session_id}:{request.technique_evaluation.get('version')}",
        source="Phase-specific reference-rep comparison"
        if request.technique_evaluation.get("coaching_mode") == "reference_comparison"
        else "Automatic basic-lunge rubric evaluation (unvalidated heuristics)",
        text=json.dumps(selected_evaluation(request), separators=(",", ":")),
    )


def coaching_evaluation_context(request):
    """Advice-oriented model context; precise evidence remains in the source panel."""
    selected = selected_evaluation(request)
    if motion_question(request.question):
        return json.dumps(motion_context(request), separators=(",", ":"))
    if request.technique_evaluation.get("coaching_mode") == "reference_comparison":
        context = {"reference_comparisons": reference_context(request, selected)}
        topic_evidence = requested_topic_evidence(request, selected)
        if topic_evidence:
            context["requested_topic_evidence"] = topic_evidence
        if classify_coach_question(request.question).kind == "rep_comparison":
            ranking = rep_comparison_result(request)
            if ranking:
                context["rep_feature_ranking"] = ranking
        return json.dumps(context, separators=(",", ":"))
    if re.search(
        r"\b(?:numbers?|measurements?|angles?|degrees|timings?|timestamps?|values?)\b",
        request.question,
        re.I,
    ):
        return json.dumps(selected, separators=(",", ":"))
    priorities = [
        {
            "rep": f["rep_number"],
            "what_to_try": f["cue"],
            "reason": plain_observation(f),
            "watch_at_seconds": round(f["evidence_ms"] / 1000, 1),
        }
        for f in selected["findings"][:2]
    ]
    return json.dumps(
        {
            "coaching_priorities": priorities,
            "selected_reps": [r["rep_number"] for r in selected["rep_measurements"]],
            "drill_benchmarks": [
                {"rep": r["rep_number"], **r["drill_benchmarks"]}
                for r in selected["rep_measurements"]
            ],
            "benchmark_policy": MOTION_POLICY,
            "checks_available": sorted(
                {
                    key.replace("_", " ")
                    for r in selected["rep_measurements"]
                    for key in r["measurements"]
                }
            ),
            "no_flag_is_not_a_positive_technique_verdict": True,
        },
        separators=(",", ":"),
    )


def _reference_comparison_spec(request):
    intent = classify_coach_question(request.question)
    question = request.question.lower()
    return {
        None: ("front_knee_angle", "finish", "finish depth"),
        "front_leg": ("front_knee_angle", "finish", "front-leg finish bend"),
        "lunge": ("front_knee_angle", "finish", "finish depth"),
        "torso": ("projected_torso_tilt", "finish", "torso position at the finish"),
        "distance": ("feet_separation_leg_lengths", "finish", "finish stance length"),
        "rear_leg": ("rear_knee_angle", "finish", "rear-leg extension at the finish"),
        "arm": (
            "weapon_elbow_angle"
            if re.search(r"\b(extension|extend|elbow|straighten)\b", question)
            else "weapon_arm_direction",
            "finish",
            "sword-arm position at the finish",
        ),
        "recovery": ("rear_knee_angle", "recovery_peak", "rear-leg position during recovery"),
    }.get(intent.topic)


def rep_comparison_result(request):
    """Rank attempts on the asked movement feature, scoped to its evidence."""
    intent = classify_coach_question(request.question)
    question = request.question.lower()
    spec = _reference_comparison_spec(request)
    within_clip = False
    if intent.topic == "speed" or (
        intent.topic == "recovery" and re.search(r"\b(fastest|slowest|fast|slow|quick)\b", question)
    ):
        recovering = intent.topic == "recovery" or bool(re.search(r"\brecover", question))
        metric = "estimated_active_recovery_time" if recovering else "action_projected_hip_speed"
        phase = "active_recovery" if recovering else "lunge_drive"
        scope = "active-recovery time" if recovering else "projected hip movement speed"
        if not recovering and re.search(r"\b(duration|interval|completion|time)\b", question):
            metric = "action_to_lunge_time"
            scope = "action-to-lunge interval"
        spec = (metric, phase, scope)
        within_clip = True
    if not spec:
        return None
    metric, phase, scope = spec

    ranked = []
    reference_range = None
    for rep in selected_evaluation(request)["rep_measurements"]:
        row = None
        if within_clip:
            measure = rep.get("measurements", {}).get(metric)
            if isinstance(measure, dict) and isinstance(measure.get("value"), (int, float)):
                row = {"current": measure["value"], "unit": measure.get("unit")}
        else:
            row = next(
                (
                    item
                    for item in rep.get("reference_comparison", {}).get("rows", [])
                    if item.get("metric") == metric
                    and item.get("phase") == phase
                    and isinstance(item.get("current"), (int, float))
                    and isinstance(item.get("reference_median"), (int, float))
                    and isinstance(item.get("reference_range"), list)
                    and len(item["reference_range"]) == 2
                ),
                None,
            )
        if not row:
            continue
        value = float(row["current"])
        if within_clip:
            score = value
            range_gap = median_gap = 0.0
        else:
            limits = list(map(float, row["reference_range"]))
            reference_range = limits
            median = float(row["reference_median"])
            range_gap = max(limits[0] - value, 0.0, value - limits[1])
            median_gap = abs(value - median)
            score = None
        phase_data = rep.get("phases", {}).get(phase, {})
        timestamp = row.get("watch_at_seconds")
        if timestamp is None and phase_data.get("representative_ms") is not None:
            timestamp = phase_data["representative_ms"] / 1000
        if timestamp is None and rep.get("selected_frame_ms") is not None:
            timestamp = rep["selected_frame_ms"] / 1000
        ranked.append(
            {
                "rep": rep["rep_number"],
                "time_seconds": round(float(timestamp), 1) if timestamp is not None else None,
                "value": value,
                "range_gap": range_gap,
                "median_gap": median_gap,
                "score": score,
            }
        )
    if len(ranked) < 2:
        return None
    if within_clip:
        best = max(ranked, key=lambda item: item["score"])
        worst = min(ranked, key=lambda item: item["score"])
        fastest, slowest = (
            (best, worst) if metric == "action_projected_hip_speed" else (worst, best)
        )
    else:
        # A value in the reference band is closer than one outside it; median
        # distance separates attempts that share the same band status.
        best = min(ranked, key=lambda item: (item["range_gap"], item["median_gap"]))
        worst = max(ranked, key=lambda item: (item["range_gap"], item["median_gap"]))
        fastest = slowest = None
    if best["rep"] == worst["rep"]:
        return None
    return {
        "best": best,
        "worst": worst,
        "rep_count": len(ranked),
        "range": reference_range,
        "metric": metric,
        "scope": scope,
        "basis": "within_clip" if within_clip else "reference_similarity",
        "fastest": fastest,
        "slowest": slowest,
    }


def rep_comparison_fallback(request):
    """Give a concise, evidence-backed answer scoped to the requested feature."""
    result = rep_comparison_result(request)
    if not result:
        return None
    best, worst = result["best"], result["worst"]
    question = request.question.lower()
    asked_fastest = bool(re.search(r"\b(fastest|quickest|shortest)\b", question))
    asked_slowest = bool(re.search(r"\b(slowest|longest)\b", question))
    if result["basis"] == "within_clip" and (asked_fastest or asked_slowest):
        selected = result["fastest"] if asked_fastest else result["slowest"]
        qualifier = "fastest" if asked_fastest else "slowest"
        if selected["time_seconds"] is None:
            return None
        return (
            f"Rep {selected['rep']} had the {qualifier} {result['scope']} in this clip, "
            f"at the {selected['time_seconds']:.1f}-second mark."
        )

    def at_time(row):
        return (
            f" at the {row['time_seconds']:.1f}-second mark"
            if row["time_seconds"] is not None
            else ""
        )

    if result["basis"] == "within_clip":
        return (
            f"Rep {best['rep']} had the highest measured {result['scope']}{at_time(best)}, while "
            f"rep {worst['rep']} had the lowest{at_time(worst)}."
        )
    return (
        f"Rep {best['rep']} was closest to your reference reps for {result['scope']}{at_time(best)}; "
        f"rep {worst['rep']} was furthest for the same feature{at_time(worst)}."
    )


def all_reps_fallback(request):
    """Summarize every rep on the feature the athlete asked about."""
    selected = selected_evaluation(request)["rep_measurements"]
    if not selected:
        return None

    intent = classify_coach_question(request.question)
    if (
        intent.topic in {None, "lunge"}
        and request.technique_evaluation.get("coaching_mode") == "reference_comparison"
    ):
        lines, cues = [], []
        for rep in selected:
            comparison = rep.get("reference_comparison", {})
            priorities = comparison.get("coaching_priorities", [])
            timestamp = rep.get("selected_frame_ms")
            label = f"Rep {rep['rep_number']}"
            if isinstance(timestamp, (int, float)):
                label += f" ({timestamp / 1000:.1f} seconds)"
            if priorities:
                priority = priorities[0]
                cues.append(priority["what_to_try"])
                text = priority["what_to_try"]
            else:
                matched = [
                    row["metric"]
                    for row in comparison.get("rows", [])
                    if row.get("phase") == "finish" and row.get("direction") == "overlaps"
                ]
                names = {
                    "front_knee_angle": "front-leg bend",
                    "rear_knee_angle": "rear-leg extension",
                    "projected_torso_tilt": "torso position",
                }
                matches = [names[name] for name in matched if name in names]
                text = (
                    "Your "
                    + " and ".join(matches[:2])
                    + " at the finish matched your reference examples."
                    if matches
                    else "No specific correction is established by this rep's available reference comparisons."
                )
            lines.append(f"{label}: {text}")
        main_cue = (
            max(set(cues), key=lambda cue: (cues.count(cue), -cues.index(cue)))
            if cues
            else "Keep the finish you used in the reps that matched your reference examples."
        )
        reply = main_cue + "\n\n" + "\n".join(lines)
        if wants_rep_comparison(request.question):
            ranking = rep_comparison_fallback(request)
            if ranking:
                reply += "\n\n" + ranking
        return reply
    spec = _reference_comparison_spec(request)
    within_clip = False
    if intent.topic == "speed":
        metric, phase, scope = "action_projected_hip_speed", "lunge_drive", "relative hip speed"
        within_clip = True
    elif intent.topic == "recovery" and re.search(
        r"\b(fast|slow|quick|time|timing|duration)\b", request.question, re.I
    ):
        metric, phase, scope = (
            "estimated_active_recovery_time",
            "active_recovery",
            "active-recovery time",
        )
        within_clip = True
    elif spec:
        metric, phase, scope = spec
    else:
        metric, phase, scope = None, None, None

    within_values = [
        float(rep["measurements"][metric]["value"])
        for rep in selected
        if within_clip
        and metric in rep.get("measurements", {})
        and isinstance(rep["measurements"][metric].get("value"), (int, float))
    ]
    within_median = median(within_values) if within_values else None
    grouped = {}
    cues = []
    for rep in selected:
        comparison = rep.get("reference_comparison", {})
        row = (
            next(
                (
                    item
                    for item in comparison.get("rows", [])
                    if item.get("metric") == metric and item.get("phase") == phase
                ),
                None,
            )
            if metric and not within_clip
            else None
        )
        measure = rep.get("measurements", {}).get(metric) if metric else None
        if within_clip and measure and isinstance(measure.get("value"), (int, float)):
            value = float(measure["value"])
            if within_median is None:
                observation = f"the {scope} was measured, but there is no clip-wide comparison"
            elif value > within_median:
                observation = f"the {scope} was above this clip's middle value"
            elif value < within_median:
                observation = f"the {scope} was below this clip's middle value"
            else:
                observation = f"the {scope} was near this clip's middle value"
        elif row:
            direction = row.get("direction")
            if not direction and isinstance(row.get("current"), (int, float)):
                limits = row.get("reference_range")
                if isinstance(limits, list) and len(limits) == 2:
                    direction = (
                        "lower"
                        if row["current"] < min(limits)
                        else "higher"
                        if row["current"] > max(limits)
                        else "overlaps"
                    )
            if metric == "front_knee_angle":
                observation = {
                    "higher": "the front leg finished straighter than your reference reps",
                    "lower": "the front leg finished with more bend than your reference reps",
                    "overlaps": "the front-leg finish fell within your reference range",
                }.get(direction, "the front-leg finish did not have a clear reference comparison")
            elif metric == "projected_torso_tilt":
                observation = {
                    "higher": "your torso tilted farther forward than in your reference reps",
                    "lower": "your torso stayed more upright than in your reference reps",
                    "overlaps": "your torso position overlapped your reference range",
                }.get(direction, "your torso finish did not have a clear reference comparison")
            elif metric == "rear_knee_angle":
                observation = {
                    "higher": "your rear leg was straighter than in your reference reps",
                    "lower": "your rear leg was more bent than in your reference reps",
                    "overlaps": "your rear-leg position overlapped your reference range",
                }.get(direction, "your rear-leg position did not have a clear reference comparison")
            elif metric == "weapon_elbow_angle":
                observation = {
                    "higher": "your sword arm was straighter than in your reference reps",
                    "lower": "your sword arm was more bent than in your reference reps",
                    "overlaps": "your sword-arm bend overlapped your reference range",
                }.get(
                    direction, "your sword-arm extension did not have a clear reference comparison"
                )
            elif metric == "weapon_arm_direction":
                observation = "your sword-arm direction differed from your reference reps"
            elif metric == "feet_separation_leg_lengths":
                observation = {
                    "higher": "your feet finished farther apart than your reference reps",
                    "lower": "your feet finished closer together than your reference reps",
                    "overlaps": "your finish stance length overlapped your reference range",
                }.get(
                    direction, "your finish stance length did not have a clear reference comparison"
                )
            else:
                observation = f"the {scope} differed from your reference reps"
        else:
            observation = f"no phase-matched {scope or 'movement'} comparison was available"

        priority = next(
            (
                item
                for item in comparison.get("coaching_priorities", [])
                if metric and metric.replace("_", " ") in item.get("reason", "").lower()
            ),
            {},
        )
        if priority.get("what_to_try"):
            cues.append(priority["what_to_try"].strip())
        phase_data = rep.get("phases", {}).get(phase or "", {})
        timestamp = row.get("watch_at_seconds") if row else None
        if timestamp is None and phase_data.get("representative_ms") is not None:
            timestamp = phase_data["representative_ms"] / 1000
        if timestamp is None and rep.get("selected_frame_ms") is not None:
            timestamp = rep["selected_frame_ms"] / 1000
        label = str(rep["rep_number"])
        if isinstance(timestamp, (int, float)):
            label += f" ({timestamp:.1f} seconds)"
        grouped.setdefault(observation, []).append(label)

    distinct_cues = list(dict.fromkeys(cue for cue in cues if cue))
    topic_cues = {
        "arm": "Finish by sending your sword hand toward the target; compare the arm line at each finish.",
        "front_leg": "Use the front-leg bend in your reference finish as your target for each rep.",
        "rear_leg": "Drive through the rear leg and finish long, matching the reference shape.",
        "torso": "Keep your torso upright through the finish, using your reference reps as the guide.",
        "recovery": "Return under control and compare the recovery shape with your reference rep.",
        "distance": "Use your reference finish spacing as a guide rather than chasing extra distance.",
        "speed": "Compare the quicker controlled drives within this clip; these image-based speeds are relative to this setup.",
        "lunge": "Use the front-leg bend in your reference finish as your target for each rep.",
    }
    opening = topic_cues.get(
        intent.topic,
        "Use the front-leg bend in your reference finish as your target for each rep.",
    )
    if intent.topic == "recovery":
        matched = next(
            (
                labels
                for observation, labels in grouped.items()
                if "rear-leg position overlapped" in observation
            ),
            [],
        )
        differed = [
            label
            for observation, labels in grouped.items()
            if "your rear leg was" in observation
            for label in labels
        ]
        parts = []
        if matched:
            parts.append(
                f"Rep {', '.join(matched)} matched your reference for rear-leg shape during recovery"
            )
        if differed:
            parts.append(
                f"Rep {', '.join(differed)} were less aligned: your rear leg was straighter at the recovery peak"
            )
        if parts:
            opening = (
                ". ".join(parts)
                + ". Try matching the rear-leg bend in your accepted reference recoveries as you return to guard."
            )
    if len(distinct_cues) == 1:
        if intent.topic != "recovery":
            opening = distinct_cues[0]
    elif distinct_cues and intent.topic != "recovery":
        opening = "The reps have different priorities, so use the cue listed with each one."
    lines = []
    phase_label = {
        "finish": "lunge finish",
        "lunge_finish": "lunge finish",
        "lunge_hold": "held finish",
        "active_recovery": "active recovery",
        "recovery_peak": "recovery peak",
        "returned_guard": "returned guard",
        "starting_guard": "starting guard",
        "lunge_drive": "lunge drive",
    }.get(phase)
    for observation, labels in grouped.items():
        noun = "Rep" if len(labels) == 1 else "Reps"
        phase_text = f" at the {phase_label}" if phase_label else ""
        lines.append(f"{noun} {', '.join(labels)}: {observation}{phase_text}.")
    return opening + "\n\n" + "\n".join(lines)


def session_evidence_fallback(request):
    """Build a safe answer from the requested feature when model review cannot.

    This is a shared recovery path for citation/schema failures, not a template for
    a particular question. It scopes to the same selected reps, builds a separate
    evidence summary for each explicitly joined movement feature, and never turns
    a missing comparison into a corrective verdict.
    """
    if request.technique_evaluation.get("coaching_mode") != "reference_comparison":
        return evaluation_fallback(request)

    intent = classify_coach_question(request.question)
    if intent.kind == "rep_comparison":
        return rep_comparison_fallback(request)

    selected = selected_evaluation(request)["rep_measurements"]
    if not selected:
        return None

    topics = question_topics(request.question)
    if not topics and intent.topic:
        topics = [intent.topic]
    if not topics:
        topics = ["lunge"]
    if len(topics) > 1 and not re.search(
        r"\b(?:and|both|as well as)\b|[,/]", request.question, re.I
    ):
        topics = [intent.topic or topics[0]]

    wanted_reps = {rep["rep_number"] for rep in selected}
    evaluation = request.technique_evaluation
    scoped_evaluation = {
        **evaluation,
        "reps": [rep for rep in evaluation.get("reps", []) if rep.get("rep_number") in wanted_reps],
    }
    labels = {
        "arm": "arm",
        "front_leg": "front leg",
        "rear_leg": "rear leg",
        "torso": "torso",
        "recovery": "recovery",
        "speed": "speed",
        "distance": "distance",
        "lunge": "lunge",
    }
    answers = []
    for topic in topics:
        focused = request.model_copy(
            update={
                "question": f"How was my {labels.get(topic, topic)} in this session?",
                "technique_evaluation": scoped_evaluation,
            }
        )
        answer = all_reps_fallback(focused)
        if answer:
            answers.append(answer)
    if answers:
        return "\n\n".join(answers)
    return evaluation_fallback(request)


def evaluation_fallback(request):
    selected = selected_evaluation(request)
    intent = classify_coach_question(request.question)
    comparisons = reference_context(request, selected)
    if request.technique_evaluation.get("coaching_mode") == "reference_comparison":
        for comparison in comparisons:
            if motion_question(request.question) and re.search(
                r"\b(?:distance|disatnce|reach|stride|long|far)\b", request.question, re.I
            ):
                row = next(
                    (
                        r
                        for r in comparison.get("comparisons", [])
                        if r["metric"] == "feet_separation_leg_lengths"
                    ),
                    None,
                )
                if row:
                    relation = (
                        "shorter"
                        if row["current"] < row["reference_range"][0]
                        else "longer"
                        if row["current"] > row["reference_range"][1]
                        else "within the reach range"
                    )
                    return (
                        "Use your reference reps to rehearse the same reach with a controlled landing. "
                        f"Your tracked feet separation is {relation} compared with those examples; "
                        "compare the finishes before deciding whether to change the step."
                    )
            if comparison.get("coaching_priorities") and not motion_question(request.question):
                priority = comparison["coaching_priorities"][0]
                return (
                    f"{priority['what_to_try']} {priority['reason']} "
                    f"Compare your finish around {priority['watch_at_seconds']:.1f} seconds with the reference reps."
                )
    if motion_question(request.question):
        reps = selected["rep_measurements"]
        if len(reps) == 1:
            rep = reps[0]
            benchmark = rep.get("drill_benchmarks", {})
            reach = benchmark.get("reach", {})
            timing = benchmark.get("timing", {})
            if (
                re.search(
                    r"\b(?:distance|disatnce|reach|stride|long|far)\b", request.question, re.I
                )
                and reach.get("status") == "estimated"
            ):
                return (
                    "Aim for a repeatable reach and a controlled landing, using your good reps as the reference. "
                    f"Rep {rep['rep_number']}'s tracked feet separation is about {reach['feet_separation_leg_lengths']:.1f} leg lengths; "
                    "your approximate drill guide is two leg lengths."
                )
            if (
                timing.get("category") == "slow"
                and re.search(r"benchmark|drill target|timing target", request.question, re.I)
                and re.search(r"\b(?:fast|speed|slow)\b", request.question, re.I)
            ):
                return (
                    "For your speed drill, try a more decisive drive into the same lunge finish. "
                    f"Rep {rep['rep_number']} takes about {timing['duration_seconds']:.1f} seconds from tracked front-foot lift to stability, "
                    "which is above your 0.5-second drill benchmark."
                )
        speeds = [
            r
            for r in request.technique_evaluation.get("reps", [])
            if "action_projected_hip_speed" in r["measurements"]
        ]
        if len(reps) == 1 and "action_projected_hip_speed" in reps[0]["measurements"]:
            rep = reps[0]
            speed = rep["measurements"]["action_projected_hip_speed"]["value"]
            others = [r for r in speeds if r["rep_number"] != rep["rep_number"]]
            if others and all(
                speed < r["measurements"]["action_projected_hip_speed"]["value"] for r in others
            ):
                return (
                    f"Rep {rep['rep_number']} has lower tracked hip speed than your other reps in this recording. "
                    "Try repeating the same target and lunge distance with a more decisive rear-leg drive, then compare the movement. "
                    "That comparison describes relative motion; it doesn't measure power or establish whether you're fast enough."
                )
        return (
            "We can compare tracked hip motion and action timing across your reps, but those don't measure force or distance in metres. "
            "For a useful comparison, repeat the same target and intended lunge distance rather than chasing a universal speed target."
        )
    findings = selected["findings"]
    if intent.topic not in {None, "lunge"}:
        names = _TOPIC_MEASUREMENTS.get(intent.topic, set())
        findings = [
            f
            for f in findings
            if any(name.replace("_", " ") in f.get("observation", "").lower() for name in names)
        ]
    if findings:
        f = findings[0]
        return f"{f['cue']} {plain_observation(f)} You can check this in rep {f['rep_number']} around {f['evidence_ms'] / 1000:.1f} seconds. Repeat a few slow lunges and compare the finish to see whether that cue changes the movement."
    if intent.topic not in {None, "lunge"}:
        return None  # Let the caller use relevant instruction rather than an unrelated correction.
    if selected["rep_measurements"] and all(
        r.get("status") == "unavailable" for r in selected["rep_measurements"]
    ):
        return (
            "For your next set, try a slow lunge and a deliberate return to the same guard. "
            "Watch the finish and recovery side by side, choosing one movement cue to work on before adding speed."
        )
    return (
        "Try a slow repeat toward the same target, then compare your finish and return to guard. "
        "Treat this as a practice experiment: choose one cue and see whether it makes the movement easier to repeat."
    )


def evaluation_issues(request, reply, metrics):
    from fencecoach.coach.grounding import unsupported_claims

    selected = selected_evaluation(request)
    findings = selected["findings"]
    rules = {f["rule"] for f in findings}
    allowed = set()
    if selected["rep_measurements"]:
        allowed.add("Describe measured intervals, not a verified action count.")
    if "front_knee_shallow" in rules:
        allowed.add("Knee-depth corrections are not established by these measurements.")
    if any(
        "front-leg bend" in p["what_to_try"]
        for r in selected["rep_measurements"]
        for p in r.get("reference_comparison", {}).get("coaching_priorities", [])
    ):
        allowed.add("Knee-depth corrections are not established by these measurements.")
    issues = [i for i in unsupported_claims(reply, metrics) if i not in allowed]
    if (
        any(
            "action_projected_hip_speed" in r["measurements"]
            for r in selected_evaluation(request)["rep_measurements"]
        )
        and re.search(
            r"(?:don't have|do not have|no|without|lack).{0,30}speed measurements", reply, re.I
        )
        and not re.search(r"(?:physical|absolute|calibrated|metres|meters|m/s)", reply, re.I)
    ):
        issues.append(
            "Relative hip-speed measurements are available; do not deny all speed evidence."
        )
    if "A reported measurement or timestamp is absent from supplied evidence." in issues:
        values = [float(m.value) for m in metrics]
        values += [float(m.value) / 1000 for m in metrics if m.unit == "ms"]
        values += [t / 1000 for m in metrics for t in (m.start_ms, m.end_ms) if t is not None]
        for rep in request.technique_evaluation.get("reps", []):
            for row in rep.get("reference_comparison", {}).get("rows", []):
                values.extend(
                    v
                    for k in ("current", "reference_median", "difference", "watch_at_seconds")
                    if isinstance((v := row.get(k)), (int, float))
                )
                for range_name in ("reference_range", "current_range"):
                    values.extend(
                        value
                        for value in row.get(range_name, [])
                        if isinstance(value, (int, float))
                    )
            benchmark = rep.get("drill_benchmarks", {})
            timing = benchmark.get("timing", {})
            if timing.get("duration_seconds") is not None:
                values.append(timing["duration_seconds"])
            values.extend([0.4, 0.5])
            for m in rep["measurements"].values():
                values.extend([m["value"], m["time_ms"] / 1000])
                if m["unit"] == "ms":
                    values.append(m["value"] / 1000)
            for phase in rep.get("phases", {}).values():
                values.extend([phase["start_ms"] / 1000, phase["end_ms"] / 1000])
                values.extend(m["value"] for m in phase["measurements"].values())
        numbers = re.findall(
            r"(?<![\w-])(\d+(?:\.\d+)?)\s*(?:degrees?|deg\b|°|ratio\b|milliseconds|ms\b|seconds|s\b)",
            reply.lower(),
        )
        if all(any(abs(float(n) - v) <= max(0.1, abs(v) * 0.01) for v in values) for n in numbers):
            issues.remove("A reported measurement or timestamp is absent from supplied evidence.")
    if re.search(
        r"\b(?:perfect|flawless|definitely correct|proves|too slow|too fast|unpowerful|unexplosive|lacks? (?:power|explosiveness)|not (?:powerful|explosive)|lost balance|heel lifted|heel lifts)\b",
        reply,
        re.I,
    ):
        issues.append(
            "Automatic rubric findings do not establish a global verdict, speed target, balance or foot contact."
        )
    return issues
