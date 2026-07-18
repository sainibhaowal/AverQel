from app.services.deepspace.integrations.export_service import DeepSpaceExportService


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
