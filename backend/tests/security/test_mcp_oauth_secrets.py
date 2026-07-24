from __future__ import annotations

from tests.integration import test_mcp_provider_oauth as provider_oauth_tests


def test_oauth_tokens_never_enter_server_config_or_events(
    db_session, seed_user, monkeypatch
) -> None:
    provider_oauth_tests.test_static_provider_oauth_encrypts_pending_data_and_captures_identity(
        db_session, seed_user, monkeypatch
    )
