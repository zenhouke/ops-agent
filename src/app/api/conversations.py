import os
from pathlib import Path
from typing import cast

from fastapi import APIRouter, HTTPException, Response, status

from app.api.schemas import (
    ConversationAppendEventsRequest,
    ConversationAppendEventsResponse,
    ConversationContextStatusView,
    ConversationEventsPageView,
    ConversationTokenUsageView,
    ConversationCreateRequest,
    ConversationCreateResponse,
    ConversationDetailView,
    ConversationSummaryView,
    ConversationUpdateRequest,
)
from app.db.repositories.model_usage import sum_conversation_usage
from app.db.session import Session, engine
from app.services.context_manager import ContextManager, JsonObject
from app.services.conversation_service import ConversationService
from app.services.model_service import ModelService

router = APIRouter()


def get_conversation_service() -> ConversationService:
    configured = os.getenv("OPS_AGENT_CONVERSATIONS_DIR", "")
    base_dir = Path(configured) if configured else Path.cwd() / ".ops-agent" / "conversations"
    return ConversationService(base_dir=base_dir, model_service=ModelService())


@router.get("/api/conversations", response_model=list[ConversationSummaryView])
def list_conversations() -> list[ConversationSummaryView]:
    service = get_conversation_service()
    return [ConversationSummaryView.model_validate(summary.__dict__) for summary in service.list_conversations()]


@router.post("/api/conversations", response_model=ConversationCreateResponse)
def create_conversation(payload: ConversationCreateRequest) -> ConversationCreateResponse:
    service = get_conversation_service()
    summary = service.create_conversation(
        selected_model=payload.selected_model,
        asset_id=payload.asset_id,
    )
    return ConversationCreateResponse(
        conversation=ConversationSummaryView.model_validate(summary.__dict__),
        events=[],
    )


@router.patch("/api/conversations/{conversation_id}", response_model=ConversationSummaryView)
def update_conversation(conversation_id: str, payload: ConversationUpdateRequest) -> ConversationSummaryView:
    service = get_conversation_service()
    try:
        detail = service.update_selected_model(conversation_id, payload.selected_model)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Conversation not found") from exc
    return ConversationSummaryView.model_validate(service.to_summary(detail).__dict__)


@router.get("/api/conversations/{conversation_id}", response_model=ConversationDetailView)
def get_conversation(conversation_id: str) -> ConversationDetailView:
    service = get_conversation_service()
    try:
        detail = service.get_conversation(conversation_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Conversation not found") from exc
    return ConversationDetailView.model_validate(detail.__dict__)


@router.get("/api/conversations/{conversation_id}/events", response_model=ConversationEventsPageView)
def get_conversation_events(conversation_id: str, offset: int = 0, limit: int = 200, tail: int | None = None) -> ConversationEventsPageView:
    service = get_conversation_service()
    try:
        page = service.get_events_tail(conversation_id, limit=tail) if tail is not None else service.get_events_page(conversation_id, offset=offset, limit=limit)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Conversation not found") from exc
    return ConversationEventsPageView(
        conversation=ConversationSummaryView.model_validate(page.conversation.__dict__),
        events=page.events,
        offset=page.offset,
        limit=page.limit,
        total=page.total,
        has_more_before=page.has_more_before,
        has_more_after=page.has_more_after,
    )


@router.post("/api/conversations/{conversation_id}/events", response_model=ConversationAppendEventsResponse)
def append_conversation_events(conversation_id: str, payload: ConversationAppendEventsRequest) -> ConversationAppendEventsResponse:
    service = get_conversation_service()
    try:
        detail = service.append_events(conversation_id, payload.events)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Conversation not found") from exc
    return ConversationAppendEventsResponse(
        conversation=ConversationSummaryView.model_validate(service.to_summary(detail).__dict__),
        appended_count=len(payload.events),
    )


@router.get("/api/conversations/{conversation_id}/context", response_model=ConversationContextStatusView)
def get_conversation_context(conversation_id: str) -> ConversationContextStatusView:
    service = get_conversation_service()
    try:
        detail = service.get_conversation(conversation_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Conversation not found") from exc

    context_manager = ContextManager(service.base_dir / "context")
    events = cast(list[JsonObject], detail.events or [])
    with Session(engine) as session:
        usage = sum_conversation_usage(session, conversation_id)
    token_usage = ConversationTokenUsageView(
        input_tokens=usage.input_tokens,
        output_tokens=usage.output_tokens,
        cache_creation_input_tokens=usage.cache_creation_input_tokens,
        cache_read_input_tokens=usage.cache_read_input_tokens,
        total_tokens=usage.total_tokens,
    )
    metadata = context_manager.read_metadata(conversation_id)
    source_revision = context_manager.source_revision(events)
    if metadata is None or metadata.source_conversation_revision != source_revision:
        model_config = ModelService().load_settings()
        result = context_manager.prepare_context(conversation_id, events, model_config)
        return ConversationContextStatusView(
            context_percent=result.context_percent,
            context_status=result.context_status,
            token_usage=token_usage,
        )
    return ConversationContextStatusView(
        context_percent=metadata.context_percent,
        context_status=metadata.context_status,
        token_usage=token_usage,
    )


@router.delete("/api/conversations/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
def delete_conversation(conversation_id: str) -> Response:
    service = get_conversation_service()
    try:
        service.delete_conversation(conversation_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Conversation not found") from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)
