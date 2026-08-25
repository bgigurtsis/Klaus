# CLAUDE.md

Living reference for AI assistants working on the Klaus codebase.
Last updated: 2026-08-25 (roadmap execution complete: wizard/config splits,
turn retries, async STT load, idle capture throttling). `DECISIONS.md` is the
authoritative log of choices and rejected approaches — read it before
proposing structural changes.

## Project Summary

Klaus is a voice-based research assistant for physical paper and PDFs. On
macOS it captures physical pages from Apple's Desk View, reads the active PDF
window (preferring Accessibility selected text over a window image), or pulls
the current page from a reMarkable tablet ("Paper Pure"). The user asks
through push-to-talk (default) or voice activation, and Klaus answers aloud
via a speech-to-speech model.

## Tech Stack

- **Python 3.11+** with threads (not asyncio; Gemini runs `asyncio.run` per
  turn inside a worker thread)
- **PyQt6** — desktop GUI, dark theme only
- **OpenAI Realtime** (`gpt-realtime-2.1`, `gpt-realtime-2.1-mini` — the
  default) over a persistent WebSocket
- **Gemini Live** (`gemini-3.1-flash-live-preview` via `google-genai`) —
  alternate engine with Google Search grounding
- **Moonshine Voice** — local on-device STT
- **sounddevice + webrtcvad** — audio capture, PTT and voice-activated modes
- **OpenCV** — background camera thread
- **Quartz + ApplicationServices (pyobjc)** — window capture and selected text
- **SQLite** — persistent memory at `~/.klaus/klaus.db`
- **macOS Keychain** (`keyring` via `secrets_store.py`) — API key storage,
  with env-var/`.env` fallback
- **pynput** — global hotkeys (skipped entirely on macOS ≥ 26 to avoid a
  segfault; Qt key events cover the focused-window case)
- **Config** — `~/.klaus/config.toml`

There is no Anthropic dependency, no Tavily search, and no separate TTS API:
both engines stream 24 kHz PCM speech directly.

## Module Map

### `klaus/` (core)

| Module | Lines | Purpose |
|--------|------:|---------|
| `main.py` | ~700 | Entry point + `KlausApp`: component wiring, Qt signal bridge, `_safe_slot` delegates, live device switch, settings reload |
| `hotkeys.py` | ~250 | pynput import gating and `HotkeyListener` (global PTT/toggle keys) |
| `config.py` | ~680 | Config interpretation: `RuntimeSettings` driven by `_RUNTIME_SETTING_SPECS` (exports generate from the spec table; consistency test in `test_config.py`), dynamic system prompt, thin `save_*` validators |
| `config_store.py` | ~180 | Config persistence: data-dir paths, default template, TOML parsing, raw read/write, `set_top_level_value` |
| `audio.py` | ~760 | `PushToTalkRecorder`, `VoiceActivatedRecorder` (confirmed onset, speculative maybe-end, gated barge-in with bleed calibration and echo rejection, `prime_with_seed`) |
| `realtime.py` | ~700 | `RealtimeBrain`: persistent OpenAI Realtime WebSocket, audio+context turns, streamed PCM/transcripts, cancel + unplayed-audio truncation, `warm_up()`, single retry of connection drops with zero output; `build_live_brain()` picks the engine by provider |
| `gemini_live.py` | ~460 | `GeminiLiveBrain`: per-turn Gemini Live session (`asyncio.run` in a thread), local `_history` resent each turn, Google Search tool, same zero-output single-retry |
| `audio_output.py` | ~195 | Shared PCM playback over one persistent output stream; cues are skipped while a response streams; drain-deadline estimate + `wait_for_drain()` so teardown outlasts the speaker tail; `stop()` closes the stream for immediate silence |
| `stt.py` | ~210 | Moonshine local transcription with download retry/backoff; `AsyncSpeechToText` loads the model on a background thread (`transcribe` blocks until ready) |
| `memory.py` | ~270 | SQLite sessions/exchanges persistence |
| `camera.py` | ~180 | Shared capture loop (5 fps window / 1 fps tablet), auto-rotation, base64/thumbnail export, `capture_text_context` |
| `macos_reading_source.py` | ~300 | Desk View / active-window capture (`CGWindowListCreateImage`), Accessibility selected text |
| `remarkable_reading_source.py` | ~370 | reMarkable "Paper Pure" page capture over HTTPS |
| `remarkable_pairing_server.py` | ~165 | Local pairing endpoint for the tablet |
| `device_catalog.py` | ~145 | Reading-source and camera/mic enumeration (no physical camera probes on macOS) |
| `query_router.py` | ~220 | Purely local route scoring (no LLM call); hardcoded 0.55 confidence floor, safe contextual default |
| `notes.py` | ~280 | Obsidian vault note tools |
| `secrets_store.py` | ~100 | Keychain get/set/delete for API keys |
| `permissions.py` | ~40 | Maps capture errors to actionable guidance (currently Screen Recording only) |
| `earcons.py` | ~45 | Numpy-synthesized tones; only the accepted-question tone plays |
| `skill_loader.py` | ~20 | Loads bundled skill text (`klaus/skills/`) into the system prompt |
| `reading_source.py` | ~25 | Reading-source protocol |

