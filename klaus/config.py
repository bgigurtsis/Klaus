import logging
import os
import re
import tomllib
from pathlib import Path
from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

DATA_DIR = Path.home() / ".klaus"
DB_PATH = DATA_DIR / "klaus.db"
CONFIG_PATH = DATA_DIR / "config.toml"

_DEFAULT_CONFIG_TEMPLATE = """\
# Klaus configuration
# Uncomment and edit any line to override the default.

# Set to true after the setup wizard completes.
# setup_complete = false

# Push-to-talk hotkey (default: F2)
# hotkey = "F2"

# Camera device index (default: 0)
# camera_index = 0

# Camera resolution (default: 1920x1080)
# camera_width = 1920
# camera_height = 1080

# Camera rotation (default: auto)
# "auto" rotates portrait frames to landscape; "none" disables rotation.
# Fixed angles: "90", "180", "270"
# camera_rotation = "auto"

# TTS voice (default: marin)
# Options: coral, nova, alloy, ash, ballad, echo, fable, onyx, sage, shimmer, verse, cedar, marin
# voice = "marin"

# TTS playback speed 0.25-4.0 (default: 1.0)
# tts_speed = 1.0

# Input mode (default: voice_activation)
# Options: voice_activation, push_to_talk
# input_mode = "voice_activation"

# Voice activation sensitivity 0-3 (default: 3, higher = more aggressive filtering)
# vad_sensitivity = 3

# Seconds of silence before voice activation finalizes (default: 1.5)
# vad_silence_timeout = 1.5

# Require enough voiced content before accepting a VAD utterance.
# Helps reject fan/hum/background-noise false triggers.
# Minimum utterance duration in seconds (default: 0.5)
# vad_min_duration = 0.5
# Minimum voiced-frame ratio across an utterance (default: 0.35)
# vad_min_voiced_ratio = 0.35
# Minimum voiced 30ms frames in an utterance (default: 8)
# vad_min_voiced_frames = 8
#
# Secondary local quality gate (runs after WebRTC VAD checks).
# Minimum RMS loudness in dBFS (default: -37.0, higher = stricter)
# vad_min_rms_dbfs = -37.0
# Minimum strongest contiguous voiced run of 30ms frames (default: 6)
# vad_min_voiced_run_frames = 6
#
# Moonshine STT model size (default: "medium")
# Options: tiny, small, medium
# stt_moonshine_model = "medium"
# Moonshine language code (default: "en")
# stt_moonshine_language = "en"

# Optional: describe your background so Klaus can tailor explanations.
# user_background = ""

# Log level (default: INFO)
# Options: DEBUG, INFO, WARNING, ERROR
# log_level = "INFO"

[api_keys]
# anthropic = ""
# openai = ""
# tavily = ""
"""

# ---------------------------------------------------------------------------
# Load user config (TOML)
# ---------------------------------------------------------------------------

DATA_DIR.mkdir(parents=True, exist_ok=True)

_user_config: dict = {}
if CONFIG_PATH.exists():
    with open(CONFIG_PATH, "rb") as _f:
        _user_config = tomllib.load(_f)
else:
    CONFIG_PATH.write_text(_DEFAULT_CONFIG_TEMPLATE, encoding="utf-8")

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

# ---------------------------------------------------------------------------
# API keys -- TOML [api_keys] section first, .env fallback
# ---------------------------------------------------------------------------

load_dotenv()

_api_keys: dict = _user_config.get("api_keys", {})

ANTHROPIC_API_KEY: str = _api_keys.get("anthropic", "") or os.getenv("ANTHROPIC_API_KEY", "")
OPENAI_API_KEY: str = _api_keys.get("openai", "") or os.getenv("OPENAI_API_KEY", "")
TAVILY_API_KEY: str = _api_keys.get("tavily", "") or os.getenv("TAVILY_API_KEY", "")
OBSIDIAN_VAULT_PATH: str = os.getenv("OBSIDIAN_VAULT_PATH", "")

_log.info(
    "API keys: Anthropic=%s | OpenAI=%s | Tavily=%s",
    "set" if ANTHROPIC_API_KEY else "missing",
    "set" if OPENAI_API_KEY else "missing",
    "set" if TAVILY_API_KEY else "missing",
)
if OBSIDIAN_VAULT_PATH:
    _log.info("Obsidian vault path: %s", OBSIDIAN_VAULT_PATH)
