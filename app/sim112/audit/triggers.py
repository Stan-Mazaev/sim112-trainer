"""
Матрица экстренных триггеров 112.

Когда заявитель произносит определённую фразу (например, «ребёнок не дышит»),
AuditEngine фиксирует это событие и запускает таймер. Курсант обязан
активировать соответствующую службу в течение норматива (max_response_sec).

Если не успел — нарушение LATE_ACTIVATION.
Если вообще не активировал — MISSED_ACTIVATION (критичнее).

НОРМАТИВЫ ВЗЯТЫ из регламентов 112 (приблизительно, для тренажёра):
- Ребёнок не дышит, человек без сознания → скорая за 10 сек.
- Открытое пламя, запах газа, пожар → МЧС/газ за 15 сек.
- Оружие, насилие → полиция за 10 сек.
- ДТП с зажатыми → все три службы за 15 сек.
"""

from __future__ import annotations

import re
from typing import Iterable

from app.sim112.schemas import (
    ScenarioId,
    ServiceType,
    SeverityLevel,
    TriggerEvent,
)






_WORD_START = r"(?<![а-яёa-z])"
_WORD_END = r"(?![а-яёa-z])"






class TriggerRule:
    """
    Одно правило: паттерн → служба → норматив.
    """

    def __init__(
        self,
        key: str,
        patterns: list[str],
        services: list[ServiceType],
        max_response_sec: int,
        severity: SeverityLevel,
        scenario_ids: set[ScenarioId] | None = None,
    ):
        self.key = key
        self.patterns = [re.compile(p, re.IGNORECASE) for p in patterns]
        self.services = services
        self.max_response_sec = max_response_sec
        self.severity = severity

        self.scenario_ids = scenario_ids

    def matches(self, text: str, scenario_id: ScenarioId) -> str | None:
        """
        Проверяет, сработал ли триггер на данной реплике.
        Возвращает саму фразу (raw_phrase) или None.
        """
        if self.scenario_ids is not None and scenario_id not in self.scenario_ids:
            return None
        for pat in self.patterns:
            m = pat.search(text)
            if m:
                return m.group(0)
        return None






