from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, model_validator
from sqlmodel import Session

from app.db.session import get_session
from app.services.network_topology_service import NetworkTopologyService


router = APIRouter(prefix="/api/network-topology", tags=["network-topology"])
service = NetworkTopologyService()


class TopologyCollectRequest(BaseModel):
    name: str = ""
    asset_ids: list[int] = Field(default_factory=list, alias="assetIds")
    instance_id: int | None = Field(default=None, alias="instanceId", gt=0)
    organization: str | None = None
    max_concurrency: int = Field(default=4, alias="maxConcurrency", ge=1, le=8)

    @model_validator(mode="after")
    def validate_scope(self):
        if self.instance_id is not None or self.organization is not None:
            if self.instance_id is None or self.organization is None or self.asset_ids:
                raise ValueError("Specify an instance and organization, or assetIds, exclusively.")
        elif not self.asset_ids:
            raise ValueError("Select assets or a JumpServer organization.")
        return self


@router.get("/snapshots")
def list_snapshots(instance_id: int | None = None, organization: str | None = None, session: Session = Depends(get_session)) -> list[dict[str, Any]]:
    if (instance_id is None) != (organization is None):
        raise HTTPException(status_code=400, detail="Specify both instance_id and organization.")
    return service.list(session, instance_id=instance_id, organization=organization)


@router.get("/snapshots/{snapshot_id}")
def get_snapshot(snapshot_id: int, session: Session = Depends(get_session)) -> dict[str, Any]:
    try:
        return service.get(session, snapshot_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Topology snapshot not found") from exc


@router.post("/snapshots", status_code=201)
def collect_snapshot(payload: TopologyCollectRequest, session: Session = Depends(get_session)) -> dict[str, Any]:
    try:
        if payload.instance_id is not None and payload.organization is not None:
            return service.collect_organization(session, instance_id=payload.instance_id, organization=payload.organization, name=payload.name, max_workers=payload.max_concurrency)
        return service.collect(session, name=payload.name, asset_ids=payload.asset_ids, max_workers=payload.max_concurrency)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="JumpServer instance not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
