# CLAUDE.md

Living reference for AI assistants working on the Klaus codebase.
Last updated: 2026-08-24 (capsule voice dock, pill control language, QSS split
into theme_qss modules).

## Project Summary

Klaus is a voice-based research assistant for physical paper and PDFs. On macOS,
it captures physical pages from Apple's Desk View or reads the active PDF window.
It prefers selected PDF text when Accessibility exposes it and falls back to a
window image. The user asks through push-to-talk or voice activation, and Klaus
responds aloud through text-to-speech.

## Tech Stack

- **Python 3.11+** with threads (not asyncio)
- **PyQt6** -- desktop GUI with dark theme
- **OpenCV** -- background camera thread
- **AVFoundation (pyobjc, macOS-only)** -- native camera display names
- **Quartz + ApplicationServices (pyobjc, macOS-only)** -- reading-window
  capture and selected-text access
- **sounddevice + webrtcvad** -- audio capture, PTT and voice-activated recording
- **Moonshine Voice** -- local on-device STT (replaced OpenAI STT)
- **OpenAI gpt-realtime-2.1** -- default speech-to-speech engine over WebSocket
- **OpenAI gpt-4o-mini-tts** -- streamed text-to-speech for the legacy engine
- **Anthropic Claude** (`claude-sonnet-5`; `claude-haiku-4-5` for routing and
  standalone definitions) -- optional legacy vision + tool-use engine
- **Tavily** -- optional web search tool for Realtime or the legacy engine
- **SQLite** -- persistent memory at `~/.klaus/klaus.db`
- **pynput** -- global hotkeys (cross-platform, replaces `keyboard`)
- **Config** -- `~/.klaus/config.toml` (user settings + API keys) with `.env` fallback

## Module Map

### `klaus/` (core)

| Module | Lines | Purpose |
|--------|------:|---------|
| `config.py` | ~970 | Config via TOML + .env, models (incl. `definition_model`), reading source indices, voice/latency settings (`tts_streaming`, `vad_early_stt_timeout`, `vad_start_trigger_ms`, `barge_in_*`, `earcons_enabled`), dynamic system prompt, query-router thresholds/flags, save/reload helpers |
| `main.py` | ~1050 | Entry point; wires all components, hotkeys, setup wizard gate, Qt signal bridge, `_safe_slot`, live device-switch with rollback, per-turn cancel event, barge-in dispatch + seed priming, speculative-STT wiring, earcon triggers, live chat streaming signals |
| `audio.py` | ~640 | PushToTalkRecorder, VoiceActivatedRecorder (confirmed voice onset, suspend/resume stream, early maybe-end callback for speculative STT, gated barge-in mode with bleed calibration, `prime_with_seed`), AudioPlayer |
| `brain.py` | ~520 | Optional legacy Claude vision + tool-use loop, route-aware context + model selection, first-clause emission, `AskCancelled` cancellation, sentence caps, history (auto-trimmed), streaming, `reload_clients()` |
| `realtime.py` | ~440 | Persistent GPT Realtime WebSocket conversation, full-audio and reading-context turns, streamed PCM and transcript events, local tool calls, cancellation, and unplayed-audio truncation |
| `memory.py` | 254 | SQLite persistence (sessions, exchanges, knowledge_profile) |
| `tts.py` | ~330 | Shared PCM playback plus legacy OpenAI gpt-4o-mini-tts streaming, WAV fallback, earcon playback, and client reload |
| `earcons.py` | 55 | Numpy-synthesized state-cue tones; the active flow uses the accepted-question tone |
| `camera.py` | ~230 | Shared camera/macOS-window background capture, auto-rotation, selected-text access, base64/thumbnail export |
| `macos_reading_source.py` | ~270 | Desk View and active-window selection, CoreGraphics window capture, Accessibility selected-text access |
| `device_catalog.py` | ~330 | Reading source and camera/mic enumeration and labeling; macOS UI skips physical camera probes |
| `stt.py` | 103 | Moonshine Voice local transcription |
| `notes.py` | 100 | Obsidian vault note-taking (set_notes_file, save_note tools) |
| `search.py` | 50 | Tavily web search tool definition + execution |
| `query_router.py` | ~480 | Local Realtime route policy plus the optional legacy LLM fallback; maps question intent to context policy |
| `services/question_pipeline.py` | ~245 | One turn: transcribe (speculative-aware) -> route (concurrent with reading context) -> prefer selected text or capture image -> streamed answer -> persist; timing log and cancellation |
| `services/speculative_stt.py` | 100 | `SpeculativeTranscriber`: STT during the VAD silence window, validated by exact PCM gap at finalize |

