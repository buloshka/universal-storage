from typing import Any, Generic, Literal, TypeVar, overload
from uuid import UUID

from pydantic import BaseModel
from sqlalchemy import delete as sa_delete
from sqlalchemy import select
from sqlalchemy import update as sa_update
from sqlalchemy.ext.asyncio import AsyncSession

from storage.adapters.sql.models import SQLBaseModel
from storage.core.entity import utc_now
from storage.core.repository import BaseRepository
from storage.exceptions import ConcurrencyError, NotFoundError

ModelT = TypeVar("ModelT", bound=SQLBaseModel)
EntityT = TypeVar("EntityT", bound=BaseModel)
CreateSchemaT = TypeVar("CreateSchemaT", bound=BaseModel)
UpdateSchemaT = TypeVar("UpdateSchemaT", bound=BaseModel)


class SQLRepository(
    BaseRepository[EntityT, CreateSchemaT, UpdateSchemaT],
    Generic[ModelT, EntityT, CreateSchemaT, UpdateSchemaT],
):
    """
    Generic asynchronous repository for SQLAlchemy 2.0 models.
    Automatically maps ORM rows to Pydantic entities and enforces optimistic concurrency control.
    """

    model: type[ModelT]
    entity_schema: type[EntityT]

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def _to_entity(self, instance: ModelT) -> EntityT:
        """Convert an ORM model instance into a validated Pydantic entity."""
        return self.entity_schema.model_validate(instance, from_attributes=True)

    async def get_by(self, *, raise_not_found: bool = False, **filters: Any) -> EntityT | None:
        stmt = select(self.model).filter_by(**filters)
        result = await self._session.execute(stmt)
        instance = result.scalar_one_or_none()

        if instance is None:
            if raise_not_found:
                raise NotFoundError(f"{self.model.__name__} matching {filters} was not found.")
            return None

        return self._to_entity(instance)

    async def get_for_update(self, entity_id: UUID | str) -> EntityT:
        """
        Acquire a row-level pessimistic lock (SELECT ... FOR UPDATE) within the active transaction.
        Raises NotFoundError if the record does not exist.
        """
        stmt = select(self.model).where(self.model.id == entity_id).with_for_update()
        result = await self._session.execute(stmt)
        instance = result.scalar_one_or_none()

        if instance is None:
            raise NotFoundError(f"{self.model.__name__} with id={entity_id} was not found.")

        return self._to_entity(instance)

    async def list(self, *, limit: int = 100, offset: int = 0, **filters: Any) -> list[EntityT]:
        stmt = select(self.model).filter_by(**filters).limit(limit).offset(offset)
        result = await self._session.execute(stmt)
        return [self._to_entity(row) for row in result.scalars().all()]

    async def create(self, schema: CreateSchemaT) -> EntityT:
        instance = self.model(**schema.model_dump())
        self._session.add(instance)
        await self._session.flush()
        await self._session.refresh(instance)
        return self._to_entity(instance)

    async def update(
        self,
        entity_id: UUID | str,
        schema: UpdateSchemaT,
        *,
        expected_version: int | None = None,
    ) -> EntityT:
        update_data = schema.model_dump(exclude_unset=True)
        update_data["updated_at"] = utc_now()

        stmt = sa_update(self.model).where(self.model.id == entity_id)

        if expected_version is not None:
            stmt = stmt.where(self.model.version == expected_version)
            update_data["version"] = expected_version + 1
        else:
            update_data["version"] = self.model.version + 1

        stmt = stmt.values(**update_data).returning(self.model)
        result = await self._session.execute(stmt)
        updated_instance = result.scalar_one_or_none()

        if updated_instance is None:
            exists_stmt = select(self.model.id).where(self.model.id == entity_id)
            exists = (await self._session.execute(exists_stmt)).scalar_one_or_none()
            if exists is None:
                raise NotFoundError(f"{self.model.__name__} with id={entity_id} was not found.")
            raise ConcurrencyError(
                f"Version conflict while updating {self.model.__name__} id={entity_id}: "
                f"expected version {expected_version}."
            )

        return self._to_entity(updated_instance)

    async def delete(
        self,
        entity_id: UUID | str,
        *,
        expected_version: int | None = None,
    ) -> None:
        stmt = sa_delete(self.model).where(self.model.id == entity_id)
        if expected_version is not None:
            stmt = stmt.where(self.model.version == expected_version)

        result = await self._session.execute(stmt)

        if result.rowcount == 0:
            exists_stmt = select(self.model.id).where(self.model.id == entity_id)
            exists = (await self._session.execute(exists_stmt)).scalar_one_or_none()
            if exists is None:
                raise NotFoundError(f"{self.model.__name__} with id={entity_id} was not found.")
            raise ConcurrencyError(
                f"Version conflict while deleting {self.model.__name__} id={entity_id}: "
                f"expected version {expected_version}."
            )
