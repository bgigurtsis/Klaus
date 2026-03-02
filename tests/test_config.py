"""Tests for klaus.config -- persistence helpers used by setup wizard."""

import tomllib
from pathlib import Path
from unittest.mock import patch

import pytest

import klaus.config as config


@pytest.fixture
def config_dir(tmp_path, monkeypatch):
    """Redirect config to a temporary directory."""
    cfg_path = tmp_path / "config.toml"
    cfg_path.write_text(config._DEFAULT_CONFIG_TEMPLATE, encoding="utf-8")
    monkeypatch.setattr(config, "CONFIG_PATH", cfg_path)
    return cfg_path


class TestReadWriteConfigText:
    def test_read_returns_template_when_missing(self, tmp_path, monkeypatch):
        missing = tmp_path / "nonexistent.toml"
        monkeypatch.setattr(config, "CONFIG_PATH", missing)
        text = config._read_config_text()
        assert "[api_keys]" in text

    def test_read_returns_existing_content(self, config_dir):
        config_dir.write_text("hello = true\n", encoding="utf-8")
        assert config._read_config_text() == "hello = true\n"

    def test_write_persists_content(self, config_dir):
        config._write_config_text("custom = 42\n")
        assert config_dir.read_text(encoding="utf-8") == "custom = 42\n"


class TestIsSetupComplete:
    def test_false_by_default(self, monkeypatch):
        monkeypatch.setattr(config, "_user_config", {})
        assert config.is_setup_complete() is False

    def test_true_when_set(self, monkeypatch):
        monkeypatch.setattr(config, "_user_config", {"setup_complete": True})
        assert config.is_setup_complete() is True

    def test_false_when_explicitly_false(self, monkeypatch):
        monkeypatch.setattr(config, "_user_config", {"setup_complete": False})
        assert config.is_setup_complete() is False


class TestSaveApiKeys:
    def test_writes_keys_to_existing_section(self, config_dir):
        config.save_api_keys("sk-ant-aaa", "sk-bbb", "tvly-ccc")
        text = config_dir.read_text(encoding="utf-8")
        assert 'anthropic = "sk-ant-aaa"' in text
        assert 'openai = "sk-bbb"' in text
        assert 'tavily = "tvly-ccc"' in text

    def test_roundtrip_via_toml_parse(self, config_dir):
        config.save_api_keys("sk-ant-round", "sk-trip", "tvly-test")
        with open(config_dir, "rb") as f:
            parsed = tomllib.load(f)
        assert parsed["api_keys"]["anthropic"] == "sk-ant-round"
        assert parsed["api_keys"]["openai"] == "sk-trip"
        assert parsed["api_keys"]["tavily"] == "tvly-test"

    def test_appends_section_when_missing(self, config_dir):
        config_dir.write_text("setup_complete = false\n", encoding="utf-8")
        config.save_api_keys("sk-ant-x", "sk-y", "tvly-z")
        text = config_dir.read_text(encoding="utf-8")
        assert "[api_keys]" in text
        assert 'anthropic = "sk-ant-x"' in text

    def test_overwrites_existing_keys(self, config_dir):
        config.save_api_keys("sk-ant-old", "sk-old", "tvly-old")
        config.save_api_keys("sk-ant-new", "sk-new", "tvly-new")
        text = config_dir.read_text(encoding="utf-8")
        assert "sk-ant-old" not in text
        assert 'anthropic = "sk-ant-new"' in text

    def test_escapes_newlines_and_quotes(self, config_dir):
        config.save_api_keys('sk-ant-a"b\nc', "sk-openai", "tvly-tavily")
        with open(config_dir, "rb") as f:
            parsed = tomllib.load(f)
        assert parsed["api_keys"]["anthropic"] == 'sk-ant-a"b\nc'


class TestSetTopLevelValue:
    def test_uncomments_commented_key(self, config_dir):
        config._set_top_level_value("setup_complete", "true")
        text = config_dir.read_text(encoding="utf-8")
        assert "setup_complete = true" in text
        assert "# setup_complete" not in text

    def test_updates_existing_uncommented_key(self, config_dir):
        config._set_top_level_value("setup_complete", "true")
        config._set_top_level_value("setup_complete", "false")
        text = config_dir.read_text(encoding="utf-8")
        assert "setup_complete = false" in text
        assert "setup_complete = true" not in text

    def test_inserts_new_key_when_absent(self, config_dir):
        config_dir.write_text("[api_keys]\n", encoding="utf-8")
        config._set_top_level_value("new_key", "42")
        text = config_dir.read_text(encoding="utf-8")
        assert "new_key = 42" in text