TRIGGER_RULES: list[TriggerRule] = [



    TriggerRule(
        key="child_not_breathing",
        patterns=[
            _WORD_START + r"ребенок\s+не\s+дышит" + _WORD_END,
            _WORD_START + r"ребёнок\s+не\s+дышит" + _WORD_END,
            _WORD_START + r"ребенку?\s+плохо" + _WORD_END,
            _WORD_START + r"малыш\s+не\s+дышит" + _WORD_END,
        ],
        services=[ServiceType.AMBULANCE],
        max_response_sec=10,
        severity=SeverityLevel.HIGH,
    ),

    TriggerRule(
        key="person_unconscious",
        patterns=[
            _WORD_START + r"без\s+сознани",
            _WORD_START + r"не\s+дышит" + _WORD_END,
            _WORD_START + r"не\s+приходит\s+в\s+себя" + _WORD_END,
            _WORD_START + r"потерял\s+сознани",
            _WORD_START + r"потеряла\s+сознани",
        ],
        services=[ServiceType.AMBULANCE],
        max_response_sec=10,
        severity=SeverityLevel.HIGH,
    ),

    TriggerRule(
        key="severe_bleeding",
        patterns=[
            _WORD_START + r"кров(ь|отечение|ью)" + _WORD_END,
            _WORD_START + r"хлещет\s+кровь" + _WORD_END,
            _WORD_START + r"много\s+крови" + _WORD_END,
        ],
        services=[ServiceType.AMBULANCE],
        max_response_sec=15,
        severity=SeverityLevel.MEDIUM,
    ),

    TriggerRule(
        key="heart_problem",
        patterns=[
            _WORD_START + r"сердечный\s+приступ" + _WORD_END,
            _WORD_START + r"инфаркт" + _WORD_END,
            _WORD_START + r"сердце" + _WORD_END + r".*" + _WORD_START + r"(остановилось|болит\s+сильно)" + _WORD_END,
        ],
        services=[ServiceType.AMBULANCE],
        max_response_sec=10,
        severity=SeverityLevel.HIGH,
    ),



    TriggerRule(
        key="open_flame",
        patterns=[
            _WORD_START + r"открыто[его]\s+пламя" + _WORD_END,
            _WORD_START + r"всё\s+горит" + _WORD_END,
            _WORD_START + r"все\s+горит" + _WORD_END,
            _WORD_START + r"огн(ем|онь)" + _WORD_END + r".*" + _WORD_START + r"охватило" + _WORD_END,
        ],
        services=[ServiceType.FIRE],
        max_response_sec=15,
        severity=SeverityLevel.HIGH,
    ),

    TriggerRule(
        key="fire_in_apartment",
        patterns=[
            _WORD_START + r"пожар" + _WORD_END,
            _WORD_START + r"горит\s+(квартира|дом|кухня|комната)" + _WORD_END,
            _WORD_START + r"дым\s+везде" + _WORD_END,
            _WORD_START + r"всё\s+в\s+дыму" + _WORD_END,
        ],
        services=[ServiceType.FIRE],
        max_response_sec=15,
        severity=SeverityLevel.HIGH,
    ),

    TriggerRule(
        key="gas_smell",
        patterns=[
            _WORD_START + r"запах\s+газа" + _WORD_END,
            _WORD_START + r"пахнет\s+газом" + _WORD_END,
            _WORD_START + r"газом\s+пахнет" + _WORD_END,
            _WORD_START + r"утечка\s+газа" + _WORD_END,
        ],
        services=[ServiceType.GAS],
        max_response_sec=15,
        severity=SeverityLevel.HIGH,
    ),



    TriggerRule(
        key="armed_person",
        patterns=[
            _WORD_START + r"человек\s+с\s+оружием" + _WORD_END,
            _WORD_START + r"вооружен",
            _WORD_START + r"с\s+пистолетом" + _WORD_END,
            _WORD_START + r"с\s+ножом" + _WORD_END,
            _WORD_START + r"с\s+ружь[её]м" + _WORD_END,
        ],
        services=[ServiceType.POLICE],
        max_response_sec=10,
        severity=SeverityLevel.HIGH,
    ),

    TriggerRule(
        key="robbery",
        patterns=[
            _WORD_START + r"ограблен",
            _WORD_START + r"грабител",
            _WORD_START + r"ворвал(ись|ся)" + _WORD_END,
            _WORD_START + r"влом(ились|ился)" + _WORD_END,
        ],
        services=[ServiceType.POLICE],
        max_response_sec=15,
        severity=SeverityLevel.HIGH,
    ),

    TriggerRule(
        key="violence_against_person",
        patterns=[
            _WORD_START + r"убива(ю|ет|ют)" + _WORD_END,
            _WORD_START + r"избива(ю|ет|ют)" + _WORD_END,
            _WORD_START + r"напад(ают|ение|ает)" + _WORD_END,
        ],
        services=[ServiceType.POLICE, ServiceType.AMBULANCE],
        max_response_sec=10,
        severity=SeverityLevel.HIGH,
    ),



    TriggerRule(
        key="accident_jammed",
        patterns=[
            _WORD_START + r"зажат",
            _WORD_START + r"зажало" + _WORD_END,
            _WORD_START + r"в\s+машине\s+люди" + _WORD_END,
            _WORD_START + r"не\s+может\s+выбраться" + _WORD_END,
        ],
        services=[ServiceType.FIRE, ServiceType.AMBULANCE, ServiceType.POLICE],
        max_response_sec=15,
        severity=SeverityLevel.HIGH,
    ),

    TriggerRule(
        key="accident_general",
        patterns=[
            _WORD_START + r"авари[яю]" + _WORD_END,
            _WORD_START + r"ДТП" + _WORD_END,
            _WORD_START + r"столкновение" + _WORD_END,
            _WORD_START + r"машины\s+столкнулись" + _WORD_END,
        ],
        services=[ServiceType.AMBULANCE, ServiceType.POLICE],
        max_response_sec=15,
        severity=SeverityLevel.MEDIUM,
    ),



    TriggerRule(
        key="child_in_danger",
        patterns=[
            _WORD_START + r"ребен(ок|ку)\s+(в\s+опасности|в\s+огне|под\s+завалом)" + _WORD_END,
            _WORD_START + r"ребён(ок|ку)\s+(в\s+опасности|в\s+огне)" + _WORD_END,
            _WORD_START + r"дети\s+внутри" + _WORD_END,
            _WORD_START + r"дети\s+в\s+квартире" + _WORD_END,
        ],
        services=[ServiceType.FIRE, ServiceType.AMBULANCE],
        max_response_sec=15,
        severity=SeverityLevel.HIGH,
    ),

    TriggerRule(
        key="drowning",
        patterns=[
            _WORD_START + r"тонет" + _WORD_END,
            _WORD_START + r"утопает" + _WORD_END,
            _WORD_START + r"в\s+воде" + _WORD_END + r".*" + _WORD_START + r"человек" + _WORD_END,
        ],
        services=[ServiceType.AMBULANCE],
        max_response_sec=15,
        severity=SeverityLevel.HIGH,
    ),
]






