# CLAUDE.md

Living reference for AI assistants working on the Klaus codebase.
Last updated: 2026-03-02 (app icon + dock name).

## Project Summary

Klaus is a voice-based research assistant for reading physical papers and books.
The user places a document under a camera, speaks a question (push-to-talk or
voice-activated), and Klaus sees the page via Claude's vision API, reasons about
the question, and responds aloud through text-to-speech. It runs as a PyQt6
desktop app on Windows and macOS.

## Tech Stack

- **Python 3.11+** with threads (not asyncio)
- **PyQt6** -- desktop GUI with dark theme
- **OpenCV** -- background camera thread
- **AVFoundation (pyobjc, macOS-only)** -- native camera display names
- **sounddevice + webrtcvad** -- audio capture, PTT and voice-activated recording
- **Moonshine Voice** -- local on-device STT (replaced OpenAI STT)
- **OpenAI gpt-4o-mini-tts** -- text-to-speech with sentence-level streaming
- **Anthropic Claude** (`claude-sonnet-4-6`) -- vision + tool use
- **Tavily** -- web search exposed as a Claude tool
- **SQLite** -- persistent memory at `~/.klaus/klaus.db`
- **pynput** -- global hotkeys (cross-platform, replaces `keyboard`)
- **Config** -- `~/.klaus/config.toml` (user settings + API keys) with `.env` fallback

## Module Map

### `klaus/` (core)

| Module | Lines | Purpose |
|--------|------:|---------|
| `config.py` | 527 | Config via TOML + .env, models, voice settings, dynamic system prompt with user background, query-router thresholds/feature flags, save/reload helpers, immediate runtime setters for camera/mic |
| `main.py` | 941 | Entry point; wires all components, hotkeys (conditional pynput + Qt), setup wizard gate, Qt signal bridge, `_safe_slot` decorator, live device-switch handlers with rollback, post-settings client reload, app icon + dock name setup (skipped on macOS 26 + Py 3.14), shifted-key variant mapping for macOS ISO keyboards; routes questions before full context capture |
| `audio.py` | 486 | PushToTalkRecorder, VoiceActivatedRecorder (with device selection, suspend/resume stream), AudioPlayer |
| `brain.py` | 440 | Claude vision + tool-use loop, route-aware context assembly, sentence-cap enforcement, conversation history, streaming, `reload_clients()` |
| `memory.py` | 254 | SQLite persistence (sessions, exchanges, knowledge_profile) |
| `tts.py` | 248 | OpenAI gpt-4o-mini-tts with persistent OutputStream, sentence-level batching, `reload_client()` |
| `camera.py` | 164 | OpenCV background thread, frame capture, auto-rotation, base64/thumbnail export, camera enumeration |
| `device_catalog.py` | 221 | Shared camera/mic enumeration and labeling (AVFoundation names on macOS, disambiguated mic labels, default markers) |
| `stt.py` | 103 | Moonshine Voice local transcription |
| `notes.py` | 100 | Obsidian vault note-taking (set_notes_file, save_note tools) |
| `search.py` | 50 | Tavily web search tool definition + execution |
| `query_router.py` | 458 | Hybrid local + LLM route classifier with timeout/fallback; maps question intent to context policy |

### `klaus/ui/`

| Module | Lines | Purpose |
|--------|------:|---------|
| `theme.py` | 586 | Palette tokens, dimensions, single `application_stylesheet()` QSS, `apply_dark_titlebar()`, `load_fonts()` |
| `chat_widget.py` | 260 | Scrollable chat feed with message cards, thumbnails, replay |
| `session_panel.py` | 190 | Session list sidebar with context menu |
| `main_window.py` | 204 | Top-level window layout, splitter, header, settings button, Qt key events for in-app hotkeys |
| `setup_wizard.py` | 904 | First-run 7-step setup wizard (API keys, camera, mic, model download, user background, Obsidian vault) with shared device labels and persisted mic selection |
| `settings_dialog.py` | 443 | Tabbed settings dialog (API keys, camera, mic, profile + Obsidian vault) with immediate camera/mic apply + persistence signals |
| `status_widget.py` | 120 | Status bar (Idle/Listening/Thinking/Speaking), mode toggle, stop |
| `camera_widget.py` | 71 | Live camera preview (~30 fps) |
| `icon.png` | -- | Application icon (owl logo); used for window, taskbar, and macOS dock |

## Key Architecture Decisions

