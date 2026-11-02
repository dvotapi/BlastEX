"""ТОиР и запчасти по возрасту машины: процент первоначальной стоимости (шкала типа техники)."""
from datetime import date
from decimal import Decimal

import pytest
from pydantic import ValidationError

from cost.model import age_scale, drilling, equipment
from cost.model.inputs import ModelContext
from cost.v2.schemas.equipment import EquipmentTypePayload
from tests import model_fixtures as fx

AS_OF = date(2026, 11, 2)
TIERS = [
    {"upto_years": "2", "maintenance_pct": "2", "spare_parts_pct": "4"},
    {"upto_years": "4", "maintenance_pct": "4", "spare_parts_pct": "6"},
    {"upto_years": "7", "maintenance_pct": "6", "spare_parts_pct": "8"},
    {"upto_years": None, "maintenance_pct": "8", "spare_parts_pct": "10"},
]


def _rig_type(**extra):
    base = next(item for item in fx.EQUIPMENT_TYPES if item.code == "RIG_JK830")
    return fx.item(base.code, base.name, {**base.payload, "maintenance_mode": "AGE_SCALE", "maintenance_age_tiers": TIERS, **extra})


def _rig_asset(commissioned: str | None, **extra):
    base = next(item for item in fx.EQUIPMENT_ASSETS if item.code == "ASSET_RIG")
    payload = {**base.payload, **extra}
    if commissioned is not None:
        payload["commissioned_on"] = commissioned
    return fx.item(base.code, base.name, payload)


def _context(rig_type, asset, **params):
    types = tuple(rig_type if item.code == rig_type.code else item for item in fx.EQUIPMENT_TYPES)
    assets = tuple(asset if item.code == asset.code else item for item in fx.EQUIPMENT_ASSETS)
    references = fx.references(equipment_types=types, equipment_assets=assets)
    return ModelContext(references, fx.parameters(**params), fx.physical(), as_of=AS_OF)


def _line(context, code):
    return next(line for line in context.lines if line.cost_item_code == code)


# --- выбор ступени --------------------------------------------------------------


def test_age_is_counted_from_commissioning_to_the_calculation_date() -> None:
    assert age_scale.age_in_years(date(2024, 11, 2), AS_OF) == pytest.approx(Decimal("2.0"), abs=Decimal("0.01"))
    assert age_scale.age_in_years(date(2027, 1, 1), AS_OF) == 0


@pytest.mark.parametrize(
    ("age", "maintenance_pct"),
    [(Decimal("0.5"), "2"), (Decimal("1.99"), "2"), (Decimal("2"), "4"), (Decimal("6.9"), "6"), (Decimal("7"), "8"), (Decimal("30"), "8")],
)
def test_tier_is_the_first_whose_bound_exceeds_the_age(age: Decimal, maintenance_pct: str) -> None:
    tier = age_scale.pick_tier(TIERS, age)
    assert tier is not None and tier["maintenance_pct"] == maintenance_pct


# --- станок -----------------------------------------------------------------------


def test_rig_maintenance_and_spare_parts_follow_the_age_tier() -> None:
    """JK830 введён 01.04.2026: возраст 0,6 года — ступень «до 2 лет» (2 % ТОиР, 4 % запчасти)."""

    context = _context(_rig_type(), _rig_asset("2026-04-01"))
    norms = drilling.compute(context)
    assert norms is not None

    initial, plan = Decimal("28450000"), Decimal("40")
    maintenance = _line(context, "DRILL_MAINTENANCE")
    spare_parts = _line(context, "DRILL_SPARE_PARTS")
    assert maintenance.unit_price_rub == initial * Decimal("2") / 100 / (plan * 12)
    assert spare_parts.unit_price_rub == initial * Decimal("4") / 100 / (plan * 12)
    # ТОиР — на рабочие смены и смены ТОиР, запчасти — только на рабочие.
    assert maintenance.quantity == norms.rig_shifts + norms.maintenance_shifts
    assert spare_parts.quantity == norms.rig_shifts
    assert maintenance.price_origin == "CALC" and spare_parts.price_origin == "CALC"
    assert "до 2 лет" in maintenance.formula and "% /" in maintenance.formula


