from __future__ import annotations

import json
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from fencecoach.automatic_training import AutomaticTraining
from fencecoach.coach.graph import EvidenceValidationError, run_coach
from fencecoach.coach.providers import provider_status
from fencecoach.coaching_jobs import CoachingJobs, CoachingWorker
from fencecoach.dataset_api import dataset_router
from fencecoach.repository import Repository
from fencecoach.schemas import (
    CoachingReport,
    CoachRequest,
    ReportRequest,
    RunRecord,
    SessionCreate,
    SessionRecord,
    TrainingLog,
    TrainingLogCreate,
)
from fencecoach.settings import settings
from fencecoach.video_api import UploadLimit, video_router
from fencecoach.video_jobs import VideoJobs, VideoWorker, availability

logger = logging.getLogger(__name__)
repository = Repository(settings.fencecoach_db_path)
coaching_jobs = CoachingJobs(repository)
video_jobs = VideoJobs(settings.fencecoach_db_path, settings.fencecoach_video_dir)
automatic_training = AutomaticTraining(settings.fencecoach_video_dir.parent / "training")


@asynccontextmanager
async def lifespan(app):
    repository.list_sessions()
    if settings.fencecoach_seed_examples:
        from fencecoach.demo_seed import seed_examples

        seed_examples(video_jobs, settings.fencecoach_examples_dir)
    if settings.fencecoach_automatic_training:
        automatic_training.start()
    coaching_worker = CoachingWorker(coaching_jobs)
    if settings.fencecoach_coaching_worker:
        coaching_worker.start()
    worker = VideoWorker(video_jobs, settings.fencecoach_pose_model)
    if settings.fencecoach_video_worker:
        worker.start()
    yield
    if settings.fencecoach_automatic_training:
        automatic_training.close()
    if settings.fencecoach_coaching_worker:
        coaching_worker.close()
    if settings.fencecoach_video_worker:
        worker.close()


app = FastAPI(
    title="FenceCoach",
    version="0.5.0",
    description="Cited coaching reports over measured fencing-session data.",
    lifespan=lifespan,
)
app.add_middleware(UploadLimit)
app.include_router(video_router(video_jobs, settings))
app.include_router(
    dataset_router(settings.fencecoach_video_dir.parent / "training", automatic_training)
)
web = Path(__file__).parent / "web"
app.mount("/static", StaticFiles(directory=web), name="static")


@app.get("/", include_in_schema=False)
def dashboard():
    return FileResponse(web / "index.html")


@app.get("/dataset", include_in_schema=False)
def dataset_workspace():
    return FileResponse(web / "dataset.html")


@app.get("/health")
def health():
    return {"status": "ok", "version": "0.5.0"}


@app.get("/api/config")
def configuration():
    return {
        **provider_status(),
        "embedding_configured": bool(settings.bedrock_embedding_model_id),
        "region": settings.aws_region,
        "demo_available": True,
        "video": {
            **availability(settings.fencecoach_pose_model),
            "worker_enabled": settings.fencecoach_video_worker,
            "demo_ready": (
                settings.fencecoach_video_dir.parent / "video-demo" / "mit-jump-lunge.mp4"
            ).is_file(),
        },
    }


@app.get("/api/sessions", response_model=list[SessionRecord])
def list_sessions():
    return repository.list_sessions()


@app.post("/api/sessions", response_model=SessionRecord, status_code=201)
def create_session(data: SessionCreate):
    return repository.create_session(data)


@app.post("/api/demo", response_model=SessionRecord, status_code=201)
def load_demo():
    data = SessionCreate.model_validate_json(
        (web / "sample-session.json").read_text(encoding="utf-8-sig")
    )
    return repository.create_session(data, is_demo=True)


@app.get("/api/sessions/{session_id}", response_model=SessionRecord)
def get_session(session_id: str):
    result = repository.get_session(session_id)
    if not result:
        raise HTTPException(404, "Session not found.")
    return result


@app.get("/api/sessions/{session_id}/reports", response_model=list[RunRecord])
def list_reports(session_id: str):
    get_session(session_id)
    return repository.list_runs(session_id)


@app.get("/api/sessions/{session_id}/compare/{baseline_id}")
def compare(session_id: str, baseline_id: str):
    from fencecoach.comparisons import compare_sessions

    return compare_sessions(get_session(session_id), get_session(baseline_id))


