"""Проверка загрузки сценария из JSON — валидация через Pydantic."""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.sim112.scenarios.schemas import Ticket


def main():
    if len(sys.argv) < 2:
        print("Использование: python scripts/check_scenario.py ticket_01")
        sys.exit(1)

    name = sys.argv[1]


    path = ROOT / "app" / "sim112" / "scenarios" / "tickets" / f"{name}.json"
    if not path.exists():
        path = ROOT / "app" / "sim112" / "scenarios" / f"{name}.json"

    if not path.exists():
        print(f"Файл не найден: {path}")
        sys.exit(1)

    with path.open(encoding="utf-8") as f:
        raw = json.load(f)

    ticket = Ticket.model_validate(raw)

    print(f"Билет №{ticket.ticket_number}")
    print(f"Источник: {ticket.source}")
    print(f"Сценариев: {len(ticket.scenarios)}")
    print()

    for sc in ticket.scenarios:
        print(f"  [{sc.id}] случай {sc.case_number} ({sc.difficulty})")
        print(f"     Ситуация: {sc.situation}")
        print(f"     Адрес:    {sc.address}")
        print(f"     Заявитель: {sc.caller.fio} ({sc.caller.role})")
        print(f"     Открытие: {sc.caller.opening_line}")
        print(f"     → Классификация: {sc.expected.classification_id} — {sc.expected.classification_name}")
        print(f"     → Службы (всего): {sc.expected.services}")
        print(f"     → По ЕКП авто:    {sc.expected.services_ekp}")
        print(f"     → Пострадавшие: {sc.expected.victims_present}, Угроза жизни: {sc.expected.threat_to_life}")
        print()

    print("[OK] Сценарий валиден.")


if __name__ == "__main__":
    main()