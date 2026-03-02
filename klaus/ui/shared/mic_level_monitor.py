from __future__ import annotations

import logging
import threading

import numpy as np
import sounddevice as sd

logger = logging.getLogger(__name__)


class MicLevelMonitor:
    """Small helper to sample microphone input level for UI meters."""

    def __init__(self) -> None:
        self._stream: sd.InputStream | None = None
        self._rms = 0.0
        self._lock = threading.Lock()

    def start(self, device: int | None, sample_rate: int = 16000) -> bool:
        self.stop()

        def callback(indata, frames, time_info, status):
            rms = float(np.sqrt(np.mean(indata.astype(np.float32) ** 2)))
            with self._lock:
                self._rms = rms

        try:
            self._stream = sd.InputStream(
                samplerate=sample_rate,
                channels=1,
                dtype="int16",
                device=device,
                callback=callback,
            )
            self._stream.start()
        except Exception as exc:
            logger.warning("Failed to open mic stream: %s", exc)
            self._stream = None
            return False
        return True

    def stop(self) -> None:
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                pass
            self._stream = None

    def level_percent(self) -> int:
        with self._lock:
            rms = self._rms
        return min(int(rms / 32768 * 800), 100)
