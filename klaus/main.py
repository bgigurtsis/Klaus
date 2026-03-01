"""Klaus -- Voice Research Assistant. Entry point."""

import functools
import logging
import queue
import sys
import time
import threading

from pynput.keyboard import Key, KeyCode, Listener as KeyboardListener

import klaus.config as config
from klaus.config import (
    PUSH_TO_TALK_KEY,
    TOGGLE_KEY,
    INPUT_MODE,
    VAD_SENSITIVITY,
    VAD_SILENCE_TIMEOUT,
    VAD_MIN_DURATION,
    VAD_MIN_VOICED_RATIO,
    VAD_MIN_VOICED_FRAMES,
    VAD_MIN_RMS_DBFS,
    VAD_MIN_VOICED_RUN_FRAMES,
)


def _resolve_pynput_key(key_name: str) -> Key | KeyCode:
    """Convert a config key name (e.g. ``'F2'``) to a pynput key object."""
    try:
        return getattr(Key, key_name.lower())
    except AttributeError:
        if len(key_name) == 1:
            return KeyCode.from_char(key_name)
        raise ValueError(f"Unknown hotkey: {key_name!r}")

from klaus.stt import SpeechToText  # noqa: E402  (before PyQt6: moonshine.dll must load first)

from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QApplication

logger = logging.getLogger(__name__)


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
from klaus.ui.main_window import MainWindow


