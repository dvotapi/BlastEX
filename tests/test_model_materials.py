"""Стоимость ВМ и средств инициирования по выбранной номенклатуре.

Количество берёт технический паспорт, вкладка выбирает наименование, цена
приходит из справочника. Проверяем именно эту цепочку.
"""
from __future__ import annotations

from decimal import Decimal

import pytest

from cost.model import materials
from cost.model.inputs import ModelContext
from cost.v2.models import CostLayer
from tests.model_fixtures import parameters, physical, references


def context(*, nomenclature=None, package_code="DRILL_AND_BLAST", **drivers) -> ModelContext:
    params = parameters(
        package_code=package_code,
        nomenclature=dict(nomenclature or {}),
        electric_detonators_qty=Decimal(str(drivers.pop("electric_detonators_qty", "0"))),
    )
    return ModelContext(references(), params, physical(**drivers))


def line(context: ModelContext, cost_item_code: str):
    return next(row for row in context.lines if row.cost_item_code == cost_item_code)


def test_explosive_line_is_mass_from_the_passport_times_the_current_price() -> None:
    ctx = context(nomenclature={"EXPLOSIVE": "MAT_EVERSIN"}, explosive_kg="29038.86")
    materials.compute(ctx)

    row = line(ctx, "MATERIAL_EXPLOSIVE")
    assert row.amount_rub == Decimal("29038.86") * Decimal("48.9")
    assert row.layer is CostLayer.VARIABLE
    assert row.operation_code == "EVV_MANUFACTURE_ON_SITE"
    assert row.cost_item_name == "ЭВВ Эверсин-100"
    assert "48.9 ₽/кг" in row.formula
    assert "material_prices.PR_EVERSIN" in row.formula


def test_downhole_nsi_is_priced_per_hole() -> None:
    ctx = context(nomenclature={"NSI_DOWNHOLE": "MAT_NSI"}, downhole_nsi="189")
    materials.compute(ctx)

    row = line(ctx, "MATERIAL_NSI_DOWNHOLE")
    assert row.amount_rub == Decimal("189") * Decimal("900")
    assert row.operation_code == "PRIMER_ASSEMBLY"


def test_surface_and_start_nsi_belong_to_the_initiation_network() -> None:
    ctx = context(
        nomenclature={"NSI_SURFACE": "MAT_NSI_SURFACE", "NSI_START": "MAT_NSI_START"},
        surface_nsi="189",
        start_nsi="2",
    )
    materials.compute(ctx)

    assert line(ctx, "MATERIAL_NSI_SURFACE").amount_rub == Decimal("189") * Decimal("240")
    assert line(ctx, "MATERIAL_NSI_START").amount_rub == Decimal("2") * Decimal("3210")
    assert line(ctx, "MATERIAL_NSI_SURFACE").operation_code == "INITIATION_NETWORK"


def test_booster_pieces_are_converted_to_kilograms() -> None:
    """Промежуточные детонаторы паспорт считает штуками, а справочник хранит цену килограмма."""

    ctx = context(nomenclature={"BOOSTER": "MAT_BOOSTER"}, intermediate_detonators="189")
    materials.compute(ctx)

    row = line(ctx, "MATERIAL_BOOSTER")
    assert row.amount_rub == Decimal("189") * Decimal("0.8") * Decimal("150")
    assert "189 шт × 0.8 кг" in row.formula


def test_electric_detonators_come_from_the_tab_not_the_passport() -> None:
    ctx = context(
        nomenclature={"DETONATOR_ELECTRIC": "MAT_DETONATOR_EL"}, electric_detonators_qty="4"
    )
    materials.compute(ctx)

    row = line(ctx, "MATERIAL_DETONATOR")
    assert row.amount_rub == Decimal("4") * Decimal("45")
    assert row.operation_code == "BLAST_EXECUTION"
    assert ctx.lineage["electric_detonators"] == "количество задано на вкладке"


def test_missing_selection_warns_and_adds_no_line() -> None:
    ctx = context(explosive_kg="100")
    materials.compute(ctx)

    assert not any(row.cost_item_code == "MATERIAL_EXPLOSIVE" for row in ctx.lines)
    assert any("Не выбрано основное ВВ" in text for text in ctx.warnings)


def test_missing_price_warns_and_adds_no_line() -> None:
    ctx = context(nomenclature={"EXPLOSIVE": "MAT_PROTOLIT"}, explosive_kg="100")
    materials.compute(ctx)

    assert not any(row.cost_item_code == "MATERIAL_EXPLOSIVE" for row in ctx.lines)
    assert any("нет цены" in text for text in ctx.warnings)


def test_unknown_code_warns_and_adds_no_line() -> None:
    ctx = context(nomenclature={"EXPLOSIVE": "MAT_GHOST"}, explosive_kg="100")
    materials.compute(ctx)

    assert ctx.lines == []
    assert any("MAT_GHOST" in text for text in ctx.warnings)


def test_booster_without_unit_mass_warns() -> None:
    ctx = context(nomenclature={"BOOSTER": "MAT_NSI"}, intermediate_detonators="10")
    materials.compute(ctx)

    assert ctx.lines == []
    assert any("масса единицы" in text for text in ctx.warnings)


def test_zero_driver_produces_neither_line_nor_warning() -> None:
    """Патронов нет — нет и строки: пустое место в смете не повод пугать сметчика."""

    ctx = context(explosive_kg="0", downhole_nsi="0", surface_nsi="0", start_nsi="0",
                  intermediate_detonators="0", boosters="0")
    materials.compute(ctx)

    assert ctx.lines == []
    assert ctx.warnings == []


def test_role_outside_the_package_is_skipped() -> None:
    ctx = context(
        nomenclature={"EXPLOSIVE": "MAT_EVERSIN"}, package_code="DRILLING", explosive_kg="100"
    )
    materials.compute(ctx)

    assert ctx.lines == []
    assert ctx.warnings == []


def test_every_role_is_allowed_by_the_reference_schema() -> None:
    """Модель и справочник должны знать один и тот же набор ролей."""

    from cost.v2.schemas import section_json_schema

    allowed = set(section_json_schema("materials")["properties"]["nomenclature_role"]["enum"])
    assert {role.code for role in materials.ROLES} <= allowed


def test_cost_rule_yields_to_the_selected_nomenclature() -> None:
    """Правило затрат на ВВ и выбранное наименование — это одна статья, не две."""

    from cost.model.engine import compute_block_economics

    result = compute_block_economics(
        {"physical": physical(), "lineage": {}},
        parameters(nomenclature={"EXPLOSIVE": "MAT_EVERSIN"}),
        references(),
    )

    explosive = [row for row in result.lines if row.cost_item_code == "MATERIAL_EXPLOSIVE"]
    assert len(explosive) == 1
    assert explosive[0].cost_item_name == "ЭВВ Эверсин-100"
    assert any("выбранная номенклатура" in text for text in result.warnings)


def test_cost_rule_still_works_without_a_selection() -> None:
    from cost.model.engine import compute_block_economics

    result = compute_block_economics(
        {"physical": physical(), "lineage": {}}, parameters(), references()
    )

    explosive = [row for row in result.lines if row.cost_item_code == "MATERIAL_EXPLOSIVE"]
    assert len(explosive) == 1
    assert explosive[0].cost_item_name == "Гранулит на блок"
