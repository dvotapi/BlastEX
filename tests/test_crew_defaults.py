"""Должности БВР из импорта V1 становятся прямым персоналом, бригада — по умолчанию."""
from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

from cost.model.engine import compute_block_economics
from cost.model.inputs import CrewMember
from cost.v2.crew_defaults import DEFAULT_CREW_CODE, reclassify_positions
from cost.v2.models import ReferenceItem
from tests import model_fixtures as fx

IMPORTED = {
    "POSITION_LABOR_MASTER": "Руководитель взрывных работ (мастер БВР)",
    "POSITION_LABOR_BLASTERS": "Взрывники",
    "POSITION_LABOR_DRIVER_SZM": "Водитель СЗМ",
    "POSITION_LABOR_DRIVER_DEL": "Водитель доставщика",
    "POSITION_LABOR_MINER": "Горнорабочий",
    "POSITION_LABOR_DRILLER": "Бурильщик",
}


def imported_snapshot():
    """Как после импорта Cost V1: все должности косвенные, ставки есть."""

    positions = tuple(
        ReferenceItem(code=code, name=name, payload={"category": "INDIRECT"}, source="Cost V1")
        for code, name in IMPORTED.items()
    )
    rates = tuple(
        ReferenceItem(
            code=f"RATE_{code}",
            name=f"Ставка: {name}",
            payload={"position_code": code, "fixed_monthly_rub": "60000", "piece_rate_rub": "0.25"},
        )
        for code, name in IMPORTED.items()
    )
    return fx.references(
        positions=(*fx.POSITIONS, *positions),
        labor_rates=(*fx.LABOR_RATES, *rates),
    )


def test_blasting_positions_become_direct_with_operations() -> None:
    sections, report = reclassify_positions(imported_snapshot())

    positions = {item.code: item.payload for item in sections["positions"]}
    master = positions["POSITION_LABOR_MASTER"]
    assert master["category"] == "DIRECT"
    assert master["operation_code"] == "BLAST_EXECUTION"
    assert master["norm_operations_per_month"] == "10"
    assert master["piece_driver"] == "rock_volume_m3"
    assert positions["POSITION_LABOR_DRIVER_SZM"]["operation_code"] == "BULK_CHARGING_SZM"
    # Бурильщику норма выездов не нужна: его смены выводятся только из станка.
    assert "norm_operations_per_month" not in positions["POSITION_LABOR_DRILLER"]
    assert positions["POS_WAREHOUSE_HEAD"]["category"] == "INDIRECT"
    assert set(report.reclassified) == set(IMPORTED)
    assert report.missing == ["POSITION_LABOR_ASSISTANT"]


def test_default_crew_is_seven_people() -> None:
    sections, report = reclassify_positions(imported_snapshot())

    template = next(item for item in sections["crew_templates"] if item.code == DEFAULT_CREW_CODE)
    members = {m["position_code"]: Decimal(m["headcount"]) for m in template.payload["members"]}
    assert members == {
        "POSITION_LABOR_MASTER": 1,
        "POSITION_LABOR_BLASTERS": 2,
        "POSITION_LABOR_DRIVER_SZM": 1,
        "POSITION_LABOR_DRIVER_DEL": 1,
        "POSITION_LABOR_MINER": 2,
    }
    assert sum(members.values()) == 7
    assert template.payload["package_code"] == "DRILL_AND_BLAST"
    assert len(report.crew_members) == 5


def test_reclassification_is_idempotent() -> None:
    first, _ = reclassify_positions(imported_snapshot())
    again = replace(imported_snapshot(), sections={k: tuple(v) for k, v in first.items()})
    second, report = reclassify_positions(again)

    assert report.reclassified == []
    assert set(report.already_direct) == set(IMPORTED)
    assert [i.payload for i in second["positions"]] == [i.payload for i in first["positions"]]
    assert [i.code for i in second["crew_templates"]].count(DEFAULT_CREW_CODE) == 1


def test_reclassified_crew_produces_labor_lines() -> None:
    """Смысл всей операции: ФОТ мастера, взрывников и водителей появляется в смете."""

    sections, _ = reclassify_positions(imported_snapshot())
    references = replace(imported_snapshot(), sections={k: tuple(v) for k, v in sections.items()})
    crew = tuple(
        CrewMember(m["position_code"], Decimal(m["headcount"]))
        for item in sections["crew_templates"] if item.code == DEFAULT_CREW_CODE
        for m in item.payload["members"]
    )

    result = compute_block_economics(fx.snapshot(), fx.parameters(crew=crew), references)

    codes = {line.cost_item_code for line in result.lines}
    assert {"LABOR_POSITION_LABOR_MASTER", "LABOR_POSITION_LABOR_BLASTERS", "LABOR_POSITION_LABOR_MINER"} <= codes
    assert "LABOR_POSITION_LABOR_DRIVER_SZM" in codes
    assert {"LABOR_CONTRIBUTIONS", "LABOR_VACATION_RESERVE"} <= codes
    master = next(line for line in result.lines if line.cost_item_code == "LABOR_POSITION_LABOR_MASTER")
    # 60 000 ₽/мес / 21 см × 2,1 см на блок (21 / 10 взрывов) × 1 чел + сдельная 0,25 × 60 000 м³.
    assert master.amount_rub == Decimal("60000") / 21 * (Decimal("21") / 10) + Decimal("0.25") * 60000
    assert not any("норматив операций" in text for text in result.warnings)
