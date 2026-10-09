"""OpenInference spans for Phoenix, plus a durable local trace record."""

import json
import logging
import threading
from contextlib import contextmanager
from datetime import UTC, datetime

from fencecoach.settings import settings

_provider = None
_lock = threading.Lock()


def provider():
    global _provider
    with _lock:
        if _provider is None:
            from opentelemetry.sdk.resources import Resource
            from opentelemetry.sdk.trace import TracerProvider

            _provider = TracerProvider(
                resource=Resource.create(
                    {"service.name": "fencecoach", "openinference.project.name": "fencecoach"}
                )
            )
            if settings.fencecoach_phoenix_endpoint:
                from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
                from opentelemetry.sdk.trace.export import BatchSpanProcessor

                _provider.add_span_processor(
                    BatchSpanProcessor(
                        OTLPSpanExporter(endpoint=settings.fencecoach_phoenix_endpoint, timeout=3)
                    )
                )
        return _provider


@contextmanager
def span(name, kind="CHAIN"):
    tracer = provider().get_tracer("fencecoach")
    with tracer.start_as_current_span(name, attributes={"openinference.span.kind": kind}) as item:
        yield item


def record_run(run, root_span):
    run.trace_id = f"{root_span.get_span_context().trace_id:032x}"
    run.token_usage_available = bool(run.input_tokens or run.output_tokens)
    if run.mode in {"local", "demo"}:
        run.cost_usd = 0.0  # API fees only; excludes electricity/hardware.
    elif (
        run.token_usage_available
        and settings.fencecoach_input_usd_per_million is not None
        and settings.fencecoach_output_usd_per_million is not None
    ):
        run.cost_usd = (
            run.input_tokens * settings.fencecoach_input_usd_per_million
            + run.output_tokens * settings.fencecoach_output_usd_per_million
        ) / 1_000_000
    attributes = {
        "fencecoach.run_id": run.run_id,
        "fencecoach.session_id": run.session_id,
        "llm.model_name": run.model_id or "sample",
        "fencecoach.mode": run.mode,
        "fencecoach.latency_ms": run.latency_ms,
        "llm.token_count.prompt": run.input_tokens,
        "llm.token_count.completion": run.output_tokens,
        "fencecoach.token_usage_available": run.token_usage_available,
        "fencecoach.citation_count": run.citation_count,
    }
    if run.cost_usd is not None:
        attributes["llm.cost.total"] = run.cost_usd
    root_span.set_attributes(attributes)
    record = {
        "created_at": datetime.now(UTC).isoformat(),
        "trace_id": run.trace_id,
        **attributes,
        "steps": [s.model_dump() for s in run.trace],
        "cost_note": "API fee estimate from configured rates; local fees zero; cancelled streams may not report tokens.",
    }
    try:
        path = settings.fencecoach_db_path.parent / "traces/coach.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        with _lock, path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(record) + "\n")
    except OSError:
        logging.exception("Could not persist local coaching trace")


def flush():
    if _provider is not None:
        _provider.force_flush(timeout_millis=5000)
