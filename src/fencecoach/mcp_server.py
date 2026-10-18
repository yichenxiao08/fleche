"""Local, read-only MCP session tools. Run from the project directory over stdio."""

import json

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from fencecoach.comparisons import compare_sessions
from fencecoach.rag.knowledge import search_knowledge
from fencecoach.repository import Repository
from fencecoach.settings import settings

mcp = FastMCP(
    "Flèche",
    instructions="Use measurements as evidence, not a correctness score. Never turn unsupported footage or interval counts into technique verdicts. All tools are read-only.",
)
READ_ONLY = ToolAnnotations(
    readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False
)


def repository():
    return Repository(settings.fencecoach_db_path)


def session(session_id):
    item = repository().get_session(session_id)
    if item is None:
        raise ValueError("Session not found. Read fencecoach://sessions for available IDs.")
    if item.video_job_id:
        from fencecoach.quality import assess_quality

        path = settings.fencecoach_video_dir / item.video_job_id / "result.json"
        if not path.is_file():
            raise ValueError("Video evidence is missing; restore or re-analyze the clip.")
        result = json.loads(path.read_text(encoding="utf-8"))
        if not (result.get("quality_gate") or assess_quality(result))["coaching_allowed"]:
            raise ValueError("Unsupported footage: not eligible for personalized coaching.")
    return item


@mcp.resource("fencecoach://sessions")
def available_sessions() -> str:
    return json.dumps(
        [
            {
                "session_id": s.session_id,
                "title": s.title,
                "is_demo": s.is_demo,
                "capture_profile": s.capture_profile,
            }
            for s in repository().list_sessions()
        ]
    )


@mcp.tool(annotations=READ_ONLY)
def get_session_measurements(session_id: str, metric_name: str = "") -> dict:
    """Read saved measurements, timestamps, and provenance for a supported session."""
    s = session(session_id)
    return {
        "session_id": s.session_id,
        "is_demo": s.is_demo,
        "capture_profile": s.capture_profile,
        "measurements": [
            m.model_dump(mode="json")
            for m in s.metrics
            if not metric_name or metric_name.lower() in m.name.lower()
        ],
        "limit": "2D pose measurements and visibility confidence are not correctness scores.",
    }


@mcp.tool(annotations=READ_ONLY)
def list_reps(session_id: str) -> dict:
    """List reviewed timing intervals; they are not independently verified action counts."""
    s = session(session_id)
    spans = sorted(
        {
            (m.start_ms, m.end_ms)
            for m in s.metrics
            if m.name == "recovery_time" and m.start_ms is not None and m.end_ms is not None
        }
    )
    return {
        "session_id": s.session_id,
        "intervals": [
            {"number": i + 1, "peak_ms": a, "recovery_end_ms": b} for i, (a, b) in enumerate(spans)
        ],
        "limit": "Reviewed recovery windows, not verified lunge classifications.",
    }


@mcp.tool(annotations=READ_ONLY)
def compare_to_baseline(session_id: str, baseline_session_id: str, metric_name: str = "") -> dict:
    """Compare matching-unit measurements only when declared camera setups match."""
    return compare_sessions(session(session_id), session(baseline_session_id), metric_name)


@mcp.tool(annotations=READ_ONLY)
def get_practice_history(limit: int = 10) -> dict:
    """Read self-reported journal entries; these are not independent movement evidence."""
    return {
        "logs": [
            log.model_dump(mode="json")
            for log in repository().list_logs()[: max(1, min(limit, 30))]
        ],
        "limit": "Athlete self reports.",
    }


@mcp.tool(annotations=READ_ONLY)
def search_coaching_library(query: str, limit: int = 3) -> dict:
    """Retrieve authored guidance with source IDs; distinguish guidance from measured faults."""
    return {
        "sources": [
            s.model_dump(mode="json")
            for s in search_knowledge(
                query[:500], limit=max(1, min(limit, 5)), use_embeddings=False
            )
        ]
    }


def main():
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
