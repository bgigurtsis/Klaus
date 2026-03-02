import ctypes
import io
import inspect
import logging
import sys
import time
import wave
from pathlib import Path
from typing import Any

import numpy as np

import klaus.config as config

logger = logging.getLogger(__name__)


def _preload_native_lib() -> None:
    """Pre-load moonshine.dll before PyQt6 to avoid WinError 1114 on Windows.

    PyQt6 loads DLLs that conflict with moonshine's native library if it hasn't
    been loaded first.  Calling this at import time (before PyQt6) sidesteps the
    issue entirely.
    """
    if sys.platform != "win32":
        return
    try:
        import moonshine_voice
        dll = Path(moonshine_voice.__file__).parent / "moonshine.dll"
        if dll.exists():
            ctypes.CDLL(str(dll))
    except Exception:
        pass


_preload_native_lib()


class SpeechToText:
    """Transcribes audio using Moonshine Voice (local, on-device)."""

    def __init__(self, settings: config.RuntimeSettings | None = None) -> None:
        self._settings = settings or config.get_runtime_settings()
        self._transcriber = self._load_moonshine()

    def reload_settings(self, settings: config.RuntimeSettings | None = None) -> None:
        self._settings = settings or config.get_runtime_settings()
        self._transcriber = self._load_moonshine()

    def transcribe(self, wav_bytes: bytes) -> str:
        """Transcribe WAV audio bytes to text."""
        return self._transcribe_moonshine(wav_bytes)

    # ------------------------------------------------------------------
    # Moonshine backend
    # ------------------------------------------------------------------

    def _load_moonshine(self) -> Any:
        """Load the Moonshine Voice transcriber, downloading the model if needed."""
        try:
            from moonshine_voice import (
                Transcriber,
                get_model_for_language,
            )
        except ImportError as exc:
            raise RuntimeError(
                "moonshine-voice is not installed. "
                "Install with `pip install moonshine-voice`."
            ) from exc

        logger.info(
            "Loading Moonshine STT (model=%s, language=%s) — "
            "first launch may take 10-30s to download and compile the model ...",
            self._settings.stt_moonshine_model,
            self._settings.stt_moonshine_language,
        )
        t0 = time.monotonic()
        kwargs: dict[str, object] = {}
        try:
            params = inspect.signature(get_model_for_language).parameters
        except (TypeError, ValueError):
            params = {}
        if "model_size" in params:
            kwargs["model_size"] = self._settings.stt_moonshine_model
        elif "model" in params:
            kwargs["model"] = self._settings.stt_moonshine_model

        try:
            model_path, model_arch = get_model_for_language(
                self._settings.stt_moonshine_language, **kwargs
            )
        except TypeError:
            # Older moonshine-voice versions may not expose model selection.
            model_path, model_arch = get_model_for_language(
                self._settings.stt_moonshine_language
            )
        transcriber = Transcriber(
            model_path=model_path, model_arch=model_arch
        )
        elapsed = time.monotonic() - t0
        logger.info(
            "Moonshine STT ready in %.1fs (language=%s, path=%s)",
            elapsed,
            self._settings.stt_moonshine_language,
            model_path,
        )
        return transcriber

    def _transcribe_moonshine(self, wav_bytes: bytes) -> str:
        """Run Moonshine Voice on WAV bytes, return transcript text."""
        audio, sample_rate = self._decode_wav(wav_bytes)
        logger.info(
            "Transcribing audio (%.1f KB, backend=moonshine)",
            len(wav_bytes) / 1024,
        )

        transcript = self._transcriber.transcribe_without_streaming(
            audio.tolist(), sample_rate
        )

        parts = [line.text.strip() for line in transcript.lines if line.text.strip()]
        text = " ".join(parts)
        logger.info("Transcript (%d chars): %s", len(text), text[:80])
        return text

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------

    @staticmethod
    def _decode_wav(wav_bytes: bytes) -> tuple[np.ndarray, int]:
        """Decode WAV bytes to mono float32 samples in [-1, 1] and sample rate."""
        with wave.open(io.BytesIO(wav_bytes), "rb") as wf:
            channels = wf.getnchannels()
            sample_width = wf.getsampwidth()
            sample_rate = wf.getframerate()
            raw_frames = wf.readframes(wf.getnframes())

        if sample_width != 2:
            raise ValueError(f"Unsupported WAV sample width: {sample_width}")

        audio = np.frombuffer(raw_frames, dtype=np.int16).astype(np.float32)
        if channels > 1:
            audio = audio.reshape(-1, channels).mean(axis=1)
        return audio / 32768.0, sample_rate
