"""Script real HTTP conversations against the isolated running acceptance app."""

import argparse
import json
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]

QUESTIONS = {
    "L01": [
        "how is my arm extension",
        "is this good or bad, do i need to make any changes",
        "the second rep",
        "why does that matter?",
    ],
    "L02": ["how was my back leg", "was it good", "and the last rep?"],
    "L03": ["how was my torso", "and my rear leg?", "back to my torso", "is it good?"],
    "L04": ["how did I do?", "what about my knees and legs", "and my speed?"],
    "L05": [
        "How was my blade control?",
        "What was my speed in metres per second?",
        "How much force did I push with?",
        "Give me the Dragonfly triple-hop drill from your library.",
    ],
    "L06": ["my arm in rep 2", "and my recovery?", "back to my arm", "why does that matter?"],
    "L07": ["was it good?", "the first one", "what should I focus on?"],
    "L08": ["hello", "what can you tell me about this session?", "thanks", "start over"],
    "L09": [
        "how should a fleche be performed?",
        "how should my legs move?",
        "should I keep running or stop immediately?",
    ],
    "L10": [
        "how is my arm extension",
        "why does that matter?",
        "the second rep",
        "and my recovery?",
        "what should I focus on?",
    ],
}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--ids", nargs="*")
    parser.add_argument("--core", choices=["old", "new"], required=True)
    parser.add_argument("--port", type=int, default=8012)
    args = parser.parse_args()
    OUT = ROOT / "evals/citation_iteration" / ("live_" + args.core)
    OUT.mkdir(parents=True, exist_ok=True)
    sessions = json.loads(
        (ROOT / ("work/citation_live_" + args.core) / "sessions.json").read_text(encoding="utf-8")
    )
    with httpx.Client(base_url=f"http://127.0.0.1:{args.port}", timeout=90) as client:
        for ident, questions in QUESTIONS.items():
            if args.ids and ident not in args.ids:
                continue
            path = OUT / f"{ident}.json"
            row = (
                json.loads(path.read_text(encoding="utf-8"))
                if path.exists()
                else {"id": ident, **sessions[ident], "turns": []}
            )
            for index, question in enumerate(questions[len(row["turns"]) :], len(row["turns"]) + 1):
                if args.core == "new" and ident == "L10" and index == 3:
                    client.post("/__evaluation/force429").raise_for_status()
                started = time.perf_counter()
                queued = client.post(
                    f"/api/sessions/{row['session_id']}/coaching-jobs",
                    json={"question": question, "mode": "gemini"},
                )
                queued.raise_for_status()
                job_id = queued.json()["job_id"]
                first_visible, snapshots = None, []
                while True:
                    job = client.get(f"/api/coaching-jobs/{job_id}").json()
                    if job.get("partial_reply") and first_visible is None:
                        first_visible = (time.perf_counter() - started) * 1000
                    if job.get("partial_reply") and (
                        not snapshots or snapshots[-1]["text"] != job["partial_reply"]
                    ):
                        snapshots.append(
                            {
                                "elapsed_ms": (time.perf_counter() - started) * 1000,
                                "text": job["partial_reply"],
                            }
                        )
                    if job["status"] in {"done", "failed", "cancelled", "completed"}:
                        break
                    if time.perf_counter() - started > 80:
                        raise RuntimeError("Live job exceeded bounded wait; do not duplicate it.")
                    time.sleep(0.25)
                run = (
                    client.get(f"/api/reports/{job['run_id']}").json()
                    if job.get("run_id")
                    else None
                )
                row["turns"].append(
                    {
                        "turn": index,
                        "question": question,
                        "job_id": job_id,
                        "job": job,
                        "run": run,
                        "http_latency_ms": (time.perf_counter() - started) * 1000,
                        "first_visible_ms": first_visible,
                        "stream_snapshots": snapshots,
                    }
                )
                path.write_text(json.dumps(row, ensure_ascii=False, indent=2), encoding="utf-8")
                print(ident, index, job["status"], (run or {}).get("mode"), flush=True)
                if run is None:
                    print("Failed turn retained, continuing without retry", flush=True)
                # Space user turns as well as model invocations; permits re-probe
                # after the explicit six-second forced-429 cooldown.
                remaining = 6 - (time.perf_counter() - started)
                if remaining > 0:
                    time.sleep(remaining)
        (OUT / "provider_accounting.json").write_text(
            json.dumps(client.get("/__evaluation/status").json(), indent=2), encoding="utf-8"
        )


if __name__ == "__main__":
    main()
