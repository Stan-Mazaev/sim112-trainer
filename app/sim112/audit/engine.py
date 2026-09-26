"""
Оркестратор аудита тренажёра.

Единая точка входа для всех проверок. Хранит:
- TriggerDetector — ловит триггерные фразы в речи заявителя.
- ViolationDetector — фиксирует нарушения регламента 112.
- Метрики — считаются на каждом шаге и в конце звонка.

Вызывается из session/orchestrator.py:
- on_step() — после каждой реплики курсанта.
- on_caller_speech() — после каждой реплики заявителя (для триггеров).
- on_service_activation() — при нажатии кнопки службы.
- finalize() — при завершении звонка.

Никакой LLM здесь быть не должно — только детерминированные правила.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.sim112.audit.metrics import (
    compute_airtime_control,
    compute_all_metrics,
    compute_protocol_adherence,
    compute_response_times,
    compute_average_response_time,
)
from app.sim112.audit.triggers import TriggerDetector
from app.sim112.audit.violations import ViolationDetector
from app.sim112.schemas import (
    AirtimeControl,
    CallCard,
    CallerState,
    EmergencyAudit,
    ProtocolAdherence,
    ProtocolAlert,
    Scenario,
    ScenarioId,
    ServiceActivation,
    SeverityLevel,
    TriggerEvent,
    Violation,
    ViolationType,
)
from app.sim112.scenarios.schemas import Expected






@dataclass
class AuditStepResult:
    """
    Что возвращает AuditEngine после обработки одной реплики курсанта.
    """
    protocol_adherence: ProtocolAdherence
    airtime_control: AirtimeControl
    new_violations: list[Violation] = field(default_factory=list)
    new_triggers: list[TriggerEvent] = field(default_factory=list)
    grounding_phrases: list[str] = field(default_factory=list)
    unprofessional_phrases: list[str] = field(default_factory=list)






class AuditEngine:
    """
    Один экземпляр на звонок.

    Курсант ходит через on_step(), заявитель — через on_caller_speech(),
    кнопки служб — через on_service_activation().
    """

    def __init__(self, scenario: Scenario, expected: "Expected | None" = None):
        self.scenario = scenario
        self.expected = expected
        self.trigger_detector = TriggerDetector(scenario.id)
        self.violation_detector = ViolationDetector()


        self.triggers: list[TriggerEvent] = []
        self.activations: list[ServiceActivation] = []
        self.dispatcher_texts: list[str] = []


        self.dispatcher_speech_sec: float = 0.0
        self.caller_speech_sec: float = 0.0


        self.current_sec: int = 0


        self.all_violations: list[Violation] = []





    def on_caller_speech(
        self,
        caller_text: str,
        duration_sec: float,
    ) -> list[TriggerEvent]:
        """
        Вызывается при каждой реплике заявителя.
        - Учитывает время его речи.
        - Детектит триггеры.
        Возвращает список новых триггеров.
        """
        self.caller_speech_sec += duration_sec

        events = self.trigger_detector.detect(caller_text, at_sec=self.current_sec)
        self.triggers.extend(events)
        return events

    def on_dispatcher_speech(
        self,
        dispatcher_text: str,
        duration_sec: float,
    ) -> list[Violation]:
        """
        Вызывается при каждой реплике курсанта.
        - Учитывает время его речи.
        - Проверяет тон на грубость.
        - Проверяет пропуск заземления (на 31-й секунде).
        Возвращает список новых нарушений.
        """
        self.dispatcher_speech_sec += duration_sec
        self.dispatcher_texts.append(dispatcher_text)

        violations: list[Violation] = []


        violations.extend(
            self.violation_detector.check_dispatcher_tone(
                dispatcher_text, at_sec=self.current_sec,
            )
        )


        violations.extend(
            self.violation_detector.check_grounding_usage(
                elapsed_sec=self.current_sec,
                dispatcher_texts=self.dispatcher_texts,
            )
        )


        for trigger in self.triggers:
            violations.extend(
                self.violation_detector.check_trigger_response(
                    trigger=trigger,
                    activations=self.activations,
                    current_sec=self.current_sec,
                )
            )

        self.all_violations.extend(violations)
        return violations

    def on_service_activation(
        self,
        service,
        at_sec: int | None = None,
    ) -> list[Violation]:
        """
        Вызывается при нажатии кнопки службы.
        Проверяет, не просрочена ли активация.
        Возвращает список новых нарушений.
        """
        if at_sec is None:
            at_sec = self.current_sec

        activation = ServiceActivation(service=service, activated_at_sec=at_sec)
        self.activations.append(activation)


        violations: list[Violation] = []
        for trigger in self.triggers:
            violations.extend(
                self.violation_detector.check_trigger_response(
                    trigger=trigger,
                    activations=self.activations,
                    current_sec=at_sec,
                )
            )
        self.all_violations.extend(violations)
        return violations

    def tick(self, seconds: int = 1) -> None:
        """Увеличивает внутренний счётчик времени звонка."""
        self.current_sec += seconds





    def snapshot_metrics(self, card: CallCard) -> AuditStepResult:
        """
        Возвращает текущие метрики для UI.
        Вызывается после каждого шага.
        """
        adherence = compute_protocol_adherence(
            card=card,
            required_fields=self.scenario.required_fields,
            critical_fields=self.scenario.critical_fields,
        )
        airtime = compute_airtime_control(
            dispatcher_speech_sec=self.dispatcher_speech_sec,
            caller_speech_sec=self.caller_speech_sec,
            scenario_id=self.scenario.id,
        )

        return AuditStepResult(
            protocol_adherence=adherence,
            airtime_control=airtime,
        )





    def finalize(
        self,
        card: CallCard,
        caller_state: CallerState,
    ) -> dict[str, Any]:
        """
        Вызывается в конце звонка.
        - Проверяет оставшиеся триггеры (не активированные).
        - Проверяет карточку на пустые поля.
        - Собирает итоговый EmergencyAudit и ProtocolAlert.
        """



        for trigger in self.triggers:
            new_violations = self.violation_detector.check_trigger_response(
                trigger=trigger,
                activations=self.activations,
                current_sec=self.current_sec,
            )
            self.all_violations.extend(new_violations)



        card_violations = self.violation_detector.check_card_fields(
            card=card,
            required_fields=self.scenario.required_fields,
            critical_fields=self.scenario.critical_fields,
            current_sec=self.current_sec,
        )
        self.all_violations.extend(card_violations)


        ekp_violations = self.check_ekp_classification(card)
        for v in ekp_violations:
            self.violation_detector.fired.add(
                f"{v.type}:{v.related_field or 'common'}"
            )


        metrics = compute_all_metrics(
            card=card,
            required_fields=self.scenario.required_fields,
            critical_fields=self.scenario.critical_fields,
            scenario_id=self.scenario.id,
            dispatcher_speech_sec=self.dispatcher_speech_sec,
            caller_speech_sec=self.caller_speech_sec,
            triggers=self.triggers,
            activations=self.activations,
        )


        emergency_audit = EmergencyAudit(
            triggers_detected=list(self.triggers),
            activations=list(self.activations),
            response_times_sec=metrics["response_times_sec"],
            violations=list(self.all_violations),
        )


        protocol_alert = self._build_protocol_alert()

        return {
            "protocol_adherence": metrics["protocol_adherence"],
            "airtime_control": metrics["airtime_control"],
            "response_times_sec": metrics["response_times_sec"],
            "average_response_sec": metrics["average_response_sec"],
            "emergency_audit": emergency_audit,
            "protocol_alert": protocol_alert,
            "caller_state": caller_state,
            "duration_sec": self.current_sec,
            "violations": list(self.all_violations),
        }

    def _collect_violations_snapshot(self) -> list[Violation]:
        """
        Заглушка для сбора нарушений из detector.
        В реальной реализации detector должен уметь отдавать свои накопления.
        """


        return []

    def _build_protocol_alert(self) -> ProtocolAlert:
        """Формирует итоговый alert по речи курсанта."""
        from app.sim112.caller.state import (
            extract_grounding_phrases,
            extract_unprofessional_phrases,
        )

        grounding: list[str] = []
        unprofessional: list[str] = []

        for text in self.dispatcher_texts:
            grounding.extend(extract_grounding_phrases(text))
            unprofessional.extend(extract_unprofessional_phrases(text))


        grounding = list(dict.fromkeys(grounding))
        unprofessional = list(dict.fromkeys(unprofessional))

        return ProtocolAlert(
            has_violations=len(unprofessional) > 0,
            violations=[],
            grounding_phrases_used=grounding,
            unprofessional_phrases=unprofessional,
        )





    def check_ekp_classification(self, card: CallCard) -> list[Violation]:
        """
        Проверяет, правильно ли курсант классифицировал происшествие по ЕКП
        и всех ли служб оповестил.

        Работает только если в оркестратор передан expected.
        Возвращает список новых нарушений.
        """
        if self.expected is None:
            return []

        violations: list[Violation] = []


        if card.classification_id != self.expected.classification_id:
            violations.append(Violation(
                type=ViolationType.CLASSIFICATION_MISMATCH,
                severity=SeverityLevel.HIGH,
                detected_at_sec=self.current_sec,
                description=(
                    f"Неверный итоговый тип. Курсант выбрал "
                    f"'{card.classification_name or '—'}', ожидалось "
                    f"'{self.expected.classification_name}'."
                ),
                related_field="classification_id",
            ))


        exp_signs = self.expected.signs
        sign_mismatches = []
        if exp_signs.sign_l1 and card.sign_l1 != exp_signs.sign_l1:
            sign_mismatches.append(f"признак-1: '{card.sign_l1 or '—'}' вместо '{exp_signs.sign_l1}'")
        if exp_signs.sign_l2 and card.sign_l2 != exp_signs.sign_l2:
            sign_mismatches.append(f"признак-2: '{card.sign_l2 or '—'}' вместо '{exp_signs.sign_l2}'")
        if exp_signs.sign_l3 and card.sign_l3 != exp_signs.sign_l3:
            sign_mismatches.append(f"признак-3: '{card.sign_l3 or '—'}' вместо '{exp_signs.sign_l3}'")

        if sign_mismatches:
            violations.append(Violation(
                type=ViolationType.SIGN_MISMATCH,
                severity=SeverityLevel.MEDIUM,
                detected_at_sec=self.current_sec,
                description="Несовпадение признаков: " + "; ".join(sign_mismatches),
                related_field="signs",
            ))


        expected_set = set(self.expected.services)
        actual_set = set(card.services_activated)

        missed = expected_set - actual_set
        extra = actual_set - expected_set

        if missed:
            violations.append(Violation(
                type=ViolationType.MISSED_SERVICE,
                severity=SeverityLevel.CRITICAL,
                detected_at_sec=self.current_sec,
                description=(
                    f"Не оповещены службы: {', '.join(sorted(missed))}. "
                    f"По сценарию должны быть: {', '.join(sorted(expected_set))}."
                ),
            ))

        if extra:
            violations.append(Violation(
                type=ViolationType.EXTRA_SERVICE,
                severity=SeverityLevel.LOW,
                detected_at_sec=self.current_sec,
                description=f"Избыточное оповещение: {', '.join(sorted(extra))}.",
            ))


        if not card.caller_fio:
            violations.append(Violation(
                type=ViolationType.MISSED_CALLER_FIO,
                severity=SeverityLevel.LOW,
                detected_at_sec=self.current_sec,
                description="Не зафиксировано ФИО заявителя.",
                related_field="caller_fio",
            ))


        if not card.caller_role:
            violations.append(Violation(
                type=ViolationType.MISSED_CALLER_ROLE,
                severity=SeverityLevel.LOW,
                detected_at_sec=self.current_sec,
                description="Не указан статус заявителя (очевидец / участник / родственник).",
                related_field="caller_role",
            ))

        self.all_violations.extend(violations)
        return violations