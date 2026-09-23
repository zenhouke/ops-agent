from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from threading import RLock
from time import sleep
from uuid import uuid4

from app.core.llm.retry import is_retryable_model_error, model_retry_delay
from app.services.knowledge_models import KnowledgeExtractionJob, KnowledgeExtractionTask
from app.services.knowledge_service import (
    KnowledgeService, RecoverableKnowledgeServiceError, KnowledgeDraftParseError,
    KnowledgeReplanError, KnowledgeIndexUpdateError,
)
from app.utils.file_store import atomic_write_json

logger = logging.getLogger(__name__)
_MAX_RETRIES = 3


class KnowledgeExtractionService:
    """Durable source batches and receipts allow replay without duplicate knowledge writes."""

    def __init__(self, service: KnowledgeService, jobs_dir: Path) -> None:
        self._service = service
        self._jobs_dir = jobs_dir
        self._lock = RLock()
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="knowledge-extraction")
        self._jobs: dict[str, KnowledgeExtractionTask] = {}
        self._service.recover_extraction_batches()
        pending = []
        for path in jobs_dir.glob("*.json"):
            try:
                job = KnowledgeExtractionTask.model_validate_json(path.read_text())
            except (ValueError, OSError):
                continue
            if path.stem != job.id:
                continue
            if job.status in {"queued", "running"}:
                if job.batches:
                    job.status = "queued"
                    job.progress = "服务已恢复，继续未完成的批次。"
                    pending.append(job.id)
                else:
                    job.status = "failed"
                    job.error = "旧任务未保存提炼快照，请重新提炼。"
                self._save(job)
            self._jobs[job.id] = job
        for job_id in pending:
            self._executor.submit(self._run, job_id)

    @staticmethod
    def _view(job: KnowledgeExtractionTask) -> KnowledgeExtractionJob:
        return KnowledgeExtractionJob.model_validate(job.model_dump())

    def latest(self, conversation_id: str) -> KnowledgeExtractionJob | None:
        with self._lock:
            jobs = [job for job in self._jobs.values() if job.conversation_id == conversation_id]
            return self._view(max(jobs, key=lambda job: job.created_at)) if jobs else None

    def submit(self, conversation_id: str, *, max_source_events: int = 120, model_name: str | None = None) -> KnowledgeExtractionJob:
        with self._lock:
            previous = self.latest(conversation_id)
            if previous and previous.status in {"queued", "running"}:
                return previous
            batches, source = self._service.extraction_batches(conversation_id, max_source_events)
            now = datetime.now(UTC).isoformat()
            job = KnowledgeExtractionTask(
                id=f"extract_{uuid4().hex}", conversation_id=conversation_id, created_at=now, updated_at=now,
                source=source, batches=batches, total_batches=len(batches), model_name=model_name,
                status="queued" if batches else "succeeded",
                progress=f"已排队，共 {len(batches)} 批。" if batches else "没有新增或修改的会话内容，无需重复提炼。",
            )
            self._save(job)
            self._jobs[job.id] = job
            if batches:
                self._executor.submit(self._run, job.id)
            return self._view(job)

    def _save(self, job: KnowledgeExtractionTask) -> None:
        job.updated_at = datetime.now(UTC).isoformat()
        atomic_write_json(self._jobs_dir / f"{job.id}.json", job.model_dump())

    def _run(self, job_id: str) -> None:
        job = self._jobs[job_id]
        try:
            self._service.recover_extraction_batches()
            with self._lock:
                job.status = "running"
                job.error = None
                self._save(job)
            for index in range(job.completed_batches, len(job.batches)):
                batch = job.batches[index]
                feedback = ""
                preferred_ids: list[str] = []
                results: list[tuple[str, str]] = []
                for attempt in range(_MAX_RETRIES + 1):
                    with self._lock:
                        job.progress = f"正在提炼第 {index + 1}/{job.total_batches} 批。"
                        if attempt:
                            job.progress += f" 自动重试 {attempt}/{_MAX_RETRIES}，重新合并最新知识。"
                        self._save(job)
                    results.clear()
                    try:
                        self._service.extract_and_save(
                            batch.document, job.source, model_name=job.model_name,
                            batch_key=batch.key, fingerprints=batch.fingerprints,
                            feedback=feedback, preferred_entry_ids=preferred_ids,
                            on_saved=lambda action, entry_id: results.append((action, entry_id)),
                        )
                        break
                    except Exception as exc:
                        replan = isinstance(exc, (KnowledgeDraftParseError, KnowledgeReplanError))
                        transient = is_retryable_model_error(exc)
                        if attempt >= _MAX_RETRIES or not (replan or transient or isinstance(exc, KnowledgeIndexUpdateError)):
                            raise
                        feedback = str(exc) if replan else "Previous request failed temporarily; generate a fresh valid plan using current knowledge."
                        if isinstance(exc, KnowledgeReplanError):
                            preferred_ids = exc.entry_ids
                        with self._lock:
                            job.retry_count += 1
                            job.progress = f"第 {index + 1}/{job.total_batches} 批暂未完成，准备自动重试 {attempt + 1}/{_MAX_RETRIES}。"
                            self._save(job)
                        if transient:
                            sleep(model_retry_delay(exc, attempt + 1))
                with self._lock:
                    for action, entry_id in results:
                        ids = job.created_ids if action == "create" else job.updated_ids if action == "update" else job.kept_ids
                        if entry_id not in ids:
                            ids.append(entry_id)
                    job.completed_batches = index + 1
                    self._save(job)
        except Exception as exc:
            logger.warning("Knowledge extraction %s failed (%s)", job_id, type(exc).__name__)
            with self._lock:
                job.status = "failed"
                job.error = str(exc) if isinstance(exc, RecoverableKnowledgeServiceError) else "后台提炼失败，请检查模型服务后重试。"
                job.progress = f"已完成 {job.completed_batches}/{job.total_batches} 批；再次提炼会跳过已完成的内容。"
                self._save(job)
        else:
            with self._lock:
                job.status = "succeeded"
                job.progress = f"已完成全部 {job.total_batches} 批。"
                job.batches = []
                self._save(job)

    def close(self) -> None:
        self._executor.shutdown(wait=True)
