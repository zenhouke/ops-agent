#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from collections.abc import Callable, Iterator
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from pydantic import SecretStr

from app.core.llm.types import LLMCompletionChunk, LLMMessage
from app.core.loop.agent_loop import AgentLoop
import app.core.loop.agent_loop as agent_loop_module
from app.core.loop.loop_state import LoopContext, LoopRuntimeStep, LoopState
from app.core.tool.ask_followup import AskFollowupHandler
from app.core.tool.handler import ToolDisplayMetadata
from app.core.tool.schema import LLMToolCall, LLMToolDefinition
from app.core.tool.terminal_autonomy import RequestTerminalSessionHandler
from app.core.tool.update_task_state import UpdateTaskStateHandler
from app.services.context_manager import ContextManager
from app.shared.enums import ModelProvider
from app.shared.schemas import ModelConfig


def model_config() -> ModelConfig:
    return ModelConfig(
        provider=ModelProvider.OPENAI_COMPATIBLE,
        model_name="dialogue-eval",
        base_url="http://invalid",
        api_key=SecretStr("not-used"),
    )


def loop_state(runtime_id: str, prompt: str = "检查目标") -> LoopState:
    return LoopState(
        phase="executing",
        context=LoopContext(
            runtime_id=runtime_id,
            conversation_id="eval-conversation",
            asset_id=0,
            asset_type="local_terminal",
            terminal_id=None,
            asset_summary="local evaluation asset",
            shell_type="bash",
            os_type="linux",
            user_prompt=prompt,
            model_config=model_config(),
        ),
    )


class DummyTool:
    def __init__(self, *, succeeds: bool = True) -> None:
        self.succeeds = succeeds
        self.calls = 0

    @property
    def definition(self) -> LLMToolDefinition:
        return LLMToolDefinition(
            name="dummy",
            description="Deterministic evaluation tool.",
            input_schema={"type": "object", "properties": {}},
        )

    def needs_approval(self, args: dict[str, Any]) -> tuple[str, str]:
        _ = args
        return "allow", "evaluation"

    def display_metadata(self, args: dict[str, Any]) -> ToolDisplayMetadata:
        _ = args
        return ToolDisplayMetadata(display_text="evaluation tool")

    def execute(
        self,
        *,
        state: LoopState,
        step_id: str,
        args: dict[str, Any],
        manager=None,
    ) -> Iterator:
        _ = state, step_id, args
        self.calls += 1
        output = "ok" if self.succeeds else "expected evaluation failure"
        if manager:
            yield from manager.update(tool_output=output)
        return self.succeeds, output


def scenario_followup_resume_and_hidden_reasoning() -> None:
    state = loop_state("eval-followup")

    class Provider:
        def __init__(self) -> None:
            self.calls = 0

        def stream_complete(self, *, config, request):
            _ = config
            self.calls += 1
            if self.calls == 1:
                yield LLMCompletionChunk(
                    thinking_delta="hidden reasoning",
                    tool_calls=[LLMToolCall(
                        id="followup-1",
                        name="ask_followup",
                        arguments={"question": "目标资产是哪一台？"},
                    )],
                    finish_reason="tool_calls",
                )
                return
            assert request.messages[-1].role == "user"
            assert request.messages[-1].content == "资产 42"
            yield LLMCompletionChunk(delta="已确认目标资产。", finish_reason="stop")

    provider = Provider()
    agent_loop_module.build_llm_provider = lambda config: provider
    loop = AgentLoop(tools=[AskFollowupHandler()])
    first_events = list(loop.run(state))
    assert state.phase == "waiting_user_input"
    assert state.pending_followup_question == "目标资产是哪一台？"
    assert any(event.payload.get("ask") == "followup" for event in first_events)
    assert all(not event.payload.get("thinking") for event in first_events)
    state.phase = "executing"
    state.pending_followup_question = None
    state.pending_user_messages.append("资产 42")
    list(loop.run(state))
    assert state.phase == "completed"
    assert state.summary == "已确认目标资产。"


def scenario_runtime_steering_preempts_unstarted_tool() -> None:
    state = loop_state("eval-steering", "执行检查")
    tool = DummyTool()

    class Provider:
        def __init__(self) -> None:
            self.calls = 0

        def stream_complete(self, *, config, request):
            _ = config
            self.calls += 1
            if self.calls == 1:
                state.pending_user_messages.append("不要执行，改为只说明方案")
                yield LLMCompletionChunk(
                    tool_calls=[LLMToolCall(id="tool-1", name="dummy", arguments={})],
                    finish_reason="tool_calls",
                )
                return
            assert request.messages[-1].content == "不要执行，改为只说明方案"
            yield LLMCompletionChunk(delta="已改为只说明方案。", finish_reason="stop")

    agent_loop_module.build_llm_provider = lambda config: Provider()
    list(AgentLoop(tools=[tool]).run(state))
    assert tool.calls == 0
    assert state.phase == "completed"


def scenario_tool_failure_can_be_recovered() -> None:
    state = loop_state("eval-recovery", "诊断问题")
    tool = DummyTool(succeeds=False)

    class Provider:
        def __init__(self) -> None:
            self.calls = 0

        def stream_complete(self, *, config, request):
            _ = config, request
            self.calls += 1
            if self.calls == 1:
                yield LLMCompletionChunk(
                    tool_calls=[LLMToolCall(id="tool-2", name="dummy", arguments={})],
                    finish_reason="tool_calls",
                )
                return
            yield LLMCompletionChunk(delta="首个检查失败，但替代证据已经给出结论。", finish_reason="stop")

    agent_loop_module.build_llm_provider = lambda config: Provider()
    list(AgentLoop(tools=[tool]).run(state))
    assert any(step.status == "failed" for step in state.steps)
    assert state.phase == "completed"


def scenario_approval_guidance_reaches_continuation() -> None:
    state = loop_state("eval-approval-guidance", "执行变更")
    state.phase = "approving"
    state.steps.append(LoopRuntimeStep(
        step_id="approval-step",
        title="dummy",
        reason="evaluation",
        risk_level="high",
    ))
    state.pending_tool_call_id = "approval-call"
    state.pending_tool_name = "dummy"
    state.pending_tool_args = {}
    state.pending_approval_step_id = "approval-step"
    state.messages.append(LLMMessage(
        role="assistant",
        content="",
        tool_calls=[LLMToolCall(id="approval-call", name="dummy", arguments={})],
    ))
    state.pending_user_messages.append("不要执行，改为只读诊断")

    class Provider:
        def stream_complete(self, *, config, request):
            _ = config
            assert request.messages[-1].role == "user"
            assert request.messages[-1].content == "不要执行，改为只读诊断"
            assert any(message.role == "tool" and "rejected" in message.content.lower() for message in request.messages)
            yield LLMCompletionChunk(delta="已按拒绝原因切换为只读诊断。", finish_reason="stop")

    agent_loop_module.build_llm_provider = lambda config: Provider()
    list(AgentLoop(tools=[DummyTool()]).resume_with_approval(state, approved=False))
    assert state.phase == "completed"
    assert state.summary == "已按拒绝原因切换为只读诊断。"


def scenario_semantic_task_state_round_trip() -> None:
    events = [
        {"id": "u1", "kind": "user", "text": "检查磁盘"},
        {
            "id": "state1",
            "kind": "task_state",
            "goal": "定位磁盘占用",
            "currentRequest": "先只读检查",
            "scope": ["asset-42"],
            "constraints": ["不得删除文件"],
            "acceptanceCriteria": ["给出可验证根因"],
            "verifiedFacts": ["磁盘使用率 92% (source: df output)"],
            "decisions": ["仅只读诊断"],
            "openItems": ["定位最大目录"],
            "completedItems": [],
            "revision": 3,
        },
    ]
    with TemporaryDirectory() as tmp:
        result = ContextManager(Path(tmp)).prepare_context(
            "eval-conversation",
            events,
            model_config(),
            current_prompt="继续，但不要删除文件",
        )
    assert result.task_state.goal == "定位磁盘占用"
    assert result.task_state.current_request == "继续，但不要删除文件"
    assert "asset-42" in result.task_state.retrieval_query("继续")

    state = loop_state("eval-task-state")
    state.context.task_state = result.task_state

    class Provider:
        def __init__(self) -> None:
            self.calls = 0

        def stream_complete(self, *, config, request):
            _ = config
            self.calls += 1
            if self.calls == 1:
                yield LLMCompletionChunk(
                    tool_calls=[LLMToolCall(
                        id="state-update-1",
                        name="update_task_state",
                        arguments={
                            "verified_facts": [
                                "磁盘使用率 92% (source: df output)",
                                "/var 占用最大 (source: du output)",
                            ],
                            "open_items": ["确认 /var 下的具体目录"],
                            "completed_items": ["确认磁盘总体使用率"],
                        },
                    )],
                    finish_reason="tool_calls",
                )
                return
            assert "/var 占用最大" in request.messages[1].content
            yield LLMCompletionChunk(delta="任务状态已更新。", finish_reason="stop")

    agent_loop_module.build_llm_provider = lambda config: Provider()
    runtime_events = list(AgentLoop(tools=[UpdateTaskStateHandler()]).run(state))
    assert any(event.event_type == "task_state" for event in runtime_events)
    assert state.context.task_state.revision == 4


