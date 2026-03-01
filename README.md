# Klaus

A voice-based research assistant for reading physical papers and books. Place a paper under a document camera (or phone on a tripod), speak a question, and Klaus sees the page and answers aloud in a natural voice.

**Stack:** Claude Sonnet 4 (vision + tool use) | Moonshine Medium local STT | OpenAI gpt-4o-mini-tts | Tavily web search | PyQt6 desktop UI | SQLite memory

**Platforms:** Windows and macOS

## Quick Setup

**Windows:**

```
pip install pipx && pipx ensurepath
```

Restart your terminal, then:

```
pipx install klaus-assistant
klaus
```

**macOS:**

```
brew tap bgigurtsis/klaus
brew install klaus
klaus
```

On first launch, a setup wizard walks you through API keys, camera, mic, and voice model setup.

### Updating

**Windows:** `pipx upgrade klaus-assistant`

**macOS:** `brew upgrade klaus`

## Camera Setup

**Required:** A camera is required for Klaus to ingest what you're currently reading and to use it as context.

A USB document camera (AKA visualiser) is reccomended. Alternatively, a phone on a gooseneck mount (~$10-15) pointed straight down at your reading surface works. Either should gives Klaus a clear, stable view of the full page.

Some reccomended apps to connect your phone to your computer are listed below: 

| Setup | App |
|-------|-----|
| macOS + iPhone | Built-in -- [Continuity Camera](https://support.apple.com/en-us/102546) (iOS 16+, macOS Ventura+, no install needed) |
| macOS + Android | [Camo](https://reincubate.com/camo/) (free, 1080p) -- install on phone + Mac, pair via QR or USB |
| Windows + Android | [DroidCam](https://www.dev47apps.com/) (free) -- install on phone + PC, connect over Wi-Fi or USB |
| Windows + iPhone | [Camo](https://reincubate.com/camo/) (free, 1080p) -- install on phone + PC, pair via QR or USB |

Klaus auto-detects portrait orientation and rotates the image. Override with `camera_rotation` in `~/.klaus/config.toml` if needed.


## Other install options

**Prerequisites:** Python 3.11+, camera, mic, speakers. On Windows, install [Visual C++ Build Tools](https://visualstudio.microsoft.com/visual-cpp-build-tools/) (Desktop development with C++) so `webrtcvad` can compile. On macOS without Homebrew: `brew install python@3.13 portaudio`.

**From source (development):**

```
git clone https://github.com/bgigurtsis/Klaus.git
cd Klaus
pip install -e .
klaus
```

**API keys:** The setup wizard asks for them on first launch, or add to `~/.klaus/config.toml` under `[api_keys]`: [Anthropic](https://console.anthropic.com/settings/keys), [OpenAI](https://platform.openai.com/api-keys), [Tavily](https://app.tavily.com/home) (free tier: 1,000 searches/mo). Optional: `OBSIDIAN_VAULT_PATH` in `.env` for Obsidian notes.

## Latency & Cost

End-to-end latency from question to first spoken word is 2-3 seconds (STT + Claude + first TTS chunk). TTS streams sentence-by-sentence so playback starts before the full response is generated.

| Usage | Approx. cost |
|-------|-------------|
| 10 questions | ~$0.05 |
| 50 questions | ~$0.25 |
| 100 questions/day | ~$2.50-3.50/day |

Largest cost driver is Claude (vision + context window). STT is free (local). TTS is $0.015/min of generated audio.

## Usage

Klaus captures the page image when your question ends and sends it with your transcript to Claude. If Claude is uncertain about a claim, it searches the web via Tavily before answering.

## Configuration

Settings live in `~/.klaus/config.toml` (created on first run). Edit any line to override defaults:

| Setting | Default | Notes |
|---------|---------|-------|
| `hotkey` | `F2` | Push-to-talk key, works without app focus |
| `input_mode` | `voice_activation` | Or `push_to_talk` |
| `voice` | `cedar` | Options: coral, nova, alloy, ash, ballad, echo, fable, onyx, sage, shimmer, verse, cedar, marin |
| `tts_speed` | `1.0` | 0.25 to 4.0 |
| `camera_index` | `0` | Change if you have multiple cameras |
| `camera_rotation` | `auto` | `auto`, `none`, `90`, `180`, `270` |
| `camera_width` / `camera_height` | `1920` / `1080` | Camera resolution |
| `vad_sensitivity` | `3` | 0-3, higher = more aggressive noise filtering |
| `vad_silence_timeout` | `1.5` | Seconds of silence before voice activation finalizes |
| `log_level` | `INFO` | DEBUG, INFO, WARNING, ERROR |

## Architecture

```
Mic --> WebRTC VAD --> Moonshine Medium (local STT) --\
                                                       --> Claude (vision + tools) --> TTS --> Speakers
Camera (live feed) -----------------------------------/        |
                                                               +--> Tavily (web search)
                                                               +--> Obsidian (notes)
                                                               +--> SQLite (memory)
                                                               +--> Chat UI
```

Speech-to-text runs entirely locally via Moonshine Medium (245M params, ~300ms latency, no API cost). Voice activation uses WebRTC VAD with multi-stage filtering (voiced ratio, RMS loudness, contiguous voiced runs) to reject background noise before audio reaches STT.


## Module Layout

| Module | Role |
|--------|------|
| `config.py` | Config, API keys, system prompt, voice settings |
| `camera.py` | OpenCV background thread, frame capture, auto-rotation |
| `audio.py` | Push-to-talk recorder (sounddevice), VAD recorder, WAV buffer |
| `stt.py` | Moonshine Voice local speech-to-text |
| `tts.py` | OpenAI gpt-4o-mini-tts with sentence-level streaming |
| `brain.py` | Claude vision + tool use, conversation history, tool-use loop |
| `search.py` | Tavily web search, exposed as a Claude tool |
| `notes.py` | Obsidian vault note-taking, exposed as Claude tools |
| `memory.py` | SQLite persistence (sessions, exchanges, knowledge profile) |
| `ui/` | PyQt6 GUI (main window, camera, chat, sessions, status, theme, setup wizard, settings) |
| `main.py` | Wires everything together, hotkey listener, Qt signal bridge |

## Data

- Config: `~/.klaus/config.toml`
- Database: `~/.klaus/klaus.db` (sessions, exchanges, knowledge profile)
- No images stored, only a short hash of each page capture
- Delete the database to start fresh
