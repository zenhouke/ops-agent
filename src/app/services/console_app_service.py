from __future__ import annotations

import logging
import time
from collections.abc import Iterator
from typing import Any, cast

from sqlmodel import Session

from app.core.connectors.device_profiles import (
    select_device_profile,
    select_execution_profile,
)
from app.core.connectors.execution_context import build_asset_summary, build_device_context, infer_os_type
from app.core.llm.types import LLMMessage, LLMTokenUsage
from app.core.llm.errors import user_facing_llm_error
from app.core.loop.loop_state import LoopContext, LoopState
from app.core.loop.runtime_manager import LoopRuntimeManager, new_runtime_id
from app.core.runtime.control import get_runtime_control
from app.core.tool.execute_command import ExecuteCommandHandler
from app.core.tool.load_skill import LoadSkillHandler
from app.core.tool.terminal_autonomy import ListAssetsHandler, RequestTerminalSessionHandler
from app.db.repositories.assets import get_asset
from app.db.repositories.models import get_default_model_config, get_model_config_by_model_name
from app.db.repositories.model_usage import create_model_usage, sum_conversation_usage
from app.db.session import Session as DbSession, engine
from app.services.approval_service import get_approval_service
from app.services.console_orchestrator import TaskOrchestrator, TerminalSessionAdapter
from app.services.context_manager import ContextManager, JsonObject
from app.utils.local_terminal_asset import build_local_terminal_asset
from app.services.mcp_service import McpService
from app.services.model_service import ModelService
from app.services.observability_service import trace_detached_operation
from app.services.ops_plugin_service import get_ops_plugin_service
from app.services.skill_service import SkillService
from app.services.terminal_service import TerminalService


logger = logging.getLogger(__name__)


