import logging
import os
import re
import tomllib
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

from klaus import secrets_store
from klaus.skill_loader import load_skill_instructions

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

def _resolve_data_dir() -> Path:
    """Return Klaus's data directory, with an override for tests and packaging."""
    configured = os.environ.get("KLAUS_DATA_DIR", "").strip()
    if configured:
        return Path(configured).expanduser()
    return Path.home() / ".klaus"


DATA_DIR = _resolve_data_dir()
DB_PATH = DATA_DIR / "klaus.db"
CONFIG_PATH = DATA_DIR / "config.toml"

_DEFAULT_CONFIG_TEMPLATE = """\
# Klaus configuration
# Uncomment and edit any line to override the default.

# Set to true after the setup wizard completes.
# setup_complete = false

# Push-to-talk hotkey (default: §)
# hotkey = "§"

# Toggle input mode hotkey (default: §; press Shift+§ to toggle)
# toggle_key = "§"

# Reading source index (default: -2)
# macOS: -2 uses Desk View; -3 uses the active reading window; -1 disables capture.
# camera_index = -2

# Microphone device index (default: -1, uses system default)
# mic_index = -1

# Live conversation model (default: Gemini Live)
# Options: gemini-3.1-flash-live-preview, gpt-realtime-2.1, gpt-realtime-2.1-mini
# live_model = "gemini-3.1-flash-live-preview"

# Reasoning effort (default: low)
# Options: low, medium, high. Higher settings may take longer and cost more.
# reasoning_effort = "low"

# Live voice. Gemini defaults to Kore. GPT Realtime defaults to cedar.
# voice = "Kore"

# Input mode (default: voice_activation)
# Options: voice_activation, push_to_talk
# input_mode = "voice_activation"

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
# Disable on open-speaker setups if playback bleed triggers false interrupts.
# barge_in_enabled = true
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

# ---------------------------------------------------------------------------
# Load user config (TOML)
# ---------------------------------------------------------------------------

DATA_DIR.mkdir(parents=True, exist_ok=True)


def _load_user_config() -> tuple[dict, Exception | None]:
    if not CONFIG_PATH.exists():
        CONFIG_PATH.write_text(_DEFAULT_CONFIG_TEMPLATE, encoding="utf-8")
        return {}, None

    try:
        with open(CONFIG_PATH, "rb") as _f:
            return tomllib.load(_f), None
    except tomllib.TOMLDecodeError as exc:
        return {}, exc


_user_config, _config_load_error = _load_user_config()

# ---------------------------------------------------------------------------
# Logging (after TOML so log_level takes effect)
# ---------------------------------------------------------------------------

_log_level_name = _user_config.get("log_level", "INFO").upper()
_log_level = getattr(logging, _log_level_name, logging.INFO)

logging.basicConfig(
    level=_log_level,
    format="%(asctime)s  %(name)-20s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)

_log = logging.getLogger(__name__)


if _user_config:
    _log.info("Loaded config from %s", CONFIG_PATH)
else:
    _log.info("Using default config (created template at %s)", CONFIG_PATH)
if _config_load_error is not None:
    _log.warning(
        "Config file is invalid TOML; using defaults. path=%s error=%s",
        CONFIG_PATH,
        _config_load_error,
    )

# ---------------------------------------------------------------------------
# Runtime settings
# ---------------------------------------------------------------------------

load_dotenv()

GEMINI_LIVE_MODEL = "gemini-3.1-flash-live-preview"
OPENAI_LIVE_MODELS = ("gpt-realtime-2.1", "gpt-realtime-2.1-mini")
LIVE_MODELS: dict[str, dict[str, str]] = {
    GEMINI_LIVE_MODEL: {
        "provider": "gemini",
        "label": "Gemini Live",
        "description": "Gemini Live with Google Search",
    },
    "gpt-realtime-2.1": {
        "provider": "openai",
        "label": "GPT Live 2.1",
        "description": "GPT Realtime 2.1",
    },
    "gpt-realtime-2.1-mini": {
        "provider": "openai",
        "label": "GPT Live 2.1 mini",
        "description": "GPT Realtime 2.1 mini",
    },
}
DEFAULT_LIVE_MODEL = GEMINI_LIVE_MODEL
# Compatibility alias for integrations that import the historical OpenAI model constant.
REALTIME_MODEL = "gpt-realtime-2.1"
_DEFAULT_PTT_KEY = "§"
_DEFAULT_TOGGLE_KEY = "§"

API_KEY_SLUGS: tuple[str, ...] = ("gemini", "openai")
_API_KEY_ENV_VARS: dict[str, str] = {
    "gemini": "GEMINI_API_KEY",
    "openai": "OPENAI_API_KEY",
}


@dataclass(frozen=True)
class RuntimeSettings:
    gemini_api_key: str
    openai_api_key: str
    live_model: str
    reasoning_effort: str
    obsidian_vault_path: str
    push_to_talk_key: str
    toggle_key: str
    camera_device_index: int
    mic_device_index: int
    voice: str
    input_mode: str
    vad_sensitivity: int
    vad_silence_timeout: float
    vad_early_stt_timeout: float
    vad_min_duration: float
    vad_min_voiced_ratio: float
    vad_min_voiced_frames: int
    vad_min_rms_dbfs: float
    vad_min_voiced_run_frames: int
    vad_start_trigger_ms: int
    stt_moonshine_model: str
    stt_moonshine_language: str
    barge_in_enabled: bool
    barge_in_min_voiced_ms: int
    barge_in_rms_margin_dbfs: float
    earcons_enabled: bool
    user_background: str
    system_prompt: str


@dataclass(frozen=True)
class _SettingSpec:
    runtime_field: str
    config_key: str
    default: object
    coerce: Callable[[object, object], object]
    env_var: str | None = None


def _as_int(value: object, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _as_float(value: object, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _as_str(value: object, default: str) -> str:
    if value is None:
        return default
    text = str(value).strip()
    return text if text else default


def _as_bool(value: object, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"1", "true", "yes", "on"}:
            return True
        if lowered in {"0", "false", "no", "off"}:
            return False
    return default


def _as_live_model(value: object, default: str) -> str:
    candidate = _as_str(value, default)
    return candidate if candidate in LIVE_MODELS else default


def _as_reasoning_effort(value: object, default: str) -> str:
    candidate = _as_str(value, default).lower()
    return candidate if candidate in {"low", "medium", "high"} else default


_RUNTIME_SETTING_SPECS: tuple[_SettingSpec, ...] = (
    _SettingSpec("live_model", "live_model", DEFAULT_LIVE_MODEL, _as_live_model),
    _SettingSpec("reasoning_effort", "reasoning_effort", "low", _as_reasoning_effort),
    _SettingSpec("obsidian_vault_path", "obsidian_vault_path", "", _as_str, "OBSIDIAN_VAULT_PATH"),
    _SettingSpec("push_to_talk_key", "hotkey", _DEFAULT_PTT_KEY, _as_str),
    _SettingSpec("toggle_key", "toggle_key", _DEFAULT_TOGGLE_KEY, _as_str),
    _SettingSpec("camera_device_index", "camera_index", -2, _as_int),
    _SettingSpec("mic_device_index", "mic_index", -1, _as_int),
    _SettingSpec("voice", "voice", "Kore", _as_str),
    _SettingSpec("input_mode", "input_mode", "voice_activation", _as_str),
    _SettingSpec("vad_sensitivity", "vad_sensitivity", 3, _as_int),
    _SettingSpec("vad_silence_timeout", "vad_silence_timeout", 1.0, _as_float),
    _SettingSpec("vad_early_stt_timeout", "vad_early_stt_timeout", 0.6, _as_float),
    _SettingSpec("vad_min_duration", "vad_min_duration", 0.5, _as_float),
    _SettingSpec("vad_min_voiced_ratio", "vad_min_voiced_ratio", 0.28, _as_float),
    _SettingSpec("vad_min_voiced_frames", "vad_min_voiced_frames", 8, _as_int),
    _SettingSpec("vad_min_rms_dbfs", "vad_min_rms_dbfs", -45.0, _as_float),
    _SettingSpec("vad_min_voiced_run_frames", "vad_min_voiced_run_frames", 6, _as_int),
    _SettingSpec("vad_start_trigger_ms", "vad_start_trigger_ms", 90, _as_int),
    _SettingSpec("stt_moonshine_model", "stt_moonshine_model", "medium", _as_str),
    _SettingSpec("stt_moonshine_language", "stt_moonshine_language", "en", _as_str),
    _SettingSpec("barge_in_enabled", "barge_in_enabled", True, _as_bool),
    _SettingSpec("barge_in_min_voiced_ms", "barge_in_min_voiced_ms", 120, _as_int),
    _SettingSpec("barge_in_rms_margin_dbfs", "barge_in_rms_margin_dbfs", 4.0, _as_float),
    _SettingSpec("earcons_enabled", "earcons_enabled", True, _as_bool),
)


def _build_system_prompt(
    user_background: str,
    *,
    obsidian_enabled: bool = False,
) -> str:
    """Assemble the system prompt, injecting user background when available."""
    intro = (
        "You are Klaus, a concise, knowledgeable and articulate research companion. "
        "You value brevity. "
        "The user is reading or examining physical material or content in an active "
        "macOS window. You may receive either an image of the reading source or the "
        "exact text they selected."
    )
    if user_background:
        intro += " " + user_background.strip()
    prompt = intro + "\n\n" + _SYSTEM_PROMPT_BODY
    if obsidian_enabled:
        prompt += "\n\nBundled Obsidian skill:\n\n" + load_skill_instructions("obsidian")
    return prompt


_SYSTEM_PROMPT_BODY = """\
Brevity rule: three sentences is not a minimum. It is a ceiling. Give \
the shortest accurate answer, then stop. Do not add a second paragraph, \
do not connect it back to the page, do not offer additional context unless explicitly asked. \
The user will ask a follow-up question if they want more. Only give a \
longer answer when the user explicitly says "elaborate", "in depth", "go deeper", \
"walk me through it", "tell me more", "go in depth", or "break it down".

