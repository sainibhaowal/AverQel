from __future__ import annotations

from uuid import uuid4

from sqlalchemy import select, text

from app.db.session import get_session_factory, set_db_tenant_context
from app.integrations.models.connector import Connector
from app.integrations.models.connector_secret import ConnectorSecret
from app.integrations.models.integration import Integration


def test_connector_rls_blocks_cross_tenant_reads(
    seed_user,
) -> None:
    tenant_a = seed_user(
        "connector-rls-a",
        "connector-a@example.com",
        "StrongPass!1234",
        ("admin",),
    )
    tenant_b = seed_user(
        "connector-rls-b",
        "connector-b@example.com",
        "StrongPass!1234",
        ("admin",),
    )

    session = get_session_factory()()
    session.execute(text("SET ROLE aks_app"))
    try:
        integration = Integration(
            id=uuid4(),
            name=f"Connector RLS Integration {uuid4().hex[:8]}",
            slug=f"connector-rls-{uuid4().hex[:8]}",
            description="Tenant isolation test integration",
            ui_metadata={},
        )
        session.add(integration)
        session.flush()

        set_db_tenant_context(session, tenant_a.tenant_id)
        connector = Connector(
            tenant_id=tenant_a.tenant_id,
            user_id=tenant_a.user_id,
            integration_id=integration.id,
            name="Tenant A Connector",
            config={},
            sync_frequency="daily",
        )
        session.add(connector)
        session.flush()
        session.add(
            ConnectorSecret(
                connector_id=connector.id,
                tenant_id=tenant_a.tenant_id,
                secret_ciphertext=b"ciphertext",
                secret_nonce=b"nonce",
                secret_kid="kid-a",
                secret_type="access_token",
                metadata_json={"source": "test"},
            )
        )
        session.commit()

        tenant_a_session = get_session_factory()()
        tenant_a_session.execute(text("SET ROLE aks_app"))
        try:
            set_db_tenant_context(tenant_a_session, tenant_a.tenant_id)
            own_connector = tenant_a_session.get(Connector, connector.id)
            assert own_connector is not None
            own_secret = tenant_a_session.execute(
                select(ConnectorSecret).where(
                    ConnectorSecret.connector_id == connector.id
                )
            ).scalar_one_or_none()
            assert own_secret is not None
        finally:
            tenant_a_session.execute(text("RESET ROLE"))
            tenant_a_session.close()

        tenant_b_session = get_session_factory()()
        tenant_b_session.execute(text("SET ROLE aks_app"))
        try:
            set_db_tenant_context(tenant_b_session, tenant_b.tenant_id)
            cross_connector = tenant_b_session.get(Connector, connector.id)
            assert cross_connector is None
            cross_secret = tenant_b_session.execute(
                select(ConnectorSecret).where(
                    ConnectorSecret.connector_id == connector.id
                )
            ).scalar_one_or_none()
            assert cross_secret is None
        finally:
            tenant_b_session.execute(text("RESET ROLE"))
            tenant_b_session.close()
    finally:
        session.execute(text("RESET ROLE"))
        session.close()