class TestMarkSetupComplete:
    def test_sets_flag(self, config_dir):
        config.mark_setup_complete()
        with open(config_dir, "rb") as f:
            parsed = tomllib.load(f)
        assert parsed["setup_complete"] is True


class TestSaveCameraIndex:
    def test_sets_camera_index(self, config_dir):
        config.save_camera_index(2)
        with open(config_dir, "rb") as f:
            parsed = tomllib.load(f)
        assert parsed["camera_index"] == 2

    def test_overwrites_camera_index(self, config_dir):
        config.save_camera_index(1)
        config.save_camera_index(3)
        with open(config_dir, "rb") as f:
            parsed = tomllib.load(f)
        assert parsed["camera_index"] == 3


class TestSetDeviceIndexes:
    def test_set_camera_index_updates_runtime_and_file(self, config_dir):
        config.set_camera_index(7, persist=True)
        assert config.CAMERA_DEVICE_INDEX == 7
        with open(config_dir, "rb") as f:
            parsed = tomllib.load(f)
        assert parsed["camera_index"] == 7

    def test_set_mic_index_updates_runtime_and_file(self, config_dir):
        config.set_mic_index(4, persist=True)
        assert config.MIC_DEVICE_INDEX == 4
        with open(config_dir, "rb") as f:
            parsed = tomllib.load(f)
        assert parsed["mic_index"] == 4

    def test_setters_runtime_only_with_persist_false(self, config_dir):
        before = config_dir.read_text(encoding="utf-8")
        config.set_camera_index(9, persist=False)
        config.set_mic_index(5, persist=False)
        after = config_dir.read_text(encoding="utf-8")

        assert config.CAMERA_DEVICE_INDEX == 9
        assert config.MIC_DEVICE_INDEX == 5
        assert before == after


class TestReload:
    def test_reloads_api_keys(self, config_dir, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("TAVILY_API_KEY", raising=False)
        config.save_api_keys("sk-ant-reload", "sk-reload", "tvly-reload")
        config.reload()
        assert config.ANTHROPIC_API_KEY == "sk-ant-reload"
        assert config.OPENAI_API_KEY == "sk-reload"
        assert config.TAVILY_API_KEY == "tvly-reload"

    def test_reloads_camera_index(self, config_dir):
        config.save_camera_index(5)
        config.reload()
        assert config.CAMERA_DEVICE_INDEX == 5

    def test_reload_when_file_missing(self, tmp_path, monkeypatch):
        missing = tmp_path / "gone.toml"
        monkeypatch.setattr(config, "CONFIG_PATH", missing)
        monkeypatch.setenv("ANTHROPIC_API_KEY", "env-key")
        config.reload()
        assert config.ANTHROPIC_API_KEY == "env-key"

    def test_reload_invalid_toml_uses_defaults(self, tmp_path, monkeypatch):
        bad = tmp_path / "bad.toml"
        bad.write_text('hotkey = "F2"\napi_keys = "oops\n', encoding="utf-8")
        monkeypatch.setattr(config, "CONFIG_PATH", bad)
        monkeypatch.setenv("ANTHROPIC_API_KEY", "env-key")

        config.reload()

        assert config.ANTHROPIC_API_KEY == "env-key"
        assert config.CAMERA_DEVICE_INDEX == 0


class TestKeyValidationPatterns:
    """Test the format-based key validation used by the setup wizard."""

    @pytest.mark.parametrize("key,expected", [
        ("sk-ant-" + "a" * 40, True),
        ("sk-ant-" + "a" * 33, True),
        ("sk-ant-short", False),
        ("wrong-prefix-key-12345678901234567890", False),
        ("", False),
    ])
    def test_anthropic_key_format(self, key, expected):
        valid = key.startswith("sk-ant-") and len(key) >= 40
        assert valid == expected

    @pytest.mark.parametrize("key,expected", [
        ("sk-" + "a" * 20, True),
        ("sk-" + "a" * 17, True),
        ("sk-short", False),
        ("wrong-key", False),
    ])
    def test_openai_key_format(self, key, expected):
        valid = key.startswith("sk-") and len(key) >= 20
        assert valid == expected

    @pytest.mark.parametrize("key,expected", [
        ("tvly-" + "a" * 20, True),
        ("tvly-" + "a" * 15, True),
        ("tvly-short", False),
        ("wrong-key", False),
    ])
    def test_tavily_key_format(self, key, expected):
        valid = key.startswith("tvly-") and len(key) >= 20
        assert valid == expected
