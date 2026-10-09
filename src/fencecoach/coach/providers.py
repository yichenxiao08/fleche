"""Explicit provider selection: sample reports never masquerade as a live LLM."""

from __future__ import annotations

import json
from urllib.error import URLError
from urllib.request import Request, urlopen

from fencecoach.settings import settings


def warm_local_model():
    """Load the configured model without generating a reply; callers run this in the background."""
    if settings.fencecoach_chat_provider != "local":
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


def chat_model(mode):
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
            num_ctx=4096,
            # Structured coaching reports are short; avoid slow oversized local
            # generations on modest hardware.
            num_predict=240,
            keep_alive=-1,
            client_kwargs={"timeout": 180},
        )
    if mode == "gemini":
        from langchain_google_genai import ChatGoogleGenerativeAI

        if not settings.gemini_api_key.get_secret_value():
            raise RuntimeError("Save GEMINI_API_KEY in the server's .env file for Gemini coaching.")
        options = (
            {"thinking_level": "low"}
            if "gemini-3" in settings.gemini_chat_model
            else {"thinking_budget": 0}
        )
        return ChatGoogleGenerativeAI(
            model=settings.gemini_chat_model,
            api_key=settings.gemini_api_key,
            vertexai=False,
            temperature=1.0,
            max_tokens=2048,
            timeout=20,
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
