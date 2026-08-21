from uuid import uuid4

from app.ingestion.services.table_extractor import ExtractedTable, TableExtractor
from app.providers.models.provider_reembedding_job import ProviderReembeddingJob


def test_extracted_table_formats_text_and_json() -> None:
    table = ExtractedTable(page_number=2, headers=["Name", "Value"], rows=[["A", "1"]])
    assert table.to_text() == "Name | Value\n--- | ---\nA | 1"
    assert table.to_json() == {
        "page_number": 2,
        "headers": ["Name", "Value"],
        "rows": [["A", "1"]],
    }
    assert ExtractedTable(page_number=1).to_text() == ""


def test_table_extractor_handles_missing_dependency_and_bad_pdf(monkeypatch) -> None:
    real_import = __import__("builtins").__import__

    def missing_pdfplumber(name, *args, **kwargs):
        if name == "pdfplumber":
            raise ImportError("missing")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", missing_pdfplumber)
    assert TableExtractor().extract_tables(b"not a pdf") == []


def test_provider_reembedding_job_defaults_and_fields() -> None:
    tenant_id, provider_id = uuid4(), uuid4()
    job = ProviderReembeddingJob(
        tenant_id=tenant_id,
        provider_config_id=provider_id,
        status="pending",
        target_model="embed-v2",
    )
    assert job.tenant_id == tenant_id
    assert job.status == "pending"
    assert job.target_model == "embed-v2"
