from __future__ import annotations

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, LargeBinary, SmallInteger, String, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.platform.database.base import Base


class ComposioCredential(Base):
    """Encrypted platform Composio project key, configured by a platform admin."""

    __tablename__ = "composio_credentials"
    __table_args__ = (CheckConstraint("id = 1", name="ck_composio_credentials_singleton"),)

    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True, default=1)
    secret_ciphertext: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    secret_nonce: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    secret_kid: Mapped[str] = mapped_column(String(128), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
        onupdate=func.now(),
    )
