from dataclasses import dataclass, field
from typing import Any, Literal

from app.core.tool.schema import LLMToolCall, LLMToolChoice, LLMToolDefinition

LLMMessageRole = Literal["system", "user", "assistant", "tool"]
LLMCacheSegment = Literal[
    "system",
    "history",
    "summary",
    "current_user",
    "runtime_context",
    "assistant_response",
    "tool_result",
]
LLMCacheStatus = Literal["cacheable", "volatile", "inherit"]


@dataclass(frozen=True)
class LLMPromptCachePolicy:
    enabled: bool = False
    ttl: Literal["ephemeral", "one_hour"] = "ephemeral"
    breakpoint: Literal["last_cacheable_message"] = "last_cacheable_message"


@dataclass(frozen=True)
class LLMMessage:
    role: LLMMessageRole
    content: str
    tool_call_id: str | None = None
    name: str | None = None
    tool_calls: list[LLMToolCall] = field(default_factory=list)
    cache_segment: LLMCacheSegment | None = None
    cache_status: LLMCacheStatus = "inherit"


@dataclass(frozen=True)
class LLMCompletionRequest:
    messages: list[LLMMessage]
    tools: list[LLMToolDefinition] = field(default_factory=list)
    tool_choice: LLMToolChoice | None = None
    temperature: float | None = None
    max_tokens: int | None = None
    json_mode: bool = False
    json_schema: dict[str, Any] | None = None
    cache_policy: LLMPromptCachePolicy | None = None


@dataclass(frozen=True)
class LLMTokenUsage:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_creation_input_tokens: int = 0
    cache_read_input_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens + self.cache_creation_input_tokens + self.cache_read_input_tokens


@dataclass(frozen=True)
class LLMCompletionResponse:
    text: str = ""
    tool_calls: list[LLMToolCall] = field(default_factory=list)
    finish_reason: str | None = None
    thinking: str = ""
    usage: LLMTokenUsage | None = None


@dataclass(frozen=True)
class LLMCompletionChunk:
    delta: str = ""
    tool_calls: list[LLMToolCall] = field(default_factory=list)
    finish_reason: str | None = None
    tool_arguments_delta: str = ""
    thinking_delta: str = ""
    usage: LLMTokenUsage | None = None
    tool_call_preview: LLMToolCall | None = None
