from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, Integer, Uuid
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from storage.core.entity import utc_now


class SQLBaseModel(DeclarativeBase):
    """
    Base declarative model for all relational database tables.
    Provides UUID primary key, UTC timestamps, and a version column for optimistic locking.
    """

    __abstract__ = True

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
    )
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
