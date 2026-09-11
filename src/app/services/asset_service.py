import json

from sqlmodel import select

from app.db.models import Asset, AssetGroup
from app.db.repositories.assets import (
    create_asset,
    create_asset_group,
    delete_asset_graph,
    delete_asset_group,
    get_asset_group,
    list_asset_groups,
    list_assets,
    list_assets_by_proxy_asset_id,
    update_asset_group,
)
from app.db.repositories.audit import create_audit_log
from app.db.repositories.common import commit_refresh, touch_updated_at
from app.db.repositories.credentials import create_credential, get_credential_by_asset_id, update_credential
from app.db.repositories.ssh_keys import get_ssh_key
from app.shared.enums import AssetType
from app.services.credential_factory import build_credential_service
from app.services.credential_service import CredentialService


class GroupNotFoundError(ValueError):
    pass


class SSHKeyNotFoundError(ValueError):
    pass


class ProxyAssetNotFoundError(ValueError):
    pass


class ProxyAssetInvalidError(ValueError):
    pass


class ProxyAssetInUseError(ValueError):
    def __init__(self, dependent_count: int):
        self.dependent_count = dependent_count
        super().__init__(f"Proxy asset is used by {dependent_count} asset(s)")


PROXY_TARGET_TYPES = {
    AssetType.LINUX.value,
    AssetType.NETWORK.value,
    AssetType.CISCO.value,
    AssetType.HUAWEI.value,
    AssetType.JUNIPER.value,
    AssetType.H3C.value,
}
PROXY_CANDIDATE_TYPES = {AssetType.LINUX.value}


def _ensure_group_exists(session, group_id):
    if group_id is not None and get_asset_group(session, group_id) is None:
        raise GroupNotFoundError("Group not found")


def _ensure_ssh_key_exists(session, ssh_key_id):
    if ssh_key_id is not None and get_ssh_key(session, ssh_key_id) is None:
        raise SSHKeyNotFoundError("SSH key not found")


def _ensure_proxy_asset_valid(session, proxy_asset_id, *, target_asset_id, target_asset_type):
    if proxy_asset_id is None:
        return
    if target_asset_type not in PROXY_TARGET_TYPES:
        raise ProxyAssetInvalidError("SSH proxy is supported only for Linux and network device assets in this version")
    if proxy_asset_id == target_asset_id:
        raise ProxyAssetInvalidError("Asset cannot use itself as a proxy")
    proxy_asset = get_asset_record(session, proxy_asset_id)
    if proxy_asset is None:
        raise ProxyAssetNotFoundError("Proxy asset not found")
    if proxy_asset.asset_type not in PROXY_CANDIDATE_TYPES:
        raise ProxyAssetInvalidError("Proxy asset must be a Linux asset")
    if proxy_asset.proxy_asset_id is not None:
        raise ProxyAssetInvalidError("Proxy chains are not supported")


def create_asset_group_record(session, payload):
    proxy_password = payload.proxy_password.get_secret_value() if payload.proxy_password else ""
    encrypted = build_credential_service().encrypt_secret(proxy_password) if proxy_password else ""
    return create_asset_group(session, name=payload.name, description=payload.description,
                              proxy_type=payload.proxy_type, proxy_host=payload.proxy_host,
                              proxy_port=payload.proxy_port, proxy_username=payload.proxy_username,
                              proxy_password_encrypted=encrypted)


def ensure_default_asset_group(session):
    existing_group = session.exec(select(AssetGroup).where(AssetGroup.name == "default")).first()
    if existing_group is not None:
        return existing_group
    return create_asset_group(session, name="default", description="Default Group")


def list_asset_group_records(session):
    return list_asset_groups(session)


def get_asset_group_record(session, group_id):
    return get_asset_group(session, group_id)


def update_asset_group_record(session, group_id, payload):
    values = payload.model_dump(exclude={"proxy_password"}, exclude_unset=True)
    if payload.proxy_password is not None and payload.proxy_password.get_secret_value():
        values["proxy_password_encrypted"] = build_credential_service().encrypt_secret(payload.proxy_password.get_secret_value())
    return update_asset_group(session, group_id, **values)


def delete_asset_group_record(session, group_id):
    return delete_asset_group(session, group_id)


