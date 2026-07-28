from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=128)
    full_name: str = Field(..., min_length=1, max_length=255)
    organization_name: Optional[str] = Field(
        None, max_length=255,
        description="Optional name for a new org. If omitted, user joins default-org.",
    )


class LoginRequest(BaseModel):
    email: EmailStr
    password: str
    # Only required when the user has 2FA enabled. Absence triggers a 401
    # with X-Auth-Reason: totp_required so the frontend can prompt for it.
    totp_code: Optional[str] = None


class DeleteAccountRequest(BaseModel):
    # Re-enter the current password to confirm intent + identity before an
    # irreversible account deletion.
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: str
    organization_id: str
    role: str


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    email: str
    full_name: str
    is_active: bool
    is_superuser: bool
    created_at: datetime


class MeResponse(BaseModel):
    user: UserResponse
    organization_id: str
    role: str
