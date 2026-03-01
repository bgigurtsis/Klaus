# CLAUDE.md

Living reference for AI assistants working on the Klaus codebase.
Last updated: 2026-03-01.

## Project Summary

Klaus is a voice-based research assistant for reading physical papers and books.
The user places a document under a camera, speaks a question (push-to-talk or
voice-activated), and Klaus sees the page via Claude's vision API, reasons about
the question, and responds aloud through text-to-speech. It runs as a PyQt6
desktop app on Windows.

## Tech Stack

- **Python 3.11+** with threads (not asyncio)
- **PyQt6** -- desktop GUI with dark theme
- **OpenCV** -- background camera thread
- **sounddevice + webrtcvad** -- audio capture, PTT and voice-activated recording
- **Moonshine Voice** -- local on-device STT (replaced OpenAI STT)
- **OpenAI gpt-4o-mini-tts** -- text-to-speech with sentence-level streaming
- **Anthropic Claude** (`claude-sonnet-4-6`) -- vision + tool use
- **Tavily** -- web search exposed as a Claude tool
- **SQLite** -- persistent memory at `~/.klaus/klaus.db`
- **Config** -- `~/.klaus/config.toml` (user settings) + `.env` (API keys)

## Module Map

### `klaus/` (core)

| Module | Lines | Purpose |
|--------|------:|---------|
| `config.py` | 252 | Config via TOML + .env, models, voice settings, system prompt |
| `main.py` | 511 | Entry point; wires all components, hotkeys, Qt signal bridge |
| `audio.py` | 390 | PushToTalkRecorder, VoiceActivatedRecorder, AudioPlayer |
| `brain.py` | 300 | Claude vision + tool-use loop, conversation history, streaming |
| `memory.py` | 254 | SQLite persistence (sessions, exchanges, knowledge_profile) |
| `tts.py` | 165 | OpenAI gpt-4o-mini-tts with sentence-level batching |
| `camera.py` | 126 | OpenCV background thread, frame capture, base64/thumbnail export |
| `stt.py` | 103 | Moonshine Voice local transcription |
| `notes.py` | 100 | Obsidian vault note-taking (set_notes_file, save_note tools) |
| `search.py` | 50 | Tavily web search tool definition + execution |

### `klaus/ui/`

| Module | Lines | Purpose |
|--------|------:|---------|
| `chat_widget.py` | 252 | Scrollable chat feed with message cards, thumbnails, replay |
| `session_panel.py` | 200 | Session list sidebar with context menu |
| `theme.py` | 158 | Centralized color palette, fonts, QSS fragments |
| `status_widget.py` | 107 | Status bar (Idle/Listening/Thinking/Speaking), mode toggle, stop |
| `main_window.py` | 105 | Top-level window layout, splitter, header |
| `camera_widget.py` | 86 | Live camera preview (~30 fps) |

## Key Architecture Decisions

- **Threading model**: PyQt6 main thread for UI; daemon threads for question
  processing, camera capture, TTS synthesis. Thread-safe communication via
  `pyqtSignal`.
- **No asyncio**: Anthropic/OpenAI sync clients work fine with threads; PyQt's
  event loop doesn't integrate easily with asyncio.
- **Input modes**: Push-to-talk (F2 hold) and voice-activated (F3 toggles).
  Default is voice activation. VAD uses webrtcvad.
- **TTS sentence batching**: Claude's response is split into sentences; a
  synthesis worker generates audio per chunk; playback starts on the first chunk
  for low perceived latency. Max 4000 chars per API call.
- **Local STT**: Moonshine Voice runs on-device (no API call). Model and
  language are configurable in `config.toml`.
- **Persistent memory**: SQLite at `~/.klaus/klaus.db` with tables for sessions,
  exchanges, and knowledge_profile. Knowledge summary is injected into Claude's
  system prompt.
- **Notes**: Optional Obsidian vault integration. Active only when
  `OBSIDIAN_VAULT_PATH` is set in `.env`.

## Development Conventions

See `.cursor/rules/` for authoritative style rules:
- `python-style.mdc` -- type hints, threading, dataclasses, pathlib, pytest
- `logging.mdc` -- module-level loggers, lazy `%s` formatting, no secrets in logs
- `klaus-architecture.mdc` -- module layout, tech stack
- `klaus-knowledge.mdc` -- design rationale and API choices (partially stale)

Other conventions:
- `.env` for API keys -- never committed
- Modules kept under ~200 lines where practical (some exceed this)
- Tests with pytest, mocking external APIs (`pytest>=8.0.0` is a dependency)

## Current Status and Known Gaps

- **No test suite**: pytest is listed in requirements.txt but no `tests/`
  directory exists.
- **knowledge_profile unused**: `memory.py` defines `update_knowledge()` but it
  is never called; the knowledge_profile table stays empty.
- **Stale cursor rules**: `klaus-knowledge.mdc` references `gpt-4o-mini-transcribe`
  for STT (now Moonshine), voice `coral` (now `cedar`), and model
  `claude-sonnet-4-20250514` (now `claude-sonnet-4-6`).
- **scipy unused**: Listed in requirements.txt but not imported anywhere.
- **faster-whisper unused**: Listed in requirements.txt but Moonshine Voice is
  used instead.

## Keeping This File Current

After completing any request that changes the Klaus codebase, update this file
to reflect the change. Specifically:

1. **Module map**: Add, remove, or update entries when modules are created,
   deleted, renamed, or significantly resized (line counts).
2. **Tech stack**: Update when dependencies are added, removed, or swapped.
3. **Architecture decisions**: Update when threading model, data flow, API
   choices, or storage patterns change.
4. **Current status / known gaps**: Mark items resolved when fixed; add new
   items when discovered.
5. **Last updated date**: Bump the date at the top of this file.

Do not rewrite sections that haven't changed. Keep edits surgical.
