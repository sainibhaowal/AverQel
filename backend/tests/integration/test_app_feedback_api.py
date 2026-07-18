from __future__ import annotations

from fastapi.testclient import TestClient

from app.core.auth import create_access_token
from app.core.config import get_settings
from app.models.system.app_feedback import AppFeedback, FeedbackCampaign
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
