from collections.abc import AsyncGenerator
from uuid import UUID

import fakeredis.aioredis
import pytest
from beanie import init_beanie
from mongomock_motor import AsyncMongoMockClient
from pydantic import BaseModel

from storage.adapters.mongo import MongoBaseModel, MongoRepository
from storage.adapters.redis import RedisRepository
from storage.core import BaseEntity
from storage.exceptions import ConcurrencyError, NotFoundError


# --- Shared Schemas & Entities ---


class AccountEntity(BaseEntity):
    """Domain entity for testing NoSQL repositories."""

    owner: str
    balance: int


class AccountCreate(BaseModel):
    """Schema for creating an account."""

    owner: str
    balance: int = 0


class AccountUpdate(BaseModel):
    """Schema for updating an account."""

    owner: str | None = None
    balance: int | None = None


# --- MongoDB Setup & Tests ---


class AccountDocument(MongoBaseModel):
    """Beanie document model for MongoDB tests."""

    owner: str
    balance: int

    class Settings:
        name = "test_accounts"


class AccountMongoRepository(MongoRepository[AccountDocument, AccountEntity, AccountCreate, AccountUpdate]):
    """Concrete MongoDB repository."""

    model = AccountDocument
    entity_schema = AccountEntity


@pytest.fixture
async def init_mock_mongo() -> AsyncGenerator[None, None]:
    """Initialize Beanie ODM backed by an in-memory MongoDB mock client."""
    client = AsyncMongoMockClient()
    await init_beanie(database=client["test_db"], document_models=[AccountDocument])
    yield
    client.close()


async def test_mongo_crud_and_optimistic_locking(init_mock_mongo: None) -> None:
    """Verify MongoRepository CRUD lifecycle, get_by(raise_not_found=True), and version conflict detection."""
    repo = AccountMongoRepository()

    created = await repo.create(AccountCreate(owner="Alice", balance=100))
    assert created.version == 1
    assert isinstance(created.id, UUID)

    fetched = await repo.get_by(owner="Alice", raise_not_found=True)
    assert fetched.id == created.id

    updated = await repo.update(created.id, AccountUpdate(balance=150), expected_version=1)
    assert updated.balance == 150
    assert updated.version == 2

    with pytest.raises(ConcurrencyError):
        await repo.update(created.id, AccountUpdate(balance=200), expected_version=1)

    with pytest.raises(ConcurrencyError):
        await repo.delete(created.id, expected_version=1)

    await repo.delete(created.id, expected_version=2)

    with pytest.raises(NotFoundError):
        await repo.get_by(id=created.id, raise_not_found=True)


# --- Redis Setup & Tests ---


class AccountRedisRepository(RedisRepository[AccountEntity, AccountCreate, AccountUpdate]):
    """Concrete Redis Key-Value repository."""

    entity_schema = AccountEntity
    key_prefix = "test:account"
    default_ttl = 300


@pytest.fixture
async def redis_repo() -> AsyncGenerator[AccountRedisRepository, None]:
    """Provide a RedisRepository backed by an in-memory FakeRedis async client."""
    client = fakeredis.aioredis.FakeRedis(decode_responses=True)
    yield AccountRedisRepository(client)
    await client.aclose()


async def test_redis_crud_ttl_and_optimistic_locking(redis_repo: AccountRedisRepository) -> None:
    """Verify RedisRepository CRUD, TTL preservation, and WATCH/MULTI optimistic locking."""
    created = await redis_repo.create(AccountCreate(owner="Bob", balance=500))
    assert created.version == 1

    fetched = await redis_repo.get_by(id=created.id, raise_not_found=True)
    assert fetched.owner == "Bob"

    updated = await redis_repo.update(created.id, AccountUpdate(balance=750), expected_version=1)
    assert updated.balance == 750
    assert updated.version == 2

    with pytest.raises(ConcurrencyError):
        await redis_repo.update(created.id, AccountUpdate(balance=0), expected_version=1)

    items = await redis_repo.list(owner="Bob")
    assert len(items) == 1
    assert items[0].version == 2

    await redis_repo.delete(created.id, expected_version=2)

    assert await redis_repo.get_by(id=created.id) is None
