"""One deterministic classification for evidence routing in coach turns."""

from __future__ import annotations

import re
from dataclasses import dataclass

from fencecoach.coach.turns import general_instruction, history_instruction, motion_question


@dataclass(frozen=True)
class CoachIntent:
    kind: str
    needs_video_metrics: bool = False
    needs_technique_evaluation: bool = False
    compare_all_reps: bool = False
    rep_number: int | None = None
    topic: str | None = None
    rep_numbers: tuple[int, ...] = ()


_REP = r"(?:reps?|repetitions?|lunges?|attempts?)"
_NUMBER_WORDS = r"(?:\d+|one|two|three|four|five|six|seven|eight|nine|ten)"
_ALL_REP_SELECTOR = (
    rf"\b(?:all|each|every)\s+(?:of\s+)?(?:(?:my|your|the)\s+)?"
    rf"(?:{_NUMBER_WORDS}\s+)?{_REP}\b"
)
_NUMBERED_REP_SELECTOR = (
    r"\brep(?:s|etition(?:s)?)?\s*#?\s*\d+"
    r"(?:\s*(?:,|and|&)\s*(?:rep(?:s|etition(?:s)?)?\s*)?#?\s*\d+)*"
)
_REP_SELECTOR = re.compile(
    r"\b(?:(?:in|for|across|from|over|on|during|throughout|of)\s+)?(?:"
    + _ALL_REP_SELECTOR
    + "|"
    + _NUMBERED_REP_SELECTOR
    + ")",
    re.I,
)


def without_rep_selectors(text: str) -> str:
    """Remove explicit rep coverage independently of the requested movement."""
    return _REP_SELECTOR.sub("", text)


# A temporal qualifier is a scope dimension, not another movement subject.
# Share its grammar with dialogue resolution so retrieval and state agree.
PHASE_QUALIFIER = re.compile(
    r"\b(?:at|during|before|after)\s+(?:the\s+)?(?:starting guard|initial guard|"
    r"active recovery|recovery peak|peak (?:of (?:the )?)?recovery|returned guard|"
    r"return(?:ed)? to guard|lunge drive|lunge finish|lunge hold|finish|recovery|lunge)\b|"
    r"\b(?:starting guard|initial guard|active recovery|recovery peak|returned guard)\b",
    re.I,
)


def without_phase_qualifiers(text: str) -> str:
    """Remove prepositional phase scope while keeping independently named subjects."""
    return PHASE_QUALIFIER.sub(
        lambda match: (
            "" if re.match(r"(?:at|during|before|after)\b", match.group(), re.I) else match.group()
        ),
        text,
    )


def wants_rep_comparison(question: str) -> bool:
    """Recognize rankings even when the athlete does not use 'compare' exactly."""
    ranking = re.search(
        r"\b(?:best|worst|strongest|weakest|better|worse|fastest|quickest|slowest|longest|shortest|furthest|closest)\b|\bmost\s+(?:consistent|upright|stable|explosive|powerful)\b|\bleast\s+consistent\b",
        question,
        re.I,
    )
    subject = re.search(rf"\b{_REP}\b|\bwhich\s+(?:one|was|of these|of my)\b", question, re.I)
    return bool(ranking and subject)


def wants_all_reps(question: str) -> bool:
    return bool(
        re.search(_ALL_REP_SELECTOR, question, re.I)
        or re.search(
            r"\b(?:all|each|every)\s+(?:of\s+)?(?:(?:my|your|the)\s+)?(?:recoveries|returns to guard)\b",
            question,
            re.I,
        )
    )


def mentioned_rep_numbers(text: str) -> set[int]:
    """Read explicit rep numbers from prose or a compact grouped list."""
    mentions = re.finditer(
        _NUMBERED_REP_SELECTOR,
        text,
        re.I,
    )
    mentioned = {int(number) for match in mentions for number in re.findall(r"\d+", match.group())}
    return mentioned