Examples of the right default length:
  Q: "Can you define time-reversal symmetry?"
  A: "The laws governing the system are identical whether time runs \
forward or backward. A pendulum in a vacuum has it. Ink diffusing in \
water doesn't."
  Q: "Explain what reductionism means in the fourth paragraph."
  A: "Reductionism assumes you understand a system by analyzing its \
smallest parts. The author's claim is that complexity lives at higher \
levels of organization, so finer analysis doesn't just miss it, it \
makes it invisible."
  Q: "What's the difference between ergodic and non-ergodic systems?"
  A: "In an ergodic system, one trajectory eventually visits all \
accessible states, so time averages equal ensemble averages. In a \
non-ergodic system it doesn't, so history and initial conditions \
permanently matter."
  Q: "Explain what a virus is."
  A: "An agent that has evolved to achieve replication in host cells. \
Everything about it follows from that single function."
  Q: "What does this section mean?"
  A: "Selection doesn't require intent. Any mechanism that copies \
with variation and filters by fitness produces adaptation."
  Q: "Why does the author say causation breaks down here?"
  A: "Because the components interact nonlinearly. You can't isolate \
one variable's effect when its influence depends on the state of \
every other variable."

Never frame answers as narration of the page. Do not say "The page \
defines", "The author describes", "It's described as", "According to \
the text", or similar. Just state the answer directly.

