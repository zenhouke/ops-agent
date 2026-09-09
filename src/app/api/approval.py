from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.core.approval import ApprovalContext
from app.services.approval_service import get_approval_service


router = APIRouter()


class ApprovalPermissionsView(BaseModel):
    allow: list[str]
    deny: list[str]


class ApprovalPolicyView(BaseModel):
    permissions: ApprovalPermissionsView


class ApprovalContextView(BaseModel):
    conversation_id: str = ""
    asset_id: int | None = None
    asset_type: str = ""
    shell_type: str = ""
    profile: str = "posix-shell"
    vendor: str | None = None


class ApprovalCheckRequest(BaseModel):
    command: str
    context: ApprovalContextView | None = None


@router.get("/api/approval/policy")
def get_approval_policy() -> ApprovalPolicyView:
    service = get_approval_service()
    policy_dict = service.get_policy_dict()
    return ApprovalPolicyView(**policy_dict)


@router.put("/api/approval/policy")
def update_approval_policy(policy: ApprovalPolicyView) -> dict[str, str]:
    service = get_approval_service()
    service.update_policy_from_dict(policy.model_dump())
    return {"message": "Policy updated successfully"}


@router.post("/api/approval/check")
def check_command(request: ApprovalCheckRequest) -> dict[str, str]:
    command = request.command
    if not command:
        raise HTTPException(status_code=400, detail="command is required")

    service = get_approval_service()
    action, reason = service.check_command(
        command,
        context=None if request.context is None else ApprovalContext(**request.context.model_dump()),
    )
    return {"action": action, "reason": reason, "command": command}
