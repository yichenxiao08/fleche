"""Connect an existing server-side Gemini key and select Gemini as the coach default."""

import json
import re
import sys
import time
from pathlib import Path

from google import genai
from google.genai import types
from pydantic import SecretStr

from fencecoach.coach.graph import run_coach
from fencecoach.schemas import CoachRequest
from fencecoach.settings import settings


def main():
    key = settings.gemini_api_key.get_secret_value().strip()
    if not key:
        raise SystemExit("Save GEMINI_API_KEY in .env first. Do not put the key in chat.")
    settings.gemini_api_key = SecretStr(key)
    try:
        with genai.Client(
            api_key=key, vertexai=False, http_options=types.HttpOptions(timeout=20000)
        ) as client:
            available = {m.name.removeprefix("models/") for m in client.models.list() if m.name}
        if settings.gemini_chat_model not in available:
            choices = [
                m
                for m in sorted(available)
                if "flash" in m and not any(s in m for s in ("image", "tts", "audio", "live"))
            ]
            print(json.dumps({"status": "choose_model", "available_flash_models": choices}))
            raise SystemExit("Set GEMINI_CHAT_MODEL to an available text model and rerun.")
        start = time.perf_counter()
        response = run_coach(
            CoachRequest(
                session_id="gemini-setup",
                question="In a simple fencing lunge, which arm reaches toward the target: sword arm or non-sword arm?",
            ),
            mode="gemini",
        )
        if not response.report.summary:
            raise RuntimeError("empty_response")
    except SystemExit:
        raise
    except Exception as exc:
        # SDK exception strings can contain request details. Never print a credential or URL.
        detail = re.sub(r"https?://\S+", "[provider URL]", str(exc).replace(key, "[redacted]"))
        print(
            json.dumps(
                {
                    "status": "connection_failed",
                    "error_type": type(exc).__name__,
                    "code": getattr(exc, "code", None),
                    "detail": detail[:800],
                }
            )
        )
        sys.exit(1)
    path = Path(".env")
    lines = path.read_text(encoding="utf-8-sig").splitlines() if path.exists() else []
    found = False
    for i, line in enumerate(lines):
        if line.startswith("FENCECOACH_CHAT_PROVIDER="):
            lines[i] = "FENCECOACH_CHAT_PROVIDER=gemini"
            found = True
    if not found:
        lines.append("FENCECOACH_CHAT_PROVIDER=gemini")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "status": "connected",
                "model": settings.gemini_chat_model,
                "latency_ms": round((time.perf_counter() - start) * 1000),
                "answer": response.report.summary,
                "reference_count": len(response.sources),
            }
        )
    )
    print("Restart the server, then refresh the coach page to select Gemini AI.")


if __name__ == "__main__":
    main()
