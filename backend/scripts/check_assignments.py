import asyncio

from sqlalchemy import select

from app.auth.models.tenant import Tenant
from app.platform.database.session import get_session_factory
from app.providers.models.provider_assignment import ProviderAssignment


async def check_assignments():
    factory = get_session_factory()
    db = factory()
    try:
        # Get first tenant
        stmt_tenant = select(Tenant)
        tenant = db.execute(stmt_tenant).scalars().first()
        if not tenant:
            print("No tenants found")
            return

        print(f"Checking assignments for Tenant: {tenant.name} ({tenant.id})")

        stmt = select(ProviderAssignment).where(ProviderAssignment.tenant_id == tenant.id)
        assignments = db.execute(stmt).scalars().all()

        if not assignments:
            print("No provider assignments found for this tenant.")
        else:
            for a in assignments:
                print(
                    f" - Scope: {a.feature_scope}, Provider: {a.provider_id}, Status: {a.is_active}"
                )

    finally:
        db.close()


if __name__ == "__main__":
    asyncio.run(check_assignments())
