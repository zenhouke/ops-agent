from __future__ import annotations

from dataclasses import dataclass, field

from app.core.connectors.device_profiles import NETWORK_CLI_PROFILE, matches_command_prefix, select_device_profile


@dataclass
class ApprovalPermissions:
    allow: list[str] = field(default_factory=list)
    deny: list[str] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class TrustedCommandRule:
    command: str
    conversation_id: str
    asset_id: int
    profile: str


@dataclass
class ApprovalPolicy:
    permissions: ApprovalPermissions = field(default_factory=ApprovalPermissions)
    trusted_commands: list[TrustedCommandRule] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class ApprovalContext:
    conversation_id: str = ""
    asset_id: int | None = None
    asset_type: str = ""
    shell_type: str = ""
    profile: str = "posix-shell"
    vendor: str | None = None


class ApprovalChecker:

    def __init__(self, policy: ApprovalPolicy):
        self._policy = policy

    def check_command(self, command: str, context: ApprovalContext | None = None) -> tuple[str, str]:
        command = command.strip()
        for prefix in self._policy.permissions.deny:
            if _matches_command_prefix(prefix, command):
                return "deny", f"deny prefix: {prefix}"

        effective_context = context or ApprovalContext()
        if effective_context.profile == NETWORK_CLI_PROFILE:
            if is_multiline_network_command(command):
                return "deny", "network device commands must be submitted one line at a time for per-command approval"
            level = _classify_network_command(command, effective_context)
            for trusted_rule in self._policy.trusted_commands:
                if _matches_trusted_command(trusted_rule, command, effective_context) and level == 0:
                    return "allow", "trusted exact command"
            if level == 0:
                return "ask", "network device read-only command, handled by default approval policy"
            if level == 1:
                return "ask", "network device mode switch command requires approval"
            if level == 2:
                return "ask", "network device configuration change command requires approval"
            if level == 3:
                return "ask", "network device save configuration command requires separate approval"
            return "ask", "network device high-risk command requires approval"

        for trusted_rule in self._policy.trusted_commands:
            if _matches_trusted_command(trusted_rule, command, effective_context):
                return "allow", "trusted exact command"
        return "ask", "default policy: approval required"


def _matches_command_prefix(prefix: str, command: str) -> bool:
    return matches_command_prefix(prefix, command)


def _matches_trusted_command(rule: TrustedCommandRule, command: str, context: ApprovalContext) -> bool:
    """A trust grant is exact and scoped to one conversation, asset, and execution profile."""
    return bool(
        rule.command
        and rule.command != "*"
        and command == rule.command
        and context.conversation_id
        and context.asset_id is not None
        and context.conversation_id == rule.conversation_id
        and context.asset_id == rule.asset_id
        and context.profile == rule.profile
    )


def create_default_policy() -> ApprovalPolicy:
    return ApprovalPolicy(permissions=ApprovalPermissions())


def is_multiline_network_command(command: str) -> bool:
    return len([line for line in command.splitlines() if line.strip()]) > 1


def _classify_network_command(command: str, context: ApprovalContext) -> int:
    normalized = command.strip().lower()
    if not normalized:
        return 4

    profile = select_device_profile(context.asset_type, context.shell_type)
    level0_prefixes = profile.read_prefixes if profile is not None else ("show", "display", "ping", "traceroute", "tracert", "?")
    level1_prefixes = profile.config_entry + profile.config_exit if profile is not None else ("configure terminal", "conf t", "system-view", "configure", "end", "return")
    level3_prefixes = profile.save_commands if profile is not None else ("write memory", "copy running-config startup-config", "save", "commit")
    level4_prefixes = (
        "reload", "reset", "delete", "erase", "shutdown", "format",
        "request system reboot", "request system halt", "reboot",
    )
    level2_prefixes = ("interface", "vlan", "ip route", "acl", "undo", "no ")

    if _matches_any(level4_prefixes, normalized):
        return 4
    if _matches_any(level3_prefixes, normalized):
        return 3
    if _matches_any(level2_prefixes, normalized):
        return 2
    if _matches_any(level1_prefixes, normalized):
        return 1
    if _matches_any(level0_prefixes, normalized):
        return 0
    return 2


def _matches_any(prefixes: tuple[str, ...], command: str) -> bool:
    return any(_matches_command_prefix(prefix, command) for prefix in prefixes)
