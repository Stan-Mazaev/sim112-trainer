"""Точка входа FastAPI. Монтирует роуты, стартует всё."""

from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api.v1.endpoints.health import router as health_router
from app.api.v1.endpoints.simulation import router as simulation_router
from app.ws.instructor import router as ws_instructor_router
from app.ws.call import router as ws_call_router

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")


class UTF8JSONResponse(JSONResponse):
    """JSONResponse с явным charset=utf-8 — чтобы Windows-клиенты не портили кириллицу."""
    media_type = "application/json; charset=utf-8"


app = FastAPI(
    title="Система 112",
    description="ИИ-тренажёр диспетчеров экстренных служб",
    version="0.1.0",
    default_response_class=UTF8JSONResponse,
)


@app.on_event("startup")
async def _startup_preload_models():
    """
    Прогреваем STT и TTS при старте, чтобы первая фраза курсанта
    обрабатывалась без 10-секундной паузы.
    """
    import asyncio
    import logging
    logger = logging.getLogger("sim112.startup")

    async def _warm_stt():
        try:
            from app.sim112.voice.stt import get_stt_engine
            engine = get_stt_engine()
            await asyncio.to_thread(engine._ensure_loaded)
            logger.info("STT: прогрев завершён")
        except Exception as exc:
            logger.warning("STT прогрев не удался: %s", exc)

    async def _warm_tts():
        try:
            from app.sim112.voice.tts import get_tts_engine
            engine = get_tts_engine()
            logger.info("TTS: голос '%s'", engine._voice_name)
        except Exception as exc:
            logger.warning("TTS прогрев не удался: %s", exc)

    await asyncio.gather(_warm_stt(), _warm_tts())


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router, prefix="/api/v1")
app.include_router(simulation_router, prefix="/api/v1")


app.include_router(ws_instructor_router)
app.include_router(ws_call_router)


@app.get("/")
async def root() -> dict:
    return {
        "service": "sim112-backend",
        "docs": "/docs",
        "health": "/api/v1/health",
    }



from pathlib import Path

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"
if FRONTEND_DIR.exists():
    app.mount(
        "/arm",
        StaticFiles(directory=str(FRONTEND_DIR / "arm"), html=True),
        name="arm",
    )


if FRONTEND_DIR.exists():
    app.mount(
        "/instructor",
        StaticFiles(directory=str(FRONTEND_DIR / "instructor"), html=True),
        name="instructor",
    )