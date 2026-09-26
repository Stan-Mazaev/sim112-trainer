"""Health-эндпоинт. Показывает, что сервер жив и в каком режиме работает."""

from __future__ import annotations

import os

from fastapi import APIRouter

router = APIRouter(prefix="/health", tags=["Health"])


@router.get("")
async def health() -> dict:
    from app.sim112.caller.engine import HAS_TRANSFORMERS

    return {
        "status": "OK",
        "service": "sim112-backend",
        "version": "0.1.0",
        "llm_mode": os.getenv("ENABLE_LOCAL_WEIGHTS", "false").lower() == "true" and HAS_TRANSFORMERS,
        "caller_mode": "llm" if (os.getenv("ENABLE_LOCAL_WEIGHTS", "false").lower() == "true" and HAS_TRANSFORMERS) else "fallback",
    }