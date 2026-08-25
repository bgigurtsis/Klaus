import io
import inspect
import logging
import threading
import time
import wave
from typing import Any, Callable

import numpy as np

import klaus.config as config

logger = logging.getLogger(__name__)


class AsyncSpeechToText:
    """Loads Moonshine on a background thread so the window shows first.

    ``transcribe`` blocks until the model is ready, so a question asked while
    the model is still loading waits instead of failing. ``on_ready`` is
    called once from the loader thread with ``None`` on success or the load
    error.
    """

    def __init__(
        self,
        settings: config.RuntimeSettings | None = None,
        on_ready: Callable[[Exception | None], None] | None = None,
    ) -> None:
        self._settings = settings
        self._on_ready = on_ready
        self._inner: SpeechToText | None = None
        self._error: Exception | None = None
        self._ready = threading.Event()
        threading.Thread(target=self._load, daemon=True, name="stt-loader").start()

    def _load(self) -> None:
        try:
            self._inner = SpeechToText(settings=self._settings)
        except Exception as exc:
            logger.error("Speech model failed to load: %s", exc)
            self._error = exc
        finally:
            self._ready.set()
            if self._on_ready:
                self._on_ready(self._error)

    @property
    def is_ready(self) -> bool:
        return self._ready.is_set() and self._error is None

    def wait_ready(self, timeout: float | None = None) -> bool:
        return self._ready.wait(timeout)

    def transcribe(self, wav_bytes: bytes) -> str:
        self._ready.wait()
        if self._error is not None or self._inner is None:
            raise RuntimeError(f"The speech model failed to load: {self._error}")
        return self._inner.transcribe(wav_bytes)

    def reload_settings(self, settings: config.RuntimeSettings | None = None) -> None:
        self._ready.wait()
        if self._inner is not None:
            self._inner.reload_settings(settings=settings)


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
            "Loading Moonshine STT (model=%s, language=%s) - "
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

        model_path, model_arch = self._get_model_with_retry(
            get_model_for_language, kwargs
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

    def _get_model_with_retry(self, get_model_for_language: Any, kwargs: dict) -> Any:
        """Fetch the model, retrying transient download failures with backoff.

        Moonshine caches completed files, so each retry resumes at file
        granularity rather than starting the 245 MB download over.
        """
        last_error: Exception | None = None
        for attempt in range(3):
            if attempt:
                delay = 2.0 * attempt
                logger.warning(
                    "Moonshine model download failed (%s); retrying in %.0fs",
                    last_error,
                    delay,
                )
                time.sleep(delay)
            try:
                return get_model_for_language(
                    self._settings.stt_moonshine_language, **kwargs
                )
            except TypeError:
                # Older moonshine-voice versions may not expose model selection.
                return get_model_for_language(self._settings.stt_moonshine_language)
            except OSError as exc:
                last_error = exc
        raise RuntimeError(
            f"Could not download the Moonshine speech model: {last_error}"
        ) from last_error

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
