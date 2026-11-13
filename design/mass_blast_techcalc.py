"""Технический расчёт массового взрыва (прил. 10 ФНП 494) как данные (TASK-018, PR 2, §3.1).

Разделы 1–17 по одному блоку проекта: каждое число — величина с формулой,
подстановкой, пунктом ФНП и происхождением (`FIELD_SOURCES`), текст — строка.
Безопасные расстояния (разд. 13–15) — готовые `SafetyValue` из
`design/safety/`, расход (разд. 10–12) — `explosives_consumption`; здесь они
только раскладываются по разделам. Проект блока только читается.

Отклонения от формы ВМ.09.03 v0.11 (решения владельца):
- масса ВВ в разд. 4 — по декам без округления (как расход, решение PR 1),
  сумма таблицы параметров кратно 5 кг — примечанием;
- q расчётный = (ВВ + ПД) / V по контуру, как в форме; отклонение от
  типового проекта больше 10 % — `q_deviation`, а без обоснования —
  `q_just_missing` (ошибка, п. 411; решение В7).
"""
from __future__ import annotations

import math
from statistics import median
from typing import Any, Mapping, Sequence

from design.mass_blast_calc import ConsumptionLine
from design.geometry import block_area_m2
from design.mass_blast_table import ParameterTable
from design.models import BlastDesign, HoleLoad, is_explosive_deck_kind
from design.safety import SafetyValue, num
from design.safety.design import SafetyResult
from design.safety.holes import primer_items

__all__ = ["Q_DEVIATION_SHARE", "VOLUME_MISMATCH_SHARE", "network_intervals", "technical_calculation"]

VOLUME_MISMATCH_SHARE = 0.10
Q_DEVIATION_SHARE = 0.10
GRAPHICS_LINE = (
    "Графические приложения: Г.1 схема расположения скважин; Г.2 поперечные профили через заряды; "
    "Г.3 схема заряжания, забойки и отвода оборудования; Г.4 схема взрывной сети; Г.5 ситуационный план "
    "с опасной зоной, постами охраны и взрывной станцией. План блока и схемы фактического расположения "
    "скважин подписываются исполнителями съёмки с указанием должностей."
)
GASES_TEXT = (
    "Не рассчитывается: газоопасность учитывается при одновременном взрыве зарядов выброса общей "
    "массой более 200 т (п. 814)."
)
PURPOSE_LABELS = {"MINING": "добыча", "STRIPPING": "вскрыша"}


def _value(
    label: str,
    value: Any,
    unit: str = "",
    *,
    formula: str = "",
    substitution: str = "",
    basis: str = "",
    source: str = "DESIGN",
    note: str = "",
) -> dict[str, Any]:
    return {
        "label": label,
        "value": value,
        "unit": unit,
        "formula": formula,
        "substitution": substitution,
        "basis": basis,
        "source": source,
        "note": note,
    }


def _safety(label: str, item: SafetyValue, note: str = "") -> dict[str, Any]:
    return _value(
        label,
        item.value,
        item.unit,
        formula=item.formula,
        substitution=item.substitution,
        basis=item.basis,
        source=item.source,
        note=note,
    )


def _text(text: str) -> dict[str, Any]:
    return {"text": text}


def _digits(value: float) -> int:
    return 0 if float(value).is_integer() else (1 if (value * 10).is_integer() else 2)