def test_older_rig_lands_on_a_higher_tier() -> None:
    """TM255 2016 года: больше 7 лет — последняя ступень (8 % / 10 %)."""

    context = _context(_rig_type(), _rig_asset("2016-01-01"))
    drilling.compute(context)

    initial, plan = Decimal("28450000"), Decimal("40")
    assert _line(context, "DRILL_MAINTENANCE").unit_price_rub == initial * Decimal("8") / 100 / (plan * 12)
    assert _line(context, "DRILL_SPARE_PARTS").unit_price_rub == initial * Decimal("10") / 100 / (plan * 12)
    assert "старше" in _line(context, "DRILL_MAINTENANCE").formula


def test_manual_plan_shifts_change_the_rate_per_shift() -> None:
    """Плановые смены — параметр вкладки: 20 смен вместо 40 удваивают ставку за смену."""

    context = _context(_rig_type(), _rig_asset("2026-04-01"), rig_plan_shifts=Decimal("20"))
    drilling.compute(context)

    assert _line(context, "DRILL_MAINTENANCE").unit_price_rub == Decimal("28450000") * Decimal("2") / 100 / (Decimal("20") * 12)


def test_rig_without_commissioning_date_falls_back_to_per_shift_rates_with_a_warning() -> None:
    context = _context(_rig_type(), _rig_asset(None))
    drilling.compute(context)

    assert _line(context, "DRILL_MAINTENANCE").unit_price_rub == Decimal("750")
    assert _line(context, "DRILL_SPARE_PARTS").unit_price_rub == Decimal("2750")
    assert _line(context, "DRILL_MAINTENANCE").price_origin == "REFERENCE"
    assert any("дата ввода" in warning for warning in context.warnings)


def test_future_commissioning_date_counts_as_new_but_warns() -> None:
    context = _context(_rig_type(), _rig_asset("2062-04-01"))
    drilling.compute(context)

    assert _line(context, "DRILL_MAINTENANCE").unit_price_rub == Decimal("28450000") * Decimal("2") / 100 / (Decimal("40") * 12)
    assert any("позже даты расчёта" in warning for warning in context.warnings)


def test_broken_commissioning_date_falls_back_and_names_the_value() -> None:
    context = _context(_rig_type(), _rig_asset("01.04.2026"))
    drilling.compute(context)

    assert _line(context, "DRILL_MAINTENANCE").unit_price_rub == Decimal("750")
    assert any("не разобрана" in warning and "01.04.2026" in warning for warning in context.warnings)


def test_rig_without_initial_cost_falls_back_with_a_warning() -> None:
    context = _context(_rig_type(), _rig_asset("2026-04-01", initial_cost_rub="0", depreciation_per_shift_rub="1000"))
    drilling.compute(context)

    assert _line(context, "DRILL_MAINTENANCE").unit_price_rub == Decimal("750")
    assert any("первоначальная стоимость" in warning for warning in context.warnings)


def test_rig_without_asset_falls_back_with_a_warning() -> None:
    references = fx.references(
        equipment_types=tuple(_rig_type() if item.code == "RIG_JK830" else item for item in fx.EQUIPMENT_TYPES),
        equipment_assets=tuple(item for item in fx.EQUIPMENT_ASSETS if item.code != "ASSET_RIG"),
    )
    context = ModelContext(references, fx.parameters(), fx.physical(), as_of=AS_OF)
    drilling.compute(context)

    assert _line(context, "DRILL_MAINTENANCE").unit_price_rub == Decimal("750")
    assert any("не заведено основное средство" in warning and "ТОиР" in warning for warning in context.warnings)


def test_per_shift_mode_ignores_the_tiers_and_commissioning_date() -> None:
    context = _context(_rig_type(maintenance_mode="PER_SHIFT", maintenance_age_tiers=[]), _rig_asset("2016-01-01"))
    drilling.compute(context)

    assert _line(context, "DRILL_MAINTENANCE").unit_price_rub == Decimal("750")
    assert not any("ТОиР и запчасти по ставкам" in warning for warning in context.warnings)


