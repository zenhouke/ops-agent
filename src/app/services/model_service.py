import json
import os
import re
from pathlib import Path
from typing import Any, Literal, cast

from pydantic import SecretStr
from sqlmodel import Session

from app.core.prompts.auxiliary import CONVERSATION_TITLE, build_knowledge_extraction_prompt
from app.core.llm.cc_switch import DEFAULT_BASE_URL, DEFAULT_MODEL, LOCAL_API_KEY, PROVIDER, require_cc_switch
from app.core.llm.types import LLMCompletionRequest, LLMMessage
from app.core.llm.factory import build_llm_provider

from app.db.models import ModelConfigRecord
from app.db.repositories.models import get_default_model_config, list_model_names_by_provider
from app.db.session import engine
from app.services.credential_factory import build_credential_service
from app.services.credential_service import CredentialService
from app.services.prompt_settings_service import get_prompt_settings_service
from app.shared import config as shared_config
from app.shared.enums import ModelProvider
from app.shared.schemas import ModelConfig

PromptCacheTTL = Literal["ephemeral", "one_hour"]


class ModelService:
    def __init__(self, provider_client=None, settings_path: Path | None = None):
        self._provider_client = provider_client
        self._settings_path = settings_path or shared_config.SETTINGS_PATH
        self._use_default_record = settings_path is None

    
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
                        content=CONVERSATION_TITLE,
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
        extraction_prompt = get_prompt_settings_service().get_snapshot().effective["knowledgeExtraction"]
        config = self.load_settings()
        if model_name and model_name != config.model_name:
            config = config.model_copy(update={"model_name": model_name})
        provider = self._provider_client or build_llm_provider(config)
        max_tokens = config.max_tokens if isinstance(config.max_tokens, int) and config.max_tokens > 0 else 2048
        request = LLMCompletionRequest(
            messages=[
                LLMMessage(
                    role="system",
                    content=build_knowledge_extraction_prompt(extraction_prompt),
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
        # The configured Messages route has no embedding endpoint. Retrieval uses
        # its existing lexical fallback instead of contacting another provider.
        raise ValueError("CC Switch Messages does not expose embeddings; use keyword retrieval.")

    def _fallback_conversation_title(self, prompt: str) -> str:
        text = prompt.strip()
        text = re.sub(r"^(请|麻烦|帮我|你帮我|请帮我|能不能|可以|是否)+", "", text)
        text = re.sub(r"[，。,.；;：:!?！？\s]+", "", text)
        text = re.sub(r"(有啥问题|有什么问题|吗|呢|吧)+$", "", text)
        text = text.replace("一下", "")
        return (text or "新会话")[:12]

    def build_default_config(self) -> ModelConfig:
        provider = ModelProvider(os.environ.get("OPS_AGENT_PROVIDER", PROVIDER.value))
        require_cc_switch(provider)
        return ModelConfig(
            provider=provider,
            model_name=os.environ.get("OPS_AGENT_MODEL", DEFAULT_MODEL),
            base_url=os.environ.get("OPS_AGENT_BASE_URL", DEFAULT_BASE_URL),
            api_key=SecretStr(os.environ.get("OPS_AGENT_API_KEY", LOCAL_API_KEY)),
            timeout_seconds=int(os.environ.get("OPS_AGENT_TIMEOUT_SECONDS", "180")),
            temperature=float(os.environ.get("OPS_AGENT_TEMPERATURE", "0.2")),
            max_tokens=int(os.environ.get("OPS_AGENT_MAX_TOKENS", "4096")),
            prompt_cache_enabled=os.environ.get("OPS_AGENT_PROMPT_CACHE_ENABLED", "true").lower() != "false",
            prompt_cache_ttl=self._normalize_prompt_cache_ttl(os.environ.get("OPS_AGENT_PROMPT_CACHE_TTL", "ephemeral")),
        )

    def load_settings(self) -> ModelConfig:
        # Agent runs, titles and knowledge extraction share the selected default.
        # Explicit settings paths remain useful for isolated configuration tools.
        if self._use_default_record:
            with Session(engine) as session:
                record = get_default_model_config(session)
                if record is not None:
                    config = self.from_record(record)
                    require_cc_switch(config.provider)
                    return config
        return self._load_file_settings()

    def _load_file_settings(self) -> ModelConfig:
        default_config = self.build_default_config()
        if not self._settings_path.exists():
            return default_config
        
        payload = json.loads(self._settings_path.read_text(encoding="utf-8"))
        config = ModelConfig(
            provider=ModelProvider(payload.get("provider", default_config.provider.value)),
            model_name=payload.get("model_name", default_config.model_name),
            base_url=payload.get("base_url", default_config.base_url),
            api_key=default_config.api_key,
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
            
        require_cc_switch(config.provider)
        return config

    def save_settings(self, config: ModelConfig) -> ModelConfig:
        require_cc_switch(config.provider)
        self._settings_path.parent.mkdir(parents=True, exist_ok=True)
        self._settings_path.write_text(
            json.dumps(
                {
                    "provider": config.provider.value,
                    "model_name": config.model_name,
                    "base_url": config.base_url,
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
        require_cc_switch(config.provider)
        # CC Switch routes model IDs; a separate vendor /models query is invalid.
        return [config.model_name or DEFAULT_MODEL]

    def encrypt_api_key(self, api_key: SecretStr) -> tuple[str, str]:
        credential_service = self._credential_service()
        return CredentialService.encryption_version, credential_service.encrypt_secret(api_key.get_secret_value())

    def decrypt_api_key(self, record: ModelConfigRecord) -> SecretStr:
        return SecretStr(
            self._credential_service().decrypt_secret(
                record.encrypted_api_key,
                record.api_key_encryption_version,
            )
        )

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
