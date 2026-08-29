from __future__ import annotations

from dataclasses import replace

from app.core.llm.types import LLMCompletionRequest, LLMMessage, LLMPromptCachePolicy
from app.core.loop.loop_state import LoopContext, LoopState
from app.core.loop.prompts import (
    build_manual_skill_system_prompt,
    build_tool_calling_system_prompt,
)
from app.core.tool.schema import LLMToolDefinition


class AgentLLMRequestBuilder:
    MAX_STATE_MESSAGES = 40
    KEEP_RECENT_MESSAGES = 18
    MAX_STATE_MESSAGE_CHARS = 80_000
    MAX_MESSAGE_CONTENT_CHARS = 8_000
    MAX_COMPACTED_SUMMARY_CHARS = 12_000

    def build_tool_calling_request(self, *, state: LoopState, tools: list[LLMToolDefinition]) -> LLMCompletionRequest:
        messages = self._annotate_state_messages(state)
        if messages and messages[0].role == "system":
            messages[0] = replace(messages[0], content=build_tool_calling_system_prompt(state.context))
        sorted_tools = sorted(tools, key=lambda tool: tool.name)
        return LLMCompletionRequest(
            messages=messages,
            tools=sorted_tools,
            json_mode=False,
            cache_policy=self._cache_policy(state.context),
        )

    def build_initial_tool_calling_messages(self, *, state: LoopState) -> list[LLMMessage]:
        ctx = state.context
        messages = [self._make_system_message(build_tool_calling_system_prompt(ctx))]
        manual_skill_prompt = build_manual_skill_system_prompt(ctx)
        if manual_skill_prompt:
            messages.append(self._make_system_message(manual_skill_prompt))
        messages.extend(self._annotate_history_messages(ctx.conversation_history))
        messages.append(
            LLMMessage(
                role="user",
                content=ctx.user_prompt,
                cache_segment="current_user",
                cache_status="volatile",
            )
        )
        return messages

    def compact_state_messages(self, state: LoopState) -> None:
        if state.phase == "approving" or state.pending_tool_call_id:
            return

        total_chars = sum(len(message.content) for message in state.messages)
        needs_compaction = len(state.messages) > self.MAX_STATE_MESSAGES or total_chars > self.MAX_STATE_MESSAGE_CHARS
        if not needs_compaction:
            state.messages = [self._truncate_message(message) for message in state.messages]
            return

        system_messages = [message for message in state.messages if message.role == "system"]
        non_system_messages = [
            message
            for message in state.messages
            if message.role != "system" and not self._is_compacted_summary_message(message)
        ]
        split_index = max(0, len(non_system_messages) - self.KEEP_RECENT_MESSAGES)
        while split_index > 0 and non_system_messages[split_index].role == "tool":
            split_index -= 1
        recent_messages = non_system_messages[split_index:]
        older_messages = non_system_messages[:split_index]
        summary = self._build_compacted_summary(existing_summary=state.summary, messages=older_messages)
        state.summary = summary

        compacted_messages = [self._truncate_message(message) for message in system_messages]
        if summary:
            compacted_messages.append(
                LLMMessage(
                    role="user",
                    content=f"Earlier runtime context summary:\n{summary}",
                    cache_segment="summary",
                    cache_status="cacheable",
                )
            )
        compacted_messages.extend(self._truncate_message(message) for message in recent_messages)
        state.messages = compacted_messages

    def _build_compacted_summary(self, *, existing_summary: str | None, messages: list[LLMMessage]) -> str:
        lines: list[str] = []
        if existing_summary:
            lines.append(existing_summary)
        for message in messages:
            label = message.role
            if message.name:
                label = f"{label}:{message.name}"
            content = self._truncate_text(message.content, 1200)
            if message.tool_call_id:
                lines.append(f"[{label} tool_call_id={message.tool_call_id}] {content}")
            else:
                lines.append(f"[{label}] {content}")
        return self._truncate_text("\n".join(line for line in lines if line), self.MAX_COMPACTED_SUMMARY_CHARS)

    def _is_compacted_summary_message(self, message: LLMMessage) -> bool:
        return message.cache_segment == "summary" and message.content.startswith("Earlier runtime context summary:\n")

    def _truncate_message(self, message: LLMMessage) -> LLMMessage:
        truncated = self._truncate_text(message.content, self.MAX_MESSAGE_CONTENT_CHARS)
        if truncated == message.content:
            return message
        return replace(message, content=truncated)

    def _truncate_text(self, text: str, max_chars: int) -> str:
        if len(text) <= max_chars:
            return text
        head_chars = min(2000, max_chars // 4)
        tail_chars = max(0, max_chars - head_chars)
        return f"{text[:head_chars]}\n...[truncated {len(text) - max_chars} chars]...\n{text[-tail_chars:]}"

    def _annotate_state_messages(self, state: LoopState) -> list[LLMMessage]:
        self.compact_state_messages(state)
        messages: list[LLMMessage] = []
        last_user_index = max((index for index, message in enumerate(state.messages) if message.role == "user"), default=-1)
        for index, message in enumerate(state.messages):
            if message.role == "system":
                messages.append(self._apply_cache_metadata(message, segment="system", status="cacheable"))
                continue
            if index == last_user_index and not self._has_followup_content(state.messages, index):
                messages.append(self._apply_cache_metadata(message, segment="current_user", status="volatile"))
                continue
            messages.append(self._apply_cache_metadata(message, segment="history", status="cacheable"))
        return messages

    def _annotate_history_messages(self, messages: list[LLMMessage]) -> list[LLMMessage]:
        return [self._apply_cache_metadata(message, segment="history", status="cacheable") for message in messages]

    def _has_followup_content(self, messages: list[LLMMessage], user_index: int) -> bool:
        return any(message.role in {"assistant", "tool"} for message in messages[user_index + 1 :])

    def _make_system_message(self, content: str) -> LLMMessage:
        return LLMMessage(role="system", content=content, cache_segment="system", cache_status="cacheable")

    def _cache_policy(self, ctx: LoopContext) -> LLMPromptCachePolicy:
        return LLMPromptCachePolicy(
            enabled=ctx.model_config.prompt_cache_enabled,
            ttl=ctx.model_config.prompt_cache_ttl,
        )

    def _apply_cache_metadata(self, message: LLMMessage, *, segment: str, status: str) -> LLMMessage:
        return replace(message, cache_segment=segment, cache_status=status)
