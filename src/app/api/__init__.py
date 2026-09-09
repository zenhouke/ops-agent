from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
import logging
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.api.middleware.authentication import ApiAuthenticationMiddleware
from app.api.middleware.observability import ObservabilityMiddleware
from app.api.middleware.security import RequestLimitMiddleware, SecurityHeadersMiddleware
from app.api.auth import router as auth_router
from app.api.assets import router as assets_router
from app.api.approval import router as approval_router
from app.api.groups import router as groups_router
from app.api.health import router as health_router
from app.api.knowledge import router as knowledge_router
from app.api.jumpserver import router as jumpserver_router
from app.api.mcp import router as mcp_router
from app.api.models import router as models_router
from app.api.network_topology import router as network_topology_router
from app.api.plugins import router as plugins_router
from app.api.prompt_settings import router as prompt_settings_router
from app.api.console import router as console_router
from app.api.conversations import router as conversations_router
from app.api.skills import router as skills_router
from app.api.ssh_keys import router as ssh_keys_router
from app.api.system import router as system_router
from app.api.terminal import get_terminal_service, router as terminal_router
from app.api.scheduler import router as scheduler_router
from app.api.alerts import router as alerts_router
from app.db.session import Session, engine, init_db
from app.db.repositories.audit import backfill_legacy_audit_chain
from app.services.asset_service import ensure_default_asset_group
from app.services.credential_migration_service import migrate_legacy_credentials, migrate_legacy_model_settings
from app.shared.config import APP_DIR
from app.utils.secure_storage import harden_storage_tree
from app.utils.process_lock import ProcessLock
from app.services.scheduler_service import get_scheduler_service
from app.api.console import get_console_app_service
from app.services.observability_service import configure_telemetry, shutdown_telemetry

logger = logging.getLogger(__name__)
IS_PRODUCTION = os.environ.get("OPS_AGENT_ENV", "").lower() == "production"


def _csv_env(name: str, default: list[str]) -> list[str]:
    value = os.environ.get(name)
    return [item.strip() for item in value.split(",") if item.strip()] if value else default


def _validate_production_configuration() -> None:
    if not IS_PRODUCTION:
        return
    if os.environ.get("OPS_AGENT_AUTH_DISABLED", "false").lower() in {"1", "true", "yes"}:
        raise RuntimeError("API authentication cannot be disabled in production")
    if not os.environ.get("OPS_AGENT_ALLOWED_HOSTS", "").strip():
        raise RuntimeError("OPS_AGENT_ALLOWED_HOSTS must be set in production")
    secret_key = os.environ.get("OPS_AGENT_SECRET_KEY", "").strip()
    api_token = os.environ.get("OPS_AGENT_API_TOKEN", "").strip()
    if len(secret_key) < 32:
        raise RuntimeError("OPS_AGENT_SECRET_KEY must contain at least 32 characters in production")
    if len(api_token) < 32:
        raise RuntimeError("OPS_AGENT_API_TOKEN must contain at least 32 characters in production")
    if secret_key == api_token:
        raise RuntimeError("OPS_AGENT_SECRET_KEY and OPS_AGENT_API_TOKEN must be different")


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    _validate_production_configuration()
    with ProcessLock(APP_DIR / "instance.lock"):
        configure_telemetry()
        harden_storage_tree(APP_DIR)
        init_db()
        with Session(engine) as session:
            migrated_model_settings = migrate_legacy_model_settings(session)
            migrated_credentials = migrate_legacy_credentials(session)
            migrated_audit_entries = backfill_legacy_audit_chain(session)
            ensure_default_asset_group(session)
        if migrated_credentials:
            logger.info("Migrated %d credential record(s) to authenticated encryption.", migrated_credentials)
        if migrated_model_settings:
            logger.info("Migrated legacy plaintext model settings to encrypted storage.")
        if migrated_audit_entries:
            logger.info("Added integrity hashes to %d legacy audit entries.", migrated_audit_entries)
        recovered = get_console_app_service().recover_persisted_runtimes()
        if recovered:
            logger.warning("Recovered %d interrupted agent runtimes after restart.", recovered)
        get_scheduler_service().start_loop()
        try:
            yield
        finally:
            get_scheduler_service().stop_loop()
            get_console_app_service().close()
            shutdown_telemetry()


app = FastAPI(
    title="Ops Agent API",
    lifespan=lifespan,
    docs_url=None if IS_PRODUCTION else "/docs",
    redoc_url=None if IS_PRODUCTION else "/redoc",
    openapi_url=None if IS_PRODUCTION else "/openapi.json",
)
app.add_middleware(ObservabilityMiddleware)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(
    RequestLimitMiddleware,
    max_body_bytes=int(os.environ.get("OPS_AGENT_MAX_REQUEST_BYTES", str(2 * 1024 * 1024))),
    max_concurrency=int(os.environ.get("OPS_AGENT_MAX_CONCURRENCY", "64")),
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=_csv_env("OPS_AGENT_CORS_ORIGINS", [] if IS_PRODUCTION else [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "tauri://localhost",
        "https://tauri.localhost",
    ]),
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=_csv_env("OPS_AGENT_ALLOWED_HOSTS", ["127.0.0.1", "localhost"]),
)
app.add_middleware(ApiAuthenticationMiddleware)
app.include_router(health_router)
app.include_router(auth_router)
app.include_router(models_router)
app.include_router(network_topology_router)
app.include_router(plugins_router)
app.include_router(prompt_settings_router)
app.include_router(mcp_router)
app.include_router(assets_router)
app.include_router(approval_router)
app.include_router(terminal_router)
app.include_router(groups_router)
app.include_router(console_router)
app.include_router(conversations_router)
app.include_router(knowledge_router)
app.include_router(jumpserver_router)
app.include_router(skills_router)
app.include_router(ssh_keys_router)
app.include_router(system_router)
app.include_router(scheduler_router)
app.include_router(alerts_router)


__all__ = [
    "app",
    "auth_router",
    "assets_router",
    "approval_router",
    "get_terminal_service",
    "groups_router",
    "health_router",
    "knowledge_router",
    "jumpserver_router",
    "console_router",
    "conversations_router",
    "lifespan",
    "mcp_router",
    "models_router",
    "plugins_router",
    "prompt_settings_router",
    "skills_router",
    "ssh_keys_router",
    "system_router",
    "terminal_router",
    "scheduler_router",
    "alerts_router",
]
