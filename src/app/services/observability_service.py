from __future__ import annotations

import os
import time
import logging
from logging.handlers import RotatingFileHandler
from contextlib import contextmanager
from typing import Any, Iterator

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from app.core.runtime.control import get_runtime_control
from app.shared.config import APP_DIR
from app.utils.secure_storage import ensure_private_directory, ensure_private_file
from app.services.redaction_service import RedactionService

_tracer_provider: TracerProvider | None = None
_file_logging_configured = False


class _RedactingLogFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = RedactionService().redact_text(record.getMessage())
        record.args = ()
        return True


def _configure_file_logging() -> None:
    global _file_logging_configured
    if _file_logging_configured:
        return
    enabled = os.environ.get("OPS_AGENT_FILE_LOG", "").lower() in {"1", "true", "yes"}
    if not enabled and os.environ.get("OPS_AGENT_ENV", "").lower() != "production":
        return
    log_dir = APP_DIR / "logs"
    ensure_private_directory(log_dir)
    log_path = log_dir / "ops-agent.log"
    handler = RotatingFileHandler(log_path, maxBytes=10 * 1024 * 1024, backupCount=5, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    handler.addFilter(_RedactingLogFilter())
    logging.getLogger().addHandler(handler)
    ensure_private_file(log_path)
    _file_logging_configured = True


def configure_telemetry() -> None:
    global _tracer_provider
    _configure_file_logging()
    if _tracer_provider is not None:
        return
    provider = TracerProvider(resource=Resource.create({"service.name": "ops-agent"}))
    endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "").strip()
    if endpoint:
        provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint)))
    trace.set_tracer_provider(provider)
    _tracer_provider = provider


def shutdown_telemetry() -> None:
    global _tracer_provider
    if _tracer_provider is not None:
        _tracer_provider.shutdown()
        _tracer_provider = None


@contextmanager
def trace_operation(name: str, attributes: dict[str, Any] | None = None) -> Iterator[None]:
    tracer = trace.get_tracer("ops-agent")
    with tracer.start_as_current_span(name) as span:
        for key, value in (attributes or {}).items():
            if value is not None:
                span.set_attribute(key, value)
        yield


@contextmanager
def trace_detached_operation(name: str, attributes: dict[str, Any] | None = None) -> Iterator[None]:
    span = trace.get_tracer("ops-agent").start_span(name)
    try:
        for key, value in (attributes or {}).items():
            if value is not None:
                span.set_attribute(key, value)
        yield
    except Exception as error:
        span.record_exception(error)
        raise
    finally:
        span.end()


class ObservabilityService:
    def __init__(self) -> None:
        self._started_monotonic = time.monotonic()

    def runtime_snapshot(self) -> dict[str, Any]:
        control = get_runtime_control()
        snapshot = control.metrics.snapshot(control.limits)
        snapshot["processUptimeSeconds"] = max(0.0, time.monotonic() - self._started_monotonic)
        return snapshot


_observability_service = ObservabilityService()


def get_observability_service() -> ObservabilityService:
    return _observability_service
