from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class SupportedFormat(BaseModel):
    extension: str
    category: str
    extraction_method: str
    needs_conversion: bool = False

    model_config = ConfigDict(extra="forbid")


class SystemLimits(BaseModel):
    max_upload_size_bytes: int
    max_tenant_storage_bytes: int
    max_pdf_pages: int
    max_text_chars: int
    ocr_max_pages: int
    vision_max_pages: int

    model_config = ConfigDict(extra="forbid")


class CapabilitiesResponse(BaseModel):
    supported_formats: list[SupportedFormat]
    ocr_enabled: bool
    vision_enabled: bool
    limits: SystemLimits

    model_config = ConfigDict(extra="forbid")
