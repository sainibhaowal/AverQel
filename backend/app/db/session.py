from __future__ import annotations

import logging
import time
from collections.abc import Generator
from functools import lru_cache
from uuid import UUID

from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings
from app.system.services.metrics_service import DB_CONNECTION_CHECKOUT_DURATION_SECONDS

logger = logging.getLogger(__name__)


def _observe_checkout_duration(duration_seconds: float) -> None:
    """Record DB checkout timing without breaking request flow."""
    try:
        DB_CONNECTION_CHECKOUT_DURATION_SECONDS.observe(duration_seconds)
    except Exception:  # noqa: BLE001
        logger.debug("DB checkout metric observation failed.", exc_info=True)


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    """Create and cache the SQLAlchemy engine."""
    settings = get_settings()
    return create_engine(
        settings.database_url,
        pool_pre_ping=True,
        pool_recycle=1800,
        pool_size=10,
        max_overflow=20,
        pool_timeout=30,
    )


@lru_cache(maxsize=1)
def get_session_factory() -> sessionmaker[Session]:
    """Create and cache the SQLAlchemy session factory."""
    return sessionmaker(
        bind=get_engine(),
        autocommit=False,
        autoflush=False,
        expire_on_commit=False,
    )


def SessionLocal() -> Session:  # noqa: N802
    """Compatibility alias for get_session_factory()()."""
    return get_session_factory()()


def get_db() -> Generator[Session, None, None]:
    """Yield a request-scoped database session with role setup and cleanup."""
    checkout_start = time.perf_counter()
    db = get_session_factory()()
    _observe_checkout_duration(time.perf_counter() - checkout_start)

    role_applied = False

    try:
        db.execute(text("SET ROLE aks_app"))
        role_applied = True
        yield db
    finally:
        try:
            db.rollback()
        except Exception:  # noqa: BLE001
            logger.debug("Session rollback during cleanup failed.", exc_info=True)

        if role_applied:
            try:
                db.execute(text("RESET ROLE"))
                db.commit()
            except Exception:  # noqa: BLE001
                logger.debug("RESET ROLE during cleanup failed.", exc_info=True)
                try:
                    db.rollback()
                except Exception:  # noqa: BLE001
                    logger.debug(
                        "Session rollback after RESET ROLE failure failed.",
                        exc_info=True,
                    )

        try:
            db.close()
        except Exception:  # noqa: BLE001
            logger.warning("Database session close failed.", exc_info=True)


def set_db_tenant_context(db: Session, tenant_id: UUID | str) -> None:
    """Bind tenant id into the current DB session context."""
    db.execute(
        text("SELECT set_config('app.tenant_id', :tenant_id, true)"),
        {"tenant_id": str(tenant_id)},
    )


def reset_db_state() -> None:
    """Clear cached DB engine and session factory state."""
    get_session_factory.cache_clear()
    get_engine.cache_clear()
