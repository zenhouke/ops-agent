from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel
from sqlmodel import Session, select, col

from app.db.session import get_session
from app.db.models import ScheduledJob
from app.services.asset_service import get_asset_record
from app.services.scheduler_service import get_scheduler_service

router = APIRouter()


class ScheduledJobCreate(BaseModel):
    name: str
    asset_id: int
    prompt: str
    interval_seconds: int = 3600
    enabled: bool = True


class ScheduledJobUpdate(BaseModel):
    name: str | None = None
    asset_id: int | None = None
    prompt: str | None = None
    interval_seconds: int | None = None
    enabled: bool | None = None


class ScheduledJobView(BaseModel):
    id: int
    name: str
    asset_id: int
    prompt: str
    interval_seconds: int
    enabled: bool
    last_run_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


def _validate_job_fields(*, name: str | None, asset_id: int | None, prompt: str | None, interval_seconds: int | None, session: Session) -> None:
    if name is not None and not name.strip():
        raise HTTPException(status_code=400, detail="Job name is required")
    if prompt is not None and not prompt.strip():
        raise HTTPException(status_code=400, detail="Job prompt is required")
    if interval_seconds is not None and interval_seconds < 60:
        raise HTTPException(status_code=400, detail="Interval must be at least 60 seconds")
    if asset_id is not None and get_asset_record(session, asset_id) is None:
        raise HTTPException(status_code=404, detail="Asset not found")


def _to_job_view(job: ScheduledJob) -> ScheduledJobView:
    return ScheduledJobView(
        id=job.id or 0,
        name=job.name,
        asset_id=job.asset_id,
        prompt=job.prompt,
        interval_seconds=job.interval_seconds,
        enabled=job.enabled,
        last_run_at=job.last_run_at,
        created_at=job.created_at,
        updated_at=job.updated_at,
    )


@router.get("/api/scheduler/jobs", response_model=list[ScheduledJobView])
def list_jobs(session: Session = Depends(get_session)) -> list[ScheduledJobView]:
    statement = select(ScheduledJob).order_by(col(ScheduledJob.created_at).desc())
    jobs = session.exec(statement).all()
    return [_to_job_view(job) for job in jobs]


@router.get("/api/scheduler/jobs/{job_id}", response_model=ScheduledJobView)
def get_job(job_id: int, session: Session = Depends(get_session)) -> ScheduledJobView:
    job = session.get(ScheduledJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return _to_job_view(job)


@router.post("/api/scheduler/jobs", response_model=ScheduledJobView, status_code=201)
def create_job(payload: ScheduledJobCreate, session: Session = Depends(get_session)) -> ScheduledJobView:
    _validate_job_fields(
        name=payload.name,
        asset_id=payload.asset_id,
        prompt=payload.prompt,
        interval_seconds=payload.interval_seconds,
        session=session,
    )
    job = ScheduledJob(
        name=payload.name.strip(),
        asset_id=payload.asset_id,
        prompt=payload.prompt.strip(),
        interval_seconds=payload.interval_seconds,
        enabled=payload.enabled,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    session.add(job)
    session.commit()
    session.refresh(job)
    return _to_job_view(job)


@router.put("/api/scheduler/jobs/{job_id}", response_model=ScheduledJobView)
def update_job(
    job_id: int,
    payload: ScheduledJobUpdate,
    session: Session = Depends(get_session),
) -> ScheduledJobView:
    job = session.get(ScheduledJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    _validate_job_fields(
        name=payload.name,
        asset_id=payload.asset_id,
        prompt=payload.prompt,
        interval_seconds=payload.interval_seconds,
        session=session,
    )

    if payload.name is not None:
        job.name = payload.name.strip()
    if payload.asset_id is not None:
        job.asset_id = payload.asset_id
    if payload.prompt is not None:
        job.prompt = payload.prompt.strip()
    if payload.interval_seconds is not None:
        job.interval_seconds = payload.interval_seconds
    if payload.enabled is not None:
        job.enabled = payload.enabled

    job.updated_at = datetime.now(UTC)
    session.add(job)
    session.commit()
    session.refresh(job)
    return _to_job_view(job)


@router.delete("/api/scheduler/jobs/{job_id}", status_code=204)
def delete_job(job_id: int, session: Session = Depends(get_session)) -> Response:
    job = session.get(ScheduledJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    session.delete(job)
    session.commit()
    return Response(status_code=204)


@router.post("/api/scheduler/jobs/{job_id}/trigger")
async def trigger_job(
    job_id: int,
    session: Session = Depends(get_session),
) -> dict[str, str]:
    job = session.get(ScheduledJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    if job.id is None:
        raise HTTPException(status_code=500, detail="Job ID is not generated")

    now = datetime.now(UTC)
    job.last_run_at = now
    job.updated_at = now
    session.add(job)
    session.commit()

    # Run the job in the background thread pool
    asyncio.create_task(
        asyncio.to_thread(get_scheduler_service()._run_job_sync, job.id)
    )
    return {"status": "triggered"}
