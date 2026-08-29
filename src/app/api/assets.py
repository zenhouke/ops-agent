from fastapi import APIRouter, Depends, HTTPException, Response
from sqlmodel import Session

from app.api.schemas import AssetConnectionTestRequest, AssetConnectionTestView, AssetView
from app.db.session import get_session
from app.services.asset_service import (
    GroupNotFoundError,
    ProxyAssetInUseError,
    ProxyAssetInvalidError,
    ProxyAssetNotFoundError,
    SSHKeyNotFoundError,
    create_asset_record,
    delete_asset_record,
    get_asset_record,
    list_asset_records,
    update_asset_record,
)
from app.services.asset_connection_service import AssetConnectionService
from app.shared.schemas import AssetCreate

router = APIRouter()
_asset_connection_service = AssetConnectionService()


def to_asset_view(asset) -> AssetView:
    return AssetView(
        id=asset.id or 0,
        group_id=asset.group_id,
        ssh_key_id=asset.ssh_key_id,
        proxy_asset_id=asset.proxy_asset_id,
        name=asset.name,
        asset_type=asset.asset_type,
        host=asset.host,
        port=asset.port,
        username=asset.username,
        auth_type=asset.auth_type,
        tags=asset.tags.split(",") if asset.tags else [],
        vendor=asset.vendor,
        description=asset.description,
    )


@router.get("/api/assets")
def list_assets(session: Session = Depends(get_session)) -> list[AssetView]:
    return [to_asset_view(asset) for asset in list_asset_records(session)]


@router.post("/api/assets/connection-test", response_model=AssetConnectionTestView)
def test_asset_connection(
    payload: AssetConnectionTestRequest,
    session: Session = Depends(get_session),
) -> AssetConnectionTestView:
    try:
        result = _asset_connection_service.test(
            session,
            asset_id=payload.asset_id,
            asset_data=payload.asset,
        )
    except Exception as exc:
        return AssetConnectionTestView(success=False, message=str(exc))
    return AssetConnectionTestView.model_validate(result)


@router.get("/api/assets/{asset_id}")
def get_asset(asset_id: int, session: Session = Depends(get_session)) -> AssetView:
    asset = get_asset_record(session, asset_id)
    if asset is None:
        raise HTTPException(status_code=404, detail="Asset not found")
    return to_asset_view(asset)


@router.post("/api/assets", status_code=201)
def create_asset(payload: AssetCreate, session: Session = Depends(get_session)) -> AssetView:
    try:
        asset = create_asset_record(session, payload)
    except GroupNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Group not found") from exc
    except SSHKeyNotFoundError as exc:
        raise HTTPException(status_code=404, detail="SSH key not found") from exc
    except ProxyAssetNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Proxy asset not found") from exc
    except ProxyAssetInvalidError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return to_asset_view(asset)


@router.put("/api/assets/{asset_id}")
def update_asset(asset_id: int, payload: AssetCreate, session: Session = Depends(get_session)) -> AssetView:
    try:
        asset = update_asset_record(session, asset_id, payload)
    except GroupNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Group not found") from exc
    except SSHKeyNotFoundError as exc:
        raise HTTPException(status_code=404, detail="SSH key not found") from exc
    except ProxyAssetNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Proxy asset not found") from exc
    except ProxyAssetInvalidError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if asset is None:
        raise HTTPException(status_code=404, detail="Asset not found")
    return to_asset_view(asset)


@router.delete("/api/assets/{asset_id}", status_code=204)
def delete_asset(asset_id: int, session: Session = Depends(get_session)) -> Response:
    try:
        deleted = delete_asset_record(session, asset_id)
    except ProxyAssetInUseError as exc:
        raise HTTPException(status_code=409, detail=f"Proxy asset is used by {exc.dependent_count} asset(s)") from exc
    if not deleted:
        raise HTTPException(status_code=404, detail="Asset not found")
    return Response(status_code=204)
