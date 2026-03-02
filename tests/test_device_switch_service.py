from __future__ import annotations

from klaus.services.device_switch import DeviceSwitchService


class _FakeCamera:
    fail_indices: set[int] = set()

    def __init__(self, device_index: int = 0):
        self._device_index = device_index
        self.started = False

    def start(self) -> None:
        if self._device_index in self.fail_indices:
            raise RuntimeError("camera unavailable")
        self.started = True

    def stop(self) -> None:
        self.started = False


class _FakeVAD:
    fail_devices: set[int | None] = set()

    def __init__(self, device: int | None):
        self._device = device
        self._running = False

    def start(self) -> None:
        if self._device in self.fail_devices:
            self._running = False
            return
        self._running = True

    def stop(self) -> None:
        self._running = False

    @property
    def is_running(self) -> bool:
        return self._running


def _service(persist_camera, persist_mic, show_error) -> DeviceSwitchService:
    return DeviceSwitchService(
        camera_factory=_FakeCamera,
        vad_builder=lambda device: _FakeVAD(device),
        persist_camera_index=persist_camera.append,
        persist_mic_index=persist_mic.append,
        show_error=lambda title, message: show_error.append((title, message)),
    )


class TestDeviceSwitchService:
    def test_camera_switch_success(self):
        persisted_camera: list[int] = []
        persisted_mic: list[int | None] = []
        errors: list[tuple[str, str]] = []
        service = _service(persisted_camera, persisted_mic, errors)
        current = _FakeCamera(0)
        applied: list[_FakeCamera] = []

        result = service.switch_camera(
            current_camera=current,
            previous_index=0,
            target_index=1,
            apply_camera=applied.append,
        )

        assert result.success is True
        assert result.active_index == 1
        assert result.camera._device_index == 1
        assert len(applied) == 1
        assert persisted_camera == []
        assert errors == []

    def test_camera_switch_failure_rolls_back(self):
        _FakeCamera.fail_indices = {2}
        persisted_camera: list[int] = []
        persisted_mic: list[int | None] = []
        errors: list[tuple[str, str]] = []
        service = _service(persisted_camera, persisted_mic, errors)
        current = _FakeCamera(0)
        applied: list[_FakeCamera] = []

        result = service.switch_camera(
            current_camera=current,
            previous_index=0,
            target_index=2,
            apply_camera=applied.append,
        )

        assert result.success is False
        assert result.active_index == 0
        assert result.camera._device_index == 0
        assert persisted_camera == [0]
        assert len(errors) == 1
        _FakeCamera.fail_indices = set()

    def test_mic_switch_failure_rolls_back_and_persists(self):
        persisted_camera: list[int] = []
        persisted_mic: list[int | None] = []
        errors: list[tuple[str, str]] = []
        service = _service(persisted_camera, persisted_mic, errors)

        current = _FakeVAD(3)
        current.start()
        _FakeVAD.fail_devices = {8}

        result = service.switch_mic(
            current_vad=current,
            previous_device=3,
            target_device=8,
            input_mode="voice_activation",
        )

        assert result.success is False
        assert result.active_device == 3
        assert result.vad_recorder._device == 3
        assert result.vad_recorder.is_running is True
        assert persisted_mic == [3]
        assert len(errors) == 1
        _FakeVAD.fail_devices = set()
