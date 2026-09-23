"""Bounded retry policy for transient model/gateway failures only."""
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import math
import random

import httpx
from anthropic import APIConnectionError

MAX_MODEL_RETRIES = 3


class ModelStreamInterrupted(RuntimeError):
    """The upstream stream closed without its completion marker."""


class ModelRetryExhausted(RuntimeError):
    def __init__(self) -> None:
        super().__init__("模型服务暂时不可用，自动重试 3 次后仍未恢复。已完成的命令不会重复执行，请稍后在原会话继续。")


def is_retryable_model_error(error: Exception) -> bool:
    status = getattr(error, "status_code", None)
    message = str(error).lower()
    # Permanent failures must not become retryable through a nested proxy message.
    if status in {401, 403, 404} or any(marker in message for marker in (
        "insufficient_quota", "quota exceeded", "credit balance", "insufficient balance",
        "invalid api key", "authentication_error", "permission_denied", "certificate_verify_failed",
    )):
        return False
    if status in {408, 409, 429, 500, 502, 503, 504, 529}:
        return True
    if isinstance(error, (ModelStreamInterrupted, APIConnectionError, httpx.TransportError, TimeoutError, ConnectionError)):
        return True
    body = getattr(error, "body", None)
    if isinstance(body, dict):
        details = body.get("error", body)
        if isinstance(details, dict) and details.get("type") in {
            "overloaded_error", "rate_limit_error", "service_unavailable_error", "stream_error",
        }:
            return True
    # Gateways can wrap upstream overloads in 400/422 conversion errors.
    return status in {400, 422} and any(marker in message for marker in (
        "overloaded", "overloaded_error", "service_unavailable_error",
        "rate_limit_error", "concurrency limit", "too many concurrent",
    ))


def model_retry_delay(error: Exception, retry_number: int) -> float:
    delay = 2 ** retry_number + random.uniform(0, 0.5)
    headers = getattr(getattr(error, "response", None), "headers", {})
    retry_after = headers.get("retry-after")
    if retry_after:
        try:
            requested = float(retry_after)
        except (TypeError, ValueError):
            try:
                requested = (parsedate_to_datetime(str(retry_after)) - datetime.now(timezone.utc)).total_seconds()
            except (TypeError, ValueError, OverflowError):
                requested = 0
        if math.isfinite(requested):
            delay = max(delay, min(60, requested))
    return delay
