"""Документы 6–10 — слои дня взрыва (TASK-018 §2, §2.1; эталон v0.11, стр. 21–30).

Источник — ревизия слоя (`mass_blast_layer_revisions.context`): `seed`
(перенесено из проекта), `payload` (введено вручную), `view` (строки и итоги
наряда). Поля, которые заполняют на месте от руки, — белые клетки с рамкой
без заливки. Нумерация — своя у каждого документа («Стр. 1 из 1»).
"""
from __future__ import annotations

from typing import Any, Callable, Mapping

from reportlab.lib.colors import white
from reportlab.lib.units import mm
from reportlab.platypus import KeepInFrame, Table, TableStyle

from design.reporting.brand import FONT_FALLBACK, GRAPHITE, GREY, LINE, ORGANIZATION, register_fallback_font
from design.reporting.mass_blast import frame
from design.reporting.mass_blast.common import (
    DASH,
    RED_HEX,
    cell,
    date,
    grid_style,
    num,
    p,
    person_line,
    rich,
    short,
    spacer,
    text,
)
from design.reporting.mass_blast.frame import HEADER_H, Margins, Part

LAYER_DOCUMENTS = {
    "READINESS_ACT": ("Акт готовности блока", "Акт готовности блока к заряжанию (приложение № 13 к ФНП 494, п. 413)"),
    "NOTIFICATION": ("Уведомление", ""),
    "NARYAD": ("Наряд-путёвка", ""),
    "TALON": ("Талон-допуск", "Талон-допуск после массового взрыва (форма Общества)"),
    "ACCEPTANCE_ACT": ("Акт приёмки работ", "Акт приёмки выполненных работ (форма по договору подряда)"),
}
TALON_COPIES = (
    "Экземпляр 1 — представителю заказчика",
    "Экземпляр 2 — руководителю взрывных работ (в дело проекта)",
)
CUT_LINE = "✂ линия отреза"
MONTHS = ("января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа", "сентября", "октября", "ноября",
          "декабря")


# --- общее ---------------------------------------------------------------

def _seed(revision: Mapping[str, Any]) -> Mapping[str, Any]:
    return revision.get("seed") or {}


def _payload(revision: Mapping[str, Any]) -> Mapping[str, Any]:
    return revision.get("payload") or {}


def _blocks(seed: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    return list(seed.get("blocks") or [])


def _codes(seed: Mapping[str, Any]) -> str:
    return ", ".join(text(b.get("code")) for b in _blocks(seed) if text(b.get("code")))


def _horizons(seed: Mapping[str, Any]) -> str:
    return ", ".join(dict.fromkeys(text(b.get("horizon")) for b in _blocks(seed) if text(b.get("horizon"))))


def layer_header(seed: Mapping[str, Any]) -> str:
    project = seed.get("project") or {}
    number = text(project.get("project_no"))
    parts = ["Проект массового взрыва" + (f" № {number}" if number else "")]
    if _codes(seed):
        parts.append(f"блок № {_codes(seed)}")
    if _horizons(seed):
        parts.append(f"гор. {_horizons(seed)}")
    return " · ".join(parts)


def _parties(seed: Mapping[str, Any]) -> tuple[str, str]:
    parties = seed.get("parties") or {}
    return text(parties.get("customer_name")), text(parties.get("contractor_name")) or ORGANIZATION


def _date_words(value: str) -> str:
    """«2026-10-14» → «14» октября 2026 г.»; другое — как есть."""

    raw = text(value)
    if len(raw) == 10 and raw[4] == "-" and raw[7] == "-" and raw[:4].isdigit():
        month = int(raw[5:7])
        if 1 <= month <= 12:
            return f"«{raw[8:10]}» {MONTHS[month - 1]} {raw[:4]} г."
    return raw or "«___» ____________ 20__ г."


def _write_in(width: float, height: float = 6 * mm, value: str = "", style: str = "bold") -> Table:
    """Белая клетка с рамкой для записи от руки (заполненная — со значением)."""

    table = Table([[p(value, style) if value else ""]], colWidths=[width], rowHeights=[height])
    table.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.6, GRAPHITE), ("BACKGROUND", (0, 0), (-1, -1), white),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("LEFTPADDING", (0, 0), (-1, -1), 3),
    ]))
    return table


def _sign(width: float, label: str, who: str, caption: str = "должность, фамилия, инициалы") -> Table:
    table = Table(
        [[p(label, "body"), "", ""], [p(who or " ", "bold"), "", ""], [p(caption, "small"), "", p("подпись", "small_c")]],
        colWidths=[width - 40 * mm, 8 * mm, 32 * mm],
    )
    table.setStyle(TableStyle([
        ("LINEBELOW", (2, 1), (2, 1), 0.6, GRAPHITE), ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 0.5), ("VALIGN", (0, 0), (-1, -1), "BOTTOM"),
    ]))
    return table