else:
    _log.warning("OBSIDIAN_VAULT_PATH not set -- notes feature disabled")

# ---------------------------------------------------------------------------
# Models (not user-configurable)
# ---------------------------------------------------------------------------

CLAUDE_MODEL = "claude-sonnet-4-6"
TTS_MODEL = "gpt-4o-mini-tts"

# ---------------------------------------------------------------------------
# User-configurable settings (overridable via config.toml)
# ---------------------------------------------------------------------------

PUSH_TO_TALK_KEY: str = _user_config.get("hotkey", "F2")
CAMERA_DEVICE_INDEX: int = _user_config.get("camera_index", 0)
CAMERA_FRAME_WIDTH: int = _user_config.get("camera_width", 1920)
CAMERA_FRAME_HEIGHT: int = _user_config.get("camera_height", 1080)
CAMERA_ROTATION: str = str(_user_config.get("camera_rotation", "auto"))
TTS_VOICE: str = _user_config.get("voice", "cedar")
TTS_SPEED: float = float(_user_config.get("tts_speed", 1.0))

INPUT_MODE: str = _user_config.get("input_mode", "voice_activation")
VAD_SENSITIVITY: int = int(_user_config.get("vad_sensitivity", 3))
VAD_SILENCE_TIMEOUT: float = float(_user_config.get("vad_silence_timeout", 1.5))
VAD_MIN_DURATION: float = float(_user_config.get("vad_min_duration", 0.5))
VAD_MIN_VOICED_RATIO: float = float(_user_config.get("vad_min_voiced_ratio", 0.28))
VAD_MIN_VOICED_FRAMES: int = int(_user_config.get("vad_min_voiced_frames", 8))
VAD_MIN_RMS_DBFS: float = float(_user_config.get("vad_min_rms_dbfs", -37.0))
VAD_MIN_VOICED_RUN_FRAMES: int = int(_user_config.get("vad_min_voiced_run_frames", 6))

STT_MOONSHINE_MODEL: str = str(_user_config.get("stt_moonshine_model", "medium"))
STT_MOONSHINE_LANGUAGE: str = str(_user_config.get("stt_moonshine_language", "en"))

USER_BACKGROUND: str = str(_user_config.get("user_background", ""))

TTS_VOICE_INSTRUCTIONS = (
    "Speak at a natural conversational pace, not slow or deliberate. "
    "You are a sharp colleague giving a quick answer across a desk. "
    "Be direct and matter-of-fact, not performative. No vocal fry, no uptalk."
)

_log.info(
    "Settings: hotkey=%s | camera=%d (%dx%d) | voice=%s (speed=%.2f) | input_mode=%s | log_level=%s",
    PUSH_TO_TALK_KEY, CAMERA_DEVICE_INDEX,
    CAMERA_FRAME_WIDTH, CAMERA_FRAME_HEIGHT,
    TTS_VOICE, TTS_SPEED, INPUT_MODE, _log_level_name,
)
_log.info(
    (
        "VAD: sensitivity=%d | silence_timeout=%.1fs | min_duration=%.1fs | "
        "min_voiced_ratio=%.2f | min_voiced_frames=%d | "
        "min_rms_dbfs=%.1f | min_voiced_run_frames=%d"
    ),
    VAD_SENSITIVITY,
    VAD_SILENCE_TIMEOUT,
    VAD_MIN_DURATION,
    VAD_MIN_VOICED_RATIO,
    VAD_MIN_VOICED_FRAMES,
    VAD_MIN_RMS_DBFS,
    VAD_MIN_VOICED_RUN_FRAMES,
)
_log.info(
    "STT: moonshine_model=%s | moonshine_language=%s",
    STT_MOONSHINE_MODEL, STT_MOONSHINE_LANGUAGE,
)

def _build_system_prompt() -> str:
    """Assemble the system prompt, injecting user background when available."""
    intro = (
        "You are Klaus, a knowledgeable and articulate research companion. "
        "The user is reading a physical paper or book, which you can see "
        "via their document camera."
    )
    if USER_BACKGROUND:
        intro += " " + USER_BACKGROUND.strip()
    return intro + "\n\n" + _SYSTEM_PROMPT_BODY