def question_topics(question: str) -> list[str]:
    """Return every explicit movement topic, from specific body part to broad motion."""
    question = corrected_subject(question)
    patterns = (
        (
            "recovery",
            r"\b(?:recover(?:y|ies|ing)?|return(?:ed|ing)? to guard|returned (?:to )?guard|en garde|reset)\b",
        ),
        (
            "speed",
            r"\b(?:speed|fast(?:er|est)?|slow(?:er|est)?|explosi(?:ve|veness)|power(?:ful)?|timing|duration|interval)\b",
        ),
        ("distance", r"\b(?:distance|stride|reach|spacing|feet separation|travel)\b"),
        (
            "rear_leg",
            r"\b(?:rear|back)\s+(?:leg|foot|heel|knee)\b|\bheel\b",
        ),
        (
            "torso",
            r"\b(?:torso|trunk|upright|lean|posture|chest|upper body|back straight|back upright|back)\b",
        ),
        (
            "arm",
            r"\b(?:arms?|hands?|elbows?|sword arm|weapon arm|non[- ]sword arm|extension|extending)\b",
        ),
        ("front_leg", r"\b(?:front|lead)\s+(?:leg|foot|knee)\b|\bknees?\b"),
        ("lunge", r"\b(?:lunge|lunges|technique|form|footwork)\b"),
    )
    subject = without_phase_qualifiers(question)
    topics = [topic for topic, pattern in patterns if re.search(pattern, subject, re.I)]
    if not topics:
        # A standalone recovery question still names a movement; it only acts
        # as phase scope when another subject is explicitly present.
        topics = [topic for topic, pattern in patterns if re.search(pattern, question, re.I)]
    if (
        "arm" in topics
        and set(topics).intersection({"front_leg", "rear_leg", "torso"})
        and not re.search(r"\b(?:arms?|hands?|elbows?|sword|weapon)\b", question, re.I)
    ):
        # Extension describes the named body part; the word alone does not turn
        # back-leg or torso extension into a weapon-arm question.
        topics.remove("arm")
    if (
        "rear_leg" in topics
        and re.search(r"\bback\s+(?:leg|foot|heel|knee|arm|hand)\b", question, re.I)
        and not re.search(
            r"\b(?:torso|trunk|upright|lean|posture|chest|upper body|back straight|back upright)\b",
            question,
            re.I,
        )
    ):
        topics.remove("torso")
    if (
        "rear_leg" in topics
        and "front_leg" in topics
        and re.search(r"\b(?:rear|back)\s+(?:leg|foot|heel|knee)\b", question, re.I)
        and not re.search(r"\b(?:front|lead)\s+(?:leg|foot|knee)\b", question, re.I)
    ):
        topics.remove("front_leg")
    if (
        "lunge" in topics
        and any(topic != "lunge" for topic in topics)
        and not re.search(r"\b(?:lunge form|lunge technique|whole lunge)\b", question, re.I)
    ):
        topics.remove("lunge")
    return topics


def corrected_subject(question: str) -> str:
    """Prefer the subject named in a correction over the rejected earlier subject."""
    correction = re.search(
        r"\b(?:i(?:['’]?m| am| was) asking about|i asked about|i mean|i meant|"
        r"i(?:['’]?m| am) talking about|the question is(?: about)?|focus on)\s+(.+)$",
        question,
        re.I,
    )
    return correction.group(1).strip() if correction else question


def arm_roles(question: str) -> tuple[str, ...]:
    """Resolve anatomical side and weapon role without treating 'non-sword' as sword."""
    text = corrected_subject(question)
    roles = []
    non_weapon = r"\b(?:non[- ](?:sword|weapon)|off[- ]?hand|unarmed|free)\s*(?:arm|hand|elbow)?\b"
    if re.search(non_weapon, text, re.I):
        roles.append("non_weapon")
    remaining = re.sub(non_weapon, "", text, flags=re.I)
    if re.search(r"\b(?:sword|weapon)\s+(?:arm|hand|elbow)\b", remaining, re.I):
        roles.append("weapon")
    for side in ("left", "right"):
        if re.search(rf"\b{side}\s+(?:arm|hand|elbow)\b", remaining, re.I):
            roles.append(side)
    if not roles and "arm" in question_topics(text):
        roles.extend(
            ("weapon", "non_weapon")
            if re.search(r"\b(?:both arms|arms|hands)\b", text, re.I)
            else ("weapon",)
        )
    return tuple(roles)


def arm_sides(question: str, profile: dict) -> set[str]:
    """Return only sides established by the capture profile or explicitly named."""
    weapon = profile.get("weapon_arm")
    return {
        side
        for role in arm_roles(question)
        if (
            side := role
            if role in {"left", "right"}
            else weapon
            if role == "weapon"
            else {"left": "right", "right": "left"}.get(weapon)
        )
        in {"left", "right"}
    }