# --- 6. акт готовности -----------------------------------------------------

def readiness_story(revision: Mapping[str, Any], width: float) -> list:
    seed, payload = _seed(revision), _payload(revision)
    project = seed.get("project") or {}
    customer, contractor = _parties(seed)
    codes, horizons = _codes(seed), _horizons(seed)
    act_date = text(payload.get("act_date"))
    when = Table([[p("Дата составления акта:", "grey_r"), _write_in(30 * mm, 5.5 * mm, date(act_date) if act_date else "")]],
                 colWidths=[width / 2 + 10 * mm, width / 2 - 10 * mm])
    when.setStyle(TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 2), ("VALIGN", (0, 0), (-1, -1), "MIDDLE")]))
    place = " · ".join(filter(None, (
        f"Объект: {text(project.get('object_name'))}" if text(project.get("object_name")) else "",
        f"Горизонт: {horizons} м" if horizons else "", f"Блок № {codes}" if codes else "",
    )))
    intro = (
        f"Мы, нижеподписавшиеся, представитель {customer or '________________'} (бурение) и руководитель взрывных работ "
        f"{contractor}, составили настоящий акт о том, что блок № {codes or '___'} горизонта {horizons or '___'} м "
        "полностью подготовлен к заряжанию:"
    )
    conditions = list(seed.get("conditions") or [])
    marks = dict(payload.get("conditions") or {})
    rows = [[cell(h, "th") for h in ("№", "Условие готовности", "Да / нет", "Примечание")]]
    for index, condition in enumerate(conditions, start=1):
        mark = marks.get(str(index))
        rows.append([cell(index, "td_c"), cell(condition), cell("да" if mark is True else "нет" if mark is False else "", "td_bc"), ""])
    table = Table(rows, colWidths=[8 * mm, width * 0.5, 22 * mm, width - 8 * mm - width * 0.5 - 22 * mm],
                  rowHeights=[None] + [11 * mm] * len(conditions))
    table.setStyle(TableStyle(grid_style(rows=len(conditions), zebra=False, padding=1.5)))
    conclusion = {"READY": "ГОТОВ", "NOT_READY": "НЕ ГОТОВ"}.get(text(payload.get("conclusion")), "ГОТОВ / НЕ ГОТОВ (нужное подчеркнуть)")
    handed = text(payload.get("handed_by")) or person_line(seed.get("customer_approver"))
    accepted = text(payload.get("accepted_by")) or person_line(seed.get("blast_manager"))
    half = width / 2 - 4 * mm
    signs = Table([[
        _sign(half, f"Передал (бурение): {customer}" if customer else "Передал (бурение):", handed),
        _sign(half, f"Принял (взрывные работы): {contractor}", accepted),
    ]], colWidths=[width / 2, width / 2])
    signs.setStyle(TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 0), ("VALIGN", (0, 0), (-1, -1), "TOP")]))
    surveyor = Table([[
        _sign(half, "Исполнительная съёмка блока выполнена и передана:", text(seed.get("surveyor_name")) or "маркшейдер"),
        p("«___» ___________ 20__ г.", "body"),
    ]], colWidths=[width / 2, width / 2])
    surveyor.setStyle(TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 0), ("VALIGN", (0, 0), (-1, -1), "BOTTOM")]))
    return [
        p("АКТ", "act_red"), spacer(1),
        p(f"готовности блока № {codes or '___'} к заряжанию", "bold_c"), spacer(0.5),
        p(place, "grey_c"), spacer(0.5), when, spacer(4),
        p(intro, "body"), spacer(4), table, spacer(5),
        p("Замечания по подготовке блока:", "bold"), spacer(1), _write_in(width, 12 * mm, text(payload.get("remarks")), "body"),
        spacer(6),
        p("", "bold", markup=f"Заключение: блок № {rich(codes or '___')} для заряжания — {rich(conclusion)}. Блок передан "
                             f"взрывному участку {rich(contractor)} (п. 413 ФНП 494)."),
        spacer(7), signs, spacer(4), p("«___» ___________ 20__ г.", "body"), spacer(6), surveyor, spacer(6),
        p("Если бурение и взрывание выполняет один участок Общества, акт не оформляется (п. 413); готовность "
          "отмечается в распорядке.", "small"),
    ]


# --- 7. уведомление --------------------------------------------------------

def _addressee(revision: Mapping[str, Any]) -> Mapping[str, Any]:
    view = revision.get("view") or {}
    return view.get("addressee") or _seed(revision).get("addressee") or {}


