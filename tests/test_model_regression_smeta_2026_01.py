"""Регрессия модели на рабочей смете БВР.

Источник — «Смета ТГ от 23.03.2026.xlsx», лист «Расчет стоимости БВР»,
столбец «БВР сухие» (гранулит, блок 30 000 м³, сетка 4×4, глубина 11,5,
перебур 1). Справочники и паспорт вынесены в `tests/fixtures/smeta_2026_01/`.

Сходятся с допуском 1 %: раздел 1.1 (ВМ), 1.2 (прямые расходы бурения на
метр), 2.3 (ФОТ блока), 2.5 (амортизация СЗМ).

Расхождения зафиксированы осознанно (см. `README.md` фикстуры):

* 1.2 — в смете цена метра (1 008,67 ₽) включает ОПР 100 000 ₽, накладные
  100 000 ₽ и прибыль ×1,2. В модели ОПР — постоянная затрата юнита, а
  прибыль — шаг надбавок, поэтому сравнивается «итого прямые расходы».
  Сама смета в D37 забыла слагаемое D18 (буровая оснастка, 10,33 ₽/м) —
  здесь оно учтено.
* 1.2 ФОТ бурильщиков (250,59 ₽/м) в смете сидит внутри цены метра и
  умножается на 1,42; в модели это ФОТ блока со взносами 30,42 % и резервом
  отпусков 20 %. Поэтому из сравнения метра ФОТ исключён.
* 2.1 (хранение 51 000 ₽) — в смете константа; в модели склад считается
  ёмкостью ресурсного пула по плану юнита.
* 2.2 (суточные 5 000 ₽) — в смете «чел × смен/2 × 1000 ₽»; в модели
  начисляется по чел-сменам и только на вахтовом объекте.
* 2.4 (ГСМ 24 480 ₽) — в смете четыре машины по 300 км с общей нормой; в
  модели ДТ считается по норме каждой машины на её собственные рейсы.
* 2.6 (ОПР 77 700 ₽) — в модели это постоянные затраты юнита,
  распределяемые по плановому объёму, а не сумма на блок.
"""
from __future__ import annotations

import json
from dataclasses import replace
from decimal import Decimal
from pathlib import Path

import pytest

from cost.model.engine import compute_block_economics
from cost.model.inputs import ModelParameters
from cost.v2.models import ReferenceItem, ReferenceSnapshot
from cost.v2.references import default_reference_snapshot


FIXTURES = Path(__file__).parent / "fixtures" / "smeta_2026_01"
TOLERANCE = Decimal("0.01")


def _references() -> ReferenceSnapshot:
    data = json.loads((FIXTURES / "references.json").read_text(encoding="utf-8"))
    base = default_reference_snapshot()
    sections = dict(base.sections)
    for section, items in data["sections"].items():
        sections[section] = tuple(ReferenceItem.from_dict(item) for item in items)
    return replace(base, revision_id="SMETA-2026-01", sections=sections)


def _passport() -> dict:
    return json.loads((FIXTURES / "passport.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def result():
    passport = _passport()
    params = ModelParameters.from_dict(passport["parameters"])
    return compute_block_economics(
        {"physical": passport["physical"], "lineage": {}},
        params,
        _references(),
        passport_name=passport["object_name"],
    ), passport["excel"]


def _sum(economics, *codes: str) -> Decimal:
    return sum(
        (line.amount_rub for line in economics.lines if line.cost_item_code in codes),
        Decimal("0"),
    )


def _within(actual: Decimal, expected: float, tolerance: Decimal = TOLERANCE) -> bool:
    reference = Decimal(str(expected))
    return abs(actual - reference) / reference <= tolerance


def test_section_1_1_materials(result) -> None:
    economics, excel = result
    materials = _sum(
        economics,
        "MATERIAL_EXPLOSIVE",
        "MATERIAL_NSI_DOWNHOLE",
        "MATERIAL_NSI_DUPLICATE",
        "MATERIAL_NSI_SURFACE",
        "MATERIAL_NSI_START",
    )
    assert _within(materials, excel["section_1_1_materials_rub"])


def test_section_1_2_drilling_direct_cost_per_metre(result) -> None:
    economics, excel = result
    drilling_m = economics.natural.values["drilling_m"]
    drilling_lines = _sum(
        economics,
        "DRILL_TOOLING",
        "DRILL_FUEL",
        "DRILL_SPARE_PARTS",
        "DRILL_INSPECTION",
        "DRILL_DEPRECIATION",
    )
    per_metre = drilling_lines / drilling_m
    # Смета: «итого прямые» минус ФОТ бурильщиков плюс забытая в D37 оснастка.
    expected = (
        Decimal(str(excel["drilling_direct_rub_per_m"]))
        - Decimal(str(excel["drilling_labor_rub_per_m"]))
        + Decimal("10.333")
    )
    assert abs(per_metre - expected) / expected <= TOLERANCE


def test_drilling_cost_components_match_the_sheet(result) -> None:
    economics, excel = result
    drilling_m = economics.natural.values["drilling_m"]
    tooling = _sum(economics, "DRILL_TOOLING") / drilling_m
    fuel = _sum(economics, "DRILL_FUEL") / drilling_m
    spare = _sum(economics, "DRILL_SPARE_PARTS") / drilling_m

    assert _within(tooling, excel["drilling_tooling_rub_per_m"])
    assert _within(fuel, excel["drilling_fuel_rub_per_m"])
    assert _within(spare, excel["drilling_spare_parts_rub_per_m"])


def test_commercial_speed_and_shifts_match_the_sheet(result) -> None:
    economics, _ = result
    natural = economics.natural.values

    assert natural["v_commercial_m_per_shift"] == Decimal("120")
    assert round(float(natural["rig_shifts"]), 3) == 17.626


def test_section_2_3_block_labor(result) -> None:
    economics, excel = result
    # ФОТ бурильщика в смете сидит в цене метра (раздел 1.2), поэтому
    # сравнивается ФОТ блока без него и с его долей отчислений.
    block_positions = _sum(
        economics,
        "LABOR_POS_MASTER",
        "LABOR_POS_BLASTER",
        "LABOR_POS_SZM_DRIVER",
        "LABOR_POS_DELIVERY_DRIVER",
    )
    contributions = block_positions * Decimal("0.3042")
    reserve = (block_positions + contributions) * Decimal("0.20")
    assert _within(block_positions + contributions + reserve, excel["section_2_3_labor_rub"])


def test_section_2_5_szm_depreciation(result) -> None:
    economics, excel = result
    natural = economics.natural.values
    assert natural["szm_shifts"] == Decimal(str(excel["szm_shifts"]))

    szm = _sum(economics, "SZM_DEPRECIATION")
    expected = Decimal(str(excel["szm_depreciation_rub_per_shift"])) * Decimal(
        str(excel["szm_shifts"])
    )
    assert _within(szm, float(expected))


def test_documented_deviations_are_visible_not_silent(result) -> None:
    """Расхождения с Excel не прячутся: их видно в структуре и параметрах."""

    economics, _ = result
    codes = {line.cost_item_code for line in economics.lines}
    # 2.6 сметы стала постоянной затратой юнита, распределяемой по плану.
    assert "UNIT_UFC_OPR" in codes
    # 2.2 сметы: на невахтовом объекте суточные не начисляются.
    assert "LABOR_PER_DIEM" not in codes
