from __future__ import annotations

import uuid

from sqlalchemy import select, text

from app.integrations.models.mcp_server import MCPEvent
from app.system.repositories.base import BaseRepository


class MCPEventsRepository(BaseRepository):
    def append(
        self,
        *,
        tenant_id: uuid.UUID,
        server_id: uuid.UUID,
        event_type: str,
        payload: dict,
        user_id: uuid.UUID | None = None,
    ) -> MCPEvent:
        self.apply_tenant_scope(tenant_id)
        # Serialize sequence allocation for concurrent lifecycle/tool workers.
        self.db.execute(
            text("SELECT pg_advisory_xact_lock(hashtext(:server_id))"),
            {"server_id": str(server_id)},
        )
        last = self.db.execute(
            select(MCPEvent.sequence)
            .where(MCPEvent.tenant_id == tenant_id, MCPEvent.server_id == server_id)
            .order_by(MCPEvent.sequence.desc())
            .limit(1)
        ).scalar_one_or_none()
        event = MCPEvent(
            tenant_id=tenant_id,
            user_id=user_id,
            server_id=server_id,
            event_type=event_type,
            sequence=int(last or 0) + 1,
            payload=payload,
        )
        self.db.add(event)
        self.db.flush()
        return event

    def list_since(
        self,
        *,
        tenant_id: uuid.UUID,
        server_id: uuid.UUID,
        sequence: int = 0,
        limit: int = 500,
    ) -> list[MCPEvent]:
        self.apply_tenant_scope(tenant_id)
        statement = (
            select(MCPEvent)
            .where(
                MCPEvent.tenant_id == tenant_id,
                MCPEvent.server_id == server_id,
                MCPEvent.sequence > sequence,
            )
            .order_by(MCPEvent.sequence.asc())
            .limit(min(max(limit, 1), 1000))
        )
        return list(self.db.execute(statement).scalars().all())
