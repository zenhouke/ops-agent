from __future__ import annotations

import hashlib
import logging
import secrets
import uuid
from collections.abc import Iterator
from typing import Any

logger = logging.getLogger(__name__)

from app.core.llm.types import LLMCompletionResponse, LLMMessage, LLMTokenUsage
from app.core.llm.factory import build_llm_provider
from app.core.loop.agent_loop_support import AgentLoopSupportMixin
from app.core.loop.request_builder import AgentLLMRequestBuilder
from app.core.loop.loop_events import (
    LoopEvent,
    emit_failed,
)
from app.core.loop.loop_state import LoopRuntimeStep, LoopState
from app.core.loop.message_manager import MessageManager
from app.core.loop.plan_execution import PlanExecutionMixin
from app.core.loop.prompts import (
    build_manual_skill_system_prompt,
)
from app.core.runtime.control import (
    RuntimeBudgetExceededError,
    RuntimeCancelledError,
    get_runtime_control,
)
from app.core.tool.handler import ToolHandler


EventCallback = Any


class AgentLoop(PlanExecutionMixin, AgentLoopSupportMixin):
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

    def _check_runtime_budget(self, state: LoopState) -> None:
        import time

        if state.cancel_requested:
            raise RuntimeCancelledError(state.cancellation_reason or "Runtime cancelled by operator.")
        if state.deadline_monotonic is not None and time.monotonic() >= state.deadline_monotonic:
            get_runtime_control().metrics.increment("budget_exceeded")
            raise RuntimeBudgetExceededError("Runtime deadline exceeded.")

    def _before_llm_call(self, state: LoopState) -> None:
        self._check_runtime_budget(state)
        if state.max_llm_calls and state.llm_calls >= state.max_llm_calls:
            get_runtime_control().metrics.increment("budget_exceeded")
            raise RuntimeBudgetExceededError("Maximum LLM call budget exceeded.")
        state.llm_calls += 1
        get_runtime_control().metrics.increment("llm_calls")

    def _before_tool_call(self, state: LoopState) -> None:
        self._check_runtime_budget(state)
        if state.max_tool_calls and state.tool_calls >= state.max_tool_calls:
            get_runtime_control().metrics.increment("budget_exceeded")
            raise RuntimeBudgetExceededError("Maximum tool call budget exceeded.")
        state.tool_calls += 1

    def run(self, state: LoopState) -> Iterator[LoopEvent]:
        manager = MessageManager(runtime_id=state.context.runtime_id)
        if state.context.mode == "plan":
            yield from self._run_plan_mode(state, manager=manager)
            return
        yield from self._tool_calling_loop(state, manager=manager)

    def resume_with_approval(self, state: LoopState, *, approved: bool) -> Iterator[LoopEvent]:
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
            self._before_tool_call(state)
            with get_runtime_control().tool_slot():
                ok, output = yield from handler.execute(
                    state=state,
                    step_id=current_step.step_id,
                    args=args,
                    manager=manager,
                )

        current_step.status = "completed" if ok else "failed"
        current_step.output = output if ok else f"Command Failed: {output}"
        self._append_pending_tool_result(state, content=current_step.output)
        self._clear_pending_approval(state)
        yield from manager.finalize(exit_code=0 if ok else 1)
        
        if state.context.mode == "plan":
            yield from self._run_plan_mode(state, manager=manager, continue_existing=True)
            return
        yield from self._tool_calling_loop(state, manager=manager)

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

        unresolved_tool_failure = any(step.status == "failed" for step in state.steps)

        while True:
            response_text_parts: list[str] = []
            response_thinking_parts: list[str] = []
            response_tool_calls = []
            finish_reason: str | None = None
            usage: LLMTokenUsage | None = None

            # Start a new assistant message for the LLM response
            yield from manager.begin_message(message_type="say", say_type="text")

            self._before_llm_call(state)
            first_chunk_logged = False
            for chunk in provider.stream_complete(
                config=ctx.model_config,
                request=self._request_builder.build_tool_calling_request(state=state, tools=tools),
            ):
                self._check_runtime_budget(state)
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
                if finalize_on_complete:
                    if unresolved_tool_failure:
                        state.phase = "failed"
                        state.error_message = summary
                        yield emit_failed(runtime_id=ctx.runtime_id, error=summary)
                        return False, False, summary
                    state.phase = "completed"
                    state.summary = summary
                return False, True, summary

            restart_tool_calling = False
            for index, tool_call in enumerate(response.tool_calls):
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
                
                self._before_tool_call(state)
                with get_runtime_control().tool_slot():
                    ok, output = yield from handler.execute(
                        state=state,
                        step_id=step.step_id,
                        args=args,
                        manager=manager,
                    )

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
