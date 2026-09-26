"""
Pydantic-схемы для сценариев из билетов 112.

Отличаются от старых Scenario из app.sim112.schemas:
- явная привязка к ЕКП (classification_id)
- эталонный ответ для оценки курсанта (expected)
- три случая в одном билете = три сценария
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


CallerRole = Literal["очевидец", "участник", "родственник", "сосед", "пострадавший", "неизвестный"]
Difficulty = Literal["novice", "normal", "extreme"]


class Caller(BaseModel):
    """Описание заявителя в сценарии."""

    fio: str = Field(..., description="ФИО заявителя из билета")
    phone: str = Field(..., description="Телефон заявителя из билета")
    role: CallerRole = Field(..., description="Кто заявитель по отношению к происшествию")
    opening_line: str = Field(..., description="Первая фраза заявителя при поднятии трубки")

    initial_panic: int = Field(default=50, ge=0, le=100, description="Стартовая паника заявителя")
    initial_trust: int = Field(default=40, ge=0, le=100, description="Стартовое доверие к диспетчеру")
    initial_cooperation: int = Field(default=30, ge=0, le=100, description="Стартовая готовность давать информацию")

    hidden_facts: dict[str, Any] = Field(
        default_factory=dict,
        description="Факты, которые заявитель знает, но расскажет только при правильных вопросах",
    )

    model_config = ConfigDict(extra="forbid")


class ExpectedSigns(BaseModel):
    """Формализованные признаки, которые курсант должен выбрать в АРМ."""

    sign_l1: str | None = Field(default=None, description="112-Признак.1")
    sign_l2: str | None = Field(default=None, description="112-Признак.2")
    sign_l3: str | None = Field(default=None, description="112-Признак.3")


class Expected(BaseModel):
    """Эталонный ответ — с чем AuditEngine будет сравнивать действия курсанта."""

    classification_id: str = Field(..., description="ID типа в ЕКП, например '1.1.1.1'")
    classification_name: str = Field(..., description="Итоговый тип происшествия, например 'пожар: мусор'")
    signs: ExpectedSigns = Field(..., description="Ожидаемые формализованные признаки")

    services: list[str] = Field(
        ...,
        description="Службы, которые должны получить карточку (с учётом ручного добавления)",
    )
    services_ekp: list[str] = Field(
        default_factory=list,
        description="Службы, которые сработают автоматически по ЕКП",
    )

    victims_present: bool = Field(..., description="Ожидаемое значение флага 'пострадавшие'")
    threat_to_life: bool = Field(..., description="Ожидаемое значение флага 'угроза жизни'")

    additional_fields: dict[str, Any] = Field(
        default_factory=dict,
        description="Прочие поля карточки, специфичные для сценария",
    )

    model_config = ConfigDict(extra="forbid")


class TicketScenario(BaseModel):
    """Один вызов из билета — сценарий для тренажёра."""

    id: str = Field(..., description="Уникальный ID сценария, например 'ticket_01_case_01'")
    ticket_number: int = Field(..., ge=1, description="Номер билета")
    case_number: int = Field(..., ge=1, description="Номер случая внутри билета")
    difficulty: Difficulty = Field(default="normal")

    situation: str = Field(..., description="Краткое описание происшествия (из билета)")
    address: str = Field(..., description="Адрес из билета")
    address_details: str | None = Field(
        default=None, description="Уточнения к адресу (тоже из билета)"
    )

    caller: Caller = Field(..., description="Заявитель")
    expected: Expected = Field(..., description="Эталонный ответ для оценки")

    hints: list[str] = Field(
        default_factory=list,
        description="Подсказки для инструктора — что важно в этом сценарии",
    )

    model_config = ConfigDict(extra="forbid")


class Ticket(BaseModel):
    """Билет целиком — три сценария."""

    ticket_number: int = Field(..., ge=1)
    source: str = Field(default="Билеты-задачи по C 112 . АГС_ГСИ.pdf")
    scenarios: list[TicketScenario] = Field(..., min_length=1)

    model_config = ConfigDict(extra="forbid")