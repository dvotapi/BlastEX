"""Опубликованная ревизия Cost V2 → структуры движка Cost V1 (спецификация §6)."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from cost.catalog import DEFAULT_CATALOG
from cost.drilling_data import DEFAULT_DRILL_RIGS, DEFAULT_WORK_OBJECTS
from cost.explosive_data import DEFAULT_EXPLOSIVES
from cost.fixed_costs import DEFAULT_FIXED_COSTS
from cost.labor import DEFAULT_LABOR_CATALOG
from cost.rock_data import DEFAULT_ROCKS
from cost.v2.legacy_adapter import LegacyReferences, legacy_references_from_snapshot
from cost.v2.models import ReferenceItem, ReferenceSnapshot
from cost.v2.references import default_reference_snapshot


def _snapshot(**sections) -> ReferenceSnapshot:
    base = {key: () for key in default_reference_snapshot().sections}
    base.update({key: tuple(items) for key, items in sections.items()})
    return ReferenceSnapshot(
        revision_id="REV-TEST",
        sections=base,
        published_at=datetime.now(timezone.utc),
        published_by="test",
    )


def _item(code: str, name: str, payload: dict | None = None, **kwargs) -> ReferenceItem:
    return ReferenceItem(code=code, name=name, payload=dict(payload or {}), **kwargs)


class TestFallbacks:
    def test_empty_snapshot_gives_defaults_and_warnings(self):
        legacy = legacy_references_from_snapshot(default_reference_snapshot())

        assert isinstance(legacy, LegacyReferences)
        assert legacy.work_objects == tuple(DEFAULT_WORK_OBJECTS)
        assert legacy.drill_rigs == tuple(DEFAULT_DRILL_RIGS)
        assert legacy.rocks == tuple(DEFAULT_ROCKS)
        assert legacy.explosives == tuple(DEFAULT_EXPLOSIVES)
        assert legacy.catalog == tuple(DEFAULT_CATALOG)
        assert legacy.fixed_costs == tuple(DEFAULT_FIXED_COSTS)
        assert legacy.labor_catalog == tuple(DEFAULT_LABOR_CATALOG)
        assert any("Карьеры и объекты" in warning for warning in legacy.warnings)
        assert any("Породы" in warning for warning in legacy.warnings)

    def test_inactive_items_are_ignored(self):
        legacy = legacy_references_from_snapshot(
            _snapshot(sites=[_item("SITE_A", "Карьер А", {"mobilization_km": 10}, is_active=False)])
        )
        assert legacy.work_objects == tuple(DEFAULT_WORK_OBJECTS)


class TestMapping:
    def test_sites_become_work_objects(self):
        legacy = legacy_references_from_snapshot(
            _snapshot(
                sites=[
                    _item("SITE_A", "Карьер А", {"mobilization_km": "220", "diesel_price_ton_rub": "52200"}),
                    _item("SITE_B", "Карьер Б", {"mobilization_km": None}),
                ]
            )
        )
        names = [obj.name for obj in legacy.work_objects]
        assert names == ["Карьер А", "Карьер Б"]
        assert legacy.work_objects[0].mobilization_km == 220.0
        assert legacy.work_objects[0].diesel_price_ton_rub == 52_200.0
        assert legacy.work_objects[1].mobilization_km == 0.0
        assert legacy.work_objects[1].diesel_price_ton_rub is None
        assert any("Карьер Б" in warning and "мобилизац" in warning.lower() for warning in legacy.warnings)

    def test_drill_rigs_come_from_assets_of_drill_rig_type(self):
        legacy = legacy_references_from_snapshot(
            _snapshot(
                equipment_types=[
                    _item("TYPE_JK", "JK 830-3", {"kind": "DRILL_RIG", "fuel_l_per_h": "50"}),
                    _item("TYPE_CAR", "Легковой", {"kind": "LIGHT_VEHICLE"}),
                ],
                equipment_assets=[
                    _item("RIG_JK", "JK 830-3", {"equipment_type_code": "TYPE_JK", "depreciation_per_shift_rub": "11854.17"}),
                    _item("RIG_CALC", "Станок без нормы", {"equipment_type_code": "TYPE_JK", "initial_cost_rub": "8400000", "useful_life_months": "84", "productive_shifts_per_month": "20", "fuel_l_per_h": "40"}),
                    _item("CAR_1", "Луидор", {"equipment_type_code": "TYPE_CAR", "initial_cost_rub": "1000", "useful_life_months": "10", "productive_shifts_per_month": "2"}),
                ],
            )
        )
        rigs = {rig.name: rig for rig in legacy.drill_rigs}
        assert set(rigs) == {"JK 830-3", "Станок без нормы"}
        assert rigs["JK 830-3"].depreciation_per_shift_rub == pytest.approx(11_854.17)
        assert rigs["JK 830-3"].fuel_l_per_h == 50.0
        assert rigs["Станок без нормы"].depreciation_per_shift_rub == pytest.approx(8_400_000 / 84 / 20)
        assert rigs["Станок без нормы"].fuel_l_per_h == 40.0
        assets = {asset.name: asset for asset in legacy.depreciation_assets}
        assert set(assets) == {"Станок без нормы", "Луидор"}
        assert assets["Луидор"].depreciation_per_shift_rub == pytest.approx(50.0)

    def test_rocks_and_explosives(self):
        legacy = legacy_references_from_snapshot(
            _snapshot(
                rocks=[_item("ROCK_GABBRO", "Габбро-диабаз", {"density_t_m3": "2.9", "ucs_mpa": "168", "fissuring_ff": "2.2"})],
                materials=[
                    _item("EXP_GRANULIT", "Гранулит-РП", {"category": "EXPLOSIVE", "density_t_m3": "0.85", "power_mj_kg": "3.76", "chart_label": "ГРАНУЛИТ-РП", "legacy_ref": "ПВВ Гранулит-РП"}),
                    _item("EXP_NEW", "Новое ВВ", {"material_kind": "ВВ", "density_t_m3": "1.1", "power_mj_kg": "3"}),
                ],
            )
        )
        assert legacy.rocks[0].name == "Габбро-диабаз"
        assert legacy.rocks[0].ucs_mpa == 168.0
        assert legacy.rocks[0].fissuring_ff == 2.2
        keys = [item.key for item in legacy.explosives]
        assert keys == ["ПВВ Гранулит-РП", "EXP_NEW"]
        assert legacy.explosives[0].chart_label == "ГРАНУЛИТ-РП"
        assert legacy.explosives[1].chart_label == "НОВОЕ ВВ"

    def test_catalog_uses_prices_and_unit_symbols(self):
        legacy = legacy_references_from_snapshot(
            _snapshot(
                units=[_item("KG", "Килограмм", {"symbol": "кг"}), _item("PIECE", "Штука", {"symbol": "шт"})],
                materials=[
                    _item("MAT_VV", "ЭВВ Эверсин-100", {"category": "explosive", "unit": "KG", "legacy_ref": "vv_eversin"}),
                    _item("MAT_NSI", "НСИ 6 м", {"category": "downhole_nsi", "unit": "PIECE", "length_m": "6"}),
                    _item("MAT_BIT", "Коронка", {"category": "TOOL", "unit": "PIECE"}),
                ],
                material_prices=[
                    _item("PRICE_MAT_VV", "Стоимость", {"material_code": "MAT_VV", "price_rub": "48.9"}),
                ],
            )
        )
        items = {item.id: item for item in legacy.catalog}
        assert set(items) == {"vv_eversin", "MAT_NSI"}
        assert items["vv_eversin"].unit == "кг"
        assert items["vv_eversin"].price == 48.9
        assert items["MAT_NSI"].price == 0.0
        assert items["MAT_NSI"].length_m == 6.0
        assert any("НСИ 6 м" in warning and "цена" in warning.lower() for warning in legacy.warnings)

    def test_fixed_costs_and_positions(self):
        legacy = legacy_references_from_snapshot(
            _snapshot(
                cost_items=[
                    _item("V1_FIXED_STORAGE", "Хранение", {"legacy_section": "2.1", "amount_rub": "45000", "legacy_ref": "fc_21_storage"}, comment="склад"),
                    _item("V1_FIXED_OFF", "Выключено", {"legacy_section": "2.2", "amount_rub": "1"}, is_active=False),
                    _item("variable", "variable", {"kind": "behavior_type"}),
                ],
                positions=[
                    _item("POSITION_MASTER", "Мастер", {"legacy_ref": "labor_master"}),
                    _item("POS_DRILLER", "Машинист", {}),
                ],
                labor_rates=[
                    _item("RATE_MASTER", "Ставка", {"position_code": "POSITION_MASTER", "fixed_monthly_rub": "80000", "piece_rate_rub": "0.25"}),
                ],
            )
        )
        fixed = {item.id: item for item in legacy.fixed_costs}
        assert set(fixed) == {"fc_21_storage", "V1_FIXED_OFF"}
        assert fixed["fc_21_storage"].section == "2.1"
        assert fixed["fc_21_storage"].amount_rub == 45_000.0
        assert fixed["fc_21_storage"].note == "склад"
        assert fixed["V1_FIXED_OFF"].enabled is False
        positions = {item.id: item for item in legacy.labor_catalog}
        assert set(positions) == {"labor_master", "POS_DRILLER"}
        assert positions["labor_master"].fixed_salary_monthly == 80_000.0
        assert positions["labor_master"].piece_rate_per_m3 == 0.25
        assert positions["POS_DRILLER"].fixed_salary_monthly == 0.0
        assert any("Машинист" in warning and "ставк" in warning.lower() for warning in legacy.warnings)
