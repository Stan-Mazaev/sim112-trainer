"""
Генератор финального отчёта по звонку.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from app.sim112.schemas import CallReport


def _grade_label(grade: int) -> str:
    if grade >= 90:
        return "отлично"
    if grade >= 75:
        return "хорошо"
    if grade >= 60:
        return "удовлетворительно"
    if grade >= 40:
        return "неудовлетворительно"
    return "провал"


def compute_grade(final_data: dict[str, Any]) -> int:
    from app.sim112.audit.violations import VIOLATION_WEIGHTS

    score = 100
    for violation in final_data.get("violations", []):
        weight = VIOLATION_WEIGHTS.get(violation.type, 5)
        score -= weight
    return max(0, min(100, score))


def generate_report(orchestrator, final_data: dict[str, Any]) -> CallReport:
    grade = compute_grade(final_data)


    expected_dump: dict[str, Any] | None = None
    exp = getattr(orchestrator, "expected", None)
    if exp is not None:
        expected_dump = exp.model_dump() if hasattr(exp, "model_dump") else dict(exp)


    card_dump = orchestrator.card_manager.card.model_dump()

    return CallReport(
        call_id=final_data["call_id"],
        cadet_id=final_data["cadet_id"],
        scenario_id=final_data["scenario_id"],
        duration_sec=final_data["duration_sec"],
        protocol_adherence=final_data["protocol_adherence"],
        airtime_control=final_data["airtime_control"],
        emergency_audit=final_data["emergency_audit"],
        protocol_alert=final_data["protocol_alert"],
        final_panic_index=final_data["caller_state"].panic,
        final_compliance_index=final_data["caller_state"].compliance,
        grade=grade,
        grade_label=_grade_label(grade),
        recommendations=[],
        timeline=final_data["timeline"],
        cadet_name=getattr(orchestrator, "cadet_name", None),
        scenario_title=getattr(orchestrator.scenario, "title", None),
        expected=expected_dump,
        card=card_dump,
        created_at=datetime.utcnow(),
    )