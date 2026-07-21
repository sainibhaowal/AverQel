from __future__ import annotations

import uuid
from collections.abc import Callable
from io import BytesIO

from fastapi.testclient import TestClient
from pypdf import PdfWriter
from pytest import MonkeyPatch

from app.core.config import Settings
from app.ingestion.services.extractors.base import ExtractionRequest, ExtractionResult
from app.ingestion.services.extractors.layout_vision_extractor import (
    LayoutVisionExtractor,
)
from app.ingestion.services.ocr_service import OcrPageResult, OcrResult, OcrService
from app.system.services.storage_service import StorageService, StoredObject
from tests.conftest import SeededUser


def _login(client: TestClient, seeded: SeededUser) -> str:
    response = client.post(
        "/api/v1/auth/login",
        headers={"X-Tenant-Id": str(seeded.tenant_id)},
        json={"email": seeded.email, "password": seeded.password},
    )
    assert response.status_code == 200
    return str(response.json()["access_token"])


def _patch_storage(monkeypatch: MonkeyPatch) -> None:
    in_memory_objects: dict[tuple[str, str], bytes] = {}

    def fake_put(
        self: StorageService,
        *,
        tenant_id: uuid.UUID,
        document_id: uuid.UUID,
        filename: str,
        content_type: str,
        payload: bytes,
    ) -> StoredObject:
        object_key = f"{tenant_id}/{document_id}/{filename}"
        in_memory_objects[(self.settings.minio_bucket, object_key)] = payload
        return StoredObject(
            bucket=self.settings.minio_bucket,
            object_key=object_key,
            etag="etag",
            size_bytes=len(payload),
            content_type=content_type,
        )

    def fake_get(self: StorageService, *, bucket: str, object_key: str) -> bytes:
        return in_memory_objects[(bucket, object_key)]

    monkeypatch.setattr(StorageService, "put_bytes", fake_put)
    monkeypatch.setattr(StorageService, "get_bytes", fake_get)


def _blank_pdf_bytes() -> bytes:
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


def test_image_upload_emits_ocr_metadata_and_band(
    client: TestClient,
    settings: Settings,
    seed_user: Callable[[str, str, str, tuple[str, ...]], SeededUser],
    monkeypatch: MonkeyPatch,
) -> None:
    settings.upload_allowed_mime_types = [
        *settings.upload_allowed_mime_types,
        "image/png",
    ]
    settings.upload_allowed_extensions = [*settings.upload_allowed_extensions, ".png"]
    client.app.dependency_overrides[lambda: Settings] = lambda: settings  # type: ignore

    _patch_storage(monkeypatch)

    def fake_ocr(self: OcrService, payload: bytes, filename: str) -> OcrResult:
        _ = (self, payload, filename)
        return OcrResult(text="image extracted text", confidence=0.92, warnings=[])

    monkeypatch.setattr(OcrService, "extract_image_text", fake_ocr)

    seeded = seed_user(
        "tenant-obs-image",
        "editor-obs-image@tenant.example",
        "StrongPass!1234",
        ("editor",),
    )
    token = _login(client, seeded)

    response = client.post(
        "/api/v1/documents/upload",
        headers={
            "Authorization": f"Bearer {token}",
            "X-Tenant-Id": str(seeded.tenant_id),
            "Idempotency-Key": "idem-obs-image-1",
        },
        files={"file": ("image.png", b"fake-image-bytes", "image/png")},
    )
    assert response.status_code == 200
    doc_id = response.json()["document_id"]

    status = client.get(
        f"/api/v1/documents/{doc_id}/status",
        headers={
            "Authorization": f"Bearer {token}",
            "X-Tenant-Id": str(seeded.tenant_id),
        },
    )
    assert status.status_code == 200
    payload = status.json()
    assert payload["status"] == "indexed"
    assert payload["extraction_ocr_used"] is True
    assert payload["extraction_confidence_band"] in {"high", "medium", "low"}


def test_pdf_low_coverage_triggers_vision_fallback_and_metrics(
    client: TestClient,
    settings: Settings,
    seed_user: Callable[[str, str, str, tuple[str, ...]], SeededUser],
    monkeypatch: MonkeyPatch,
) -> None:
    _patch_storage(monkeypatch)
    settings.vision_enabled = True
    settings.extraction_low_coverage_threshold = 0.9

    def fake_pdf_ocr(
        self: OcrService, images: list[bytes], page_numbers: list[int] | None = None
    ) -> list[OcrPageResult]:
        _ = (self, images)
        numbers = page_numbers or [1]
        return [
            OcrPageResult(
                page_number=numbers[0],
                text="x",
                confidence=0.1,
                warnings=["ocr_low_confidence"],
            )
        ]

    def fake_vision(
        self: LayoutVisionExtractor,
        request: ExtractionRequest,
        primary: ExtractionResult,
    ) -> ExtractionResult:
        _ = (self, request)
        return ExtractionResult(
            text=primary.text + "\n\nvision block",
            page_count=primary.page_count,
            extraction_method="layout_vision_fallback",
            coverage_score=0.95,
            ocr_used=True,
            vision_used=True,
            warnings=[*primary.warnings, "vision_layout_fallback_used"],
        )

    monkeypatch.setattr(OcrService, "extract_pdf_page_text", fake_pdf_ocr)
    monkeypatch.setattr(LayoutVisionExtractor, "extract_with_primary", fake_vision)

    seeded = seed_user(
        "tenant-obs-vision",
        "editor-obs-vision@tenant.example",
        "StrongPass!1234",
        ("editor",),
    )
    token = _login(client, seeded)

    response = client.post(
        "/api/v1/documents/upload",
        headers={
            "Authorization": f"Bearer {token}",
            "X-Tenant-Id": str(seeded.tenant_id),
            "Idempotency-Key": "idem-obs-vision-1",
        },
        files={"file": ("blank.pdf", _blank_pdf_bytes(), "application/pdf")},
    )
    assert response.status_code == 200
    doc_id = response.json()["document_id"]

    status = client.get(
        f"/api/v1/documents/{doc_id}/status",
        headers={
            "Authorization": f"Bearer {token}",
            "X-Tenant-Id": str(seeded.tenant_id),
        },
    )
    assert status.status_code == 200
    payload = status.json()
    assert payload["extraction_vision_used"] is True
    assert "vision_layout_fallback_used" in payload["extraction_warnings"]

    metrics = client.get("/api/v1/metrics")
    assert metrics.status_code == 200
    body = metrics.text
    assert "aks_extraction_method_total" in body
    assert "aks_extraction_fallback_total" in body
    assert "aks_extraction_stage_duration_seconds" in body
