# Universal Storage

An asynchronous, modular storage library built on **Pydantic v2** and designed for reuse across Python projects via `uv`. Implements the **Repository** and **Unit of Work** patterns with built-in **Optimistic Concurrency Control** (`version` tracking) across both relational and non-relational databases.

## Features

- **Unified CRUD Contract (`BaseRepository`)**: Consistent async interface (`get_by`, `list`, `create`, `update`, `delete`) with type-safe `@overload` on `get_by(..., raise_not_found=True/False)`.
- **Built-in Concurrency Protection**:
  - **SQL (SQLAlchemy 2.0)**: Atomic `UPDATE ... WHERE version = X` (Optimistic Lock) and `SELECT ... FOR UPDATE` (`get_for_update` Pessimistic Lock).
  - **MongoDB (Beanie ODM)**: Atomic `find_one_and_update` with `$inc: {"version": 1}`.
  - **Redis (`redis.asyncio`)**: Optimistic transactions via `WATCH / MULTI / EXEC` and distributed locking (`RedisClientManager.lock`).
- **Modular Extras**: Install only the database drivers needed for your target project.
- **Async Alembic Scaffolding**: Built-in CLI command `storage-init-alembic` to bootstrap async migrations in seconds.

---

## Installation (via `uv`)

Pin a specific release tag (e.g., `v0.1.0`) in your target project:

```bash
# PostgreSQL + Redis
uv add "universal-storage[postgres,redis] @ git+https://github.com<your-username>/universal-storage.git@v0.1.0"

# MongoDB only
uv add "universal-storage[mongo] @ git+https://github.com<your-username>/universal-storage.git@v0.1.0"

# SQLite only
uv add "universal-storage[sqlite] @ git+https://github.com<your-username>/universal-storage.git@v0.1.0"
```

Available extras: `sql`, `postgres`, `sqlite`, `mysql`, `mongo`, `redis`, `all`.

---

## Quick Start Examples

### 1. Relational Databases (SQLAlchemy 2.0 Async)

```python
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


# 1. Define ORM Model (inherits id, created_at, updated_at, version)
class UserModel(SQLBaseModel):
    __tablename__ = "users"
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)


# 2. Define Pydantic Entity & DTOs
class UserEntity(BaseEntity):
    email: str


class UserCreate(BaseModel):
    email: str


class UserUpdate(BaseModel):
    email: str | None = None


# 3. Define Repository
class UserRepository(SQLRepository[UserModel, UserEntity, UserCreate, UserUpdate]):
    model = UserModel
    entity_schema = UserEntity


# 4. Usage with Unit of Work
async def main() -> None:
    config = SQLStorageConfig(dsn="postgresql+asyncpg://user:pass@localhost:5432/db")
    manager = SQLSessionManager(config)
    uow = SQLUnitOfWork(manager.session_factory)

    async with uow:
        repo = UserRepository(uow.session)
        user = await repo.create(UserCreate(email="dev@example.com"))

        # Optimistic locking: raises ConcurrencyError if version changed concurrently
        updated = await repo.update(
            user.id,
            UserUpdate(email="new@example.com"),
            expected_version=user.version,
        )

    await manager.close()
```

#### Initializing Async Alembic Migrations
Run inside your target project root:
```bash
uv run storage-init-alembic
uv run alembic revision --autogenerate -m "initial"
uv run alembic upgrade head
```

---

### 2. MongoDB (Beanie ODM)

```python
from pydantic import BaseModel

from storage.adapters.mongo import (
    MongoBaseModel,
    MongoClientManager,
    MongoRepository,
    MongoStorageConfig,
)
from storage.core import BaseEntity


class OrderDocument(MongoBaseModel):
    total: float

    class Settings:
        name = "orders"


class OrderEntity(BaseEntity):
    total: float


class OrderCreate(BaseModel):
    total: float


class OrderUpdate(BaseModel):
    total: float | None = None


class OrderRepository(MongoRepository[OrderDocument, OrderEntity, OrderCreate, OrderUpdate]):
    model = OrderDocument
    entity_schema = OrderEntity


async def main() -> None:
    config = MongoStorageConfig(dsn="mongodb://localhost:27017", database="shop")
    manager = MongoClientManager(config)
    await manager.init_models([OrderDocument])

    repo = OrderRepository()
    order = await repo.create(OrderCreate(total=99.9))
    await repo.update(order.id, OrderUpdate(total=120.0), expected_version=order.version)

    manager.close()
```

---

### 3. Redis (Key-Value + Distributed Locks)

```python
from pydantic import BaseModel

from storage.adapters.redis import RedisClientManager, RedisRepository, RedisStorageConfig
from storage.core import BaseEntity


class SessionEntity(BaseEntity):
    user_id: str


class SessionCreate(BaseModel):
    user_id: str


class SessionUpdate(BaseModel):
    user_id: str | None = None


class SessionRepository(RedisRepository[SessionEntity, SessionCreate, SessionUpdate]):
    entity_schema = SessionEntity
    key_prefix = "session"
    default_ttl = 3600  # seconds


async def main() -> None:
    config = RedisStorageConfig(dsn="redis://localhost:6379/0")
    manager = RedisClientManager(config)
    repo = SessionRepository(manager.client)

    # Distributed lock (raises LockError if busy)
    async with manager.lock("lock:session:creation", timeout=10.0, blocking_timeout=2.0):
        session = await repo.create(SessionCreate(user_id="42"))

    await manager.close()
```

---

## Running Library Tests

```bash
uv run pytest -v
```
