from __future__ import annotations

from dataclasses import asdict, dataclass, field
import hashlib
import json
from pathlib import Path
import re
from tempfile import NamedTemporaryFile
from typing import Literal, TypeAlias, cast

from app.core.llm.types import LLMMessage
from app.shared.schemas import ModelConfig

JsonValue: TypeAlias = str | int | float | bool | None | list["JsonValue"] | dict[str, "JsonValue"]
JsonObject: TypeAlias = dict[str, JsonValue]

ContextStatus = Literal["normal", "warning", "critical"]
FitStatus = Literal["fits", "compacted_to_fit", "overflow"]
SegmentKind = Literal["user", "assistant", "command", "approval", "error"]


@dataclass(slots=True)
class MessageSegment:
    kind: SegmentKind
    role: Literal["user", "assistant"]
    content: str
    event_index: int


@dataclass(slots=True)
class ContextSummary:
    user_goal: list[str] = field(default_factory=list)
    current_state: list[str] = field(default_factory=list)
    key_decisions: list[str] = field(default_factory=list)
    commands_and_results: list[str] = field(default_factory=list)
    failures_and_risks: list[str] = field(default_factory=list)
    open_tasks: list[str] = field(default_factory=list)
    constraints: list[str] = field(default_factory=list)


@dataclass(slots=True)
class ContextPreparationResult:
    prepared_messages: list[LLMMessage]
    estimated_input_tokens: int
    context_percent: int
    context_status: ContextStatus
    compaction_applied: bool
    summary_revision: str | None
    source_conversation_revision: str
    fit_status: FitStatus


@dataclass(slots=True)
class ContextMetadata:
    conversation_id: str
    context_percent: int
    context_status: ContextStatus
    estimated_input_tokens: int
    compaction_applied: bool
    summary_revision: str | None
    source_conversation_revision: str
    fit_status: FitStatus


