# Klaus

Klaus is a desktop voice assistant built for reading physical papers and books. You place a page under a document camera (or phone on a tripod), ask a question out loud, and Klaus answers in natural speech while keeping the page context and conversation visible in the UI. 

The experience is tuned for fast study loops: read, ask, clarify, and continue without switching between typing and separate search tools.

Klaus also searches the web when necessary to answer your query, and has the ability to write notes directly to your obsidian vault when asked.

Under the hood, WebRTC voice activation detection or push to talk feeds Moonshine Medium (local speech to text model), then a hybrid router (local heuristics with `claude-haiku-4-5` fallback) decides whether to include camera image, history, memory, and notes context. 

Main reasoning loop runs on `claude-sonnet-4-6`. Tools include Tavily for search and optional Obsidian note actions. Output is streamed sentence by sentence to OpenAI `gpt-4o-mini-tts`. End to end latency is around 2-4 seconds.

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

> **macOS input monitoring:** When launching Klaus from a terminal, macOS may prompt you to grant that terminal app Accessibility (input monitoring) permission. This is required for global hotkeys — specifically, the push-to-talk and voice-activation toggle keys — to work while Klaus is not in focus. If you'd prefer not to grant this permission, simply deny the prompt; you can still switch input modes using the buttons in the Klaus UI.

> **macOS + Python 3.14:** `pynput` global hotkeys can crash on macOS 26. Klaus now disables global hotkeys on this combo and keeps in-app hotkeys active; use Python 3.13 for stable global hotkeys.

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

**Prerequisites:** Python 3.11-3.13, camera, mic, speakers. On Windows, install [Visual C++ Build Tools](https://visualstudio.microsoft.com/visual-cpp-build-tools/) (Desktop development with C++) so `webrtcvad` can compile. On macOS without Homebrew: `brew install python@3.13 portaudio`.

**From source (development):**

```
git clone https://github.com/bgigurtsis/Klaus.git
cd Klaus
pip install -e .
klaus
```

**API keys:** The setup wizard asks for them on first launch. On macOS, Klaus stores them in Apple Keychain and resolves keys in this order: environment variables (`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `TAVILY_API_KEY`) first, then Keychain, then legacy `~/.klaus/config.toml` fallback if Keychain is unavailable. Provider links: [Anthropic](https://console.anthropic.com/settings/keys), [OpenAI](https://platform.openai.com/api-keys), [Tavily](https://app.tavily.com/home) (free tier: 1,000 searches/mo). Optional: `OBSIDIAN_VAULT_PATH` in `.env` for Obsidian notes.

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
| `toggle_key` | `§` (macOS) / `F3` (Windows) | Toggle between `voice_activation` and `push_to_talk` |
| `input_mode` | `voice_activation` | Or `push_to_talk` |
| `voice` | `cedar` | Options: coral, nova, alloy, ash, ballad, echo, fable, onyx, sage, shimmer, verse, cedar, marin |
| `tts_speed` | `1.0` | 0.25 to 4.0 |
| `camera_index` | `0` | Change if you have multiple cameras |
| `mic_index` | `-1` | `-1` uses system default microphone |
| `camera_rotation` | `auto` | `auto`, `none`, `90`, `180`, `270` |
| `camera_width` / `camera_height` | `1920` / `1080` | Camera resolution |
| `vad_sensitivity` | `3` | 0-3, higher = more aggressive noise filtering |
| `vad_silence_timeout` | `1.5` | Seconds of silence before voice activation finalizes |
| `stt_moonshine_model` | `medium` | Options: `tiny`, `small`, `medium` |
| `stt_moonshine_language` | `en` | Moonshine language code |
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
