from __future__ import annotations

import os
import threading
import time
from collections import deque
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from typing import Any, Iterator


class RuntimeCapacityError(RuntimeError):
    """Raised when bounded runtime capacity cannot be acquired in time."""


class RuntimeCancelledError(RuntimeError):
    """Raised when an operator cancels an active runtime."""


class RuntimeBudgetExceededError(RuntimeError):
    """Raised when a runtime exceeds one of its configured budgets."""


def _positive_int(name: str, default: int) -> int:
    try:
        value = int(os.environ.get(name, str(default)))
    except ValueError:
        return default
    return value if value > 0 else default


def _positive_float(name: str, default: float) -> float:
    try:
        value = float(os.environ.get(name, str(default)))
    except ValueError:
        return default
    return value if value > 0 else default


def _percentile(values: list[float], quantile: float) -> float:
    if not values:
        return 0.0
    position = (len(values) - 1) * quantile
    lower = int(position)
    upper = min(lower + 1, len(values) - 1)
    fraction = position - lower
    return values[lower] + (values[upper] - values[lower]) * fraction


@dataclass(frozen=True, slots=True)
class RuntimeLimits:
    max_concurrent_runs: int
    max_concurrent_tools: int
    max_llm_calls: int
    max_tool_calls: int
    runtime_timeout_seconds: float
    queue_wait_seconds: float
    max_scheduler_jobs: int
    scheduler_lease_seconds: int
    max_mcp_calls_per_server: int

    @classmethod
    def from_env(cls) -> "RuntimeLimits":
        return cls(
            max_concurrent_runs=_positive_int("OPS_AGENT_MAX_CONCURRENT_RUNS", 4),
            max_concurrent_tools=_positive_int("OPS_AGENT_MAX_CONCURRENT_TOOLS", 8),
            max_llm_calls=_positive_int("OPS_AGENT_MAX_LLM_CALLS", 20),
            max_tool_calls=_positive_int("OPS_AGENT_MAX_TOOL_CALLS", 40),
            runtime_timeout_seconds=_positive_float("OPS_AGENT_RUNTIME_TIMEOUT_SECONDS", 900.0),
            queue_wait_seconds=_positive_float("OPS_AGENT_QUEUE_WAIT_SECONDS", 5.0),
            max_scheduler_jobs=_positive_int("OPS_AGENT_MAX_SCHEDULER_JOBS", 2),
            scheduler_lease_seconds=_positive_int("OPS_AGENT_SCHEDULER_LEASE_SECONDS", 3600),
            max_mcp_calls_per_server=_positive_int("OPS_AGENT_MAX_MCP_CALLS_PER_SERVER", 2),
        )


