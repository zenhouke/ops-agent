"""Conversation storage composition shared by API and background services."""
import os
from pathlib import Path

from app.services.conversation_service import ConversationService
from app.services.model_service import ModelService


def get_conversation_service() -> ConversationService:
    configured = os.getenv("OPS_AGENT_CONVERSATIONS_DIR", "")
    base_dir = Path(configured) if configured else Path.cwd() / ".ops-agent" / "conversations"
    return ConversationService(base_dir=base_dir, model_service=ModelService())
