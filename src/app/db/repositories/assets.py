from typing import Any, cast

from sqlalchemy import delete, desc, update
from sqlmodel import Session, col, select

from app.db.models import  Asset, AssetGroup, Credential, ModelUsage
from app.db.repositories.common import commit_refresh, touch_updated_at
from app.shared.schemas import AssetCreate


def create_asset_group(session: Session, *, name: str, description: str = "", **proxy) -> AssetGroup:
    row = AssetGroup(name=name, description=description, **proxy)
    return commit_refresh(session, row)


def list_asset_groups(session: Session) -> list[AssetGroup]:
    return list(session.exec(select(AssetGroup).order_by(AssetGroup.name)).all())


def get_asset_group(session: Session, group_id: int) -> AssetGroup | None:
    return session.get(AssetGroup, group_id)


def update_asset_group(session: Session, group_id: int, *, name: str | None = None, description: str | None = None, **proxy) -> AssetGroup | None:
    row = get_asset_group(session, group_id)
    if row is None:
        return None
    if name is not None:
        row.name = name
    if description is not None:
        row.description = description
    for key, value in proxy.items():
        if value is not None:
            setattr(row, key, value)
    touch_updated_at(row)
    return commit_refresh(session, row)


def delete_asset_group(session: Session, group_id: int) -> bool:
    row = get_asset_group(session, group_id)
    if row is None:
        return False
    session.exec(update(Asset).where(col(Asset.group_id) == group_id).values(group_id=None))
    session.delete(row)
    session.commit()
    return True


def create_asset(session: Session, data: AssetCreate) -> Asset:
    payload = data.model_dump(exclude={"credential_secret", "proxy_password"})
    payload["asset_type"] = data.asset_type.value
    payload["tags"] = ",".join(data.tags)
    asset = Asset(**payload)
    return commit_refresh(session, asset)


def list_assets(session: Session) -> list[Asset]:
    return list(session.exec(select(Asset).order_by(desc(cast(Any, Asset.id)))).all())


def list_assets_by_proxy_asset_id(session: Session, proxy_asset_id: int) -> list[Asset]:
    return list(session.exec(select(Asset).where(col(Asset.proxy_asset_id) == proxy_asset_id)).all())


def get_asset(session: Session, asset_id: int) -> Asset | None:
    return session.exec(select(Asset).where(Asset.id == asset_id)).first()


def delete_asset_graph(session: Session, asset_id: int) -> bool:
    asset = session.get(Asset, asset_id)
    if asset is None:
        return False

    session.exec(delete(Credential).where(col(Credential.asset_id) == asset_id))

    session.delete(asset)
    session.commit()
    return True