def _named_phases(phase_text: str) -> set[str]:
    """Map an explicit phase name to its measured scope, without topic inference."""
    if re.search(
        r"\b(?:peak|deepest point)\s+(?:of )?(?:the )?recovery\b|\brecovery peak\b",
        phase_text,
        re.I,
    ):
        return {"recovery_peak"}
    if re.search(r"\bactive recovery\b", phase_text, re.I):
        return {"active_recovery"}
    if re.search(r"\b(?:return(?:ed)? to guard|back in guard|returned guard)\b", phase_text, re.I):
        return {"returned_guard"}
    if re.search(
        r"\b(?:recover(?:y|ies|ing)?|return(?:ed|ing)?|reset|en garde)\b", phase_text, re.I
    ):
        return {"active_recovery", "recovery_peak", "returned_guard"}
    if re.search(r"\b(?:starting|initial) guard\b|\bbefore (?:the )?lunge\b", phase_text, re.I):
        return {"starting_guard"}
    if re.search(r"\blunge (?:drive|hold)\b", phase_text, re.I):
        return {"lunge_hold" if re.search(r"\bhold\b", phase_text, re.I) else "lunge_drive"}
    if re.search(
        r"\b(?:at|during) (?:the )?(?:lunge )?finish\b|\bfinish position\b", phase_text, re.I
    ):
        # "finish" is a legacy name for the finish sample. A held lunge is
        # a different measured interval and cannot stand in for that sample.
        return {"finish", "lunge_finish"}
    return set()


def question_phases(question: str) -> set[str]:
    """Prefer explicit phase scope, then named movement, then implied phases."""
    question = corrected_subject(question)
    qualifier = PHASE_QUALIFIER.search(question)
    phases = _named_phases(qualifier.group()) if qualifier else set()
    # A qualifier such as "after the lunge" has no single measured phase.
    # Keep an explicitly named return/recovery elsewhere in the question.
    phases = phases or _named_phases(question)
    if phases:
        return phases
    topic_phases = {
        "recovery": {"active_recovery", "recovery_peak", "returned_guard"},
        "speed": {"lunge_drive", "active_recovery"},
        "distance": {"lunge_drive", "lunge_finish", "lunge_hold"},
        "rear_leg": {"lunge_drive", "lunge_finish", "recovery_peak", "returned_guard"},
        "torso": {"lunge_drive", "lunge_hold", "lunge_finish"},
        "arm": {"lunge_drive", "lunge_hold", "lunge_finish"},
        "front_leg": {"starting_guard", "lunge_hold", "lunge_finish"},
        "lunge": {"starting_guard", "lunge_drive", "lunge_hold", "lunge_finish"},
    }
    return set().union(*(topic_phases.get(topic, set()) for topic in question_topics(question)))


def question_topic(question: str) -> str | None:
    """Find the physical feature the athlete is asking about, if explicit."""
    topics = question_topics(question)
    return topics[0] if topics else None


def classify_coach_question(question: str) -> CoachIntent:
    """Classify the requested operation once so evidence and answer paths agree."""
    raw_text = question.strip()
    text = corrected_subject(raw_text).strip()
    topic = question_topic(text)
    if history_instruction(text):
        return CoachIntent("history")
    if wants_rep_comparison(text):
        return CoachIntent("rep_comparison", True, True, compare_all_reps=True, topic=topic)
    if wants_all_reps(text):
        return CoachIntent("all_reps", True, True, compare_all_reps=True, topic=topic)
    rep_numbers = tuple(sorted(mentioned_rep_numbers(text)))
    if len(rep_numbers) > 1:
        return CoachIntent("specific_reps", True, True, topic=topic, rep_numbers=rep_numbers)
    if re.search(r"\b(?:last|final)\s+(?:rep|lunge|one)\b|\bmy last\b", text, re.I):
        return CoachIntent("last_rep", True, True, topic=topic)
    if re.search(r"\b(?:first|opening)\s+(?:rep|lunge|one)\b|\bmy first\b", text, re.I):
        return CoachIntent("first_rep", True, True, topic=topic)
    if rep_numbers:
        return CoachIntent("specific_rep", True, True, rep_number=rep_numbers[0], topic=topic)
    if general_instruction(text):
        # Ask the video first for a movement-specific question when this
        # session contains that evidence; general guidance remains the fallback.
        has_relevant_topic = topic in {
            "arm",
            "front_leg",
            "rear_leg",
            "torso",
            "recovery",
            "speed",
            "distance",
            "lunge",
        }
        return CoachIntent(
            "general_instruction",
            has_relevant_topic,
            has_relevant_topic,
            topic=topic,
        )

    personal = re.search(r"\b(i|my|it|this|that|these|session|clip|video|reps?)\b", text, re.I)
    assessment = re.search(
        r"\b(analy[sz]e|assess|evaluate|review|check|correct|feedback|improve|establish|observation|cue|drill|wrong|best|worst)\b|break down|work on",
        text,
        re.I,
    )
    movement = bool(topic)
    session_reference = re.search(
        r"\b(measured|measurements|intervals|timestamp|recorded|video|clip)\b", text, re.I
    )
    needs_measurements = bool(
        (personal and (assessment or movement or motion_question(text)))
        or "supported observation" in text.lower()
        or (movement and session_reference)
        or (text != raw_text and movement)
    )
    return (
        CoachIntent("personal_assessment", True, True, topic=topic)
        if needs_measurements
        else CoachIntent("general_chat", topic=topic)
    )
