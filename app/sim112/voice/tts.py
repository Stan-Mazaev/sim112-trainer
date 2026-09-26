"""
Обёртка над pyttsx3 (Windows SAPI5) для синтеза речи заявителя.

Особенности:
- pyttsx3 НЕ потокобезопасен. Используется Lock + запуск в отдельном потоке
  через asyncio.to_thread, чтобы не блокировать event loop FastAPI.
- Кэш на диске: одна и та же фраза с теми же параметрами синтезируется один раз.
- Параметры голоса зависят от уровня паники: чем выше — тем быстрее и громче.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
from pathlib import Path
from threading import Lock

import pyttsx3


logger = logging.getLogger("sim112.voice.tts")


class TTSEngine:
    """
    Singleton-обёртка над pyttsx3. Один экземпляр на весь процесс.
    """

    def __init__(self, cache_dir: Path, voice_name_hint: str = "Irina"):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._lock = Lock()
        self._voice_id: str | None = None
        self._voice_name: str | None = None
        self._detect_voice(voice_name_hint)

    def _detect_voice(self, hint: str) -> None:
        """Ищет голос по подстроке в имени (например, 'Irina')."""
        try:
            engine = pyttsx3.init()
            voices = engine.getProperty("voices")
            for v in voices:
                if hint.lower() in v.name.lower():
                    self._voice_id = v.id
                    self._voice_name = v.name
                    logger.info("TTS: выбран голос '%s' (%s)", v.name, v.id)
                    break
            engine.stop()
        except Exception as exc:
            logger.error("TTS: не удалось инициализировать движок: %s", exc)

    def _synthesize_sync(
        self,
        text: str,
        rate: int,
        volume: float,
        out_path: Path,
    ) -> None:
        """
        Синхронный синтез. Вызывается из потока через asyncio.to_thread.
        pyttsx3 инициализируется заново на каждый вызов — иначе на Windows
        бывают зависания между сохранениями.
        """
        with self._lock:
            engine = pyttsx3.init()
            try:
                if self._voice_id:
                    engine.setProperty("voice", self._voice_id)
                engine.setProperty("rate", rate)
                engine.setProperty("volume", volume)
                engine.save_to_file(text, str(out_path))
                engine.runAndWait()
            finally:
                try:
                    engine.stop()
                except Exception:
                    pass

    async def synthesize(self, text: str, panic_level: int = 50) -> bytes:
        """
        Асинхронный синтез. Возвращает WAV-байты.

        Кэш: ключ = md5(text | rate | volume).
        """
        text = (text or "").strip()
        if not text:
            return b""

        rate, volume = self._params_for_panic(panic_level)
        key = hashlib.md5(f"{text}|{rate}|{volume}".encode("utf-8")).hexdigest()
        cache_file = self.cache_dir / f"{key}.wav"

        if cache_file.exists() and cache_file.stat().st_size > 44:
            return cache_file.read_bytes()

        try:
            await asyncio.to_thread(
                self._synthesize_sync, text, rate, volume, cache_file
            )
        except Exception as exc:
            logger.error("TTS: ошибка синтеза '%s': %s", text[:50], exc)
            return b""

        if not cache_file.exists() or cache_file.stat().st_size <= 44:
            logger.error("TTS: файл не создан или пуст: %s", cache_file)
            return b""

        return cache_file.read_bytes()

    @staticmethod
    def _params_for_panic(panic: int) -> tuple[int, float]:
        """
        Маппинг уровня паники → (rate, volume).

        panic  0–29: спокойствие, rate=140, volume=0.85
        panic 30–59: волнение, rate=160, volume=0.95
        panic 60–79: паника, rate=185, volume=1.0
        panic 80–100: истерика, rate=210, volume=1.0
        """
        if panic < 30:
            return 140, 0.85
        if panic < 60:
            return 160, 0.95
        if panic < 80:
            return 185, 1.0
        return 210, 1.0



_tts_instance: TTSEngine | None = None


def get_tts_engine() -> TTSEngine:
    global _tts_instance
    if _tts_instance is None:
        from app.core.config import settings
        cache_dir = Path(getattr(settings, "AUDIO_CACHE_DIR", "data/audio_cache"))
        _tts_instance = TTSEngine(cache_dir=cache_dir)
    return _tts_instance