from typing import Any, cast
from sqlalchemy import desc
from sqlmodel import Session, select

from app.db.models import ModelConfigRecord
from app.db.repositories.common import commit_refresh, touch_updated_at


def create_model_config(
    session: Session,
    *,
    name: str,
    provider: str,
    base_url: str,
    api_key_encryption_version: str,
    encrypted_api_key: str,
    model_name: str,
    is_default: bool = False,
    timeout_seconds: int = 30,
    temperature: float = 0.2,
    max_tokens: int = 1024,
    description: str = "",
) -> ModelConfigRecord:
    if is_default:
        clear_default_model_configs(session)
    row = ModelConfigRecord(
        name=name,
        provider=provider,
        base_url=base_url,
        api_key_encryption_version=api_key_encryption_version,
        encrypted_api_key=encrypted_api_key,
        model_name=model_name,
        is_default=is_default,
        timeout_seconds=timeout_seconds,
        temperature=temperature,
        max_tokens=max_tokens,
        description=description,
    )
    return commit_refresh(session, row)


def list_model_configs(session: Session) -> list[ModelConfigRecord]:
    return list(session.exec(select(ModelConfigRecord).order_by(desc(cast(Any, ModelConfigRecord.id)))).all())


def list_model_names_by_provider(session: Session, provider: str) -> list[str]:
    rows = session.exec(
        select(ModelConfigRecord.model_name)
        .where(ModelConfigRecord.provider == provider)
        .order_by(desc(cast(Any, ModelConfigRecord.id)))
    ).all()
    return list(dict.fromkeys(rows))


def get_model_config(session: Session, model_config_id: int) -> ModelConfigRecord | None:
    return session.get(ModelConfigRecord, model_config_id)


def get_model_config_by_model_name(session: Session, model_name: str) -> ModelConfigRecord | None:
    return session.exec(
        select(ModelConfigRecord)
        .where(ModelConfigRecord.model_name == model_name)
        .order_by(desc(cast(Any, ModelConfigRecord.id)))
    ).first()


def get_default_model_config(session: Session) -> ModelConfigRecord | None:
    return session.exec(select(ModelConfigRecord).where(ModelConfigRecord.is_default == True)).first()


def clear_default_model_configs(session: Session) -> None:
    rows = session.exec(select(ModelConfigRecord).where(ModelConfigRecord.is_default == True)).all()
    for row in rows:
        row.is_default = False
        touch_updated_at(row)
        session.add(row)
    session.commit()


def set_default_model_config(session: Session, model_config_id: int) -> ModelConfigRecord | None:
    row = get_model_config(session, model_config_id)
    if row is None:
        return None
    clear_default_model_configs(session)
    row.is_default = True
    touch_updated_at(row)
    return commit_refresh(session, row)


def update_model_config(session: Session, model_config_id: int, **updates: Any) -> ModelConfigRecord | None:
    row = get_model_config(session, model_config_id)
    if row is None:
        return None
    if updates.get("is_default") is True:
        clear_default_model_configs(session)
    for key, value in updates.items():
        if hasattr(row, key) and value is not None:
            setattr(row, key, value)
    touch_updated_at(row)
    return commit_refresh(session, row)


def delete_model_config(session: Session, model_config_id: int) -> bool:
    row = get_model_config(session, model_config_id)
    if row is None:
        return False
    session.delete(row)
    session.commit()
    return True
