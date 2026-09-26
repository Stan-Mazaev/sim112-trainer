"""
Прогон всех билетных сценариев через CallOrchestrator без HTTP и голоса.
Цель: убедиться, что ни один из билетов не падает на старте/шагах/PDF.
"""

import asyncio
import json
import sys
import traceback
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from app.sim112.schemas import (
    CallerState,
    DifficultyLevel,
    Scenario,
    ScenarioId,
    ServiceType,
)
from app.sim112.scenarios.schemas import Expected, Ticket
from app.sim112.session.orchestrator import CallOrchestrator
from app.sim112.report.generator import generate_report
from app.sim112.report.pdf import render_report_pdf


TICKETS_DIR = _PROJECT_ROOT / "app" / "sim112" / "scenarios" / "tickets"


def _ticket_to_legacy_scenario(sc) -> Scenario:
    c = sc.caller
    return Scenario(
        id=ScenarioId.FIRE_APARTMENT,
        title=(
            f"Билет {sc.ticket_number}, случай {sc.case_number} — "
            f"{sc.situation}"
        ),
        description=sc.situation,
        difficulty=DifficultyLevel(sc.difficulty),
        initial_prompt="",
        opening_line=c.opening_line,
        airtime_target=(30, 60),
        required_fields=["address", "what_happened"],
        critical_fields=["address"],
        initial_caller_state=CallerState(
            panic=c.initial_panic,
            trust=c.initial_trust,
            cooperation=c.initial_cooperation,
            phase="shock",
            hidden_facts=dict(c.hidden_facts),
        ),
        hidden_facts_template=dict(c.hidden_facts),
    )


async def run_one(sc) -> dict:
    scenario = _ticket_to_legacy_scenario(sc)
    expected = Expected.model_validate(sc.expected.model_dump())

    orch = CallOrchestrator(
        cadet_id=1,
        scenario=scenario,
        difficulty=scenario.difficulty,
        expected=expected,
    )
    orch.cadet_name = "Смоук-тест"

    await orch.start()
    await orch.step("Слушайте меня внимательно. Что случилось?")
    await orch.step("Назовите адрес.")
    await orch.update_card("address", sc.address)
    await orch.update_card("what_happened", sc.situation)
    await orch.activate_service(ServiceType.POLICE)

    final = await orch.end(reason="smoke")
    report = generate_report(orch, final)
    pdf_bytes = render_report_pdf(report)

    return {
        "id": sc.id,
        "grade": report.grade,
        "violations": len(report.emergency_audit.violations),
        "pdf_size": len(pdf_bytes),
    }


async def main() -> int:
    files = sorted(TICKETS_DIR.glob("ticket_*.json"))
    if not files:
        print(f"Нет билетов в {TICKETS_DIR}")
        return 1

    total = 0
    ok = 0
    fails: list[tuple[str, str]] = []

    for path in files:
        try:
            with path.open(encoding="utf-8") as f:
                raw = json.load(f)
            ticket = Ticket.model_validate(raw)
        except Exception as exc:
            print(f"[FAIL load] {path.name}: {exc}")
            fails.append((path.name, traceback.format_exc(limit=3)))
            continue

        print(f"\n=== {path.name} (билет {ticket.ticket_number}) ===")
        for sc in ticket.scenarios:
            total += 1
            try:
                r = await run_one(sc)
                print(
                    f"  OK   {r['id']:<24} "
                    f"grade={r['grade']:>3}  "
                    f"violations={r['violations']:>2}  "
                    f"pdf={r['pdf_size']:>6}б"
                )
                ok += 1
            except Exception as exc:
                tb = traceback.format_exc(limit=3)
                print(f"  FAIL {sc.id}: {exc}")
                fails.append((sc.id, tb))

    print(f"\n{'='*60}")
    print(f"Итого: {ok}/{total} OK")
    if fails:
        print(f"Провалов: {len(fails)}")
        for sid, tb in fails[:5]:
            print(f"\n--- {sid} ---")
            print(tb)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))