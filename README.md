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

## Install

Requires Python 3.11+, a camera or webcam, a microphone, and speakers.

### Windows

1. Install [Python 3.11+](https://www.python.org/downloads/) (check "Add to PATH" during install).

2. Install [Visual C++ Build Tools](https://visualstudio.microsoft.com/visual-cpp-build-tools/) -- needed to compile `webrtcvad`. Select the "Desktop development with C++" workload.

3. Set up [pipx](https://pipx.pypa.io/) (one-time, installs apps with PATH handled automatically):

```
pip install pipx
pipx ensurepath
```

Close and reopen your terminal so the new PATH takes effect.

4. Install Klaus:

```
pipx install klaus-assistant
klaus
```

Global hotkeys (F2/F3) work without app focus. No extra permissions required on Windows.

### macOS

Install via Homebrew:

```
brew tap bgigurtsis/klaus
brew install klaus
klaus
```

Or manually:

1. Install Python 3.11+ and PortAudio:

```
brew install python@3.13 portaudio
```

2. Set up pipx and install Klaus:

```
pip install pipx
pipx ensurepath
pipx install klaus-assistant
klaus
```

On macOS, the system will prompt you to grant **Accessibility** permission to your terminal (or Klaus) for global hotkeys to work. Go to System Settings > Privacy & Security > Accessibility and enable the app.

### From source (development)

```
git clone https://github.com/bgigurtsis/Klaus.git
cd Klaus
pip install -e .
klaus
```

### First launch

On first launch, a setup wizard walks you through API key entry, camera selection, microphone test, voice model download, and an optional background profile. No manual config file editing required.

### API keys

Klaus needs three API keys. The setup wizard will ask for them, or you can add them to `~/.klaus/config.toml` under `[api_keys]`:

| Key | Where to get it |
|-----|-----------------|
| Anthropic | [console.anthropic.com/settings/keys](https://console.anthropic.com/settings/keys) |
| OpenAI | [platform.openai.com/api-keys](https://platform.openai.com/api-keys) |
| Tavily | [app.tavily.com](https://app.tavily.com/home) (free tier: 1,000 searches/mo) |

Optional: set `OBSIDIAN_VAULT_PATH` in `.env` to enable note-saving to your Obsidian vault.

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
| Change settings | Gear icon in the header |

Klaus captures the page image when your question ends and sends it with your transcript to Claude. If Claude is uncertain about a claim, it searches the web via Tavily before answering.

## Using a Phone as Your Camera

You don't need a dedicated document camera. A phone on a cheap tripod pointed down at your desk works well.

**macOS** -- Continuity Camera works natively. Any iPhone running iOS 16+ paired with a Mac on macOS Ventura+ appears as a webcam automatically. No extra app needed; just select the iPhone in Klaus settings.

**Windows** -- Install [DroidCam](https://www.dev47apps.com/) (free, Android and iOS) or [Camo](https://reincubate.com/camo/) (free tier, Android and iOS). These create a virtual webcam that Klaus picks up. Connect your phone, then select the virtual camera in Klaus settings.

**Mounting** -- An adjustable gooseneck phone mount or a small phone tripod aimed straight down at the reading surface gives the best results. These run about $10-15 on Amazon. Make sure the full page is visible in the camera preview.

Klaus auto-detects portrait orientation from phone cameras and rotates the image to landscape. If auto-detection gets it wrong, set `camera_rotation` in `~/.klaus/config.toml` to `"none"`, `"90"`, `"180"`, or `"270"`.

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
