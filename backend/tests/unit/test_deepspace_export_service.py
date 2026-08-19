from app.deepspace.integrations.export_service import DeepSpaceExportService
from app.deepspace.api.export import _download_content_disposition


def test_pdf_export_handles_unicode_content_without_crashing():
    service = DeepSpaceExportService()

    pdf = service.generate_pdf(
        """
        <h1>Export 😊</h1>
        <p>This paragraph has emoji 😊, smart quotes “ok”, em dash —, and Привет.</p>
        <ul><li>Bullet with emoji ✨</li></ul>
        <table><tr><th>Name 😊</th></tr><tr><td>Value Привет</td></tr></table>
        """,
        title="DeepSpace 😊 Export",
    )

    assert pdf.getvalue().startswith(b"%PDF")


def test_markdown_export_returns_markdown_not_source_html():
    service = DeepSpaceExportService()

    markdown = (
        service.generate_md(
            "<h1>Title</h1><p>A <strong>bold</strong> paragraph.</p>"
            "<ul><li>One</li><li>Two</li></ul>"
            "<table><tr><th>Name</th><th>Value</th></tr><tr><td>A</td><td>1</td></tr></table>"
        )
        .getvalue()
        .decode("utf-8")
    )

    assert markdown.startswith("# Title")
    assert "**bold**" in markdown
    assert "- One" in markdown
    assert "| Name | Value |" in markdown
    assert "<h1>" not in markdown


def test_export_header_supports_unicode_note_titles() -> None:
    disposition = _download_content_disposition(
        title="Ravi’s research ✓",
        extension="pdf",
    )

    # Starlette can encode the fallback header value, and browsers retain the
    # original title through the RFC 5987 filename parameter.
    disposition.encode("latin-1")
    assert 'filename="Ravi_s_research_.pdf"' in disposition
    assert "filename*=UTF-8''Ravi%E2%80%99s%20research%20%E2%9C%93.pdf" in disposition
