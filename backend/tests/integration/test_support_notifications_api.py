from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

from fastapi.testclient import TestClient

from app.auth.dependencies import create_access_token
from app.core.config import get_settings
from tests.conftest import SeededUser


def test_assigned_admin_sla_notice_uses_recipient_tenant(monkeypatch) -> None:
    from app.system.workers import tasks_notifications

    ticket_owner_tenant = uuid4()
    admin_tenant = uuid4()
    admin_id = uuid4()
    ticket = SimpleNamespace(id=uuid4(), tenant_id=ticket_owner_tenant, assigned_admin_id=admin_id)
    calls = []
    monkeypatch.setattr(
        tasks_notifications,
        "add_user_notification",
        lambda db, **kwargs: calls.append(kwargs),
    )

    assert tasks_notifications._notify_assigned_admin(
        object(),
        ticket=ticket,
        assigned_admin_tenants={admin_id: admin_tenant},
        event_type="sla_first_response_breached",
        title="Overdue",
        message="Ticket is overdue.",
        resource_id=str(ticket.id),
        idempotency_key=f"test:{ticket.id}",
    )
    assert calls[0]["tenant_id"] == admin_tenant
    assert calls[0]["tenant_id"] != ticket_owner_tenant


def _headers(seeded: SeededUser) -> dict[str, str]:
    token = create_access_token(
        user_id=seeded.user_id,
        tenant_id=seeded.tenant_id,
        roles={"admin"},
        settings=get_settings(),
    )
    return {"Authorization": f"Bearer {token}", "X-Tenant-Id": str(seeded.tenant_id)}


