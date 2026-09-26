"""
Оркестратор звонка.

Держит вместе:
- CallerStateMachine + CallerEngine — заявитель.
- AuditEngine — аудит и метрики.
- CardManager — карточка вызова.
- EventBus — таймлайн для инструктора.

Один экземпляр на один звонок. Хранится в памяти процесса, сериализуется
в БД (session_state) батч-очередью раз в 500 мс.
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any
from uuid import uuid4

from app.sim112.audit.engine import AuditEngine
from app.sim112.caller.engine import CallerEngine, get_caller_engine
from app.sim112.caller.prompts import get_opening_line
from app.sim112.caller.state import CallerStateMachine
from app.sim112.schemas import (
    CallCard,
    CadetTurnResult,
    CallerState,
    CallerTurn,
    DifficultyLevel,
    EventType,
    Scenario,
    ScenarioId,
    ServiceActivation,
    ServiceType,
    SessionStatus,
    Violation,
)
from app.sim112.scenarios.schemas import Expected
from app.sim112.session.card import CardManager
from app.sim112.session.events import EventBus



DEFAULT_DISPATCHER_TURN_SEC = 3.0
DEFAULT_CALLER_TURN_SEC = 3.0


class CallOrchestrator:
    """
    Управляет одной сессией звонка от начала до конца.

    Жизненный цикл:
    1. start() — создать сессию, получить opening_line заявителя.
    2. step() — обработать реплику курсанта (текст после STT).
    3. activate_service() — зафиксировать активацию службы.
    4. update_card() — обновить поле карточки.
    5. end() — завершить звонок, получить финальные метрики.
    """

    def __init__(
        self,
        cadet_id: int,
        scenario: Scenario,
        difficulty: DifficultyLevel = DifficultyLevel.NORMAL,
        expected: Expected | None = None,
    ):
        self.call_id = str(uuid4())
        self.cadet_id = cadet_id
        self.scenario = scenario
        self.difficulty = difficulty


        initial_state = self._initial_state_for_difficulty(scenario, difficulty)
        self.caller_state_machine = CallerStateMachine(
            initial_state=initial_state,
            relevant_keywords=self._keywords_for_scenario(scenario.id),
        )
        self.caller_engine: CallerEngine = get_caller_engine()
        self.caller_engine.initialize_for_scenario(scenario)


        self.audit = AuditEngine(scenario, expected=expected)


        self.card_manager = CardManager(scenario_fields=scenario.required_fields)


        self.events = EventBus()


        self.history: list[dict[str, Any]] = []


        self.status = SessionStatus.ACTIVE
        self.started_at = datetime.utcnow()
        self.ended_at: datetime | None = None


        self.all_violations: list[Violation] = []


        self.expected = expected
        self.cadet_name: str | None = None


        self.final_data: dict[str, Any] | None = None





    async def start(self) -> dict[str, Any]:
        """
        Инициализация звонка. Возвращает opening_line заявителя.
        Не использует LLM — берёт готовую фразу из сценария.
        """
        opening = get_opening_line(self.scenario)


        self.audit.on_caller_speech(opening, duration_sec=DEFAULT_CALLER_TURN_SEC)
        self.history.append({"role": "caller", "text": opening})


        await self.events.emit(
            EventType.CALL_STARTED,
            payload={
                "call_id": self.call_id,
                "cadet_id": self.cadet_id,
                "scenario": self.scenario.title or str(self.scenario.id),
            },
            at_sec=0,
        )
        await self.events.emit(
            EventType.CALLER_SPEECH,
            payload={"text": opening},
            at_sec=0,
        )

        return {
            "call_id": self.call_id,
            "opening_line": opening,
            "caller_state": self.caller_state_machine.state.model_dump(),
        }





    async def step(
        self,
        dispatcher_text: str,
        duration_sec: float = DEFAULT_DISPATCHER_TURN_SEC,
    ) -> CadetTurnResult:
        """
        Обрабатывает одну реплику курсанта.
        Возвращает полный результат для UI.
        """
        if self.status != SessionStatus.ACTIVE:
            raise RuntimeError(f"Звонок не активен: {self.status}")


        dispatcher_sec = int(self.audit.current_sec)
        new_violations_from_speech = self.audit.on_dispatcher_speech(
            dispatcher_text,
            duration_sec=duration_sec,
        )


        await self.events.emit(
            EventType.DISPATCHER_SPEECH,
            payload={"text": dispatcher_text, "duration_sec": duration_sec},
            at_sec=dispatcher_sec,
        )
        for violation in new_violations_from_speech:
            await self.events.emit(
                EventType.VIOLATION_DETECTED,
                payload={
                    "type": violation.type.value,
                    "severity": int(violation.severity),
                    "description": violation.description,
                },
                at_sec=violation.detected_at_sec,
            )


        self.history.append({"role": "dispatcher", "text": dispatcher_text})


        caller_turn, action, delta = await self.caller_engine.respond(
            state_machine=self.caller_state_machine,
            scenario=self.scenario,
            dispatcher_text=dispatcher_text,
            history=self.history,
            duration_sec=duration_sec,
        )


        self.audit.tick(int(duration_sec) + int(DEFAULT_CALLER_TURN_SEC))


        new_triggers = self.audit.on_caller_speech(
            caller_turn.text,
            duration_sec=DEFAULT_CALLER_TURN_SEC,
        )


        await self.events.emit(
            EventType.CALLER_SPEECH,
            payload={"text": caller_turn.text, "action": action.value},
            at_sec=self.audit.current_sec,
        )
        for trigger in new_triggers:
            await self.events.emit(
                EventType.TRIGGER_DETECTED,
                payload={
                    "key": trigger.trigger_key,
                    "phrase": trigger.raw_phrase,
                    "expected_services": [s.value for s in trigger.expected_services],
                    "max_response_sec": trigger.max_response_sec,
                },
                at_sec=trigger.detected_at_sec,
            )


        self.history.append({"role": "caller", "text": caller_turn.text})


        trigger_violations = []
        for trigger in new_triggers:
            trigger_violations.extend(
                self.audit.violation_detector.check_trigger_response(
                    trigger=trigger,
                    activations=self.audit.activations,
                    current_sec=self.audit.current_sec,
                )
            )
        self.all_violations.extend(trigger_violations)


        metrics_snapshot = self.audit.snapshot_metrics(self.card_manager.card)


        return CadetTurnResult(
            caller_response_text=caller_turn.text,
            caller_state=self.caller_state_machine.state,
            protocol_adherence=metrics_snapshot.protocol_adherence,
            airtime_control=metrics_snapshot.airtime_control,
            panic_index=self.caller_state_machine.state.panic,
            compliance_index=self.caller_state_machine.state.compliance,
            trust_index=self.caller_state_machine.state.trust,
            emergency_audit=self._build_emergency_audit_snapshot(),
            protocol_alert=self.audit._build_protocol_alert(),
        )





    async def update_card(self, field: str, value: Any) -> dict[str, Any]:
        """Обновляет поле карточки и возвращает актуальные метрики."""
        accepted = self.card_manager.update(field, value)

        if accepted:
            await self.events.emit(
                EventType.CARD_FIELD_UPDATED,
                payload={"field": field, "value": value},
                at_sec=self.audit.current_sec,
            )

        snapshot = self.audit.snapshot_metrics(self.card_manager.card)
        return {
            "accepted": accepted,
            "card": self.card_manager.card.model_dump(),
            "protocol_adherence": snapshot.protocol_adherence,
        }





    async def activate_service(self, service: ServiceType) -> dict[str, Any]:
        """Курсант нажал кнопку службы."""
        at_sec = self.audit.current_sec
        violations = self.audit.on_service_activation(service, at_sec=at_sec)


        svc_value = service.value if hasattr(service, "value") else str(service)
        if svc_value not in self.card_manager.card.services_activated:
            self.card_manager.card.services_activated.append(svc_value)

        await self.events.emit(
            EventType.SERVICE_ACTIVATED,
            payload={"service": service.value},
            at_sec=at_sec,
        )
        for violation in violations:
            await self.events.emit(
                EventType.VIOLATION_DETECTED,
                payload={
                    "type": violation.type.value,
                    "severity": int(violation.severity),
                    "description": violation.description,
                },
                at_sec=violation.detected_at_sec,
            )

        return {
            "activation": {"service": service.value, "at_sec": at_sec},
            "new_violations": [v.model_dump() for v in violations],
        }





    async def end(self, reason: str = "completed") -> dict[str, Any]:
        """
        Завершает звонок, финализирует аудит, рассылает нарушения инструктору.

        Единый источник нарушений — emergency_audit.violations (то же,
        что читает модалка отчёта). Раньше использовался orchestrator.all_violations,
        из-за чего список нарушений в панели инструктора и в модалке расходился,
        и оценка считалась не по тем данным.
        """
        self.status = SessionStatus.COMPLETED
        self.ended_at = datetime.utcnow()


        final = self.audit.finalize(
            card=self.card_manager.card,
            caller_state=self.caller_state_machine.state,
        )




        emergency_audit = final.get("emergency_audit")

        if emergency_audit is None:
            final["violations"] = list(self.all_violations)
        elif isinstance(emergency_audit, dict):
            final["violations"] = list(emergency_audit.get("violations") or [])
        else:
            final["violations"] = list(getattr(emergency_audit, "violations", []) or [])

        final["timeline"] = self.events.timeline()
        final["reason"] = reason
        final["call_id"] = self.call_id
        final["cadet_id"] = self.cadet_id
        final["scenario_id"] = self.scenario.id
        final["scenario_title"] = self.scenario.title
        final["cadet_name"] = self.cadet_name
        final["expected"] = (
            self.expected.model_dump() if self.expected is not None else None
        )



        for v in final["violations"]:
            await self.events.emit(
                EventType.VIOLATION_DETECTED,
                payload={
                    "type": v.type.value if hasattr(v.type, "value") else str(v.type),
                    "severity": int(v.severity) if hasattr(v.severity, "value") else int(v.severity),
                    "description": v.description,
                },
                at_sec=v.detected_at_sec,
            )

        await self.events.emit(
            EventType.CALL_ENDED,
            payload={
                "reason": reason,
                "violations_count": len(final["violations"]),
            },
            at_sec=self.audit.current_sec,
        )

        self.final_data = final
        return final





    @staticmethod
    def _initial_state_for_difficulty(
        scenario: Scenario,
        difficulty: DifficultyLevel,
    ) -> CallerState:
        """Корректирует стартовое состояние по уровню сложности."""
        base = scenario.initial_caller_state.model_copy(deep=True)

        if difficulty == DifficultyLevel.NOVICE:
            base.panic = max(30, base.panic - 20)
            base.cooperation = min(100, base.cooperation + 20)
            base.trust = min(100, base.trust + 10)
        elif difficulty == DifficultyLevel.EXTREME:
            base.panic = min(100, base.panic + 15)
            base.cooperation = max(0, base.cooperation - 15)
            base.trust = max(0, base.trust - 10)


        if scenario.hidden_facts_template:
            base.hidden_facts = dict(scenario.hidden_facts_template)

        return base

    @staticmethod
    def _keywords_for_scenario(scenario_id: ScenarioId) -> set[str]:
        """Ключевые слова, по которым классификатор понимает, что вопрос релевантный."""
        mapping = {
            ScenarioId.FIRE_APARTMENT: {
                "адрес", "улиц", "дом", "этаж", "подъезд", "квартир",
                "горит", "гори", "пожар", "дым", "огн",
                "люди", "дет", "пострадав", "ранен", "жертв",
                "выход", "эвакуац", "что случил", "что произошл", "что горит",
            },
            ScenarioId.FIRE_HIGHRISE: {
                "адрес", "улиц", "дом", "этаж", "подъезд", "лифт", "лестниц",
                "горит", "пожар", "дым", "огн",
                "люди", "дет", "пострадав", "ранен",
                "выход", "эвакуац", "что горит",
            },
            ScenarioId.ACCIDENT_JAMMED: {
                "адрес", "мест", "улиц", "перекрёсток", "перекресток", "машин",
                "зажат", "заблокирован", "пострадав", "ранен", "люди", "скор",
                "что случил", "что произошл", "сколько",
            },
            ScenarioId.MEDICAL_UNCONSCIOUS: {
                "адрес", "улиц", "дом", "дышит", "дыхани", "сознани",
                "возраст", "лет", "болезн", "аллерг",
                "что случил", "что произошл", "кто", "когда", "пострадав",
            },
            ScenarioId.CRIME_ROBBERY: {
                "адрес", "мест", "оруж", "сколько", "где вы", "прячет",
                "выход", "тихо", "преступ", "грабител", "что случил",
            },
            ScenarioId.GAS_LEAK: {
                "адрес", "улиц", "дом", "квартир", "запах", "газ",
                "откуд", "источник", "что случил", "где",
            },
        }
        return mapping.get(scenario_id, set())

    def _build_emergency_audit_snapshot(self):
        """Быстрый снимок EmergencyAudit для UI (на каждом шаге)."""
        from app.sim112.schemas import EmergencyAudit
        from app.sim112.audit.metrics import compute_response_times
        return EmergencyAudit(
            triggers_detected=list(self.audit.triggers),
            activations=list(self.audit.activations),
            response_times_sec=compute_response_times(
                self.audit.triggers,
                self.audit.activations,
            ),
            violations=list(self.all_violations),
        )