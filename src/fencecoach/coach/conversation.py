"""A normal chat turn with optional, bounded access to coaching evidence tools."""

from __future__ import annotations

import json
import logging
import operator
import re
import time
from datetime import UTC, datetime
from typing import Annotated, TypedDict
from uuid import uuid4

from httpx import TransportError
from langchain_core.exceptions import (
    ModelAPIError,
    ModelConnectionError,
    ModelTimeoutError,
)
from langchain_core.messages import AIMessage, AnyMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import tool
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages

from fencecoach.coach.analysis import _rep_key, build_coaching_brief
from fencecoach.coach.answer_review import (
    AnswerDraft,
    AnswerReview,
    cited_subject_issues,
    evidence_ids,
    review_issues,
    review_messages,
)
from fencecoach.coach.answer_style import (
    ADVICE_FIRST_POLICY,
    format_answer,
    format_timings,
    requests_numbers,
    response_evidence_issues,
    style_issues,
)
from fencecoach.coach.dialogue_state import resolve_turn
from fencecoach.coach.grounding import (
    assessment_issues,
    evidence_summary,
    unsupported_claims,
)
from fencecoach.coach.intent import (
    arm_sides,
    classify_coach_question,
    corrected_subject,
    mentioned_rep_numbers,
    question_phases,
    question_topics,
    wants_all_reps,
    without_rep_selectors,
)
from fencecoach.coach.latency import (
    coaching_session_context,
    compact_guidance,
    wants_detail,
    wants_rep_comparison,
)
from fencecoach.coach.policy import SESSION_DIALOGUE_POLICY
from fencecoach.coach.providers import chat_model, configured_model_id, provider_status
from fencecoach.coach.reviewed import (
    feedback_source,
    reviewed_claim_issues,
    select_feedback,
)
from fencecoach.coach.router import route
from fencecoach.coach.technique_evidence import (
    MOTION_POLICY,
    baseline_context,
    current_session_context,
    evaluation_issues,
    evaluation_source,
    explicit_phase_requested,
    question_scoped_session_context,
    rep_comparison_result,
    requested_feature_names,
    session_evidence_context,
)
from fencecoach.coach.turns import (
    clarification,
    conversation_issues,
    general_instruction,
)
from fencecoach.comparisons import comparable_capture
from fencecoach.rag.knowledge import search_knowledge
from fencecoach.schemas import (
    CoachingObservation,
    CoachingReport,
    CoachRequest,
    DrillRecommendation,
    EvidenceRef,
    KnowledgeSource,
    RunRecord,
    TraceEvent,
)
from fencecoach.settings import settings
from fencecoach.telemetry import span


class CoachAnswerError(RuntimeError):
    """A draft could not be repaired into a supported answer to the same question."""

    def __init__(self, message, validation_issues=None):
        super().__init__(message)
        self.validation_issues = validation_issues or []


class ChatState(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]
    trace: Annotated[list[TraceEvent], operator.add]
    rounds: int
    calls: int
    input_tokens: int
    output_tokens: int


def _text(message):
    if isinstance(message.content, str):
        text = message.content.strip()
        if "<think>" in text and "</think>" not in text:
            return ""
        text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
        if re.match(r"^(okay,?\s+the user|the user is asking|let me think\b)", text, re.IGNORECASE):
            return ""
        return text
    return "\n".join(
        block.get("text", "")
        for block in message.content
        if isinstance(block, dict) and block.get("type") == "text"
    ).strip()


def _needs_measurements(question):
    return classify_coach_question(question).needs_video_metrics


def run_conversation(
    request: CoachRequest, mode: str, model=None, on_step=None, on_text=None
) -> RunRecord:
    if settings.coach_core == "new":
        from fencecoach.coach.core_new import run_new_core

        return run_new_core(request, mode, model, on_step, on_text)
    if settings.fencecoach_verified_dialogue and mode in {"gemini", "local"}:
        from fencecoach.coach.verified_dialogue import run_verified_conversation

        return run_verified_conversation(request, mode, model, on_step, on_text)
    if model is not None:
        return _run_conversation(request, mode, model, on_step, on_text)
    started = time.perf_counter()

    def generate(provider):
        if provider != mode and on_step:
            on_step("local_fallback")
        return _run_conversation(request, provider, on_step=on_step, on_text=on_text)

    run, fallback_reason = route(generate, mode)
    run.fallback_reason = fallback_reason
    if fallback_reason:
        run.model_id = (run.model_id or settings.ollama_chat_model) + " (provider failover: local)"
        run.trace.insert(
            0,
            TraceEvent(
                step="local_fallback",
                detail="Gemini was unavailable; the local model received the same current-session data and conversation. Reason: "
                + fallback_reason,
                elapsed_ms=round((time.perf_counter() - started) * 1000, 2),
            ),
        )
        run.latency_ms = round((time.perf_counter() - started) * 1000, 2)
    return run