class TriggerDetector:
    """
    Детектор триггеров в репликах заявителя.

    Хранит историю — каждый триггер срабатывает один раз за звонок.
    Если заявитель повторил фразу — не считаем повторно.
    """

    def __init__(self, scenario_id: ScenarioId):
        self.scenario_id = scenario_id
        self.fired: set[str] = set()

    def detect(self, text: str, at_sec: int) -> list[TriggerEvent]:
        """
        Находит в тексте все сработавшие триггеры.
        Возвращает список новых (ещё не сработавших ранее) TriggerEvent.

        Дедупликация:
        - Если на одной реплике совпали пересекающиеся правила (одна фраза
          содержится в другой), в события попадает только специфичное (длинная фраза).
        - НО помечаем как fired ОБА правила — чтобы на следующей реплике
          вложенное правило не сработало повторно на той же фразе.
        """
        candidates: list[tuple[TriggerRule, str]] = []
        for rule in TRIGGER_RULES:
            if rule.key in self.fired:
                continue
            raw = rule.matches(text, self.scenario_id)
            if raw is None:
                continue
            candidates.append((rule, raw))

        if not candidates:
            return []


        filtered: list[tuple[TriggerRule, str]] = []
        for rule, raw in candidates:
            is_substring_of_other = any(
                other_raw != raw
                and raw.lower() in other_raw.lower()
                and len(other_raw) > len(raw)
                for _, other_raw in candidates
            )
            if not is_substring_of_other:
                filtered.append((rule, raw))



        for rule, _raw in candidates:
            self.fired.add(rule.key)

        events: list[TriggerEvent] = []
        for rule, raw in filtered:
            events.append(
                TriggerEvent(
                    trigger_key=rule.key,
                    raw_phrase=raw,
                    detected_at_sec=at_sec,
                    expected_services=rule.services,
                    max_response_sec=rule.max_response_sec,
                    severity=rule.severity,
                )
            )
        return events

    def reset(self) -> None:
        self.fired.clear()






def get_expected_triggers(scenario_id: ScenarioId) -> list[TriggerRule]:
    """
    Возвращает список триггеров, которые МОГУТ сработать в сценарии.
    Используется инструктором для отображения «что должно было быть».
    """
    return [
        rule for rule in TRIGGER_RULES
        if rule.scenario_ids is None or scenario_id in rule.scenario_ids
    ]