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
        try:
            self._write_entry(entry)
            self._append_audit("knowledge.created", entry.id)
        except Exception:
            self._entry_path(entry.id).unlink(missing_ok=True)
            self._markdown_path(entry.id).unlink(missing_ok=True)
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
        markdown_path = self._markdown_path(existing.id)
        previous_markdown = markdown_path.read_text(encoding="utf-8") if markdown_path.exists() else None
        try:
            self._write_entry(updated)
            self._append_audit("knowledge.updated", updated.id)
        except Exception:
            atomic_write_json(self._entry_path(existing.id), previous_payload)
            if previous_markdown is None:
                markdown_path.unlink(missing_ok=True)
            else:
                atomic_write_text(markdown_path, previous_markdown)
            raise
        return updated

    def delete(self, entry_id: str) -> None:
        path = self._entry_path(entry_id)
        if not path.exists():
            return
        previous_text = path.read_text(encoding="utf-8")
        markdown_path = self._markdown_path(entry_id)
        previous_markdown = markdown_path.read_text(encoding="utf-8") if markdown_path.exists() else None
        path.unlink()
        markdown_path.unlink(missing_ok=True)
        try:
            self._append_audit("knowledge.deleted", entry_id)
        except Exception:
            atomic_write_text(path, previous_text)
            if previous_markdown is not None:
                atomic_write_text(markdown_path, previous_markdown)
            raise

    def _new_entry_id(self) -> str:
        return f"kb_{uuid.uuid4().hex}"

    def _entry_path(self, entry_id: str) -> Path:
        if not _VALID_ENTRY_ID_PATTERN.fullmatch(entry_id):
            raise ValueError(f"Invalid knowledge entry id: {entry_id}")
        return self._entries_dir / f"{entry_id}.json"

    def _markdown_path(self, entry_id: str) -> Path:
        if not _VALID_ENTRY_ID_PATTERN.fullmatch(entry_id):
            raise ValueError(f"Invalid knowledge entry id: {entry_id}")
        return self._entries_dir / f"{entry_id}.md"

    def _write_entry(self, entry: KnowledgeEntry) -> None:
        atomic_write_json(
            self._entry_path(entry.id),
            entry.model_dump(by_alias=True),
        )
        atomic_write_text(self._markdown_path(entry.id), self._render_markdown(entry))

    def _render_markdown(self, entry: KnowledgeEntry) -> str:
        title = " ".join(entry.title.split()) or "未命名知识"
        lines = [
            f"# {title}",
            "",
            f"- 知识 ID：`{entry.id}`",
            f"- 创建时间：{entry.created_at}",
            f"- 更新时间：{entry.updated_at}",
        ]
        if entry.tags:
            lines.append(f"- 标签：{', '.join(entry.tags)}")
        if entry.source_conversation.id or entry.source_conversation.title:
            source_label = entry.source_conversation.title or entry.source_conversation.id or ""
            lines.append(f"- 来源会话：{source_label}")

        self._append_section(lines, "摘要", entry.summary)
        self._append_section(lines, "问题", entry.problem)
        self._append_section(lines, "诊断", entry.diagnosis)
        self._append_section(lines, "处置", entry.resolution)

        if entry.commands:
            lines.extend(["", "## 相关命令"])
            for index, command in enumerate(entry.commands, start=1):
                lines.extend(["", f"### 命令 {index}"])
                if command.command.strip():
                    fence = "`" * max(3, self._longest_backtick_run(command.command) + 1)
                    lines.extend(["", f"{fence}sh", command.command.strip(), fence])
                if command.purpose.strip():
                    lines.extend(["", f"- 用途：{command.purpose.strip()}"])
                if command.outcome.strip():
                    lines.append(f"- 结果：{command.outcome.strip()}")

        if entry.assets:
            lines.extend(["", "## 相关资产", ""])
            for asset in entry.assets:
                label = asset.label.strip() or "未命名资产"
                suffix = f"（ID：{asset.asset_id}）" if asset.asset_id is not None else ""
                lines.append(f"- {label}{suffix}")

        if entry.sources:
            lines.extend(["", "## 证据来源"])
            for index, source in enumerate(entry.sources, start=1):
                reference = source.event_id or (
                    f"事件 #{source.event_index}" if source.event_index is not None else source.event_type
                ) or f"来源 {index}"
                lines.extend(["", f"### {reference}"])
                if source.relevance.strip():
                    lines.extend(["", source.relevance.strip()])
                if source.quote.strip():
                    lines.extend(["", *[f"> {line}" for line in source.quote.strip().splitlines()]])

        return "\n".join(lines).rstrip() + "\n"

    def _append_section(self, lines: list[str], title: str, content: str) -> None:
        if content.strip():
            lines.extend(["", f"## {title}", "", content.strip()])

    def _longest_backtick_run(self, value: str) -> int:
        return max((len(match.group(0)) for match in re.finditer(r"`+", value)), default=0)

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