def notification_story(revision: Mapping[str, Any], width: float) -> list:
    seed, payload = _seed(revision), _payload(revision)
    project = seed.get("project") or {}
    customer, contractor = _parties(seed)
    addressee = _addressee(revision)
    letterhead = [line.strip() for line in text(seed.get("letterhead")).splitlines() if line.strip()] or [contractor]
    head = [p(letterhead[0], "bold_r")] + [p(line, "grey_r") for line in letterhead[1:]]
    out_no, out_date = text(payload.get("out_no")), text(payload.get("out_date"))
    recipient = " ".join(filter(None, (text(addressee.get("recipient_position")), text(addressee.get("recipient_name")))))
    top = Table([[
        p(f"Исх. № {out_no or '_____'} от {date(out_date) if out_date else '__________'}", "body"),
        p(recipient or " ", "body"),
    ]], colWidths=[width * 0.5, width * 0.5])
    top.setStyle(TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 0), ("VALIGN", (0, 0), (-1, -1), "TOP")]))
    object_name = text(project.get("object_name"))
    body = (
        "В соответствии с п. 154 Федеральных норм и правил в области промышленной безопасности «Правила безопасности "
        "при производстве, хранении и применении взрывчатых материалов промышленного назначения» (приказ Ростехнадзора "
        f"от 03.12.2020 № 494) {contractor} информирует Вас о проведении массового взрыва на объекте "
        f"{object_name or '________'}" + (f" ({customer})" if customer else "") + "."
    )
    place = ", ".join(filter(None, (object_name, f"блок № {_codes(seed)}" if _codes(seed) else "",
                                    f"гор. {_horizons(seed)}" if _horizons(seed) else "")))
    depths = "; ".join(short(b.get("depth_mean_m"), 1) for b in _blocks(seed) if b.get("depth_mean_m") is not None)
    diameters = ", ".join(str(int(d)) for d in seed.get("diameter_mm") or [])
    names = ", ".join(text(n) for n in seed.get("explosive_names") or [])
    rows = [
        [cell(h, "th") for h in (
            "№", "Организация, адрес, Ф. И. О. и телефон технического руководителя", "Дата, время и место проведения взрыва",
            "Наименование и масса ВВ, кг", "Диаметр (мм) и средняя глубина скважин (м)",
            "Замедление между рядами и группами зарядов, мс",
        )],
        [
            cell(1, "td_c"),
            cell("\n".join(filter(None, (customer, text(seed.get("customer_tech_contact")))))),
            cell(f"{date(project.get('blast_date'))}  {text(project.get('blast_time'))}\n{place}", "td_c"),
            cell(f"{names}\n{num(seed.get('explosive_kg'), 0)}", "td_c"),
            cell(f"{diameters or DASH}\n{depths or DASH}", "td_c"),
            cell("; ".join(text(i) for i in seed.get("intervals") or []) or DASH, "td_c"),
        ],
    ]
    widths = [8 * mm, width * 0.27, width * 0.2, width * 0.16, width * 0.15]
    widths.append(width - sum(widths))
    table = Table(rows, colWidths=widths)
    table.setStyle(TableStyle(grid_style(rows=1, zebra=False, padding=3)))
    zone = (seed.get("zones") or {}).get("people")
    manager = person_line(seed.get("blast_manager"))
    footer = f"Опасная зона для людей — {num(zone, 0)} м." if zone is not None else "Опасная зона для людей — ____ м."
    if manager:
        footer += f" Ответственный руководитель массового взрыва — {manager}."
    signer = text(addressee.get("signer")) or text(payload.get("signer"))
    sign = Table([[p(signer or " ", "body"), "", ""], ["", "", p("подпись", "small_c")]],
                 colWidths=[width - 40 * mm, 8 * mm, 32 * mm])
    sign.setStyle(TableStyle([("LINEBELOW", (2, 0), (2, 0), 0.6, GRAPHITE), ("LEFTPADDING", (0, 0), (-1, -1), 0),
                              ("VALIGN", (0, 0), (-1, -1), "BOTTOM")]))
    salutation = text(addressee.get("salutation"))
    story: list = head + [spacer(6), top, spacer(10), p("Уведомление о проведении массового взрыва", "bold_c"), spacer(6)]
    if salutation:
        story += [p(salutation, "body"), spacer(2)]
    story += [p(body, "body"), spacer(5), table, spacer(5), p(footer, "body"), spacer(14), sign]
    return story


# --- 8. наряд-путёвка ------------------------------------------------------

def _bar(title: str, width: float) -> Table:
    table = Table([[p(title, "th_l")]], colWidths=[width])
    table.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), GRAPHITE), ("LEFTPADDING", (0, 0), (-1, -1), 3),
                               ("TOPPADDING", (0, 0), (-1, -1), 1.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 1.5)]))
    return table


