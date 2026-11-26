import asyncio
from collections.abc import AsyncGenerator

import pytest
from pydantic import BaseModel
from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from storage.adapters.sql import (
    SQLBaseModel,
    SQLRepository,
    SQLSessionManager,
    SQLStorageConfig,
    SQLUnitOfWork,
)
from storage.core import BaseEntity
from storage.exceptions import ConcurrencyError, NotFoundError


class ItemModel(SQLBaseModel):
    """Test SQLAlchemy ORM model."""

    __tablename__ = "test_items"

    name: Mapped[str] = mapped_column(String(100), nullable=False)
    quantity: Mapped[int] = mapped_column(default=0, nullable=False)


class ItemEntity(BaseEntity):
    """Test Pydantic domain entity."""

    name: str
    quantity: int


class ItemCreate(BaseModel):
    """Schema for creating an item."""

    name: str
    quantity: int = 0


class ItemUpdate(BaseModel):
    """Schema for updating an item."""

    name: str | None = None
    quantity: int | None = None


class ItemRepository(SQLRepository[ItemModel, ItemEntity, ItemCreate, ItemUpdate]):
    """Concrete repository for ItemModel."""

    model = ItemModel
    entity_schema = ItemEntity


@pytest.fixture
async def session_manager() -> AsyncGenerator[SQLSessionManager, None]:
    """Provide an isolated in-memory SQLite session manager with initialized tables."""
    config = SQLStorageConfig(dsn="sqlite+aiosqlite:///:memory:")
    manager = SQLSessionManager(config)

    async with manager.engine.begin() as conn:
        await conn.run_sync(SQLBaseModel.metadata.create_all)

    yield manager
    await manager.close()


async def test_sql_crud_lifecycle(session_manager: SQLSessionManager) -> None:
    """Verify create, get_by, list, update (with auto-version increment), and delete."""
    uow = SQLUnitOfWork(session_manager.session_factory)

    async with uow:
        repo = ItemRepository(uow.session)
        created = await repo.create(ItemCreate(name="Laptop", quantity=5))
        assert created.name == "Laptop"
        assert created.quantity == 5
        assert created.version == 1

    async with uow:
        repo = ItemRepository(uow.session)
        fetched = await repo.get_by(id=created.id, raise_not_found=True)
        assert fetched.id == created.id

        updated = await repo.update(created.id, ItemUpdate(quantity=10))
        assert updated.quantity == 10
        assert updated.version == 2

    async with uow:
        repo = ItemRepository(uow.session)
        items = await repo.list()
        assert len(items) == 1
        assert items[0].version == 2

        await repo.delete(created.id)

    async with uow:
        repo = ItemRepository(uow.session)
        missing = await repo.get_by(id=created.id)
        assert missing is None


async def test_get_by_raise_not_found(session_manager: SQLSessionManager) -> None:
    """Verify get_by raises NotFoundError when raise_not_found=True and record is missing."""
    uow = SQLUnitOfWork(session_manager.session_factory)

    async with uow:
        repo = ItemRepository(uow.session)
        with pytest.raises(NotFoundError):
            await repo.get_by(name="NonExistent", raise_not_found=True)


async def test_optimistic_locking_concurrency_conflict(session_manager: SQLSessionManager) -> None:
    """
    Simulate two concurrent workers reading the same entity version and attempting to update it.
    The first worker succeeds; the second worker must receive ConcurrencyError.
    """
    uow = SQLUnitOfWork(session_manager.session_factory)

    async with uow:
        repo = ItemRepository(uow.session)
        item = await repo.create(ItemCreate(name="Limited Ticket", quantity=1))
        initial_version = item.version

    async def worker_update(new_qty: int) -> ItemEntity:
        worker_uow = SQLUnitOfWork(session_manager.session_factory)
        async with worker_uow:
            worker_repo = ItemRepository(worker_uow.session)
            return await worker_repo.update(
                item.id,
                ItemUpdate(quantity=new_qty),
                expected_version=initial_version,
            )

    results = await asyncio.gather(
        worker_update(0),
        worker_update(0),
        return_exceptions=True,
    )

    successes = [r for r in results if isinstance(r, ItemEntity)]
    errors = [r for r in results if isinstance(r, ConcurrencyError)]

    assert len(successes) == 1
    assert successes[0].version == initial_version + 1
    assert len(errors) == 1


async def test_optimistic_locking_on_delete(session_manager: SQLSessionManager) -> None:
    """Verify delete with stale expected_version raises ConcurrencyError and preserves the record."""
    uow = SQLUnitOfWork(session_manager.session_factory)

    async with uow:
        repo = ItemRepository(uow.session)
        item = await repo.create(ItemCreate(name="Protected Doc", quantity=1))
        await repo.update(item.id, ItemUpdate(quantity=2))

    async with uow:
        repo = ItemRepository(uow.session)
        with pytest.raises(ConcurrencyError):
            await repo.delete(item.id, expected_version=1)

        still_exists = await repo.get_by(id=item.id, raise_not_found=True)
        assert still_exists.version == 2
