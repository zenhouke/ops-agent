from __future__ import annotations

import asyncio
from datetime import UTC, datetime
import logging
import re

from sqlmodel import Session, select

from app.db.models import ScheduledJob
from app.db.session import engine
from app.services.alert_service import get_alert_service

logger = logging.getLogger(__name__)


class SchedulerService:
    def __init__(self) -> None:
        self._running = False
        self._task: asyncio.Task | None = None

    def start_loop(self) -> None:
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._scheduler_loop())
        logger.info("Scheduler background loop started.")

    def stop_loop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            self._task = None
        logger.info("Scheduler background loop stopped.")

    async def _scheduler_loop(self) -> None:
        # Give the server a few seconds to start up completely
        await asyncio.sleep(5)
        while self._running:
            try:
                await self._check_and_run_jobs()
            except Exception as exc:
                logger.exception("Error in scheduler loop tick: %s", exc)
            await asyncio.sleep(10)

    async def _check_and_run_jobs(self) -> None:
        now = datetime.now(UTC)
        with Session(engine) as session:
            statement = select(ScheduledJob).where(ScheduledJob.enabled == True)
            jobs = session.exec(statement).all()
            for job in jobs:
                # Check if it is time to run
                should_run = False
                if job.last_run_at is None:
                    should_run = True
                else:
                    # last_run_at is stored in UTC or naive. Ensure UTC comparison.
                    last_run = job.last_run_at
                    if last_run.tzinfo is None:
                        last_run = last_run.replace(tzinfo=UTC)
                    elapsed = (now - last_run).total_seconds()
                    if elapsed >= job.interval_seconds:
                        should_run = True

                if should_run and job.id is not None:
                    logger.info("Scheduling job: %s (id=%s)", job.name, job.id)
                    # Update last run time immediately to prevent double-triggering
                    job.last_run_at = now
                    job.updated_at = now
                    session.add(job)
                    session.commit()
                    session.refresh(job)

                    # Trigger the job asynchronously in a separate thread so it doesn't block the loop
                    asyncio.create_task(
                        asyncio.to_thread(self._run_job_sync, job.id)
                    )

    def _run_job_sync(self, job_id: int) -> None:
        with Session(engine) as session:
            job = session.get(ScheduledJob, job_id)
            if not job or not job.enabled:
                return

            from app.api.console import get_console_app_service
            from app.api.conversations import get_conversation_service
            from app.api.terminal import get_terminal_service

            conversation_service = get_conversation_service()
            console_app = get_console_app_service()
            terminal_service = get_terminal_service()
            default_model = console_app._resolve_model_config(session, None)
            conversation = conversation_service.create_conversation(selected_model=default_model.model_name)
            conversation_id = conversation.id
            logger.info("Starting background job execution conversation_id=%s for job_id=%s", conversation_id, job.id)

            try:
                conversation_service.append_events(
                    conversation_id,
                    [
                        {
                            "id": f"scheduler-user-{job.id}-{conversation_id}",
                            "kind": "user",
                            "text": job.prompt,
                        }
                    ],
                    async_title_generation=False,
                )

                # stream_run will automatically load assets, configure context, and run the agent loop
                events_generator = console_app.stream_run(
                    session=session,
                    prompt=job.prompt,
                    asset_id=job.asset_id,
                    conversation_id=conversation_id,
                    mode="agent",
                    terminal_service=terminal_service,
                )

                # Iterate through all yielded events to run the loop generator to completion
                runtime_id = None
                has_ask_approval = False
                
                for event in events_generator:
                    if not runtime_id and "runtimeId" in event:
                        runtime_id = event["runtimeId"]
                    if event.get("kind") == "ask" and event.get("askType") == "command":
                        has_ask_approval = True
                        logger.info("Job %s (runtime_id=%s) paused for command approval.", job.name, runtime_id)

                # Fetch runtime state after completion
                if runtime_id:
                    rt = console_app.runtime_manager.get_runtime(runtime_id)
                    if rt:
                        phase = rt.state.phase
                        logger.info("Job %s (runtime_id=%s) finished with phase: %s", job.name, runtime_id, phase)
                        
                        alert_service = get_alert_service()
                        if phase == "approving" or has_ask_approval:
                            # Create a critical approval-required alert
                            alert_service.create_alert(
                                session,
                                asset_id=job.asset_id,
                                title=f"等待审批：定时任务 - {job.name}",
                                message=f"定时巡检任务遇到需要审批的命令，已安全暂停。请进入控制台进行审批以继续执行。",
                                severity="critical",
                                job_id=job.id,
                                runtime_id=runtime_id,
                                conversation_id=conversation_id,
                            )
                        elif phase == "completed":
                            summary = rt.state.summary or ""
                            # Parse summary for alerts
                            alert_pattern = re.compile(r"\[ALERT:\s*(.*?)\]\s*(.*)", re.IGNORECASE)
                            matches = alert_pattern.findall(summary)
                            
                            if matches:
                                for title, msg in matches:
                                    alert_service.create_alert(
                                        session,
                                        asset_id=job.asset_id,
                                        title=title.strip() or f"巡检告警：{job.name}",
                                        message=msg.strip(),
                                        severity="warning",
                                        job_id=job.id,
                                        runtime_id=runtime_id,
                                        conversation_id=conversation_id,
                                    )
                            elif "[ALERT]" in summary or "异常" in summary or "warning" in summary.lower() or "error" in summary.lower():
                                alert_service.create_alert(
                                    session,
                                    asset_id=job.asset_id,
                                    title=f"巡检告警：{job.name}",
                                    message=summary,
                                    severity="warning",
                                    job_id=job.id,
                                    runtime_id=runtime_id,
                                    conversation_id=conversation_id,
                                )
                        elif phase == "failed":
                            # Create failure alert
                            alert_service.create_alert(
                                session,
                                asset_id=job.asset_id,
                                title=f"巡检失败：{job.name}",
                                message=rt.state.error_message or "定时巡检任务执行失败。",
                                severity="warning",
                                job_id=job.id,
                                runtime_id=runtime_id,
                                conversation_id=conversation_id,
                            )
            except Exception as exc:
                logger.exception("Failed executing scheduled job %s", job.name)
                # Create systems alert
                try:
                    get_alert_service().create_alert(
                        session,
                        asset_id=job.asset_id,
                        title=f"巡检异常：{job.name}",
                        message=f"执行任务时发生系统异常：{exc}",
                        severity="warning",
                        job_id=job.id,
                        conversation_id=conversation_id,
                    )
                except Exception:
                    pass


_scheduler_service: SchedulerService | None = None


def get_scheduler_service() -> SchedulerService:
    global _scheduler_service
    if _scheduler_service is None:
        _scheduler_service = SchedulerService()
    return _scheduler_service
