"""Application-owned conversation scope and measured-only, pre-call evidence.

No answer selection, prose validation or revision loop. Library material is kept
separate from athlete measurements, including when tracking is unsupported.
"""

from __future__ import annotations

import hashlib
import json
import re
from copy import deepcopy

from fencecoach.coach.intent import (
    PHASE_QUALIFIER,
    arm_roles,
    mentioned_rep_numbers,
    question_topics,
    wants_all_reps,
    wants_rep_comparison,
)
from fencecoach.coach.packet_meaning import assessments, describe
from fencecoach.rag.knowledge import search_knowledge
from fencecoach.schemas import DialogueState

ORDINALS = {
    word: index
    for index, word in enumerate(
        (
            "first",
            "second",
            "third",
            "fourth",
            "fifth",
            "sixth",
            "seventh",
            "eighth",
            "ninth",
            "tenth",
        ),
        1,
    )
}
FEATURES = {
    "arm": ("weapon_elbow_angle", "weapon_arm_direction"),
    "front_leg": ("front_knee_angle", "front_knee_ahead_of_toe"),
    "rear_leg": ("rear_knee_angle",),
    "torso": ("projected_torso_tilt", "forward_torso_pitch_change"),
    "speed": ("action_to_lunge_time", "action_projected_hip_speed"),
    "recovery": ("estimated_active_recovery_time", "finish_to_guard_time"),
    "distance": ("feet_separation", "feet_separation_leg_lengths"),
    "overview": ("weapon_elbow_angle", "front_knee_angle", "action_to_lunge_time"),
    "lunge": ("weapon_elbow_angle", "front_knee_angle", "action_to_lunge_time"),
}
QUERIES = {
    "arm": "sword weapon arm extension direction elbow lunge",
    "front_leg": "front knee bend leg lunge posture",
    "rear_leg": "rear back leg knee extension propulsion lunge",
    "torso": "torso posture upright back lean lunge",
    "speed": "lunge speed timing body projected measurement",
    "recovery": "recovery returning lunge en garde",
    "distance": "lunge distance stride feet separation",
    "overview": "lunge teaching technique review",
    "lunge": "lunge teaching technique review",
    "blade": "blade point control tracking weapon",
    "force": "rear leg propulsion force measurement",
    "fleche": "fleche running attack front rear leg crossing",
}
MEANINGS = {
    "weapon_elbow_angle": "Included weapon-elbow angle; larger means straighter, not earlier extension or better technique.",
    "weapon_arm_direction": "Weapon-arm direction relative to image horizontal; not elbow bend or blade tracking.",
    "front_knee_angle": "Included front-knee angle; smaller means more bend, not automatically better technique.",
    "rear_knee_angle": "Included rear-knee angle; larger means straighter, not pushing force or power.",
    "projected_torso_tilt": "Magnitude away from image upright; smaller means more upright. Not spinal shape, balance or forward direction.",
    "forward_torso_pitch_change": "Projected torso pitch change, not a diagnosis of back posture.",
    "action_to_lunge_time": "Action-anchor to lunge bookmark interval; not front-foot-lift to sustained stable finish.",
    "action_projected_hip_speed": "Image-plane hip speed in torso lengths per second; not calibrated metres per second or sword speed.",
    "estimated_active_recovery_time": "Estimated backward hip-motion onset to return bookmark; not the entire hold plus recovery.",
    "finish_to_guard_time": "Lunge-finish to guard interval including any hold; not active recovery speed.",
}


def _explicit_topics(text):
    if re.search(r"\b(?:blade|point control|parry)\b", text, re.I):
        return ["blade"]
    if re.search(
        r"\b(?:force|push(?:ed|ing)?\s+hard|how\s+hard\s+did\s+i\s+push|"
        r"did\s+i\s+drive|how\s+much\s+power|how\s+strong\s+was\s+my\s+push)\b",
        text,
        re.I,
    ):
        return ["force"]
    if re.search(r"\bfl[eèé]che\b", text, re.I):
        specific = [t for t in question_topics(text) if t not in {"lunge", "overview"}]
        return specific or ["fleche"]
    if re.search(r"\b(?:overall|how did i do|actually know|whole session)\b", text, re.I):
        return ["overview"]
    topics = question_topics(text)
    if not topics and re.search(r"\bdrills?\b", text, re.I):
        return ["drill"]
    if re.search(r"\b(?:knees|legs)\b", text, re.I) and not re.search(
        r"\b(?:front|rear|back|lead)\s+(?:knee|leg)", text, re.I
    ):
        topics = [t for t in topics if t not in {"front_leg", "rear_leg"}] + [
            "front_leg",
            "rear_leg",
        ]
    return topics