def _info_grid(revision: Mapping[str, Any], width: float) -> Table:
    seed, payload = _seed(revision), _payload(revision)
    project = seed.get("project") or {}
    people = seed.get("people") or {}
    totals = (revision.get("view") or {}).get("totals") or {}
    customer, _contractor = _parties(seed)
    number = text(project.get("project_no"))
    rows = [
        ("Подразделение", "", "Заказчик", customer, "Дата выдачи / смена", date(payload.get("issue_date")) if payload.get("issue_date") else ""),
        ("Место работ (объект)", text(project.get("object_name")), "Горизонт(ы)", _horizons(seed),
         "Дата массового взрыва", date(project.get("blast_date"))),
        ("Проект МВ / паспорт БВР", f"Проект массового взрыва № {number}" if number else "", "Всего скважин, шт",
         num(totals.get("blocks_holes"), 0), "Масса зарядов (проект), кг", num(totals.get("blocks_charge_kg"), 0)),
        ("Взрывник (Ф. И. О.)", person_line(people.get("blaster")), "Индивид. индекс взрывника", text(payload.get("blaster_index")),
         "Зав. складом / раздатчик", person_line(people.get("storekeeper"))),
        ("Склад выдачи ВМ", text(payload.get("warehouse")), "Спецавтомобиль", text(payload.get("vehicle")),
         "Водитель", text(payload.get("driver"))),
        ("Разрешение на ведение ВР", text(payload.get("permit")), "", "", "", ""),
    ]
    data = [[cell(a, "td"), cell(b, "td_b"), cell(c, "td"), cell(d, "td_b"), cell(e, "td"), cell(f, "td_b")] for a, b, c, d, e, f in rows]
    w = width / 3
    table = Table(data, colWidths=[w * 0.38, w * 0.62] * 3)
    style = [("GRID", (0, 0), (-1, -1), 0.4, LINE), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
             ("TOPPADDING", (0, 0), (-1, -1), 1), ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
             ("LEFTPADDING", (0, 0), (-1, -1), 2),
             # Разрешение на ведение ВР — длинное: на всю строку.
             ("SPAN", (1, len(rows) - 1), (5, len(rows) - 1))]
    table.setStyle(TableStyle(style))
    return table


def _naryad_blocks(revision: Mapping[str, Any], width: float) -> list:
    seed = _seed(revision)
    totals = (revision.get("view") or {}).get("totals") or {}
    heads = ("№", "Блок (выработка, уступ)", "Горизонт", "Скважин (шпуров) по проекту, шт", "Масса зарядов по проекту, кг",
             "Заряжено скважин, шт", "Фактически заряжено, кг", "Взорвано зарядов, шт", "Масса взорванных зарядов, кг",
             "Отказы, шт", "Отклонение факт − проект, кг", "Примечание")
    rows = [[cell(h, "th") for h in heads]]
    blocks = _blocks(seed)
    # Форма 4: 5 строк (до 5 блоков во взрыве); блоков больше — строка на каждый.
    row_count = max(5, len(blocks))
    for index in range(row_count):
        block = blocks[index] if index < len(blocks) else None
        if block:
            rows.append([cell(index + 1, "td_c"), cell(block.get("code"), "td_c"), cell(block.get("horizon"), "td_c"),
                         cell(num(block.get("holes"), 0), "td_c"), cell(num(block.get("charge_kg"), 0), "td_c")] + [""] * 7)
        else:
            rows.append([cell(index + 1, "td_c")] + [""] * 11)
    rows.append(["", "", cell("Итого", "td_b"), cell(num(totals.get("blocks_holes"), 0), "td_bc"),
                 cell(num(totals.get("blocks_charge_kg"), 0), "td_bc")] + [""] * 7)
    fractions = (0.03, 0.14, 0.06, 0.08, 0.08, 0.07, 0.08, 0.07, 0.08, 0.06, 0.08)
    widths = [width * f for f in fractions]
    widths.append(width - sum(widths))
    table = Table(rows, colWidths=widths, rowHeights=[None] + [4.6 * mm] * (row_count + 1))
    table.setStyle(TableStyle(grid_style(rows=row_count + 1, zebra=False, padding=0.8)
                              + [("SPAN", (0, row_count + 1), (1, row_count + 1))]))
    reserve = "; ".join(f"{item['label']} {num(item['qty'], 0)} {item['unit']}" for item in totals.get("reserve") or [])
    story: list = [_bar("1. МЕСТО ПРОИЗВОДСТВА РАБОТ И ЗАРЯДЫ (по проекту массового взрыва / паспорту БВР)", width), table]
    if reserve:
        story.append(p("", "td", markup=f'<font color="{RED_HEX}"><b>Запас (добавлен менеджером, входит в «Выписано»): '
                                        f"{rich(reserve)}.</b></font>"))
    return story


