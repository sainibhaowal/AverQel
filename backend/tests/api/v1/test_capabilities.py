from collections.abc import Callable

from fastapi.testclient import TestClient

from tests.conftest import SeededUser


def _login(client: TestClient, tenant_id: str, email: str, password: str) -> str:
    response = client.post(
        "/api/v1/auth/login",
        headers={"X-Tenant-Id": tenant_id},
        json={"email": email, "password": password},
    )
    assert response.status_code == 200
    return response.json()["access_token"]


def test_get_capabilities(
    client: TestClient,
    seed_user: Callable[[str, str, str, tuple[str, ...]], SeededUser],
) -> None:
    user = seed_user(
        "capabilities-tenant",
        "capabilities@example.com",
        "StrongPass!1234",
        ("reader",),
    )
    token = _login(client, str(user.tenant_id), user.email, user.password)

    response = client.get(
        "/api/v1/capabilities",
        headers={
            "Authorization": f"Bearer {token}",
            "X-Tenant-Id": str(user.tenant_id),
        },
    )
    assert response.status_code == 200
    data = response.json()

    # Check structure
    assert "supported_formats" in data
    assert "ocr_enabled" in data
    assert "vision_enabled" in data
    assert "limits" in data

    # Check formats
    formats = data["supported_formats"]
    assert len(formats) > 0
    extensions = [f["extension"] for f in formats]
    assert ".pdf" in extensions
    assert ".docx" in extensions

    # Check limits
    assert "max_upload_size_bytes" in data["limits"]
    assert "max_pdf_pages" in data["limits"]
    assert data["limits"]["max_pdf_pages"] == 1000  # default from Settings
