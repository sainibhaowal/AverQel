import asyncio

from sqlalchemy import select

from app.db.session import get_session_factory
from app.models.providers.provider_config import ProviderConfig


async def check_configs():
    factory = get_session_factory()
    db = factory()
    try:
        stmt = select(ProviderConfig)
        configs = db.execute(stmt).scalars().all()

        if not configs:
            print("No provider configs found.")
        else:
            for c in configs:
                # Print all attributes to see what we have
                attrs = {k: v for k, v in vars(c).items() if not k.startswith("_")}
                print(f" - Config: {attrs}")

    finally:
        db.close()


if __name__ == "__main__":
    asyncio.run(check_configs())