def _explicit_phases(text):
    # A named temporal qualifier scopes the topic; 'my recovery' names a topic.
    patterns = (
        ("starting_guard", r"\b(?:starting|initial) guard\b|\bstart of (?:the )?lunge\b"),
        ("recovery_peak", r"\b(?:recovery peak|peak of (?:the )?recovery)\b"),
        ("returned_guard", r"\b(?:returned guard|return(?:ed)? to guard)\b"),
        (
            "active_recovery",
            r"\b(?:during|at|in) (?:the )?(?:active )?recovery\b|\bactive recovery\b",
        ),
        ("lunge_drive", r"\b(?:lunge drive|during (?:the )?drive)\b"),
        ("lunge_hold", r"\b(?:lunge hold|held lunge|hold phase)\b"),
        (
            "lunge_finish",
            r"\b(?:lunge finish|at (?:the )?finish|finish position|the finish|^finish$)\b",
        ),
    )
    phases = [name for name, pattern in patterns if re.search(pattern, text, re.I)]
    if "recovery_peak" in phases and "active_recovery" in phases:
        phases.remove("active_recovery")
    return phases


def _open_evaluation(text):
    return bool(
        re.fullmatch(
            r"(?:is it good|how did i do|what should i improve|what should i focus on)[.!?]*",
            text.strip(),
            re.I,
        )
    )


