from __future__ import annotations

import hashlib
import json
import os
import tempfile
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping

from app.core.loop.prompt_defaults import DEFAULT_PROMPTS
from app.shared import config as shared_config


PROMPT_KEYS = (
    "agentBehavior",
    "incidentResponse",
    "knowledgeExtraction",
    "memoryUsage",
    "organizationRules",
)
MAX_PROMPT_CHARS = 8_000

IMMUTABLE_SAFETY_SUMMARY = (
    "Command execution must use authenticated tools and real tool results; command approvals, asset scope and "
    "whitelists, terminal authorization, secret protection, cancellation/recovery limits, tool protocol, and the "
    "strict knowledge JSON schema cannot be overridden here."
)


class PromptSettingsConflictError(Exception):
    pass


@dataclass(frozen=True, slots=True)
class PromptSettingsSnapshot:
    schema_version: int
    revision: int
    overrides: dict[str, str]
    defaults: dict[str, str]
    effective: dict[str, str]
    updated_at: str | None
    immutable_safety_summary: str = IMMUTABLE_SAFETY_SUMMARY

    def to_dict(self) -> dict[str, object]:
        return {
            "schemaVersion": self.schema_version,
            "revision": self.revision,
            "overrides": dict(self.overrides),
            "defaults": dict(self.defaults),
            "effective": dict(self.effective),
            "updatedAt": self.updated_at,
            "immutableSafetySummary": self.immutable_safety_summary,
            "maxPromptChars": MAX_PROMPT_CHARS,
        }


class PromptSettingsService:
    def __init__(self, settings_path: Path | None = None, audit_path: Path | None = None) -> None:
        self._settings_path = settings_path or shared_config.PROMPT_SETTINGS_PATH
        self._audit_path = audit_path or shared_config.PROMPT_SETTINGS_AUDIT_PATH
        self._lock = threading.RLock()

    def get_snapshot(self) -> PromptSettingsSnapshot:
        with self._lock:
            payload = self._read()
            overrides = self._normalize_overrides(payload.get("overrides", {}))
            revision_value = payload.get("revision", 0)
            revision = revision_value if isinstance(revision_value, int) and revision_value >= 0 else 0
            updated_at_value = payload.get("updatedAt")
            updated_at = updated_at_value if isinstance(updated_at_value, str) else None
            effective = {
                key: overrides[key] if overrides[key] else DEFAULT_PROMPTS[key]
                for key in PROMPT_KEYS
            }
            return PromptSettingsSnapshot(
                schema_version=1,
                revision=revision,
                overrides=overrides,
                defaults=dict(DEFAULT_PROMPTS),
                effective=effective,
                updated_at=updated_at,
            )

    def preview(self, overrides: Mapping[str, object]) -> PromptSettingsSnapshot:
        current = self.get_snapshot()
        normalized = self._normalize_overrides(overrides)
        return PromptSettingsSnapshot(
            schema_version=1,
            revision=current.revision,
            overrides=normalized,
            defaults=dict(DEFAULT_PROMPTS),
            effective={key: normalized[key] or DEFAULT_PROMPTS[key] for key in PROMPT_KEYS},
            updated_at=current.updated_at,
        )

    def update(self, revision: int, overrides: Mapping[str, object]) -> PromptSettingsSnapshot:
        with self._lock:
            current = self.get_snapshot()
            if revision != current.revision:
                raise PromptSettingsConflictError(
                    f"Prompt settings changed from revision {revision} to {current.revision}; reload before saving."
                )
            normalized = self._normalize_overrides(overrides)
            updated_at = datetime.now(timezone.utc).isoformat()
            payload = {
                "schemaVersion": 1,
                "revision": current.revision + 1,
                "overrides": normalized,
                "updatedAt": updated_at,
            }
            self._write_json_atomic(payload)
            self._append_audit(current.overrides, normalized, payload["revision"], updated_at)
            return self.get_snapshot()

    def reset(self, revision: int) -> PromptSettingsSnapshot:
        return self.update(revision, {})

    def _read(self) -> dict[str, object]:
        if not self._settings_path.exists():
            return {"schemaVersion": 1, "revision": 0, "overrides": {}, "updatedAt": None}
        try:
            payload = json.loads(self._settings_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError("Prompt settings file is unreadable or invalid JSON.") from exc
        if not isinstance(payload, dict):
            raise ValueError("Prompt settings must be a JSON object.")
        return payload

    def _normalize_overrides(self, value: Mapping[str, object] | object) -> dict[str, str]:
        source = value if isinstance(value, Mapping) else {}
        unknown = set(source) - set(PROMPT_KEYS)
        if unknown:
            raise ValueError(f"Unknown prompt setting: {sorted(unknown)[0]}")
        normalized: dict[str, str] = {}
        for key in PROMPT_KEYS:
            raw = source.get(key, "")
            if not isinstance(raw, str):
                raise ValueError(f"Prompt override {key} must be text.")
            text = raw.replace("\x00", "").strip()
            if len(text) > MAX_PROMPT_CHARS:
                raise ValueError(f"Prompt override {key} exceeds {MAX_PROMPT_CHARS} characters.")
            normalized[key] = text
        return normalized

    def _write_json_atomic(self, payload: dict[str, object]) -> None:
        self._settings_path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary_name = tempfile.mkstemp(prefix="prompt-settings-", suffix=".tmp", dir=self._settings_path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=False, indent=2)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_name, self._settings_path)
        finally:
            if os.path.exists(temporary_name):
                os.unlink(temporary_name)

    def _append_audit(self, before: dict[str, str], after: dict[str, str], revision: int, updated_at: str) -> None:
        changed = [key for key in PROMPT_KEYS if before.get(key, "") != after.get(key, "")]
        digest = hashlib.sha256(json.dumps(after, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
        record = {"revision": revision, "updatedAt": updated_at, "changedKeys": changed, "contentSha256": digest}
        self._audit_path.parent.mkdir(parents=True, exist_ok=True)
        with self._audit_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")


_prompt_settings_service = PromptSettingsService()


def get_prompt_settings_service() -> PromptSettingsService:
    return _prompt_settings_service