def _naryad_materials(revision: Mapping[str, Any], width: float) -> list:
    seed, payload = _seed(revision), _payload(revision)
    view = revision.get("view") or {}
    lines = list(view.get("lines") or [])
    totals = view.get("totals") or {}
    vv_site = bool(view.get("vv_site") or payload.get("vv_site"))
    codes = [text(b.get("code")) for b in _blocks(seed) if text(b.get("code"))]
    top = ["№", "Наименование ВМ", "Завод-изготовитель", "Дата изгот.", "№ партии", "Ед. изм.", "Масса ед., кг",
           "Выписано", "", "Выдано", "", "Израсходовано", "", "Возвращено (остаток)", "", "Распределение расхода по блокам",
           "Контроль"]
    sub = [""] * 7 + ["кол-во", "кг"] * 4 + ["", ""]
    rows = [[cell(h, "th") for h in top], [cell(h, "th") for h in sub]]
    style: list[tuple] = [("SPAN", (c, 0), (c, 1)) for c in (0, 1, 2, 3, 4, 5, 6, 15, 16)]
    style += [("SPAN", (c, 0), (c + 1, 0)) for c in (7, 9, 11, 13)]
    for index, line in enumerate(lines, start=1):
        explosive = line.get("kind") == "explosive"
        unit_mass = line.get("unit_mass_kg")
        returned = "—" if explosive and vv_site else ""
        distribution = "; ".join(f"Блок {code} — ____ {text(line.get('unit'))}" for code in codes) or ""
        rows.append([
            cell(index, "td_c"), cell(line.get("name")), "", "", "", cell(line.get("unit"), "td_c"),
            cell(num(unit_mass, 3) if unit_mass is not None else "", "td_c"),
            cell(num(line.get("issue_qty"), 0), "td_bc"),
            # Килограммы — как в ревизии (0,9 кг × 2 = 1,8 кг), без округления до целых.
            cell(short(line.get("issue_kg"), 3) if line.get("issue_kg") is not None else "", "td_c"),
            "", "", "", "", cell(returned, "td_c"), cell(returned, "td_c"), cell(distribution), "",
        ])
    rows.append([cell(len(lines) + 1, "td_c")] + [""] * 16)
    first_total = len(rows)
    rows.append([cell("Итого ВВ, кг", "td_br"), "", "", "", "", "", "", "",
                 cell(short(totals.get("explosive_issue_kg"), 3), "td_bc")] + [""] * 8)
    rows.append([cell("Итого средства инициирования, шт", "td_br"), "", "", "", "", "", "",
                 cell(num(totals.get("initiation_issue_pcs"), 0), "td_bc"), ""] + [""] * 8)
    style += [("SPAN", (0, first_total), (6, first_total)), ("SPAN", (0, first_total + 1), (6, first_total + 1)),
              ("ALIGN", (0, first_total), (6, first_total + 1), "RIGHT")]
    fractions = (0.025, 0.15, 0.08, 0.05, 0.06, 0.035, 0.045, 0.045, 0.045, 0.04, 0.04, 0.04, 0.04, 0.04, 0.04, 0.13)
    widths = [width * f for f in fractions]
    widths.append(width - sum(widths))
    table = Table(rows, colWidths=widths, rowHeights=[None, None] + [4.4 * mm] * (len(rows) - 2))
    table.setStyle(TableStyle(grid_style(header_rows=2, rows=len(rows) - 2, zebra=False, padding=0.6) + style))
    return [_bar("2. УЧЁТ ВЗРЫВЧАТЫХ МАТЕРИАЛОВ — в количестве и в килограммах (кг = кол-во × масса единицы)", width), table]


def _naryad_signatures(revision: Mapping[str, Any], width: float) -> list:
    seed, payload = _seed(revision), _payload(revision)
    project = seed.get("project") or {}
    people = seed.get("people") or {}
    issue_date = date(payload.get("issue_date")) if payload.get("issue_date") else ""
    blast_date = date(project.get("blast_date")) if project.get("blast_date") else ""
    before = (
        ("Наряд-путёвку выписал (рук. участка / лицо технадзора)", person_line(people.get("site_manager"))),
        ("Перевозку ВМ и ВР разрешаю (руководитель ВР)", person_line(people.get("blast_manager"))),
        ("ВМ выдал (зав. складом / раздатчик ВМ)", person_line(people.get("storekeeper"))),
        ("ВМ получил (взрывник)", person_line(people.get("blaster"))),
        ("Работники, привлекаемые к доставке ВМ (Ф. И. О.)", text(payload.get("delivery")) or person_line(people.get("escort"))),
    )
    after = (
        ("ВМ израсходовал (взрывник)", person_line(people.get("blaster"))),
        ("Расход ВМ подтверждаю (руководитель ВР смены)", person_line(people.get("blast_manager"))),
        ("Остаток ВМ сдал (взрывник)", person_line(people.get("blaster"))),
        ("Остаток ВМ принял (зав. складом / раздатчик ВМ)", person_line(people.get("storekeeper"))),
        ("Наряд-путёвку принял на склад (дата сдачи путёвки)", person_line(people.get("storekeeper"))),
    )
    rows = [[cell(h, "th") for h in ("ДО ВЗРЫВА: выписка, выдача", "Должность, Ф. И. О.", "Подпись", "Дата",
                                     "ПОСЛЕ ВЗРЫВА: расход, возврат", "Должность, Ф. И. О.", "Подпись", "Дата")]]
    for (label_b, who_b), (label_a, who_a) in zip(before, after):
        rows.append([cell(label_b), cell(who_b), "", cell(issue_date, "td_c"), cell(label_a), cell(who_a), "",
                     cell(blast_date, "td_c")])
    fractions = (0.17, 0.16, 0.07, 0.07, 0.17, 0.16, 0.07)
    widths = [width * f for f in fractions]
    widths.append(width - sum(widths))
    table = Table(rows, colWidths=widths, rowHeights=[None] + [6.2 * mm] * len(before))
    table.setStyle(TableStyle(grid_style(rows=len(before), zebra=False, padding=0.8)))
    return [_bar("3. ПОДПИСИ", width), table]


