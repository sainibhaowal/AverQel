from __future__ import annotations

import logging

from fastapi import APIRouter, Depends

from app.core.auth import AuthContext, get_auth_context
from app.core.config import Settings, get_settings
from app.schemas.auth.capabilities import (
    CapabilitiesResponse,
    SupportedFormat,
    SystemLimits,
)
from app.services.ingestion.extractors.router import ExtractorRouter

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/capabilities", tags=["capabilities"])


@router.get("", response_model=CapabilitiesResponse)
def get_capabilities(
    settings: Settings = Depends(get_settings),
    _auth: AuthContext = Depends(get_auth_context),
) -> CapabilitiesResponse:
    extractor_router = ExtractorRouter(settings=settings)

    supported_formats = [
        SupportedFormat(
            extension=item.extension,
            category=item.category,
            extraction_method=item.extraction_method,
            needs_conversion=item.needs_conversion,
        )
        for item in extractor_router.describe_supported_formats()
    ]

    return CapabilitiesResponse(
        supported_formats=supported_formats,
        ocr_enabled=settings.ocr_enabled,
        vision_enabled=settings.vision_enabled,
        limits=SystemLimits(
            max_upload_size_bytes=settings.upload_max_bytes,
            max_tenant_storage_bytes=settings.tenant_max_storage_bytes,
            max_pdf_pages=settings.parser_max_pdf_pages,
            max_text_chars=settings.parser_max_text_chars,
            ocr_max_pages=settings.ocr_max_pages,
            vision_max_pages=settings.vision_max_pages,
        ),
    )
