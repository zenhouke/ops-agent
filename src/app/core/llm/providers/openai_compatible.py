import json
import logging
from collections.abc import Iterator
from typing import Any, cast

logger = logging.getLogger(__name__)

from app.core.llm.base import LLMCompletionChunk, LLMCompletionRequest, LLMCompletionResponse
from app.core.llm.types import LLMTokenUsage
from app.core.llm.provider_presets import get_provider_preset
from app.core.tool import LLMToolCall
from app.shared.schemas import ModelConfig


class OpenAICompatibleLLMProvider:
    def __init__(self, client: Any = None):
        self._client = client

  
    def stream_complete(
        self,
        *,
        config: ModelConfig,
        request: LLMCompletionRequest,
    ) -> Iterator[LLMCompletionChunk]:
        params = self._build_completion_params(config=config, request=request, stream=True)
        self._log_request_summary(config=config, params=params, stream=True)
        try:
            response = self._get_client(config).chat.completions.create(**params)
            finish_reason: str | None = None
            usage: LLMTokenUsage | None = None
            tool_call_fragments: dict[int, dict[str, Any]] = {}
            for chunk in response:
                usage = self._extract_usage(chunk) or usage
                if not chunk.choices:
                    continue
                choice = chunk.choices[0]
                finish_reason = getattr(choice, "finish_reason", finish_reason)
                delta = getattr(choice, "delta", None)
                text = getattr(delta, "content", None)
                reasoning = getattr(delta, "reasoning_content", None)
                for tool_call in getattr(delta, "tool_calls", None) or []:
                    index = getattr(tool_call, "index", 0) or 0
                    current = tool_call_fragments.setdefault(index, {"id": "", "name": "", "arguments": ""})
                    tool_call_id = getattr(tool_call, "id", None)
                    if isinstance(tool_call_id, str) and tool_call_id:
                        current["id"] = tool_call_id
                    function = getattr(tool_call, "function", None)
                    function_name = getattr(function, "name", None)
                    if isinstance(function_name, str) and function_name:
                        current["name"] = function_name
                    function_arguments = getattr(function, "arguments", None)
                    if isinstance(function_arguments, str) and function_arguments:
                        current["arguments"] += function_arguments
                        yield LLMCompletionChunk(tool_arguments_delta=function_arguments)
                if isinstance(reasoning, str) and reasoning:
                    yield LLMCompletionChunk(thinking_delta=reasoning)
                if isinstance(text, str) and text:
                    yield LLMCompletionChunk(delta=text)
        except Exception as exc:
            if self._is_openai_api_error(exc):
                self._log_api_error(exc, config=config, params=params)
            raise
        yield LLMCompletionChunk(
            tool_calls=self._build_stream_tool_calls(tool_call_fragments),
            finish_reason=finish_reason,
            usage=usage,
        )

    def complete(
        self,
        *,
        config: ModelConfig,
        request: LLMCompletionRequest,
    ) -> LLMCompletionResponse:
        params = self._build_completion_params(config=config, request=request, stream=False)
        self._log_request_summary(config=config, params=params, stream=False)
        try:
            response = self._get_client(config).chat.completions.create(**params)
        except Exception as exc:
            if self._is_openai_api_error(exc):
                self._log_api_error(exc, config=config, params=params)
            raise
        choice = response.choices[0] if getattr(response, "choices", None) else None
        message = getattr(choice, "message", None)
        text = getattr(message, "content", "") or ""
        thinking = getattr(message, "reasoning_content", "") or ""
        tool_calls = self._parse_tool_calls(getattr(message, "tool_calls", None))
        finish_reason = getattr(choice, "finish_reason", None)
        if not text:
            logger.warning(
                "OpenAI-compatible completion returned empty content: finish_reason=%s refusal=%s tool_calls=%d message_type=%s",
                finish_reason,
                getattr(message, "refusal", None),
                len(tool_calls),
                getattr(message, "type", None),
            )
        return LLMCompletionResponse(text=text, tool_calls=tool_calls, finish_reason=finish_reason, thinking=thinking, usage=self._extract_usage(response))

    def _extract_usage(self, response: Any) -> LLMTokenUsage | None:
        usage = getattr(response, "usage", None)
        if usage is None:
            return None
        input_tokens = int(getattr(usage, "prompt_tokens", 0) or getattr(usage, "input_tokens", 0) or 0)
        output_tokens = int(getattr(usage, "completion_tokens", 0) or getattr(usage, "output_tokens", 0) or 0)
        return LLMTokenUsage(input_tokens=input_tokens, output_tokens=output_tokens)

    def _is_openai_api_error(self, exc: Exception) -> bool:
        return exc.__class__.__name__ == "APIError" and exc.__class__.__module__.startswith("openai")

    def _log_api_error(self, exc: Exception, *, config: ModelConfig, params: dict[str, Any]) -> None:
        logger.error(
            "OpenAI-compatible API request failed: status_code=%s body=%s model=%s provider=%s base_url=%s message_roles=%s tool_call_ids=%s",
            getattr(exc, "status_code", None),
            self._extract_error_body(exc),
            config.model_name,
            config.provider,
            config.base_url,
            self._message_roles(params),
            self._tool_call_ids(params),
        )

    def _log_request_summary(self, *, config: ModelConfig, params: dict[str, Any], stream: bool) -> None:
        logger.info(
            "OpenAI-compatible request summary: model=%s provider=%s base_url=%s stream=%s messages=%d roles=%s tools=%d tool_choice=%s response_format=%s extra_body_keys=%s tool_call_ids=%s message_summary=%s",
            config.model_name,
            config.provider,
            config.base_url,
            stream,
            self._message_count(params),
            self._message_roles(params),
            self._tools_count(params),
            self._tool_choice_summary(params),
            self._response_format_type(params),
            self._extra_body_keys(params),
            self._tool_call_ids(params),
            self._message_summary(params),
        )

    def _extract_error_body(self, exc: Exception) -> Any:
        body = getattr(exc, "body", None)
        if body is not None:
            return body
        response = getattr(exc, "response", None)
        if response is None:
            return None
        try:
            return response.json()
        except Exception:
            try:
                return response.text
            except Exception:
                return None

    def _message_count(self, params: dict[str, Any]) -> int:
        messages = params.get("messages")
        return len(messages) if isinstance(messages, list) else 0

    def _message_roles(self, params: dict[str, Any]) -> list[str]:
        messages = params.get("messages")
        if not isinstance(messages, list):
            return []
        return [str(message.get("role", "")) for message in messages if isinstance(message, dict)]

    def _message_summary(self, params: dict[str, Any]) -> list[dict[str, Any]]:
        messages = params.get("messages")
        if not isinstance(messages, list):
            return []
        summary: list[dict[str, Any]] = []
        for index, message in enumerate(messages):
            if not isinstance(message, dict):
                continue
            tool_calls = message.get("tool_calls")
            summary.append(
                {
                    "index": index,
                    "role": message.get("role"),
                    "has_content": bool(message.get("content")),
                    "tool_calls": len(tool_calls) if isinstance(tool_calls, list) else 0,
                    "tool_call_id": message.get("tool_call_id") if message.get("role") == "tool" else None,
                }
            )
        return summary

    def _tools_count(self, params: dict[str, Any]) -> int:
        tools = params.get("tools")
        return len(tools) if isinstance(tools, list) else 0

    def _tool_choice_summary(self, params: dict[str, Any]) -> Any:
        tool_choice = params.get("tool_choice")
        if isinstance(tool_choice, dict):
            function = tool_choice.get("function")
            return {"type": tool_choice.get("type"), "function": function.get("name") if isinstance(function, dict) else None}
        return tool_choice

    def _response_format_type(self, params: dict[str, Any]) -> Any:
        response_format = params.get("response_format")
        if isinstance(response_format, dict):
            return response_format.get("type")
        return response_format

    def _extra_body_keys(self, params: dict[str, Any]) -> list[str]:
        extra_body = params.get("extra_body")
        if not isinstance(extra_body, dict):
            return []
        return sorted(str(key) for key in extra_body)

    def _tool_call_ids(self, params: dict[str, Any]) -> dict[str, list[str]]:
        assistant_ids: list[str] = []
        tool_ids: list[str] = []
        messages = params.get("messages")
        if not isinstance(messages, list):
            return {"assistant": assistant_ids, "tool": tool_ids}
        for message in messages:
            if not isinstance(message, dict):
                continue
            if message.get("role") == "assistant":
                for tool_call in message.get("tool_calls") or []:
                    if isinstance(tool_call, dict):
                        tool_call_id = tool_call.get("id")
                        if tool_call_id:
                            assistant_ids.append(str(tool_call_id))
            if message.get("role") == "tool":
                tool_call_id = message.get("tool_call_id")
                if tool_call_id:
                    tool_ids.append(str(tool_call_id))
        return {"assistant": assistant_ids, "tool": tool_ids}

    def _build_completion_params(self, *, config: ModelConfig, request: LLMCompletionRequest, stream: bool) -> dict[str, Any]:
        preset = get_provider_preset(config.provider)
        max_tokens_param = preset.max_tokens_param if preset is not None else "max_tokens"
        params: dict[str, Any] = {
            "model": config.model_name,
            "temperature": request.temperature if request.temperature is not None else config.temperature,
            max_tokens_param: request.max_tokens if request.max_tokens is not None else config.max_tokens,
            "messages": cast(Any, [self._serialize_message(message) for message in request.messages]),
            "stream": stream,
        }
        if stream and config.provider_options.get("stream_include_usage", True):
            params["stream_options"] = {"include_usage": True}
        tools = self._serialize_tools(request)
        if tools:
            params["tools"] = cast(Any, tools)

        tool_choice = self._serialize_tool_choice(request)
        if tool_choice is not None:
            params["tool_choice"] = cast(Any, tool_choice)

        if request.json_schema is not None:
            params["response_format"] = {"type": "json_schema", "json_schema": request.json_schema}
        elif request.json_mode:
            params["response_format"] = {"type": "json_object"}
        extra_body = self._build_extra_body(config=config, request=request, preset=preset)
        if extra_body:
            params["extra_body"] = extra_body
        return params

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

    def _serialize_message(self, message):
        payload = {"role": message.role, "content": message.content}
        if message.tool_call_id:
            payload["tool_call_id"] = message.tool_call_id
        if message.name and message.role != "tool":
            payload["name"] = message.name
        if message.role == "assistant" and message.tool_calls:
            payload["tool_calls"] = [
                {
                    "id": tool_call.id,
                    "type": "function",
                    "function": {
                        "name": tool_call.name,
                        "arguments": tool_call.raw_arguments if isinstance(tool_call.raw_arguments, str) and tool_call.raw_arguments else json.dumps(tool_call.arguments),
                    },
                }
                for tool_call in message.tool_calls
            ]
        return payload

    def _serialize_tools(self, request: LLMCompletionRequest) -> list[dict[str, Any]]:
        return [
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.input_schema,
                },
            }
            for tool in request.tools
        ]

    def _serialize_tool_choice(self, request: LLMCompletionRequest) -> Any:
        if request.tool_choice is None:
            return None
        if request.tool_choice.name:
            return {"type": "function", "function": {"name": request.tool_choice.name}}
        return request.tool_choice.mode

    def _parse_tool_calls(self, tool_calls: Any) -> list[LLMToolCall]:
        parsed: list[LLMToolCall] = []
        for tool_call in tool_calls or []:
            function = getattr(tool_call, "function", None)
            raw_arguments = getattr(function, "arguments", None)
            arguments = self._safe_load_arguments(raw_arguments)
            parsed.append(
                LLMToolCall(
                    id=getattr(tool_call, "id", ""),
                    name=getattr(function, "name", ""),
                    arguments=arguments,
                    raw_arguments=raw_arguments if isinstance(raw_arguments, str) else None,
                )
            )
        return parsed

    def _safe_load_arguments(self, raw_arguments: Any) -> dict[str, Any]:
        if not isinstance(raw_arguments, str) or not raw_arguments:
            return {}
        try:
            value = json.loads(raw_arguments)
        except json.JSONDecodeError:
            return {}
        return value if isinstance(value, dict) else {}

    def _build_stream_tool_calls(self, fragments: dict[int, dict[str, Any]]) -> list[LLMToolCall]:
        parsed: list[LLMToolCall] = []
        for index in sorted(fragments):
            fragment = fragments[index]
            raw_arguments = fragment.get("arguments") if isinstance(fragment.get("arguments"), str) else None
            parsed.append(
                LLMToolCall(
                    id=str(fragment.get("id") or f"tool-call-{index}"),
                    name=str(fragment.get("name") or ""),
                    arguments=self._safe_load_arguments(raw_arguments),
                    raw_arguments=raw_arguments,
                )
            )
        return parsed

    def _build_extra_body(self, *, config: ModelConfig, request: LLMCompletionRequest, preset: Any) -> dict[str, Any] | None:
        extra_body: dict[str, Any] = {}
        if preset is not None and preset.default_extra_body:
            extra_body.update(preset.default_extra_body)

        options = config.provider_options or {}
        configured_extra_body = options.get("extra_body")
        if isinstance(configured_extra_body, dict):
            extra_body.update(configured_extra_body)

        if request.cache_policy is not None and request.cache_policy.enabled:
            cache_options = options.get("openai_compatible_prompt_cache")
            if isinstance(cache_options, dict):
                extra_body.update(cache_options)
                extra_body.setdefault("enabled", True)
                extra_body.setdefault("ttl", request.cache_policy.ttl)

        return extra_body or None
