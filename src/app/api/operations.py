from __future__ import annotations

from typing import Literal
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, model_validator
from app.services.operations_service import get_operations_service

router = APIRouter(prefix="/api/operations", tags=["operations"])


class OperationCreate(BaseModel):
    kind: Literal["sync", "topology", "inspection"]
    instanceId: int = Field(gt=0)
    organization: str | None = Field(default=None, max_length=255)
    prompt: str = Field(default="", max_length=20000)
    maxConcurrency: int = Field(default=4, ge=1, le=8)

    @model_validator(mode="after")
    def check_scope(self):
        if self.kind != "sync" and self.organization is None:
            raise ValueError("请选择组织。")
        return self


@router.get("")
def list_operations(kind: Literal["sync", "topology", "inspection"] | None = None, instance_id: int | None = None, organization: str | None = None):
    return get_operations_service().list(kind=kind, instance_id=instance_id, organization=organization)


@router.post("", status_code=202)
def create_operation(payload: OperationCreate):
    try:
        return get_operations_service().start(payload.kind, payload.model_dump(exclude={"kind"}))
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/{operation_id}")
def get_operation(operation_id: str):
    try:
        return get_operations_service().get(operation_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="后台任务不存在") from exc


@router.post("/{operation_id}/{action}")
def control_operation(operation_id: str, action: Literal["cancel", "retry"]):
    service = get_operations_service()
    try:
        return service.cancel(operation_id) if action == "cancel" else service.retry(operation_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="后台任务不存在") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