def _run_conversation(
    request: CoachRequest, mode: str, model=None, on_step=None, on_text=None
) -> RunRecord:
    started = time.perf_counter()
    provided_model = model is not None
    original_question = request.question
    resolved_question, dialogue_state = resolve_turn(request)
    request = request.model_copy(
        update={"question": resolved_question, "dialogue_state": dialogue_state}
    )
    intent = classify_coach_question(request.question)
    latest_intent = classify_coach_question(original_question)
    corrected_turn = corrected_subject(original_question) != original_question
    current_topics = set(question_topics(request.question))
    prior_topic_question = next(
        (
            item.content
            for item in reversed(request.conversation_history)
            if item.role == "user" and current_topics.intersection(question_topics(item.content))
        ),
        "",
    )
    prior_topic_intent = (
        classify_coach_question(prior_topic_question) if prior_topic_question else None
    )
    all_reps_requested = (
        wants_all_reps(original_question)
        or (dialogue_state.all_reps and requests_numbers(original_question))
        or bool(
            corrected_turn
            and prior_topic_intent
            and prior_topic_intent.kind in {"all_reps", "rep_comparison"}
        )
    )
    assessment_question = (
        prior_topic_question if corrected_turn and prior_topic_question else request.question
    )
    provider_fallback = False
    failover_used = False
    publish_text = on_text
    if publish_text:

        def publish_formatted(text):
            publish_text(format_answer(text))

        on_text = publish_formatted
    # Every user-facing answer is authored by the model. Tools and evaluators
    # return evidence only; they never short-circuit the conversational writer.
    model = model if model is not None else chat_model(mode)
    sources = {}
    consulted = {}
    plan = None
    reviewed_reps = select_feedback(request)
    review_context = bool(reviewed_reps)
    if re.search(
        r"\bautomatic(?:ally)?\b|without (?:my )?(?:review|feedback)", request.question, re.I
    ):
        review_context = False
        reviewed_reps = []
    scoped_feedback_source = feedback_source(request, reviewed_reps) if reviewed_reps else None
    session_evaluation_available = bool(request.technique_evaluation.get("reps")) and (
        not review_context
        or request.technique_evaluation.get("coaching_mode") == "reference_comparison"
    )
    # Evidence availability, rather than wording/category, controls session context.
    evaluation_context = session_evaluation_available

    def claim_issues(reply, metrics):
        if session_evaluation_available:
            return evaluation_issues(request, reply, metrics)
        return (
            reviewed_claim_issues(request, reply, metrics)
            if review_context
            else unsupported_claims(reply, metrics)
        )

    def answer_issues(reply, metrics):
        issues = (
            []
            if intent.kind == "rep_comparison"
            else style_issues(
                request.question, reply, personal=review_context or evaluation_context
            )
        ) + (
            claim_issues(reply, metrics)
            if review_context or session_evaluation_available
            else assessment_issues(request, reply, metrics)
        )
        if wants_rep_comparison(request.question):
            result = rep_comparison_result(request)
            requested_ranks = []
            if result and re.search(r"\b(fastest|quickest)\b", request.question, re.I):
                requested_ranks = [result.get("fastest")]
            elif result and re.search(r"\b(slowest|longest)\b", request.question, re.I):
                requested_ranks = [result.get("slowest")]
            elif result:
                requested_ranks = [result["best"], result["worst"]]
            if result and any(
                rank and not re.search(rf"\brep\s*#?\s*{rank['rep']}\b", reply, re.I)
                for rank in requested_ranks
            ):
                issues.append(
                    "A best/worst rep question must name both reps supported by the supplied comparison."
                )
        if all_reps_requested:
            expected_reps = [
                rep.get("rep_number")
                for rep in request.technique_evaluation.get("reps", [])
                if isinstance(rep.get("rep_number"), int)
            ]
            mentioned = mentioned_rep_numbers(reply)
            missing_reps = [
                rep_number for rep_number in expected_reps if rep_number not in mentioned
            ]
            if missing_reps:
                issues.append(
                    "An all-reps answer must cover every supplied rep number: "
                    + ", ".join(map(str, missing_reps))
                    + "."
                )
        topic_patterns = {
            "arm": r"\b(arm|hand|elbow|sword)\b",
            "front_leg": r"\b(knee|front[- ]leg|front foot|stance)\b",
            "rear_leg": r"\b(rear|back[- ](?:leg|knee|foot)|heel)\b",
            "torso": r"\b(torso|trunk|upright|posture|chest)\b",
            "recovery": r"\b(recover(?:y|ies|ing)?|return(?:ed|ing)?|guard)\b",
            "speed": r"\b(speed|fast|slow|quick|pace|timing)\b",
            "distance": r"\b(distance|stride|reach|feet|travel|spacing|stance)\b",
            "lunge": r"\b(lunge|finish|knee|leg)\b",
        }
        requested_topics = question_topics(request.question) or (
            [intent.topic] if intent.topic else []
        )
        # A pronoun follow-up can refer to the subject through the exchange;
        # it need not repeat the same anatomical noun on every turn.
        for topic in question_topics(without_rep_selectors(original_question)):
            topic_pattern = topic_patterns.get(topic)
            if topic_pattern and not re.search(topic_pattern, reply, re.I):
                issues.append(f"The answer did not address the requested {topic} topic.")
        allowed_features = requested_feature_names(request)
        feature_phrases = {
            "front_knee_angle": r"\bfront[- ](?:leg|knee)|\blead knee\b",
            "front_knee_ahead_of_toe": r"\bfront[- ](?:leg|knee)|\blead knee\b",
            "front_foot_lift_to_stable_finish": r"\bfront foot|\blead foot\b",
            "rear_knee_angle": r"\b(?:rear|back)[- ]knee|\b(?:rear|back) leg\b",
            "rear_foot_displacement_inches": r"\b(?:rear|back) foot|\bheel\b",
            "rear_foot_displacement_leg_lengths": r"\b(?:rear|back) foot|\bheel\b",
            "rear_heel_grounded": r"\b(?:rear|back) foot|\bheel\b",
            "projected_torso_tilt": r"\btorso|\btrunk|\bchest\b|\bupright posture\b",
            "forward_torso_pitch_change": r"\btorso|\btrunk|\bchest\b|\bupright posture\b",
            "weapon_arm_direction": r"(?<!non-)(?<!non )\b(?:sword|weapon) (?:arm|hand)",
            "non_weapon_arm_direction": r"\bnon[- ](?:sword|weapon) (?:arm|hand)",
            "feet_separation_leg_lengths": r"\bfeet separation|\bstance length|\bstride length|\bdistance between (?:the )?feet",
        }
        phrase_features = {}
        for feature, pattern in feature_phrases.items():
            phrase_features.setdefault(pattern, set()).add(feature)
        for pattern, features in phrase_features.items():
            if (
                requested_topics
                and "lunge" not in requested_topics
                and not features.intersection(allowed_features)
                and re.search(pattern, reply, re.I)
            ):
                issues.append(
                    "The answer introduced feedback about an unrequested body part; stay within the athlete's requested feature and phase."
                )
        asks_for_assessment = bool(
            re.search(
                r"\b(?:how (?:was|were|did)\b|good or bad|good/bad|"
                r"(?:is|are|was|were) (?:it|they|those|these) (?:good|bad|correct|right)|"
                r"did i do (?:well|that right))\b",
                assessment_question,
                re.I,
            )
        )
        if asks_for_assessment and requested_topics and relevant_reference_available:
            assessment_pattern = re.compile(
                r"\b(?:match(?:es|ed)?|overlap(?:s|ped)?|within|outside|similar|aligned|"
                r"differ(?:s|ed|ent)?|straighter|more bent|less|on target|off target|"
                r"consistent|varied|closer|further|than|compared|good|bad|mixed|"
                r"better|worse|stronger|weaker|matched)\b",
                re.I,
            )
            if not assessment_pattern.search(reply):
                issues.append(
                    "The athlete asked for an assessment; say directly how the requested movement compares with its reference."
                )
            first_sentence = re.split(r"(?<=[.!?])\s+", reply.strip(), maxsplit=1)[0]
            if not assessment_pattern.search(first_sentence):
                issues.append(
                    "Lead with the direct assessment, not a generic coaching cue, when the athlete asks how the reps were."
                )
        if request.technique_evaluation.get("reps") and re.search(
            r"\b(?:no|not|isn't|aren't)\b.{0,45}\b(?:rep breakdown|rep data|repetition data)\b|"
            r"\brep breakdown\b.{0,35}\b(?:not (?:available|detailed)|missing|unavailable)\b",
            reply,
            re.I,
        ):
            issues.append(
                "The current session has per-rep evidence; do not claim the breakdown is missing."
            )
        issues += response_evidence_issues(
            original_question,
            reply,
            available=relevant_evidence_available
            and intent.needs_video_metrics
            and not general_instruction(request.question),
        )
        return issues

    def measured(items):
        items = list(items)
        consulted.update({metric.metric_id: metric for metric in items})
        return [
            metric.model_dump(
                mode="json",
                include={
                    "metric_id",
                    "name",
                    "value",
                    "unit",
                    "confidence",
                    "start_ms",
                    "end_ms",
                    "baseline_value",
                },
                exclude_none=True,
            )
            for metric in items
        ]

    @tool
    def get_technique_evaluation(
        feature_names: list[str] | None = None,
        phase_names: list[str] | None = None,
        rep_numbers: list[int] | None = None,
    ) -> str:
        """Read exact session records with source IDs, phase sample ranges, approved references and corrections. Select feature/phase names and rep numbers from the inventory; empty filters read all. Choose the data by the question's meaning, not a canned topic category."""
        source = evaluation_source(request)
        sources[source.source_id] = source
        return json.dumps(
            session_evidence_context(
                request, feature_names or (), phase_names or (), rep_numbers or ()
            ),
            separators=(",", ":"),
        )

    @tool
    def get_reviewed_feedback(rep_number: int = 0) -> str:
        """Read submitted human technique feedback for this clip, with its evidence frames and intended drill. Zero reads all reps; a positive number selects that rep. Role is self-declared; this is not an automatic model verdict."""
        reps = (
            [r for r in request.reviewed_feedback.get("reps", []) if r["rep_number"] == rep_number]
            if rep_number
            else request.reviewed_feedback.get("reps", [])
        )
        if request.reviewed_feedback.get("status") != "submitted" or not reps:
            return json.dumps({"error": "No submitted feedback for that rep."})
        source = feedback_source(request, reps)
        sources[source.source_id] = source
        return source.text

    @tool
    def get_session_metrics(metric_name: str = "", rep_number: int = 0) -> str:
        """Read all matching current-session measurements without truncation. Select a metric substring and optional rep number from the session inventory; empty name and rep zero read all. Filtering follows these explicit arguments, not a guessed question category."""
        needle = metric_name.lower().strip()
        if needle in {"lunge", "lunges", "technique", "form", "all"}:
            needle = ""
        terms = ("arm", "elbow", "shoulder") if needle == "arm" else (needle,)
        items = [
            metric
            for metric in request.metrics
            if not needle or any(term in metric.name.lower() for term in terms)
        ]
        if "arm" in question_topics(needle):
            sides = arm_sides(needle, request.capture_profile)
            items = [
                metric
                for metric in request.metrics
                if metric.name.startswith(tuple(side + "_" for side in sides))
                and any(
                    term in metric.name for term in ("arm_extension", "elbow_angle", "wrist_height")
                )
            ]
        if rep_number:
            items = [
                m
                for m in items
                if _rep_key(m) and int(_rep_key(m).rsplit(":", 1)[-1]) == rep_number
            ]
        return json.dumps(
            {
                "measurements": measured(items),
                "matching_count": len(items),
                "coaching_brief": evidence_summary(request, items),
                "capture_profile": request.capture_profile,
                "notes": request.session_notes[:1500],
                "limits": "Measurements describe tracked image-plane motion, not a pass/fail technique verdict.",
            }
        )

    @tool
    def inspect_reviewed_rep(rep_number: int = 0) -> str:
        """List reviewed movement intervals with timestamps. Give a one-based rep number for its measured details; zero lists intervals. These are timing windows, not verified lunge classifications."""
        if request.technique_evaluation.get("reps"):
            packet = json.loads(current_session_context(request))
            reps = packet["per_rep_measurements"]
            if rep_number:
                selected = next((rep for rep in reps if rep["rep"] == rep_number), None)
                return json.dumps(selected or {"error": "That reviewed rep is not available."})
            return json.dumps(
                {
                    "current_session_id": request.session_id,
                    "rep_count": len(reps),
                    "intervals": [
                        {
                            "rep_number": rep["rep"],
                            "finish_seconds": rep["finish_seconds"],
                            "phases": {
                                name: phase["interval_seconds"]
                                for name, phase in rep["phases"].items()
                            },
                        }
                        for rep in reps
                    ],
                }
            )
        grouped = {}
        for metric in request.metrics:
            if metric.start_ms is not None and metric.end_ms is not None:
                key = _rep_key(metric)
                if key:
                    grouped.setdefault(key, []).append(metric)
        ordered = sorted(
            (
                (
                    (
                        min(metric.start_ms for metric in items),
                        max(metric.end_ms for metric in items),
                    ),
                    items,
                )
                for items in grouped.values()
            ),
            key=lambda item: item[0],
        )
        if rep_number == 0:
            return json.dumps(
                {
                    "intervals": [
                        {"rep_number": index + 1, "start_ms": window[0], "end_ms": window[1]}
                        for index, (window, _) in enumerate(ordered)
                    ],
                    "limit": "Intervals may describe different phases; do not count them as verified lunges.",
                }
            )
        if rep_number < 1 or rep_number > len(ordered):
            return json.dumps({"error": "That reviewed interval is not available."})
        window, items = ordered[rep_number - 1]
        return json.dumps(
            {
                "rep_number": rep_number,
                "start_ms": window[0],
                "end_ms": window[1],
                "measurements": measured(items),
                "capture_profile": request.capture_profile,
            }
        )

    @tool
    def compare_to_baseline(metric_name: str = "", phase: str = "", rep_number: int = 0) -> str:
        """Read approved phase-matched reference-rep comparisons, source identities and supported cues. Use exact feature/phase names from the session inventory; empty filters read all, rep zero reads all reps. Scalar baseline deltas are separate observations, not correctness verdicts."""
        items = [metric for metric in request.metrics if metric_name.lower() in metric.name.lower()]
        if phase:
            # Raw scalar metrics do not carry canonical phase attribution.
            items = []
        elif rep_number:
            items = [
                metric
                for metric in items
                if _rep_key(metric) and int(_rep_key(metric).rsplit(":", 1)[-1]) == rep_number
            ]
        return json.dumps(
            {
                "reference_rep_comparisons": baseline_context(
                    request, metric_name, phase, rep_number
                ),
                "measurements": measured(items),
                "comparisons": [
                    {
                        "metric_id": metric.metric_id,
                        "delta": metric.value - metric.baseline_value
                        if metric.baseline_value is not None
                        else None,
                        "unit": metric.unit,
                    }
                    for metric in items
                ],
            }
        )

    @tool
    def search_coaching_library(query: str) -> str:
        """Retrieve relevant authored fencing guidance and its measurement limitations."""
        docs = search_knowledge(
            query, limit=3 if needs_tools else 1, use_embeddings=(mode == "bedrock")
        )
        sources.update({doc.source_id: doc for doc in docs})
        return json.dumps(
            [
                {
                    "source_id": doc.source_id,
                    "source": doc.source,
                    "text": compact_guidance(doc.text, 1000 if needs_tools else 650),
                }
                for doc in docs
            ]
        )

    @tool
    def get_training_history() -> str:
        """Read self-reported practice logs, not independently measured video evidence."""
        return json.dumps(request.training_history[:8])

    @tool
    def get_previous_reviews() -> str:
        """Read earlier review summaries as conversational context, not proof of technique."""
        return json.dumps(request.previous_reviews)

    @tool
    def compare_recent_sessions(metric_name: str) -> str:
        """Compare a named measurement with prior sessions and flag capture comparability explicitly."""
        metric_name = metric_name.strip()
        if not metric_name:
            return json.dumps({"error": "Choose one specific measurement to compare."})
        matched_current = [
            metric for metric in request.metrics if metric_name.lower() in metric.name.lower()
        ]
        current_units = {metric.unit for metric in matched_current}
        current_profile = request.capture_profile or {}
        sessions = []
        for session in request.session_history[:5]:
            prior_profile = session.get("capture_profile") or {}
            comparable, reason = comparable_capture(current_profile, prior_profile)
            measurements = [
                metric
                for metric in session["metrics"]
                if metric_name.lower() in metric["name"].lower() and metric["unit"] in current_units
            ][:12]
            sessions.append(
                {
                    "session_id": session["session_id"],
                    "date": session["date"],
                    "capture_comparable": comparable,
                    "comparability_reason": reason,
                    "capture_profile": prior_profile,
                    "measurements": measurements,
                }
            )
        return json.dumps(
            {
                "metric": metric_name,
                "current_measurement_available": bool(matched_current),
                "current_units": sorted(current_units),
                "sessions": sessions,
                "comparison_policy": "Only same-unit measurements from sessions marked capture_comparable support a measured comparison. A change is not itself improvement.",
            },
            separators=(",", ":"),
        )

    @tool
    def prepare_practice_plan(
        name: str, steps: list[str], success_criterion: str, knowledge_ids: list[str]
    ) -> str:
        """Draft a practice card when the athlete asks for a drill/plan. First retrieve relevant guidance, then cite its exact knowledge IDs. Does not save anything."""
        nonlocal plan
        if not knowledge_ids or any(source_id not in sources for source_id in knowledge_ids):
            return json.dumps(
                {"error": "Retrieve relevant coaching guidance before preparing a plan."}
            )
        if not name.strip() or not steps or len(steps) > 6 or not success_criterion.strip():
            return json.dumps(
                {"error": "Provide a name, one to six concrete steps, and what to watch for."}
            )
        plan = DrillRecommendation(
            name=name[:120],
            steps=[step[:500] for step in steps],
            success_criterion=success_criterion[:500],
            evidence=[
                EvidenceRef(
                    source_type="knowledge",
                    source_id=source_id,
                    note=sources[source_id].source.replace("_", " "),
                )
                for source_id in dict.fromkeys(knowledge_ids)
            ],
        )
        return json.dumps({"draft": plan.model_dump(), "saved": False})

    available = {
        item.name: item
        for item in (
            get_session_metrics,
            get_technique_evaluation,
            get_reviewed_feedback,
            inspect_reviewed_rep,
            compare_to_baseline,
            search_coaching_library,
            get_training_history,
            get_previous_reviews,
            compare_recent_sessions,
            prepare_practice_plan,
        )
    }
    detailed = wants_detail(request.question)
    advertised = list(available.values())
    needs_tools = True
    with_tools = model.bind_tools(advertised) if hasattr(model, "bind_tools") else model
    plain_model = model
    structured_dialogue = mode == "gemini" and hasattr(model, "with_structured_output")
    if structured_dialogue:
        output_options = {
            "response_mime_type": "application/json",
            "response_json_schema": AnswerDraft.model_json_schema(),
        }
        with_tools = with_tools.bind(**output_options)
        plain_model = model.bind(**output_options)
    if mode == "local" and hasattr(model, "bind"):
        budget = (
            240
            if detailed or re.search(r"\bplan\b", request.question, re.I)
            else (160 if needs_tools else max(80, min(180, settings.fencecoach_fast_reply_tokens)))
        )
        options = {"num_ctx": 32768, "num_predict": budget, "temperature": 0}
        with_tools = with_tools.bind(options=options)
        plain_model = model.bind(options=options)
    context = json.dumps(
        {
            "session_id": request.session_id,
            "skill_level": request.skill_level,
            "capture_profile": request.capture_profile,
            "available_measurements": len(request.metrics),
            "video_evidence_gap": request.evidence_unavailable_reason[:500],
        }
    )
    no_think = mode == "local" and "qwen3" in settings.ollama_chat_model
    directive = "\n/no_think" if no_think else ""
    policy = (
        SESSION_DIALOGUE_POLICY
        + "\nActive session identity and capture: "
        + context
        + "\nMotion interpretation:\n"
        + MOTION_POLICY
        + "\nAnswer presentation:\n"
        + ADVICE_FIRST_POLICY
        + "\nThe active-session packet is scoped to the request when a feature or phase is clear; its inventory shows what else the session contains. Treat it as the authority for personal feedback. Read-only tools return evidence data; you are the only component that writes the conversational answer. Call the coaching-library tool only when general technique knowledge is needed, and do not retrieve or repeat it by default."
        + "\nApplication-owned conversation scope: "
        + dialogue_state.model_dump_json(exclude={"last_cited_evidence"})
        + "\nResolved evidence query: "
        + resolved_question
        + "\nUse that scope as a contextual hint to resolve references and choose evidence. The athlete's latest explicit subject takes precedence; if it names something outside the inventory, explain the precise gap or clarify it. Answer the actual latest question naturally; the scope is not a script or a required answer format."
        + directive
    )
    corrected_scope = corrected_subject(original_question)
    if corrected_scope != original_question:
        policy += (
            "\nThe athlete is correcting the previous answer. The corrected subject is: "
            + corrected_scope
            + ". Treat that as authoritative, discard the previous off-topic feature, "
            "and answer only the corrected subject unless the athlete asks for more."
        )
    if structured_dialogue:
        policy += (
            "\nReturn the supplied JSON schema. Cite exact packet evidence IDs for every "
            "personal observation and comparison in session_evidence_ids; keep IDs out "
            "of the conversational answer. Check the whole packet before declaring an "
            "aspect unavailable. Use tools when the supplied evidence cannot answer it. "
            "For ordinary analysis, write a brief qualitative assessment in answer and "
            "one representative rep/statistic in supporting_example. The interface joins "
            "them as one compact reply. For an explicit numerical question, give the "
            "numbers directly in answer; for an all-reps request, cover all requested reps."
        )
    if all_reps_requested:
        policy += (
            "\nThe athlete requests every repetition: give one concise, distinct line "
            "per supplied rep in order, then the overall pattern and useful supported cue."
        )
    if requests_numbers(request.question):
        policy += (
            "\nThe latest request asks for numerical support. Give an actual value with units "
            "for the active feature, phase and rep, and briefly relate it to the observation "
            "or matching reference. One example is enough unless all values were requested. "
            "Do not return only the earlier qualitative assessment."
        )
    system = SystemMessage(content=policy)

    def event(step, detail, start):
        return TraceEvent(
            step=step, detail=detail, elapsed_ms=round((time.perf_counter() - start) * 1000, 2)
        )

    def invoke_dialogue_model(selected_model, messages, plain, events, response_schema=None):
        """Retry transient provider failure on an alternate model with identical context."""
        nonlocal model, plain_model, with_tools, failover_used, provider_fallback
        try:
            return selected_model.invoke(messages)
        except (
            ModelAPIError,
            ModelConnectionError,
            ModelTimeoutError,
            TransportError,
            TimeoutError,
            ConnectionError,
        ):
            # Prefer local fallback before spending another cloud request.
            if (
                not provided_model
                and settings.fencecoach_local_fallback
                and provider_status()["local_ready"]
            ):
                raise
            if (
                provided_model
                or mode != "gemini"
                or failover_used
                or not settings.gemini_fallback_model
                or settings.gemini_fallback_model == settings.gemini_chat_model
            ):
                raise
            start = time.perf_counter()
            failover_used = True
            provider_fallback = True
            model = chat_model(mode, model_id=settings.gemini_fallback_model)
            plain_model = model
            with_tools = model.bind_tools(advertised) if needs_tools else model
            if structured_dialogue:
                with_tools = with_tools.bind(**output_options)
                plain_model = model.bind(**output_options)
            events.append(
                event(
                    "provider_failover",
                    "The primary provider failed; the alternate model received the same question and session evidence.",
                    start,
                )
            )
            alternate = (
                model.with_structured_output(
                    response_schema, method="json_schema", include_raw=True
                )
                if response_schema
                else plain_model
                if plain
                else with_tools
            )
            return alternate.invoke(messages)

    def _respond(state, plain=False):
        start = time.perf_counter()
        stream_guard_events = []
        if on_step:
            on_step("agent")
        messages = [system, *state["messages"]]
        if mode == "local":
            messages.append(
                SystemMessage(
                    content="LATEST ATHLETE QUESTION: "
                    + original_question
                    + ". Apply the shared evidence workflow to the complete requested scope. Resolve follow-ups using the recent conversation; current records override earlier answers."
                )
            )
        if clarification(request):
            messages.append(
                SystemMessage(
                    content="Answer the latest clarification: "
                    + original_question
                    + ". Resolve what it refers to using the conversation and session records. Correct earlier wrong guidance rather than repeating it."
                )
            )
        if plain:
            messages.append(
                SystemMessage(
                    content="Tool budget reached. Answer naturally using evidence already available; state a specific gap if needed."
                )
            )
        selected_model = plain_model if plain else with_tools
        response = invoke_dialogue_model(selected_model, messages, plain, stream_guard_events)
        usage = getattr(response, "usage_metadata", None) or {}
        return {
            "messages": [response],
            "rounds": state["rounds"] + 1,
            "input_tokens": state["input_tokens"] + int(usage.get("input_tokens", 0)),
            "output_tokens": state["output_tokens"] + int(usage.get("output_tokens", 0)),
            "trace": stream_guard_events
            + [
                event(
                    "conversation",
                    "Answered directly."
                    if not response.tool_calls
                    else "Requested coaching evidence.",
                    start,
                )
            ],
        }

    def respond(state, plain=False):
        with span("model_response", "LLM") as current:
            current.set_attribute(
                "llm.model_name",
                getattr(model, "model", None) or getattr(model, "model_id", None) or mode,
            )
            value = _respond(state, plain)
            current.set_attribute(
                "llm.token_count.prompt", value["input_tokens"] - state["input_tokens"]
            )
            current.set_attribute(
                "llm.token_count.completion", value["output_tokens"] - state["output_tokens"]
            )
            return value

    def invoke_tool(name, args):
        with span(name, "TOOL"):
            return available[name].invoke(args)

    def execute(state):
        messages, events = [], []
        count = state["calls"]
        if on_step:
            on_step("tools")
        for call in state["messages"][-1].tool_calls:
            start = time.perf_counter()
            if count >= 8:
                result = "Tool budget reached. Use the evidence already returned."
            else:
                count += 1
                try:
                    result = invoke_tool(call["name"], call["args"])
                except (KeyError, ValueError, TypeError) as exc:
                    result = "Tool input was unavailable or invalid: " + type(exc).__name__
            messages.append(ToolMessage(content=result, tool_call_id=call["id"]))
            events.append(event(call["name"], "Returned tool result.", start))
        return {"messages": messages, "calls": count, "trace": events}

    graph = StateGraph(ChatState)
    graph.add_node("respond", respond)
    graph.add_node("tools", execute)
    graph.add_node("final_answer", lambda state: respond(state, plain=True))
    graph.add_edge(START, "respond")
    graph.add_conditional_edges(
        "respond", lambda state: "tools" if state["messages"][-1].tool_calls else END
    )
    graph.add_conditional_edges(
        "tools",
        lambda state: "final_answer" if state["rounds"] >= 3 or state["calls"] >= 8 else "respond",
    )
    graph.add_edge("final_answer", END)
    # Keep the most recent exchange intact instead of overflowing the model's
    # context with twelve potentially six-thousand-character messages.
    history_limit = 6000 if detailed else 2600 if _needs_measurements(request.question) else 1600
    exchanges = []
    pending_user = None
    for item in request.conversation_history:
        if item.role == "user":
            pending_user = item
        elif item.role == "assistant" and pending_user is not None:
            exchanges.append((pending_user, item))
            pending_user = None
    recent_history = []
    remaining = history_limit
    for user_message, assistant_message in reversed(exchanges):
        cost = len(user_message.content) + len(assistant_message.content)
        if cost <= remaining:
            recent_history[0:0] = [user_message, assistant_message]
            remaining -= cost
            continue
        if not recent_history and remaining >= 2:
            # Preserve the latest question and its answer as a pair. If the old
            # answer was unusually long, keep its ending within the same budget.
            user_budget = min(len(user_message.content), 240, max(1, remaining // 3))
            assistant_budget = remaining - user_budget
            if user_budget and assistant_budget:
                recent_history = [
                    user_message.model_copy(
                        update={"content": user_message.content[-user_budget:]}
                    ),
                    assistant_message.model_copy(
                        update={"content": assistant_message.content[-assistant_budget:]}
                    ),
                ]
        break
    history = [
        HumanMessage(content=item.content)
        if item.role == "user"
        else AIMessage(content=item.content)
        for item in recent_history
    ]
    initial_messages = [*history, HumanMessage(content=original_question + directive)]
    session_check_started = time.perf_counter()
    session_snapshot = current_session_context(request)
    answer_packet = json.loads(question_scoped_session_context(request))
    if scoped_feedback_source:
        answer_packet["submitted_feedback"] = {
            "evidence_id": scoped_feedback_source.source_id,
            "feedback": json.loads(scoped_feedback_source.text),
        }
    answer_snapshot = json.dumps(answer_packet, separators=(",", ":"))
    relevant_evidence_available = bool(answer_packet.get("session_measurements")) or any(
        rep.get("measures")
        or rep.get("reference_comparisons")
        or any(phase.get("values") for phase in rep.get("phases", {}).values())
        for rep in answer_packet.get("per_rep_measurements", [])
    )
    relevant_reference_available = any(
        rep.get("reference_comparisons") for rep in answer_packet.get("per_rep_measurements", [])
    )
    session_source = KnowledgeSource(
        source_id=f"current-session:{request.session_id}",
        source="Current session evidence check",
        text=session_snapshot,
    )
    sources[session_source.source_id] = session_source
    initial_messages.insert(
        0,
        SystemMessage(
            content="Active session evidence checked against the athlete's latest question (reference data): "
            + (coaching_session_context(answer_snapshot))
        ),
    )
    initial_trace = [
        event(
            "assess_current_session",
            "Selected active-session evidence for the exact question before composing the answer.",
            session_check_started,
        )
    ]
    initial_calls = 0
    if evaluation_context:
        start = time.perf_counter()
        source = evaluation_source(request)
        sources[source.source_id] = source
        initial_trace.append(
            event(
                "get_technique_evaluation",
                "Read per-rep geometry, action timing and explicit rubric findings.",
                start,
            )
        )
    if reviewed_reps:
        start = time.perf_counter()
        source = scoped_feedback_source
        sources[source.source_id] = source
        initial_trace.append(
            event(
                "get_reviewed_feedback",
                "Loaded submitted rep-specific feedback and evidence frames.",
                start,
            )
        )
    result = graph.compile().invoke(
        {
            "messages": initial_messages,
            "trace": initial_trace,
            "rounds": 0,
            "calls": initial_calls,
            "input_tokens": 0,
            "output_tokens": 0,
        },
        config={"recursion_limit": 12},
    )
    reply = format_timings(_text(result["messages"][-1]))
    metadata = getattr(result["messages"][-1], "response_metadata", {}) or {}
    if not reply:
        raise CoachAnswerError(
            "The coach returned an empty answer. Your question is kept; try again."
        )
    semantically_reviewed = False
    cited_session_ids = []
    review_validation_issues = []
    if structured_dialogue:
        start = time.perf_counter()
        packet = json.loads(session_snapshot)
        try:
            draft = AnswerDraft.model_validate_json(reply)
        except ValueError as exc:
            raise CoachAnswerError(
                "The coach returned an incomplete answer. Your question is kept; try again."
            ) from exc
        cited_session_ids = list(draft.session_evidence_ids)
        # The independent reviewer judges the writer's answer and evidence IDs;
        # it cannot replace the conversational answer with its own prose.
        reviewer = model.with_structured_output(
            AnswerReview, method="json_schema", include_raw=True
        )
        reviews = []
        # Review independently against the full active session. Restricting this
        # to the draft's citations lets a generic/wrong-topic draft hide evidence.
        review_packet = json.loads(coaching_session_context(answer_snapshot))
        reviewed = invoke_dialogue_model(
            reviewer,
            review_messages(
                request.question,
                {
                    "answer": draft.conversational_text,
                    "writer_evidence_ids": draft.session_evidence_ids,
                },
                review_packet,
                [
                    {"id": doc.source_id, "text": doc.text}
                    for doc in sources.values()
                    if "#chunk-" in doc.source_id
                ],
                [
                    {"role": item.role, "content": item.content}
                    for item in request.conversation_history[-4:]
                ],
            ),
            True,
            reviews,
            response_schema=AnswerReview,
        )
        decision = reviewed.get("parsed")
        requested_features = requested_feature_names(request)
        requested_phases = (
            question_phases(request.question) if explicit_phase_requested(request.question) else ()
        )
        requested_rep = intent.rep_number
        requested_reps = intent.rep_numbers
        numbers = [r["rep"] for r in packet.get("per_rep_measurements", [])]
        if all_reps_requested or intent.kind == "rep_comparison":
            requested_reps = tuple(numbers)
        if numbers and intent.kind in {"first_rep", "last_rep"}:
            requested_rep = min(numbers) if intent.kind == "first_rep" else max(numbers)
        timing_gap = (
            intent.topic == "arm"
            and re.search(
                r"\b(before|after|earlier|later|timing|onset|start)\b", request.question, re.I
            )
            and "arm_extension_timing" not in packet.get("measured_features_available", [])
        )
        require_session = bool(
            relevant_evidence_available
            and (latest_intent.needs_video_metrics or requests_numbers(original_question))
            and not clarification(request)
            and not timing_gap
        )
        validation = review_issues(
            decision,
            packet,
            requested_features if not clarification(request) else (),
            requested_rep,
            require_session,
            requested_phases,
            requested_reps,
            draft.conversational_text,
        )
        if not set(draft.session_evidence_ids).issubset(evidence_ids(packet)):
            validation.append("The writer cited an evidence ID absent from the current session.")
        validation += cited_subject_issues(
            packet,
            draft.session_evidence_ids,
            requested_features if not clarification(request) else (),
            requested_rep,
            requested_phases,
            requested_reps,
        )
        if isinstance(decision, AnswerReview):
            validation += style_issues(
                request.question, draft.conversational_text, personal=bool(evidence_ids(packet))
            )
        if validation:
            logging.getLogger(__name__).warning(
                "Coach response review rejected the draft: %s", validation
            )
            review_validation_issues = validation
            reply = format_timings(draft.conversational_text)
            usage = getattr(reviewed.get("raw"), "usage_metadata", None) or {}
            result["input_tokens"] += int(usage.get("input_tokens", 0))
            result["output_tokens"] += int(usage.get("output_tokens", 0))
            result["trace"].extend(reviews)
        else:
            semantically_reviewed = True
            reply = format_timings(draft.conversational_text)
            usage = getattr(reviewed.get("raw"), "usage_metadata", None) or {}
            result["input_tokens"] += int(usage.get("input_tokens", 0))
            result["output_tokens"] += int(usage.get("output_tokens", 0))
            result["trace"].extend(reviews)
            result["trace"].append(
                event(
                    "semantic_review",
                    "Reviewed relevance and interpretation against actual session record IDs. "
                    + " ".join(decision.corrections),
                    start,
                )
            )
    # Semantic review validates evidence identity, while local checks validate
    # the conversational scope and prevent a reviewed draft from repeating a
    # rejected prior answer or switching body parts.
    issues = list(
        dict.fromkeys(
            conversation_issues(request, reply)
            + answer_issues(reply, request.metrics)
            + claim_issues(reply, request.metrics)
            + review_validation_issues
        )
    )
    if (
        not semantically_reviewed
        and metadata.get("done_reason") == "length"
        and reply[-1] not in ".!?"
    ):
        issues.append("The answer was cut off before completion.")
    if issues:
        start = time.perf_counter()
        if on_step:
            on_step("grounding")
        repairs = []
        repair_instruction = HumanMessage(
            content=(
                "Repair the preceding draft while answering the SAME original question: "
                + original_question
                + ". Keep the corrected subject, active-session evidence and conversation. "
                "Do not substitute a different body part, generic drill or a canned reply. "
                "Resolve these validation issues: " + json.dumps(issues)
            )
        )
        if structured_dialogue:
            # The conversational writer remains the only component that can
            # author the reply. The separate reviewer can accept or flag it,
            # then the writer gets one bounded chance to correct the same answer.
            writer = model.with_structured_output(
                AnswerDraft, method="json_schema", include_raw=True
            )
            rewritten = invoke_dialogue_model(
                writer,
                [system, *result["messages"], repair_instruction],
                True,
                repairs,
                response_schema=AnswerDraft,
            )
            repaired_draft = rewritten.get("parsed")
            if not isinstance(repaired_draft, AnswerDraft):
                raise CoachAnswerError(
                    "The coach couldn't complete a corrected answer. Your question is kept; try again.",
                    issues,
                )
            reply = format_timings(repaired_draft.conversational_text)
            repaired = rewritten.get("raw")
            reviewer = model.with_structured_output(
                AnswerReview, method="json_schema", include_raw=True
            )
            reviewed_repair = invoke_dialogue_model(
                reviewer,
                review_messages(
                    request.question,
                    {
                        "answer": reply,
                        "writer_evidence_ids": repaired_draft.session_evidence_ids,
                    },
                    review_packet,
                    [
                        {"id": doc.source_id, "text": doc.text}
                        for doc in sources.values()
                        if "#chunk-" in doc.source_id
                    ],
                    [
                        {"role": item.role, "content": item.content}
                        for item in request.conversation_history[-4:]
                    ],
                ),
                True,
                repairs,
                response_schema=AnswerReview,
            )
            decision = reviewed_repair.get("parsed")
            if not isinstance(decision, AnswerReview):
                raise CoachAnswerError(
                    "The coach couldn't verify a corrected answer. Your question is kept; try again.",
                    issues,
                )
            remaining_review_issues = review_issues(
                decision,
                packet,
                requested_features if not clarification(request) else (),
                requested_rep,
                require_session,
                requested_phases,
                requested_reps,
                reply,
            )
            if not set(repaired_draft.session_evidence_ids).issubset(evidence_ids(packet)):
                remaining_review_issues.append(
                    "The corrected writer cited an evidence ID absent from the current session."
                )
            remaining_review_issues += cited_subject_issues(
                packet,
                repaired_draft.session_evidence_ids,
                requested_features if not clarification(request) else (),
                requested_rep,
                requested_phases,
                requested_reps,
            )
            remaining_issues = list(
                dict.fromkeys(
                    remaining_review_issues
                    + style_issues(
                        request.question,
                        reply,
                        personal=bool(evidence_ids(packet)),
                    )
                    + conversation_issues(request, reply)
                    + answer_issues(reply, request.metrics)
                    + claim_issues(reply, request.metrics)
                )
            )
            if remaining_issues:
                logging.getLogger(__name__).warning(
                    "Coach corrected answer rejected: %s", remaining_issues
                )
                raise CoachAnswerError(
                    "The coach couldn't verify a corrected answer. Your question is kept; try again.",
                    remaining_issues,
                )
            cited_session_ids = list(repaired_draft.session_evidence_ids)
            semantically_reviewed = True
            review_usage = getattr(reviewed_repair.get("raw"), "usage_metadata", None) or {}
            result["input_tokens"] += int(review_usage.get("input_tokens", 0))
            result["output_tokens"] += int(review_usage.get("output_tokens", 0))
        else:
            repaired = invoke_dialogue_model(
                plain_model,
                [system, *result["messages"], repair_instruction],
                True,
                repairs,
            )
            reply = format_timings(_text(repaired))
        repaired_metadata = getattr(repaired, "response_metadata", {}) or {}
        if repaired_metadata.get("done_reason") == "length" and reply and reply[-1] not in ".!?":
            raise CoachAnswerError(
                "The local coach couldn't complete a checked reply. Your question is kept; try again.",
                [*issues, "The repaired answer was truncated."],
            )
        usage = getattr(repaired, "usage_metadata", None) or {}
        result["input_tokens"] += int(usage.get("input_tokens", 0))
        result["output_tokens"] += int(usage.get("output_tokens", 0))
        result["trace"].extend(repairs)
        result["trace"].append(
            event(
                "answer_repair",
                "Rewrote the same question against the same evidence: " + " ".join(issues),
                start,
            )
        )
        plan = None
        if not structured_dialogue:
            remaining_issues = list(
                dict.fromkeys(
                    conversation_issues(request, reply)
                    + answer_issues(reply, request.metrics)
                    + claim_issues(reply, request.metrics)
                )
            )
        if not reply or (not structured_dialogue and remaining_issues):
            logging.getLogger(__name__).warning(
                "Coach answer repair failed local checks: %s",
                remaining_issues or ["The repaired answer was empty."],
            )
            raise CoachAnswerError(
                "The coach couldn't produce a supported answer to this question. Your question is kept; try again.",
                remaining_issues or ["The repaired answer was empty."],
            )
    reply = format_answer(reply)
    if not reply:
        raise CoachAnswerError(
            "The coach couldn't complete this answer. Your question is kept; try again."
        )
    if on_text:
        on_text(reply)
    observations = []
    observations.append(
        CoachingObservation(
            claim="Active-session evidence was checked first and used only where it answers the question.",
            evidence=[
                EvidenceRef(
                    source_type="knowledge",
                    source_id=session_source.source_id,
                    note="Question-aware summary of current clip measurements and review findings.",
                )
            ],
        )
    )
    if evaluation_context:
        source = evaluation_source(request)
        observations.append(
            CoachingObservation(
                claim=(
                    "Compared phase-specific measurements with submitted reference reps."
                    if request.technique_evaluation.get("coaching_mode") == "reference_comparison"
                    else "Automatic per-rep rubric findings consulted; heuristics are not validated technique classifications."
                ),
                evidence=[
                    EvidenceRef(
                        source_type="knowledge",
                        source_id=source.source_id,
                        note="Timestamped geometry and explicit basic-drill review flags.",
                    )
                ],
            )
        )
    if reviewed_reps:
        source = feedback_source(request, reviewed_reps)
        observations.append(
            CoachingObservation(
                claim="Submitted human technique feedback consulted; reviewer role is self-declared.",
                evidence=[
                    EvidenceRef(
                        source_type="knowledge",
                        source_id=source.source_id,
                        note=f"Submitted review revision {request.reviewed_feedback['revision']}; rep-specific human feedback.",
                    )
                ],
            )
        )
    guidance_sources = [doc for doc in sources.values() if "#chunk-" in doc.source_id]
    if guidance_sources and not consulted:
        observations.append(
            CoachingObservation(
                claim="General technique references consulted for this answer; this is not a video assessment.",
                evidence=[
                    EvidenceRef(
                        source_type="knowledge",
                        source_id=doc.source_id,
                        note="Technique guidance: " + doc.source,
                    )
                    for doc in guidance_sources[:3]
                ],
            )
        )
    if consulted:
        brief = build_coaching_brief(
            request.model_copy(update={"metrics": list(consulted.values())})
        )
        preferred = (brief.get("selected_focus") or {}).get("evidence_ids", [])
        evidence_metrics = sorted(
            consulted.values(), key=lambda metric: metric.metric_id not in preferred
        )
        observations.append(
            CoachingObservation(
                claim="Session measurements consulted for this answer.",
                evidence=[
                    EvidenceRef(
                        source_type="metric",
                        source_id=metric.metric_id,
                        note=metric.name.replace("_", " "),
                    )
                    for metric in evidence_metrics[:12]
                ],
            )
        )
    report = CoachingReport(summary=reply, observations=observations, next_drill=plan)
    refs = [ref for observation in observations for ref in observation.evidence]
    if plan:
        refs += plan.evidence
    dialogue_state.last_cited_evidence = list(
        dict.fromkeys([*cited_session_ids, *(ref.source_id for ref in refs)])
    )
    return RunRecord(
        run_id=uuid4().hex,
        session_id=request.session_id,
        created_at=datetime.now(UTC),
        question=original_question,
        response_kind="conversation",
        focus_metric_id=request.focus_metric_id,
        mode=mode,
        model_id=(
            (
                getattr(model, "model", None)
                or getattr(model, "model_id", None)
                or "alternate provider"
            )
            + " (provider failover)"
            if provider_fallback
            else getattr(model, "model", None)
            or getattr(model, "model_id", None)
            or configured_model_id(mode)
        ),
        retrieval_method="bedrock-vector"
        if mode == "bedrock" and settings.bedrock_embedding_model_id
        else "bm25",
        report=report,
        sources=list(sources.values()),
        trace=result["trace"],
        latency_ms=round((time.perf_counter() - started) * 1000, 2),
        input_tokens=result["input_tokens"],
        output_tokens=result["output_tokens"],
        citation_count=len(refs),
        citation_ids_valid=True,
        dialogue_state=dialogue_state,
        answer_contract={
            "engine": "llm_tools",
            "resolved_question": resolved_question,
            "model_authored": True,
            "semantic_reviewed": semantically_reviewed,
            "tool_calls": result["calls"],
            "session_evidence_ids": cited_session_ids,
        },
    )
