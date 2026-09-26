"""Смоук: старт → пара реплик → end → PDF на диск. Без HTTP, без TTS."""
import asyncio
import sys
from pathlib import Path


_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from app.sim112.schemas import DifficultyLevel, ServiceType
from app.sim112.scenarios.registry import get_registry
from app.sim112.session.orchestrator import CallOrchestrator
from app.sim112.report.generator import generate_report
from app.sim112.report.pdf import render_report_pdf


async def main():

    import json
    ticket_path = _PROJECT_ROOT / "app" / "sim112" / "scenarios" / "tickets" / "ticket_20.json"
    if not ticket_path.exists():

        ticket_path = _PROJECT_ROOT / "sim112" / "scenarios" / "tickets" / "ticket_20.json"
    assert ticket_path.exists(), f"Не найден ticket_20.json ни в одном из путей"

    with ticket_path.open(encoding="utf-8") as f:
        ticket = json.load(f)
    sc = ticket["scenarios"][0]


    from app.sim112.schemas import Scenario, ScenarioId, CallerState
    scenario = Scenario(
        id=ScenarioId.FIRE_APARTMENT,
        title=sc["id"],
        description=sc["situation"],
        difficulty=DifficultyLevel(sc["difficulty"]),
        initial_prompt="",
        opening_line=sc["caller"]["opening_line"],
        airtime_target=(30, 60),
        required_fields=["address", "what_happened"],
        critical_fields=["address"],
        initial_caller_state=CallerState(
            panic=sc["caller"]["initial_panic"],
            trust=sc["caller"]["initial_trust"],
            cooperation=sc["caller"]["initial_cooperation"],
            phase="shock",
            hidden_facts=dict(sc["caller"]["hidden_facts"]),
        ),
        hidden_facts_template=dict(sc["caller"]["hidden_facts"]),
    )

    from app.sim112.scenarios.schemas import Expected
    expected = Expected.model_validate(sc["expected"])

    orch = CallOrchestrator(
        cadet_id=1,
        scenario=scenario,
        difficulty=scenario.difficulty,
        expected=expected,
    )
    orch.cadet_name = "Иванов Иван Иванович"
    await orch.start()


    await orch.step("Слушайте меня внимательно. Что случилось?")
    await orch.step("Назовите адрес.")
    await orch.update_card("address", sc["address"])
    await orch.update_card("what_happened", sc["situation"])
    await orch.activate_service(ServiceType.POLICE)

    final = await orch.end(reason="completed")
    report = generate_report(orch, final)

    pdf_bytes = render_report_pdf(report)
    out = _PROJECT_ROOT / "smoke_report.pdf"
    out.write_bytes(pdf_bytes)
    print(f"OK: {out.resolve()} ({len(pdf_bytes)} байт)")
    print(f"grade={report.grade}, violations={len(report.emergency_audit.violations)}")


if __name__ == "__main__":
    asyncio.run(main())