def scenario_unverified_execution_claim_is_rejected() -> None:
    state = loop_state("eval-unverified-execution", "检查服务状态")

    class Provider:
        def __init__(self) -> None:
            self.calls = 0

        def stream_complete(self, *, config, request):
            _ = config
            self.calls += 1
            if self.calls == 1:
                yield LLMCompletionChunk(delta="命令已执行成功，Exit code: 0", finish_reason="stop")
                return
            assert "rejected" in request.messages[-1].content
            yield LLMCompletionChunk(delta="没有执行命令，当前没有可验证结果。", finish_reason="stop")

    provider = Provider()
    agent_loop_module.build_llm_provider = lambda config: provider
    events = list(AgentLoop(tools=[]).run(state))
    assert provider.calls == 2
    assert state.phase == "completed"
    assert state.summary == "没有执行命令，当前没有可验证结果。"
    assert any("未经工具验证" in str(event.payload.get("text") or "") for event in events)


def scenario_cross_asset_discovery_requires_approval() -> None:
    import asyncio
    from unittest.mock import MagicMock
    from app.core.loop.runtime_manager import LoopRuntimeManager
    from app.core.tool.terminal_autonomy import ListAssetsHandler
    from app.core.tool.ports import AssetSummary
    from app.core.tool.execute_command import ExecuteCommandHandler
    from app.services.conversation_service import ConversationService
    from app.db.models import Asset

    candidates = [AssetSummary(2, "core", "huawei", host="192.0.2.1", group_name="机房 A", access_via="jumpserver")]
    catalog = MagicMock()
    catalog.list_assets.return_value = candidates
    catalog.get_asset.return_value = candidates[0]
    for approved in (False, True):
        with TemporaryDirectory(prefix="ops-discovery-eval-") as tmp:
            conversations = ConversationService(Path(tmp))
            conversation = conversations.create_conversation(None, asset_id=1)
            manager = LoopRuntimeManager(tools_factory=lambda _: [ListAssetsHandler(catalog), RequestTerminalSessionHandler(manager, catalog=catalog)], runtime_store=MagicMock())
            ctx = loop_state(f"eval-cross-device-{approved}", "服务器网络不通，不知道接在哪台交换机，请通过 JumpServer 查").context
            ctx.asset_id = 1
            ctx.conversation_id = conversation.id
            ctx.conversation_primary_asset_id = 1
            ctx.allowed_asset_ids = [1]
            state = manager.create_runtime(conversation_id=conversation.id, asset_id=1, terminal_id=None, context=ctx)
            terminal = MagicMock()
            terminal.open_session.return_value = {"terminal_id": "core-terminal", "channel": None}
            terminal.get_shell_kind.return_value = "huawei"

            class Provider:
                calls = 0
                def stream_complete(self, *, config, request):
                    self.calls += 1
                    if self.calls == 1:
                        name, args = "list_assets", {"intent": "remote_execution_required", "justification": "查找关联交换机", "query": "机房 A"}
                    elif self.calls == 2:
                        output = json.loads(next(m.content for m in reversed(request.messages) if m.role == "tool"))
                        assert output["assets"][0]["host"] == "192.0.2.1"
                        assert output["assets"][0]["access_via"] == "jumpserver"
                        name, args = "request_terminal_session", {"asset_id": 2, "reason": "机房 A 的核心设备候选，需查询 ARP/MAC", "intent": "remote_execution_required"}
                    else:
                        assert ctx.conversation_scope_mode == ("multi" if approved else "single")
                        assert ctx.allowed_asset_ids == ([1, 2] if approved else [1])
                        yield LLMCompletionChunk(delta="下一步需验证服务器接入端口。", finish_reason="stop")
                        return
                    yield LLMCompletionChunk(tool_calls=[LLMToolCall(id=f"discover-{self.calls}", name=name, arguments=args)], finish_reason="tool_calls")

            provider = Provider()
            agent_loop_module.build_llm_provider = lambda config: provider
            events = list(manager.run(runtime_id=ctx.runtime_id, terminal_service=terminal))
            assert state.phase == "waiting_terminal_approval"
            assert ctx.conversation_scope_mode == "single" and ctx.allowed_asset_ids == [1]
            assert ExecuteCommandHandler._scope_error(state, 2) is not None
            terminal.open_session.assert_not_called()
            event = next(event for event in events if event.get("kind") == "terminal_session_request")
            assert event["scopeExpansionRequired"] is True
            try:
                conversations.ensure_asset_access(conversation.id, 2)
            except ValueError:
                pass
            else:
                raise AssertionError("Scope expanded before approval")
            result = asyncio.run(manager.decide_terminal_request(ctx.runtime_id, event["requestId"], approval_token=event["approvalToken"], approved=approved,
                terminal_service=terminal, asset=Asset(id=2, name="core", asset_type="huawei", host="192.0.2.1")))
            if approved:
                conversations.allow_asset(conversation.id, 2)
            list(manager.resume_after_terminal_request(runtime_id=ctx.runtime_id, resume_message=str(result.get("resumeMessage") or "User rejected connection"), terminal_service=terminal, authorization_id=result.get("authorizationId")))
            assert state.phase == "completed" and provider.calls == 3
            assert terminal.open_session.call_count == int(approved)
            assert (ExecuteCommandHandler._scope_error(state, 2) is None) == approved
            restored = ConversationService(Path(tmp)).get_conversation(conversation.id)
            assert restored.scope_mode == ("multi" if approved else "single")
            assert restored.asset_id == 1 and restored.allowed_asset_ids == ([1, 2] if approved else [1])



def scenario_removed_discovery_mode_keeps_history_readable() -> None:
    from dataclasses import asdict
    from app.services.conversation_service import ConversationService
    with TemporaryDirectory(prefix="ops-discovery-compat-") as tmp:
        service = ConversationService(Path(tmp))
        summary = service.create_conversation(None, asset_id=1)
        payload = asdict(summary)
        payload["discovery_context"] = ""
        assert service._summary_from_payload(payload).scope_mode == "single"
        payload.update(scope_mode="discovery", discovery_context="192.0.2.40 网络不通", events=[])
        detail = service._detail_from_payload(payload)
        assert detail.scope_mode == "multi" and detail.events[0]["text"] == "192.0.2.40 网络不通"
        assert detail.event_count == 1


def scenario_approval_rechecks_terminal_consistency() -> None:
    state = loop_state("eval-approval-consistency", "执行受控命令")
    authorization = SimpleNamespace(
        authorization_id="auth-1",
        status="active",
        asset_id=1,
        asset_name="asset-1",
        terminal_id="terminal-1",
        asset_type="linux",
        shell_type="bash",
        execution_profile="posix-shell",
        device_vendor=None,
    )

    class Terminal:
        def resolve_terminal_authorization(self, runtime_id: str, authorization_id: str):
            assert runtime_id == state.context.runtime_id
            assert authorization_id == authorization.authorization_id
            return authorization

        def session_belongs_to_asset(self, terminal_id: str, asset_id: int) -> bool:
            return terminal_id == authorization.terminal_id and asset_id == authorization.asset_id

    class ApprovalTool(DummyTool):
        def __init__(self) -> None:
            super().__init__()
            self._terminal = Terminal()

        @property
        def definition(self) -> LLMToolDefinition:
            return LLMToolDefinition(
                name="execute_command",
                description="Evaluation command tool.",
                input_schema={"type": "object", "properties": {}},
            )

        def needs_approval(self, args: dict[str, Any]) -> tuple[str, str]:
            _ = args
            return "ask", "evaluation approval"

        def display_metadata(self, args: dict[str, Any]) -> ToolDisplayMetadata:
            _ = args
            return ToolDisplayMetadata(display_text="echo safe", extra={"kind": "command"})

    class Provider:
        def __init__(self) -> None:
            self.calls = 0

        def stream_complete(self, *, config, request):
            _ = config, request
            self.calls += 1
            if self.calls == 1:
                yield LLMCompletionChunk(
                    tool_calls=[LLMToolCall(
                        id="approval-consistency-1",
                        name="execute_command",
                        arguments={"authorization_id": "auth-1", "command": "echo safe", "explanation": "打印测试标记，验证审批时重新检查终端授权。"},
                    )],
                    finish_reason="tool_calls",
                )
                return
            yield LLMCompletionChunk(delta="授权目标变化，命令未执行。", finish_reason="stop")

    provider = Provider()
    tool = ApprovalTool()
    agent_loop_module.build_llm_provider = lambda config: provider
    loop = AgentLoop(tools=[tool])
    list(loop.run(state))
    assert state.phase == "approving"
    authorization.terminal_id = "terminal-changed"
    list(loop.resume_with_approval(state, approved=True))
    assert tool.calls == 0
    assert state.phase == "completed"
    assert state.steps[0].status == "failed"


