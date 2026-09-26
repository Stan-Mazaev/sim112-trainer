"""
E2E-прогон сценария из билета через CallOrchestrator.

Показывает разницу между «идеальным курсантом» и «курсантом с ошибками».
"""

import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.sim112.scenarios.schemas import Ticket, TicketScenario
from app.sim112.schemas import (
    CallerState,
    DifficultyLevel,
    Scenario,
    ScenarioId,
    ServiceType,
)
from app.sim112.session.orchestrator import CallOrchestrator


def load_ticket(number: int) -> Ticket:
    path = ROOT / "app" / "sim112" / "scenarios" / "tickets" / f"ticket_{number:02d}.json"
    with path.open(encoding="utf-8") as f:
        return Ticket.model_validate(json.load(f))


def scenario_to_legacy(ticket_scenario: TicketScenario) -> Scenario:
    """
    Конвертирует сценарную модель в старую Scenario из sim112.schemas,
    которую принимает CallOrchestrator.
    """
    caller = ticket_scenario.caller
    initial_state = CallerState(
        panic=caller.initial_panic,
        trust=caller.initial_trust,
        cooperation=caller.initial_cooperation,
        phase="shock",
        hidden_facts=dict(caller.hidden_facts),
    )

    return Scenario(
        id=ScenarioId.FIRE_APARTMENT,
        title=(
            f"Билет {ticket_scenario.ticket_number}, "
            f"случай {ticket_scenario.case_number} — "
            f"{ticket_scenario.situation}"
        ),
        description=ticket_scenario.situation,
        difficulty=DifficultyLevel(ticket_scenario.difficulty),
        initial_prompt="",
        opening_line=caller.opening_line,
        airtime_target=(30, 60),
        required_fields=["address", "what_happened"],
        critical_fields=["address"],
        initial_caller_state=initial_state,
        hidden_facts_template=dict(caller.hidden_facts),
    )


async def run_case(ticket_scenario: TicketScenario, *, make_mistakes: bool) -> None:
    print("=" * 70)
    print(f"Сценарий: {ticket_scenario.id}")
    print(f"Ситуация: {ticket_scenario.situation}")
    print(f"Ожидаемая классификация: {ticket_scenario.expected.classification_id} — {ticket_scenario.expected.classification_name}")
    print(f"Ожидаемые службы: {ticket_scenario.expected.services}")
    print(f"Режим: {'С ОШИБКАМИ' if make_mistakes else 'ИДЕАЛЬНЫЙ'}")
    print("=" * 70)

    legacy = scenario_to_legacy(ticket_scenario)
    orch = CallOrchestrator(
        cadet_id=1,
        scenario=legacy,
        difficulty=DifficultyLevel(ticket_scenario.difficulty),
        expected=ticket_scenario.expected,
    )

    start = await orch.start()
    print(f"opening: {start['opening_line']}")
    print()


    await orch.step("Назовите адрес!", duration_sec=3.0)
    await orch.step("Что именно горит?", duration_sec=3.0)


    await orch.update_card("address", ticket_scenario.address)
    await orch.update_card("what_happened", ticket_scenario.situation)

    if not make_mistakes:

        await orch.update_card("caller_fio", ticket_scenario.caller.fio)
        await orch.update_card("caller_role", ticket_scenario.caller.role)
        await orch.update_card("classification_id", ticket_scenario.expected.classification_id)
        await orch.update_card("classification_name", ticket_scenario.expected.classification_name)
        await orch.update_card("sign_l1", ticket_scenario.expected.signs.sign_l1)
        if ticket_scenario.expected.signs.sign_l2:
            await orch.update_card("sign_l2", ticket_scenario.expected.signs.sign_l2)
        if ticket_scenario.expected.signs.sign_l3:
            await orch.update_card("sign_l3", ticket_scenario.expected.signs.sign_l3)


    services = ticket_scenario.expected.services if not make_mistakes else ["police"]
    for svc in services:
        try:
            await orch.activate_service(ServiceType(svc))
        except ValueError:
            pass


    final = await orch.end()
    print("--- ИТОГИ ---")
    print(f"Нарушений всего: {len(final.get('violations', []))}")
    for v in final.get("violations", []):
        if isinstance(v, dict):
            print(f"  • {v.get('type')} | {v.get('description')}")
        else:
            print(f"  • {v.type.value} | {v.description}")
    print()


async def main():
    ticket = load_ticket(1)


    await run_case(ticket.scenarios[0], make_mistakes=False)


    await run_case(ticket.scenarios[0], make_mistakes=True)


    await run_case(ticket.scenarios[1], make_mistakes=False)




    await run_case(ticket.scenarios[1], make_mistakes=True)


if __name__ == "__main__":
    asyncio.run(main())