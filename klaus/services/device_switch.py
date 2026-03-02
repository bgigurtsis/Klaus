from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Callable

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CameraSwitchResult:
    success: bool
    camera: object
    active_index: int


@dataclass(frozen=True)
class MicSwitchResult:
    success: bool
    vad_recorder: object
    active_device: int | None


class DeviceSwitchService:
    """Apply live camera/mic switches with rollback on failure."""

    def __init__(
        self,
        camera_factory: Callable[[int], object],
        vad_builder: Callable[[int | None], object],
        persist_camera_index: Callable[[int], None],
        persist_mic_index: Callable[[int | None], None],
        show_error: Callable[[str, str], None],
    ) -> None:
        self._camera_factory = camera_factory
        self._vad_builder = vad_builder
        self._persist_camera_index = persist_camera_index
        self._persist_mic_index = persist_mic_index
        self._show_error = show_error

    def switch_camera(
        self,
        current_camera: object,
        previous_index: int,
        target_index: int,
        apply_camera: Callable[[object], None],
    ) -> CameraSwitchResult:
        target = int(target_index)
        if target == previous_index:
            return CameraSwitchResult(True, current_camera, target)

        current_camera.stop()
        candidate = self._camera_factory(target)
        if target >= 0:
            try:
                candidate.start()
            except RuntimeError as exc:
                logger.warning("Camera switch failed for index %d: %s", target, exc)
                rollback_index = previous_index
                rollback_camera = self._camera_factory(rollback_index)
                if rollback_index >= 0:
                    try:
                        rollback_camera.start()
                    except RuntimeError as rollback_exc:
                        logger.warning(
                            "Camera rollback failed for index %d: %s",
                            rollback_index,
                            rollback_exc,
                        )
                        rollback_index = -1
                        rollback_camera = self._camera_factory(-1)
                apply_camera(rollback_camera)
                self._persist_camera_index(rollback_index)
                self._show_error(
                    "Camera Unavailable",
                    "Could not switch to that camera. Reverted to the previous device.",
                )
                return CameraSwitchResult(False, rollback_camera, rollback_index)

        apply_camera(candidate)
        return CameraSwitchResult(True, candidate, target)

    def switch_mic(
        self,
        current_vad: object,
        previous_device: int | None,
        target_device: int | None,
        input_mode: str,
    ) -> MicSwitchResult:
        target = None if target_device is None else int(target_device)
        if target == previous_device:
            return MicSwitchResult(True, current_vad, target)

        previous_recorder = current_vad
        was_running = previous_recorder.is_running
        previous_recorder.stop()

        candidate = self._vad_builder(target)
        candidate.start()
        if not candidate.is_running:
            candidate.stop()
            logger.warning("Mic switch failed for device %s", target)

            rollback = self._vad_builder(previous_device)
            if was_running:
                rollback.start()
                if not rollback.is_running:
                    logger.warning("Mic rollback failed for device %s", previous_device)
                    rollback.stop()
                    rollback = self._vad_builder(None)
                    rollback.start()
                    if rollback.is_running:
                        previous_device = None
                    else:
                        logger.warning("Mic fallback to system default also failed")
            self._persist_mic_index(previous_device)
            self._show_error(
                "Microphone Unavailable",
                "Could not switch to that microphone. Reverted to the previous device.",
            )
            return MicSwitchResult(False, rollback, previous_device)

        if input_mode != "voice_activation":
            candidate.stop()

        return MicSwitchResult(True, candidate, target)
