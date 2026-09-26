"""
In-memory менеджер активных сессий звонков.

Стратегия хранения:
- Все сессии держатся в одном dict.
- Завершённые сессии автоматически ограничиваются LRU-политикой:
  не более MAX_COMPLETED последних.
- Инструктор может явно закрыть разбор (`close_review`), тогда сессия
  удаляется немедленно.
- Активные сессии LRU-политикой не затрагиваются — они всегда живут,
  пока не завершатся.
"""

from __future__ import annotations

import asyncio
from collections import OrderedDict
from typing import Optional

from app.sim112.session.orchestrator import CallOrchestrator


class SessionManager:
    MAX_COMPLETED = 100

    def __init__(self):

        self._sessions: "OrderedDict[str, CallOrchestrator]" = OrderedDict()
        self._lock = asyncio.Lock()





    async def add(self, orchestrator: CallOrchestrator) -> None:
        async with self._lock:
            self._sessions[orchestrator.call_id] = orchestrator
            self._sessions.move_to_end(orchestrator.call_id)
            self._enforce_completed_limit_locked()

    async def get(self, call_id: str) -> Optional[CallOrchestrator]:
        async with self._lock:
            return self._sessions.get(call_id)

    async def remove(self, call_id: str) -> None:
        async with self._lock:
            self._sessions.pop(call_id, None)

    def all_ids(self) -> list[str]:
        return list(self._sessions.keys())

    def count(self) -> int:
        return len(self._sessions)

    def counts(self) -> dict[str, int]:
        """Диагностика: сколько активных и завершённых."""
        active = 0
        completed = 0
        for orch in self._sessions.values():
            status = orch.status.value if hasattr(orch.status, "value") else str(orch.status)
            if status == "active":
                active += 1
            else:
                completed += 1
        return {"total": len(self._sessions), "active": active, "completed": completed}





    def _enforce_completed_limit_locked(self) -> None:
        """
        Удаляет самые старые ЗАВЕРШЁННЫЕ сессии, если их больше MAX_COMPLETED.

        Работает без lock — вызывается только из методов, уже удерживающих lock.
        Порядок итерации OrderedDict — от старых к новым.
        """
        if len(self._sessions) <= self.MAX_COMPLETED:
            return


        completed_ids = [
            cid
            for cid, orch in self._sessions.items()
            if (orch.status.value if hasattr(orch.status, "value") else str(orch.status)) != "active"
        ]



        excess = len(completed_ids) - self.MAX_COMPLETED
        if excess <= 0:
            return

        for cid in completed_ids[:excess]:
            self._sessions.pop(cid, None)





    async def close_review(self, call_id: str) -> bool:
        """
        Инструктор закончил разбор — сессия удаляется.
        Возвращает True, если сессия была найдена и удалена.
        """
        async with self._lock:
            return self._sessions.pop(call_id, None) is not None



_session_manager: SessionManager | None = None


def get_session_manager() -> SessionManager:
    global _session_manager
    if _session_manager is None:
        _session_manager = SessionManager()
    return _session_manager