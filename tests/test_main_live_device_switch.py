"""Focused integration boundaries for KlausApp live device switching."""

from __future__ import annotations

import threading
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from klaus.main import KlausApp
from klaus.services.turn_coordinator import TurnCoordinator
from klaus.services.turn_state import TurnState


def _make_app(service: MagicMock) -> KlausApp:
    app = KlausApp.__new__(KlausApp)
    app._device_switch_service = service
    app._camera = "old-camera"
    app._vad_recorder = "old-vad"
    app._active_camera_index = 0
    app._active_mic_device = 1
    app._input_mode = "voice_activation"
    app._audio_output = MagicMock()
    app._window = SimpleNamespace(
        camera_widget=SimpleNamespace(
            set_camera=MagicMock(),
            set_source_selection=MagicMock(),
        ),
        clear_permission_warning=MagicMock(),
        show_permission_warning=MagicMock(),
    )
    app._ensure_device_switch_service = MagicMock()
    app._rebuild_question_pipeline = MagicMock()
    app._surface_reading_source_error = MagicMock()
    app._show_device_switch_error = MagicMock()
    app._turn_state = TurnState()
    return app


def _make_coordinator(
    turn_state: TurnState,
    *,
    ptt_recorder: MagicMock,
    pipeline: MagicMock,
    signals: MagicMock,
) -> TurnCoordinator:
    return TurnCoordinator(
        turn_state=turn_state,
        speculative_stt=MagicMock(),
        stt=MagicMock(),
        audio_output=MagicMock(),
        signals=signals,
        get_vad_recorder=MagicMock(),
        get_ptt_recorder=lambda: ptt_recorder,
        get_pipeline=lambda: pipeline,
        get_brain=MagicMock(),
        get_input_mode=lambda: "push_to_talk",
        get_current_session_id=lambda: None,
        update_exchange_count=MagicMock(),
    )


def test_ptt_press_during_answer_cancels_and_starts_new_recording() -> None:
    turn_state = TurnState()
    cancel_event = turn_state.begin_turn()
    pipeline = MagicMock()
    ptt_recorder = MagicMock(is_recording=False)
    signals = MagicMock()

    coordinator = _make_coordinator(
        turn_state, ptt_recorder=ptt_recorder, pipeline=pipeline, signals=signals
    )
    coordinator.on_key_down()

    assert cancel_event.is_set()
    pipeline.cancel_active.assert_called_once()
    ptt_recorder.start_recording.assert_called_once()
    signals.state_changed.emit.assert_called_once_with("listening")


def test_ptt_release_queues_question_until_cancelled_turn_finishes() -> None:
    turn_state = TurnState()
    turn_state.begin_turn()
    ptt_recorder = MagicMock(is_recording=True)
    ptt_recorder.stop_recording.return_value = b"next-question"
    signals = MagicMock()

    coordinator = _make_coordinator(
        turn_state, ptt_recorder=ptt_recorder, pipeline=MagicMock(), signals=signals
    )
    coordinator.on_key_up()

    assert turn_state.end_turn() == (None, b"next-question")
    signals.state_changed.emit.assert_called_once_with("thinking")


def test_apply_camera_device_live_delegates_to_service_and_refreshes_pipeline():
    service = MagicMock()
    service.switch_camera.return_value = SimpleNamespace(
        success=False,
        camera="rollback-camera",
        active_index=0,
        error_message="camera unavailable",
    )
    app = _make_app(service)

    ok, effective_index = KlausApp._apply_camera_device_live(app, 2)

    app._ensure_device_switch_service.assert_called_once()
    service.switch_camera.assert_called_once()
    kwargs = service.switch_camera.call_args.kwargs
    assert kwargs["current_camera"] == "old-camera"
    assert kwargs["previous_index"] == 0
    assert kwargs["target_index"] == 2
    assert kwargs["apply_camera"] is app._window.camera_widget.set_camera
    assert kwargs["force"] is False

    assert ok is False
    assert effective_index == 0
    assert app._camera == "rollback-camera"
    assert app._active_camera_index == 0
    app._rebuild_question_pipeline.assert_called_once()
    app._surface_reading_source_error.assert_called_once_with("camera unavailable")


