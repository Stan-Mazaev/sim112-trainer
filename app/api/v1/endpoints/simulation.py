"""
REST-эндпоинты тренажёра.

Поток курсанта:
1. POST /simulation/start — инструктор или курсант выбирает сценарий.
2. POST /simulation/step — курсант говорит реплику (текст после STT).
3. POST /simulation/card/update — курсант заполняет поле карточки.
4. POST /simulation/service/activate — курсант нажимает кнопку службы.
5. POST /simulation/end — завершение звонка, финальный отчёт.
"""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException, Response, status

from app.sim112.schemas import (
    CardUpdateRequest,
    CardUpdateResponse,
    EndSimulationRequest,
    EndSimulationResponse,
    Scenario,
    ScenarioId,
    ServiceActivateRequest,
    ServiceActivateResponse,
    StartSimulationRequest,
    StartSimulationResponse,
    StepSimulationRequest,
    StepSimulationResponse,
    DifficultyLevel,
    CallReport,
    CallerState,
)
from app.sim112.scenarios.registry import get_registry
from app.sim112.session.manager import get_session_manager
from app.sim112.session.orchestrator import CallOrchestrator
from app.sim112.report.generator import generate_report
from app.sim112.voice.pipe import VoicePipe
from app.sim112.voice.tts import get_tts_engine

logger = logging.getLogger("sim112.api.simulation")

router = APIRouter(prefix="/simulation", tags=["Simulation 112"])






TICKETS_DIR = Path(__file__).resolve().parents[3] / "sim112" / "scenarios" / "tickets"


def _find_ticket_scenario(scenario_id: str):
    """
    Ищет TicketScenario по его id во всех файлах ticket_*.json.
    Возвращает TicketScenario или None.
    """
    if not TICKETS_DIR.exists():
        return None

    import json as _json
    from app.sim112.scenarios.schemas import Ticket

    for path in sorted(TICKETS_DIR.glob("ticket_*.json")):
        try:
            with path.open(encoding="utf-8") as f:
                raw = _json.load(f)
            ticket = Ticket.model_validate(raw)
        except Exception as exc:
            logger.warning("Не удалось загрузить билет %s: %s", path.name, exc)
            continue

        for sc in ticket.scenarios:
            if sc.id == scenario_id:
                return sc

    return None


def _ticket_to_legacy_scenario(ticket_scenario) -> Scenario:
    """
    Конвертирует TicketScenario из билета в старый Scenario,
    который принимает CallOrchestrator.
    """
    c = ticket_scenario.caller
    return Scenario(
        id=ScenarioId.FIRE_APARTMENT,
        title=(
            f"Билет {ticket_scenario.ticket_number}, "
            f"случай {ticket_scenario.case_number} — "
            f"{ticket_scenario.situation}"
        ),
        description=ticket_scenario.situation,
        difficulty=DifficultyLevel(ticket_scenario.difficulty),
        initial_prompt="",
        opening_line=c.opening_line,
        airtime_target=(30, 60),
        required_fields=["address", "what_happened"],
        critical_fields=["address"],
        initial_caller_state=CallerState(
            panic=c.initial_panic,
            trust=c.initial_trust,
            cooperation=c.initial_cooperation,
            phase="shock",
            hidden_facts=dict(c.hidden_facts),
        ),
        hidden_facts_template=dict(c.hidden_facts),
    )






@router.post(
    "/start",
    response_model=StartSimulationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Начать новую сессию звонка",
)
async def start_simulation(payload: StartSimulationRequest) -> StartSimulationResponse:

    if payload.scenario_id.startswith("ticket_"):

        ticket_scenario = _find_ticket_scenario(payload.scenario_id)
        if ticket_scenario is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Сценарий билета '{payload.scenario_id}' не найден",
            )
        scenario = _ticket_to_legacy_scenario(ticket_scenario)
        expected = ticket_scenario.expected
    else:

        try:
            sid = ScenarioId(payload.scenario_id)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Неизвестный scenario_id '{payload.scenario_id}'",
            )
        registry = get_registry()
        scenario = registry.get(sid)
        if scenario is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Сценарий '{payload.scenario_id}' не найден",
            )
        expected = None


    orchestrator = CallOrchestrator(
        cadet_id=payload.cadet_id,
        scenario=scenario,
        difficulty=payload.difficulty,
        expected=expected,
    )
    orchestrator.cadet_name = payload.cadet_name
    start_data = await orchestrator.start()

    manager = get_session_manager()
    await manager.add(orchestrator)

    logger.info(
        "Сессия %s создана: cadet=%s, scenario=%s, difficulty=%s",
        orchestrator.call_id,
        payload.cadet_id,
        payload.scenario_id,
        payload.difficulty,
    )


    opening_audio = await _tts_audio_b64(
        start_data["opening_line"],
        panic=orchestrator.caller_state_machine.state.panic,
    )

    return StartSimulationResponse(
        call_id=orchestrator.call_id,
        scenario=scenario,
        opening_line=start_data["opening_line"],
        opening_audio_b64=opening_audio,
        caller_state=orchestrator.caller_state_machine.state,
        card_template=orchestrator.card_manager.card,
    )






