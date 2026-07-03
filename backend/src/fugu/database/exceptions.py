"""Typed exceptions for the asynchronous database layer."""


class DatabaseException(RuntimeError):
    """Base exception for all Fugu database failures."""


class DatabaseRoutingError(DatabaseException):
    """Raised when a requested workload target is not registered."""


class ConnectionPoolExhaustedError(DatabaseException):
    """Raised when a connection cannot be acquired before the pool timeout."""


class DatabaseUnavailableError(DatabaseException):
    """Raised when a configured database cannot be reached."""


class QueryExecutionError(DatabaseException):
    """Raised when a database statement fails."""


class TransactionRollbackError(DatabaseException):
    """Raised when rollback itself fails after a transaction error."""
