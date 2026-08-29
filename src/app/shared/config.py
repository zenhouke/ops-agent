import os
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[3]
APP_DIR = Path(os.environ.get("OPS_AGENT_DATA_DIR", PROJECT_ROOT / ".ops-agent"))
DB_PATH = APP_DIR / "ops_agent.db"
SETTINGS_PATH = APP_DIR / "settings.json"
PROMPT_SETTINGS_PATH = APP_DIR / "prompt_settings.json"
PROMPT_SETTINGS_AUDIT_PATH = APP_DIR / "prompt_settings.audit.jsonl"
MCP_SERVERS_PATH = APP_DIR / "mcp_servers.json"
TEST_DB_PATH = APP_DIR / "ops_agent.test.db"
WINDOWS_APP_NAME = "Ops Agent"
WSL_TEST_MODE = True
