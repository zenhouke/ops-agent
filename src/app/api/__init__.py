from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.middleware.observability import ObservabilityMiddleware
from app.api.assets import router as assets_router
from app.api.approval import router as approval_router
from app.api.groups import router as groups_router
from app.api.health import router as health_router
from app.api.knowledge import router as knowledge_router
from app.api.mcp import router as mcp_router
from app.api.models import router as models_router
from app.api.console import router as console_router
from app.api.conversations import router as conversations_router
from app.api.skills import router as skills_router
from app.api.ssh_keys import router as ssh_keys_router
from app.api.system import router as system_router
from app.api.terminal import get_terminal_service, router as terminal_router
from app.api.scheduler import router as scheduler_router
from app.api.alerts import router as alerts_router
from app.db.session import Session, engine, init_db
from app.services.asset_service import ensure_default_asset_group
from app.services.scheduler_service import get_scheduler_service
from app.api.console import get_console_app_service
from app.services.observability_service import configure_telemetry, shutdown_telemetry

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    configure_telemetry()
    init_db()
    with Session(engine) as session:
        ensure_default_asset_group(session)
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


app = FastAPI(title="Ops Agent API", lifespan=lifespan)
app.add_middleware(ObservabilityMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "tauri://localhost",
        "https://tauri.localhost",
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(health_router)
app.include_router(models_router)
app.include_router(mcp_router)
app.include_router(assets_router)
app.include_router(approval_router)
app.include_router(terminal_router)
app.include_router(groups_router)
app.include_router(console_router)
app.include_router(conversations_router)
app.include_router(knowledge_router)
app.include_router(skills_router)
app.include_router(ssh_keys_router)
app.include_router(system_router)
app.include_router(scheduler_router)
app.include_router(alerts_router)


__all__ = [
    "app",
    "assets_router",
    "approval_router",
    "get_terminal_service",
    "groups_router",
    "health_router",
    "knowledge_router",
    "console_router",
    "conversations_router",
    "lifespan",
    "mcp_router",
    "models_router",
    "skills_router",
    "ssh_keys_router",
    "system_router",
    "terminal_router",
    "scheduler_router",
    "alerts_router",
]
