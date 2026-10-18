"""Explicit provider selection: sample reports never masquerade as a live LLM."""

from __future__ import annotations

import json
from urllib.error import URLError
from urllib.request import Request, urlopen

from fencecoach.settings import settings


def provider_failure(exc):
    """Public, credential-free errors shared by direct and queued conversations."""
    import httpx
    from langchain_core.exceptions import ModelAPIError, ModelRateLimitError, ModelTimeoutError

    from fencecoach.coach.router import ProvidersUnavailable, failure_reason

    if isinstance(exc, ProvidersUnavailable):
        primary = (exc.primary_reason or "").removeprefix("cooldown:")
        if primary == "rate_limit" and exc.fallback_reason == "not_ready":
            return (
                503,
                "Gemini's usage limit was reached and the local coach isn't ready. Your question is kept; start Ollama or retry when Gemini's limit resets.",
            )
        if exc.fallback_reason == "timeout":
            return (
                504,
                "The primary coach was unavailable and the local coach timed out. Your question is kept; retry shortly.",
            )
        if exc.fallback_reason == "not_ready":
            return (
                503,
                "Gemini was unavailable and the local coach isn't ready. Your question is kept; check Ollama and retry.",
            )
        return (
            503,
            "Gemini was unavailable and the local coach also failed. Your question is kept; check provider status and retry.",
        )

    # Google and other SDKs often raise their own exception classes. Normalize
    # their status/code/cause chain through the same classifier used by routing
    # instead of turning a quota or timeout into an unhelpful generic error.
    reason = failure_reason(exc)
    if reason == "rate_limit":
        return (
            429,
            "The AI provider's usage limit was reached. Your question is kept; retry when the limit resets or check provider usage.",
        )
    if reason == "timeout":
        return (
            504,
            "The coaching provider took too long to respond. Your question is kept; try again.",
        )
    if reason == "connection":
        return (
            503,
            "The coaching provider could not be reached. Your question is kept; check the connection and retry.",
        )
    if reason == "transient":
        return (
            503,
            "The coaching provider is temporarily unavailable. Your question is kept; try again shortly.",
        )

    if isinstance(exc, ModelRateLimitError):
        return (
            429,
            "The AI provider's API quota has been reached. Your question is kept. Retry after the limit resets or check your provider's API usage.",
        )
    if isinstance(exc, (ModelTimeoutError, httpx.TimeoutException, TimeoutError)):
        return (
            504,
            "The coaching provider took too long to respond. Your question is kept; try again.",
        )
    if isinstance(exc, ModelAPIError):
        if "high demand" in str(exc).lower():
            return (
                503,
                "Gemini's servers are busy right now. Your question is kept; try again shortly.",
            )
        return (
            503,
            "The coaching provider is temporarily unavailable. Your question is kept; try again.",
        )
    return None


def gemini_transport():
    """Bind Gemini connections to IPv4 without changing system networking.

    LangChain forwards the same client_args to Google SDK sync and async
    clients, so this transport implements both HTTPX interfaces.
    """
    import httpx

    class IPv4Transport(httpx.BaseTransport, httpx.AsyncBaseTransport):
        def __init__(self):
            self.sync = httpx.HTTPTransport(local_address="0.0.0.0", retries=0)
            self.async_ = httpx.AsyncHTTPTransport(local_address="0.0.0.0", retries=0)

        def handle_request(self, request):
            return self.sync.handle_request(request)

        async def handle_async_request(self, request):
            return await self.async_.handle_async_request(request)

        def close(self):
            self.sync.close()

        async def aclose(self):
            await self.async_.aclose()

    return IPv4Transport()


