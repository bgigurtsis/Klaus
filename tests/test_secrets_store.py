"""Tests for the Keychain-backed secrets store."""

from __future__ import annotations

import sys
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from klaus import secrets_store


class _PasswordDeleteError(Exception):
    pass


def _fake_keyring(store: dict[tuple[str, str], str]):
    def get_password(service, account):
        return store.get((service, account))

    def set_password(service, account, value):
        store[(service, account)] = value

    def delete_password(service, account):
        if (service, account) not in store:
            raise _PasswordDeleteError()
        del store[(service, account)]

    return SimpleNamespace(
        get_password=get_password,
        set_password=set_password,
        delete_password=delete_password,
        errors=SimpleNamespace(PasswordDeleteError=_PasswordDeleteError),
    )


@pytest.fixture
def keyring_store():
    store: dict[tuple[str, str], str] = {}
    with patch.dict(sys.modules, {"keyring": _fake_keyring(store)}):
        yield store


def test_set_get_delete_api_key_round_trip(keyring_store):
    secrets_store.set_api_key("openai", "sk-secret")

    assert secrets_store.get_api_key("openai") == "sk-secret"
    assert secrets_store.has_api_key("openai")
    assert keyring_store == {
        (secrets_store.KEYCHAIN_SERVICE, "openai"): "sk-secret"
    }

    secrets_store.delete_api_key("openai")
    assert secrets_store.get_api_key("openai") == ""
    assert not secrets_store.has_api_key("openai")


def test_get_api_key_strips_whitespace(keyring_store):
    keyring_store[(secrets_store.KEYCHAIN_SERVICE, "gemini")] = "  key  \n"
    assert secrets_store.get_api_key("gemini") == "key"


def test_unknown_slug_is_rejected_before_touching_keychain(keyring_store):
    with pytest.raises(ValueError, match="Unsupported API key slug"):
        secrets_store.get_api_key("anthropic")
    with pytest.raises(ValueError, match="Unsupported API key slug"):
        secrets_store.set_api_key("anthropic", "value")


def test_delete_missing_key_is_a_no_op(keyring_store):
    secrets_store.delete_api_key("openai")  # nothing stored; must not raise


def test_remarkable_password_round_trip(keyring_store):
    secrets_store.set_remarkable_password("pairing-pw")
    assert secrets_store.get_remarkable_password() == "pairing-pw"

    secrets_store.delete_remarkable_password()
    assert secrets_store.get_remarkable_password() == ""
    secrets_store.delete_remarkable_password()  # second delete is a no-op


def test_backend_errors_surface_as_secrets_store_error():
    broken = MagicMock()
    broken.get_password.side_effect = RuntimeError("keychain locked")
    broken.errors = SimpleNamespace(PasswordDeleteError=_PasswordDeleteError)
    with patch.dict(sys.modules, {"keyring": broken}):
        with pytest.raises(secrets_store.SecretsStoreError, match="keychain locked"):
            secrets_store.get_api_key("openai")
