from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from collections.abc import Callable
from copy import deepcopy
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path
import threading
from typing import Any
from uuid import uuid4

from sqlmodel import Session

from app.db.repositories.operations import OperationRepository
from app.db.repositories.jumpserver import get_instance, list_bindings
from app.db.session import engine
from app.services.operation_progress import OperationCancelled, OperationProgress
from app.shared.config import APP_DIR

ACTIVE = {"queued", "running", "cancelling"}
RETRYABLE = {"failed", "cancelled", "interrupted"}


class OperationsService:
    def __init__(self, directory: Path):
        self._repo = OperationRepository(directory)
        self._lock = threading.RLock()
        self._jobs = {job["id"]: job for job in self._repo.list()}
        self._executor = ThreadPoolExecutor(max_workers=3, thread_name_prefix="ops-background")
        self._closed = False
        self._inspect_asset: Callable[..., dict] | None = None
        self._runtime_lookup: Callable[[str], Any] | None = None
        for job in self._jobs.values():
            if job["status"] in ACTIVE:
                job.update(status="interrupted", message="服务重启导致任务中断，可重试未完成项。")
                for item in job["items"]:
                    if item["status"] in ACTIVE:
                        item["status"] = "interrupted"
                self._save(job)

    def bind(self, *, inspect_asset: Callable[..., dict], runtime_lookup: Callable[[str], Any]) -> None:
        self._inspect_asset = inspect_asset
        self._runtime_lookup = runtime_lookup

    def _save(self, job: dict[str, Any]) -> None:
        job["updatedAt"] = datetime.now(UTC).isoformat()
        self._repo.save(job)

    def list(self, *, kind: str | None = None, instance_id: int | None = None, organization: str | None = None) -> list[dict[str, Any]]:
        with self._lock:
            self._refresh_inspections()
            rows = [deepcopy(job) for job in self._jobs.values()
                    if (kind is None or job["kind"] == kind)
                    and (instance_id is None or job["payload"]["instanceId"] == instance_id)
                    and (organization is None or job["payload"].get("organization") == organization)]
        return sorted(rows, key=lambda row: row["createdAt"], reverse=True)

    def _refresh_inspections(self) -> None:
        for job in self._jobs.values():
            if job["kind"] != "inspection" or job["status"] in ACTIVE:
                continue
            changed = False
            for item in job["items"]:
                if item["status"] not in {"waiting_approval", "waiting_input", "resuming"} or not item.get("runtimeId"):
                    continue
                runtime = self._runtime_lookup(item["runtimeId"]) if self._runtime_lookup else None
                if runtime is None:
                    continue
                state = runtime.state
                status = {"completed": "completed", "failed": "failed", "approving": "waiting_approval", "waiting_terminal_approval": "waiting_approval", "waiting_user_input": "waiting_input"}.get(state.phase, "resuming")
                if status == "completed" and "[ALERT" in (state.summary or ""):
                    status = "warning"
                message = state.summary or state.error_message or ("人工处理后继续执行" if status == "resuming" else item["message"])
                if item["status"] != status or item["message"] != message:
                    item.update(status=status, message=message)
                    changed = True
            if changed:
                if job["status"] == "partial" and all(item["status"] in {"completed", "warning"} for item in job["items"]):
                    job["status"] = "completed"
                self._save(job)

    def get(self, job_id: str) -> dict[str, Any]:
        with self._lock:
            return deepcopy(self._jobs[job_id])

    def validate(self, kind: str, payload: dict[str, Any]) -> None:
        if kind not in {"sync", "topology", "inspection"}:
            raise ValueError("不支持的后台任务类型。")
        with Session(engine) as session:
            instance = get_instance(session, payload["instanceId"])
            if instance is None or not instance.enabled or instance.auth_mode != "ssh_gateway":
                raise ValueError("请选择已启用的 SSH JumpServer 实例。")
            if kind != "sync":
                from app.services.jumpserver_service import get_jumpserver_service
                groups = get_jumpserver_service().list_organizations(session, instance.id or 0)
                group = next((g for g in groups if g["id"] == payload.get("organization")), None)
                if group is None:
                    raise ValueError("组织不存在，请先在设置中同步资产。")
                if kind == "topology" and not group["networkAssetIds"]:
                    raise ValueError("该组织没有可采集的网络设备。")
                if kind == "inspection" and not str(payload.get("prompt", "")).strip():
                    raise ValueError("请输入巡检要求。")

    def start(self, kind: str, payload: dict[str, Any], *, inline: bool = False,
              previous: dict[str, Any] | None = None) -> dict[str, Any]:
        self.validate(kind, payload)
        with self._lock:
            if self._closed:
                raise ValueError("后台服务正在关闭。")
            self._refresh_inspections()
            superseded = {job["retryOf"] for job in self._jobs.values() if job.get("retryOf")}
            if sum(job["status"] in ACTIVE for job in self._jobs.values()) >= 12:
                raise ValueError("后台任务队列已满，请稍后重试。")
            for job in self._jobs.values():
                if previous and job["id"] == previous["id"]:
                    continue
                waiting = job["id"] not in superseded and job["kind"] == "inspection" and job["status"] == "partial" and any(item["status"] in {"waiting_approval", "waiting_input", "resuming"} for item in job["items"])
                if (job["status"] in ACTIVE or waiting) and job["kind"] == kind and job["payload"]["instanceId"] == payload["instanceId"] and (kind == "sync" or job["payload"].get("organization") == payload.get("organization")):
                    raise ValueError("同一范围已有任务正在运行，请等待或取消后重试。")
            now = datetime.now(UTC).isoformat()
            job = {"id": f"op_{uuid4().hex}", "kind": kind, "payload": deepcopy(payload), "status": "queued",
                   "message": "等待执行", "createdAt": now, "updatedAt": now, "total": 0, "completed": 0,
                   "items": [], "result": None, "retryOf": previous["id"] if previous else None}
            if previous and kind == "inspection" and previous["items"]:
                job["items"] = [deepcopy(item) for item in previous["items"] if item["status"] not in RETRYABLE | ACTIVE]
                job["payload"]["assetIds"] = [item["assetId"] for item in previous["items"]]
            if previous and kind == "topology" and previous.get("result"):
                job["payload"]["previousSnapshotId"] = previous["result"]["id"]
                job["payload"]["assetIds"] = previous["result"]["requestedAssetIds"]
            self._jobs[job["id"]] = job
            self._save(job)
        if inline:
            self._run(job["id"])
        else:
            self._executor.submit(self._run, job["id"])
        return self.get(job["id"])

    def cancel(self, job_id: str) -> dict[str, Any]:
        with self._lock:
            job = self._jobs[job_id]
            if job["status"] in ACTIVE:
                job.update(status="cancelling", message="正在取消，等待当前查询安全结束，不再启动后续设备操作。")
                self._save(job)
            return deepcopy(job)

    def retry(self, job_id: str) -> dict[str, Any]:
        job = self.get(job_id)
        if job["status"] not in RETRYABLE | {"partial"}:
            raise ValueError("仅失败、部分失败、取消或中断的任务可以重试。")
        return self.start(job["kind"], job["payload"], previous=job)

    def _progress(self, job_id: str) -> OperationProgress:
        def update(**values):
            with self._lock:
                job = self._jobs[job_id]
                for key in ("message", "total", "completed"):
                    if values.get(key) is not None and values[key] != "":
                        job[key] = values[key]
                item = values.get("item")
                if item is not None:
                    job["items"] = [row for row in job["items"] if row["assetId"] != item["assetId"]] + [item]
                self._save(job)
        def cancelled() -> bool:
            with self._lock:
                return self._jobs[job_id]["status"] == "cancelling"
        return OperationProgress(cancelled, update)

    def _run(self, job_id: str) -> None:
        progress = self._progress(job_id)
        try:
            progress.checkpoint()
            with self._lock:
                progress.checkpoint()
                self._jobs[job_id]["status"] = "running"
                self._save(self._jobs[job_id])
            job = self.get(job_id)
            payload = job["payload"]
            with Session(engine) as session:
                from app.services.jumpserver_service import get_jumpserver_service
                if job["kind"] == "sync":
                    result = get_jumpserver_service().sync(session, payload["instanceId"], progress=progress)
                elif job["kind"] == "topology":
                    from app.services.network_topology_service import NetworkTopologyService
                    service = NetworkTopologyService()
                    group = next(g for g in get_jumpserver_service().list_organizations(session, payload["instanceId"]) if g["id"] == payload["organization"])
                    ids = payload.get("assetIds", group["networkAssetIds"])
                    if not set(ids).issubset(group["networkAssetIds"]):
                        raise ValueError("资产组织归属已变化，请重新采集当前组织。")
                    result = service.collect(session, name=f"{group['name']} · 网络拓扑", asset_ids=ids,
                                             max_workers=payload.get("maxConcurrency", 4), progress=progress,
                                             previous_snapshot_id=payload.get("previousSnapshotId"))
                else:
                    result = self._inspect(session, job, progress)
            with self._lock:
                target = self._jobs[job_id]
                target["result"] = result
                target["status"] = "cancelled" if target["status"] == "cancelling" else result.get("status", "completed")
                target["message"] = "已取消，已完成结果保留" if target["status"] == "cancelled" else "任务执行结束"
                self._save(target)
        except OperationCancelled as exc:
            with self._lock:
                for item in self._jobs[job_id]["items"]:
                    if item["status"] in ACTIVE:
                        item.update(status="cancelled", message="已取消")
                self._jobs[job_id].update(status="cancelled", message=str(exc))
                self._save(self._jobs[job_id])
        except Exception as exc:
            with self._lock:
                for item in self._jobs[job_id]["items"]:
                    if item["status"] in ACTIVE:
                        item.update(status="failed", message="任务中断，尚未完成")
                self._jobs[job_id].update(status="failed", message=str(exc))
                self._save(self._jobs[job_id])

    def _inspect(self, session: Session, job: dict[str, Any], progress: OperationProgress) -> dict[str, Any]:
        if self._inspect_asset is None:
            raise ValueError("巡检服务尚未初始化。")
        payload = job["payload"]
        bindings = [b for b in list_bindings(session, payload["instanceId"]) if b.active and (b.org_id or b.org_name) == payload["organization"]]
        assets = {b.asset_id: b.external_name for b in bindings}
        ids = payload.get("assetIds", list(assets))
        if not ids:
            raise ValueError("该组织没有可巡检资产。")
        done = {item["assetId"]: item for item in job["items"]}
        for asset_id in ids:
            if asset_id not in done:
                progress.report(item={"assetId": asset_id, "assetName": assets.get(asset_id, str(asset_id)), "status": "queued", "message": "等待巡检"})
        progress.report(total=len(ids), completed=len(done), message="按组织逐台巡检；审批请求会保留在对应设备任务中。")
        for asset_id in ids:
            progress.checkpoint()
            if asset_id in done:
                continue
            name = assets.get(asset_id, str(asset_id))
            progress.report(item={"assetId": asset_id, "assetName": name, "status": "running", "message": "巡检中"})
            if asset_id not in assets:
                item = {"assetId": asset_id, "assetName": name, "status": "failed", "message": "资产已不属于该组织或授权已失效。"}
            else:
                item = self._inspect_asset(asset_id, payload["prompt"], name, payload.get("scheduledJobId"), progress)
                item["assetName"] = name
            done[asset_id] = item
            progress.report(completed=len(done), item=item)
        return {"status": "partial" if any(i["status"] not in {"completed", "warning"} for i in done.values()) else "completed"}

    def close(self) -> None:
        with self._lock:
            self._closed = True
            for job in self._jobs.values():
                if job["status"] in ACTIVE:
                    job["status"] = "cancelling"
                    self._save(job)
        self._executor.shutdown(wait=True)


@lru_cache(maxsize=1)
def get_operations_service() -> OperationsService:
    return OperationsService(APP_DIR / "operations")
