from __future__ import annotations

import re
import shlex
from collections.abc import Iterator
from typing import Any

from app.core.loop.loop_events import LoopEvent
from app.core.loop.loop_state import LoopState
from app.core.loop.message_manager import MessageManager
from app.core.tool.execute_command import ExecuteCommandHandler
from app.core.tool.handler import ToolDisplayMetadata
from app.core.tool.schema import LLMToolDefinition
from app.services.ops_plugin_service import OpsPluginTool


class OpsPluginToolHandler:
    def __init__(self, *, tool: OpsPluginTool, terminal: Any) -> None:
        self._tool = tool
        self._delegate = ExecuteCommandHandler(terminal)

    @property
    def definition(self) -> LLMToolDefinition:
        schema = self._tool.input_schema
        properties = dict(schema.get("properties") or {})
        properties["authorization_id"] = {
            "type": "string",
            "description": "Runtime terminal authorization ID for the target session.",
        }
        required = list(dict.fromkeys([*(schema.get("required") or []), "authorization_id"]))
        return LLMToolDefinition(
            name=self._tool.exposed_name,
            description=(
                f"{self._tool.description} "
                "This declarative operations plugin still uses the standard command approval policy."
            ),
            input_schema={
                "type": "object",
                "properties": properties,
                "required": required,
                "additionalProperties": False,
            },
        )

    def needs_approval(self, args: dict[str, Any]) -> tuple[str, str]:
        try:
            args["command"] = self._render_command(args)
        except ValueError as exc:
            return "deny", str(exc)
        action, reason = self._delegate.needs_approval(args)
        if action == "deny":
            return action, reason
        if self._tool.asset_types and str(args.get("asset_type") or "") not in self._tool.asset_types:
            return "deny", "Plugin tool is not compatible with this asset type."
        return action, reason

    def display_metadata(self, args: dict[str, Any]) -> ToolDisplayMetadata:
        try:
            command = self._render_command(args)
        except ValueError:
            command = self._tool.command_template
        return ToolDisplayMetadata(
            description=self._tool.description,
            display_text=command,
            extra={
                "kind": "command",
                "pluginId": self._tool.plugin_id,
                "pluginTool": self._tool.name,
            },
        )

    def execute(
        self,
        *,
        state: LoopState,
        step_id: str,
        args: dict[str, Any],
        manager: MessageManager | None = None,
    ) -> Iterator[LoopEvent]:
        args["command"] = self._render_command(args)
        return (yield from self._delegate.execute(
            state=state,
            step_id=step_id,
            args=args,
            manager=manager,
        ))

    def _render_command(self, args: dict[str, Any]) -> str:
        properties = self._tool.input_schema.get("properties") or {}
        required = set(self._tool.input_schema.get("required") or [])
        values: dict[str, str] = {}
        for name, raw_schema in properties.items():
            schema = raw_schema if isinstance(raw_schema, dict) else {}
            value = args.get(name)
            if value is None or value == "":
                if name in required:
                    raise ValueError(f"Missing required plugin parameter: {name}")
                values[name] = "''"
                continue
            if not isinstance(value, str | int | float | bool):
                raise ValueError(f"Plugin parameter {name} must be a scalar value")
            text = str(value)
            if len(text) > min(int(schema.get("maxLength") or 256), 1024):
                raise ValueError(f"Plugin parameter {name} is too long")
            choices = schema.get("enum")
            if isinstance(choices, list) and value not in choices:
                raise ValueError(f"Plugin parameter {name} is not an allowed value")
            pattern = schema.get("pattern")
            if pattern and re.fullmatch(str(pattern), text) is None:
                raise ValueError(f"Plugin parameter {name} has an invalid format")
            values[name] = shlex.quote(text)
        try:
            return self._tool.command_template.format_map(values)
        except (KeyError, ValueError) as exc:
            raise ValueError("Unable to render plugin command safely") from exc
