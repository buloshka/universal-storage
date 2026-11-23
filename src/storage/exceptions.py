class StorageError(Exception):
    """Base exception for all data storage layer errors."""


class NotFoundError(StorageError):
    """Raised when a requested object is not found."""


class ConcurrencyError(StorageError):
    """Raised when a concurrency conflict occurs, such as a version mismatch."""


class LockError(StorageError):
    """Raised when an attempt to acquire a lock (pessimistic or distributed) fails."""


class ConnectionConfigError(StorageError):
    """Raised when storage connection parameters are incorrectly configured."""
