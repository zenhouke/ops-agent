from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from app.core.loop.loop_events import LoopEvent
from app.core.loop.loop_state import LoopState
from app.core.loop.message_manager import MessageManager
from app.core.tool.handler import ToolDisplayMetadata
from app.core.tool.schema import LLMToolDefinition
from app.core.tool.ports import SkillLoader


class LoadSkillHandler:
    def __init__(self, skill_service: SkillLoader) -> None:
        self._skill_service = skill_service

    @property
    def definition(self) -> LLMToolDefinition:
        return LLMToolDefinition(
            name="load_skill",
            description="Load the full instructions for an available skill by name.",
            input_schema={
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "The name of the skill to load.",
                    }
                },
                "required": ["name"],
            },
        )

    def needs_approval(self, args: dict[str, Any]) -> tuple[str, str]:
        _ = args
        return "allow", "Skill loading only reads local skill instructions."

    def display_metadata(self, args: dict[str, Any]) -> ToolDisplayMetadata:
        name = str(args.get("name", "")).strip()
        display_name = name or "skill"
        return ToolDisplayMetadata(
            description="Load local skill instructions into the current runtime.",
            display_text=f"Load skill {display_name}",
            extra={"kind": "skill"},
        )

    def execute(self, *, state: LoopState, step_id: str, args: dict[str, Any], manager: MessageManager | None = None) -> Iterator[LoopEvent]:
        _ = step_id
        name = str(args.get("name", "")).strip()
        if not name:
            output = "Skill name is required."
            if manager:
                yield from manager.update(tool_output=output)
            return False, output

        if state.context.loaded_skill_name:
            output = (
                "Skill already loaded for this runtime: "
                f"{state.context.loaded_skill_name}. Continue using the existing loaded skill instructions."
            )
            if manager:
                yield from manager.update(tool_output=output)
            return True, output

        try:
            skill = self._skill_service.load_skill(name)
        except ValueError as exc:
            output = str(exc)
            if manager:
                yield from manager.update(tool_output=output)
            return False, output

        state.context.loaded_skill_name = skill.name
        state.context.manual_skill_name = skill.name
        state.context.manual_skill_content = skill.body
        output = (
            f"Loaded skill: {skill.name}\n"
            "These instructions apply only to the current runtime and are not persisted to conversation history.\n\n"
            f"{skill.body}"
        )
        if manager:
            yield from manager.update(tool_output=f"Loaded skill: {skill.name}")
        return True, output