### `klaus/ui/`

| Module | Lines | Purpose |
|--------|------:|---------|
| `theme.py` | ~140 | Palette tokens, dimensions, `apply_dark_titlebar()`, `load_fonts()`; QSS delegated to theme_qss |
| `theme_qss.py` | ~690 | Main-window QSS assembled from theme tokens |
| `theme_qss_dialogs.py` | ~180 | Dialog and setup-wizard QSS |
| `chat_widget.py` | 260 | Scrollable chat feed with message cards, thumbnails, replay |
| `session_panel.py` | 190 | Session list sidebar with visible action menus |
| `main_window.py` | 204 | Top-level window layout, splitter, header, settings button, Qt key events for in-app hotkeys |
| `setup_wizard.py` | ~920 | First-run 7-step setup wizard (API keys, reading source, mic, model download, user background, Obsidian vault) with live source preview |
| `settings_dialog.py` | ~525 | Tabbed settings dialog for voice, API keys, reading source, mic, profile, and Obsidian |
| `status_widget.py` | ~225 | Single-line capsule voice dock: state dot/word/hint, mode pill, Stop pill while busy |
| `camera_widget.py` | ~100 | Main Desk View/PDF selector and live preview with source-specific waiting messages |
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
- **Two macOS reading sources**: source index `-2` captures the Desk View window.
  Source index `-3` captures the frontmost non-Klaus window. The latter prefers
  exact Accessibility selected text for a grounded turn and uses a CoreGraphics
  window image when no selection exists. The macOS setup and settings pickers
  avoid opening physical cameras, which prevents contention with Desk View.
- **Confirmed voice onset**: voice activation requires `vad_start_trigger_ms`
  of consecutive WebRTC-positive frames above the RMS floor before it emits the
  listening state. The 300ms pre-buffer preserves the start of the question.
- **Default Realtime engine**: `voice_engine = "realtime"` sends each finalized
  WAV question plus selected text or a reading-window image to
  `gpt-realtime-2.1`. The app keeps one WebSocket conversation per reading
  session, streams 24 kHz PCM output into the shared TTS player, receives the
  answer transcript for chat and persistence, executes local search and notes
  tools, and truncates audio that a cancellation stopped before playback.
  `voice_engine = "legacy"` keeps the Claude plus OpenAI TTS path.
- **Realtime local routing**: the Realtime engine uses `local_route_decision()`
  without another model call. A low-confidence local result gets the safe
  contextual default. The legacy engine retains the hybrid Claude router.
- **Legacy TTS streaming**: Claude's response streams token-by-token; the first chunk
  is emitted at the first clause boundary past ~50 chars (`tts_first_clause_split`),
  then full sentences. Each chunk is synthesized via OpenAI's streaming API
  (`with_streaming_response`, `response_format="pcm"`, 24 kHz int16 mono) and
  PCM blocks are written to the persistent `sd.OutputStream` as they arrive,
  so audio starts before synthesis completes. `tts_streaming = false` restores
  the WAV-per-sentence fallback. Max 4000 chars per API call. On macOS the
  stream uses `latency='high'` (avoids CoreAudio crackling).
  `suspend_stream`/`resume_stream` must be called from non-callback threads.
- **Barge-in**: with `barge_in_enabled` (default), the VAD mic stream stays
  open during playback in a *gated* mode: frames must pass max-aggressiveness
  webrtcvad AND an RMS floor calibrated from the first ~300ms of playback
  bleed AND a sustained voiced run (`barge_in_min_voiced_ms`). On trigger the
  turn's cancel event is set, TTS stops (dispatched off the audio callback
  thread), and the buffered barge-in audio is primed into the recorder
  (`prime_with_seed`) so the user's first words aren't clipped. When disabled,
  the old suspend-mic-during-playback behavior applies (use on open-speaker
  setups with heavy bleed).
- **Cancellable turns**: each turn gets a fresh `threading.Event`; the Interrupt
  button, PTT keypress, and voice barge-in can set it. Realtime sends
  `response.cancel`, stops PCM playback, and truncates unheard server audio.
  Legacy `Brain.ask` checks the event while streaming. Klaus does not persist a
  cancelled turn, and the chat keeps its partial answer marked Interrupted.
