from datetime import datetime, timezone
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


def utc_now() -> datetime:
    """Return the current UTC datetime."""
    return datetime.now(timezone.utc)


class BaseEntity(BaseModel):
    """
    Base entity model with optimistic locking support.

    This model provides standard fields for identification, auditing, and
    concurrency control. The `version` field is used to prevent lost updates
    in concurrent scenarios (e.g., multiple workers processing the same task).
    """

    id: UUID = Field(
        default_factory=uuid4,
        description="Unique identifier for the entity."
    )
    created_at: datetime = Field(
        default_factory=utc_now,
        description="Timestamp when the entity was created (UTC)."
    )
    updated_at: datetime = Field(
        default_factory=utc_now,
        description="Timestamp of the last update to the entity (UTC)."
    )
    version: int = Field(
        default=1,
        ge=1,
        description=(
            "Concurrency version number for optimistic locking. "
            "Incremented on each successful update; used to detect "
            "conflicting concurrent modifications."
        )
    )
