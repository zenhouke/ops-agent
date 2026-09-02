from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any

from app.core.approval import ApprovalChecker, ApprovalContext, ApprovalPermissions, ApprovalPolicy, TrustedCommandRule, create_default_policy
from app.shared.config import SETTINGS_PATH
from app.utils.file_store import atomic_write_json


class ApprovalService:

    def __init__(self, config_path: str | None = None):
        if config_path is None:
            config_path = str(SETTINGS_PATH)

        self._config_path = Path(config_path)
        self._lock = threading.RLock()
        self._policy = self._load_policy()
        self._checker = ApprovalChecker(self._policy)

    def _load_policy(self) -> ApprovalPolicy:
        if not self._config_path.exists():
            policy = create_default_policy()
            self._save_policy(policy)
            return policy

        try:
            with open(self._config_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            permissions_data = data.get("permissions") if isinstance(data, dict) else None
            if isinstance(permissions_data, dict):
                deny = [item.strip() for item in permissions_data.get("deny", []) if isinstance(item, str) and item.strip()]
                trusted_commands = []
                for item in data.get("trusted_commands", []):
                    if not isinstance(item, dict):
                        continue
                    command = str(item.get("command", "")).strip()
                    conversation_id = str(item.get("conversation_id", "")).strip()
                    profile = str(item.get("profile", "")).strip()
                    asset_id = item.get("asset_id")
                    if command and command != "*" and conversation_id and profile and isinstance(asset_id, int):
                        trusted_commands.append(TrustedCommandRule(command, conversation_id, asset_id, profile))
                policy = ApprovalPolicy(
                    permissions=ApprovalPermissions(allow=[], deny=deny),
                    trusted_commands=trusted_commands,
                )
                if permissions_data.get("allow"):
                    self._save_policy(policy)
                return policy

            approval_data = data.get("approval") if isinstance(data, dict) else None
            if isinstance(approval_data, dict):
                policy = create_default_policy()
                self._save_policy(policy)
                return policy
        except Exception:
            return create_default_policy()

        policy = create_default_policy()
        self._save_policy(policy)
        return policy

    def _save_policy(self, policy: ApprovalPolicy | None = None) -> None:
        if policy is None:
            policy = self._policy

        with self._lock:
            existing_data: dict[str, Any] = {}
            if self._config_path.exists():
                try:
                    with open(self._config_path, "r", encoding="utf-8") as f:
                        loaded = json.load(f)
                    if isinstance(loaded, dict):
                        existing_data = loaded
                except Exception:
                    existing_data = {}

            existing_data.pop("approval", None)
            existing_data["permissions"] = {"allow": [], "deny": policy.permissions.deny}
            existing_data["trusted_commands"] = [
                {
                    "command": rule.command,
                    "conversation_id": rule.conversation_id,
                    "asset_id": rule.asset_id,
                    "profile": rule.profile,
                }
                for rule in policy.trusted_commands
            ]
            atomic_write_json(self._config_path, existing_data)

    def check_command(self, command: str, context: ApprovalContext | None = None) -> tuple[str, str]:
        return self._checker.check_command(command, context)

    def add_allow_command(self, command: str, *, context: ApprovalContext) -> bool:
        command = command.strip()
        if not command or command == "*" or not context.conversation_id or context.asset_id is None:
            return False
        rule = TrustedCommandRule(command, context.conversation_id, context.asset_id, context.profile)
        with self._lock:
            if rule in self._policy.trusted_commands:
                return False
            self._policy.trusted_commands.append(rule)
            self._checker = ApprovalChecker(self._policy)
            self._save_policy()
            return True

    def add_allow_prefix(self, prefix: str) -> bool:
        """Legacy global trust cannot be represented safely and is intentionally rejected."""
        _ = prefix
        return False

    def get_policy_dict(self) -> dict[str, Any]:
        return {"permissions": {"allow": [], "deny": self._policy.permissions.deny}}

    def update_policy_from_dict(self, data: dict[str, Any]) -> None:
        permissions_data = data.get("permissions") if isinstance(data, dict) else None
        deny = permissions_data.get("deny", []) if isinstance(permissions_data, dict) else []
        with self._lock:
            self._policy = ApprovalPolicy(
                permissions=ApprovalPermissions(
                    allow=[],
                    deny=[item.strip() for item in deny if isinstance(item, str) and item.strip()],
                ),
                trusted_commands=self._policy.trusted_commands,
            )
            self._checker = ApprovalChecker(self._policy)
            self._save_policy()


_approval_service: ApprovalService | None = None


def get_approval_service() -> ApprovalService:
    global _approval_service
    if _approval_service is None:
        _approval_service = ApprovalService()
    return _approval_service
