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


_REP = r"(?:reps?|repetitions?|lunges?|attempts?)"
_NUMBER_WORDS = r"(?:\d+|one|two|three|four|five|six|seven|eight|nine|ten)"


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
        re.search(
            rf"\b(?:all|each|every)\s+(?:(?:{_NUMBER_WORDS})\s+)?{_REP}\b",
            question,
            re.I,
        )
    )


def mentioned_rep_numbers(text: str) -> set[int]:
    """Read explicit rep numbers from prose or a compact grouped list."""
    mentioned = {
        int(number)
        for number in re.findall(r"\brep\s*#?\s*(\d+)\b", text, re.I)
    }
    mentioned.update(
        int(number)
        for number in re.findall(
            r"(?:\breps\s+|,\s*)(\d+)(?:\s+\(\d+\.\d+\s+seconds\))?(?=\s*(?:,|:))",
            text,
            re.I,
        )
    )
    return mentioned


def question_topic(question: str) -> str | None:
    """Find the physical feature the athlete is asking about, if explicit."""
    text = question.lower()
    if re.search(r"\b(recover|recovery|return|returned|reset|en garde|guard)\b", text):
        return "recovery"
    if re.search(r"\b(timing|duration|interval)\b", text):
        return "speed"
    if re.search(r"\b(speed|fast|faster|slow|slower|explosive|explosiveness|power|powerful)\b", text):
        return "speed"
    if re.search(r"\b(distance|stride|reach|far|long|travel|displacement)\b", text):
        return "distance"
    if re.search(r"\b(rear|back)\s+(?:foot|leg|heel)\b|\bheel\b", text):
        return "rear_leg"
    if re.search(r"\b(torso|trunk|upright|back|lean|posture)\b", text):
        return "torso"
    if re.search(r"\b(arm|hand|elbow|extension|extend|sword arm|non[- ]sword)\b", text):
        return "arm"
    if re.search(r"\b(knee|knees|front leg|lead leg|front foot)\b", text):
        return "front_leg"
    if re.search(r"\b(lunge|lunge form|technique|footwork|form)\b", text):
        return "lunge"
    return None


def classify_coach_question(question: str) -> CoachIntent:
    """Classify the requested operation once so evidence and answer paths agree."""
    text = question.strip()
    topic = question_topic(text)
    if history_instruction(text):
        return CoachIntent("history")
    if wants_all_reps(text):
        return CoachIntent("all_reps", True, True, compare_all_reps=True, topic=topic)
    if wants_rep_comparison(text):
        return CoachIntent("rep_comparison", True, True, compare_all_reps=True, topic=topic)
    if re.search(r"\b(?:last|final)\s+(?:rep|lunge|one)\b|\bmy last\b", text, re.I):
        return CoachIntent("last_rep", True, True, topic=topic)
    if re.search(r"\b(?:first|opening)\s+(?:rep|lunge|one)\b|\bmy first\b", text, re.I):
        return CoachIntent("first_rep", True, True, topic=topic)
    named = re.search(r"\brep(?:etition)?\s*(\d+)\b", text, re.I)
    if named:
        return CoachIntent("specific_rep", True, True, rep_number=int(named[1]), topic=topic)
    if general_instruction(text):
        # Ask the video first for a movement-specific question when this
        # session contains that evidence; general guidance remains the fallback.
        has_relevant_topic = topic in {"arm", "front_leg", "rear_leg", "torso", "recovery", "speed", "distance", "lunge"}
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
    )
    return (
        CoachIntent("personal_assessment", True, True, topic=topic)
        if needs_measurements
        else CoachIntent("general_chat", topic=topic)
    )
