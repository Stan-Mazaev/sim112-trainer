"""Проверка итоговой оценки для идеального и плохого прогонов."""

import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.sim112.scenarios.schemas import Ticket
from app.sim112.schemas import (
    CallerState, DifficultyLevel, Scenario, ScenarioId, ServiceType,
)
from app.sim112.session.orchestrator import CallOrchestrator
from app.sim112.report.generator import compute_grade


def load_case(ticket_num: int, case_num: int):
    path = ROOT / "app" / "sim112" / "scenarios" / "tickets" / f"ticket_{ticket_num:02d}.json"
    with path.open(encoding="utf-8") as f:
        t = Ticket.model_validate(json.load(f))
    for sc in t.scenarios:
        if sc.case_number == case_num:
            return sc
    raise ValueError(f"Сценарий {ticket_num}/{case_num} не найден")


def to_legacy(sc) -> Scenario:
    c = sc.caller
    return Scenario(
        id=ScenarioId.FIRE_APARTMENT,
        title=sc.id,
        description=sc.situation,
        difficulty=DifficultyLevel(sc.difficulty),
        initial_prompt="",
        opening_line=c.opening_line,
        airtime_target=(30, 60),
        required_fields=["address", "what_happened"],
        critical_fields=["address"],
        initial_caller_state=CallerState(
            panic=c.initial_panic, trust=c.initial_trust,
            cooperation=c.initial_cooperation, phase="shock",
            hidden_facts=dict(c.hidden_facts),
        ),
        hidden_facts_template=dict(c.hidden_facts),
    )


async def run(sc, *, mistakes: bool):
    orch = CallOrchestrator(
        cadet_id=1, scenario=to_legacy(sc),
        difficulty=DifficultyLevel(sc.difficulty),
        expected=sc.expected,
    )
    await orch.start()
    await orch.step("Назовите адрес!", duration_sec=3.0)
    await orch.step("Что случилось?", duration_sec=3.0)
    await orch.update_card("address", sc.address)
    await orch.update_card("what_happened", sc.situation)

    if not mistakes:
        await orch.update_card("caller_fio", sc.caller.fio)
        await orch.update_card("caller_role", sc.caller.role)
        await orch.update_card("classification_id", sc.expected.classification_id)
        await orch.update_card("classification_name", sc.expected.classification_name)
        await orch.update_card("sign_l1", sc.expected.signs.sign_l1)
        if sc.expected.signs.sign_l2:
            await orch.update_card("sign_l2", sc.expected.signs.sign_l2)
        if sc.expected.signs.sign_l3:
            await orch.update_card("sign_l3", sc.expected.signs.sign_l3)
        services = sc.expected.services
    else:
        services = ["police"]

    for svc in services:
        try:
            await orch.activate_service(ServiceType(svc))
        except ValueError:
            pass

    final = await orch.end()
    grade = compute_grade(final)
    return grade, final["violations"]


async def main():
    sc = load_case(1, 1)

    print("=" * 60)
    print(f"Сценарий: {sc.id} — {sc.expected.classification_name}")
    print("=" * 60)

    grade, v = await run(sc, mistakes=False)
    print(f"\n[ИДЕАЛЬНЫЙ]  Оценка: {grade}/100  Нарушений: {len(v)}")
    for x in v:
        t = x["type"] if isinstance(x, dict) else x.type.value
        print(f"   • {t}")

    grade, v = await run(sc, mistakes=True)
    print(f"\n[С ОШИБКАМИ] Оценка: {grade}/100  Нарушений: {len(v)}")
    for x in v:
        t = x["type"] if isinstance(x, dict) else x.type.value
        print(f"   • {t}")


if __name__ == "__main__":
    asyncio.run(main())