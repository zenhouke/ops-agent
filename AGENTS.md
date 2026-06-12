# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概览

Ops Agent 是一个面向运维场景的 AI 助手控制台，包含 Python FastAPI 后端、React/Vite Web UI 和 Tauri 2 桌面壳。核心交互是：选择资产、打开终端、发起助手运行、人工审批命令、查看流式结果。

## 常用命令

除特别说明外，命令都在仓库根目录执行。

### 初始化

```bash
# 如果是windows：
uv python install 3.13.5 && uv venv .venv --seed && .\venv\Scripts\activate
# 如果是linux\mac:
python -m venv .venv && source .venv/bin/activate

pip install -r requirements.txt
cd web && pnpm install
```

### 开发

```bash
./scripts/run.sh
```

- `./scripts/run.sh` 会同时启动后端和前端，并清理 8000 / 5173 端口上的旧进程。
- 后端默认监听 `127.0.0.1:8000`，前端默认运行在 `http://localhost:5173`。
- 后端可用 `OPS_AGENT_HOST`、`OPS_AGENT_PORT`、`OPS_AGENT_RELOAD` 覆盖。
- Vite 开发服务器会把 `/api` 代理到 `http://127.0.0.1:8000`；浏览器构建可用 `VITE_API_BASE_URL` 改写 API 地址。

### 验证

```bash
source .venv/bin/activate  &&  pyright
cd web && pnpm build
cd web/src-tauri && cargo check
```

- `web/package.json` 没有前端测试或 lint 脚本；前端标准验证是 `pnpm build`。
- 单测只在现有测试文件里选跑，不要为了验证新增测试文件。

### 打包

```bash
./scripts/build_desktop_bundle.sh
./scripts/build_desktop_bundle.sh macos
./scripts/build_desktop_bundle.sh linux
./scripts/build_desktop_bundle.sh windows
```

打包脚本会先装 Python 依赖和 PyInstaller，再把 `src/app/main.py` 构建成 `web/bin/ops-agent-backend*`，最后执行 `pnpm tauri:build`。

## 后端架构

- 入口是 `src/app/main.py`：创建 `.ops-agent/`，读取 `OPS_AGENT_*` 环境变量，启动 Uvicorn 的 `app.api:app`。
- FastAPI 组合在 `src/app/api/__init__.py`：lifespan 里初始化 SQLite schema，并挂载 health、assets、groups、models、SSH keys、terminal、console、conversations、approvals、system 路由。
- 数据层由 `src/app/db/models.py`、`src/app/db/repositories/` 和 `.ops-agent/ops_agent.db` 组成，配置来自 `src/app/shared/config.py`。
- `src/app/services/` 是业务层；路由保持轻薄，资产、模型、凭据、终端、会话逻辑尽量放回现有 service 模块。
- 终端访问围绕 `TerminalService` 和 `src/app/core/connectors/`，包括本地 PTY、SSH/network、serial 和 session 管理；终端流式通信走 `/api/terminal/...` 的 WebSocket。
- 助手执行围绕 `ConsoleAppService`、`LoopRuntimeManager` 和 `AgentLoop`；console run / approval 通过 SSE 从 `/api/console/run` 和 `/api/console/approval` 输出。
- 工具执行走 `ExecuteCommandHandler`；审批状态属于 loop runtime，必须保留“危险命令先人工审批”的链路。
- LLM provider 通过 `build_llm_provider` 选择，当前实现放在 `src/app/core/llm/providers/`。
- 会话历史由 `ConversationService` 持久化，用来重建多轮上下文，不在 SQL 表里直接保存。

## 前端架构

- `web/src/App.tsx` 是控制台 Shell，负责 bootstrap、资产选择、terminal tabs、conversation state、assistant run 和 settings dialog。
- `web/src/api/` 按后端领域拆分；`web/src/api/client.ts` 会优先读 Tauri 提供的 base URL，否则走 `VITE_API_BASE_URL` 或同源 dev proxy。
- `web/src/hooks/console/` 拆分了 bootstrap、资产目录、会话持久化、终端会话和 agent run / approval 流。
- `web/src/components/assistant/` 和 `web/src/components/assistant/conversation/` 消费后端 SSE 事件，渲染 message、command、plan、approval、error 卡片。
- `web/src/components/terminal/` 用 xterm.js + 后端 WebSocket 会话。
- `web/src/components/layout/` 放通用布局组件；设计 token 和 Tailwind 约定在 `web/src/index.css`、`web/tailwind.config.js`。

## 桌面端架构

- `web/src-tauri/tauri.conf.json` 里配置了 `pnpm dev` / `pnpm build` 作为前后端开发和构建入口。
- `web/src-tauri/src/main.rs` 会在 `OPS_AGENT_BACKEND_PORT` 未监听时启动后端；debug 走 `scripts/start_backend_dev.sh`，release 走 Tauri resource 里的 bundled backend binary。
- `backend_base_url` 由 Tauri 暴露，前端在 `web/src/desktop.ts` 消费，所以桌面构建不要硬编码浏览器 API origin。

## 编码规则
- 默认使用中文进行项目思考、协作、说明和回答，除非用户明确要求使用其他语言。
- 使用superpowers技能设计文档的时候需要分析当前代码结构，然后再进行设计。
- 小功能（修改小于200行的代码）使用brainstorming加直接编码就行，不使用整个superpowers技能包。
- 先思考再回答；实现前先明确理解、假设和边界，不要边写边猜。
- 保持改动克制，只改和当前需求直接相关的文件。
- 后端遵循 API Router -> Service -> Repository/Core；前端遵循 Component -> Hook -> API Client；Tauri 只负责桌面进程和运行时。
- 维护人工审批链路。涉及命令执行时，不要绕过审批，也不要把模型输出直接变成执行结果。
- 修改 `AgentLoop`、`MessageManager`、console API 或会话渲染时，保持 SSE 事件结构和前端事件归一化一致。
- 涉及 UI 时，尽量启动对应开发服务并手动验证关键流程；如果无法验证，要说明实际验证了什么。
- 不要依赖 `.venv/`、`web/node_modules/`、`__pycache__/` 或 build output 作为源码。
