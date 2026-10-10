"""Missing evidence is a conversation outcome, rather than a failed chat request."""

import re
import time
from datetime import UTC, datetime
from uuid import uuid4

from fencecoach.schemas import CoachingReport, RunRecord, TraceEvent


def needs_evidence_reply(request, mode):
    if not request.evidence_unavailable_reason:
        return False
    if (
        any(
            "projected_torso_tilt" in r.get("measurements", {})
            for r in request.technique_evaluation.get("reps", [])
        )
        and mode != "demo"
    ):
        return False
    from fencecoach.coach.conversation import _needs_measurements
    from fencecoach.coach.turns import general_instruction, history_instruction

    # Desired positions and "how should I...?" remain answerable from teaching
    # references even when the uploaded clip fails tracking QA.
    if mode != "demo" and (
        general_instruction(request.question) or history_instruction(request.question)
    ):
        return False

    return (
        mode == "demo"
        or _needs_measurements(request.question)
        or bool(
            re.search(
                r"\b(video|clip|reps?|baseline|compare|measurements?|timestamps?)\b",
                request.question,
                re.I,
            )
        )
    )


def evidence_reply(request, mode, on_step=None, on_text=None):
    started = time.perf_counter()
    reason = request.evidence_unavailable_reason.removeprefix(
        "This video is unsupported for coaching. "
    )
    reply = (
        "I can discuss the technique, but this clip's tracking check doesn't give me "
        "reliable evidence for a personal correction yet. "
        + reason
        + " You can ask a general fencing question here, or choose Try sample chat "
        "to explore a review using sample measurements."
    )
    if on_step:
        on_step("evidence_check")
    if on_text:
        on_text(reply)
    return RunRecord(
        run_id=uuid4().hex,
        session_id=request.session_id,
        created_at=datetime.now(UTC),
        question=request.question,
        response_kind="conversation",
        mode=mode,
        model_id="evidence-check",
        retrieval_method="none",
        report=CoachingReport(summary=reply, limitations=[request.evidence_unavailable_reason]),
        sources=[],
        trace=[
            TraceEvent(
                step="evidence_check",
                detail="Explained missing video evidence; no rejected measurements or model generation used.",
                elapsed_ms=round((time.perf_counter() - started) * 1000, 2),
            )
        ],
        latency_ms=round((time.perf_counter() - started) * 1000, 2),
        input_tokens=0,
        output_tokens=0,
        citation_count=0,
        citation_ids_valid=True,
    )
