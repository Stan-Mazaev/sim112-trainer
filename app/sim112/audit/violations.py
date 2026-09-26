"""
Детектор нарушений регламента 112.

Работает детерминированно. Никакой LLM здесь быть не должно —
оценка курсанта обязана быть воспроизводимой.

Три категории проверок:

1. Временные (по таймлайну):
   - LATE_ACTIVATION: служба активирована позже норматива.
   - MISSED_ACTIVATION: служба не активирована до конца звонка.
   - NO_GROUNDING_FIRST_30S: не использовал заземление в первые 30 сек.

2. По карточке вызова:
   - MISSED_CRITICAL_FIELD: критическое поле осталось пустым.
   - MISSED_REQUIRED_FIELD: обязательное поле осталось пустым.

3. По речи курсанта:
   - UNPROFESSIONAL_TONE: грубость, повышение тона.
   - INTERRUPTED_CALLER: перебивание (по коротким репликам курсанта подряд).

Детектор хранит внутреннее состояние (fired violations), чтобы не
фиксировать одну ошибку дважды.
"""

from __future__ import annotations

from typing import Iterable


from app.sim112.caller.state import (
    extract_grounding_phrases,
    extract_unprofessional_phrases,
)
from app.sim112.schemas import (
    CallCard,
    ServiceActivation,
    SeverityLevel,
    TriggerEvent,
    Violation,
    ViolationType,
)






VIOLATION_WEIGHTS: dict[ViolationType, int] = {
    ViolationType.MISSED_CRITICAL_FIELD:     20,
    ViolationType.MISSED_REQUIRED_FIELD:     8,
    ViolationType.LATE_ACTIVATION:           15,
    ViolationType.MISSED_ACTIVATION:         25,
    ViolationType.AIRTIME_OUT_OF_RANGE:      5,
    ViolationType.INTERRUPTED_CALLER:        8,
    ViolationType.UNPROFESSIONAL_TONE:       20,
    ViolationType.INAPPROPRIATE_QUESTION:    5,
    ViolationType.NO_GROUNDING_FIRST_30S:    10,
    ViolationType.CLASSIFICATION_MISMATCH:   25,
    ViolationType.SIGN_MISMATCH:             12,
    ViolationType.MISSED_CALLER_FIO:         5,
    ViolationType.MISSED_CALLER_ROLE:        5,
    ViolationType.MISSED_SERVICE:            30,
    ViolationType.EXTRA_SERVICE:             3,
}