@router.post(
    "/step",
    response_model=StepSimulationResponse,
    summary="Обработать реплику курсанта",
)
async def step_simulation(payload: StepSimulationRequest) -> StepSimulationResponse:
    orchestrator = await _get_orchestrator_or_404(payload.call_id)

    try:
        turn = await orchestrator.step(
            dispatcher_text=payload.dispatcher_text,
            duration_sec=payload.duration_sec or 3.0,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))

    audio_b64 = await _tts_audio_b64(
        turn.caller_response_text,
        panic=turn.panic_index,
    )

    return StepSimulationResponse(
        turn=turn,
        caller_audio_url=None,
        caller_audio_b64=audio_b64,
    )






@router.post(
    "/card/update",
    response_model=CardUpdateResponse,
    summary="Обновить поле карточки вызова",
)
async def update_card(payload: CardUpdateRequest) -> CardUpdateResponse:
    orchestrator = await _get_orchestrator_or_404(payload.call_id)

    result = await orchestrator.update_card(payload.field, payload.value)

    if not result["accepted"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Поле '{payload.field}' не разрешено для данного сценария",
        )

    return CardUpdateResponse(
        card=orchestrator.card_manager.card,
        protocol_adherence=result["protocol_adherence"],
    )






@router.post(
    "/service/activate",
    response_model=ServiceActivateResponse,
    summary="Активировать экстренную службу",
)
async def activate_service(payload: ServiceActivateRequest) -> ServiceActivateResponse:
    orchestrator = await _get_orchestrator_or_404(payload.call_id)

    result = await orchestrator.activate_service(payload.service)

    from app.sim112.schemas import ServiceActivation
    activation = ServiceActivation(
        service=payload.service,
        activated_at_sec=result["activation"]["at_sec"],
    )

    return ServiceActivateResponse(
        activation=activation,
        new_violations=result["new_violations"],
    )






@router.post(
    "/end",
    response_model=EndSimulationResponse,
    summary="Завершить звонок и получить отчёт",
)
async def end_simulation(payload: EndSimulationRequest) -> EndSimulationResponse:
    orchestrator = await _get_orchestrator_or_404(payload.call_id)

    final_data = await orchestrator.end(reason=payload.reason)


    report = generate_report(orchestrator, final_data)





    logger.info(
        "Сессия %s завершена. Итоговая оценка: %s",
        payload.call_id,
        report.grade,
    )

    return EndSimulationResponse(report=report)






@router.get(
    "/scenarios",
    summary="Список доступных сценариев из билетов",
)
async def list_scenarios() -> dict:
    """
    Возвращает список сценариев из билетов — для селектора в АРМ.
    """
    import json
    from pathlib import Path

    tickets_dir = Path(__file__).resolve().parents[3] / "sim112" / "scenarios" / "tickets"
    items: list[dict] = []

    if tickets_dir.exists():
        for path in sorted(tickets_dir.glob("ticket_*.json")):
            with path.open(encoding="utf-8") as f:
                data = json.load(f)
            ticket_number = data.get("ticket_number")
            for sc in data.get("scenarios", []):
                items.append({
                    "id": sc["id"],
                    "ticket_number": ticket_number,
                    "case_number": sc["case_number"],
                    "situation": sc["situation"],
                    "difficulty": sc["difficulty"],
                })

    return {"scenarios": items}






