import os
import sys
from importlib import import_module
from pathlib import Path

ROOT_SRC = Path(__file__).resolve().parents[1]
if str(ROOT_SRC) not in sys.path:
    sys.path.insert(0, str(ROOT_SRC))

from app.shared.config import APP_DIR


def main() -> None:
    APP_DIR.mkdir(parents=True, exist_ok=True)
    host = os.environ.get("OPS_AGENT_HOST", "127.0.0.1")
    port = int(os.environ.get("OPS_AGENT_PORT", os.environ.get("OPS_AGENT_BACKEND_PORT", "8000")))
    default_reload = "false" if getattr(sys, "frozen", False) else "true"
    reload = os.environ.get("OPS_AGENT_RELOAD", default_reload).lower() == "true"
    import_module("uvicorn").run("app.api:app", host=host, port=port, reload=reload)

if __name__ == "__main__":
    main()
