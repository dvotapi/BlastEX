"""Документ 4: распорядок проведения массового взрыва (прил. 12 ФНП 494, эталон v0.11, стр. 13–14).

Два «УТВЕРЖДАЮ» (заказчик слева, подрядчик справа, п. 414), пп. 1–20 —
«пункт / значение», ответственные (пп. 8, 18, 21–28, 36) — одной таблицей,
сигналы пп. 29–33 — «действие / сигнал / время», п. 34, посты п. 35,
ознакомление п. 37, подписи «составил / проверил». Данные — `schedule` (PR 2).
"""
from __future__ import annotations

from typing import Any, Mapping

from reportlab.lib.units import mm
from reportlab.platypus import KeepTogether, Table, TableStyle

from design.reporting.brand import LINE, ORGANIZATION
from design.reporting.mass_blast.common import (
    RED_HEX,
    cell,
    date,
    date_short,
    grid_style,
    p,
    rich,
    signature_row,
    spacer,
    text,
)

APPROVAL_NOTE = (
    "п. 414: утверждают технические руководители заказчика и подрядчика или лица, назначенные приказом "
    "(тогда под подписью — приказ № и дата)"
)


def _approver(signer: Mapping[str, Any], organization: str) -> list:
    name = text(signer.get("name"))
    position = " ".join(filter(None, (text(signer.get("position")), organization)))
    authority = text(signer.get("authority"))
    lines = [
        p("УТВЕРЖДАЮ", "cap"), spacer(0.8), p(position or " ", "body"),
        p(f"___________  {name}     «___» _______ 20__ г." if name else "___________     «___» _______ 20__ г.", "body"),
    ]
    if authority:
        lines.append(p(authority, "small"))
    return lines


def _point_markup(point: str, title: str) -> str:
    number = f'<font color="{RED_HEX}"><b>{rich(point)}.</b></font> ' if point else ""
    return number + rich(title)


def _point_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        cells = [
            p(date_short(value.get("from_date")), "bold"), p(date_short(value.get("to_date")), "bold"),
            p(text(value.get("shift_from")), "bold"),
            p("", markup=f'<font color="{RED_HEX}"><b>{rich(value.get("blast_day_until"))}</b></font>'),
        ]
        table = Table([cells], colWidths=[20 * mm, 20 * mm, 16 * mm, 16 * mm])
        table.setStyle(TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 0), ("TOPPADDING", (0, 0), (-1, -1), 0),
                                   ("BOTTOMPADDING", (0, 0), (-1, -1), 0)]))
        return table
    value = text(value)
    if len(value) == 10 and value[4] == "-" and value[7] == "-":
        value = date(value)
    return p(value, "bold")


def _points(schedule: Mapping[str, Any], width: float) -> Table:
    rows = [[p("", "body", markup=_point_markup(text(item.get("point")), text(item.get("title")))), _point_value(item.get("value"))]
            for item in schedule.get("points") or []]
    table = Table(rows, colWidths=[width * 0.48, width * 0.52])
    table.setStyle(TableStyle([
        ("LINEBELOW", (0, 0), (-1, -1), 0.4, LINE), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (0, -1), 6 * mm), ("TOPPADDING", (0, 0), (-1, -1), 1.2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1.6),
    ]))
    return table


def _section_title(point: str, title: str) -> Any:
    return p("", "section", markup=_point_markup(point, title))


def _responsibilities(block: Mapping[str, Any], width: float) -> list:
    rows = [[cell(h, "th") for h in ("п.", "Обязанность", "Должность, фамилия, инициалы", "Подпись")]]
    items = list(block.get("rows") or [])
    for item in items:
        rows.append([cell(item.get("points"), "td_red"), cell(item.get("duty")), cell(item.get("who")), ""])
    table = Table(rows, colWidths=[13 * mm, width * 0.46, width - 13 * mm - width * 0.46 - 26 * mm, 26 * mm], repeatRows=1)
    table.setStyle(TableStyle(grid_style(rows=len(items), zebra=False, padding=2.2)))
    return [_section_title(text(block.get("point")), text(block.get("title"))), spacer(0.8), table]


def _signals(block: Mapping[str, Any], width: float) -> list:
    rows = [[cell(h, "th") for h in ("п.", "Действие", "Сигнал", "Время")]]
    items = list(block.get("rows") or [])
    for item in items:
        time = text(item.get("time"))
        if time and item.get("not_earlier"):
            time = f"не ранее {time}"
        rows.append([cell(item.get("point"), "td_red"), cell(item.get("action")), cell(item.get("signal")), cell(time, "td_bc")])
    table = Table(rows, colWidths=[13 * mm, width - 13 * mm - 36 * mm - 26 * mm, 36 * mm, 26 * mm], repeatRows=1)
    table.setStyle(TableStyle(grid_style(rows=len(items), zebra=False, padding=2.5)))
    return [_section_title(text(block.get("point")), text(block.get("title"))), spacer(0.8), table]