NARYAD_NOTE = (
    "Заполняется в соответствии с п. 561 и приложением № 18 ФНП «Правила безопасности при производстве, хранении и "
    "применении ВМ промышленного назначения» (приказ Ростехнадзора от 03.12.2020 № 494). Разд. 1 гр. «Заряжено», "
    "«Взорвано», «Отказы», разд. 2 гр. «Израсходовано», «Возвращено» заполняются после взрыва. Графа «Выписано» = "
    "по проекту + запас (запас добавляет менеджер, на опасные зоны не влияет). Наряд-путёвка сдаётся на склад вместе "
    "с остатком ВМ."
)


def naryad_story(revision: Mapping[str, Any], width: float) -> list:
    seed, payload = _seed(revision), _payload(revision)
    _customer, contractor = _parties(seed)
    number = text(payload.get("number"))
    head = Table([[
        [p(contractor, "bold"), p("Организация-исполнитель", "small")],
        [p(f"НАРЯД-ПУТЁВКА № {number}" if number else "НАРЯД-ПУТЁВКА № ______", "bold_c"),
         p("на производство взрывных работ взрывнику", "body_c")],
        [p("Форма 4", "body_r"), p("форма 4 приказа Общества (приложение № 18 к ФНП 494)", "small")],
    ]], colWidths=[width * 0.3, width * 0.4, width * 0.3])
    head.setStyle(TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                              ("VALIGN", (0, 0), (-1, -1), "TOP")]))
    story: list = [head, spacer(1.5), _info_grid(revision, width), spacer(2)]
    story += _naryad_blocks(revision, width) + [spacer(2)]
    story += _naryad_materials(revision, width) + [spacer(2)]
    story += _naryad_signatures(revision, width) + [spacer(1.5), p(NARYAD_NOTE, "small")]
    return [KeepInFrame(width, frame.landscape(frame.A4)[1] - 23 * mm, story, mode="shrink")]


# --- 9. талон-допуск -------------------------------------------------------

def _talon_half(revision: Mapping[str, Any], width: float) -> list:
    seed, payload = _seed(revision), _payload(revision)
    project = seed.get("project") or {}
    codes, horizons = _codes(seed), _horizons(seed)
    issued_date = text(payload.get("issued_date")) or text(project.get("blast_date"))
    issued_time = text(payload.get("issued_time"))
    time_text = f"{issued_time[:2]} ч {issued_time[3:5]} мин" if len(issued_time) == 5 else "___ ч ___ мин"
    issued_by = text(payload.get("issued_by")) or person_line(seed.get("blast_manager"))
    received_by = text(payload.get("received_by")) or person_line(seed.get("talon_receiver"))
    when = Table([[p("Дата:", "body_r"), p(date(issued_date) if issued_date else "__________", "bold"),
                   p("Время выдачи:", "body_r"), p(time_text, "body")]],
                 colWidths=[width * 0.2, width * 0.25, width * 0.25, width * 0.3])
    when.setStyle(TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 2)]))
    not_before = text(seed.get("admittance_not_before")) or "____"
    admit = Table([[p("Осмотр блока произведён, сигнал «отбой» подан, отказавших зарядов нет. Допуск людей "
                      "(п. 422 ФНП 494) — не ранее:", "body"), p(not_before, "summary_value")]],
                  colWidths=[width * 0.6, width * 0.4])
    admit.setStyle(TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 0), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                               ("ALIGN", (1, 0), (1, 0), "CENTER")]))
    return [
        p("ТАЛОН-ДОПУСК", "title_red"), spacer(1),
        p(f"для работы на блоке № {codes or '___'} горизонта {horizons or '___'} м после проведения взрывных работ", "body_c"),
        p(f"Объект: {text(project.get('object_name'))}" if text(project.get("object_name")) else " ", "grey_c"),
        spacer(1), when, spacer(3), admit, spacer(3),
        _sign(width, "Выдал — ответственный руководитель массового взрыва:", issued_by), spacer(2),
        _sign(width, "Получил — представитель заказчика:", received_by),
    ]


