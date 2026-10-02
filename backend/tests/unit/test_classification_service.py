from app.documents.models.document import Document
from app.documents.models.organization import DocumentClassificationRule
from app.documents.services.classification_service import ClassificationService


def _document(*, filename: str, content_type: str = "application/pdf") -> Document:
    return Document(filename=filename, content_type=content_type)


def _rule(*, pattern: str, content_type: str | None = None) -> DocumentClassificationRule:
    return DocumentClassificationRule(filename_pattern=pattern, content_type=content_type)


def test_classification_match_is_case_insensitive_and_supports_filename_globs() -> None:
    assert ClassificationService.matches(
        _rule(pattern="invoice-*.pdf"),
        _document(filename="Invoice-2026.PDF"),
    )


def test_classification_match_requires_exact_content_type_when_configured() -> None:
    rule = _rule(pattern="*", content_type="application/pdf")
    assert ClassificationService.matches(rule, _document(filename="report.pdf"))
    assert not ClassificationService.matches(
        rule,
        _document(
            filename="report.docx",
            content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ),
    )


def test_classification_match_rejects_non_matching_filename() -> None:
    assert not ClassificationService.matches(
        _rule(pattern="invoice-*.pdf"),
        _document(filename="contract.pdf"),
    )
