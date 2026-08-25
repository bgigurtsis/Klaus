"""Config file persistence: paths, the default template, and TOML edits.

This module owns everything that reads or writes ``~/.klaus/config.toml``
as text. Interpretation of the values (types, defaults, runtime settings)
stays in :mod:`klaus.config`.
"""

from __future__ import annotations

import os
import re
import tomllib
from pathlib import Path


def _resolve_data_dir() -> Path:
    """Return Klaus's data directory, with an override for tests and packaging."""
    configured = os.environ.get("KLAUS_DATA_DIR", "").strip()
    if configured:
        return Path(configured).expanduser()
    return Path.home() / ".klaus"


DATA_DIR = _resolve_data_dir()
DB_PATH = DATA_DIR / "klaus.db"
CONFIG_PATH = DATA_DIR / "config.toml"

DEFAULT_CONFIG_TEMPLATE = """\
# Klaus configuration
# Uncomment and edit any line to override the default.

# Set to true after the setup wizard completes.
# setup_complete = false

# Push-to-talk hotkey (default: §)
# hotkey = "§"

# Toggle input mode hotkey (default: §; press Shift+§ to toggle)
# toggle_key = "§"

# Reading source index (default: -1)
# macOS: -2 uses Desk View; -3 uses the active reading window; -1 disables capture.
# reMarkable Paper Pure: -4 uses the paired tablet screen.
# camera_index = -1

# Paper Pure connection. Klaus stores the password in Apple Keychain.
# remarkable_address = "https://10.11.99.1:2001"
# remarkable_username = "klaus"
# remarkable_certificate_sha256 = ""

# Microphone device index (default: -1, uses system default)
# mic_index = -1

# Live conversation model (default: GPT Live 2.1 mini)
# Options: gemini-3.1-flash-live-preview, gpt-realtime-2.1, gpt-realtime-2.1-mini
# live_model = "gpt-realtime-2.1-mini"

# Reasoning effort (default: high)
# Options: low, medium, high. Higher settings may take longer and cost more.
# reasoning_effort = "high"

# Live voice. Gemini defaults to Kore. GPT Realtime defaults to cedar.
# voice = "cedar"

# Input mode (default: push_to_talk)
# Options: voice_activation, push_to_talk
# input_mode = "push_to_talk"

# Voice activation sensitivity 0-3 (default: 3, higher = more aggressive filtering)
# vad_sensitivity = 3

# Seconds of silence before voice activation finalizes (default: 1.0)
# vad_silence_timeout = 1.0

# Seconds of silence before speculative STT starts on the audio so far.
# Must be below vad_silence_timeout; set to 0 to disable. (default: 0.6)
# vad_early_stt_timeout = 0.6

# Require enough voiced content before accepting a VAD utterance.
# Helps reject fan/hum/background-noise false triggers.
# Minimum utterance duration in seconds (default: 0.5)
# vad_min_duration = 0.5
# Minimum voiced-frame ratio across an utterance (default: 0.28)
# vad_min_voiced_ratio = 0.28
# Minimum voiced 30ms frames in an utterance (default: 8)
# vad_min_voiced_frames = 8
#
# Secondary local quality gate (runs after WebRTC VAD checks).
# Minimum RMS loudness in dBFS (default: -45.0, higher = stricter)
# vad_min_rms_dbfs = -45.0
# Minimum strongest contiguous voiced run of 30ms frames (default: 6)
# vad_min_voiced_run_frames = 6
# Consecutive voiced time required before listening starts (default: 90ms)
# vad_start_trigger_ms = 90
#
# Moonshine STT model size (default: "medium")
# Options: tiny, small, medium
# stt_moonshine_model = "medium"
# Moonshine language code (default: "en")
# stt_moonshine_language = "en"

# Allow interrupting Klaus by speaking while it talks (voice mode only).
# Keep this off on open-speaker setups because playback can resemble speech.
# barge_in_enabled = false
# Minimum sustained speech (ms) required to trigger a barge-in (default: 120)
# barge_in_min_voiced_ms = 120
# Loudness margin (dB) above measured playback bleed required for barge-in
# barge_in_rms_margin_dbfs = 4.0

# Play short audio cues on capture/cancel state changes.
# earcons_enabled = true

# Optional: describe your background so Klaus can tailor explanations.
# user_background = ""
# Optional: path to your Obsidian vault folder for the notes feature.
# obsidian_vault_path = ""

# Log level (default: INFO)
# Options: DEBUG, INFO, WARNING, ERROR
# log_level = "INFO"

"""


def load_user_config() -> tuple[dict, Exception | None]:
    """Parse config.toml, writing the template first on a fresh install."""
    if not CONFIG_PATH.exists():
        CONFIG_PATH.write_text(DEFAULT_CONFIG_TEMPLATE, encoding="utf-8")
        return {}, None

    try:
        with open(CONFIG_PATH, "rb") as _f:
            return tomllib.load(_f), None
    except tomllib.TOMLDecodeError as exc:
        return {}, exc


def read_config_text() -> str:
    """Read config.toml as raw text."""
    if CONFIG_PATH.exists():
        return CONFIG_PATH.read_text(encoding="utf-8")
    return DEFAULT_CONFIG_TEMPLATE


def write_config_text(text: str) -> None:
    """Write raw text to config.toml."""
    CONFIG_PATH.write_text(text, encoding="utf-8")


def escape_toml_basic_string(value: str) -> str:
    return (
        value.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\r", "")
        .replace("\n", "\\n")
    )


def set_top_level_value(key: str, value: str) -> None:
    """Set a top-level key in config.toml, uncommenting if necessary."""
    text = read_config_text()
    uncommented = re.compile(rf"^{re.escape(key)}\s*=\s*.*$", re.MULTILINE)
    commented = re.compile(rf"^#\s*{re.escape(key)}\s*=\s*.*$", re.MULTILINE)
    line = f"{key} = {value}"

    if uncommented.search(text):
        text = uncommented.sub(lambda _m: line, text)
    elif commented.search(text):
        text = commented.sub(lambda _m: line, text)
    else:
        first_newline = text.index("\n") if "\n" in text else len(text)
        text = text[:first_newline] + "\n" + line + text[first_newline:]
    write_config_text(text)
