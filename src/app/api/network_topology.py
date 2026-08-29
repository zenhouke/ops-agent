from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlmodel import Session

from app.db.session import get_session
from app.services.network_topology_service import NetworkTopologyService


router = APIRouter(prefix="/api/network-topology", tags=["network-topology"])
service = NetworkTopologyService()


class TopologyCollectRequest(BaseModel):
    name: str = ""
    asset_ids: list[int] = Field(alias="assetIds", min_length=1)
    max_concurrency: int = Field(default=4, alias="maxConcurrency", ge=1, le=8)


@router.get("/snapshots")
def list_snapshots(session: Session = Depends(get_session)) -> list[dict[str, Any]]:
    return service.list(session)


@router.get("/snapshots/{snapshot_id}")
def get_snapshot(snapshot_id: int, session: Session = Depends(get_session)) -> dict[str, Any]:
    try:
        return service.get(session, snapshot_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Topology snapshot not found") from exc


@router.post("/snapshots", status_code=201)
def collect_snapshot(payload: TopologyCollectRequest, session: Session = Depends(get_session)) -> dict[str, Any]:
    try:
        return service.collect(session, name=payload.name, asset_ids=payload.asset_ids, max_workers=payload.max_concurrency)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
