"""Klaus -- Voice Research Assistant. Entry point."""

import functools
import logging
import os
import platform
import sys
import threading

from pynput.keyboard import Key, KeyCode, Listener as KeyboardListener

import klaus.config as config


def _resolve_pynput_key(key_name: str) -> Key | KeyCode:
    """Convert a config key name (e.g. ``'F2'``) to a pynput key object."""
    try:
        return getattr(Key, key_name.lower())
    except AttributeError:
        if len(key_name) == 1:
            return KeyCode.from_char(key_name)
        raise ValueError(f"Unknown hotkey: {key_name!r}")

from klaus.stt import SpeechToText  # noqa: E402  (before PyQt6: moonshine.dll must load first)

from PyQt6.QtWidgets import QApplication, QMessageBox
from PyQt6.QtCore import QObject, pyqtSignal

logger = logging.getLogger(__name__)
_SHIFT_KEYS = {Key.shift, Key.shift_l, Key.shift_r}


def _should_disable_global_hotkeys() -> bool:
    """Return True when starting pynput global hotkeys is known to crash.

    macOS 26 + Python 3.14 has a crash path in pynput/Carbon keyboard APIs
    (HIToolbox dispatch queue assertion). Keep the app alive by disabling
    global hotkeys and relying on in-app Qt hotkeys.
    """
    if sys.platform != "darwin":
        return False
    if os.environ.get("KLAUS_FORCE_GLOBAL_HOTKEYS") == "1":
        return False

    mac_version = platform.mac_ver()[0]
    try:
        mac_major = int(mac_version.split(".", 1)[0])
    except (TypeError, ValueError):
        return False

    return mac_major >= 26 and sys.version_info >= (3, 14)


def _mark_key_pressed(pressed: set[object], key: object | None) -> bool:
    """Track key presses and suppress repeated press events for held keys."""
    if key is None:
        return False
    if key in pressed:
        return False
    pressed.add(key)
    return True


def _mark_key_released(pressed: set[object], key: object | None) -> None:
    if key is None:
        return
    pressed.discard(key)


def _is_shift_active(pressed: set[object]) -> bool:
    return any(key in pressed for key in _SHIFT_KEYS)


def _hotkey_action_for_press(
    *,
    platform_name: str,
    key: Key | KeyCode | None,
    ptt_key: Key | KeyCode,
    toggle_key: Key | KeyCode,
    shift_active: bool,
) -> str | None:
    """Classify a key press as ``ptt_down``, ``toggle``, or ``None``."""
    if key is None:
        return None
    if key != ptt_key and key != toggle_key:
        return None

    if platform_name == "darwin" and ptt_key == toggle_key and key == ptt_key:
        return "toggle" if shift_active else "ptt_down"

    if key == toggle_key:
        return "toggle"
    if key == ptt_key:
        return "ptt_down"
    return None


def _safe_slot(func):
    """Prevent unhandled exceptions from reaching PyQt6's C++ layer.

    PyQt6 calls abort() when a Python exception escapes a slot invoked from
    C++ signal dispatch.  This decorator catches and logs the exception so the
    app stays alive.
    """
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception:
            logger.error(
                "Unhandled exception in slot %s", func.__name__, exc_info=True,
            )
    return wrapper


from klaus.camera import Camera
from klaus.audio import PushToTalkRecorder, VoiceActivatedRecorder
from klaus.tts import TextToSpeech
from klaus.brain import Brain
from klaus.memory import Memory
from klaus.notes import NotesManager
from klaus.services import (
    DeviceSwitchService,
    PipelineContext,
    PipelineHooks,
    QuestionPipeline,
)
from klaus.ui.main_window import MainWindow


def _new_guard_stats() -> dict[str, int]:
    """Create a fresh per-session STT guard stats dict."""
    return {
        "vad_discarded": 0,
        "quality_gate_discarded": 0,
    }


def _configured_mic_device() -> int | None:
    """Return configured mic device index, or None for system default."""
    if config.MIC_DEVICE_INDEX < 0:
        return None
    return config.MIC_DEVICE_INDEX


