"""Measure queued local replies over HTTP using explicitly synthetic demo data."""

import json
import time
from pathlib import Path

import httpx
import numpy as np


def main():
    rows = []
    with httpx.Client(base_url="http://127.0.0.1:8001", timeout=30) as client:
        client.get("/health").raise_for_status()
        sessions = client.get("/api/sessions").json()
        demo = next((s for s in sessions if s.get("is_demo") and not s.get("video_job_id")), None)
        if demo is None:
            response = client.post("/api/demo")
            response.raise_for_status()
            demo = response.json()
        for question in (
            "What can you tell me about my lunge from this evidence?",
            "Which measurements can help me understand my arm extension?",
            "What is recovery in fencing?",
            "Why?",
        ):
            started = time.perf_counter()
            response = client.post(
                f"/api/sessions/{demo['session_id']}/coaching-jobs",
                json={"question": question, "mode": "local"},
            )
            response.raise_for_status()
            job = response.json()
            first = None
            while time.perf_counter() - started < 60:
                response = client.get(f"/api/coaching-jobs/{job['job_id']}")
                response.raise_for_status()
                job = response.json()
                elapsed = (time.perf_counter() - started) * 1000
                if job.get("partial_reply") and first is None:
                    first = elapsed
                if job["status"] in {"completed", "failed"}:
                    break
                time.sleep(0.1)
            if job["status"] != "completed":
                raise RuntimeError(job.get("error") or "Reply timed out")
            run = client.get(f"/api/reports/{job['run_id']}").json()
            rows.append(
                {
                    "question": question,
                    "completion_ms": round(elapsed, 2),
                    "first_text_ms": round(first, 2) if first else None,
                    "model_latency_ms": run["latency_ms"],
                    "grounding_replacement": any(s["step"] == "grounding" for s in run["trace"]),
                    "answer": run["report"]["summary"],
                }
            )
            print(question, round(elapsed), flush=True)
    report = {
        "scope": "Warmed same-machine queued HTTP requests, polled every 100ms, synthetic demo measurements with accumulating conversation history; not real-video or expert-quality validation.",
        "cases": len(rows),
        "p50_ms": float(np.percentile([r["completion_ms"] for r in rows], 50)),
        "p95_ms": float(np.percentile([r["completion_ms"] for r in rows], 95)),
        "first_text_p50_ms": float(
            np.percentile([r["first_text_ms"] for r in rows if r["first_text_ms"]], 50)
        ),
        "answers": rows,
    }
    destination = Path("data/evals/reply-latency-http.json")
    destination.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "answers"}), flush=True)


if __name__ == "__main__":
    main()
