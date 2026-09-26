"""
Голосовой пайплайн: STT (курсант) + TTS (заявитель).
"""

from __future__ import annotations

import base64
import logging

import numpy as np

from app.sim112.voice.stt import STTEngine
from app.sim112.voice.tts import TTSEngine


logger = logging.getLogger("sim112.voice.pipe")


class VoicePipe:
    """Фасад над голосовыми движками."""

    def __init__(self, stt: STTEngine, tts: TTSEngine):
        self.stt = stt
        self.tts = tts



    async def transcribe_dispatcher_pcm(self, pcm_bytes: bytes) -> str:
        """
        Принимает PCM Int16 LE (моно, 16 кГц) как bytes.
        Возвращает распознанный текст.
        """
        if not pcm_bytes:
            return ""
        pcm_int16 = np.frombuffer(pcm_bytes, dtype=np.int16)
        return await self.stt.transcribe(pcm_int16)



    async def caller_speech_audio_b64(self, text: str, panic: int) -> str | None:
        """Синтез речи заявителя, возвращает WAV в base64."""
        wav_bytes = await self.tts.synthesize(text, panic_level=panic)
        if not wav_bytes:
            return None
        return base64.b64encode(wav_bytes).decode("ascii")