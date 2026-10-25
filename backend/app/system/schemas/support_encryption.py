from __future__ import annotations

import binascii
import re
import uuid

from pydantic import BaseModel, ConfigDict, Field, field_validator


class SupportKeyRegistration(BaseModel):
    key_id: str = Field(..., min_length=64, max_length=64)
    public_key: str = Field(..., min_length=100, max_length=2048)
    private_key_ciphertext: str = Field(..., min_length=100, max_length=12_000)
    salt: str = Field(..., min_length=20, max_length=32)
    iv: str = Field(..., min_length=16, max_length=24)

    model_config = ConfigDict(extra="forbid")

    @field_validator("key_id")
    @classmethod
    def validate_key_id(cls, value: str) -> str:
        if not re.fullmatch(r"[a-f0-9]{64}", value):
            raise ValueError("key_id must be a lowercase SHA-256 fingerprint")
        return value

    @field_validator("public_key", "private_key_ciphertext", "salt", "iv")
    @classmethod
    def validate_base64(cls, value: str) -> str:
        import base64

        try:
            base64.b64decode(value, validate=True)
        except (ValueError, binascii.Error) as exc:
            raise ValueError("key fields must use standard base64 encoding") from exc
        return value


class SupportPublicKeyResponse(BaseModel):
    key_id: str
    public_key: str

    model_config = ConfigDict(extra="forbid")


class SupportPrivateKeyResponse(SupportPublicKeyResponse):
    private_key_ciphertext: str
    salt: str
    iv: str


class EncryptedPayload(BaseModel):
    encrypted_payload: str = Field(..., min_length=100, max_length=150_000)

    model_config = ConfigDict(extra="forbid")


class LegacyEncryptedMessage(BaseModel):
    id: uuid.UUID
    encrypted_payload: str = Field(..., min_length=100, max_length=150_000)

    model_config = ConfigDict(extra="forbid")


class SupportRecordEncryptionMigration(BaseModel):
    encrypted_payload: str | None = Field(default=None, min_length=100, max_length=150_000)
    messages: list[LegacyEncryptedMessage] = Field(default_factory=list, max_length=500)

    model_config = ConfigDict(extra="forbid")


class FeedbackRecordEncryptionMigration(SupportRecordEncryptionMigration):
    pass


class LegacySupportRecord(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    user_key_initialized: bool = True


class LegacySupportRecordPage(BaseModel):
    items: list[LegacySupportRecord]
    total: int


class LegacyFeedbackRecord(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    user_key_initialized: bool = True


class LegacyFeedbackRecordPage(BaseModel):
    items: list[LegacyFeedbackRecord]
    total: int