class RuntimeMetrics:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._started_at = time.time()
        self._counters: dict[str, int] = {
            "runs_started": 0,
            "runs_completed": 0,
            "runs_failed": 0,
            "runs_cancelled": 0,
            "runs_rejected": 0,
            "budget_exceeded": 0,
            "llm_calls": 0,
            "tool_calls": 0,
            "mcp_calls": 0,
            "scheduler_runs": 0,
            "scheduler_failures": 0,
            "runtime_guidance_messages": 0,
            "runtime_guidance_messages_applied": 0,
            "followup_questions": 0,
            "followup_resumes": 0,
            "approvals_with_guidance": 0,
            "task_state_updates": 0,
            "completed_with_tool_failures": 0,
        }
        self._active_runs = 0
        self._active_tools = 0
        self._run_durations: deque[float] = deque(maxlen=256)
        self._first_response_durations: deque[float] = deque(maxlen=256)
        self._first_response_runtime_ids: set[str] = set()
        self._first_response_runtime_order: deque[str] = deque()
        self._logical_runs: dict[str, float] = {}
        self._finished_runtime_ids: set[str] = set()
        self._finished_runtime_order: deque[str] = deque()

    def increment(self, name: str, value: int = 1) -> None:
        with self._lock:
            self._counters[name] = self._counters.get(name, 0) + value

    def run_started(self, runtime_id: str) -> None:
        with self._lock:
            if runtime_id in self._logical_runs or runtime_id in self._finished_runtime_ids:
                return
            self._logical_runs[runtime_id] = time.monotonic()
            self._counters["runs_started"] += 1

    def run_finished(
        self,
        runtime_id: str,
        *,
        status: str,
        duration_seconds: float | None = None,
    ) -> None:
        with self._lock:
            if runtime_id in self._finished_runtime_ids:
                return
            started = self._logical_runs.pop(runtime_id, None)
            duration = duration_seconds
            if duration is None and started is not None:
                duration = time.monotonic() - started
            self._run_durations.append(max(0.0, duration or 0.0))
            counter = {
                "completed": "runs_completed",
                "cancelled": "runs_cancelled",
            }.get(status, "runs_failed")
            self._counters[counter] += 1
            if len(self._finished_runtime_order) >= 2048:
                self._finished_runtime_ids.discard(self._finished_runtime_order.popleft())
            self._finished_runtime_ids.add(runtime_id)
            self._finished_runtime_order.append(runtime_id)

    def run_capacity_started(self) -> None:
        with self._lock:
            self._active_runs += 1

    def record_first_response(self, runtime_id: str, duration_seconds: float) -> None:
        with self._lock:
            if runtime_id in self._first_response_runtime_ids:
                return
            if len(self._first_response_runtime_order) >= 2048:
                self._first_response_runtime_ids.discard(self._first_response_runtime_order.popleft())
            self._first_response_runtime_ids.add(runtime_id)
            self._first_response_runtime_order.append(runtime_id)
            self._first_response_durations.append(max(0.0, duration_seconds))

    def run_capacity_finished(self) -> None:
        with self._lock:
            self._active_runs = max(0, self._active_runs - 1)

    def tool_started(self) -> None:
        with self._lock:
            self._active_tools += 1
            self._counters["tool_calls"] += 1

    def tool_finished(self) -> None:
        with self._lock:
            self._active_tools = max(0, self._active_tools - 1)

    def snapshot(self, limits: RuntimeLimits) -> dict[str, Any]:
        with self._lock:
            durations = sorted(self._run_durations)
            first_response_durations = sorted(self._first_response_durations)
            runs_started = self._counters.get("runs_started", 0)
            guidance_messages = (
                self._counters.get("runtime_guidance_messages", 0)
                + self._counters.get("approvals_with_guidance", 0)
            )
            return {
                "startedAt": self._started_at,
                "uptimeSeconds": max(0.0, time.time() - self._started_at),
                "activeRuns": self._active_runs,
                "activeTools": self._active_tools,
                "recentRunDurationP95Seconds": _percentile(durations, 0.95),
                "dialogue": {
                    "firstResponseSamples": len(first_response_durations),
                    "firstResponseP50Seconds": _percentile(first_response_durations, 0.5),
                    "firstResponseP95Seconds": _percentile(first_response_durations, 0.95),
                    "clarificationRate": self._counters.get("followup_questions", 0) / runs_started if runs_started else 0.0,
                    "guidanceApplyRate": min(
                        1.0,
                        self._counters.get("runtime_guidance_messages_applied", 0) / guidance_messages,
                    ) if guidance_messages else 0.0,
                },
                "counters": dict(self._counters),
                "limits": asdict(limits),
            }


class RuntimeControl:
    def __init__(self, limits: RuntimeLimits | None = None) -> None:
        self.limits = limits or RuntimeLimits.from_env()
        self.metrics = RuntimeMetrics()
        self._run_capacity = threading.BoundedSemaphore(self.limits.max_concurrent_runs)
        self._tool_capacity = threading.BoundedSemaphore(self.limits.max_concurrent_tools)

    @contextmanager
    def run_slot(self) -> Iterator[None]:
        acquired = self._run_capacity.acquire(timeout=self.limits.queue_wait_seconds)
        if not acquired:
            self.metrics.increment("runs_rejected")
            raise RuntimeCapacityError("Agent runtime capacity is full. Please retry shortly.")
        self.metrics.run_capacity_started()
        try:
            yield
        finally:
            self.metrics.run_capacity_finished()
            self._run_capacity.release()

    @contextmanager
    def tool_slot(self) -> Iterator[None]:
        acquired = self._tool_capacity.acquire(timeout=self.limits.queue_wait_seconds)
        if not acquired:
            raise RuntimeCapacityError("Tool execution capacity is full. Please retry shortly.")
        self.metrics.tool_started()
        try:
            yield
        finally:
            self.metrics.tool_finished()
            self._tool_capacity.release()


_runtime_control: RuntimeControl | None = None
_runtime_control_lock = threading.Lock()


def get_runtime_control() -> RuntimeControl:
    global _runtime_control
    if _runtime_control is None:
        with _runtime_control_lock:
            if _runtime_control is None:
                _runtime_control = RuntimeControl()
    return _runtime_control
