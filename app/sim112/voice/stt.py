"""
Обёртка над faster-whisper для распознавания речи курсанта.

Модель: Systran/faster-whisper-tiny (int8, CPU).
Принимает numpy-массив float32, частота 16000 Гц, моно.
"""

from __future__ import annotations

import asyncio
import logging
from threading import Lock

import numpy as np
from faster_whisper import WhisperModel


logger = logging.getLogger("sim112.voice.stt")

SAMPLE_RATE = 16000


class STTEngine:
    """Singleton-обёртка над faster-whisper."""

    def __init__(self, model_name: str = "base", device: str = "cpu", compute_type: str = "int8"):
        self._lock = Lock()
        self._model: WhisperModel | None = None
        self._model_name = model_name
        self._device = device
        self._compute_type = compute_type

    def _ensure_loaded(self) -> None:
        """Ленивая загрузка модели (не при старте сервера, а при первом использовании)."""
        if self._model is not None:
            return
        with self._lock:
            if self._model is not None:
                return
            logger.info("STT: загружаю модель '%s' (%s, %s)...", self._model_name, self._device, self._compute_type)
            self._model = WhisperModel(
                self._model_name,
                device=self._device,
                compute_type=self._compute_type,
            )
            logger.info("STT: модель загружена.")

    def _transcribe_sync(self, pcm_int16: np.ndarray) -> str:
        """Синхронная транскрипция. Принимает Int16 PCM, конвертирует в float32."""
        self._ensure_loaded()
        assert self._model is not None


        audio = pcm_int16.astype(np.float32) / 32768.0

        segments, _info = self._model.transcribe(
            audio,
            language="ru",
            beam_size=5,
            vad_filter=True,
            vad_parameters={
                "min_silence_duration_ms": 500,
                "min_speech_duration_ms": 300,
            },
            condition_on_previous_text=False,
            initial_prompt=(
                "Диалог с оператором службы 112. "
                "Слова: адрес, улица, дом, квартира, подъезд, этаж, "
                "пожар, дым, горит, пострадавшие, скорая, полиция, МЧС, "
                "человек без сознания, кровотечение, помощь, срочно."
            ),
        )
        text = " ".join(seg.text.strip() for seg in segments).strip()
        return text

    async def transcribe(self, pcm_int16: np.ndarray) -> str:
        """
        Асинхронная транскрипция. Работает в отдельном потоке,
        чтобы не блокировать event loop FastAPI.
        """
        if pcm_int16.size == 0:
            return ""


        min_samples = int(SAMPLE_RATE * 0.3)
        if pcm_int16.size < min_samples:
            logger.debug("STT: фрагмент слишком короткий (%d сэмплов)", pcm_int16.size)
            return ""

        try:
            return await asyncio.to_thread(self._transcribe_sync, pcm_int16)
        except Exception as exc:
            logger.error("STT: ошибка транскрипции: %s", exc)
            return ""



_stt_instance: STTEngine | None = None


def get_stt_engine() -> STTEngine:
    global _stt_instance
    if _stt_instance is None:
        _stt_instance = STTEngine()
    return _stt_instance