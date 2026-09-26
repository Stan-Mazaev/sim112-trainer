"""
Реестр сценариев. Загружает JSON-файлы из папки scenarios/.
Хранит их в памяти. Один реестр на процесс.
"""

from __future__ import annotations

import json
from pathlib import Path

from app.sim112.schemas import Scenario, ScenarioId


SCENARIOS_DIR = Path(__file__).parent


class ScenarioRegistry:
    def __init__(self):
        self._scenarios: dict[ScenarioId, Scenario] = {}
        self._load_all()

    def _load_all(self) -> None:
        for path in SCENARIOS_DIR.glob("*.json"):
            try:
                with path.open("r", encoding="utf-8") as f:
                    data = json.load(f)
                scenario = Scenario.model_validate(data)
                self._scenarios[scenario.id] = scenario
            except Exception as exc:
                print(f"[ScenarioRegistry] Ошибка загрузки {path.name}: {exc}")

    def get(self, scenario_id: ScenarioId) -> Scenario | None:
        return self._scenarios.get(scenario_id)

    def all(self) -> list[Scenario]:
        return list(self._scenarios.values())

    def ids(self) -> list[ScenarioId]:
        return list(self._scenarios.keys())


_registry: ScenarioRegistry | None = None


def get_registry() -> ScenarioRegistry:
    global _registry
    if _registry is None:
        _registry = ScenarioRegistry()
    return _registry