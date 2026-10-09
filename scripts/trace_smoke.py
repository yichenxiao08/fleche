"""Verify a real local model/tool trace reaches the local Phoenix database."""

import json
import sqlite3
import time
from pathlib import Path

from fencecoach.coach.graph import run_coach
from fencecoach.schemas import CoachRequest, SessionCreate
from fencecoach.settings import settings
from fencecoach.telemetry import flush


def main():
    project = Path(__file__).resolve().parents[1]
    settings.fencecoach_phoenix_endpoint = "http://127.0.0.1:6006/v1/traces"
    settings.ollama_chat_model = "qwen2.5:1.5b"
    sample = SessionCreate.model_validate_json(
        (project / "src/fencecoach/web/sample-session.json").read_text(encoding="utf-8-sig")
    )
    run = run_coach(
        CoachRequest(
            session_id="trace-synthetic-measurements",
            metrics=sample.metrics,
            question="How consistent are the measured recovery intervals?",
        ),
        mode="local",
    )
    flush()
    databases = list((project / "data/phoenix").rglob("*.db"))
    if not databases:
        raise RuntimeError("Phoenix database is unavailable.")
    for _ in range(30):
        with sqlite3.connect(str(databases[0])) as db:
            rows = db.execute(
                "SELECT count(*) FROM traces WHERE trace_id=?", (run.trace_id,)
            ).fetchone()[0]
            spans = db.execute(
                "SELECT name FROM spans WHERE trace_rowid IN (SELECT id FROM traces WHERE trace_id=?)",
                (run.trace_id,),
            ).fetchall()
        if rows == 1 and len(spans) >= 3:
            break
        time.sleep(0.2)
    assert rows == 1 and len(spans) >= 3, (rows, spans)
    report = {
        "status": "passed",
        "trace_id": run.trace_id,
        "model": run.model_id,
        "latency_ms": run.latency_ms,
        "input_tokens": run.input_tokens,
        "output_tokens": run.output_tokens,
        "token_usage_available": run.token_usage_available,
        "cost_usd": run.cost_usd,
        "spans": [r[0] for r in spans],
        "input": "Synthetic sample measurements; live local model, tools, and actual Phoenix collector.",
    }
    (project / "data/evals/tracing-smoke.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )
    print(json.dumps(report))


if __name__ == "__main__":
    main()
