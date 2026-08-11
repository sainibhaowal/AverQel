from app.deepspace.integrations.export_service import DeepSpaceExportService


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
