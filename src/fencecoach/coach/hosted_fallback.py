"""Bounded Groq plain-prose generation, without SDK retries or credential-bearing errors."""

import asyncio

import httpx
from langchain_core.messages import AIMessage

from fencecoach.settings import settings


class HostedError(RuntimeError):
    def __init__(self, status, detail="", retry_after=0):
        self.detail = detail
        self.retry_after = retry_after
        self.status_code = status
        self.headers = {"retry-after": retry_after} if retry_after else {}
        super().__init__(f"Hosted fallback HTTP {status}: {detail}")


class HostedFallback:
    def invoke(self, messages):
        return asyncio.run(self._invoke(messages))

    async def _invoke(self, messages):
        async with asyncio.timeout(20):
            return await self._request(messages)

    async def _request(self, messages):
        roles = {"human": "user", "ai": "assistant", "system": "system"}
        body = {
            "model": settings.groq_chat_model,
            "messages": [{"role": roles[m.type], "content": m.content} for m in messages],
            "reasoning_effort": "none",
            "reasoning_format": "hidden",
            "max_completion_tokens": 384,
            "temperature": 0.3,
            "stream": False,
        }
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(20, connect=5), trust_env=False
        ) as client:
            response = await client.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": "Bearer " + settings.groq_api_key.get_secret_value()},
                json=body,
            )
        if response.status_code != 200:
            detail = response.text.replace(settings.groq_api_key.get_secret_value(), "[REDACTED]")
            raise HostedError(
                response.status_code, detail[:1000], response.headers.get("retry-after", 0)
            )
        value = response.json()
        usage = value.get("usage", {})
        cached = usage.get("prompt_tokens_details", {}).get("cached_tokens")
        return AIMessage(
            content=value["choices"][0]["message"].get("content") or "",
            usage_metadata={
                "input_tokens": usage.get("prompt_tokens", 0),
                "output_tokens": usage.get("completion_tokens", 0),
                "total_tokens": usage.get("total_tokens", 0),
                "input_token_details": {"cache_read": cached} if cached is not None else {},
            },
            response_metadata={
                "provider": "groq",
                "model": value.get("model", settings.groq_chat_model),
                "raw_usage": usage,
                "finish_reason": value["choices"][0].get("finish_reason"),
                "stream": False,
            },
        )
