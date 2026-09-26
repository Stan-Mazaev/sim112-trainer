"""
Обёртка над faster-whisper для распознавания речи курсанта.
Модель: Systran/faster-whisper-base (int8, CPU).
Принимает numpy-массив Int16, частота 16000 Гц, моно.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
from threading import Lock

import numpy as np
from faster_whisper import WhisperModel


logger = logging.getLogger("sim112.voice.stt")

SAMPLE_RATE = 16000


def _optimal_cpu_threads() -> int:
    logical = os.cpu_count() or 4
    return max(2, logical - 1)


class STTEngine:
    def __init__(
        self,
        model_name: str = "base",
        device: str = "cpu",
        compute_type: str = "int8",
        cpu_threads: int | None = None,
    ):
        self._lock = Lock()
        self._model: WhisperModel | None = None
        self._model_name = model_name
        self._device = device
        self._compute_type = compute_type
        self._cpu_threads = cpu_threads or _optimal_cpu_threads()

        self._cache: dict[str, str] = {}
        self._cache_max = 256

    def _ensure_loaded(self) -> None:
        if self._model is not None:
            return
        with self._lock:
            if self._model is not None:
                return
            logger.info(
                "STT: загружаю модель '%s' (%s, %s, cpu_threads=%d)...",
                self._model_name, self._device, self._compute_type, self._cpu_threads,
            )
            self._model = WhisperModel(
                self._model_name,
                device=self._device,
                compute_type=self._compute_type,
                cpu_threads=self._cpu_threads,
                num_workers=1,
            )
            logger.info("STT: модель загружена. Прогреваю энкодер...")
            self._warmup_locked()
            logger.info("STT: прогрев завершён.")

    def _warmup_locked(self) -> None:
        if self._model is None:
            return
        silence = np.zeros(int(SAMPLE_RATE * 0.5), dtype=np.float32)
        try:
            segments, _ = self._model.transcribe(
                silence, language="ru", beam_size=1, best_of=1,
                temperature=0.0, vad_filter=False,
                condition_on_previous_text=False, without_timestamps=True,
            )
            list(segments)
        except Exception as exc:
            logger.warning("STT: прогрев упал (не критично): %s", exc)

    def _transcribe_sync(self, pcm_int16: np.ndarray) -> str:
        key = hashlib.md5(pcm_int16.tobytes()).hexdigest()
        hit = self._cache.get(key)
        if hit is not None:
            logger.debug("STT: кэш-хит %s", key[:8])
            return hit

        self._ensure_loaded()
        assert self._model is not None

        audio = pcm_int16.astype(np.float32) / 32768.0

        segments, _info = self._model.transcribe(
            audio,
            language="ru",
            beam_size=1,
            best_of=1,
            temperature=0.0,
            vad_filter=True,
            vad_parameters={
                "min_silence_duration_ms": 300,
                "min_speech_duration_ms": 200,
                "speech_pad_ms": 100,
            },
            condition_on_previous_text=False,
            without_timestamps=True,
            initial_prompt=(
                "Диспетчер службы 112. Фразы: слушайте меня внимательно, "
                "что случилось, что произошло, что у вас, что там, "
                "назовите адрес, скажите адрес, ваш адрес, "
                "есть пострадавшие, есть ли пострадавшие, "
                "сколько человек, сколько людей, "
                "вызовите скорую, вызовите полицию, вызовите МЧС, "
                "не волнуйтесь, помощь едет, я вас слышу."
            ),
        )
        text = " ".join(seg.text.strip() for seg in segments).strip()

        if len(self._cache) >= self._cache_max:
            self._cache.pop(next(iter(self._cache)))
        self._cache[key] = text
        return text

    async def transcribe(self, pcm_int16: np.ndarray) -> str:
        if pcm_int16.size == 0:
            return ""
        min_samples = int(SAMPLE_RATE * 0.3)
        if pcm_int16.size < min_samples:
            return ""
        try:
            return await asyncio.to_thread(self._transcribe_sync, pcm_int16)
        except Exception as exc:
            logger.error("STT: ошибка транскрипции: %s", exc)
            return ""

    def warmup(self) -> None:
        self._ensure_loaded()


_stt_instance: STTEngine | None = None


def get_stt_engine() -> STTEngine:
    global _stt_instance
    if _stt_instance is None:
        _stt_instance = STTEngine()
    return _stt_instance