def _resolve(text, state, rep_ids):
    state = state.model_copy(deep=True)
    state.turn_type = "coaching"
    state.assumption_note = ""
    state.resolution_confidence = "high"
    text = re.sub(r"\bback\s+to\s+", "", text, flags=re.I)
    normalized = text.strip().lower().rstrip(".!?")
    if normalized in {"start over", "reset conversation", "new conversation"}:
        state = DialogueState(
            session_id=state.session_id,
            core_version="new2",
            turn_type="restart",
            history_reset=True,
        )
        return state
    if re.fullmatch(r"(?:hi|hey|hello|good morning|good evening)", normalized):
        state.turn_type = "greeting"
        return state
    if re.fullmatch(
        r"(?:thanks|thank you|thank you so much|ok|okay|got it|great|cool)(?: thanks)?", normalized
    ):
        state.turn_type = "acknowledgment"
        return state
    if re.search(r"\bwhat can you (?:tell|say).*session", normalized):
        text = "whole session overview"
        state.turn_type = "session_summary"
    prior_topics = list(state.topics)
    if re.search(r"\bfl[eèé]che\b", text, re.I):
        state.movement = "fleche"
    elif re.search(r"\badvance\b", text, re.I):
        state.movement = "advance"
    elif re.search(r"\bretreat\b", text, re.I):
        state.movement = "retreat"
    elif re.search(r"\blunges?\b", text, re.I):
        state.movement = "lunge"
    clarification = state.open_clarifying_question
    # Clarification ordinals select options before they can be read as reps.
    if clarification:
        options = clarification.get("options", [])
        chosen = next((o for o in options if text.strip().lower() == o["label"].lower()), None)
        match = re.fullmatch(
            r"(?:the )?(first|second|third)(?: one| option)?(?: please)?[.!?]?", text.strip(), re.I
        )
        if match and ORDINALS[match[1].lower()] <= len(options):
            chosen = options[ORDINALS[match[1].lower()] - 1]
        if chosen:
            state.topics = list(chosen.get("topics", state.topics))
            state.phases = list(chosen.get("phases", state.phases))
            state.rep_numbers = list(chosen.get("rep_numbers", state.rep_numbers))
            state.current_topic = ", ".join(state.topics)
            state.subject = chosen["label"]
            state.open_clarifying_question = None
            return state
    phase_qualifier = PHASE_QUALIFIER.search(text)
    topic_text = PHASE_QUALIFIER.sub("", text) if phase_qualifier else text
    topics = _explicit_topics(topic_text)
    if (
        topics == ["distance"]
        and "front_leg" in prior_topics
        and re.search(r"\b(?:deep(?:er)?|shallow(?:er)?|bend|bent)\b", text, re.I)
    ):
        topics.append("front_leg")
    # Topic ontology order is not presentation order. Sort by the earliest
    # independently resolved span of the user's alternatives.
    if " or " in text.lower():
        presented = []
        for option in re.split(r"\bor\b", topic_text, flags=re.I):
            for topic in _explicit_topics(option):
                if topic in topics and topic not in presented:
                    presented.append(topic)
        topics = presented + [t for t in topics if t not in presented]
    # Open evaluations with no established subject are clarified in the packet.
    if _open_evaluation(text):
        topics = []
    # A bare recovery question is a topic switch, a temporal qualifier is not.
    if not topics and not prior_topics and not _open_evaluation(text):
        topics = _explicit_topics(text)
    if topics:
        if re.search(r"\bor\b", text, re.I) and len(topics) in {2, 3}:
            state.open_clarifying_question = {
                "question": "Which would you like to review?",
                "options": [{"label": t.replace("_", " "), "topics": [t]} for t in topics],
            }
            state.resolution_confidence = "low"
            state.current_topic = ", ".join(topics)
            return state
        state.topics = topics
        state.subject = ", ".join(topics)
        if topics != prior_topics:
            state.phases = []
            state.last_cited_evidence = []
        state.open_clarifying_question = None
    phases = _explicit_phases(text)
    if phases:
        state.phases = phases
    elif "recovery" in state.topics:
        state.phases = ["active_recovery"]
    if "lunge_hold" in state.phases and "lunge_finish" in state.phases:
        state.phases.remove("lunge_finish")
    numbers = sorted(mentioned_rep_numbers(text))
    for word, number in ORDINALS.items():
        if re.search(rf"\b{word}\s+(?:rep(?:etition)?|lunge|one)\b", text, re.I):
            numbers = [number]
    if re.search(r"\b(?:last|final)\s+(?:rep|lunge|one)\b", text, re.I):
        numbers = [max(rep_ids)] if rep_ids else []
    all_reps = (
        wants_all_reps(text)
        or wants_rep_comparison(text)
        or bool(
            re.search(
                r"\b(?:across|during|throughout|in) (?:this |the |my )?(?:session|drill|set)\b",
                text,
                re.I,
            )
        )
    )
    if numbers:
        state.rep_numbers, state.all_reps = numbers, False
    elif all_reps or "overview" in topics:
        state.rep_numbers, state.all_reps = [], True
    # Topic changes retain an explicitly selected rep, but broad session scope clears it.
    state.arm_roles = list(arm_roles(text)) or state.arm_roles
    if re.search(r"\b(?:generally|in general)\b", text, re.I):
        state.scope = "general"
    elif topics or numbers or all_reps:
        state.scope = "session"
    if not state.topics:
        if re.search(r"\b(?:hi|hello|thanks|thank you)\b", text, re.I):
            state.topics = ["conversation"]
        elif _open_evaluation(text):
            state.open_clarifying_question = {
                "question": "Do you mean your weapon arm, front leg, or recovery?",
                "options": [
                    {"label": label, "topics": [topic]}
                    for label, topic in (
                        ("weapon arm", "arm"),
                        ("front leg", "front_leg"),
                        ("recovery", "recovery"),
                    )
                ],
            }
            state.resolution_confidence = "low"
        else:
            state.open_clarifying_question = None
    elif not topics and not numbers and not phases and not state.open_clarifying_question:
        state.resolution_confidence = "moderate"
        state.assumption_note = "Assuming you mean " + state.current_topic.replace("_", " ") + "."
    state.current_topic = ", ".join(state.topics)
    return state


def resolve_scope(request, snapshot):
    rep_ids = sorted(
        {r["rep"] for r in snapshot.get("per_rep_measurements", []) if r.get("rep") is not None}
    )
    state = request.dialogue_state
    if state is None or state.session_id != request.session_id or state.core_version != "new2":
        state = DialogueState(session_id=request.session_id, core_version="new2")
        for message in request.conversation_history:
            if message.role == "user":
                state = _resolve(message.content, state, rep_ids)
    return _resolve(request.question, state, rep_ids)


SCOPED_SOURCES = {
    "arm": {"lunge_arm_roles.md", "pose_measurements.md"},
    "front_leg": {
        "solo_lunge_review_rubric.md",
        "lunge_teaching_reference.md",
        "pose_measurements.md",
    },
    "rear_leg": {
        "rear_leg_propulsion_reference.md",
        "solo_lunge_review_rubric.md",
        "lunge_teaching_reference.md",
    },
    "torso": {"pose_measurements.md", "solo_lunge_review_rubric.md"},
    "speed": {"lunge_speed_reference.md", "pose_measurements.md"},
    "recovery": {"recovery_basics.md", "recovery_measurements.md"},
    "blade": {"pose_measurements.md"},
    "force": {"rear_leg_propulsion_reference.md", "pose_measurements.md"},
    "distance": {"pose_measurements.md", "guard_width_reference.md"},
    "overview": {"solo_lunge_review_rubric.md", "lunge_teaching_reference.md"},
    "lunge": {"solo_lunge_review_rubric.md", "lunge_teaching_reference.md"},
}
PARAGRAPHS = {
    "arm": r"\barm|elbow|wrist",
    "torso": r"torso tilt|spinal",
    "speed": r"\bspeed|timing",
    "blade": r"blade|weapon tracking",
    "force": r"force|power",
    "front_leg": r"knee",
    "distance": r"separation|width",
}