def talon_story(revision: Mapping[str, Any], width: float) -> list:
    page_h = frame.A4[1]
    margins = Margins()
    first_top = page_h - HEADER_H - 3 * mm
    half_one = first_top - page_h / 2 - 2 * mm
    gap = HEADER_H + 5 * mm
    half_two = page_h / 2 - gap - margins.bottom - 2 * mm
    table = Table(
        [[KeepInFrame(width, half_one, _talon_half(revision, width), mode="shrink")], [""],
         [KeepInFrame(width, half_two, _talon_half(revision, width), mode="shrink")]],
        colWidths=[width], rowHeights=[half_one, gap + 2 * mm, half_two],
    )
    table.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0),
                               ("RIGHTPADDING", (0, 0), (-1, -1), 0), ("TOPPADDING", (0, 0), (-1, -1), 0),
                               ("BOTTOMPADDING", (0, 0), (-1, -1), 0)]))
    return [table]


def _talon_extra(canvas, part: Part, logo, _page: int) -> None:
    """Линия отреза ровно посередине листа и шапка второго экземпляра."""

    page_w, page_h = part.pagesize
    middle = page_h / 2
    register_fallback_font()
    canvas.setStrokeColor(GREY)
    canvas.setLineWidth(0.6)
    canvas.setDash(4, 3)
    canvas.line(part.margins.left, middle, page_w - part.margins.right, middle)
    canvas.setDash()
    label_w = canvas.stringWidth(CUT_LINE, FONT_FALLBACK, 6.5)
    canvas.setFillColor(white)
    canvas.rect(page_w / 2 - label_w / 2 - 3, middle - 4, label_w + 6, 8, stroke=0, fill=1)
    canvas.setFillColor(GREY)
    canvas.setFont(FONT_FALLBACK, 6.5)
    canvas.drawCentredString(page_w / 2, middle - 2.2, CUT_LINE)
    frame.draw_header(canvas, part, logo, 0, top=middle - 3 * mm, header=TALON_COPIES[1], title=part.title)


# --- 10. акт приёмки -------------------------------------------------------

def _acceptance_text(seed: Mapping[str, Any]) -> list[str]:
    project = seed.get("project") or {}
    template = text(seed.get("acceptance_text"))
    values = {
        "{блок}": _codes(seed) or "___", "{горизонт}": _horizons(seed) or "___",
        "{дата взрыва}": _date_words(text(project.get("blast_date"))),
    }
    for key, value in values.items():
        template = template.replace(key, value)
    return [line.strip() for line in template.replace("\\n", "\n").splitlines() if line.strip()]


