from __future__ import annotations

import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from typing import Any

from sqlmodel import Session, select

from app.core.connectors.network import NetworkConnector
from app.core.connectors.jumpserver_menu import JumpServerMenuConnector
from app.core.connectors.server import ServerConnector
from app.core.connectors.device_profiles import netmiko_device_type
from app.db.models import Asset, AssetGroup, JumpServerAssetBinding, JumpServerInstance
from app.db.repositories.jumpserver import get_binding, get_binding_for_asset, get_instance, list_bindings, list_instances
from app.services.credential_service import CredentialService
from app.services.jumpserver_client import JumpServerClient
from app.services.jumpserver_ssh_client import JumpServerSSHClient
from app.services.secret_key import get_ops_agent_secret_key


class JumpServerService:
    def _credentials(self) -> CredentialService:
        return CredentialService(get_ops_agent_secret_key())

    def client(self, instance: JumpServerInstance) -> JumpServerClient:
        secret = self._credentials().decrypt_secret(
            instance.encrypted_access_key_secret,
            instance.access_key_secret_encryption_version,
        )
        return JumpServerClient(
            base_url=instance.base_url,
            org_id=instance.org_id,
            access_key_id=instance.access_key_id,
            access_key_secret=secret,
            verify_tls=instance.verify_tls,
        )

    def gateway_client(self, instance: JumpServerInstance) -> JumpServerSSHClient:
        private_key = self._credentials().decrypt_secret(
            instance.encrypted_access_key_secret,
            instance.access_key_secret_encryption_version,
        )
        return JumpServerSSHClient(
            gateway_url=instance.base_url,
            username=instance.access_key_id,
            private_key=private_key,
        )

    def list_instances(self, session: Session) -> list[dict[str, Any]]:
        return [
            self._instance_view(
                item,
                sum(1 for binding in list_bindings(session, item.id or 0) if binding.active),
            )
            for item in list_instances(session)
        ]

    def create_instance(self, session: Session, payload: Any) -> dict[str, Any]:
        if payload.access_key_secret is None:
            raise ValueError("JumpServer authentication secret is required.")
        secret = payload.access_key_secret.get_secret_value()
        row = JumpServerInstance(
            auth_mode=payload.auth_mode,
            name=payload.name.strip(),
            base_url=payload.base_url.strip().rstrip("/"),
            org_id=payload.org_id.strip(),
            access_key_id=payload.access_key_id.strip(),
            access_key_secret_encryption_version=CredentialService.encryption_version,
            encrypted_access_key_secret=self._credentials().encrypt_secret(secret),
            verify_tls=payload.verify_tls,
            enabled=payload.enabled,
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        return self._instance_view(row, 0)

    def update_instance(self, session: Session, instance_id: int, payload: Any) -> dict[str, Any]:
        row = get_instance(session, instance_id)
        if row is None:
            raise KeyError(instance_id)
        if payload.auth_mode is not None and payload.auth_mode != row.auth_mode and payload.access_key_secret is None:
            raise ValueError("Changing JumpServer authentication mode requires a new secret or private key.")
        next_mode = payload.auth_mode or row.auth_mode
        next_url = payload.base_url or row.base_url
        if next_mode == "ssh_gateway" and not next_url.startswith("ssh://"):
            raise ValueError("SSH gateway mode requires an ssh:// address.")
        if next_mode == "access_key" and not next_url.startswith(("http://", "https://")):
            raise ValueError("Access Key mode requires an http:// or https:// address.")
        for key in ("name", "auth_mode", "base_url", "org_id", "access_key_id", "verify_tls", "enabled"):
            value = getattr(payload, key)
            if value is not None:
                setattr(row, key, value.strip().rstrip("/") if isinstance(value, str) else value)
        if payload.access_key_secret is not None and payload.access_key_secret.get_secret_value():
            row.encrypted_access_key_secret = self._credentials().encrypt_secret(payload.access_key_secret.get_secret_value())
            row.access_key_secret_encryption_version = CredentialService.encryption_version
        row.updated_at = datetime.now(UTC)
        session.add(row)
        session.commit()
        session.refresh(row)
        active_count = sum(1 for binding in list_bindings(session, instance_id) if binding.active)
        return self._instance_view(row, active_count)

    def test(self, session: Session, instance_id: int) -> dict[str, Any]:
        row = get_instance(session, instance_id)
        if row is None:
            raise KeyError(instance_id)
        try:
            client = self.gateway_client(row) if row.auth_mode == "ssh_gateway" else self.client(row)
            profile = client.profile()
            row.connection_status = "ok"
            row.last_error = ""
            message = f"Connected as {profile.get('username') or profile.get('name') or 'JumpServer user'}."
            success = True
        except Exception as exc:
            row.connection_status = "failed"
            row.last_error = str(exc)
            message = str(exc)
            success = False
        row.updated_at = datetime.now(UTC)
        session.add(row)
        session.commit()
        return {"success": success, "message": message}

    def sync(self, session: Session, instance_id: int) -> dict[str, Any]:
        instance = get_instance(session, instance_id)
        if instance is None:
            raise KeyError(instance_id)
        client: Any = self.gateway_client(instance) if instance.auth_mode == "ssh_gateway" else self.client(instance)
        try:
            remote_assets = client.list_all_assets()
        except Exception as exc:
            instance.connection_status = "failed"
            instance.last_error = str(exc)
            instance.updated_at = datetime.now(UTC)
            session.add(instance)
            session.commit()
            raise
        details: dict[str, dict[str, Any]] = {}

        def load_detail(external_id: str) -> dict[str, Any]:
            if instance.auth_mode == "ssh_gateway":
                return next((item for item in remote_assets if str(item.get("id")) == external_id), {})
            detail = client.get_permitted_asset(external_id)
            if not isinstance(detail.get("permed_accounts"), list) and not isinstance(detail.get("accounts"), list):
                detail["permed_accounts"] = client.get_permitted_accounts(external_id, detail)
            return detail

        with ThreadPoolExecutor(max_workers=min(4, max(1, len(remote_assets)))) as pool:
            futures = {pool.submit(load_detail, str(item.get("id", ""))): str(item.get("id", "")) for item in remote_assets if item.get("id")}
            for future in as_completed(futures):
                external_id = futures[future]
                try:
                    details[external_id] = future.result()
                except Exception:
                    details[external_id] = {}

        now = datetime.now(UTC)
        group_marker = f"ops-agent:jumpserver-instance:{instance_id}"
        jumpserver_group = session.exec(
            select(AssetGroup).where(AssetGroup.description == group_marker)
        ).first()
        expected_group_name = f"JumpServer · {instance.name}"
        if jumpserver_group is None:
            jumpserver_group = AssetGroup(
                name=expected_group_name,
                description=group_marker,
            )
            session.add(jumpserver_group)
            session.flush()
        elif jumpserver_group.name != expected_group_name:
            jumpserver_group.name = expected_group_name
            jumpserver_group.updated_at = now
            session.add(jumpserver_group)
        if jumpserver_group.id is None:
            raise ValueError("JumpServer asset group id was not generated.")
        seen: set[str] = set()
        created = updated = skipped = 0
        for remote in remote_assets:
            external_id = str(remote.get("id", ""))
            if not external_id:
                continue
            detail = details.get(external_id) or remote
            normalized = self._normalize_asset(remote, detail)
            if not normalized["supported"]:
                skipped += 1
                continue
            seen.add(external_id)
            binding = get_binding(session, instance_id, external_id)
            if binding is None:
                local_asset = Asset(
                    group_id=jumpserver_group.id, name=normalized["name"], asset_type=normalized["local_type"],
                    host=normalized["address"], port=normalized["port"], username=normalized["account_username"] or "JumpServer",
                    auth_type="jumpserver", tags="jumpserver", vendor=normalized["platform"],
                    description=f"Managed by JumpServer instance {instance.name}",
                )
                session.add(local_asset); session.flush()
                if local_asset.id is None:
                    raise ValueError("Local JumpServer asset id was not generated.")
                binding = JumpServerAssetBinding(instance_id=instance_id, asset_id=local_asset.id, external_asset_id=external_id, external_name=normalized["name"])
                created += 1
            else:
                local_asset = session.get(Asset, binding.asset_id)
                if local_asset is None:
                    continue
                local_asset.name = normalized["name"]; local_asset.host = normalized["address"]; local_asset.port = normalized["port"]
                local_asset.asset_type = normalized["local_type"]; local_asset.vendor = normalized["platform"]
                updated += 1
            local_asset.group_id = jumpserver_group.id
            valid_refs = {str(account.get("id") or account.get("name") or account.get("username") or "") for account in normalized["accounts"]}
            if instance.auth_mode != "ssh_gateway" and (
                not binding.account_ref or binding.account_ref not in valid_refs
            ):
                binding.account_ref, binding.account_username = normalized["account_ref"], normalized["account_username"]
            local_asset.username = binding.account_username or "JumpServer"
            local_asset.auth_type = "jumpserver"
            local_asset.description = f"Managed by JumpServer instance {instance.name}"
            binding.external_name = normalized["name"]; binding.address = normalized["address"]; binding.platform = normalized["platform"]
            binding.category = normalized["category"]; binding.asset_type = normalized["type"]
            binding.protocols_json = json.dumps(normalized["protocols"], ensure_ascii=False); binding.accounts_json = json.dumps(normalized["accounts"], ensure_ascii=False)
            binding.active = True; binding.last_seen_at = now; binding.updated_at = now
            session.add(local_asset); session.add(binding)
        for binding in list_bindings(session, instance_id):
            if binding.external_asset_id not in seen:
                binding.active = False; binding.updated_at = now; session.add(binding)
                local_asset = session.get(Asset, binding.asset_id)
                if local_asset is not None:
                    local_asset.description = f"JumpServer access revoked on instance {instance.name}"
                    local_asset.updated_at = now
                    session.add(local_asset)
        instance.last_sync_at = now; instance.connection_status = "ok"; instance.last_error = ""; instance.updated_at = now
        session.add(instance); session.commit()
        return {
            "success": True,
            "created": created,
            "updated": updated,
            "total": len(remote_assets),
            "skipped": skipped,
        }

    def list_assets(self, session: Session, instance_id: int) -> list[dict[str, Any]]:
        return [self._binding_view(item) for item in list_bindings(session, instance_id)]

    def select_account(self, session: Session, binding_id: int, account_ref: str) -> dict[str, Any]:
        binding = session.get(JumpServerAssetBinding, binding_id)
        if binding is None:
            raise KeyError(binding_id)
        instance = get_instance(session, binding.instance_id)
        if instance is not None and instance.auth_mode == "ssh_gateway":
            binding.account_ref = account_ref.strip()
            binding.account_username = account_ref.strip()
            binding.updated_at = datetime.now(UTC)
            session.add(binding)
            asset = session.get(Asset, binding.asset_id)
            if asset is not None:
                asset.username = binding.account_username
                asset.updated_at = datetime.now(UTC)
                session.add(asset)
            session.commit()
            session.refresh(binding)
            return self._binding_view(binding)
        accounts = json.loads(binding.accounts_json)
        account = next((item for item in accounts if str(item.get("id") or item.get("name") or item.get("username") or "") == account_ref), None)
        if account is None:
            raise ValueError("Selected account is not permitted for this asset.")
        binding.account_ref = account_ref; binding.account_username = str(account.get("username") or account.get("name") or "")
        binding.updated_at = datetime.now(UTC); session.add(binding)
        asset = session.get(Asset, binding.asset_id)
        if asset is not None:
            asset.username = binding.account_username or "JumpServer"; asset.updated_at = datetime.now(UTC); session.add(asset)
        session.commit(); session.refresh(binding)
        return self._binding_view(binding)

    def connector_for_asset(self, session: Session, asset: Asset):
        if asset.id is None:
            return None
        binding = get_binding_for_asset(session, asset.id)
        if binding is None:
            return None
        if not binding.active:
            raise ValueError("JumpServer asset is inactive because its authorization was revoked.")
        instance = get_instance(session, binding.instance_id)
        if instance is None or not instance.enabled:
            raise ValueError("JumpServer instance is unavailable.")
        if instance.auth_mode == "ssh_gateway":
            gateway = self.gateway_client(instance)
            if not binding.account_ref:
                discovered_account = gateway.discover_default_account(
                    asset_name=binding.external_name,
                    address=binding.address,
                )
                binding.account_ref = discovered_account
                binding.account_username = discovered_account
                binding.updated_at = datetime.now(UTC)
                persisted_asset = session.get(Asset, binding.asset_id)
                if persisted_asset is not None:
                    persisted_asset.username = discovered_account
                    persisted_asset.updated_at = datetime.now(UTC)
                    session.add(persisted_asset)
                session.add(binding)
                session.commit()
            return JumpServerMenuConnector(
                gateway,
                asset_name=binding.external_name,
                address=binding.address,
                account=binding.account_ref,
                asset_type=asset.asset_type,
                shell_kind="network" if asset.asset_type in {"network", "cisco", "huawei", "h3c", "juniper"} else "posix",
            )
        if not binding.account_ref:
            raise ValueError("JumpServer asset has no permitted account selected.")
        client = self.client(instance)
        protocols = json.loads(binding.protocols_json)
        protocol_names = [
            str(item.get("name", "")).lower()
            for item in protocols
            if isinstance(item, dict)
        ]
        target_protocol = "ssh" if "ssh" in protocol_names else "telnet" if "telnet" in protocol_names else "ssh"
        connection = client.create_ssh_connection(
            asset_id=binding.external_asset_id,
            account_ref=binding.account_ref,
            protocol=target_protocol,
        )
        close_callback = lambda: client.expire_token(connection.token_id)
        if asset.asset_type in {"network", "cisco", "huawei", "h3c", "juniper"}:
            return NetworkConnector({
                "asset_type": asset.asset_type, "device_type": netmiko_device_type(asset.asset_type) or "autodetect",
                "host": connection.host, "port": connection.port, "username": f"JMS-{connection.token_id}", "password": connection.token_value,
            }, close_callback=close_callback)
        return ServerConnector(connection.host, connection.port, f"JMS-{connection.token_id}", password=connection.token_value, close_callback=close_callback)

    def _normalize_asset(self, remote: dict[str, Any], detail: dict[str, Any]) -> dict[str, Any]:
        platform_value = detail.get("platform") or remote.get("platform") or ""
        platform = str(platform_value.get("name") or platform_value.get("type") or "") if isinstance(platform_value, dict) else str(platform_value)
        category = str(detail.get("category") or remote.get("category") or "")
        asset_type = str(detail.get("type") or remote.get("type") or "")
        asset_name = str(detail.get("name") or remote.get("name") or "")
        combined = f"{asset_name} {platform} {category} {asset_type}".lower()
        local_type = next(
            (vendor for vendor in ("cisco", "huawei", "h3c", "juniper") if vendor in combined),
            "network" if any(word in combined for word in ("device", "network", "switch", "router")) else "linux",
        )
        if re.search(r"(?:^|[^a-z0-9])(?:qfx|mx|ex|srx|ptx|acx)\d", combined):
            local_type = "juniper"
        protocols = detail.get("protocols") or remote.get("protocols") or []
        selected_protocol = next(
            (
                item
                for name in ("ssh", "telnet")
                for item in protocols
                if isinstance(item, dict) and str(item.get("name", "")).lower() == name
            ),
            {},
        )
        supported = bool(selected_protocol)
        accounts_raw = detail.get("permed_accounts") or remote.get("permed_accounts") or []
        accounts = [{key: item.get(key) for key in ("id", "name", "username", "alias", "secret_type", "privileged", "is_active")} for item in accounts_raw if isinstance(item, dict)]
        active_accounts = [item for item in accounts if item.get("is_active") is not False]
        selected = active_accounts[0] if active_accounts else (accounts[0] if accounts else {})
        account_ref = str(selected.get("id") or selected.get("name") or selected.get("username") or "")
        return {
            "name": str(detail.get("name") or remote.get("name") or detail.get("address") or remote.get("address") or "JumpServer asset"),
            "address": str(detail.get("address") or remote.get("address") or ""), "platform": platform,
            "category": category, "type": asset_type, "local_type": local_type, "protocols": protocols,
            "port": int(selected_protocol.get("port", 22) or 22), "accounts": accounts, "account_ref": account_ref,
            "account_username": str(selected.get("username") or selected.get("name") or ""), "supported": supported,
        }

    @staticmethod
    def _instance_view(row: JumpServerInstance, asset_count: int) -> dict[str, Any]:
        return {"id": row.id, "authMode": row.auth_mode, "name": row.name, "baseUrl": row.base_url, "orgId": row.org_id, "accessKeyId": row.access_key_id,
                "accessKeySecretMasked": "••••••••", "verifyTls": row.verify_tls, "enabled": row.enabled,
                "connectionStatus": row.connection_status, "lastError": row.last_error, "lastSyncAt": row.last_sync_at.isoformat() if row.last_sync_at else None, "assetCount": asset_count}

    @staticmethod
    def _binding_view(row: JumpServerAssetBinding) -> dict[str, Any]:
        return {"id": row.id, "assetId": row.asset_id, "externalAssetId": row.external_asset_id, "name": row.external_name,
                "address": row.address, "platform": row.platform, "category": row.category, "type": row.asset_type,
                "accounts": json.loads(row.accounts_json), "accountRef": row.account_ref, "accountUsername": row.account_username, "active": row.active}


_service: JumpServerService | None = None


def get_jumpserver_service() -> JumpServerService:
    global _service
    if _service is None:
        _service = JumpServerService()
    return _service