TOPIC_TEXT = {
    **PARAGRAPHS,
    "rear_leg": r"rear|back leg",
    "front_leg": r"front|lead|knee angle",
    "recovery": r"recover|return.*guard",
    "overview": r".",
    "lunge": r".",
}


def _teaching(query, named_item=None, topics=(), movement=""):
    try:
        docs = search_knowledge(query, limit=60)
    except Exception as exc:
        return [{"lookup_error": type(exc).__name__}]
    if named_item:
        terms = set(re.findall(r"[a-z]+", named_item.lower()))
        docs = [d for d in docs if terms <= set(re.findall(r"[a-z]+", d.text.lower()))]
    else:
        allowed = (
            {"fleche_reference.md", "fleche_timing_reference.md"}
            if movement == "fleche" or "fleche" in topics
            else set().union(*(SCOPED_SOURCES.get(t, set()) for t in topics))
        )
        docs = [
            d
            for d in docs
            if not d.source_id.split("#")[0].endswith(".md") or d.source_id.split("#")[0] in allowed
        ]
    rows = []
    for doc in docs[:2]:
        # URLs and source bibliographies add irrelevant numbers and context.
        body = re.split(r"\n(?:Sources?:|https?://)", doc.text, maxsplit=1)[0]
        body = re.sub(r"https?://\S+", "", body)
        if doc.source_id.split("#")[0] in {"pose_measurements.md", "solo_lunge_review_rubric.md"}:
            pattern = "|".join(TOPIC_TEXT[t] for t in topics if t in TOPIC_TEXT)
            fragments = re.split(
                r"(?<=[.!?])\s+(?=[A-Z])", re.sub(r"(?m)^#.*$", "", body).replace("\n", " ")
            )
            body = " ".join(
                p
                for p in fragments
                if pattern
                and re.search(pattern, p, re.I)
                and not re.search(
                    r"user's chosen|submitted feedback|reference-rated|intentional errors", p, re.I
                )
            )
        if not body.strip():
            continue
        rows.append(
            {
                "source_id": doc.source_id,
                "kind": "general teaching material, not an athlete target",
                "text": body[:750],
            }
        )
    return rows


