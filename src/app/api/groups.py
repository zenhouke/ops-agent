from fastapi import APIRouter, Depends, HTTPException, Response
from sqlmodel import Session

from app.api.schemas import AssetGroupCreate, AssetGroupUpdate, AssetGroupView
from app.db.session import get_session
from app.services.asset_service import (
    create_asset_group_record,
    delete_asset_group_record,
    list_asset_group_records,
    update_asset_group_record,
)

router = APIRouter()


def to_asset_group_view(group) -> AssetGroupView:
    return AssetGroupView(
        id=group.id or 0,
        name=group.name,
        description=group.description,
        created_at=group.created_at,
        updated_at=group.updated_at,
        proxy_type=group.proxy_type, proxy_host=group.proxy_host, proxy_port=group.proxy_port,
        proxy_username=group.proxy_username,
    )


@router.get("/api/groups")
def list_groups(session: Session = Depends(get_session)) -> list[AssetGroupView]:
    return [to_asset_group_view(group) for group in list_asset_group_records(session)]


@router.post("/api/groups", status_code=201)
def create_group(payload: AssetGroupCreate, session: Session = Depends(get_session)) -> AssetGroupView:
    return to_asset_group_view(create_asset_group_record(session, payload))


@router.put("/api/groups/{group_id}")
def update_group(group_id: int, payload: AssetGroupUpdate, session: Session = Depends(get_session)) -> AssetGroupView:
    group = update_asset_group_record(session, group_id, payload)
    if group is None:
        raise HTTPException(status_code=404, detail="Group not found")
    return to_asset_group_view(group)


@router.delete("/api/groups/{group_id}", status_code=204)
def delete_group(group_id: int, session: Session = Depends(get_session)) -> Response:
    deleted = delete_asset_group_record(session, group_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Group not found")
    return Response(status_code=204)