def _new_guard_stats() -> dict[str, int]:
    """Create a fresh per-session STT guard stats dict."""
    return {
        "vad_discarded": 0,
        "quality_gate_discarded": 0,
    }


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
        self._current_session_id: str | None = None
        self._processing = False
        self._speaking = False
        self._input_mode: str = INPUT_MODE
        self._guard_stats = _new_guard_stats()
        self._guard_stats_lock = threading.Lock()
        self._hotkey_listener: KeyboardListener | None = None
        self._ptt_pynput_key = _resolve_pynput_key(PUSH_TO_TALK_KEY)
        self._toggle_pynput_key = _resolve_pynput_key(TOGGLE_KEY)

    def _init_components(self) -> None:
        """Create all API-dependent components.

        Called after the setup wizard has finished (if needed) so that API keys
        and device selections are available.
        """
        self._camera = Camera()
        self._ptt_recorder = PushToTalkRecorder()
        self._vad_recorder = VoiceActivatedRecorder(
            on_speech_start=self._on_vad_speech_start,
            on_speech_end=self._on_vad_speech_end,
            on_speech_discard=self._on_vad_discard,
            sensitivity=VAD_SENSITIVITY,
            silence_timeout=VAD_SILENCE_TIMEOUT,
            min_duration=VAD_MIN_DURATION,
            min_voiced_ratio=VAD_MIN_VOICED_RATIO,
            min_voiced_frames=VAD_MIN_VOICED_FRAMES,
            min_rms_dbfs=VAD_MIN_RMS_DBFS,
            min_voiced_run_frames=VAD_MIN_VOICED_RUN_FRAMES,
        )
        self._stt = SpeechToText()
        self._tts = TextToSpeech()
        self._notes = NotesManager()
        self._brain = Brain(notes=self._notes)
        self._memory = Memory()

    def run(self) -> None:
        logger.info("Klaus starting")
        app = QApplication(sys.argv)
        app.setApplicationName("Klaus")

        from klaus.ui import theme
        theme.load_fonts()
        app.setWindowIcon(QIcon(str(theme.ICON_PATH)))

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

        self._init_components()

        self._window = MainWindow()
        self._connect_signals()

        try:
            self._camera.start()
        except RuntimeError as e:
            logger.warning("Camera unavailable: %s", e)

        self._window.camera_widget.set_camera(self._camera)
        self._window.set_hotkeys(PUSH_TO_TALK_KEY, TOGGLE_KEY)

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
        ptt_key = self._ptt_pynput_key
        toggle_key = self._toggle_pynput_key

        def on_press(key: Key | KeyCode | None) -> None:
            if key == toggle_key:
                self._toggle_input_mode()
            elif key == ptt_key:
                self._on_key_down()

        def on_release(key: Key | KeyCode | None) -> None:
            if key == ptt_key:
                self._on_key_up()

        try:
            self._hotkey_listener = KeyboardListener(
                on_press=on_press, on_release=on_release,
            )
            self._hotkey_listener.daemon = True
            self._hotkey_listener.start()
            logger.info(
                "Global hotkey listener started (ptt=%s, toggle=%s)",
                PUSH_TO_TALK_KEY, TOGGLE_KEY,
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
            logger.info("Input mode: push-to-talk (hotkey: %s)", PUSH_TO_TALK_KEY)
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
            logger.info("Transcribing audio...")
            transcript = self._stt.transcribe(wav_bytes)
            if not transcript:
                logger.info("Empty transcript, returning to idle")
                self._signals.state_changed.emit("idle")
                return

            self._signals.state_changed.emit("thinking")

            logger.info("Capturing page image from camera...")
            image_b64 = self._camera.capture_base64_jpeg()
            thumbnail = self._camera.capture_thumbnail_bytes()
            logger.info("Page image: %s", "captured" if image_b64 else "unavailable")

            now = time.time()
            self._signals.transcription_ready.emit(
                transcript, now, thumbnail or b""
            )

            memory_context = self._memory.get_knowledge_summary()

            if self._notes.current_file:
                notes_context = f"Current notes file: {self._notes.current_file}"
            else:
                notes_context = "No notes file set for this session."

            sentence_queue: queue.Queue[str | None] = queue.Queue()
            first_sentence = threading.Event()

            def on_sentence(text: str) -> None:
                sentence_queue.put(text)
                if not first_sentence.is_set():
                    first_sentence.set()
                    self._speaking = True
                    self._signals.state_changed.emit("speaking")

            tts_thread = threading.Thread(
                target=self._tts.speak_streaming,
                args=(sentence_queue,),
                daemon=True,
            )
            tts_thread.start()

            logger.info(
                "Sending to Claude (image=%s, memory=%s, notes=%s)",
                "yes" if image_b64 else "no",
                "yes" if memory_context else "no",
                self._notes.current_file or "none",
            )
            exchange = self._brain.ask(
                question=transcript,
                image_base64=image_b64,
                memory_context=memory_context if memory_context else None,
                notes_context=notes_context,
                on_sentence=on_sentence,
            )
            sentence_queue.put(None)

            if exchange.notes_file_changed and self._current_session_id:
                self._memory.set_session_notes_file(
                    self._current_session_id, self._notes.current_file
                )

            logger.info("Claude responded (%d chars), saving exchange", len(exchange.assistant_text))

            if self._current_session_id:
                record = self._memory.save_exchange(
                    session_id=self._current_session_id,
                    user_text=exchange.user_text,
                    assistant_text=exchange.assistant_text,
                    image_base64=exchange.image_base64,
                    searches=exchange.searches,
                )
                exchange_id = record.id
            else:
                exchange_id = ""

            self._signals.response_ready.emit(
                exchange.assistant_text, time.time(), exchange_id
            )

            self._update_exchange_count()
            self._signals.sessions_changed.emit()

            tts_thread.join()
            logger.info("Playback complete, idle")
            self._signals.state_changed.emit("idle")

        except Exception as e:
            logger.error("Processing failed: %s", e, exc_info=True)
            self._signals.error.emit(str(e))
            self._signals.state_changed.emit("idle")
        finally:
            self._speaking = False
            self._processing = False
            if self._input_mode == "voice_activation":
                self._vad_recorder.resume()

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

    @_safe_slot
    def _on_settings_requested(self) -> None:
        """Open the settings dialog."""
        from klaus.ui.settings_dialog import SettingsDialog
        dlg = SettingsDialog(self._window)
        from klaus.ui import theme
        theme.apply_dark_titlebar(dlg)
        dlg.exec()

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
