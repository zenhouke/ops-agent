from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from typing import Any, cast

from sqlmodel import Session

from app.services.connector_factory import connector_factory
from app.services.jumpserver_service import get_jumpserver_service
from app.db.models import Asset, NetworkTopologyLink, NetworkTopologyNode, NetworkTopologySnapshot
from app.db.repositories.assets import get_asset
from app.db.repositories.jumpserver import get_binding_for_asset
from app.db.repositories.network_topology import get_topology, list_topology_snapshots, save_topology
from app.shared.enums import AssetType
from app.services.operation_progress import OperationProgress, OperationCancelled


NETWORK_ASSET_TYPES = {AssetType.NETWORK.value, AssetType.CISCO.value, AssetType.HUAWEI.value, AssetType.H3C.value, AssetType.JUNIPER.value}


class NetworkTopologyService:
    def collect_organization(self, session: Session, *, instance_id: int, organization: str, name: str, max_workers: int = 4) -> dict[str, Any]:
        groups = get_jumpserver_service().list_organizations(session, instance_id)
        group = next((item for item in groups if item["id"] == organization), None)
        if group is None:
            raise ValueError("该组织不存在或尚未同步资产，请先同步 SSH 资产。")
        return self.collect(session, name=name or f"{group['name']} · 网络拓扑", asset_ids=group["networkAssetIds"], max_workers=max_workers)

    def collect(self, session: Session, *, name: str, asset_ids: list[int], max_workers: int = 4, progress: OperationProgress | None = None, previous_snapshot_id: int | None = None) -> dict[str, Any]:
        unique_ids = list(dict.fromkeys(asset_ids))
        if not unique_ids:
            raise ValueError("Select at least one network asset.")
        assets: list[Asset] = []
        scopes: set[tuple[int, str] | None] = set()
        for asset_id in unique_ids:
            asset = get_asset(session, asset_id)
            if asset is None:
                raise ValueError(f"Asset {asset_id} was not found.")
            if asset.asset_type not in NETWORK_ASSET_TYPES:
                raise ValueError(f"Asset {asset_id} is not a network device.")
            assets.append(asset)
            binding = get_binding_for_asset(session, asset_id)
            scopes.add((binding.instance_id, binding.org_id or binding.org_name) if binding else None)
        if len(scopes) > 1:
            raise ValueError("网络拓扑必须按单个组织采集，不能混合不同组织或本地资产。")
        scope = next(iter(scopes))

        results: list[dict[str, Any]] = []
        errors: list[dict[str, Any]] = []
        reused: set[int] = set()
        if previous_snapshot_id is not None:
            previous = get_topology(session, previous_snapshot_id)
            if previous is None or set(json.loads(previous[0].requested_asset_ids_json)) != set(unique_ids):
                raise ValueError("重试快照与当前资产范围不一致。")
            old, old_nodes, old_links = previous
            if scope != (old.instance_id, old.organization):
                raise ValueError("重试快照不属于当前组织。")
            failed = {item["assetId"] for item in json.loads(old.errors_json)}
            by_id = {asset.id: asset for asset in assets}
            for node in old_nodes:
                if node.asset_id is None or node.asset_id not in by_id or node.asset_id in failed:
                    continue
                raw = json.loads(node.raw_json)
                if not raw.get("facts", {}).get("records"):
                    continue
                reused.add(node.asset_id)
                results.append({"asset": by_id[node.asset_id], "facts": raw["facts"],
                                "interfaces": {"records": json.loads(node.interfaces_json)},
                                "neighbors": raw.get("neighbors") or {"records": [json.loads(link.raw_json) for link in old_links if link.source_node_key == node.node_key]}})
        pending = [asset for asset in assets if asset.id not in reused]
        if progress:
            progress.report(total=len(assets), completed=len(reused), message="开始按设备采集")
            for asset in assets:
                progress.report(item={"assetId": asset.id, "assetName": asset.name, "status": "completed" if asset.id in reused else "queued", "message": "保留上次成功结果" if asset.id in reused else "等待采集"})

        def collect_one(asset: Asset):
            if progress:
                progress.checkpoint()
                progress.report(item={"assetId": asset.id, "assetName": asset.name, "status": "running", "message": "查询设备、接口与邻居"})
            return self._collect_asset(asset, progress) if progress else self._collect_asset(asset)

        with ThreadPoolExecutor(max_workers=max(1, min(max_workers, 8, len(assets)))) as pool:
            futures = {pool.submit(collect_one, asset): asset for asset in pending}
            for future in as_completed(futures):
                asset = futures[future]
                try:
                    results.append(future.result())
                    item_status, message = "completed", "采集完成"
                except Exception as exc:
                    errors.append({"assetId": asset.id, "assetName": asset.name, "message": str(exc)})
                    item_status = "cancelled" if isinstance(exc, OperationCancelled) else "failed"
                    message = str(exc)
                if progress:
                    progress.report(completed=len(results) + len(errors), item={"assetId": asset.id, "assetName": asset.name, "status": item_status, "message": message})

        nodes, links = self._build_graph(assets, results)
        snapshot = NetworkTopologySnapshot(
            instance_id=scope[0] if scope else None,
            organization=scope[1] if scope else None,
            name=name.strip() or f"Topology {datetime.now(UTC).strftime('%Y-%m-%d %H:%M')}",
            status="failed" if errors and not results else "partial" if errors else "completed",
            requested_asset_ids_json=json.dumps(unique_ids),
            errors_json=json.dumps(errors, ensure_ascii=False),
        )
        saved = save_topology(session, snapshot, nodes, links)
        return self.get(session, saved.id or 0)

    def list(self, session: Session, *, instance_id: int | None = None, organization: str | None = None) -> list[dict[str, Any]]:
        return [self._snapshot_summary(item) for item in list_topology_snapshots(session, instance_id=instance_id, organization=organization)]

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

    def _collect_asset(self, asset: Asset, progress: OperationProgress | None = None) -> dict[str, Any]:
        connector = connector_factory(asset)
        try:
            collector = getattr(connector, "collect_structured", None)
            if not callable(collector):
                raise ValueError("Asset connector does not support structured network collection.")
            if progress:
                progress.checkpoint()
            facts = cast(dict[str, Any], collector("facts"))
            if not facts.get("records"):
                raise ValueError("Device facts were returned but could not be parsed for this vendor.")
            if progress:
                progress.checkpoint()
            interfaces = cast(dict[str, Any], collector("interfaces"))
            if not interfaces.get("records"):
                raise ValueError("Device interfaces were returned but could not be parsed for this vendor.")
            if progress:
                progress.checkpoint()
            return {
                "asset": asset,
                "facts": facts,
                "interfaces": interfaces,
                "neighbors": cast(dict[str, Any], collector("neighbors")),
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
                raw_json=json.dumps({"facts": (result or {}).get("facts", {}), "neighbors": (result or {}).get("neighbors", {})}, ensure_ascii=False),
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
        return {"id": snapshot.id, "name": snapshot.name, "instanceId": snapshot.instance_id, "organization": snapshot.organization, "status": snapshot.status, "requestedAssetIds": json.loads(snapshot.requested_asset_ids_json), "errors": json.loads(snapshot.errors_json), "createdAt": snapshot.created_at.isoformat()}
