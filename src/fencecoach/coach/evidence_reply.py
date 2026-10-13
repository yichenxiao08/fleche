"""Missing evidence is a conversation outcome, rather than a failed chat request."""

import time
from datetime import UTC, datetime
from uuid import uuid4

from fencecoach.schemas import CoachingReport, RunRecord, TraceEvent


def needs_evidence_reply(request, mode):
    # A live coach must inspect the same available session context and answer
    # the actual question, even when tracking failed. Do not replace personal
    # follow-ups with a canned request for a new video based on their wording.
    return mode == "demo" and bool(request.evidence_unavailable_reason)


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
