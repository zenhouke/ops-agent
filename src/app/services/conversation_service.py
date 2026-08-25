from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import logging
from datetime import UTC, datetime
from pathlib import Path
import re
import threading
from uuid import uuid4

from app.utils.file_store import atomic_write_json

logger = logging.getLogger(__name__)
CONVERSATION_ID_PATTERN = re.compile(r"^conv_[A-Za-z0-9]+$")


@dataclass
class ConversationSummary:
    id: str
    title: str
    selected_model: str | None
    created_at: str
    updated_at: str
    event_count: int
    last_event_kind: str | None


@dataclass
class ConversationDetail:
    id: str
    title: str
    selected_model: str | None
    created_at: str
    updated_at: str
    event_count: int
    last_event_kind: str | None
    events: list[dict]


@dataclass
class ConversationEventsPage:
    conversation: ConversationSummary
    events: list[dict]
    offset: int
    limit: int
    total: int
    has_more_before: bool
    has_more_after: bool


class ConversationService:
    _lock_guard = threading.Lock()
    _locks: dict[Path, threading.RLock] = {}

    def __init__(self, base_dir: Path, model_service=None):
        self._base_dir = Path(base_dir)
        self._model_service = model_service
        lock_key = self._base_dir.resolve()
        with self._lock_guard:
            self._lock = self._locks.setdefault(lock_key, threading.RLock())

    @property
    def base_dir(self) -> Path:
        return self._base_dir

    def create_conversation(self, selected_model: str | None) -> ConversationSummary:
        conversation_id = f"conv_{uuid4().hex}"
        timestamp = self._utc_now()
        detail = ConversationDetail(
            id=conversation_id,
            title="New",
            selected_model=selected_model,
            created_at=timestamp,
            updated_at=timestamp,
            event_count=0,
            last_event_kind=None,
            events=[],
        )
        with self._lock:
            self._ensure_base_dir()
            self._write_detail(detail)
            self._upsert_summary(detail)
        return self._to_summary(detail)

    def branch_conversation(
        self,
        conversation_id: str,
        *,
        before_event_id: str | None = None,
        through_event_id: str | None = None,
    ) -> ConversationDetail:
        if before_event_id and through_event_id:
            raise ValueError("Choose either before_event_id or through_event_id.")
        with self._lock:
            source = self.get_conversation(conversation_id)
            boundary_id = before_event_id or through_event_id
            boundary_index = len(source.events) - 1
            if boundary_id:
                boundary_index = next(
                    (
                        index
                        for index, event in enumerate(source.events)
                        if event.get("id") == boundary_id or event.get("eventId") == boundary_id
                    ),
                    -1,
                )
                if boundary_index < 0:
                    raise ValueError("Branch event not found.")
            copied_end = boundary_index if before_event_id else boundary_index + 1
            timestamp = self._utc_now()
            branch_event = {
                "id": f"branch-{uuid4().hex}",
                "kind": "conversation_branch",
                "sourceConversationId": source.id,
                "sourceEventId": boundary_id,
            }
            copied_events = [self._sanitize_event(dict(event)) for event in source.events[:copied_end]]
            events = [branch_event, *copied_events]
            detail = ConversationDetail(
                id=f"conv_{uuid4().hex}",
                title=f"{source.title} · 分支",
                selected_model=source.selected_model,
                created_at=timestamp,
                updated_at=timestamp,
                event_count=len(events),
                last_event_kind=events[-1].get("kind") if events else None,
                events=events,
            )
            self._ensure_base_dir()
            self._write_detail(detail)
            self._upsert_summary(detail)
            return detail

    def list_conversations(self) -> list[ConversationSummary]:
        with self._lock:
            index_path = self._index_path()
            if not index_path.exists():
                return []
            payload = json.loads(index_path.read_text(encoding="utf-8"))
        summaries = [ConversationSummary(**item) for item in payload]
        return self._sort_summaries(summaries)

    def get_conversation(self, conversation_id: str) -> ConversationDetail:
        with self._lock:
            payload = json.loads(self._detail_path(conversation_id).read_text(encoding="utf-8"))
        return ConversationDetail(**payload)

    def get_events_page(self, conversation_id: str, *, offset: int, limit: int) -> ConversationEventsPage:
        detail = self.get_conversation(conversation_id)
        total = len(detail.events)
        normalized_limit = max(1, min(limit, 500))
        normalized_offset = max(0, min(offset, total))
        page_events = detail.events[normalized_offset : normalized_offset + normalized_limit]
        return ConversationEventsPage(
            conversation=self._to_summary(detail),
            events=page_events,
            offset=normalized_offset,
            limit=normalized_limit,
            total=total,
            has_more_before=normalized_offset > 0,
            has_more_after=normalized_offset + len(page_events) < total,
        )

    def get_events_tail(self, conversation_id: str, *, limit: int) -> ConversationEventsPage:
        detail = self.get_conversation(conversation_id)
        total = len(detail.events)
        normalized_limit = max(1, min(limit, 500))
        offset = max(0, total - normalized_limit)
        page_events = detail.events[offset:]
        return ConversationEventsPage(
            conversation=self._to_summary(detail),
            events=page_events,
            offset=offset,
            limit=normalized_limit,
            total=total,
            has_more_before=offset > 0,
            has_more_after=False,
        )

    def append_events(self, conversation_id: str, events: list[dict], *, async_title_generation: bool = True) -> ConversationDetail:
        with self._lock:
            detail = self.get_conversation(conversation_id)
            sanitized_events = [self._sanitize_event(event) for event in events]
            had_user_event = any(event.get("kind") == "user" for event in detail.events)
            self._merge_events(detail.events, sanitized_events)
            detail.event_count = len(detail.events)
            detail.last_event_kind = detail.events[-1].get("kind") if detail.events else None
            detail.updated_at = self._utc_now()

            generated_title_sync = None
            first_user_text = None
            should_generate_title = not had_user_event or self._is_default_title(detail.title)
            if should_generate_title:
                first_user_text = next(
                    (
                        event.get("text")
                        for event in sanitized_events
                        if event.get("kind") == "user" and isinstance(event.get("text"), str)
                    ),
                    None,
                )
                if first_user_text and not async_title_generation:
                    generated_title_sync = self._generate_title(first_user_text, detail.selected_model)
                    if generated_title_sync:
                        detail.title = generated_title_sync

            self._write_detail(detail)
            self._upsert_summary(detail)

        if should_generate_title and first_user_text and async_title_generation:
            import threading
            threading.Thread(
                target=self._update_conversation_title_sync,
                args=(conversation_id, first_user_text),
                daemon=True
            ).start()

        return detail

    def _update_conversation_title_sync(self, conversation_id: str, prompt: str) -> None:
        """Background worker to update conversation title without blocking."""
        try:
            # Get model early to pass to title generator
            initial_detail = self.get_conversation(conversation_id)
            generated_title = self._generate_title(prompt, initial_detail.selected_model)
            
            if generated_title:
                with self._lock:
                    # Re-fetch detail to avoid overwriting events that were appended during generation
                    detail = self.get_conversation(conversation_id)
                    if generated_title != detail.title:
                        detail.title = generated_title
                        detail.updated_at = self._utc_now()
                        self._write_detail(detail)
                        self._upsert_summary(detail)
        except Exception:
            logger.exception("Failed to update conversation title conversation_id=%s", conversation_id)

    def delete_conversation(self, conversation_id: str) -> None:
        with self._lock:
            detail_path = self._detail_path(conversation_id)
            if not detail_path.exists():
                raise FileNotFoundError(conversation_id)
            detail_path.unlink()
            self._delete_summary(conversation_id)

    def _sanitize_event(self, event: dict) -> dict:
        sanitized = dict(event)
        if "approvalToken" in sanitized:
            sanitized["approvalToken"] = None
        tool_call = sanitized.get("toolCall")
        if isinstance(tool_call, dict) and "approvalToken" in tool_call:
            sanitized["toolCall"] = {**tool_call, "approvalToken": None}
        return sanitized

    def _merge_events(self, existing_events: list[dict], new_events: list[dict]) -> None:
        event_index_by_identity = {
            identity: index
            for index, event in enumerate(existing_events)
            if (identity := self._event_identity(event)) is not None
        }
        for event in new_events:
            identity = self._event_identity(event)
            existing_index = event_index_by_identity.get(identity) if identity is not None else None
            if existing_index is not None:
                existing_events[existing_index] = event
                continue
            if identity is not None:
                event_index_by_identity[identity] = len(existing_events)
            existing_events.append(event)

    def _event_identity(self, event: dict) -> tuple[object, ...] | None:
        if self._is_agent_message(event):
            return ("message", event.get("id"))
        event_id = event.get("eventId")
        if isinstance(event_id, str) and event_id:
            return ("event", event_id)
        runtime_id = event.get("runtimeId")
        sequence = event.get("sequence")
        if isinstance(runtime_id, str) and runtime_id and isinstance(sequence, int):
            return ("runtime", runtime_id, sequence)
        event_id = event.get("id")
        if isinstance(event_id, str) and event_id:
            return ("id", event_id)
        return None

    def _is_agent_message(self, event: dict) -> bool:
        return event.get("kind") == "message" and event.get("type") in {"say", "ask"} and isinstance(event.get("id"), str)

    def _is_default_title(self, title: str) -> bool:
        return title.strip() in {"", "New"}

    def _generate_title(self, prompt: str, model_name: str | None) -> str | None:
        if self._model_service is None:
            return None
        generator = getattr(self._model_service, "generate_conversation_title", None)
        if generator is None:
            return None
        try:
            title = generator(prompt, model_name=model_name)
        except Exception:
            logger.exception("Failed to generate conversation title model_name=%s", model_name)
            return None
        if not isinstance(title, str):
            return None
        title = title.strip()
        return title or None

    def to_summary(self, detail: ConversationDetail) -> ConversationSummary:
        return self._to_summary(detail)

    def _to_summary(self, detail: ConversationDetail) -> ConversationSummary:
        return ConversationSummary(
            id=detail.id,
            title=detail.title,
            selected_model=detail.selected_model,
            created_at=detail.created_at,
            updated_at=detail.updated_at,
            event_count=detail.event_count,
            last_event_kind=detail.last_event_kind,
        )

    def _ensure_base_dir(self) -> None:
        self._base_dir.mkdir(parents=True, exist_ok=True)

    def _index_path(self) -> Path:
        return self._base_dir / "index.json"

    def _detail_path(self, conversation_id: str) -> Path:
        if not CONVERSATION_ID_PATTERN.fullmatch(conversation_id):
            raise FileNotFoundError(conversation_id)
        return self._base_dir / f"{conversation_id}.json"

    def _write_detail(self, detail: ConversationDetail) -> None:
        self._write_json(self._detail_path(detail.id), asdict(detail))

    def _upsert_summary(self, detail: ConversationDetail) -> None:
        conversation_id = detail.id
        summaries = [item for item in self.list_conversations() if item.id != conversation_id]
        summaries.append(self._to_summary(detail))
        self._write_index(summaries)

    def _delete_summary(self, conversation_id: str) -> None:
        summaries = [item for item in self.list_conversations() if item.id != conversation_id]
        self._write_index(summaries)

    def _write_index(self, summaries: list[ConversationSummary]) -> None:
        ordered = self._sort_summaries(summaries)
        self._write_json(self._index_path(), [asdict(item) for item in ordered])

    def _sort_summaries(self, summaries: list[ConversationSummary]) -> list[ConversationSummary]:
        return sorted(summaries, key=lambda item: item.updated_at, reverse=True)

    def _write_json(self, path: Path, payload: dict | list) -> None:
        atomic_write_json(path, payload)

    def _utc_now(self) -> str:
        return datetime.now(UTC).isoformat()
