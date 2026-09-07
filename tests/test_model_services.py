"""Ручные услуги прогона: проживание, медосмотр, сторонние организации."""
from __future__ import annotations

from decimal import Decimal

from cost.model import logistics, services
from cost.model.engine import compute_block_economics
from cost.model.inputs import ModelContext, ServiceCharge
from cost.model.services import service_code
from cost.v2.models import CostLayer
from tests import model_fixtures as fx


def _context(*charges: ServiceCharge, **params) -> ModelContext:
    return ModelContext(fx.references(), fx.parameters(services=charges, **params), fx.physical())


def _line(context: ModelContext, name: str):
    return next(row for row in context.lines if row.cost_item_name == name)


def test_flat_service_becomes_a_cost_line_of_the_chosen_layer() -> None:
    context = _context(
        ServiceCharge("Проживание и питание", Decimal("120000"), "project_direct", "BLAST_EXECUTION")
    )
    services.compute(context)

    line = _line(context, "Проживание и питание")
    assert line.amount_rub == Decimal("120000")
    assert line.layer is CostLayer.PROJECT_DIRECT
    assert line.operation_code == "BLAST_EXECUTION"
    assert line.cost_item_code == "SERVICE_PROZHIVANIE_I_PITANIE"
    assert line.formula == "введено на вкладке"


def test_per_shift_service_multiplies_by_the_operation_shifts() -> None:
    """Медосмотр экипажа СЗМ — за каждую смену заряжания: четыре рейса, четыре смены."""

    context = _context(
        ServiceCharge("Предрейсовый медосмотр", Decimal("350"), "project_direct", "BULK_CHARGING_SZM", per_shift=True)
    )
    logistics.compute(context)
    services.compute(context)

    line = _line(context, "Предрейсовый медосмотр")
    assert line.amount_rub == Decimal("350") * 4
    assert "4 см × 350 ₽/см" in line.formula


def test_per_shift_service_without_shifts_is_charged_once_and_warns() -> None:
    context = _context(
        ServiceCharge("Выпуск на линию", Decimal("500"), "variable", "VM_DELIVERY_SITE", per_shift=True)
    )
    logistics.compute(context)  # патронов в паспорте нет — рейсов доставщика тоже
    services.compute(context)

    assert _line(context, "Выпуск на линию").amount_rub == Decimal("500")
    assert any("Выпуск на линию" in text and "разов" in text for text in context.warnings)


def test_service_outside_the_package_is_skipped() -> None:
    context = _context(
        ServiceCharge("Услуга бурового подрядчика", Decimal("1"), "variable", "PRODUCTION_DRILLING"),
        package_code="BLASTING_NO_DRILLING",
    )
    services.compute(context)

    assert context.lines == []


def test_service_already_in_cost_rules_is_not_charged_twice() -> None:
    """После переноса в справочник строка вкладки уступает правилу и говорит об этом."""

    rule = fx.item(
        service_code("Проживание и питание"),
        "Проживание и питание",
        {
            "operation_code": "BLAST_EXECUTION",
            "cost_item_code": service_code("Проживание и питание"),
            "behavior_type": "FIXED",
            "cost_layer": "project_direct",
            "fixed_rub": "120000",
        },
    )
    result = compute_block_economics(
        fx.snapshot(),
        fx.parameters(
            services=(ServiceCharge("Проживание и питание", Decimal("120000"), "project_direct", "BLAST_EXECUTION"),)
        ),
        fx.references(cost_rules=(*fx.COST_RULES, rule)),
    )

    lodging = [row for row in result.lines if row.cost_item_name == "Проживание и питание"]
    assert len(lodging) == 1
    assert any("уже есть в правилах затрат" in text for text in result.warnings)


def test_service_code_is_a_stable_latin_code() -> None:
    assert service_code("Проживание и питание") == "SERVICE_PROZHIVANIE_I_PITANIE"
    assert service_code("  Услуги ООО «Взрыв-Сервис» №2 ") == "SERVICE_USLUGI_OOO_VZRYV_SERVIS_2"
    assert len(service_code("х" * 200)) <= 80


def test_services_survive_the_parameters_round_trip() -> None:
    params = fx.parameters(
        services=(ServiceCharge("Медосмотр", Decimal("350"), "variable", "BULK_CHARGING_SZM", per_shift=True),)
    )
    restored = type(params).from_dict(params.to_dict())

    assert restored.services == params.services
