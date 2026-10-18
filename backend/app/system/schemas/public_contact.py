from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict, Field, field_validator

_EMAIL_PATTERN = re.compile(
    r"^[A-Z0-9.!#$%&'*+/=?^_`{|}~-]+@"
    r"[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?"
    r"(?:\.[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?)+$",
    re.IGNORECASE,
)


def is_valid_email_address(value: str) -> bool:
    return bool(_EMAIL_PATTERN.fullmatch(value))


class PublicContactCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=100)
    email: str = Field(min_length=3, max_length=254)
    subject: str = Field(min_length=1, max_length=120)
    message: str = Field(min_length=1, max_length=8_000)
    verification_token: str = Field(min_length=32, max_length=128)
    website: str = Field(default="", max_length=200)

    @field_validator("name", "subject", mode="before")
    @classmethod
    def normalize_single_line_fields(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        normalized = value.strip()
        if any(ord(character) < 32 or ord(character) == 127 for character in normalized):
            raise ValueError("This field must be a single line of text.")
        return normalized

    @field_validator("email", mode="before")
    @classmethod
    def normalize_and_validate_email(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        normalized = value.strip()
        if not is_valid_email_address(normalized):
            raise ValueError("Enter a valid email address.")
        return normalized

    @field_validator("message", mode="before")
    @classmethod
    def normalize_message(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        normalized = value.strip()
        if "\x00" in normalized:
            raise ValueError("The message contains an unsupported character.")
        return normalized


class PublicContactStatusResponse(BaseModel):
    available: bool


class PublicContactVerificationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str = Field(min_length=3, max_length=254)

    @field_validator("email", mode="before")
    @classmethod
    def normalize_and_validate_email(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        normalized = value.strip()
        if not is_valid_email_address(normalized):
            raise ValueError("Enter a valid email address.")
        return normalized


class PublicContactVerificationConfirm(PublicContactVerificationRequest):
    challenge_id: str = Field(pattern=r"^[A-Za-z0-9_-]{24,128}$")
    code: str = Field(pattern=r"^[0-9]{6}$")


class PublicContactVerificationSent(BaseModel):
    challenge_id: str
    expires_in_seconds: int


class PublicContactVerificationAccepted(BaseModel):
    verified: bool = True
    verification_token: str
    expires_in_seconds: int


class PublicContactAccepted(BaseModel):
    accepted: bool = True
