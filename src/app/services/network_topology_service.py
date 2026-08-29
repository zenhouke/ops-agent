from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from typing import Any

from sqlmodel import Session

from app.core.connectors.server import connector_factory
from app.core.connectors.network import NetworkConnector
from app.db.models import Asset, NetworkTopologyLink, NetworkTopologyNode, NetworkTopologySnapshot
from app.db.repositories.assets import get_asset
from app.db.repositories.network_topology import get_topology, list_topology_snapshots, save_topology
from app.shared.enums import AssetType


NETWORK_ASSET_TYPES = {AssetType.NETWORK.value, AssetType.CISCO.value, AssetType.HUAWEI.value, AssetType.H3C.value, AssetType.JUNIPER.value}


class NetworkTopologyService:
    def collect(self, session: Session, *, name: str, asset_ids: list[int], max_workers: int = 4) -> dict[str, Any]:
        unique_ids = list(dict.fromkeys(asset_ids))
        if not unique_ids:
            raise ValueError("Select at least one network asset.")
        assets: list[Asset] = []
        for asset_id in unique_ids:
            asset = get_asset(session, asset_id)
            if asset is None:
                raise ValueError(f"Asset {asset_id} was not found.")
            if asset.asset_type not in NETWORK_ASSET_TYPES:
                raise ValueError(f"Asset {asset_id} is not a network device.")
            assets.append(asset)

        results: list[dict[str, Any]] = []
        errors: list[dict[str, Any]] = []
        with ThreadPoolExecutor(max_workers=max(1, min(max_workers, 8, len(assets)))) as pool:
            futures = {pool.submit(self._collect_asset, asset): asset for asset in assets}
            for future in as_completed(futures):
                asset = futures[future]
                try:
                    results.append(future.result())
                except Exception as exc:
                    errors.append({"assetId": asset.id, "assetName": asset.name, "message": str(exc)})

        nodes, links = self._build_graph(assets, results)
        snapshot = NetworkTopologySnapshot(
            name=name.strip() or f"Topology {datetime.now(UTC).strftime('%Y-%m-%d %H:%M')}",
            status="partial" if errors else "completed",
            requested_asset_ids_json=json.dumps(unique_ids),
            errors_json=json.dumps(errors, ensure_ascii=False),
        )
        saved = save_topology(session, snapshot, nodes, links)
        return self.get(session, saved.id or 0)

    def list(self, session: Session) -> list[dict[str, Any]]:
        return [self._snapshot_summary(item) for item in list_topology_snapshots(session)]

    def get(self, session: Session, snapshot_id: int) -> dict[str, Any]:
        graph = get_topology(session, snapshot_id)
        if graph is None:
            raise KeyError(snapshot_id)
        snapshot, nodes, links = graph
        return {
            **self._snapshot_summary(snapshot),
            "nodes": [{
                "id": node.node_key, "assetId": node.asset_id, "name": node.name, "host": node.host,
                "vendor": node.vendor, "model": node.model, "serialNumber": node.serial_number,
                "softwareVersion": node.software_version, "external": node.external,
                "interfaces": json.loads(node.interfaces_json),
            } for node in nodes],
            "links": [{
                "id": link.id, "source": link.source_node_key, "target": link.target_node_key,
                "sourceInterface": link.source_interface, "targetInterface": link.target_interface,
                "protocol": link.protocol,
            } for link in links],
        }

    def _collect_asset(self, asset: Asset) -> dict[str, Any]:
        connector = connector_factory(asset)
        try:
            if not isinstance(connector, NetworkConnector):
                raise ValueError("Asset did not resolve to a network connector.")
            return {
                "asset": asset,
                "facts": connector.collect_structured("facts"),
                "interfaces": connector.collect_structured("interfaces"),
                "neighbors": connector.collect_structured("neighbors"),
            }
        finally:
            connector.close()

    def _build_graph(self, assets: list[Asset], results: list[dict[str, Any]]):
        by_asset_id = {result["asset"].id: result for result in results}
        nodes: list[NetworkTopologyNode] = []
        name_index: dict[str, str] = {}
        for asset in assets:
            result = by_asset_id.get(asset.id)
            facts = (result or {}).get("facts", {}).get("records", [])
            fact = facts[0] if facts else {}
            node_key = f"asset:{asset.id}"
            name = str(fact.get("hostname") or asset.name)
            name_index[name.lower()] = node_key
            name_index[asset.name.lower()] = node_key
            if asset.host:
                name_index[asset.host.lower()] = node_key
            nodes.append(NetworkTopologyNode(
                snapshot_id=0, node_key=node_key, asset_id=asset.id, name=name, host=asset.host,
                vendor=str((result or {}).get("facts", {}).get("vendor") or asset.vendor or asset.asset_type),
                model=self._text(fact.get("model")), serial_number=self._text(fact.get("serialNumber")),
                software_version=self._text(fact.get("softwareVersion")),
                interfaces_json=json.dumps((result or {}).get("interfaces", {}).get("records", []), ensure_ascii=False),
                raw_json=json.dumps({"facts": (result or {}).get("facts", {})}, ensure_ascii=False),
            ))
        external: dict[str, NetworkTopologyNode] = {}
        links: list[NetworkTopologyLink] = []
        seen: set[tuple[str, str, str, str]] = set()
        for result in results:
            source = f"asset:{result['asset'].id}"
            for neighbor in result["neighbors"].get("records", []):
                identity = self._text(neighbor.get("neighborName") or neighbor.get("managementAddress")) or "unknown"
                target = name_index.get(identity.lower())
                if target is None:
                    target = f"external:{identity.lower()}"
                    external.setdefault(target, NetworkTopologyNode(snapshot_id=0, node_key=target, name=identity, host=self._text(neighbor.get("managementAddress")), external=True))
                local_if = self._text(neighbor.get("localInterface"))
                remote_if = self._text(neighbor.get("neighborInterface"))
                key = (source, target, local_if, remote_if)
                reverse = (target, source, remote_if, local_if)
                if key in seen or reverse in seen:
                    continue
                seen.add(key)
                links.append(NetworkTopologyLink(snapshot_id=0, source_node_key=source, target_node_key=target, source_interface=local_if, target_interface=remote_if, protocol=self._text(neighbor.get("protocol")), raw_json=json.dumps(neighbor, ensure_ascii=False)))
        nodes.extend(external.values())
        return nodes, links

    @staticmethod
    def _text(value: Any) -> str:
        if isinstance(value, list):
            return ", ".join(str(item) for item in value)
        return str(value or "")

    @staticmethod
    def _snapshot_summary(snapshot: NetworkTopologySnapshot) -> dict[str, Any]:
        return {"id": snapshot.id, "name": snapshot.name, "status": snapshot.status, "requestedAssetIds": json.loads(snapshot.requested_asset_ids_json), "errors": json.loads(snapshot.errors_json), "createdAt": snapshot.created_at.isoformat()}
