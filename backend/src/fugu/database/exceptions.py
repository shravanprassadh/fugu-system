"""Typed exceptions for the asynchronous database layer."""


class DatabaseError(RuntimeError):
    """Base error for all Fugu database failures."""


class DatabaseRoutingError(DatabaseError):
    """Raised when a requested workload target is not registered."""


class ConnectionPoolExhaustedError(DatabaseError):
    """Raised when a connection cannot be acquired before the pool timeout."""


class DatabaseUnavailableError(DatabaseError):
    """Raised when a configured database cannot be reached."""


class QueryExecutionError(DatabaseError):
    """Raised when a database statement fails."""


class TransactionRollbackError(DatabaseError):
    """Raised when rollback itself fails after a transaction error."""


class EntityNotFoundError(DatabaseError):
    """Raised when a requested record does not exist within the permitted scope."""
