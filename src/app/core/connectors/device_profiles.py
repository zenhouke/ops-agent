from __future__ import annotations

from dataclasses import dataclass

from app.shared.enums import AssetType


POSIX_SHELL_PROFILE = "posix-shell"
NETWORK_CLI_PROFILE = "network-cli"
NETWORK_SHELL_TYPES = (AssetType.NETWORK.value, AssetType.SERIAL.value)

NETMIKO_DEVICE_TYPES: dict[str, str] = {
    AssetType.NETWORK.value: "autodetect",
    AssetType.CISCO.value: "cisco_ios",
    AssetType.HUAWEI.value: "huawei",
    AssetType.H3C.value: "hp_comware",
    AssetType.JUNIPER.value: "juniper",
}


@dataclass(frozen=True, slots=True)
class DeviceProfile:
    vendor: str
    read_prefixes: tuple[str, ...]
    config_entry: tuple[str, ...]
    config_exit: tuple[str, ...]
    save_commands: tuple[str, ...]
    prompt_patterns: tuple[str, ...]
    pager_patterns: tuple[str, ...]
    confirm_patterns: tuple[str, ...]
    error_patterns: tuple[str, ...]


GENERIC_DEVICE_PROFILE = DeviceProfile(
    vendor="generic",
    read_prefixes=("show", "display", "ping", "traceroute", "tracert", "?"),
    config_entry=("configure terminal", "conf t", "system-view", "configure"),
    config_exit=("end", "return", "exit", "quit"),
    save_commands=("write memory", "copy running-config startup-config", "save", "commit"),
    prompt_patterns=(r"(?m)(?:^|[\r\n]).+[>#\]]\s*$", r"(?m)(?:^|[\r\n])<[^>]+>\s*$"),
    pager_patterns=(r"--More--", r"---- More ----", r"---\(more\)---", r"More:"),
    confirm_patterns=(r"\[Y/N\]", r"\(y/n\)", r"continue\?", r"\[confirm\]", r"\[yes/no\]"),
    error_patterns=(r"% ?Invalid input", r"% ?Incomplete command", r"Error:", r"Unrecognized command", r"Unknown command"),
)

_DEVICE_PROFILES: dict[str, DeviceProfile] = {
    AssetType.CISCO.value: DeviceProfile(
        vendor="cisco",
        read_prefixes=("show", "ping", "traceroute", "?"),
        config_entry=("configure terminal", "conf t"),
        config_exit=("end", "exit"),
        save_commands=("write memory", "copy running-config startup-config"),
        prompt_patterns=(r"(?m)(?:^|[\r\n]).+>\s*$", r"(?m)(?:^|[\r\n]).+#\s*$", r"(?m)(?:^|[\r\n]).+\(config[^)]*\)#\s*$"),
        pager_patterns=(r"--More--",),
        confirm_patterns=(r"\[confirm\]", r"\[yes/no\]", r"Destination filename"),
        error_patterns=(r"% ?Invalid input", r"% ?Incomplete command", r"% ?Ambiguous command"),
    ),
    AssetType.HUAWEI.value: DeviceProfile(
        vendor="huawei",
        read_prefixes=("display", "ping", "tracert", "?"),
        config_entry=("system-view",),
        config_exit=("return", "quit"),
        save_commands=("save",),
        prompt_patterns=(r"(?m)(?:^|[\r\n])<[^>]+>\s*$", r"(?m)(?:^|[\r\n])\[[^\]]+\]\s*$"),
        pager_patterns=(r"---- More ----", r"  ---- More ----"),
        confirm_patterns=(r"\[Y/N\]", r"\(y/n\)", r"continue\?"),
        error_patterns=(r"Error:", r"Wrong parameter", r"Unrecognized command", r"Incomplete command"),
    ),
    AssetType.H3C.value: DeviceProfile(
        vendor="h3c",
        read_prefixes=("display", "ping", "tracert", "?"),
        config_entry=("system-view",),
        config_exit=("return", "quit"),
        save_commands=("save",),
        prompt_patterns=(r"(?m)(?:^|[\r\n])<[^>]+>\s*$", r"(?m)(?:^|[\r\n])\[[^\]]+\]\s*$"),
        pager_patterns=(r"---- More ----",),
        confirm_patterns=(r"\[Y/N\]", r"\(y/n\)", r"continue\?"),
        error_patterns=(r"% ?Wrong parameter", r"Error:", r"Unrecognized command", r"Incomplete command"),
    ),
    AssetType.JUNIPER.value: DeviceProfile(
        vendor="juniper",
        read_prefixes=("show", "ping", "traceroute", "?"),
        config_entry=("configure",),
        config_exit=("exit",),
        save_commands=("commit",),
        prompt_patterns=(r"(?m)(?:^|[\r\n]).+>\s*$", r"(?m)(?:^|[\r\n]).+#\s*$"),
        pager_patterns=(r"---\(more\)---",),
        confirm_patterns=(r"\[yes,no\]", r"\(yes/no\)"),
        error_patterns=(r"syntax error", r"unknown command", r"error:"),
    ),
    AssetType.NETWORK.value: GENERIC_DEVICE_PROFILE,
    AssetType.SERIAL.value: GENERIC_DEVICE_PROFILE,
}


def is_network_shell(shell_type: str | None = None, asset_type: str | None = None) -> bool:
    normalized_shell = _normalize(shell_type)
    normalized_asset = _normalize(asset_type)
    return normalized_shell in NETWORK_SHELL_TYPES or normalized_asset in _DEVICE_PROFILES


def select_execution_profile(asset_type: str, shell_type: str) -> str:
    if is_network_shell(shell_type=shell_type, asset_type=asset_type):
        return NETWORK_CLI_PROFILE
    return POSIX_SHELL_PROFILE


def matches_command_prefix(prefix: str, command: str) -> bool:
    prefix = prefix.strip()
    if not prefix:
        return False
    if prefix == "*":
        return True
    return command == prefix or command.startswith(f"{prefix} ")


def select_device_profile(asset_type: str, shell_type: str) -> DeviceProfile | None:
    normalized_asset = _normalize(asset_type)
    normalized_shell = _normalize(shell_type)
    if normalized_asset not in _DEVICE_PROFILES and normalized_shell not in NETWORK_SHELL_TYPES:
        return None
    return _DEVICE_PROFILES.get(normalized_asset, GENERIC_DEVICE_PROFILE)


def netmiko_device_type(asset_type: str) -> str | None:
    return NETMIKO_DEVICE_TYPES.get(_normalize(asset_type))


def asset_type_for_netmiko_device_type(device_type: str | None) -> str:
    normalized = _normalize(device_type)
    if normalized.startswith("cisco_"):
        return AssetType.CISCO.value
    if normalized.startswith("juniper"):
        return AssetType.JUNIPER.value
    if normalized.startswith(("hp_comware", "h3c")):
        return AssetType.H3C.value
    if normalized.startswith("huawei"):
        return AssetType.HUAWEI.value
    return AssetType.NETWORK.value


def _normalize(value: str | None) -> str:
    return (value or "").strip().lower()
