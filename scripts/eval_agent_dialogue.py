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
            assert "/var 占用最大" in request.messages[0].content
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


def scenario_single_asset_scope_denies_cross_asset_terminal() -> None:
    state = loop_state("eval-single-asset-scope", "检查当前设备")
    state.context.asset_id = 1
    state.context.conversation_primary_asset_id = 1
    state.context.allowed_asset_ids = [1]
    state.context.conversation_scope_mode = "single"

    class Provider:
        def __init__(self) -> None:
            self.calls = 0

        def stream_complete(self, *, config, request):
            _ = config
            self.calls += 1
            if self.calls == 1:
                yield LLMCompletionChunk(
                    tool_calls=[LLMToolCall(
                        id="terminal-request-1",
                        name="request_terminal_session",
                        arguments={
                            "asset_id": 2,
                            "reason": "尝试访问其他资产",
                            "intent": "remote_execution_required",
                        },
                    )],
                    finish_reason="tool_calls",
                )
                return
            tool_messages = [message.content for message in request.messages if message.role == "tool"]
            assert any('"status":"scope_denied"' in content for content in tool_messages)
            yield LLMCompletionChunk(delta="当前对话不能访问其他资产。", finish_reason="stop")

    provider = Provider()
    agent_loop_module.build_llm_provider = lambda config: provider
    handler = RequestTerminalSessionHandler(None, catalog=None)  # type: ignore[arg-type]
    list(AgentLoop(tools=[handler]).run(state))
    assert provider.calls == 2
    assert state.phase == "completed"
    assert state.context.allowed_asset_ids == [1]


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
    assert "auth-updated" in request.messages[0].content
    assert "auth-original" not in request.messages[0].content
    assert "自定义业务说明" in request.messages[0].content
    assert "Every command requires explicit operator approval" in request.messages[0].content
    assert ctx.organization_rules_prompt in request.messages[0].content
    memory = next(message for message in request.messages if message.cache_segment == "runtime_context")
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
        assert service.discover_models(config) == [DEFAULT_MODEL]
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


def main() -> int:
    scenarios: list[tuple[str, Callable[[], None]]] = [
        ("prompt_composition_preserves_boundaries", scenario_prompt_composition_preserves_boundaries),
        ("auxiliary_generation_uses_default_model", scenario_auxiliary_generation_uses_default_model),
        ("cc_switch_is_the_only_active_provider", scenario_cc_switch_is_the_only_active_provider),
        ("followup_resume_and_hidden_reasoning", scenario_followup_resume_and_hidden_reasoning),
        ("runtime_steering_preempts_unstarted_tool", scenario_runtime_steering_preempts_unstarted_tool),
        ("tool_failure_can_be_recovered", scenario_tool_failure_can_be_recovered),
        ("approval_guidance_reaches_continuation", scenario_approval_guidance_reaches_continuation),
        ("semantic_task_state_round_trip", scenario_semantic_task_state_round_trip),
        ("unverified_execution_claim_is_rejected", scenario_unverified_execution_claim_is_rejected),
        ("single_asset_scope_denies_cross_asset_terminal", scenario_single_asset_scope_denies_cross_asset_terminal),
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