def test_screen_recording_failure_surfaces_permission_action() -> None:
    app = KlausApp.__new__(KlausApp)
    app._window = SimpleNamespace(show_permission_warning=MagicMock())

    KlausApp._surface_reading_source_error(
        app,
        "Allow Klaus under System Settings > Privacy & Security > "
        "Screen & System Audio Recording, then restart Klaus.",
    )

    app._window.show_permission_warning.assert_called_once()
    title, message, settings_url = (
        app._window.show_permission_warning.call_args.args
    )
    assert title == "Allow Screen Recording"
    assert "turn it off and on" in message
    assert "quit and reopen Klaus" in message
    assert "choosing the source again" in message
    assert settings_url.startswith("x-apple.systempreferences:")


def test_apply_mic_device_live_delegates_to_service_and_updates_active_device():
    service = MagicMock()
    new_vad = MagicMock()
    service.switch_mic.return_value = SimpleNamespace(
        success=True,
        vad_recorder=new_vad,
        active_device=4,
    )
    app = _make_app(service)

    ok, effective_device = KlausApp._apply_mic_device_live(app, 4)

    app._ensure_device_switch_service.assert_called_once()
    service.switch_mic.assert_called_once_with(
        current_vad="old-vad",
        previous_device=1,
        target_device=4,
        input_mode="voice_activation",
    )

    assert ok is True
    assert effective_device == 4
    assert app._vad_recorder is new_vad
    assert app._active_mic_device == 4
    app._audio_output.set_playback_observer.assert_called_once_with(
        new_vad.observe_playback,
    )


@patch("klaus.main.config.set_camera_index")
def test_main_reading_selector_switches_and_persists(mock_set_camera_index):
    service = MagicMock()
    service.switch_camera.return_value = SimpleNamespace(
        success=True,
        camera="desk-view-camera",
        active_index=-2,
        error_message=None,
    )
    app = _make_app(service)

    KlausApp._on_reading_source_changed(app, -2)

    mock_set_camera_index.assert_called_once_with(-2, persist=True)
    app._window.camera_widget.set_source_selection.assert_called_with(-2)
    app._window.clear_permission_warning.assert_called_once()


@patch("klaus.main.config.set_camera_index")
@patch("klaus.main.config.reload")
def test_remarkable_pairing_forces_active_tablet_client_refresh(
    mock_reload, mock_set_camera_index
):
    app = _make_app(MagicMock())
    app._apply_camera_device_live = MagicMock(return_value=(True, -4))
    app._window.chat_widget = SimpleNamespace(add_status_message=MagicMock())
    app._window.show = MagicMock()
    app._window.raise_ = MagicMock()
    app._window.activateWindow = MagicMock()

    KlausApp._on_remarkable_paired(app, "Paired over Wi-Fi.")

    mock_reload.assert_called_once()
    app._apply_camera_device_live.assert_called_once_with(-4, force=True)
    mock_set_camera_index.assert_called_once_with(-4, persist=True)
    app._window.chat_widget.add_status_message.assert_called_once_with(
        "Paired over Wi-Fi."
    )


def test_camera_switch_refused_while_turn_in_progress() -> None:
    service = MagicMock()
    app = _make_app(service)
    app._turn_state.begin_turn()

    ok, effective_index = KlausApp._apply_camera_device_live(app, 2)

    assert ok is False
    assert effective_index == 0
    service.switch_camera.assert_not_called()
    app._show_device_switch_error.assert_called_once()


def test_forced_camera_switch_bypasses_turn_guard() -> None:
    service = MagicMock()
    service.switch_camera.return_value = SimpleNamespace(
        success=True,
        camera="new-camera",
        active_index=2,
        error_message=None,
    )
    app = _make_app(service)
    app._turn_state.begin_turn()

    ok, _ = KlausApp._apply_camera_device_live(app, 2, force=True)

    assert ok is True
    service.switch_camera.assert_called_once()


def test_mic_switch_refused_while_turn_in_progress() -> None:
    service = MagicMock()
    app = _make_app(service)
    app._turn_state.begin_turn()

    ok, effective_device = KlausApp._apply_mic_device_live(app, 4)

    assert ok is False
    assert effective_device == 1
    service.switch_mic.assert_not_called()
    app._show_device_switch_error.assert_called_once()
