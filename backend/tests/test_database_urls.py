"""Tests for canonical PostgreSQL URL handling."""

from __future__ import annotations

import pytest
from sqlalchemy.engine import make_url

from fugu.database.urls import asyncpg_dsn, sqlalchemy_asyncpg_url


def test_sqlalchemy_url_selects_asyncpg_for_plain_postgresql_scheme() -> None:
    normalized = make_url(sqlalchemy_asyncpg_url("postgresql://localhost/fugu"))

    assert normalized.drivername == "postgresql+asyncpg"


def test_sqlalchemy_url_translates_libpq_sslmode_for_asyncpg() -> None:
    normalized = make_url(
        sqlalchemy_asyncpg_url("postgresql://localhost/fugu?sslmode=require")
    )

    assert normalized.drivername == "postgresql+asyncpg"
    assert normalized.query["ssl"] == "require"
    assert "sslmode" not in normalized.query


def test_direct_asyncpg_dsn_translates_sqlalchemy_ssl_option() -> None:
    normalized = make_url(
        asyncpg_dsn("postgresql+asyncpg://localhost/fugu?ssl=verify-full")
    )

    assert normalized.drivername == "postgresql"
    assert normalized.query["sslmode"] == "verify-full"
    assert "ssl" not in normalized.query


def test_conflicting_ssl_options_are_rejected() -> None:
    with pytest.raises(ValueError, match="conflicting ssl and sslmode"):
        sqlalchemy_asyncpg_url(
            "postgresql://localhost/fugu?ssl=require&sslmode=verify-full"
        )


def test_non_postgresql_scheme_is_rejected() -> None:
    with pytest.raises(ValueError, match="PostgreSQL scheme"):
        sqlalchemy_asyncpg_url("sqlite:///tmp/fugu.db")
