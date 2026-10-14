"""Semantic review against the same canonical evidence, independent of question categories."""

import json
import re

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from fencecoach.coach.policy import EVIDENCE_REVIEW_POLICY


class PersonalChange(BaseModel):
    feature: str = Field(
        description="Exact metric name from the evidence record establishing the correction."
    )
    evidence_id: str = Field(
        description="Exact ID of a reference_comparison with supported_change, or submitted human feedback."
    )


class AnswerDraft(BaseModel):
    answer: str = Field(
        description="Direct natural conversational answer. For ordinary analysis, INTERPRET the observed movement in plain language (for example bent versus straight, position matching versus differing), rather than merely reporting a measurement. Give a short qualitative assessment or supported cue and place its one numerical example ONLY in supporting_example. Lack of an approved reference prevents a correctness verdict, not an observation of measured shape. For explicit numerical questions or an all-reps breakdown, answer the requested detail here. No internal evidence IDs."
    )
    supporting_example: str = Field(
        default="",
        description="For ordinary personal analysis, exactly one concise sentence about ONE representative rep or statistic that supports the main assessment, with units/reference comparison if useful. Choose the rep illustrating the stated difference. No second rep/example, no list, and no internal IDs. Empty when the answer already supplies explicitly requested numbers or a full breakdown, or evidence is unavailable.",
    )
    session_evidence_ids: list[str] = Field(
        default_factory=list,
        description="Exact evidence_id values supporting all current-session observations and comparisons. Cite the requested rep/phase; empty for entirely general answers.",
    )

    @property
    def conversational_text(self):
        def facts(text):
            return {
                (
                    float(number),
                    "deg" if unit.lower() in {"deg", "degree", "degrees", "°"} else unit.lower(),
                )
                for number, unit in re.findall(
                    r"(-?\d+(?:\.\d+)?)\s*(degrees?|deg\b|°|seconds?|%|leg lengths?)", text, re.I
                )
            }

        def reps(text):
            return set(re.findall(r"\brep(?:s|etition(?:s)?)?\s*#?\s*(\d+)\b", text, re.I))

        support_facts = facts(self.supporting_example)
        # Adding a playback timestamp does not make a repeated angle a new
        # statistical example. Keep genuinely new reference values or timing
        # measurements; omit duplicate geometry even when only its bookmark is new.
        geometry_facts = {fact for fact in support_facts if not fact[1].startswith("second")}
        if geometry_facts:
            support_facts = geometry_facts
        support_parts = set(
            re.findall(
                r"\b(?:torso|knee|elbow|arm|hip|foot|leg)\b", self.supporting_example.lower()
            )
        )
        answer_parts = set(
            re.findall(r"\b(?:torso|knee|elbow|arm|hip|foot|leg)\b", self.answer.lower())
        )
        if (
            support_facts
            and support_facts.issubset(facts(self.answer))
            and reps(self.supporting_example).issubset(reps(self.answer))
            and support_parts.issubset(answer_parts)
        ):
            # Both model-written fields can contain the same example. Preserve
            # its complete answer once instead of repeating the measured value.
            return self.answer.strip()
        return " ".join(
            part.strip() for part in (self.answer, self.supporting_example) if part.strip()
        )


class AnswerReview(BaseModel):
    session_evidence_relevant: bool = Field(
        default=False,
        description="Independently inspect all supplied question-scoped active-session records against the question and recent conversation. True when any record answers part of the question, even if the draft omitted it or the user did not explicitly mention the session.",
    )
    addresses_question: bool = Field(
        description="The candidate answer directly addresses every part of the current question."
    )
    grounded: bool = Field(
        description="Every personal observation or correction in the candidate answer is supported by relevant supplied evidence; general guidance is not presented as a detected fault."
    )
    uses_session_evidence: bool = Field(
        description="The candidate answer makes at least one observation or comparison about the current session."
    )
    session_evidence_ids: list[str] = Field(
        default_factory=list,
        description="Exact evidence_id values supporting the personal claims in the candidate answer. Empty when the answer is entirely general.",
    )
    personal_changes: list[PersonalChange] = Field(
        default_factory=list,
        description="Every correction of the athlete's current technique in the candidate answer. A matching feature needs no correction. General instructions and clearly optional experiments are not detected faults.",
    )
    corrections: list[str] = Field(
        default_factory=list,
        description="Errors corrected in the draft; empty if no corrections were needed.",
    )


def evidence_ids(value):
    """Extract actual record IDs, not model-created identifiers."""
    found = set()
    if isinstance(value, dict):
        if isinstance(value.get("evidence_id"), str):
            found.add(value["evidence_id"])
        for item in value.values():
            found.update(evidence_ids(item))
    elif isinstance(value, list):
        for item in value:
            found.update(evidence_ids(item))
    return found


def supported_changes(value):
    records = {}
    if isinstance(value, dict):
        record_id = value.get("evidence_id")
        if record_id and (value.get("supported_change") or str(record_id).startswith("review:")):
            records[record_id] = value.get("metric")
        for item in value.values():
            records.update(supported_changes(item))
    elif isinstance(value, list):
        for item in value:
            records.update(supported_changes(item))
    return records