_SYSTEM_PROMPT_BODY = """\
Brevity rule: three sentences is not a minimum. It is a ceiling. Give \
the shortest accurate answer, then stop. Do not add a second paragraph, \
do not connect it back to the page, do not offer additional context. \
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

Your job:

- The image from the document camera is context, not a prompt. Always \
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
- If you are unsure about something, say so. Do not confabulate. Use \
web search to verify claims, look up referenced papers or authors, \
check definitions, or find additional context when your own knowledge \
is insufficient or uncertain. It is always better to search and give \
an accurate answer than to guess.

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

SYSTEM_PROMPT: str = _build_system_prompt()


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


def save_api_keys(anthropic: str, openai: str, tavily: str) -> None:
    """Write API keys to the [api_keys] section of config.toml."""
    text = _read_config_text()
    new_section = (
        "[api_keys]\n"
        f'anthropic = "{anthropic}"\n'
        f'openai = "{openai}"\n'
        f'tavily = "{tavily}"\n'
    )
    section_re = re.compile(
        r"\[api_keys\].*?(?=\n\[|\Z)", re.DOTALL,
    )
    if section_re.search(text):
        text = section_re.sub(new_section.rstrip(), text)
    else:
        text = text.rstrip() + "\n\n" + new_section
    _write_config_text(text)


def _set_top_level_value(key: str, value: str) -> None:
    """Set a top-level key in config.toml, uncommenting if necessary."""
    text = _read_config_text()
    uncommented = re.compile(rf"^{re.escape(key)}\s*=\s*.*$", re.MULTILINE)
    commented = re.compile(rf"^#\s*{re.escape(key)}\s*=\s*.*$", re.MULTILINE)
    line = f"{key} = {value}"

    if uncommented.search(text):
        text = uncommented.sub(line, text)
    elif commented.search(text):
        text = commented.sub(line, text)
    else:
        first_newline = text.index("\n") if "\n" in text else len(text)
        text = text[:first_newline] + "\n" + line + text[first_newline:]
    _write_config_text(text)


def mark_setup_complete() -> None:
    """Set ``setup_complete = true`` in config.toml."""
    _set_top_level_value("setup_complete", "true")


def save_camera_index(index: int) -> None:
    """Persist the chosen camera index to config.toml."""
    _set_top_level_value("camera_index", str(index))


def save_user_background(text: str) -> None:
    """Persist the user background description to config.toml."""
    escaped = text.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
    _set_top_level_value("user_background", f'"{escaped}"')


def reload() -> None:
    """Re-read config.toml and update module-level constants.

    Call after the setup wizard writes new values so that components created
    afterward pick up the fresh configuration.
    """
    global _user_config, _api_keys
    global ANTHROPIC_API_KEY, OPENAI_API_KEY, TAVILY_API_KEY
    global CAMERA_DEVICE_INDEX, CAMERA_FRAME_WIDTH, CAMERA_FRAME_HEIGHT, CAMERA_ROTATION
    global USER_BACKGROUND, SYSTEM_PROMPT

    if CONFIG_PATH.exists():
        with open(CONFIG_PATH, "rb") as f:
            _user_config = tomllib.load(f)
    else:
        _user_config = {}

    _api_keys = _user_config.get("api_keys", {})
    ANTHROPIC_API_KEY = _api_keys.get("anthropic", "") or os.getenv("ANTHROPIC_API_KEY", "")
    OPENAI_API_KEY = _api_keys.get("openai", "") or os.getenv("OPENAI_API_KEY", "")
    TAVILY_API_KEY = _api_keys.get("tavily", "") or os.getenv("TAVILY_API_KEY", "")

    CAMERA_DEVICE_INDEX = _user_config.get("camera_index", 0)
    CAMERA_FRAME_WIDTH = _user_config.get("camera_width", 1920)
    CAMERA_FRAME_HEIGHT = _user_config.get("camera_height", 1080)
    CAMERA_ROTATION = str(_user_config.get("camera_rotation", "auto"))

    USER_BACKGROUND = str(_user_config.get("user_background", ""))
    SYSTEM_PROMPT = _build_system_prompt()

    _log.info("Config reloaded from %s", CONFIG_PATH)
    _log.info(
        "API keys: Anthropic=%s | OpenAI=%s | Tavily=%s",
        "set" if ANTHROPIC_API_KEY else "missing",
        "set" if OPENAI_API_KEY else "missing",
        "set" if TAVILY_API_KEY else "missing",
    )
