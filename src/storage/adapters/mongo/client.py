from beanie import Document, init_beanie
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import Field

from storage.config import BaseStorageConfig


class MongoStorageConfig(BaseStorageConfig):
    """Configuration for MongoDB connections."""

    dsn: str = Field(..., description="MongoDB connection URI (e.g., mongodb://localhost:27017)")
    database: str = Field(..., description="Target MongoDB database name")


class MongoClientManager:
    """Manages the global AsyncIOMotorClient connection pool and initializes Beanie ODM."""

    def __init__(self, config: MongoStorageConfig) -> None:
        self._config = config
        self._client: AsyncIOMotorClient = AsyncIOMotorClient(
            config.dsn,
            maxPoolSize=config.pool_size + config.max_overflow,
            minPoolSize=min(1, config.pool_size),
            serverSelectionTimeoutMS=int(config.pool_timeout * 1000),
        )

    @property
    def client(self) -> AsyncIOMotorClient:
        """Return the underlying Motor async client."""
        return self._client

    async def init_models(self, document_models: list[type[Document]]) -> None:
        """Initialize Beanie ODM with the provided list of Document classes."""
        await init_beanie(
            database=self._client[self._config.database],
            document_models=document_models,
        )

    def close(self) -> None:
        """Close the Motor client and release all pooled connections."""
        self._client.close()