def build_packet(request, state, snapshot, *, conversation_only=False):
    topics = state.topics
    overview_for_clarification = (
        conversation_only
        and not topics
        and state.turn_type == "coaching"
        and _open_evaluation(request.question)
    )
    measurement_topics = ["overview"] if overview_for_clarification else topics
    selected_features = set().union(*(set(FEATURES.get(topic, ())) for topic in measurement_topics))
    if "arm" in topics and state.arm_roles == ["non_weapon"]:
        selected_features = {f.replace("weapon_", "non_weapon_", 1) for f in selected_features}
    all_reps = snapshot.get("per_rep_measurements", [])
    available_reps = sorted({r["rep"] for r in all_reps if r.get("rep") is not None})
    requested = state.rep_numbers
    chosen = all_reps  # Relative comparisons need every comparable rep, even for a selected rep.
    phases = state.phases
    # Unqualified finish questions include both producer finish labels. Keep
    # each reading's actual phase, including clips with mixed finish/hold reps.
    if (not phases or set(phases) <= {"lunge_finish", "lunge_hold"}) and not (
        _explicit_phases(request.question) or "speed" in topics
    ):
        features_by_phase = {
            phase: any(
                (record.get("phase") == phase and feature in selected_features)
                for rep in chosen
                for feature, record in rep.get("measures", {}).items()
            )
            or any(
                selected_features.intersection(
                    rep.get("phases", {}).get(phase, {}).get("values", {})
                )
                for rep in chosen
            )
            for phase in ("lunge_finish", "lunge_hold")
        }
        available_finish_phases = [phase for phase, present in features_by_phase.items() if present]
        if available_finish_phases:
            phases = state.phases = available_finish_phases
    if not phases and selected_features and state.movement not in {"fleche", "advance", "retreat"}:
        available_phases = {p for r in chosen for p in r.get("phases", {})}
        preferred = (
            "lunge_drive"
            if "speed" in topics
            else next((p for p in ("lunge_finish", "lunge_hold") if p in available_phases), None)
        )
        if preferred:
            phases = [preferred]
            state.phases = phases
    snapshot_hash = hashlib.sha256(
        json.dumps(
            [snapshot, request.evidence_unavailable_reason, request.capture_profile], sort_keys=True
        ).encode()
    ).hexdigest()
    cached = state.last_packet if state.packet_snapshot_hash == snapshot_hash else None
    same_scope = (
        cached
        and cached.get("scope", {}).get("topics") == topics
        and cached["scope"].get("phases") == state.phases
        and cached["scope"].get("rep_numbers") == requested
        and cached["scope"].get("movement") == state.movement
        and cached.get("query_scope") == state.scope
    )
    availability = "measurements_available"
    warning = request.evidence_unavailable_reason.strip()
    quality = request.technique_evaluation.get("whole_clip_quality")
    local_geometry = any(
        rep.get("status") not in {"unsupported", "unavailable"}
        and rep.get("geometry_available", True)
        and rep.get("measurements")
        for rep in request.technique_evaluation.get("reps", [])
    )
    if warning or (quality in {"unsupported", "rejected"} and not local_geometry):
        availability = "tracking_unsupported"
    elif not any(r.get("measures") or r.get("phases") for r in all_reps) and not snapshot.get(
        "session_measurements"
    ):
        availability = "none"
    measurements = []
    movement_mismatch = state.movement in {"fleche", "advance", "retreat"} and not any(
        state.movement in phase for rep in chosen for phase in rep.get("phases", {})
    )
    if (
        availability == "measurements_available"
        and state.scope != "general"
        and not movement_mismatch
    ):
        for rep in chosen:
            for feature in sorted(selected_features):
                if feature not in selected_features:
                    continue
                record = rep.get("measures", {}).get(feature)
                phase_record = next(
                    (
                        rep.get("phases", {}).get(p)
                        for p in phases
                        if feature in rep.get("phases", {}).get(p, {}).get("values", {})
                    ),
                    None,
                )
                if record and (not record.get("phase") or not phases or record["phase"] in phases):
                    item = {
                        k: record.get(k)
                        for k in ("evidence_id", "feature", "rep", "phase", "value", "unit")
                    }
                elif phase_record:
                    item = {
                        "evidence_id": f"{phase_record['evidence_id']}:{feature}",
                        "feature": feature,
                        "rep": rep["rep"],
                        "phase": phase_record["phase"],
                        "value": phase_record["values"][feature],
                        "unit": phase_record.get("units", {}).get(feature),
                    }
                else:
                    continue
                if item["value"] is not None:
                    measurements.append(item)
        # Raw sided arm samples are preserved only for the declared role and exact rep.
        if "arm" in topics:
            side = request.capture_profile.get("weapon_arm")
            if state.arm_roles == ["non_weapon"] and side in {"left", "right"}:
                side = "left" if side == "right" else "right"
            for row in snapshot.get("session_measurements", []):
                if (
                    "arm_extension" not in row.get("feature", "")
                    or side not in {"left", "right"}
                    or not row["feature"].startswith(side + "_")
                ):
                    continue
                if phases and row.get("phase") not in phases:
                    continue
                measurements.append(
                    {
                        k: row.get(k)
                        for k in ("evidence_id", "feature", "rep", "phase", "value", "unit")
                    }
                )
    # Keep all matching reps for relative arithmetic; the writer sees only the selected
    # rows plus compact comparison objects, never a silently truncated comparison.
    measurements = sorted(measurements, key=lambda r: (r["feature"], r.get("rep") or 0))
    reference_comparisons = []
    reference_contexts = []
    if availability == "measurements_available" and state.scope != "general":
        for rep in chosen:
            if requested and rep["rep"] not in requested:
                continue
            context = rep.get("reference_context", {})
            if context.get("status") != "available":
                continue
            for reference in rep.get("reference_comparisons", []):
                matching = next(
                    (
                        row
                        for row in measurements
                        if row.get("rep") == rep["rep"]
                        and row["feature"] == reference.get("metric")
                        and row.get("unit") == reference.get("unit")
                        and (
                            "finish"
                            if row.get("phase") in {"lunge_finish", "lunge_hold"}
                            else row.get("phase")
                        )
                        == reference.get("phase")
                    ),
                    None,
                )
                if matching and reference.get("reference_range"):
                    if context not in reference_contexts:
                        reference_contexts.append(context)
                    reference_comparisons.append(
                        {
                            **reference,
                            "measurement_phase": matching.get("phase"),
                            "context_id": reference_contexts.index(context),
                        }
                    )
    if conversation_only:
        from collections import defaultdict

        grouped = defaultdict(list)
        described = [describe(row) for row in measurements]
        for row in described:
            grouped[(row["feature"], row.get("phase"), row.get("unit"))].append(row)
        comparison = []
        for (feature, phase, unit), rows in grouped.items():
            low, high = min(rows, key=lambda r: r["value"]), max(rows, key=lambda r: r["value"])
            comparison.append(
                {
                    "feature": feature,
                    "phase": phase,
                    "unit": unit,
                    "minimum": low,
                    "maximum": high,
                    "spread": round(high["value"] - low["value"], 3),
                    "meaning": "Describe this whole range before praise. Do not select the straightest rep as the finding or infer smoothness/quality from the extrema.",
                }
            )
        selected = [r for r in described if not requested or r.get("rep") in requested]
        labels = {
            "arm": "arm extension/direction",
            "front_leg": "front knee",
            "rear_leg": "rear knee",
            "torso": "torso",
            "speed": "lunge timing/hip speed",
            "recovery": "recovery",
            "distance": "distance",
        }
        usable_features = set()
        if availability == "measurements_available":
            for rep in all_reps:
                usable_features.update(rep.get("measures", {}))
                for phase in rep.get("phases", {}).values():
                    usable_features.update(phase.get("values", {}))
            usable_features.update(
                r.get("feature") for r in snapshot.get("session_measurements", [])
            )
        missing = [labels[t] for t in labels if not set(FEATURES.get(t, ())) & usable_features]
        available_topics = [labels[t] for t in labels if labels[t] not in missing]
        # Only the current resolved subject can authorize a gap statement.
        # Other topics are filtered out of this packet, not missing from the session.
        gap_topics = []
        if state.scope != "general":
            for topic in topics:
                if topic not in {*labels, "blade", "force", "fleche", "advance", "retreat"}:
                    continue
                features = set(FEATURES.get(topic, ()))
                if topic == "arm" and state.arm_roles == ["non_weapon"]:
                    features = {f.replace("weapon_", "non_weapon_", 1) for f in features}
                if not any(row["feature"] in features for row in selected):
                    gap_topics.append(topic)
        requested_missing = [labels.get(t, t.replace("_", " ")) for t in gap_topics]
        subject = ", ".join(requested_missing)
        session_gap = all(not set(FEATURES.get(t, ())) & usable_features for t in gap_topics)
        gap = (
            (
                f"No usable measurements for {subject} "
                + ("in this session" if session_gap else "in the requested rep/phase")
                + "; cause unknown."
            )
            if gap_topics
            else None
        )
        return {
            "current_question": request.question,
            "session_overview": (
                f"This session has {len(available_reps)} recorded reps; usable measurements cover "
                + ", ".join(available_topics)
                + "."
                if availability == "measurements_available" and available_topics
                else f"This session has {len(available_reps)} recorded reps."
            ),
            "overview_then_clarify": overview_for_clarification,
            "availability": {
                "status": availability,
                "requested_statement": gap,
                "available_session_topics": available_topics,
                "gap_scope_note": (
                    "Answer current_question and its resolved topics only. Earlier questions "
                    "are history, not additional pending requests. Measurements omitted for "
                    "another topic are filtered out, not missing. State a data gap only for "
                    "requested_missing_topics; never imply a gap for an unrequested or previous topic."
                ),
                "requested_missing_topics": requested_missing,
                "cause": "unknown" if gap else None,
                "verified_visibility_observations": [],
                "requested_scope": (
                    "unresolved_subject"
                    if not topics
                    else "available"
                    if selected
                    else "no_measurements_for_requested_scope"
                    if gap
                    else "general_guidance"
                ),
                "tracking_warning": "Tracking marked unsupported; specific cause unknown."
                if warning and gap
                else (
                    "Whole-clip quality was rejected; only usable per-rep geometry is supplied."
                    if quality in {"unsupported", "rejected"} and local_geometry
                    else ""
                ),
            },
            "scope": {
                "topics": topics,
                "phases": state.phases,
                "rep_numbers": requested,
                "available_reps": available_reps,
                "movement": state.movement,
            },
            "capture": request.capture_profile,
            "measurements": selected,
            "reference_comparisons": reference_comparisons,
            "reference_contexts": reference_contexts,
            "reference_policy": (
                "Compare the supplied phase-matched measurements with the athlete's chosen "
                "reference lunges when available. These examples are not universal numerical "
                "pass/fail boundaries. Preserve their stated corrections; an aspect with a "
                "stated issue is not a positive target. A reference difference does not "
                "establish force, balance, safety, or distance travelled. Reference current "
                "and current_range describe the comparison's phase summary, which may differ "
                "from a single-frame measurement. Missing reps are not covered."
            ),
            "not_measured": [
                "shoulder height",
                "smoothness",
                "elbow locking",
                "tactical effects",
                "qualitative movement speed",
                "blade/point tracking",
                "force",
                "calibrated real-world speed",
            ],
            "session_comparison": comparison,
            "clarification": state.open_clarifying_question,
            "resolution": {
                "confidence": state.resolution_confidence,
                "assumption": state.assumption_note,
            },
            "turn_type": state.turn_type,
            "already_said": state.already_given[-6:],
        }
    named = re.search(r"\b(?:the|a)\s+([a-z][a-z -]+?)\s+drill\b", request.question, re.I)
    named_item = (
        named[1] if named and named[1].lower() not in {"next", "simple", "useful", "good"} else None
    )
    query = " ".join(QUERIES.get(t, request.question) for t in topics)
    if state.movement == "fleche":
        query = "fleche " + " ".join(topics)
    if named_item:
        query = named_item + " drill"
    guidance = (
        deepcopy(cached["general_guidance"])
        if same_scope and not named_item
        else _teaching(query, named_item, topics, state.movement)
        if topics != ["conversation"]
        and state.turn_type not in {"greeting", "acknowledgment", "restart"}
        else []
    )
    library_error = guidance[0].get("lookup_error") if guidance else None
    if library_error:
        guidance = []
    operation = "observation"
    if wants_rep_comparison(request.question):
        operation = "compare measured aspects; no overall quality ranking is established"
    elif re.search(r"\bwhy\b|what does that mean", request.question, re.I):
        operation = "explain the last observation, not another numeric report"
    elif re.search(r"\b(?:good|bad|better|worse|correct|right position)\b", request.question, re.I):
        operation = "assess what the measurements can and cannot establish; do not substitute a repeated measurement for the verdict"
    elif re.search(r"\b(?:focus|improve|should i do|anything else)\b", request.question, re.I):
        operation = (
            "give a relevant practice focus from teaching material, labeled as general advice"
        )
    selected_status = "available" if measurements else "no_measurements_for_requested_scope"
    if availability != "measurements_available":
        selected_status = availability
    elif movement_mismatch:
        selected_status = "no_measurements_for_requested_movement"
    packet = {
        "availability": {
            "status": availability,
            "requested_scope": selected_status,
            "tracking_warning": "Measurement producer marked tracking unsupported; specific visual cause is not established in this packet."
            if availability == "tracking_unsupported"
            else None,
            "visibility_observations": [],
            "interpretation": "Missing measurements do not establish that the footage fails to show a body part.",
        },
        "scope": {
            "topics": topics,
            "phases": state.phases,
            "rep_numbers": requested,
            "all_reps": state.all_reps,
            "available_reps": available_reps,
            "unavailable_requested_reps": [r for r in requested if r not in available_reps],
            "movement": state.movement,
        },
        "requested_operation": operation,
        "last_cited_evidence": state.last_cited_evidence,
        "capture": {
            k: request.capture_profile.get(k, "unspecified")
            for k in ("weapon_arm", "front_leg", "camera_view")
        },
        "measurements": measurements,
        "feature_meanings": {
            f: MEANINGS.get(f, "Projected image measurement; not a correctness target.")
            for f in sorted({m["feature"] for m in measurements})
        },
        "general_guidance": guidance,
        "named_library_item": {
            "name": named_item,
            "status": "lookup_unavailable"
            if library_error
            else ("found" if guidance else "not_found"),
        }
        if named_item
        else None,
        "clarification": deepcopy(state.open_clarifying_question),
        "policy": "Athlete facts are only the measurements above. Library text is general teaching, never the athlete's target or a finding about this clip. No reference-rep ranges or universal targets are supplied. Answer on the requested subject even when tracking is unsupported.",
    }
    for row in measurements:
        row["topic"] = next(
            (
                topic
                for topic in topics
                if row["feature"] in FEATURES.get(topic, ())
                or (topic == "arm" and "arm_extension" in row["feature"])
            ),
            topics[0] if topics else "overview",
        )
    all_measurements = [describe(row) for row in measurements]
    packet["measurements"] = [
        r for r in all_measurements if not requested or r.get("rep") in requested
    ]
    previous = _previous_comparison(request, state)
    packet["assessments"] = assessments(topics, all_measurements, guidance, previous)
    if state.turn_type in {"greeting", "acknowledgment", "restart"}:
        packet["measurements"] = []
        packet["general_guidance"] = []
        packet["assessments"] = []
        packet["clarification"] = None
    packet["scope_text"] = (
        f"This packet covers {', '.join(topics) or 'unresolved subject'}, movement {state.movement or 'saved session'}, reps {requested or 'all available'}, phases {state.phases or 'available phases'}. Missing items here do not imply they are missing throughout the session."
    )
    packet["turn_type"] = state.turn_type
    packet["resolution"] = {
        "confidence": state.resolution_confidence,
        "assumption": state.assumption_note,
    }
    packet["conversation_memory"] = {
        "already_given": state.already_given[-6:],
        "assessment_already_explained": state.assessment_explained,
        "instruction": "Advance the answer. Do not restate these values or advice unless explicitly asked to repeat or compare. For a previously explained not-assessed verdict, give the next useful step instead of another decline.",
    }
    # This is a deterministic ladder decision, not a second model/router call.
    if state.turn_type in {"greeting", "acknowledgment", "restart"}:
        action = "Reply naturally in one short sentence; no evidence, numbers or question."
    elif state.open_clarifying_question:
        action = "Ask the supplied single clarification question and its concrete options."
    elif not packet["measurements"]:
        action = "Name the specific measurement gap briefly, then share relevant retrieved general guidance. Do not discuss missing grading standards when measurements themselves are absent. If no guidance exists, name that gap and offer one specific way to obtain it."
    elif operation.startswith("explain"):
        action = "Explain what the already-cited observation means using its definition and limits. Do not repeat its numbers or repeat a grading decline."
    elif operation.startswith("assess"):
        action = "Answer with the supplied relative comparison, naming the measured aspect. Explain that the library cue is not a pass/fail number; do not turn the absence of a threshold into a decline."
        if ",".join(state.topics) in state.assessment_explained:
            action = "The assessment limit was already explained. Advance with one useful next step from the retrieved material; do not decline again or repeat numbers."
    elif operation.startswith("give"):
        action = "Give a new supported practice focus, without restating earlier values or advice."
    else:
        action = "Answer the current question from the scoped evidence; distinguish observation from a quality judgment."
    packet["response_plan"] = action
    packet["query_scope"] = state.scope
    packet["evidence_reused"] = bool(same_scope)
    state.packet_snapshot_hash = snapshot_hash
    if library_error:
        packet["library_availability"] = {"status": "unavailable", "error_type": library_error}
    return packet


