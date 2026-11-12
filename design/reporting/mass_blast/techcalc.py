"""Документ 2: технический расчёт массового взрыва (прил. 10 ФНП 494, эталон v0.11, стр. 7–8).

Разделы 1–17 — из `blocks_v2[i].technical_calculation` (PR 2): подпись,
значение, единица, подстановка. Формулы — общий вид формы набором
(`formulas.py`), разд. 7 — рисунок колонки и таблица значений, разд. 10–12 —
одна таблица расхода, разд. 13 — с новой страницы (как в эталоне).
"""
from __future__ import annotations

from typing import Any, Mapping, Sequence

from reportlab.lib.units import mm
from reportlab.platypus import KeepTogether, PageBreak, Table, TableStyle

from design.reporting.brand import LINE, ORGANIZATION
from design.reporting.mass_blast.charge_column import ChargeColumn
from design.reporting.mass_blast.common import (
    DASH,
    RED_HEX,
    cell,
    grid_style,
    num,
    p,
    rich,
    short,
    signature_row,
    spacer,
    text,
    value_text,
)
from design.reporting.mass_blast.formulas import section_formulas

LABEL_W = 80 * mm
VALUE_W = 30 * mm
UNIT_W = 12 * mm
# Виды дек проекта блока (`design.models.DECK_KINDS`) — словами для печати.
DECK_LABELS = {
    "stemming": "забойка", "charge": "ВВ", "bulk_explosive": "ВВ", "packaged_explosive": "патронированное ВВ",
    "air": "воздушный промежуток", "air_deck": "воздушный промежуток", "inert_deck": "инертный промежуток",
    "water_deck": "водный промежуток", "primer": "ПД", "booster": "ПД", "detonator": "детонатор",
}
APPENDIX_LINE = (
    "Графические приложения: Г.1 схема расположения скважин; Г.2 поперечные профили через заряды; Г.3 схема заряжания, "
    "забойки и отвода оборудования; Г.4 схема взрывной сети; Г.5 ситуационный план с опасной зоной, постами охраны и "
    "взрывной станцией. План блока и схемы фактического расположения скважин подписываются исполнителями съёмки "
    "с указанием должностей."
)


def _heading(number: str, title: str, width: float) -> Table:
    table = Table([[p("", markup=f'<font color="{RED_HEX}">{rich(number)}.</font> {rich(title)}', style="section")]],
                  colWidths=[width])
    table.setStyle(TableStyle([
        ("LINEABOVE", (0, 0), (-1, 0), 0.5, LINE), ("LEFTPADDING", (0, 0), (-1, -1), 6 * mm),
        ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
    ]))
    return table


def _note(item: Mapping[str, Any]) -> str:
    return "; ".join(part for part in (text(item.get("substitution")), text(item.get("note"))) if part)


def _items_table(items: Sequence[Mapping[str, Any]], width: float) -> Table | None:
    if not items:
        return None
    note_w = width - 6 * mm - LABEL_W - VALUE_W - UNIT_W
    rows: list[list] = []
    style: list[tuple] = [
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 2), ("TOPPADDING", (0, 0), (-1, -1), 0.3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0.3), ("LEFTPADDING", (4, 0), (4, -1), 3 * mm),
    ]
    for index, item in enumerate(items):
        if "text" in item:
            rows.append(["", p(item["text"], "item"), "", "", ""])
            style.append(("SPAN", (1, index), (4, index)))
            continue
        value = item.get("value")
        if isinstance(value, str):
            note = _note(item)
            rows.append(["", p(item.get("label"), "item"), p(value, "item_b"), "", p(note, "note")])
            style.append(("SPAN", (2, index), (3, index) if note else (4, index)))
        else:
            rows.append([
                "", p(item.get("label"), "item"), p(value_text(value), "item_br"), p(item.get("unit"), "item_grey"),
                p(_note(item), "note"),
            ])
    table = Table(rows, colWidths=[6 * mm, LABEL_W, VALUE_W, UNIT_W, note_w])
    table.setStyle(TableStyle(style))
    return table