class ContextManager:
    recent_segment_count = 12
    warning_threshold_percent = 70
    critical_threshold_percent = 90
    default_context_window_tokens = 32_000
    output_reserve_tokens = 4_000
    command_output_limit = 2_000
    summary_item_limit = 8

    def __init__(self, metadata_dir: Path) -> None:
        self._metadata_dir = Path(metadata_dir)
        self._metadata_dir.mkdir(parents=True, exist_ok=True)

    def estimate_text_tokens(self, text: str) -> int:
        if not text:
            return 0
        return max(1, (len(text) + 3) // 4)

    def estimate_messages_tokens(self, messages: list[LLMMessage]) -> int:
        return sum(self.estimate_text_tokens(message.content) + 4 for message in messages)

    def context_window_tokens(self, model_config: ModelConfig) -> int:
        model_name = model_config.model_name.lower()
        if "claude" in model_name:
            return 200_000
        if "gpt-4" in model_name or "gpt-5" in model_name:
            return 128_000
        return self.default_context_window_tokens

    def source_revision(self, events: list[JsonObject]) -> str:
        payload = json.dumps(events, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]

    def status_for_percent(self, context_percent: int) -> ContextStatus:
        if context_percent >= self.critical_threshold_percent:
            return "critical"
        if context_percent >= self.warning_threshold_percent:
            return "warning"
        return "normal"

    def metadata_path(self, conversation_id: str) -> Path:
        safe_id = re.sub(r"[^A-Za-z0-9_-]", "_", conversation_id) or "conversation"
        return self._metadata_dir / f"{safe_id}.context.json"

    def prepare_context(self, conversation_id: str, events: list[JsonObject], model_config: ModelConfig) -> ContextPreparationResult:
        source_revision = self.source_revision(events)
        segments = self.normalize_events(events)
        if segments and segments[-1].role == "user":
            segments = segments[:-1]

        raw_messages = self.messages_from_segments(segments)
        raw_tokens = self.estimate_messages_tokens(raw_messages)
        raw_percent = self.context_percent_for_tokens(raw_tokens, model_config)
        raw_fits = self.fits_context_window(raw_tokens, model_config)

        prepared_messages = raw_messages
        estimated_tokens = raw_tokens
        context_percent = raw_percent
        compaction_applied = False
        summary_revision: str | None = None
        fit_status: FitStatus = "fits" if raw_fits else "overflow"

        if raw_percent >= self.warning_threshold_percent and len(segments) > self.recent_segment_count:
            compacted_messages, summary_revision = self.compact_segments(segments)
            compacted_tokens = self.estimate_messages_tokens(compacted_messages)
            compacted_percent = self.context_percent_for_tokens(compacted_tokens, model_config)
            prepared_messages = compacted_messages
            estimated_tokens = compacted_tokens
            context_percent = compacted_percent
            compaction_applied = True
            fit_status = "compacted_to_fit" if self.fits_context_window(compacted_tokens, model_config) else "overflow"

        result = ContextPreparationResult(
            prepared_messages=prepared_messages,
            estimated_input_tokens=estimated_tokens,
            context_percent=context_percent,
            context_status=self.status_for_percent(context_percent),
            compaction_applied=compaction_applied,
            summary_revision=summary_revision,
            source_conversation_revision=source_revision,
            fit_status=fit_status,
        )
        self.write_metadata(conversation_id, result)
        return result

    def context_percent_for_tokens(self, estimated_input_tokens: int, model_config: ModelConfig) -> int:
        available_tokens = max(1, self.context_window_tokens(model_config) - self.output_reserve_tokens)
        return min(100, max(0, round(estimated_input_tokens * 100 / available_tokens)))

    def fits_context_window(self, estimated_input_tokens: int, model_config: ModelConfig) -> bool:
        available_tokens = max(1, self.context_window_tokens(model_config) - self.output_reserve_tokens)
        return estimated_input_tokens <= available_tokens

    def normalize_events(self, events: list[JsonObject]) -> list[MessageSegment]:
        segments: list[MessageSegment] = []
        for event_index, event in enumerate(events):
            kind = str(event.get("kind") or "")
            event_type = str(event.get("type") or "")

            if kind == "user":
                self._append_segment(segments, "user", "user", self._string_value(event.get("text")), event_index)
                continue

            if kind == "message" and event_type == "say":
                self._normalize_message_event(segments, event, event_index)
                continue

            if kind in {"approval_required", "approval_decision", "approval_granted", "approval_rejected"}:
                self._normalize_approval_event(segments, event, event_index)
                continue

            if kind in {"command_start", "command_end", "execution_started", "execution_completed"}:
                self._normalize_command_event(segments, event, event_index)
                continue

            if kind in {"command_chunk", "execution_output"}:
                self._append_segment(segments, "command", "assistant", self._string_value(event.get("text"))[: self.command_output_limit], event_index)
                continue

            if kind == "final":
                self._append_segment(segments, "assistant", "assistant", self._string_value(event.get("text")), event_index)
                continue

            if kind == "delta":
                self._append_segment(segments, "assistant", "assistant", self._string_value(event.get("text")), event_index)
                continue

            if kind == "error":
                text = self._string_value(event.get("text"))
                if text:
                    self._append_segment(segments, "error", "assistant", f"[Error: {text}]", event_index)

        return segments

    def messages_from_segments(self, segments: list[MessageSegment]) -> list[LLMMessage]:
        messages: list[LLMMessage] = []
        for segment in segments:
            if segment.content:
                messages.append(LLMMessage(role=segment.role, content=segment.content))
        return messages

    def compact_segments(self, segments: list[MessageSegment]) -> tuple[list[LLMMessage], str]:
        older_segments = segments[:-self.recent_segment_count]
        recent_segments = segments[-self.recent_segment_count:]
        summary = self.summarize_segments(older_segments)
        summary_content = self.format_summary(summary)
        summary_revision = hashlib.sha256(summary_content.encode("utf-8")).hexdigest()[:16]
        return [LLMMessage(role="assistant", content=summary_content), *self.messages_from_segments(recent_segments)], summary_revision

    def summarize_segments(self, segments: list[MessageSegment]) -> ContextSummary:
        summary = ContextSummary()
        for segment in segments:
            content = self._compact_line(segment.content)
            if not content:
                continue
            if segment.kind == "user":
                self._append_limited(summary.user_goal, content)
                self._append_limited(summary.open_tasks, content)
            elif segment.kind == "command":
                self._append_limited(summary.commands_and_results, content)
            elif segment.kind == "approval":
                self._append_limited(summary.key_decisions, content)
                self._append_limited(summary.constraints, content)
            elif segment.kind == "error":
                self._append_limited(summary.failures_and_risks, content)
            else:
                self._append_limited(summary.current_state, content)
        return summary

    def format_summary(self, summary: ContextSummary) -> str:
        sections = [
            ("User goal", summary.user_goal),
            ("Current state", summary.current_state),
            ("Key decisions", summary.key_decisions),
            ("Commands and results", summary.commands_and_results),
            ("Failures and risks", summary.failures_and_risks),
            ("Open tasks", summary.open_tasks),
            ("Constraints", summary.constraints),
        ]
        lines = ["Earlier conversation summary:"]
        for title, items in sections:
            if not items:
                continue
            lines.append(f"{title}:")
            lines.extend(f"- {item}" for item in items)
        return "\n".join(lines)

    def write_metadata(self, conversation_id: str, result: ContextPreparationResult) -> None:
        metadata = ContextMetadata(
            conversation_id=conversation_id,
            context_percent=result.context_percent,
            context_status=result.context_status,
            estimated_input_tokens=result.estimated_input_tokens,
            compaction_applied=result.compaction_applied,
            summary_revision=result.summary_revision,
            source_conversation_revision=result.source_conversation_revision,
            fit_status=result.fit_status,
        )
        path = self.metadata_path(conversation_id)
        with NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as tmp:
            json.dump(asdict(metadata), tmp, ensure_ascii=False, indent=2)
            tmp.write("\n")
            tmp_path = Path(tmp.name)
        tmp_path.replace(path)

    def read_metadata(self, conversation_id: str) -> ContextMetadata | None:
        path = self.metadata_path(conversation_id)
        if not path.exists():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        return ContextMetadata(
            conversation_id=str(data.get("conversation_id") or conversation_id),
            context_percent=int(data.get("context_percent") or 0),
            context_status=cast(ContextStatus, data.get("context_status") or "normal"),
            estimated_input_tokens=int(data.get("estimated_input_tokens") or 0),
            compaction_applied=bool(data.get("compaction_applied")),
            summary_revision=cast(str | None, data.get("summary_revision")),
            source_conversation_revision=str(data.get("source_conversation_revision") or ""),
            fit_status=cast(FitStatus, data.get("fit_status") or "fits"),
        )

    def _normalize_message_event(self, segments: list[MessageSegment], event: JsonObject, event_index: int) -> None:
        if bool(event.get("partial")):
            return
        say_type = str(event.get("say") or "")
        if say_type == "text":
            self._append_segment(segments, "assistant", "assistant", self._string_value(event.get("text")), event_index)
            return
        if say_type == "error":
            text = self._string_value(event.get("text"))
            if text:
                self._append_segment(segments, "error", "assistant", f"[Error: {text}]", event_index)
            return
        if say_type != "tool_use":
            return

        tool_call = event.get("toolCall") or event.get("tool_call") or {}
        tool_call = tool_call if isinstance(tool_call, dict) else {}
        command = self._string_value(tool_call.get("command") or tool_call.get("name"))
        output = self._string_value(event.get("toolOutput") or event.get("tool_output"))
        exit_code = event.get("exitCode") if event.get("exitCode") is not None else event.get("exit_code")
        parts: list[str] = []
        if command:
            parts.append(f"[Executed: {command}]")
        if output:
            parts.append(f"Output:\n{self._truncate(output)}")
        if exit_code is not None:
            parts.append(f"Exit code: {exit_code}")
        self._append_segment(segments, "command", "assistant", "\n".join(parts), event_index)

    def _normalize_approval_event(self, segments: list[MessageSegment], event: JsonObject, event_index: int) -> None:
        kind = self._string_value(event.get("kind"))
        command = self._string_value(event.get("command"))
        status = self._string_value(event.get("status"))
        reason = self._string_value(event.get("reason"))
        text = self._string_value(event.get("text"))
        content = " | ".join(part for part in [kind, status, command, reason, text] if part)
        self._append_segment(segments, "approval", "assistant", content, event_index)

    def _normalize_command_event(self, segments: list[MessageSegment], event: JsonObject, event_index: int) -> None:
        kind = self._string_value(event.get("kind"))
        command = self._string_value(event.get("command"))
        title = self._string_value(event.get("title"))
        exit_code = event.get("exitCode") if event.get("exitCode") is not None else event.get("exit_code")
        summary = self._string_value(event.get("summary"))
        parts = [part for part in [kind, title, command, summary] if part]
        if exit_code is not None:
            parts.append(f"exit_code={exit_code}")
        self._append_segment(segments, "command", "assistant", " | ".join(parts), event_index)

    def _append_segment(self, segments: list[MessageSegment], kind: SegmentKind, role: Literal["user", "assistant"], content: str, event_index: int) -> None:
        content = content.strip()
        if content:
            segments.append(MessageSegment(kind=kind, role=role, content=content, event_index=event_index))

    def _append_limited(self, items: list[str], item: str) -> None:
        if item in items:
            return
        if len(items) < self.summary_item_limit:
            items.append(item)

    def _compact_line(self, text: str) -> str:
        return " ".join(text.strip().split())[:500]

    def _truncate(self, text: str) -> str:
        return text[: self.command_output_limit] + ("..." if len(text) > self.command_output_limit else "")

    def _string_value(self, value: JsonValue | object) -> str:
        if value is None:
            return ""
        if isinstance(value, str):
            return value.strip()
        return str(value).strip()
