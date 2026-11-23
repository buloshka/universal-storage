from abc import ABC, abstractmethod
from types import TracebackType
from typing import Self


class BaseUnitOfWork(ABC):
    """
    Unit of Work contract for managing connection lifecycles and atomic transactions.
    Acquires a lightweight session from the connection pool on entry and commits/rolls back on exit.
    """

    async def __aenter__(self) -> Self:
        await self._connect()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        if exc_type is not None:
            await self.rollback()
        else:
            await self.commit()
        await self._disconnect()

    @abstractmethod
    async def _connect(self) -> None:
        """Acquire a session or connection from the pool."""

    @abstractmethod
    async def _disconnect(self) -> None:
        """Close the session and return the connection to the pool."""

    @abstractmethod
    async def commit(self) -> None:
        """Commit the current transaction."""

    @abstractmethod
    async def rollback(self) -> None:
        """Rollback the current transaction on error."""
