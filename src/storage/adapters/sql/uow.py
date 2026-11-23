from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from storage.core.uow import BaseUnitOfWork


class SQLUnitOfWork(BaseUnitOfWork):
    """SQLAlchemy implementation of the Unit of Work pattern."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory
        self._session: AsyncSession | None = None

    @property
    def session(self) -> AsyncSession:
        """Return the active AsyncSession. Raises RuntimeError if accessed outside context manager."""
        if self._session is None:
            raise RuntimeError("SQLUnitOfWork must be entered via 'async with' before accessing the session.")
        return self._session

    async def _connect(self) -> None:
        self._session = self._session_factory()

    async def _disconnect(self) -> None:
        if self._session is not None:
            await self._session.close()
            self._session = None

    async def commit(self) -> None:
        if self._session is not None:
            await self._session.commit()

    async def rollback(self) -> None:
        if self._session is not None:
            await self._session.rollback()