def acceptance_story(revision: Mapping[str, Any], width: float) -> list:
    seed, payload = _seed(revision), _payload(revision)
    customer, contractor = _parties(seed)
    contract = seed.get("contract") or {}
    appendix = text(payload.get("appendix_no")) or text(contract.get("acceptance_appendix_no"))
    contract_no = text(payload.get("contract_no")) or text(contract.get("contract_no"))
    contract_date = text(payload.get("contract_date")) or text(contract.get("contract_date"))
    customer_person = text(payload.get("customer_person")) or text(contract.get("customer_responsible"))
    contractor_person = person_line(seed.get("blast_manager"))
    act_date = text(payload.get("act_date"))
    codes = _codes(seed)
    commission = Table([
        [p("Ответственное лицо Заказчика", "body"), p(", ".join(filter(None, (customer_person or "________________", customer))), "bold")],
        [p("Ответственное лицо Подрядчика", "body"), p(", ".join(filter(None, (contractor_person or "________________", contractor))), "bold")],
    ], colWidths=[width * 0.4, width * 0.6])
    commission.setStyle(TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 0), ("LINEBELOW", (1, 0), (1, -1), 0.4, LINE),
                                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("TOPPADDING", (0, 0), (-1, -1), 3)]))
    accepted = payload.get("accepted_volume_m3")
    volume = Table([[p("— по технологическому взрыванию", "body"),
                     _write_in(40 * mm, 6 * mm, num(accepted, 0) if accepted is not None else ""), p("м³", "body")]],
                   colWidths=[width * 0.55, 42 * mm, width * 0.45 - 42 * mm])
    volume.setStyle(TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 0), ("VALIGN", (0, 0), (-1, -1), "MIDDLE")]))
    blocks = _blocks(seed)
    grid = "; ".join(
        f"{short(b.get('spacing_mean_m'), 1)} × {short(b.get('burden_mean_m'), 1)}"
        for b in blocks if b.get("spacing_mean_m") is not None and b.get("burden_mean_m") is not None
    )
    q = seed.get("specific_q_kg_m3")
    params = Table([
        [p("", "body", markup=f'<font color="{RED_HEX}"><b>1.</b></font> Сетка скважин, м'), p(grid or DASH, "bold_c")],
        [p("", "body", markup=f'<font color="{RED_HEX}"><b>2.</b></font> Удельный расход ВМ, кг/м³'),
         p(short(q, 2) if q is not None else DASH, "bold_c")],
    ], colWidths=[width * 0.5, 45 * mm])
    params.setStyle(TableStyle([("LEFTPADDING", (0, 0), (0, -1), 4 * mm), ("LINEBELOW", (1, 0), (1, -1), 0.4, LINE)]))
    remarks = text(payload.get("remarks"))
    remark_rows = [[p(remarks, "body")]] if remarks else [[""], [""], [""]]
    remarks_table = Table(remark_rows, colWidths=[width], rowHeights=None if remarks else [6 * mm] * 3)
    remarks_table.setStyle(TableStyle([("LINEBELOW", (0, 0), (-1, -1), 0.4, LINE), ("LEFTPADDING", (0, 0), (-1, -1), 0)]))

    def signer(label: str, who: str) -> Table:
        table = Table([[p(label, "body"), "", p(who or " ", "body")], ["", p("подпись", "small_c"),
                                                                        p("должность, фамилия, инициалы", "small")]],
                      colWidths=[width * 0.4, 38 * mm, width * 0.6 - 38 * mm])
        table.setStyle(TableStyle([("LINEBELOW", (1, 0), (1, 0), 0.6, GRAPHITE), ("LEFTPADDING", (0, 0), (-1, -1), 0),
                                   ("LEFTPADDING", (2, 0), (2, -1), 4 * mm), ("VALIGN", (0, 0), (-1, -1), "BOTTOM")]))
        return table

    story: list = [
        p(f"Приложение № {appendix or '[№]'}", "body_r"),
        p(f"к договору подряда на производство взрывных работ № {contract_no or '[№ договора]'} от "
          f"{date(contract_date) if contract_date else '[дата]'}", "body_r"),
        spacer(5), p(_date_words(act_date) if act_date else "«___» ____________ 20__ г.", "body"), spacer(5),
        p("АКТ", "act_red"), p(f"приёмки выполненных работ блока № {codes or '___'}", "bold_c"), spacer(6),
        p("Комиссия в составе:", "bold"), spacer(1), commission, spacer(4), p("составили настоящий акт:", "body"), spacer(1),
    ]
    story += [p(line, "body") for line in _acceptance_text(seed)]
    volume_contour = seed.get("volume_contour_m3")
    story += [
        spacer(4), p("К оплате принимаются следующие объёмы:", "bold"), spacer(1), volume,
        p(f"по проекту (маркшейдерский контур): {num(volume_contour, 0)} м³" if volume_contour else " ", "small"),
        spacer(4), p("Параметры взрывных работ:", "bold"), spacer(1), params, spacer(5),
        p("Данный акт составлен в 2-х равноценных экземплярах, по одному каждой стороне. Настоящий акт является "
          "основанием для дальнейших взаиморасчётов.", "body"),
        spacer(5), p("Особые замечания:", "bold"), remarks_table, spacer(10),
        signer("Ответственное лицо Заказчика", customer_person), spacer(5),
        signer("Ответственное лицо Подрядчика", contractor_person),
    ]
    return story


# --- сборка ----------------------------------------------------------------

STORIES: dict[str, Callable[[Mapping[str, Any], float], list]] = {
    "READINESS_ACT": readiness_story,
    "NOTIFICATION": notification_story,
    "NARYAD": naryad_story,
    "TALON": talon_story,
    "ACCEPTANCE_ACT": acceptance_story,
}


def layer_part(revision: Mapping[str, Any]) -> Part:
    """Документ слоя по ревизии слоя (`context` ревизии: kind, seed, payload, view)."""

    kind = text(revision.get("kind"))
    if kind not in STORIES:
        raise ValueError(f"Неизвестный вид документа дня взрыва: {kind}.")
    label, title = LAYER_DOCUMENTS[kind]
    seed = _seed(revision)
    landscape = kind == "NARYAD"
    margins = Margins(left=10 * mm, right=10 * mm, top=10 * mm, bottom=12 * mm) if landscape else Margins()
    width = frame.frame_width(landscape, margins)
    header = TALON_COPIES[0] if kind == "TALON" else layer_header(seed)
    return Part(
        key=f"layer:{kind}", label=label, title=title, header="" if kind == "NOTIFICATION" else header,
        story=lambda: STORIES[kind](revision, width), numbering="own", landscape=landscape,
        header_pages="none" if landscape else "first", margins=margins,
        draw_extra=_talon_extra if kind == "TALON" else None,
    )


def render_layer_document(revision: Mapping[str, Any], *, draft: bool = False) -> bytes:
    part = layer_part(revision)
    return frame.render([part], title=part.label, duplex=False, draft=draft)


__all__ = ["LAYER_DOCUMENTS", "layer_part", "render_layer_document"]