class ConsoleAppService:
    def __init__(
        self,
        *,
        model_service: ModelService | None = None,
        skill_service: SkillService | None = None,
        mcp_service: McpService | None = None,
    ) -> None:
        self._model_service = model_service or ModelService()
        self._skill_service = skill_service or SkillService()
        self._mcp_service = mcp_service or McpService()
        self._ops_plugin_service = get_ops_plugin_service()
        self.runtime_manager = LoopRuntimeManager(
            tools_factory=self._build_tool_handlers,
            usage_callback=self._record_model_usage,
        )

    def _build_tool_handlers(self, ts: TerminalService) -> list[Any]:
        terminal = TerminalSessionAdapter(ts, self.runtime_manager)
        return [
            LoadSkillHandler(self._skill_service),
            ListAssetsHandler(),
            RequestTerminalSessionHandler(self.runtime_manager),
            ExecuteCommandHandler(terminal),
            *self._ops_plugin_service.build_tool_handlers(terminal),
            *self._mcp_service.build_tool_handlers(),
        ]

    def _record_model_usage(self, state: LoopState, usage: LLMTokenUsage, call_kind: str) -> None:
        try:
            with DbSession(engine) as session:
                create_model_usage(
                    session,
                    runtime_id=state.context.runtime_id,
                    conversation_id=state.context.conversation_id,
                    model_config=state.context.model_config,
                    usage=usage,
                    call_kind=call_kind,
                )
                total_usage = sum_conversation_usage(session, state.context.conversation_id)
                state.latest_usage = {
                    "inputTokens": total_usage.input_tokens,
                    "outputTokens": total_usage.output_tokens,
                    "cacheCreationInputTokens": total_usage.cache_creation_input_tokens,
                    "cacheReadInputTokens": total_usage.cache_read_input_tokens,
                    "totalTokens": total_usage.total_tokens,
                }
        except Exception:
            logger.exception("Failed to record model usage runtime_id=%s", state.context.runtime_id)

    def _conversation_token_usage_payload(self, conversation_id: str) -> dict[str, int]:
        try:
            with DbSession(engine) as session:
                usage = sum_conversation_usage(session, conversation_id)
        except Exception:
            logger.exception("Failed to load conversation usage conversation_id=%s", conversation_id)
            usage = LLMTokenUsage()
        return {
            "inputTokens": usage.input_tokens,
            "outputTokens": usage.output_tokens,
            "cacheCreationInputTokens": usage.cache_creation_input_tokens,
            "cacheReadInputTokens": usage.cache_read_input_tokens,
            "totalTokens": usage.total_tokens,
        }

    def _context_percent_for_status_event(self, *, context_percent: int, token_usage: dict[str, int], model_config) -> int:
        if context_percent > 0:
            return context_percent
        return self._context_manager().context_percent_for_tokens(token_usage.get("totalTokens") or 0, model_config)

    def _context_status_for_percent(self, context_percent: int):
        return self._context_manager().status_for_percent(context_percent)

    def _append_knowledge_context(
        self,
        conversation_history: list[LLMMessage],
        knowledge_context: str,
    ) -> list[LLMMessage]:
        if not knowledge_context.strip():
            return conversation_history
        return [
            *conversation_history,
            LLMMessage(
                role="system",
                content=knowledge_context,
                cache_segment="runtime_context",
                cache_status="volatile",
            ),
        ]

    def build_orchestrator(self, terminal_service: TerminalService) -> TaskOrchestrator:
        return TaskOrchestrator(self, terminal_service)

    def close(self) -> None:
        self._mcp_service.close()

    def recover_persisted_runtimes(self) -> int:
        return self.runtime_manager.recover_persisted_runtimes()

    def stream_run(
        self,
        *,
        session: Session,
        prompt: str,
        asset_id: int,
        terminal_id: str | None = None,
        model_name: str | None = None,
        selected_skill_name: str | None = None,
        conversation_id: str = "console",
        terminal_service: TerminalService,
    ) -> Iterator[dict]:
        asset = self._resolve_asset(session, asset_id)
        model_config = self._resolve_model_config(session, model_name)
        if terminal_id is None:
            terminal_id = terminal_service.find_session_id(f"asset:{asset_id}")
        if terminal_id and not terminal_service.session_belongs_to_asset(terminal_id, asset_id):
            logger.warning(
                "Ignoring terminal_id that does not belong to asset: asset_id=%s terminal_id=%s",
                asset_id,
                terminal_id,
            )
            terminal_id = None
        asset_summary = build_asset_summary(asset)
        asset_type = str(getattr(asset, "asset_type", "") or "")
        shell_type = self._resolve_shell_type(terminal_service, terminal_id)
        execution_profile = select_execution_profile(asset_type, shell_type)
        device_profile = select_device_profile(asset_type, shell_type)
        os_type = infer_os_type(shell_type, execution_profile=execution_profile)
        device_context = build_device_context(execution_profile, device_profile)

        context_result = self._prepare_conversation_context(conversation_id, model_config)
        conversation_history = context_result.prepared_messages
        knowledge_entries_injected = 0
        knowledge_context_chars = 0
        try:
            from app.services.knowledge_factory import get_knowledge_service

            asset_label = str(getattr(asset, "name", "") or "")
            asset_group = str(
                getattr(asset, "group", "")
                or getattr(asset, "group_name", "")
                or ""
            )
            knowledge_service = get_knowledge_service()
            knowledge_entries = knowledge_service.search_for_agent(
                prompt,
                asset_label=asset_label,
                asset_group=asset_group,
                conversation_id=conversation_id,
            )
            knowledge_context = knowledge_service.format_agent_context(knowledge_entries)
            if knowledge_context.strip():
                conversation_history = self._append_knowledge_context(
                    conversation_history,
                    knowledge_context,
                )
                knowledge_entries_injected = len(knowledge_entries)
                knowledge_context_chars = len(knowledge_context)
        except Exception:
            logger.warning(
                "Failed to load knowledge context conversation_id=%s asset_id=%s",
                conversation_id,
                asset_id,
                exc_info=True,
            )

        runtime_id = new_runtime_id()
        skill_packages = self._skill_service.list_skills()
        available_skills = [
            {"name": skill.name, "description": skill.description}
            for skill in skill_packages
            if skill.valid
        ]
        loaded_skill_name: str | None = None
        manual_skill_name: str | None = None
        manual_skill_content = ""
        if selected_skill_name:
            manual_skill_name = selected_skill_name.strip() or None
            if manual_skill_name:
                try:
                    loaded_skill = self._skill_service.load_skill(manual_skill_name)
                except ValueError as exc:
                    yield self._runtime_error_event(runtime_id, str(exc), recoverable=True)
                    return
                loaded_skill_name = loaded_skill.name
                manual_skill_name = loaded_skill.name
                manual_skill_content = loaded_skill.body

        context = LoopContext(
            runtime_id=runtime_id,
            conversation_id=conversation_id,
            asset_id=asset_id,
            asset_type=asset_type,
            terminal_id=terminal_id,
            asset_summary=asset_summary,
            shell_type=shell_type,
            os_type=os_type,
            execution_profile=execution_profile,
            device_vendor=device_profile.vendor if device_profile else None,
            device_context=device_context,
            user_prompt=prompt,
            model_config=model_config,
            conversation_history=conversation_history,
            available_skills=available_skills,
            loaded_skill_name=loaded_skill_name,
            manual_skill_name=manual_skill_name,
            manual_skill_content=manual_skill_content,
        )

        self.runtime_manager.create_runtime(
            conversation_id=conversation_id,
            asset_id=asset_id,
            terminal_id=terminal_id,
            context=context,
        )
        initial_runtime_events: list[dict[str, Any]] = []
        if terminal_id:
            authorization = self.runtime_manager.create_initial_terminal_authorization(
                runtime_id,
                conversation_id=conversation_id,
                asset_id=asset_id,
                asset_name=str(getattr(asset, "name", "") or f"asset-{asset_id}"),
                terminal_id=terminal_id,
            )
            context.default_authorization_id = authorization.authorization_id
            _, initial_runtime_events = self.runtime_manager.events_since(runtime_id, 0)

        token_usage = self._conversation_token_usage_payload(conversation_id)
        context_percent = self._context_percent_for_status_event(
            context_percent=context_result.context_percent,
            token_usage=token_usage,
            model_config=model_config,
        )
        yield {
            "id": f"evt-context-{runtime_id}",
            "kind": "context_status",
            "runtimeId": runtime_id,
            "contextPercent": context_percent,
            "contextStatus": self._context_status_for_percent(context_percent),
            "tokenUsage": token_usage,
            "compactionApplied": context_result.compaction_applied,
            "fitStatus": context_result.fit_status,
            "summaryRevision": context_result.summary_revision,
            "sourceConversationRevision": context_result.source_conversation_revision,
            "knowledgeEntriesInjected": knowledge_entries_injected,
            "knowledgeContextChars": knowledge_context_chars,
        }

        for event in initial_runtime_events:
            yield event

        yield from self._stream_events_with_error_handling(
            runtime_id=runtime_id,
            log_message="stream_run failed conversation_id=%s runtime_id=%s",
            event_iter_factory=lambda: self.runtime_manager.run(runtime_id=runtime_id, terminal_service=terminal_service),
            conversation_id=conversation_id,
            runtime_id_log=runtime_id,
        )

    def stream_approve(
        self,
        *,
        session: Session,
        runtime_id: str,
        approved: bool,
        approval_token: str | None,
        allow_prefix: str | None,
        terminal_service: TerminalService,
    ) -> Iterator[dict]:
        _ = session
        runtime = self.runtime_manager.get_runtime(runtime_id)
        if runtime is None:
            yield self._runtime_error_event(runtime_id, "Runtime not found.", recoverable=False)
            return

        def resume_events():
            if approved and allow_prefix:
                get_approval_service().add_allow_prefix(allow_prefix)
            return self.runtime_manager.resume(
                runtime_id=runtime_id,
                approved=approved,
                approval_token=approval_token,
                terminal_service=terminal_service,
            )

        yield from self._stream_events_with_error_handling(
            runtime_id=runtime_id,
            log_message="stream_approve failed runtime_id=%s",
            event_iter_factory=resume_events,
            runtime_id_log=runtime_id,
        )

    def cancel_runtime(self, runtime_id: str) -> dict[str, Any]:
        return self.runtime_manager.cancel(runtime_id)

    def stream_after_terminal_request(self, *, runtime_id: str, resume_message: str, terminal_service: TerminalService, authorization_id: str | None = None) -> Iterator[dict]:
        yield from self._stream_events_with_error_handling(
            runtime_id=runtime_id,
            log_message="stream_after_terminal_request failed runtime_id=%s",
            event_iter_factory=lambda: self.runtime_manager.resume_after_terminal_request(
                runtime_id=runtime_id,
                resume_message=resume_message,
                terminal_service=terminal_service,
                authorization_id=authorization_id,
            ),
            runtime_id_log=runtime_id,
        )

    def _stream_events_with_error_handling(
        self,
        *,
        runtime_id: str,
        log_message: str,
        event_iter_factory,
        **log_context: Any,
    ) -> Iterator[dict]:
        control = get_runtime_control()
        started = time.monotonic()
        status = "failed"
        control.metrics.run_started(runtime_id)
        try:
            iterator = iter(event_iter_factory())
            while True:
                try:
                    with control.run_slot():
                        with trace_detached_operation("agent.runtime.step", {"ops.runtime_id": runtime_id}):
                            event = next(iterator)
                except StopIteration:
                    try:
                        snapshot = self.runtime_manager.get_snapshot(runtime_id)
                        status = "failed" if snapshot.get("status") == "failed" else "completed"
                    except ValueError:
                        status = "completed"
                    return
                yield event
        except Exception as exc:
            logger.exception(log_message, *log_context.values())
            message = user_facing_llm_error(exc)
            runtime_error = self.runtime_manager.fail_runtime(runtime_id, message)
            yield runtime_error or self._runtime_error_event(runtime_id, message, recoverable=True)
        finally:
            control.metrics.run_finished(
                runtime_id,
                status=status,
                duration_seconds=time.monotonic() - started,
            )

    def _runtime_error_event(self, runtime_id: str, text: str, *, recoverable: bool) -> dict[str, Any]:
        return {
            "id": f"evt-error-{runtime_id}",
            "kind": "error",
            "runtimeId": runtime_id,
            "sequence": -1,
            "ts": "",
            "text": text,
            "recoverable": recoverable,
        }

    def _resolve_asset(self, session: Session, asset_id: int):
        asset = get_asset(session, asset_id)
        if asset is None and asset_id == 0:
            asset = build_local_terminal_asset()
        if asset is None:
            raise ValueError(f"Asset not found: {asset_id}")
        return asset

    def _resolve_model_config(self, session: Session, model_name: str | None):
        default_record = get_default_model_config(session)
        if model_name:
            selected_record = get_model_config_by_model_name(session, model_name)
            if selected_record is not None:
                return self._model_service.from_record(selected_record)
            if default_record is not None:
                raise ValueError(f"Model is not configured: {model_name}")
        default_config = (
            self._model_service.from_record(default_record)
            if default_record is not None
            else self._model_service.load_settings()
        )
        if model_name and model_name != default_config.model_name:
            default_config = default_config.model_copy(update={"model_name": model_name})
        return default_config

    def _resolve_shell_type(self, terminal_service: TerminalService, terminal_id: str | None) -> str:
        shell_type = "unknown"
        if terminal_id:
            try:
                shell_type = terminal_service.get_shell_kind(terminal_id)
            except ValueError:
                shell_type = "unknown"
        return shell_type

    def _prepare_conversation_context(self, conversation_id: str, model_config):
        context_manager = self._context_manager()
        if not conversation_id or conversation_id == "console":
            return context_manager.prepare_context(conversation_id or "console", [], model_config)

        from app.api.conversations import get_conversation_service
        service = get_conversation_service()
        try:
            detail = service.get_conversation(conversation_id)
        except FileNotFoundError:
            logger.warning("Conversation not found while preparing context conversation_id=%s", conversation_id)
            return context_manager.prepare_context(conversation_id, [], model_config)

        events = cast(list[JsonObject], detail.events or [])
        result = context_manager.prepare_context(conversation_id, events, model_config)
        logger.info(
            "Prepared conversation context: %d messages from %d events, %d%%, fit=%s",
            len(result.prepared_messages),
            len(events),
            result.context_percent,
            result.fit_status,
        )
        return result

    def _context_manager(self) -> ContextManager:
        from app.api.conversations import get_conversation_service
        service = get_conversation_service()
        return ContextManager(service.base_dir / "context")
