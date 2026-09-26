"""
Pydantic v2 схемы тренажёра «Система 112».

Разделены на 4 логических блока:
1. Enums — перечисления (сценарии, фазы, службы, типы нарушений).
2. Доменные модели — CallerState, CallCard, метрики, нарушения.
3. Схемы сессии и профилей — SessionState, CadetProfile, CallReport.
4. API-контракты — Request/Response для роутов /simulation/* и /instructor/*.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field






class ScenarioId(str, Enum):
    """Идентификаторы сценариев чрезвычайных ситуаций."""
    FIRE_APARTMENT = "fire_apartment"
    FIRE_HIGHRISE = "fire_highrise"
    ACCIDENT_JAMMED = "accident_jammed"
    MEDICAL_UNCONSCIOUS = "medical_unconscious"
    CRIME_ROBBERY = "crime_robbery"
    GAS_LEAK = "gas_leak"


class DifficultyLevel(str, Enum):
    """Уровень сложности сценария."""
    NOVICE = "novice"
    NORMAL = "normal"
    EXTREME = "extreme"


class CallerPhase(str, Enum):
    """Фаза эмоционального состояния заявителя в рамках звонка."""
    SHOCK = "shock"
    PANIC = "panic"
    COORDINATION = "coordination"
    RESOLUTION = "resolution"


class ServiceType(str, Enum):
    """Экстренные службы, которые активирует диспетчер."""
    FIRE = "fire"
    POLICE = "police"
    AMBULANCE = "ambulance"
    GAS = "gas"
    GKH = "gkh"
    METRO = "metro"
    LIFT = "lift"
    WATER = "water"
    HEAT = "heat"
    POWER = "power"
    ROADS = "roads"


class ViolationType(str, Enum):
    """Типы нарушений регламента 112, фиксируемые AuditEngine."""

    MISSED_CRITICAL_FIELD = "missed_critical_field"
    MISSED_REQUIRED_FIELD = "missed_required_field"

    LATE_ACTIVATION = "late_activation"
    MISSED_ACTIVATION = "missed_activation"

    CLASSIFICATION_MISMATCH = "classification_mismatch"
    SIGN_MISMATCH = "sign_mismatch"
    MISSED_CALLER_FIO = "missed_caller_fio"
    MISSED_CALLER_ROLE = "missed_caller_role"

    MISSED_SERVICE = "missed_service"
    EXTRA_SERVICE = "extra_service"

    AIRTIME_OUT_OF_RANGE = "airtime_out_of_range"
    INTERRUPTED_CALLER = "interrupted_caller"

    UNPROFESSIONAL_TONE = "unprofessional_tone"
    INAPPROPRIATE_QUESTION = "inappropriate_question"

    NO_GROUNDING_FIRST_30S = "no_grounding_first_30s"


class SeverityLevel(int, Enum):
    """Уровень критичности нарушения."""
    LOW = 1
    MEDIUM = 2
    HIGH = 3
    CRITICAL = 4


class SessionStatus(str, Enum):
    """Статус сессии звонка."""
    ACTIVE = "active"
    COMPLETED = "completed"
    ABORTED = "aborted"


class EventType(str, Enum):
    """Типы событий таймлайна звонка (для инструктора)."""
    CALL_STARTED = "call_started"
    DISPATCHER_SPEECH = "dispatcher_speech"
    CALLER_SPEECH = "caller_speech"
    CARD_FIELD_UPDATED = "card_field_updated"
    SERVICE_ACTIVATED = "service_activated"
    TRIGGER_DETECTED = "trigger_detected"
    VIOLATION_DETECTED = "violation_detected"
    PHASE_CHANGED = "phase_changed"
    CALL_ENDED = "call_ended"






class CallerState(BaseModel):
    """
    Внутреннее состояние ИИ-заявителя. Стейт-машина на 4 шкалах + скрытые факты.

    Двигается детерминированными правилами из `audit/state.py` на основании
    поведения курсанта (реплика, тон, инструкция). LLM лишь озвучивает то,
    что уже определено стейтом.
    """

    panic: int = Field(default=80, ge=0, le=100, description="Уровень паники (0-100)")
    compliance: int = Field(default=20, ge=0, le=100, description="Готовность выполнять инструкции (0-100)")
    trust: int = Field(default=40, ge=0, le=100, description="Доверие к диспетчеру (0-100)")
    cooperation: int = Field(default=30, ge=0, le=100, description="Готовность давать информацию (0-100)")

    hidden_facts: dict[str, Any] = Field(
        default_factory=dict,
        description="Факты, которые заявитель знает, но ещё не озвучил (адрес, этаж, детали)",
    )
    revealed_facts: set[str] = Field(
        default_factory=set,
        description="Ключи фактов из hidden_facts, которые уже озвучены в диалоге",
    )
    refused_topics: set[str] = Field(
        default_factory=set,
        description="Темы, на которые заявитель не отвечает (в панике, например, не может назвать адрес)",
    )

    phase: CallerPhase = Field(default=CallerPhase.SHOCK, description="Текущая фаза звонка")
    last_dispatcher_question: str | None = Field(
        default=None,
        description="Последний вопрос курсанта — на него заявитель реагирует в следующей реплике",
    )
    call_duration_sec: int = Field(default=0, ge=0, description="Длительность звонка в секундах")

    model_config = ConfigDict(use_enum_values=True)


class CallCard(BaseModel):
    """
    Карточка вызова — поля, которые курсант заполняет в АРМ.

    Разделена на 4 логических блока:
    1. Универсальные поля происшествия.
    2. Сведения о заявителе.
    3. Классификация по ЕКП (что курсант выбрал в панели признаков).
    4. Оповещённые службы (кого нажал в панели служб).
    """


    address: str | None = Field(default=None, description="Адрес происшествия")
    what_happened: str | None = Field(default=None, description="Что случилось")
    victims_present: bool | None = Field(default=None, description="Есть ли пострадавшие")
    victims_count: int | None = Field(default=None, ge=0, description="Количество пострадавших")
    threat_to_life: bool | None = Field(default=None, description="Угроза жизни")


    caller_fio: str | None = Field(default=None, description="ФИО заявителя")
    caller_role: str | None = Field(
        default=None,
        description="Роль заявителя: очевидец / участник / родственник / сосед",
    )
    caller_phone: str | None = Field(default=None, description="Предоставленный телефон заявителя")


    classification_id: str | None = Field(
        default=None,
        description="ID итогового типа в ЕКП (например '1.1.1.1')",
    )
    classification_name: str | None = Field(
        default=None,
        description="Название итогового типа ('пожар: мусор')",
    )
    sign_l1: str | None = Field(default=None, description="112-Признак.1")
    sign_l2: str | None = Field(default=None, description="112-Признак.2")
    sign_l3: str | None = Field(default=None, description="112-Признак.3")


    services_activated: list[str] = Field(
        default_factory=list,
        description="Службы, которые курсант активировал в панели (fire, police, ambulance, gas, ...)",
    )


    scenario_fields: dict[str, Any] = Field(
        default_factory=dict,
        description="Дополнительные поля, специфичные для сценария",
    )

    model_config = ConfigDict(use_enum_values=True)


class ProtocolAdherence(BaseModel):
    """Оценка соблюдения протокола сбора информации."""

    percent: int = Field(..., ge=0, le=100, description="Процент заполнения карточки (0-100)")
    filled_fields: list[str] = Field(default_factory=list, description="Заполненные поля")
    missed_critical: list[str] = Field(
        default_factory=list, description="Незаполненные критические поля (высокий вес)"
    )
    missed_required: list[str] = Field(
        default_factory=list, description="Незаполненные обязательные поля (обычный вес)"
    )


class AirtimeControl(BaseModel):
    """Оценка баланса речи диспетчера и заявителя."""

    dispatcher_percent: int = Field(..., ge=0, le=100, description="% речи диспетчера")
    caller_percent: int = Field(..., ge=0, le=100, description="% речи заявителя")
    target_min: int = Field(..., ge=0, le=100, description="Нижняя граница целевого диапазона")
    target_max: int = Field(..., ge=0, le=100, description="Верхняя граница целевого диапазона")
    in_range: bool = Field(..., description="Находится ли доля диспетчера в целевом диапазоне")
    advice: str = Field(default="", description="Рекомендация инструктора по управлению эфиром")


class TriggerEvent(BaseModel):
    """Событие обнаружения триггерной фразы заявителя."""

    trigger_key: str = Field(..., description="Ключ триггера (например, 'ребенок_не_дышит')")
    raw_phrase: str = Field(..., description="Фраза, в которой найден триггер")
    detected_at_sec: int = Field(..., ge=0, description="Секунда звонка, когда триггер сработал")
    expected_services: list[ServiceType] = Field(
        ..., description="Службы, которые должны быть активированы"
    )
    max_response_sec: int = Field(..., ge=0, description="Норматив реакции в секундах")
    severity: SeverityLevel = Field(..., description="Критичность триггера")


class ServiceActivation(BaseModel):
    """Событие активации службы курсантом."""

    service: ServiceType = Field(..., description="Активированная служба")
    activated_at_sec: int = Field(..., ge=0, description="Секунда звонка, когда нажата кнопка")


class Violation(BaseModel):
    """Одно зафиксированное нарушение регламента."""

    type: ViolationType = Field(..., description="Тип нарушения")
    severity: SeverityLevel = Field(..., description="Уровень критичности")
    detected_at_sec: int = Field(..., ge=0, description="Секунда, когда нарушение зафиксировано")
    description: str = Field(..., description="Человекочитаемое описание")
    related_field: str | None = Field(default=None, description="Связанное поле карточки, если применимо")
    related_trigger: str | None = Field(default=None, description="Связанный триггер, если применимо")


class EmergencyAudit(BaseModel):
    """Итог аудита реакции на экстренные триггеры."""

    triggers_detected: list[TriggerEvent] = Field(default_factory=list)
    activations: list[ServiceActivation] = Field(default_factory=list)
    response_times_sec: dict[str, int] = Field(
        default_factory=dict,
        description="trigger_key -> фактическое время реакции в секундах",
    )
    violations: list[Violation] = Field(default_factory=list)


class ProtocolAlert(BaseModel):
    """Результат работы Protocol & Safety Shield (аналог DLP, но под 112)."""

    has_violations: bool = Field(default=False)
    violations: list[Violation] = Field(default_factory=list)
    grounding_phrases_used: list[str] = Field(
        default_factory=list, description="Заземляющие фразы курсанта (green flags)"
    )
    unprofessional_phrases: list[str] = Field(
        default_factory=list, description="Некорректные фразы курсанта (red flags)"
    )


class CallerTurn(BaseModel):
    """Результат генерации реплики заявителя (возврат CallerEngine)."""

    text: str = Field(..., description="Что заявитель сказал")
    state_delta: dict[str, Any] = Field(
        default_factory=dict,
        description="Изменения CallerState, предложенные LLM",
    )
    revealed_facts: list[str] = Field(
        default_factory=list, description="Ключи фактов, которые заявитель озвучил в этой реплике"
    )


class CadetTurnResult(BaseModel):
    """
    Полный результат одного шага курсанта.
    Это то, что возвращает /simulation/step.
    """

    caller_response_text: str = Field(..., description="Реплика заявителя (для TTS)")
    caller_state: CallerState = Field(..., description="Актуальное состояние заявителя")

    protocol_adherence: ProtocolAdherence = Field(..., description="Соблюдение протокола сбора")
    airtime_control: AirtimeControl = Field(..., description="Баланс эфира")
    panic_index: int = Field(..., ge=0, le=100, description="Индекс паники заявителя")
    compliance_index: int = Field(..., ge=0, le=100, description="Индекс выполнения инструкций")
    trust_index: int = Field(..., ge=0, le=100, description="Индекс доверия к диспетчеру")

    emergency_audit: EmergencyAudit = Field(..., description="Аудит реакции на триггеры")
    protocol_alert: ProtocolAlert = Field(..., description="Результат Protocol Shield")

    model_config = ConfigDict(use_enum_values=True)






class Scenario(BaseModel):
    """Справочник сценария (загружается из JSON)."""

    id: ScenarioId = Field(..., description="Идентификатор сценария")
    title: str = Field(..., description="Название для UI")
    description: str = Field(..., description="Краткое описание для инструктора")
    difficulty: DifficultyLevel = Field(..., description="Уровень сложности")

    initial_prompt: str = Field(..., description="Системный промт для CallerEngine")
    opening_line: str = Field(..., description="Первая фраза заявителя при поднятии трубки")

    required_fields: list[str] = Field(
        default_factory=list, description="Обязательные поля карточки (вес 1)"
    )
    critical_fields: list[str] = Field(
        default_factory=list, description="Критические поля карточки (вес 3)"
    )
    airtime_target: tuple[int, int] = Field(
        ..., description="Целевой диапазон доли речи диспетчера, %"
    )

    initial_caller_state: CallerState = Field(..., description="Стартовое состояние заявителя")
    hidden_facts_template: dict[str, Any] = Field(
        default_factory=dict, description="Шаблон скрытых фактов для инициализации"
    )

    model_config = ConfigDict(use_enum_values=True)


class SessionState(BaseModel):
    """Полное состояние активной сессии звонка."""

    call_id: str = Field(default_factory=lambda: str(uuid4()), description="UUID звонка")
    cadet_id: int = Field(..., description="ID курсанта")
    scenario_id: ScenarioId = Field(..., description="ID сценария")

    caller_state: CallerState = Field(..., description="Состояние заявителя")
    card: CallCard = Field(default_factory=CallCard, description="Карточка вызова")

    events: list[dict[str, Any]] = Field(
        default_factory=list, description="Таймлайн событий (см. EventType)"
    )
    activations: list[ServiceActivation] = Field(
        default_factory=list, description="Все активации служб"
    )
    triggers: list[TriggerEvent] = Field(
        default_factory=list, description="Все обнаруженные триггеры"
    )
    violations: list[Violation] = Field(
        default_factory=list, description="Все зафиксированные нарушения"
    )

    dispatcher_speech_sec: float = Field(default=0.0, description="Суммарное время речи диспетчера")
    caller_speech_sec: float = Field(default=0.0, description="Суммарное время речи заявителя")

    status: SessionStatus = Field(default=SessionStatus.ACTIVE, description="Статус сессии")
    started_at: datetime = Field(default_factory=datetime.utcnow, description="Начало звонка")
    ended_at: datetime | None = Field(default=None, description="Окончание звонка")

    model_config = ConfigDict(use_enum_values=True)


class CadetProfile(BaseModel):
    """Паспорт курсанта — накапливается между сессиями."""

    cadet_id: int = Field(..., description="ID курсанта")
    full_name: str = Field(default="", description="ФИО")
    group_id: str | None = Field(default=None, description="Учебная группа")

    stress_resistance: int = Field(default=50, ge=0, le=100, description="Устойчивость к стрессу")
    avg_response_time_sec: float = Field(default=0.0, ge=0, description="Среднее время реакции")
    conflict_tendency: int = Field(default=0, ge=0, le=100, description="Склонность к конфликту")

    total_sessions: int = Field(default=0, ge=0, description="Проведено сессий")
    avg_protocol_adherence: int = Field(default=0, ge=0, le=100, description="Среднее по протоколу")
    avg_compliance_impact: int = Field(default=0, ge=0, le=100, description="Средний эффект на заявителя")

    recommended_scenarios: list[ScenarioId] = Field(
        default_factory=list, description="Сценарии, которые надо отработать"
    )

    model_config = ConfigDict(use_enum_values=True)


class CallReport(BaseModel):
    """Финальный отчёт по звонку."""

    call_id: str = Field(..., description="UUID звонка")
    cadet_id: int = Field(..., description="ID курсанта")
    scenario_id: ScenarioId = Field(..., description="ID сценария")
    duration_sec: int = Field(..., ge=0, description="Длительность звонка")

    protocol_adherence: ProtocolAdherence = Field(..., description="Соблюдение протокола")
    airtime_control: AirtimeControl = Field(..., description="Баланс эфира")
    emergency_audit: EmergencyAudit = Field(..., description="Аудит триггеров")
    protocol_alert: ProtocolAlert = Field(..., description="Результат Shield")

    final_panic_index: int = Field(..., ge=0, le=100, description="Индекс паники в конце звонка")
    final_compliance_index: int = Field(..., ge=0, le=100, description="Комплаенс в конце звонка")

    grade: int = Field(..., ge=0, le=100, description="Итоговая оценка (0-100)")
    grade_label: str = Field(..., description="Текстовая интерпретация: 'отлично', 'хорошо' и т.д.")

    recommendations: list[str] = Field(
        default_factory=list, description="Персональные рекомендации курсанту"
    )
    timeline: list[dict[str, Any]] = Field(
        default_factory=list, description="Полный таймлайн событий для разбора"
    )


    cadet_name: str | None = Field(default=None, description="ФИО курсанта")
    scenario_title: str | None = Field(default=None, description="Название сценария (из билета)")
    expected: dict[str, Any] | None = Field(
        default=None,
        description="Эталон сценария (Expected.model_dump)",
    )
    card: dict[str, Any] | None = Field(
        default=None,
        description="Итоговая карточка курсанта (CallCard.model_dump)",
    )

    created_at: datetime = Field(default_factory=datetime.utcnow)

    model_config = ConfigDict(use_enum_values=True)








class StartSimulationRequest(BaseModel):
    cadet_id: int = Field(..., description="ID курсанта")
    cadet_name: str | None = Field(
        default=None,
        description="ФИО курсанта (опционально, для PDF-отчёта)",
    )
    scenario_id: str = Field(
        ...,
        description=(
            "ID сценария: либо старый ScenarioId "
            "('fire_apartment', 'accident_jammed'...), "
            "либо ID билета ('ticket_01_case_01')."
        ),
    )
    difficulty: DifficultyLevel = Field(
        default=DifficultyLevel.NORMAL, description="Уровень сложности"
    )


class StartSimulationResponse(BaseModel):
    call_id: str = Field(..., description="UUID созданной сессии")
    scenario: Scenario = Field(..., description="Метаданные сценария")
    opening_line: str = Field(..., description="Первая фраза заявителя")
    opening_audio_b64: str | None = Field(
        default=None,
        description="Озвучка opening_line в base64 (если TTS включён)",
    )
    caller_state: CallerState = Field(..., description="Стартовое состояние заявителя")
    card_template: CallCard = Field(..., description="Пустая карточка вызова для UI")




class StepSimulationRequest(BaseModel):
    call_id: str = Field(..., description="UUID звонка")
    dispatcher_text: str = Field(..., min_length=1, description="Реплика диспетчера (после STT)")
    duration_sec: float = Field(default=0.0, ge=0, description="Длительность реплики в секундах")


class StepSimulationResponse(BaseModel):
    turn: CadetTurnResult = Field(..., description="Полный результат шага")
    caller_audio_url: str | None = Field(
        default=None,
        description="URL сгенерированного TTS-аудио заявителя (если включён)",
    )
    caller_audio_b64: str | None = Field(
        default=None,
        description="WAV заявителя в base64 (если TTS включён)",
    )




class CardUpdateRequest(BaseModel):
    call_id: str = Field(..., description="UUID звонка")
    field: str = Field(..., description="Имя поля карточки")
    value: Any = Field(..., description="Значение поля")


class CardUpdateResponse(BaseModel):
    card: CallCard = Field(..., description="Обновлённая карточка")
    protocol_adherence: ProtocolAdherence = Field(..., description="Актуальный % соблюдения")




class ServiceActivateRequest(BaseModel):
    call_id: str = Field(..., description="UUID звонка")
    service: ServiceType = Field(..., description="Какую службу активирует курсант")


class ServiceActivateResponse(BaseModel):
    activation: ServiceActivation = Field(..., description="Зафиксированная активация")
    new_violations: list[Violation] = Field(
        default_factory=list, description="Нарушения, возникшие в результате этой активации"
    )




class EndSimulationRequest(BaseModel):
    call_id: str = Field(..., description="UUID звонка")
    reason: str = Field(default="completed", description="Причина завершения")


class EndSimulationResponse(BaseModel):
    report: CallReport = Field(..., description="Финальный отчёт")




class AssignScenarioRequest(BaseModel):
    cadet_id: int = Field(..., description="Кому назначить")
    scenario_id: ScenarioId = Field(..., description="Какой сценарий")
    difficulty: DifficultyLevel = Field(default=DifficultyLevel.NORMAL)


class AssignScenarioResponse(BaseModel):
    assignment_id: str = Field(..., description="UUID назначения")
    call_id: str | None = Field(default=None, description="Созданная сессия (если сразу стартовали)")