def scenario_prompt_composition_preserves_boundaries() -> None:
    from app.core.loop.request_builder import AgentLLMRequestBuilder
    from app.core.prompts.memory import build_memory_context, MEMORY_CONSTRAINTS
    from app.core.prompts.auxiliary import build_knowledge_extraction_prompt

    state = loop_state("prompt-boundaries")
    ctx = state.context
    ctx.agent_behavior_prompt = "自定义业务说明"
    ctx.organization_rules_prompt = "组织规则" * 2500
    ctx.default_authorization_id = "auth-original"
    ctx.knowledge_context = build_memory_context(["历史证据"], guidance="记忆偏好" * 2000)
    ctx.conversation_history = [LLMMessage(role="user", content="历史问题")]
    builder = AgentLLMRequestBuilder()
    state.messages = builder.build_initial_tool_calling_messages(state=state)
    assert [message.role for message in state.messages] == ["system", "user", "system", "user"]
    assert state.messages[-1].content == ctx.user_prompt
    assert MEMORY_CONSTRAINTS in ctx.knowledge_context
    original_memory = ctx.knowledge_context
    ctx.default_authorization_id = "auth-updated"
    request = builder.build_tool_calling_request(state=state, tools=[])
    assert "auth-updated" in request.messages[1].content
    assert "auth-original" not in request.messages[1].content
    assert "自定义业务说明" in request.messages[0].content
    assert "Every command requires explicit operator approval" in request.messages[0].content
    assert ctx.organization_rules_prompt in request.messages[0].content
    memory = next(message for message in request.messages if message.cache_segment == "runtime_context" and message.content == original_memory)
    assert memory.cache_status == "volatile" and memory.content == original_memory
    ctx.loaded_skill_name = "evaluation"
    ctx.manual_skill_content = "技能规则" * 2500
    builder.append_loaded_skill(state)
    builder.append_loaded_skill(state)
    builder.compact_state_messages(state)
    assert sum(ctx.manual_skill_content in message.content for message in state.messages) == 1
    extraction = build_knowledge_extraction_prompt("仅提取已证实事实")
    assert "strict JSON" in extraction and "redactionWarnings" in extraction
    assert "仅提取已证实事实" in extraction


def scenario_auxiliary_generation_uses_default_model() -> None:
    from unittest.mock import patch
    from sqlalchemy import create_engine
    from sqlmodel import Session
    from app.db.models import ModelConfigRecord
    from app.core.llm.types import LLMCompletionResponse
    from app.services.model_service import ModelService
    import app.services.model_service as models

    calls = []

    class Provider:
        def complete(self, *, config, request):
            calls.append((config, request))
            return LLMCompletionResponse(text="验证标题")

    with TemporaryDirectory(prefix="ops-default-model-eval-") as tmp:
        engine = create_engine(f"sqlite:///{Path(tmp) / 'models.db'}")
        ModelConfigRecord.__table__.create(engine)
        try:
            with Session(engine) as session:
                session.add(ModelConfigRecord(
                    name="Selected CC Switch", provider="anthropic", base_url="http://example.invalid",
                    api_key_encryption_version="evaluation", encrypted_api_key="not-a-real-key",
                    model_name="selected-model", is_default=True,
                ))
                session.commit()
            with patch.object(models, "engine", engine), patch.object(ModelService, "decrypt_api_key", return_value=SecretStr("evaluation")):
                service = ModelService(provider_client=Provider())
                assert service.generate_conversation_title("验证当前模型") == "验证标题"
                service.generate_knowledge_draft("已验证的事件")
                assert len(calls) == 2
                assert all(config.model_name == "selected-model" and config.provider == ModelProvider.ANTHROPIC for config, _ in calls)
                assert calls[0][1].messages[0].role == "system"
                assert calls[1][1].json_mode is True
        finally:
            engine.dispose()


def scenario_cc_switch_is_the_only_active_provider() -> None:
    from app.core.llm.factory import build_llm_provider
    from app.core.llm.cc_switch import DEFAULT_MODEL, DEFAULT_BASE_URL
    from app.services.model_service import ModelService
    from app.api.schemas.resources import ModelConfigCreate
    from pydantic import ValidationError
    from unittest.mock import patch
    import os

    with TemporaryDirectory(prefix="ops-cc-default-eval-") as tmp, patch.dict(os.environ, {}, clear=True):
        service = ModelService(settings_path=Path(tmp) / "settings.json")
        config = service.load_settings()
        assert config.provider == ModelProvider.ANTHROPIC
        assert config.model_name == DEFAULT_MODEL and config.base_url == DEFAULT_BASE_URL
        assert config.model_name == ""  # No hard-coded model choice.
        for provider in ModelProvider:
            if provider == ModelProvider.ANTHROPIC:
                continue
            try:
                build_llm_provider(config.model_copy(update={"provider": provider}))
            except ValueError as exc:
                assert "CC Switch" in str(exc)
            else:
                raise AssertionError(f"Legacy provider remains callable: {provider}")
        try:
            ModelConfigCreate(name="legacy", provider="openai_compatible", base_url="http://example.invalid", api_key="evaluation", model_name="legacy")
        except ValidationError:
            pass
        else:
            raise AssertionError("Model API accepted an unsupported provider")



def scenario_unbound_conversation_does_not_bind_on_send() -> None:
    from app.services.conversation_service import ConversationService
    from app.api.schemas.runtime import ConversationCreateRequest
    with TemporaryDirectory(prefix="ops-unbound-eval-") as tmp:
        service = ConversationService(Path(tmp))
        assert ConversationCreateRequest().asset_id is None
        conversation = service.create_conversation(None)
        assert conversation.asset_id is None and conversation.allowed_asset_ids == []
        assert conversation.scope_mode == "multi"
        service.ensure_asset_access(conversation.id, None)
        try:
            service.ensure_asset_access(conversation.id, 0)
        except ValueError:
            pass
        else:
            raise AssertionError("Unbound chat silently authorized the local terminal")
        service.allow_asset(conversation.id, 2)
        service.append_events(conversation.id, [{"id": "request", "kind": "user", "text": "请继续排查"}], async_title_generation=False)
        restored = ConversationService(Path(tmp)).get_conversation(conversation.id)
        assert restored.asset_id is None and restored.allowed_asset_ids == [2]
        rewritten = service.truncate_before_event(conversation.id, "request")
        assert rewritten.asset_id is None and rewritten.allowed_asset_ids == [2]
        assert service.create_conversation(None, asset_id=0).allowed_asset_ids == [0]
        assert service.create_conversation(None, asset_id=7).allowed_asset_ids == [7]


def scenario_unbound_api_ignores_stale_terminal_selection() -> None:
    import asyncio
    from unittest.mock import MagicMock, patch
    from starlette.requests import Request
    from app.api.console import run_console_agent
    from app.services.conversation_service import ConversationService
    with TemporaryDirectory(prefix="ops-unbound-api-") as tmp:
        service = ConversationService(Path(tmp))
        for target in (None, 0, 7):
            conversation = service.create_conversation(None, asset_id=target)
            body = json.dumps({"prompt": "继续排查", "asset_id": target if target is not None else 7,
                               "terminal_id": "previous-terminal", "conversation_id": conversation.id}).encode()
            async def receive():
                return {"type": "http.request", "body": body, "more_body": False}
            request = Request({"type": "http", "method": "POST", "path": "/api/console/run", "headers": []}, receive)
            orchestrator = MagicMock()
            orchestrator.stream_run.return_value = iter([{"kind": "final", "text": "evaluation"}])
            with patch("app.api.console.get_conversation_service", return_value=service):
                asyncio.run(run_console_agent(request, session=MagicMock(), orchestrator=orchestrator))
            kwargs = orchestrator.stream_run.call_args.kwargs
            assert kwargs["asset_id"] == target
            assert kwargs["terminal_id"] == (None if target is None else "previous-terminal")
            assert kwargs["allowed_asset_ids"] == ([] if target is None else [target])
            restored = service.get_conversation(conversation.id)
            assert restored.asset_id == target and restored.events[0]["assetId"] == target


