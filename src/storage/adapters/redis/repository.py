from typing import Any, Generic, TypeVar
from uuid import UUID

from pydantic import BaseModel
from redis.asyncio import Redis
from redis.exceptions import WatchError

from storage.core.entity import BaseEntity, utc_now
from storage.core.repository import BaseRepository
from storage.exceptions import ConcurrencyError, NotFoundError

EntityT = TypeVar("EntityT", bound=BaseEntity)
CreateSchemaT = TypeVar("CreateSchemaT", bound=BaseModel)
UpdateSchemaT = TypeVar("UpdateSchemaT", bound=BaseModel)


class RedisRepository(
    BaseRepository[EntityT, CreateSchemaT, UpdateSchemaT],
    Generic[EntityT, CreateSchemaT, UpdateSchemaT],
):
    """
    Generic asynchronous Key-Value repository for Redis.
    Stores Pydantic entities as JSON strings, supports TTL, and enforces optimistic locking via WATCH/MULTI.
    """

    entity_schema: type[EntityT]
    key_prefix: str
    default_ttl: int | None = None

    def __init__(self, client: Redis) -> None:
        self._client = client

    def _build_key(self, entity_id: UUID | str) -> str:
        """Construct the namespaced Redis key for an entity ID."""
        return f"{self.key_prefix}:{entity_id}"

    def _deserialize(self, raw_data: str | bytes) -> EntityT:
        """Validate and deserialize raw JSON from Redis into the target Pydantic entity."""
        return self.entity_schema.model_validate_json(raw_data)

    @staticmethod
    def _matches_filters(entity: EntityT, filters: dict[str, Any]) -> bool:
        """Check whether an entity matches all provided field-value filters."""
        for field, expected_value in filters.items():
            if not hasattr(entity, field) or getattr(entity, field) != expected_value:
                return False
        return True

    async def get_by(self, *, raise_not_found: bool = False, **filters: Any) -> EntityT | None:
        if "id" in filters and len(filters) == 1:
            raw = await self._client.get(self._build_key(filters["id"]))
            if raw is None:
                if raise_not_found:
                    raise NotFoundError(f"{self.entity_schema.__name__} with id={filters['id']} was not found.")
                return None
            return self._deserialize(raw)

        async for key in self._client.scan_iter(match=f"{self.key_prefix}:*"):
            raw = await self._client.get(key)
            if raw is None:
                continue
            entity = self._deserialize(raw)
            if self._matches_filters(entity, filters):
                return entity

        if raise_not_found:
            raise NotFoundError(f"{self.entity_schema.__name__} matching {filters} was not found.")
        return None

    async def list(self, *, limit: int = 100, offset: int = 0, **filters: Any) -> list[EntityT]:
        if limit == 0:
            return []

        matched: list[EntityT] = []
        skipped = 0

        async for key in self._client.scan_iter(match=f"{self.key_prefix}:*"):
            raw = await self._client.get(key)
            if raw is None:
                continue

            entity = self._deserialize(raw)
            if filters and not self._matches_filters(entity, filters):
                continue

            if skipped != offset:
                skipped += 1
                continue

            matched.append(entity)

            if len(matched) == limit:
                break

        return matched

    async def create(self, schema: CreateSchemaT, *, ttl: int | None = None) -> EntityT:
        entity = self.entity_schema(**schema.model_dump())
        key = self._build_key(entity.id)
        effective_ttl = ttl if ttl is not None else self.default_ttl

        await self._client.set(key, entity.model_dump_json(), ex=effective_ttl)
        return entity

    async def update(
        self,
        entity_id: UUID | str,
        schema: UpdateSchemaT,
        *,
        expected_version: int | None = None,
        ttl: int | None = None,
    ) -> EntityT:
        key = self._build_key(entity_id)

        async with self._client.pipeline(transaction=True) as pipe:
            try:
                await pipe.watch(key)
                raw = await self._client.get(key)

                if raw is None:
                    await pipe.unwatch()
                    raise NotFoundError(f"{self.entity_schema.__name__} with id={entity_id} was not found.")

                current_entity = self._deserialize(raw)

                if expected_version is not None and current_entity.version != expected_version:
                    await pipe.unwatch()
                    raise ConcurrencyError(
                        f"Version conflict while updating {self.entity_schema.__name__} id={entity_id}: "
                        f"expected version {expected_version}, got {current_entity.version}."
                    )

                update_data = schema.model_dump(exclude_unset=True)
                update_data["updated_at"] = utc_now()
                update_data["version"] = current_entity.version + 1

                updated_entity = current_entity.model_copy(update=update_data)
                remaining_pttl = await self._client.pttl(key)

                pipe.multi()
                if ttl is not None:
                    await pipe.set(key, updated_entity.model_dump_json(), ex=ttl)
                elif remaining_pttl > 0:
                    await pipe.set(key, updated_entity.model_dump_json(), px=remaining_pttl)
                else:
                    await pipe.set(key, updated_entity.model_dump_json())

                await pipe.execute()
                return updated_entity

            except WatchError as exc:
                raise ConcurrencyError(
                    f"Concurrent modification detected in Redis for {self.entity_schema.__name__} id={entity_id}."
                ) from exc

    async def delete(
        self,
        entity_id: UUID | str,
        *,
        expected_version: int | None = None,
    ) -> None:
        key = self._build_key(entity_id)

        if expected_version is None:
            deleted_count = await self._client.delete(key)
            if deleted_count == 0:
                raise NotFoundError(f"{self.entity_schema.__name__} with id={entity_id} was not found.")
            return

        async with self._client.pipeline(transaction=True) as pipe:
            try:
                await pipe.watch(key)
                raw = await self._client.get(key)

                if raw is None:
                    await pipe.unwatch()
                    raise NotFoundError(f"{self.entity_schema.__name__} with id={entity_id} was not found.")

                current_entity = self._deserialize(raw)
                if current_entity.version != expected_version:
                    await pipe.unwatch()
                    raise ConcurrencyError(
                        f"Version conflict while deleting {self.entity_schema.__name__} id={entity_id}: "
                        f"expected version {expected_version}, got {current_entity.version}."
                    )

                pipe.multi()
                await pipe.delete(key)
                await pipe.execute()

            except WatchError as exc:
                raise ConcurrencyError(
                    f"Concurrent deletion conflict in Redis for {self.entity_schema.__name__} id={entity_id}."
                ) from exc
