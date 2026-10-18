"""Layer 1: model, standing briefing, recent chat, and two optional tool calls.

No turn resolver, selector, reviewer, repair loop or retrieval precondition.
The old core remains the default and retains its production checks.
"""

from __future__ import annotations

import json
import time
from datetime import UTC, datetime
from functools import lru_cache
from uuid import uuid4

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import tool

from fencecoach.coach.providers import chat_model, configured_model_id
from fencecoach.coach.router import route
from fencecoach.coach.technique_evidence import current_session_context, session_evidence_context
from fencecoach.rag.knowledge import search_knowledge
from fencecoach.schemas import CoachingReport, CoachRequest, KnowledgeSource, RunRecord, TraceEvent

PERSONA = """You are Flèche, talking with the athlete about their saved practice clip.
Answer the current question in a few natural sentences. Carry the topic and rep through
follow-ups using the recent chat. When ambiguous, state a reasonable assumption and proceed.
Use evidence tools for specific numbers or details beyond the standing briefing. Tools are
optional; you have at most two tool calls per turn. Use the library for coaching explanations
and drills. Only state numbers, faults, cues or drills supported by the briefing, tool results
or retrieved library; when a specific item is missing, say so for that item and share what is
known. Distinguish a measured shape from an interpretation. Explain why an observation matters
when asked, without reciting the same measurement. Treat prior replies as conversation, not
proof. Speak plainly, and keep source IDs in the evidence trace rather than in spoken prose."""

# Prompt-only experiments for the Layer 1 checkpoint. V0 remains the saved
# baseline; V1 tests a less defensive coach voice, V2 changes briefing shape,
# and V3 also improves the tool contracts.
PERSONA_V1 = """You are Flèche, a practical fencing coach talking with an athlete about this clip.
Answer the question they just asked first, in plain, natural language. Keep it brief and
specific; respond to what they mean in this conversation instead of restarting a report.
For an ambiguous follow-up, use the most likely meaning from the recent chat and say your
assumption in a few words. Ask one short question only if two readings are equally likely.
Use the session briefing for known facts and call a tool when a requested detail is missing
or needs another rep or phase. Tools are for you: never announce, propose, or ask permission
to look something up. Use no more than two tool calls, then answer. Do not repeat a number,
restate the whole measurement, or add an offer to continue unless that helps this turn.
Keep measured facts separate from coaching judgment. Only give clip-specific numbers, faults,
cues, or drills supported by the briefing, a tool result, or a library entry. If one requested
fact is unavailable, say that briefly and still answer the parts you can. If you give general
advice, label it as general. Sound like a coach in an ongoing conversation, not a report."""
PERSONA_V2 = PERSONA_V1
PERSONA_V3 = PERSONA_V1

EVIDENCE_TOOL_V0 = "Read saved values/reference cues. Select features, optional phases/reps; empty lists read all. Raw arm features retain detected-event labels."
LIBRARY_TOOL_V0 = "Find authored explanations, cues and drills. Empty results mean that item is missing; answer with the evidence you have."
EVIDENCE_TOOL_V3 = "Get clip measurements or reference comparisons for a requested feature, rep or phase. Use exact feature names in the briefing. If the feature is unclear, pass empty feature_names to inspect all evidence. Never substitute a different rep or phase; raw arm samples are detected events, not phase values."
LIBRARY_TOOL_V3 = "Search authored fencing explanations, cues or drills using the athlete's wording. Use for general technique questions or a named drill, not clip measurements. Results are teaching material, not facts about this athlete. If no entry matches, say that item is unavailable and answer from session evidence you do have."


