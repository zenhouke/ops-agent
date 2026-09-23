from sqlmodel import Session, col, func, select

from app.core.llm.types import LLMTokenUsage
from app.db.models import ModelUsage
from app.shared.schemas import ModelConfig


def create_model_usage(
    session: Session,
    *,
    runtime_id: str,
    conversation_id: str,
    model_config: ModelConfig,
    usage: LLMTokenUsage,
    call_kind: str = "agent",
    model_config_id: int | None = None,
    task_id: int | None = None,
) -> ModelUsage:
    row = ModelUsage(
        task_id=task_id,
        runtime_id=runtime_id,
        conversation_id=conversation_id,
        model_config_id=model_config_id,
        provider=model_config.provider.value,
        model_name=model_config.model_name,
        base_url_snapshot=model_config.base_url,
        temperature_snapshot=model_config.temperature,
        max_tokens_snapshot=model_config.max_tokens,
        input_tokens=usage.input_tokens,
        output_tokens=usage.output_tokens,
        cache_creation_input_tokens=usage.cache_creation_input_tokens,
        cache_read_input_tokens=usage.cache_read_input_tokens,
        total_tokens=usage.total_tokens,
        call_kind=call_kind,
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


def sum_conversation_usage(session: Session, conversation_id: str) -> LLMTokenUsage:
    row = session.exec(
        select(
            func.coalesce(func.sum(ModelUsage.input_tokens), 0),
            func.coalesce(func.sum(ModelUsage.output_tokens), 0),
            func.coalesce(func.sum(ModelUsage.cache_creation_input_tokens), 0),
            func.coalesce(func.sum(ModelUsage.cache_read_input_tokens), 0),
        ).where(ModelUsage.conversation_id == conversation_id)
    ).one()
    return LLMTokenUsage(
        input_tokens=int(row[0] or 0),
        output_tokens=int(row[1] or 0),
        cache_creation_input_tokens=int(row[2] or 0),
        cache_read_input_tokens=int(row[3] or 0),
    )


def latest_agent_usage(session: Session, conversation_id: str) -> ModelUsage | None:
    return session.exec(select(ModelUsage).where(
        ModelUsage.conversation_id == conversation_id,
        ModelUsage.call_kind == "agent",
    ).order_by(col(ModelUsage.id).desc())).first()
