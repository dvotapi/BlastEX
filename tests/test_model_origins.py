"""Происхождение количества и цены строк сметы: паспорт, расчёт, справочник, норматив, ручной ввод."""
from decimal import Decimal

from cost.model.engine import compute_block_economics
from cost.model.inputs import CrewMember
from tests import model_fixtures as fx

NOMENCLATURE = {"EXPLOSIVE": "MAT_ANFO", "NSI_DOWNHOLE": "MAT_NSI"}


def _lines():
    result = compute_block_economics(fx.snapshot(), fx.parameters(nomenclature=NOMENCLATURE), fx.references())
    return {line.cost_item_code: line for line in result.lines}


def test_material_quantity_comes_from_passport_and_price_from_reference() -> None:
    line = _lines()["MATERIAL_EXPLOSIVE"]
    assert line.quantity_origin == "PASSPORT"
    assert line.price_origin == "REFERENCE"


def test_crew_shifts_are_normative_until_edited() -> None:
    normative = _lines()["LABOR_POS_BLASTER"]
    assert normative.quantity_origin == "NORM"

    edited = compute_block_economics(
        fx.snapshot(),
        fx.parameters(
            nomenclature=NOMENCLATURE,
            crew=(CrewMember("POS_BLASTER", Decimal("2"), Decimal("4")),),
        ),
        fx.references(),
    )
    line = next(row for row in edited.lines if row.cost_item_code == "LABOR_POS_BLASTER")
    assert line.quantity_origin == "MANUAL"


def test_every_line_serializes_its_origins() -> None:
    for line in _lines().values():
        payload = line.to_dict()
        assert "quantity_origin" in payload and "price_origin" in payload
