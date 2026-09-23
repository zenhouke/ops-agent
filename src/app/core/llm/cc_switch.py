"""CC Switch defaults. Provider denotes its wire protocol, not another vendor."""
from app.shared.enums import ModelProvider

PROVIDER = ModelProvider.ANTHROPIC
DEFAULT_BASE_URL = "http://127.0.0.1:15721"
DEFAULT_MODEL = ""
LOCAL_API_KEY = "cc-switch-local"


def require_cc_switch(provider: ModelProvider) -> None:
    if provider is not PROVIDER:
        raise ValueError("Only the CC Switch Messages route (anthropic protocol) is supported. Update the model configuration.")
