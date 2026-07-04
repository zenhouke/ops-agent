from __future__ import annotations

import hashlib
import json
import logging
import secrets
import re
import uuid
from collections.abc import Callable, Generator, Iterator
from typing import Any

logger = logging.getLogger(__name__)
_SECRET_ARG_KEY_RE = re.compile(r"(token|password|passwd|secret|api[_-]?key|authorization|cookie|credential)", re.IGNORECASE)

from app.core.llm.types import LLMCompletionResponse, LLMMessage, LLMTokenUsage
from app.core.llm.factory import build_llm_provider
from app.core.loop.request_builder import AgentLLMRequestBuilder
from app.core.loop.loop_events import (
    AgentMessage,
    LoopEvent,
    emit_completed,
    emit_failed,
    emit_plan_update,
)
from app.core.loop.loop_state import LoopRuntimeStep, LoopState
from app.core.loop.message_manager import MessageManager
from app.core.loop.prompts import (
    build_manual_skill_system_prompt,
)
from app.core.tool.handler import ToolDisplayMetadata, ToolHandler


EventCallback = Any


class AgentLoop:
    def __init__(
        self,
        *,
        tools: list[ToolHandler],
        request_builder: AgentLLMRequestBuilder | None = None,
        usage_callback: Any | None = None,
    ) -> None:
        self._tools = {t.definition.name: t for t in tools}
        self._request_builder = request_builder or AgentLLMRequestBuilder()
        self._usage_callback = usage_callback

    def _get_tool_display_metadata(self, handler: ToolHandler | None, args: dict[str, Any]) -> ToolDisplayMetadata:
        if handler is None:
            return ToolDisplayMetadata()
        display_metadata = getattr(handler, "display_metadata", None)
        if display_metadata is None:
            return ToolDisplayMetadata()
        return display_metadata(args)

    def _args_for_display(self, handler: ToolHandler | None, args: dict[str, Any]) -> dict[str, Any]:
        metadata = self._get_tool_display_metadata(handler, args)
        if metadata.extra.get("kind") != "mcp":
            return args
        return self._redact_sensitive_args(args)

    def _redact_sensitive_args(self, value: Any) -> Any:
        if isinstance(value, dict):
            return {
                key: "[redacted]" if _SECRET_ARG_KEY_RE.search(str(key)) else self._redact_sensitive_args(item)
                for key, item in value.items()
            }
        if isinstance(value, list):
            return [self._redact_sensitive_args(item) for item in value]
        return value

    def _clear_pending_approval(self, state: LoopState) -> None:
        state.pending_tool_call_id = None
        state.pending_tool_name = None
        state.pending_tool_args = None
        state.pending_message_id = None
        state.pending_approval_token_hash = None
        state.pending_approval_token = None
        state.pending_approval_step_id = None
        state.pending_approval_consistency = None

    def _append_pending_tool_result(self, state: LoopState, *, content: str) -> None:
        message = LLMMessage(
            role="tool",
            content=content,
            tool_call_id=state.pending_tool_call_id,
            name=state.pending_tool_name,
        )
        pending_tool_call_id = state.pending_tool_call_id
        if pending_tool_call_id is None:
            state.messages.append(message)
            return
        for index in range(len(state.messages) - 1, -1, -1):
            candidate = state.messages[index]
            if candidate.role != "assistant":
                continue
            tool_call_ids = [tool_call.id for tool_call in candidate.tool_calls]
            if pending_tool_call_id not in tool_call_ids:
                continue
            insert_at = index + 1
            for tool_call_id in tool_call_ids:
                if tool_call_id == pending_tool_call_id:
                    break
                while insert_at < len(state.messages):
                    existing = state.messages[insert_at]
                    if existing.role == "tool" and existing.tool_call_id == tool_call_id:
                        insert_at += 1
                        break
                    if existing.role == "tool":
                        insert_at += 1
                        continue
                    break
            state.messages.insert(insert_at, message)
            return
        state.messages.append(message)

    def _build_approval_consistency(self, state: LoopState, args: dict[str, Any], tool_call_id: str) -> dict[str, Any] | None:
        authorization_id = str(args.get("authorization_id", "") or "")
        handler = self._tools.get("execute_command")
        terminal = getattr(handler, "_terminal", None)
        resolver = getattr(terminal, "resolve_terminal_authorization", None)
        if not authorization_id or resolver is None:
            raise ValueError("Missing terminal authorization resolver.")
        authorization = resolver(state.context.runtime_id, authorization_id)
        return {
            "runtime_id": state.context.runtime_id,
            "conversation_id": state.context.conversation_id,
            "tool_call_id": tool_call_id,
            "authorization_id": authorization.authorization_id,
            "status": authorization.status,
            "asset_id": authorization.asset_id,
            "asset_name": authorization.asset_name,
            "terminal_id": authorization.terminal_id,
            "command": args.get("command"),
        }

    def _approval_consistency_error(self, state: LoopState) -> str | None:
        snapshot = state.pending_approval_consistency
        if state.pending_tool_name != "execute_command" or not snapshot:
            return None
        args = state.pending_tool_args or {}
        handler = self._tools.get("execute_command")
        terminal = getattr(handler, "_terminal", None)
        resolver = getattr(terminal, "resolve_terminal_authorization", None)
        belongs_to_asset = getattr(terminal, "session_belongs_to_asset", None)
        if resolver is None or belongs_to_asset is None:
            return "Missing terminal authorization resolver."
        try:
            authorization = resolver(state.context.runtime_id, str(snapshot["authorization_id"]))
        except ValueError as exc:
            return str(exc)
        if authorization.status != "active":
            return "Terminal authorization is no longer active."
        if authorization.terminal_id != snapshot["terminal_id"]:
            return "Authorized terminal changed after approval was requested."
        if authorization.asset_id != snapshot["asset_id"]:
            return "Authorized asset changed after approval was requested."
        if args.get("authorization_id") != snapshot["authorization_id"]:
            return "Approval target authorization changed."
        if args.get("terminal_id") != snapshot["terminal_id"]:
            return "Approval terminal changed."
        if args.get("command") != snapshot["command"]:
            return "Approved command changed before execution."
        if not belongs_to_asset(authorization.terminal_id, authorization.asset_id):
            return "Authorized terminal is no longer valid for the asset."
        return None

    def _record_usage(self, state: LoopState, usage: LLMTokenUsage | None, *, call_kind: str) -> None:
        if usage is None or self._usage_callback is None:
            return
        if usage.total_tokens <= 0:
            return
        self._usage_callback(state, usage, call_kind)

    def _prepare_tool_args(self, handler: ToolHandler, args: dict[str, Any], state: LoopState) -> dict[str, Any]:
        metadata = self._get_tool_display_metadata(handler, args)
        if metadata.extra.get("kind") != "command":
            return args
        prepared = dict(args)
        used_default_authorization = False
        if state.context.default_authorization_id and not str(prepared.get("authorization_id", "") or ""):
            prepared["authorization_id"] = state.context.default_authorization_id
            used_default_authorization = True
        if used_default_authorization and state.context.terminal_id and not str(prepared.get("terminal_id", "") or ""):
            prepared["terminal_id"] = state.context.terminal_id
        prepared.setdefault("asset_type", state.context.asset_type)
        prepared["runtime_id"] = state.context.runtime_id
        prepared["shell_type"] = state.context.shell_type
        prepared["execution_profile"] = state.context.execution_profile
        if state.context.device_vendor:
            prepared["device_vendor"] = state.context.device_vendor
        return prepared

    def _is_missing_command(self, handler: ToolHandler, args: dict[str, Any]) -> bool:
        metadata = self._get_tool_display_metadata(handler, args)
        return metadata.extra.get("kind") == "command" and not str(args.get("command", "")).strip()

    def _build_tool_call_payload(
        self,
        *,
        handler: ToolHandler | None,
        tool_call_id: str | None,
        tool_name: str | None,
        args: dict[str, Any],
        command: str | None = None,
    ) -> dict[str, Any]:
        metadata = self._get_tool_display_metadata(handler, args)
        payload: dict[str, Any] = {
            "id": tool_call_id,
            "name": tool_name,
            "args": self._args_for_display(handler, args),
        }
        if metadata.description:
            payload["description"] = metadata.description
        if metadata.display_text:
            payload["displayText"] = metadata.display_text
        protected_keys = {"id", "name", "args", "command", "description", "displayText"}
        for key, value in metadata.extra.items():
            if key not in protected_keys:
                payload[key] = value
        normalized_command = (command or "").strip()
        if normalized_command:
            payload["command"] = normalized_command
        return payload

    def run(self, state: LoopState) -> Iterator[LoopEvent]:
        manager = MessageManager(runtime_id=state.context.runtime_id)
        if state.cancel_requested:
            state.phase = "cancelled"
            state.error_message = state.error_message or "Runtime cancelled."
            yield emit_failed(runtime_id=state.context.runtime_id, error=state.error_message)
            return
        if state.context.mode == "plan":
            yield from self._run_plan_mode(state, manager=manager)
            return
        yield from self._tool_calling_loop(state, manager=manager)

    def resume_with_approval(
        self,
        state: LoopState,
        *,
        approved: bool,
        on_approval_validated: Callable[[], None] | None = None,
    ) -> Iterator[LoopEvent]:
        if state.cancel_requested:
            state.phase = "cancelled"
            state.error_message = state.error_message or "Runtime cancelled."
            yield emit_failed(runtime_id=state.context.runtime_id, error=state.error_message)
            return
        if state.phase != "approving":
            return

        manager = MessageManager(runtime_id=state.context.runtime_id)
        current_step = state.get_current_step()
        if current_step is None:
            return

        # Reuse the ask message's ID so the frontend replaces the card in-place
        reuse_id = state.pending_message_id

        if not approved:
            current_step.status = "failed"
            
            # Reuse the ask message ID to replace it with a rejection message
            if reuse_id:
                yield from manager.resume_message(message_id=reuse_id, message_type="say", say_type="error")
                yield from manager.finalize(text="Command execution rejected by user.")
            else:
                # Fallback: create a new message if no ID to reuse
                yield from manager.begin_message(message_type="say", say_type="error")
                yield from manager.finalize(text="Command execution rejected by user.")
            
            current_step.output = "Command execution rejected by user."
            self._append_pending_tool_result(state, content=current_step.output)
            self._clear_pending_approval(state)
            if state.context.mode == "plan":
                yield from self._run_plan_mode(state, manager=manager, continue_existing=True)
                return
            yield from self._tool_calling_loop(state, manager=manager)
            return

        consistency_error = self._approval_consistency_error(state)
        if consistency_error:
            current_step.status = "failed"
            current_step.output = consistency_error
            if reuse_id:
                yield from manager.resume_message(message_id=reuse_id, message_type="say", say_type="error")
                yield from manager.finalize(text=consistency_error)
            else:
                yield from manager.begin_message(message_type="say", say_type="error")
                yield from manager.finalize(text=consistency_error)
            self._append_pending_tool_result(state, content=consistency_error)
            self._clear_pending_approval(state)
            if state.context.mode == "plan":
                yield from self._run_plan_mode(state, manager=manager, continue_existing=True)
                return
            yield from self._tool_calling_loop(state, manager=manager)
            return

        if on_approval_validated is not None:
            on_approval_validated()

        if state.cancel_requested:
            state.phase = "cancelled"
            state.error_message = state.error_message or "Runtime cancelled."
            yield emit_failed(runtime_id=state.context.runtime_id, error=state.error_message)
            return

        current_step.status = "running"
        state.phase = "executing"

        tool_name = state.pending_tool_name
        args = state.pending_tool_args or {}
        handler = None
        if tool_name is not None:
            handler = self._tools.get(tool_name)
        
        # Reuse the ask message ID to replace it with tool execution message
        command = str(args.get("command", "")).strip()
        tool_call_payload = self._build_tool_call_payload(
            handler=handler,
            tool_call_id=state.pending_tool_call_id,
            tool_name=tool_name,
            args=args,
            command=command,
        )
        if reuse_id:
            yield from manager.resume_message(message_id=reuse_id, message_type="say", say_type="tool_use")
            yield from manager.update(tool_call=tool_call_payload)
        else:
            # Fallback: create a new message if no ID to reuse
            yield from manager.begin_message(message_type="say", say_type="tool_use")
            yield from manager.update(tool_call=tool_call_payload)

        if handler is None:
            ok, output = False, f"Unsupported tool: {tool_name}"
        else:
            ok, output = yield from handler.execute(state=state, step_id=current_step.step_id, args=args, manager=manager)

        current_step.status = "completed" if ok else "failed"
        current_step.output = output if ok else f"Command Failed: {output}"
        self._append_pending_tool_result(state, content=current_step.output)
        self._clear_pending_approval(state)
        yield from manager.finalize(exit_code=0 if ok else 1)
        
        if state.context.mode == "plan":
            yield from self._run_plan_mode(state, manager=manager, continue_existing=True)
            return
        yield from self._tool_calling_loop(state, manager=manager)

    def _run_plan_mode(self, state: LoopState, *, manager: MessageManager, continue_existing: bool = False) -> Iterator[LoopEvent]:
        if state.cancel_requested:
            state.phase = "cancelled"
            state.error_message = state.error_message or "Runtime cancelled."
            yield emit_failed(runtime_id=state.context.runtime_id, error=state.error_message)
            return

        if not continue_existing and not state.steps:
            yield from self._generate_plan(state, manager=manager)
            return

        if state.phase == "waiting_plan_approval":
            return

        while state.cursor < len(state.steps):
            if state.cancel_requested:
                state.phase = "cancelled"
                state.error_message = state.error_message or "Runtime cancelled."
                yield emit_failed(runtime_id=state.context.runtime_id, error=state.error_message)
                return
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

            paused, _, summary = yield from self._tool_calling_loop(state, manager=manager, plan_step=step, finalize_on_complete=False)
            if paused:
                return

            if step.status == "failed":
                if summary:
                    step.output = summary
                state.phase = "failed"
                state.error_message = summary or "Failed to execute plan step."
                yield emit_failed(runtime_id=state.context.runtime_id, error=state.error_message)
                return

            if step.exit_code is None and not step.output:
                step.status = "failed"
                state.phase = "failed"
                state.error_message = (
                    "Plan step finished without command execution evidence. "
                    "Use execute_command on the authorized terminal before completing an operational step."
                )
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
        yield emit_completed(runtime_id=state.context.runtime_id, summary=state.summary)

    def _emit_plan_state(self, state: LoopState, *, title: str) -> LoopEvent:
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
            status=state.phase,
        )

    def _summarize_plan_completion(self, state: LoopState, *, manager: MessageManager) -> Generator[LoopEvent, None, str]:
        provider = build_llm_provider(state.context.model_config)
        ctx = state.context
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
        for chunk in provider.stream_complete(config=ctx.model_config, request=request):
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

    def _generate_plan(self, state: LoopState, *, manager: MessageManager) -> Iterator[LoopEvent]:
        provider = build_llm_provider(state.context.model_config)
        ctx = state.context
        if state.cancel_requested:
            state.phase = "cancelled"
            state.error_message = state.error_message or "Runtime cancelled."
            yield emit_failed(runtime_id=ctx.runtime_id, error=state.error_message)
            return
        
        yield from manager.begin_message(message_type="say", say_type="text")
        request = self._request_builder.build_plan_generation_request(state=state)
        try:
            response = provider.complete(config=ctx.model_config, request=request)
            self._record_usage(state, response.usage, call_kind="plan_generation")
            payload = json.loads(self._extract_json_payload(response.text))
            raw_steps = payload.get("steps") or []
            if not isinstance(raw_steps, list):
                raise ValueError("planner returned invalid steps")
            if not raw_steps:
                logger.warning("Planner returned empty steps; using fallback step (runtime_id=%s)", ctx.runtime_id)
                raw_steps = [
                    {
                        "title": "Execute user task",
                        "reason": "The planner returned no steps, so execute the user's request directly.",
                        "working_directory": "",
                        "expected_output": "Complete the user's requested operations task.",
                        "risk_level": "medium",
                    }
                ]

            state.steps = []
            state.cursor = 0
            for index, item in enumerate(raw_steps, start=1):
                data = item if isinstance(item, dict) else {}

                state.steps.append(
                    LoopRuntimeStep(
                        step_id=f"step-{uuid.uuid4().hex[:8]}",
                        title=str(data.get("title") or f"Step {index}"),
                        reason=str(data.get("reason") or "Executing plan step"),
                        risk_level=str(data.get("risk_level") or "low"),
                        working_directory=str(data.get("working_directory") or "") or None,
                        expected_output=str(data.get("expected_output") or "") or None,
                        status="pending",
                    )
                )

            state.phase = "waiting_plan_approval"
            state.locked_plan = False
            yield emit_plan_update(
                runtime_id=ctx.runtime_id,
                plan_id=f"plan-{ctx.runtime_id}",
                title="Task Plan",
                steps=state.steps,
                version=state.plan_version,
                locked_plan=state.locked_plan,
                is_latest=True,
                updated=False,
                loading=False,
                mode=ctx.mode,
                status=state.phase,
            )
        except Exception as exc:
            error = f"Task planning failed: {exc}"
            state.phase = "failed"
            state.error_message = error
            yield from manager.finalize(text=f"\nError: {error}")
            yield emit_failed(runtime_id=ctx.runtime_id, error=error)

    def _extract_json_payload(self, text: str) -> str:
        stripped = text.strip()
        if stripped.startswith("```"):
            stripped = re.sub(r"^```(?:json)?\s*", "", stripped, flags=re.IGNORECASE)
            stripped = re.sub(r"\s*```$", "", stripped)
        return stripped

    def _build_step_messages(self, state: LoopState, step: LoopRuntimeStep) -> list[LLMMessage]:
        return self._request_builder.build_plan_step_messages(state=state, step=step)

    def _tool_calling_loop(
        self,
        state: LoopState,
        *,
        manager: MessageManager,
        plan_step: LoopRuntimeStep | None = None,
        finalize_on_complete: bool = True,
    ) -> Iterator[LoopEvent]:
        provider = build_llm_provider(state.context.model_config)
        ctx = state.context

        tools = [t.definition for t in self._tools.values()]

        if not state.messages:
            state.messages = self._request_builder.build_initial_tool_calling_messages(state=state)

        import time

        unresolved_tool_failure = any(step.status == "failed" for step in state.steps)

        while True:
            if state.cancel_requested:
                state.phase = "cancelled"
                state.error_message = state.error_message or "Runtime cancelled."
                yield emit_failed(runtime_id=ctx.runtime_id, error=state.error_message)
                return True, False, state.error_message
            response_text_parts: list[str] = []
            response_thinking_parts: list[str] = []
            response_tool_calls = []
            finish_reason: str | None = None
            usage: LLMTokenUsage | None = None

            # Start a new assistant message for the LLM response
            yield from manager.begin_message(message_type="say", say_type="text")

            t0 = time.monotonic()
            first_chunk_logged = False
            for chunk in provider.stream_complete(
                config=ctx.model_config,
                request=self._request_builder.build_tool_calling_request(state=state, tools=tools),
            ):
                if state.cancel_requested:
                    state.phase = "cancelled"
                    state.error_message = state.error_message or "Runtime cancelled."
                    yield from manager.finalize(text="\nCancelled.")
                    yield emit_failed(runtime_id=ctx.runtime_id, error=state.error_message)
                    return True, False, state.error_message
                if not first_chunk_logged:
                    first_chunk_logged = True
                if chunk.thinking_delta:
                    response_thinking_parts.append(chunk.thinking_delta)
                    yield from manager.update(thinking=chunk.thinking_delta)
                if chunk.delta:
                    response_text_parts.append(chunk.delta)
                    yield from manager.update(text=chunk.delta)
                if chunk.tool_calls:
                    response_tool_calls = chunk.tool_calls
                if chunk.finish_reason:
                    finish_reason = chunk.finish_reason
                usage = chunk.usage or usage
            self._record_usage(state, usage, call_kind="agent")

            thinking_content = "".join(response_thinking_parts)
            if thinking_content:
                logger.info("LLM Thinking: %s (runtime_id=%s, model=%s)", thinking_content[:200], ctx.runtime_id, ctx.model_config.model_name)

            response = LLMCompletionResponse(
                text="".join(response_text_parts),
                tool_calls=response_tool_calls,
                finish_reason=finish_reason,
                thinking=thinking_content,
                usage=usage,
            )

            if response.text or response.tool_calls:
                state.messages.append(
                    LLMMessage(
                        role="assistant",
                        content=response.text,
                        tool_calls=response.tool_calls,
                    )
                )
            
            # Finalize the assistant's text message
            yield from manager.finalize()

            if not response.tool_calls:
                summary = response.text or "Task execution completed."
                if state.cancel_requested:
                    state.phase = "cancelled"
                    state.error_message = state.error_message or "Runtime cancelled."
                    return True, False, state.error_message
                if finalize_on_complete:
                    state.phase = "completed"
                    state.summary = summary
                return False, True, summary

            restart_tool_calling = False
            for index, tool_call in enumerate(response.tool_calls):
                if state.cancel_requested:
                    state.phase = "cancelled"
                    state.error_message = state.error_message or "Runtime cancelled."
                    yield emit_failed(runtime_id=ctx.runtime_id, error=state.error_message)
                    return True, False, state.error_message
                handler = self._tools.get(tool_call.name)
                if handler is None:
                    state.messages.append(
                        LLMMessage(
                            role="tool",
                            content=f"Unsupported tool: {tool_call.name}",
                            tool_call_id=tool_call.id,
                            name=tool_call.name,
                        )
                    )
                    continue

                args = self._prepare_tool_args(handler, tool_call.arguments, state)
                command = str(args.get("command", "")).strip()
                working_directory = args.get("working_directory")

                if self._is_missing_command(handler, args):
                    state.messages.append(
                        LLMMessage(
                            role="tool",
                            content="Command tool call missing required 'command' argument. Please provide the exact command to execute.",
                            tool_call_id=tool_call.id,
                            name=tool_call.name,
                        )
                    )
                    continue

                if plan_step is None:
                    step = LoopRuntimeStep(
                        step_id=f"step-{uuid.uuid4().hex[:8]}",
                        title=command or tool_call.name,
                        reason="LLM requested tool execution",
                        risk_level="low",
                        working_directory=str(working_directory) if working_directory else None,
                        status="pending",
                    )
                    state.steps.append(step)
                    state.cursor = len(state.steps) - 1
                else:
                    step = plan_step
                    step.working_directory = str(working_directory) if working_directory else None

                action, reason = handler.needs_approval(args)
                args["approval_policy"] = action
                if action == "deny":
                    step.status = "failed"
                    unresolved_tool_failure = True
                    state.messages.append(
                        LLMMessage(
                            role="tool",
                            content=f"Command denied: {reason}",
                            tool_call_id=tool_call.id,
                            name=tool_call.name,
                        )
                    )
                    continue

                if action == "ask":
                    consistency: dict[str, Any] | None = None
                    if tool_call.name == "execute_command":
                        try:
                            consistency = self._build_approval_consistency(state, args, tool_call.id)
                        except ValueError as exc:
                            step.status = "failed"
                            unresolved_tool_failure = True
                            state.messages.append(
                                LLMMessage(
                                    role="tool",
                                    content=f"Command denied: {exc}",
                                    tool_call_id=tool_call.id,
                                    name=tool_call.name,
                                )
                            )
                            continue
                    step.reason = reason
                    step.risk_level = "high"
                    state.phase = "approving"
                    approval_token = secrets.token_urlsafe(32)
                    state.pending_tool_call_id = tool_call.id
                    state.pending_tool_name = tool_call.name
                    state.pending_tool_args = args
                    state.pending_approval_step_id = step.step_id
                    state.pending_approval_token = approval_token
                    state.pending_approval_token_hash = hashlib.sha256(approval_token.encode("utf-8")).hexdigest()
                    state.pending_approval_consistency = consistency

                    # Prevent HTTP 400 error by satisfying all remaining tool calls in the response
                    for remaining_tool_call in response.tool_calls[index + 1:]:
                        state.messages.append(
                            LLMMessage(
                                role="tool",
                                content="Cancelled because a previous command in the sequence required user approval.",
                                tool_call_id=remaining_tool_call.id,
                                name=remaining_tool_call.name,
                            )
                        )
                        
                    # Emit an 'ask' message for approval
                    yield from manager.begin_message(
                        message_type="ask",
                        ask_type="command",
                    )
                    yield from manager.finalize(
                        tool_call=self._build_tool_call_payload(
                            handler=handler,
                            tool_call_id=tool_call.id,
                            tool_name=tool_call.name,
                            args=args,
                            command=args.get("command", command),
                        ) | {"approvalToken": approval_token}
                    )
                    # Save the message ID so resume_with_approval can reuse it
                    state.pending_message_id = manager.last_finalized_id
                    return True, None, ""

                step.status = "running"
                state.phase = "executing"
                if state.cancel_requested:
                    state.phase = "cancelled"
                    state.error_message = state.error_message or "Runtime cancelled."
                    yield emit_failed(runtime_id=ctx.runtime_id, error=state.error_message)
                    return True, False, state.error_message

                # Emit a 'say' message for tool execution
                yield from manager.begin_message(message_type="say", say_type="tool_use")
                yield from manager.update(
                    tool_call=self._build_tool_call_payload(
                        handler=handler,
                        tool_call_id=tool_call.id,
                        tool_name=tool_call.name,
                        args=args,
                        command=args.get("command", command),
                    )
                )
                
                # handler.execute should yield output deltas to the manager
                ok, output = yield from handler.execute(state=state, step_id=step.step_id, args=args, manager=manager)

                step.status = "completed" if ok else "failed"
                tool_content = output if ok else f"Command Failed: {output}"
                step.output = tool_content
                unresolved_tool_failure = any(step.status == "failed" for step in state.steps)
                state.messages.append(
                    LLMMessage(
                        role="tool",
                        content=tool_content,
                        tool_call_id=tool_call.id,
                        name=tool_call.name,
                    )
                )
                yield from manager.finalize(exit_code=0 if ok else 1)

                if ok and tool_call.name == "request_terminal_session":
                    state.phase = "waiting_terminal_approval"
                    cancellation_content = (
                        "Paused because terminal access requires separate user confirmation. "
                        "Wait for the terminal decision before continuing."
                    )
                    for remaining_tool_call in response.tool_calls[index + 1:]:
                        state.messages.append(
                            LLMMessage(
                                role="tool",
                                content=cancellation_content,
                                tool_call_id=remaining_tool_call.id,
                                name=remaining_tool_call.name,
                            )
                        )
                    return True, None, ""

                if ok and tool_call.name == "load_skill":
                    cancellation_content = (
                        "Cancelled because load_skill changed the runtime instructions. "
                        "Re-evaluate before using more tools."
                    )
                    for remaining_tool_call in response.tool_calls[index + 1:]:
                        state.messages.append(
                            LLMMessage(
                                role="tool",
                                content=cancellation_content,
                                tool_call_id=remaining_tool_call.id,
                                name=remaining_tool_call.name,
                            )
                        )
                    manual_skill_prompt = build_manual_skill_system_prompt(ctx)
                    if manual_skill_prompt and not any(
                        message.role == "system" and message.content == manual_skill_prompt
                        for message in state.messages
                    ):
                        state.messages.append(LLMMessage(role="system", content=manual_skill_prompt))
                    restart_tool_calling = True
                    break

            if restart_tool_calling:
                continue

        return False, True, ""
