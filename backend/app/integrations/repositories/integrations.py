from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.integrations.models.connector import Connector
from app.integrations.models.integration import Integration


class IntegrationRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_integrations(self) -> list[Integration]:
        result = self.session.execute(
            select(Integration).where(Integration.is_active).order_by(Integration.name)
        )
        return list(result.scalars().all())

    def get_connectors(self, tenant_id: uuid.UUID) -> list[Connector]:
        stmt = (
            select(Connector)
            .options(selectinload(Connector.integration))
            .where(Connector.tenant_id == tenant_id)
            .order_by(Connector.created_at.desc())
        )
        result = self.session.execute(stmt)
        return list(result.scalars().all())

    def get_connector(self, tenant_id: uuid.UUID, connector_id: uuid.UUID) -> Connector | None:
        stmt = (
            select(Connector)
            .options(selectinload(Connector.integration))
            .where(Connector.tenant_id == tenant_id, Connector.id == connector_id)
        )
        return self.session.execute(stmt).scalars().first()

    def get_connector_by_slug(self, tenant_id: uuid.UUID, slug: str) -> Connector | None:
        stmt = (
            select(Connector)
            .options(selectinload(Connector.integration))
            .join(Integration)
            .where(
                Connector.tenant_id == tenant_id,
                Integration.slug == slug,
            )
            .order_by(Connector.created_at.desc())
        )
        return self.session.execute(stmt).scalars().first()
