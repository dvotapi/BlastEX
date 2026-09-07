"""Стоимость ВМ и средств инициирования по выбранной номенклатуре.

Количество берёт технический паспорт, вкладка выбирает наименование, цена
приходит из справочника. Проверяем именно эту цепочку — и то, как она
уживается с правилами затрат, которые считали ВМ раньше.
"""
from __future__ import annotations

from decimal import Decimal

from cost.model import materials
from cost.model.engine import compute_block_economics
from cost.model.inputs import ModelContext
from cost.v2.models import CostLayer
from tests.model_fixtures import parameters, physical, references


def context(
    *, nomenclature=None, package_code="DRILL_AND_BLAST", electric_detonators_qty="0", **drivers
) -> ModelContext:
    params = parameters(
        package_code=package_code,
        nomenclature=dict(nomenclature or {}),
        electric_detonators_qty=Decimal(electric_detonators_qty),
    )
    return ModelContext(references(), params, physical(**drivers))


def run(ctx: ModelContext, rule_drivers: set[str] | None = None) -> materials.MaterialsOutcome:
    """Модуль плюс предупреждения — как их выдаст движок после правил затрат."""

    outcome = materials.compute(ctx)
    materials.report_gaps(ctx, outcome, rule_drivers or set())
    return outcome


def line(ctx: ModelContext, cost_item_code: str):
    return next(row for row in ctx.lines if row.cost_item_code == cost_item_code)


def lines(result, cost_item_code: str):
    return [row for row in result.lines if row.cost_item_code == cost_item_code]


def test_explosive_line_is_mass_from_the_passport_times_the_current_price() -> None:
    ctx = context(nomenclature={"EXPLOSIVE": "MAT_EVERSIN"}, explosive_kg="29038.86")
    run(ctx)

    row = line(ctx, "MATERIAL_EXPLOSIVE")
    assert row.amount_rub == Decimal("29038.86") * Decimal("48.9")
    assert row.layer is CostLayer.VARIABLE
    assert row.operation_code == "EVV_MANUFACTURE_ON_SITE"
    assert row.cost_item_name == "ЭВВ Эверсин-100"
    assert "48.9 ₽/кг" in row.formula
    assert "material_prices.PR_EVERSIN" in row.formula


def test_downhole_nsi_is_priced_per_hole() -> None:
    ctx = context(nomenclature={"NSI_DOWNHOLE": "MAT_NSI"}, downhole_nsi="189")
    run(ctx)

    row = line(ctx, "MATERIAL_NSI_DOWNHOLE")
    assert row.amount_rub == Decimal("189") * Decimal("900")
    assert row.operation_code == "PRIMER_ASSEMBLY"


def test_surface_and_start_nsi_belong_to_the_initiation_network() -> None:
    ctx = context(
        nomenclature={"NSI_SURFACE": "MAT_NSI_SURFACE", "NSI_START": "MAT_NSI_START"},
        surface_nsi="189",
        start_nsi="2",
    )
    run(ctx)

    assert line(ctx, "MATERIAL_NSI_SURFACE").amount_rub == Decimal("189") * Decimal("240")
    assert line(ctx, "MATERIAL_NSI_START").amount_rub == Decimal("2") * Decimal("3210")
    assert line(ctx, "MATERIAL_NSI_SURFACE").operation_code == "INITIATION_NETWORK"


def test_booster_pieces_are_converted_to_kilograms() -> None:
    """Промежуточные детонаторы паспорт считает штуками, а справочник хранит цену килограмма."""

    ctx = context(nomenclature={"BOOSTER": "MAT_BOOSTER"}, intermediate_detonators="189")
    run(ctx)

    row = line(ctx, "MATERIAL_BOOSTER")
    assert row.amount_rub == Decimal("189") * Decimal("0.8") * Decimal("150")
    assert "189 шт × 0.8 кг" in row.formula


def test_electric_detonators_come_from_the_tab_not_the_passport() -> None:
    ctx = context(
        nomenclature={"DETONATOR_ELECTRIC": "MAT_DETONATOR_EL"}, electric_detonators_qty="4"
    )
    run(ctx)

    row = line(ctx, "MATERIAL_DETONATOR")
    assert row.amount_rub == Decimal("4") * Decimal("45")
    assert row.operation_code == "BLAST_EXECUTION"
    assert ctx.lineage["electric_detonators"] == "количество задано на вкладке"


def test_contour_package_charges_explosive_through_garland_charging() -> None:
    """В контурном взрывании нет изготовления ЭВВ на месте — ВВ идёт в монтаж гирлянд."""

    ctx = context(
        nomenclature={"EXPLOSIVE": "MAT_EVERSIN", "NSI_DOWNHOLE": "MAT_NSI"},
        package_code="CONTOUR_BLASTING",
        explosive_kg="100",
        downhole_nsi="10",
    )
    run(ctx)

    assert line(ctx, "MATERIAL_EXPLOSIVE").operation_code == "GARLAND_CHARGING"
    assert line(ctx, "MATERIAL_NSI_DOWNHOLE").operation_code == "GARLAND_CHARGING"


