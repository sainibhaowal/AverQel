from __future__ import annotations

from tests.integration import test_mcp_provider_oauth as provider_oauth_tests


def test_google_oauth_flow_encrypts_tokens_and_captures_owner_identity(
    db_session, seed_user, monkeypatch
) -> None:
    provider_oauth_tests.test_static_provider_oauth_encrypts_pending_data_and_captures_identity(
        db_session, seed_user, monkeypatch
    )


def test_disconnect_revokes_and_deletes_the_local_credential(
    db_session, seed_user, monkeypatch
) -> None:
    provider_oauth_tests.test_static_provider_disconnect_revokes_and_removes_local_token(
        db_session, seed_user, monkeypatch
    )