def focused_packet(packet, selected_ids):
    """Select exact cited facts, independent of question wording or feature names."""
    records = []
    selected = set(selected_ids)

    def collect(value):
        if isinstance(value, dict):
            if value.get("evidence_id") in selected:
                records.append(value)
            for item in value.values():
                collect(item)
        elif isinstance(value, list):
            for item in value:
                collect(item)

    collect(packet)
    return {
        **{
            key: packet.get(key)
            for key in (
                "current_session_id",
                "current_clip_reps_detected",
                "capture_context",
                "measured_features_available",
                "measurement_policy",
                "feature_meanings",
            )
        },
        "cited_evidence_records": records,
        "instruction": "Only the cited records support personal claims. The feature inventory indicates other measurements exist, not their values. If the wrong feature was cited, fix the answer's relevance without inventing missing values.",
    }


def cited_subject_issues(
    packet,
    selected_ids,
    requested_features=(),
    rep_number=None,
    requested_phases=(),
    rep_numbers=(),
):
    """Reject wrong-feature/rep citations before the single-call answer is released."""
    records = focused_packet(packet, selected_ids)["cited_evidence_records"]
    issues = []
    if requested_features and records:
        features = set()
        for record in records:
            features.update(record.get("values", {}))
            features.add(record.get("feature") or record.get("metric") or record.get("name"))
        if features - {None} and not features.intersection(requested_features):
            issues.append("The cited records omit the requested measured feature.")
    if (
        rep_number is not None
        and records
        and not any(record.get("rep") == rep_number for record in records)
    ):
        issues.append("The cited records omit the requested rep.")
    if rep_numbers and records:
        cited_reps = {record.get("rep") for record in records}
        missing_reps = sorted(set(rep_numbers) - cited_reps)
        if missing_reps:
            issues.append(
                "The cited records omit requested reps: " + ", ".join(map(str, missing_reps)) + "."
            )
    matching = [
        record
        for record in records
        if record.get("feature") in requested_features
        or record.get("metric") in requested_features
        or set(record.get("values", {})).intersection(requested_features)
    ]
    phase_scope = set(requested_phases)
    if phase_scope.intersection({"lunge_finish", "lunge_hold"}):
        phase_scope.add("finish")
    if (
        requested_phases
        and matching
        and not any(record.get("phase") in phase_scope for record in matching)
    ):
        issues.append(
            "The cited feature belongs to a different phase than the athlete asked about."
        )
    return issues


def review_issues(
    decision,
    packet,
    requested_features=(),
    rep_number=None,
    require_session=False,
    requested_phases=(),
    requested_reps=(),
    answer="",
):
    """Local acceptance rules shared by initial reviews and their bounded repair."""
    if not isinstance(decision, AnswerReview):
        return ["The review was incomplete."]
    issues = []
    if not decision.grounded or not decision.addresses_question:
        issues.append("The answer is unsupported or does not address the exact question.")
    if (
        require_session or decision.session_evidence_relevant
    ) and not decision.uses_session_evidence:
        issues.append(
            "Relevant current-session evidence exists but the answer is entirely general."
        )
    if decision.uses_session_evidence and not decision.session_evidence_ids:
        issues.append("Personal observations need actual session record IDs.")
    if not set(decision.session_evidence_ids).issubset(evidence_ids(packet)):
        issues.append("A cited evidence ID is absent from the current session.")
    issues.extend(
        cited_subject_issues(
            packet,
            decision.session_evidence_ids,
            requested_features,
            rep_number,
            requested_phases,
            requested_reps,
        )
    )
    records = focused_packet(packet, decision.session_evidence_ids)["cited_evidence_records"]
    degree_values = []
    for record in records:
        if record.get("unit") == "deg":
            degree_values.extend(
                value
                for value in (record.get("value"), record.get("current"))
                if isinstance(value, (int, float))
            )
            degree_values.extend(
                value
                for value in record.get("reference_range", [])
                if isinstance(value, (int, float))
            )
        for feature, value in record.get("values", {}).items():
            if any(
                term in feature for term in ("angle", "tilt", "pitch", "arm_direction")
            ) and isinstance(value, (int, float)):
                degree_values.append(value)
    if records:
        reported = re.findall(r"(-?\d+(?:\.\d+)?)\s*(?:degrees?|deg\b|°)", answer, re.I)
        if any(
            not any(abs(float(number) - value) <= 0.15 for value in degree_values)
            for number in reported
        ):
            issues.append("A reported angle is absent from the cited feature/phase records.")
    allowed = supported_changes(packet)
    for change in decision.personal_changes:
        if requested_features and change.feature not in requested_features:
            issues.append(
                "A corrective cue addresses an unrequested feature instead of the athlete's current subject."
            )
        if change.evidence_id not in allowed or (
            allowed[change.evidence_id] is not None
            and allowed[change.evidence_id] != change.feature
        ):
            issues.append(
                "A personal correction needs the matching authorized feature/phase, not a plain measurement."
            )
    return list(dict.fromkeys(issues))


def review_messages(question, draft, packet, guidance, history):
    return [
        SystemMessage(content=EVIDENCE_REVIEW_POLICY),
        HumanMessage(
            content=json.dumps(
                {
                    "question": question,
                    "draft": draft,
                    "active_session": packet,
                    "guidance": guidance,
                    "recent_conversation": history,
                },
                separators=(",", ":"),
            )
        ),
    ]