class Signals(QObject):
    """Thread-safe signals to update the UI from background threads."""

    state_changed = pyqtSignal(str)
    mode_changed = pyqtSignal(str)
    transcription_ready = pyqtSignal(str, float, bytes)  # text, timestamp, thumbnail_bytes
    response_ready = pyqtSignal(str, float, str)  # text, timestamp, exchange_id
    error = pyqtSignal(str)
    exchange_count_updated = pyqtSignal(int)
    sessions_changed = pyqtSignal()
    status_message = pyqtSignal(str)


class KlausApp:
    """Wires all components together into the core interaction loop."""

    def __init__(self):
        self._signals = Signals()
        self._runtime_settings = config.get_runtime_settings()
        self._current_session_id: str | None = None
        self._processing = False
        self._speaking = False
        self._input_mode: str = self._runtime_settings.input_mode
        self._guard_stats = _new_guard_stats()
        self._guard_stats_lock = threading.Lock()
        self._hotkey_listener: KeyboardListener | None = None
        self._ptt_key_name = self._runtime_settings.push_to_talk_key
        self._toggle_key_name = self._runtime_settings.toggle_key
        self._ptt_pynput_key = _resolve_pynput_key(self._ptt_key_name)
        self._toggle_pynput_key = _resolve_pynput_key(self._toggle_key_name)
        self._active_camera_index: int = config.CAMERA_DEVICE_INDEX
        self._active_mic_device: int | None = _configured_mic_device()

    def _build_vad_recorder(self, device: int | None) -> VoiceActivatedRecorder:
        settings = config.get_runtime_settings()
        return VoiceActivatedRecorder(
            on_speech_start=self._on_vad_speech_start,
            on_speech_end=self._on_vad_speech_end,
            on_speech_discard=self._on_vad_discard,
            sensitivity=settings.vad_sensitivity,
            silence_timeout=settings.vad_silence_timeout,
            min_duration=settings.vad_min_duration,
            min_voiced_ratio=settings.vad_min_voiced_ratio,
            min_voiced_frames=settings.vad_min_voiced_frames,
            min_rms_dbfs=settings.vad_min_rms_dbfs,
            min_voiced_run_frames=settings.vad_min_voiced_run_frames,
            device=device,
        )

    def _init_components(self) -> None:
        """Create all API-dependent components.

        Called after the setup wizard has finished (if needed) so that API keys
        and device selections are available.
        """
        self._runtime_settings = config.get_runtime_settings()
        settings = self._runtime_settings
        self._camera = Camera(
            settings.camera_device_index,
            frame_width=settings.camera_frame_width,
            frame_height=settings.camera_frame_height,
            rotation=settings.camera_rotation,
        )
        self._active_camera_index = settings.camera_device_index
        self._active_mic_device = _configured_mic_device()
        self._ptt_recorder = PushToTalkRecorder()
        self._vad_recorder = self._build_vad_recorder(self._active_mic_device)
        self._stt = SpeechToText(settings=settings)
        self._tts = TextToSpeech(settings=settings)
        self._notes = NotesManager(base_path=settings.obsidian_vault_path)
        self._brain = Brain(notes=self._notes)
        self._memory = Memory()
        self._rebuild_question_pipeline()
        self._ensure_device_switch_service()

    def _rebuild_question_pipeline(self) -> None:
        required = ("_stt", "_camera", "_brain", "_memory", "_notes", "_tts")
        if not all(hasattr(self, attr) for attr in required):
            return
        self._question_pipeline = QuestionPipeline(
            stt=self._stt,
            camera=self._camera,
            brain=self._brain,
            memory=self._memory,
            notes=self._notes,
            tts=self._tts,
        )

    def _ensure_device_switch_service(self) -> None:
        if hasattr(self, "_device_switch_service"):
            return
        self._device_switch_service = DeviceSwitchService(
            camera_factory=Camera,
            vad_builder=self._build_vad_recorder,
            persist_camera_index=lambda index: config.set_camera_index(index, persist=True),
            persist_mic_index=lambda device: config.set_mic_index(
                -1 if device is None else device,
                persist=True,
            ),
            show_error=self._show_device_switch_error,
        )

    def run(self) -> None:
        logger.info("Klaus starting")
        app = QApplication(sys.argv)
        app.setApplicationName("Klaus")

        from klaus.ui import theme
        theme.load_fonts()

        if not config.is_setup_complete():
            from klaus.ui.setup_wizard import SetupWizard
            wizard = SetupWizard()
            theme.apply_dark_titlebar(wizard)
            wizard.show()
            app.exec()
            if not config.is_setup_complete():
                logger.info("Setup wizard closed without completing, exiting")
                sys.exit(0)
            config.reload()
            self._runtime_settings = config.get_runtime_settings()
            self._input_mode = self._runtime_settings.input_mode
            self._ptt_key_name = self._runtime_settings.push_to_talk_key
            self._toggle_key_name = self._runtime_settings.toggle_key
            self._ptt_pynput_key = _resolve_pynput_key(self._ptt_key_name)
            self._toggle_pynput_key = _resolve_pynput_key(self._toggle_key_name)

        self._init_components()

        self._window = MainWindow()
        self._connect_signals()

        try:
            self._camera.start()
            self._active_camera_index = self._camera.device_index
        except RuntimeError as e:
            logger.warning("Camera unavailable: %s", e)
            self._active_camera_index = -1

        self._window.camera_widget.set_camera(self._camera)
        self._window.set_hotkeys(self._ptt_key_name, self._toggle_key_name)

        self._load_sessions()

        self._start_hotkey_listener()
        self._setup_input_mode()
        self._signals.mode_changed.emit(self._input_mode)

        self._window.show()
        self._window.chat_widget.scroll_to_bottom()
        logger.info("UI ready")
        exit_code = app.exec()

        self._shutdown()
        sys.exit(exit_code)

    def _connect_signals(self) -> None:
        sig = self._signals

        sig.state_changed.connect(self._on_state_changed)
        sig.transcription_ready.connect(self._on_transcription_ready)
        sig.response_ready.connect(self._on_response_ready)
        sig.error.connect(self._on_error)
        sig.exchange_count_updated.connect(self._window.status_widget.set_exchange_count)
        sig.status_message.connect(self._window.chat_widget.add_status_message)

        sig.mode_changed.connect(self._window.status_widget.set_mode)
        sig.sessions_changed.connect(self._refresh_session_list)

        self._window.session_changed.connect(self._on_session_changed)
        self._window.new_session_requested.connect(self._on_new_session)
        self._window.rename_requested.connect(self._on_session_renamed)
        self._window.delete_requested.connect(self._on_session_deleted)
        self._window.replay_requested.connect(self._on_replay)
        self._window.mode_toggle_requested.connect(self._toggle_input_mode)
        self._window.stop_requested.connect(self._on_stop_requested)
        self._window.settings_requested.connect(self._on_settings_requested)

        self._window.ptt_key_pressed.connect(self._on_key_down)
        self._window.ptt_key_released.connect(self._on_key_up)
        self._window.toggle_key_pressed.connect(self._toggle_input_mode)

    # -- State handling --

    @_safe_slot
    def _on_state_changed(self, state: str) -> None:
        """Route state changes to the status widget."""
        self._window.status_widget.set_state(state)

    def _session_tag(self) -> str:
        if self._current_session_id:
            return self._current_session_id[:8]
        return "none"

    def _reset_guard_stats(self) -> None:
        """Reset guard stats whenever the active session changes."""
        with self._guard_stats_lock:
            self._guard_stats = _new_guard_stats()
            snapshot = dict(self._guard_stats)
        logger.info(
            "STT guard stats reset (session=%s): vad_discarded=%d | quality_gate_discarded=%d",
            self._session_tag(),
            snapshot["vad_discarded"],
            snapshot["quality_gate_discarded"],
        )

    def _increment_guard_stat(self, key: str, event: str, reason: str = "-") -> None:
        """Increment one guard stat and log a structured snapshot."""
        with self._guard_stats_lock:
            if key not in self._guard_stats:
                return
            self._guard_stats[key] += 1
            snapshot = dict(self._guard_stats)
        logger.info(
            "STT guard event=%s reason=%s session=%s vad_discarded=%d quality_gate_discarded=%d",
            event,
            reason,
            self._session_tag(),
            snapshot["vad_discarded"],
            snapshot["quality_gate_discarded"],
        )

    # -- Input mode --

    def _start_hotkey_listener(self) -> None:
        """Start the pynput global hotkey listener.

        On macOS this requires Accessibility permission, which is hard to grant
        when running as a Python script.  If the listener fails to start we log
        a warning but carry on -- the Qt in-app key events (keyPressEvent on
        MainWindow) still work when the window is focused.
        """
        if _should_disable_global_hotkeys():
            logger.warning(
                "Global hotkeys disabled on macOS %s with Python %s due a known "
                "pynput crash. In-app hotkeys still work when the Klaus window "
                "is focused. Use Python 3.13 for stable global hotkeys, or set "
                "KLAUS_FORCE_GLOBAL_HOTKEYS=1 to force-enable (may crash).",
                platform.mac_ver()[0] or "unknown",
                platform.python_version(),
            )
            if sys.platform == "darwin":
                logger.info(
                    "macOS: F-keys trigger system actions by default "
                    "(F3 = Mission Control). Use Fn+key, enable 'Use F1, F2, etc. "
                    "keys as standard function keys' in System Settings > Keyboard, "
                    "or set a different key in ~/.klaus/config.toml (toggle_key)."
                )
            return

        ptt_key = self._ptt_pynput_key
        toggle_key = self._toggle_pynput_key
        pressed_keys: set[Key | KeyCode] = set()
        ptt_key_armed = False

        def on_press(key: Key | KeyCode | None) -> None:
            nonlocal ptt_key_armed
            if not _mark_key_pressed(pressed_keys, key):
                return

            action = _hotkey_action_for_press(
                platform_name=sys.platform,
                key=key,
                ptt_key=ptt_key,
                toggle_key=toggle_key,
                shift_active=_is_shift_active(pressed_keys),
            )
            if action == "toggle":
                self._toggle_input_mode()
                return
            if action == "ptt_down" and not ptt_key_armed:
                ptt_key_armed = True
                self._on_key_down()

        def on_release(key: Key | KeyCode | None) -> None:
            nonlocal ptt_key_armed
            _mark_key_released(pressed_keys, key)
            if key == ptt_key and ptt_key_armed:
                ptt_key_armed = False
                self._on_key_up()

        try:
            self._hotkey_listener = KeyboardListener(
                on_press=on_press, on_release=on_release,
            )
            self._hotkey_listener.daemon = True
            self._hotkey_listener.start()
            logger.info(
                "Global hotkey listener started (ptt=%s, toggle=%s)",
                self._ptt_key_name,
                self._toggle_key_name,
            )
        except Exception as exc:
            logger.warning(
                "Global hotkey listener failed to start: %s. "
                "In-app hotkeys still work when the Klaus window is focused.",
                exc,
            )

        if sys.platform == "darwin":
            logger.info(
                "macOS: F-keys trigger system actions by default "
                "(F3 = Mission Control). Use Fn+key, enable 'Use F1, F2, etc. "
                "keys as standard function keys' in System Settings > Keyboard, "
                "or set a different key in ~/.klaus/config.toml (toggle_key)."
            )

    def _setup_input_mode(self) -> None:
        """Activate the current input mode and deactivate the other."""
        if self._input_mode == "push_to_talk":
            if self._vad_recorder.is_running:
                self._vad_recorder.stop()
            logger.info("Input mode: push-to-talk (hotkey: %s)", self._ptt_key_name)
        else:
            self._vad_recorder.start()
            logger.info("Input mode: voice activation")

    def _cancel_active_capture_for_mode_switch(self) -> None:
        """Abort any in-progress capture before switching input modes."""
        if self._input_mode == "voice_activation":
            if self._vad_recorder.is_running:
                self._vad_recorder.stop()
                logger.info("Cancelled active voice-activation capture")
        elif self._ptt_recorder.is_recording:
            self._ptt_recorder.stop_recording()
            logger.info("Cancelled active push-to-talk capture")

    @_safe_slot
    def _toggle_input_mode(self) -> None:
        """Switch between push-to-talk and voice activation."""
        if self._processing:
            return

        self._cancel_active_capture_for_mode_switch()

        if self._input_mode == "push_to_talk":
            self._input_mode = "voice_activation"
        else:
            self._input_mode = "push_to_talk"
        self._setup_input_mode()
        self._signals.mode_changed.emit(self._input_mode)
        self._signals.state_changed.emit("idle")
        logger.info("Toggled input mode to %s", self._input_mode)

    # -- VAD callbacks --

    def _on_vad_speech_start(self) -> None:
        """Called from VAD thread when speech begins."""
        if self._input_mode != "voice_activation":
            return
        if self._speaking:
            self._tts.stop()
        if self._processing and not self._speaking:
            return
        self._signals.state_changed.emit("listening")

    def _on_vad_speech_end(self, wav_bytes: bytes) -> None:
        """Called from VAD thread when speech ends with silence timeout."""
        if self._input_mode != "voice_activation":
            return
        if not wav_bytes:
            self._signals.state_changed.emit("idle")
            return
        if self._processing and not self._speaking:
            return
        self._processing = True
        self._vad_recorder.pause()
        thread = threading.Thread(
            target=self._process_question, args=(wav_bytes,), daemon=True,
        )
        thread.start()

    def _on_vad_discard(self, reason: str) -> None:
        """Track why a VAD candidate was dropped before STT."""
        if reason.startswith("quality_"):
            self._increment_guard_stat(
                key="quality_gate_discarded",
                event="vad_discard",
                reason=reason,
            )
            return
        self._increment_guard_stat(
            key="vad_discarded",
            event="vad_discard",
            reason=reason,
        )

    # -- Session management --

    def _load_sessions(self) -> None:
        sessions = self._memory.list_sessions()
        if not sessions:
            session = self._memory.create_session("Untitled Session")
            sessions = [session]

        session_dicts = self._build_session_dicts(sessions)
        self._current_session_id = sessions[0].id
        self._reset_guard_stats()
        self._window.set_sessions(session_dicts, self._current_session_id)

        logger.info(
            "Loaded %d session(s), active: '%s'",
            len(sessions), sessions[0].title,
        )

        self._load_session_history(self._current_session_id)
        self._notes.current_file = self._memory.get_session_notes_file(
            self._current_session_id
        )
        self._update_exchange_count()

    def _build_session_dicts(self, sessions) -> list[dict]:
        """Build enriched session dicts with exchange counts for the UI."""
        result = []
        for s in sessions:
            count = self._memory.count_exchanges(s.id)
            result.append({
                "id": s.id,
                "title": s.title,
                "updated_at": s.updated_at,
                "exchange_count": count,
            })
        return result

    def _update_exchange_count(self) -> None:
        """Emit the per-session exchange count."""
        if self._current_session_id:
            count = self._memory.count_exchanges(self._current_session_id)
        else:
            count = 0
        self._signals.exchange_count_updated.emit(count)

    @_safe_slot
    def _refresh_session_list(self) -> None:
        """Reload and repopulate the session panel."""
        sessions = self._memory.list_sessions()
        session_dicts = self._build_session_dicts(sessions)
        self._window.set_sessions(session_dicts, self._current_session_id)

    def _load_session_history(self, session_id: str) -> None:
        self._window.chat_widget.clear()
        exchanges = self._memory.get_exchanges(session_id)
        for ex in exchanges:
            self._window.chat_widget.add_message(
                role="user",
                text=ex.user_text,
                timestamp=ex.created_at,
                exchange_id=ex.id,
            )
            self._window.chat_widget.add_message(
                role="assistant",
                text=ex.assistant_text,
                timestamp=ex.created_at,
                exchange_id=ex.id,
            )

    @_safe_slot
    def _on_session_changed(self, session_id: str) -> None:
        logger.info("Switched to session %s", session_id[:8])
        self._current_session_id = session_id
        self._reset_guard_stats()
        self._brain.clear_history()
        self._notes.current_file = self._memory.get_session_notes_file(session_id)
        self._load_session_history(session_id)
        self._window.chat_widget.scroll_to_bottom()
        self._update_exchange_count()

        sessions = self._memory.list_sessions()
        for s in sessions:
            if s.id == session_id:
                self._window.set_current_session_title(s.title)
                break

    @_safe_slot
    def _on_new_session(self, title: str) -> None:
        session = self._memory.create_session(title)
        self._current_session_id = session.id
        self._reset_guard_stats()
        self._brain.clear_history()
        self._notes.current_file = None

        self._refresh_session_list()
        self._window.chat_widget.clear()
        self._window.set_current_session_title(title)
        self._update_exchange_count()

    @_safe_slot
    def _on_session_renamed(self, session_id: str, new_title: str) -> None:
        """Handle session rename from the UI."""
        logger.info("Renaming session %s to '%s'", session_id[:8], new_title)
        self._memory.update_session_title(session_id, new_title)
        self._refresh_session_list()
        if session_id == self._current_session_id:
            self._window.set_current_session_title(new_title)

    @_safe_slot
    def _on_session_deleted(self, session_id: str) -> None:
        """Handle session delete from the UI."""
        logger.info("Deleting session %s", session_id[:8])
        self._memory.delete_session(session_id)

        sessions = self._memory.list_sessions()
        if not sessions:
            session = self._memory.create_session("Untitled Session")
            sessions = [session]

        session_dicts = self._build_session_dicts(sessions)
        new_current = sessions[0].id
        self._current_session_id = new_current
        self._reset_guard_stats()
        self._window.set_sessions(session_dicts, new_current)
        self._window.set_current_session_title(sessions[0].title)

        self._brain.clear_history()
        self._notes.current_file = self._memory.get_session_notes_file(new_current)
        self._load_session_history(new_current)
        self._window.chat_widget.scroll_to_bottom()
        self._update_exchange_count()

    # -- Push-to-talk --

    @_safe_slot
    def _on_key_down(self) -> None:
        if self._input_mode != "push_to_talk":
            return
        if self._speaking:
            self._tts.stop()
        if self._processing and not self._speaking:
            return
        self._ptt_recorder.start_recording()
        self._signals.state_changed.emit("listening")

    @_safe_slot
    def _on_key_up(self) -> None:
        if self._input_mode != "push_to_talk":
            return
        if not self._ptt_recorder.is_recording:
            return
        wav_bytes = self._ptt_recorder.stop_recording()
        if wav_bytes is None:
            self._signals.state_changed.emit("idle")
            return

        self._processing = True
        thread = threading.Thread(
            target=self._process_question, args=(wav_bytes,), daemon=True
        )
        thread.start()

    def _process_question(self, wav_bytes: bytes) -> None:
        try:
            context = PipelineContext(
                input_mode=self._input_mode,
                current_session_id=self._current_session_id,
                suspend_input_stream=self._vad_recorder.suspend_stream,
            )
            hooks = PipelineHooks(
                on_state=self._signals.state_changed.emit,
                on_transcription=self._signals.transcription_ready.emit,
                on_response=self._signals.response_ready.emit,
                on_sessions_changed=self._signals.sessions_changed.emit,
                on_exchange_count_updated=self._update_exchange_count,
                on_speaking_started=self._on_pipeline_speaking_started,
            )
            self._question_pipeline.run(
                wav_bytes,
                context=context,
                hooks=hooks,
            )

        except Exception as e:
            logger.error("Processing failed: %s", e, exc_info=True)
            self._signals.error.emit(str(e))
            self._signals.state_changed.emit("idle")
        finally:
            self._speaking = False
            self._processing = False
            if self._input_mode == "voice_activation":
                self._vad_recorder.resume_stream()
                self._vad_recorder.resume()

    def _on_pipeline_speaking_started(self) -> None:
        self._speaking = True
        self._signals.state_changed.emit("speaking")

    # -- UI callbacks --

    @_safe_slot
    def _on_transcription_ready(self, text: str, timestamp: float, thumbnail: bytes) -> None:
        self._window.chat_widget.add_message(
            role="user",
            text=text,
            timestamp=timestamp,
            thumbnail_bytes=thumbnail if thumbnail else None,
        )

    @_safe_slot
    def _on_response_ready(self, text: str, timestamp: float, exchange_id: str) -> None:
        self._window.chat_widget.add_message(
            role="assistant",
            text=text,
            timestamp=timestamp,
            exchange_id=exchange_id,
        )

    @_safe_slot
    def _on_replay(self, exchange_id: str) -> None:
        exchanges = self._memory.get_exchanges(self._current_session_id or "")
        for ex in exchanges:
            if ex.id == exchange_id:
                threading.Thread(
                    target=self._replay_audio, args=(ex.assistant_text,), daemon=True
                ).start()
                return

    def _replay_audio(self, text: str) -> None:
        self._signals.state_changed.emit("speaking")
        self._tts.speak(text)
        self._signals.state_changed.emit("idle")

    @_safe_slot
    def _on_stop_requested(self) -> None:
        """Handle stop button click from the UI."""
        if self._speaking:
            logger.info("Stop requested via UI")
            self._tts.stop()

    def _show_device_switch_error(self, title: str, message: str) -> None:
        QMessageBox.warning(self._window, title, message)

    def _apply_camera_device_live(self, new_index: int) -> tuple[bool, int]:
        """Switch the active camera immediately, with automatic rollback."""
        self._ensure_device_switch_service()
        result = self._device_switch_service.switch_camera(
            current_camera=self._camera,
            previous_index=self._active_camera_index,
            target_index=int(new_index),
            apply_camera=self._window.camera_widget.set_camera,
        )
        self._camera = result.camera
        self._active_camera_index = result.active_index
        self._rebuild_question_pipeline()
        return result.success, result.active_index

    def _apply_mic_device_live(self, new_device: int | None) -> tuple[bool, int | None]:
        """Switch the active microphone immediately, with automatic rollback."""
        self._ensure_device_switch_service()
        result = self._device_switch_service.switch_mic(
            current_vad=self._vad_recorder,
            previous_device=self._active_mic_device,
            target_device=new_device,
            input_mode=self._input_mode,
        )
        self._vad_recorder = result.vad_recorder
        self._active_mic_device = result.active_device
        return result.success, result.active_device

    @_safe_slot
    def _on_settings_requested(self) -> None:
        """Open settings and apply non-device settings when the dialog closes."""
        from klaus.ui.settings_dialog import SettingsDialog
        dlg = SettingsDialog(
            self._window,
            active_camera_index=self._active_camera_index,
            active_mic_device=self._active_mic_device,
        )
        from klaus.ui import theme
        theme.apply_dark_titlebar(dlg)

        def on_camera_device_changed(new_index: int) -> None:
            _, effective_index = self._apply_camera_device_live(new_index)
            dlg.set_camera_selection(effective_index)

        def on_mic_device_changed(new_device: object) -> None:
            parsed_device = new_device if new_device is None else int(new_device)
            _, effective_device = self._apply_mic_device_live(parsed_device)
            dlg.set_mic_selection(effective_device)

        dlg.camera_device_changed.connect(on_camera_device_changed)
        dlg.mic_device_changed.connect(on_mic_device_changed)
        dlg.exec()

        # Settings dialog saves + reloads config on accept.
        self._runtime_settings = config.get_runtime_settings()
        self._ptt_key_name = self._runtime_settings.push_to_talk_key
        self._toggle_key_name = self._runtime_settings.toggle_key
        self._ptt_pynput_key = _resolve_pynput_key(self._ptt_key_name)
        self._toggle_pynput_key = _resolve_pynput_key(self._toggle_key_name)
        self._window.set_hotkeys(self._ptt_key_name, self._toggle_key_name)
        if self._hotkey_listener:
            self._hotkey_listener.stop()
            self._hotkey_listener = None
            self._start_hotkey_listener()

        vault = config.OBSIDIAN_VAULT_PATH or ""
        current_base = self._notes.base_path
        if vault != current_base:
            self._notes = NotesManager(vault)
            self._brain.set_notes_manager(self._notes)
            self._rebuild_question_pipeline()

        self._brain.reload_clients()
        self._tts.reload_client(settings=self._runtime_settings)
        self._stt.reload_settings(settings=self._runtime_settings)

    @_safe_slot
    def _on_error(self, message: str) -> None:
        self._window.chat_widget.add_status_message(f"Error: {message}")

    # -- Shutdown --

    def _shutdown(self) -> None:
        logger.info("Klaus shutting down")
        if self._hotkey_listener:
            self._hotkey_listener.stop()
        self._vad_recorder.stop()
        self._tts.stop()
        self._camera.stop()
        self._memory.close()
        logger.info("Shutdown complete")


def main():
    app = KlausApp()
    app.run()


if __name__ == "__main__":
    main()
