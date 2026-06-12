from __future__ import annotations

import json
import re
import uuid
from datetime import UTC, datetime
from pathlib import Path

from typing import List

from pydantic import ValidationError

from app.services.knowledge_models import (
    KnowledgeDraft,
    KnowledgeEntry,
    KnowledgeSourceConversation,
)
from app.utils.file_store import atomic_write_json, atomic_write_text

_VALID_ENTRY_ID_PATTERN = re.compile(r"^kb_[A-Za-z0-9]+$")


class KnowledgeDocumentStore:
    def __init__(self, base_dir: Path) -> None:
        self._base_dir = base_dir
        self._entries_dir = base_dir / "entries"
        self._audit_log_path = base_dir / "audit.jsonl"

    def create(
        self,
        draft: KnowledgeDraft,
        source_conversation: KnowledgeSourceConversation,
        embedding: List[float] | None = None,
    ) -> KnowledgeEntry:
        timestamp = self._now_iso()
        entry = KnowledgeEntry(
            id=self._new_entry_id(),
            title=draft.title,
            summary=draft.summary,
            problem=draft.problem,
            diagnosis=draft.diagnosis,
            resolution=draft.resolution,
            commands=list(draft.commands),
            assets=list(draft.assets),
            tags=list(draft.tags),
            sources=list(draft.sources),
            sourceConversation=source_conversation,
            embedding=embedding,
            createdAt=timestamp,
            updatedAt=timestamp,
        )
        self._write_entry(entry)
        try:
            self._append_audit("knowledge.created", entry.id)
        except Exception:
            self._entry_path(entry.id).unlink(missing_ok=True)
            raise
        return entry

    def get(self, entry_id: str) -> KnowledgeEntry:
        path = self._entry_path(entry_id)
        payload = json.loads(path.read_text(encoding="utf-8"))
        return KnowledgeEntry.model_validate(payload)

    def list(self) -> list[KnowledgeEntry]:
        if not self._entries_dir.exists():
            return []

        entries: list[KnowledgeEntry] = []
        for path in self._entries_dir.glob("*.json"):
            entry_id = path.stem
            if not _VALID_ENTRY_ID_PATTERN.fullmatch(entry_id):
                continue
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
                entry = KnowledgeEntry.model_validate(payload)
            except (json.JSONDecodeError, OSError, ValidationError):
                continue
            if entry.id != entry_id:
                continue
            entries.append(entry)
        return sorted(entries, key=lambda entry: entry.updated_at, reverse=True)

    def update(
        self,
        entry_id: str,
        draft: KnowledgeDraft,
        source_conversation: KnowledgeSourceConversation,
        embedding: List[float] | None = None,
    ) -> KnowledgeEntry:
        existing = self.get(entry_id)
        updated = KnowledgeEntry(
            id=existing.id,
            title=draft.title,
            summary=draft.summary,
            problem=draft.problem,
            diagnosis=draft.diagnosis,
            resolution=draft.resolution,
            commands=list(draft.commands),
            assets=list(draft.assets),
            tags=list(draft.tags),
            sources=list(draft.sources),
            sourceConversation=source_conversation,
            embedding=embedding if embedding is not None else existing.embedding,
            createdAt=existing.created_at,
            updatedAt=self._now_iso(),
        )
        previous_payload = existing.model_dump(by_alias=True)
        self._write_entry(updated)
        try:
            self._append_audit("knowledge.updated", updated.id)
        except Exception:
            atomic_write_json(self._entry_path(existing.id), previous_payload)
            raise
        return updated

    def delete(self, entry_id: str) -> None:
        path = self._entry_path(entry_id)
        if not path.exists():
            return
        previous_text = path.read_text(encoding="utf-8")
        path.unlink()
        try:
            self._append_audit("knowledge.deleted", entry_id)
        except Exception:
            atomic_write_text(path, previous_text)
            raise

    def _new_entry_id(self) -> str:
        return f"kb_{uuid.uuid4().hex}"

    def _entry_path(self, entry_id: str) -> Path:
        if not _VALID_ENTRY_ID_PATTERN.fullmatch(entry_id):
            raise ValueError(f"Invalid knowledge entry id: {entry_id}")
        return self._entries_dir / f"{entry_id}.json"

    def _write_entry(self, entry: KnowledgeEntry) -> None:
        atomic_write_json(
            self._entry_path(entry.id),
            entry.model_dump(by_alias=True),
        )

    def _append_audit(self, action: str, entry_id: str) -> None:
        self._audit_log_path.parent.mkdir(parents=True, exist_ok=True)
        with self._audit_log_path.open("a", encoding="utf-8") as handle:
            handle.write(
                json.dumps(
                    {
                        "ts": self._now_iso(),
                        "action": action,
                        "entryId": entry_id,
                    },
                    ensure_ascii=False,
                )
            )
            handle.write("\n")

    def _now_iso(self) -> str:
        return datetime.now(UTC).isoformat()