def _json(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def _session_key(request):
    # Only evidence affects caching: no question, chat, resolved scope or old reviews.
    return _json(
        request.model_dump(
            mode="json",
            include={
                "session_id",
                "metrics",
                "capture_profile",
                "technique_evaluation",
                "reviewed_feedback",
                "session_notes",
                "evidence_unavailable_reason",
            },
        )
    )


@lru_cache(maxsize=32)
def _snapshot(key):
    request = CoachRequest.model_validate({**json.loads(key), "question": "Session briefing"})
    evaluation = dict(request.technique_evaluation)
    evaluation["reps"] = [
        rep
        for rep in evaluation.get("reps", [])
        if rep.get("status") not in {"unsupported", "unavailable"}
        and rep.get("geometry_available", True)
    ]
    request = request.model_copy(update={"technique_evaluation": evaluation})
    if request.evidence_unavailable_reason:
        request = request.model_copy(update={"metrics": [], "technique_evaluation": {}})
    packet = json.loads(current_session_context(request))
    # Reuse the measured evidence serializer, not its question focus or instruction.
    for field in (
        "instruction",
        "question_relevant_focus",
        "supported_current_observations",
        "recurring_reference_comparison",
        "per_rep_reference_findings",
    ):
        packet.pop(field, None)
    for row in packet["session_measurements"]:
        if "arm_extension" in row["feature"] and row.get("unit") == "ratio":
            row["meaning"] = (
                "Shoulder-to-wrist distance divided by upper-arm plus forearm length in the image. "
                "A ratio near one describes a straighter tracked arm, not extension timing or correctness."
            )
    return _json(packet)


@lru_cache(maxsize=32)
def _briefing(key):
    data = json.loads(key)
    packet = json.loads(_snapshot(key))
    evaluation = data.get("technique_evaluation", {})
    profile = data.get("capture_profile", {})
    reps = packet["per_rep_measurements"]
    clip_type = (
        profile.get("drill_type")
        or profile.get("activity")
        or (
            f"{profile['scene_type']} practice"
            if profile.get("scene_type")
            else "unspecified practice"
        )
    )
    quality = evaluation.get("whole_clip_quality", "not recorded")
    gap = data.get("evidence_unavailable_reason", "")
    lines = [
        f"Session {data['session_id']}. Clip: {clip_type}. Recorded reps: {packet['current_clip_reps_detected']}.",
        f"Tracking quality: {quality}. Evidence availability: {gap or 'saved measurements below'}.",
        f"Declared weapon arm: {profile.get('weapon_arm', 'unknown')}; front leg: {profile.get('front_leg', 'unknown')}; camera: {profile.get('camera_view', 'unspecified')}.",
        "These are projected image measurements. Angles describe shape, not force or balance; torso lean is magnitude from upright. Reach ratios divide shoulder-to-wrist distance by upper-arm plus forearm length in the image. Larger included elbow/knee angles mean straighter joints. Finish-to-guard includes holds; active recovery is a separate estimated interval. Unknown phase stays unknown. Compare references for the same feature and phase. Reference examples retain reviewer corrections and are not universal ideals. Name anatomical/weapon roles from the capture profile, and image directions as image directions. Tools expose other reps, phases and approved reference cues.",
        "Standing examples (not a whole-set assessment):",
    ]
    features = (
        "weapon_elbow_angle",
        "feet_separation",
        "front_knee_angle",
        "estimated_active_recovery_time",
        "finish_to_guard_time",
        "action_to_lunge_time",
    )
    for feature in features:
        found = next(((r, r["measures"][feature]) for r in reps if feature in r["measures"]), None)
        if found:
            rep, row = found
            lines.append(
                f"Rep {rep['rep']}, {row.get('phase') or 'interval/phase unspecified'}: {feature} = {row['value']} {row['unit']}."
            )
        else:
            lines.append(f"{feature}: no saved phase measurement.")
    arm_side = profile.get("weapon_arm")
    reach = next(
        (
            m
            for m in packet["session_measurements"]
            if "arm_extension" in m["feature"]
            and (arm_side not in {"left", "right"} or m["feature"].startswith(arm_side + "_"))
        ),
        None,
    )
    if reach:
        lines.append(
            f"Rep {reach['rep']}, {reach['feature']} (raw event, not phase median): {reach['value']} {reach['unit']}, {reach.get('start_ms')} ms."
        )
    else:
        lines.append("Arm reach: no raw measurement available.")
    unavailable = sorted({str(x) for r in reps for x in r.get("review_checks", [])})
    if unavailable:
        lines.append("Warnings: " + "; ".join(unavailable)[:200])
    features = sorted({name for rep in reps for name in rep["measures"]})
    if features:
        lines.append("Other evidence feature names: " + ", ".join(features))
    return "\n".join(lines)


@lru_cache(maxsize=32)
def _briefing_v2(key):
    """A compact evidence-first briefing with aliases matching athlete language."""
    data = json.loads(key)
    packet = json.loads(_snapshot(key))
    profile = data.get("capture_profile") or {}
    evaluation = data.get("technique_evaluation") or {}
    reps = packet.get("per_rep_measurements", [])
    feature_names = sorted({name for rep in reps for name in rep.get("measures", {})})
    aliases = {
        "torso / torso lean": "projected_torso_tilt",
        "back leg / rear knee": "rear_knee_angle",
        "front knee": "front_knee_angle",
        "arm bend": "weapon_elbow_angle",
        "recovery": "estimated_active_recovery_time and finish_to_guard_time (includes holds)",
    }
    available_aliases = [
        f"{label} = {feature}"
        for label, feature in aliases.items()
        if any(feature in names for names in (feature_names,))
    ]
    if any(
        "arm_extension" in row.get("feature", "") for row in packet.get("session_measurements", [])
    ):
        available_aliases.append(
            "arm reach / extension = weapon_arm_direction and declared weapon-side arm_extension_at_onset sample"
        )
    if not available_aliases:
        available_aliases.append(
            "no matching saved feature name is listed; inspect evidence before saying the clip has no data"
        )
    lines = [
        f"Clip: {profile.get('drill_type') or profile.get('activity') or 'practice'}; {packet.get('current_clip_reps_detected')} detected reps; tracking {evaluation.get('whole_clip_quality', 'quality not recorded')}.",
        f"Roles: weapon arm {profile.get('weapon_arm', 'unknown')}; front leg {profile.get('front_leg', 'unknown')}; camera {profile.get('camera_view', 'unspecified')}. Measurements are projected image evidence, not force, balance, calibrated distance or real-world speed.",
        "Use recent chat to understand short follow-ups. A rep value describes that rep only. A measured shape is evidence; a judgment such as good, stable or effective is interpretation. Compare only the same feature and phase. Reference examples are not universal targets; reviewer corrections are not observations of this athlete.",
        "Use exact saved values for clip facts. Missing evidence for one feature does not erase evidence for another. Reach-at-onset is a raw detected sample, not a phase median or proof of correct timing. Angles describe projected shape; do not infer force, balance, speed, stability or cause from an angle alone. Give a simple interpretation when asked, label it as coaching judgment, and tie it to a visible comparison or label general advice as general.",
        "Athlete wording to saved feature names: " + "; ".join(available_aliases) + ".",
        "Saved measurements (rep, phase, feature=value):",
    ]
    measurements = []
    for rep in reps:
        for feature, row in rep.get("measures", {}).items():
            measurements.append(
                (
                    rep.get("rep", 0),
                    row.get("phase") or "phase unspecified",
                    feature,
                    row.get("value"),
                    row.get("unit"),
                )
            )
    for rep, phase, feature, value, unit in measurements[:8]:
        lines.append(f"Rep {rep} {phase}: {feature}={value} {unit}.")
    for row in packet.get("session_measurements", []):
        if "arm_extension" in row.get("feature", ""):
            lines.append(
                f"Rep {row.get('rep')}, raw detected event (not phase median): {row['feature']}={row.get('value')} {row.get('unit')} at {row.get('start_ms')} ms."
            )
            break
    if not measurements and not packet.get("session_measurements"):
        lines.append("No saved measurements are available for this clip.")
    if feature_names:
        lines.append("Other exact evidence feature names: " + ", ".join(feature_names) + ".")
    return "\n".join(lines)


def standing_briefing(request, profile="v3"):
    if profile in {"v2", "v3"}:
        return _briefing_v2(_session_key(request))
    return _briefing(_session_key(request))


def _text(message):
    if isinstance(message.content, str):
        return message.content.strip()
    return "\n".join(
        x.get("text", "")
        for x in message.content
        if isinstance(x, dict) and x.get("type") == "text"
    ).strip()


def run_new_core(request, mode, model=None, on_step=None, on_text=None, profile="packet"):
    if profile == "packet":
        from fencecoach.coach.core_packet import run_packet_core

        return run_packet_core(request, mode, model, on_step, on_text)
    if model is not None:
        return _generate(request, mode, model, on_step, on_text, profile)
    started = time.perf_counter()
    run, reason = route(
        lambda provider: _generate(request, provider, chat_model(provider), on_step, None, profile),
        mode,
    )
    run.fallback_reason = reason
    run.latency_ms = round((time.perf_counter() - started) * 1000, 2)
    if on_text:
        on_text(run.report.summary)
        run.first_visible_ms = run.latency_ms
    return run


def _generate(request, mode, model, on_step, on_text, profile="v3"):
    started = time.perf_counter()
    key = _session_key(request)
    persona = PERSONA if profile == "v0" else PERSONA_V1
    briefing, snapshot = standing_briefing(request, profile), _snapshot(key)
    sources, trace = {}, []

    def event(step, detail):
        trace.append(
            TraceEvent(
                step=step,
                detail=detail,
                elapsed_ms=round((time.perf_counter() - started) * 1000, 2),
            )
        )
        if on_step:
            on_step(step)

    evidence_description = EVIDENCE_TOOL_V3 if profile == "v3" else EVIDENCE_TOOL_V0
    library_description = LIBRARY_TOOL_V3 if profile == "v3" else LIBRARY_TOOL_V0

    @tool(description=evidence_description)
    def get_session_evidence(
        feature_names: list[str],
        phase_names: list[str] | None = None,
        rep_numbers: list[int] | None = None,
    ) -> str:
        """Read saved values and reference cues."""
        packet = session_evidence_context(
            request, feature_names, phase_names or (), rep_numbers or (), snapshot=snapshot
        )
        result = {
            "session_id": request.session_id,
            "reps": packet["per_rep_measurements"],
            "raw_metrics": packet["session_measurements"],
            "reference_baselines": packet["reference_baselines"],
            "feature_meanings": {
                k: v
                for k, v in packet["feature_meanings"].items()
                if not feature_names or k in feature_names
            },
            "submitted_feedback": packet["submitted_feedback"],
            "measurement_policy": packet["measurement_policy"],
        }
        encoded = _json(result)
        sources[f"session:{request.session_id}"] = KnowledgeSource(
            source_id=f"session:{request.session_id}", source="Saved session evidence", text=encoded
        )
        return encoded

    @tool(description=library_description)
    def search_coaching_library(query: str) -> str:
        """Find authored explanations, cues and drills."""
        docs = search_knowledge(query, limit=3)
        sources.update({d.source_id: d for d in docs})
        return _json([d.model_dump(mode="json") for d in docs])

    tools = [get_session_evidence, search_coaching_library]
    by_name = {t.name: t for t in tools}
    messages = [SystemMessage(content=persona + "\n\n" + briefing)]
    messages += [
        (HumanMessage if m.role == "user" else AIMessage)(content=m.content)
        for m in request.conversation_history[-10:]
    ]
    messages.append(HumanMessage(content=request.question))
    event(
        "layer1_input",
        _json(
            {
                "persona": persona,
                "profile": profile,
                "briefing": briefing,
                "history": [m.model_dump() for m in request.conversation_history[-10:]],
                "question": request.question,
            }
        ),
    )
    calls = input_tokens = output_tokens = 0
    bound = model.bind_tools(tools)
    for _ in range(3):
        event("agent", f"{mode}:{configured_model_id(mode)}; tool calls used {calls}/2")
        try:
            response = (bound if calls < 2 else model).invoke(messages)
        except Exception as exc:
            event("provider_error", _json({"provider": mode, "exception_type": type(exc).__name__}))
            exc.layer1_trace = trace
            raise
        usage = getattr(response, "usage_metadata", None) or {}
        input_tokens += usage.get("input_tokens", 0)
        output_tokens += usage.get("output_tokens", 0)
        tool_calls = getattr(response, "tool_calls", [])
        event(
            "layer1_model",
            _json({"text": _text(response), "tool_calls": tool_calls, "usage": usage}),
        )
        messages.append(response)
        if not tool_calls:
            answer = _text(response)
            if not answer:
                raise RuntimeError("The Layer 1 provider returned no answer.")
            break
        for call in tool_calls:
            if calls >= 2:
                result = _json(
                    {"tool_budget": "Two calls used. Answer now using available evidence."}
                )
            else:
                calls += 1
                try:
                    result = by_name[call["name"]].invoke(call["args"])
                except Exception as exc:
                    # Missing evidence is not an answer gate.
                    result = _json(
                        {"tool_error": type(exc).__name__, "item_unavailable": call["name"]}
                    )
            event("tools", _json({"name": call["name"], "args": call["args"], "result": result}))
            messages.append(ToolMessage(content=result, tool_call_id=call["id"]))
        messages.append(
            SystemMessage(
                content=f"Tool calls remaining: {max(0, 2 - calls)}. Answer from available evidence when none remain."
            )
        )
    else:
        raise RuntimeError("The Layer 1 provider did not finish within the tool budget.")
    elapsed = round((time.perf_counter() - started) * 1000, 2)
    if on_text:
        on_text(answer)
    event("layer1_answer", answer)
    return RunRecord(
        run_id=uuid4().hex,
        session_id=request.session_id,
        created_at=datetime.now(UTC),
        question=request.question,
        response_kind="conversation",
        mode=mode,
        model_id=configured_model_id(mode),
        retrieval_method="optional-bm25",
        report=CoachingReport(summary=answer),
        sources=list(sources.values()),
        trace=trace,
        latency_ms=elapsed,
        first_visible_ms=elapsed if on_text else None,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        token_usage_available=bool(input_tokens),
        citation_count=0,
        citation_ids_valid=True,
        answer_contract={
            "core": "new",
            "layer": 1,
            "model_authored": True,
            "tool_calls": calls,
            "checks": "none",
        },
    )
