"""Durable coaching requests with progress and bounded concurrency."""

from __future__ import annotations

import json
import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from datetime import UTC, datetime
from uuid import uuid4

from fencecoach.coach.graph import EvidenceValidationError, run_coach
from fencecoach.coach.providers import provider_failure, warm_local_model
from fencecoach.schemas import CoachRequest
from fencecoach.settings import settings


class CoachingJobs:
    """Versioned queue: workers using the legacy protocol cannot claim new jobs."""

    def __init__(self, repository):
        self.repository = repository
        with closing(repository._connect()) as db, db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS coaching_jobs_v2 (id TEXT PRIMARY KEY, status TEXT NOT NULL, created_at TEXT NOT NULL, payload TEXT NOT NULL)"
            )
            # Retain old request records for polling/history. New workers never
            # claim this queue; old in-memory application versions only know it.
            db.execute(
                "CREATE TABLE IF NOT EXISTS coaching_jobs (id TEXT PRIMARY KEY, status TEXT NOT NULL, created_at TEXT NOT NULL, payload TEXT NOT NULL)"
            )

    def create(self, request: CoachRequest, mode):
        job = dict(
            queue_version=2,
            job_id=uuid4().hex,
            session_id=request.session_id,
            status="queued",
            stage="Waiting for coach",
            created_at=datetime.now(UTC).isoformat(),
            request=request.model_dump(mode="json"),
            mode=mode,
            error=None,
            run_id=None,
            partial_reply="",
        )
        with closing(self.repository._connect()) as db, db:
            db.execute("BEGIN IMMEDIATE")
            if (
                db.execute(
                    "SELECT count(*) FROM coaching_jobs_v2 WHERE status IN ('queued','running')"
                ).fetchone()[0]
                >= 50
            ):
                raise ValueError("Coaching queue is full. Try again shortly.")
            db.execute(
                "INSERT INTO coaching_jobs_v2 VALUES (?,?,?,?)",
                (job["job_id"], job["status"], job["created_at"], json.dumps(job)),
            )
        return self.public(job)

    @staticmethod
    def public(job):
        result = {
            k: v
            for k, v in job.items()
            if k not in {"request", "owner", "lease_until", "failure_detail"}
        }
        result["question"] = job.get("request", {}).get("question", "")
        return result

    def get(self, job_id):
        with closing(self.repository._connect()) as db:
            row = db.execute(
                "SELECT payload FROM coaching_jobs_v2 WHERE id=?", (job_id,)
            ).fetchone()
            if not row:
                row = db.execute(
                    "SELECT payload FROM coaching_jobs WHERE id=?", (job_id,)
                ).fetchone()
            return self.public(json.loads(row[0])) if row else None

    def cancel(self, job_id):
        with closing(self.repository._connect()) as db, db:
            db.execute("BEGIN IMMEDIATE")
            table = "coaching_jobs_v2"
            row = db.execute(
                "SELECT payload FROM coaching_jobs_v2 WHERE id=?", (job_id,)
            ).fetchone()
            if not row:
                table = "coaching_jobs"
                row = db.execute(
                    "SELECT payload FROM coaching_jobs WHERE id=?", (job_id,)
                ).fetchone()
            if not row:
                return None
            job = json.loads(row[0])
            if job["status"] in {"queued", "running"}:
                job.update(status="cancelled", stage="Stopped", error=None)
                db.execute(
                    f"UPDATE {table} SET status='cancelled',payload=? WHERE id=?",
                    (json.dumps(job), job_id),
                )
            return self.public(job)

    def claim(self, owner):
        with closing(self.repository._connect()) as db, db:
            db.execute("BEGIN IMMEDIATE")
            for row in db.execute(
                "SELECT id,payload FROM coaching_jobs_v2 WHERE status='running'"
            ).fetchall():
                stale = json.loads(row[1])
                if stale.get("lease_until", 0) < time.time():
                    stale.update(
                        status="failed",
                        error="The coaching worker stopped. Submit your question again.",
                        stage="Interrupted",
                    )
                    db.execute(
                        "UPDATE coaching_jobs_v2 SET status='failed',payload=? WHERE id=?",
                        (json.dumps(stale), row[0]),
                    )
            row = db.execute(
                "SELECT id,payload FROM coaching_jobs_v2 WHERE status='queued' ORDER BY created_at LIMIT 1"
            ).fetchone()
            if not row:
                return None
            job = json.loads(row[1])
            job.update(
                status="running",
                stage="Reading session evidence",
                started_at=time.time(),
                owner=owner,
                lease_until=time.time() + 45,
            )
            db.execute(
                "UPDATE coaching_jobs_v2 SET status='running',payload=? WHERE id=?",
                (json.dumps(job), row[0]),
            )
            return job

    def update(self, job_id, owner, **fields):
        with closing(self.repository._connect()) as db, db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT payload FROM coaching_jobs_v2 WHERE id=?", (job_id,)
            ).fetchone()
            job = json.loads(row[0])
            if job["status"] != "running" or job.get("owner") != owner:
                return False
            job.update(fields, lease_until=time.time() + 45)
            db.execute(
                "UPDATE coaching_jobs_v2 SET status=?,payload=? WHERE id=?",
                (job["status"], json.dumps(job), job_id),
            )
            return True


