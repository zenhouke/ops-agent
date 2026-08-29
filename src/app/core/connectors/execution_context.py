from typing import Any

from app.core.connectors.device_profiles import NETWORK_CLI_PROFILE, DeviceProfile


def build_asset_summary(asset: Any) -> str:
    return (
        f"asset={getattr(asset, 'name', '')}, type={getattr(asset, 'asset_type', '')}, "
        f"host={getattr(asset, 'host', '')}, user={getattr(asset, 'username', '')}"
    )


def infer_os_type(shell_type: str, *, execution_profile: str = "posix-shell") -> str:
    if execution_profile == NETWORK_CLI_PROFILE:
        if shell_type == "serial":
            return "serial-console"
        return "network-device"
    if shell_type in {"powershell", "cmd"}:
        return "Windows"
    if shell_type == "posix":
        return "Darwin/Linux"
    return "unknown"


def build_device_context(execution_profile: str, device_profile: DeviceProfile | None) -> str:
    if execution_profile != NETWORK_CLI_PROFILE or device_profile is None:
        return ""

    base_rules = [
        "You are operating a network device CLI, not a Linux shell.",
        "Do not use Linux commands.",
        f"Use the current device vendor syntax: {device_profile.vendor}.",
        "Prefer read-only inspection commands before changes.",
        "For device facts, interfaces, or L2 neighbors, prefer the dedicated structured network collection tools over free-form execute_command output.",
        "Treat prompts, pagination, configuration modes, and confirmations as protocol state.",
        "Agent commands use a dedicated management CLI channel that is separate from the operator's interactive terminal. Do not assume manual terminal mode changes apply here; use the prompts returned by Agent command results.",
        "Never save configuration unless the user explicitly approves a save action.",
        "If command output contains an error pattern or an unexpected confirmation prompt, stop and explain.",
    ]
    if device_profile.vendor == "generic":
        base_rules.append(
            "This is a generic network device profile. Structured collection tools will auto-detect the supported vendor driver. For other work, use '?' to inspect available commands before choosing vendor-specific read-only commands or entering configuration mode."
        )
    else:
        base_rules.append(
            f"Read-only prefixes: {', '.join(device_profile.read_prefixes)}. Save commands requiring separate approval: {', '.join(device_profile.save_commands)}."
        )
    return "\n".join(base_rules)
