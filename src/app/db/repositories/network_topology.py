from __future__ import annotations

from typing import Any, cast

from sqlalchemy import desc
from sqlmodel import Session, col, select

from app.db.models import NetworkTopologyLink, NetworkTopologyNode, NetworkTopologySnapshot


def save_topology(session: Session, snapshot: NetworkTopologySnapshot, nodes: list[NetworkTopologyNode], links: list[NetworkTopologyLink]) -> NetworkTopologySnapshot:
    session.add(snapshot)
    session.flush()
    if snapshot.id is None:
        raise ValueError("topology snapshot id was not generated")
    for row in [*nodes, *links]:
        row.snapshot_id = snapshot.id
        session.add(row)
    session.commit()
    session.refresh(snapshot)
    return snapshot


def list_topology_snapshots(session: Session) -> list[NetworkTopologySnapshot]:
    return list(session.exec(select(NetworkTopologySnapshot).order_by(desc(cast(Any, NetworkTopologySnapshot.created_at)))).all())


def get_topology(session: Session, snapshot_id: int):
    snapshot = session.get(NetworkTopologySnapshot, snapshot_id)
    if snapshot is None:
        return None
    nodes = list(session.exec(select(NetworkTopologyNode).where(col(NetworkTopologyNode.snapshot_id) == snapshot_id)).all())
    links = list(session.exec(select(NetworkTopologyLink).where(col(NetworkTopologyLink.snapshot_id) == snapshot_id)).all())
    return snapshot, nodes, links
