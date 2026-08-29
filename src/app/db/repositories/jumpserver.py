from __future__ import annotations

from sqlmodel import Session, col, select

from app.db.models import JumpServerAssetBinding, JumpServerInstance


def list_instances(session: Session) -> list[JumpServerInstance]:
    return list(session.exec(select(JumpServerInstance).order_by(JumpServerInstance.name)).all())


def get_instance(session: Session, instance_id: int) -> JumpServerInstance | None:
    return session.get(JumpServerInstance, instance_id)


def get_binding_for_asset(session: Session, asset_id: int) -> JumpServerAssetBinding | None:
    return session.exec(select(JumpServerAssetBinding).where(col(JumpServerAssetBinding.asset_id) == asset_id)).first()


def get_binding(session: Session, instance_id: int, external_asset_id: str) -> JumpServerAssetBinding | None:
    return session.exec(select(JumpServerAssetBinding).where(
        col(JumpServerAssetBinding.instance_id) == instance_id,
        col(JumpServerAssetBinding.external_asset_id) == external_asset_id,
    )).first()


def list_bindings(session: Session, instance_id: int) -> list[JumpServerAssetBinding]:
    return list(session.exec(select(JumpServerAssetBinding).where(col(JumpServerAssetBinding.instance_id) == instance_id).order_by(JumpServerAssetBinding.external_name)).all())