- **Threading model**: PyQt6 main thread for UI; daemon threads for question
  processing, camera capture, TTS synthesis. Thread-safe communication via
  `pyqtSignal`.
- **No asyncio**: Anthropic/OpenAI sync clients work fine with threads; PyQt's
  event loop doesn't integrate easily with asyncio.
- **Input modes**: Push-to-talk (F2 hold) and voice-activated (F3 toggles).
  Default is voice activation. VAD uses webrtcvad. Both PTT and toggle keys
  are configurable in `config.toml` (`hotkey`, `toggle_key`). Two hotkey
  backends run in parallel: **Qt key events** on `MainWindow`
  (`keyPressEvent`/`keyReleaseEvent`) work when the window is focused with
  no OS permissions; **pynput** provides global hotkeys but requires macOS
  Accessibility permission and starts gracefully (logs a warning on failure).
  On macOS, F-keys trigger system actions (F3 = Mission Control) by default;
  users can press Fn+key, enable "Use standard function keys", or configure
  a different key.
- **Cross-platform**: Windows and macOS. Platform-specific code is guarded by
  `sys.platform` checks: `cv2.CAP_DSHOW` (Windows camera backend),
  `moonshine.dll` preload (Windows DLL conflict workaround), DWM dark title
  bar (Windows only, no-op elsewhere).
- **TTS sentence batching**: Claude's response is split into sentences; a
  synthesis worker generates audio per chunk; playback starts on the first chunk
  for low perceived latency. Max 4000 chars per API call. A single persistent
  `sd.OutputStream` is reused across all chunks in a session (avoids macOS
  CoreAudio crackling from rapid stream create/destroy). On macOS, uses
  `latency='high'`. The VAD mic stream is suspended (`suspend_stream`) before
  TTS playback and reopened (`resume_stream`) after, freeing the CoreAudio
  device during output. `suspend_stream`/`resume_stream` must be called from
  non-callback threads (never from the audio callback itself).
- **Local STT**: Moonshine Voice runs on-device (no API call). Model and
  language are configurable in `config.toml`.
- **Persistent memory**: SQLite at `~/.klaus/klaus.db` with tables for sessions,
  exchanges, and knowledge_profile. Knowledge summary is injected into Claude's
  system prompt.
- **Query routing policy**: `query_router.py` classifies each transcript before
  answer generation. Local semantic scoring handles most turns with negligible
  latency. Uncertain turns can invoke a short LLM router call with strict timeout
  (`router_timeout_ms`, default 350ms). Low-confidence/failed routing falls back
  to `standalone_definition`. Route policy controls whether image/history/memory/
  notes context is sent and applies per-turn sentence caps.
- **Definition behavior**: standalone definition turns are constrained to max
  two sentences and suppress page/history/memory/notes context; page-grounded
  definition turns keep image context and a short history window (2 turns).
- **Notes**: Optional Obsidian vault integration. `OBSIDIAN_VAULT_PATH` is stored
  in `config.toml` (with `.env` fallback). Configurable in the setup wizard
  ("About You" step) and settings dialog ("Profile" tab) via a native folder
  picker. Notes are disabled when the path is empty.
- **Single QSS theme**: All styling lives in `theme.py` via one
  `application_stylesheet()` function. Widgets use `setObjectName()` for
  targeted selectors (e.g. `#klaus-header`, `#session-list`). Only dynamic
  state (status bar color) uses inline `setStyleSheet`. Dark Windows title bar
  via DWM API (`apply_dark_titlebar()`). Dialogs (`QLineEdit`, `QMessageBox`,
  `QInputDialog`) are styled globally and get dark title bars.
- **Bundled Inter font**: `klaus/ui/fonts/` contains Inter .ttf files (Regular,
  Medium, SemiBold, Bold). `theme.load_fonts()` registers them with Qt at
  startup. Falls back to Segoe UI if missing.
- **First-run setup wizard**: On first launch (`setup_complete` is false in
  config.toml), a 7-step wizard runs before the main app: welcome, API key
  entry, camera selection, microphone test, voice model download, user
  background (optional), done. Camera/mic labels now come from the shared
  `device_catalog` module; mic changes rebind the live meter immediately; and
  the selected mic index is persisted (including system default = `-1`). The
  wizard writes config and calls `config.reload()` before handing off to the
  main event loop.
  `KlausApp._init_components()` defers all API-dependent object creation until
  after the wizard completes.