def _posts(block: Mapping[str, Any], width: float) -> list:
    title = text(block.get("title"))
    instructed = text(block.get("instructed_by"))
    if instructed:
        title += f"; инструктаж и расстановку производит {instructed}"
    rows = [[cell(h, "th") for h in ("№", "Место поста", "Выставлен", "Постовой (Ф. И. О.)", "Подпись")]]
    items = list(block.get("rows") or [])
    for item in items:
        rows.append([cell(item.get("number"), "td_c"), cell(item.get("location")), cell(item.get("posted_at"), "td_c"),
                     cell(item.get("guard")), ""])
    rows.append(["", "", "", "", ""])
    table = Table(rows, colWidths=[10 * mm, width * 0.44, 24 * mm, width - 10 * mm - width * 0.44 - 24 * mm - 22 * mm, 22 * mm],
                  rowHeights=[None] + [None] * len(items) + [4.5 * mm], repeatRows=1)
    table.setStyle(TableStyle(grid_style(rows=len(items) + 1, zebra=False, padding=1.2)))
    return [_section_title(text(block.get("point")), title), spacer(0.8), table]


def _familiarization(block: Mapping[str, Any], width: float) -> list:
    rows = [[cell(h, "th") for h in ("№", "Фамилия, инициалы", "Должность", "Дата", "Подпись")]]
    items = list(block.get("rows") or [])
    for index, item in enumerate(items, start=1):
        rows.append([cell(index, "td_c"), cell(item.get("name")), cell(item.get("position")), "", ""])
    table = Table(rows, colWidths=[10 * mm, width * 0.36, width - 10 * mm - width * 0.36 - 44 * mm, 22 * mm, 22 * mm],
                  rowHeights=[None] + [4.6 * mm] * len(items), repeatRows=1)
    table.setStyle(TableStyle(grid_style(rows=len(items), zebra=False, padding=1)))
    return [_section_title(text(block.get("point")), text(block.get("title"))), spacer(0.8), table]


def schedule_story(context: Mapping[str, Any], width: float) -> list:
    schedule = context.get("schedule") or {}
    requisites = context.get("requisites") or {}
    blocks = list(context.get("blocks") or [])
    customer = text(requisites.get("customer_name"))
    contractor = text(requisites.get("contractor_name")) or ORGANIZATION
    approvals = Table(
        [[_approver(requisites.get("customer_approver") or {}, customer),
          _approver(requisites.get("contractor_approver") or {}, contractor)]],
        colWidths=[width / 2, width / 2],
    )
    approvals.setStyle(TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 0), ("VALIGN", (0, 0), (-1, -1), "TOP")]))
    codes = ", ".join(text(b.get("code")) for b in blocks if text(b.get("code")))
    horizons = ", ".join(dict.fromkeys(text(b.get("horizon")) for b in blocks if text(b.get("horizon"))))
    heading = " · ".join(filter(None, (
        "РАСПОРЯДОК ПРОВЕДЕНИЯ МАССОВОГО ВЗРЫВА",
        f"блок № {codes}" if codes else "", f"гор. {horizons} м" if horizons else "",
    )))
    story: list = [approvals, spacer(0.5), p(APPROVAL_NOTE, "small"), spacer(1.5), p(heading, "doc_red"), spacer(1),
                   _points(schedule, width), spacer(5)]
    if schedule.get("responsibilities"):
        story += [KeepTogether(_responsibilities(schedule["responsibilities"], width)), spacer(5)]
    if schedule.get("signals"):
        story += [KeepTogether(_signals(schedule["signals"], width)), spacer(4)]
    refusal = schedule.get("refusal")
    if refusal:
        row = Table([[p("", "body", markup=_point_markup(text(refusal.get("point")), text(refusal.get("title")))),
                      p(refusal.get("value"), "bold")]], colWidths=[width * 0.48, width * 0.52])
        row.setStyle(TableStyle([("LINEBELOW", (0, 0), (-1, -1), 0.4, LINE), ("LEFTPADDING", (0, 0), (0, -1), 6 * mm),
                                 ("VALIGN", (0, 0), (-1, -1), "MIDDLE")]))
        story += [row, spacer(5)]
    if schedule.get("posts"):
        story += [KeepTogether(_posts(schedule["posts"], width)), spacer(5)]
    if schedule.get("familiarization"):
        story += [KeepTogether(_familiarization(schedule["familiarization"], width)), spacer(6)]
    story += [
        signature_row("Распорядок составил:", requisites.get("made_by"), width),
        signature_row("Распорядок проверил:", requisites.get("checked_by"), width),
    ]
    return story


__all__ = ["schedule_story"]
