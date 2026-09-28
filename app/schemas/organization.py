from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.models.organization_membership import MemberRole


class OrganizationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    slug: str
    is_active: bool
    created_at: datetime


class MyOrganizationItem(BaseModel):
    """An organization the current user belongs to, with their role in it."""
    organization: OrganizationResponse
    role: str
    is_default: bool
    joined_at: datetime


class MemberResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str  # membership id
    user_id: str
    email: str
    full_name: str
    role: str
    is_default: bool
    joined_at: datetime


class InviteMemberRequest(BaseModel):
    email: EmailStr
    role: MemberRole = MemberRole.editor


class UpdateMemberRequest(BaseModel):
    role: MemberRole


class SwitchOrgRequest(BaseModel):
    organization_id: str = Field(..., min_length=1)


class ApiKeyCreateRequest(BaseModel):
    name: str = Field(..., min_length=3, max_length=120)
    scopes: list[str] = Field(default_factory=lambda: ["read"])

    @field_validator("scopes")
    @classmethod
    def validate_scopes(cls, value: list[str]) -> list[str]:
        allowed = {"read", "write", "admin"}
        normalized = sorted({scope.strip().lower() for scope in value if scope.strip()})
        if not normalized:
            raise ValueError("At least one scope is required")
        unknown = set(normalized) - allowed
        if unknown:
            raise ValueError(f"Unsupported API key scope(s): {', '.join(sorted(unknown))}")
        return normalized


class ApiKeyResponse(BaseModel):
    id: str
    name: str
    key_prefix: str
    scopes: list[str]
    created_by: str | None
    created_at: datetime
    revoked_at: datetime | None
    revoked_by: str | None
    last_used_at: datetime | None
    usage_total_calls: int = 0
    usage_last_called_at: datetime | None = None
    rate_limit_limit: int | None = None
    rate_limit_window_seconds: int | None = None


class ApiKeyCreateResponse(ApiKeyResponse):
    secret: str


class ApiKeyUsageEndpointSummary(BaseModel):
    path: str
    method: str
    total_calls: int
    total_items: int
    last_called_at: datetime | None


class ApiKeyUsageSummary(BaseModel):
    api_key_id: str
    total_calls: int
    total_items: int
    last_called_at: datetime | None
    endpoints: list[ApiKeyUsageEndpointSummary]
