"""Resolve asset credentials and assemble transport drivers at the service boundary."""
from app.core.connectors.server import ServerConnector
from app.core.connectors.network import NetworkConnector
from app.core.connectors.local_pty import LocalPtyConnector
from app.core.connectors.serial import SerialConnector
from app.core.connectors.ssh_host_keys import strict_netmiko_options
from app.core.connectors.tcp_proxy import TCPProxyConfig, open_proxy_socket


def connector_factory(asset, *, credential_secret_override: str | None = None):
    from sqlmodel import Session

    from app.db.models import AssetGroup
    from app.db.session import engine
    from app.core.connectors.ssh_proxy import (
        SSHProxyAssetNotFoundError,
        SSHProxyAuthenticationMaterialError,
        SSHProxyConfig,
        SSHProxyConfigurationError,
        SSHProxyUnsupportedTargetError,
    )
    from app.services.asset_service import get_asset_credential_record, get_asset_record
    from app.services.credential_service import CredentialService
    from app.shared.secret_key import get_ops_agent_secret_key
    from app.services.ssh_key_service import get_ssh_key_record
    from app.core.connectors.device_profiles import netmiko_device_type

    credential_service = CredentialService(secret_key=get_ops_agent_secret_key())
    asset_id = getattr(asset, "id", None)
    asset_type = getattr(asset, "asset_type", "")

    if getattr(asset, "auth_type", "") == "jumpserver":
        from app.services.jumpserver_service import get_jumpserver_service
        with Session(engine) as session:
            connector = get_jumpserver_service().connector_for_asset(session, asset)
        if connector is None:
            raise ValueError("JumpServer asset binding was not found.")
        return connector

    if asset_type == "local_terminal":
        return LocalPtyConnector()

    if asset_type == "serial":
        serial_tags = {
            key: value
            for tag in getattr(asset, "tags", [])
            if ":" in tag
            for key, value in [tag.split(":", 1)]
        }
        parity_mapping = {
            "none": "N",
            "odd": "O",
            "even": "E",
        }
        try:
            bytesize = int(serial_tags.get("data-bits", "8"))
            stopbits = float(serial_tags.get("stop-bits", "1"))
        except ValueError as exc:
            raise ValueError("Invalid serial tag configuration") from exc
        parity = parity_mapping.get(serial_tags.get("parity", "none"), "N")
        return SerialConnector(
            device=getattr(asset, "host"),
            baudrate=int(getattr(asset, "port") or 9600),
            bytesize=bytesize,
            parity=parity,
            stopbits=stopbits,
        )

    password = None
    private_key = None
    passphrase = None
    proxy_config = None
    tcp_proxy_config = None

    with Session(engine) as session:
        def resolve_auth_material(current_asset):
            current_asset_id = getattr(current_asset, "id", None)
            current_auth_type = getattr(current_asset, "auth_type", "")
            current_ssh_key_id = getattr(current_asset, "ssh_key_id", None)
            resolved_password = None
            resolved_private_key = None
            resolved_passphrase = None
            is_target_asset = current_asset is asset

            if current_auth_type in {"password", "password_and_key"}:
                credential = None if is_target_asset and credential_secret_override is not None else get_asset_credential_record(session, current_asset_id)
                if credential is None:
                    if is_target_asset and credential_secret_override is not None:
                        resolved_password = credential_secret_override
                    else:
                        raise ValueError(f"Password credential is required for {current_auth_type} auth")
                if credential is not None:
                    resolved_password = credential_service.decrypt_secret(
                        credential.encrypted_blob,
                        credential.encryption_version,
                    )
            if current_auth_type in {"key", "password_and_key"}:
                if current_ssh_key_id is None:
                    raise ValueError("SSH key is required for key auth")
                ssh_key = get_ssh_key_record(session, current_ssh_key_id)
                if ssh_key is None:
                    raise ValueError("SSH key not found")
                resolved_private_key = credential_service.decrypt_secret(
                    ssh_key.encrypted_private_key,
                    ssh_key.private_key_encryption_version,
                )
                if ssh_key.encrypted_passphrase:
                    resolved_passphrase = credential_service.decrypt_secret(
                        ssh_key.encrypted_passphrase,
                        ssh_key.passphrase_encryption_version,
                    )
            elif current_auth_type != "password":
                credential = get_asset_credential_record(session, current_asset_id)
                if credential is not None:
                    resolved_password = credential_service.decrypt_secret(
                        credential.encrypted_blob,
                        credential.encryption_version,
                    )

            if resolved_password is None and resolved_private_key is None:
                raise SSHProxyAuthenticationMaterialError("SSH authentication material is required")
            return resolved_password, resolved_private_key, resolved_passphrase

        password, private_key, passphrase = resolve_auth_material(asset)
        proxy_type = getattr(asset, "proxy_type", "inherit")
        proxy_source = asset
        if proxy_type == "inherit" and getattr(asset, "group_id", None) is not None:
            proxy_source = session.get(AssetGroup, asset.group_id) or asset
            proxy_type = getattr(proxy_source, "proxy_type", "none")
        if proxy_type in {"http_connect", "socks5"}:
            if not getattr(proxy_source, "proxy_host", "") or not getattr(proxy_source, "proxy_port", 0):
                raise ValueError("Proxy host and port are required")
            proxy_password = None
            encrypted_proxy_password = getattr(proxy_source, "proxy_password_encrypted", "")
            if encrypted_proxy_password:
                proxy_password = credential_service.decrypt_secret(encrypted_proxy_password, CredentialService.encryption_version)
            transient_proxy_password = getattr(proxy_source, "proxy_password", None)
            if transient_proxy_password is not None:
                proxy_password = transient_proxy_password.get_secret_value() if hasattr(transient_proxy_password, "get_secret_value") else str(transient_proxy_password)
            tcp_proxy_config = TCPProxyConfig(proxy_type, proxy_source.proxy_host, proxy_source.proxy_port, proxy_source.proxy_username or None, proxy_password)
        proxy_asset_id = getattr(asset, "proxy_asset_id", None)
        if proxy_asset_id is not None:
            if proxy_asset_id == asset_id:
                raise SSHProxyConfigurationError("Asset cannot use itself as a proxy")
            proxy_target_types = {"linux", "network", "cisco", "huawei", "juniper", "h3c"}
            if asset_type not in proxy_target_types:
                raise SSHProxyUnsupportedTargetError(
                    "SSH proxy is supported only for Linux and network device assets in this version"
                )
            proxy_asset = get_asset_record(session, proxy_asset_id)
            if proxy_asset is None:
                raise SSHProxyAssetNotFoundError("Proxy asset not found")
            if getattr(proxy_asset, "asset_type", None) != "linux":
                raise SSHProxyConfigurationError("Proxy asset must be a Linux asset")
            if getattr(proxy_asset, "proxy_asset_id", None) is not None:
                raise SSHProxyConfigurationError("Proxy chains are not supported")
            proxy_password, proxy_private_key, proxy_passphrase = resolve_auth_material(proxy_asset)
            proxy_config = SSHProxyConfig(
                asset_id=getattr(proxy_asset, "id"),
                name=getattr(proxy_asset, "name"),
                host=getattr(proxy_asset, "host"),
                port=getattr(proxy_asset, "port"),
                username=getattr(proxy_asset, "username"),
                password=proxy_password,
                private_key=proxy_private_key,
                passphrase=proxy_passphrase,
            )

    if asset_type in {"network", "cisco", "huawei", "juniper", "h3c"}:
        device_type = netmiko_device_type(asset_type)
        if device_type is None:
            raise ValueError(f"Unsupported network asset type: {asset_type}")

        device_params = {
            "device_type": device_type,
            "asset_type": asset_type,
            "host": getattr(asset, "host"),
            "port": getattr(asset, "port"),
            "username": getattr(asset, "username"),
            "allow_agent": False,
            **strict_netmiko_options(),
        }
        ssh_params = {
            "host": getattr(asset, "host"),
            "port": getattr(asset, "port"),
            "username": getattr(asset, "username"),
            "password": password,
            "private_key": private_key,
            "passphrase": passphrase,
            "proxy_config": proxy_config,
            "tcp_proxy_config": tcp_proxy_config,
        }
        if private_key:
            device_params["use_keys"] = True
            device_params["key_file"] = None
            device_params["pkey"] = ServerConnector(
                host=getattr(asset, "host"),
                port=getattr(asset, "port"),
                username=getattr(asset, "username"),
                private_key=private_key,
                passphrase=passphrase,
            )._load_private_key()
            if passphrase:
                device_params["passphrase"] = passphrase
            if password is not None:
                device_params["password"] = password
        elif password is not None:
            device_params["password"] = password
        else:
            raise ValueError("Network device authentication material is required")
        return NetworkConnector(device_params, ssh_params)

    return ServerConnector(
        host=getattr(asset, "host"),
        port=getattr(asset, "port"),
        username=getattr(asset, "username"),
        password=password,
        private_key=private_key,
        passphrase=passphrase,
        proxy_config=proxy_config,
        tcp_proxy_config=tcp_proxy_config,
    )
