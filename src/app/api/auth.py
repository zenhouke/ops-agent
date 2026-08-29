from fastapi import APIRouter

from app.services.auth_service import is_api_authentication_required

router = APIRouter()


@router.get("/api/auth/status")
def auth_status() -> dict[str, bool]:
    return {"required": is_api_authentication_required()}


@router.post("/api/auth/verify", status_code=204)
def verify_authentication() -> None:
    return None
