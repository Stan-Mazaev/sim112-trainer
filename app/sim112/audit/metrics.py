"""
Расчёт метрик звонка.

Все метрики детерминированные. Никакой LLM.
Четыре метрики:

1. ProtocolAdherence — насколько полно курсант собрал обязательные поля карточки.
   Формула: взвешенная сумма заполненных полей / общий вес × 100.
   Критические поля весят ×3, обычные ×1.

2. AirtimeControl — баланс речи диспетчера и заявителя.
   Целевой диапазон зависит от сценария (см. AIRTIME_TARGETS).

3. Panic/Compliance/Trust — берутся из CallerState напрямую.
   Здесь только упаковка в удобный формат.

4. ResponseTime — среднее время реакции на триггеры.
"""

from __future__ import annotations

from typing import Any

from app.sim112.schemas import (
    AirtimeControl,
    CallCard,
    ProtocolAdherence,
    ScenarioId,
    ServiceActivation,
    TriggerEvent,
)






CRITICAL_WEIGHT = 3
REQUIRED_WEIGHT = 1


def compute_protocol_adherence(
    card: CallCard,
    required_fields: list[str],
    critical_fields: list[str],
) -> ProtocolAdherence:
    """
    Считает % заполнения карточки.

    Критические поля весят ×3, обычные ×1.
    Поле, которое есть и в required, и в critical, считается только как critical.
    """

    critical_set = set(critical_fields)
    required_only = [f for f in required_fields if f not in critical_set]


    filled = _get_filled_fields(card)

    filled_critical = [f for f in critical_fields if f in filled]
    filled_required = [f for f in required_only if f in filled]
    missed_critical = [f for f in critical_fields if f not in filled]
    missed_required = [f for f in required_only if f not in filled]


    total_weight = len(critical_fields) * CRITICAL_WEIGHT + len(required_only) * REQUIRED_WEIGHT
    if total_weight == 0:
        return ProtocolAdherence(
            percent=100,
            filled_fields=list(filled),
            missed_critical=[],
            missed_required=[],
        )

    gained = len(filled_critical) * CRITICAL_WEIGHT + len(filled_required) * REQUIRED_WEIGHT
    percent = int(round(gained / total_weight * 100))

    return ProtocolAdherence(
        percent=percent,
        filled_fields=sorted(filled),
        missed_critical=sorted(missed_critical),
        missed_required=sorted(missed_required),
    )


def _get_filled_fields(card: CallCard) -> set[str]:
    """Собирает заполненные поля карточки в один set."""
    filled: set[str] = set()

    base = {
        "address": card.address,
        "what_happened": card.what_happened,
        "victims_present": card.victims_present,
        "victims_count": card.victims_count,
        "threat_to_life": card.threat_to_life,
    }
    for name, value in base.items():
        if value is not None and value != "":
            filled.add(name)

    for name, value in card.scenario_fields.items():
        if value is not None and value != "":
            filled.add(name)

    return filled









AIRTIME_TARGETS: dict[ScenarioId, tuple[int, int]] = {
    ScenarioId.FIRE_APARTMENT:    (35, 50),
    ScenarioId.FIRE_HIGHRISE:     (35, 50),
    ScenarioId.ACCIDENT_JAMMED:   (30, 45),
    ScenarioId.MEDICAL_UNCONSCIOUS: (45, 60),
    ScenarioId.CRIME_ROBBERY:     (15, 30),
    ScenarioId.GAS_LEAK:          (35, 50),
}


def compute_airtime_control(
    dispatcher_speech_sec: float,
    caller_speech_sec: float,
    scenario_id: ScenarioId,
) -> AirtimeControl:
    """
    Считает баланс речи диспетчера и заявителя.

    Формула: доля диспетчера = его секунды / общие секунды × 100.
    Если общих секунд 0 — возвращаем 50/50 и метку «недостаточно данных».
    """
    total = dispatcher_speech_sec + caller_speech_sec
    if total <= 0:
        target_min, target_max = AIRTIME_TARGETS.get(scenario_id, (30, 50))
        return AirtimeControl(
            dispatcher_percent=50,
            caller_percent=50,
            target_min=target_min,
            target_max=target_max,
            in_range=True,
            advice="Недостаточно данных для оценки баланса эфира.",
        )

    d_percent = int(round(dispatcher_speech_sec / total * 100))
    d_percent = max(0, min(100, d_percent))
    c_percent = 100 - d_percent

    target_min, target_max = AIRTIME_TARGETS.get(scenario_id, (30, 50))
    in_range = target_min <= d_percent <= target_max

    advice = _airtime_advice(d_percent, target_min, target_max)

    return AirtimeControl(
        dispatcher_percent=d_percent,
        caller_percent=c_percent,
        target_min=target_min,
        target_max=target_max,
        in_range=in_range,
        advice=advice,
    )


def _airtime_advice(percent: int, t_min: int, t_max: int) -> str:
    """Формирует рекомендацию по управлению эфиром."""
    if t_min <= percent <= t_max:
        return "Баланс эфира в норме: инициатива у диспетчера, заявитель активно отвечает."

    if percent < t_min:
        diff = t_min - percent
        return (
            f"Диспетчер говорит слишком мало ({percent}%, цель {t_min}–{t_max}%). "
            f"Не хватает {diff}% активных уточняющих вопросов. "
            f"Заявитель может уйти в бесконтрольную панику."
        )

    diff = percent - t_max
    return (
        f"Диспетчер говорит слишком много ({percent}%, цель {t_min}–{t_max}%). "
        f"Превышение на {diff}%. Диспетчер подавляет заявителя, "
        f"не даёт ему сообщить важные детали."
    )






def compute_response_times(
    triggers: list[TriggerEvent],
    activations: list[ServiceActivation],
) -> dict[str, int]:
    """
    Для каждого триггера считает фактическое время реакции.

    Реакция — это активация ХОТЯ БЫ ОДНОЙ из ожидаемых служб ПОСЛЕ триггера.
    Если реакции не было — значение -1.
    """
    result: dict[str, int] = {}

    for trigger in triggers:
        activation_times = []
        for service in trigger.expected_services:
            matched = [
                a.activated_at_sec for a in activations
                if a.service == service and a.activated_at_sec >= trigger.detected_at_sec
            ]
            if matched:
                activation_times.append(min(matched))

        if activation_times:

            first = min(activation_times)
            result[trigger.trigger_key] = first - trigger.detected_at_sec
        else:
            result[trigger.trigger_key] = -1

    return result


def compute_average_response_time(response_times: dict[str, int]) -> float:
    """Среднее время реакции по всем закрытым триггерам."""
    valid = [t for t in response_times.values() if t >= 0]
    if not valid:
        return 0.0
    return round(sum(valid) / len(valid), 1)






def compute_all_metrics(
    *,
    card: CallCard,
    required_fields: list[str],
    critical_fields: list[str],
    scenario_id: ScenarioId,
    dispatcher_speech_sec: float,
    caller_speech_sec: float,
    triggers: list[TriggerEvent],
    activations: list[ServiceActivation],
) -> dict[str, Any]:
    """
    Удобная обёртка: считает все метрики одним вызовом.
    Используется в audit/engine.py и report/generator.py.
    """
    adherence = compute_protocol_adherence(card, required_fields, critical_fields)
    airtime = compute_airtime_control(dispatcher_speech_sec, caller_speech_sec, scenario_id)
    response_times = compute_response_times(triggers, activations)
    avg_response = compute_average_response_time(response_times)

    return {
        "protocol_adherence": adherence,
        "airtime_control": airtime,
        "response_times_sec": response_times,
        "average_response_sec": avg_response,
    }