"""Tests for the current Keychain-backed Klaus configuration."""

import tomllib

import pytest

import klaus.config as config


def test_resolve_data_dir_prefers_environment_override(tmp_path, monkeypatch):
    monkeypatch.setenv("KLAUS_DATA_DIR", str(tmp_path))
    assert config._resolve_data_dir() == tmp_path


@pytest.fixture
def config_dir(tmp_path, monkeypatch):
    path = tmp_path / "config.toml"
    path.write_text(config._DEFAULT_CONFIG_TEMPLATE, encoding="utf-8")
    monkeypatch.setattr(config, "CONFIG_PATH", path)
    return path


def test_default_template_never_contains_api_keys():
    assert "api_keys" not in config._DEFAULT_CONFIG_TEMPLATE
    assert "OPENAI_API_KEY" not in config._DEFAULT_CONFIG_TEMPLATE


def test_set_api_key_writes_only_to_keychain(monkeypatch, config_dir):
    saved: list[tuple[str, str]] = []
    monkeypatch.setattr(
        config.secrets_store,
        "set_api_key",
        lambda slug, value: saved.append((slug, value)),
    )
    config.save_api_key("sk-test-key")
    assert saved == [("openai", "sk-test-key")]
    assert "sk-test-key" not in config_dir.read_text(encoding="utf-8")


def test_save_api_key_propagates_keychain_errors(monkeypatch):
    def unavailable(*_args):
        raise config.secrets_store.SecretsStoreError("Keychain disabled")

    monkeypatch.setattr(config.secrets_store, "set_api_key", unavailable)
    with pytest.raises(config.secrets_store.SecretsStoreError, match="Keychain disabled"):
        config.save_api_key("sk-test-key")


def test_openai_key_loads_from_environment(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-environment-key")
    settings = config._settings_from_config({})
    assert settings.openai_api_key == "sk-environment-key"
    assert config.get_api_key_sources()["openai"] == "env"


def test_keychain_value_loads_when_environment_is_empty(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(config.secrets_store, "get_api_key", lambda _: "sk-keychain-key")
    settings = config._settings_from_config({})
    assert settings.openai_api_key == "sk-keychain-key"
    assert config.get_api_key_sources()["openai"] == "keychain"


def test_mark_setup_complete_persists(config_dir):
    config.mark_setup_complete()
    with config_dir.open("rb") as file:
        assert tomllib.load(file)["setup_complete"] is True


def test_voice_and_input_preferences_persist(config_dir):
    config.save_voice("marin")
    config.save_barge_in_enabled(False)
    config.save_input_mode("push_to_talk")
    with config_dir.open("rb") as file:
        saved = tomllib.load(file)
    assert saved["voice"] == "marin"
    assert saved["barge_in_enabled"] is False
    assert saved["input_mode"] == "push_to_talk"


def test_unknown_input_mode_fails():
    with pytest.raises(ValueError, match="Unknown input mode"):
        config.save_input_mode("always_recording")


def test_defaults_use_realtime_and_desk_view():
    settings = config._settings_from_config({})
    assert settings.camera_device_index == -2
    assert settings.live_model == config.GEMINI_LIVE_MODEL
    assert settings.voice == "Kore"
    assert settings.barge_in_enabled is True


def test_live_model_and_reasoning_effort_persist(config_dir):
    config.save_live_model("gpt-realtime-2.1-mini")
    config.save_reasoning_effort("high")
    with config_dir.open("rb") as file:
        saved = tomllib.load(file)
    assert saved["live_model"] == "gpt-realtime-2.1-mini"
    assert saved["reasoning_effort"] == "high"
