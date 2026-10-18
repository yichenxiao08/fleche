"""Extract selected genuine saved failure episodes; never generate historical dialogue."""

import json
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "evals/layer1"
# These are manually worded interactions with persisted user/assistant history.
# Fast scripted smoke runs (notably Oct 9 16:55/17:04/17:24) are excluded.
EPISODES = [
    ("H01", "knees-back-speed", "lost topic", ["d5b1d501b", "3fc37d6b3", "aad1cf338"]),
    (
        "H02",
        "arm-clarification",
        "lost topic",
        ["f8aa377bf", "2a78b53b5", "2aa43692f", "9853845b1"],
    ),
    ("H03", "general-arm-angle", "router misclassification", ["44e004b5a", "b54f11b07"]),
    ("H04", "fleche-followups", "lost topic", ["68758b2fa", "e8f83a015", "267f2c4bd"]),
    ("H05", "rep-two-advice", "lost topic", ["eb04c7d79", "b69b25456", "544032a6a"]),
    ("H06", "last-rep", "provider error", ["94aee5e5b", "f6b25728c", "350a36c9d"]),
    (
        "H07",
        "ranking-arm-torso",
        "lost topic",
        ["ec71dbf21", "b55d91406", "52d0566fc", "7fadecfa5", "1c9e6a5a1"],
    ),
    ("H08", "rear-leg-good", "lost topic", ["c83a95009", "86ca8a924", "1e5facfad"]),
    (
        "H09",
        "torso-good-rear-leg",
        "prompt pushing refusal",
        ["3012aeb80", "0f551d6f7", "5b8c06f91", "3e9c59f6b", "53fa88ad5", "a9f7a72a0"],
    ),
    ("H10", "arm-partial-correction", "check blocking reply", ["245307e07", "daeb1c0cf"]),
]


def extract():
    db = sqlite3.connect(f"file:{ROOT / 'data/fencecoach.sqlite3'}?mode=ro", uri=True)
    runs = {
        json.loads(s)["run_id"]: json.loads(s) for (s,) in db.execute("SELECT payload FROM runs")
    }
    jobs = []
    counts = {}
    for table in ("sessions", "runs", "coaching_jobs", "coaching_jobs_v2"):
        counts[table] = db.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
        if table.startswith("coaching_jobs"):
            jobs.extend(
                (table, json.loads(s)) for (s,) in db.execute(f"SELECT payload FROM {table}")
            )
    episodes = []
    for ident, name, tag, prefixes in EPISODES:
        turns = []
        for prefix in prefixes:
            matches = [(table, p) for table, p in jobs if p["job_id"].startswith(prefix)]
            assert len(matches) == 1, prefix
            table, job = matches[0]
            run = runs.get(job.get("run_id"))
            turns.append(
                {
                    "question": job["request"]["question"],
                    "old_answer": run["report"]["summary"] if run else job.get("partial_reply", ""),
                    "old_error": job.get("error"),
                    "old_report": run.get("report") if run else None,
                    "old_provider": run.get("mode") if run else job.get("mode"),
                    "old_latency_ms": run.get("latency_ms") if run else None,
                    "created_at": job["created_at"],
                    "source": f"data/fencecoach.sqlite3:{table}:{job['job_id']}",
                    "run_id": job.get("run_id"),
                    "failure_detail": job.get("failure_detail"),
                    "request": job["request"],
                }
            )
        episodes.append(
            {
                "id": ident,
                "name": name,
                "origin": "historical saved user episode",
                "tag": tag,
                "turns": turns,
            }
        )
    db.close()
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "historical_inputs.json").write_text(
        json.dumps({"counts": counts, "episodes": episodes}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    lines = [
        "# Coach failure diagnosis — Layer 1",
        "",
        "Read-only diagnosis, 2026-10-14: all 9 sessions, 113 runs, 121 coaching_jobs, 9 coaching_jobs_v2 and saved histories in data/fencecoach.sqlite3; data logs, evals/results, evals/coach_audit, work/coach-audit logs; Codex thread 01a138b9-5e3f-75f3-8512-f968ba7825ec (confirms review failures, adds no athlete chat). Audit fixtures and fast scripted DB smoke runs are excluded.",
        "",
        "**10 historical failure episodes, 34 turns, exactly 4 identifiable saved session chat streams** retained; fewer than 10 independent conversations in this selection. Overlapping context is not independent history. Fill the gap with explicitly labeled **replays of these same sequences** on both providers. Original turns, complete old summaries/errors, requests and IDs: `evals/layer1/historical_inputs.json`. The DB lacks an author flag: human provenance is conservatively inferred from saved context, timings, script matches and the user-confirmed October 14 sequence.",
        "",
        "| Episode | Original excerpt / old behavior | Failure tag | DB table + job source |",
        "|---|---|---|---|",
    ]
    excerpts = [
        "“what about my knees and legs” → “Focus on the arm extension for now.”",
        "“which arm” → repeats “extend your arm to the side” without naming the arm.",
        "General “at what angle should i extend my sword arm and non sword arm” → tracking refusal.",
        "Flèche follow-up → “After executing the lunge…” loses the action.",
        "“so what should i do” → generic explosive-drive advice drops measured rep/hold context.",
        "“what about my last rep” → provider error, then treats rep 2 as last in a five-rep clip.",
        "“what about torso” → “I don't have usable movement evidence”; next torso reply gives knee angle.",
        "“was it good” after rear-leg question → answers about front knee.",
        "“so is this good” / “so its good to have it upright correct?” → repeats torso measurement; straighter/bent later times out.",
        "“how is my arm extension” → reach ratio 1.0 only; “is this good or bad, do i need to make any changes” → CoachAnswerError.",
    ]
    for ep, excerpt in zip(episodes, excerpts, strict=True):
        source = ep["turns"][-1]["source"].split(":", 1)[1]
        lines.append(f"| {ep['id']} | {excerpt} | {ep['tag']} | {source} (full chain in inputs) |")
    lines.extend(
        [
            "",
            "Mechanism: routing/retrieval narrows evidence prematurely; selectors repeat numbers instead of interpreting follow-ups; review/repair rejects prose after a partial answer. Empty-retrieval/prompt-refusal causes are suspected, not proven where traces are missing. Layer 1 must supply session context and recent messages every turn, let the model choose evidence and answer, and expose provider errors. Preserve the old production safeguards.",
        ]
    )
    (ROOT / "docs/coach_failure_diagnosis.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "counts": counts,
                "historical_episodes": len(episodes),
                "turns": sum(len(x["turns"]) for x in episodes),
                "session_streams": len({x["turns"][0]["request"]["session_id"] for x in episodes}),
            }
        )
    )


if __name__ == "__main__":
    extract()