def test_support_ticket_thread_and_durable_notifications(
    client: TestClient, seed_user, monkeypatch
) -> None:
    seeded = seed_user("Support Tenant", "support-admin@example.org", "StrongPass!1234", ("admin",))
    get_settings().bootstrap_super_admin_emails = [seeded.email]
    headers = _headers(seeded)

    created = client.post(
        "/api/v1/support/tickets",
        headers=headers,
        json={
            "subject": "DeepSpace run did not finish",
            "description": "The run stopped before returning its findings.",
            "category": "deepspace_agent",
        },
    )
    assert created.status_code == 200
    ticket_id = created.json()["id"]
    assert created.json()["priority"] == "normal"
    assert created.json()["first_response_due_at"]
    assert created.json()["resolution_due_at"]

    queue = client.get("/api/v1/support/admin/queue", headers=headers)
    assert queue.status_code == 200
    assert queue.json()["total"] == 1
    assert queue.json()["items"][0]["id"] == ticket_id

    assigned = client.patch(
        f"/api/v1/support/admin/tickets/{ticket_id}",
        headers=headers,
        json={"assigned_admin_id": str(seeded.user_id)},
    )
    assert assigned.status_code == 200
    assert assigned.json()["assigned_admin_id"] == str(seeded.user_id)

    admin_detail = client.get(f"/api/v1/support/admin/tickets/{ticket_id}", headers=headers)
    assert admin_detail.status_code == 200
    assert admin_detail.json()["messages"][0]["kind"] == "acknowledgment"

    internal = client.post(
        f"/api/v1/support/admin/tickets/{ticket_id}/messages",
        headers=headers,
        json={"body": "Check run telemetry before responding.", "visibility": "internal"},
    )
    assert internal.status_code == 200
    public = client.post(
        f"/api/v1/support/admin/tickets/{ticket_id}/messages",
        headers=headers,
        json={"body": "We are investigating this run.", "visibility": "public"},
    )
    assert public.status_code == 200
    assert public.json()["status"] == "waiting_user"

    user_detail = client.get(f"/api/v1/support/tickets/{ticket_id}", headers=headers)
    assert user_detail.status_code == 200
    bodies = [item["body"] for item in user_detail.json()["messages"]]
    assert "We are investigating this run." in bodies
    assert "Check run telemetry before responding." not in bodies

    notification_list = client.get("/api/v1/notifications", headers=headers)
    assert notification_list.status_code == 200
    assert {item["event_type"] for item in notification_list.json()} >= {
        "ticket_received",
        "ticket_reply",
    }

    preferences = client.put(
        "/api/v1/notifications/preferences",
        headers=headers,
        json={"email_enabled": False, "digest_frequency": "daily", "muted_domains": ["support"]},
    )
    assert preferences.status_code == 200
    assert preferences.json()["email_delivery_available"] is False
    assert preferences.json()["digest_frequency"] == "daily"
    muted_feed = client.get("/api/v1/notifications", headers=headers)
    assert muted_feed.status_code == 200
    assert all(item["event_domain"] != "support" for item in muted_feed.json())

    rejected_attachment = client.post(
        f"/api/v1/support/tickets/{ticket_id}/attachments",
        headers=headers,
        files={"file": ("fake.pdf", b"not a PDF", "application/pdf")},
    )
    assert rejected_attachment.status_code == 415

    from app.ingestion.services.security.malware_scan_service import (
        MalwareScanResult,
        MalwareScanService,
    )
    from app.system.api import support as support_api
    from app.system.services.storage_service import StoredObject

    attachment_bytes = b"%PDF-1.4\nminimal support attachment"
    monkeypatch.setattr(
        MalwareScanService, "scan_bytes", lambda *args, **kwargs: MalwareScanResult(is_clean=True)
    )

    def fake_put(self, *, tenant_id, document_id, filename, content_type, payload):
        return StoredObject(
            bucket=get_settings().minio_bucket,
            object_key=f"{tenant_id}/{document_id}/{filename}",
            etag="test-etag",
            size_bytes=len(payload),
            content_type=content_type,
        )

    monkeypatch.setattr(support_api.StorageService, "put_bytes", fake_put)
    monkeypatch.setattr(
        support_api.StorageService, "get_tenant_bytes", lambda *args, **kwargs: attachment_bytes
    )
    uploaded = client.post(
        f"/api/v1/support/tickets/{ticket_id}/attachments",
        headers=headers,
        files={"file": ("trace.pdf", attachment_bytes, "application/pdf")},
    )
    assert uploaded.status_code == 201
    assert uploaded.json()["filename"] == "trace.pdf"
    user_detail_with_file = client.get(f"/api/v1/support/tickets/{ticket_id}", headers=headers)
    attachment = user_detail_with_file.json()["attachments"][0]
    downloaded = client.get(attachment["download_url"], headers=headers)
    assert downloaded.status_code == 200
    assert downloaded.content == attachment_bytes
    admin_detail_with_file = client.get(
        f"/api/v1/support/admin/tickets/{ticket_id}", headers=headers
    )
    admin_download = client.get(
        admin_detail_with_file.json()["attachments"][0]["download_url"], headers=headers
    )
    assert admin_download.status_code == 200

    other = seed_user(
        "Different Support Tenant", "other-support-user@example.org", "StrongPass!1234", ("user",)
    )
    hidden = client.get(f"/api/v1/support/tickets/{ticket_id}", headers=_headers(other))
    assert hidden.status_code == 404


def test_opted_in_notification_uses_retryable_email_outbox(
    client: TestClient, seed_user, monkeypatch
) -> None:
    seeded = seed_user(
        "Email Notice Tenant", "email-notice@example.org", "StrongPass!1234", ("admin",)
    )
    settings = get_settings()
    monkeypatch.setattr(settings, "notification_smtp_host", "smtp.example.test")
    monkeypatch.setattr(settings, "notification_smtp_from", "notices@example.test")
    monkeypatch.setattr(settings, "bootstrap_super_admin_emails", [seeded.email])
    headers = _headers(seeded)
    opted_in = client.put(
        "/api/v1/notifications/preferences",
        headers=headers,
        json={"email_enabled": True, "digest_frequency": "none", "muted_domains": []},
    )
    assert opted_in.status_code == 200

    ticket = client.post(
        "/api/v1/support/tickets",
        headers=headers,
        json={"subject": "Email delivery test", "description": "An opted-in receipt."},
    )
    assert ticket.status_code == 200

    from app.system.workers import tasks_notifications

    sent: list[dict[str, str]] = []
    monkeypatch.setattr(tasks_notifications, "_send_email", lambda **kwargs: sent.append(kwargs))
    delivered = tasks_notifications.dispatch_email_outbox.run()
    assert delivered >= 1
    assert len(sent) == 1
    assert "Support request received" in sent[0]["body"]
