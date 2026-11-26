from typing import Any, Generic, TypeVar
from uuid import UUID

from pydantic import BaseModel
from pymongo import ReturnDocument

from storage.adapters.mongo.models import MongoBaseModel
from storage.core.entity import utc_now
from storage.core.repository import BaseRepository
from storage.exceptions import ConcurrencyError, NotFoundError

DocT = TypeVar("DocT", bound=MongoBaseModel)
EntityT = TypeVar("EntityT", bound=BaseModel)
CreateSchemaT = TypeVar("CreateSchemaT", bound=BaseModel)
UpdateSchemaT = TypeVar("UpdateSchemaT", bound=BaseModel)


class MongoRepository(
    BaseRepository[EntityT, CreateSchemaT, UpdateSchemaT],
    Generic[DocT, EntityT, CreateSchemaT, UpdateSchemaT],
):
    """
    Generic asynchronous repository for MongoDB via Beanie ODM.
    Enforces atomic optimistic concurrency control using MongoDB's $inc operator.
    """

    model: type[DocT]
    entity_schema: type[EntityT]

    def _to_entity(self, document: DocT | dict[str, Any]) -> EntityT:
        """Convert a Beanie Document or raw BSON dict into a validated Pydantic entity."""
        if isinstance(document, dict):
            data = dict(document)
            if "_id" in data and "id" not in data:
                data["id"] = data.pop("_id")
            return self.entity_schema.model_validate(data)
        return self.entity_schema.model_validate(document.model_dump())

    @staticmethod
    def _normalize_filters(filters: dict[str, Any]) -> dict[str, Any]:
        """Map 'id' filter key to MongoDB's native '_id' field."""
        normalized = dict(filters)
        if "id" in normalized:
            normalized["_id"] = normalized.pop("id")
        return normalized

    async def get_by(self, *, raise_not_found: bool = False, **filters: Any) -> EntityT | None:
        query = self._normalize_filters(filters)
        document = await self.model.find_one(query)

        if document is None:
            if raise_not_found:
                raise NotFoundError(f"{self.model.__name__} matching {filters} was not found.")
            return None

        return self._to_entity(document)

    async def list(self, *, limit: int = 100, offset: int = 0, **filters: Any) -> list[EntityT]:
        query = self._normalize_filters(filters)
        documents = await self.model.find(query).skip(offset).limit(limit).to_list()
        return [self._to_entity(doc) for doc in documents]

    async def create(self, schema: CreateSchemaT) -> EntityT:
        document = self.model(**schema.model_dump())
        await document.insert()
        return self._to_entity(document)

    async def update(
        self,
        entity_id: UUID | str,
        schema: UpdateSchemaT,
        *,
        expected_version: int | None = None,
    ) -> EntityT:
        update_data = schema.model_dump(exclude_unset=True)
        update_data["updated_at"] = utc_now()

        query: dict[str, Any] = {"_id": entity_id}
        if expected_version is not None:
            query["version"] = expected_version

        collection = self.model.get_motor_collection()
        updated_raw = await collection.find_one_and_update(
            query,
            {
                "$set": update_data,
                "$inc": {"version": 1},
            },
            return_document=ReturnDocument.AFTER,
        )

        if updated_raw is None:
            exists = await collection.find_one({"_id": entity_id}, {"_id": 1})
            if exists is None:
                raise NotFoundError(f"{self.model.__name__} with id={entity_id} was not found.")
            raise ConcurrencyError(
                f"Version conflict while updating {self.model.__name__} id={entity_id}: "
                f"expected version {expected_version}."
            )

        return self._to_entity(updated_raw)

    async def delete(
        self,
        entity_id: UUID | str,
        *,
        expected_version: int | None = None,
    ) -> None:
        query: dict[str, Any] = {"_id": entity_id}
        if expected_version is not None:
            query["version"] = expected_version

        collection = self.model.get_motor_collection()
        result = await collection.delete_one(query)

        if result.deleted_count == 0:
            exists = await collection.find_one({"_id": entity_id}, {"_id": 1})
            if exists is None:
                raise NotFoundError(f"{self.model.__name__} with id={entity_id} was not found.")
            raise ConcurrencyError(
                f"Version conflict while deleting {self.model.__name__} id={entity_id}: "
                f"expected version {expected_version}."
            )
