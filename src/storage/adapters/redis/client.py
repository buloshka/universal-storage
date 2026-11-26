from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from pydantic import Field
from redis.asyncio import ConnectionPool, Redis
from redis.exceptions import LockError as RedisDriverLockError

from storage.config import BaseStorageConfig
from storage.exceptions import LockError


class RedisStorageConfig(BaseStorageConfig):
    """Configuration for Redis connections."""

    dsn: str = Field(..., description="Redis connection URL (e.g., redis://localhost:6379/0)")
    decode_responses: bool = Field(default=True, description="Decode Redis byte responses to UTF-8 strings")


class RedisClientManager:
    """Manages the global Redis ConnectionPool and provides async client access and distributed locks."""

    def __init__(self, config: RedisStorageConfig) -> None:
        self._config = config
        self._pool: ConnectionPool = ConnectionPool.from_url(
            config.dsn,
            max_connections=config.pool_size + config.max_overflow,
            socket_timeout=config.pool_timeout,
            decode_responses=config.decode_responses,
        )
        self._client: Redis = Redis(connection_pool=self._pool)

    @property
    def client(self) -> Redis:
        """Return the shared async Redis client backed by the connection pool."""
        return self._client

    @asynccontextmanager
    async def lock(
        self,
        name: str,
        *,
        timeout: float = 10.0,
        blocking_timeout: float | None = 5.0,
    ) -> AsyncGenerator[None, None]:
        """
        Acquire a distributed lock in Redis.

        Args:
            name: Unique lock identifier (e.g., 'lock:order:123').
            timeout: Maximum lock lifetime in seconds before auto-release (prevents deadlocks).
            blocking_timeout: Max seconds to wait for lock acquisition. None means wait indefinitely; 0 means fail fast.

        Raises:
            LockError: If the lock cannot be acquired within blocking_timeout.
        """
        distributed_lock = self._client.lock(
            name=name,
            timeout=timeout,
            blocking_timeout=blocking_timeout,
        )
        acquired = await distributed_lock.acquire()
        if not acquired:
            raise LockError(f"Could not acquire distributed lock '{name}' within {blocking_timeout}s.")

        try:
            yield
        finally:
            try:
                await distributed_lock.release()
            except RedisDriverLockError:
                pass

    async def close(self) -> None:
        """Close the Redis client and disconnect all pooled connections."""
        await self._client.aclose()
        await self._pool.aclose()
