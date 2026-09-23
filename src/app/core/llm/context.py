"""Input budgeting for complete requests; estimates are never billed usage."""
import json
from dataclasses import asdict

from app.core.llm.types import LLMCompletionRequest
from app.shared.schemas import ModelConfig


def context_window_tokens(config: ModelConfig) -> int:
    configured = config.provider_options.get("context_window_tokens")
    if isinstance(configured, int) and not isinstance(configured, bool) and configured > 0:
        return configured
    name = config.model_name.lower()
    return 200_000 if "claude" in name else 128_000 if "gpt-4" in name or "gpt-5" in name else 32_000


def input_budget_tokens(config: ModelConfig) -> int:
    return max(1, context_window_tokens(config) - max(4_000, config.max_tokens))


def estimate_request_tokens(request: LLMCompletionRequest) -> int:
    # Includes system prompts, tool schemas, tool arguments/results and history.
    # The provider's returned usage remains authoritative.
    payload = json.dumps({"messages": [asdict(item) for item in request.messages],
                          "tools": [asdict(item) for item in request.tools]}, ensure_ascii=False)
    return max(1, (len(payload) + 3) // 4)
