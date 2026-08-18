import json
from collections.abc import Iterator
from typing import Any, cast

from app.core.llm.base import LLMCompletionChunk, LLMCompletionRequest, LLMCompletionResponse
from app.core.llm.types import LLMTokenUsage
from app.core.tool import LLMToolCall
from app.shared.schemas import ModelConfig


class OpenAIResponsesLLMProvider:
    def __init__(self, client: Any = None):
        self._client = client

    def stream_complete(
        self,
        *,
        config: ModelConfig,
        request: LLMCompletionRequest,
    ) -> Iterator[LLMCompletionChunk]:
        stream = self._get_client(config).responses.create(**self._build_response_params(config=config, request=request, stream=True))
        finish_reason: str | None = None
        usage: LLMTokenUsage | None = None
        tool_fragments: dict[str, dict[str, Any]] = {}
        current_tool_item_id: str | None = None
        output_text_parts: list[str] = []
        thinking_parts: list[str] = []

        for event in stream:
            event_type = getattr(event, "type", "")
            if event_type == "response.output_text.delta":
                delta = getattr(event, "delta", "")
                if isinstance(delta, str) and delta:
                    output_text_parts.append(delta)
                    yield LLMCompletionChunk(delta=delta)
                continue
            if event_type in {
                "response.reasoning.delta",
                "response.reasoning_text.delta",
                "response.reasoning_summary_text.delta",
            }:
                delta = getattr(event, "delta", "")
                if isinstance(delta, str) and delta:
                    thinking_parts.append(delta)
                    yield LLMCompletionChunk(thinking_delta=delta)
                continue
            if event_type == "response.function_call_arguments.delta":
                item_id = self._event_item_id(event) or current_tool_item_id or "tool-call-0"
                fragment = self._get_tool_fragment(tool_fragments, item_id)
                delta = getattr(event, "delta", "")
                if isinstance(delta, str) and delta:
                    fragment["arguments"] += delta
                    yield LLMCompletionChunk(tool_arguments_delta=delta)
                continue
            if event_type == "response.output_item.added":
                item = getattr(event, "item", None)
                item_id = self._event_item_id(event) or self._event_item_id(item) or f"tool-call-{len(tool_fragments)}"
                if self._merge_response_tool_item(tool_fragments, item_id, item):
                    current_tool_item_id = item_id
                continue
            if event_type in {"response.output_item.done", "response.function_call_arguments.done"}:
                item = getattr(event, "item", None)
                item_id = self._event_item_id(event) or self._event_item_id(item) or current_tool_item_id or f"tool-call-{len(tool_fragments)}"
                self._merge_response_tool_item(tool_fragments, item_id, item)
                continue
            if event_type == "response.completed":
                response = getattr(event, "response", None)
                finish_reason = getattr(response, "status", None) or finish_reason
                usage = self._extract_usage(response) or usage
                self._merge_response_output(tool_fragments, response)
                completed_text = getattr(response, "output_text", "") or ""
                streamed_text = "".join(output_text_parts)
                if isinstance(completed_text, str) and completed_text.startswith(streamed_text):
                    remaining_text = completed_text[len(streamed_text):]
                    if remaining_text:
                        output_text_parts.append(remaining_text)
                        yield LLMCompletionChunk(delta=remaining_text)
                completed_thinking = self._extract_reasoning_text(response)
                streamed_thinking = "".join(thinking_parts)
                if completed_thinking.startswith(streamed_thinking):
                    remaining_thinking = completed_thinking[len(streamed_thinking):]
                    if remaining_thinking:
                        thinking_parts.append(remaining_thinking)
                        yield LLMCompletionChunk(thinking_delta=remaining_thinking)
                continue
            if event_type == "response.failed":
                response = getattr(event, "response", None)
                error = getattr(response, "error", None) or getattr(event, "error", None)
                message = getattr(error, "message", None) or str(error or "OpenAI Responses request failed")
                raise RuntimeError(message)

        yield LLMCompletionChunk(tool_calls=self._build_tool_calls(tool_fragments), finish_reason=finish_reason, usage=usage)

    def complete(
        self,
        *,
        config: ModelConfig,
        request: LLMCompletionRequest,
    ) -> LLMCompletionResponse:
        response = self._get_client(config).responses.create(**self._build_response_params(config=config, request=request, stream=False))
        return LLMCompletionResponse(
            text=getattr(response, "output_text", "") or "",
            tool_calls=self._extract_tool_calls(response),
            finish_reason=getattr(response, "status", None),
            thinking=self._extract_reasoning_text(response),
            usage=self._extract_usage(response),
        )

    def _extract_usage(self, response: Any) -> LLMTokenUsage | None:
        usage = getattr(response, "usage", None)
        if usage is None:
            return None
        input_tokens = int(getattr(usage, "input_tokens", 0) or 0)
        output_tokens = int(getattr(usage, "output_tokens", 0) or 0)
        return LLMTokenUsage(input_tokens=input_tokens, output_tokens=output_tokens)

    def _get_client(self, config: ModelConfig):
        if self._client is not None:
            return self._client
        from openai import OpenAI

        self._client = OpenAI(
            api_key=config.api_key.get_secret_value(),
            base_url=config.base_url,
            timeout=config.timeout_seconds,
        )
        return self._client

    def _build_response_params(self, *, config: ModelConfig, request: LLMCompletionRequest, stream: bool) -> dict[str, Any]:
        params: dict[str, Any] = {
            "model": config.model_name,
            "input": self._serialize_input(request),
            "stream": stream,
        }
        temperature = request.temperature if request.temperature is not None else config.temperature
        if temperature is not None:
            params["temperature"] = temperature
        max_tokens = request.max_tokens if request.max_tokens is not None else config.max_tokens
        if max_tokens is not None:
            params["max_output_tokens"] = max_tokens

        instructions = self._serialize_instructions(request)
        if instructions:
            params["instructions"] = instructions

        tools = self._serialize_tools(request)
        if tools:
            params["tools"] = cast(Any, tools)

        tool_choice = self._serialize_tool_choice(request)
        if tool_choice is not None:
            params["tool_choice"] = cast(Any, tool_choice)

        text_format = self._serialize_text_format(request)
        if text_format is not None:
            params["text"] = {"format": text_format}

        options = config.provider_options or {}
        for key in (
            "background",
            "include",
            "metadata",
            "parallel_tool_calls",
            "previous_response_id",
            "prompt",
            "reasoning",
            "service_tier",
            "store",
            "truncation",
            "user",
        ):
            if key in options:
                params[key] = options[key]

        hosted_tools = options.get("openai_responses_tools")
        if isinstance(hosted_tools, list):
            params.setdefault("tools", [])
            params["tools"].extend(hosted_tools)

        extra_body = options.get("extra_body")
        if isinstance(extra_body, dict):
            params["extra_body"] = extra_body

        return params

    def _serialize_instructions(self, request: LLMCompletionRequest) -> str:
        return "\n\n".join(message.content for message in request.messages if message.role == "system" and message.content)

    def _serialize_input(self, request: LLMCompletionRequest) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for message in request.messages:
            if message.role == "system":
                continue
            if message.role == "tool":
                items.append({"type": "function_call_output", "call_id": message.tool_call_id or "", "output": message.content})
                continue
            if message.role == "assistant" and message.tool_calls:
                if message.content:
                    items.append({"role": "assistant", "content": message.content})
                for tool_call in message.tool_calls:
                    raw_arguments = tool_call.raw_arguments if isinstance(tool_call.raw_arguments, str) else json.dumps(tool_call.arguments)
                    items.append(
                        {
                            "type": "function_call",
                            "call_id": tool_call.id,
                            "name": tool_call.name,
                            "arguments": raw_arguments,
                        }
                    )
                continue
            role = "assistant" if message.role == "assistant" else "user"
            items.append({"role": role, "content": message.content})
        return items

    def _serialize_tools(self, request: LLMCompletionRequest) -> list[dict[str, Any]]:
        return [
            {
                "type": "function",
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.input_schema,
            }
            for tool in request.tools
        ]

    def _serialize_tool_choice(self, request: LLMCompletionRequest) -> Any:
        if request.tool_choice is None:
            return None
        if request.tool_choice.name:
            return {"type": "function", "name": request.tool_choice.name}
        return request.tool_choice.mode

    def _serialize_text_format(self, request: LLMCompletionRequest) -> dict[str, Any] | None:
        if request.json_schema is not None:
            return {"type": "json_schema", **request.json_schema}
        if request.json_mode:
            return {"type": "json_object"}
        return None

    def _extract_tool_calls(self, response: Any) -> list[LLMToolCall]:
        fragments: dict[str, dict[str, Any]] = {}
        self._merge_response_output(fragments, response)
        return self._build_tool_calls(fragments)

    def _merge_response_output(self, fragments: dict[str, dict[str, Any]], response: Any) -> None:
        for index, item in enumerate(getattr(response, "output", []) or []):
            item_id = self._event_item_id(item) or f"tool-call-{index}"
            self._merge_response_tool_item(fragments, item_id, item)

    def _merge_response_tool_item(self, fragments: dict[str, dict[str, Any]], item_id: str, item: Any) -> bool:
        if item is None or getattr(item, "type", None) != "function_call":
            return False
        fragment = self._get_tool_fragment(fragments, item_id)
        call_id = getattr(item, "call_id", None) or getattr(item, "id", None)
        if isinstance(call_id, str) and call_id:
            fragment["id"] = call_id
        name = getattr(item, "name", None)
        if isinstance(name, str) and name:
            fragment["name"] = name
        arguments = getattr(item, "arguments", None)
        if isinstance(arguments, str):
            fragment["arguments"] = arguments
        return True

    def _event_item_id(self, value: Any) -> str | None:
        for name in ("item_id", "id", "call_id"):
            item_id = getattr(value, name, None)
            if item_id is not None:
                return str(item_id)
        return None

    def _get_tool_fragment(self, fragments: dict[str, dict[str, Any]], item_id: str) -> dict[str, Any]:
        if item_id in fragments:
            return fragments[item_id]
        for fragment in fragments.values():
            if fragment.get("id") == item_id:
                return fragment
        fragments[item_id] = {"id": item_id, "name": "", "arguments": ""}
        return fragments[item_id]

    def _build_tool_calls(self, fragments: dict[str, dict[str, Any]]) -> list[LLMToolCall]:
        tool_calls: list[LLMToolCall] = []
        for item_id in sorted(fragments):
            fragment = fragments[item_id]
            raw_arguments = fragment.get("arguments") if isinstance(fragment.get("arguments"), str) else ""
            tool_calls.append(
                LLMToolCall(
                    id=str(fragment.get("id") or item_id),
                    name=str(fragment.get("name") or ""),
                    arguments=self._safe_load_arguments(raw_arguments),
                    raw_arguments=raw_arguments,
                )
            )
        return tool_calls

    def _safe_load_arguments(self, raw_arguments: Any) -> dict[str, Any]:
        if not isinstance(raw_arguments, str) or not raw_arguments:
            return {}
        try:
            value = json.loads(raw_arguments)
        except json.JSONDecodeError:
            return {}
        return value if isinstance(value, dict) else {}

    def _extract_reasoning_text(self, response: Any) -> str:
        text_parts: list[str] = []
        for item in getattr(response, "output", []) or []:
            if getattr(item, "type", None) != "reasoning":
                continue
            for summary in getattr(item, "summary", []) or []:
                text = getattr(summary, "text", None)
                if isinstance(text, str) and text:
                    text_parts.append(text)
        return "".join(text_parts)
