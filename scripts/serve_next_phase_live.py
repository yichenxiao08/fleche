"""Loopback-only running-app acceptance server using a separate saved-session DB.

Uses the real API, request construction, repository and providers. The sole
fault-injection hook raises one synthetic 429 before an actual fallback request.
Never import this launcher from production code.
"""

import json
import os
import shutil
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import uvicorn
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]
DIRECTORY = ROOT / "work/next_phase_live"
DIRECTORY.mkdir(parents=True, exist_ok=True)
local_values = dotenv_values(ROOT / ".env")
source_db = Path(
    os.environ.get("FENCECOACH_DB_PATH")
    or local_values.get("FENCECOACH_DB_PATH")
    or "data/fencecoach.sqlite3"
)
source_videos = Path(
    os.environ.get("FENCECOACH_VIDEO_DIR")
    or local_values.get("FENCECOACH_VIDEO_DIR")
    or "data/videos"
)
target_db = DIRECTORY / "server.sqlite3"
if not target_db.exists():
    with (
        sqlite3.connect(f"file:{source_db.resolve().as_posix()}?mode=ro", uri=True) as src,
        sqlite3.connect(target_db) as dst,
    ):
        src.backup(dst)
    for source in source_videos.glob("*/result.json"):
        target = DIRECTORY / "videos" / source.parent.name / source.name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)

# Set isolation BEFORE importing the package: fencecoach.__init__ imports API.
os.environ.update(
    {
        "COACH_CORE": "new",
        "FENCECOACH_DB_PATH": str(target_db),
        "FENCECOACH_DATABASE_URL": "",
        "FENCECOACH_VIDEO_DIR": str(DIRECTORY / "videos"),
        "FENCECOACH_VIDEO_WORKER": "false",
        "FENCECOACH_COACHING_WORKER": "true",
        "FENCECOACH_AUTOMATIC_TRAINING": "false",
        "FENCECOACH_SEED_EXAMPLES": "false",
    }
)
from fencecoach.settings import settings  # noqa: E402

# Process-local opt-in; .env and application defaults are never changed.
settings.coach_core = "new"
settings.fencecoach_db_path = target_db
settings.fencecoach_video_dir = DIRECTORY / "videos"
settings.fencecoach_video_worker = False
settings.fencecoach_coaching_worker = True
settings.fencecoach_automatic_training = False
settings.fencecoach_seed_examples = False
settings.fencecoach_provider_cooldown_seconds = 6

from eval_layer2 import PacedGemini  # noqa: E402

from fencecoach import coaching_jobs as job_module  # noqa: E402
from fencecoach.api import app, repository  # noqa: E402
from fencecoach.coach import core_packet  # noqa: E402
from fencecoach.coach.router import gemini_circuit  # noqa: E402

job_module.warm_local_model = lambda: None

cases = json.loads((ROOT / "evals/layer2/inputs.json").read_text(encoding="utf-8"))
by_id = {r["id"]: r for r in cases}
manifest_path = DIRECTORY / "sessions.json"
if not manifest_path.exists():
    manifest = {}
    for ident, parent in [
        (f"L{i:02d}", parent)
        for i, parent in enumerate(
            ["H10", "H08", "H09", "H01", "E12", "H07", "H02", "E11", "H04", "S11"], 1
        )
    ]:
        source = repository.get_session(by_id[parent]["saved_request"]["session_id"])
        assert source is not None
        session = source.model_copy(
            update={
                "session_id": uuid4().hex,
                "created_at": datetime.now(UTC),
                "title": "Next phase live " + ident,
            }
        )
        with repository._connect() as db:
            db.execute(
                "INSERT INTO sessions VALUES (?,?,?)",
                (session.session_id, session.created_at.isoformat(), session.model_dump_json()),
            )
        manifest[ident] = {
            "session_id": session.session_id,
            "source_case": parent,
            "source_session": source.session_id,
        }
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
else:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for ident, item in manifest.items():
        if repository.get_session(item["session_id"]) is None:
            source = repository.get_session(item["source_session"])
            session = source.model_copy(
                update={
                    "session_id": item["session_id"],
                    "created_at": datetime.now(UTC),
                    "title": "Next phase live " + ident,
                }
            )
            with repository._connect() as db:
                db.execute(
                    "INSERT INTO sessions VALUES (?,?,?)",
                    (session.session_id, session.created_at.isoformat(), session.model_dump_json()),
                )
assert repository.path.resolve() == target_db.resolve(), "Acceptance repository is not isolated."

control = {"force_429": False, "gemini_attempts": 0, "synthetic_429": 0}
original_chat_model = core_packet.chat_model


class SyntheticRateLimit(Exception):
    status_code = 429
    headers = {"retry-after": "6"}


class ForcedModel:
    def bind_tools(self, tools):
        return self

    def invoke(self, messages):
        control["synthetic_429"] += 1
        raise SyntheticRateLimit("Evaluation-only forced 429; no Gemini request was made.")


def live_model(mode):
    if mode == "gemini":
        if control["force_429"]:
            control["force_429"] = False
            return ForcedModel()
        model = PacedGemini(original_chat_model(mode))
        original_invoke = model.invoke

        def counted(messages):
            control["gemini_attempts"] += 1
            return original_invoke(messages)

        # bind_tools returns another wrapper, so count its invoke as well.
        original_bind = model.bind_tools

        def bind(tools):
            bound = original_bind(tools)
            bound_invoke = bound.invoke

            def counted_bound(messages):
                control["gemini_attempts"] += 1
                return bound_invoke(messages)

            bound.invoke = counted_bound
            return bound

        model.invoke, model.bind_tools = counted, bind
        return model
    return original_chat_model(mode)


core_packet.chat_model = live_model


@app.post("/__evaluation/force429")
def force_next_429():
    gemini_circuit.success()
    control["force_429"] = True
    return {"next_gemini_turn": "synthetic_429_then_real_local"}


@app.get("/__evaluation/status")
def acceptance_status():
    return {**control, "core": settings.coach_core, "isolated_database": True}


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8011, log_level="warning")