class CoachingWorker:
    def __init__(self, jobs):
        self.jobs = jobs
        self.stop = threading.Event()
        self.thread = threading.Thread(
            target=self.supervise, daemon=True, name="coaching-supervisor"
        )

    def start(self):
        threading.Thread(target=warm_local_model, daemon=True, name="coach-warmup").start()
        self.thread.start()

    def close(self):
        self.stop.set()
        self.thread.join(timeout=3)

    def execute(self, job, owner):
        try:
            last_publish = 0.0

            def publish(text):
                nonlocal last_publish
                now = time.monotonic()
                # The browser polls every 300 ms. Persisting every model token
                # only adds SQLite lock contention without making the answer
                # appear any sooner; keep the first token and sample at 150 ms.
                if last_publish and now - last_publish < 0.15:
                    return
                last_publish = now
                self.jobs.update(
                    job["job_id"], owner, partial_reply=text, stage="Coach is replying"
                )

            stages = {
                "evidence_check": "Checking video availability",
                "gather_metrics": "Reading session evidence",
                "retrieve": "Finding relevant practice notes",
                "agent": "Coach is thinking",
                "local_fallback": "Gemini is unavailable; local coach is thinking",
                "grounding": "Checking that the advice matches your evidence",
                "tools": "Checking measurements and training history",
                "format_report": "Writing your coaching review",
                "validate": "Checking evidence references",
            }
            run = run_coach(
                CoachRequest.model_validate(job["request"]),
                job["mode"],
                on_step=lambda step: self.jobs.update(
                    job["job_id"], owner, stage=stages.get(step, "Reviewing evidence")
                ),
                on_text=publish,
            )
            # Save run and complete job in one transaction, only while this worker owns the lease.
            with closing(self.jobs.repository._connect()) as db, db:
                db.execute("BEGIN IMMEDIATE")
                current = json.loads(
                    db.execute(
                        "SELECT payload FROM coaching_jobs_v2 WHERE id=?", (job["job_id"],)
                    ).fetchone()[0]
                )
                if current["status"] != "running" or current.get("owner") != owner:
                    return
                db.execute(
                    "INSERT INTO runs VALUES (?,?,?,?)",
                    (run.run_id, run.session_id, run.created_at.isoformat(), run.model_dump_json()),
                )
                current.update(status="completed", stage="Review ready", run_id=run.run_id)
                db.execute(
                    "UPDATE coaching_jobs_v2 SET status='completed',payload=? WHERE id=?",
                    (json.dumps(current), job["job_id"]),
                )
        except Exception as exc:
            logging.exception("Coaching job failed")
            import httpx

            known_failure = provider_failure(exc)
            if known_failure:
                _, message = known_failure
            elif isinstance(exc, (httpx.TransportError, ConnectionError, OSError)):
                message = "Flèche couldn't connect to the coaching provider. Your question is kept; check the server's internet connection and retry."
            else:
                message = (
                    str(exc)[:400]
                    if isinstance(exc, (EvidenceValidationError, RuntimeError))
                    else "Flèche hit an internal error while answering. Your question is kept; try again."
                )
            self.jobs.update(
                job["job_id"],
                owner,
                status="failed",
                stage="Review interrupted",
                error=message,
                failure_detail={
                    "exception_type": type(exc).__name__,
                    "exception_module": type(exc).__module__,
                },
            )

    def supervise(self):
        owner = uuid4().hex
        active = {}
        concurrency = max(1, min(8, settings.fencecoach_coaching_concurrency))
        with ThreadPoolExecutor(max_workers=concurrency, thread_name_prefix="coach") as pool:
            while not self.stop.wait(0.2):
                try:
                    for job_id, (future, lease_renewed) in list(active.items()):
                        if future.done():
                            del active[job_id]
                        elif time.monotonic() - lease_renewed >= 15:
                            with closing(self.jobs.repository._connect()) as db:
                                row = db.execute(
                                    "SELECT payload FROM coaching_jobs_v2 WHERE id=?", (job_id,)
                                ).fetchone()
                            current = json.loads(row[0]) if row else {}
                            limit = 90 if current.get("mode") == "local" else 45
                            if time.time() - current.get("started_at", time.time()) > limit:
                                self.jobs.update(
                                    job_id,
                                    owner,
                                    status="failed",
                                    stage="Timed out",
                                    error="The coach took too long to respond. Your question is kept; try again.",
                                )
                            else:
                                self.jobs.update(job_id, owner)
                            active[job_id] = (future, time.monotonic())
                    while len(active) < concurrency:
                        job = self.jobs.claim(owner)
                        if not job:
                            break
                        active[job["job_id"]] = (
                            pool.submit(self.execute, job, owner),
                            time.monotonic(),
                        )
                except Exception:
                    logging.exception("Coaching supervisor failed")
