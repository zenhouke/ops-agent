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
    handler = RequestTerminalSessionHandler(None)  # type: ignore[arg-type]
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
                        arguments={"authorization_id": "auth-1", "command": "echo safe"},
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


def main() -> int:
    scenarios: list[tuple[str, Callable[[], None]]] = [
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
