from __future__ import annotations

from app.core.loop.loop_state import LoopContext, LoopRuntimeStep


def build_skill_index_prompt(ctx: LoopContext) -> str:
    if not ctx.available_skills:
        return ""
    lines = ["Available skills:"]
    for skill in ctx.available_skills:
        name = skill.get("name", "").strip()
        description = skill.get("description", "").strip()
        if name and description:
            lines.append(f"- {name}: {description}")
    if len(lines) == 1:
        return ""
    lines.append("")
    lines.append(
        "If a skill is relevant to the user's task, call load_skill with its name before continuing. "
        "Do not load a skill unless it is useful for the current task. At most one skill may be loaded for this runtime."
    )
    return "\n".join(lines)


def build_planner_skill_index_prompt(ctx: LoopContext) -> str:
    if not ctx.available_skills:
        return ""
    lines = ["Available skills for planning (summaries only):"]
    for skill in ctx.available_skills:
        name = skill.get("name", "").strip()
        description = skill.get("description", "").strip()
        if name and description:
            lines.append(f"- {name}: {description}")
    if len(lines) == 1:
        return ""
    lines.extend(
        [
            "",
            "During JSON plan generation, automatic load_skill calls are not available.",
            "Use these summaries only to account for relevant capabilities at a high level while planning.",
            "Do not include skill bodies, tool calls, or commands in the plan.",
            "A skill may already be manually selected for this runtime, and a relevant skill can be loaded later during plan-step execution.",
        ]
    )
    return "\n".join(lines)


def build_manual_skill_system_prompt(ctx: LoopContext) -> str:
    if not ctx.loaded_skill_name or not ctx.manual_skill_content:
        return ""
    return (
        f"Loaded skill for this runtime: {ctx.loaded_skill_name}\n"
        "These instructions apply only to the current runtime and must not be treated as persisted conversation history.\n\n"
        f"{ctx.manual_skill_content}"
    )


def build_plan_step_system_prompt(ctx: LoopContext) -> str:
    device_context = f"\n\n设备执行规则:\n{ctx.device_context}" if ctx.device_context else ""
    skill_prompt = build_skill_index_prompt(ctx)
    skill_section = f"\n\n{skill_prompt}" if skill_prompt else ""
    authorization_context = ""
    if ctx.default_authorization_id:
        authorization_context += f"Initial authorized terminal authorization_id: {ctx.default_authorization_id}\n"
    if ctx.terminal_id:
        authorization_context += f"Initial authorized terminal terminal_id: {ctx.terminal_id}\n"
    return (
        f"Operating System Type: {ctx.os_type}\n"
        f"Current Host Information: {ctx.asset_summary}\n"
        f"{authorization_context}"
        f"Shell: {ctx.shell_type}\n"
        f"Execution Profile: {ctx.execution_profile}{device_context}\n\n"
        "You are an operations assistant executing a single plan step. "
        "The initial/current terminal is already authorized when an authorization_id is provided above; use execute_command with that authorization_id and the matching terminal_id for current-terminal work and do not request a new terminal session for it. "
        "Treat Current Host Information and the initial/current terminal as authoritative for phrases like current system, current host, current machine, or current device. "
        "Prior remote terminal sessions mentioned in conversation history are historical and transient; do not infer the current asset from them. "
        "Default to the current selected or already-authorized terminal context. Do not discover assets by default. "
        "Use list_assets only when the original task or current step explicitly requires choosing a remote asset; include its schema-required intent and justification. "
        "Use request_terminal_session only when remote asset access is explicitly required by the task or step, or when you first explain why the current task needs that remote asset; include its schema-required intent. "
        "Run commands only with execute_command using both an authorization_id and its matching terminal_id so the target terminal is explicit. Never treat asset_id or terminal_id as execution credentials. "
        "Operational plan steps require live evidence: before summarizing a step that inspects or changes the host, call execute_command on the authorized terminal and base the summary on the command output. "
        "Prioritize completing the current step, and provide a brief summary only after the required evidence has been collected. "
        "Respond in Chinese unless the user explicitly requests another language."
        f"{skill_section}"
    )


def build_plan_step_user_prompt(ctx: LoopContext, step: LoopRuntimeStep) -> str:
    return (
        f"Original Task: {ctx.user_prompt}\n"
        f"Current Step Title: {step.title}\n"
        f"Current Step Reason: {step.reason}\n"
        f"Recommended Working Directory: {step.working_directory or 'Not specified'}\n"
        f"Expected Output: {step.expected_output or 'Not specified'}\n"
        "Please execute around the current step, adjust parameters if necessary, but do not deviate from the step goal."
    )


def build_tool_calling_system_prompt(ctx: LoopContext) -> str:
    mode_instruction = (
        "You are a cautious operations assistant. You can use the provided tools to perform actions. The system will automatically determine if an action can be executed directly based on policies."
        if ctx.mode == "plan"
        else "You are an autonomous operations assistant. You can use the provided tools to perform actions. The system will automatically determine if an action can be executed directly based on policies."
    )
    device_context = f"\nDevice Execution Rules:\n{ctx.device_context}\n" if ctx.device_context else "\n"
    skill_prompt = build_skill_index_prompt(ctx)
    skill_section = f"\n\n{skill_prompt}" if skill_prompt else ""
    authorization_context = ""
    if ctx.default_authorization_id:
        authorization_context += f"Initial authorized terminal authorization_id: {ctx.default_authorization_id}\n"
    if ctx.terminal_id:
        authorization_context += f"Initial authorized terminal terminal_id: {ctx.terminal_id}\n"
    return (
        f"Operating System Type: {ctx.os_type}\n"
        f"Current Host Information: {ctx.asset_summary}\n"
        f"{authorization_context}"
        f"Shell: {ctx.shell_type}\n"
        f"Execution Profile: {ctx.execution_profile}{device_context}\n"
        "Rules: " + mode_instruction + "\n"
        "The initial/current terminal is already authorized when an authorization_id is provided above; use execute_command with that authorization_id and the matching terminal_id for current-terminal work and do not request a new terminal session for it. "
        "Treat Current Host Information and the initial/current terminal as authoritative for phrases like current system, current host, current machine, or current device. "
        "Prior remote terminal sessions mentioned in conversation history are historical and transient; do not infer the current asset from them. "
        "Default to the current selected or already-authorized terminal context. Do not discover assets by default. "
        "Use list_assets only when the user explicitly asks about assets/hosts or the task cannot reasonably be completed in the current context without choosing a remote asset; every list_assets call must include its schema-required intent and justification. "
        "Use request_terminal_session only when the user explicitly asks to connect to or operate on a remote asset, or after you have first explained why remote access is required; every request_terminal_session call must include its schema-required intent. "
        "Run commands only through execute_command with both an authorization_id and its matching terminal_id so the target terminal is explicit. Never treat asset_id or terminal_id as an execution credential. "
        "Call tools only when the user's request requires action in the current authorized context or explicitly requires remote asset access. "
        "Respond in Chinese unless the user explicitly requests another language."
        f"{skill_section}"
    )
