"""Exercise real stdio MCP initialization, discovery, resource read, and five tools."""

import asyncio
import json
import os
import sys
import tempfile
from datetime import date
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from fencecoach.repository import Repository
from fencecoach.schemas import SessionCreate, TrainingLogCreate


async def check():
    project = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory() as directory:
        db = Path(directory) / "mcp.sqlite3"
        repo = Repository(db)
        sample = SessionCreate.model_validate_json(
            (project / "src/fencecoach/web/sample-session.json").read_text(encoding="utf-8-sig")
        )
        sample.capture_profile = {
            "camera_setup_id": "fixture-side",
            "weapon": "foil",
            "weapon_arm": "right",
            "front_leg": "right",
            "facing": "right",
            "camera_motion": "fixed",
            "scene_type": "solo",
        }
        current = repo.create_session(sample, is_demo=True)
        previous = repo.create_session(sample, is_demo=True)
        repo.save_log(
            TrainingLogCreate(
                practiced_on=date.today(),
                duration_minutes=10,
                notes="MCP test fixture",
                session_id=current.session_id,
            )
        )
        params = StdioServerParameters(
            command=sys.executable,
            args=["-m", "fencecoach.mcp_server"],
            env={
                **os.environ,
                "FENCECOACH_DB_PATH": str(db),
                "FENCECOACH_DATABASE_URL": "",
                "FENCECOACH_KNOWLEDGE_DIR": str(project / "knowledge"),
            },
        )
        async with stdio_client(params) as (read, write), ClientSession(read, write) as client:
            await client.initialize()
            discovered = await client.list_tools()
            assert len(discovered.tools) == 5
            assert all(t.annotations.readOnlyHint for t in discovered.tools)
            resources = await client.list_resources()
            assert len(resources.resources) == 1
            await client.read_resource("fencecoach://sessions")
            calls = [
                ("get_session_measurements", {"session_id": current.session_id}),
                ("list_reps", {"session_id": current.session_id}),
                (
                    "compare_to_baseline",
                    {"session_id": current.session_id, "baseline_session_id": previous.session_id},
                ),
                ("get_practice_history", {"limit": 2}),
                ("search_coaching_library", {"query": "foil lunge arm extension"}),
            ]
            for name, args in calls:
                response = await client.call_tool(name, args)
                assert not response.isError, response.content
                assert response.content
            missing = await client.call_tool("get_session_measurements", {"session_id": "missing"})
            assert missing.isError
    report = {
        "status": "passed",
        "transport": "real stdio subprocess",
        "tools": [name for name, _ in calls],
        "read_only_annotations": True,
        "unknown_session_error": True,
        "client": "official Python MCP SDK",
        "claude_desktop_code": "Not exercised: Claude is not installed/authenticated on this machine.",
    }
    (project / "data/evals").mkdir(parents=True, exist_ok=True)
    (project / "data/evals/mcp-smoke.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )
    print(json.dumps(report))


if __name__ == "__main__":
    asyncio.run(check())
