from __future__ import annotations

from collections.abc import Iterator
from typing import TYPE_CHECKING, Any

from sqlmodel import Session

from app.core.loop.runtime_manager import LoopRuntimeManager
from app.services.terminal_service import TerminalService

if TYPE_CHECKING:
    from app.services.console_app_service import ConsoleAppService


class TerminalSessionAdapter:
    def __init__(
        self,
        terminal_service: TerminalService,
        runtime_manager: LoopRuntimeManager,
    ) -> None:
        self._terminal_service = terminal_service
        self._runtime_manager = runtime_manager

    def get_session(self, terminal_id: str) -> Any | None:
        return self._terminal_service.get_session(terminal_id)

    def resolve_terminal_authorization(self, runtime_id: str, authorization_id: str) -> Any:
        return self._runtime_manager.resolve_terminal_authorization(runtime_id, authorization_id)

    def session_belongs_to_asset(self, terminal_id: str, asset_id: int) -> bool:
        return self._terminal_service.session_belongs_to_asset(terminal_id, asset_id)

    def append_terminal_command_submitted(
        self,
        runtime_id: str,
        *,
        authorization_id: str,
        asset_id: int,
        asset_name: str,
        terminal_id: str,
        command: str,
        approval_policy: str,
    ) -> dict[str, Any]:
        return self._runtime_manager.append_terminal_command_submitted(
            runtime_id,
            authorization_id=authorization_id,
            asset_id=asset_id,
            asset_name=asset_name,
            terminal_id=terminal_id,
            command=command,
            approval_policy=approval_policy,
        )

    def acquire_terminal_slot(self, runtime_id: str, terminal_id: str) -> bool:
        return self._runtime_manager.acquire_terminal_slot(runtime_id, terminal_id)

    def release_terminal_slot(self, runtime_id: str, terminal_id: str) -> None:
        self._runtime_manager.release_terminal_slot(runtime_id, terminal_id)


class TaskOrchestrator:
    def __init__(
        self,
        app_service: "ConsoleAppService",
        terminal_service: TerminalService,
    ) -> None:
        self._app_service = app_service
        self._terminal_service = terminal_service

    def stream_run(
        self,
        *,
        session: Session,
        prompt: str,
        operator_prompt: str | None = None,
        asset_id: int,
        terminal_id: str | None = None,
        model_name: str | None = None,
        selected_skill_name: str | None = None,
        mode: str = "standard",
        conversation_id: str = "console",
        conversation_scope_mode: str = "single",
        conversation_primary_asset_id: int | None = None,
        allowed_asset_ids: list[int] | None = None,
    ) -> Iterator[dict]:
        return self._app_service.stream_run(
            session=session,
            prompt=prompt,
            operator_prompt=operator_prompt,
            asset_id=asset_id,
            terminal_id=terminal_id,
            model_name=model_name,
            selected_skill_name=selected_skill_name,
            mode=mode,
            conversation_id=conversation_id,
            conversation_scope_mode=conversation_scope_mode,
            conversation_primary_asset_id=conversation_primary_asset_id,
            allowed_asset_ids=allowed_asset_ids,
            terminal_service=self._terminal_service,
        )

    def stream_approve(
        self,
        *,
        session: Session,
        runtime_id: str,
        approved: bool,
        approval_token: str | None = None,
        allow_prefix: str | None = None,
        guidance: str | None = None,
    ) -> Iterator[dict]:
        return self._app_service.stream_approve(
            session=session,
            runtime_id=runtime_id,
            approved=approved,
            approval_token=approval_token,
            allow_prefix=allow_prefix,
            guidance=guidance,
            terminal_service=self._terminal_service,
        )

    def stream_user_message(self, *, runtime_id: str, message: str) -> Iterator[dict]:
        return self._app_service.stream_user_message(
            runtime_id=runtime_id,
            message=message,
            terminal_service=self._terminal_service,
        )

    def stream_after_terminal_request(
        self,
        *,
        runtime_id: str,
        resume_message: str,
        authorization_id: str | None = None,
    ) -> Iterator[dict]:
        return self._app_service.stream_after_terminal_request(
            runtime_id=runtime_id,
            resume_message=resume_message,
            terminal_service=self._terminal_service,
            authorization_id=authorization_id,
        )
