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
CORE = os.environ.get("CITATION_LIVE_CORE", "new")
PORT = int(os.environ.get("CITATION_LIVE_PORT", "8012"))
DIRECTORY = ROOT / ("work/citation_live_" + CORE)
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
        "COACH_CORE": CORE,
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
settings.coach_core = CORE
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
                "title": "Citation live " + ident,
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
                    "title": "Citation live " + ident,
                }
            )
            with repository._connect() as db:
                db.execute(
                    "INSERT INTO sessions VALUES (?,?,?)",
                    (session.session_id, session.created_at.isoformat(), session.model_dump_json()),
                )
assert repository.path.resolve() == target_db.resolve(), "Acceptance repository is not isolated."

control = {"force_429": False, "gemini_attempts": 0, "synthetic_429": 0}
from fencecoach.coach import conversation, providers  # noqa: E402

original_chat_model = providers.chat_model


class SyntheticRateLimit(Exception):
    status_code = 429
    headers = {"retry-after": "6"}


class WrappedModel:
    def __init__(self, model=None, forced=False):
        self.model, self.forced = model, forced

    def __getattr__(self, key):
        return getattr(self.model, key)

    def bind_tools(self, tools):
        return WrappedModel(self.model.bind_tools(tools), self.forced) if self.model else self

    def bind(self, **kwargs):
        return WrappedModel(self.model.bind(**kwargs), self.forced) if self.model else self

    def invoke(self, messages):
        if self.forced:
            control["synthetic_429"] += 1
            raise SyntheticRateLimit("Evaluation-only forced 429")
        control["gemini_attempts"] += 1
        return PacedGemini(self.model).invoke(messages)


def live_model(mode, model_id=None):
    if mode == "gemini":
        forced = control["force_429"]
        control["force_429"] = False
        return WrappedModel(None if forced else original_chat_model(mode, model_id), forced)
    return original_chat_model(mode, model_id)


core_packet.chat_model = live_model
conversation.chat_model = live_model
providers.chat_model = live_model


@app.post("/__evaluation/force429")
def force_next_429():
    gemini_circuit.success()
    control["force_429"] = True
    return {"next_gemini_turn": "synthetic_429_then_hosted_or_degraded"}


@app.get("/__evaluation/status")
def acceptance_status():
    return {**control, "core": settings.coach_core, "isolated_database": True}


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=PORT, log_level="warning")
