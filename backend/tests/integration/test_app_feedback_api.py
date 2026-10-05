from __future__ import annotations

from fastapi.testclient import TestClient

from app.auth.dependencies import create_access_token
from app.core.config import get_settings
from app.system.models.app_feedback import AppFeedback, FeedbackCampaign
from tests.conftest import SeededUser


def _auth_headers(seeded: SeededUser) -> dict[str, str]:
    token = create_access_token(
        user_id=seeded.user_id,
        tenant_id=seeded.tenant_id,
        roles={"admin"},
        settings=get_settings(),
    )
    return {
        "Authorization": f"Bearer {token}",
        "X-Tenant-Id": str(seeded.tenant_id),
    }


def test_app_feedback_campaigns_and_admin_submissions_round_trip(
    client: TestClient,
    db_session,
    seed_user,
) -> None:
    seeded = seed_user(
        "Feedback Tenant",
        "feedback-admin@example.org",
        "StrongPass!1234",
        ("admin",),
    )
    get_settings().bootstrap_super_admin_emails = [seeded.email]
    headers = _auth_headers(seeded)

    campaign = FeedbackCampaign(
        title="Feature check-in",
        description="Tell us what should be improved next.",
        is_active=True,
    )
    db_session.add(campaign)
    db_session.commit()
    db_session.refresh(campaign)

    campaigns_response = client.get("/api/v1/app-feedback/campaigns", headers=headers)
    assert campaigns_response.status_code == 200
    campaigns = campaigns_response.json()
    assert len(campaigns) == 1
    assert campaigns[0]["title"] == "Feature check-in"

    submit_response = client.post(
        "/api/v1/app-feedback/submit",
        headers=headers,
        json={
            "campaign_id": str(campaign.id),
            "subject": "Dashboard spacing",
            "content": "The memory page should fill the available width.",
            "category": "ux_improvement",
        },
    )
    assert submit_response.status_code == 200
    submission = submit_response.json()
    assert submission["subject"] == "Dashboard spacing"

    feedback_row = db_session.query(AppFeedback).one()
    assert feedback_row.subject == "Dashboard spacing"

    submissions_response = client.get(
        "/api/v1/app-feedback/admin/submissions",
        headers=headers,
    )
    assert submissions_response.status_code == 200
    submissions = submissions_response.json()
    assert len(submissions) == 1
    assert submissions[0]["email"] == seeded.email
    assert submissions[0]["subject"] == "Dashboard spacing"

    detail_response = client.get(f"/api/v1/app-feedback/mine/{submission['id']}", headers=headers)
    assert detail_response.status_code == 200
    assert len(detail_response.json()["messages"]) == 0

    note_response = client.post(
        f"/api/v1/app-feedback/admin/submissions/{submission['id']}/messages",
        headers=headers,
        json={"body": "Internal triage note", "visibility": "internal"},
    )
    assert note_response.status_code == 200
    reply_response = client.post(
        f"/api/v1/app-feedback/admin/submissions/{submission['id']}/messages",
        headers=headers,
        json={"body": "Thanks, we have triaged this.", "visibility": "public"},
    )
    assert reply_response.status_code == 200

    user_detail = client.get(f"/api/v1/app-feedback/mine/{submission['id']}", headers=headers)
    assert user_detail.status_code == 200
    assert [item["body"] for item in user_detail.json()["messages"]] == [
        "Thanks, we have triaged this."
    ]
    notifications = client.get("/api/v1/notifications", headers=headers)
    assert notifications.status_code == 200
    assert {item["event_type"] for item in notifications.json()} >= {
        "feedback_received",
        "feedback_reply",
    }
    receipt = next(
        item for item in notifications.json() if item["event_type"] == "feedback_received"
    )
    read_response = client.post(f"/api/v1/notifications/{receipt['id']}/read", headers=headers)
    assert read_response.status_code == 200
    assert read_response.json()["read_at"] is not None
    dismiss_response = client.delete(f"/api/v1/notifications/{receipt['id']}", headers=headers)
    assert dismiss_response.status_code == 204
    refreshed = client.get("/api/v1/notifications", headers=headers)
    assert receipt["id"] not in {item["id"] for item in refreshed.json()}

    other = seed_user(
        "Other Tenant", "other-feedback-user@example.org", "StrongPass!1234", ("user",)
    )
    other_headers = _auth_headers(other)
    forbidden_detail = client.get(
        f"/api/v1/app-feedback/mine/{submission['id']}", headers=other_headers
    )
    assert forbidden_detail.status_code == 404