def _construction_groups(design: BlastDesign, table_rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Конструкции заряда: одинаковая последовательность дек и марок, до трёх самых частых."""

    loads: dict[str, HoleLoad] = {load.hole_id: load for load in design.loads}
    holes = {hole.id: hole for hole in design.holes if hole.enabled}
    by_key: dict[tuple, list[str]] = {}
    for row in table_rows:
        load = loads.get(row["hole_id"])
        # Конструкция — у заряженной скважины: взрывчатая дека с нулевой массой
        # зарядом не считается (забойки у такой скважины в таблице нет).
        if load is None or row["stemming_m"] is None:
            continue
        ordered = sorted(load.decks, key=lambda deck: min(deck.from_m, deck.to_m))
        key = tuple((deck.kind, deck.product or deck.explosive_key if is_explosive_deck_kind(deck.kind) else "") for deck in ordered)
        by_key.setdefault((key, len(primer_items(load))), []).append(row["hole_id"])
    groups: list[dict[str, Any]] = []
    rows = {row["hole_id"]: row for row in table_rows}
    for (key, primer_count), ids in sorted(by_key.items(), key=lambda item: -len(item[1]))[:3]:
        lengths = [holes[i].length_m for i in ids]
        stems = [float(rows[i]["stemming_m"]) for i in ids]
        subdrills = [holes[i].subdrill_m for i in ids]
        bottoms = []
        for hole_id in ids:
            for primer in primer_items(loads[hole_id]):
                bottoms.append(holes[hole_id].length_m - primer.position_m)
        diameter = median(holes[i].diameter_mm for i in ids) / 1000.0
        stem_min = min(stems)
        groups.append(
            {
                "hole_count": len(ids),
                "decks": [kind for kind, _ in key],
                "products": sorted({product for _, product in key if product}),
                "depth_mean_m": round(sum(lengths) / len(lengths), 1),
                "bench_height_mean_m": round(sum(holes[i].bench_height_m for i in ids) / len(ids), 1),
                "subdrill_mean_m": round(sum(subdrills) / len(subdrills), 1),
                "stemming_mean_m": round(sum(stems) / len(stems), 1),
                "stemming_min_m": round(stem_min, 1),
                # Длина заряда — сумма взрывчатых дек: воздушные и инертные промежутки не заряд.
                "charge_length_mean_m": round(
                    sum(
                        abs(deck.to_m - deck.from_m)
                        for hole_id in ids
                        for deck in loads[hole_id].decks
                        if is_explosive_deck_kind(deck.kind)
                    )
                    / len(ids),
                    1,
                ),
                "primer_from_bottom_m": round(min(bottoms), 1) if bottoms else None,
                "primers_per_hole": primer_count,
                "stemming_to_d_min": round(stem_min / diameter, 1) if diameter > 0 else None,
            }
        )
    return groups


def technical_calculation(
    design: BlastDesign,
    *,
    block: Mapping[str, Any],
    safety: SafetyResult,
    table: ParameterTable,
    consumption: Sequence[ConsumptionLine],
    texts: Mapping[str, Any],
    q_tp: Mapping[str, Any],
    objects: Sequence[Mapping[str, Any]],
    volume_m3: float,
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    """Разделы 1–17 по одному блоку и замечания с кодами §7 плана PR 2.

    `block` — код, горизонт, поля блока проекта МВ (порода, гидрогеология,
    назначение, площадь); `texts` — тексты проекта (ТП, способ инициирования,
    схема, конструкция, материал забойки, долото, k разбуривания, особые
    условия, УВВ на здания); `q_tp` — {value, source, basis, justification}.
    """

    issues: list[dict[str, str]] = []
    totals = table.totals
    rows = table.rows
    hole_count = totals["hole_count"]
    explosive_kg = sum(line.quantity for line in consumption if line.kind == "explosive")
    primer_kg = sum(float(line.mass_kg or 0.0) for line in consumption if line.kind == "primer")
    sections: list[dict[str, Any]] = []

    # 1. Общие сведения
    area_manual = block.get("area_m2")
    area = float(area_manual) if area_manual not in (None, "") else block_area_m2(design.contour)
    purpose = PURPOSE_LABELS.get(str(block.get("purpose") or ""), str(block.get("purpose") or ""))
    general = f"Блок № {block.get('code', '')}, гор. {block.get('horizon', '')} м"
    if purpose:
        general += f", {purpose}"
    if area:
        general += f"; площадь {num(area)} м²"
    basis = str(texts.get("tp_basis") or "").strip()
    general += f". Основание: {basis + ', ' if basis else ''}маркшейдерская съёмка блока, результаты предыдущих взрывов (п. 411)."
    sections.append({"number": "1", "title": "Общие сведения", "items": [_text(general)]})

    # 2. Геология и гидрогеология
    f_value = safety.params.hardness_f
    parts = [str(block.get(key) or "").strip() for key in ("rock_text", "hydro_text")]
    geology = "; ".join([part for part in parts if part] + [f"f = {num(f_value, _digits(f_value))}"])
    sections.append({"number": "2", "title": "Геология и гидрогеология", "items": [_text(geology)]})

    # 3. Объём
    table_volume = totals.get("volume_m3")
    note = f"по таблице параметров {num(table_volume)} м³" if table_volume else "по таблице параметров — не определён (нет шага сетки у части скважин)"
    sections.append(
        {
            "number": "3",
            "title": "Объём взрываемого массива (по маркшейдерскому контуру)",
            "items": [_value("Объём", round(volume_m3), "м³", basis="контур блока и поверхности проекта", note=note)],
        }
    )
    if volume_m3 > 0 and table_volume:
        share = abs(table_volume - volume_m3) / volume_m3
        if share > VOLUME_MISMATCH_SHARE:
            issues.append(
                {
                    "level": "warning",
                    "code": "volume_mismatch",
                    "message": f"Объём по таблице параметров {num(table_volume)} м³ отличается от объёма по контуру "
                    f"{num(volume_m3)} м³ на {num(share * 100, 1)} % (больше 10 %): проверьте контур и сетку.",
                }
            )

    # 4. Параметры БВР и расчёт зарядов
    items: list[dict[str, Any]] = []
    items.append(_value("Скважин / объём бурения", f"{hole_count} шт / {num(totals['depth_m'], 1)} п. м"))
    diameters = [row["diameter_mm"] for row in rows]
    d_mm = float(median(diameters)) if diameters else 0.0
    bit, reaming = texts.get("bit_mm"), texts.get("reaming_k")
    d_note = f"долото {num(float(bit))} мм × k_разб {num(float(reaming), 2)}" if bit and reaming else ""
    if len(set(diameters)) > 1:
        d_note = "; ".join(filter(None, [d_note, f"диаметры скважин {min(diameters)}–{max(diameters)} мм, указан средний"]))
    items.append(_value("Диаметр скважины d", round(d_mm), "мм", note=d_note))
    if hole_count:
        items.append(
            _value(
                "Глубина L (ср. / мин. – макс.)",
                f"{num(totals['depth_mean_m'], 1)} / {num(totals['depth_min_m'], 1)} – {num(totals['depth_max_m'], 1)} м",
            )
        )
        bench_mean = sum(row["bench_height_m"] for row in rows) / hole_count
        items.append(
            _value("Высота уступа H_у (ср.) / перебур l_пер (ср.)", f"{num(bench_mean, 1)} / {num(totals['subdrill_mean_m'] or 0, 1)} м")
        )
    if totals.get("spacing_mean_m") and totals.get("burden_mean_m"):
        items.append(
            _value(
                "Сетка a × b (между скважинами × между рядами, ср.)",
                f"{num(totals['spacing_mean_m'], 1)} × {num(totals['burden_mean_m'], 1)} м",
            )
        )
    explosive_names = [line.name for line in consumption if line.kind == "explosive"]
    density = _density(design)
    items.append(
        _value(
            "ВВ / плотность заряжания Δ",
            f"{', '.join(explosive_names) or '—'} / {num(density) if density else '—'} кг/м³",
        )
    )
    primer_names = [line.name for line in consumption if line.kind == "primer"]
    init_names = [line.name for line in consumption if line.kind in ("nsi_downhole", "detonator_electronic")]
    items.append(_value("Промежуточный детонатор / средства инициирования", f"{', '.join(primer_names) or '—'} / {', '.join(init_names) or '—'}"))
    p_kg_m = math.pi * (d_mm / 1000.0) ** 2 / 4.0 * density if density else 0.0
    items.append(
        _value(
            "Вместимость 1 м, P",
            round(p_kg_m, 2),
            "кг/м",
            formula="P = π·d²/4·Δ",
            substitution=f"π·{num(d_mm / 1000.0, 3)}²/4·{num(density)} = {num(p_kg_m, 2)}",
            source="CALCULATED",
        )
    )
    # Типовая скважина — заряженная; l_зар — сумма взрывчатых дек: воздушные и
    # инертные промежутки рассредоточенного заряда не заряд. При сплошной
    # колонке l_зар = L − l_заб, как в форме.
    charged = [row for row in rows if row["stemming_m"] is not None]
    charge_mean = sum(row["charge_length_m"] for row in charged) / len(charged) if charged else 0.0
    typical = p_kg_m * charge_mean
    items.append(
        _value(
            "Заряд типовой скважины, Q",
            round(typical),
            "кг",
            formula="Q = P·l_зар",
            substitution=f"{num(p_kg_m, 2)}·{num(charge_mean, 1)} = {num(typical)}",
            source="CALCULATED",
            note="l_зар — длина колонки ВВ (L − l_заб без промежутков), ср.; по скважинам — таблица параметров",
        )
    )
    items.append(
        _value(
            "Масса ВВ в блоке (сумма по скважинам) / макс. заряд",
            f"{num(explosive_kg)} / {num(totals['charge_max_kg'] or 0)} кг",
            note=f"по таблице параметров (кратно {num(table.charge_round_kg)} кг) — {num(totals['charge_kg'])} кг",
        )
    )
    q_value = q_tp.get("value")
    if q_value:
        items.append(_value("Удельный расход ВВ: проектный (ТП) q_п", float(q_value), "кг/м³", source=str(q_tp.get("source") or "REFERENCE"), note=str(q_tp.get("basis") or "")))
    else:
        issues.append(
            {
                "level": "warning",
                "code": "q_tp_missing",
                "message": "Не задан удельный расход по типовому проекту (реквизиты объекта или проект МВ): отклонение q не проверено.",
            }
        )
    q_calc = (explosive_kg + primer_kg) / volume_m3 if volume_m3 > 0 else 0.0
    q_note = ""
    deviation = None
    if q_value and float(q_value) > 0:
        deviation = abs(q_calc - float(q_value)) / float(q_value)
        q_note = "отклонение от ТП > 10 % — см. обоснование" if deviation > Q_DEVIATION_SHARE else "в пределах ±10 % от ТП"
    items.append(
        _value(
            "Удельный расход ВМ расчётный, q",
            round(q_calc, 2),
            "кг/м³",
            formula="q = (Q_ВВ + Q_ПД)/V",
            substitution=f"({num(explosive_kg)} + {num(primer_kg)})/{num(volume_m3)} = {num(q_calc, 2)}",
            source="CALCULATED",
            note=q_note,
        )
    )
    if deviation is not None and deviation > Q_DEVIATION_SHARE:
        issues.append(
            {
                "level": "warning",
                "code": "q_deviation",
                "message": f"Расчётный удельный расход {num(q_calc, 2)} кг/м³ отличается от проектного "
                f"{num(float(q_value), 2)} кг/м³ на {num(deviation * 100)} %.",
            }
        )
        justification = str(q_tp.get("justification") or "").strip()
        if justification:
            items.append(_text(f"Обоснование удельного расхода: {justification}"))
        else:
            issues.append(
                {
                    "level": "error",
                    "code": "q_just_missing",
                    "message": "Удельный расход отличается от типового проекта больше чем на 10 %: "
                    "укажите обоснование (п. 411 ФНП 494).",
                }
            )
    if totals["depth_m"]:
        items.append(_value("Выход горной массы с 1 п. м", round(volume_m3 / totals["depth_m"], 1), "м³/п. м", source="CALCULATED"))
    # Вместимость 1 м — ещё и ключом: её печатает шапка таблицы параметров (PR 3).
    sections.append({"number": "4", "title": "Параметры БВР и расчёт зарядов", "items": items, "p_kg_m": round(p_kg_m, 2)})

    # 5–9. Тексты
    system = design.network.system
    sections.append({"number": "5", "title": "Способ инициирования зарядов и взрывной сети", "items": [_text(str(texts.get("initiation") or ""))]})
    electric = (
        "Не выполняется — электронная система инициирования: сеть проверяется по паспорту системы."
        if system == "electronic"
        else "Не выполняется — неэлектрическая система инициирования (НСИ)."
    )
    sections.append({"number": "6", "title": "Расчёт электровзрывной сети и силы тока", "items": [_text(electric)]})
    sections.append(
        {
            "number": "7",
            "title": "Конструкция заряда и боевика, вид и величина забойки",
            "items": [_text(str(texts.get("charge_design") or ""))],
            "constructions": _construction_groups(design, rows),
            "stemming_material": str(texts.get("stemming_material") or ""),
        }
    )
    nsi = sorted({line.name for line in consumption if line.kind in ("nsi_downhole", "nsi_surface", "starter", "detonator_electronic")})
    cord = "ДШ применяется по схеме сети" if design.network.detonating_cords else "ДШ не применяется"
    sections.append(
        {"number": "8", "title": "Тип детонирующего шнура и замедлителей", "items": [_text(f"{cord}. НСИ: {'; '.join(nsi) or '—'}")]}
    )
    scheme = str(texts.get("scheme") or "").strip()
    intervals = network_intervals([design])
    line = "; ".join(filter(None, [scheme, "интервалы: " + "; ".join(intervals) if intervals else ""]))
    sections.append({"number": "9", "title": "Схема взрывания с интервалами замедлений", "items": [_text(f"{line} (Г.4).".lstrip())]})

    # 10–12. Расход
    sections.append(
        {
            "number": "10–12",
            "title": "Предполагаемый расход ВМ по наименованиям (по проекту; запас — в наряде-путёвке)",
            "consumption": _consumption_rows(consumption),
        }
    )

    # 13. Разлёт
    zones = safety.zones
    flyrock = safety.flyrock
    sections.append(
        {
            "number": "13",
            "title": "Безопасные расстояния по разлёту кусков (пп. 784–786, прил. 21)",
            "items": [
                _safety("r_разл серии (наименьшие η_заб и a, наибольшие η_з и f)", flyrock.series),
                _safety("Поправка на рельеф K_р (п. 785)", flyrock.relief),
                _safety("R_разл с рельефом", flyrock.with_relief),
                _safety("Опасная зона для людей (принято)", zones.people, note=f"определяет: {zones.people_factor}"),
                _safety("Для механизмов (принято проектом)", zones.mechanisms),
            ],
        }
    )

    # 14. УВВ
    airblast = safety.airblast
    group_n = len(airblast.group.charges) if airblast.group else 0
    sections.append(
        {
            "number": "14",
            "title": "Безопасные расстояния по ударной воздушной волне (пп. 796–807)",
            "items": [
                _value("K_з / N — зарядов в группе", f"{num(airblast.kz.value or 0, 3)} / {group_n}", basis="ФНП 494 пп. 803, 806"),
                _safety("Q_э — эквивалентная масса", airblast.qe),
                _safety("Коэффициенты: замедление (п. 806) × порода (п. 804) × мороз (п. 807)", airblast.factors),
                _safety("r_в — по остеклению (расчёт)", airblast.calculated),
                _safety("Безопасное расстояние по остеклению (принято)", airblast.accepted),
                _text(_buildings_line(texts, objects)),
            ],
        }
    )

    # 15. Сейсмика
    seismic = safety.seismic
    params = safety.params
    sections.append(
        {
            "number": "15",
            "title": "Сейсмически безопасные расстояния (пп. 792–795)",
            "items": [
                _value(
                    "Q / N / K_г / K_с / α",
                    f"{num(seismic.chosen.q_kg)} кг / {seismic.chosen.n} / {num(params.k_ground, _digits(params.k_ground))} / "
                    f"{num(params.k_structure, _digits(params.k_structure))} / {num(params.alpha_blast, _digits(params.alpha_blast))}",
                    basis="ФНП 494 пп. 792, 794",
                    note="Q = ВВ + ПД; N — групп замедления по сети (< 20 мс — одна группа)",
                ),
                _safety("r_с (расчёт)", seismic.calculated),
                _safety("Сейсмически безопасное расстояние (принято)", seismic.accepted),
            ],
        }
    )

    sections.append({"number": "16", "title": "Безопасное расстояние по воздействию газов", "items": [_text(GASES_TEXT)]})

    other = str(texts.get("other") or "").strip()
    footer = "Для объектов «В ЗОНЕ» — мероприятия по защите и согласование с владельцем (п. 138)."
    sections.append(
        {
            "number": "17",
            "title": "Прочие сведения",
            "objects": list(objects),
            "items": [_text(f"Особые условия: {other}. {footer}" if other else footer)],
        }
    )
    for section in sections:
        if "items" in section:
            section["items"] = [item for item in section["items"] if "text" not in item or item["text"].strip()]
    return sections, issues


def network_intervals(designs: Sequence[BlastDesign]) -> list[str]:
    """Интервалы замедления сети для текста: НСИ и ДШ — по соединителям, электронная — по каналам.

    У электронной сети времена — абсолютные моменты каналов (`electronic_channels`),
    поверхностных соединителей нет: печатаются диапазон времён и наименьший
    интервал между соседними моментами.
    """

    surface = sorted({float(c.delay_ms) for design in designs for c in design.network.surface_connectors})
    downhole = sorted({float(c.delay_ms) for design in designs for c in design.network.downhole_connectors})
    times = sorted({float(c.time_ms) for design in designs for c in design.network.electronic_channels})
    parts: list[str] = []
    if surface:
        parts.append("поверхностные " + ", ".join(num(value, _digits(value)) for value in surface) + " мс")
    if downhole:
        parts.append("в скважине " + ", ".join(num(value, _digits(value)) for value in downhole) + " мс")
    if times:
        text = f"электронные: время срабатывания {num(times[0], _digits(times[0]))}–{num(times[-1], _digits(times[-1]))} мс"
        steps = [b - a for a, b in zip(times, times[1:]) if b - a > 0]
        if steps:
            step = min(steps)
            text += f", наименьший интервал {num(step, _digits(step))} мс"
        parts.append(text)
    return parts


def _density(design: BlastDesign) -> float:
    """Δ, кг/м³ — по декам проекта: масса деки к её объёму, медиана по скважинам."""

    holes = {hole.id: hole for hole in design.holes}
    values: list[float] = []
    for load in design.loads:
        hole = holes.get(load.hole_id)
        if hole is None or not hole.enabled or hole.diameter_mm <= 0:
            continue
        area = math.pi * (hole.diameter_mm / 1000.0) ** 2 / 4.0
        for deck in load.decks:
            length = abs(deck.to_m - deck.from_m)
            if is_explosive_deck_kind(deck.kind) and deck.mass_kg > 0 and length > 0:
                values.append(deck.mass_kg / (length * area))
    return round(median(values)) if values else 0.0


def _consumption_rows(lines: Sequence[ConsumptionLine]) -> list[dict[str, Any]]:
    numbers = {"explosive": "10", "primer": "11"}
    rows: list[dict[str, Any]] = []
    nsi_numbered = False
    for line in lines:
        number = numbers.get(line.kind, "")
        if line.kind not in numbers and not nsi_numbered:
            number, nsi_numbered = "12", True
        rows.append({"item": number, **line.to_dict()})
    return rows


def _buildings_line(texts: Mapping[str, Any], objects: Sequence[Mapping[str, Any]]) -> str:
    manual = str(texts.get("airblast_buildings") or "").strip()
    if manual:
        return f"На здания и сооружения (пп. 796–801): {manual}"
    inside = [item for item in objects if item.get("kind") == "buildings" and item.get("position") == "В ЗОНЕ"]
    if not inside:
        return "На здания и сооружения (пп. 796–801): охраняемых зданий и сооружений в зоне действия УВВ нет."
    return "На здания и сооружения (пп. 796–801): здания в зоне — см. п. 17 и мероприятия распорядка (п. 14)."

