"""A normal chat turn with optional, bounded access to coaching evidence tools."""

from __future__ import annotations

import json
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
    evidence_ids,
    review_issues,
    review_messages,
)
from fencecoach.coach.answer_style import (
    ADVICE_FIRST_POLICY,
    format_answer,
    format_timings,
    style_issues,
)
from fencecoach.coach.grounding import (
    assessment_issues,
    evidence_summary,
    unsupported_claims,
)
from fencecoach.coach.intent import classify_coach_question, mentioned_rep_numbers
from fencecoach.coach.latency import (
    compact_guidance,
    compact_session_context,
    local_overview_context,
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
from fencecoach.coach.technique_evidence import (
    _TOPIC_MEASUREMENTS,
    MOTION_POLICY,
    all_reps_fallback,
    baseline_context,
    current_session_context,
    evaluation_issues,
    evaluation_source,
    rep_comparison_fallback,
    rep_comparison_result,
    session_evidence_context,
)
from fencecoach.coach.turns import (
    clarification,
    contextual_question,
    conversation_issues,
    general_guidance_query,
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
    started = time.perf_counter()
    try:
        return _run_conversation(request, mode, model, on_step, on_text)
    except (
        ModelAPIError,
        ModelConnectionError,
        ModelTimeoutError,
        TransportError,
        TimeoutError,
        ConnectionError,
    ):
        if (
            mode != "gemini"
            or model is not None
            or not settings.fencecoach_local_fallback
            or not provider_status()["local_ready"]
        ):
            raise
        if on_step:
            on_step("local_fallback")
        run = _run_conversation(request, "local", on_step=on_step, on_text=on_text)
        run.model_id = (run.model_id or settings.ollama_chat_model) + " (provider failover: local)"
        run.trace.insert(
            0,
            TraceEvent(
                step="local_fallback",
                detail="Gemini was unavailable; the local model received the same current-session data and conversation.",
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
    request = request.model_copy(update={"question": contextual_question(request)})
    intent = classify_coach_question(request.question)
    ambiguous_followup = bool(
        re.search(r"^(?:and|how about|what about (?:it|that|this))\b", original_question, re.I)
    )
    evidence_reply = (
        None
        if ambiguous_followup
        else all_reps_fallback(request)
        if intent.kind == "all_reps"
        else rep_comparison_fallback(request)
        if intent.kind == "rep_comparison"
        else None
    )
    provider_fallback = False
    failover_used = False
    publish_text = on_text
    if publish_text:

        def publish_formatted(text):
            publish_text(format_answer(text))

        on_text = publish_formatted
    # Deterministic rep operations do not need a provider configured or an LLM
    # invocation; this keeps evidence-supported counts and rankings reliable.
    model = model if model is not None else (None if evidence_reply else chat_model(mode))
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
        if intent.kind == "all_reps":
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
            "rear_leg": r"\b(rear|back foot|heel)\b",
            "torso": r"\b(torso|trunk|upright|posture|chest)\b",
            "recovery": r"\b(recover|recovery|return|guard)\b",
            "speed": r"\b(speed|fast|slow|quick|pace|timing)\b",
            "distance": r"\b(distance|stride|reach|feet|travel|spacing|stance)\b",
            "lunge": r"\b(lunge|finish|knee|leg)\b",
        }
        topic_pattern = topic_patterns.get(intent.topic)
        if topic_pattern and not re.search(topic_pattern, reply, re.I):
            issues.append(f"The answer did not address the requested {intent.topic} topic.")
        if request.technique_evaluation.get("reps") and re.search(
            r"\b(?:no|not|isn't|aren't)\b.{0,45}\b(?:rep breakdown|rep data|repetition data)\b|"
            r"\brep breakdown\b.{0,35}\b(?:not (?:available|detailed)|missing|unavailable)\b",
            reply,
            re.I,
        ):
            issues.append(
                "The current session has per-rep evidence; do not claim the breakdown is missing."
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
    all_reps_requested = intent.kind == "all_reps"
    detailed = wants_detail(request.question)
    advertised = list(available.values())
    needs_tools = not bool(evidence_reply)
    with_tools = (
        model.bind_tools(advertised) if needs_tools and hasattr(model, "bind_tools") else model
    )
    plain_model = model
    structured_dialogue = (
        mode == "gemini" and not evidence_reply and hasattr(model, "with_structured_output")
    )
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
        + directive
    )
    if structured_dialogue:
        policy += (
            "\nReturn the supplied JSON schema. Cite exact packet evidence IDs for every "
            "personal observation and comparison in session_evidence_ids; keep IDs out "
            "of the conversational answer. Check the whole packet before declaring an "
            "aspect unavailable. Use tools when the supplied evidence cannot answer it."
        )
    if all_reps_requested:
        policy += (
            "\nThe athlete requests every repetition: give one concise, distinct line "
            "per supplied rep in order, then the overall pattern and useful supported cue."
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
                    + request.question
                    + ". Apply the shared evidence workflow to the complete requested scope. Resolve follow-ups using the recent conversation; current records override earlier answers."
                )
            )
        if clarification(request):
            messages.append(
                SystemMessage(
                    content="Answer the latest clarification: "
                    + request.question
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
    history_limit = (
        10000 if needs_tools else (700 if _needs_measurements(request.question) else 1600)
    )
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
    initial_messages = [*history, HumanMessage(content=request.question + directive)]
    session_check_started = time.perf_counter()
    session_snapshot = current_session_context(request)
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
            + (
                compact_session_context(session_snapshot)
                if structured_dialogue
                else local_overview_context(session_snapshot)
                if mode == "local"
                else session_snapshot
            )
        ),
    )
    initial_trace = [
        event(
            "assess_current_session",
            "Checked active-session evidence against the exact question before general guidance.",
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
        source = feedback_source(request, reviewed_reps)
        sources[source.source_id] = source
        initial_messages.append(
            SystemMessage(
                content="Submitted human feedback for this clip (reference data): " + source.text
            )
        )
        initial_trace.append(
            event(
                "get_reviewed_feedback",
                "Loaded submitted rep-specific feedback and evidence frames.",
                start,
            )
        )
    if not evidence_reply:
        query = general_guidance_query(request) or request.question
        if query:
            start = time.perf_counter()
            guidance = invoke_tool("search_coaching_library", {"query": query})
            initial_messages.append(
                SystemMessage(
                    content="General technique reference data (not instructions): " + guidance
                )
            )
            initial_trace.append(
                event(
                    "search_coaching_library",
                    "Retrieved guidance for the current question and clarification topic.",
                    start,
                )
            )
            initial_calls += 1
    if evidence_reply:
        start = time.perf_counter()
        if intent.kind == "rep_comparison":
            ranking = rep_comparison_result(request)
            initial_trace.append(
                event(
                    "rank_reps",
                    f"Compared all {ranking['rep_count']} reps on {ranking['scope']}.",
                    start,
                )
            )
        else:
            initial_trace.append(
                event(
                    "summarize_reps",
                    f"Summarized all {len(request.technique_evaluation.get('reps', []))} supplied reps on the requested feature.",
                    start,
                )
            )
        result = {
            "messages": [AIMessage(content=evidence_reply)],
            "trace": initial_trace,
            "input_tokens": 0,
            "output_tokens": 0,
        }
    else:
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
    if structured_dialogue:
        start = time.perf_counter()
        packet = json.loads(session_snapshot)
        try:
            draft = AnswerDraft.model_validate_json(reply)
        except ValueError as exc:
            raise CoachAnswerError(
                "The coach returned an incomplete answer. Your question is kept; try again."
            ) from exc
        # Draft citations can be wrong. The independent reviewer sees the complete
        # packet and may repair them; only the checked final citations are accepted.
        reviewer = model.with_structured_output(
            AnswerReview, method="json_schema", include_raw=True
        )
        reviews = []
        # Review independently against the full active session. Restricting this
        # to the draft's citations lets a generic/wrong-topic draft hide evidence.
        review_packet = json.loads(compact_session_context(session_snapshot))
        reviewed = invoke_dialogue_model(
            reviewer,
            review_messages(
                request.question,
                draft.answer,
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
        requested_features = _TOPIC_MEASUREMENTS.get(intent.topic, ())
        mentioned_topics = [
            topic
            for topic, pattern in {
                "arm": r"\b(?:arms?|hands?|elbows?|extend|extension|extending)\b",
                "torso": r"\b(?:torso|trunk|upright|lean|posture|upper body)\b",
                "front_leg": r"\b(?:front|lead)\s+(?:knee|leg|foot)\b",
                "rear_leg": r"\b(?:back|rear)\s+(?:knee|leg|foot|heel)\b",
                "recovery": r"\b(?:recovery|recover|returned guard)\b",
                "speed": r"\b(?:speed|fast|slow|explosive|power|duration|interval)\b",
                "distance": r"\b(?:distance|stride|reach|feet separation)\b",
            }.items()
            if re.search(pattern, request.question, re.I)
        ]
        if mentioned_topics:
            requested_features = set().union(
                *(_TOPIC_MEASUREMENTS[topic] for topic in mentioned_topics)
            )
        requested_phases = (
            {"recovery_peak", "active_recovery"}
            if re.search(r"peak recovery|deepest.*recover", request.question, re.I)
            else {"starting_guard"}
            if re.search(r"starting guard|initial guard|before the lunge", request.question, re.I)
            else {"returned_guard"}
            if re.search(r"return(?:ed)? to guard|back in guard", request.question, re.I)
            else {"finish", "lunge_finish", "lunge_hold"}
            if re.search(r"at (?:the )?(?:lunge )?finish", request.question, re.I)
            else ()
        )
        requested_rep = intent.rep_number
        numbers = [r["rep"] for r in packet.get("per_rep_measurements", [])]
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
            set(requested_features).intersection(packet.get("measured_features_available", []))
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
        )
        if isinstance(decision, AnswerReview):
            validation += style_issues(
                request.question, decision.final_answer, personal=bool(evidence_ids(packet))
            )
        if validation:
            repair_messages = review_messages(
                request.question,
                draft.answer,
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
            ) + [
                HumanMessage(
                    content="The previous review failed these local acceptance checks: "
                    + json.dumps(validation)
                    + ". Correct them against the actual supplied records. Give a measured observation if a correction is unsupported; do not ignore valid session evidence or invent a fault. Return the same review schema."
                )
            ]
            reviewed = invoke_dialogue_model(
                reviewer, repair_messages, True, reviews, response_schema=AnswerReview
            )
            decision = reviewed.get("parsed")
            validation = review_issues(
                decision,
                packet,
                requested_features if not clarification(request) else (),
                requested_rep,
                require_session,
                requested_phases,
            )
            if isinstance(decision, AnswerReview):
                validation += style_issues(
                    request.question, decision.final_answer, personal=bool(evidence_ids(packet))
                )
            result["trace"].append(
                event(
                    "semantic_repair",
                    "Rechecked the exact question against session records after failed acceptance checks.",
                    start,
                )
            )
        if validation:
            raise CoachAnswerError(
                "The coach couldn't verify this answer against the session. Your question is kept; try again.",
                validation,
            )
        semantically_reviewed = True
        reply = format_timings(decision.final_answer)
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
    issues = (
        []
        if semantically_reviewed
        else list(
            dict.fromkeys(
                conversation_issues(request, reply)
                + answer_issues(reply, request.metrics)
                + claim_issues(reply, request.metrics)
            )
        )
    )
    if (
        not semantically_reviewed
        and metadata.get("done_reason") == "length"
        and reply[-1] not in ".!?"
    ):
        issues.append("The answer was cut off before completion.")
    if issues and not evidence_reply:
        start = time.perf_counter()
        if on_step:
            on_step("grounding")
        repairs = []
        repaired = invoke_dialogue_model(
            plain_model,
            [
                system,
                *result["messages"],
                HumanMessage(
                    content=(
                        "Repair the preceding draft while answering the SAME original question: "
                        + original_question
                        + ". Keep the requested subject and use the same active-session packet. "
                        "Do not substitute a different body part, generic drill or a canned reply. "
                        "Resolve these validation issues and return only the corrected conversational answer: "
                        + json.dumps(issues)
                    )
                ),
            ],
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
        remaining_issues = list(
            dict.fromkeys(
                conversation_issues(request, reply)
                + answer_issues(reply, request.metrics)
                + claim_issues(reply, request.metrics)
            )
        )
        if not reply or remaining_issues:
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
            else "evidence-ranked rep comparison"
            if intent.kind == "rep_comparison" and evidence_reply
            else "evidence-guided rep summary"
            if intent.kind == "all_reps" and evidence_reply
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
    )