- **Speculative STT**: the VAD fires `on_speech_maybe_end` at
  `vad_early_stt_timeout` (default 0.6s) of silence; Moonshine starts on that
  snapshot while the final `vad_silence_timeout` (default 1.0s) elapses. At
  finalize the speculative transcript is used only if the finalized audio is
  exactly `speculative_gap_bytes` longer than the snapshot (i.e. only silence
  was appended). See `services/speculative_stt.py`.
- **Earcons**: `earcons.py` creates tones with numpy, so the app needs no audio
  assets. The active flow plays only the accepted-question tone. Listening and
  interruption stay silent because a tone could leak into the next recording.
  Disable the tone with `earcons_enabled = false`.
- **Turn latency instrumentation**: `TurnTimings` in
  `services/question_pipeline.py` logs per-turn marks (transcript, route,
  first sentence, first audio, done) as one INFO line per turn.
- **Legacy route-aware model**: `standalone_definition` turns use `definition_model`
  (default `claude-haiku-4-5`); all other routes use `CLAUDE_MODEL`
  (`claude-sonnet-5`). The router LLM fallback runs concurrently with the
  eager page-image capture in the pipeline.
- **Local STT**: Moonshine Voice runs on-device (no API call). Model and
  language are configurable in `config.toml`.
- **Persistent memory**: SQLite at `~/.klaus/klaus.db` stores sessions,
  exchanges, and the dormant knowledge_profile table. GPT Realtime keeps live
  conversational context on its WebSocket session.
- **Query routing policy**: `query_router.py` classifies each transcript before
  answer generation. Realtime uses local semantic scoring and a safe contextual
  default for low-confidence results. Legacy mode can invoke a short Claude
  router call with a strict timeout. Route policy controls reading and notes
  context and can apply per-turn sentence caps.
- **Definition behavior**: standalone definition turns are constrained to max
  two sentences and suppress page/history/memory/notes context; page-grounded
  definition turns keep image context and a short history window (2 turns).
- **Notes**: Optional Obsidian vault integration. `OBSIDIAN_VAULT_PATH` is stored
  in `config.toml` (with `.env` fallback). Configurable in the setup wizard
  ("About You" step) and settings dialog ("Profile" tab) via a native folder
  picker. Notes are disabled when the path is empty.
- **Single QSS theme**: Tokens live in `theme.py`; the stylesheet is assembled
  in `theme_qss.py` (main window) plus `theme_qss_dialogs.py` (dialogs/wizard)
  and returned by `theme.application_stylesheet()`. Widgets use
  `setObjectName()` for targeted selectors (e.g. `#klaus-header`). Only dynamic
  state (dock state dot, `dockState` capsule property) uses inline styling or
  repolish. Controls share a pill language: each border-radius is tuned to half
  the control's height (Qt draws radius > height/2 badly, so there is no shared
  radius token). Dark Windows title bar via DWM API (`apply_dark_titlebar()`).
- **Capsule voice dock**: `StatusWidget` is one 52px pill (max 860px, matching
  the chat column). Busy states (`thinking`, `speaking`) set the capsule's
  `dockState` property to `hot` (pink border tint), swap the right-side
  controls for a Stop pill, and require `style().unpolish/polish` to retint.
  Interrupt styling uses LISTENING_COLOR pink, not error red.
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

- **knowledge_profile dormant**: `memory.py` keeps the knowledge_profile table
  and `update_knowledge()`/`get_knowledge_summary()`, but the pipeline no
  longer injects it (it was always empty). Wire or remove fully if revisited.
- **Stale cursor rules**: `klaus-knowledge.mdc` references `gpt-4o-mini-transcribe`
  for STT (now Moonshine), voice `coral` (now `cedar`), and model
  `claude-sonnet-4-20250514` (now `claude-sonnet-5`).
- **Barge-in on open speakers**: the RMS-calibrated gate may false-trigger on
  loud playback bleed; `barge_in_enabled = false` restores the suspend-mic
  behavior. No acoustic echo cancellation.
- **No voice cancel during thinking**: barge-in only arms once speaking starts;
  while thinking, cancel is Stop button or PTT keypress only.
- **Window capture API**: macOS window capture currently uses the deprecated
  `CGWindowListCreateImage`; migrate to ScreenCaptureKit if Apple removes it.
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