def _construction(section: Mapping[str, Any], width: float) -> list:
    """Рисунок колонки на группу конструкций (до 3 в ряд) и таблица значений:
    графа на конструкцию."""

    constructions = list(section.get("constructions") or [])[:3]
    if not constructions:
        return [p("Конструкция заряда не определена: скважины не заряжены в проекте блока.", "note")]
    material = text(section.get("stemming_material")) or DASH
    several = len(constructions) > 1

    def values(item: Mapping[str, Any]) -> list[str]:
        decks = " — ".join(DECK_LABELS.get(text(d), text(d)) for d in item.get("decks") or [])
        products = ", ".join(text(d) for d in item.get("products") or [])
        return [
            f"{decks} ({products})" if products else decks or DASH,
            value_text(item.get("depth_mean_m")),
            value_text(item.get("bench_height_mean_m")),
            value_text(item.get("subdrill_mean_m")),
            f"{value_text(item.get('stemming_mean_m'))} / {value_text(item.get('stemming_min_m'))}",
            value_text(item.get("charge_length_mean_m")),
            value_text(item.get("primer_from_bottom_m")),
            value_text(item.get("primers_per_hole")),
            material,
            value_text(item.get("stemming_to_d_min")),
        ]

    labels = [
        ("Конструкция", ""), ("L — глубина скважины (ср.)", "м"), ("H_у — высота уступа (ср.)", "м"),
        ("l_пер — перебур (ср.)", "м"), ("l_заб — забойка (ср. / мин.)", "м"), ("l_зар — длина заряда (ср.)", "м"),
        ("l_б — боевик от дна скважины", "м"), ("ПД в скважине, шт", ""), ("Материал забойки", ""),
        ("Мин. забойка / d (для K_з, п. 803)", ""),
    ]
    columns = [values(item) for item in constructions]
    drawing_w = 36 * mm if not several else min(30 * mm, (width * 0.5) / len(constructions) - 2 * mm)
    drawings_w = len(constructions) * (drawing_w + 2 * mm) + 6 * mm
    gap = 4 * mm   # просвет между рисунком (его подписями справа) и таблицей значений
    table_w = width - drawings_w - gap
    value_w = (table_w - 44 * mm - 8 * mm) / len(constructions)
    rows: list[list] = []
    if several:
        rows.append([p("", "cons_label")] + [p(f"Конструкция {n} — {constructions[n - 1].get('hole_count') or DASH} скв.", "cons_value")
                                       for n in range(1, len(constructions) + 1)] + [""])
    for index, (label, unit) in enumerate(labels):
        rows.append([p(label, "cons_label")] + [p(column[index], "cons_value") for column in columns] + [p(unit, "cons_label")])
    table = Table(rows, colWidths=[44 * mm] + [value_w] * len(constructions) + [8 * mm])
    table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0.4), ("BOTTOMPADDING", (0, 0), (-1, -1), 0.4),
    ]))
    pictures = Table(
        [[ChargeColumn(drawing_w, double_primer=int(item.get("primers_per_hole") or 1) > 1,
                       side_labels=index == len(constructions) - 1)
          for index, item in enumerate(constructions)]],
        colWidths=[drawing_w + 2 * mm] * len(constructions),
    )
    pictures.setStyle(TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 2 * mm)]))
    block = Table([[pictures, table]], colWidths=[drawings_w, table_w + gap])
    block.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("LEFTPADDING", (0, 0), (0, 0), 6 * mm), ("LEFTPADDING", (1, 0), (1, 0), gap),
    ]))
    return [block]


def _mass_text(line: Mapping[str, Any]) -> str:
    """Масса строки расхода; у ПД без массы в справочнике (`primer_mass_unknown`,
    расход пишет 0 или только известную часть) — не число, а пометка."""

    mass = line.get("mass_kg")
    if line.get("warning") == "primer_mass_unknown":
        return f"не менее {num(mass, 1)}" if mass else "не известна"
    return num(mass, 1) if mass is not None else DASH


def _consumption(section: Mapping[str, Any], width: float) -> Table:
    rows = [[cell(h, "th") for h in ("п.", "Наименование", "Количество", "Ед.", "Масса, кг")]]
    lines = list(section.get("consumption") or [])
    for line in lines:
        quantity = line.get("quantity")
        # Килограммы — с той же точностью, что и графа «Масса, кг» (60,4 кг), штуки — целыми.
        digits = 1 if text(line.get("unit")) == "кг" else 0
        mass = line.get("mass_kg")
        rows.append([
            cell(line.get("item"), "td_red"),
            cell(f"{text(line.get('name'))}, {short(line.get('delay_ms'), 1)} мс" if line.get("delay_ms") is not None
                 else line.get("name")),
            cell(num(quantity, digits) if quantity is not None else DASH, "td_bc"),
            cell(line.get("unit"), "td_c"), cell(_mass_text(line), "td_r"),
        ])
    widths = [10 * mm, width - 10 * mm - 28 * mm - 14 * mm - 26 * mm, 28 * mm, 14 * mm, 26 * mm]
    table = Table(rows, colWidths=widths, repeatRows=1)
    table.setStyle(TableStyle(grid_style(rows=len(lines), padding=1)))
    return table


