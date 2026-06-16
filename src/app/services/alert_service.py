from __future__ import annotations

import asyncio
from datetime import UTC, datetime
import logging
from typing import AsyncIterator

from sqlmodel import Session, select, col

from app.db.models import Alert

logger = logging.getLogger(__name__)


class AlertService:
    def __init__(self) -> None:
        self._listeners: set[asyncio.Queue[dict]] = set()

    def create_alert(
        self,
        session: Session,
        *,
        asset_id: int,
        title: str,
        message: str,
        severity: str = "warning",
        job_id: int | None = None,
        runtime_id: str | None = None,
        conversation_id: str | None = None,
    ) -> Alert:
        alert = Alert(
            asset_id=asset_id,
            title=title,
            message=message,
            severity=severity,
            job_id=job_id,
            runtime_id=runtime_id,
            conversation_id=conversation_id,
            status="unread",
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        session.add(alert)
        session.commit()
        session.refresh(alert)
        
        # Publish to listeners (SSE)
        self.publish({
            "type": "new_alert",
            "id": alert.id,
            "jobId": alert.job_id,
            "assetId": alert.asset_id,
            "runtimeId": alert.runtime_id,
            "conversationId": alert.conversation_id,
            "severity": alert.severity,
            "title": alert.title,
            "message": alert.message,
            "status": alert.status,
            "createdAt": alert.created_at.isoformat(),
            "updatedAt": alert.updated_at.isoformat(),
        })
        return alert

    def list_alerts(
        self,
        session: Session,
        *,
        status: str | None = None,
        limit: int = 50,
    ) -> list[Alert]:
        statement = select(Alert)
        if status:
            statement = statement.where(Alert.status == status)
        statement = statement.order_by(col(Alert.created_at).desc()).limit(limit)
        return list(session.exec(statement).all())

    def update_alert_status(self, session: Session, alert_id: int, status: str) -> Alert | None:
        alert = session.get(Alert, alert_id)
        if alert is None:
            return None
        alert.status = status
        alert.updated_at = datetime.now(UTC)
        session.add(alert)
        session.commit()
        session.refresh(alert)
        
        # Publish update to listeners
        self.publish({
            "type": "alert_updated",
            "id": alert.id,
            "status": alert.status,
        })
        return alert

    def publish(self, event: dict) -> None:
        for queue in list(self._listeners):
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                pass

    async def subscribe(self) -> AsyncIterator[dict]:
        queue: asyncio.Queue[dict] = asyncio.Queue(maxsize=100)
        self._listeners.add(queue)
        try:
            while True:
                event = await queue.get()
                yield event
        finally:
            self._listeners.remove(queue)


_alert_service: AlertService | None = None


def get_alert_service() -> AlertService:
    global _alert_service
    if _alert_service is None:
        _alert_service = AlertService()
    return _alert_service
