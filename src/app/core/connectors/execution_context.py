from typing import Any

from app.core.connectors.device_profiles import NETWORK_CLI_PROFILE


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
