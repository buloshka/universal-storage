from collections.abc import AsyncGenerator
from typing import Any

from pydantic import Field
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from storage.config import BaseStorageConfig


class SQLStorageConfig(BaseStorageConfig):
    """Configuration for relational database connections."""

    dsn: str = Field(..., description="Async database connection URL (e.g., postgresql+asyncpg://...)")
    echo: bool = Field(default=False, description="Enable SQLAlchemy SQL query logging")
    pool_pre_ping: bool = Field(default=True, description="Verify connections before using them from the pool")


class SQLSessionManager:
    """Manages the global AsyncEngine connection pool and provides lightweight session instances."""

    def __init__(self, config: SQLStorageConfig) -> None:
        self._config = config
        engine_kwargs: dict[str, Any] = {
            "echo": config.echo,
            "pool_pre_ping": config.pool_pre_ping,
        }

        if not config.dsn.startswith("sqlite"):
            engine_kwargs["pool_size"] = config.pool_size
            engine_kwargs["max_overflow"] = config.max_overflow
            engine_kwargs["pool_timeout"] = config.pool_timeout

        self._engine: AsyncEngine = create_async_engine(config.dsn, **engine_kwargs)
        self._session_factory: async_sessionmaker[AsyncSession] = async_sessionmaker(
            bind=self._engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False,
        )

    @property
    def engine(self) -> AsyncEngine:
        """Return the underlying SQLAlchemy AsyncEngine."""
        return self._engine

    @property
    def session_factory(self) -> async_sessionmaker[AsyncSession]:
        """Return the configured async session maker."""
        return self._session_factory

    async def get_session(self) -> AsyncGenerator[AsyncSession, None]:
        """Yield a lightweight database session from the connection pool."""
        async with self._session_factory() as session:
            yield session

    async def close(self) -> None:
        """Dispose of the connection pool on application shutdown."""
        await self._engine.dispose()
