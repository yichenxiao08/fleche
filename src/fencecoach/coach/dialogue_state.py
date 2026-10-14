"""Resolve session-scoped follow-ups without using an assistant's prose as evidence."""

from __future__ import annotations

import re

from fencecoach.coach.intent import (
    arm_roles,
    corrected_subject,
    mentioned_rep_numbers,
    question_phases,
    question_topics,
)
from fencecoach.coach.turns import history_instruction
from fencecoach.schemas import DialogueState

ORDINALS = {
    "first": 1,
    "second": 2,
    "third": 3,
    "fourth": 4,
    "fifth": 5,
    "sixth": 6,
    "seventh": 7,
    "eighth": 8,
    "ninth": 9,
    "tenth": 10,
}


_EXPLICIT_PHASE = re.compile(
    r"\b(?:at|during|before|after)\s+(?:the\s+)?(?:starting guard|initial guard|"
    r"active recovery|recovery peak|peak (?:of (?:the )?)?recovery|returned guard|"
    r"return(?:ed)? to guard|lunge drive|lunge finish|finish|recovery|lunge)\b|"
    r"\b(?:starting guard|initial guard|active recovery|recovery peak|returned guard)\b",
    re.I,
)


def _subject(question):
    """Store a subject without a stale question, scope instruction or verdict."""
    text = re.sub(r"\brep\s+\d+\b", "", question)
    text = re.sub(
        r"\b(?:in general|generally|not (?:my|this) (?:session|video))\b", "", text, flags=re.I
    ).strip(" ,:?")
    text = re.sub(
        r"^(?:how (?:is|was|are|were)\s+|how (?:do|can|should) (?:i|you|we)\s+|"
        r"what about\s+|and\s+)",
        "",
        text,
        flags=re.I,
    )
    return re.sub(r"\s+", " ", text).strip(" ,:?")[:350]


def resolve_turn(request):
    state = request.dialogue_state
    if state is None or state.session_id != request.session_id:
        state = DialogueState(session_id=request.session_id)
        for message in request.conversation_history:
            if message.role == "user":
                _, state = _resolve(message.content, state, request)
    else:
        state = state.model_copy(deep=True)
        # A previous answer can be saved with a subject but an empty topic set
        # after an ambiguous turn. Rebuild that incomplete snapshot from the
        # user's saved turns, which are the durable conversation record.
        if not state.topics and state.subject:
            recovered = DialogueState(session_id=request.session_id)
            for message in request.conversation_history:
                if message.role == "user":
                    _, recovered = _resolve(message.content, recovered, request)
            if recovered.topics:
                state = recovered
            else:
                state.topics = question_topics(state.subject)
    return _resolve(request.question, state, request)


def _resolve(question, state, request):
    question = corrected_subject(question.strip())
    for word, number in ORDINALS.items():
        question = re.sub(
            rf"\b{word}\s+(?:rep(?:etition)?|one|lunge)\b", f"rep {number}", question, flags=re.I
        )
    topics = question_topics(question)
    # A newly named unsupported subject is still a topic switch, never an empty filter.
    explicit_other = bool(
        re.search(r"\b(?:blade|parry|injury|force|nutrition|sleep)\b", question, re.I)
    )
    followup = bool(
        re.search(
            r"^(?:so\s+)?(?:why\b|is (?:it|that|this)\b|are (?:they|those)\b|"
            r"what (?:should i|about|does that|do you mean)\b|and\b|how about\b|"
            r"can you\b|give me (?:a number|numbers)\b|was it\b|are you sure\b|"
            r"how (?:is|was|are|were) (?:mine|it|that|this|they|those)\b|"
            r"(?:is|was|are|were) mine\b)",
            question,
            re.I,
        )
    )
    broad = bool(
        re.search(r"\b(?:overall|whole session|all reps|every rep|how did i do)\b", question, re.I)
    )
    explicit_general = bool(
        re.search(r"\b(?:in general|generally|not (?:my|this) (?:session|video))\b", question, re.I)
    )
    numbers = sorted(mentioned_rep_numbers(question))
    question = re.sub(r"\b(best|worst|fastest|slowest) one\b", r"\1 rep", question, flags=re.I)
    if re.search(r"\b(?:last|final)\s+(?:rep|one|lunge)\b", question, re.I):
        available = [r["rep_number"] for r in request.technique_evaluation.get("reps", [])]
        if available:
            numbers = [max(available)]
            question = re.sub(
                r"\b(?:last|final)\s+(?:rep|one|lunge)\b", f"rep {numbers[0]}", question, flags=re.I
            )
    phase_qualifier = _EXPLICIT_PHASE.search(question)
    # A phase-only follow-up retains the body part. Naming recovery directly
    # ("And my recovery?") still switches topics; "at the recovery peak" does not.
    phase_only = bool(
        followup
        and phase_qualifier
        and state.subject
        and not question_topics(_EXPLICIT_PHASE.sub("", question))
        and not re.search(r"\bmy (?:active )?recovery\b", question, re.I)
    )
    attribute_followup = bool(
        followup
        and state.subject
        and re.search(r"^(?:was|is) it (?:faster|slower|better|worse)\b", question, re.I)
    )
    # When a message contains no identifiable new topic, keep the active
    # coaching subject. This covers ordinary contextual questions in many
    # phrasings without maintaining a brittle list of follow-up sentences.
    topicless_continuation = bool(
        state.subject
        and not topics
        and not explicit_other
        and not broad
        and not explicit_general
        and not history_instruction(question)
    )
    inherit = (
        (followup or topicless_continuation)
        and (not topics or phase_only or attribute_followup)
        and not explicit_other
        and not broad
    )
    personal = bool(re.search(r"\b(?:my|mine|did i|was i|am i)\b", question, re.I)) or bool(numbers)
    if explicit_general:
        state.scope = "general"
    elif history_instruction(question):
        state.scope = "history"
    elif personal or broad:
        state.scope = "session"
    if inherit and state.subject:
        state.subject = _subject(state.subject)
        if phase_qualifier:
            state.subject = (
                _EXPLICIT_PHASE.sub("", state.subject).strip() + " " + phase_qualifier.group()
            ).strip()
        resolved = f"Regarding {state.subject} in this session: {question}"
    else:
        resolved = question
        if topics or explicit_other or broad:
            state.subject = _subject(question)
            state.topics = topics
            if broad or not followup:
                state.rep_numbers = []
            if re.search(
                r"\b(?:in general|generally|not (?:my|this) (?:session|video))\b", question, re.I
            ):
                state.scope = "general"
            elif history_instruction(question):
                state.scope = "history"
            else:
                state.scope = "session"
    if numbers:
        state.rep_numbers = numbers
    elif broad:
        state.rep_numbers = []
    elif state.rep_numbers and followup:
        resolved += " (rep " + ", ".join(map(str, state.rep_numbers)) + ")"
    state.topics = question_topics(resolved)
    state.phases = sorted(question_phases(resolved))
    state.arm_roles = list(arm_roles(resolved)) if "arm" in state.topics else []
    return resolved, state