def test_missing_selection_warns_when_nobody_charged_the_item() -> None:
    ctx = context(explosive_kg="100")
    run(ctx)

    assert not any(row.cost_item_code == "MATERIAL_EXPLOSIVE" for row in ctx.lines)
    assert any("Не выбрано: основное ВВ" in text for text in ctx.warnings)


def test_missing_selection_is_silent_when_a_cost_rule_charged_the_item() -> None:
    """Правило затрат по массе ВВ — прежний путь; ругаться на него нельзя."""

    ctx = context(explosive_kg="100")
    run(ctx, rule_drivers={"explosive_kg"})

    assert not any("основное ВВ" in text for text in ctx.warnings)
    # Позиции, которых не закрыло ни правило, ни выбор, остаются предупреждением.
    assert any("промежуточный детонатор" in text for text in ctx.warnings)


def test_missing_price_names_the_fallback_rule() -> None:
    ctx = context(nomenclature={"EXPLOSIVE": "MAT_PROTOLIT"}, explosive_kg="100")
    run(ctx, rule_drivers={"explosive_kg"})

    assert not any(row.cost_item_code == "MATERIAL_EXPLOSIVE" for row in ctx.lines)
    assert any("нет цены" in text and "посчитано по правилу затрат" in text for text in ctx.warnings)


def test_missing_price_without_a_rule_says_the_item_is_unpriced() -> None:
    ctx = context(nomenclature={"EXPLOSIVE": "MAT_PROTOLIT"}, explosive_kg="100")
    run(ctx)

    assert any("нет цены" in text and "не оценено в деньгах" in text for text in ctx.warnings)


def test_unknown_code_warns_and_adds_no_line() -> None:
    ctx = context(nomenclature={"EXPLOSIVE": "MAT_GHOST"}, explosive_kg="100")
    run(ctx)

    assert ctx.lines == []
    assert any("MAT_GHOST" in text for text in ctx.warnings)


def test_booster_without_unit_mass_warns() -> None:
    ctx = context(nomenclature={"BOOSTER": "MAT_NSI"}, intermediate_detonators="10")
    run(ctx)

    assert ctx.lines == []
    assert any("масса единицы" in text for text in ctx.warnings)


def test_zero_driver_produces_neither_line_nor_warning() -> None:
    """Патронов нет — нет и строки: пустое место в смете не повод пугать сметчика."""

    ctx = context(explosive_kg="0", downhole_nsi="0", surface_nsi="0", start_nsi="0",
                  intermediate_detonators="0", boosters="0")
    run(ctx)

    assert ctx.lines == []
    assert ctx.warnings == []


def test_package_without_charging_is_skipped_silently() -> None:
    ctx = context(
        nomenclature={"EXPLOSIVE": "MAT_EVERSIN"}, package_code="DRILLING", explosive_kg="100"
    )
    run(ctx)

    assert ctx.lines == []
    assert ctx.warnings == []


def test_every_role_is_allowed_by_the_reference_schema() -> None:
    """Модель и справочник должны знать один и тот же набор ролей."""

    from cost.v2.schemas import section_json_schema

    allowed = set(section_json_schema("materials")["properties"]["nomenclature_role"]["enum"])
    assert {role.code for role in materials.ROLES} <= allowed


# --- вместе с правилами затрат (через движок) ------------------------------


def test_cost_rule_yields_to_the_selected_nomenclature_by_driver() -> None:
    """Правило на НСИ пишет статью MATERIAL_NSI, роль — MATERIAL_NSI_DOWNHOLE: коды разные,
    драйвер один, и строка должна быть одна."""

    result = compute_block_economics(
        {"physical": physical(), "lineage": {}},
        parameters(nomenclature={"EXPLOSIVE": "MAT_EVERSIN", "NSI_DOWNHOLE": "MAT_NSI"}),
        references(),
    )

    assert [row.cost_item_name for row in lines(result, "MATERIAL_EXPLOSIVE")] == ["ЭВВ Эверсин-100"]
    assert [row.cost_item_name for row in lines(result, "MATERIAL_NSI_DOWNHOLE")] == ["НСИ скважинное"]
    assert lines(result, "MATERIAL_NSI") == []
    assert sum("выбранная номенклатура" in text for text in result.warnings) == 2


def test_cost_rules_still_price_materials_without_a_selection_and_do_not_warn() -> None:
    result = compute_block_economics(
        {"physical": physical(), "lineage": {}}, parameters(), references()
    )

    assert [row.cost_item_name for row in lines(result, "MATERIAL_EXPLOSIVE")] == ["Гранулит на блок"]
    assert lines(result, "MATERIAL_NSI") != []
    assert not any("основное ВВ" in text for text in result.warnings)
    assert not any("скважинное НСИ" in text for text in result.warnings)


def test_selection_without_a_price_falls_back_to_the_rule_and_says_so() -> None:
    result = compute_block_economics(
        {"physical": physical(), "lineage": {}},
        parameters(nomenclature={"EXPLOSIVE": "MAT_PROTOLIT"}),
        references(),
    )

    assert [row.cost_item_name for row in lines(result, "MATERIAL_EXPLOSIVE")] == ["Гранулит на блок"]
    assert any("Протолит" in text and "посчитано по правилу затрат" in text for text in result.warnings)
    assert not any("не оценено в деньгах" in text for text in result.warnings)
