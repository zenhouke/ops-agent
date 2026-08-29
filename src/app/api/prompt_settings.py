from fastapi import APIRouter, HTTPException

from app.api.schemas.prompt_settings import (
    PromptSettingsResetRequest,
    PromptSettingsUpdateRequest,
    PromptSettingsView,
)
from app.services.prompt_settings_service import PromptSettingsConflictError, get_prompt_settings_service


router = APIRouter()


def _view(payload: dict[str, object]) -> PromptSettingsView:
    return PromptSettingsView.model_validate(payload)


@router.get("/api/prompt-settings", response_model=PromptSettingsView)
def get_prompt_settings() -> PromptSettingsView:
    return _view(get_prompt_settings_service().get_snapshot().to_dict())


@router.put("/api/prompt-settings", response_model=PromptSettingsView)
def update_prompt_settings(request: PromptSettingsUpdateRequest) -> PromptSettingsView:
    try:
        snapshot = get_prompt_settings_service().update(
            request.revision,
            request.overrides.model_dump(by_alias=True),
        )
    except PromptSettingsConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _view(snapshot.to_dict())


@router.post("/api/prompt-settings/preview", response_model=PromptSettingsView)
def preview_prompt_settings(request: PromptSettingsUpdateRequest) -> PromptSettingsView:
    try:
        snapshot = get_prompt_settings_service().preview(request.overrides.model_dump(by_alias=True))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _view(snapshot.to_dict())


@router.post("/api/prompt-settings/reset", response_model=PromptSettingsView)
def reset_prompt_settings(request: PromptSettingsResetRequest) -> PromptSettingsView:
    try:
        snapshot = get_prompt_settings_service().reset(request.revision)
    except PromptSettingsConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return _view(snapshot.to_dict())
