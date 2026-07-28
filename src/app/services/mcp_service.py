from __future__ import annotations

import json
import os
import re
import threading
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any

import anyio
from mcp import ClientSession
from mcp.client.sse import sse_client
from mcp.client.stdio import StdioServerParameters, stdio_client

from app.core.runtime.control import get_runtime_control
from app.services.mcp_config_store import (
    DiscoveredMCPTool,
    MCPConfigStore,
    MCPServerConfig,
    MCPToolConfig,
)


@dataclass(frozen=True)
class MCPCallResult:
    ok: bool
    text_output: str = ""
    structured_output: Any | None = None
    raw_meta: dict[str, Any] = field(default_factory=dict)
    error_message: str = ""


class McpService:
    def __init__(self, store: MCPConfigStore | None = None) -> None:
        self._store = store or MCPConfigStore()
        limits = get_runtime_control().limits
        self._executor = ThreadPoolExecutor(max_workers=max(2, limits.max_concurrent_tools))
        self._capacity_lock = threading.Lock()
        self._server_capacity: dict[str, threading.BoundedSemaphore] = {}
        self._per_server_limit = limits.max_mcp_calls_per_server

    def close(self) -> None:
        self._executor.shutdown(wait=False, cancel_futures=True)

    @property
    def store(self) -> MCPConfigStore:
        return self._store

    def list_servers(self) -> list[MCPServerConfig]:
        return self._store.list_servers()

    def build_tool_handlers(self) -> list[Any]:
        from app.core.tool.mcp import McpToolHandler

        return [
            McpToolHandler(service=self, server=server, tool=tool)
            for server, tool in self._store.list_injectable_tools()
        ]

    def refresh_server(self, server_id: str) -> MCPServerConfig | None:
        server = self._store.get_server(server_id)
        if server is None:
            return None
        try:
            discovered = self.discover_tools(server)
            return self._store.merge_discovered_tools(server_id, discovered)
        except Exception as exc:
            message = str(exc).strip() or "Unable to refresh MCP server tools."
            return self._store.mark_refresh_failed(server_id, message)

    def discover_tools(self, server: MCPServerConfig) -> list[DiscoveredMCPTool]:
        if server.transport == "stdio":
            return self._discover_stdio_tools(server)
        if server.transport == "http_sse":
            return self._discover_http_sse_tools(server)
        raise ValueError(f"Unsupported MCP transport: {server.transport}")

    def call_tool(
        self,
        server: MCPServerConfig,
        tool: MCPToolConfig,
        arguments: dict[str, Any],
    ) -> MCPCallResult:
        capacity = self._capacity_for(server.id)
        if not capacity.acquire(timeout=get_runtime_control().limits.queue_wait_seconds):
            return MCPCallResult(ok=False, error_message="MCP server concurrency limit reached.")
        get_runtime_control().metrics.increment("mcp_calls")
        try:
            if server.transport == "stdio":
                return self._call_stdio_tool(server, tool.original_name, arguments)
            if server.transport == "http_sse":
                return self._call_http_sse_tool(server, tool.original_name, arguments)
            return MCPCallResult(
                ok=False,
                error_message=f"Unsupported MCP transport: {server.transport}",
            )
        finally:
            capacity.release()

    def _capacity_for(self, server_id: str) -> threading.BoundedSemaphore:
        with self._capacity_lock:
            capacity = self._server_capacity.get(server_id)
            if capacity is None:
                capacity = threading.BoundedSemaphore(self._per_server_limit)
                self._server_capacity[server_id] = capacity
            return capacity

    def normalize_output(self, result: MCPCallResult, *, max_chars: int = 12000) -> str:
        if not result.ok:
            output = result.error_message.strip() or result.text_output.strip() or "MCP tool call failed."
        else:
            text_output = result.text_output.strip()
            structured_output = result.structured_output
            if text_output and structured_output is not None:
                output = (
                    f"{text_output}\n\nStructured output:\n"
                    f"{self._serialize_structured_output(structured_output)}"
                )
            elif text_output:
                output = text_output
            elif structured_output is not None:
                output = self._serialize_structured_output(structured_output)
            else:
                output = "MCP tool returned no content."

        if len(output) > max_chars:
            return output[:max_chars] + "\n\n[Output truncated]"
        return output

    def _serialize_structured_output(self, value: Any) -> str:
        try:
            return json.dumps(value, ensure_ascii=False, indent=2)
        except (TypeError, ValueError):
            return str(value)

    def _normalize_sdk_response(self, response: Any) -> MCPCallResult:
        is_error = bool(
            getattr(response, "isError", False)
            or getattr(response, "is_error", False)
        )
        content = getattr(response, "content", None)
        if content is None and isinstance(response, dict):
            content = response.get("content")
        structured = getattr(response, "structuredContent", None)
        if structured is None:
            structured = getattr(response, "structured_content", None)
        if structured is None and isinstance(response, dict):
            structured = response.get("structuredContent", response.get("structured_content"))

        texts: list[str] = []
        structured_items: list[dict[str, Any]] = []
        if content is None:
            content_items: list[Any] = []
        elif isinstance(content, list | tuple):
            content_items = list(content)
        else:
            content_items = [content]

        for item in content_items:
            if isinstance(item, str):
                texts.append(item)
                continue
            text = getattr(item, "text", None)
            if text is None and isinstance(item, dict):
                text = item.get("text")
            if text is not None:
                texts.append(str(text))
            if structured is None:
                structured_item = self._structured_content_item(item)
                if structured_item is not None:
                    structured_items.append(structured_item)

        if structured is None and structured_items:
            structured = structured_items[0] if len(structured_items) == 1 else structured_items

        text_output = "\n".join(part for part in texts if part)
        if is_error:
            return MCPCallResult(
                ok=False,
                text_output=text_output,
                structured_output=structured,
                error_message=text_output or "MCP tool returned an error.",
                raw_meta={"response_type": type(response).__name__},
            )
        return MCPCallResult(
            ok=True,
            text_output=text_output,
            structured_output=structured,
            raw_meta={"response_type": type(response).__name__},
        )

    def _structured_content_item(self, item: Any) -> dict[str, Any] | None:
        if isinstance(item, dict):
            return item

        model_dump = getattr(item, "model_dump", None)
        if callable(model_dump):
            dumped = model_dump()
            if isinstance(dumped, dict):
                return dumped

        dict_method = getattr(item, "dict", None)
        if callable(dict_method):
            dumped = dict_method()
            if isinstance(dumped, dict):
                return dumped

        return None

    def _tool_from_sdk(self, tool: Any) -> DiscoveredMCPTool:
        schema = getattr(tool, "inputSchema", None)
        if schema is None:
            schema = getattr(tool, "input_schema", None)
        if schema is None and isinstance(tool, dict):
            schema = tool.get("inputSchema", tool.get("input_schema"))
        if not isinstance(schema, dict):
            schema = {}

        name = getattr(tool, "name", None)
        if name is None and isinstance(tool, dict):
            name = tool.get("name")
        description = getattr(tool, "description", None)
        if description is None and isinstance(tool, dict):
            description = tool.get("description")

        return DiscoveredMCPTool(
            name=str(name or ""),
            description=str(description or ""),
            input_schema=schema,
        )

    def _discover_stdio_tools(self, server: MCPServerConfig) -> list[DiscoveredMCPTool]:
        try:
            return self._run_async_sync_safe(self._discover_stdio_tools_async(server), timeout_seconds=self._timeout_seconds(server) + 5)
        except TimeoutError as exc:
            raise RuntimeError("MCP stdio discovery timed out.") from exc
        except Exception as exc:
            raise RuntimeError(self._sanitize_transport_error(server, exc, action="discover tools")) from exc

    def _discover_http_sse_tools(self, server: MCPServerConfig) -> list[DiscoveredMCPTool]:
        try:
            return self._run_async_sync_safe(self._discover_http_sse_tools_async(server), timeout_seconds=self._timeout_seconds(server) + 5)
        except TimeoutError as exc:
            raise RuntimeError("MCP HTTP/SSE discovery timed out.") from exc
        except Exception as exc:
            raise RuntimeError(self._sanitize_transport_error(server, exc, action="discover tools")) from exc

    def _call_stdio_tool(
        self,
        server: MCPServerConfig,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> MCPCallResult:
        try:
            return self._run_async_sync_safe(self._call_stdio_tool_async(server, tool_name, arguments), timeout_seconds=self._timeout_seconds(server) + 5)
        except TimeoutError:
            return MCPCallResult(ok=False, error_message="MCP stdio tool call timed out.")
        except Exception as exc:
            return MCPCallResult(
                ok=False,
                error_message=self._sanitize_transport_error(server, exc, action=f"call tool '{tool_name}'"),
            )

    def _call_http_sse_tool(
        self,
        server: MCPServerConfig,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> MCPCallResult:
        try:
            return self._run_async_sync_safe(self._call_http_sse_tool_async(server, tool_name, arguments), timeout_seconds=self._timeout_seconds(server) + 5)
        except TimeoutError:
            return MCPCallResult(ok=False, error_message="MCP HTTP/SSE tool call timed out.")
        except Exception as exc:
            return MCPCallResult(
                ok=False,
                error_message=self._sanitize_transport_error(server, exc, action=f"call tool '{tool_name}'"),
            )

    def _run_async_sync_safe(self, coroutine: Any, *, timeout_seconds: float | None = None) -> Any:
        async def runner() -> Any:
            return await coroutine

        future = self._executor.submit(anyio.run, runner)
        try:
            return future.result(timeout=timeout_seconds)
        except FutureTimeoutError as exc:
            future.cancel()
            raise TimeoutError from exc

    async def _discover_stdio_tools_async(self, server: MCPServerConfig) -> list[DiscoveredMCPTool]:
        async with self._stdio_session(server) as session:
            tools: list[DiscoveredMCPTool] = []
            cursor: str | None = None
            while True:
                result = await session.list_tools(cursor=cursor)
                tools.extend(self._tool_from_sdk(tool) for tool in result.tools)
                cursor = getattr(result, "nextCursor", None)
                if not cursor:
                    break
            return tools

    async def _discover_http_sse_tools_async(self, server: MCPServerConfig) -> list[DiscoveredMCPTool]:
        async with self._http_sse_session(server) as session:
            tools: list[DiscoveredMCPTool] = []
            cursor: str | None = None
            while True:
                result = await session.list_tools(cursor=cursor)
                tools.extend(self._tool_from_sdk(tool) for tool in result.tools)
                cursor = getattr(result, "nextCursor", None)
                if not cursor:
                    break
            return tools

    async def _call_stdio_tool_async(
        self,
        server: MCPServerConfig,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> MCPCallResult:
        async with self._stdio_session(server) as session:
            response = await session.call_tool(
                tool_name,
                arguments=arguments,
                read_timeout_seconds=self._timeout_delta(server),
            )
            return self._normalize_sdk_response(response)

    async def _call_http_sse_tool_async(
        self,
        server: MCPServerConfig,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> MCPCallResult:
        async with self._http_sse_session(server) as session:
            response = await session.call_tool(
                tool_name,
                arguments=arguments,
                read_timeout_seconds=self._timeout_delta(server),
            )
            return self._normalize_sdk_response(response)

    @asynccontextmanager
    async def _stdio_session(self, server: MCPServerConfig):
        self._validate_stdio_server(server)
        params = StdioServerParameters(
            command=server.command,
            args=list(server.args),
            env=dict(server.env) or None,
        )
        with open(os.devnull, "w", encoding="utf-8") as errlog:
            async with stdio_client(params, errlog=errlog) as streams:
                async with self._client_session(streams, server) as session:
                    yield session

    @asynccontextmanager
    async def _http_sse_session(self, server: MCPServerConfig):
        self._validate_http_sse_server(server)
        async with sse_client(
            server.url,
            headers=dict(server.headers) or None,
            timeout=self._timeout_seconds(server),
            sse_read_timeout=self._timeout_seconds(server),
        ) as streams:
            async with self._client_session(streams, server) as session:
                yield session

    @asynccontextmanager
    async def _client_session(self, streams: Any, server: MCPServerConfig):
        read_stream, write_stream = streams
        session = ClientSession(
            read_stream,
            write_stream,
            read_timeout_seconds=self._timeout_delta(server),
        )
        async with session:
            with anyio.fail_after(self._timeout_seconds(server)):
                await session.initialize()
            yield session

    def _timeout_seconds(self, server: MCPServerConfig) -> float:
        timeout_seconds = int(getattr(server, "timeout_seconds", 30) or 30)
        return float(timeout_seconds if timeout_seconds > 0 else 30)

    def _timeout_delta(self, server: MCPServerConfig) -> timedelta:
        return timedelta(seconds=self._timeout_seconds(server))

    def _validate_stdio_server(self, server: MCPServerConfig) -> None:
        if not server.command.strip():
            raise ValueError("MCP stdio server command is required.")

    def _validate_http_sse_server(self, server: MCPServerConfig) -> None:
        if not server.url.strip():
            raise ValueError("MCP HTTP/SSE server URL is required.")

    def _sanitize_transport_error(self, server: MCPServerConfig, exc: Exception, *, action: str) -> str:
        transport_label = "MCP stdio" if server.transport == "stdio" else "MCP HTTP/SSE"
        text = str(exc).strip()
        if not text:
            return f"{transport_label} failed to {action}."

        scrubbed = text
        for secret in list(server.env.values()) + list(server.headers.values()) + list(server.args):
            if secret:
                scrubbed = scrubbed.replace(secret, "[redacted]")
                for token in re.split(r"[\s=,:;]+", secret):
                    if token:
                        scrubbed = scrubbed.replace(token, "[redacted]")
        for value in (server.command, server.url):
            if value and value in scrubbed:
                scrubbed = scrubbed.replace(value, "[configured target]")

        return f"{transport_label} failed to {action}: {scrubbed}"