def _objects(section: Mapping[str, Any], width: float) -> Table:
    """Охраняемые объекты: тип объекта и определяющий фактор (`factor`) — раздельно."""

    objects = list(section.get("objects") or [])
    heads = ("Охраняемый объект", "Тип", "Определяющий фактор", "Расстояние, м", "Безопасное, м", "Положение")
    rows = [[cell(h, "th") for h in heads]]
    style_extra: list[tuple] = []
    for index, item in enumerate(objects, start=1):
        inside = text(item.get("position")) == "В ЗОНЕ"
        rows.append([
            cell(item.get("name")), cell(item.get("kind_label") or item.get("kind"), "td_c"), cell(item.get("factor"), "td_c"),
            cell(num(item.get("distance_m"), 0), "td_c"), cell(num(item.get("required_m"), 0), "td_c"),
            cell(item.get("position"), "td_red" if inside else "td_bc"),
        ])
        if inside:
            style_extra.append(("BACKGROUND", (5, index), (5, index), "#FCEDEE"))
    # Пустые строки для дописывания, как в эталоне (не меньше трёх строк таблицы).
    blank = max(0, 3 - len(objects))
    rows += [[""] * len(heads) for _ in range(blank)]
    widths = [width * 0.3, width * 0.13, width * 0.17, width * 0.13, width * 0.13]
    widths.append(width - sum(widths))
    table = Table(rows, colWidths=widths, rowHeights=[None] + [None] * len(objects) + [4.2 * mm] * blank)
    table.setStyle(TableStyle(grid_style(rows=len(rows) - 1, padding=1) + style_extra))
    return table


def techcalc_story(context: Mapping[str, Any], block_index: int, width: float) -> list:
    block = (context.get("blocks_v2") or [])[block_index]
    v1_block = (context.get("blocks") or [{}])[block_index] if block_index < len(context.get("blocks") or []) else {}
    project = context.get("project") or {}
    requisites = context.get("requisites") or {}
    approver = requisites.get("contractor_approver") or {}
    contractor = text(requisites.get("contractor_name")) or ORGANIZATION
    name = text(approver.get("name"))
    approve = Table([[
        "",
        [
            p("УТВЕРЖДАЮ", "cap"), spacer(1),
            p(" ".join(filter(None, (text(approver.get("position")), contractor))) or " ", "body"),
            p(f"___________  {name}    «___» _______ 20__ г." if name else "___________    «___» _______ 20__ г.", "body"),
        ],
    ]], colWidths=[width * 0.5, width * 0.5])
    approve.setStyle(TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 0), ("VALIGN", (0, 0), (-1, -1), "TOP")]))
    horizon = text(block.get("horizon") or v1_block.get("horizon"))
    heading = " · ".join(filter(None, (
        "ТЕХНИЧЕСКИЙ РАСЧЁТ МАССОВОГО ВЗРЫВА", text(project.get("object_name")),
        f"гор. {horizon} м" if horizon else "", f"блок № {text(block.get('code'))}" if text(block.get("code")) else "",
    )))
    story: list = [approve, spacer(5), p(heading, "doc_red"), spacer(1.5)]
    for section in block.get("technical_calculation") or []:
        number = text(section.get("number"))
        if number == "13":
            story.append(PageBreak())
        part: list = [_heading(number, section.get("title"), width)]
        formulas = section_formulas(number)
        for formula in formulas:
            formula.hAlign = "LEFT"
            part.append(Table([["", formula]], colWidths=[6 * mm, width - 6 * mm], style=[
                ("LEFTPADDING", (0, 0), (-1, -1), 0), ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ]))
        if number == "7":
            part += _construction(section, width)
        elif number == "10–12" or "consumption" in section:
            part.append(_consumption(section, width))
        if number == "17" or "objects" in section:
            part += [spacer(1), _objects(section, width)]
        items = _items_table(section.get("items") or [], width)
        if items is not None:
            part.append(items)
        story.append(KeepTogether(part))
    story += [
        spacer(8),
        signature_row("Расчёт составил:", requisites.get("made_by"), width),
        signature_row("Расчёт проверил:", requisites.get("checked_by"), width),
        spacer(3), p(APPENDIX_LINE, "note"),
    ]
    return story


__all__ = ["techcalc_story"]
