"""Справочники методики ФОТ по файлу владельца «Расчёт заработной платы» (TASK-010).

Функция «опубликованный снимок → дополненные разделы» (Т10), как
`reclassify_positions`: импорт xlsx заменяет раздел целиком и затёр бы
должности организации, поэтому на проде данные дописываются отсюда. Правила:

- записи, которой нет, заводится новая с источником `payroll_seed`;
- у записи, которая уже есть, заполняются только пустые ключи payload —
  заданные значения не меняются (решение владельца 14.09.2026);
- заданное значение, которое расходится с файлом, остаётся, но называется в
  `kept` отчёта: форма справочника пишет в payload умолчания схемы, и
  «Применить» до сида превратил бы их в заданные значения;
- повторный прогон ничего не меняет.

Расчёт по ставкам (`labor.compute`) новых ключей не читает, поэтому смета
после сида та же.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Mapping

from cost.v2.models import ReferenceItem, ReferenceSnapshot, finite_decimal
from cost.v2.references import normalize_sections

SOURCE = "payroll_seed"
_COMMENT = "Файл «Расчёт заработной платы» 2026: уточните по штатному расписанию и СОУТ."

PAYROLL_YEAR = "2026"
PAYROLL_PARAMS: dict[str, str] = {
    "year": PAYROLL_YEAR,
    "mrot": "27093",
    "annual_hours_40": "1972",
    "annual_hours_36": "1774.4",
    "work_days_year": "247",
    "holidays_year": "14",
    "night_pct": "0.20",
    "vacation_days_base": "28",
    "margin_share_warn": "0.70",
}

# Кривая машиниста и помощника: 45 ₽ на норме 1 500 м за 13 смен, 168,66 ₽ на
# потолке 2 400 м. Узлы с четырьмя знаками: с двумя премия при 2 400 м
# расходится с методикой на 0,24 ₽ (решения, §1).
DRILLER_SCALE: dict[str, str] = {
    "scale_type": "CURVE_POWER",
    "norm_per_shift": "115.3846",
    "rate_norm": "45",
    "ceiling_per_shift": "184.6154",
    "rate_ceiling": "168.66",
}

# Доп. тариф взносов по классу условий труда, ст. 428 НК РФ.
EXTRA_TARIFFS: tuple[dict[str, str], ...] = (
    {"work_conditions_class": "3.1", "rate": "0.02"},
    {"work_conditions_class": "3.2", "rate": "0.04"},
    {"work_conditions_class": "3.3", "rate": "0.06"},
    {"work_conditions_class": "3.4", "rate": "0.07"},
    {"work_conditions_class": "4", "rate": "0.08"},
)

HARDNESS_BANDS: tuple[dict[str, str | None], ...] = (
    {"f_from": None, "f_to": "8", "k": "0.9"},
    {"f_from": "8", "f_to": "12", "k": "1.0"},
    {"f_from": "12", "f_to": "16", "k": "1.1"},
    {"f_from": "16", "f_to": "18", "k": "1.2"},
    {"f_from": "18", "f_to": None, "k": "1.3"},
)
BASE_DIAMETER_MM = Decimal("152")
OWNER_DIAMETERS_MM: tuple[str, ...] = ("110", "127", "140", "152", "165", "190", "215", "250")

DOWNTIME_REASONS: tuple[tuple[str, str, bool, bool], ...] = (
    # код, наименование, не по вине машиниста, плановое ТОиР
    ("DT_WAIT_BLOCK", "Ожидание готовности блока", True, False),
    ("DT_RIG_REPAIR", "Ремонт станка не по вине машиниста", True, False),
    ("DT_BLASTING", "Взрывные работы", True, False),
    ("DT_WEATHER", "Погодные условия", True, False),
    ("DT_NO_SUPPLY", "Нет воды, топлива или энергии", True, False),
    ("DT_RELOCATION_ORDER", "Перегон по распоряжению", True, False),
    ("DT_PLANNED_MAINTENANCE", "Плановое ТОиР", True, True),
    ("DT_LATE", "Опоздание", False, False),
    ("DT_FAULT_BREAKDOWN", "Поломка по вине машиниста", False, False),
    ("DT_ABSENCE", "Отсутствие на смене", False, False),
)

_DRILLING = {
    "department": "DRILLING_BLASTING",
    "pay_system": "PIECE_PROGRESSIVE",
    "work_conditions_class": "3.2",
    "hazard_pct": "0.04",
    "extra_vacation_days": "7",
    "night_hours_per_shift": "8",
    "output_unit": "M",
    "output_source": "OWN_OUTPUT",
    "difficulty": "NORMALIZED_METERS",
}
_BLASTING = {"department": "DRILLING_BLASTING", "pay_system": "PIECE_PROGRESSIVE"}

# 14 должностей листа «Список должностей и формы премирования». Первые семь
# уже заведены импортом Cost V1 под этими кодами (сопоставление утвердил
# владелец 14.09.2026); наименование существующей записи сид не меняет.
POSITIONS: tuple[tuple[str, str, dict[str, str]], ...] = (
    ("POSITION_LABOR_DRILLER", "Машинист буровой установки", _DRILLING),
    ("POSITION_LABOR_ASSISTANT", "Помощник машиниста буровой установки", _DRILLING),
    ("POSITION_LABOR_DRIVER_SZM", "Водитель-оператор СЗМ", _BLASTING),
    ("POSITION_LABOR_BLASTERS", "Взрывник", _BLASTING),
    ("POSITION_LABOR_MASTER", "Мастер-взрывник", _BLASTING),
    ("POSITION_LABOR_MINER", "Горнорабочий", {**_BLASTING, "output_source": "SECTION_OUTPUT"}),
    ("POSITION_LABOR_DRIVER_DEL", "Водитель ДОПОГ (кат. B, C, E)", {"department": "TRANSPORT", "pay_system": "PIECE_BONUS"}),
    ("POSITION_LABOR_SENIOR_BLASTER", "Старший взрывник", _BLASTING),
    ("POSITION_LABOR_DRIVER", "Водитель (все категории)", {"department": "TRANSPORT", "pay_system": "PIECE_BONUS", "output_unit": "KM"}),
    ("POSITION_LABOR_LOADER_DRIVER", "Водитель погрузчика", {"department": "TRANSPORT", "pay_system": "PIECE_BONUS", "output_unit": "M3"}),
    ("POSITION_LABOR_VM_DISPENSER", "Раздатчик ВМ", {"department": "WAREHOUSE", "pay_system": "TIME_BONUS"}),
    ("POSITION_LABOR_STOREKEEPER", "Кладовщик", {"department": "WAREHOUSE", "pay_system": "TIME_BONUS"}),
    ("POSITION_LABOR_EMULSION_OPERATOR", "Аппаратчик линии ЭВВ", {"department": "WAREHOUSE", "pay_system": "PIECE_BONUS", "output_unit": "T"}),
    ("POSITION_LABOR_REPAIR_FITTER", "Слесарь по ремонту оборудования и автомобилей", {"department": "MAINTENANCE", "pay_system": "TIME_BONUS"}),
)
# Сопоставленные владельцем: ни одной из них в снимке — вероятно, не та организация.
MAPPED_POSITIONS: tuple[str, ...] = tuple(code for code, *_ in POSITIONS[:7])
SCALED_POSITIONS: tuple[str, ...] = ("POSITION_LABOR_DRILLER", "POSITION_LABOR_ASSISTANT")

KM_UNIT = ReferenceItem(
    code="KM",
    name="Километр",
    payload={"symbol": "км", "dimension": "length", "factor_to_base": 1000},
    source=SOURCE,
)


@dataclass
class PayrollSeedReport:
    added: list[str] = field(default_factory=list)
    filled: list[str] = field(default_factory=list)
    # Заданные значения, которые расходятся с файлом: сид их не меняет.
    kept: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    # Коды из `MAPPED_POSITIONS`, которые нашлись среди должностей снимка.
    matched_positions: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "added": list(self.added),
            "filled": list(self.filled),
            "kept": list(self.kept),
            "skipped": list(self.skipped),
            "matched_positions": list(self.matched_positions),
        }


def seed_payroll_references(
    snapshot: ReferenceSnapshot,
) -> tuple[dict[str, list[ReferenceItem]], PayrollSeedReport]:
    sections = {name: list(items) for name, items in normalize_sections(snapshot.sections).items()}
    report = PayrollSeedReport()
    _units(sections, report)
    _positions(sections, report)
    _driller_scales(sections, report)
    _extra_tariffs(sections, report)
    _payroll_params(sections, report)
    _drilling_difficulty(sections, report)
    _downtime_reasons(sections, report)
    return sections, report


def _empty(value: Any) -> bool:
    return value is None or value == "" or value == []


def _fill(item: ReferenceItem, values: Mapping[str, Any]) -> tuple[ReferenceItem, list[str]]:
    """Запись с заполненными пустыми ключами и список этих ключей."""

    filled = [key for key in values if _empty(item.payload.get(key))]
    if not filled:
        return item, []
    return replace(item, payload={**item.payload, **{key: values[key] for key in filled}}), filled


def _same(current: Any, expected: Any) -> bool:
    """Значение записи равно значению файла.

    Число приходит то строкой, то числом: `"0.04"`, `0.04` и `"0.040"` — одно
    значение. Списки (таблица доп. тарифов) сравниваются поэлементно той же
    функцией: длина совпадает, у строк-словарей совпадают ключи, а значения
    сравниваются рекурсивно — иначе таблица с теми же числами, но другого
    типа (`0.02` вместо `"0.02"`), считалась бы расходящейся с файлом.
    """

    if isinstance(current, list) or isinstance(expected, list):
        if not isinstance(current, list) or not isinstance(expected, list):
            return False
        if len(current) != len(expected):
            return False
        return all(_same(left, right) for left, right in zip(current, expected))
    if isinstance(current, Mapping) or isinstance(expected, Mapping):
        if not isinstance(current, Mapping) or not isinstance(expected, Mapping):
            return False
        if set(current.keys()) != set(expected.keys()):
            return False
        return all(_same(current[key], expected[key]) for key in current)
    if str(current) == str(expected):
        return True
    left = finite_decimal(current)
    return left is not None and left == finite_decimal(expected)


def _kept(prefix: str, item: ReferenceItem, values: Mapping[str, Any]) -> list[str]:
    """Строки отчёта о заданных значениях записи, которые расходятся с файлом."""

    lines: list[str] = []
    for key, expected in values.items():
        current = item.payload.get(key)
        if _empty(current) or _same(current, expected):
            continue
        if isinstance(expected, list):
            lines.append(f"{prefix}: {key} задан, отличается от файла")
        else:
            lines.append(f"{prefix}: {key}={current} (файл: {expected})")
    return lines


def _new(code: str, name: str, payload: Mapping[str, Any]) -> ReferenceItem:
    return ReferenceItem(code=code, name=name, payload=dict(payload), source=SOURCE, comment=_COMMENT)


def _units(sections: dict[str, list[ReferenceItem]], report: PayrollSeedReport) -> None:
    if any(item.code == KM_UNIT.code for item in sections["units"]):
        return
    sections["units"].append(KM_UNIT)
    report.added.append(f"units:{KM_UNIT.code}")


def _positions(sections: dict[str, list[ReferenceItem]], report: PayrollSeedReport) -> None:
    by_code = {item.code: index for index, item in enumerate(sections["positions"])}
    for code, name, values in POSITIONS:
        index = by_code.get(code)
        if index is None:
            # Новая должность — косвенная: в смету блока она попадёт, только
            # когда человек классифицирует её и включит в состав бригады.
            sections["positions"].append(_new(code, name, {"category": "INDIRECT", **values}))
            report.added.append(f"positions:{code}")
            continue
        item = sections["positions"][index]
        if code in MAPPED_POSITIONS and item.is_active:
            report.matched_positions.append(code)
        report.kept.extend(_kept(f"positions:{code}", item, values))
        updated, filled = _fill(item, values)
        if filled:
            sections["positions"][index] = updated
            report.filled.append(f"positions:{code}: {', '.join(filled)}")


def _driller_scales(sections: dict[str, list[ReferenceItem]], report: PayrollSeedReport) -> None:
    for code in SCALED_POSITIONS:
        index = next(
            (
                i
                for i, item in enumerate(sections["labor_rates"])
                if item.is_active
                and item.payload.get("position_code") == code
                and _empty(item.payload.get("condition_code"))
            ),
            None,
        )
        if index is None:
            # Новая ставка без условия бурения сменила бы выбор ставки в
            # расчёте по ставкам (`labor._labor_rate`) — не заводим.
            report.skipped.append(f"labor_rates:{code}: нет ставки без условия бурения, шкала не заведена")
            continue
        rate = sections["labor_rates"][index]
        report.kept.extend(_kept(f"labor_rates:{rate.code}", rate, DRILLER_SCALE))
        if not _empty(rate.payload.get("scale_type")):
            continue
        updated, filled = _fill(rate, DRILLER_SCALE)
        sections["labor_rates"][index] = updated
        report.filled.append(f"labor_rates:{rate.code}: {', '.join(filled)}")


def _extra_tariffs(sections: dict[str, list[ReferenceItem]], report: PayrollSeedReport) -> None:
    index = next((i for i, item in enumerate(sections["organization_rates"]) if item.is_active), None)
    if index is None:
        report.skipped.append("organization_rates: нет действующей записи, доп. тариф не заведён")
        return
    rates = sections["organization_rates"][index]
    values = {"extra_tariffs": [dict(row) for row in EXTRA_TARIFFS]}
    report.kept.extend(_kept(f"organization_rates:{rates.code}", rates, values))
    updated, filled = _fill(rates, values)
    if filled:
        sections["organization_rates"][index] = updated
        report.filled.append(f"organization_rates:{updated.code}: extra_tariffs")


def _payroll_params(sections: dict[str, list[ReferenceItem]], report: PayrollSeedReport) -> None:
    year = Decimal(PAYROLL_YEAR)
    if any(
        item.is_active and finite_decimal(item.payload.get("year")) == year
        for item in sections["payroll_params"]
    ):
        return
    code = f"PAYROLL_PARAMS_{PAYROLL_YEAR}"
    if any(item.code == code for item in sections["payroll_params"]):
        # Запись с этим кодом уже есть, но выключена (не тот год действует) —
        # новая с тем же кодом сломала бы публикацию на дубле.
        report.skipped.append(
            f"payroll_params:{code}: запись выключена — новая не заведена; включите её или смените код"
        )
        return
    sections["payroll_params"].append(_new(code, f"Параметры ФОТ {PAYROLL_YEAR}", PAYROLL_PARAMS))
    report.added.append(f"payroll_params:{code}")


def _bit_diameters(sections: dict[str, list[ReferenceItem]]) -> set[Decimal]:
    materials = {item.code: item for item in sections["materials"] if item.is_active}
    found: set[Decimal] = set()
    for condition in sections["drilling_conditions"]:
        if not condition.is_active:
            continue
        material = materials.get(str(condition.payload.get("bit_material_code") or ""))
        # Пустой, битый («abc», NaN) или неположительный диаметр (в
        # `MaterialPayload` это «диаметр не задан», а не ноль) пропускается:
        # о нём скажет проверка ревизии, таблица строится из остальных.
        diameter = finite_decimal(material.payload.get("diameter_mm")) if material is not None else None
        if diameter is None or diameter <= 0:
            continue
        try:
            (diameter / BASE_DIAMETER_MM).quantize(Decimal("0.01"), ROUND_HALF_UP)
        except ArithmeticError:
            # Коэффициент диаметра не вычисляется (огромный диаметр не
            # укладывается в точность Decimal) — коронка в таблицу не попадает.
            continue
        found.add(diameter.normalize())
    return found


def _drilling_difficulty_tables(sections: dict[str, list[ReferenceItem]]) -> dict[str, list[dict[str, Any]]]:
    """Таблицы владельца: полосы крепости и диаметры владельца ∪ коронок условий.

    Общая для новой записи и для заполнения пустых таблиц действующей —
    те же данные не должны собираться по-разному в двух местах.
    """

    diameters = sorted({Decimal(value) for value in OWNER_DIAMETERS_MM} | _bit_diameters(sections))
    return {
        "hardness": [dict(row) for row in HARDNESS_BANDS],
        # Стартовое k = Ø / 152 (показатель 1) до калибровки по факту.
        "diameter": [
            {
                "diameter_mm": format(diameter, "f"),
                "k": format((diameter / BASE_DIAMETER_MM).quantize(Decimal("0.01"), ROUND_HALF_UP), "f"),
            }
            for diameter in diameters
        ],
    }


def _drilling_difficulty(sections: dict[str, list[ReferenceItem]], report: PayrollSeedReport) -> None:
    index = next(
        (i for i, item in enumerate(sections["drilling_difficulty"]) if item.is_active), None
    )
    if index is None:
        code = "DRILLING_DIFFICULTY_BASE"
        if any(item.code == code for item in sections["drilling_difficulty"]):
            # Запись с этим кодом уже есть, но выключена — новая с тем же
            # кодом сломала бы публикацию на дубле.
            report.skipped.append(
                f"drilling_difficulty:{code}: запись выключена — новая не заведена; включите её или смените код"
            )
            return
        payload = _drilling_difficulty_tables(sections)
        sections["drilling_difficulty"].append(_new(code, "Сложность бурения: база f 10, Ø 152 мм", payload))
        report.added.append(f"drilling_difficulty:{code}")
        return
    # Форма даёт допустимую схемой действующую запись с пустыми таблицами
    # ({"hardness": [], "diameter": []}) — к ней те же _kept + _fill, что и
    # к остальным существующим записям; заданные таблицы сид не меняет.
    item = sections["drilling_difficulty"][index]
    values = _drilling_difficulty_tables(sections)
    report.kept.extend(_kept(f"drilling_difficulty:{item.code}", item, values))
    updated, filled = _fill(item, values)
    if filled:
        sections["drilling_difficulty"][index] = updated
        report.filled.append(f"drilling_difficulty:{updated.code}: {', '.join(filled)}")


def _downtime_reasons(sections: dict[str, list[ReferenceItem]], report: PayrollSeedReport) -> None:
    by_code = {item.code: index for index, item in enumerate(sections["downtime_reasons"])}
    for code, name, excusable, planned in DOWNTIME_REASONS:
        index = by_code.get(code)
        if index is None:
            sections["downtime_reasons"].append(
                _new(code, name, {"excusable": excusable, "planned_maintenance": planned})
            )
            report.added.append(f"downtime_reasons:{code}")
            continue
        item = sections["downtime_reasons"][index]
        values = {"excusable": excusable, "planned_maintenance": planned}
        report.kept.extend(_kept(f"downtime_reasons:{code}", item, values))
        updated, filled = _fill(item, values)
        if filled:
            sections["downtime_reasons"][index] = updated
            report.filled.append(f"downtime_reasons:{code}: {', '.join(filled)}")


__all__ = ["MAPPED_POSITIONS", "PayrollSeedReport", "seed_payroll_references"]
