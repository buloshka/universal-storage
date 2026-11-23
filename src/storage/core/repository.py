from abc import ABC, abstractmethod
from typing import Any, Generic, Literal, TypeVar, overload
from uuid import UUID

from pydantic import BaseModel


EntityT = TypeVar("EntityT", bound=BaseModel)
CreateSchemaT = TypeVar("CreateSchemaT", bound=BaseModel)
UpdateSchemaT = TypeVar("UpdateSchemaT", bound=BaseModel)


class BaseRepository(ABC, Generic[EntityT, CreateSchemaT, UpdateSchemaT]):
    """Unified CRUD contract for relational and non-relational repositories."""

    @overload
    async def get_by(self, *, raise_not_found: Literal[True], **filters: Any) -> EntityT: ...

    @overload
    async def get_by(self, *, raise_not_found: Literal[False] = ..., **filters: Any) -> EntityT | None: ...

    @abstractmethod
    async def get_by(self, *, raise_not_found: bool = False, **filters: Any) -> EntityT | None:
        """
        Retrieve a single entity matching the given field filters (e.g., id=..., email=...).

        Args:
            raise_not_found: If True, raises NotFoundError instead of returning None.
            **filters: Field-value pairs to match against.

        Returns:
            The matched entity, or None if not found and raise_not_found is False.

        Raises:
            NotFoundError: If no matching entity is found and raise_not_found is True.
        """

    @abstractmethod
    async def list(self, *, limit: int = 100, offset: int = 0, **filters: Any) -> list[EntityT]:
        """Retrieve a paginated list of entities matching optional filters."""

    @abstractmethod
    async def create(self, schema: CreateSchemaT) -> EntityT:
        """Create and persist a new entity from the creation schema."""

    @abstractmethod
    async def update(
        self,
        entity_id: UUID | str,
        schema: UpdateSchemaT,
        *,
        expected_version: int | None = None,
    ) -> EntityT:
        """
        Update an existing entity by ID.

        Args:
            entity_id: Primary identifier of the entity.
            schema: Partial or full update schema.
            expected_version: Optional version number for optimistic locking.

        Raises:
            NotFoundError: If the entity does not exist.
            ConcurrencyError: If expected_version does not match the stored version.
        """

    @abstractmethod
    async def delete(
        self,
        entity_id: UUID | str,
        *,
        expected_version: int | None = None,
    ) -> None:
        """
        Delete an existing entity by ID.

        Args:
            entity_id: Primary identifier of the entity.
            expected_version: Optional version number to prevent deleting a modified record.

        Raises:
            NotFoundError: If the entity does not exist.
            ConcurrencyError: If expected_version does not match the stored version.
        """
