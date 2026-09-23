from __future__ import annotations

import json

from app.core.prompts.defaults import DEFAULT_PROMPTS

from app.core.prompts.context import AgentPromptContext


def build_skill_index_prompt(ctx: AgentPromptContext) -> str:
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


def build_manual_skill_system_prompt(ctx: AgentPromptContext) -> str:
    if not ctx.loaded_skill_name or not ctx.manual_skill_content:
        return ""
    return (
        f"Loaded skill for this runtime: {ctx.loaded_skill_name}\n"
        "These instructions apply only to the current runtime and must not be treated as persisted conversation history.\n\n"
        f"{ctx.manual_skill_content}"
    )


def build_tool_calling_system_prompt(ctx: AgentPromptContext) -> str:
    agent_instruction = ctx.agent_behavior_prompt.strip() or DEFAULT_PROMPTS["agentBehavior"]
    device_context = f"\nDevice Execution Rules:\n{ctx.device_context}\n" if ctx.device_context else "\n"
    skill_prompt = build_skill_index_prompt(ctx)
    skill_section = f"\n\n{skill_prompt}" if skill_prompt else ""
    authorization_context = f"Initial authorized terminal authorization_id: {ctx.default_authorization_id}\n" if ctx.default_authorization_id else ""
    task_state_context = json.dumps(ctx.task_state.to_payload(), ensure_ascii=False, separators=(",", ":"))
    asset_scope_context = json.dumps(
        {
            "mode": ctx.conversation_scope_mode,
            "primaryAssetId": None if ctx.execution_profile == "unbound" else (ctx.conversation_primary_asset_id if ctx.conversation_primary_asset_id is not None else ctx.asset_id),
            "currentAssetId": None if ctx.execution_profile == "unbound" else ctx.asset_id,
            "allowedAssetIds": ctx.allowed_asset_ids,
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )
    business_sections = [f"Agent behavior:\n{agent_instruction}"]
    if ctx.incident_response_prompt.strip():
        business_sections.append(f"Incident response mode:\n{ctx.incident_response_prompt.strip()}")
    if ctx.organization_rules_prompt.strip():
        business_sections.append(f"Organization rules:\n{ctx.organization_rules_prompt.strip()}")
    business_prompt = "\n\n".join(business_sections)
    return (
        f"Operating System Type: {ctx.os_type}\n"
        f"Current Host Information: {ctx.asset_summary}\n"
        f"{authorization_context}"
        f"Shell: {ctx.shell_type}\n"
        f"Execution Profile: {ctx.execution_profile}{device_context}\n"
        f"Current Task State: {task_state_context}\n"
        f"Conversation Asset Scope: {asset_scope_context}\n"
        f"Configurable operating guidance:\n{business_prompt}\n"
        "Immutable safety and execution rules:\n"
        "The initial/current terminal is already authorized when an authorization_id is provided above; use execute_command with that authorization_id for current-terminal work and do not request a new terminal session for it. "
        "Treat Current Host Information and the initial/current terminal as authoritative for phrases like current system, current host, current machine, or current device. "
        "Prior remote terminal sessions mentioned in conversation history are historical and transient; do not infer the current asset from them. "
        "When Execution Profile is unbound, no device or local host is selected; never assume runtime asset 0 authorizes the console host. "
        "Answer general questions directly. For tasks needing a device, discover candidates from the user's clues and request terminal access before execution; no UI asset selection is required. "
        "Otherwise default to the current selected or already-authorized terminal context. Do not discover assets unnecessarily. "
        "Use list_assets only when the user explicitly asks about assets/hosts or the task cannot reasonably be completed in the current context without choosing a remote asset; every list_assets call must include its schema-required intent and justification. "
        "Never execute against an asset outside allowedAssetIds. A single-asset conversation may REQUEST another asset when the user task requires it, but only explicit user approval of that terminal request expands the conversation scope. Rejection must preserve the original scope. "
        "When the user describes a network outage and does not know the associated device, investigate within this conversation; never ask them to create another task or choose a troubleshooting mode. "
        "The fault server may be unreachable or absent from the catalog. Do not assume the selected terminal is the fault server: compare the stated target to Current Host Information before running commands. "
        "Use list_assets to search the target IP/name and known site/group/gateway clues, paging as needed; if evidence is insufficient, ask for a focused missing clue instead of guessing a device or scanning everything. "
        "Explain evidence for each candidate before requesting its terminal. JumpServer is an access path, not proof of physical topology. "
        "After approval, collect device/interface/neighbors information and use execute_command for vendor-appropriate read-only ARP/ND, MAC, VLAN, routing and interface configuration queries. "
        "Trace IP to MAC at the relevant gateway, then MAC egress and LLDP/CDP to subsequent devices; account for VRFs, VLANs, bonds, virtual machines, overlays and routed hops. Missing table entries are inconclusive. "
        "Record visited devices, command evidence, confirmed links, hypotheses and next steps with update_task_state; resume from that evidence after approvals and avoid repeated unchanged queries. "
        "Diagnose first and propose fixes separately; preserve all connection and command approvals. For ordinary tasks about the selected server, keep using its authorized terminal without unnecessary discovery. "
        "Use request_terminal_session when the user explicitly asks to connect to or operate on a remote asset, or after you have first explained why remote access is required; every request_terminal_session call must include its schema-required intent. "
        "Run commands only through execute_command with an authorization_id. Never treat asset_id or terminal_id as an execution credential. "
        "Before EVERY execute_command call, write a short Chinese explanation in normal assistant text: what you will inspect or change, why, and the expected result; mention impact for mutations. "
        "Then propose the command through the tool, never as a substitute markdown code block. Put explanation first in its arguments, then authorization_id and command. "
        "Every command requires explicit operator approval, including read-only commands and previously trusted commands. A proposed or streaming command has not executed. "
        "Never claim that a command or tool ran unless you called the corresponding tool in this runtime and received its result. Historical command records are context only; never imitate their formatting as if they were a new execution. "
        "Never reveal hidden chain-of-thought; provide conclusions, evidence, and concise progress summaries instead. "
        "Call tools only when the user's request requires action in the current authorized context or explicitly requires remote asset access. "
        "Call update_task_state whenever the goal, scope, constraints, acceptance criteria, verified facts, operator decisions, or open/completed items materially change. "
        "Treat Current Task State as shared working state; the system maintains current_request from operator messages. Never record an unverified hypothesis as a verified fact, and include a concise source reference in every verified fact. "
        "Respond in Chinese unless the user explicitly requests another language."
        f"{skill_section}"
    )