def warm_local_model():
    """Load the configured model without generating a reply; callers run this in the background."""
    if settings.coach_core == "new":
        return
    if settings.fencecoach_chat_provider != "local" and not settings.fencecoach_local_fallback:
        return
    request = Request(
        settings.ollama_base_url.rstrip("/") + "/api/generate",
        data=json.dumps(
            {
                "model": settings.ollama_chat_model,
                "prompt": "",
                "stream": False,
                "keep_alive": -1,
                "options": {"num_ctx": 4096},
            }
        ).encode(),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urlopen(request, timeout=60) as response:
            response.read()
    except (URLError, TimeoutError, ValueError, OSError):
        pass  # Readiness is reported by provider_status; startup must not block.


def provider_status():
    model_ready = False
    error = None
    try:
        with urlopen(settings.ollama_base_url.rstrip("/") + "/api/tags", timeout=2) as response:
            models = json.load(response).get("models", [])
        model_ready = any(m.get("name") == settings.ollama_chat_model for m in models)
    except (URLError, TimeoutError, ValueError, OSError):
        error = "Local model server is not running."
    provider = settings.fencecoach_chat_provider
    ready = {
        "local": model_ready,
        "bedrock": bool(settings.bedrock_chat_model_id),
        "gemini": bool(settings.gemini_api_key.get_secret_value()),
    }
    return {
        "provider": provider,
        "local_ready": model_ready,
        "bedrock_ready": bool(settings.bedrock_chat_model_id),
        "gemini_ready": ready["gemini"],
        "gemini_model_id": settings.gemini_chat_model,
        "live_configured": ready.get(provider, False),
        "model_id": configured_model_id(provider),
        "local_error": error
        or (None if model_ready else "The selected local model is not downloaded."),
    }


def configured_model_id(mode):
    return {
        "local": settings.ollama_chat_model,
        "bedrock": settings.bedrock_chat_model_id,
        "gemini": settings.gemini_chat_model,
    }.get(mode)


def chat_model(mode, model_id=None, *, max_tokens=2048, temperature=None):
    if mode == "local":
        from langchain_ollama import ChatOllama

        if not provider_status()["local_ready"]:
            raise RuntimeError(
                "Local coaching model is not ready. Start Ollama and pull the configured model."
            )
        return ChatOllama(
            model=settings.ollama_chat_model,
            base_url=settings.ollama_base_url,
            temperature=0,
            reasoning=False,
            num_ctx=4096 if settings.fencecoach_verified_dialogue else 16384,
            # Structured coaching reports are short; avoid slow oversized local
            # generations on modest hardware.
            num_predict=240,
            keep_alive=-1,
            client_kwargs={
                "timeout": settings.fencecoach_local_timeout_seconds
                if settings.fencecoach_verified_dialogue
                else 180
            },
        )
    if mode == "gemini":
        from langchain_google_genai import ChatGoogleGenerativeAI

        if not settings.gemini_api_key.get_secret_value():
            raise RuntimeError("Save GEMINI_API_KEY in the server's .env file for Gemini coaching.")
        selected_model = model_id or settings.gemini_chat_model
        options = (
            {"thinking_level": "minimal" if selected_model == "gemini-3.5-flash-lite" else "low"}
            if "gemini-3" in selected_model
            else {"thinking_budget": 0}
        )
        timeout = max(
            10, settings.gemini_request_timeout_seconds
        )  # Google's request deadline has a 10-second minimum.
        client_options = {"timeout": timeout}
        if settings.gemini_force_ipv4:
            client_options["transport"] = gemini_transport()
        return ChatGoogleGenerativeAI(
            model=selected_model,
            api_key=settings.gemini_api_key,
            vertexai=False,
            **(
                {"temperature": temperature}
                if temperature is not None
                else {"temperature": 1.0}
                if "gemini-3.6" not in selected_model
                and "gemini-3.5-flash-lite" not in selected_model
                else {}
            ),
            max_tokens=max_tokens,
            timeout=timeout,
            client_args=client_options,
            max_retries=0,
            include_thoughts=False,
            **options,
        )
    if mode == "bedrock":
        from botocore.config import Config
        from langchain_aws import ChatBedrockConverse

        if not settings.bedrock_chat_model_id:
            raise RuntimeError(
                "Configure BEDROCK_CHAT_MODEL_ID and AWS credentials for cloud coaching."
            )
        return ChatBedrockConverse(
            model=settings.bedrock_chat_model_id,
            region_name=settings.aws_region,
            temperature=0,
            config=Config(connect_timeout=10, read_timeout=120, retries={"max_attempts": 1}),
        )
    return None