def _report_or_error(request: CoachRequest, mode: str):
    try:
        return run_coach(request, mode)
    except EvidenceValidationError as exc:
        raise HTTPException(422, str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(503, str(exc)) from exc
    except Exception as exc:
        logger.exception("Coaching provider failed")
        raise HTTPException(
            502,
            "The AI provider request failed. Check the selected model server or cloud credentials and try again.",
        ) from exc


def require_supported_session(session):
    """Apply QA to legacy saved video sessions as well as newly accepted clips."""
    if not session.video_job_id:
        return
    from fencecoach.quality import assess_quality

    path = video_jobs.directory / session.video_job_id / "result.json"
    if not path.is_file():
        raise HTTPException(
            409, "Video evidence is unavailable; restore or re-analyze the clip before coaching."
        )
    result = json.loads(path.read_text(encoding="utf-8"))
    qa = result.get("quality_gate") or assess_quality(result)
    if not qa["coaching_allowed"]:
        raise HTTPException(
            422,
            "This video is unsupported for coaching. "
            + " ".join(i["tip"] for i in qa["issues"] if i["severity"] == "reject"),
        )


def coaching_request(session, data):
    """Keep general conversation available without exposing rejected video evidence."""
    context = repository.coaching_context(session.session_id)
    try:
        require_supported_session(session)
    except HTTPException as exc:
        # History tools must not reintroduce measurements from failed footage.
        return CoachRequest(
            session_id=session.session_id,
            question=data.question,
            skill_level=session.skill_level,
            metrics=[],
            evidence_unavailable_reason=str(exc.detail),
            training_history=context["training_history"],
            session_history=context["session_history"],
            conversation_history=context["conversation_history"],
            session_notes=(
                "Current video measurements are unavailable. Prior sessions and self-reported "
                "training logs may be used as historical context, but are not evidence about "
                "the rejected clip. " + str(exc.detail)
            ),
        )
    if data.focus_metric_id and not any(
        metric.metric_id == data.focus_metric_id for metric in session.metrics
    ):
        raise HTTPException(422, "The selected measurement is not in this session.")
    return CoachRequest(
        session_id=session.session_id,
        question=data.question,
        skill_level=session.skill_level,
        metrics=session.metrics,
        focus_metric_id=data.focus_metric_id,
        session_notes=session.notes,
        capture_profile=session.capture_profile,
        **context,
    )


@app.post("/api/sessions/{session_id}/reports", response_model=RunRecord, status_code=201)
def create_report(session_id: str, data: ReportRequest):
    session = get_session(session_id)
    request = coaching_request(session, data)
    return repository.save_run(_report_or_error(request, data.mode))


@app.get("/api/reports/{run_id}", response_model=RunRecord)
def get_report(run_id: str):
    run = repository.get_run(run_id)
    if not run:
        raise HTTPException(404, "Report not found.")
    if not run.citation_ids_valid:
        raise HTTPException(
            422, "This review was invalidated. Submit the question again for a cited review."
        )
    return run


@app.post("/coach", response_model=CoachingReport)
def original_coaching_endpoint(request: CoachRequest):
    return _report_or_error(request, "bedrock").report


@app.get("/api/training-logs", response_model=list[TrainingLog])
def training_logs():
    return repository.list_logs()


@app.post("/api/training-logs", response_model=TrainingLog, status_code=201)
def create_training_log(data: TrainingLogCreate):
    try:
        return repository.save_log(data)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@app.put("/api/training-logs/{log_id}", response_model=TrainingLog)
def edit_training_log(log_id: str, data: TrainingLogCreate):
    try:
        return repository.save_log(data, log_id)
    except KeyError as exc:
        raise HTTPException(404, "Training log not found.") from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@app.delete("/api/training-logs/{log_id}", status_code=204)
def delete_training_log(log_id: str):
    if not repository.delete_log(log_id):
        raise HTTPException(404, "Training log not found.")


@app.post("/api/sessions/{session_id}/coaching-jobs", status_code=202)
def queue_coaching(session_id: str, data: ReportRequest):
    session = get_session(session_id)
    try:
        request = coaching_request(session, data)
        return coaching_jobs.create(request, data.mode)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@app.get("/api/coaching-jobs/{job_id}")
def coaching_job(job_id: str):
    result = coaching_jobs.get(job_id)
    if not result:
        raise HTTPException(404, "Coaching request not found.")
    return result


@app.get("/api/practice-plans")
def practice_plans():
    return repository.list_plans()


@app.post("/api/reports/{run_id}/practice-plan", status_code=201)
def save_practice_plan(run_id: str):
    try:
        return repository.save_plan(run_id)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