- **User background**: Optional free-text description stored as `user_background`
  in `config.toml`. `_build_system_prompt()` assembles the system prompt
  dynamically, appending the user's background to the intro paragraph when
  present. Editable in the setup wizard ("About You" step) and the settings
  dialog ("Profile" tab). `brain.py` accesses `config.SYSTEM_PROMPT` via module
  reference (not `from`-import) so it picks up changes after `config.reload()`.
- **API key storage**: Keys are stored in `~/.klaus/config.toml` under the
  `[api_keys]` section. Falls back to `.env` via `python-dotenv` for backward
  compatibility. Keys are validated in the wizard by format (prefix + length),
  not by live API calls.
- **Settings live reload**: Camera/mic selectors in `settings_dialog.py` now
  apply and persist immediately, without Save. The dialog emits device-change
  signals; `main.py` live-switches camera/VAD on each change; and failed switches
  auto-revert to the last working device (with UI rollback and persisted rollback).
  Save is still used for API keys/profile/vault and triggers `config.reload()`.
  `NotesManager` is recreated on vault path change, and `Brain.reload_clients()`
  / `TextToSpeech.reload_client()` hot-swap API clients after dialog close.
  Hotkeys, VAD params, TTS voice/speed, and STT model are not in the dialog and
  still require an app restart.
- **Camera auto-rotation**: `camera.py` detects portrait frames (h > w) and
  rotates 90 CW automatically. Configurable via `camera_rotation` in
  `config.toml` (`auto`, `none`, `90`, `180`, `270`).
- **Safe slots**: PyQt6 calls `abort()` when an unhandled Python exception
  escapes a slot invoked from C++ signal dispatch. All `KlausApp` slot handlers
  connected to UI signals use the `@_safe_slot` decorator (defined in
  `main.py`) which catches and logs exceptions so the app stays alive. Hardware
  enumeration calls (`list_camera_devices`, `list_input_devices`, `sd.InputStream`)
  in settings/setup flows and `VoiceActivatedRecorder` are wrapped with
  try/except for the same reason.
- **App icon**: `klaus/ui/icon.png` is set as the window icon via
  `QApplication.setWindowIcon()` (cross-platform). On macOS, pyobjc overrides
  the dock icon (`NSApplication.setApplicationIconImage_`) and the menu-bar /
  dock name (`NSBundle.mainBundle().infoDictionary()["CFBundleName"] = "Klaus"`)
  so the app shows "Klaus" instead of "Python". Both pyobjc calls use
  `Foundation` and `AppKit`, which are transitive dependencies of the existing
  `pyobjc-framework-AVFoundation` requirement.
- **Packaging**: `pyproject.toml` with `hatchling` build backend. Entry point:
  `klaus = "klaus.main:main"`. Homebrew formula in `homebrew/klaus.rb` for
  macOS distribution via a tap repo.

## Development Conventions

See `.cursor/rules/` for authoritative style rules:
- `python-style.mdc` -- type hints, threading, dataclasses, pathlib, pytest
- `logging.mdc` -- module-level loggers, lazy `%s` formatting, no secrets in logs
- `klaus-architecture.mdc` -- module layout, tech stack
- `klaus-knowledge.mdc` -- design rationale and API choices (partially stale)

Other conventions:
- API keys in `~/.klaus/config.toml` `[api_keys]` section (`.env` fallback supported)
- Dependencies in `pyproject.toml` (`requirements.txt` removed)
- Modules kept under ~200 lines where practical (some exceed this)
- Tests with pytest, mocking external APIs (`pytest>=8.0.0` in `[project.optional-dependencies]`)

## Current Status and Known Gaps

- **knowledge_profile unused**: `memory.py` defines `update_knowledge()` but it
  is never called; the knowledge_profile table stays empty.
- **Stale cursor rules**: `klaus-knowledge.mdc` references `gpt-4o-mini-transcribe`
  for STT (now Moonshine), voice `coral` (now `cedar`), and model
  `claude-sonnet-4-20250514` (now `claude-sonnet-4-6`).
- **Remaining test failures**: full suite still has two legacy failures:
  `tests/test_audio.py::TestPushToTalkRecorder::test_to_wav_bytes_produces_valid_wav`
  references removed `_to_wav_bytes`, and
  `tests/test_tts.py::TestSpeakWithMock::test_speak_calls_api_and_plays`
  expects `sd.play` while playback now uses a persistent `sd.OutputStream`.
- **Router cost/latency tuning**: ambiguous turns may incur an extra lightweight
  routing call; tune `router_*` thresholds/timeouts in `config.toml` if latency
  or fallback behavior needs adjustment.

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
