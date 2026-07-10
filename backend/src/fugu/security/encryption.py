"""Authenticated encryption for provider credentials stored in the database."""

from __future__ import annotations

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy.ext.asyncio import AsyncSession

from fugu.boot.config import InfrastructureConfig, get_settings
from fugu.database.models import ProviderCredential
from fugu.database.repositories import ProviderCredentialRepository
from fugu.security.exceptions import (
    CryptographicError,
    DecryptionFailedError,
    EncryptionFailedError,
)


class SymmetricVaultEngine:
    """Encrypt and authenticate provider credentials with a versioned Fernet key."""

    def __init__(self, encryption_key: str, *, key_version: int = 1) -> None:
        if key_version < 1:
            raise ValueError("Vault key versions must be positive integers.")
        try:
            self._cipher = Fernet(encryption_key.encode("utf-8"))
        except (TypeError, ValueError) as exc:
            raise CryptographicError("The configured vault encryption key is invalid.") from exc
        self.key_version = key_version

    @classmethod
    def from_settings(
        cls,
        settings: InfrastructureConfig | None = None,
    ) -> SymmetricVaultEngine:
        """Construct the vault from validated runtime settings."""
        resolved_settings = settings or get_settings()
        return cls(resolved_settings.vault_encryption_key.get_secret_value())

    def encrypt_provider_credential(self, plaintext_secret: str) -> str:
        """Encrypt a non-empty provider credential for authenticated storage."""
        if not plaintext_secret or not plaintext_secret.strip():
            raise EncryptionFailedError("Provider credentials cannot be empty.")
        try:
            return self._cipher.encrypt(plaintext_secret.encode("utf-8")).decode("ascii")
        except (TypeError, ValueError, UnicodeError) as exc:
            raise EncryptionFailedError("Provider credential encryption failed.") from exc

    def decrypt_provider_credential(self, encrypted_ciphertext: str) -> str:
        """Authenticate and decrypt an encrypted provider credential."""
        if not encrypted_ciphertext or not encrypted_ciphertext.strip():
            raise DecryptionFailedError("Encrypted provider credentials cannot be empty.")
        try:
            plaintext = self._cipher.decrypt(encrypted_ciphertext.encode("ascii"))
            return plaintext.decode("utf-8")
        except (InvalidToken, TypeError, ValueError, UnicodeError) as exc:
            raise DecryptionFailedError("Provider credential authentication or decryption failed.") from exc


class ProviderCredentialVault:
    """Persist and retrieve provider credentials without exposing plaintext rows."""

    def __init__(self, cipher: SymmetricVaultEngine) -> None:
        self._cipher = cipher

    async def store(
        self,
        session: AsyncSession,
        *,
        provider_name: str,
        plaintext_secret: str,
    ) -> ProviderCredential:
        """Create or rotate one encrypted credential and advance its public revision."""
        normalized_provider = provider_name.strip().lower()
        if not normalized_provider:
            raise EncryptionFailedError("Provider names cannot be empty.")

        encrypted_secret = self._cipher.encrypt_provider_credential(plaintext_secret)
        credential = await ProviderCredentialRepository.get_by_provider(
            session,
            normalized_provider,
        )
        if credential is None:
            credential = await ProviderCredentialRepository.add(
                session,
                provider_name=normalized_provider,
                encrypted_secret=encrypted_secret,
                key_version=self._cipher.key_version,
            )
        else:
            credential.encrypted_secret = encrypted_secret
            credential.key_version += 1
            await session.flush()
        return credential

    async def retrieve(self, session: AsyncSession, *, provider_name: str) -> str | None:
        """Return a decrypted provider credential when one is configured."""
        credential = await ProviderCredentialRepository.get_by_provider(
            session,
            provider_name.strip().lower(),
        )
        if credential is None:
            return None
        return self._cipher.decrypt_provider_credential(credential.encrypted_secret)
