from __future__ import annotations

from app.core.loop.loop_state import LoopPhase, LoopState


class RuntimeStateTransitionError(RuntimeError):
    """Raised when a runtime attempts an invalid or incomplete phase transition."""


_ALLOWED_TRANSITIONS: dict[LoopPhase, frozenset[LoopPhase]] = {
    "executing": frozenset({
        "approving",
        "waiting_terminal_approval",
        "waiting_user_input",
        "completed",
        "failed",
    }),
    "approving": frozenset({"executing", "failed"}),
    "waiting_terminal_approval": frozenset({"executing", "failed"}),
    "waiting_user_input": frozenset({"executing", "failed"}),
    "completed": frozenset(),
    "failed": frozenset(),
}


def runtime_invariant_errors(state: LoopState, phase: LoopPhase | None = None) -> list[str]:
    target = phase or state.phase
    errors: list[str] = []
    if target == "approving":
        required = {
            "pending_tool_call_id": state.pending_tool_call_id,
            "pending_tool_name": state.pending_tool_name,
            "pending_tool_args": state.pending_tool_args,
            "pending_approval_step_id": state.pending_approval_step_id,
            "pending_approval_token": state.pending_approval_token,
            "pending_approval_token_hash": state.pending_approval_token_hash,
        }
        errors.extend(name for name, value in required.items() if value is None)
    elif target == "waiting_user_input" and not state.pending_followup_question:
        errors.append("pending_followup_question")
    elif target in {"completed", "failed"}:
        if state.pending_approval_token is not None:
            errors.append("pending_approval_token")
        if state.pending_approval_token_hash is not None:
            errors.append("pending_approval_token_hash")
    return errors


def transition_runtime_state(
    state: LoopState,
    target: LoopPhase,
    *,
    reason: str | None = None,
) -> None:
    source = state.phase
    if target != source and target not in _ALLOWED_TRANSITIONS[source]:
        detail = f" ({reason})" if reason else ""
        raise RuntimeStateTransitionError(f"Invalid runtime transition: {source} -> {target}{detail}")
    errors = runtime_invariant_errors(state, target)
    if errors:
        detail = f" ({reason})" if reason else ""
        raise RuntimeStateTransitionError(
            f"Runtime invariant failed for {target}: {', '.join(errors)}{detail}"
        )
    state.phase = target


def clear_pending_approval_state(state: LoopState) -> None:
    state.pending_tool_call_id = None
    state.pending_tool_name = None
    state.pending_tool_args = None
    state.pending_message_id = None
    state.pending_approval_token_hash = None
    state.pending_approval_token = None
    state.pending_approval_step_id = None
    state.pending_approval_consistency = None


def fail_runtime_state(state: LoopState, message: str) -> None:
    clear_pending_approval_state(state)
    state.pending_followup_question = None
    state.pending_followup_message_id = None
    state.error_message = message
    transition_runtime_state(state, "failed", reason=message)
