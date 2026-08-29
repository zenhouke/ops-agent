from __future__ import annotations

from types import SimpleNamespace

from sqlmodel import Session

from app.core.connectors.network import NetworkConnector
from app.core.connectors.server import connector_factory
from app.services.asset_service import get_asset_record


class AssetConnectionService:
    def test(self, session: Session, *, asset_id: int | None, asset_data) -> dict[str, object]:
        if asset_id is not None and get_asset_record(session, asset_id) is None:
            raise ValueError("Asset not found")

        payload = asset_data.model_dump(exclude={"credential_secret"})
        payload["id"] = asset_id
        payload["asset_type"] = asset_data.asset_type.value
        payload["tags"] = list(asset_data.tags)
        transient_asset = SimpleNamespace(**payload)
        credential_override = (
            asset_data.credential_secret.get_secret_value()
            if asset_data.credential_secret is not None
            else None
        )
        connector = connector_factory(
            transient_asset,
            credential_secret_override=credential_override,
        )
        try:
            if isinstance(connector, NetworkConnector):
                facts = connector.connection_facts()
                return {
                    "success": True,
                    "message": "Network device connection succeeded.",
                    "detected_device_type": facts["deviceType"],
                    "detected_asset_type": facts["assetType"],
                    "prompt": facts["prompt"],
                }
            connector.open_interactive()
            return {
                "success": True,
                "message": "Connection succeeded.",
            }
        finally:
            connector.close()
