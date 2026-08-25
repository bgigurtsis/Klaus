"""Voice-powered research assistant for physical and digital media."""

from __future__ import annotations

import functools
import logging
import platform
import sys
import threading

from klaus.hotkeys import HotkeyListener, should_disable_global_hotkeys

import klaus.config as config
from klaus.permissions import guidance_for_error
from klaus.stt import AsyncSpeechToText

from PyQt6.QtWidgets import QApplication, QMessageBox
from PyQt6.QtCore import QObject, pyqtSignal

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


from klaus import earcons
from klaus.camera import Camera
from klaus.audio import PushToTalkRecorder, VoiceActivatedRecorder
from klaus.audio_output import AudioOutput
from klaus.realtime import build_live_brain
from klaus.memory import Memory
from klaus.notes import NotesManager
from klaus.remarkable_pairing_server import RemarkablePairingServer
from klaus.services import (
    DeviceSwitchService,
    QuestionPipeline,
    SessionService,
    SessionView,
    SpeculativeTranscriber,
    TurnCoordinator,
    TurnState,
)
from klaus.ui.main_window import MainWindow


_ERROR_HINTS: tuple[tuple[tuple[str, ...], str], ...] = (
    (
        ("unauthorized", "invalid api key", "invalid_api_key", "401", "api key"),
        "The API key was rejected. Check it under Settings → API Keys.",
    ),
    (
        ("rate limit", "rate_limit", "429", "quota"),
        "The model is rate-limiting requests. Wait a moment, then retry.",
    ),
    (
        ("timed out", "timeout", "connection", "getaddrinfo", "network", "ssl", "socket"),
        "Klaus could not reach the model. Check your internet connection, then retry.",
    ),
)


def _humanize_error(message: str) -> str:
    """Prefix a raw exception message with a plain-language explanation."""
    lowered = message.lower()
    for needles, hint in _ERROR_HINTS:
        if any(needle in lowered for needle in needles):
            return f"{hint}\n{message}"
    return f"Something went wrong answering that question.\n{message}"


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
    assistant_text_delta = pyqtSignal(str)  # live transcript fragment for chat display
    turn_cancelled = pyqtSignal()
    error = pyqtSignal(str)
    exchange_count_updated = pyqtSignal(int)
    sessions_changed = pyqtSignal()
    status_message = pyqtSignal(str)
    remarkable_paired = pyqtSignal(str)
    stt_ready = pyqtSignal(str)  # empty on success, else the load error


