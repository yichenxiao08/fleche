"""Bounded local inference for the packet core; legacy provider settings stay intact."""

from __future__ import annotations

import asyncio
import json
import time

import httpx
from langchain_core.messages import AIMessage

from fencecoach.settings import settings

LOCAL_CONTEXT = 4096
LOCAL_GENERATION = 160
LOCAL_DEADLINE_SECONDS = 20


class PacketQwen:
    """Plain-text streaming Ollama request with a total wall-clock deadline."""

    def __init__(self, timeout=LOCAL_DEADLINE_SECONDS):
        self.timeout = timeout

    def invoke(self, messages, on_text=None):
        async def generate():
            started = time.perf_counter()
            content, first_token, metadata = [], None, {}
            roles = {"human": "user", "ai": "assistant", "system": "system"}
            payload = {
                "model": settings.ollama_chat_model,
                "messages": [{"role": roles[m.type], "content": m.content} for m in messages],
                "stream": True,
                "think": False,
                "keep_alive": -1,
                "options": {
                    "temperature": 0,
                    "num_ctx": LOCAL_CONTEXT,
                    "num_predict": LOCAL_GENERATION,
                },
            }
            try:
                async with asyncio.timeout(self.timeout):
                    async with (
                        httpx.AsyncClient(timeout=httpx.Timeout(self.timeout, connect=3)) as client,
                        client.stream(
                            "POST", settings.ollama_base_url.rstrip("/") + "/api/chat", json=payload
                        ) as response,
                    ):
                        response.raise_for_status()
                        async for line in response.aiter_lines():
                            if not line:
                                continue
                            row = json.loads(line)
                            if row.get("error"):
                                raise RuntimeError(row["error"])
                            token = row.get("message", {}).get("content", "")
                            if token:
                                if first_token is None:
                                    first_token = (time.perf_counter() - started) * 1000
                                content.append(token)
                                if on_text:
                                    on_text(token)
                            if row.get("done"):
                                metadata = {
                                    k: row.get(k)
                                    for k in (
                                        "load_duration",
                                        "prompt_eval_count",
                                        "prompt_eval_duration",
                                        "eval_count",
                                        "eval_duration",
                                        "done_reason",
                                    )
                                }
            except TimeoutError as exc:
                raise TimeoutError(
                    f"Local coach exceeded {self.timeout}s wall-clock deadline; request cancelled."
                ) from exc
            metadata["first_token_ms"] = first_token
            metadata["wall_ms"] = (time.perf_counter() - started) * 1000
            return AIMessage(
                content="".join(content),
                response_metadata=metadata,
                usage_metadata={
                    "input_tokens": metadata.get("prompt_eval_count") or 0,
                    "output_tokens": metadata.get("eval_count") or 0,
                    "total_tokens": (metadata.get("prompt_eval_count") or 0)
                    + (metadata.get("eval_count") or 0),
                },
            )

        return asyncio.run(generate())


def warm_packet_qwen():
    started = time.perf_counter()
    with httpx.Client(timeout=LOCAL_DEADLINE_SECONDS) as client:
        response = client.post(
            settings.ollama_base_url.rstrip("/") + "/api/generate",
            json={
                "model": settings.ollama_chat_model,
                "prompt": "",
                "stream": False,
                "keep_alive": -1,
                "options": {"num_ctx": LOCAL_CONTEXT, "num_predict": LOCAL_GENERATION},
            },
        )
        response.raise_for_status()
        result = response.json()
    return {
        "wall_ms": round((time.perf_counter() - started) * 1000, 2),
        "load_duration": result.get("load_duration"),
        "runtime": {
            "num_ctx": LOCAL_CONTEXT,
            "num_predict": LOCAL_GENERATION,
            "think": False,
            "hard_deadline_s": LOCAL_DEADLINE_SECONDS,
        },
    }
