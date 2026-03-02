"""Focused integration boundaries for KlausApp live device switching."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from klaus.main import KlausApp


def _make_app(service: MagicMock) -> KlausApp:
    app = KlausApp.__new__(KlausApp)
    app._device_switch_service = service
    app._camera = "old-camera"
    app._vad_recorder = "old-vad"
    app._active_camera_index = 0
    app._active_mic_device = 1
    app._input_mode = "voice_activation"
    app._window = SimpleNamespace(camera_widget=SimpleNamespace(set_camera=MagicMock()))
    app._ensure_device_switch_service = MagicMock()
    app._rebuild_question_pipeline = MagicMock()
    return app


def test_apply_camera_device_live_delegates_to_service_and_refreshes_pipeline():
    service = MagicMock()
    service.switch_camera.return_value = SimpleNamespace(
        success=False,
        camera="rollback-camera",
        active_index=0,
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

    assert ok is False
    assert effective_index == 0
    assert app._camera == "rollback-camera"
    assert app._active_camera_index == 0
    app._rebuild_question_pipeline.assert_called_once()


def test_apply_mic_device_live_delegates_to_service_and_updates_active_device():
    service = MagicMock()
    service.switch_mic.return_value = SimpleNamespace(
        success=True,
        vad_recorder="new-vad",
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
    assert app._vad_recorder == "new-vad"
    assert app._active_mic_device == 4