class KlausApp:
    """Wires all components together into the core interaction loop."""

    def __init__(self):
        self._signals = Signals()
        self._runtime_settings = config.get_runtime_settings()
        self._turn_state = TurnState()
        self._input_mode: str = self._runtime_settings.input_mode
        self._last_ui_state = "idle"
        self._hotkeys = HotkeyListener(
            self._runtime_settings.push_to_talk_key,
            self._runtime_settings.toggle_key,
            on_ptt_down=self._on_key_down,
            on_ptt_up=self._on_key_up,
            on_toggle=self._toggle_input_mode,
        )
        self._active_camera_index: int = config.CAMERA_DEVICE_INDEX
        self._active_mic_device: int | None = _configured_mic_device()

    def _build_vad_recorder(self, device: int | None) -> VoiceActivatedRecorder:
        settings = config.get_runtime_settings()
        return VoiceActivatedRecorder(
            on_speech_start=self._on_vad_speech_start,
            on_speech_end=self._on_vad_speech_end,
            on_speech_discard=self._on_vad_discard,
            on_speech_maybe_end=self._on_vad_speech_maybe_end,
            on_barge_in=self._on_barge_in,
            sensitivity=settings.vad_sensitivity,
            silence_timeout=settings.vad_silence_timeout,
            early_silence_timeout=settings.vad_early_stt_timeout,
            min_duration=settings.vad_min_duration,
            min_voiced_ratio=settings.vad_min_voiced_ratio,
            min_voiced_frames=settings.vad_min_voiced_frames,
            min_rms_dbfs=settings.vad_min_rms_dbfs,
            min_voiced_run_frames=settings.vad_min_voiced_run_frames,
            start_trigger_ms=settings.vad_start_trigger_ms,
            barge_in_min_voiced_ms=settings.barge_in_min_voiced_ms,
            barge_in_rms_margin_dbfs=settings.barge_in_rms_margin_dbfs,
            device=device,
        )

    def _init_components(self) -> None:
        """Create all API-dependent components.

        Called after the setup wizard has finished (if needed) so that API keys
        and device selections are available.
        """
        self._runtime_settings = config.get_runtime_settings()
        settings = self._runtime_settings
        self._camera = Camera(settings.camera_device_index)
        self._active_camera_index = settings.camera_device_index
        self._active_mic_device = _configured_mic_device()
        self._ptt_recorder = PushToTalkRecorder()
        self._vad_recorder = self._build_vad_recorder(self._active_mic_device)
        self._stt = AsyncSpeechToText(
            settings=settings,
            on_ready=lambda error: self._signals.stt_ready.emit(
                str(error) if error else ""
            ),
        )
        self._speculative_stt = SpeculativeTranscriber(self._stt.transcribe)
        self._audio_output = AudioOutput(
            playback_observer=self._vad_recorder.observe_playback,
        )
        self._notes = NotesManager(base_path=settings.obsidian_vault_path)
        self._brain = build_live_brain(
            notes=self._notes,
            audio_output=self._audio_output,
            settings=settings,
        )
        self._memory = Memory()
        self._rebuild_question_pipeline()
        self._ensure_device_switch_service()
        self._coordinator = TurnCoordinator(
            turn_state=self._turn_state,
            speculative_stt=self._speculative_stt,
            stt=self._stt,
            audio_output=self._audio_output,
            signals=self._signals,
            get_vad_recorder=lambda: self._vad_recorder,
            get_ptt_recorder=lambda: self._ptt_recorder,
            get_pipeline=lambda: self._question_pipeline,
            get_brain=lambda: self._brain,
            get_input_mode=lambda: self._input_mode,
            get_current_session_id=lambda: self._session_service.current_session_id,
            update_exchange_count=lambda: self._session_service.update_exchange_count(),
            wake_camera=lambda: self._camera.wake(),
        )

    def _rebuild_question_pipeline(self) -> None:
        required = ("_stt", "_camera", "_brain", "_memory", "_notes")
        if not all(hasattr(self, attr) for attr in required):
            return
        self._question_pipeline = QuestionPipeline(
            stt=self._stt,
            camera=self._camera,
            brain=self._brain,
            memory=self._memory,
            notes=self._notes,
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

        _skip_pyobjc = should_disable_global_hotkeys()
        if not _skip_pyobjc:
            import ctypes, ctypes.util
            from Foundation import NSBundle, NSProcessInfo
            _libc = ctypes.CDLL(ctypes.util.find_library("c"))
            _libc.setprogname(b"Klaus")
            bundle = NSBundle.mainBundle()
            info = bundle.infoDictionary()
            info["CFBundleName"] = "Klaus"
            info["CFBundleDisplayName"] = "Klaus"
            NSProcessInfo.processInfo().setProcessName_("Klaus")
        elif _skip_pyobjc:
            logger.debug(
                "Skipping pyobjc process-name setup (macOS %s + Python %s "
                "has intermittent ctypes segfaults in pyobjc)",
                platform.mac_ver()[0], platform.python_version(),
            )

        app = QApplication(sys.argv)
        app.setApplicationName("Klaus")
        app.setApplicationDisplayName("Klaus")

        from pathlib import Path
        from PyQt6.QtGui import QIcon
        _icon_path = Path(__file__).resolve().parent / "ui" / "icon.png"
        if _icon_path.is_file():
            app.setWindowIcon(QIcon(str(_icon_path)))
            if not _skip_pyobjc:
                from AppKit import NSApplication, NSImage
                ns_app = NSApplication.sharedApplication()
                ns_image = NSImage.alloc().initByReferencingFile_(str(_icon_path))
                ns_image.setName_("NSApplicationIcon")
                ns_app.setApplicationIconImage_(ns_image)

        from klaus.ui import theme
        theme.load_fonts()
        from PyQt6.QtGui import QFont
        app_font = QFont(theme.FONT_FAMILY_NAME)
        app_font.setPixelSize(theme.FONT_SIZE_BODY)
        app.setFont(app_font)

        if not config.is_setup_complete() or not config.has_active_api_key():
            from klaus.ui.setup_wizard import SetupWizard
            wizard = SetupWizard()
            wizard.show()
            app.exec()
            config.reload()
            if not config.is_setup_complete() or not config.has_active_api_key():
                logger.info("Setup wizard closed without completing, exiting")
                sys.exit(0)
            self._runtime_settings = config.get_runtime_settings()
            self._input_mode = self._runtime_settings.input_mode
            self._hotkeys.set_keys(
                self._runtime_settings.push_to_talk_key,
                self._runtime_settings.toggle_key,
            )

        self._init_components()

        self._window = MainWindow()
        self._connect_signals()
        self._pairing_server = RemarkablePairingServer(
            on_paired=self._signals.remarkable_paired.emit,
        )
        try:
            self._pairing_server.start()
        except OSError as exc:
            logger.warning("One-click Paper Pure pairing is unavailable: %s", exc)
            self._pairing_server = None

        startup_reading_error: str | None = None
        try:
            self._camera.start()
            self._active_camera_index = self._camera.device_index
        except RuntimeError as e:
            logger.warning("Reading source unavailable: %s", e)
            startup_reading_error = str(e)
            self._camera = Camera(-1)
            self._active_camera_index = -1

        self._window.camera_widget.set_camera(self._camera)
        if startup_reading_error:
            self._surface_reading_source_error(startup_reading_error)
        self._window.set_hotkeys(
            self._hotkeys.ptt_key_name, self._hotkeys.toggle_key_name
        )

        self._session_service = self._create_session_service()
        self._session_service.load_initial()

        self._hotkeys.start()
        self._setup_input_mode()
        config.save_input_mode(self._input_mode)
        self._signals.mode_changed.emit(self._input_mode)

        self._window.show()
        self._window.chat_widget.scroll_to_bottom()
        if not self._stt.is_ready:
            self._signals.state_changed.emit("loading")
        logger.info("UI ready")
        exit_code = app.exec()

        self._shutdown()
        sys.exit(exit_code)

    def _connect_signals(self) -> None:
        sig = self._signals

        sig.state_changed.connect(self._on_state_changed)
        sig.transcription_ready.connect(self._on_transcription_ready)
        sig.response_ready.connect(self._on_response_ready)
        sig.assistant_text_delta.connect(self._on_assistant_text_delta)
        sig.turn_cancelled.connect(self._on_turn_cancelled_ui)
        sig.error.connect(self._on_error)
        sig.exchange_count_updated.connect(self._window.status_widget.set_exchange_count)
        sig.status_message.connect(self._window.chat_widget.add_status_message)
        sig.remarkable_paired.connect(self._on_remarkable_paired)
        sig.stt_ready.connect(self._on_stt_ready)

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
        self._window.camera_widget.source_changed.connect(
            self._on_reading_source_changed
        )

        self._window.ptt_key_pressed.connect(self._on_key_down)
        self._window.ptt_key_released.connect(self._on_key_up)
        self._window.toggle_key_pressed.connect(self._toggle_input_mode)

    # -- State handling --

    @_safe_slot
    def _on_state_changed(self, state: str) -> None:
        """Route state changes to the status widget."""
        if (
            state == "idle"
            and self._input_mode == "push_to_talk"
            and (self._ptt_recorder.is_recording or self._turn_state.has_queued_ptt_wav)
        ):
            state = "listening" if self._ptt_recorder.is_recording else "thinking"
        previous_state = self._last_ui_state
        self._last_ui_state = state
        self._window.status_widget.set_state(state)
        if state == "thinking" and previous_state != "thinking":
            self._play_earcon(earcons.accept_tone)

    @_safe_slot
    def _on_stt_ready(self, error: str) -> None:
        """Clear the loading capsule once the speech model finishes loading."""
        if error:
            self._signals.error.emit(f"The speech model failed to load: {error}")
        if self._last_ui_state == "loading":
            self._signals.state_changed.emit("idle")

    def _play_earcon(self, tone_factory) -> None:
        """Play a short audio cue without blocking the calling thread."""
        if not config.EARCONS_ENABLED:
            return
        threading.Thread(
            target=self._audio_output.play_pcm, args=(tone_factory(),), daemon=True,
        ).start()

    # -- Input mode --

    def _setup_input_mode(self) -> None:
        """Activate the current input mode and deactivate the other."""
        if self._input_mode == "push_to_talk":
            if self._vad_recorder.is_running:
                self._vad_recorder.stop()
            logger.info(
                "Input mode: push-to-talk (hotkey: %s)", self._hotkeys.ptt_key_name
            )
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
        if self._turn_state.processing:
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

    # -- VAD callbacks (delegate to the coordinator; called from audio threads) --

    def _on_vad_speech_start(self) -> None:
        self._coordinator.on_vad_speech_start()

    def _on_vad_speech_maybe_end(self, wav_bytes: bytes) -> None:
        self._coordinator.on_vad_speech_maybe_end(wav_bytes)

    def _on_vad_speech_end(self, wav_bytes: bytes) -> None:
        self._coordinator.on_vad_speech_end(wav_bytes)

    def _on_barge_in(self, seed) -> None:
        self._coordinator.on_barge_in(seed)

    def _on_vad_discard(self, reason: str) -> None:
        self._coordinator.on_vad_discard(reason)

    # -- Session management --

    def _create_session_service(self) -> SessionService:
        view = SessionView(
            set_sessions=self._window.set_sessions,
            set_current_title=self._window.set_current_session_title,
            clear_chat=self._window.chat_widget.clear,
            add_chat_message=self._window.chat_widget.add_message,
            scroll_chat_to_bottom=self._window.chat_widget.scroll_to_bottom,
            emit_exchange_count=self._signals.exchange_count_updated.emit,
        )
        return SessionService(
            self._memory,
            self._notes,
            view,
            reset_guard_stats=self._coordinator.reset_guard_stats,
            clear_brain_history=lambda: self._brain.clear_history(),
        )

    @property
    def _current_session_id(self) -> str | None:
        return self._session_service.current_session_id

    def _update_exchange_count(self) -> None:
        self._session_service.update_exchange_count()

    @_safe_slot
    def _refresh_session_list(self) -> None:
        self._session_service.refresh_list()

    @_safe_slot
    def _on_session_changed(self, session_id: str) -> None:
        self._session_service.activate(session_id)

    @_safe_slot
    def _on_new_session(self, title: str) -> None:
        self._session_service.create(title)

    @_safe_slot
    def _on_session_renamed(self, session_id: str, new_title: str) -> None:
        self._session_service.rename(session_id, new_title)

    @_safe_slot
    def _on_session_deleted(self, session_id: str) -> None:
        self._session_service.delete(session_id)

    # -- Push-to-talk --

    @_safe_slot
    def _on_key_down(self) -> None:
        self._coordinator.on_key_down()

    @_safe_slot
    def _on_key_up(self) -> None:
        self._coordinator.on_key_up()

    # -- UI callbacks --

    @_safe_slot
    def _on_transcription_ready(self, text: str, timestamp: float, thumbnail: bytes) -> None:
        self._window.chat_widget.add_message(
            role="user",
            text=text,
            timestamp=timestamp,
            thumbnail_bytes=thumbnail if thumbnail else None,
        )
        self._window.chat_widget.show_thinking()

    @_safe_slot
    def _on_assistant_text_delta(self, text: str) -> None:
        """Append a live transcript fragment to the assistant card."""
        self._window.chat_widget.append_assistant_stream(text)

    @_safe_slot
    def _on_turn_cancelled_ui(self) -> None:
        self._window.chat_widget.abort_assistant_stream()
        self._window.chat_widget.add_status_message(
            "Answer interrupted. Ask your next question whenever you are ready."
        )

    @_safe_slot
    def _on_response_ready(self, text: str, timestamp: float, exchange_id: str) -> None:
        record = self._memory.get_exchange(exchange_id) if exchange_id else None
        note_file_path = record.note_file_path if record else None
        if self._window.chat_widget.finalize_assistant_stream(
            text, exchange_id, note_file_path,
        ):
            return
        self._window.chat_widget.add_message(
            role="assistant",
            text=text,
            timestamp=timestamp,
            exchange_id=exchange_id,
            note_file_path=note_file_path,
        )

    @_safe_slot
    def _on_replay(self, exchange_id: str) -> None:
        exchanges = self._memory.get_exchanges(self._current_session_id or "")
        for ex in exchanges:
            if ex.id == exchange_id:
                threading.Thread(
                    target=self._coordinator.replay,
                    args=(ex.assistant_text,),
                    daemon=True,
                ).start()
                return

    @_safe_slot
    def _on_stop_requested(self) -> None:
        self._coordinator.request_stop()

    def _show_device_switch_error(self, title: str, message: str) -> None:
        QMessageBox.warning(self._window, title, message)

    def _surface_reading_source_error(self, error: str) -> None:
        guidance = guidance_for_error(error)
        if guidance is None:
            self._show_device_switch_error(
                "Reading Source Unavailable",
                f"{error}\n\nKlaus reverted to the previous reading source.",
            )
            return
        self._window.show_permission_warning(
            guidance.title,
            guidance.message,
            guidance.settings_url,
        )

    @_safe_slot
    def _on_reading_source_changed(self, new_index: int) -> None:
        """Apply a Desk View/PDF switch from the main preview selector."""
        success, effective_index = self._apply_camera_device_live(new_index)
        if success:
            config.set_camera_index(effective_index, persist=True)
        self._window.camera_widget.set_source_selection(effective_index)

    def _apply_camera_device_live(
        self, new_index: int, *, force: bool = False
    ) -> tuple[bool, int]:
        """Switch the active reading source immediately, with rollback."""
        if not force and self._turn_state.processing:
            logger.info("Deferred reading-source switch: a turn is in progress")
            self._show_device_switch_error(
                "Turn in Progress",
                "Klaus is answering a question. Stop the answer or wait for it "
                "to finish, then switch the reading source.",
            )
            return False, self._active_camera_index
        self._ensure_device_switch_service()
        result = self._device_switch_service.switch_camera(
            current_camera=self._camera,
            previous_index=self._active_camera_index,
            target_index=int(new_index),
            apply_camera=self._window.camera_widget.set_camera,
            force=force,
        )
        self._camera = result.camera
        self._active_camera_index = result.active_index
        self._rebuild_question_pipeline()
        if result.success:
            self._window.clear_permission_warning()
        elif result.error_message:
            self._surface_reading_source_error(result.error_message)
        return result.success, result.active_index

    def _apply_mic_device_live(self, new_device: int | None) -> tuple[bool, int | None]:
        """Switch the active microphone immediately, with automatic rollback."""
        if self._turn_state.processing:
            logger.info("Deferred microphone switch: a turn is in progress")
            self._show_device_switch_error(
                "Turn in Progress",
                "Klaus is answering a question. Stop the answer or wait for it "
                "to finish, then switch the microphone.",
            )
            return False, self._active_mic_device
        self._ensure_device_switch_service()
        result = self._device_switch_service.switch_mic(
            current_vad=self._vad_recorder,
            previous_device=self._active_mic_device,
            target_device=new_device,
            input_mode=self._input_mode,
        )
        self._vad_recorder = result.vad_recorder
        self._active_mic_device = result.active_device
        self._audio_output.set_playback_observer(
            self._vad_recorder.observe_playback,
        )
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
        self._hotkeys.restart(
            self._runtime_settings.push_to_talk_key,
            self._runtime_settings.toggle_key,
        )
        self._window.set_hotkeys(
            self._hotkeys.ptt_key_name, self._hotkeys.toggle_key_name
        )

        vault = config.OBSIDIAN_VAULT_PATH or ""
        current_base = self._notes.base_path
        if vault != current_base:
            self._notes = NotesManager(vault)
            self._session_service.set_notes_manager(self._notes)
            self._brain.set_notes_manager(self._notes)
            self._rebuild_question_pipeline()
        brain_is_gemini = type(self._brain).__name__ == "GeminiLiveBrain"
        selected_is_gemini = config.active_api_key_slug() == "gemini"
        if brain_is_gemini != selected_is_gemini:
            self._brain.close()
            self._brain = build_live_brain(
                notes=self._notes,
                audio_output=self._audio_output,
                settings=self._runtime_settings,
            )
            self._rebuild_question_pipeline()
        else:
            self._brain.reload_clients()
        self._window.set_live_model(config.live_model_details()["label"])
        self._stt.reload_settings(settings=self._runtime_settings)

    @_safe_slot
    def _on_error(self, message: str) -> None:
        self._window.chat_widget.dismiss_thinking()
        self._window.chat_widget.add_error_message(
            _humanize_error(message),
            on_retry=self._coordinator.retry_last_failed,
        )

    @_safe_slot
    def _on_remarkable_paired(self, message: str) -> None:
        """Select the tablet after reManager completes one-click pairing."""
        config.reload()
        success, effective_index = self._apply_camera_device_live(-4, force=True)
        if success:
            config.set_camera_index(effective_index, persist=True)
            self._window.camera_widget.set_source_selection(effective_index)
            self._window.chat_widget.add_status_message(message)
        self._window.show()
        self._window.raise_()
        self._window.activateWindow()

    # -- Shutdown --

    def _shutdown(self) -> None:
        logger.info("Klaus shutting down")
        if getattr(self, "_pairing_server", None) is not None:
            self._pairing_server.stop()
        self._hotkeys.stop()
        self._vad_recorder.stop()
        self._audio_output.stop()
        close_brain = getattr(self._brain, "close", None)
        if callable(close_brain):
            close_brain()
        self._camera.stop()
        self._memory.close()
        logger.info("Shutdown complete")


def main():
    app = KlausApp()
    app.run()


if __name__ == "__main__":
    main()
