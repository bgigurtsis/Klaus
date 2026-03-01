# Klaus

A voice-based research assistant for reading physical papers and books. Place a paper under a document camera, speak a question, and Klaus sees the page and answers aloud in a natural voice.

**Stack:** Claude Sonnet 4 (vision + tool use) | Moonshine Medium local STT | OpenAI gpt-4o-mini-tts | Tavily web search | PyQt6 desktop UI | SQLite memory

## Quick Start

Requires Python 3.11+, a document camera or webcam, a microphone, and speakers. Windows only (global hotkeys use the `keyboard` library).

```
git clone https://github.com/yourusername/Klaus.git
cd Klaus
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
```

Add your API keys to `.env`:

| Key | Where to get it |
|-----|-----------------|
| `ANTHROPIC_API_KEY` | [console.anthropic.com](https://console.anthropic.com/) |
| `OPENAI_API_KEY` | [platform.openai.com](https://platform.openai.com/) |
| `TAVILY_API_KEY` | [tavily.com](https://tavily.com/) (free tier: 1,000 searches/mo) |
| `OBSIDIAN_VAULT_PATH` | Path to your Obsidian vault (optional, enables note-saving) |

Run:

```
python -m klaus.main
```

## Usage

| Action | How |
|--------|-----|
| Ask a question (push-to-talk) | Hold **F2**, speak, release |
| Ask a question (voice activation) | Just speak (default mode) |
| Toggle input mode | **F3** |
| Switch papers | Session dropdown in the header |
| New session | **+ New Session** |
| Replay an answer | Replay button on any response card |
| Stop playback | Stop button in the status bar |
| Save notes | Ask Klaus to save to an Obsidian file by name |

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

## Latency & Cost

End-to-end latency from question to first spoken word is 2-3 seconds (STT + Claude + first TTS chunk). TTS streams sentence-by-sentence so playback starts before the full response is generated.

| Usage | Approx. cost |
|-------|-------------|
| 10 questions | ~$0.05 |
| 50 questions | ~$0.25 |
| 100 questions/day | ~$2.50-3.50/day |

Largest cost driver is Claude (vision + context window). STT is free (local). TTS is $0.015/min of generated audio.

## Module Layout

| Module | Role |
|--------|------|
| `config.py` | Config, API keys, system prompt, voice settings |
| `camera.py` | OpenCV background thread, frame capture, base64/thumbnail export |
| `audio.py` | Push-to-talk recorder (sounddevice), VAD recorder, WAV buffer |
| `stt.py` | Moonshine Voice local speech-to-text |
| `tts.py` | OpenAI gpt-4o-mini-tts with sentence-level streaming |
| `brain.py` | Claude vision + tool use, conversation history, tool-use loop |
| `search.py` | Tavily web search, exposed as a Claude tool |
| `notes.py` | Obsidian vault note-taking, exposed as Claude tools |
| `memory.py` | SQLite persistence (sessions, exchanges, knowledge profile) |
| `ui/` | PyQt6 GUI (main window, camera, chat, sessions, status, theme) |
| `main.py` | Wires everything together, hotkey listener, Qt signal bridge |

## Data

- Config: `~/.klaus/config.toml`
- Database: `~/.klaus/klaus.db` (sessions, exchanges, knowledge profile)
- No images stored, only a short hash of each page capture
- Delete the database to start fresh
