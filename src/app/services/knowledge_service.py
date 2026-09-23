from __future__ import annotations

import json
import hashlib
import difflib
import re
from collections.abc import Mapping, Sequence
from typing import Any
from threading import RLock
from functools import wraps

from pydantic import ValidationError

from app.core.prompts.memory import build_memory_context
from app.services.knowledge_document_store import KnowledgeDocumentStore
from app.services.knowledge_models import (
    KnowledgeDraft,
    KnowledgeEntry,
    KnowledgeReindexResult,
    KnowledgeSearchFilters,
    KnowledgeSearchPage,
    KnowledgeSourceConversation,
    KnowledgeSourceRef,
    KnowledgeExtractionPlan,
    KnowledgeExtractionBatch,
)
from app.services.knowledge_search_index import KnowledgeSearchIndex
from app.services.model_service import ModelService
from app.services.redaction_service import RedactionService

_MAX_EVENT_EXCERPT = 700
_MAX_SOURCE_DOCUMENT = 24000
_KNOWLEDGE_WRITE_LOCK = RLock()


def _serialized_write(method):
    @wraps(method)
    def wrapped(*args, **kwargs):
        with _KNOWLEDGE_WRITE_LOCK:
            return method(*args, **kwargs)
    return wrapped


_MEMORY_CANDIDATE_LIMIT = 100
_MEMORY_RESULT_LIMIT = 3
_MIN_SEMANTIC_RELEVANCE = 0.35
_MIN_LEXICAL_RELEVANCE = 0.08
_RETRIEVAL_STOP_TERMS = {
    "一个", "一下", "什么", "如何", "当前", "用户", "问题", "任务", "进行", "这个", "需要",
    "agent", "please", "the", "this", "with",
}


class KnowledgeServiceError(Exception):
    pass


class RecoverableKnowledgeServiceError(KnowledgeServiceError):
    pass


class KnowledgeConversationNotFoundError(RecoverableKnowledgeServiceError):
    pass


class KnowledgeEmptySourceError(RecoverableKnowledgeServiceError):
    pass


class KnowledgeDraftGenerationError(RecoverableKnowledgeServiceError):
    pass


class KnowledgeDraftParseError(RecoverableKnowledgeServiceError):
    pass


class KnowledgeReplanError(KnowledgeDraftGenerationError):
    def __init__(self, message: str, entry_ids: list[str] | None = None):
        super().__init__(message)
        self.entry_ids = entry_ids or []


class KnowledgeVersionConflictError(RecoverableKnowledgeServiceError):
    pass


class KnowledgeIndexUpdateError(RecoverableKnowledgeServiceError):
    pass


