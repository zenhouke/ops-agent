from __future__ import annotations

import json
import hashlib
from contextlib import contextmanager
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
        self._pending_batch: tuple[Path, dict] | None = None

    def versions(self, entry_id: str) -> list[dict[str, str]]:
        self.get(entry_id)
        directory = self._version_dir(entry_id)
        items = []
        for path in directory.glob('v_*.json'):
            try:
                entry = KnowledgeEntry.model_validate_json(path.read_text(encoding='utf-8'))
                if entry.id == entry_id:
                    items.append({'id': path.stem, 'updatedAt': entry.updated_at, 'title': entry.title})
            except (ValueError, OSError):
                continue
        return sorted(items, key=lambda item: item['updatedAt'], reverse=True)

    def version(self, entry_id: str, version_id: str) -> KnowledgeEntry:
        if not re.fullmatch(r'v_[a-f0-9]{64}', version_id):
            raise ValueError('Invalid knowledge version')
        entry = KnowledgeEntry.model_validate_json((self._version_dir(entry_id) / f'{version_id}.json').read_text(encoding='utf-8'))
        if entry.id != entry_id:
            raise ValueError('Knowledge version does not belong to entry')
        return entry

    def _version_dir(self, entry_id: str) -> Path:
        self._entry_path(entry_id)
        return self._base_dir / 'versions' / entry_id

    def _save_version(self, entry: KnowledgeEntry) -> None:
        payload = entry.model_dump(by_alias=True)
        digest = hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        path = self._version_dir(entry.id) / f'v_{digest}.json'
        if not path.exists():
            atomic_write_json(path, payload)

    def receipt(self, key: str) -> dict | None:
        if not re.fullmatch(r'[a-f0-9]{64}', key):
            raise ValueError('Invalid extraction batch key')
        path = self._base_dir / 'receipts' / f'{key}.json'
        return json.loads(path.read_text(encoding='utf-8')) if path.exists() else None

    def processed_fingerprints(self, conversation_id: str) -> set[str]:
        fingerprints: set[str] = set()
        for path in (self._base_dir / 'receipts').glob('*.json'):
            payload = json.loads(path.read_text(encoding='utf-8'))
            if payload.get('conversation_id') == conversation_id:
                fingerprints.update(payload.get('fingerprints', []))
        return fingerprints

    def recover_batches(self) -> bool:
        recovered = False
        for path in (self._base_dir / 'pending_batches').glob('*.json'):
            journal = json.loads(path.read_text(encoding='utf-8'))
            if self.receipt(path.stem) is None:
                self._rollback(journal)
                recovered = True
            path.unlink()
        return recovered

    def _rollback(self, journal: dict) -> None:
        for entry_id, original in journal.items():
            if original is None:
                self._entry_path(entry_id).unlink(missing_ok=True)
                self._markdown_path(entry_id).unlink(missing_ok=True)
            else:
                self._write_entry(KnowledgeEntry.model_validate(original))

    @contextmanager
    def batch_transaction(self, key: str | None, receipt: dict):
        if key is None:
            yield
            return
        self.receipt(key)  # validate before building a filesystem path
        path = self._base_dir / 'pending_batches' / f'{key}.json'
        self._pending_batch = (path, {})
        atomic_write_json(path, {})
        try:
            yield
            # This durable receipt is the commit point; restart replays the result, not the model call.
            atomic_write_json(self._base_dir / 'receipts' / f'{key}.json', receipt)
        except Exception:
            self._rollback(self._pending_batch[1])
            path.unlink(missing_ok=True)
            raise
        else:
            path.unlink(missing_ok=True)
        finally:
            self._pending_batch = None

    def _track_before_write(self, entry_id: str) -> None:
        if self._pending_batch is None:
            return
        path, originals = self._pending_batch
        if entry_id not in originals:
            originals[entry_id] = self.get(entry_id).model_dump(by_alias=True) if self._entry_path(entry_id).exists() else None
            atomic_write_json(path, originals)

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
        self._track_before_write(entry.id)
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
        self._track_before_write(entry_id)
        self._save_version(existing)
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
        atomic_write_text(self._markdown_path(entry.id), self.render_markdown(entry))

    def render_markdown(self, entry: KnowledgeEntry) -> str:
        title = " ".join(entry.title.split()) or "未命名知识"
        lines = [
            f"# {title}",
            "",
            f"- 创建时间：{entry.created_at}",
            f"- 更新时间：{entry.updated_at}",
        ]
        if entry.tags:
            lines.append(f"- 标签：{', '.join(entry.tags)}")
        if entry.source_conversation.id or entry.source_conversation.title:
            source_label = entry.source_conversation.title or "关联会话"
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
                lines.extend(["", f"### 来源 {index}"])
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
