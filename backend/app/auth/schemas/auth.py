from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class AuthUserResponse(BaseModel):
    user_id: str
    tenant_id: str
    roles: list[str]

    model_config = ConfigDict(extra="forbid")


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=1024)

    model_config = ConfigDict(extra="forbid")

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        normalized = value.strip().lower()
        if "@" not in normalized:
            raise ValueError("email must include '@'")
        return normalized


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: AuthUserResponse
    requires_2fa: bool = False
    pending_token: str | None = None

    model_config = ConfigDict(extra="forbid")


class RefreshResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int

    model_config = ConfigDict(extra="forbid")


class LogoutResponse(BaseModel):
    success: bool

    model_config = ConfigDict(extra="forbid")


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=1024)
    new_password: str = Field(min_length=1, max_length=1024)

    model_config = ConfigDict(extra="forbid")


class ProfileResponse(BaseModel):
    user_id: str
    tenant_id: str
    collection_code: str
    email: str
    roles: list[str]
    status: str
    created_at: datetime
    last_login_at: datetime | None
    totp_enabled: bool = False
    avatar: str | None = None

    model_config = ConfigDict(extra="forbid")


class ProfileUpdateRequest(BaseModel):
    avatar: str | None = None

    model_config = ConfigDict(extra="forbid")


class RegisterRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=1024)

    model_config = ConfigDict(extra="forbid")

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        normalized = value.strip().lower()
        if "@" not in normalized:
            raise ValueError("email must include '@'")
        return normalized


class UserRegisterResponse(BaseModel):
    user_id: str
    email: str
    status: str = "active"

    model_config = ConfigDict(extra="forbid")


class AccountActivityItem(BaseModel):
    id: str
    action: str
    status: str
    resource_type: str
    resource_id: str | None
    created_at: datetime
    details: dict[str, str] = Field(default_factory=dict)

    model_config = ConfigDict(extra="forbid")


class AccountActivityResponse(BaseModel):
    items: list[AccountActivityItem]

    model_config = ConfigDict(extra="forbid")


class ExportAccountResponse(BaseModel):
    generated_at: datetime
    account: dict[str, object]
    workspace_counts: dict[str, int]
    recent_activity: list[AccountActivityItem]

    model_config = ConfigDict(extra="forbid")


class DeleteAccountRequest(BaseModel):
    password: str = Field(min_length=1, max_length=1024)

    model_config = ConfigDict(extra="forbid")


class DeleteAccountResponse(BaseModel):
    success: bool = True

    model_config = ConfigDict(extra="forbid")


class CookiePreferencesRequest(BaseModel):
    essential: bool = True
    analytics: bool = False
    marketing: bool = False

    model_config = ConfigDict(extra="forbid")


class CookiePreferencesResponse(BaseModel):
    success: bool = True

    model_config = ConfigDict(extra="forbid")


# ------------------------------------------------------------------
# 2FA schemas
# ------------------------------------------------------------------


class TotpVerifyRequest(BaseModel):
    pending_token: str = Field(min_length=1)
    code: str = Field(min_length=6, max_length=16)

    model_config = ConfigDict(extra="forbid")


class TotpSetupResponse(BaseModel):
    secret: str
    provisioning_uri: str

    model_config = ConfigDict(extra="forbid")


class TotpConfirmRequest(BaseModel):
    code: str = Field(min_length=6, max_length=6)

    model_config = ConfigDict(extra="forbid")


class TotpConfirmResponse(BaseModel):
    backup_codes: list[str]

    model_config = ConfigDict(extra="forbid")


class TotpDisableRequest(BaseModel):
    password: str = Field(min_length=1, max_length=1024)

    model_config = ConfigDict(extra="forbid")


TokenResponse.model_rebuild()
ProfileResponse.model_rebuild()
