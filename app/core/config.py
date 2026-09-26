"""
Конфигурация приложения.

Использует pydantic-settings: читает из .env, поддерживает дефолты,
валидирует типы при загрузке.
"""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):

    APP_NAME: str = "sim112"
    APP_VERSION: str = "0.1.0"
    DEBUG: bool = False


    DATABASE_URL: str = "sqlite+aiosqlite:///./data/sim112.db"



    ENABLE_LOCAL_WEIGHTS: bool = False
    ENABLE_4BIT_QUANTIZATION: bool = True
    MODEL_NAME: str = "google/gemma-2-2b-it"
    MODEL_DEVICE: str = "cpu"



    MAX_CONTEXT_MESSAGES: int = 15


    AUDIO_CACHE_DIR: str = "data/audio_cache"
    VOSK_MODEL_DIR: str = "data/vosk/vosk-model-small-ru-0.22"


    TTS_ENABLED: bool = True
    STT_ENABLED: bool = False


    LOG_LEVEL: str = "INFO"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )



    def ensure_dirs(self) -> None:
        """Создаёт все нужные папки из настроек."""
        for d in (self.AUDIO_CACHE_DIR,):
            Path(d).mkdir(parents=True, exist_ok=True)


        if self.DATABASE_URL.startswith("sqlite"):

            db_path = self.DATABASE_URL.split("///", 1)[-1]
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)



settings = Settings()
settings.ensure_dirs()