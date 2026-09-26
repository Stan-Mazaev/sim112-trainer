"""
Стейт-машина ИИ-заявителя.

Ключевая идея: поведение заявителя определяется ДЕТЕРМИНИРОВАННЫМИ правилами,
а не прихотью LLM. LLM (CallerEngine) лишь озвучивает то, что уже решено здесь.

Это даёт:
- Воспроизводимость: одинаковое поведение курсанта → одинаковое поведение заявителя.
- Аттестуемость: изменение состояния можно логировать и приложить к отчёту.
- Отладку: если заявитель ведёт себя странно, видно, какое правило сработало.

Управление идёт через один класс CallerStateMachine, который:
1. Классифицирует реплику курсанта (тип действия).
2. Применяет правила изменения шкал (panic, trust, compliance, cooperation).
3. Обновляет фазу.
4. Открывает/скрывает скрытые факты.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum

from app.sim112.schemas import CallerPhase, CallerState






class DispatcherAction(str, Enum):
    """Тип действия, совершённого курсантом в реплике."""
    GROUNDING = "grounding"
    RELEVANT_QUESTION = "relevant_question"
    IRRELEVANT_QUESTION = "irrelevant_question"
    INSTRUCTION = "instruction"
    REPEATED_QUESTION = "repeated_question"
    UNPROFESSIONAL = "unprofessional"
    SILENCE = "silence"
    REPEAT_BACK = "repeat_back"






_WORD_START = r"(?<![а-яёa-z])"
_WORD_END = r"(?![а-яёa-z])"


_GROUNDING_PATTERNS = [
    re.compile(_WORD_START + r"я\s+вас\s+слышу" + _WORD_END, re.IGNORECASE),
    re.compile(_WORD_START + r"помощь\s+уже\s+(едет|выехала|в\s+пути)" + _WORD_END, re.IGNORECASE),
    re.compile(_WORD_START + r"я\s+рядом" + _WORD_END, re.IGNORECASE),
    re.compile(_WORD_START + r"мы\s+(вместе|справимся)" + _WORD_END, re.IGNORECASE),
    re.compile(_WORD_START + r"дышите\s+(глубже|спокойнее|ровно)" + _WORD_END, re.IGNORECASE),
    re.compile(_WORD_START + r"вы\s+справитесь" + _WORD_END, re.IGNORECASE),
    re.compile(_WORD_START + r"я\s+помогу\s+вам" + _WORD_END, re.IGNORECASE),
    re.compile(_WORD_START + r"успокойтесь\s*,?\s*я\s+вас\s+слушаю" + _WORD_END, re.IGNORECASE),
]

_UNPROFESSIONAL_PATTERNS = [
    re.compile(_WORD_START + r"не\s+орите" + _WORD_END, re.IGNORECASE),
    re.compile(_WORD_START + r"успокойтесь\s+уже" + _WORD_END, re.IGNORECASE),
    re.compile(_WORD_START + r"ждите\s+и\s+не\s+мешайте" + _WORD_END, re.IGNORECASE),
    re.compile(_WORD_START + r"это\s+не\s+моя\s+проблема" + _WORD_END, re.IGNORECASE),
    re.compile(_WORD_START + r"вы\s+мне\s+надоели" + _WORD_END, re.IGNORECASE),
    re.compile(_WORD_START + r"я\s+не\s+обязан" + _WORD_END, re.IGNORECASE),
    re.compile(_WORD_START + r"заткнитесь" + _WORD_END, re.IGNORECASE),
    re.compile(_WORD_START + r"не\s+кричите" + _WORD_END, re.IGNORECASE),
]


_INSTRUCTION_PATTERNS = [
    re.compile(_WORD_START + r"(откройте|закройте|выйдите|зайдите|положите|встаньте|сядьте|нажмите|наберите)" + _WORD_END, re.IGNORECASE),
    re.compile(_WORD_START + r"(намочите|приложите|переверните|поднимите|опустите)" + _WORD_END, re.IGNORECASE),
    re.compile(_WORD_START + r"(сделайте|повторите|оставайтесь|держитесь|не\s+двигайтесь)" + _WORD_END, re.IGNORECASE),
    re.compile(_WORD_START + r"(бегите|уходите|спрячьтесь|закройтесь|отойдите|присядьте)" + _WORD_END, re.IGNORECASE),
]


_INFO_REQUEST_IMPERATIVES = [
    re.compile(_WORD_START + r"(назовите|назови|скажите|скажи|сообщите|уточните|укажите|опишите|расскажите)" + _WORD_END, re.IGNORECASE),
]


def classify_dispatcher_action(
    text: str,
    already_asked: set[str],
    relevant_keywords: set[str],
) -> DispatcherAction:
    """
    Классифицирует реплику курсанта по типу действия.
    Порядок проверок: от критичного к мягкому.
    """
    if not text or not text.strip():
        return DispatcherAction.SILENCE

    lowered = text.lower()


    for pat in _UNPROFESSIONAL_PATTERNS:
        if pat.search(lowered):
            return DispatcherAction.UNPROFESSIONAL


    for pat in _GROUNDING_PATTERNS:
        if pat.search(lowered):
            return DispatcherAction.GROUNDING


    normalized = lowered.strip(" ?!.,")
    if normalized in already_asked:
        return DispatcherAction.REPEATED_QUESTION








    has_question_mark = "?" in text
    has_question_word = any(
        w in lowered for w in ("что", "где", "когда", "сколько", "как", "кто", "чем", "почему")
    )
    has_info_imperative = any(pat.search(lowered) for pat in _INFO_REQUEST_IMPERATIVES)


    has_scenario_keyword = any(kw in lowered for kw in relevant_keywords)



    question_starters = (
        "есть ли", "есть пострадав", "есть ранен", "есть люди", "есть дет",
        "сколько людей", "сколько пострадав", "сколько человек",
        "кто там", "кто пострадал", "что там", "что видно",
        "расскажите", "уточните", "опишите",
    )
    has_question_starter = any(s in lowered for s in question_starters)

    if has_question_mark or has_question_word or has_info_imperative \
            or has_scenario_keyword or has_question_starter:
        if has_scenario_keyword or has_question_starter:
            return DispatcherAction.RELEVANT_QUESTION
        return DispatcherAction.IRRELEVANT_QUESTION


    for pat in _INSTRUCTION_PATTERNS:
        if pat.search(lowered):
            return DispatcherAction.INSTRUCTION


    return DispatcherAction.REPEAT_BACK






@dataclass(frozen=True)
class StateDelta:
    """Изменения шкал от одного действия курсанта."""
    panic: int = 0
    trust: int = 0
    compliance: int = 0
    cooperation: int = 0
    reveals_fact: bool = False



DELTA_TABLE: dict[DispatcherAction, StateDelta] = {
    DispatcherAction.GROUNDING:          StateDelta(panic=-10, trust=+5,  compliance=+5,  cooperation=+3),
    DispatcherAction.RELEVANT_QUESTION:  StateDelta(panic=-3,  trust=+2,  compliance=+2,  cooperation=+15, reveals_fact=True),
    DispatcherAction.IRRELEVANT_QUESTION: StateDelta(panic=+3, trust=-2,  compliance=0,   cooperation=0),
    DispatcherAction.INSTRUCTION:        StateDelta(panic=-2,  trust=+1,  compliance=+8,  cooperation=+1, reveals_fact=True),
    DispatcherAction.REPEATED_QUESTION:  StateDelta(panic=+5,  trust=-4,  compliance=0,   cooperation=-2),
    DispatcherAction.UNPROFESSIONAL:     StateDelta(panic=+15, trust=-15, compliance=-10, cooperation=-10),
    DispatcherAction.SILENCE:            StateDelta(panic=+8,  trust=-3,  compliance=0,   cooperation=0),
    DispatcherAction.REPEAT_BACK:        StateDelta(panic=0,   trust=+1,  compliance=0,   cooperation=0),
}






def determine_phase(
    current_phase: CallerPhase,
    panic: int,
    trust: int,
    call_duration_sec: int,
) -> CallerPhase:
    """Определяет фазу по текущим метрикам и времени звонка."""

    if trust < 20 and current_phase in (CallerPhase.COORDINATION, CallerPhase.RESOLUTION):
        return CallerPhase.PANIC


    if panic < 15 and trust > 60:
        return CallerPhase.RESOLUTION


    if panic < 40 and trust > 40:
        return CallerPhase.COORDINATION


    if call_duration_sec < 30:
        return CallerPhase.SHOCK


    if panic >= 60:
        return CallerPhase.PANIC

    return CallerPhase.COORDINATION






class CallerStateMachine:
    """
    Управляет состоянием заявителя на протяжении звонка.

    Один экземпляр на один звонок. Хранит историю заданных вопросов,
    чтобы детектить повторы.
    """

    def __init__(self, initial_state: CallerState, relevant_keywords: set[str] | None = None):
        self.state = initial_state
        self._asked_questions: set[str] = set()
        self._relevant_keywords = relevant_keywords or set()

    def apply_dispatcher_turn(
        self,
        dispatcher_text: str,
        duration_delta_sec: float,
    ) -> tuple[DispatcherAction, StateDelta]:
        """
        Применяет реплику курсанта к состоянию заявителя.

        Возвращает: (действие, дельта) — для логирования в таймлайн.
        """
        action = classify_dispatcher_action(
            dispatcher_text,
            self._asked_questions,
            self._relevant_keywords,
        )


        normalized = dispatcher_text.lower().strip(" ?!.,")
        if action in (DispatcherAction.RELEVANT_QUESTION, DispatcherAction.IRRELEVANT_QUESTION):
            self._asked_questions.add(normalized)

        delta = DELTA_TABLE[action]


        self.state.panic = _clamp(self.state.panic + delta.panic)
        self.state.trust = _clamp(self.state.trust + delta.trust)
        self.state.compliance = _clamp(self.state.compliance + delta.compliance)
        self.state.cooperation = _clamp(self.state.cooperation + delta.cooperation)


        self.state.call_duration_sec += int(duration_delta_sec)


        self.state.phase = determine_phase(
            self.state.phase,
            self.state.panic,
            self.state.trust,
            self.state.call_duration_sec,
        )

        return action, delta

    def reveal_facts(self, fact_keys: list[str]) -> None:
        """Отмечает, что заявитель озвучил данные факты."""
        for key in fact_keys:
            if key in self.state.hidden_facts:
                self.state.revealed_facts.add(key)

    def can_reveal(self, fact_key: str) -> bool:
        """
        Может ли заявитель сейчас озвучить данный факт.

        Логика:
        - Если факт в refused_topics — не может.
        - Если заявитель в фазе SHOCK и факт требует связной речи (например, 'адрес') — не может.
        - Иначе — может, если cooperation достаточно высок.
        """
        if fact_key in self.state.refused_topics:
            return False
        if fact_key not in self.state.hidden_facts:
            return False


        if fact_key in ("address", "full_address") and self.state.cooperation < 30:
            return False


        return self.state.cooperation >= 20

    def unrevealed_facts(self) -> dict:
        """Возвращает факты, которые заявитель ещё не озвучил."""
        return {
            k: v for k, v in self.state.hidden_facts.items()
            if k not in self.state.revealed_facts
        }






def _clamp(value: int, lo: int = 0, hi: int = 100) -> int:
    return max(lo, min(hi, value))


def is_grounding_phrase(text: str) -> bool:
    """Открытая функция для использования в AuditEngine."""
    lowered = text.lower()
    return any(pat.search(lowered) for pat in _GROUNDING_PATTERNS)


def is_unprofessional_phrase(text: str) -> bool:
    """Открытая функция для использования в AuditEngine."""
    lowered = text.lower()
    return any(pat.search(lowered) for pat in _UNPROFESSIONAL_PATTERNS)


def extract_grounding_phrases(text: str) -> list[str]:
    """Возвращает найденные заземляющие фразы — для отчёта."""
    found = []
    lowered = text.lower()
    for pat in _GROUNDING_PATTERNS:
        m = pat.search(lowered)
        if m:
            found.append(m.group(0))
    return found


def extract_unprofessional_phrases(text: str) -> list[str]:
    """Возвращает найденные непрофессиональные фразы — для отчёта."""
    found = []
    lowered = text.lower()
    for pat in _UNPROFESSIONAL_PATTERNS:
        m = pat.search(lowered)
        if m:
            found.append(m.group(0))
    return found