def _previous_comparison(request, state):
    """A declared, identical camera setup and side/action context are required.

    Missing setup identity is not evidence of comparability. Never use a saved
    report's prose or reference values as a previous-session measurement.
    """
    from fencecoach.coach.core_new import _session_key, _snapshot
    from fencecoach.schemas import CoachRequest

    candidates = [r for r in request.session_history if r.get("session_id") != request.session_id]
    candidates.sort(key=lambda r: r.get("date", ""), reverse=True)
    if not candidates:
        return {"status": "not_comparable", "reason": "No previous saved session supplied."}
    previous = candidates[0]
    a, b = request.capture_profile, previous.get("capture_profile", {})
    keys = (
        "camera_setup_id",
        "camera_view",
        "camera_motion",
        "weapon",
        "weapon_arm",
        "front_leg",
        "facing",
        "inference_crop",
    )
    if not a.get("camera_setup_id") or any(
        a.get(k) != b.get(k) or a.get(k) in (None, "", "unknown", "unspecified") for k in keys
    ):
        return {
            "status": "not_comparable",
            "reason": "Previous capture has no verified identical camera setup, view, sides and crop.",
        }
    prior = CoachRequest.model_validate(
        {**previous, "question": request.question, "session_history": []}
    )
    scope = state.model_copy(deep=True)
    scope.session_id = prior.session_id
    scope.rep_numbers = []
    scope.last_packet = None
    packet = build_packet(prior, scope, json.loads(_snapshot(_session_key(prior))))
    return {
        "status": "comparable",
        "session_id": prior.session_id,
        "measurements": packet["measurements"],
    }
