"""
Экспорт отчёта по звонку в PDF.

Чистый reportlab (platypus). Шрифт с кириллицей:
  1) системный Arial (Windows/macOS — из коробки),
  2) DejaVu в data/fonts/ (кладите оба ttf — гарантия на чужой машине).
"""

from __future__ import annotations

import io
import logging
from pathlib import Path
from typing import Any

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from app.sim112.schemas import CallReport, ViolationType

logger = logging.getLogger("sim112.report.pdf")






_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_LOCAL_FONTS_DIR = _PROJECT_ROOT / "data" / "fonts"

_FONT_PAIRS: list[tuple[Path, Path]] = [

    (Path("C:/Windows/Fonts/arial.ttf"), Path("C:/Windows/Fonts/arialbd.ttf")),
    (Path("C:/Windows/Fonts/DejaVuSans.ttf"),
     Path("C:/Windows/Fonts/DejaVuSans-Bold.ttf")),

    (Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
     Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")),
    (Path("/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"),
     Path("/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf")),

    (Path("/Library/Fonts/Arial.ttf"), Path("/Library/Fonts/Arial Bold.ttf")),
    (Path("/System/Library/Fonts/Supplemental/Arial.ttf"),
     Path("/System/Library/Fonts/Supplemental/Arial Bold.ttf")),

    (_LOCAL_FONTS_DIR / "DejaVuSans.ttf",
     _LOCAL_FONTS_DIR / "DejaVuSans-Bold.ttf"),
]

_FONT_NAMES: tuple[str, str] | None = None


def _register_fonts() -> tuple[str, str]:
    """Регистрирует пару (regular, bold). Возвращает их имена."""
    global _FONT_NAMES
    if _FONT_NAMES is not None:
        return _FONT_NAMES

    for reg, bold in _FONT_PAIRS:
        if not reg.exists():
            continue

        pdfmetrics.registerFont(TTFont("Sim112Sans", str(reg)))
        if bold.exists():
            pdfmetrics.registerFont(TTFont("Sim112Sans-Bold", str(bold)))
            _FONT_NAMES = ("Sim112Sans", "Sim112Sans-Bold")
        else:
            logger.warning(
                "Bold-версия не найдена рядом с %s — использую regular", reg,
            )
            _FONT_NAMES = ("Sim112Sans", "Sim112Sans")

        logger.info(
            "PDF-шрифт: %s (bold: %s)",
            reg, bold if bold.exists() else "= regular",
        )
        return _FONT_NAMES

    raise FileNotFoundError(
        "Не найден шрифт с кириллицей для PDF. Положите "
        f"DejaVuSans.ttf и DejaVuSans-Bold.ttf в {_LOCAL_FONTS_DIR} "
        "или установите Arial (Windows/macOS)."
    )






_BLUE = colors.HexColor("#1a3d6b")
_BLUE_LIGHT = colors.HexColor("#f4f7fb")
_GREY = colors.HexColor("#666666")
_GREEN = "#1b7a2e"
_RED = "#b00020"
_AMBER = "#a07000"

_STYLES_CACHE: dict[str, ParagraphStyle] | None = None


def _styles() -> dict[str, ParagraphStyle]:
    global _STYLES_CACHE
    if _STYLES_CACHE is not None:
        return _STYLES_CACHE

    font_r, font_b = _register_fonts()
    base = getSampleStyleSheet()

    s = {
        "title": ParagraphStyle(
            "t", parent=base["Title"],
            fontName=font_b, fontSize=17, leading=21,
            alignment=TA_LEFT, spaceAfter=2, textColor=_BLUE,
        ),
        "meta": ParagraphStyle(
            "m", fontName=font_r, fontSize=9.5, leading=13, textColor=_GREY,
        ),
        "h2": ParagraphStyle(
            "h2", fontName=font_b, fontSize=12.5, leading=16,
            spaceBefore=10, spaceAfter=5, textColor=_BLUE,
        ),
        "body": ParagraphStyle(
            "b", fontName=font_r, fontSize=10, leading=13, spaceAfter=3,
        ),
        "cell": ParagraphStyle(
            "c", fontName=font_r, fontSize=9, leading=12,
        ),
        "cell_b": ParagraphStyle(
            "cb", fontName=font_b, fontSize=9, leading=12,
        ),
        "cell_head": ParagraphStyle(
            "ch", fontName=font_b, fontSize=9.5, leading=12,
            textColor=colors.white,
        ),
        "grade_num": ParagraphStyle(
            "gn", fontName=font_b, fontSize=40, leading=44,
            alignment=TA_CENTER, textColor=_BLUE,
        ),
        "grade_lbl": ParagraphStyle(
            "gl", fontName=font_r, fontSize=13, leading=17,
            alignment=TA_CENTER, textColor=colors.HexColor("#333333"),
        ),
        "sign": ParagraphStyle(
            "sg", fontName=font_r, fontSize=9, leading=12,
            textColor=_GREY, spaceBefore=10,
        ),
    }
    _STYLES_CACHE = s
    return s






_VIOLATION_LABELS: dict[str, str] = {
    ViolationType.MISSED_CRITICAL_FIELD.value: "Не заполнено критич. поле",
    ViolationType.MISSED_REQUIRED_FIELD.value: "Не заполнено обяз. поле",
    ViolationType.LATE_ACTIVATION.value: "Поздняя активация службы",
    ViolationType.MISSED_ACTIVATION.value: "Служба не активирована",
    ViolationType.CLASSIFICATION_MISMATCH.value: "Неверная классификация ЕКП",
    ViolationType.SIGN_MISMATCH.value: "Неверный признак",
    ViolationType.MISSED_CALLER_FIO.value: "Не записано ФИО заявителя",
    ViolationType.MISSED_CALLER_ROLE.value: "Не определена роль заявителя",
    ViolationType.MISSED_SERVICE.value: "Служба не оповещена",
    ViolationType.EXTRA_SERVICE.value: "Лишняя служба",
    ViolationType.AIRTIME_OUT_OF_RANGE.value: "Эфир вне нормы",
    ViolationType.INTERRUPTED_CALLER.value: "Перебивание заявителя",
    ViolationType.UNPROFESSIONAL_TONE.value: "Некорректный тон",
    ViolationType.INAPPROPRIATE_QUESTION.value: "Неуместный вопрос",
    ViolationType.NO_GROUNDING_FIRST_30S.value: "Нет заземления в 1-е 30 сек",
}


def _table(rows: list[list[Any]], col_widths: list[float], *, header: bool = False) -> Table:
    t = Table(rows, colWidths=col_widths, repeatRows=1 if header else 0)
    style = [
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#cccccc")),
    ]
    if header:
        style += [
            ("BACKGROUND", (0, 0), (-1, 0), _BLUE),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ]
    t.setStyle(TableStyle(style))
    return t


def _ok(cond: bool) -> str:
    """Безопасные маркеры: Arial/DejaVu не всегда имеют U+2713/U+2717."""
    if cond:
        return f"<font color='{_GREEN}'><b>OK</b></font>"
    return f"<font color='{_RED}'><b>X</b></font>"


def _fmt_bool(v: Any) -> str:
    if v is True:
        return "да"
    if v is False:
        return "нет"
    return "—"


def _fmt_val(v: Any) -> str:
    if v is None or v == "":
        return "—"
    if isinstance(v, bool):
        return _fmt_bool(v)
    return str(v)






def _build_expected_section(
    report: CallReport, s: dict[str, ParagraphStyle],
) -> list[Any]:
    exp = report.expected or {}
    card = report.card or {}

    rows: list[list[Any]] = [[
        Paragraph("Поле", s["cell_head"]),
        Paragraph("Эталон", s["cell_head"]),
        Paragraph("Курсант", s["cell_head"]),
        Paragraph("", s["cell_head"]),
    ]]

    exp_id = exp.get("classification_id")
    exp_name = exp.get("classification_name") or ""
    act_id = card.get("classification_id")
    act_name = card.get("classification_name") or ""
    cls_match = exp_id is not None and exp_id == act_id
    rows.append([
        Paragraph("Классификация ЕКП", s["cell"]),
        Paragraph(f"{_fmt_val(exp_id)} — {exp_name}" if exp_id else "—", s["cell"]),
        Paragraph(f"{_fmt_val(act_id)} — {act_name}" if act_id else "—", s["cell"]),
        Paragraph(_ok(cls_match) if exp_id else Paragraph("—", s["cell"]), s["cell"]),
    ])

    signs_exp = exp.get("signs") or {}
    for key, label in (("sign_l1", "Признак 1"),
                       ("sign_l2", "Признак 2"),
                       ("sign_l3", "Признак 3")):
        e = signs_exp.get(key)
        a = card.get(key)
        mark = _ok(e == a) if e else "—"
        rows.append([
            Paragraph(label, s["cell"]),
            Paragraph(_fmt_val(e), s["cell"]),
            Paragraph(_fmt_val(a), s["cell"]),
            Paragraph(mark, s["cell"]),
        ])

    services_exp = set(exp.get("services") or [])
    services_act = set(card.get("services_activated") or [])
    missed = services_exp - services_act
    extra = services_act - services_exp
    mark = _ok(not missed and not extra) if services_exp else "—"
    rows.append([
        Paragraph("Службы", s["cell"]),
        Paragraph(", ".join(sorted(services_exp)) or "—", s["cell"]),
        Paragraph(", ".join(sorted(services_act)) or "—", s["cell"]),
        Paragraph(mark, s["cell"]),
    ])
    if missed or extra:
        bits = []
        if missed:
            bits.append(
                f"<font color='{_RED}'>не оповещены: "
                f"{', '.join(sorted(missed))}</font>"
            )
        if extra:
            bits.append(
                f"<font color='{_AMBER}'>лишние: "
                f"{', '.join(sorted(extra))}</font>"
            )
        rows.append([
            Paragraph("", s["cell"]),
            Paragraph("", s["cell"]),
            Paragraph(" · ".join(bits), s["cell"]),
            Paragraph("", s["cell"]),
        ])

    for key, label in (("victims_present", "Пострадавшие"),
                       ("threat_to_life", "Угроза жизни")):
        e = exp.get(key)
        a = card.get(key)
        mark = _ok(e == a) if e is not None else "—"
        rows.append([
            Paragraph(label, s["cell"]),
            Paragraph(_fmt_bool(e), s["cell"]),
            Paragraph(_fmt_bool(a), s["cell"]),
            Paragraph(mark, s["cell"]),
        ])

    return [_table(rows, [40 * mm, 60 * mm, 60 * mm, 15 * mm], header=True)]


def _build_violations_section(
    report: CallReport, s: dict[str, ParagraphStyle],
) -> list[Any]:
    from app.sim112.audit.violations import VIOLATION_WEIGHTS

    violations = list(report.emergency_audit.violations)
    if not violations:
        return [Paragraph("Нарушений не зафиксировано.", s["body"])]

    rows: list[list[Any]] = [[
        Paragraph("Время", s["cell_head"]),
        Paragraph("Тип", s["cell_head"]),
        Paragraph("Вес", s["cell_head"]),
        Paragraph("Описание", s["cell_head"]),
    ]]
    for v in violations:
        vtype = v.type.value if hasattr(v.type, "value") else str(v.type)
        weight = VIOLATION_WEIGHTS.get(v.type, "—")
        rows.append([
            Paragraph(f"{v.detected_at_sec} с", s["cell"]),
            Paragraph(_VIOLATION_LABELS.get(vtype, vtype), s["cell"]),
            Paragraph(f"−{weight}", s["cell"]),
            Paragraph(v.description, s["cell"]),
        ])
    return [_table(rows, [18 * mm, 40 * mm, 12 * mm, 105 * mm], header=True)]


def _build_card_section(
    report: CallReport, s: dict[str, ParagraphStyle],
) -> list[Any]:
    card = report.card or {}
    if not card:
        return [Paragraph("Карточка недоступна.", s["body"])]

    fields = [
        ("address", "Адрес"),
        ("what_happened", "Что случилось"),
        ("victims_present", "Пострадавшие"),
        ("victims_count", "Количество пострадавших"),
        ("threat_to_life", "Угроза жизни"),
        ("caller_fio", "ФИО заявителя"),
        ("caller_role", "Роль заявителя"),
        ("caller_phone", "Телефон заявителя"),
        ("classification_id", "ЕКП ID"),
        ("classification_name", "ЕКП название"),
        ("sign_l1", "Признак 1"),
        ("sign_l2", "Признак 2"),
        ("sign_l3", "Признак 3"),
    ]
    rows: list[list[Any]] = [[
        Paragraph("Поле", s["cell_head"]),
        Paragraph("Значение", s["cell_head"]),
    ]]
    for key, label in fields:
        rows.append([
            Paragraph(label, s["cell"]),
            Paragraph(_fmt_val(card.get(key)), s["cell"]),
        ])
    for k, v in (card.get("scenario_fields") or {}).items():
        rows.append([
            Paragraph(str(k), s["cell"]),
            Paragraph(_fmt_val(v), s["cell"]),
        ])
    return [_table(rows, [55 * mm, 120 * mm], header=True)]






def render_report_pdf(report: CallReport) -> bytes:
    """Собирает PDF-отчёт и возвращает байты."""
    s = _styles()

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=18 * mm, rightMargin=18 * mm,
        topMargin=16 * mm, bottomMargin=16 * mm,
        title=f"Отчёт 112 — {report.call_id[:8]}",
        author="Система 112 — ИИ-тренажёр",
        subject="Отчёт по тренировке оператора",
    )

    story: list[Any] = []


    story.append(Paragraph(
        "Отчёт по тренировке оператора Системы 112", s["title"],
    ))
    story.append(Spacer(1, 3))
    story.append(Paragraph(
        "ДГОЧСиПБ · ГБУ «Система 112» · г. Москва", s["meta"],
    ))
    story.append(Spacer(1, 8))

    meta_rows = [
        [Paragraph("<b>Звонок</b>", s["cell"]),
         Paragraph(report.call_id, s["cell"])],
        [Paragraph("<b>Сценарий</b>", s["cell"]),
         Paragraph(report.scenario_title or str(report.scenario_id), s["cell"])],
        [Paragraph("<b>Курсант</b>", s["cell"]),
         Paragraph(report.cadet_name or f"ID {report.cadet_id}", s["cell"])],
        [Paragraph("<b>Дата</b>", s["cell"]),
         Paragraph(report.created_at.strftime("%d.%m.%Y %H:%M"), s["cell"])],
        [Paragraph("<b>Длительность</b>", s["cell"]),
         Paragraph(f"{report.duration_sec} сек", s["cell"])],
    ]
    story.append(_table(meta_rows, [30 * mm, 145 * mm]))
    story.append(Spacer(1, 8))


    if report.grade >= 75:
        grade_color = _GREEN
    elif report.grade >= 60:
        grade_color = _AMBER
    else:
        grade_color = _RED

    grade_tbl = Table(
        [[
            Paragraph(
                f"<font color='{grade_color}'>{report.grade}</font>",
                s["grade_num"],
            ),
            Paragraph(
                f"<b>из 100</b><br/>{report.grade_label}<br/>"
                f"<font size=9 color='#666666'>"
                f"Нарушений: {len(report.emergency_audit.violations)}"
                f"</font>",
                s["grade_lbl"],
            ),
        ]],
        colWidths=[45 * mm, 130 * mm],
    )
    grade_tbl.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("BACKGROUND", (0, 0), (-1, -1), _BLUE_LIGHT),
        ("BOX", (0, 0), (-1, -1), 0.8, _BLUE),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))
    story.append(grade_tbl)
    story.append(Spacer(1, 10))


    story.append(Paragraph("Ключевые метрики", s["h2"]))
    pa = report.protocol_adherence
    air = report.airtime_control

    def _ok_html(cond: bool) -> str:
        return _ok(cond)

    metric_rows: list[list[Any]] = [[
        Paragraph("Метрика", s["cell_head"]),
        Paragraph("Значение", s["cell_head"]),
        Paragraph("Норматив", s["cell_head"]),
        Paragraph("Оценка", s["cell_head"]),
    ]]

    metric_rows.append([
        Paragraph("Protocol Adherence", s["cell"]),
        Paragraph(f"{pa.percent}%", s["cell_b"]),
        Paragraph("≥ 80%", s["cell"]),
        Paragraph(_ok_html(pa.percent >= 80), s["cell"]),
    ])
    metric_rows.append([
        Paragraph("Airtime (доля диспетчера)", s["cell"]),
        Paragraph(f"{air.dispatcher_percent}%", s["cell_b"]),
        Paragraph(f"{air.target_min}–{air.target_max}%", s["cell"]),
        Paragraph(_ok_html(air.in_range), s["cell"]),
    ])
    metric_rows.append([
        Paragraph("Паника заявителя (конец)", s["cell"]),
        Paragraph(str(report.final_panic_index), s["cell_b"]),
        Paragraph("—", s["cell"]),
        Paragraph("—", s["cell"]),
    ])
    metric_rows.append([
        Paragraph("Комплаенс заявителя (конец)", s["cell"]),
        Paragraph(str(report.final_compliance_index), s["cell_b"]),
        Paragraph("—", s["cell"]),
        Paragraph("—", s["cell"]),
    ])
    story.append(_table(
        metric_rows, [65 * mm, 30 * mm, 35 * mm, 45 * mm], header=True,
    ))
    story.append(Spacer(1, 8))


    if report.expected:
        story.append(Paragraph("Соответствие эталону", s["h2"]))
        story.extend(_build_expected_section(report, s))
        story.append(Spacer(1, 8))


    violations = list(report.emergency_audit.violations)
    story.append(Paragraph(f"Нарушения ({len(violations)})", s["h2"]))
    story.extend(_build_violations_section(report, s))
    story.append(Spacer(1, 8))


    story.append(Paragraph(
        "Карточка вызова (заполнено курсантом)", s["h2"],
    ))
    story.extend(_build_card_section(report, s))


    story.append(Spacer(1, 14))
    story.append(Paragraph(
        "Инструктор _________________________     "
        "Дата _________________",
        s["sign"],
    ))

    doc.build(story)
    return buf.getvalue()