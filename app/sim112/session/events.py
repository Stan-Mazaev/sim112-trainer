"""
Шина событий для инструктора.

Каждое действие в звонке (реплика курсанта, реплика заявителя, активация службы,
обнаружение триггера, нарушение) кладётся в таймлайн. Инструктор видит это
в реальном времени через WebSocket /ws/instructor/{call_id}.

Шина не привязана к транспорту — она просто собирает события в список.
Отправка через WebSocket — задача session/orchestrator.py.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Callable, Awaitable

from app.sim112.schemas import EventType



EventListener = Callable[[EventType, dict[str, Any]], Any] | Callable[[EventType, dict[str, Any]], Awaitable[Any]]


class EventBus:
    """
    Один экземпляр на звонок.
    Хранит таймлайн + рассылает события подписчикам (инструктор, лог).
    """

    def __init__(self):
        self._timeline: list[dict[str, Any]] = []
        self._listeners: list[EventListener] = []





    def subscribe(self, listener: EventListener) -> None:
        """Добавляет слушателя. Обычно это WebSocket-канал инструктора."""
        self._listeners.append(listener)

    def unsubscribe(self, listener: EventListener) -> None:
        if listener in self._listeners:
            self._listeners.remove(listener)





    async def emit(
        self,
        event_type: EventType,
        payload: dict[str, Any],
        at_sec: int | None = None,
    ) -> None:
        """
        Публикует событие:
        1. Кладёт в таймлайн.
        2. Рассылает всем подписчикам.
        """
        event = {
            "type": event_type.value if hasattr(event_type, "value") else str(event_type),
            "at_sec": at_sec,
            "timestamp": datetime.utcnow().isoformat(),
            "payload": payload,
        }
        self._timeline.append(event)

        for listener in list(self._listeners):
            try:
                result = listener(event_type, event)

                if hasattr(result, "__await__"):
                    await result
            except Exception as exc:

                print(f"[EventBus] Ошибка в слушателе: {exc}")

    def emit_sync(
        self,
        event_type: EventType,
        payload: dict[str, Any],
        at_sec: int | None = None,
    ) -> None:
        """
        Синхронный вариант — для использования в местах без await.

        ВАЖНО: async-слушатели не смогут быть вызваны синхронно.
        Если такой слушатель обнаружен — громко предупреждаем и закрываем корутину,
        чтобы не было RuntimeWarning. Для полноценной работы с async-слушателями
        используйте `await emit(...)`.
        """
        event = {
            "type": event_type.value if hasattr(event_type, "value") else str(event_type),
            "at_sec": at_sec,
            "timestamp": datetime.utcnow().isoformat(),
            "payload": payload,
        }
        self._timeline.append(event)

        for listener in list(self._listeners):
            try:
                result = listener(event_type, event)
                if hasattr(result, "__await__"):


                    print(
                        f"[EventBus] emit_sync: слушатель {listener} — async, "
                        f"уведомление пропущено. Используйте `await emit(...)`."
                    )
                    if hasattr(result, "close"):
                        try:
                            result.close()
                        except Exception:
                            pass
            except Exception as exc:
                print(f"[EventBus] Ошибка в слушателе: {exc}")





    def timeline(self) -> list[dict[str, Any]]:
        """Полный таймлайн звонка (для отчёта)."""
        return list(self._timeline)

    def since(self, index: int) -> list[dict[str, Any]]:
        """События начиная с позиции index — для инкрементальной подгрузки."""
        return self._timeline[index:]

    def __len__(self) -> int:
        return len(self._timeline)