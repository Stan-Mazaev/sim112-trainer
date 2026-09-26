"""
WebSocket для голосового канала курсант↔заявитель.

Клиент отправляет:
  - {"type": "audio_start"}              — начал говорить
  - {"type": "audio_chunk", "data": b64} — чанк PCM Int16 LE (16 кГц, моно)
  - {"type": "audio_end"}                — закончил говорить

Сервер отвечает:
  - {"type": "stt_result", "text": "..."}         — что распознали
  - {"type": "caller_response",
     "text": "...",
     "audio_b64": "..."}                          — ответ заявителя + голос
  - {"type": "turn", "metrics": {...}}            — метрики для HUD
  - {"type": "error", "message": "..."}
"""

from __future__ import annotations

import base64
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.sim112.session.manager import get_session_manager


logger = logging.getLogger("sim112.ws.call")

router = APIRouter()


MAX_TURN_BYTES = 16_000 * 2 * 60


@router.websocket("/ws/call/{call_id}")
async def ws_call(websocket: WebSocket, call_id: str):
    await websocket.accept()

    manager = get_session_manager()
    orchestrator = await manager.get(call_id)
    if orchestrator is None:
        await websocket.send_json({"type": "error", "message": "session_not_found"})
        await websocket.close()
        return

    logger.info("Голосовой канал открыт для звонка %s", call_id)

    buffer = bytearray()
    recording = False

    try:
        while True:
            msg = await websocket.receive_json()
            msg_type = msg.get("type")


            if msg_type == "audio_start":
                buffer.clear()
                recording = True
                await websocket.send_json({"type": "audio_ack", "state": "recording"})
                continue


            if msg_type == "audio_chunk":
                if not recording:
                    continue
                data_b64 = msg.get("data") or ""
                try:
                    chunk = base64.b64decode(data_b64)
                except Exception:
                    continue
                if len(buffer) + len(chunk) > MAX_TURN_BYTES:
                    logger.warning("Буфер переполнен, обрезаю.")
                    recording = False
                    buffer.clear()
                    await websocket.send_json({"type": "error", "message": "audio_too_long"})
                    continue
                buffer.extend(chunk)
                continue


            if msg_type == "audio_end":
                recording = False
                pcm_bytes = bytes(buffer)
                buffer.clear()

                if not pcm_bytes:
                    await websocket.send_json({"type": "stt_result", "text": ""})
                    continue


                try:
                    pipe = _get_voice_pipe()
                    dispatcher_text = await pipe.transcribe_dispatcher_pcm(pcm_bytes)
                except Exception as exc:
                    logger.error("STT упал: %s", exc)
                    await websocket.send_json({"type": "error", "message": "stt_failed"})
                    continue

                await websocket.send_json({
                    "type": "stt_result",
                    "text": dispatcher_text,
                })

                if not dispatcher_text.strip():
                    continue


                try:
                    turn = await orchestrator.step(
                        dispatcher_text=dispatcher_text,
                        duration_sec=len(pcm_bytes) / (16_000 * 2),
                    )
                except Exception as exc:
                    logger.error("orchestrator.step упал: %s", exc)
                    await websocket.send_json({"type": "error", "message": "step_failed"})
                    continue


                caller_text = turn.caller_response_text
                panic = turn.panic_index
                audio_b64 = await _tts_audio_b64(caller_text, panic=panic)


                await websocket.send_json({
                    "type": "caller_response",
                    "text": caller_text,
                    "audio_b64": audio_b64,
                    "panic": panic,
                })

                await websocket.send_json({
                    "type": "turn",
                    "metrics": {
                        "protocol_percent": turn.protocol_adherence.percent,
                        "panic_index": turn.panic_index,
                        "compliance_index": turn.compliance_index,
                        "trust_index": turn.trust_index,
                    },
                })
                continue


            await websocket.send_json({"type": "error", "message": f"unknown_type:{msg_type}"})

    except WebSocketDisconnect:
        logger.info("Голосовой канал закрыт для звонка %s", call_id)
    except Exception as exc:
        logger.error("Ошибка голосового WS для %s: %s", call_id, exc)




def _get_voice_pipe():
    from app.sim112.voice.pipe import VoicePipe
    from app.sim112.voice.stt import get_stt_engine
    from app.sim112.voice.tts import get_tts_engine
    return VoicePipe(stt=get_stt_engine(), tts=get_tts_engine())


async def _tts_audio_b64(text: str, panic: int) -> str | None:
    try:
        pipe = _get_voice_pipe()
        return await pipe.caller_speech_audio_b64(text, panic)
    except Exception as exc:
        logger.warning("TTS не отработал: %s", exc)
        return None