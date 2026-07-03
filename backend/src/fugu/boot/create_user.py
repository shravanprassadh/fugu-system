"""Secure operator CLI for creating database-backed Fugu users."""

from __future__ import annotations

import argparse
import asyncio
import sys
from getpass import getpass
from typing import Literal

from fugu.database.connection import DatabaseSessionRegistry, DatabaseTarget, get_session_registry
from fugu.database.models import User
from fugu.database.repositories import UserRepository
from fugu.security.auth import IdentitySecurityManager

UserRole = Literal["user", "admin"]


class UserBootstrapError(RuntimeError):
    """Raised when an operator-supplied user cannot be created safely."""


def validate_username(username: str) -> str:
    """Normalize and validate a username against the authentication API contract."""
    normalized = username.strip()
    if not 3 <= len(normalized) <= 255:
        raise UserBootstrapError("Username must contain between 3 and 255 characters.")
    return normalized


def validate_password(password: str) -> str:
    """Validate a plaintext password without normalizing or persisting it."""
    if not 8 <= len(password) <= 1_024:
        raise UserBootstrapError("Password must contain between 8 and 1024 characters.")
    if not password.strip():
        raise UserBootstrapError("Password cannot contain only whitespace.")
    return password


def validate_role(role: str) -> UserRole:
    """Restrict bootstrap roles to the values enforced by the database schema."""
    if role not in {"user", "admin"}:
        raise UserBootstrapError("Role must be either 'user' or 'admin'.")
    return "admin" if role == "admin" else "user"


async def create_database_user(
    registry: DatabaseSessionRegistry,
    *,
    username: str,
    password: str,
    role: str = "admin",
) -> User:
    """Create one user through the same hashing and transaction layers used by Fugu."""
    normalized_username = validate_username(username)
    validated_password = validate_password(password)
    validated_role = validate_role(role)

    async with registry.session(DatabaseTarget.MASTER) as session:
        existing = await UserRepository.get_by_username(session, normalized_username)
        if existing is not None:
            raise UserBootstrapError(f"Username {normalized_username!r} already exists.")

        password_hash = IdentitySecurityManager.compute_secure_hash(validated_password)
        return await UserRepository.add(
            session,
            username=normalized_username,
            password_hash=password_hash,
            role=validated_role,
        )


def build_argument_parser() -> argparse.ArgumentParser:
    """Build the operator-facing command-line contract."""
    parser = argparse.ArgumentParser(
        prog="fugu-create-user",
        description="Create a database-backed Fugu user with an interactively entered password.",
    )
    parser.add_argument("--username", required=True, help="Unique Fugu login name.")
    parser.add_argument(
        "--role",
        choices=("admin", "user"),
        default="admin",
        help="Authorization role assigned to the new account (default: admin).",
    )
    return parser


def read_confirmed_password() -> str:
    """Read a password twice without echoing or accepting it through shell arguments."""
    password = getpass("Password: ")
    confirmation = getpass("Confirm password: ")
    if password != confirmation:
        raise UserBootstrapError("Passwords do not match.")
    return validate_password(password)


async def run_bootstrap(*, username: str, password: str, role: str) -> User:
    """Create a user using the configured master database and release all pools."""
    registry = get_session_registry()
    try:
        return await create_database_user(
            registry,
            username=username,
            password=password,
            role=role,
        )
    finally:
        await registry.dispose_pools()
        if get_session_registry.cache_info().currsize:
            get_session_registry.cache_clear()


def main() -> int:
    """Execute the secure first-user bootstrap command."""
    parser = build_argument_parser()
    arguments = parser.parse_args()

    try:
        password = read_confirmed_password()
        user = asyncio.run(
            run_bootstrap(
                username=arguments.username,
                password=password,
                role=arguments.role,
            )
        )
    except UserBootstrapError as exc:
        print(f"User creation failed: {exc}", file=sys.stderr)
        return 1

    print(f"Created {user.role} user {user.username!r} with ID {user.id}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