def scenario_unbound_runtime_has_no_initial_authorization() -> None:
    from unittest.mock import MagicMock, patch
    from app.services.console_app_service import ConsoleAppService
    from app.core.loop.task_state import AgentTaskState
    from app.core.prompts.agent import build_tool_calling_system_prompt
    class CapturedRuntime(Exception):
        pass
    service = object.__new__(ConsoleAppService)
    service.runtime_manager = MagicMock()
    service.runtime_manager.create_runtime.side_effect = CapturedRuntime
    service._skill_service = MagicMock()
    service._skill_service.list_skills.return_value = []
    terminal = MagicMock()
    terminal.find_session_id.return_value = "local-terminal-already-open"
    context_result = SimpleNamespace(prepared_messages=[], task_state=AgentTaskState())
    with patch.object(service, "resolve_model_config", return_value=model_config()), \
         patch.object(service, "_prepare_conversation_context", return_value=context_result), \
         patch("app.services.knowledge_factory.get_knowledge_service") as knowledge:
        knowledge.return_value.search_for_agent.return_value = []
        knowledge.return_value.format_agent_context.return_value = ""
        iterator = service.stream_run(session=MagicMock(), prompt="服务器网络不通，查找关联交换机", asset_id=None,
                                      terminal_id="previous-terminal", terminal_service=terminal)
        try:
            next(iterator)
        except CapturedRuntime:
            pass
        else:
            raise AssertionError("Runtime initialization was not captured")
    terminal.find_session_id.assert_not_called()
    terminal.session_belongs_to_asset.assert_not_called()
    service.runtime_manager.create_initial_terminal_authorization.assert_not_called()
    ctx = service.runtime_manager.create_runtime.call_args.kwargs["context"]
    assert ctx.terminal_id is None and ctx.default_authorization_id is None
    assert ctx.allowed_asset_ids == [] and ctx.conversation_primary_asset_id is None
    assert ctx.execution_profile == "unbound"
    prompt = build_tool_calling_system_prompt(ctx)
    assert '"currentAssetId":null' in prompt and '"primaryAssetId":null' in prompt


def model_gateway_error(status: int = 422, message: str = "格式转换错误: Responses upstream service_unavailable_error: Our servers are currently overloaded. Please try again later.", headers=None):
    import httpx
    from anthropic import APIStatusError
    response = httpx.Response(status, request=httpx.Request("POST", "http://evaluation.invalid/messages"), headers=headers)
    return APIStatusError(message, response=response, body={"error": {"type": "proxy_error", "message": message}})


def scenario_model_retry_after_approval_does_not_repeat_tool() -> None:
    from unittest.mock import patch
    class ApprovedTool(DummyTool):
        def needs_approval(self, args):
            return "ask", "operator must approve"
    tool = ApprovedTool()
    state = loop_state("eval-model-retry")
    class Provider:
        calls = 0
        followup_requests = []
        def stream_complete(self, *, config, request):
            self.calls += 1
            if self.calls == 1:
                yield LLMCompletionChunk(tool_calls=[LLMToolCall(id="approved-once", name="dummy", arguments={})], finish_reason="tool_calls")
                return
            self.followup_requests.append(request)
            assert tool.calls == 1
            assert sum(m.role == "tool" and m.tool_call_id == "approved-once" for m in request.messages) == 1
            if self.calls < 4:
                raise model_gateway_error()
            yield LLMCompletionChunk(delta="结果分析已恢复。", finish_reason="stop")
    provider = Provider()
    agent_loop_module.build_llm_provider = lambda config: provider
    loop = AgentLoop(tools=[tool])
    list(loop.run(state))
    assert state.phase == "approving" and tool.calls == 0
    with patch.object(loop, "_wait_for_model_retry") as wait:
        events = list(loop.resume_with_approval(state, approved=True))
    assert state.phase == "completed" and state.summary == "结果分析已恢复。"
    assert provider.calls == 4 and state.llm_calls == 4 and tool.calls == 1
    assert all(request is provider.followup_requests[0] for request in provider.followup_requests)
    assert wait.call_count == 2
    assert sum("自动重试" in str(e.payload.get("text", "")) for e in events) == 2
    assert not any("自动重试" in m.content for m in state.messages)


def scenario_model_retry_limits_and_permanent_errors() -> None:
    from unittest.mock import patch
    from app.core.llm.retry import ModelRetryExhausted, is_retryable_model_error
    from app.core.loop.runtime_execution import _user_facing_runtime_error
    for status, message, expected_calls in [
        (422, "proxy_error: Our servers are currently overloaded", 4),
        (429, "rate_limit_error", 4), (503, "unavailable", 4),
        (401, "invalid api key", 1), (400, "invalid messages", 1),
        (422, "invalid tool schema", 1), (429, "insufficient_quota", 1),
    ]:
        error = model_gateway_error(status, message)
        class Provider:
            calls = 0
            def stream_complete(self, *, config, request):
                self.calls += 1
                raise error
                yield
        provider = Provider()
        agent_loop_module.build_llm_provider = lambda config: provider
        loop = AgentLoop(tools=[])
        with patch.object(loop, "_wait_for_model_retry") as wait:
            try:
                list(loop.run(loop_state(f"retry-limit-{status}")))
            except Exception as exc:
                if expected_calls == 4:
                    assert isinstance(exc, ModelRetryExhausted)
                    assert "自动重试 3 次" in _user_facing_runtime_error(exc)
                else:
                    assert exc is error
            else:
                raise AssertionError("Expected model failure")
        assert provider.calls == expected_calls and wait.call_count == expected_calls - 1
    import httpx
    assert is_retryable_model_error(httpx.ConnectError("connection reset"))
    assert is_retryable_model_error(httpx.ReadTimeout("timeout"))


def scenario_model_retry_does_not_replay_partial_stream() -> None:
    from unittest.mock import patch
    for preview in (False, True):
        class Provider:
            calls = 0
            def stream_complete(self, *, config, request):
                self.calls += 1
                if preview:
                    yield LLMCompletionChunk(tool_call_preview=LLMToolCall(id="draft", name="execute_command", arguments={"command": "show version", "explanation": "读取版本"}))
                else:
                    yield LLMCompletionChunk(delta="部分分析")
                raise model_gateway_error()
        provider = Provider()
        agent_loop_module.build_llm_provider = lambda config: provider
        loop = AgentLoop(tools=[])
        with patch.object(loop, "_wait_for_model_retry") as wait:
            try:
                list(loop.run(loop_state("partial-retry")))
            except Exception as exc:
                assert getattr(exc, "status_code", None) == 422
            else:
                raise AssertionError("Partial stream silently retried")
        assert provider.calls == 1 and wait.call_count == 0


def scenario_model_retry_wait_can_be_cancelled() -> None:
    from unittest.mock import patch
    from app.core.runtime.control import RuntimeCancelledError, RuntimeBudgetExceededError
    from app.core.llm.retry import model_retry_delay
    state = loop_state("retry-cancel")
    class Provider:
        calls = 0
        def stream_complete(self, *, config, request):
            self.calls += 1
            raise model_gateway_error()
            yield
    provider = Provider()
    agent_loop_module.build_llm_provider = lambda config: provider
    def cancel(_seconds):
        state.cancel_requested = True
    with patch("app.core.loop.agent_loop.time.sleep", side_effect=cancel):
        try:
            list(AgentLoop(tools=[]).run(state))
        except RuntimeCancelledError:
            pass
        else:
            raise AssertionError("Retry wait ignored cancellation")
    assert provider.calls == 1
    budget = loop_state("retry-budget")
    budget.max_llm_calls = 1
    loop = AgentLoop(tools=[])
    with patch.object(loop, "_wait_for_model_retry"):
        try:
            list(loop.run(budget))
        except RuntimeBudgetExceededError:
            pass
        else:
            raise AssertionError("Retries ignored LLM call budget")
    assert provider.calls == 2 and budget.llm_calls == 1
    with patch("app.core.llm.retry.random.uniform", return_value=0):
        assert [model_retry_delay(model_gateway_error(), i) for i in (1, 2, 3)] == [2, 4, 8]
        assert model_retry_delay(model_gateway_error(429, "rate limited", {"Retry-After": "12"}), 1) == 12
        assert model_retry_delay(model_gateway_error(429, "rate limited", {"Retry-After": "invalid"}), 1) == 2
        assert model_retry_delay(model_gateway_error(429, "rate limited", {"Retry-After": "NaN"}), 1) == 2


