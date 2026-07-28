from __future__ import annotations

import json
import logging
import re
import uuid
from collections.abc import Generator, Iterator
from typing import Any

from app.core.llm.factory import build_llm_provider
from app.core.llm.types import LLMMessage, LLMTokenUsage
from app.core.loop.loop_events import LoopEvent, emit_completed, emit_failed, emit_plan_update
from app.core.loop.loop_state import LoopRuntimeStep, LoopState
from app.core.loop.message_manager import MessageManager


logger = logging.getLogger(__name__)


class PlanExecutionMixin:
    def _run_plan_mode(
        self: Any,
        state: LoopState,
        *,
        manager: MessageManager,
        continue_existing: bool = False,
    ) -> Iterator[LoopEvent]:
        if not continue_existing and not state.steps:
            yield from self._generate_plan(state, manager=manager)
            return
        if state.phase == "waiting_plan_approval":
            return

        while state.cursor < len(state.steps):
            step = state.get_current_step()
            if step is None:
                break
            if step.status == "completed":
                state.cursor += 1
                continue
            if not state.messages:
                state.messages = self._build_step_messages(state, step)
            if step.status != "failed":
                step.status = "running"
            state.phase = "executing"
            paused, _, summary = yield from self._tool_calling_loop(
                state,
                manager=manager,
                plan_step=step,
                finalize_on_complete=False,
            )
            if paused:
                return
            if step.status == "failed":
                if summary:
                    step.output = summary
                state.phase = "failed"
                state.error_message = summary or "Failed to execute plan step."
                yield emit_failed(runtime_id=state.context.runtime_id, error=state.error_message)
                return
            step.status = "completed"
            if summary:
                step.output = summary
            yield self._emit_plan_state(state, title="Task Plan")
            state.messages = []
            state.cursor += 1

        summary = yield from self._summarize_plan_completion(state, manager=manager)
        state.phase = "completed"
        state.summary = summary
        yield emit_completed(runtime_id=state.context.runtime_id, summary=summary)

    def _emit_plan_state(self: Any, state: LoopState, *, title: str) -> LoopEvent:
        return emit_plan_update(
            runtime_id=state.context.runtime_id,
            plan_id=f"plan-{state.context.runtime_id}",
            title=title,
            steps=state.steps,
            version=state.plan_version,
            locked_plan=state.locked_plan,
            is_latest=True,
            updated=True,
            loading=False,
            mode=state.context.mode,
        )

    def _summarize_plan_completion(
        self: Any,
        state: LoopState,
        *,
        manager: MessageManager,
    ) -> Generator[LoopEvent, None, str]:
        provider = build_llm_provider(state.context.model_config)
        step_lines = []
        for index, step in enumerate(state.steps, start=1):
            parts = [f"{index}. {step.title}", f"status={step.status}"]
            if step.output:
                parts.append(f"output={step.output}")
            step_lines.append(" | ".join(parts))

        yield from manager.begin_message(message_type="say", say_type="text")
        request = self._request_builder.build_plan_summary_request(state=state, step_lines=step_lines)
        summary_parts: list[str] = []
        usage: LLMTokenUsage | None = None
        self._before_llm_call(state)
        for chunk in provider.stream_complete(config=state.context.model_config, request=request):
            self._check_runtime_budget(state)
            if chunk.delta:
                summary_parts.append(chunk.delta)
                yield from manager.update(text=chunk.delta)
            if chunk.thinking_delta:
                yield from manager.update(thinking=chunk.thinking_delta)
            usage = chunk.usage or usage
        self._record_usage(state, usage, call_kind="plan_summary")
        summary = "".join(summary_parts).strip() or "Plan execution completed."
        if summary_parts:
            yield from manager.finalize()
        else:
            yield from manager.finalize(text=summary)
        return summary

    def _generate_plan(self: Any, state: LoopState, *, manager: MessageManager) -> Iterator[LoopEvent]:
        provider = build_llm_provider(state.context.model_config)
        ctx = state.context
        yield from manager.begin_message(message_type="say", say_type="text")
        request = self._request_builder.build_plan_generation_request(state=state)
        try:
            self._before_llm_call(state)
            response = provider.complete(config=ctx.model_config, request=request)
            self._check_runtime_budget(state)
            self._record_usage(state, response.usage, call_kind="plan_generation")
            payload = json.loads(self._extract_json_payload(response.text))
            raw_steps = payload.get("steps") or []
            if not isinstance(raw_steps, list):
                raise ValueError("planner returned invalid steps")
            if not raw_steps:
                raw_steps = [{
                    "title": "Execute user task",
                    "reason": "The planner returned no steps, so execute the user's request directly.",
                    "expected_output": "Complete the user's requested operations task.",
                    "risk_level": "medium",
                }]
            state.steps = []
            state.cursor = 0
            for index, item in enumerate(raw_steps, start=1):
                data = item if isinstance(item, dict) else {}
                state.steps.append(LoopRuntimeStep(
                    step_id=f"step-{uuid.uuid4().hex[:8]}",
                    title=str(data.get("title") or f"Step {index}"),
                    reason=str(data.get("reason") or "Executing plan step"),
                    risk_level=str(data.get("risk_level") or "low"),
                    working_directory=str(data.get("working_directory") or "") or None,
                    expected_output=str(data.get("expected_output") or "") or None,
                    status="pending",
                ))
            state.phase = "waiting_plan_approval"
            state.locked_plan = False
            yield emit_plan_update(
                runtime_id=ctx.runtime_id,
                plan_id=f"plan-{ctx.runtime_id}",
                title="Task Plan",
                steps=state.steps,
                version=state.plan_version,
                locked_plan=False,
                is_latest=True,
                updated=False,
                loading=False,
                mode=ctx.mode,
            )
        except Exception as exc:
            error = f"Task planning failed: {exc}"
            state.phase = "failed"
            state.error_message = error
            yield from manager.finalize(text=f"\nError: {error}")
            yield emit_failed(runtime_id=ctx.runtime_id, error=error)

    def _extract_json_payload(self: Any, text: str) -> str:
        stripped = text.strip()
        if stripped.startswith("```"):
            stripped = re.sub(r"^```(?:json)?\s*", "", stripped, flags=re.IGNORECASE)
            stripped = re.sub(r"\s*```$", "", stripped)
        return stripped

    def _build_step_messages(self: Any, state: LoopState, step: LoopRuntimeStep) -> list[LLMMessage]:
        return self._request_builder.build_plan_step_messages(state=state, step=step)
