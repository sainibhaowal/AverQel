from __future__ import annotations

import base64
import hashlib

import pytest
from fastapi.testclient import TestClient

from app.auth.dependencies import create_access_token
from app.core.config import get_settings
from app.platform.database.session import set_db_tenant_context
from app.system.models.app_feedback import AppFeedback
from app.system.models.app_feedback_message import AppFeedbackMessage
from app.system.models.support_encryption_key import SupportEncryptionKey
from app.system.models.support_ticket import SupportTicket
from app.system.models.support_ticket_message import SupportTicketMessage
from tests.conftest import SeededUser
from tests.helpers.support_encryption import create_encrypted_payload, register_support_key


def _headers(seeded: SeededUser, roles: set[str]) -> dict[str, str]:
    token = create_access_token(
        user_id=seeded.user_id,
        tenant_id=seeded.tenant_id,
        roles=roles,
        settings=get_settings(),
    )
    return {"Authorization": f"Bearer {token}", "X-Tenant-Id": str(seeded.tenant_id)}


@pytest.mark.db_commit
def test_support_encryption_keys_are_account_owned_and_private_backups_are_not_cached(
    client: TestClient,
    db_session,
    seed_user,
) -> None:
    admin = seed_user("Encryption admin", "e2ee-admin@example.org", "StrongPass!1234", ("admin",))
    user = seed_user("Encryption user", "e2ee-user@example.org", "StrongPass!1234", ("user",))
    other = seed_user(
        "Other encryption user", "e2ee-other@example.org", "StrongPass!1234", ("user",)
    )
    get_settings().bootstrap_super_admin_emails = [admin.email]
    admin_headers = _headers(admin, {"admin"})
    user_headers = _headers(user, {"user"})
    other_headers = _headers(other, {"user"})

    admin_key_id = register_support_key(client, admin_headers, scope="platform_admin")
    user_key_id = register_support_key(client, user_headers, scope="user")

    public_key = client.get("/api/v1/support/encryption/admin-public-key", headers=user_headers)
    assert public_key.status_code == 200
    assert public_key.json()["key_id"] == admin_key_id
    assert "private_key_ciphertext" not in public_key.json()
    assert public_key.headers["cache-control"] == "no-store, max-age=0"

    own_backup = client.get("/api/v1/support/encryption/me", headers=user_headers)
    assert own_backup.status_code == 200
    assert own_backup.json()["key_id"] == user_key_id
    assert own_backup.headers["cache-control"] == "no-store, max-age=0"

    other_backup = client.get("/api/v1/support/encryption/me", headers=other_headers)
    assert other_backup.status_code == 404
    user_admin_backup = client.get(
        "/api/v1/support/encryption/admin-private-key", headers=user_headers
    )
    assert user_admin_backup.status_code == 403

    admin_backup = client.get("/api/v1/support/encryption/admin-private-key", headers=admin_headers)
    assert admin_backup.status_code == 200
    assert admin_backup.json()["key_id"] == admin_key_id
    assert admin_backup.headers["cache-control"] == "no-store, max-age=0"

    set_db_tenant_context(db_session, "bypass")
    rows = db_session.query(SupportEncryptionKey).all()
    assert {(row.scope, row.user_id) for row in rows} == {
        ("platform_admin", admin.user_id),
        ("user", user.user_id),
    }


def test_support_encryption_rejects_non_rsa_public_key(
    client: TestClient,
    seed_user,
) -> None:
    admin = seed_user(
        "Invalid key admin", "invalid-key-admin@example.org", "StrongPass!1234", ("admin",)
    )
    get_settings().bootstrap_super_admin_emails = [admin.email]
    headers = _headers(admin, {"admin"})
    invalid_der = b"not-a-public-key"
    payload = {
        "key_id": hashlib.sha256(invalid_der).hexdigest(),
        "public_key": base64.b64encode(invalid_der).decode("ascii"),
        "private_key_ciphertext": base64.b64encode(b"p" * 128).decode("ascii"),
        "salt": base64.b64encode(b"s" * 16).decode("ascii"),
        "iv": base64.b64encode(b"i" * 12).decode("ascii"),
    }

    response = client.put(
        "/api/v1/support/encryption/admin-private-key", headers=headers, json=payload
    )

    assert response.status_code == 422


