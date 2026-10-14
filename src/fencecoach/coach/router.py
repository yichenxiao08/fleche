"""Bounded Gemini → Ollama routing with a thread-safe half-open circuit."""

from __future__ import annotations

import threading
import time
from email.utils import parsedate_to_datetime

import httpx
from langchain_core.exceptions import ModelConnectionError, ModelRateLimitError, ModelTimeoutError

from fencecoach.settings import settings


class ProvidersUnavailable(RuntimeError):
    """No answer was produced; never disguise a provider failure as missing data."""

    def __init__(self, message, *, primary_reason=None, fallback_reason=None):
        super().__init__(message)
        self.primary_reason = primary_reason
        self.fallback_reason = fallback_reason


def failure_reason(exc):
    """Request/auth/validation errors are deliberately not retryable."""
    for error in (exc, exc.__cause__, exc.__context__):
        if error is None:
            continue
        response = getattr(error, "response", None)
        code = getattr(error, "status_code", None) or getattr(response, "status_code", None)
        code = code or getattr(error, "code", None)
        if callable(code):
            code = code()
        if code in {400, 401, 403, 404, 422}:
            return None
        if (
            isinstance(error, ModelRateLimitError)
            or code == 429
            or str(code).endswith("RESOURCE_EXHAUSTED")
        ):
            return "rate_limit"
        if isinstance(error, (ModelTimeoutError, httpx.TimeoutException, TimeoutError)):
            return "timeout"
        if isinstance(error, (ModelConnectionError, httpx.TransportError, ConnectionError)):
            return "connection"
        if code in {408, 500, 502, 503, 504} or str(code).endswith(
            ("UNAVAILABLE", "DEADLINE_EXCEEDED")
        ):
            return "transient"
    return None


def retry_after(exc):
    for error in (exc, exc.__cause__, exc.__context__):
        if error is None:
            continue
        response = getattr(error, "response", None)
        headers = getattr(response, "headers", None) or getattr(error, "headers", {}) or {}
        hint = headers.get("retry-after") or headers.get("Retry-After")
        if hint is not None:
            try:
                return max(0, float(hint))
            except (TypeError, ValueError):
                try:
                    return max(0, parsedate_to_datetime(hint).timestamp() - time.time())
                except (TypeError, ValueError, OverflowError):
                    pass
    return 0


class CircuitBreaker:
    def __init__(self, clock=time.monotonic):
        self.clock = clock
        self.lock = threading.Lock()
        self.until = 0.0
        self.probing = False
        self.reason = None
        self.generation = 0
        self.active_probe = None

    def acquire(self):
        allowed, reason, _ = self.acquire_lease()
        return allowed, reason

    def acquire_lease(self):
        with self.lock:
            if self.until and (self.clock() < self.until or self.probing):
                return False, self.reason, None
            if self.until:
                self.probing = True
                self.active_probe = self.generation
            return True, None, self.generation

    def success(self, lease=None):
        with self.lock:
            if lease is not None and lease != self.generation:
                return
            if self.until and not self.probing:
                return
            self.until, self.probing, self.reason = 0.0, False, None
            self.active_probe = None

    def failure(self, reason, delay):
        with self.lock:
            self.until = max(self.until, self.clock() + max(1, delay))
            self.reason = reason
            self.probing = False
            self.active_probe = None
            self.generation += 1


gemini_circuit = CircuitBreaker()


def route(operation, mode, *, breaker=None):
    """Operation returns a checked result; it must not publish unverified model text."""
    breaker = breaker or gemini_circuit
    if mode != "gemini":
        return operation(mode), None
    allowed, reason, lease = breaker.acquire_lease()
    if allowed:
        try:
            result = operation("gemini")
        except Exception as exc:
            reason = failure_reason(exc)
            if reason is None:
                # Release a half-open lease even for a request bug; do not hide it.
                breaker.success(lease)
                raise
            breaker.failure(
                reason, max(settings.fencecoach_provider_cooldown_seconds, retry_after(exc))
            )
            if not settings.fencecoach_local_fallback:
                raise
        else:
            breaker.success(lease)
            return result, None
    elif not settings.fencecoach_local_fallback:
        raise ProvidersUnavailable(
            "Gemini is cooling down after a provider failure. Your question is kept; try again shortly.",
            primary_reason=reason,
        )
    else:
        reason = "cooldown:" + str(reason)
    try:
        return operation("local"), reason
    except Exception as exc:
        if failure_reason(exc) or isinstance(exc, RuntimeError):
            fallback_reason = failure_reason(exc) or (
                "not_ready" if isinstance(exc, RuntimeError) else "unavailable"
            )
            import logging

            logging.getLogger(__name__).warning(
                "Coaching fallback failed; primary_reason=%s fallback_reason=%s",
                reason,
                fallback_reason,
            )
            raise ProvidersUnavailable(
                "Gemini is unavailable and the local coach could not respond. Your question is kept; start Ollama or try again after the provider recovers.",
                primary_reason=reason,
                fallback_reason=fallback_reason,
            ) from exc
        raise
