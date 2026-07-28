<div align="center">

<img src="web/src/public/logo.png" alt="Ops Agent Logo" width="96" />

# Ops Agent

**English** | [中文](README.zh.md)  

An AI assistant console for controlled operations workflows.

[Quick Start](#quick-start) · [Features](#features) · [Configuration](#configuration) · [Development](#development) · [Desktop](#desktop)

![Python](https://img.shields.io/badge/Python-3.13%2B-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.136-009688?logo=fastapi&logoColor=white)
![React](https://img.shields.io/badge/React-18-61DAFB?logo=react&logoColor=black)
![TypeScript](https://img.shields.io/badge/TypeScript-5-3178C6?logo=typescript&logoColor=white)
![Tauri](https://img.shields.io/badge/Tauri-2-24C8DB?logo=tauri&logoColor=white)

</div>

## What It Solves

Operational work is often split across asset inventories, terminals, model chats, approval trails, and command output. Ops Agent brings those pieces into one console: the AI plans, explains, and iterates; the operator keeps final control over command execution.

```text
Configure model -> Select asset -> Open terminal -> Ask AI -> Review plan -> Approve command -> Execute -> Feed output back
```

## Features

- Asset management for local terminals, Linux hosts, serial devices, and network devices.
- Terminal workspace with local PTY, SSH, serial, and network CLI support.
- AI operations assistant that uses asset, terminal, and conversation context for planning and troubleshooting.
- Human approval before command execution, with traceable decisions, commands, and output.
- Multiple model providers, including Anthropic, OpenAI Compatible, OpenAI Responses, Google Gemini, Azure OpenAI, and common compatible providers.
- MCP and skills support for extending assistant capabilities.
- Web and desktop modes, with Tauri packaging for desktop builds.

## Safety Model

- Default posture: AI suggests; the operator approves.
- Command output, approval decisions, and conversation events are recorded for traceability.
- Secrets should not be logged; production deployments must set `OPS_AGENT_SECRET_KEY`.
- High-risk mutating commands should not be executed automatically.

## Tech Stack

| Layer | Stack |
| --- | --- |
| Backend | Python 3.13+, FastAPI, SQLModel, SQLite, Uvicorn |
| AI / Tools | Anthropic SDK, OpenAI SDK, Google GenAI, MCP, LangGraph, Netmiko, Paramiko |
| Frontend | React 18, TypeScript, Vite, Tailwind CSS, xterm.js |
| Desktop | Tauri 2, Rust |
| Package managers | pip, pnpm |

## Quick Start

### Requirements

- Python 3.13+
- Node.js 22+
- pnpm 11+
- Rust toolchain, only for Tauri desktop development or packaging

### Install Dependencies

Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
cd web
pnpm install
cd ..
```

macOS / Linux / Git Bash:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cd web
pnpm install
cd ..
```

## Configuration

Startup scripts load `.env` from the repository root.

| Variable | Default | Description |
| --- | --- | --- |
| `OPS_AGENT_HOST` | `127.0.0.1` | Backend bind host |
| `OPS_AGENT_PORT` | `8000` | Backend port |
| `OPS_AGENT_RELOAD` | `true` | Enable Uvicorn reload |
| `OPS_AGENT_SECRET_KEY` | none | Required in production for secret encryption |
| `OPS_AGENT_PROVIDER` | `openai_compatible` | Default model provider |
| `OPS_AGENT_MODEL` | provider default | Default model name |
| `OPS_AGENT_BASE_URL` | provider default | Default model base URL |
| `OPS_AGENT_API_KEY` | `demo-key` | Default model API key |
| `OPS_AGENT_TIMEOUT_SECONDS` | `30` | Model request timeout |
| `OPS_AGENT_TEMPERATURE` | `0.2` | Model temperature |
| `OPS_AGENT_MAX_TOKENS` | `2560` | Max model output tokens |
| `OPS_AGENT_PROMPT_CACHE_ENABLED` | `true` | Enable prompt cache |
| `OPS_AGENT_PROMPT_CACHE_TTL` | `ephemeral` | Prompt cache TTL |
| `OPS_AGENT_PWSH_PATH` | auto-detect | Override PowerShell path on Windows |
| `OPS_AGENT_INSTANCE_ID` | hostname | Stable unique worker ID used for runtime ownership |
| `OPS_AGENT_RUNTIME_LEASE_SECONDS` | `300` | Runtime lease duration before another instance may recover it |
| `VITE_API_BASE_URL` | empty | Frontend API base URL; dev mode uses Vite proxy by default |

Operations plugins are declarative JSON manifests. Built-in manifests live in
`src/app/plugins/builtin/`; local manifests can be placed at
`.ops-agent/plugins/<plugin-id>/plugin.json`. Exposed tools are namespaced as
`ops__<plugin>__<tool>` and all plugin commands go through the same terminal
authorization and human approval flow as the built-in command tool.

Local runtime data:

```text
.ops-agent/
├── ops_agent.db
├── settings.json
└── mcp_servers.json
```

## Development

```bash
# Tauri desktop dev
pnpm --dir web tauri:dev

# Tauri desktop build
pnpm --dir web tauri:build
```

## Desktop

The full desktop bundle first builds the backend executable with PyInstaller, then runs the Tauri build.

```bash
./scripts/build_desktop_bundle.sh
./scripts/build_desktop_bundle.sh macos
./scripts/build_desktop_bundle.sh linux
./scripts/build_desktop_bundle.sh windows
```

Notes:

- Build each desktop target on its native platform.
- macOS can build Linux bundles through the script's Docker path.
- Windows bundles must be built on Windows.
- Linux builds require Tauri system dependencies such as `webkit2gtk`, `gtk`, `appindicator`, and `rsvg`.
- Release signing and updater flows require `TAURI_PRIVATE_KEY`, `TAURI_KEY_PASSWORD`, and `TAURI_UPDATER_PUBKEY`.


## Troubleshooting

### Frontend cannot reach backend

In dev mode, `web/vite.config.ts` proxies `/api` to the backend. If `VITE_API_BASE_URL` is set, the frontend uses it first.

### PowerShell blocks activation scripts

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

Then activate `.venv` again or use `scripts\run.bat`.
