from __future__ import annotations

import os
import time
from contextlib import contextmanager
from typing import Any, Iterator

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from app.core.runtime.control import get_runtime_control

_tracer_provider: TracerProvider | None = None


def configure_telemetry() -> None:
    global _tracer_provider
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
