import json
from jiter import from_json
from collections.abc import Iterator
from typing import Any, cast

from anthropic.types import JSONOutputFormatParam, TextBlockParam

from app.core.llm.base import LLMCompletionChunk, LLMCompletionRequest, LLMCompletionResponse
from app.core.llm.types import LLMTokenUsage
from app.core.tool import LLMToolCall
from app.shared.schemas import ModelConfig


class AnthropicLLMProvider:
    def __init__(self, client: Any = None):
        self._client = client


    def stream_complete(
        self,
        *,
        config: ModelConfig,
        request: LLMCompletionRequest,
    ) -> Iterator[LLMCompletionChunk]:
        # Consume raw events: compatible gateways may omit message_start.content,
        # which the SDK's accumulated message stream requires to be an array.
        tool_blocks: dict[int, dict[str, Any]] = {}
        finish_reason = None
        usage = None
        stopped = False
        with self._get_client(config).messages.create(
            stream=True,
            model=config.model_name,
            max_tokens=request.max_tokens if request.max_tokens is not None else config.max_tokens,
            temperature=request.temperature if request.temperature is not None else config.temperature,
            system=self._serialize_system_prompt(request),
            messages=cast(Any, self._serialize_messages(request)),
            tools=cast(Any, self._serialize_tools(request) or None),
            tool_choice=cast(Any, self._serialize_tool_choice(request)),
        ) as stream:
            for event in stream:
                if event.type == "message_start":
                    usage = self._extract_usage(event.message)
                elif event.type == "content_block_start":
                    block = event.content_block
                    if block.type == "tool_use":
                        tool_blocks[event.index] = {
                            "id": block.id, "name": block.name,
                            "input": getattr(block, "input", None) or {}, "json": "",
                        }
                    elif block.type == "text" and getattr(block, "text", None):
                        yield LLMCompletionChunk(delta=block.text)
                elif event.type == "content_block_delta":
                    delta = event.delta
                    if delta.type == "text_delta" and delta.text:
                        yield LLMCompletionChunk(delta=delta.text)
                    elif delta.type == "input_json_delta":
                        block = tool_blocks[event.index]
                        block["json"] += delta.partial_json
                        if block["name"] == "execute_command":
                            try:
                                arguments = from_json(block["json"].encode(), partial_mode="trailing-strings")
                                complete_fields = from_json(block["json"].encode(), partial_mode=True)
                            except ValueError:
                                continue
                            if isinstance(arguments, dict):
                                if not isinstance(complete_fields, dict) or "explanation" not in complete_fields:
                                    arguments.pop("explanation", None)
                                yield LLMCompletionChunk(tool_call_preview=LLMToolCall(
                                    id=block["id"], name=block["name"], arguments=arguments,
                                ))
                elif event.type == "message_delta":
                    finish_reason = getattr(event.delta, "stop_reason", None) or finish_reason
                    event_usage = getattr(event, "usage", None)
                    if event_usage is not None:
                        values = {
                            field: value for field in (
                                "input_tokens", "output_tokens", "cache_creation_input_tokens",
                                "cache_read_input_tokens",
                            ) if (value := getattr(event_usage, field, None)) is not None
                        }
                        usage = LLMTokenUsage(**{**(vars(usage) if usage else {}), **values})
                elif event.type == "message_stop":
                    stopped = True
                elif event.type == "error":
                    raise RuntimeError("AI gateway returned a streaming error")
        if not stopped:
            raise RuntimeError("AI gateway stream ended before message_stop")
        tool_calls = []
        for block in tool_blocks.values():
            arguments = json.loads(block["json"]) if block["json"] else block["input"]
            if not isinstance(arguments, dict):
                raise ValueError("AI tool arguments must be a JSON object")
            tool_calls.append(LLMToolCall(id=block["id"], name=block["name"], arguments=arguments))
        yield LLMCompletionChunk(tool_calls=tool_calls, finish_reason=finish_reason, usage=usage)

    def complete(
        self,
        *,
        config: ModelConfig,
        request: LLMCompletionRequest,
    ) -> LLMCompletionResponse:
        response = self._get_client(config).messages.create(
            model=config.model_name,
            max_tokens=request.max_tokens if request.max_tokens is not None else config.max_tokens,
            temperature=request.temperature if request.temperature is not None else config.temperature,
            system=self._serialize_system_prompt(request),
            messages=cast(Any, self._serialize_messages(request)),
            tools=cast(Any, self._serialize_tools(request) or None),
            tool_choice=cast(Any, self._serialize_tool_choice(request)),
        )
        text_parts: list[str] = []
        tool_calls: list[LLMToolCall] = []
        for block in getattr(response, "content", []) or []:
            block_type = getattr(block, "type", None)
            if block_type == "text":
                text = getattr(block, "text", None)
                if isinstance(text, str) and text:
                    text_parts.append(text)
            if block_type == "tool_use":
                tool_calls.append(
                    LLMToolCall(
                        id=getattr(block, "id", ""),
                        name=getattr(block, "name", ""),
                        arguments=getattr(block, "input", {}) if isinstance(getattr(block, "input", {}), dict) else {},
                    )
                )
        return LLMCompletionResponse(
            text="".join(text_parts),
            tool_calls=tool_calls,
            finish_reason=getattr(response, "stop_reason", None),
            usage=self._extract_usage(response),
        )

    def _extract_usage(self, response: Any) -> LLMTokenUsage | None:
        usage = getattr(response, "usage", None)
        if usage is None:
            return None
        return LLMTokenUsage(
            input_tokens=int(getattr(usage, "input_tokens", 0) or 0),
            output_tokens=int(getattr(usage, "output_tokens", 0) or 0),
            cache_creation_input_tokens=int(getattr(usage, "cache_creation_input_tokens", 0) or 0),
            cache_read_input_tokens=int(getattr(usage, "cache_read_input_tokens", 0) or 0),
        )

    def _get_client(self, config: ModelConfig):
        if self._client is not None:
            return self._client
        from anthropic import Anthropic

        self._client = Anthropic(
            api_key=config.api_key.get_secret_value(),
            base_url=config.base_url,
            timeout=config.timeout_seconds,
        )
        return self._client

    def _serialize_messages(self, request: LLMCompletionRequest) -> list[dict[str, Any]]:
        messages: list[dict[str, Any]] = []
        breakpoint_index = self._find_cache_breakpoint(request)
        for index, message in enumerate(request.messages):
            if message.role == "system":
                continue
            if message.role == "user":
                messages.append({"role": "user", "content": self._serialize_text_content(message.content, request, cacheable=index == breakpoint_index)})
                continue
            if message.role == "assistant":
                if not message.tool_calls:
                    messages.append({"role": "assistant", "content": self._serialize_text_content(message.content, request, cacheable=index == breakpoint_index)})
                    continue
                content_blocks: list[dict[str, Any]] = []
                if message.content:
                    text_block: dict[str, Any] = {"type": "text", "text": message.content}
                    if index == breakpoint_index:
                        text_block["cache_control"] = self._build_cache_control(request)
                    content_blocks.append(text_block)
                for tool_call in message.tool_calls:
                    content_blocks.append(
                        {
                            "type": "tool_use",
                            "id": tool_call.id,
                            "name": tool_call.name,
                            "input": tool_call.arguments,
                        }
                    )
                messages.append({"role": "assistant", "content": content_blocks})
                continue
            if message.role == "tool":
                messages.append(
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "tool_result",
                                "tool_use_id": message.tool_call_id or "",
                                "content": message.content,
                            }
                        ],
                    }
                )
        return messages

    def _serialize_system_prompt(self, request: LLMCompletionRequest) -> list[TextBlockParam] | str:
        system_entries = [(index, message.content) for index, message in enumerate(request.messages) if message.role == "system" and message.content]
        if not system_entries:
            return ""
        breakpoint_index = self._find_cache_breakpoint(request)
        blocks: list[TextBlockParam] = []
        for index, content in system_entries:
            block: dict[str, Any] = {"type": "text", "text": content}
            if index == breakpoint_index:
                block["cache_control"] = self._build_cache_control(request)
            blocks.append(cast(TextBlockParam, block))
        if len(blocks) == 1 and breakpoint_index != system_entries[0][0]:
            return system_entries[0][1]
        return blocks

    def _serialize_tools(self, request: LLMCompletionRequest) -> list[dict[str, Any]]:
        return [
            {
                "name": tool.name,
                "description": tool.description,
                "input_schema": tool.input_schema,
            }
            for tool in sorted(request.tools, key=lambda item: item.name)
        ]

    def _find_cache_breakpoint(self, request: LLMCompletionRequest) -> int | None:
        if request.cache_policy is None or not request.cache_policy.enabled:
            return None
        for index in range(len(request.messages) - 1, -1, -1):
            message = request.messages[index]
            if self._message_supports_cache_marker(message):
                return index
        return None

    def _message_supports_cache_marker(self, message) -> bool:
        if self._resolve_cache_status(message) != "cacheable":
            return False
        if message.role == "system":
            return bool(message.content)
        if message.role == "user":
            return bool(message.content)
        if message.role == "assistant":
            return bool(message.content)
        return False

    def _resolve_cache_status(self, message) -> str:
        if message.cache_status != "inherit":
            return message.cache_status
        defaults = {
            "system": "cacheable",
            "history": "cacheable",
            "summary": "cacheable",
            "current_user": "volatile",
            "runtime_context": "volatile",
            "assistant_response": "volatile",
            "tool_result": "volatile",
        }
        return defaults.get(message.cache_segment, "volatile")

    def _build_cache_control(self, request: LLMCompletionRequest) -> dict[str, Any]:
        ttl = request.cache_policy.ttl if request.cache_policy is not None else "ephemeral"
        if ttl == "one_hour":
            return {"type": "ephemeral", "ttl": "1h"}
        return {"type": "ephemeral"}

    def _serialize_text_content(self, content: str, request: LLMCompletionRequest, *, cacheable: bool) -> Any:
        if not cacheable:
            return content
        return [{"type": "text", "text": content, "cache_control": self._build_cache_control(request)}]

    def _serialize_tool_choice(self, request: LLMCompletionRequest) -> Any:
        if request.tool_choice is None:
            return None
        if request.tool_choice.name:
            return {"type": "tool", "name": request.tool_choice.name}
        if request.tool_choice.mode == "required":
            return {"type": "any"}
        if request.tool_choice.mode == "none":
            return None
        return {"type": "auto"}

    def _extract_tool_calls(self, blocks: list[Any]) -> list[LLMToolCall]:
        tool_calls: list[LLMToolCall] = []
        for block in blocks:
            if getattr(block, "type", None) != "tool_use":
                continue
            raw_input = getattr(block, "input", {})
            tool_calls.append(
                LLMToolCall(
                    id=getattr(block, "id", ""),
                    name=getattr(block, "name", ""),
                    arguments=raw_input if isinstance(raw_input, dict) else {},
                )
            )
        return tool_calls
