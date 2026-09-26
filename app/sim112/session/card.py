"""
Работа с карточкой вызова.

Карточка — это то, что курсант заполняет в АРМ во время звонка.
Здесь только манипуляции: создание, обновление полей, валидация.
Метрики (Protocol Adherence) считаются в audit/metrics.py.
"""

from __future__ import annotations

from typing import Any

from app.sim112.schemas import CallCard




_BASE_FIELDS = {

    "address",
    "what_happened",
    "victims_present",
    "victims_count",
    "threat_to_life",

    "caller_fio",
    "caller_role",
    "caller_phone",

    "classification_id",
    "classification_name",
    "sign_l1",
    "sign_l2",
    "sign_l3",

    "services_activated",
}


class CardManager:
    """
    Обёртка над CallCard. Принадлежит одной сессии звонка.
    """

    def __init__(self, scenario_fields: list[str] | None = None):
        """
        scenario_fields — имена полей, специфичных для сценария.
        Например, для пожара: ['floor', 'entrance', 'apartment', 'what_burning'].
        """
        self.card = CallCard()
        self.allowed_fields = _BASE_FIELDS | set(scenario_fields or [])





    def update(self, field: str, value: Any) -> bool:
        """
        Обновляет поле карточки. Возвращает True, если обновление принято.

        Правила:
        - Поле должно быть в allowed_fields.
        - Значение не может быть пустой строкой (None допустим для сброса).
        - Поле может быть как базовым, так и scenario_fields.
        """
        if field not in self.allowed_fields:
            return False


        if isinstance(value, str) and not value.strip():
            value = None

        if field in _BASE_FIELDS:
            setattr(self.card, field, value)
        else:

            if value is None:
                self.card.scenario_fields.pop(field, None)
            else:
                self.card.scenario_fields[field] = value

        return True

    def update_batch(self, updates: dict[str, Any]) -> dict[str, bool]:
        """Пакетное обновление. Возвращает {field: accepted}."""
        return {field: self.update(field, value) for field, value in updates.items()}





    def snapshot(self) -> CallCard:
        """Возвращает копию карточки (Pydantic сам сделает deepcopy)."""
        return self.card.model_copy(deep=True)

    def to_dict(self) -> dict[str, Any]:
        """Плоский словарь для UI."""
        return self.card.model_dump()





    def reset(self) -> None:
        self.card = CallCard()