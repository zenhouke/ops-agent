"""Application composition root. API routers do not own business service instances."""
from functools import lru_cache

from app.services.connector_factory import connector_factory
from app.services.console_app_service import ConsoleAppService
from app.services.conversation_factory import get_conversation_service
from app.services.scheduler_service import SchedulerService
from app.services.terminal_service import TerminalService


@lru_cache(maxsize=1)
def get_terminal_service() -> TerminalService:
    return TerminalService(connector_factory=connector_factory)


@lru_cache(maxsize=1)
def get_console_app_service() -> ConsoleAppService:
    return ConsoleAppService()


@lru_cache(maxsize=1)
def get_scheduler_service() -> SchedulerService:
    return SchedulerService(console_service=get_console_app_service(),
                            terminal_service=get_terminal_service(),
                            conversation_factory=get_conversation_service)
