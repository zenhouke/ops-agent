import json
import os
import re
from pathlib import Path
from typing import Any, Literal, cast

from pydantic import SecretStr
from sqlmodel import Session

from app.core.llm.provider_presets import get_default_base_url, get_default_model, is_openai_compatible_provider
from app.core.llm.types import LLMCompletionRequest, LLMMessage
from app.core.llm.factory import build_llm_provider

from app.db.models import ModelConfigRecord
from app.db.repositories.models import list_model_names_by_provider
from app.utils.credential_factory import build_credential_service
from app.services.credential_service import CredentialService
from app.shared import config as shared_config
from app.shared.enums import ModelProvider
from app.shared.schemas import ModelConfig

PromptCacheTTL = Literal["ephemeral", "one_hour"]


class ModelService:
    def __init__(self, provider_client=None, settings_path: Path | None = None):
        self._provider_client = provider_client
        self._settings_path = settings_path or shared_config.SETTINGS_PATH

    
    def validate(self, config: ModelConfig) -> bool:
        if self._provider_client is not None:
            provider = self._provider_client
        else:
            from app.core.llm.factory import build_llm_provider
            provider = build_llm_provider(config)
        try:
            provider.complete(
                config=config,
                request=LLMCompletionRequest(
                    messages=[LLMMessage(role="user", content="Respond with OK.")],
                    temperature=0,
                    max_tokens=16,
                    json_mode=False,
                ),
            )
            return True
        except Exception:
            return False

    def get_active_model(self, default_config: ModelConfig, session_override: ModelConfig | None) -> ModelConfig:
        return session_override or default_config

    def generate_conversation_title(self, prompt: str, *, model_name: str | None = None) -> str:
        try:
            config = self.load_settings()
            if model_name and model_name != config.model_name:
                config = config.model_copy(update={"model_name": model_name})
            provider = self._provider_client or build_llm_provider(config)
            request = LLMCompletionRequest(
                messages=[
                    LLMMessage(
                        role="system",
                        content=(
                            "You are a conversation title generator. Based on the user's first task message, generate a short Chinese title (≤12 characters, no punctuation)."
                        ),
                    ),
                    LLMMessage(role="user", content=prompt.strip()),
                ],
                temperature=0.2,
                max_tokens=32,
                json_mode=False,
            )
            response = provider.complete(config=config, request=request)
            title = (response.text or "").strip()
        except Exception:
            return self._fallback_conversation_title(prompt)
        title = title.splitlines()[0] if title else ""
        title = title.strip().strip("\"'`，。.,；;：:!?！？")
        if len(title) > 16:
            title = title[:16]
        return title or self._fallback_conversation_title(prompt)

    def generate_knowledge_draft(self, source_document: str, *, model_name: str | None = None) -> str:
        config = self.load_settings()
        if model_name and model_name != config.model_name:
            config = config.model_copy(update={"model_name": model_name})
        provider = self._provider_client or build_llm_provider(config)
        max_tokens = config.max_tokens if isinstance(config.max_tokens, int) and config.max_tokens > 0 else 2048
        request = LLMCompletionRequest(
            messages=[
                LLMMessage(
                    role="system",
                    content=(
                        "You convert operations conversations into reusable knowledge drafts. "
                        "Return strict JSON only: one parseable JSON object and no markdown, comments, or extra text. "
                        "The object must contain these fields: title, summary, problem, diagnosis, "
                        "resolution, commands, assets, tags, sources, redactionWarnings. "
                        "commands must be an array of objects with command, purpose, outcome. "
                        "assets must be an array of objects with assetId and label. "
                        "sources must be an array of objects with conversationId, eventId, eventIndex, "
                        "eventType, quote, relevance. Use empty strings or empty arrays when unknown."
                    ),
                ),
                LLMMessage(role="user", content=source_document.strip()),
            ],
            temperature=0.1,
            max_tokens=min(max_tokens, 2048),
            json_mode=True,
        )
        response = provider.complete(config=config, request=request)
        return (response.text or "").strip()

    def generate_embedding(self, text: str) -> list[float]:
        config = self.load_settings()
        if config.provider is ModelProvider.GOOGLE_GEMINI:
            import importlib
            genai = importlib.import_module("google.genai")
            options = config.provider_options or {}
            client_kwargs: dict[str, Any] = {"api_key": config.api_key.get_secret_value()}
            if options.get("vertexai") is True:
                client_kwargs = {
                    "vertexai": True,
                    "project": options.get("project"),
                    "location": options.get("location"),
                }
            elif config.base_url:
                client_kwargs["http_options"] = {"base_url": config.base_url}
            client = genai.Client(**client_kwargs)
            
            # Default embedding model for Gemini
            model = os.environ.get("OPS_AGENT_EMBEDDING_MODEL") or "text-embedding-004"
            response = client.models.embed_content(
                model=model,
                contents=text.strip(),
            )
            
            if hasattr(response, "embeddings") and response.embeddings:
                return list(response.embeddings[0].values)
            elif hasattr(response, "embedding") and response.embedding:
                return list(response.embedding.values)
            raise ValueError("Failed to retrieve embedding values from Gemini response")

        elif config.provider is ModelProvider.ANTHROPIC:
            raise ValueError("Anthropic provider does not support native embeddings. Please configure an OpenAI-compatible or Google Gemini provider.")

        else:
            from openai import OpenAI
            client = OpenAI(
                api_key=config.api_key.get_secret_value(),
                base_url=config.base_url,
                timeout=config.timeout_seconds,
            )
            model = os.environ.get("OPS_AGENT_EMBEDDING_MODEL")
            if not model:
                if "openai" in config.provider.value or "responses" in config.provider.value:
                    model = "text-embedding-3-small"
                else:
                    # Generic default for compatible endpoints (e.g. Ollama, DeepSeek)
                    model = "text-embedding-3-small"
            
            response = client.embeddings.create(
                input=[text.strip()],
                model=model,
            )
            return response.data[0].embedding

    def _fallback_conversation_title(self, prompt: str) -> str:
        text = prompt.strip()
        text = re.sub(r"^(请|麻烦|帮我|你帮我|请帮我|能不能|可以|是否)+", "", text)
        text = re.sub(r"[，。,.；;：:!?！？\s]+", "", text)
        text = re.sub(r"(有啥问题|有什么问题|吗|呢|吧)+$", "", text)
        text = text.replace("一下", "")
        return (text or "新会话")[:12]

    def build_default_config(self) -> ModelConfig:
        provider = ModelProvider(os.environ.get("OPS_AGENT_PROVIDER", ModelProvider.OPENAI_COMPATIBLE.value))
        return ModelConfig(
            provider=provider,
            model_name=os.environ.get("OPS_AGENT_MODEL", get_default_model(provider)),
            base_url=os.environ.get("OPS_AGENT_BASE_URL", get_default_base_url(provider)),
            api_key=SecretStr(os.environ.get("OPS_AGENT_API_KEY", "demo-key")),
            timeout_seconds=int(os.environ.get("OPS_AGENT_TIMEOUT_SECONDS", "30")),
            temperature=float(os.environ.get("OPS_AGENT_TEMPERATURE", "0.2")),
            max_tokens=int(os.environ.get("OPS_AGENT_MAX_TOKENS", "2560")),
            prompt_cache_enabled=os.environ.get("OPS_AGENT_PROMPT_CACHE_ENABLED", "true").lower() != "false",
            prompt_cache_ttl=self._normalize_prompt_cache_ttl(os.environ.get("OPS_AGENT_PROMPT_CACHE_TTL", "ephemeral")),
        )

    def load_settings(self) -> ModelConfig:
        default_config = self.build_default_config()
        if not self._settings_path.exists():
            return default_config
        
        payload = json.loads(self._settings_path.read_text(encoding="utf-8"))
        config = ModelConfig(
            provider=ModelProvider(payload.get("provider", default_config.provider.value)),
            model_name=payload.get("model_name", default_config.model_name),
            base_url=payload.get("base_url", default_config.base_url),
            api_key=SecretStr(payload.get("api_key", default_config.api_key.get_secret_value())),
            timeout_seconds=payload.get("timeout_seconds", default_config.timeout_seconds),
            temperature=payload.get("temperature", default_config.temperature),
            max_tokens=payload.get("max_tokens", default_config.max_tokens),
            prompt_cache_enabled=payload.get("prompt_cache_enabled", default_config.prompt_cache_enabled),
            prompt_cache_ttl=self._normalize_prompt_cache_ttl(payload.get("prompt_cache_ttl", default_config.prompt_cache_ttl)),
            provider_options=payload.get("provider_options") if isinstance(payload.get("provider_options"), dict) else default_config.provider_options,
        )

        # Only override with environment variables if they are explicitly set
        updates = {}
        if os.environ.get("OPS_AGENT_PROVIDER"):
            updates["provider"] = ModelProvider(os.environ["OPS_AGENT_PROVIDER"])
        if os.environ.get("OPS_AGENT_MODEL"):
            updates["model_name"] = os.environ["OPS_AGENT_MODEL"]
        if os.environ.get("OPS_AGENT_BASE_URL"):
            updates["base_url"] = os.environ["OPS_AGENT_BASE_URL"]
        if os.environ.get("OPS_AGENT_API_KEY"):
            updates["api_key"] = SecretStr(os.environ["OPS_AGENT_API_KEY"])
        if os.environ.get("OPS_AGENT_PROMPT_CACHE_ENABLED"):
            updates["prompt_cache_enabled"] = os.environ["OPS_AGENT_PROMPT_CACHE_ENABLED"].lower() != "false"
        if os.environ.get("OPS_AGENT_PROMPT_CACHE_TTL"):
            updates["prompt_cache_ttl"] = self._normalize_prompt_cache_ttl(os.environ["OPS_AGENT_PROMPT_CACHE_TTL"])
            
        if updates:
            config = config.model_copy(update=updates)
            
        return config

    def save_settings(self, config: ModelConfig) -> ModelConfig:
        self._settings_path.parent.mkdir(parents=True, exist_ok=True)
        self._settings_path.write_text(
            json.dumps(
                {
                    "provider": config.provider.value,
                    "model_name": config.model_name,
                    "base_url": config.base_url,
                    "api_key": config.api_key.get_secret_value(),
                    "timeout_seconds": config.timeout_seconds,
                    "temperature": config.temperature,
                    "max_tokens": config.max_tokens,
                    "prompt_cache_enabled": config.prompt_cache_enabled,
                    "prompt_cache_ttl": config.prompt_cache_ttl,
                    "provider_options": config.provider_options,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        return config

    def list_available_models(self, provider: ModelProvider, session: Session | None = None) -> list[str]:
        if session is None:
            return []
        return list_model_names_by_provider(session, provider.value)

    def discover_models(self, config: ModelConfig) -> list[str]:
        if config.provider is ModelProvider.ANTHROPIC:
            return self._discover_anthropic_models(config)
        if config.provider is ModelProvider.GOOGLE_GEMINI:
            return self._discover_google_gemini_models(config)
        if config.provider is ModelProvider.OPENAI_RESPONSES or is_openai_compatible_provider(config.provider):
            return self._discover_openai_style_models(config)
        raise ValueError(f"Unsupported model provider: {config.provider.value}")

    def _discover_openai_style_models(self, config: ModelConfig) -> list[str]:
        from openai import OpenAI

        client = OpenAI(api_key=config.api_key.get_secret_value(), base_url=config.base_url, timeout=config.timeout_seconds)
        try:
            response = client.models.list()
        except Exception as error:
            return self._fallback_discovered_models(config, error)
        models = [model_id for item in getattr(response, "data", []) or [] if isinstance(model_id := getattr(item, "id", None), str) and model_id]
        return sorted(set(models)) or [get_default_model(config.provider)]

    def _discover_anthropic_models(self, config: ModelConfig) -> list[str]:
        from anthropic import Anthropic

        client = Anthropic(api_key=config.api_key.get_secret_value(), base_url=config.base_url, timeout=config.timeout_seconds)
        try:
            response = client.models.list()
        except Exception as error:
            return self._fallback_discovered_models(config, error)
        return self._extract_model_ids(response) or [get_default_model(config.provider)]

    def _discover_google_gemini_models(self, config: ModelConfig) -> list[str]:
        import importlib

        genai = importlib.import_module("google.genai")
        options = config.provider_options or {}
        client_kwargs: dict[str, Any] = {"api_key": config.api_key.get_secret_value()}
        if options.get("vertexai") is True:
            client_kwargs = {
                "vertexai": True,
                "project": options.get("project"),
                "location": options.get("location"),
            }
        elif config.base_url:
            client_kwargs["http_options"] = {"base_url": config.base_url}
        client = genai.Client(**client_kwargs)
        try:
            response = client.models.list()
        except Exception as error:
            return self._fallback_discovered_models(config, error)
        return self._extract_model_ids(response) or [get_default_model(config.provider)]

    def _fallback_discovered_models(self, config: ModelConfig, error: Exception) -> list[str]:
        status_code = getattr(error, "status_code", None)
        if status_code == 404 or "404" in str(error):
            return [get_default_model(config.provider)]
        raise error

    def _extract_model_ids(self, response: Any) -> list[str]:
        data = getattr(response, "data", response)
        models: list[str] = []
        for item in data or []:
            model_id = getattr(item, "id", None) or getattr(item, "name", None)
            if isinstance(model_id, str) and model_id:
                models.append(model_id)
        return sorted(set(models))

    def encrypt_api_key(self, api_key: SecretStr) -> tuple[str, str]:
        credential_service = self._credential_service()
        return CredentialService.encryption_version, credential_service.encrypt_secret(api_key.get_secret_value())

    def decrypt_api_key(self, record: ModelConfigRecord) -> SecretStr:
        return SecretStr(self._credential_service().decrypt_secret(record.encrypted_api_key))

    def mask_api_key(self, api_key: str) -> str:
        if not api_key:
            return ""
        if len(api_key) <= 4:
            return "****"
        if len(api_key) <= 8:
            return f"****{api_key[-4:]}"
        return f"{api_key[:3]}****{api_key[-4:]}"

    def from_record(self, record: ModelConfigRecord) -> ModelConfig:
        return ModelConfig(
            provider=ModelProvider(record.provider),
            model_name=record.model_name,
            base_url=record.base_url,
            api_key=self.decrypt_api_key(record),
            name=record.name,
            is_default=record.is_default,
            description=record.description,
            timeout_seconds=record.timeout_seconds,
            temperature=record.temperature,
            max_tokens=record.max_tokens,
            prompt_cache_enabled=True,
            prompt_cache_ttl="ephemeral",
            provider_options={},
        )

    def to_record_payload(self, config: ModelConfig) -> dict:
        encryption_version, encrypted_api_key = self.encrypt_api_key(config.api_key)
        return {
            "name": config.name,
            "provider": config.provider.value,
            "base_url": config.base_url,
            "api_key_encryption_version": encryption_version,
            "encrypted_api_key": encrypted_api_key,
            "model_name": config.model_name,
            "is_default": config.is_default,
            "timeout_seconds": config.timeout_seconds,
            "temperature": config.temperature,
            "max_tokens": config.max_tokens,
            "description": config.description,
        }

    def _credential_service(self) -> CredentialService:
        return build_credential_service()

    def _normalize_prompt_cache_ttl(self, value: object) -> PromptCacheTTL:
        if value == "one_hour":
            return "one_hour"
        return cast(PromptCacheTTL, "ephemeral")
