from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import SecretStr
from sqlalchemy.exc import OperationalError
from sqlmodel import Session

from app.api.schemas import ModelConfigCreate, ModelConfigUpdate, ModelConfigView, ModelConnectionTestRequest, ModelConnectionTestResponse, ModelDiscoveryRequest, ModelDiscoveryResponse, ModelsView
from app.db.repositories.models import create_model_config, delete_model_config, get_default_model_config, get_model_config, list_model_configs, set_default_model_config, update_model_config
from app.db.session import get_session
from app.services.model_service import ModelService
from app.shared.enums import ModelProvider
from app.shared.schemas import ModelConfig

router = APIRouter()


def to_model_config_view(model_service: ModelService, record) -> ModelConfigView:
    api_key = model_service.decrypt_api_key(record).get_secret_value()
    return ModelConfigView(
        id=record.id or 0,
        name=record.name,
        provider=record.provider,
        base_url=record.base_url,
        api_key_masked=model_service.mask_api_key(api_key),
        model_name=record.model_name,
        is_default=record.is_default,
        timeout_seconds=record.timeout_seconds,
        temperature=record.temperature,
        max_tokens=record.max_tokens,
        prompt_cache_enabled=True,
        prompt_cache_ttl="ephemeral",
        description=record.description,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


@router.get("/api/models")
def list_models(session: Session = Depends(get_session)) -> ModelsView:
    model_service = ModelService()
    try:
        record = get_default_model_config(session)
    except OperationalError:
        record = None
    if record is None:
        return ModelsView(
            provider="",
            selected_model="",
            available_models=[],
            model_configured=False,
            configuration_message="LLM 模型未配置，请先在设置中添加并设为默认模型。",
        )
    config = model_service.from_record(record)
    return ModelsView(
        provider=config.provider.value,
        selected_model=config.model_name,
        available_models=model_service.list_available_models(config.provider, session),
        model_configured=True,
        configuration_message="",
    )


@router.get("/api/model-configs")
def list_model_config_records(session: Session = Depends(get_session)) -> list[ModelConfigView]:
    model_service = ModelService()
    return [to_model_config_view(model_service, record) for record in list_model_configs(session)]


@router.post("/api/model-configs", status_code=201)
def create_model_config_record(payload: ModelConfigCreate, session: Session = Depends(get_session)) -> ModelConfigView:
    model_service = ModelService()
    config = ModelConfig(
        name=payload.name,
        provider=ModelProvider(payload.provider),
        base_url=payload.base_url,
        api_key=payload.api_key,
        model_name=payload.model_name,
        is_default=payload.is_default,
        timeout_seconds=payload.timeout_seconds,
        temperature=payload.temperature,
        max_tokens=payload.max_tokens,
        prompt_cache_enabled=payload.prompt_cache_enabled,
        prompt_cache_ttl=payload.prompt_cache_ttl,
        description=payload.description,
    )
    record = create_model_config(session, **model_service.to_record_payload(config))
    return to_model_config_view(model_service, record)


@router.get("/api/model-configs/{config_id}")
def get_model_config_record(config_id: int, session: Session = Depends(get_session)) -> ModelConfigView:
    record = get_model_config(session, config_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Model config not found")
    model_service = ModelService()
    return to_model_config_view(model_service, record)


@router.put("/api/model-configs/{config_id}")
def update_model_config_record(config_id: int, payload: ModelConfigUpdate, session: Session = Depends(get_session)) -> ModelConfigView:
    updates = payload.model_dump(exclude_unset=True, exclude={"api_key"})
    if payload.api_key is not None:
        encryption_version, encrypted_api_key = ModelService().encrypt_api_key(payload.api_key)
        updates["api_key_encryption_version"] = encryption_version
        updates["encrypted_api_key"] = encrypted_api_key
    record = update_model_config(session, config_id, **updates)
    if record is None:
        raise HTTPException(status_code=404, detail="Model config not found")
    return to_model_config_view(ModelService(), record)


@router.delete("/api/model-configs/{config_id}", status_code=204)
def delete_model_config_record(config_id: int, session: Session = Depends(get_session)) -> Response:
    record = get_model_config(session, config_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Model config not found")
    if record.is_default:
        raise HTTPException(status_code=409, detail="Select another default model before deleting this one")
    delete_model_config(session, config_id)
    return Response(status_code=204)


@router.post("/api/model-configs/{config_id}/default")
def set_default_model_config_record(config_id: int, session: Session = Depends(get_session)) -> ModelConfigView:
    record = set_default_model_config(session, config_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Model config not found")
    return to_model_config_view(ModelService(), record)


@router.post("/api/model-configs/discover")
def discover_model_configs(payload: ModelDiscoveryRequest) -> ModelDiscoveryResponse:
    model_service = ModelService()
    config = ModelConfig(
        provider=ModelProvider(payload.provider),
        model_name="",
        base_url=payload.base_url,
        api_key=SecretStr(payload.api_key.get_secret_value()),
        timeout_seconds=payload.timeout_seconds,
        provider_options=payload.provider_options,
    )
    try:
        return ModelDiscoveryResponse(models=model_service.discover_models(config))
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except Exception as error:
        raise HTTPException(status_code=502, detail=f"Model discovery failed: {error}") from error


@router.post("/api/model-configs/test")
def test_model_config(payload: ModelConnectionTestRequest) -> ModelConnectionTestResponse:
    model_service = ModelService()
    config = ModelConfig(
        provider=ModelProvider(payload.provider),
        model_name=payload.model_name,
        base_url=payload.base_url,
        api_key=SecretStr(payload.api_key.get_secret_value()),
        timeout_seconds=payload.timeout_seconds,
        temperature=payload.temperature,
        max_tokens=payload.max_tokens,
        prompt_cache_enabled=payload.prompt_cache_enabled,
        prompt_cache_ttl=payload.prompt_cache_ttl,
        provider_options=payload.provider_options,
    )
    success = model_service.validate(config)
    return ModelConnectionTestResponse(success=success, message="Connection succeeded" if success else "Connection failed")
