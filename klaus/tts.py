import io
import logging
import re
import sys
import threading
import queue
import wave

import numpy as np
import sounddevice as sd
from openai import OpenAI

import klaus.config as config

logger = logging.getLogger(__name__)

SENTENCE_SPLIT = re.compile(r'(?<=[.!?])\s+')
MAX_CHUNK_CHARS = 4000

WRITE_BLOCK_FRAMES = 2048


class TextToSpeech:
    """Converts text to speech using gpt-4o-mini-tts with sentence-level streaming playback."""

    def __init__(self, settings: config.RuntimeSettings | None = None):
        self._settings = settings or config.get_runtime_settings()
        self._client = OpenAI(api_key=self._settings.openai_api_key)
        self._stop_event = threading.Event()
        self._playback_thread: threading.Thread | None = None
        self._stream: sd.OutputStream | None = None
        self._stream_lock = threading.Lock()

    def reload_client(self, settings: config.RuntimeSettings | None = None) -> None:
        """Recreate the OpenAI client to pick up key changes from config.reload()."""
        self._settings = settings or config.get_runtime_settings()
        self._client = OpenAI(api_key=self._settings.openai_api_key)

    @staticmethod
    def _decode_wav(wav_data: bytes) -> tuple[int, int, np.ndarray]:
        """Decode WAV bytes into (sample_rate, channels, int16 ndarray)."""
        buf = io.BytesIO(wav_data)
        with wave.open(buf, "rb") as wf:
            rate = wf.getframerate()
            channels = wf.getnchannels()
            frames = wf.readframes(wf.getnframes())
        audio = np.frombuffer(frames, dtype=np.int16)
        if channels > 1:
            audio = audio.reshape(-1, channels)
        return rate, channels, audio

    def _ensure_stream(self, rate: int, channels: int) -> sd.OutputStream:
        """Return the current output stream, creating one if needed."""
        with self._stream_lock:
            if self._stream is not None and not self._stream.closed:
                return self._stream
            latency = "high" if sys.platform == "darwin" else "low"
            self._stream = sd.OutputStream(
                samplerate=rate,
                channels=channels,
                dtype="int16",
                latency=latency,
            )
            self._stream.start()
            logger.info(
                "Opened TTS output stream (%d Hz, %d ch, latency=%s)",
                rate, channels, latency,
            )
            return self._stream

    def _close_stream(self) -> None:
        """Close the persistent output stream if open."""
        with self._stream_lock:
            if self._stream is not None and not self._stream.closed:
                try:
                    self._stream.stop()
                    self._stream.close()
                except Exception:
                    pass
                logger.info("Closed TTS output stream")
            self._stream = None

    def _write_audio(self, stream: sd.OutputStream, audio: np.ndarray) -> None:
        """Write audio to the stream in small blocks so stop stays responsive."""
        offset = 0
        total = len(audio)
        while offset < total and not self._stop_event.is_set():
            end = min(offset + WRITE_BLOCK_FRAMES, total)
            stream.write(audio[offset:end])
            offset = end

    def speak(self, text: str, on_sentence_start: callable = None) -> None:
        """Synthesize and play text. Batches into sentences for low-latency start.

        Args:
            text: The full text to speak.
            on_sentence_start: Optional callback(sentence_index, sentence_text) fired
                               before each sentence begins playback.
        """
        self._stop_event.clear()
        chunks = self._split_into_chunks(text)
        if not chunks:
            return

        logger.info(
            "TTS speaking (%d chars, %d chunks, voice=%s, model=%s)",
            len(text), len(chunks), self._settings.tts_voice, config.TTS_MODEL,
        )

        audio_queue: queue.Queue[bytes | None] = queue.Queue()

        synth_thread = threading.Thread(
            target=self._synthesize_worker,
            args=(chunks, audio_queue),
            daemon=True,
        )
        synth_thread.start()

        try:
            for i, chunk_text in enumerate(chunks):
                if self._stop_event.is_set():
                    break
                wav_data = audio_queue.get()
                if wav_data is None:
                    break
                rate, channels, audio = self._decode_wav(wav_data)
                stream = self._ensure_stream(rate, channels)
                if on_sentence_start:
                    on_sentence_start(i, chunk_text)
                self._write_audio(stream, audio)
        finally:
            self._close_stream()

    def speak_streaming(self, sentence_queue: queue.Queue[str | None]) -> None:
        """Play sentences as they arrive from a queue.

        Reads sentences from sentence_queue, synthesizes each via the API,
        and plays them sequentially. None in the queue signals completion.
        """
        self._stop_event.clear()
        audio_q: queue.Queue[bytes | None] = queue.Queue()

        synth_thread = threading.Thread(
            target=self._streaming_synth_worker,
            args=(sentence_queue, audio_q),
            daemon=True,
        )
        synth_thread.start()

        try:
            while not self._stop_event.is_set():
                wav_data = audio_q.get()
                if wav_data is None:
                    break
                rate, channels, audio = self._decode_wav(wav_data)
                stream = self._ensure_stream(rate, channels)
                self._write_audio(stream, audio)
        finally:
            self._close_stream()

        logger.info("TTS streaming playback finished")

    def _streaming_synth_worker(
        self,
        sentence_queue: queue.Queue[str | None],
        audio_queue: queue.Queue[bytes | None],
    ) -> None:
        """Read sentences from the input queue and synthesize them into audio."""
        idx = 0
        while not self._stop_event.is_set():
            sentence = sentence_queue.get()
            if sentence is None:
                break
            try:
                idx += 1
                logger.debug("Streaming synth chunk %d (%d chars)", idx, len(sentence))
                response = self._client.audio.speech.create(
                    model=config.TTS_MODEL,
                    voice=self._settings.tts_voice,
                    input=sentence,
                    instructions=config.TTS_VOICE_INSTRUCTIONS,
                    response_format="wav",
                    speed=self._settings.tts_speed,
                )
                audio_queue.put(response.content)
            except Exception as e:
                logger.warning("Streaming TTS synthesis failed on chunk %d: %s", idx, e)
                break
        audio_queue.put(None)

    def synthesize_to_wav(self, text: str) -> bytes:
        """Synthesize text to a single WAV buffer without playing it."""
        response = self._client.audio.speech.create(
            model=config.TTS_MODEL,
            voice=self._settings.tts_voice,
            input=text,
            instructions=config.TTS_VOICE_INSTRUCTIONS,
            response_format="wav",
            speed=self._settings.tts_speed,
        )
        return response.content

    def _synthesize_worker(
        self, chunks: list[str], audio_queue: queue.Queue
    ) -> None:
        for i, chunk in enumerate(chunks):
            if self._stop_event.is_set():
                audio_queue.put(None)
                return
            try:
                logger.debug("Synthesizing chunk %d/%d (%d chars)", i + 1, len(chunks), len(chunk))
                response = self._client.audio.speech.create(
                    model=config.TTS_MODEL,
                    voice=self._settings.tts_voice,
                    input=chunk,
                    instructions=config.TTS_VOICE_INSTRUCTIONS,
                    response_format="wav",
                    speed=self._settings.tts_speed,
                )
                audio_queue.put(response.content)
            except Exception as e:
                logger.warning("TTS synthesis failed on chunk %d: %s", i + 1, e)
                audio_queue.put(None)
                return
        audio_queue.put(None)

    def stop(self) -> None:
        logger.info("TTS playback interrupted")
        self._stop_event.set()
        self._close_stream()

    @staticmethod
    def _split_into_chunks(text: str) -> list[str]:
        """Split text into sentence-sized chunks respecting the token limit."""
        sentences = SENTENCE_SPLIT.split(text.strip())
        sentences = [s.strip() for s in sentences if s.strip()]

        chunks: list[str] = []
        current = ""
        for sentence in sentences:
            if len(current) + len(sentence) + 1 > MAX_CHUNK_CHARS:
                if current:
                    chunks.append(current)
                current = sentence
            else:
                current = f"{current} {sentence}".strip() if current else sentence
        if current:
            chunks.append(current)
        return chunks