# --- СЗМ и прочая техника ---------------------------------------------------------


def test_szm_uses_the_same_scale() -> None:
    szm_type = next(item for item in fx.EQUIPMENT_TYPES if item.code == "SZM_12T")
    szm_type = fx.item(
        szm_type.code, szm_type.name,
        {**szm_type.payload, "maintenance_mode": "AGE_SCALE", "maintenance_age_tiers": TIERS, "spare_parts_rub_per_shift": "0"},
    )
    szm_asset = next(item for item in fx.EQUIPMENT_ASSETS if item.code == "ASSET_SZM")
    szm_asset = fx.item(szm_asset.code, szm_asset.name, {**szm_asset.payload, "commissioned_on": "2026-04-01"})
    references = fx.references(
        equipment_types=tuple(szm_type if item.code == "SZM_12T" else item for item in fx.EQUIPMENT_TYPES),
        equipment_assets=tuple(szm_asset if item.code == "ASSET_SZM" else item for item in fx.EQUIPMENT_ASSETS),
    )
    context = ModelContext(references, fx.parameters(), fx.physical(), as_of=AS_OF)
    # Смены СЗМ — драйвер логистики; здесь он задаётся напрямую, чтобы тест не
    # зависел от порядка модулей движка.
    context.set_value("szm_shifts", Decimal("10"), "тест")
    equipment.compute(context)

    plan = Decimal("20")
    maintenance = _line(context, "SZM_MAINTENANCE")
    assert maintenance.unit_price_rub == Decimal("12000000") * Decimal("2") / 100 / (plan * 12)
    assert maintenance.price_origin == "CALC"
    # Раньше запчастей у СЗМ в справочнике не было — со шкалой строка появляется.
    assert _line(context, "SZM_SPARE_PARTS").unit_price_rub == Decimal("12000000") * Decimal("4") / 100 / (plan * 12)


# --- схема ---------------------------------------------------------------------------


def _type(**payload):
    return EquipmentTypePayload.model_validate({"kind": "DRILL_RIG", **payload})


def test_schema_accepts_a_proper_scale() -> None:
    model = _type(maintenance_mode="AGE_SCALE", maintenance_age_tiers=TIERS)
    assert [tier.maintenance_pct for tier in model.maintenance_age_tiers] == [Decimal("2"), Decimal("4"), Decimal("6"), Decimal("8")]


def test_schema_requires_tiers_for_the_age_mode() -> None:
    with pytest.raises(ValidationError) as exc:
        _type(maintenance_mode="AGE_SCALE")
    assert "ступень" in str(exc.value)


def test_schema_rejects_tiers_outside_the_age_mode() -> None:
    with pytest.raises(ValidationError) as exc:
        _type(maintenance_mode="PER_SHIFT", maintenance_age_tiers=TIERS)
    assert "по возрасту" in str(exc.value)


def test_schema_requires_an_open_last_tier_and_growing_bounds() -> None:
    with pytest.raises(ValidationError) as exc:
        _type(maintenance_mode="AGE_SCALE", maintenance_age_tiers=TIERS[:2])
    assert "последней ступени" in str(exc.value)
    with pytest.raises(ValidationError) as exc:
        _type(maintenance_mode="AGE_SCALE", maintenance_age_tiers=[TIERS[1], TIERS[0], TIERS[3]])
    assert "возрастать" in str(exc.value)


def test_schema_rejects_a_decreasing_percent() -> None:
    tiers = [TIERS[0], {**TIERS[1], "spare_parts_pct": "1"}, TIERS[3]]
    with pytest.raises(ValidationError) as exc:
        _type(maintenance_mode="AGE_SCALE", maintenance_age_tiers=tiers)
    assert "запчастей" in str(exc.value)


def test_commissioning_date_round_trips_through_xlsx_as_a_date() -> None:
    from cost.v2.reference_files import section_columns

    kinds = {column.key: column.kind for column in section_columns("equipment_assets")}
    assert kinds["commissioned_on"] == "date"
    assert {column.key: column.kind for column in section_columns("equipment_types")}["maintenance_age_tiers"] == "json"
