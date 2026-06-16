from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlmodel import Session, select

from app.db.session import get_session
from app.db.models import Alert
from app.services.alert_service import get_alert_service

router = APIRouter()
logger = logging.getLogger(__name__)


class AlertStatusUpdate(BaseModel):
    status: str  # 'unread', 'resolved', 'ignored'


class AlertView(BaseModel):
    id: int
    job_id: int | None = None
    asset_id: int
    runtime_id: str | None = None
    conversation_id: str | None = None
    severity: str
    title: str
    message: str
    status: str
    created_at: datetime
    updated_at: datetime


@router.get("/api/alerts", response_model=list[AlertView])
def list_alerts(
    status: str | None = None,
    limit: int = 50,
    session: Session = Depends(get_session),
) -> list[AlertView]:
    alert_service = get_alert_service()
    records = alert_service.list_alerts(session, status=status, limit=limit)
    return [
        AlertView(
            id=alert.id or 0,
            job_id=alert.job_id,
            asset_id=alert.asset_id,
            runtime_id=alert.runtime_id,
            conversation_id=alert.conversation_id,
            severity=alert.severity,
            title=alert.title,
            message=alert.message,
            status=alert.status,
            created_at=alert.created_at,
            updated_at=alert.updated_at,
        )
        for alert in records
    ]


@router.put("/api/alerts/{alert_id}/status", response_model=AlertView)
def update_alert_status(
    alert_id: int,
    payload: AlertStatusUpdate,
    session: Session = Depends(get_session),
) -> AlertView:
    if payload.status not in ("unread", "resolved", "ignored"):
        raise HTTPException(status_code=400, detail="Invalid status value")

    alert_service = get_alert_service()
    alert = alert_service.update_alert_status(session, alert_id, payload.status)
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
        
    return AlertView(
        id=alert.id or 0,
        job_id=alert.job_id,
        asset_id=alert.asset_id,
        runtime_id=alert.runtime_id,
        conversation_id=alert.conversation_id,
        severity=alert.severity,
        title=alert.title,
        message=alert.message,
        status=alert.status,
        created_at=alert.created_at,
        updated_at=alert.updated_at,
    )


@router.get("/api/alerts/sse")
async def stream_alerts() -> StreamingResponse:
    alert_service = get_alert_service()

    async def event_generator():
        try:
            async for event in alert_service.subscribe():
                yield f"event: {event.get('type', 'alert')}\ndata: {json.dumps(event, ensure_ascii=False)}\n\n"
        except asyncio.CancelledError:
            pass

    return StreamingResponse(event_generator(), media_type="text/event-stream")