def scenario_model_retry_uses_real_sdk_without_nested_retries(failure_kind: str = "http", partial: bool = False) -> None:
    import httpx
    from anthropic import Anthropic
    from unittest.mock import patch
    from app.core.llm.providers.anthropic import AnthropicLLMProvider
    requests = []
    def respond(request):
        requests.append(json.loads(request.content))
        if len(requests) <= 2 and failure_kind == "http":
            return httpx.Response(429 if len(requests) == 1 else 422, json={"error": {"type": "proxy_error", "message": "Responses upstream service_unavailable_error: Our servers are currently overloaded."}})
        events = [
            ("message_start", {"type": "message_start", "message": {"id": "mock-message", "type": "message", "role": "assistant", "content": [], "model": "mock", "usage": {"input_tokens": 8, "output_tokens": 0}}}),
            ("content_block_start", {"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}}),
            ("content_block_delta", {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "恢复成功。"}}),
            ("content_block_stop", {"type": "content_block_stop", "index": 0}),
            ("message_delta", {"type": "message_delta", "delta": {"stop_reason": "end_turn"}, "usage": {"output_tokens": 4}}),
            ("message_stop", {"type": "message_stop"}),
        ]
        if len(requests) <= 2 and failure_kind != "http":
            events = events[:3] if partial else events[:1]
            if failure_kind == "stream_error":
                events.append(("error", {"type": "error", "error": {"type": "stream_error", "message": "Stream error: error decoding response body"}}))
        body = "".join(f"event: {name}\ndata: {json.dumps(payload)}\n\n" for name, payload in events)
        return httpx.Response(200, text=body, headers={"content-type": "text/event-stream"})
    with httpx.Client(transport=httpx.MockTransport(respond)) as http_client:
        client = Anthropic(api_key="evaluation-only", base_url="http://evaluation.invalid", http_client=http_client)
        provider = AnthropicLLMProvider(client)
        agent_loop_module.build_llm_provider = lambda config: provider
        state = loop_state("sdk-visible-retry")
        loop = AgentLoop(tools=[])
        with patch.object(loop, "_wait_for_model_retry") as wait:
            if partial:
                from app.core.loop.runtime_execution import _user_facing_runtime_error
                try:
                    list(loop.run(state))
                except Exception as error:
                    assert "响应中断" in _user_facing_runtime_error(error)
                else:
                    raise AssertionError("Partial stream silently retried")
                assert len(requests) == 1 and wait.call_count == 0
                return
            events = list(loop.run(state))
        assert len(requests) == 3 and requests[0] == requests[1] == requests[2]
        assert state.llm_calls == 3 and state.summary == "恢复成功。"
        assert wait.call_count == 2
        assert sum("自动重试" in str(e.payload.get("text", "")) for e in events) == 2


def scenario_model_retry_stream_errors_and_truncated_responses() -> None:
    for failure_kind in ("stream_error", "truncated"):
        for partial in (False, True):
            scenario_model_retry_uses_real_sdk_without_nested_retries(failure_kind, partial)


def scenario_failed_terminal_connection_resumes_guidance() -> None:
    import asyncio
    from unittest.mock import MagicMock
    from app.core.loop.runtime_manager import LoopRuntimeManager
    from app.db.models import Asset
    for legacy in (False, True):
        manager = LoopRuntimeManager(tools_factory=lambda _: [], runtime_store=MagicMock())
        ctx = loop_state(f"failed-terminal-{legacy}").context
        state = manager.create_runtime(conversation_id=ctx.conversation_id, asset_id=0, terminal_id=None, context=ctx)
        state.phase = "waiting_terminal_approval"
        request, token, _ = manager.create_terminal_request(ctx.runtime_id, conversation_id=ctx.conversation_id, asset_id=2, asset_name="candidate", reason="inspect")
        terminal = MagicMock()
        terminal.open_session.side_effect = RuntimeError("connection timed out")
        result = asyncio.run(manager.decide_terminal_request(ctx.runtime_id, request.request_id, approval_token=token, approved=True, terminal_service=terminal, asset=Asset(id=2, name="candidate", asset_type="huawei")))
        assert result["terminalCreationStatus"] == "failed" and result["authorizationId"] is None
        assert "connection timed out" in result["resumeMessage"]
        class Provider:
            def stream_complete(self, *, config, request):
                content = str(request)
                assert "connection timed out" in content
                if legacy:
                    assert "看看其他交换机" in content
                yield LLMCompletionChunk(delta="将选择其他候选设备并申请连接。", finish_reason="stop")
        agent_loop_module.build_llm_provider = lambda config: Provider()
        if legacy:
            state.pending_user_messages.append("这台不能用，换一台")
            list(manager.submit_user_message(runtime_id=ctx.runtime_id, message="看看其他交换机", terminal_service=terminal))
        else:
            list(manager.resume_after_terminal_request(runtime_id=ctx.runtime_id, resume_message=result["resumeMessage"], terminal_service=terminal))
        assert state.phase == "completed" and not state.pending_user_messages
        assert terminal.open_session.call_count == 1

    # A failed connection must still return the continuation stream, not HTTP 502.
    import importlib
    from unittest.mock import AsyncMock, patch
    api = importlib.import_module("app.api.console")
    fake_manager = MagicMock()
    fake_manager.get_runtime.return_value = SimpleNamespace(conversation_id="eval", terminal_requests={"req": SimpleNamespace(asset_id=2, scope_expansion_required=False)})
    fake_manager.decide_terminal_request = AsyncMock(return_value=result)
    orchestrator = MagicMock()
    orchestrator.stream_after_terminal_request.return_value = iter([])
    payload = SimpleNamespace(runtime_id="eval", approval_token="test", approved=True)
    with patch.object(api, "_parse_request_model", AsyncMock(return_value=payload)), patch.object(api, "_console_app_service", SimpleNamespace(runtime_manager=fake_manager)), patch.object(api, "get_asset_record", return_value=Asset(id=2, name="candidate", asset_type="huawei")), patch.object(api, "_persisted_stream", side_effect=lambda _, events: events), patch.object(api, "_streaming_response", side_effect=list):
        events = asyncio.run(api.decide_terminal_request("req", MagicMock(), MagicMock(), terminal, orchestrator))
    assert events[0]["kind"] == "terminal_session_rejected"
    assert events[0]["terminalCreationStatus"] == "failed"
    assert "connection timed out" in orchestrator.stream_after_terminal_request.call_args.kwargs["resume_message"]


def scenario_prompt_cache_breakpoints_and_budget() -> None:
    from dataclasses import replace
    from app.core.llm.providers.anthropic import AnthropicLLMProvider
    from app.core.llm.types import LLMCompletionRequest, LLMPromptCachePolicy
    from app.core.llm.context import estimate_request_tokens
    from app.core.loop.request_builder import AgentLLMRequestBuilder
    provider = AnthropicLLMProvider()
    state = loop_state("cache-layout")
    builder = AgentLLMRequestBuilder()
    state.messages = builder.build_initial_tool_calling_messages(state=state)
    first = builder.build_tool_calling_request(state=state, tools=[])
    state.context.task_state.update({"verified_facts": ["new evidence"]})
    second = builder.build_tool_calling_request(state=state, tools=[])
    sys1, sys2 = provider._serialize_system_prompt(first), provider._serialize_system_prompt(second)
    assert isinstance(sys1, list) and isinstance(sys2, list)
    assert sys1[0] == sys2[0] and "cache_control" in sys1[0]
    assert sys1[1] != sys2[1] and "cache_control" not in sys2[1]
    for tail in (
        LLMMessage(role="assistant", content="", tool_calls=[LLMToolCall(id="call", name="inspect", arguments={"x": 1})], cache_status="cacheable"),
        LLMMessage(role="tool", content="evidence", tool_call_id="call", cache_status="cacheable"),
    ):
        request = replace(second, messages=[*second.messages, tail], cache_policy=LLMPromptCachePolicy(enabled=True, ttl="one_hour"))
        block = provider._serialize_messages(request)[-1]["content"][-1]
        assert block["cache_control"] == {"type": "ephemeral", "ttl": "1h"}
        disabled = replace(request, cache_policy=LLMPromptCachePolicy(enabled=False))
        assert "cache_control" not in str(provider._serialize_messages(disabled))
        assert "cache_control" not in str(provider._serialize_system_prompt(disabled))
    tool = LLMToolDefinition(name="inspect", description="large schema" * 200, input_schema={"type": "object"})
    assert estimate_request_tokens(LLMCompletionRequest(messages=second.messages, tools=[tool])) > estimate_request_tokens(second)
    state.messages.extend(LLMMessage(role="user", content=f"history {i}") for i in range(25))
    state.last_request_input_tokens = 100_000
    builder.build_tool_calling_request(state=state, tools=[])
    assert any(message.cache_segment == "summary" for message in state.messages)


def scenario_models_discovered_from_configured_service() -> None:
    import httpx
    from unittest.mock import patch
    from app.services.model_service import ModelService
    from app.api.schemas.resources import ModelConfigCreate
    from app.services.console_app_service import ConsoleAppService
    from unittest.mock import MagicMock
    from sqlmodel import Session, create_engine
    from app.db.models import ModelConfigRecord
    config = model_config().model_copy(update={"base_url": "https://models.invalid/v1", "api_key": SecretStr("evaluation-key")})
    calls = []
    def respond(request):
        calls.append(request)
        assert request.url.path == "/v1/models"
        assert request.headers["authorization"] == "Bearer evaluation-key"
        if not request.url.params.get("after_id"):
            return httpx.Response(200, json={"data": [{"id": "user-choice-b"}, {"id": "user-choice-a"}], "has_more": True, "last_id": "user-choice-a"})
        return httpx.Response(200, json={"data": [{"id": "user-choice-a"}, {"id": "user-choice-c"}], "has_more": False})
    real_client = httpx.Client
    with patch("app.services.model_service.httpx.Client", side_effect=lambda **kwargs: real_client(transport=httpx.MockTransport(respond), **kwargs)):
        assert ModelService().discover_models(config) == ["user-choice-b", "user-choice-a", "user-choice-c"]
    assert len(calls) == 2
    from app.core.llm.providers.anthropic import AnthropicLLMProvider
    with patch("anthropic.Anthropic") as sdk:
        AnthropicLLMProvider()._get_client(config)
        assert sdk.call_args.kwargs["base_url"] == "https://models.invalid"
    for payload, expected in (
        ({"models": ["custom", "custom"]}, ["custom"]),
        ({"models": []}, []),
        ({"data": [{"id": "available"}]}, ["available"]),
        ({"models": [{"slug": "upstream-model", "visibility": "list", "supported_in_api": True}, {"slug": "internal-model", "visibility": "hide"}, {"slug": "unavailable", "supported_in_api": False}]}, ["upstream-model"]),
    ):
        with patch("app.services.model_service.httpx.Client", side_effect=lambda **kwargs: real_client(transport=httpx.MockTransport(lambda _: httpx.Response(200, json=payload)), **kwargs)):
            assert ModelService().discover_models(config) == expected
    with patch("app.services.model_service.httpx.Client", side_effect=lambda **kwargs: real_client(transport=httpx.MockTransport(lambda _: httpx.Response(401, json={"error": "evaluation-key"})), **kwargs)):
        try:
            ModelService().discover_models(config)
        except ValueError as error:
            assert "鉴权失败" in str(error) and "evaluation-key" not in str(error)
        else:
            raise AssertionError("Discovery silently used a preset after failure")
    payload = ModelConfigCreate(base_url="https://models.invalid", api_key=SecretStr("evaluation-key"))
    assert payload.model_name == "" and payload.name == "API 服务"
    with TemporaryDirectory() as tmp:
        engine = create_engine(f"sqlite:///{Path(tmp) / 'models.db'}")
        ModelConfigRecord.__table__.create(engine)
        with Session(engine) as session:
            session.add(ModelConfigRecord(name="legacy", provider="anthropic", base_url="https://wrong.invalid", api_key_encryption_version="evaluation", encrypted_api_key="unused", model_name="user-choice-b", is_default=False))
            session.commit()
            service = ConsoleAppService()
            with patch.object(service._model_service, "load_settings", return_value=config):
                resolved = service.resolve_model_config(session, "user-choice-b")
            assert resolved.base_url == config.base_url and resolved.model_name == "user-choice-b"
            import importlib
            from app.api.schemas.resources import ModelDiscoveryRequest
            api = importlib.import_module("app.api.models")
            with patch.object(ModelService, "encrypt_api_key", return_value=("evaluation", "encrypted-placeholder")), patch.object(ModelService, "decrypt_api_key", return_value=SecretStr("evaluation-key")), patch("app.services.model_service.httpx.Client", side_effect=lambda **kwargs: real_client(transport=httpx.MockTransport(respond), **kwargs)):
                saved = api.create_model_config_record(payload, session)
                assert saved.is_default and saved.model_name == "" and saved.api_key_masked != "evaluation-key"
                available = api.list_models(session)
                assert available.available_models == ["user-choice-b", "user-choice-a", "user-choice-c"]
                assert available.selected_model == ""
                discovered = api.discover_model_configs(ModelDiscoveryRequest(config_id=saved.id, base_url=payload.base_url), session)
                assert discovered.models == available.available_models
                resolved = service.resolve_model_config(session, "user-choice-c")
                assert resolved.base_url == payload.base_url and resolved.model_name == "user-choice-c"
                assert api.list_models(session).selected_model == "user-choice-c"
        engine.dispose()


def scenario_background_knowledge_files() -> None:
    from threading import Event
    from unittest.mock import Mock, patch
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    import importlib
    from app.services.knowledge_document_store import KnowledgeDocumentStore
    from app.services.knowledge_extraction_service import KnowledgeExtractionService
    from app.services.knowledge_models import KnowledgeDraft, KnowledgeExtractionJob, KnowledgeSearchFilters
    from app.services.knowledge_search_index import KnowledgeSearchIndex
    from app.services.knowledge_service import KnowledgeService, KnowledgeDraftGenerationError, KnowledgeDraftParseError
    from app.services.redaction_service import RedactionService
    from app.utils.file_store import atomic_write_json

    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        conversation = SimpleNamespace(id="conv_eval", title="网络与磁盘排障", updated_at="2026-09-22", events=[
            {"id": "e1", "kind": "user", "text": "网络排障；password=evaluation-password"},
            {"id": "e2", "kind": "message", "type": "say", "say": "tool_use", "partial": False, "toolCall": {"command": "ip route"}, "toolOutput": "default via 10.0.0.1", "exitCode": 0},
            {"id": "e3", "kind": "message", "type": "say", "say": "text", "partial": False, "text": "磁盘告警需要检查容量，当前尚未执行清理。"},
        ])
        conversations = Mock()
        conversations.get_conversation.return_value = conversation
        model = Mock()
        model.generate_embedding.side_effect = ValueError("No embedding endpoint")
        store = KnowledgeDocumentStore(root)
        service = KnowledgeService(conversations, model, RedactionService(), store, KnowledgeSearchIndex(root / "index.sqlite"))
        started, release = Event(), Event()
        def plan(document, existing, **kwargs):
            assert "evaluation-password" not in document
            assert "default via 10.0.0.1" in document and "ip route" in document and "尚未执行清理" in document
            assert json.loads(existing) == []
            started.set()
            assert release.wait(10)
            return json.dumps({"actions": [
                {"action": "create", "draft": {"title": "网络默认路由", "summary": "确认默认路由网关", "resolution": "网关为 10.0.0.1"}},
                {"action": "create", "draft": {"title": "磁盘容量诊断", "summary": "磁盘告警需先核对容量，未执行清理"}},
            ]})
        model.plan_knowledge_extraction.side_effect = plan
        manager = KnowledgeExtractionService(service, root / "extractions")
        api = importlib.import_module("app.api.knowledge")
        app = FastAPI()
        app.include_router(api.router)
        try:
            with patch.object(api, "get_knowledge_service", return_value=service), patch.object(api, "get_knowledge_extraction_service", return_value=manager), TestClient(app) as client:
                response = client.post("/api/knowledge/extractions/conv_eval", json={})
                assert response.status_code == 202
                job_id = response.json()["id"]
                assert started.wait(5)
                again = client.post("/api/knowledge/extractions/conv_eval", json={})
                assert again.json()["id"] == job_id
                assert client.get("/api/knowledge/extractions/conv_eval").json()["job"]["status"] == "running"
                release.set()
                manager.close()
                status = client.get("/api/knowledge/extractions/conv_eval").json()
                assert status["job"]["status"] == "succeeded" and len(status["entries"]) == 2
                assert len(status["job"]["created_ids"]) == 2
                entry_id = status["entries"][0]["id"]
                assert client.get(f"/api/knowledge/{entry_id}/markdown").status_code == 200
        finally:
            release.set()
            manager.close()
        entries = service.linked_entries(conversation.id)
        assert len(list((root / "entries").glob("*.md"))) == 2
        assert service.search(KnowledgeSearchFilters(sourceConversationId=conversation.id)).total == 2
        assert service.reindex().indexed == 2
        network = next(entry for entry in entries if entry.title == "网络默认路由")
        disk = next(entry for entry in entries if entry.title == "磁盘容量诊断")
        def update_plan(document, existing, **kwargs):
            assert network.id in existing and disk.id in existing
            return json.dumps({"actions": [
                {"action": "update", "entry_id": network.id, "draft": {"title": network.title, "summary": "确认默认路由网关", "resolution": "网关为 10.0.0.1；新增邻居检查步骤"}},
                {"action": "keep", "entry_id": disk.id},
            ]})
        model.plan_knowledge_extraction.side_effect = update_plan
        document, source = service.extraction_source(conversation.id, 120)
        service.extract_and_save(document, source)
        assert len(store.list()) == 2 and "新增邻居" in service.get_entry(network.id).resolution
        assert service.get_entry(network.id).created_at == network.created_at
        # A second conversation can reuse the file without removing its first source.
        source = source.model_copy(update={"id": "conv_second"})
        model.plan_knowledge_extraction.side_effect = lambda *args, **kwargs: json.dumps({"actions": [{"action": "keep", "entry_id": network.id}]})
        service.extract_and_save(document, source)
        assert len(service.linked_entries("conv_second")) == 1
        assert service.get_entry(network.id).source_conversation.id == conversation.id
        assert service.search(KnowledgeSearchFilters(sourceConversationId="conv_second")).total == 1
        # Invalid actions must not partially create a file before discovering an invalid update.
        model.plan_knowledge_extraction.side_effect = lambda *args, **kwargs: json.dumps({"actions": [
            {"action": "create", "draft": {"title": "不应创建", "summary": "无效计划"}},
            {"action": "update", "entry_id": "kb_missing", "draft": {"title": "无效", "summary": "无效"}},
        ]})
        try:
            service.extract_and_save(document, source)
        except KnowledgeDraftParseError:
            pass
        else:
            raise AssertionError("Invalid plan should fail")
        assert len(store.list()) == 2
        # Concurrent manual edits win over stale AI plans.
        def conflicting_plan(*args, **kwargs):
            service.update_entry(network.id, KnowledgeDraft(title=network.title, summary="人工修改"), network.source_conversation)
            return json.dumps({"actions": [{"action": "update", "entry_id": network.id, "draft": {"title": network.title, "summary": "旧 AI 输出"}}]})
        model.plan_knowledge_extraction.side_effect = conflicting_plan
        try:
            service.extract_and_save(document, source)
        except KnowledgeDraftGenerationError:
            pass
        else:
            raise AssertionError("Stale plan overwrote manual changes")
        assert service.get_entry(network.id).summary == "人工修改"
        pending = KnowledgeExtractionJob(id="extract_pending", conversation_id="interrupted", status="running", created_at="2026-09-22", updated_at="2026-09-22")
        atomic_write_json(root / "extractions" / "extract_pending.json", pending.model_dump())
        restored = KnowledgeExtractionService(service, root / "extractions")
        assert restored.latest(conversation.id).status == "succeeded"
        assert restored.latest("interrupted").status == "failed"
        restored.close()
        # The newest facts must be included when the conversation exceeds the source event limit.
        conversation.events = [{"kind": "assistant", "text": f"fact-{i}"} for i in range(150)]
        document, _ = service.extraction_source(conversation.id, 2)
        assert "fact-149" in document and "fact-148" in document and "fact-0\n" not in document


def scenario_knowledge_versions_incremental_recovery() -> None:
    import hashlib
    import importlib
    from unittest.mock import Mock, patch
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.services.knowledge_document_store import KnowledgeDocumentStore
    from app.services.knowledge_extraction_service import KnowledgeExtractionService
    from app.services.knowledge_models import KnowledgeDraft, KnowledgeExtractionTask
    from app.services.knowledge_search_index import KnowledgeSearchIndex
    from app.services.knowledge_service import KnowledgeService, KnowledgeIndexUpdateError
    from app.services.redaction_service import RedactionService
    from app.utils.file_store import atomic_write_json

    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        conversation = SimpleNamespace(id='conv_incremental', title='增量路由排查', updated_at='2026-09-22', events=[
            {'kind': 'user', 'id': f'e{i}', 'text': f'路由排查证据 {i}'} for i in range(5)
        ])
        conversations = Mock()
        conversations.get_conversation.return_value = conversation
        model = Mock()
        model.generate_embedding.side_effect = ValueError('not supported')
        store = KnowledgeDocumentStore(root)
        index = KnowledgeSearchIndex(root / 'index.sqlite')
        service = KnowledgeService(conversations, model, RedactionService(), store, index)
        calls: list[str] = []
        def plan(document, documents, **kwargs):
            calls.append(document)
            existing = json.loads(documents)
            if not existing:
                return json.dumps({'actions': [{'action': 'create', 'draft': {'title': '路由排查知识', 'summary': '默认路由检查'}}]})
            return json.dumps({'actions': [{'action': 'keep', 'entry_id': existing[0]['id']}]})
        model.plan_knowledge_extraction.side_effect = plan
        manager = KnowledgeExtractionService(service, root / 'extractions')
        manager.submit(conversation.id, max_source_events=2)
        manager.close()
        completed = manager.latest(conversation.id)
        assert completed.status == 'succeeded' and completed.completed_batches == 3
        assert len(calls) == 3 and len(store.list()) == 1
        assert all(f'路由排查证据 {i}' in '\n'.join(calls) for i in range(5))
        # An unchanged conversation costs zero additional model requests.
        manager = KnowledgeExtractionService(service, root / 'extractions')
        unchanged = manager.submit(conversation.id)
        assert unchanged.status == 'succeeded' and unchanged.total_batches == 0
        manager.close()
        assert len(calls) == 3
        # Only appended evidence is sent, and edited evidence is detected too.
        conversation.events.append({'kind': 'message', 'type': 'say', 'id': 'e5', 'text': '新增路由证据', 'partial': False})
        manager = KnowledgeExtractionService(service, root / 'extractions')
        manager.submit(conversation.id)
        manager.close()
        assert len(calls) == 4 and '新增路由证据' in calls[-1] and '路由排查证据 0' not in calls[-1]
        conversation.events[-1]['text'] = '修正后的路由证据'
        batches, source = service.extraction_batches(conversation.id)
        assert len(batches) == 1 and '修正后的路由证据' in batches[0].document
        # A receipt survived but the task cursor did not: resume without calling the model again.
        service.extract_and_save(batches[0].document, source, batch_key=batches[0].key, fingerprints=batches[0].fingerprints)
        before = len(calls)
        task = KnowledgeExtractionTask(id='extract_resume', conversation_id=conversation.id, status='running', created_at='2099-01-01', updated_at='2099-01-01', batches=batches, source=source, total_batches=1)
        atomic_write_json(root / 'extractions' / 'extract_resume.json', task.model_dump())
        manager = KnowledgeExtractionService(service, root / 'extractions')
        manager.close()
        assert manager.latest(conversation.id).status == 'succeeded' and len(calls) == before
        # Long individual events must be split, not silently truncated to 700 characters.
        conversation.events.append({'kind': 'message', 'id': 'long', 'text': '长记录' * 12000 + '结尾证据', 'partial': False})
        batches, source = service.extraction_batches(conversation.id)
        assert len(batches) >= 2 and '结尾证据' in batches[-1].document
        assert all(len(batch.document) < 24000 for batch in batches)
        # Historical interrupted messages must not block later completed evidence.
        conversation.events = [{'kind': 'message', 'text': '未完成', 'partial': True}, {'kind': 'user', 'text': '完整新消息'}]
        batches, _ = service.extraction_batches(conversation.id)
        assert '完整新消息' in batches[0].document

        entry = store.list()[0]
        updated = service.update_entry(entry.id, KnowledgeDraft(title=entry.title, summary='新版：补充邻居检查'), entry.source_conversation)
        versions = service.versions(entry.id)
        assert versions and '默认路由检查' in service.version_preview(entry.id, versions[0]['id'])['markdown']
        api = importlib.import_module('app.api.knowledge')
        app = FastAPI(); app.include_router(api.router)
        with patch.object(api, 'get_knowledge_service', return_value=service), TestClient(app) as client:
            version_id = client.get(f'/api/knowledge/{entry.id}/versions').json()[0]['id']
            preview = client.get(f'/api/knowledge/{entry.id}/versions/{version_id}').json()
            assert '新版：补充邻居检查' in preview['diff'] and '默认路由检查' in preview['diff']
            restored = client.post(f'/api/knowledge/{entry.id}/versions/{version_id}/restore', json={'expectedUpdatedAt': updated.updated_at})
            assert restored.status_code == 200 and restored.json()['summary'] == '默认路由检查'
            assert len(service.versions(entry.id)) == 2
            stale = client.post(f'/api/knowledge/{entry.id}/versions/{version_id}/restore', json={'expectedUpdatedAt': updated.updated_at})
            assert stale.status_code == 409
            assert client.get(f'/api/knowledge/{entry.id}/versions/invalid').status_code == 404

        # Failure on the second file rolls back the whole batch, including the first update.
        before = service.get_entry(entry.id)
        model.plan_knowledge_extraction.side_effect = lambda *args, **kwargs: json.dumps({'actions': [
            {'action': 'update', 'entry_id': entry.id, 'draft': {'title': entry.title, 'summary': '不应部分写入'}},
            {'action': 'create', 'draft': {'title': '新路由知识', 'summary': '新路由检查'}},
        ]})
        key = hashlib.sha256(b'rollback-batch').hexdigest()
        original_index = index.index_entry
        counter = 0
        def failing_index(item, embedding):
            nonlocal counter
            counter += 1
            if counter == 2:
                raise RuntimeError('simulated index outage')
            return original_index(item, embedding)
        try:
            with patch.object(index, 'index_entry', side_effect=failing_index):
                service.extract_and_save('路由排查', source, batch_key=key, fingerprints=['rollback'])
        except KnowledgeIndexUpdateError:
            pass
        else:
            raise AssertionError('Expected simulated failure')
        assert service.get_entry(entry.id).model_dump() == before.model_dump()
        assert len(store.list()) == 1 and store.receipt(key) is None
        assert not list((root / 'pending_batches').glob('*.json'))
        # Recover a hard process crash before commit by replaying the durable rollback journal.
        journal_key = hashlib.sha256(b'crashed-batch').hexdigest()
        atomic_write_json(root / 'pending_batches' / f'{journal_key}.json', {entry.id: before.model_dump(by_alias=True)})
        service.update_entry(entry.id, KnowledgeDraft(title=entry.title, summary='崩溃时部分写入'), source)
        service.recover_extraction_batches()
        assert service.get_entry(entry.id).summary == before.summary


def scenario_knowledge_automatic_replanning() -> None:
    from unittest.mock import Mock, patch
    from app.services.knowledge_document_store import KnowledgeDocumentStore
    from app.services.knowledge_extraction_service import KnowledgeExtractionService
    from app.services.knowledge_models import KnowledgeDraft, KnowledgeSourceConversation
    from app.services.knowledge_search_index import KnowledgeSearchIndex
    from app.services.knowledge_service import KnowledgeService
    from app.services.redaction_service import RedactionService

    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        conversation = SimpleNamespace(id='conv_retry', title='路由排查', updated_at='2026-09-22', events=[{'kind': 'user', 'text': '路由检查补充证据'}])
        conversations = Mock(); conversations.get_conversation.return_value = conversation
        model = Mock(); model.generate_embedding.side_effect = ValueError('unavailable')
        store = KnowledgeDocumentStore(root)
        service = KnowledgeService(conversations, model, RedactionService(), store, KnowledgeSearchIndex(root / 'index.sqlite'))
        old = service.create_entry(KnowledgeDraft(title='默认路由', summary='原有有效知识'), KnowledgeSourceConversation(id='older'))
        counter = 0
        feedbacks = []
        def replan(document, documents, **kwargs):
            nonlocal counter
            counter += 1
            feedbacks.append(kwargs.get('feedback'))
            if counter == 1:
                return '{invalid json'
            if counter == 2:
                return json.dumps({'actions': [{'action': 'create', 'draft': {'title': '默认路由', 'summary': '新增证据'}}]})
            if counter == 3:
                service.update_entry(old.id, KnowledgeDraft(title=old.title, summary='人工补充的有效知识'), old.source_conversation)
                return json.dumps({'actions': [{'action': 'update', 'entry_id': old.id, 'draft': {'title': old.title, 'summary': '过期计划'}}]})
            assert '人工补充的有效知识' in documents
            return json.dumps({'actions': [{'action': 'update', 'entry_id': old.id, 'draft': {'title': old.title, 'summary': '人工补充的有效知识；合并新增证据'}}]})
        model.plan_knowledge_extraction.side_effect = replan
        manager = KnowledgeExtractionService(service, root / 'extractions')
        manager.submit(conversation.id); manager.close()
        job = manager.latest(conversation.id)
        assert job.status == 'succeeded' and job.retry_count == 3 and counter == 4
        assert all(feedbacks[1:]) and len(store.list()) == 1
        assert service.get_entry(old.id).summary == '人工补充的有效知识；合并新增证据'
        # Authentication errors are permanent: no retry loop and no checkpoint advance.
        class AuthenticationFailure(Exception):
            status_code = 401
        conversation.events.append({'kind': 'user', 'text': '需要新一轮路由检查'})
        model.plan_knowledge_extraction.reset_mock()
        model.plan_knowledge_extraction.side_effect = AuthenticationFailure('private upstream body')
        manager = KnowledgeExtractionService(service, root / 'extractions')
        manager.submit(conversation.id); manager.close()
        job = manager.latest(conversation.id)
        assert job.status == 'failed' and job.completed_batches == 0 and job.retry_count == 0
        assert model.plan_knowledge_extraction.call_count == 1 and 'private upstream body' not in job.error
        # Bounded transient retry succeeds without sleeping in tests.
        model.plan_knowledge_extraction.side_effect = [TimeoutError(), json.dumps({'actions': []})]
        with patch('app.services.knowledge_extraction_service.sleep'):
            manager = KnowledgeExtractionService(service, root / 'extractions')
            manager.submit(conversation.id); manager.close()
        assert manager.latest(conversation.id).status == 'succeeded' and manager.latest(conversation.id).retry_count == 1


def main() -> int:
    scenarios: list[tuple[str, Callable[[], None]]] = [
        ("knowledge_versions_incremental_recovery", scenario_knowledge_versions_incremental_recovery),
        ("knowledge_automatic_replanning", scenario_knowledge_automatic_replanning),
        ("background_knowledge_files", scenario_background_knowledge_files),
        ("models_discovered_from_configured_service", scenario_models_discovered_from_configured_service),
        ("prompt_cache_breakpoints_and_budget", scenario_prompt_cache_breakpoints_and_budget),
        ("failed_terminal_connection_resumes_guidance", scenario_failed_terminal_connection_resumes_guidance),
        ("model_retry_stream_errors_and_truncated_responses", scenario_model_retry_stream_errors_and_truncated_responses),
        ("model_retry_uses_real_sdk_without_nested_retries", scenario_model_retry_uses_real_sdk_without_nested_retries),
        ("model_retry_after_approval_does_not_repeat_tool", scenario_model_retry_after_approval_does_not_repeat_tool),
        ("model_retry_limits_and_permanent_errors", scenario_model_retry_limits_and_permanent_errors),
        ("model_retry_does_not_replay_partial_stream", scenario_model_retry_does_not_replay_partial_stream),
        ("model_retry_wait_can_be_cancelled", scenario_model_retry_wait_can_be_cancelled),
        ("unbound_conversation_does_not_bind_on_send", scenario_unbound_conversation_does_not_bind_on_send),
        ("unbound_api_ignores_stale_terminal_selection", scenario_unbound_api_ignores_stale_terminal_selection),
        ("unbound_runtime_has_no_initial_authorization", scenario_unbound_runtime_has_no_initial_authorization),
        ("removed_discovery_mode_keeps_history_readable", scenario_removed_discovery_mode_keeps_history_readable),
        ("prompt_composition_preserves_boundaries", scenario_prompt_composition_preserves_boundaries),
        ("auxiliary_generation_uses_default_model", scenario_auxiliary_generation_uses_default_model),
        ("cc_switch_is_the_only_active_provider", scenario_cc_switch_is_the_only_active_provider),
        ("followup_resume_and_hidden_reasoning", scenario_followup_resume_and_hidden_reasoning),
        ("runtime_steering_preempts_unstarted_tool", scenario_runtime_steering_preempts_unstarted_tool),
        ("tool_failure_can_be_recovered", scenario_tool_failure_can_be_recovered),
        ("approval_guidance_reaches_continuation", scenario_approval_guidance_reaches_continuation),
        ("semantic_task_state_round_trip", scenario_semantic_task_state_round_trip),
        ("unverified_execution_claim_is_rejected", scenario_unverified_execution_claim_is_rejected),
        ("cross_asset_discovery_requires_approval", scenario_cross_asset_discovery_requires_approval),
        ("approval_rechecks_terminal_consistency", scenario_approval_rechecks_terminal_consistency),
    ]
    original_provider_factory = agent_loop_module.build_llm_provider
    results: list[dict[str, str]] = []
    try:
        for name, scenario in scenarios:
            try:
                scenario()
            except Exception as exc:
                results.append({"name": name, "status": "failed", "error": str(exc)})
            else:
                results.append({"name": name, "status": "passed"})
    finally:
        agent_loop_module.build_llm_provider = original_provider_factory

    passed = sum(result["status"] == "passed" for result in results)
    report = {
        "suite": "agent-dialogue",
        "passed": passed,
        "total": len(results),
        "status": "passed" if passed == len(results) else "failed",
        "scenarios": results,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    sys.exit(main())
