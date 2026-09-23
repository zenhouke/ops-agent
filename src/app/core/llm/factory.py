from app.core.llm.cc_switch import require_cc_switch
from app.shared.schemas import ModelConfig


def build_llm_provider(config: ModelConfig):
    require_cc_switch(config.provider)
    from app.core.llm.providers.anthropic import AnthropicLLMProvider

    return AnthropicLLMProvider()
