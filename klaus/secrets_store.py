from __future__ import annotations

API_KEY_SLUGS: tuple[str, ...] = ("gemini", "openai")
KEYCHAIN_SERVICE = "com.bgigurtsis.klaus.api-keys"
KEYCHAIN_ACCOUNT_BY_SLUG: dict[str, str] = {
    "gemini": "gemini",
    "openai": "openai",
}
REMARKABLE_PASSWORD_ACCOUNT = "remarkable-paper-pure-password"


class SecretsStoreError(RuntimeError):
    """Raised when the OS secrets backend cannot be accessed."""


def _require_valid_slug(slug: str) -> str:
    if slug not in KEYCHAIN_ACCOUNT_BY_SLUG:
        raise ValueError(f"Unsupported API key slug: {slug!r}")
    return KEYCHAIN_ACCOUNT_BY_SLUG[slug]


def _load_keyring():
    try:
        import keyring
    except Exception as exc:  # pragma: no cover - backend/import errors are environment-specific
        raise SecretsStoreError(f"Failed to import keyring: {exc}") from exc
    return keyring


def get_api_key(slug: str) -> str:
    """Read an API key value from Apple Keychain."""
    account = _require_valid_slug(slug)
    keyring = _load_keyring()
    try:
        value = keyring.get_password(KEYCHAIN_SERVICE, account)
    except Exception as exc:  # pragma: no cover - backend errors are environment-specific
        raise SecretsStoreError(f"Failed reading {slug} from Keychain: {exc}") from exc
    if not value:
        return ""
    return str(value).strip()


def has_api_key(slug: str) -> bool:
    """Return whether Keychain currently has a non-empty value for a provider key."""
    return bool(get_api_key(slug))


def set_api_key(slug: str, value: str) -> None:
    """Write an API key value to Apple Keychain."""
    account = _require_valid_slug(slug)
    keyring = _load_keyring()
    try:
        keyring.set_password(KEYCHAIN_SERVICE, account, value)
    except Exception as exc:  # pragma: no cover - backend errors are environment-specific
        raise SecretsStoreError(f"Failed writing {slug} to Keychain: {exc}") from exc


def delete_api_key(slug: str) -> None:
    """Delete an API key from Apple Keychain."""
    account = _require_valid_slug(slug)
    keyring = _load_keyring()
    try:
        keyring.delete_password(KEYCHAIN_SERVICE, account)
    except keyring.errors.PasswordDeleteError:
        return
    except Exception as exc:  # pragma: no cover - backend errors are environment-specific
        raise SecretsStoreError(f"Failed deleting {slug} from Keychain: {exc}") from exc


def get_remarkable_password() -> str:
    """Read the Paper Pure pairing password from Apple Keychain."""
    keyring = _load_keyring()
    try:
        value = keyring.get_password(KEYCHAIN_SERVICE, REMARKABLE_PASSWORD_ACCOUNT)
    except Exception as exc:  # pragma: no cover - backend errors are environment-specific
        raise SecretsStoreError(f"Failed reading Paper Pure password from Keychain: {exc}") from exc
    return str(value or "")


def set_remarkable_password(value: str) -> None:
    """Write the Paper Pure pairing password to Apple Keychain."""
    keyring = _load_keyring()
    try:
        keyring.set_password(KEYCHAIN_SERVICE, REMARKABLE_PASSWORD_ACCOUNT, value)
    except Exception as exc:  # pragma: no cover - backend errors are environment-specific
        raise SecretsStoreError(f"Failed writing Paper Pure password to Keychain: {exc}") from exc


def delete_remarkable_password() -> None:
    """Delete the Paper Pure pairing password from Apple Keychain."""
    keyring = _load_keyring()
    try:
        keyring.delete_password(KEYCHAIN_SERVICE, REMARKABLE_PASSWORD_ACCOUNT)
    except keyring.errors.PasswordDeleteError:
        return
    except Exception as exc:  # pragma: no cover - backend errors are environment-specific
        raise SecretsStoreError(f"Failed deleting Paper Pure password from Keychain: {exc}") from exc
