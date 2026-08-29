from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session

from app.api.schemas.jumpserver import (
    JumpServerAccountSelection,
    JumpServerAssetBindingView,
    JumpServerInstanceCreate,
    JumpServerInstanceUpdate,
    JumpServerInstanceView,
    JumpServerOperationView,
)
from app.db.session import get_session
from app.services.jumpserver_service import get_jumpserver_service

router = APIRouter(prefix="/api/jumpserver", tags=["jumpserver"])


@router.get("/instances", response_model=list[JumpServerInstanceView])
def list_instances(session: Session = Depends(get_session)):
    return get_jumpserver_service().list_instances(session)


@router.post("/instances", response_model=JumpServerInstanceView, status_code=201)
def create_instance(payload: JumpServerInstanceCreate, session: Session = Depends(get_session)):
    return get_jumpserver_service().create_instance(session, payload)


@router.put("/instances/{instance_id}", response_model=JumpServerInstanceView)
def update_instance(instance_id: int, payload: JumpServerInstanceUpdate, session: Session = Depends(get_session)):
    try:
        return get_jumpserver_service().update_instance(session, instance_id, payload)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="JumpServer instance not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/instances/{instance_id}/test", response_model=JumpServerOperationView)
def test_instance(instance_id: int, session: Session = Depends(get_session)):
    try:
        return get_jumpserver_service().test(session, instance_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="JumpServer instance not found") from exc


@router.post("/instances/{instance_id}/sync", response_model=JumpServerOperationView)
def sync_instance(instance_id: int, session: Session = Depends(get_session)):
    try:
        return get_jumpserver_service().sync(session, instance_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="JumpServer instance not found") from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/instances/{instance_id}/assets", response_model=list[JumpServerAssetBindingView])
def list_instance_assets(instance_id: int, session: Session = Depends(get_session)):
    service = get_jumpserver_service()
    if not any(item["id"] == instance_id for item in service.list_instances(session)):
        raise HTTPException(status_code=404, detail="JumpServer instance not found")
    return service.list_assets(session, instance_id)


@router.patch("/assets/{binding_id}/account", response_model=JumpServerAssetBindingView)
def select_asset_account(binding_id: int, payload: JumpServerAccountSelection, session: Session = Depends(get_session)):
    try:
        return get_jumpserver_service().select_account(session, binding_id, payload.account_ref)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="JumpServer asset binding not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