### `klaus/services/`

| Module | Lines | Purpose |
|--------|------:|---------|
| `question_pipeline.py` | ~350 | One turn: transcribe (speculative-aware) → route ∥ context capture → image or selected text → streamed answer → persist; `TurnTimings` + rolling p50/p95 aggregator |
| `turn_coordinator.py` | ~290 | VAD/PTT/barge-in/replay/stop glue and guard stats; reads hot-swappable deps through getters |
| `session_service.py` | ~190 | Session CRUD, activation flow, notes rebinding behind a `SessionView` of UI callables |
| `turn_state.py` | ~150 | Locked owner of turn flags, per-turn cancel event, barge-in seed, queued PTT wav |
| `device_switch.py` | ~130 | Camera/mic live-switch with rollback (refused mid-turn except forced pairing refresh) |
| `speculative_stt.py` | ~90 | STT during the VAD silence window, validated by exact PCM gap at finalize |

### `klaus/ui/`

| Module | Lines | Purpose |
|--------|------:|---------|
| `setup_wizard.py` | ~175 | Wizard shell: navigation and `_finish_setup`; pages come from the two step mixins |
| `wizard_content_steps.py` | ~470 | Wizard pages: welcome, API keys, about-you, done (mixin) |
| `wizard_device_steps.py` | ~300 | Wizard pages: reading source, mic, model download with determinate progress + cancel (mixin) |
| `wizard_widgets.py` | ~145 | `StepIndicator`, `ModelDownloadThread` (progress signal, cancel), `CameraPreview` |
| `theme_qss.py` | ~670 | Main-window QSS from theme tokens |
| `settings_dialog.py` | ~695 | Tabbed settings: model/effort/voice/barge-in, API keys, reading source, reMarkable pairing, mic (with failure label), profile, vault |
| `chat_widget.py` | ~640 | Chat feed: streaming cards, thinking placeholder, error cards with Retry, thumbnails, copy/replay, centered 860px column |
| `main_window.py` | ~390 | Window layout, sidebar collapse, Qt key events for in-app hotkeys, Cmd+=/-/0 text zoom |
| `session_panel.py` | ~230 | Session list sidebar |
| `camera_widget.py` | ~210 | Reading-source selector and live preview |
| `status_widget.py` | ~210 | Capsule voice dock: state dot/word/hint, mode pill, Stop pill while busy |
| `theme_qss_dialogs.py` | ~190 | Dialog and wizard QSS |
| `desk_view_setup.py` | ~170 | Desk View setup helper dialog |
| `theme.py` | ~165 | Palette tokens, dimensions, font loading, QSS assembly + font-scale post-processing |
| `remarkable_pairing.py` | ~105 | Tablet pairing dialog |
| `image_viewer.py` | ~105 | Click-to-zoom screenshot viewer |
| `permission_banner.py` | ~85 | Amber banner with a Privacy Settings deep link |

## Key Architecture Decisions

- **Threading model**: PyQt6 main thread for UI; daemon threads for the turn
  worker, capture loop, playback, speculative STT. Cross-thread UI updates go
  through `pyqtSignal` (`Signals` in `main.py`); `@_safe_slot` keeps slot
  exceptions from aborting the process.
- **Two live engines behind one interface**: `build_live_brain()`
  (`realtime.py`) returns `RealtimeBrain` or `GeminiLiveBrain` based on the
  provider of `live_model`. Default model is `gpt-realtime-2.1-mini`;
  `reasoning_effort` defaults to `high`. Settings hot-swap the brain when the
  provider changes.