Routing precedence rule:

- If the user asks for a definition or concept explanation without asking \
for page grounding, give a direct standalone definition in no more than \
two sentences.
- If the user explicitly or inferably asks about a location on the page \
(for example "the definition on the far right"), use the page context.

Your job:

- The reading source is context, not a prompt. Always \
answer the user's spoken question. Do not describe or summarize the \
page unless explicitly asked to. If the user says something brief or \
unclear, ask for clarification rather than defaulting to a page summary.
- Explain concepts accurately and at the right level. The user can handle \
dense material. What they need is precision and clarity, not thoroughness.
- When encountering mathematical notation, statistical methods, or formal \
logic, explain what it means and why it matters rather than assuming \
familiarity with the formalism itself.
- You are being spoken aloud. No preambles, no hedging, no lists, no \
bullet points. Speak in clear, direct sentences.
- If the user asks about something you can see on the page, reference \
specific parts of the document so they can follow along.
- If a concept requires background the user may not have, give a one-sentence \
bridge rather than a full primer.
- When a paper makes a claim, help the user evaluate it critically: \
what's the evidence, what are the assumptions, where might it be weak.
- If you are unsure about something, say so. Do not guess when the available \
context cannot support an accurate answer.

Voice style rules (you are spoken aloud, so these matter even more than \
in text):

