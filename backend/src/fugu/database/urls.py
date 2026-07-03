"""Canonical PostgreSQL URL handling for async application and migration clients."""

from __future__ import annotations

from typing import TypeAlias

from sqlalchemy.engine import URL, make_url

QueryValue: TypeAlias = str | tuple[str, ...]
_SUPPORTED_DRIVERS = {"postgres", "postgresql", "postgresql+asyncpg"}
_SUPPORTED_SSL_MODES = {
    "disable",
    "allow",
    "prefer",
    "require",
    "verify-ca",
    "verify-full",
}


def _postgresql_url(value: object) -> URL:
    """Parse and validate a PostgreSQL URL without exposing its credentials."""
    database_url = make_url(str(value))
    if database_url.drivername not in _SUPPORTED_DRIVERS:
        raise ValueError("Database URLs must use a PostgreSQL scheme.")
    return database_url


def _pop_single_query_value(
    query: dict[str, QueryValue],
    key: str,
) -> str | None:
    """Remove one scalar query option and reject ambiguous repeated values."""
    value = query.pop(key, None)
    if value is None:
        return None
    if isinstance(value, tuple):
        if len(value) != 1:
            raise ValueError(f"Database URL option {key!r} must appear only once.")
        return value[0]
    return value


def _validated_ssl_mode(value: str | None) -> str | None:
    """Validate PostgreSQL SSL policy values shared by libpq and asyncpg."""
    if value is None:
        return None
    if value not in _SUPPORTED_SSL_MODES:
        allowed = ", ".join(sorted(_SUPPORTED_SSL_MODES))
        raise ValueError(f"Unsupported PostgreSQL SSL mode {value!r}; expected one of: {allowed}.")
    return value


def sqlalchemy_asyncpg_url(value: object) -> str:
    """Return a SQLAlchemy URL that consistently selects the asyncpg driver."""
    database_url = _postgresql_url(value)
    query: dict[str, QueryValue] = dict(database_url.query)
    ssl_mode = _validated_ssl_mode(_pop_single_query_value(query, "sslmode"))
    explicit_ssl = _validated_ssl_mode(_pop_single_query_value(query, "ssl"))

    if ssl_mode is not None and explicit_ssl is not None and ssl_mode != explicit_ssl:
        raise ValueError("Database URL contains conflicting ssl and sslmode values.")

    effective_ssl = explicit_ssl or ssl_mode
    if effective_ssl is not None:
        query["ssl"] = effective_ssl

    normalized = database_url.set(
        drivername="postgresql+asyncpg",
        query=query,
    )
    return normalized.render_as_string(hide_password=False)


def asyncpg_dsn(value: object) -> str:
    """Return a libpq-style DSN suitable for direct asyncpg connections."""
    database_url = _postgresql_url(value)
    query: dict[str, QueryValue] = dict(database_url.query)
    ssl_mode = _validated_ssl_mode(_pop_single_query_value(query, "sslmode"))
    explicit_ssl = _validated_ssl_mode(_pop_single_query_value(query, "ssl"))

    if ssl_mode is not None and explicit_ssl is not None and ssl_mode != explicit_ssl:
        raise ValueError("Database URL contains conflicting ssl and sslmode values.")

    effective_ssl = ssl_mode or explicit_ssl
    if effective_ssl is not None:
        query["sslmode"] = effective_ssl

    normalized = database_url.set(
        drivername="postgresql",
        query=query,
    )
    return normalized.render_as_string(hide_password=False)