- **Input modes**: push-to-talk is the default for new setups (hold `§`);
  voice activation is a toggle. Both keys configurable in `config.toml`
  (`hotkey`, `toggle_key`) — there is no in-app hotkey UI. Two hotkey
  backends: Qt key events (focused window, no permissions) and pynput
  (global, needs Accessibility, skipped on macOS ≥ 26).
- **Reading sources**: Desk View window, frontmost non-Klaus window
  (selected text preferred, window image fallback), reMarkable tablet, or
  none (audio-only — the default for new setups).
- **Voice turn**: VAD final-silence (1.0 s) confirms end of speech; a
  speculative Moonshine pass starts at 0.6 s and is used when only silence
  followed the snapshot. The pipeline routes locally, captures context, sends
  audio + context to the live engine, streams PCM into `AudioOutput`, and
  persists the exchange. `TurnTimings` logs one INFO line per turn.
- **Barge-in**: `barge_in_enabled` defaults to **false**. When on, the mic
  stays open during playback in a gated mode (max-aggressiveness VAD + RMS
  floor calibrated from playback bleed + sustained voiced run + waveform
  echo rejection); trigger cancels the turn and primes the recorder with the
  buffered speech. Teardown waits for the output stream's drain estimate
  before disarming the gate, so the audible tail of an answer cannot start
  a new turn. No acoustic echo cancellation.
- **Cancellable turns**: fresh `threading.Event` per turn; Stop pill, PTT
  keypress, and barge-in set it. Realtime sends `response.cancel` and
  truncates unheard server audio at the played position; Gemini closes its
  session. Cancelled turns are not persisted; the chat keeps the partial
  answer marked Interrupted.
- **API keys**: Keychain via `secrets_store.py` (`gemini`, `openai` slugs),
  env-var/`.env` fallback. Validated by format only (prefix + length).
- **Settings live reload**: camera/mic apply immediately with rollback on
  failure; model/effort/voice/keys/profile/vault apply on dialog accept and
  re-wire the brain in place. VAD params and hotkeys are baked at recorder
  construction — config-only, restart required.
- **Text zoom**: Cmd+= / Cmd+- / Cmd+0 scale QSS font sizes by regex
  post-processing (`ui_font_scale`); fixed-pixel chrome and inline dialog
  styles do not scale (known limitation).
- **Packaging**: `pyproject.toml` + hatchling; `scripts/install-macos-app.sh`
  builds Klaus.app signed with the stable self-signed "Klaus Code Signing"
  identity (ad-hoc signatures break TCC grants and trip Jamf — see
  DECISIONS.md). `launcher.c` forks so the bundle stays the TCC responsible
  process.

## Development Conventions

- Type hints, module-level loggers with lazy `%s` formatting, no secrets in
  logs, pathlib, pytest with mocked external APIs.
- 800-line ceiling per module; at 600 propose a split (see DECISIONS.md for
  the theme.py precedent).
- Every real decision gets a DECISIONS.md entry (append-only).
- Dependencies live in `pyproject.toml`.

## Current Status and Known Gaps

- **No module exceeds the 800-line ceiling**; seven sit in the 600–760 flag
  band (see the closing ceiling audit in DECISIONS.md for proposed splits).
- **Window capture API**: still the deprecated `CGWindowListCreateImage`
  (`macos_reading_source.py`); migrate to ScreenCaptureKit if Apple removes it.
- **Barge-in on open speakers**: RMS gate may false-trigger on loud bleed;
  it ships disabled by default. No AEC.
- **No voice cancel during thinking**: barge-in arms only once speaking
  starts.
- **Gemini `_history` is unbounded** and resent in full every turn (D3 —
  owner decision pending).
- **Owner decisions D1–D10** (reasoning-effort default, VAD timeouts, image
  downscale, Markdown chat, light mode, …) are catalogued in the review plan
  and await Billy; do not implement them unprompted.

## Keeping This File Current

After completing any request that changes the Klaus codebase, update this
file: module map (additions/removals/major resizes), tech stack, architecture
decisions, known gaps, and the date at the top. Keep edits surgical. Record
decisions and rejected approaches in DECISIONS.md, not here.
