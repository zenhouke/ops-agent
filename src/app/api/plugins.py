from __future__ import annotations

from fastapi import APIRouter

from app.services.ops_plugin_service import OpsPluginPackage, get_ops_plugin_service

router = APIRouter()


def _package_payload(package: OpsPluginPackage) -> dict[str, object]:
    return {
        "id": package.plugin_id,
        "name": package.name,
        "version": package.version,
        "description": package.description,
        "source": package.source,
        "path": package.path,
        "enabled": package.enabled,
        "valid": package.valid,
        "error": package.error,
        "updatedAt": package.updated_at.isoformat(),
        "tools": [
            {
                "name": tool.name,
                "exposedName": tool.exposed_name,
                "description": tool.description,
                "assetTypes": list(tool.asset_types),
                "inputSchema": tool.input_schema,
            }
            for tool in package.tools
        ],
    }


def _plugins_payload(*, refresh: bool) -> dict[str, object]:
    service = get_ops_plugin_service()
    plugins = service.list_plugins(refresh=refresh)
    return {
        "plugins": [_package_payload(plugin) for plugin in plugins],
        "summary": service.summary(),
    }


@router.get("/api/plugins")
def list_plugins() -> dict[str, object]:
    return _plugins_payload(refresh=False)


@router.post("/api/plugins/reload")
def reload_plugins() -> dict[str, object]:
    return _plugins_payload(refresh=True)
