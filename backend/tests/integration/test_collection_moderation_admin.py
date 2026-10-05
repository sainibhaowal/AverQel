from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.platform.database.session import set_db_tenant_context
from tests.conftest import SeededUser


def _login(client: TestClient, seeded: SeededUser) -> str:
    response = client.post(
        "/api/v1/auth/login",
        headers={"X-Tenant-Id": str(seeded.tenant_id)},
        json={"email": seeded.email, "password": seeded.password},
    )
    assert response.status_code == 200
    return str(response.json()["access_token"])


def _headers(seeded: SeededUser, token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "X-Tenant-Id": str(seeded.tenant_id),
    }


def test_collection_moderation_admin_workflow_and_role_gate(
    client: TestClient,
    db_session: Session,
    seed_user: Callable[[str, str, str, tuple[str, ...]], SeededUser],
) -> None:
    admin = seed_user(
        "collection-moderation-admin",
        "moderation-admin@example.com",
        "StrongPass!1234",
        ("admin",),
    )
    admin_headers = _headers(admin, _login(client, admin))

    collection_response = client.post(
        "/api/v1/collections",
        headers=admin_headers,
        json={"name": "Moderation workflow", "description": "Report lifecycle"},
    )
    assert collection_response.status_code == 201
    collection_id = collection_response.json()["id"]

    report_response = client.post(
        f"/api/v1/collections/{collection_id}/security/reports",
        headers=admin_headers,
        json={"reason": "spam", "details": "Reported for moderation workflow test."},
    )
    assert report_response.status_code == 201
    assert report_response.json() == {"status": "reported"}

    second_report_response = client.post(
        f"/api/v1/collections/{collection_id}/security/reports",
        headers=admin_headers,
        json={"reason": "abuse", "details": "Second report for pagination test."},
    )
    assert second_report_response.status_code == 201

    listed = client.get(
        "/api/v1/collections/admin/security/reports?status=open&limit=1&offset=0",
        headers=admin_headers,
    )
    assert listed.status_code == 200
    reports = listed.json()
    assert len(reports) == 1
    assert listed.headers["X-Total-Count"] == "2"
    assert listed.headers["X-Has-More"] == "true"
    assert reports[0]["collection_name"] == "Moderation workflow"
    next_page = client.get(
        "/api/v1/collections/admin/security/reports?status=open&limit=1&offset=1",
        headers=admin_headers,
    )
    assert next_page.status_code == 200
    assert len(next_page.json()) == 1
    assert next_page.json()[0]["id"] != reports[0]["id"]
    assert next_page.headers["X-Has-More"] == "false"

    report_id = next(
        item["id"]
        for page in (reports, next_page.json())
        for item in page
        if item["reason"] == "spam"
    )

    notifications = client.get("/api/v1/notifications?limit=100", headers=admin_headers)
    assert notifications.status_code == 200
    report_alerts = [
        item for item in notifications.json() if item["event_domain"] == "collection_moderation"
    ]
    assert len(report_alerts) == 2
    assert all(
        "Reported for moderation workflow test." not in item["message"] for item in report_alerts
    )
    assert all(
        item["href"] == f"/dashboard/admin/collections/moderation?report={item['resource_id']}"
        for item in report_alerts
    )
    direct_report = client.get(
        f"/api/v1/collections/admin/security/reports?report_id={report_id}",
        headers=admin_headers,
    )
    assert direct_report.status_code == 200
    assert [item["id"] for item in direct_report.json()] == [report_id]

    muted = client.put(
        "/api/v1/notifications/preferences",
        headers=admin_headers,
        json={
            "email_enabled": False,
            "digest_frequency": "none",
            "muted_domains": ["collection_moderation"],
        },
    )
    assert muted.status_code == 200
    assert "collection_moderation" in muted.json()["muted_domains"]

    updated = client.post(
        f"/api/v1/collections/admin/security/reports/{report_id}",
        headers=admin_headers,
        json={"status": "reviewing", "moderator_note": "Review started."},
    )
    assert updated.status_code == 200
    assert updated.json()["status"] == "reviewing"
    assert updated.json()["details"] == "Reported for moderation workflow test."

    history = client.get(
        f"/api/v1/collections/admin/security/reports/{report_id}/history?limit=2&offset=0",
        headers=admin_headers,
    )
    assert history.status_code == 200
    assert history.headers["X-Total-Count"] == "3"
    assert history.headers["X-Has-More"] == "true"
    assert {action["action_type"] for action in history.json()} == {
        "status_changed",
        "note_added",
    }
    older_history = client.get(
        f"/api/v1/collections/admin/security/reports/{report_id}/history?limit=2&offset=2",
        headers=admin_headers,
    )
    assert older_history.status_code == 200
    assert older_history.json()[0]["action_type"] == "report_created"
    assert older_history.headers["X-Has-More"] == "false"

    set_db_tenant_context(db_session, "bypass")
    with pytest.raises(SQLAlchemyError, match="append-only"):
        db_session.execute(
            text("UPDATE collection_moderation_actions SET note = 'forged' WHERE id = :action_id"),
            {"action_id": history.json()[0]["id"]},
        )
    db_session.rollback()

    editor = seed_user(
        "collection-moderation-editor",
        "moderation-editor@example.com",
        "StrongPass!1234",
        ("editor",),
    )
    editor_headers = _headers(editor, _login(client, editor))
    editor_notifications = client.get("/api/v1/notifications?limit=100", headers=editor_headers)
    assert editor_notifications.status_code == 200
    assert not any(
        item["event_domain"] == "collection_moderation" for item in editor_notifications.json()
    )

    forbidden_list = client.get(
        "/api/v1/collections/admin/security/reports?status=all",
        headers=editor_headers,
    )
    assert forbidden_list.status_code == 403

    forbidden_update = client.post(
        f"/api/v1/collections/admin/security/reports/{report_id}",
        headers=editor_headers,
        json={"status": "dismissed"},
    )
    assert forbidden_update.status_code == 403

    other_admin = seed_user(
        "collection-moderation-other-tenant",
        "moderation-other-admin@example.com",
        "StrongPass!1234",
        ("admin",),
    )
    set_db_tenant_context(db_session, "bypass")
    with pytest.raises(SQLAlchemyError):
        db_session.execute(
            text("""INSERT INTO collection_moderation_actions
                   (id, tenant_id, report_id, actor_role, action_type)
                   VALUES (gen_random_uuid(), :tenant_id, :report_id, 'admin', 'note_added')"""),
            {"tenant_id": other_admin.tenant_id, "report_id": report_id},
        )
    db_session.rollback()
    other_admin_headers = _headers(other_admin, _login(client, other_admin))
    other_tenant_list = client.get(
        "/api/v1/collections/admin/security/reports?status=all",
        headers=other_admin_headers,
    )
    assert other_tenant_list.status_code == 200
    assert other_tenant_list.json() == []
    other_tenant_deep_link = client.get(
        f"/api/v1/collections/admin/security/reports?report_id={report_id}",
        headers=other_admin_headers,
    )
    assert other_tenant_deep_link.status_code == 200
    assert other_tenant_deep_link.json() == []
    assert other_tenant_deep_link.headers["X-Total-Count"] == "0"

    other_tenant_update = client.post(
        f"/api/v1/collections/admin/security/reports/{report_id}",
        headers=other_admin_headers,
        json={"status": "dismissed"},
    )
    assert other_tenant_update.status_code == 404

    invalid_status = client.post(
        f"/api/v1/collections/admin/security/reports/{report_id}",
        headers=admin_headers,
        json={"status": "not-a-status"},
    )
    assert invalid_status.status_code == 422

    resolved = client.post(
        f"/api/v1/collections/admin/security/reports/{report_id}",
        headers=admin_headers,
        json={"status": "resolved"},
    )
    assert resolved.status_code == 200
    assert resolved.json()["status"] == "resolved"
    assert resolved.json()["resolved_at"] is not None

    invalid_transition = client.post(
        f"/api/v1/collections/admin/security/reports/{report_id}",
        headers=admin_headers,
        json={"status": "dismissed"},
    )
    assert invalid_transition.status_code == 409
    assert invalid_transition.json()["error"]["code"] == "INVALID_REPORT_STATUS_TRANSITION"
    reopened = client.post(
        f"/api/v1/collections/admin/security/reports/{report_id}",
        headers=admin_headers,
        json={"status": "open"},
    )
    assert reopened.status_code == 200
    assert reopened.json()["status"] == "open"
    assert reopened.json()["resolved_at"] is None

    # The append-only trigger still permits parent collection deletion to
    # cascade the report and its audit trail through the established workflow.
    deleted_collection = client.delete(
        f"/api/v1/collections/{collection_id}", headers=admin_headers
    )
    assert deleted_collection.status_code == 204, deleted_collection.text


def test_collection_report_submission_is_rate_limited(
    client: TestClient,
    seed_user: Callable[[str, str, str, tuple[str, ...]], SeededUser],
) -> None:
    member = seed_user(
        "collection-report-rate-limit",
        "collection-report-rate-limit@example.com",
        "StrongPass!1234",
        ("editor",),
    )
    headers = _headers(member, _login(client, member))
    collection = client.post(
        "/api/v1/collections",
        headers=headers,
        json={"name": "Report rate limit", "description": "Spam protection"},
    )
    assert collection.status_code == 201

    results = [
        client.post(
            f"/api/v1/collections/{collection.json()['id']}/security/reports",
            headers=headers,
            json={"reason": "spam", "details": "Rate limit verification."},
        )
        for _ in range(11)
    ]
    assert all(result.status_code == 201 for result in results[:10])
    assert results[10].status_code == 429
    assert results[10].json()["error"]["code"] == "RATE_LIMIT_EXCEEDED"
