"""
WebSocket-эндпоинт для панели инструктора.

Инструктор подключается к WS /ws/instructor/{call_id} и получает:
1. Всю историю событий звонка (то, что уже произошло) — сразу при подключении.
2. Все новые события в реальном времени.
"""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.sim112.session.manager import get_session_manager

logger = logging.getLogger("sim112.ws.instructor")

router = APIRouter()


@router.websocket("/ws/instructor/{call_id}")
async def ws_instructor(websocket: WebSocket, call_id: str):
    await websocket.accept()

    manager = get_session_manager()
    orchestrator = await manager.get(call_id)

    if orchestrator is None:
        await websocket.send_json({"error": "session_not_found", "call_id": call_id})
        await websocket.close()
        return

    logger.info("Инструктор подключился к звонку %s", call_id)


    queue: asyncio.Queue = asyncio.Queue(maxsize=1000)

    def listener(_event_type, event):
        """Слушатель EventBus — кладёт событие в очередь без блокировки."""
        try:
            queue.put_nowait(event)
        except asyncio.QueueFull:
            logger.warning("Очередь инструктора переполнена для %s", call_id)



    orchestrator.events.subscribe(listener)

    try:

        history = orchestrator.events.timeline()
        await websocket.send_json({
            "type": "history",
            "events": history,
            "call_id": call_id,
        })


        while True:
            event = await queue.get()
            await websocket.send_json(event)

    except WebSocketDisconnect:
        logger.info("Инструктор отключился от звонка %s", call_id)
    except Exception as exc:
        logger.error("Ошибка в WS инструктора %s: %s", call_id, exc)
    finally:
        orchestrator.events.unsubscribe(listener)