from __future__ import annotations

from urllib.parse import parse_qs, urlsplit

import pytest

from app.integrations.services.mcp_provider_auth import (
    GITHUB_MCP_OAUTH_PROFILE,
    GOOGLE_MCP_OAUTH_PROFILE,
    SLACK_MCP_OAUTH_PROFILE,
    get_mcp_provider_profile,
)


@pytest.mark.unit_no_db
def test_curated_profiles_use_fixed_provider_endpoints_and_scopes(settings) -> None:
    settings.mcp_google_oauth_client_id = "mcp-google-id"
    settings.mcp_google_oauth_client_secret = "mcp-google-secret"
    settings.mcp_oauth_redirect_uri = "https://averqel.example/api/v1/mcp/oauth/callback"

    profile = get_mcp_provider_profile("google-gmail")
    assert profile is GOOGLE_MCP_OAUTH_PROFILE
    ready, reason = profile.readiness(settings)
    assert ready is True
    assert reason is None
    assert profile.authorization_endpoint == "https://accounts.google.com/o/oauth2/v2/auth"
    authorization_url = profile.authorization_url(
        client_id="mcp-google-id",
        redirect_uri=settings.mcp_oauth_redirect_uri,
        state="signed-state",
        code_challenge="pkce-challenge",
        scopes=profile.scopes_for("google-gmail"),
    )
    assert "access_type=offline" in authorization_url
    assert "prompt=consent" in authorization_url
    assert profile.scopes_for("google-gmail") == (
        "https://www.googleapis.com/auth/gmail.readonly",
        "https://www.googleapis.com/auth/gmail.compose",
    )


@pytest.mark.unit_no_db
def test_scope_verification_rejects_escalation_and_missing_scope() -> None:
    with pytest.raises(ValueError, match="unapproved scope"):
        GOOGLE_MCP_OAUTH_PROFILE.verify_scopes(
            provider_slug="google-gmail",
            granted_scope="https://www.googleapis.com/auth/gmail.readonly https://www.googleapis.com/auth/cloud-platform",
        )

    with pytest.raises(ValueError, match="did not return granted scopes"):
        GITHUB_MCP_OAUTH_PROFILE.verify_scopes(
            provider_slug="github",
            granted_scope=None,
        )


@pytest.mark.unit_no_db
def test_github_comma_delimited_scopes_are_normalized_without_scope_escalation() -> None:
    granted = GITHUB_MCP_OAUTH_PROFILE.verify_scopes(
        provider_slug="github",
        granted_scope="repo,read:user,user:email",
    )

    assert granted == ("read:user", "repo", "user:email")

    with pytest.raises(ValueError, match="unapproved scope"):
        GITHUB_MCP_OAUTH_PROFILE.verify_scopes(
            provider_slug="github",
            granted_scope="repo,read:user,user:email,gist",
        )


@pytest.mark.unit_no_db
def test_github_revocation_uses_the_oauth_grant_endpoint() -> None:
    assert (
        GITHUB_MCP_OAUTH_PROFILE.revocation_endpoint
        == "https://api.github.com/applications/{client_id}/grant"
    )


@pytest.mark.unit_no_db
def test_slack_profile_uses_confidential_user_oauth_and_nested_token_response(settings) -> None:
    settings.mcp_slack_oauth_client_id = "slack-client-id"
    settings.mcp_slack_oauth_client_secret = "slack-client-secret"
    settings.mcp_oauth_redirect_uri = "https://averqel.example/api/v1/mcp/oauth/callback"

    profile = get_mcp_provider_profile("slack")
    assert profile is SLACK_MCP_OAUTH_PROFILE
    ready, reason = profile.readiness(settings)
    assert ready is True
    assert reason is None
    assert profile.authorization_scope_param == "scope"
    assert profile.authorization_endpoint == "https://slack.com/oauth/v2_user/authorize"
    assert profile.token_endpoint == "https://slack.com/api/oauth.v2.user.access"
    assert "chat:write" in profile.scopes_for("slack")
    assert "canvases:write" in profile.scopes_for("slack")
    authorization_url = profile.authorization_url(
        client_id="slack-client-id",
        redirect_uri=settings.mcp_oauth_redirect_uri,
        state="signed-state",
        code_challenge="pkce-challenge",
        scopes=profile.scopes_for("slack"),
    )
    query = parse_qs(urlsplit(authorization_url).query)
    assert "scope" in query

    normalized = profile.normalize_token_response(
        {
            "ok": True,
            "authed_user": {
                "id": "U123",
                "access_token": "xoxp-secret",
                "scope": "users:read,users:read.email",
            },
        }
    )
    assert normalized["access_token"] == "xoxp-secret"
    assert normalized["scope"] == "users:read,users:read.email"

    granted = profile.verify_scopes(
        provider_slug="slack",
        granted_scope=" ".join(
            (*profile.scopes_for("slack"), "identity.basic", "identity.email", "search:read")
        ),
    )
    assert "identity.basic" in granted
    assert "identity.email" in granted
    assert "search:read" in granted

    with pytest.raises(ValueError, match="unapproved scope.*admin.apps:read"):
        profile.verify_scopes(
            provider_slug="slack",
            granted_scope=" ".join((*profile.scopes_for("slack"), "admin.apps:read")),
        )


@pytest.mark.unit_no_db
def test_slack_identity_uses_safe_auth_test_labels() -> None:
    identity = SLACK_MCP_OAUTH_PROFILE.extract_identity(
        {
            "ok": True,
            "user_id": "U123",
            "user": "ravi",
            "team_id": "T123",
            "team": "AverQel",
            "private_token": "must-not-store",
        }
    )

    assert identity == {
        "provider_subject": "U123",
        "account_id": "U123",
        "display_name": "ravi",
    }


@pytest.mark.unit_no_db
def test_identity_capture_is_restricted_to_safe_account_labels() -> None:
    identity = GITHUB_MCP_OAUTH_PROFILE.extract_identity(
        {"id": 42, "login": "ravi", "name": "Ravi", "private_token": "must-not-store"},
        [{"email": "Ravi@Example.com", "primary": True}],
    )

    assert identity == {
        "provider_subject": 42,
        "account_id": 42,
        "email": "ravi@example.com",
        "display_name": "Ravi",
    }
    assert "private_token" not in identity


@pytest.mark.unit_no_db
def test_gmail_identity_uses_mailbox_profile_before_broader_userinfo() -> None:
    assert GOOGLE_MCP_OAUTH_PROFILE.identity_endpoints("google-gmail")[0].endswith(
        "/gmail/v1/users/me/profile"
    )