def create_asset_record(session, asset_data):
    _ensure_group_exists(session, asset_data.group_id)
    _ensure_ssh_key_exists(session, asset_data.ssh_key_id)
    _ensure_proxy_asset_valid(
        session,
        asset_data.proxy_asset_id,
        target_asset_id=None,
        target_asset_type=asset_data.asset_type.value,
    )
    asset = create_asset(session, asset_data)
    asset_id = asset.id
    if asset_id is None:
        raise ValueError("asset id is required")
    if asset_data.proxy_password is not None and asset_data.proxy_password.get_secret_value():
        asset.proxy_password_encrypted = build_credential_service().encrypt_secret(asset_data.proxy_password.get_secret_value())
        session.add(asset)
        session.commit()
    credential_secret = asset_data.credential_secret
    if credential_secret is None:
        return asset
    encrypted_blob = build_credential_service().encrypt_secret(credential_secret.get_secret_value())
    create_credential(
        session,
        asset_id=asset_id,
        encryption_version=CredentialService.encryption_version,
        encrypted_blob=encrypted_blob,
    )
    return asset


def get_asset_record(session, asset_id):
    return session.exec(select(Asset).where(Asset.id == asset_id)).first()


def list_asset_records(session):
    return list_assets(session)


def get_asset_credential_record(session, asset_id):
    return get_credential_by_asset_id(session, asset_id)


def update_asset_record(session, asset_id, asset_data):
    asset = get_asset_record(session, asset_id)
    if asset is None:
        return None
    _ensure_group_exists(session, asset_data.group_id)
    _ensure_ssh_key_exists(session, asset_data.ssh_key_id)
    _ensure_proxy_asset_valid(
        session,
        asset_data.proxy_asset_id,
        target_asset_id=asset_id,
        target_asset_type=asset_data.asset_type.value,
    )
    dependent_assets = list_assets_by_proxy_asset_id(session, asset_id)
    if dependent_assets and asset_data.asset_type.value not in PROXY_CANDIDATE_TYPES:
        raise ProxyAssetInvalidError("Asset is used as a proxy and must remain a Linux asset")
    if dependent_assets and asset_data.proxy_asset_id is not None:
        raise ProxyAssetInvalidError("Asset is used as a proxy and cannot itself use a proxy")

    payload = asset_data.model_dump(exclude={"credential_secret"})
    payload.pop("proxy_password", None)
    payload["asset_type"] = asset_data.asset_type.value
    payload["tags"] = ",".join(asset_data.tags)
    if asset_data.proxy_password is not None and asset_data.proxy_password.get_secret_value():
        payload["proxy_password_encrypted"] = build_credential_service().encrypt_secret(asset_data.proxy_password.get_secret_value())

    for key, value in payload.items():
        setattr(asset, key, value)
    touch_updated_at(asset)

    commit_refresh(session, asset)

    credential_secret = asset_data.credential_secret
    if credential_secret is None:
        return asset
    encrypted_blob = build_credential_service().encrypt_secret(credential_secret.get_secret_value())
    updated_credential = update_credential(
        session,
        asset_id,
        encryption_version=CredentialService.encryption_version,
        encrypted_blob=encrypted_blob,
    )
    if updated_credential is None:
        create_credential(
            session,
            asset_id=asset_id,
            encryption_version=CredentialService.encryption_version,
            encrypted_blob=encrypted_blob,
        )
    return asset


def delete_asset_record(session, asset_id):
    asset = get_asset_record(session, asset_id)
    if asset is None:
        return False
    dependent_assets = list_assets_by_proxy_asset_id(session, asset_id)
    if dependent_assets:
        raise ProxyAssetInUseError(len(dependent_assets))

    snapshot = {
        "id": asset.id,
        "name": asset.name,
        "asset_type": asset.asset_type,
        "host": asset.host,
        "port": asset.port,
        "username": asset.username,
        "auth_type": asset.auth_type,
        "proxy_asset_id": asset.proxy_asset_id,
        "tags": asset.tags,
        "vendor": asset.vendor,
        "description": asset.description,
    }
    deleted = delete_asset_graph(session, asset_id)
    if deleted:
        create_audit_log(
            session,
            action="asset.deleted",
            entity_type="asset",
            entity_id=asset_id,
            asset_id=asset_id,
            details=json.dumps(snapshot, ensure_ascii=False),
        )
    return deleted
