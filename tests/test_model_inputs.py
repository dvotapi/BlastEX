"""Параметры модели: всё, чего нет в техническом паспорте."""
from __future__ import annotations

from decimal import Decimal

from cost.model.inputs import ModelParameters


def test_parameters_carry_the_nomenclature_selection() -> None:
    params = ModelParameters.from_dict(
        {
            "package_code": "DRILL_AND_BLAST",
            "nomenclature": {"EXPLOSIVE": "MAT_VV_EVERSIN", "NSI_DOWNHOLE": "MAT_NSI_90"},
            "electric_detonators_qty": "2",
        }
    )
    assert params.nomenclature["EXPLOSIVE"] == "MAT_VV_EVERSIN"
    assert params.electric_detonators_qty == Decimal("2")


def test_empty_selection_does_not_reach_the_model() -> None:
    """Пустая строка из селекта — «не выбрано», а не выбор номенклатуры с пустым кодом."""

    params = ModelParameters.from_dict(
        {"package_code": "DRILL_AND_BLAST", "nomenclature": {"EXPLOSIVE": "", "BOOSTER": None}}
    )
    assert params.nomenclature == {}


def test_selection_survives_the_round_trip() -> None:
    params = ModelParameters.from_dict(
        {
            "package_code": "DRILL_AND_BLAST",
            "nomenclature": {"NSI_SURFACE": "MAT_SURFACE_NSI_5"},
            "electric_detonators_qty": "4",
        }
    )
    restored = ModelParameters.from_dict(params.to_dict())
    assert restored.nomenclature == {"NSI_SURFACE": "MAT_SURFACE_NSI_5"}
    assert restored.electric_detonators_qty == Decimal("4")


def test_parameters_without_nomenclature_stay_valid() -> None:
    params = ModelParameters.from_dict({"package_code": "DRILLING"})
    assert params.nomenclature == {}
    assert params.electric_detonators_qty == Decimal("0")