class ViolationDetector:
    """
    Один экземпляр на звонок. Хранит, какие нарушения уже зафиксированы.
    """

    def __init__(self):
        self.fired: set[str] = set()





    def check_trigger_response(
        self,
        trigger: TriggerEvent,
        activations: list[ServiceActivation],
        current_sec: int,
    ) -> list[Violation]:
        """
        Проверяет, успел ли курсант активировать нужные службы после триггера.

        Логика:
        - Для триггера ищем активации каждой ожидаемой службы ПОСЛЕ момента триггера.
        - Если активации нет и прошло больше max_response_sec — фиксируем LATE.
        - Если активации нет и звонок уже длиннее max_response_sec + 30 сек —
          фиксируем MISSED (уже не догнать).
        """
        violations: list[Violation] = []

        for service in trigger.expected_services:
            key = f"{ViolationType.LATE_ACTIVATION}:{trigger.trigger_key}:{service.value}"
            missed_key = f"{ViolationType.MISSED_ACTIVATION}:{trigger.trigger_key}:{service.value}"

            if key in self.fired or missed_key in self.fired:
                continue


            matched = [
                a for a in activations
                if a.service == service and a.activated_at_sec >= trigger.detected_at_sec
            ]

            if matched:
                activation = min(matched, key=lambda a: a.activated_at_sec)
                response_time = activation.activated_at_sec - trigger.detected_at_sec
                if response_time > trigger.max_response_sec:
                    self.fired.add(key)
                    violations.append(Violation(
                        type=ViolationType.LATE_ACTIVATION,
                        severity=trigger.severity,
                        detected_at_sec=activation.activated_at_sec,
                        description=(
                            f"Служба «{_service_ru(service)}» активирована через "
                            f"{response_time} сек после триггера "
                            f"«{trigger.raw_phrase}» (норматив {trigger.max_response_sec} сек)."
                        ),
                        related_trigger=trigger.trigger_key,
                    ))
            else:

                if current_sec - trigger.detected_at_sec > trigger.max_response_sec:
                    self.fired.add(missed_key)
                    violations.append(Violation(
                        type=ViolationType.MISSED_ACTIVATION,
                        severity=SeverityLevel.CRITICAL,
                        detected_at_sec=current_sec,
                        description=(
                            f"Служба «{_service_ru(service)}» НЕ активирована "
                            f"после триггера «{trigger.raw_phrase}». "
                            f"Прошло {current_sec - trigger.detected_at_sec} сек."
                        ),
                        related_trigger=trigger.trigger_key,
                    ))

        return violations

    def check_grounding_usage(
        self,
        elapsed_sec: int,
        dispatcher_texts: list[str],
    ) -> list[Violation]:
        """
        Проверяет, использовал ли курсант заземление в первые 30 секунд.
        Проверка срабатывает один раз на 31-й секунде.
        """
        key = "no_grounding_first_30s"
        if key in self.fired:
            return []
        if elapsed_sec < 30:
            return []


        has_grounding = any(extract_grounding_phrases(t) for t in dispatcher_texts)
        if has_grounding:
            self.fired.add(key)
            return []

        self.fired.add(key)
        return [Violation(
            type=ViolationType.NO_GROUNDING_FIRST_30S,
            severity=SeverityLevel.LOW,
            detected_at_sec=elapsed_sec,
            description=(
                "Курсант не использовал ни одной заземляющей фразы "
                "в первые 30 секунд звонка. Заявитель оставался в панике."
            ),
        )]





    def check_card_fields(
        self,
        card: CallCard,
        required_fields: list[str],
        critical_fields: list[str],
        current_sec: int,
    ) -> list[Violation]:
        """
        Проверяет незаполненные поля карточки. Вызывается по завершении звонка.
        """
        violations: list[Violation] = []
        filled = self._card_filled_fields(card)

        for field in critical_fields:
            key = f"{ViolationType.MISSED_CRITICAL_FIELD}:{field}"
            if key in self.fired:
                continue
            if field not in filled:
                self.fired.add(key)
                violations.append(Violation(
                    type=ViolationType.MISSED_CRITICAL_FIELD,
                    severity=SeverityLevel.HIGH,
                    detected_at_sec=current_sec,
                    description=(
                        f"Критическое поле «{_field_ru(field)}» не заполнено. "
                        f"Без него выезд невозможен."
                    ),
                    related_field=field,
                ))

        for field in required_fields:
            if field in critical_fields:
                continue
            key = f"{ViolationType.MISSED_REQUIRED_FIELD}:{field}"
            if key in self.fired:
                continue
            if field not in filled:
                self.fired.add(key)
                violations.append(Violation(
                    type=ViolationType.MISSED_REQUIRED_FIELD,
                    severity=SeverityLevel.MEDIUM,
                    detected_at_sec=current_sec,
                    description=(
                        f"Обязательное поле «{_field_ru(field)}» не заполнено."
                    ),
                    related_field=field,
                ))

        return violations

    @staticmethod
    def _card_filled_fields(card: CallCard) -> set[str]:
        """Возвращает множество заполненных полей карточки."""
        filled: set[str] = set()

        base_fields = {
            "address": card.address,
            "what_happened": card.what_happened,
            "victims_present": card.victims_present,
            "victims_count": card.victims_count,
            "threat_to_life": card.threat_to_life,
        }
        for name, value in base_fields.items():
            if value is not None and value != "":
                filled.add(name)

        for name, value in card.scenario_fields.items():
            if value is not None and value != "":
                filled.add(name)

        return filled





    def check_dispatcher_tone(
        self,
        dispatcher_text: str,
        at_sec: int,
    ) -> list[Violation]:
        """
        Проверяет реплику курсанта на грубость.
        Каждая реплика проверяется отдельно. Фиксируем первое нарушение.
        """
        key = "unprofessional_tone"
        if key in self.fired:
            return []

        phrases = extract_unprofessional_phrases(dispatcher_text)
        if not phrases:
            return []

        self.fired.add(key)
        return [Violation(
            type=ViolationType.UNPROFESSIONAL_TONE,
            severity=SeverityLevel.HIGH,
            detected_at_sec=at_sec,
            description=(
                f"Некорректные фразы в речи курсанта: "
                f"{', '.join(repr(p) for p in phrases)}. "
                f"Регламент 112 запрещает повышать тон и перебивать заявителя."
            ),
        )]





    def reset(self) -> None:
        self.fired.clear()






_SERVICE_RU = {
    "fire": "Пожарная (МЧС)",
    "ambulance": "Скорая помощь",
    "police": "Полиция",
    "gas": "Аварийная газовая служба",
    "gkh": "ДДС района (ГКХ)",
}


def _service_ru(service) -> str:
    val = service.value if hasattr(service, "value") else str(service)
    return _SERVICE_RU.get(val, val)


_FIELD_RU = {
    "address": "Адрес происшествия",
    "what_happened": "Что случилось",
    "victims_present": "Наличие пострадавших",
    "victims_count": "Количество пострадавших",
    "threat_to_life": "Угроза жизни",
    "floor": "Этаж",
    "entrance": "Подъезд",
    "apartment": "Квартира",
    "what_burning": "Что горит",
    "exit_status": "Возможность выхода",
    "jammed_count": "Количество зажатых",
    "weapon": "Наличие оружия",
}


def _field_ru(field: str) -> str:
    return _FIELD_RU.get(field, field)