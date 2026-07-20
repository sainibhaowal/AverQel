from app.auth.dependencies import create_access_token
from app.core.config import get_settings
from tests.conftest import SeededUser


def _auth_headers(seeded: SeededUser, *, roles: tuple[str, ...]) -> dict[str, str]:
    token = create_access_token(
        user_id=seeded.user_id,
        tenant_id=seeded.tenant_id,
        roles=set(roles),
        settings=get_settings(),
    )
    return {
        "Authorization": f"Bearer {token}",
        "X-Tenant-Id": str(seeded.tenant_id),
    }


def test_deepspace_note_creation_persists_payload(client, seed_user):
    seeded = seed_user(
        "Proactive Tenant",
        "proactive@example.com",
        "password123",
        ("admin",),
    )
    headers = _auth_headers(seeded, roles=("admin",))

    response = client.post(
        "/api/v1/deepspace/chats",
        headers=headers,
        json={
            "title": "Morning Draft",
            "content_html": "<p>Draft body from proactive agents.</p>",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["title"] == "Morning Draft"
    assert payload["content_html"] == "<p>Draft body from proactive agents.</p>"
