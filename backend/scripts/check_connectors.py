import asyncio

from sqlalchemy import select

from app.db.session import get_session_factory
from app.models.integrations.connector import Connector


async def check_connectors():
    factory = get_session_factory()
    db = factory()
    try:
        stmt = select(Connector)
        connectors = db.execute(stmt).scalars().all()

        if not connectors:
            print("No connectors found.")
        else:
            for c in connectors:
                attrs = {k: v for k, v in vars(c).items() if not k.startswith("_")}
                print(f" - Connector: {attrs}")

    finally:
        db.close()


if __name__ == "__main__":
    asyncio.run(check_connectors())
