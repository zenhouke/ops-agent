from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(slots=True)
class AgentTaskState:
    goal: str = ""
    current_request: str = ""
    scope: list[str] = field(default_factory=list)
    constraints: list[str] = field(default_factory=list)
    acceptance_criteria: list[str] = field(default_factory=list)
    verified_facts: list[str] = field(default_factory=list)
    decisions: list[str] = field(default_factory=list)
    open_items: list[str] = field(default_factory=list)
    completed_items: list[str] = field(default_factory=list)
    revision: int = 1

    @classmethod
    def from_payload(cls, payload: object) -> "AgentTaskState":
        data = payload if isinstance(payload, dict) else {}
        try:
            revision = max(1, int(data.get("revision") or 1))
        except (TypeError, ValueError):
            revision = 1
        return cls(
            goal=str(data.get("goal") or ""),
            current_request=str(data.get("currentRequest") or data.get("current_request") or ""),
            scope=cls._strings(data.get("scope")),
            constraints=cls._strings(data.get("constraints")),
            acceptance_criteria=cls._strings(data.get("acceptanceCriteria") or data.get("acceptance_criteria")),
            verified_facts=cls._strings(data.get("verifiedFacts") or data.get("verified_facts")),
            decisions=cls._strings(data.get("decisions")),
            open_items=cls._strings(data.get("openItems") or data.get("open_items")),
            completed_items=cls._strings(data.get("completedItems") or data.get("completed_items")),
            revision=revision,
        )

    @staticmethod
    def _strings(value: object) -> list[str]:
        if not isinstance(value, list):
            return []
        return [str(item).strip()[:1000] for item in value if item is not None and str(item).strip()][:20]

    def update(self, values: dict[str, Any]) -> None:
        string_fields = {
            "goal": "goal",
            "current_request": "current_request",
        }
        list_fields = {
            "scope": "scope",
            "constraints": "constraints",
            "acceptance_criteria": "acceptance_criteria",
            "verified_facts": "verified_facts",
            "decisions": "decisions",
            "open_items": "open_items",
            "completed_items": "completed_items",
        }
        for source, target in string_fields.items():
            if source in values:
                setattr(self, target, str(values[source] or "").strip())
        for source, target in list_fields.items():
            if source in values:
                setattr(self, target, self._strings(values[source]))
        self.revision += 1

    def to_payload(self) -> dict[str, Any]:
        data = asdict(self)
        return {
            "goal": data["goal"],
            "currentRequest": data["current_request"],
            "scope": data["scope"],
            "constraints": data["constraints"],
            "acceptanceCriteria": data["acceptance_criteria"],
            "verifiedFacts": data["verified_facts"],
            "decisions": data["decisions"],
            "openItems": data["open_items"],
            "completedItems": data["completed_items"],
            "revision": data["revision"],
        }

    def retrieval_query(self, prompt: str) -> str:
        parts = [prompt.strip(), self.goal, *self.scope, *self.constraints, *self.open_items]
        return "\n".join(dict.fromkeys(part for part in parts if part))
