from __future__ import annotations

import json
import re
import threading
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from pathlib import Path
from string import Formatter
from typing import Any

from app.shared.config import APP_DIR

PLUGIN_MANIFEST_LIMIT_BYTES = 128 * 1024
PLUGIN_LIMIT = 64
TOOLS_PER_PLUGIN_LIMIT = 32
_IDENTIFIER_RE = re.compile(r"^[a-z][a-z0-9_-]{1,63}$")


@dataclass(frozen=True)
class OpsPluginTool:
    plugin_id: str
    name: str
    exposed_name: str
    description: str
    command_template: str
    input_schema: dict[str, Any]
    asset_types: tuple[str, ...] = ()


@dataclass(frozen=True)
class OpsPluginPackage:
    plugin_id: str
    name: str
    version: str
    description: str
    source: str
    path: str
    enabled: bool
    valid: bool
    error: str | None
    updated_at: datetime
    tools: tuple[OpsPluginTool, ...] = field(default_factory=tuple)


class OpsPluginService:
    def __init__(
        self,
        *,
        builtin_dir: Path | None = None,
        local_dir: Path | None = None,
    ) -> None:
        app_root = Path(__file__).resolve().parents[1]
        self._builtin_dir = builtin_dir or (app_root / "plugins" / "builtin")
        self._local_dir = local_dir or (APP_DIR / "plugins")
        self._lock = threading.RLock()
        self._packages: tuple[OpsPluginPackage, ...] | None = None

    def list_plugins(self, *, refresh: bool = False) -> list[OpsPluginPackage]:
        with self._lock:
            if refresh or self._packages is None:
                self._packages = tuple(self._discover())
            return list(self._packages)

    def build_tool_handlers(self, terminal: Any) -> list[Any]:
        from app.core.tool.ops_plugin import OpsPluginToolHandler

        return [
            OpsPluginToolHandler(tool=tool, terminal=terminal)
            for package in self.list_plugins()
            if package.valid and package.enabled
            for tool in package.tools
        ]

    def summary(self) -> dict[str, int]:
        packages = self.list_plugins()
        return {
            "plugins": len(packages),
            "validPlugins": sum(package.valid for package in packages),
            "enabledPlugins": sum(package.valid and package.enabled for package in packages),
            "tools": sum(len(package.tools) for package in packages if package.valid and package.enabled),
        }

    def _discover(self) -> list[OpsPluginPackage]:
        manifests = [
            *(("builtin", path) for path in sorted(self._builtin_dir.glob("*.json"))),
            *(("local", path) for path in sorted(self._local_dir.glob("*/plugin.json"))),
        ][:PLUGIN_LIMIT]
        packages: list[OpsPluginPackage] = []
        seen_plugin_ids: set[str] = set()
        seen_tool_names: set[str] = set()
        for source, path in manifests:
            package = self._load_manifest(path, source=source)
            if package.valid and package.plugin_id in seen_plugin_ids:
                package = self._invalid(package, "Duplicate plugin id")
            duplicate_tool = next(
                (tool.exposed_name for tool in package.tools if tool.exposed_name in seen_tool_names),
                None,
            )
            if package.valid and duplicate_tool:
                package = self._invalid(package, f"Duplicate exposed tool name: {duplicate_tool}")
            if package.valid:
                seen_plugin_ids.add(package.plugin_id)
                seen_tool_names.update(tool.exposed_name for tool in package.tools)
            packages.append(package)
        return packages

    def _load_manifest(self, path: Path, *, source: str) -> OpsPluginPackage:
        updated_at = self._updated_at(path)
        placeholder = OpsPluginPackage(
            plugin_id=path.stem,
            name=path.stem,
            version="",
            description="",
            source=source,
            path=str(path),
            enabled=False,
            valid=False,
            error=None,
            updated_at=updated_at,
        )
        try:
            resolved = path.resolve(strict=True)
            root = (self._builtin_dir if source == "builtin" else self._local_dir).resolve()
            if not resolved.is_relative_to(root) or not resolved.is_file():
                return self._invalid(placeholder, "Manifest escapes plugin directory")
            if resolved.stat().st_size > PLUGIN_MANIFEST_LIMIT_BYTES:
                return self._invalid(placeholder, "Manifest is too large")
            payload = json.loads(resolved.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                return self._invalid(placeholder, "Manifest must be a JSON object")
            return self._parse_manifest(payload, placeholder)
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            return self._invalid(placeholder, f"Unable to read manifest: {exc}")

    def _parse_manifest(
        self,
        payload: dict[str, Any],
        package: OpsPluginPackage,
    ) -> OpsPluginPackage:
        plugin_id = str(payload.get("id") or "").strip()
        name = str(payload.get("name") or "").strip()
        version = str(payload.get("version") or "").strip()
        description = str(payload.get("description") or "").strip()
        enabled = payload.get("enabled", True)
        base = OpsPluginPackage(
            plugin_id=plugin_id or package.plugin_id,
            name=name or plugin_id or package.name,
            version=version,
            description=description,
            source=package.source,
            path=package.path,
            enabled=enabled if isinstance(enabled, bool) else False,
            valid=False,
            error=None,
            updated_at=package.updated_at,
        )
        if not _IDENTIFIER_RE.fullmatch(plugin_id):
            return self._invalid(base, "Invalid plugin id")
        if not name or not version or not description:
            return self._invalid(base, "name, version and description are required")
        if not isinstance(enabled, bool):
            return self._invalid(base, "enabled must be a boolean")
        raw_tools = payload.get("tools")
        if not isinstance(raw_tools, list) or not raw_tools:
            return self._invalid(base, "Plugin must define at least one tool")
        if len(raw_tools) > TOOLS_PER_PLUGIN_LIMIT:
            return self._invalid(base, "Plugin defines too many tools")
        try:
            tools = tuple(self._parse_tool(plugin_id, item) for item in raw_tools)
        except ValueError as exc:
            return self._invalid(base, str(exc))
        exposed_names = [tool.exposed_name for tool in tools]
        if len(exposed_names) != len(set(exposed_names)):
            return self._invalid(base, "Plugin contains duplicate tool names")
        return replace(base, valid=True, tools=tools)

    def _parse_tool(self, plugin_id: str, payload: object) -> OpsPluginTool:
        if not isinstance(payload, dict):
            raise ValueError("Tool definition must be an object")
        name = str(payload.get("name") or "").strip()
        description = str(payload.get("description") or "").strip()
        command = str(payload.get("command") or "").strip()
        if not _IDENTIFIER_RE.fullmatch(name):
            raise ValueError(f"Invalid tool name: {name or '<empty>'}")
        if not description or not command or len(command) > 4096:
            raise ValueError(f"Tool {name} requires a valid description and command")
        schema = payload.get("parameters") or {"type": "object", "properties": {}}
        if not isinstance(schema, dict) or schema.get("type") != "object":
            raise ValueError(f"Tool {name} parameters must be an object schema")
        properties = schema.get("properties") or {}
        if not isinstance(properties, dict):
            raise ValueError(f"Tool {name} properties must be an object")
        if "authorization_id" in properties:
            raise ValueError(f"Tool {name} uses reserved parameter authorization_id")
        if any(not _IDENTIFIER_RE.fullmatch(str(field)) for field in properties):
            raise ValueError(f"Tool {name} contains an invalid parameter name")
        required = schema.get("required") or []
        if not isinstance(required, list) or any(field not in properties for field in required):
            raise ValueError(f"Tool {name} required parameters are invalid")
        fields = {
            field_name
            for _, field_name, format_spec, conversion in Formatter().parse(command)
            if field_name and not format_spec and not conversion
        }
        if any(field not in properties for field in fields):
            raise ValueError(f"Tool {name} command uses an undeclared parameter")
        exposed = f"ops__{plugin_id.replace('-', '_')}__{name.replace('-', '_')}"
        raw_asset_types = payload.get("asset_types") or []
        if not isinstance(raw_asset_types, list):
            raise ValueError(f"Tool {name} asset_types must be an array")
        asset_types = tuple(str(value) for value in raw_asset_types)
        return OpsPluginTool(
            plugin_id=plugin_id,
            name=name,
            exposed_name=exposed,
            description=description,
            command_template=command,
            input_schema=schema,
            asset_types=asset_types,
        )

    def _invalid(self, package: OpsPluginPackage, error: str) -> OpsPluginPackage:
        return replace(
            package,
            enabled=False,
            valid=False,
            error=error,
            tools=(),
        )

    def _updated_at(self, path: Path) -> datetime:
        try:
            return datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)
        except OSError:
            return datetime.now(UTC)


_ops_plugin_service = OpsPluginService()


def get_ops_plugin_service() -> OpsPluginService:
    return _ops_plugin_service
