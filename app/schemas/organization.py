from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

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