class KnowledgeService:
    def __init__(
        self,
        conversation_service: Any,
        model_service: ModelService,
        redaction_service: RedactionService,
        document_store: KnowledgeDocumentStore,
        search_index: KnowledgeSearchIndex,
    ) -> None:
        self._conversation_service = conversation_service
        self._model_service = model_service
        self._redaction_service = redaction_service
        self._document_store = document_store
        self._search_index = search_index

    @staticmethod
    def _linked_to(entry: KnowledgeEntry, conversation_id: str) -> bool:
        return entry.source_conversation.id == conversation_id or any(
            source.conversation_id == conversation_id for source in entry.sources
        )

    def linked_entries(self, conversation_id: str) -> list[KnowledgeEntry]:
        return [entry for entry in self._document_store.list() if self._linked_to(entry, conversation_id)]

    def extraction_source(self, conversation_id: str, max_source_events: int) -> tuple[str, KnowledgeSourceConversation]:
        try:
            conversation = self._conversation_service.get_conversation(conversation_id)
        except FileNotFoundError as exc:
            raise KnowledgeConversationNotFoundError("会话不存在。") from exc
        if conversation is None:
            raise KnowledgeConversationNotFoundError("会话不存在。")
        source = self._build_source_document(conversation, max_source_events=max_source_events)
        if not source.strip():
            raise KnowledgeEmptySourceError("当前会话没有可提炼的内容。")
        snapshot = KnowledgeSourceConversation.model_validate(self._redaction_service.redact_value(
            self._source_conversation_snapshot(conversation).model_dump(by_alias=True),
        ))
        return self._redaction_service.redact_text(source), snapshot

    def extraction_batches(self, conversation_id: str, max_source_events: int = 120) -> tuple[list[KnowledgeExtractionBatch], KnowledgeSourceConversation]:
        try:
            conversation = self._conversation_service.get_conversation(conversation_id)
        except FileNotFoundError as exc:
            raise KnowledgeConversationNotFoundError("会话不存在。") from exc
        source = KnowledgeSourceConversation.model_validate(self._redaction_service.redact_value(
            self._source_conversation_snapshot(conversation).model_dump(by_alias=True),
        ))
        processed = self._document_store.processed_fingerprints(conversation_id)
        parts: list[tuple[str, str]] = []
        chain = conversation_id
        useful = False
        for index, event in enumerate(conversation.events):
            if not isinstance(event, Mapping):
                continue
            # A completed replacement changes the hash chain, so unfinished messages are not checkpointed.
            if event.get("partial") is True:
                continue
            text = self._normalize_event(event, index, limit=None)
            if not text:
                continue
            useful = True
            text = self._redaction_service.redact_text(text)
            for offset in range(0, len(text), 16000):
                part = text[offset:offset + 16000]
                chain = hashlib.sha256((chain + '\n' + part).encode()).hexdigest()
                if chain not in processed:
                    parts.append((chain, f"{text.splitlines()[0]}\nEvidence part {offset // 16000 + 1}\n{part}"))
        if not useful:
            raise KnowledgeEmptySourceError("当前会话没有可提炼的完整内容。")
        batches: list[KnowledgeExtractionBatch] = []
        texts: list[str] = []
        fingerprints: list[str] = []
        header = f"Conversation: {source.id}\nTitle: {source.title}\n"
        def flush() -> None:
            if not texts:
                return
            key = hashlib.sha256((conversation_id + '\n' + '\n'.join(fingerprints)).encode()).hexdigest()
            batches.append(KnowledgeExtractionBatch(key=key, document=header + '\n\n'.join(texts), fingerprints=list(fingerprints)))
            texts.clear()
            fingerprints.clear()
        for fingerprint, text in parts:
            if texts and (len(texts) >= max(1, max_source_events) or sum(map(len, texts)) + len(text) > _MAX_SOURCE_DOCUMENT - len(header) - 100):
                flush()
            texts.append(text)
            fingerprints.append(fingerprint)
        flush()
        return batches, source

    def recover_extraction_batches(self) -> None:
        with _KNOWLEDGE_WRITE_LOCK:
            if self._document_store.recover_batches():
                self._search_index.rebuild(self._document_store.list())

    def versions(self, entry_id: str) -> list[dict[str, str]]:
        return self._document_store.versions(entry_id)

    def version_preview(self, entry_id: str, version_id: str) -> dict[str, str]:
        previous = self._document_store.version(entry_id, version_id)
        current = self.get_entry(entry_id)
        old_text = self._document_store.render_markdown(previous)
        current_text = self._document_store.render_markdown(current)
        difference = '\n'.join(difflib.unified_diff(current_text.splitlines(), old_text.splitlines(), fromfile='当前版本', tofile='选中版本', lineterm=''))
        return {"markdown": old_text, "diff": difference, "currentUpdatedAt": current.updated_at}

    @_serialized_write
    def restore_version(self, entry_id: str, version_id: str, expected_updated_at: str) -> KnowledgeEntry:
        current = self.get_entry(entry_id)
        if current.updated_at != expected_updated_at:
            raise KnowledgeVersionConflictError("文件已有新修改，请重新查看差异后恢复。")
        previous = self._document_store.version(entry_id, version_id)
        # A restore is itself an update: the replaced content gets its own recoverable version.
        return self.update_entry(entry_id, KnowledgeDraft.model_validate(previous.model_dump()), previous.source_conversation)

    def extract_and_save(self, source_document: str, source: KnowledgeSourceConversation, *, model_name: str | None = None, on_saved=None, batch_key: str | None = None, fingerprints: list[str] | None = None, feedback: str = "", preferred_entry_ids: list[str] | None = None) -> None:
        if batch_key and (receipt := self._document_store.receipt(batch_key)) is not None:
            for result in receipt["results"]:
                try:
                    entry = self.get_entry(result["entry_id"])
                    self._search_index.index_entry(entry, entry.embedding or [])
                except FileNotFoundError:
                    pass
                if on_saved:
                    on_saved(result["action"], result["entry_id"])
            return
        entries = self._document_store.list()
        # Include linked notes first, then relevant notes from other conversations.
        entries.sort(key=lambda entry: (entry.id in (preferred_entry_ids or []), self._linked_to(entry, source.id or ""), self._lexical_relevance(source_document, entry)), reverse=True)
        candidates: dict[str, KnowledgeEntry] = {}
        documents = []
        size = 0
        for entry in entries:
            if entry.id not in (preferred_entry_ids or []) and not self._linked_to(entry, source.id or "") and self._lexical_relevance(source_document, entry) < _MIN_LEXICAL_RELEVANCE:
                continue
            payload = entry.model_dump(by_alias=True, exclude={"embedding"})
            length = len(json.dumps(payload, ensure_ascii=False))
            if size + length > 60000:
                continue
            candidates[entry.id] = entry
            documents.append(payload)
            size += length
            if len(documents) >= 30:
                break
        raw = self._model_service.plan_knowledge_extraction(
            source_document, self._redaction_service.redact_text(json.dumps(documents, ensure_ascii=False)), model_name=model_name, feedback=feedback,
        )
        try:
            plan = KnowledgeExtractionPlan.model_validate_json(raw)
        except (ValueError, ValidationError) as exc:
            raise KnowledgeDraftParseError("AI 返回的知识整理结果格式不正确，请重试。") from exc
        seen = set()
        titles = set()
        for action in plan.actions:
            if action.action == "create":
                if action.entry_id is not None:
                    raise KnowledgeDraftParseError("新建知识不能指定已有文件。")
            elif not action.entry_id or action.entry_id not in candidates or action.entry_id in seen:
                raise KnowledgeDraftParseError("AI 选择了无效或重复的知识文件，请重试。")
            if action.entry_id:
                seen.add(action.entry_id)
            if action.action != "keep":
                draft = action.draft
                if draft is None or not draft.title.strip() or not any(text.strip() for text in (draft.summary, draft.problem, draft.diagnosis, draft.resolution)):
                    raise KnowledgeDraftParseError("AI 返回了空的知识文件，请重试。")
                title = " ".join(draft.title.lower().split())
                if title in titles:
                    raise KnowledgeDraftParseError("AI 返回了重复的知识主题，请重试。")
                titles.add(title)
                action.draft = self._redact_draft(draft)
        # Validate every update before writing, and don't overwrite a manual edit made while AI was running.
        with _KNOWLEDGE_WRITE_LOCK:
            existing_titles = {" ".join(entry.title.lower().split()): entry.id for entry in self._document_store.list()}
            collisions = [existing_titles[" ".join(action.draft.title.lower().split())] for action in plan.actions if action.action == "create" and action.draft is not None and " ".join(action.draft.title.lower().split()) in existing_titles]
            if collisions:
                raise KnowledgeReplanError("同名知识文件已存在，请对已有文件使用 update 合并完整内容，或使用 keep。", collisions)
            for entry_id in seen:
                try:
                    current = self.get_entry(entry_id)
                except FileNotFoundError as exc:
                    raise KnowledgeReplanError("知识文件已被删除，请依据当前文件重新规划。") from exc
                if current.updated_at != candidates[entry_id].updated_at:
                    raise KnowledgeReplanError("知识文件已被修改，请合并最新内容。", [entry_id])
            results: list[dict[str, str]] = []
            receipt = {"conversation_id": source.id, "fingerprints": fingerprints or [], "results": results}
            try:
                with self._document_store.batch_transaction(batch_key, receipt):
                    for action in plan.actions:
                        existing = candidates.get(action.entry_id or "")
                        draft = action.draft
                        if action.action == "keep":
                            assert existing is not None
                            draft = KnowledgeDraft.model_validate(existing.model_dump())
                        assert draft is not None
                        # Preserve earlier provenance and attach this conversation even when no text changes.
                        refs = list(existing.sources) if existing else []
                        for ref in draft.sources:
                            if ref in refs:
                                continue
                            normalized = ref.model_copy(update={"conversation_id": source.id})
                            if normalized not in refs:
                                refs.append(normalized)
                        if not any(ref.conversation_id == source.id for ref in refs):
                            refs.append(KnowledgeSourceRef(conversationId=source.id, relevance="提炼来源会话"))
                        draft = draft.model_copy(update={"sources": refs})
                        if existing:
                            if action.action == "keep" and self._linked_to(existing, source.id or ""):
                                entry = existing
                            else:
                                entry = self.update_entry(existing.id, draft, existing.source_conversation)
                        else:
                            entry = self.create_entry(draft, source)
                        results.append({"action": action.action, "entry_id": entry.id})
            except Exception:
                if batch_key:
                    self._search_index.rebuild(self._document_store.list())
                raise
            for result in results:
                if on_saved:
                    on_saved(result["action"], result["entry_id"])

    def generate_draft_from_conversation(
        self,
        conversation_id: str,
        *,
        max_source_events: int = 120,
        model_name: str | None = None,
    ) -> tuple[KnowledgeDraft, KnowledgeSourceConversation]:
        try:
            conversation = self._conversation_service.get_conversation(conversation_id)
        except Exception as exc:
            raise KnowledgeConversationNotFoundError(f"Conversation not found: {conversation_id}") from exc
        if conversation is None:
            raise KnowledgeConversationNotFoundError(f"Conversation not found: {conversation_id}")

        source_document = self._build_source_document(conversation, max_source_events=max_source_events)
        if not source_document.strip():
            raise KnowledgeEmptySourceError("Conversation does not contain useful knowledge source events.")

        redacted_document = self._redaction_service.redact_text(source_document)
        try:
            raw_draft = self._model_service.generate_knowledge_draft(
                redacted_document,
                model_name=model_name,
            )
        except Exception as exc:
            raise KnowledgeDraftGenerationError("Failed to generate knowledge draft.") from exc

        draft = self._parse_draft(raw_draft)
        redacted_payload = self._redaction_service.redact_value(draft.model_dump(by_alias=True))
        try:
            redacted_draft = KnowledgeDraft.model_validate(redacted_payload)
        except ValidationError as exc:
            raise KnowledgeDraftParseError("Generated knowledge draft failed validation after redaction.") from exc

        return redacted_draft, self._source_conversation_snapshot(conversation)

    @_serialized_write
    def create_entry(
        self,
        draft: KnowledgeDraft,
        source_conversation: KnowledgeSourceConversation,
    ) -> KnowledgeEntry:
        redacted_draft = self._redact_draft(draft)
        embedding = None
        try:
            text = f"{redacted_draft.title}\n{redacted_draft.summary}\n{redacted_draft.problem}\n{redacted_draft.resolution}"
            embedding = self._model_service.generate_embedding(text)
        except Exception:
            embedding = []

        entry = self._document_store.create(redacted_draft, source_conversation, embedding=embedding)
        try:
            self._search_index.index_entry(entry, embedding)
        except Exception as exc:
            raise KnowledgeIndexUpdateError("Knowledge entry was saved but search index update failed. Reindex is required.") from exc
        return entry

    def get_entry(self, entry_id: str) -> KnowledgeEntry:
        return self._document_store.get(entry_id)

    def markdown(self, entry_id: str) -> str:
        return self._document_store.render_markdown(self.get_entry(entry_id))

    @_serialized_write
    def update_entry(
        self,
        entry_id: str,
        draft: KnowledgeDraft,
        source_conversation: KnowledgeSourceConversation,
    ) -> KnowledgeEntry:
        redacted_draft = self._redact_draft(draft)
        embedding = None
        try:
            text = f"{redacted_draft.title}\n{redacted_draft.summary}\n{redacted_draft.problem}\n{redacted_draft.resolution}"
            embedding = self._model_service.generate_embedding(text)
        except Exception:
            embedding = []

        entry = self._document_store.update(entry_id, redacted_draft, source_conversation, embedding=embedding)
        try:
            self._search_index.index_entry(entry, embedding)
        except Exception as exc:
            raise KnowledgeIndexUpdateError("Knowledge entry was updated but search index update failed. Reindex is required.") from exc
        return entry

    @_serialized_write
    def delete_entry(self, entry_id: str) -> None:
        try:
            self._search_index.delete_entry(entry_id)
        except Exception as exc:
            raise KnowledgeIndexUpdateError("Knowledge entry was not deleted because search index cleanup failed. Reindex is required.") from exc
        self._document_store.delete(entry_id)

    def search(self, filters: KnowledgeSearchFilters) -> KnowledgeSearchPage:
        query_embedding = None
        if filters.query.strip():
            try:
                query_embedding = self._model_service.generate_embedding(filters.query)
            except Exception:
                pass

        if not query_embedding or filters.source_conversation_id:
            entries = self._document_store.list()
            entries = [entry for entry in entries if (
                (not filters.source_conversation_id or self._linked_to(entry, filters.source_conversation_id))
                and (filters.asset_id is None or any(asset.asset_id == filters.asset_id for asset in entry.assets))
                and (not filters.tag or filters.tag.lower() in [tag.lower() for tag in entry.tags])
                and (not filters.query.strip() or self._lexical_relevance(filters.query, entry) > 0)
            )]
            if filters.query.strip():
                entries.sort(key=lambda entry: self._lexical_relevance(filters.query, entry), reverse=True)
            limit, offset = min(100, max(1, filters.limit)), max(0, filters.offset)
            return KnowledgeSearchPage(items=entries[offset:offset + limit], total=len(entries), limit=limit, offset=offset)

        hits = self._search_index.search(query_embedding, filters)
        total = self._search_index.count(filters)
        items: list[KnowledgeEntry] = []
        for hit in hits:
            try:
                items.append(self._document_store.get(hit.entry_id))
            except FileNotFoundError:
                continue
        return KnowledgeSearchPage(
            items=items,
            total=total,
            limit=filters.limit,
            offset=filters.offset,
        )

    @_serialized_write
    def reindex(self) -> KnowledgeReindexResult:
        entries = self._document_store.list()
        healed_entries = []
        for entry in entries:
            if not entry.embedding:
                try:
                    text = f"{entry.title}\n{entry.summary}\n{entry.problem}\n{entry.resolution}"
                    embedding = self._model_service.generate_embedding(text)
                    draft = KnowledgeDraft(
                        title=entry.title,
                        summary=entry.summary,
                        problem=entry.problem,
                        diagnosis=entry.diagnosis,
                        resolution=entry.resolution,
                        commands=entry.commands,
                        assets=entry.assets,
                        tags=entry.tags,
                        sources=entry.sources,
                    )
                    entry = self._document_store.update(entry.id, draft, entry.source_conversation, embedding=embedding)
                except Exception:
                    pass
            healed_entries.append(entry)
        return self._search_index.rebuild(healed_entries)

    def search_for_agent(
        self,
        prompt: str,
        asset_label: str = "",
        asset_group: str = "",
        conversation_id: str | None = None,
    ) -> list[KnowledgeEntry]:
        query = " ".join(part.strip() for part in [prompt, asset_label, asset_group] if part.strip())
        if not query or not self._search_index.has_entries():
            return []

        query_embedding = None
        try:
            query_embedding = self._model_service.generate_embedding(query)
        except Exception:
            pass

        hits = self._search_index.search(
            query_embedding,
            KnowledgeSearchFilters(
                query=query,
                limit=_MEMORY_CANDIDATE_LIMIT,
                offset=0,
            ),
        )
        ranked: list[tuple[float, KnowledgeEntry]] = []
        for hit in hits:
            try:
                entry = self._document_store.get(hit.entry_id)
            except FileNotFoundError:
                continue
            if conversation_id and self._linked_to(entry, conversation_id):
                continue
            lexical_score = self._lexical_relevance(query, entry)
            semantic_score = hit.score if query_embedding else 0.0
            if semantic_score < _MIN_SEMANTIC_RELEVANCE and lexical_score < _MIN_LEXICAL_RELEVANCE:
                continue
            ranked.append((semantic_score + lexical_score * 0.35, entry))

        ranked.sort(key=lambda item: (-item[0], item[1].id))
        return [entry for _, entry in ranked[:_MEMORY_RESULT_LIMIT]]

    def format_agent_context(self, entries: list[KnowledgeEntry], *, usage_prompt: str | None = None) -> str:
        sections: list[str] = []
        for index, entry in enumerate(entries[:3], start=1):
            assets = ", ".join(
                asset.label or str(asset.asset_id)
                for asset in entry.assets
                if asset.label or asset.asset_id is not None
            )
            source = entry.source_conversation.title or entry.source_conversation.id or "unknown"
            section = "\n".join(
                [
                    f"Relevant memory {index}",
                    f"Memory ID: {entry.id}",
                    f"Title: {entry.title}",
                    f"Assets: {assets or 'unknown'}",
                    f"Updated: {entry.updated_at}",
                    f"Summary: {entry.summary}",
                    f"Problem: {entry.problem}",
                    f"Diagnosis: {entry.diagnosis}",
                    f"Resolution: {entry.resolution}",
                    f"Source: {source}",
                ]
            )
            sections.append(self._truncate(section, 600))

        return build_memory_context(sections, guidance=usage_prompt)

    def _lexical_relevance(self, query: str, entry: KnowledgeEntry) -> float:
        query_terms = self._retrieval_terms(query)
        if not query_terms:
            return 0.0
        entry_text = "\n".join(
            [
                entry.title,
                entry.summary,
                entry.problem,
                entry.diagnosis,
                entry.resolution,
                " ".join(entry.tags),
                " ".join(asset.label for asset in entry.assets),
                " ".join(command.command for command in entry.commands),
            ]
        )
        entry_terms = self._retrieval_terms(entry_text)
        if not entry_terms:
            return 0.0
        overlap = query_terms & entry_terms
        return len(overlap) / max(1, min(len(query_terms), len(entry_terms)))

    def _retrieval_terms(self, value: str) -> set[str]:
        normalized = value.lower()
        terms = set(re.findall(r"[a-z0-9][a-z0-9_.:/-]{1,}", normalized))
        for sequence in re.findall(r"[\u4e00-\u9fff]{2,}", normalized):
            terms.update(sequence[index:index + 2] for index in range(len(sequence) - 1))
        return {term for term in terms if term not in _RETRIEVAL_STOP_TERMS}

    def _parse_draft(self, raw_draft: str) -> KnowledgeDraft:
        try:
            payload = json.loads(raw_draft)
        except json.JSONDecodeError as exc:
            raise KnowledgeDraftParseError("Model returned invalid JSON for knowledge draft.") from exc
        if not isinstance(payload, dict):
            raise KnowledgeDraftParseError("Model returned a non-object knowledge draft.")
        try:
            return KnowledgeDraft.model_validate(payload)
        except ValidationError as exc:
            raise KnowledgeDraftParseError("Model returned a knowledge draft with invalid fields.") from exc

    def _redact_draft(self, draft: KnowledgeDraft) -> KnowledgeDraft:
        payload = self._redaction_service.redact_value(draft.model_dump(by_alias=True))
        try:
            return KnowledgeDraft.model_validate(payload)
        except ValidationError as exc:
            raise KnowledgeDraftParseError("Knowledge draft failed validation after redaction.") from exc

    def _build_source_document(self, conversation: Any, *, max_source_events: int) -> str:
        events = getattr(conversation, "events", [])
        if not isinstance(events, Sequence):
            return ""

        lines = [
            f"Conversation: {self._safe_string(getattr(conversation, 'id', ''))}",
            f"Title: {self._safe_string(getattr(conversation, 'title', ''))}",
            f"Updated: {self._safe_string(getattr(conversation, 'updated_at', ''))}",
        ]
        useful = 0
        normalized_limit = max(1, max_source_events)
        for event_index, event in reversed(list(enumerate(events))):
            if useful >= normalized_limit:
                break
            if not isinstance(event, Mapping):
                continue
            event_text = self._normalize_event(event, event_index)
            if not event_text:
                continue
            if sum(len(line) for line in lines) + len(event_text) > _MAX_SOURCE_DOCUMENT - 100:
                break
            lines.insert(3, event_text)
            useful += 1

        if useful == 0:
            return ""
        return self._truncate("\n\n".join(lines), _MAX_SOURCE_DOCUMENT)

    def _normalize_event(self, event: Mapping[str, Any], event_index: int, *, limit: int | None = _MAX_EVENT_EXCERPT) -> str:
        if event.get("partial") is True:
            return ""
        event_type = self._first_string(event, ["kind", "type", "event_type", "eventType"])
        lowered_type = event_type.lower()
        text = self._event_text(event, limit=limit)
        if not self._is_useful_event(lowered_type, text):
            return ""

        event_id = self._first_string(event, ["id", "event_id", "eventId"])
        source_index = self._event_index(event, event_index)
        header_parts = [f"EventIndex: {source_index}"]
        if event_id:
            header_parts.append(f"EventId: {event_id}")
        if event_type:
            header_parts.append(f"Type: {event_type}")
        return "\n".join([" | ".join(header_parts), self._truncate(text, limit) if limit else text])

    def _event_text(self, event: Mapping[str, Any], *, limit: int | None = _MAX_EVENT_EXCERPT) -> str:
        parts: list[str] = []
        for key in ["text", "message", "content", "command", "output", "toolOutput", "exitCode", "error", "status", "result"]:
            value = event.get(key)
            text = self._stringify_value(value)
            if text:
                parts.append(f"{key}: {text}")

        for nested_key in ["data", "payload", "details", "approval", "tool", "toolCall", "assistant"]:
            nested = event.get(nested_key)
            if isinstance(nested, Mapping):
                nested_text = self._event_text(nested, limit=limit)
                if nested_text:
                    parts.append(f"{nested_key}: {nested_text}")
            elif isinstance(nested, list):
                nested_text = self._stringify_value(nested)
                if nested_text:
                    parts.append(f"{nested_key}: {nested_text}")

        text = "\n".join(dict.fromkeys(parts))
        return self._truncate(text, limit) if limit else text

    def _is_useful_event(self, event_type: str, text: str) -> bool:
        if not text.strip():
            return False
        useful_markers = [
            "message",
            "user",
            "assistant",
            "final",
            "conclusion",
            "command",
            "tool",
            "approval",
            "denied",
            "error",
            "stderr",
            "stdout",
            "output",
        ]
        if any(marker in event_type for marker in useful_markers):
            return True
        lowered_text = text.lower()
        return any(marker in lowered_text for marker in ["command:", "output:", "error:", "approval", "denied"])

    def _source_conversation_snapshot(self, conversation: Any) -> KnowledgeSourceConversation:
        return KnowledgeSourceConversation(
            id=self._safe_string(getattr(conversation, "id", "")) or None,
            title=self._safe_string(getattr(conversation, "title", "")),
            updatedAt=self._safe_string(getattr(conversation, "updated_at", "")) or None,
        )

    def _first_string(self, mapping: Mapping[str, Any], keys: list[str]) -> str:
        for key in keys:
            value = mapping.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return ""

    def _event_index(self, event: Mapping[str, Any], fallback: int) -> int:
        for key in ["eventIndex", "event_index", "index", "sequence"]:
            value = event.get(key)
            if isinstance(value, int):
                return value
            if isinstance(value, str) and value.isdigit():
                return int(value)
        return fallback

    def _stringify_value(self, value: object) -> str:
        if value is None:
            return ""
        if isinstance(value, str):
            return value.strip()
        if isinstance(value, (int, float, bool)):
            return str(value)
        if isinstance(value, Mapping):
            compact = {str(key): item for key, item in value.items() if item not in (None, "", [], {})}
            if not compact:
                return ""
            return json.dumps(compact, ensure_ascii=False, default=str)
        if isinstance(value, list):
            items = [self._stringify_value(item) for item in value]
            return "\n".join(item for item in items if item)
        return str(value).strip()

    def _safe_string(self, value: object) -> str:
        return value if isinstance(value, str) else ""

    def _truncate(self, text: str, limit: int) -> str:
        if len(text) <= limit:
            return text
        return text[: max(0, limit - 3)].rstrip() + "..."