@pytest.mark.db_commit
def test_admin_browser_migration_replaces_legacy_support_and_feedback_text(
    client: TestClient,
    db_session,
    seed_user,
) -> None:
    owner = seed_user(
        "Legacy content owner", "legacy-owner@example.org", "StrongPass!1234", ("admin",)
    )
    get_settings().bootstrap_super_admin_emails = [owner.email]
    headers = _headers(owner, {"admin"})
    admin_key_id = register_support_key(client, headers, scope="platform_admin")
    user_key_id = register_support_key(client, headers, scope="user")
    conversation_keys = [admin_key_id, user_key_id]

    set_db_tenant_context(db_session, owner.tenant_id)
    ticket = SupportTicket(
        tenant_id=owner.tenant_id,
        user_id=owner.user_id,
        subject="Legacy private subject",
        description="Legacy private support details",
        category="query",
        status="open",
    )
    feedback = AppFeedback(
        tenant_id=owner.tenant_id,
        user_id=owner.user_id,
        subject="Legacy feedback subject",
        content="Legacy feedback details",
        category="suggestion",
        status="new",
    )
    db_session.add_all([ticket, feedback])
    db_session.flush()
    public_ticket_message = SupportTicketMessage(
        tenant_id=owner.tenant_id,
        ticket_id=ticket.id,
        author_user_id=owner.user_id,
        author_role="user",
        body="Legacy public ticket reply",
        is_internal=False,
    )
    internal_ticket_message = SupportTicketMessage(
        tenant_id=owner.tenant_id,
        ticket_id=ticket.id,
        author_user_id=owner.user_id,
        author_role="admin",
        body="Legacy internal ticket note",
        is_internal=True,
    )
    public_feedback_message = AppFeedbackMessage(
        tenant_id=owner.tenant_id,
        feedback_id=feedback.id,
        author_user_id=owner.user_id,
        author_role="user",
        body="Legacy public feedback reply",
        is_internal=False,
    )
    internal_feedback_message = AppFeedbackMessage(
        tenant_id=owner.tenant_id,
        feedback_id=feedback.id,
        author_user_id=owner.user_id,
        author_role="admin",
        body="Legacy internal feedback note",
        is_internal=True,
    )
    db_session.add_all(
        [
            public_ticket_message,
            internal_ticket_message,
            public_feedback_message,
            internal_feedback_message,
        ]
    )
    db_session.commit()

    support_legacy = client.get("/api/v1/support/admin/encryption/legacy", headers=headers)
    feedback_legacy = client.get("/api/v1/app-feedback/admin/encryption/legacy", headers=headers)
    assert support_legacy.status_code == feedback_legacy.status_code == 200
    assert [item["id"] for item in support_legacy.json()["items"]] == [str(ticket.id)]
    assert [item["id"] for item in feedback_legacy.json()["items"]] == [str(feedback.id)]

    support_migration = client.put(
        f"/api/v1/support/admin/tickets/{ticket.id}/encryption",
        headers=headers,
        json={
            "encrypted_payload": create_encrypted_payload(conversation_keys),
            "messages": [
                {
                    "id": str(public_ticket_message.id),
                    "encrypted_payload": create_encrypted_payload(conversation_keys),
                },
                {
                    "id": str(internal_ticket_message.id),
                    "encrypted_payload": create_encrypted_payload([admin_key_id]),
                },
            ],
        },
    )
    feedback_migration = client.put(
        f"/api/v1/app-feedback/admin/submissions/{feedback.id}/encryption",
        headers=headers,
        json={
            "encrypted_payload": create_encrypted_payload(conversation_keys),
            "messages": [
                {
                    "id": str(public_feedback_message.id),
                    "encrypted_payload": create_encrypted_payload(conversation_keys),
                },
                {
                    "id": str(internal_feedback_message.id),
                    "encrypted_payload": create_encrypted_payload([admin_key_id]),
                },
            ],
        },
    )

    assert support_migration.status_code == 200, support_migration.text
    assert feedback_migration.status_code == 200, feedback_migration.text
    assert support_migration.json()["subject"] == "[Encrypted support request]"
    assert feedback_migration.json()["subject"] == "[Encrypted feedback]"
    assert all(
        message["body"] == "[Encrypted message]"
        for message in support_migration.json()["messages"]
        if message["author_role"] != "system"
    )
    assert all(
        message["body"] == "[Encrypted message]"
        for message in feedback_migration.json()["messages"]
    )

    set_db_tenant_context(db_session, owner.tenant_id)
    db_session.expire_all()
    assert db_session.get(SupportTicket, ticket.id).description == "[Encrypted]"
    assert db_session.get(AppFeedback, feedback.id).content == "[Encrypted]"
    assert (
        db_session.get(SupportTicketMessage, public_ticket_message.id).body == "[Encrypted message]"
    )
    assert (
        db_session.get(AppFeedbackMessage, public_feedback_message.id).body == "[Encrypted message]"
    )
