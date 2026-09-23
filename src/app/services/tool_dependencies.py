"""Service adapters for Agent tool ports. No tool accesses persistence directly."""
import json

from app.core.approval import ApprovalContext
from app.core.tool.ports import AssetSummary
from app.db.models import Asset, AssetGroup, JumpServerAssetBinding
from sqlmodel import select
from app.db.repositories.assets import get_asset, list_assets
from app.db.repositories.audit import create_audit_log
from app.db.session import Session, engine
from app.services.approval_service import get_approval_service
from app.services.redaction_service import RedactionService


class ToolAssetCatalog:
    @staticmethod
    def _summary(asset: Asset, group_name: str = "", access_via: str = "direct") -> AssetSummary:
        if asset.id is None:
            raise ValueError("Asset is not persisted")
        return AssetSummary(asset.id, asset.name, asset.asset_type, asset.group_id,
                            tuple(tag.strip() for tag in asset.tags.split(",") if tag.strip()),
                            host=asset.host, vendor=asset.vendor, group_name=group_name, access_via=access_via)

    def list_assets(self) -> list[AssetSummary]:
        with Session(engine) as session:
            groups = {group.id: group.name for group in session.exec(select(AssetGroup)).all()}
            jump_assets = {binding.asset_id for binding in session.exec(select(JumpServerAssetBinding)).all()}
            return [self._summary(asset, groups.get(asset.group_id, ""), "jumpserver" if asset.id in jump_assets else "direct")
                    for asset in list_assets(session) if asset.id is not None]

    def get_asset(self, asset_id: int) -> AssetSummary | None:
        with Session(engine) as session:
            asset = get_asset(session, asset_id)
            return self._summary(asset) if asset is not None and asset.id is not None else None


class CommandPolicyService:
    def check_command(self, command: str, context: ApprovalContext) -> tuple[str, str]:
        return get_approval_service().check_command(command, context)

    def record_submission(self, *, runtime_id: str, terminal_id: str, asset_id: int,
                          conversation_id: str, command: str, approval_policy: str) -> None:
        with Session(engine) as session:
            create_audit_log(
                session, action="command.submitted", entity_type="runtime",
                actor="agent-with-operator-policy", asset_id=asset_id, conversation_id=conversation_id,
                details=json.dumps({"runtimeId": runtime_id, "terminalId": terminal_id,
                                    "approvalPolicy": approval_policy,
                                    "command": RedactionService().redact_text(command)}, ensure_ascii=False),
            )
