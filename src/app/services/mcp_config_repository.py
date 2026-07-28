from __future__ import annotations

import json
import re
import uuid
from pathlib import Path
from typing import Any, cast

from app.services.mcp_config_models import (
    DiscoveredMCPTool,
    MCPApprovalPolicy,
    MCPServerConfig,
    MCPToolConfig,
    MCPTransport,
    _MASK_RE,
    _SECRET_KEY_PATTERN,
    _STORE_LOCK,
    _VALID_APPROVAL_POLICIES,
    _VALID_TRANSPORTS,
    _clean_name,
    _coerce_approval_policy,
    _coerce_bool,
    _coerce_connection_status,
    _coerce_discovery_status,
    _coerce_int,
    _coerce_schema,
    _coerce_str_dict,
    _coerce_str_list,
    _coerce_transport,
    now_iso,
)
from app.shared.config import MCP_SERVERS_PATH
from app.utils.file_store import atomic_write_json


class MCPConfigStore:
    def __init__(self, path: Path | None = None) -> None:
        self._path = path or MCP_SERVERS_PATH

    def load(self) -> list[MCPServerConfig]:
        payload = self._read_payload()
        servers = [
            self._server_from_dict(item)
            for item in payload.get("servers", [])
            if isinstance(item, dict)
        ]
        return self._normalize_servers(servers)

    def save(self, servers: list[MCPServerConfig]) -> list[MCPServerConfig]:
        normalized = self._normalize_servers(servers)
        payload = {
            "version": 1,
            "servers": [self._server_to_dict(server) for server in normalized],
        }
        atomic_write_json(self._path, payload)
        return normalized

    def list_servers(self) -> list[MCPServerConfig]:
        return self.load()

    def get_server(self, server_id: str) -> MCPServerConfig | None:
        return next((server for server in self.load() if server.id == server_id), None)

    def create_server(
        self,
        *,
        name: str,
        transport: MCPTransport,
        command: str = "",
        args: list[str] | None = None,
        env: dict[str, str] | None = None,
        url: str = "",
        headers: dict[str, str] | None = None,
        timeout_seconds: int = 30,
    ) -> MCPServerConfig:
        with _STORE_LOCK:
            transport_value = self._validate_transport(transport)
            servers = self.load()
            server = MCPServerConfig(
                id=f"srv_{uuid.uuid4().hex[:12]}",
                name=_clean_name(name, "MCP Server"),
                slug=self._unique_slug(name, servers),
                enabled=False,
                transport=transport_value,
                command=str(command or "").strip(),
                args=_coerce_str_list(args),
                env=_coerce_str_dict(env),
                url=str(url or "").strip(),
                headers=_coerce_str_dict(headers),
                timeout_seconds=_coerce_int(timeout_seconds, 30),
            )
            servers.insert(0, server)
            self.save(servers)
            return server

    def update_server(self, server_id: str, **updates: Any) -> MCPServerConfig | None:
        with _STORE_LOCK:
            servers = self.load()
            server = next((item for item in servers if item.id == server_id), None)
            if server is None:
                return None

            if "name" in updates and updates["name"] is not None:
                server.name = _clean_name(updates["name"], server.name)
                server.slug = self._unique_slug(server.name, servers, ignore_id=server.id)

            if "transport" in updates and updates["transport"] is not None:
                server.transport = self._validate_transport(updates["transport"])
            if "command" in updates and updates["command"] is not None:
                server.command = str(updates["command"] or "").strip()
            if "args" in updates and updates["args"] is not None:
                server.args = self._merge_masked_list(server.args, _coerce_str_list(updates["args"]))
            if "env" in updates and updates["env"] is not None:
                server.env = self._merge_masked_map(server.env, _coerce_str_dict(updates["env"]))
            if "url" in updates and updates["url"] is not None:
                server.url = str(updates["url"] or "").strip()
            if "headers" in updates and updates["headers"] is not None:
                server.headers = self._merge_masked_map(server.headers, _coerce_str_dict(updates["headers"]))
            if "timeout_seconds" in updates and updates["timeout_seconds"] is not None:
                server.timeout_seconds = _coerce_int(updates["timeout_seconds"], server.timeout_seconds)

            server.connection_status = "untested"
            server.discovery_status = "never"
            server.last_refresh_succeeded = False
            server.last_error = ""
            server.updated_at = now_iso()
            saved_servers = self.save(servers)
            return next((item for item in saved_servers if item.id == server_id), server)

    def delete_server(self, server_id: str) -> bool:
        with _STORE_LOCK:
            servers = self.load()
            next_servers = [server for server in servers if server.id != server_id]
            if len(next_servers) == len(servers):
                return False
            self.save(next_servers)
            return True

    def set_server_enabled(self, server_id: str, enabled: bool) -> MCPServerConfig | None:
        with _STORE_LOCK:
            servers = self.load()
            server = next((item for item in servers if item.id == server_id), None)
            if server is None:
                return None
            if enabled and not server.last_refresh_succeeded:
                raise ValueError("MCP server must refresh tools successfully before it can be enabled")
            server.enabled = bool(enabled)
            server.updated_at = now_iso()
            saved_servers = self.save(servers)
            return next((item for item in saved_servers if item.id == server_id), server)

    def update_tool(
        self,
        tool_id: str,
        *,
        enabled: bool | None = None,
        approval_policy: MCPApprovalPolicy | None = None,
    ) -> MCPToolConfig | None:
        with _STORE_LOCK:
            servers = self.load()
            for server in servers:
                for tool in server.tools:
                    if tool.id != tool_id:
                        continue
                    if enabled is not None:
                        tool.enabled = bool(enabled)
                    if approval_policy is not None:
                        tool.approval_policy = self._validate_approval_policy(approval_policy)
                    tool.updated_at = now_iso()
                    saved_servers = self.save(servers)
                    saved_server = next((item for item in saved_servers if item.id == server.id), None)
                    if saved_server is None:
                        return tool
                    return next((item for item in saved_server.tools if item.id == tool_id), tool)
            return None

    def list_injectable_tools(self) -> list[tuple[MCPServerConfig, MCPToolConfig]]:
        pairs: list[tuple[MCPServerConfig, MCPToolConfig]] = []
        for server in self.load():
            if not server.enabled or not server.last_refresh_succeeded:
                continue
            for tool in server.tools:
                if tool.enabled and tool.discovered:
                    pairs.append((server, tool))
        return sorted(pairs, key=lambda pair: pair[1].exposed_name)

    def merge_discovered_tools(
        self,
        server_id: str,
        discovered: list[DiscoveredMCPTool],
    ) -> MCPServerConfig | None:
        with _STORE_LOCK:
            servers = self.load()
            server = next((item for item in servers if item.id == server_id), None)
            if server is None:
                return None

            timestamp = now_iso()
            discovered_by_name: dict[str, DiscoveredMCPTool] = {}
            for item in discovered:
                name = str(item.name or "").strip()
                if not name:
                    continue
                discovered_by_name[name] = DiscoveredMCPTool(
                    name=name,
                    description=str(item.description or ""),
                    input_schema=_coerce_schema(item.input_schema),
                )

            existing = {tool.original_name: tool for tool in server.tools}
            seen_names = set(discovered_by_name)

            for original_name, item in discovered_by_name.items():
                tool = existing.get(original_name)
                if tool is None:
                    server.tools.append(
                        MCPToolConfig(
                            id=f"tool_{uuid.uuid4().hex[:12]}",
                            original_name=original_name,
                            exposed_name=self.exposed_tool_name(server.slug, original_name),
                            description=item.description,
                            input_schema=item.input_schema,
                            approval_policy="ask",
                            enabled=True,
                            discovered=True,
                            last_discovered_at=timestamp,
                        )
                    )
                    continue

                tool.description = item.description
                tool.input_schema = item.input_schema
                tool.discovered = True
                tool.last_discovered_at = timestamp
                tool.updated_at = timestamp

            for tool in server.tools:
                if tool.original_name in seen_names:
                    continue
                if tool.discovered:
                    tool.discovered = False
                    tool.updated_at = timestamp

            server.connection_status = "ok"
            server.discovery_status = "ok"
            server.last_refresh_succeeded = True
            server.last_error = ""
            server.last_discovered_at = timestamp
            server.updated_at = timestamp
            saved_servers = self.save(servers)
            return next((item for item in saved_servers if item.id == server_id), server)

    def mark_refresh_failed(self, server_id: str, error: str) -> MCPServerConfig | None:
        with _STORE_LOCK:
            servers = self.load()
            server = next((item for item in servers if item.id == server_id), None)
            if server is None:
                return None
            server.connection_status = "failed"
            server.discovery_status = "failed"
            server.last_refresh_succeeded = False
            server.last_error = str(error or "MCP refresh failed")
            server.updated_at = now_iso()
            saved_servers = self.save(servers)
            return next((item for item in saved_servers if item.id == server_id), server)

    def redacted_server(self, server: MCPServerConfig) -> dict[str, Any]:
        data = self._server_to_dict(server)
        data["args"] = self._mask_args(server.args)
        data["env"] = self._mask_map(server.env)
        data["headers"] = self._mask_map(server.headers)
        return data

    def _read_payload(self) -> dict[str, Any]:
        default_payload = {"version": 1, "servers": []}
        if not self._path.exists():
            return default_payload
        try:
            payload = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return default_payload
        if not isinstance(payload, dict):
            return default_payload
        servers = payload.get("servers")
        if not isinstance(servers, list):
            servers = []
        return {"version": 1, "servers": servers}

    def _server_from_dict(self, data: dict[str, Any]) -> MCPServerConfig:
        name = _clean_name(data.get("name"), "MCP Server")
        tools_data = data.get("tools")
        if not isinstance(tools_data, list):
            tools_data = []
        return MCPServerConfig(
            id=str(data.get("id") or f"srv_{uuid.uuid4().hex[:12]}"),
            name=name,
            slug=self.slugify(str(data.get("slug") or name)),
            enabled=_coerce_bool(data.get("enabled"), False),
            transport=_coerce_transport(data.get("transport")),
            command=str(data.get("command") or "").strip(),
            args=_coerce_str_list(data.get("args")),
            env=_coerce_str_dict(data.get("env")),
            url=str(data.get("url") or "").strip(),
            headers=_coerce_str_dict(data.get("headers")),
            timeout_seconds=_coerce_int(data.get("timeout_seconds"), 30),
            connection_status=_coerce_connection_status(data.get("connection_status")),
            discovery_status=_coerce_discovery_status(data.get("discovery_status")),
            last_error=str(data.get("last_error") or ""),
            last_discovered_at=data.get("last_discovered_at") if isinstance(data.get("last_discovered_at"), str) else None,
            last_refresh_succeeded=_coerce_bool(data.get("last_refresh_succeeded"), False),
            tools=[self._tool_from_dict(item) for item in tools_data if isinstance(item, dict)],
            created_at=str(data.get("created_at") or now_iso()),
            updated_at=str(data.get("updated_at") or now_iso()),
        )

    def _tool_from_dict(self, data: dict[str, Any]) -> MCPToolConfig:
        original_name = _clean_name(data.get("original_name"), "tool")
        exposed_name = str(data.get("exposed_name") or "").strip()
        return MCPToolConfig(
            id=str(data.get("id") or f"tool_{uuid.uuid4().hex[:12]}"),
            original_name=original_name,
            exposed_name=exposed_name,
            description=str(data.get("description") or ""),
            input_schema=_coerce_schema(data.get("input_schema")),
            approval_policy=_coerce_approval_policy(data.get("approval_policy")),
            enabled=_coerce_bool(data.get("enabled"), True),
            discovered=_coerce_bool(data.get("discovered"), True),
            last_discovered_at=data.get("last_discovered_at") if isinstance(data.get("last_discovered_at"), str) else None,
            created_at=str(data.get("created_at") or now_iso()),
            updated_at=str(data.get("updated_at") or now_iso()),
        )

    def _server_to_dict(self, server: MCPServerConfig) -> dict[str, Any]:
        return {
            "id": server.id,
            "name": server.name,
            "slug": server.slug,
            "enabled": server.enabled,
            "transport": server.transport,
            "command": server.command,
            "args": list(server.args),
            "env": dict(server.env),
            "url": server.url,
            "headers": dict(server.headers),
            "timeout_seconds": server.timeout_seconds,
            "connection_status": server.connection_status,
            "discovery_status": server.discovery_status,
            "last_error": server.last_error,
            "last_discovered_at": server.last_discovered_at,
            "last_refresh_succeeded": server.last_refresh_succeeded,
            "tools": [self._tool_to_dict(tool) for tool in server.tools],
            "created_at": server.created_at,
            "updated_at": server.updated_at,
        }

    def _tool_to_dict(self, tool: MCPToolConfig) -> dict[str, Any]:
        return {
            "id": tool.id,
            "original_name": tool.original_name,
            "exposed_name": tool.exposed_name,
            "description": tool.description,
            "input_schema": tool.input_schema,
            "approval_policy": tool.approval_policy,
            "enabled": tool.enabled,
            "discovered": tool.discovered,
            "last_discovered_at": tool.last_discovered_at,
            "created_at": tool.created_at,
            "updated_at": tool.updated_at,
        }

    def _unique_slug(
        self,
        name: str,
        servers: list[MCPServerConfig],
        *,
        ignore_id: str | None = None,
    ) -> str:
        base = self.slugify(name)
        candidate = base
        suffix = 2
        existing = {server.slug for server in servers if server.id != ignore_id}
        while candidate in existing:
            candidate = f"{base}_{suffix}"
            suffix += 1
        return candidate

    def slugify(self, value: str) -> str:
        slug = re.sub(r"[^a-zA-Z0-9_]+", "_", str(value or "").strip().lower()).strip("_")
        return slug or "mcp_server"

    def tool_name_part(self, value: str) -> str:
        part = re.sub(r"[^a-zA-Z0-9_]+", "_", str(value or "").strip().lower()).strip("_")
        return part or "tool"

    def exposed_tool_name(self, server_slug: str, tool_name: str) -> str:
        return f"mcp__{self.tool_name_part(server_slug)}__{self.tool_name_part(tool_name)}"

    def _mask_args(self, args: list[str]) -> list[str]:
        masked: list[str] = []
        redact_next = False
        for arg in args:
            text = str(arg)
            if redact_next:
                masked.append(self._mask_secret(text))
                redact_next = False
                continue
            if self._arg_contains_secret(text):
                key, separator, value = text.partition("=")
                if separator:
                    masked.append(f"{key}={self._mask_secret(value)}")
                else:
                    masked.append(text)
                    redact_next = True
                continue
            masked.append(text)
        return masked

    def _mask_map(self, payload: dict[str, str]) -> dict[str, str]:
        return {str(key): self._mask_secret(str(value)) for key, value in payload.items()}

    def _mask_secret(self, value: str) -> str:
        if not value:
            return ""
        if len(value) <= 4:
            return "****"
        return f"****{value[-4:]}"

    def _merge_masked_list(self, current: list[str], incoming: list[str]) -> list[str]:
        merged: list[str] = []
        for index, value in enumerate(incoming):
            if index < len(current) and self._is_masked_arg(value):
                merged.append(current[index])
            else:
                merged.append(value)
        return merged

    def _merge_masked_map(self, current: dict[str, str], incoming: dict[str, str]) -> dict[str, str]:
        return {
            key: current[key] if key in current and self._is_masked_secret(value) else value
            for key, value in incoming.items()
        }

    def _is_masked_secret(self, value: str) -> bool:
        return bool(_MASK_RE.fullmatch(str(value or "")))

    def _is_masked_arg(self, value: str) -> bool:
        text = str(value or "")
        _, separator, secret_value = text.partition("=")
        return self._is_masked_secret(secret_value if separator else text)

    def _arg_contains_secret(self, value: str) -> bool:
        return bool(_SECRET_KEY_PATTERN.search(value))

    def _normalize_servers(self, servers: list[MCPServerConfig]) -> list[MCPServerConfig]:
        normalized: list[MCPServerConfig] = []
        for server in servers:
            server.name = _clean_name(server.name, "MCP Server")
            server.slug = self._unique_slug(server.slug or server.name, normalized, ignore_id=server.id)
            normalized.append(server)

        used_exposed_names: set[str] = set()
        for server in normalized:
            for tool in server.tools:
                tool.original_name = _clean_name(tool.original_name, "tool")
                existing_name = str(tool.exposed_name or "").strip()
                if existing_name and existing_name not in used_exposed_names:
                    tool.exposed_name = existing_name
                    used_exposed_names.add(existing_name)
                    continue

                base_name = self.exposed_tool_name(server.slug, tool.original_name)
                candidate = base_name
                suffix = 2
                while candidate in used_exposed_names:
                    candidate = f"{base_name}_{suffix}"
                    suffix += 1
                tool.exposed_name = candidate
                used_exposed_names.add(candidate)
        return normalized

    def _validate_transport(self, value: Any) -> MCPTransport:
        if value in _VALID_TRANSPORTS:
            return value
        raise ValueError(f"Unsupported MCP transport: {value}")

    def _validate_approval_policy(self, value: Any) -> MCPApprovalPolicy:
        if value in _VALID_APPROVAL_POLICIES:
            return value
        raise ValueError(f"Unsupported MCP approval policy: {value}")
