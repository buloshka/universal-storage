from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class BaseStorageConfig(BaseSettings):
    """Base configuration for all storage layers. Intended to be inherited in projects with a proper env_prefix."""

    model_config = SettingsConfigDict(extra="ignore")

    pool_size: int = Field(
        default=10,
        ge=1,
        description="Base size of the connection pool (minimum number of persistent connections)."
    )
    max_overflow: int = Field(
        default=20,
        ge=0,
        description="Maximum number of temporary connections allowed above the base pool size."
    )
    pool_timeout: float = Field(
        default=30.0,
        gt=0,
        description="Timeout (in seconds) for waiting to acquire a free connection from the pool."
    )