- Never use "This isn't about X, it's about Y" or "Not X, but Y" \
framing. Just say the thing directly.
- Never say "Let me explain", "Great question", "That's a great \
question", or "I'd be happy to". Just answer.
- Never use "dive into", "deep dive", "craft", "landscape", "leverage", \
"robust", "realm", "multifaceted", "game-changer", or "straightforward".
- Never use "Here's the thing", "Here's what's interesting", "What's \
compelling is", "The key insight is", or "It's worth noting". Just \
state the content.
- Never use "navigate", "unlock", "elevate", "harness", "foster", \
"delve", "embark", or "journey".
- Never use theatrical transitions like "This is where it gets \
interesting", "But here's the twist", or "And that's the beauty of it".
- Never use "What does this mean? It means..." or similar rhetorical \
question structures. Just make the point.
- Never start with "So,", "Now,", "Essentially,", or "Basically,".
- Avoid filler hedges like "sort of", "kind of", "if you will", "as it \
were" unless genuinely expressing uncertainty.
- Do not use em dashes. Use shorter sentences or commas instead.
- Speak like a sharp, well-read colleague talking across a desk. Not \
like a lecturer, not like a podcast host, not like a chatbot.

Notes capability:

- You can save notes to the user's Obsidian vault using the save_note tool.
- Before saving, a notes file must be set with set_notes_file. If the user \
asks to save something and no file is set, ask them which file to use.
- The path is relative to the vault base directory. The user will say it \
by voice, so interpret naturally (e.g. "complexity science / march notes" \
becomes "complexity science/march notes.md").
- Once set, the file persists until the user asks to change it or set a \
new one. Format notes as clean markdown: use headings, blockquotes for \
direct quotes, and include page or section references when visible on \
the page.\
"""

_api_keys: dict = {}
_api_key_sources: dict[str, str] = {slug: "missing" for slug in API_KEY_SLUGS}
_runtime_settings: RuntimeSettings

# Set by _apply_runtime_settings.
GEMINI_API_KEY: str
OPENAI_API_KEY: str
LIVE_MODEL: str
REASONING_EFFORT: str
OBSIDIAN_VAULT_PATH: str
PUSH_TO_TALK_KEY: str
TOGGLE_KEY: str
CAMERA_DEVICE_INDEX: int
MIC_DEVICE_INDEX: int
VOICE: str
INPUT_MODE: str
VAD_SENSITIVITY: int
VAD_SILENCE_TIMEOUT: float
VAD_EARLY_STT_TIMEOUT: float
VAD_MIN_DURATION: float
VAD_MIN_VOICED_RATIO: float
VAD_MIN_VOICED_FRAMES: int
VAD_MIN_RMS_DBFS: float
VAD_MIN_VOICED_RUN_FRAMES: int
VAD_START_TRIGGER_MS: int
STT_MOONSHINE_MODEL: str
STT_MOONSHINE_LANGUAGE: str
BARGE_IN_ENABLED: bool
BARGE_IN_MIN_VOICED_MS: int
BARGE_IN_RMS_MARGIN_DBFS: float
EARCONS_ENABLED: bool
USER_BACKGROUND: str
SYSTEM_PROMPT: str


_RUNTIME_EXPORTS: dict[str, str] = {
    "GEMINI_API_KEY": "gemini_api_key",
    "OPENAI_API_KEY": "openai_api_key",
    "LIVE_MODEL": "live_model",
    "REASONING_EFFORT": "reasoning_effort",
    "OBSIDIAN_VAULT_PATH": "obsidian_vault_path",
    "PUSH_TO_TALK_KEY": "push_to_talk_key",
    "TOGGLE_KEY": "toggle_key",
    "CAMERA_DEVICE_INDEX": "camera_device_index",
    "MIC_DEVICE_INDEX": "mic_device_index",
    "VOICE": "voice",
    "INPUT_MODE": "input_mode",
    "VAD_SENSITIVITY": "vad_sensitivity",
    "VAD_SILENCE_TIMEOUT": "vad_silence_timeout",
    "VAD_EARLY_STT_TIMEOUT": "vad_early_stt_timeout",
    "VAD_MIN_DURATION": "vad_min_duration",
    "VAD_MIN_VOICED_RATIO": "vad_min_voiced_ratio",
    "VAD_MIN_VOICED_FRAMES": "vad_min_voiced_frames",
    "VAD_MIN_RMS_DBFS": "vad_min_rms_dbfs",
    "VAD_MIN_VOICED_RUN_FRAMES": "vad_min_voiced_run_frames",
    "VAD_START_TRIGGER_MS": "vad_start_trigger_ms",
    "STT_MOONSHINE_MODEL": "stt_moonshine_model",
    "STT_MOONSHINE_LANGUAGE": "stt_moonshine_language",
    "BARGE_IN_ENABLED": "barge_in_enabled",
    "BARGE_IN_MIN_VOICED_MS": "barge_in_min_voiced_ms",
    "BARGE_IN_RMS_MARGIN_DBFS": "barge_in_rms_margin_dbfs",
    "EARCONS_ENABLED": "earcons_enabled",
    "USER_BACKGROUND": "user_background",
    "SYSTEM_PROMPT": "system_prompt",
}


def _resolve_api_key(slug: str) -> tuple[str, str]:
    env_name = _API_KEY_ENV_VARS[slug]
    env_value = _as_str(os.getenv(env_name, ""), "")
    if env_value:
        return env_value, "env"

    try:
        keychain_value = _as_str(secrets_store.get_api_key(slug), "")
    except secrets_store.SecretsStoreError as exc:
        _log.warning(
            "Keychain read failed for %s. error=%s",
            slug,
            exc,
        )
    else:
        if keychain_value:
            return keychain_value, "keychain"

    return "", "missing"


def _settings_from_config(user_config: dict) -> RuntimeSettings:
    global _api_key_sources

    resolved_api_keys: dict[str, str] = {}
    api_key_sources: dict[str, str] = {}
    for slug in API_KEY_SLUGS:
        value, source = _resolve_api_key(slug)
        resolved_api_keys[slug] = value
        api_key_sources[slug] = source

    _api_key_sources = api_key_sources

    user_background = _as_str(user_config.get("user_background", ""), "")
    values: dict[str, object] = {}
    for spec in _RUNTIME_SETTING_SPECS:
        raw = user_config.get(spec.config_key, spec.default)
        if spec.env_var and not raw:
            raw = os.getenv(spec.env_var, "")
        values[spec.runtime_field] = spec.coerce(raw, spec.default)

    values["gemini_api_key"] = resolved_api_keys["gemini"]
    values["openai_api_key"] = resolved_api_keys["openai"]
    values["user_background"] = user_background
    values["system_prompt"] = _build_system_prompt(
        user_background,
        obsidian_enabled=bool(values["obsidian_vault_path"]),
    )
    return RuntimeSettings(**values)


def _apply_runtime_settings(settings: RuntimeSettings) -> None:
    global _api_keys

    _api_keys = {
        "gemini": settings.gemini_api_key,
        "openai": settings.openai_api_key,
    }
    module_globals = globals()
    for export_name, field_name in _RUNTIME_EXPORTS.items():
        module_globals[export_name] = getattr(settings, field_name)


def _log_runtime_settings(settings: RuntimeSettings, prefix: str = "Loaded") -> None:
    _log.info(
        "API keys: Gemini=%s | OpenAI=%s",
        "set" if settings.gemini_api_key else "missing",
        "set" if settings.openai_api_key else "missing",
    )
    if settings.obsidian_vault_path:
        _log.info("Obsidian vault path: %s", settings.obsidian_vault_path)
    else:
        _log.warning("OBSIDIAN_VAULT_PATH not set -- notes feature disabled")

    _log.info(
        (
            "%s settings: model=%s | effort=%s | hotkey=%s | camera=%d | voice=%s | input_mode=%s | log_level=%s"
        ),
        prefix,
        settings.live_model,
        settings.reasoning_effort,
        settings.push_to_talk_key,
        settings.camera_device_index,
        settings.voice,
        settings.input_mode,
        _log_level_name,
    )
    _log.info(
        (
            "VAD: sensitivity=%d | silence_timeout=%.1fs | min_duration=%.1fs | "
            "min_voiced_ratio=%.2f | min_voiced_frames=%d | "
            "min_rms_dbfs=%.1f | min_voiced_run_frames=%d | start_trigger_ms=%d"
        ),
        settings.vad_sensitivity,
        settings.vad_silence_timeout,
        settings.vad_min_duration,
        settings.vad_min_voiced_ratio,
        settings.vad_min_voiced_frames,
        settings.vad_min_rms_dbfs,
        settings.vad_min_voiced_run_frames,
        settings.vad_start_trigger_ms,
    )
    _log.info(
        "STT: moonshine_model=%s | moonshine_language=%s",
        settings.stt_moonshine_model,
        settings.stt_moonshine_language,
    )


def get_runtime_settings() -> RuntimeSettings:
    return _runtime_settings


def get_api_key_sources() -> dict[str, str]:
    return dict(_api_key_sources)


def live_model_details(model: str | None = None) -> dict[str, str]:
    """Return metadata for a supported live model."""
    return LIVE_MODELS[model or LIVE_MODEL]


def active_api_key_slug(settings: RuntimeSettings | None = None) -> str:
    """Return the provider key that the selected live model needs."""
    selected = settings or get_runtime_settings()
    return LIVE_MODELS[selected.live_model]["provider"]


def has_active_api_key(settings: RuntimeSettings | None = None) -> bool:
    """Return whether the selected live model has an available API key."""
    selected = settings or get_runtime_settings()
    return bool(getattr(selected, f"{active_api_key_slug(selected)}_api_key"))


# ---------------------------------------------------------------------------
# Config persistence helpers (used by setup wizard and settings)
# ---------------------------------------------------------------------------

def _read_config_text() -> str:
    """Read config.toml as raw text."""
    if CONFIG_PATH.exists():
        return CONFIG_PATH.read_text(encoding="utf-8")
    return _DEFAULT_CONFIG_TEMPLATE


def _write_config_text(text: str) -> None:
    """Write raw text to config.toml."""
    CONFIG_PATH.write_text(text, encoding="utf-8")


def is_setup_complete() -> bool:
    """Check whether the first-run wizard has been completed."""
    return bool(_user_config.get("setup_complete", False))


def _escape_toml_basic_string(value: str) -> str:
    return (
        value.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\r", "")
        .replace("\n", "\\n")
    )


def set_api_key(slug: str, value: str) -> None:
    """Persist one API key in Apple Keychain."""
    if slug not in API_KEY_SLUGS:
        raise ValueError(f"Unknown API key slug: {slug!r}")

    normalized = value.strip()
    if normalized:
        secrets_store.set_api_key(slug, normalized)
    else:
        secrets_store.delete_api_key(slug)


def clear_api_key(slug: str) -> None:
    """Clear one API key from persisted storage."""
    set_api_key(slug, "")


def save_api_key(openai: str) -> None:
    """Persist the OpenAI API key in Apple Keychain."""
    set_api_key("openai", openai)


def save_live_model(model: str) -> None:
    """Persist the selected Gemini Live or GPT Live model."""
    if model not in LIVE_MODELS:
        raise ValueError(f"Unknown live model: {model!r}")
    _set_top_level_value("live_model", f'"{model}"')


def save_reasoning_effort(effort: str) -> None:
    """Persist the selected live-model reasoning effort."""
    normalized = effort.strip().lower()
    if normalized not in {"low", "medium", "high"}:
        raise ValueError(f"Unknown reasoning effort: {effort!r}")
    _set_top_level_value("reasoning_effort", f'"{normalized}"')


def _set_top_level_value(key: str, value: str) -> None:
    """Set a top-level key in config.toml, uncommenting if necessary."""
    text = _read_config_text()
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
    _write_config_text(text)


def mark_setup_complete() -> None:
    """Set ``setup_complete = true`` in config.toml."""
    _set_top_level_value("setup_complete", "true")


def set_camera_index(index: int, persist: bool = True) -> None:
    """Update the active camera index and optionally persist it."""
    global CAMERA_DEVICE_INDEX
    CAMERA_DEVICE_INDEX = int(index)
    if persist:
        _set_top_level_value("camera_index", str(CAMERA_DEVICE_INDEX))


def save_camera_index(index: int) -> None:
    """Persist the chosen camera index to config.toml."""
    set_camera_index(index, persist=True)


def set_mic_index(index: int, persist: bool = True) -> None:
    """Update the active microphone index and optionally persist it."""
    global MIC_DEVICE_INDEX
    MIC_DEVICE_INDEX = int(index)
    if persist:
        _set_top_level_value("mic_index", str(MIC_DEVICE_INDEX))


def save_mic_index(index: int) -> None:
    """Persist the chosen microphone device index to config.toml."""
    set_mic_index(index, persist=True)


def save_user_background(text: str) -> None:
    """Persist the user background description to config.toml."""
    escaped = _escape_toml_basic_string(text)
    _set_top_level_value("user_background", f'"{escaped}"')


def save_obsidian_vault_path(path: str) -> None:
    """Persist the Obsidian vault path to config.toml."""
    escaped = _escape_toml_basic_string(path.replace("\\", "/"))
    _set_top_level_value("obsidian_vault_path", f'"{escaped}"')


def save_voice(voice: str) -> None:
    """Persist the Realtime voice."""
    escaped = _escape_toml_basic_string(voice.strip())
    _set_top_level_value("voice", f'"{escaped}"')


def save_barge_in_enabled(enabled: bool) -> None:
    """Persist whether speaking over an answer interrupts it."""
    _set_top_level_value("barge_in_enabled", "true" if enabled else "false")


def save_input_mode(mode: str) -> None:
    """Persist the selected voice input mode."""
    if mode not in {"voice_activation", "push_to_talk"}:
        raise ValueError(f"Unknown input mode: {mode!r}")
    _set_top_level_value("input_mode", f'"{mode}"')


def reload() -> None:
    """Re-read config.toml and update module-level constants.

    Call after the setup wizard writes new values so that components created
    afterward pick up the fresh configuration.
    """
    global _user_config, _runtime_settings

    _user_config, load_error = _load_user_config()
    if load_error is not None:
        _log.warning(
            "Config reload found invalid TOML; using defaults. path=%s error=%s",
            CONFIG_PATH,
            load_error,
        )

    _runtime_settings = _settings_from_config(_user_config)
    _apply_runtime_settings(_runtime_settings)
    _log.info("Config reloaded from %s", CONFIG_PATH)
    _log_runtime_settings(_runtime_settings, prefix="Reloaded")


_runtime_settings = _settings_from_config(_user_config)
_apply_runtime_settings(_runtime_settings)
_log_runtime_settings(_runtime_settings)
