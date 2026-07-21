import asyncio

from sqlalchemy import select

from app.platform.database.session import get_session_factory
from app.providers.models.provider_config import ProviderConfig


async def check_providers():
    factory = get_session_factory()
    db = factory()
    try:
        stmt = select(ProviderConfig)
        providers = db.execute(stmt).scalars().all()

        for p in providers:
            print(
                f"Provider: {p.provider_type}, Enabled: {p.enabled}, URL: {p.api_base_url}, ID: {p.id}"
            )

    finally:
        db.close()


if __name__ == "__main__":
    asyncio.run(check_providers())
