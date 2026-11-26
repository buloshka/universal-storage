from datetime import datetime
from uuid import UUID, uuid4

from beanie import Document
from pydantic import Field

from storage.core.entity import utc_now


class MongoBaseModel(Document):
    """
    Base Beanie document model for MongoDB collections.
    Uses UUID as primary '_id' field and tracks UTC timestamps and record version.
    """

    id: UUID = Field(default_factory=uuid4)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    version: int = Field(
        default=1,
        ge=1,
        description="Record version for optimistic concurrency control"
    )
