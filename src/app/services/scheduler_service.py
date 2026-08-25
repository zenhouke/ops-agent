from __future__ import annotations

import asyncio
from datetime import UTC, datetime
import logging
import re

from sqlmodel import Session, select

from app.db.models import ScheduledJob
from app.db.session import engine
from app.core.runtime.control import get_runtime_control
from app.services.alert_service import get_alert_service
from app.services.scheduler_lease import SchedulerLeaseStore

logger = logging.getLogger(__name__)


class SchedulerService:
    def __init__(self) -> None:
        self._running = False
        self._task: asyncio.Task | None = None
        limits = get_runtime_control().limits
        self._capacity = asyncio.Semaphore(limits.max_scheduler_jobs)
        self._leases = SchedulerLeaseStore(limits.scheduler_lease_seconds)
        self._job_tasks: set[asyncio.Task] = set()

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
        for task in list(self._job_tasks):
            task.cancel()
        logger.info("Scheduler background loop stopped.")

    async def _scheduler_loop(self) -> None:
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
                should_run = False
                if job.last_run_at is None:
                    should_run = True
                else:
                    last_run = job.last_run_at
                    if last_run.tzinfo is None:
                        last_run = last_run.replace(tzinfo=UTC)
                    elapsed = (now - last_run).total_seconds()
                    if elapsed >= job.interval_seconds:
                        should_run = True

                if should_run and job.id is not None:
                    logger.info("Scheduling job: %s (id=%s)", job.name, job.id)
                    self.submit_job(job.id)

    def submit_job(self, job_id: int) -> bool:
        owner = self._leases.claim(job_id)
        if owner is None:
            return False
        task = asyncio.create_task(self._run_claimed_job(job_id, owner))
        self._job_tasks.add(task)
        task.add_done_callback(self._job_tasks.discard)
        return True

    async def _run_claimed_job(self, job_id: int, owner: str) -> None:
        async with self._capacity:
            await asyncio.to_thread(self._run_claimed_job_sync, job_id, owner)

    def _run_claimed_job_sync(self, job_id: int, owner: str) -> None:
        status = "failed"
        error = ""
        try:
            self._leases.mark_running(job_id, owner)
            status = self._run_job_sync(job_id)
            get_runtime_control().metrics.increment("scheduler_runs")
        except Exception as exc:
            error = str(exc)
            get_runtime_control().metrics.increment("scheduler_failures")
            logger.exception("Unhandled scheduled job failure job_id=%s", job_id)
        finally:
            self._leases.finish(job_id, owner, status=status, error=error)

    def _run_job_sync(self, job_id: int) -> str:
        with Session(engine) as session:
            job = session.get(ScheduledJob, job_id)
            if not job or not job.enabled:
                return "skipped"

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

                events_generator = console_app.stream_run(
                    session=session,
                    prompt=job.prompt,
                    asset_id=job.asset_id,
                    conversation_id=conversation_id,
                    terminal_service=terminal_service,
                )

                runtime_id = None
                has_ask_approval = False
                
                for event in events_generator:
                    if not runtime_id and "runtimeId" in event:
                        runtime_id = event["runtimeId"]
                    if event.get("kind") == "ask" and event.get("askType") == "command":
                        has_ask_approval = True
                        logger.info("Job %s (runtime_id=%s) paused for command approval.", job.name, runtime_id)

                result_status = "succeeded"
                if runtime_id:
                    rt = console_app.runtime_manager.get_runtime(runtime_id)
                    if rt:
                        phase = rt.state.phase
                        logger.info("Job %s (runtime_id=%s) finished with phase: %s", job.name, runtime_id, phase)
                        
                        alert_service = get_alert_service()
                        if phase == "approving" or has_ask_approval:
                            result_status = "waiting_approval"
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
                            result_status = "failed"
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
                return result_status
            except Exception as exc:
                logger.exception("Failed executing scheduled job %s", job.name)
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
                return "failed"


_scheduler_service: SchedulerService | None = None


def get_scheduler_service() -> SchedulerService:
    global _scheduler_service
    if _scheduler_service is None:
        _scheduler_service = SchedulerService()
    return _scheduler_service