@router.get(
    "/instructor/sessions",
    summary="Список всех сессий для панели инструктора",
)
async def list_active_sessions() -> dict:
    """
    Возвращает список сессий — и активные, и завершённые.

    Завершённые остаются в памяти в течение сессии процесса,
    чтобы инструктор мог разобрать звонок с курсантом после его окончания.
    """
    manager = get_session_manager()
    active: list[dict] = []
    completed: list[dict] = []

    for call_id in manager.all_ids():
        orch = await manager.get(call_id)
        if orch is None:
            continue

        status_value = orch.status.value if hasattr(orch.status, "value") else str(orch.status)
        item = {
            "call_id": call_id,
            "cadet_id": orch.cadet_id,
            "scenario_title": orch.scenario.title or str(orch.scenario.id),
            "scenario_id": str(orch.scenario.id),
            "status": status_value,
            "started_at": orch.started_at.isoformat(),
            "ended_at": orch.ended_at.isoformat() if orch.ended_at else None,
            "duration_sec": orch.audit.current_sec,
            "violations_count": len(orch.audit.all_violations),
        }

        if status_value == "active":
            active.append(item)
        else:
            completed.append(item)


    completed.sort(key=lambda x: x.get("ended_at") or "", reverse=True)

    return {
        "active": active,
        "completed": completed,
        "counts": manager.counts(),
    }






@router.get(
    "/{call_id}/report.pdf",
    summary="Скачать PDF-отчёт по завершённому звонку",
    response_class=Response,
    responses={
        200: {"content": {"application/pdf": {}}},
        404: {"description": "Сессия не найдена"},
        409: {"description": "Звонок ещё не завершён"},
    },
)
async def download_report_pdf(call_id: str) -> Response:
    """
    Отдаёт PDF-отчёт. Доступно только пока сессия в памяти
    (завершённая, ещё не удалённая через DELETE /{call_id}).
    """
    from app.sim112.report.pdf import render_report_pdf

    orchestrator = await _get_orchestrator_or_404(call_id)

    if orchestrator.final_data is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Звонок ещё не завершён — PDF-отчёт недоступен",
        )

    report = generate_report(orchestrator, orchestrator.final_data)
    pdf_bytes = render_report_pdf(report)

    filename = f"report_{call_id}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
        },
    )






@router.get(
    "/{call_id}",
    summary="Получить текущее состояние сессии",
)
async def get_session_status(call_id: str) -> dict:
    orchestrator = await _get_orchestrator_or_404(call_id)

    return {
        "call_id": call_id,
        "status": orchestrator.status.value,
        "cadet_id": orchestrator.cadet_id,
        "scenario_id": orchestrator.scenario.id,
        "duration_sec": orchestrator.audit.current_sec,
        "caller_state": orchestrator.caller_state_machine.state.model_dump(),
        "card": orchestrator.card_manager.card.model_dump(),
        "triggers_count": len(orchestrator.audit.triggers),
        "activations_count": len(orchestrator.audit.activations),
        "violations_count": len(orchestrator.all_violations),
    }






@router.delete(
    "/{call_id}",
    summary="Закрыть разбор сессии (удалить из памяти)",
)
async def close_session_review(call_id: str) -> dict:
    """
    Инструктор завершил разбор — сессия удаляется из памяти.
    Работает для любой сессии (активной или завершённой).
    """
    manager = get_session_manager()
    removed = await manager.close_review(call_id)
    if not removed:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Сессия '{call_id}' не найдена",
        )
    logger.info("Сессия %s удалена по запросу инструктора", call_id)
    return {"ok": True, "call_id": call_id}






async def _tts_audio_b64(text: str, panic: int) -> str | None:
    """
    Безопасно синтезирует речь. Возвращает None, если TTS недоступен.
    """
    try:
        tts = get_tts_engine()
        from app.sim112.voice.pipe import VoicePipe
        from app.sim112.voice.stt import get_stt_engine
        pipe = VoicePipe(stt=get_stt_engine(), tts=tts)
        return await pipe.caller_speech_audio_b64(text, panic)
    except Exception as exc:
        logger.warning("TTS не отработал: %s", exc)
        return None


def _get_voice_pipe():
    """Возвращает фасад голосовых движков."""
    from app.sim112.voice.pipe import VoicePipe
    from app.sim112.voice.stt import get_stt_engine
    return VoicePipe(stt=get_stt_engine(), tts=get_tts_engine())


async def _get_orchestrator_or_404(call_id: str) -> CallOrchestrator:
    manager = get_session_manager()
    orchestrator = await manager.get(call_id)
    if orchestrator is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Сессия '{call_id}' не найдена или уже завершена",
        )
    return orchestrator