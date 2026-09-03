# Единые справочники, PR 1: адаптеры Cost V1, рабочее пространство в БД, отказ от файлов

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Движок Cost V1 и все вкладки BlastEX читают справочники только из опубликованной ревизии схемы `blastex` в PostgreSQL `project1`; файл `data/teams/<team>/references.json`, настройки и сценарии сметы на файлах уходят, страница «Справочники расчёта» удаляется.

**Architecture:** Новый модуль `cost/v2/legacy_adapter.py` превращает `ReferenceSnapshot` в dataclass'ы Cost V1 (объекты, станки, породы, ВМ, амортизация, номенклатура, постоянные расходы, должности); пустой раздел даёт значения по умолчанию и предупреждение. Роутеры `workspace`, `references`, `cost`, `blast`, `design` получают эти структуры через FastAPI-зависимость `current_legacy_references`, а настройки рабочего пространства и сценарии сметы хранятся в таблицах `legacy_workspace_settings` и `legacy_cost_scenarios` через репозиторий. Скрипт переноса объединяет разделы V1 с существующими, а не заменяет их.

**Tech Stack:** Python 3.12, FastAPI, Pydantic 2, SQLAlchemy 2 + Alembic, PostgreSQL 16; React 19 + TypeScript + Vite + vitest; pytest.

**Spec:** `Docs/specs/2026-09-03-unified-references-design.md`, разделы §6, §7, §9, §11, §12 (пункт 1).

## Global Constraints

- Поля payload описываются только схемами `cost/v2/schemas/`: единица — `x-unit`, ссылка — `x-ref`, подпись — `title`, пояснение — `description` (CLAUDE.md).
- Расчётные модули не знают об интерфейсе; всё, что нужно фронту, идёт через `api/` (CLAUDE.md).
- Отсутствующая запись справочника даёт предупреждение и значение по умолчанию, а не исключение (спецификация §6).
- Публикация ревизии остаётся единственной точкой записи справочников (спецификация §3).
- `data/teams` после PR читают только скрипт импорта и `design/persistence.py` вместе с модулями `design/*` и `intelligence/*`, которые импортируют `team_dir` (спецификация §7).
- Каждый метод `PostgresEconomicsRepository` без подчёркивания принимает `organization_id` первым аргументом (тест `test_every_repository_method_takes_organization_first`).
- Пользовательский текст, комментарии, коммиты — на русском языке; технические термины и коды — как есть.
- Ветка `feat/unified-references`; коммиты завершаются строкой `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`.
- Python-тесты: `.venv/bin/python -m pytest -q`; фронт: `cd frontend && npm test && npx tsc -b`.

---

## Структура файлов

| Файл | Ответственность |
|---|---|
| `cost/v2/schemas/misc.py` (изменить) | `RockPayload`: поля `ucs_mpa`, `fissuring_ff` |
| `cost/v2/schemas/materials.py` (изменить) | `MaterialPayload`: поля `density_t_m3`, `chart_label` |
| `cost/v2/legacy_adapter.py` (создать) | `LegacyReferences` и `legacy_references_from_snapshot` |
| `cost/v2/repository.py` (изменить) | `LegacyWorkspaceSettings`, методы чтения настроек и сценариев в протоколе и in-memory |
| `cost/v2/db_repository.py` (изменить) | те же методы для PostgreSQL |
| `api/services/legacy_references.py` (создать) | зависимость `current_legacy_references` |
| `api/services/converters.py`, `cost_service.py`, `blast_service.py`, `design_service.py` (изменить) | принимают `LegacyReferences` вместо чтения файлов |
| `api/routers/blast.py`, `cost.py`, `design.py`, `references.py`, `workspace.py` (изменить) | зависимости вместо файлов; `references` только чтение |
| `api/schemas/workspace.py` (изменить) | `SaveWorkspaceRequest` без `references` |
| `cost/persistence.py` (изменить) | остаются пути `data/teams`, `WorkspaceSnapshot`, `build_default_snapshot` |
| `cost/references_store.py` (удалить) | хранилище session_state Streamlit |
| `cost/engine.py` (изменить) | остаётся только `calculate_with_context` |
| `cost/v2/import_v1.py`, `scripts/import_cost_v1_to_project1.py` (изменить) | объединение разделов, породы, `--sections` |
| `frontend/src/types.ts`, `api/endpoints.ts`, `app/useWorkspace.tsx`, `app/costContext.ts`, `app/AppShell.tsx`, `pages/LaborPage.tsx` (изменить) | без записи справочников V1 |
| `frontend/src/pages/ReferencesPage.tsx`, `pages/references/{Rocks,Explosives,Depreciation,Operations,Catalog,FixedCosts}Section.tsx` (удалить) | страница «Справочники расчёта» |
| `tests/test_legacy_adapter.py`, `tests/test_legacy_adapter_roundtrip.py`, `tests/test_api_workspace.py` (создать); `tests/test_api_team_scope.py`, `test_api_geometry.py`, `test_api_cost_calculators.py`, `test_cost_v2_import.py`, `test_repository_organization_isolation.py` (изменить) | тесты |
| `README.md`, `CLAUDE.md` (изменить) | документация |

---

### Task 1: Поля схем для адаптера

**Files:**
- Modify: `cost/v2/schemas/misc.py:76-80`
- Modify: `cost/v2/schemas/materials.py:14-30`
- Test: `tests/test_reference_schemas.py`

**Interfaces:**
- Produces: `RockPayload.ucs_mpa: Decimal | None`, `RockPayload.fissuring_ff: Decimal | None`, `MaterialPayload.density_t_m3: Decimal | None`, `MaterialPayload.chart_label: str | None`.

- [ ] **Step 1: Написать падающий тест**

Добавить в конец `tests/test_reference_schemas.py`:

```python
class TestLegacyEngineFields:
    """Поля, которые движок Cost V1 читает через адаптер (спецификация §4.2, §6)."""

    def test_rock_keeps_strength_and_fissuring(self):
        from cost.v2.schemas.misc import RockPayload

        payload = RockPayload(density_t_m3=Decimal("2.9"), ucs_mpa=Decimal("168"), fissuring_ff=Decimal("2.2"))
        assert payload.ucs_mpa == Decimal("168")
        assert payload.fissuring_ff == Decimal("2.2")
        schema = section_json_schema("rocks")
        assert schema["properties"]["ucs_mpa"]["x-unit"] == "МПа"
        assert schema["properties"]["fissuring_ff"]["x-unit"] == "трещин/м"

    def test_material_keeps_explosive_density_and_chart_label(self):
        from cost.v2.schemas.materials import MaterialPayload

        payload = MaterialPayload(density_t_m3=Decimal("0.85"), chart_label="ГРАНУЛИТ-РП")
        assert payload.density_t_m3 == Decimal("0.85")
        assert payload.chart_label == "ГРАНУЛИТ-РП"
        schema = section_json_schema("materials")
        assert schema["properties"]["density_t_m3"]["x-unit"] == "т/м³"
```

- [ ] **Step 2: Убедиться, что тест падает**

Run: `.venv/bin/python -m pytest tests/test_reference_schemas.py -k LegacyEngineFields -q`
Expected: FAIL, `ValidationError ... Extra inputs are not permitted` (схема запрещает лишние поля).

- [ ] **Step 3: Добавить поля**

В `cost/v2/schemas/misc.py` класс `RockPayload` заменить на:

```python
class RockPayload(ReferencePayload):
    density_t_m3: Decimal | None = UnitField("т/м³", description="Плотность", default=None)
    hardness_f: Decimal | None = UnitField("f", description="Крепость по Протодьяконову", default=None)
    fracture_class: str | None = Field(default=None, description="Класс трещиноватости")
    ucs_mpa: Decimal | None = UnitField(
        "МПа", title="Прочность на сжатие", description="Предел прочности на одноосное сжатие", default=None, ge=0
    )
    fissuring_ff: Decimal | None = UnitField(
        "трещин/м", title="Трещиноватость", description="Число трещин на метр массива", default=None, ge=0
    )
```

В `cost/v2/schemas/materials.py` в `MaterialPayload` после `power_mj_kg` добавить:

```python
    density_t_m3: Decimal | None = UnitField(
        "т/м³", title="Плотность ВВ", description="Плотность заряда для технологического расчёта", default=None, ge=0
    )
    chart_label: str | None = Field(
        default=None, title="Подпись на схеме", description="Короткая подпись ВВ на схеме заряда"
    )
```

- [ ] **Step 4: Прогнать тесты схем**

Run: `.venv/bin/python -m pytest tests/test_reference_schemas.py tests/test_api_reference_schema.py -q`
Expected: PASS (включая проверку «у каждого числового поля есть единица»).

- [ ] **Step 5: Коммит**

```bash
git add cost/v2/schemas/misc.py cost/v2/schemas/materials.py tests/test_reference_schemas.py
git commit -m "feat(schemas): поля пород и ВМ для движка Cost V1

Прочность, трещиноватость породы, плотность и подпись ВМ нужны адаптеру
Cost V1; без них справочник V2 не заменяет references.json.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 2: Адаптер ревизии V2 в структуры Cost V1

**Files:**
- Create: `cost/v2/legacy_adapter.py`
- Test: `tests/test_legacy_adapter.py`

**Interfaces:**
- Consumes: `cost.v2.models.ReferenceSnapshot`, `ReferenceItem`; dataclass'ы V1 из `cost.drilling_data`, `cost.rock_data`, `cost.explosive_data`, `cost.depreciation_data`, `cost.catalog`, `cost.fixed_costs`, `cost.labor`, `Blast.RockProperties`.
- Produces:
  - `LegacyReferences` (frozen dataclass) с полями `work_objects`, `drill_rigs`, `rocks`, `explosives`, `depreciation_assets`, `catalog`, `fixed_costs`, `labor_catalog` (все `tuple[...]`) и `warnings: tuple[str, ...]`;
  - `legacy_references_from_snapshot(snapshot: ReferenceSnapshot) -> LegacyReferences`;
  - `default_legacy_references() -> LegacyReferences` (только значения по умолчанию, без предупреждений).

- [ ] **Step 1: Написать падающие тесты**

Создать `tests/test_legacy_adapter.py`:

```python
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
```

- [ ] **Step 2: Убедиться, что тесты падают**

Run: `.venv/bin/python -m pytest tests/test_legacy_adapter.py -q`
Expected: FAIL, `ModuleNotFoundError: No module named 'cost.v2.legacy_adapter'`.

- [ ] **Step 3: Написать адаптер**

Создать `cost/v2/legacy_adapter.py`:

```python
"""Опубликованная ревизия справочников Cost V2 → структуры движка Cost V1.

Движок V1 (`cost/strategies`, `cost/drilling.py`, `cost/geometry.py`) читает
свои dataclass'ы; их единственный источник теперь — разделы схемы `blastex`.
Пустой раздел даёт значения по умолчанию и предупреждение, а не исключение.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, Callable, Iterable, TypeVar

from Blast import RockProperties
from cost.catalog import DEFAULT_CATALOG, CatalogItem
from cost.depreciation_data import (
    DEFAULT_DEPRECIATION_ASSETS,
    FixedAssetDepreciation,
    calculate_depreciation_per_shift_rub,
)
from cost.drilling_data import DEFAULT_DRILL_RIGS, DEFAULT_WORK_OBJECTS, DrillRig, WorkObject
from cost.explosive_data import DEFAULT_EXPLOSIVES, ExplosiveCatalogItem
from cost.fixed_costs import DEFAULT_FIXED_COSTS, SECTION_TITLES, FixedCostItem
from cost.labor import DEFAULT_LABOR_CATALOG, JobPosition
from cost.rock_data import DEFAULT_ROCKS
from cost.v2.models import ReferenceItem, ReferenceSnapshot
from cost.v2.references import REFERENCE_SECTION_DEFINITIONS

# Категории номенклатуры Cost V1; «nsi» — старое имя «downhole_nsi».
_CATALOG_CATEGORIES: dict[str, str] = {
    "explosive": "explosive",
    "detonator": "detonator",
    "downhole_nsi": "downhole_nsi",
    "nsi": "downhole_nsi",
    "surface_nsi": "surface_nsi",
    "start_nsi": "start_nsi",
}
# Так импорт V1 помечал взрывчатые вещества; «ВВ» — вид материала по схеме.
_EXPLOSIVE_CATEGORY = "EXPLOSIVE"
_EXPLOSIVE_KIND = "ВВ"

T = TypeVar("T")


@dataclass(frozen=True)
class LegacyReferences:
    work_objects: tuple[WorkObject, ...]
    drill_rigs: tuple[DrillRig, ...]
    rocks: tuple[RockProperties, ...]
    explosives: tuple[ExplosiveCatalogItem, ...]
    depreciation_assets: tuple[FixedAssetDepreciation, ...]
    catalog: tuple[CatalogItem, ...]
    fixed_costs: tuple[FixedCostItem, ...]
    labor_catalog: tuple[JobPosition, ...]
    warnings: tuple[str, ...] = ()


def default_legacy_references() -> LegacyReferences:
    """Значения по умолчанию Cost V1 — для тестов и пустой организации."""

    return LegacyReferences(
        work_objects=tuple(DEFAULT_WORK_OBJECTS),
        drill_rigs=tuple(DEFAULT_DRILL_RIGS),
        rocks=tuple(DEFAULT_ROCKS),
        explosives=tuple(DEFAULT_EXPLOSIVES),
        depreciation_assets=tuple(DEFAULT_DEPRECIATION_ASSETS),
        catalog=tuple(DEFAULT_CATALOG),
        fixed_costs=tuple(DEFAULT_FIXED_COSTS),
        labor_catalog=tuple(DEFAULT_LABOR_CATALOG),
    )


def legacy_references_from_snapshot(snapshot: ReferenceSnapshot) -> LegacyReferences:
    warnings: list[str] = []
    sites = snapshot.active_items("sites")
    types = {item.code: item for item in snapshot.active_items("equipment_types")}
    assets = snapshot.active_items("equipment_assets")
    materials = snapshot.active_items("materials")
    prices = snapshot.active_items("material_prices")
    units = {item.code: str(item.payload.get("symbol") or item.name) for item in snapshot.active_items("units")}
    rates = {
        str(item.payload.get("position_code")): item
        for item in snapshot.active_items("labor_rates")
    }

    work_objects = _fallback("sites", [_work_object(item, warnings) for item in sites], DEFAULT_WORK_OBJECTS, warnings)
    drill_rigs = _fallback(
        "equipment_assets",
        [_drill_rig(item, types) for item in assets if _kind(item, types) == "DRILL_RIG"],
        DEFAULT_DRILL_RIGS,
        warnings,
    )
    depreciation = _fallback(
        "equipment_assets",
        [_depreciation(item) for item in assets if _has_depreciation_inputs(item)],
        DEFAULT_DEPRECIATION_ASSETS,
        warnings,
    )
    rocks = _fallback("rocks", [_rock(item, warnings) for item in snapshot.active_items("rocks")], DEFAULT_ROCKS, warnings)
    explosives = _fallback(
        "materials",
        [_explosive(item, warnings) for item in materials if _is_explosive(item)],
        DEFAULT_EXPLOSIVES,
        warnings,
    )
    catalog = _fallback(
        "materials",
        [_catalog_item(item, prices, units, warnings) for item in materials if _catalog_category(item)],
        DEFAULT_CATALOG,
        warnings,
    )
    fixed_costs = _fallback(
        "cost_items",
        [_fixed_cost(item) for item in snapshot.sections.get("cost_items", ()) if _is_legacy_fixed_cost(item)],
        DEFAULT_FIXED_COSTS,
        warnings,
    )
    labor = _fallback(
        "positions",
        [_position(item, rates, warnings) for item in snapshot.active_items("positions")],
        DEFAULT_LABOR_CATALOG,
        warnings,
    )
    return LegacyReferences(
        work_objects=work_objects,
        drill_rigs=drill_rigs,
        rocks=rocks,
        explosives=explosives,
        depreciation_assets=depreciation,
        catalog=catalog,
        fixed_costs=fixed_costs,
        labor_catalog=labor,
        warnings=tuple(warnings),
    )


# --- Преобразования по разделам --------------------------------------------


def _work_object(item: ReferenceItem, warnings: list[str]) -> WorkObject:
    km = _optional_number(item.payload.get("mobilization_km"))
    if km is None:
        warnings.append(f"Объект «{item.name}»: плечо мобилизации не задано, принято 0 км.")
        km = 0.0
    return WorkObject(
        name=item.name,
        mobilization_km=km,
        diesel_price_ton_rub=_optional_number(item.payload.get("diesel_price_ton_rub")),
    )


def _kind(asset: ReferenceItem, types: dict[str, ReferenceItem]) -> str:
    type_item = types.get(str(asset.payload.get("equipment_type_code") or ""))
    return str(type_item.payload.get("kind") or "") if type_item else ""


def _drill_rig(asset: ReferenceItem, types: dict[str, ReferenceItem]) -> DrillRig:
    type_item = types.get(str(asset.payload.get("equipment_type_code") or ""))
    fuel = _optional_number(asset.payload.get("fuel_l_per_h"))
    if fuel is None and type_item is not None:
        fuel = _optional_number(type_item.payload.get("fuel_l_per_h"))
    return DrillRig(
        name=asset.name,
        depreciation_per_shift_rub=_depreciation_per_shift(asset),
        fuel_l_per_h=fuel or 0.0,
    )


def _depreciation_per_shift(asset: ReferenceItem) -> float:
    explicit = _optional_number(asset.payload.get("depreciation_per_shift_rub"))
    if explicit is not None:
        return explicit
    return calculate_depreciation_per_shift_rub(
        _number(asset.payload.get("initial_cost_rub")),
        _number(asset.payload.get("useful_life_months")),
        _number(asset.payload.get("productive_shifts_per_month")),
    )


def _has_depreciation_inputs(asset: ReferenceItem) -> bool:
    return (
        _number(asset.payload.get("useful_life_months")) > 0
        and _number(asset.payload.get("productive_shifts_per_month")) > 0
    )


def _depreciation(asset: ReferenceItem) -> FixedAssetDepreciation:
    initial = _number(asset.payload.get("initial_cost_rub"))
    life = _number(asset.payload.get("useful_life_months"))
    shifts = _number(asset.payload.get("productive_shifts_per_month"))
    return FixedAssetDepreciation(
        name=asset.name,
        initial_cost_rub=initial,
        useful_life_months=life,
        productive_shifts_per_month=shifts,
        depreciation_per_shift_rub=calculate_depreciation_per_shift_rub(initial, life, shifts),
    )


def _rock(item: ReferenceItem, warnings: list[str]) -> RockProperties:
    ucs = _optional_number(item.payload.get("ucs_mpa"))
    fissuring = _optional_number(item.payload.get("fissuring_ff"))
    if ucs is None or fissuring is None:
        warnings.append(f"Порода «{item.name}»: не заданы прочность или трещиноватость, приняты нули.")
    return RockProperties(
        name=item.name,
        density_t_m3=_number(item.payload.get("density_t_m3")),
        ucs_mpa=ucs or 0.0,
        fissuring_ff=fissuring or 0.0,
    )


def _is_explosive(item: ReferenceItem) -> bool:
    return (
        str(item.payload.get("category") or "") == _EXPLOSIVE_CATEGORY
        or str(item.payload.get("material_kind") or "") == _EXPLOSIVE_KIND
    )


def _explosive(item: ReferenceItem, warnings: list[str]) -> ExplosiveCatalogItem:
    density = _optional_number(item.payload.get("density_t_m3"))
    power = _optional_number(item.payload.get("power_mj_kg"))
    if density is None or power is None:
        warnings.append(f"ВВ «{item.name}»: не заданы плотность или энергия, приняты нули.")
    return ExplosiveCatalogItem(
        key=_legacy_id(item),
        name=item.name,
        density_t_m3=density or 0.0,
        power_mj_kg=power or 0.0,
        chart_label=str(item.payload.get("chart_label") or item.name.upper()),
    )


def _catalog_category(item: ReferenceItem) -> str | None:
    return _CATALOG_CATEGORIES.get(str(item.payload.get("category") or ""))


def _catalog_item(
    item: ReferenceItem,
    prices: Iterable[ReferenceItem],
    units: dict[str, str],
    warnings: list[str],
) -> CatalogItem:
    price = next(
        (p for p in prices if str(p.payload.get("material_code") or "") == item.code),
        None,
    )
    if price is None:
        warnings.append(f"Материал «{item.name}»: в разделе «Стоимость материалов» нет цены, принят 0.")
    unit_code = str(item.payload.get("unit") or "")
    return CatalogItem(
        id=_legacy_id(item),
        name=item.name,
        category=_catalog_category(item),  # type: ignore[arg-type]
        unit=units.get(unit_code, unit_code),
        price=_number(price.payload.get("price_rub")) if price else 0.0,
        mass_kg=_optional_number(item.payload.get("mass_kg")),
        length_m=_optional_number(item.payload.get("length_m")),
        note=item.comment,
    )


def _is_legacy_fixed_cost(item: ReferenceItem) -> bool:
    return str(item.payload.get("legacy_section") or "") in SECTION_TITLES


def _fixed_cost(item: ReferenceItem) -> FixedCostItem:
    return FixedCostItem(
        id=_legacy_id(item),
        section=str(item.payload.get("legacy_section")),
        name=item.name,
        amount_rub=_number(item.payload.get("amount_rub")),
        note=item.comment,
        enabled=item.is_active,
    )


def _position(item: ReferenceItem, rates: dict[str, ReferenceItem], warnings: list[str]) -> JobPosition:
    rate = rates.get(item.code)
    if rate is None:
        warnings.append(f"Должность «{item.name}»: в разделе «Ставки персонала» нет ставки, принят 0.")
    return JobPosition(
        id=_legacy_id(item),
        name=item.name,
        fixed_salary_monthly=_number(rate.payload.get("fixed_monthly_rub")) if rate else 0.0,
        piece_rate_per_m3=_number(rate.payload.get("piece_rate_rub")) if rate else 0.0,
    )


# --- Вспомогательные --------------------------------------------------------


def _legacy_id(item: ReferenceItem) -> str:
    return str(item.payload.get("legacy_ref") or item.code)


def _fallback(section: str, items: list[T], defaults: Iterable[T], warnings: list[str]) -> tuple[T, ...]:
    if items:
        return tuple(items)
    label = REFERENCE_SECTION_DEFINITIONS.get(section, {}).get("label", section)
    warnings.append(f"Раздел «{label}» пуст: используются значения Cost V1 по умолчанию.")
    return tuple(defaults)


def _optional_number(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(Decimal(str(value)))
    except (InvalidOperation, ValueError):
        return None


def _number(value: Any) -> float:
    parsed = _optional_number(value)
    return parsed if parsed is not None else 0.0
```

- [ ] **Step 4: Прогнать тесты адаптера**

Run: `.venv/bin/python -m pytest tests/test_legacy_adapter.py -q`
Expected: PASS. Если `test_empty_snapshot_gives_defaults_and_warnings` падает на `rocks`: проверить, что раздел `rocks` есть в `REFERENCE_SECTION_DEFINITIONS` с меткой «Породы» (`cost/v2/references.py:76`).

- [ ] **Step 5: Коммит**

```bash
git add cost/v2/legacy_adapter.py tests/test_legacy_adapter.py
git commit -m "feat(cost): адаптер ревизии справочников V2 в структуры Cost V1

Объекты, станки, породы, ВМ, амортизация, номенклатура, постоянные расходы
и должности собираются из опубликованной ревизии; пустой раздел даёт
значения по умолчанию и предупреждение.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 3: Настройки рабочего пространства и сценарии сметы в репозитории

**Files:**
- Modify: `cost/v2/repository.py` (протокол `EconomicsRepository`, класс `InMemoryEconomicsRepository`)
- Modify: `cost/v2/db_repository.py` (рядом с `import_legacy_workspace`, строка 778)
- Test: `tests/test_repository_organization_isolation.py`, `tests/test_cost_v2_repository.py`

**Interfaces:**
- Produces в `cost/v2/repository.py`:

```python
@dataclass(frozen=True)
class LegacyWorkspaceSettings:
    team_name: str
    active_scenario_id: str
    active_work_object_name: str
    reference_revision_id: str | None = None
```

  и методы репозитория (протокол, in-memory, PostgreSQL):
  - `get_legacy_workspace(self, organization_id: str) -> LegacyWorkspaceSettings | None`
  - `import_legacy_workspace(self, organization_id, user_id, *, team_name, active_scenario_id, active_work_object_name, reference_revision_id=None) -> None` (уже есть в PostgreSQL)
  - `get_legacy_scenario(self, organization_id: str, scenario_key: str) -> dict[str, Any] | None`
  - `import_legacy_scenarios(self, organization_id, user_id, scenarios: Mapping[str, dict[str, Any]], *, reference_revision_id=None) -> list[str]` (уже есть в PostgreSQL)

- [ ] **Step 1: Написать падающие тесты**

В `tests/test_repository_organization_isolation.py` добавить после `test_event_runs_require_own_passport`:

```python
def test_legacy_workspace_and_scenarios_are_organization_scoped(repository) -> None:
    repository.import_legacy_workspace(
        ORG_A,
        "a@example.ru",
        team_name="Команда А",
        active_scenario_id="drilling",
        active_work_object_name="Карьер А",
    )
    repository.import_legacy_scenarios(
        ORG_A,
        "a@example.ru",
        {"drilling": {"labor_shifts_per_month": 7, "labor_assignment_records": [{"id": "la_1"}]}},
    )

    settings = repository.get_legacy_workspace(ORG_A)
    assert settings is not None
    assert settings.team_name == "Команда А"
    assert settings.active_scenario_id == "drilling"
    assert settings.active_work_object_name == "Карьер А"
    assert repository.get_legacy_workspace(ORG_B) is None

    scenario = repository.get_legacy_scenario(ORG_A, "drilling")
    assert scenario is not None
    assert scenario["labor_shifts_per_month"] == 7
    assert scenario["labor_assignment_records"] == [{"id": "la_1"}]
    assert repository.get_legacy_scenario(ORG_A, "blasting") is None
    assert repository.get_legacy_scenario(ORG_B, "drilling") is None


def test_legacy_workspace_is_overwritten_not_duplicated(repository) -> None:
    for name in ("Первое", "Второе"):
        repository.import_legacy_workspace(
            ORG_A, "a@example.ru", team_name=name, active_scenario_id="drill_blast", active_work_object_name="X"
        )
    assert repository.get_legacy_workspace(ORG_A).team_name == "Второе"
    repository.import_legacy_scenarios(ORG_A, "a", {"drill_blast": {"labor_shifts_per_month": 1}})
    repository.import_legacy_scenarios(ORG_A, "a", {"drill_blast": {"labor_shifts_per_month": 2}})
    assert repository.get_legacy_scenario(ORG_A, "drill_blast")["labor_shifts_per_month"] == 2
```

- [ ] **Step 2: Убедиться, что тесты падают**

Run: `.venv/bin/python -m pytest tests/test_repository_organization_isolation.py -q`
Expected: FAIL, `AttributeError: 'InMemoryEconomicsRepository' object has no attribute 'import_legacy_workspace'`.

- [ ] **Step 3: Протокол и in-memory реализация**

В `cost/v2/repository.py` после класса `StoredEconomicsRun` добавить:

```python
@dataclass(frozen=True)
class LegacyWorkspaceSettings:
    """Настройки рабочего пространства Cost V1: команда, сценарий, объект."""

    team_name: str
    active_scenario_id: str
    active_work_object_name: str
    reference_revision_id: str | None = None
```

В протокол `EconomicsRepository` после `get_economics_run` добавить:

```python
    def get_legacy_workspace(self, organization_id: str) -> LegacyWorkspaceSettings | None: ...

    def import_legacy_workspace(
        self,
        organization_id: str,
        user_id: str,
        *,
        team_name: str,
        active_scenario_id: str,
        active_work_object_name: str,
        reference_revision_id: str | None = None,
    ) -> None: ...

    def get_legacy_scenario(self, organization_id: str, scenario_key: str) -> dict[str, Any] | None: ...

    def import_legacy_scenarios(
        self,
        organization_id: str,
        user_id: str,
        scenarios: Mapping[str, dict[str, Any]],
        *,
        reference_revision_id: str | None = None,
    ) -> list[str]: ...
```

Убедиться, что `Mapping` импортирован из `typing` (добавить в существующий импорт, если нет).

В `InMemoryEconomicsRepository.__init__` добавить:

```python
        self._legacy_workspace: dict[str, LegacyWorkspaceSettings] = {}
        self._legacy_scenarios: dict[tuple[str, str], dict[str, Any]] = {}
```

В конец класса `InMemoryEconomicsRepository` добавить:

```python
    def get_legacy_workspace(self, organization_id: str) -> LegacyWorkspaceSettings | None:
        with self._lock:
            return self._legacy_workspace.get(organization_id)

    def import_legacy_workspace(
        self,
        organization_id: str,
        user_id: str,
        *,
        team_name: str,
        active_scenario_id: str,
        active_work_object_name: str,
        reference_revision_id: str | None = None,
    ) -> None:
        with self._lock:
            self._legacy_workspace[organization_id] = LegacyWorkspaceSettings(
                team_name=team_name,
                active_scenario_id=active_scenario_id,
                active_work_object_name=active_work_object_name,
                reference_revision_id=reference_revision_id,
            )

    def get_legacy_scenario(self, organization_id: str, scenario_key: str) -> dict[str, Any] | None:
        with self._lock:
            stored = self._legacy_scenarios.get((organization_id, scenario_key))
            return deepcopy(stored) if stored is not None else None

    def import_legacy_scenarios(
        self,
        organization_id: str,
        user_id: str,
        scenarios: Mapping[str, dict[str, Any]],
        *,
        reference_revision_id: str | None = None,
    ) -> list[str]:
        with self._lock:
            imported: list[str] = []
            for scenario_key, payload in scenarios.items():
                self._legacy_scenarios[(organization_id, scenario_key)] = {
                    **deepcopy(dict(payload)),
                    "reference_revision_id": reference_revision_id,
                }
                imported.append(scenario_key)
            return imported
```

- [ ] **Step 4: PostgreSQL-реализация чтения**

В `cost/v2/db_repository.py` импортировать `LegacyWorkspaceSettings` из `cost.v2.repository` (дописать в существующий импорт из этого модуля) и перед `import_legacy_workspace` добавить:

```python
    def get_legacy_workspace(self, organization_id: str) -> LegacyWorkspaceSettings | None:
        with self.session_factory() as session:
            row = session.get(LegacyWorkspaceSettingsRow, organization_id)
            if row is None:
                return None
            return LegacyWorkspaceSettings(
                team_name=row.team_name,
                active_scenario_id=row.active_scenario_id,
                active_work_object_name=row.active_work_object_name,
                reference_revision_id=row.reference_revision_id,
            )

    def get_legacy_scenario(self, organization_id: str, scenario_key: str) -> dict[str, Any] | None:
        with self.session_factory() as session:
            row = session.scalar(
                select(LegacyCostScenarioRow).where(
                    LegacyCostScenarioRow.organization_id == organization_id,
                    LegacyCostScenarioRow.scenario_key == scenario_key,
                )
            )
            if row is None:
                return None
            # Отдельные колонки — источник правды для того, что фронт правит;
            # payload хранит остальное (смены в месяц и т.п.).
            return {
                **dict(row.payload or {}),
                "labor_assignment_records": list(row.labor_assignment_records or []),
                "drilling_calculator_input": dict(row.drilling_calculator_input or {}),
                "scenario_phase_overrides": dict(row.scenario_phase_overrides or {}),
                "reference_revision_id": row.reference_revision_id,
            }
```

- [ ] **Step 5: Прогнать тесты репозитория**

Run: `.venv/bin/python -m pytest tests/test_repository_organization_isolation.py tests/test_cost_v2_repository.py -q`
Expected: PASS, включая `test_every_repository_method_takes_organization_first` (новые методы принимают `organization_id` первым).

- [ ] **Step 6: Коммит**

```bash
git add cost/v2/repository.py cost/v2/db_repository.py tests/test_repository_organization_isolation.py
git commit -m "feat(repository): чтение настроек рабочего пространства и сценариев сметы

Таблицы legacy_workspace_settings и legacy_cost_scenarios получают методы
чтения в протоколе, in-memory и PostgreSQL; запись уже была.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 4: Зависимость `current_legacy_references` и сервисы расчёта без файлов

**Files:**
- Create: `api/services/legacy_references.py`
- Modify: `api/services/converters.py:108-175`, `api/services/cost_service.py`, `api/services/blast_service.py:59-77`, `api/services/design_service.py:991-1016`
- Modify: `api/routers/cost.py`, `api/routers/blast.py`, `api/routers/design.py:252-254`
- Test: `tests/test_api_cost_calculators.py`, `tests/test_api_geometry.py`, `tests/test_design_cost.py` (проверить вызовы `estimate_design_cost`)

**Interfaces:**
- Produces `api/services/legacy_references.py`:
  - `load_legacy_references(repository: EconomicsRepository, organization_id: str) -> LegacyReferences`
  - `current_legacy_references(organization_id=Depends(current_team_id), repository=Depends(get_economics_repository)) -> LegacyReferences`
- Меняет сигнатуры:
  - `converters.build_calculation_context(request, legacy: LegacyReferences) -> CalculationContext`
  - `cost_service.calculate_cost(request, legacy: LegacyReferences)`
  - `cost_service.calculate_drilling_unit(request, legacy: LegacyReferences)`
  - `cost_service.resolve_materials_auto(request, legacy: LegacyReferences)`
  - `blast_service.resolve_explosive_item(legacy: LegacyReferences, explosive_key: str)`
  - `blast_service.compute_geometry(payload, legacy: LegacyReferences)`
  - `design_service.estimate_design_cost(request, legacy: LegacyReferences)`

- [ ] **Step 1: Зависимость**

Создать `api/services/legacy_references.py`:

```python
"""Справочники Cost V1 для роутеров: одна зависимость вместо чтения файлов."""
from __future__ import annotations

from fastapi import Depends

from api.security import current_team_id
from api.services.economics_service import get_economics_repository
from cost.v2.legacy_adapter import LegacyReferences, legacy_references_from_snapshot
from cost.v2.repository import EconomicsRepository


def load_legacy_references(repository: EconomicsRepository, organization_id: str) -> LegacyReferences:
    """Опубликованная ревизия организации в структурах Cost V1."""

    return legacy_references_from_snapshot(repository.get_reference_snapshot(organization_id))


def current_legacy_references(
    organization_id: str = Depends(current_team_id),
    repository: EconomicsRepository = Depends(get_economics_repository),
) -> LegacyReferences:
    return load_legacy_references(repository, organization_id)
```

- [ ] **Step 2: Переписать тесты калькуляторов и геометрии под новые сигнатуры**

В `tests/test_api_cost_calculators.py` заменить импорты и класс `DrillingUnitCalculatorTests`:

```python
import unittest

from api.schemas.cost import (
    DrillingUnitCalculateRequest,
    DrillingUnitCostInputSchema,
    JobPositionSchema,
    LaborAssignmentSchema,
    LaborCalculateRequest,
)
from api.services.cost_service import calculate_drilling_unit, calculate_labor
from cost.drilling import DEFAULT_DRILLING_PRICE_PER_M
from cost.labor import LaborFOTSettings, calculate_labor_fot, labor_assignments_from_records, labor_catalog_from_records
from cost.v2.legacy_adapter import default_legacy_references


class DrillingUnitCalculatorTests(unittest.TestCase):
    def test_default_input_matches_excel_reference_price(self):
        request = DrillingUnitCalculateRequest(input=DrillingUnitCostInputSchema())
        response = calculate_drilling_unit(request, default_legacy_references())
        self.assertAlmostEqual(response.result.price_per_m, DEFAULT_DRILLING_PRICE_PER_M)
        self.assertTrue(response.summary_rows)
```

Удалить из файла импорты `tempfile`, `Path`, `patch`, `cost.persistence`. Класс `LaborCalculatorTests` не меняется.

В `tests/test_api_geometry.py`: убрать импорты `tempfile`, `Path`, `patch`, `cost.persistence`; добавить `from cost.v2.legacy_adapter import default_legacy_references`; удалить метод `setUp`; каждый вызов `post_blast_geometry(payload, team_id="default")` и `post_hole_scheme(payload, team_id="default")` заменить на `post_blast_geometry(payload, legacy=default_legacy_references())` и `post_hole_scheme(payload, legacy=default_legacy_references())`. Найти вызовы: `grep -n "team_id=" tests/test_api_geometry.py`.

Проверить `tests/test_design_cost.py`: `grep -n "estimate_design_cost\|calculate_cost(" tests/test_design_cost.py`. Каждый прямой вызов получает второй аргумент `default_legacy_references()`; если вызовы идут через `TestClient`, тест не меняется.

- [ ] **Step 3: Убедиться, что тесты падают**

Run: `.venv/bin/python -m pytest tests/test_api_cost_calculators.py tests/test_api_geometry.py tests/test_design_cost.py -q`
Expected: FAIL, `TypeError: calculate_drilling_unit() ...` (старые сигнатуры).

- [ ] **Step 4: converters.py**

В `api/services/converters.py`:
- удалить импорт `from cost.persistence import DEFAULT_TEAM_ID, load_team_references`;
- заменить импорт из `cost.drilling_data` на `from cost.drilling_data import DEFAULT_OBJECT_NAME, find_object`;
- удалить импорты `DEFAULT_CATALOG`, `catalog_to_records`, `DEFAULT_FIXED_COSTS`, `DEFAULT_LABOR_CATALOG` (оставить `catalog_from_records`, `fixed_costs_from_records`, `labor_assignments_from_records`, `labor_catalog_from_records`, `DEFAULT_LABOR_ASSIGNMENTS`, `LaborFOTSettings`);
- добавить `from cost.v2.legacy_adapter import LegacyReferences`;
- функцию `build_calculation_context` заменить на:

```python
def build_calculation_context(
    request: CostCalculateRequest,
    legacy: LegacyReferences,
) -> CalculationContext:
    """Контекст сметы: справочники — из опубликованной ревизии, переопределения — из запроса."""

    from api.exceptions import WorkObjectNotFoundError

    ctx_input = request.context or CalculationContextInputSchema()
    work_object_name = resolve_work_object_name(request.work_object_name)
    work_objects = list(legacy.work_objects)
    drill_rigs = list(legacy.drill_rigs)
    work_object = find_object(work_object_name, work_objects)
    if work_object is None:
        raise WorkObjectNotFoundError(work_object_name)

    catalog = (
        list(legacy.catalog)
        if ctx_input.catalog is None
        else catalog_from_records([item.model_dump() for item in ctx_input.catalog])
    )
    labor_catalog = (
        list(legacy.labor_catalog)
        if ctx_input.labor_catalog is None
        else labor_catalog_from_records([item.model_dump() for item in ctx_input.labor_catalog])
    )
    labor_assignments = (
        list(DEFAULT_LABOR_ASSIGNMENTS)
        if ctx_input.labor_assignments is None
        else labor_assignments_from_records([item.model_dump() for item in ctx_input.labor_assignments])
    )
    fixed_costs = (
        list(legacy.fixed_costs)
        if ctx_input.fixed_costs_items is None
        else fixed_costs_from_records([item.model_dump() for item in ctx_input.fixed_costs_items])
    )

    drilling_defaults = DrillingUnitCostInput(object_name=work_object_name)
    if ctx_input.drilling_input is not None:
        drilling_dict = drilling_defaults.__dict__ | ctx_input.drilling_input.model_dump(exclude_unset=True)
        drilling_dict["object_name"] = work_object_name
        drilling_input = DrillingUnitCostInput(**drilling_dict)
    else:
        drilling_input = DrillingUnitCostInput(**(drilling_defaults.__dict__ | {"object_name": work_object_name}))

    labor_settings = (
        LaborFOTSettings()
        if ctx_input.labor_settings is None
        else LaborFOTSettings(**ctx_input.labor_settings.model_dump())
    )

    return CalculationContext(
        work_object=work_object,
        work_objects=work_objects,
        drill_rigs=drill_rigs,
        catalog=catalog,
        labor_catalog=labor_catalog,
        labor_assignments=labor_assignments,
        fixed_costs_items=fixed_costs,
        drilling_input_base=drilling_input,
        labor_settings=labor_settings,
        scenario_phase_overrides=dict(ctx_input.scenario_phase_overrides),
    )
```

Убедиться, что `asdict` больше не нужен в этом модуле, кроме `_serialize_value` (там используется — оставить).

- [ ] **Step 5: cost_service.py**

В `api/services/cost_service.py`:
- `calculate_cost(request)` → `calculate_cost(request: CostCalculateRequest, legacy: LegacyReferences)`; вызов `build_calculation_context(request)` → `build_calculation_context(request, legacy)`; добавить импорт `from cost.v2.legacy_adapter import LegacyReferences`;
- `calculate_drilling_unit(request, team_id)` → `calculate_drilling_unit(request, legacy: LegacyReferences)`; удалить импорты `cost.drilling_data` и `cost.persistence` внутри функции; тело после импортов:

```python
    params = DrillingUnitCostInput(**request.input.model_dump())
    result = calculate_drilling_unit_cost(
        params, work_objects=list(legacy.work_objects), drill_rigs=list(legacy.drill_rigs)
    )
```

- `resolve_materials_auto(request, team_id)` → `resolve_materials_auto(request, legacy: LegacyReferences)`; удалить импорты `cost.persistence` и `cost.catalog` внутри функции; `catalog = list(legacy.catalog)`.

- [ ] **Step 6: blast_service.py и design_service.py**

В `api/services/blast_service.py` заменить `resolve_explosive_item` и первую строку `compute_geometry`:

```python
def resolve_explosive_item(legacy: LegacyReferences, explosive_key: str):
    """ВВ по ключу UI, с откатом на первый элемент справочника."""
    items = list(legacy.explosives)
    return next((item for item in items if item.key == explosive_key), items[0])


def compute_geometry(payload, legacy: LegacyReferences):
    """Геометрия скважины и блока для панели схемы заряда (api/schemas/blast.BlastGeometryRequest)."""
    from cost.geometry import (
        calculate_block_geometry,
        calculate_hole_geometry,
        normalize_initiation_config,
    )

    explosive_item = resolve_explosive_item(legacy, payload.explosive_key)
```

Добавить в начало модуля `from cost.v2.legacy_adapter import LegacyReferences`.

В `api/services/design_service.py`: `def estimate_design_cost(request: DesignCostRequest) -> AggregatedCostResultSchema:` → `def estimate_design_cost(request: DesignCostRequest, legacy: LegacyReferences) -> AggregatedCostResultSchema:`, последняя строка `return calculate_cost(cost_request, legacy)`; добавить импорт `from cost.v2.legacy_adapter import LegacyReferences`.

- [ ] **Step 7: Роутеры**

`api/routers/cost.py` полностью:

```python
"""REST-роутер сметного расчёта."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from api.schemas.cost import (
    AggregatedCostResultSchema,
    CostCalculateRequest,
    DrillingUnitCalculateRequest,
    DrillingUnitCalculateResponse,
    LaborCalculateRequest,
    LaborCalculateResponse,
    MaterialsAutoRequest,
    MaterialsAutoResponse,
)
from api.services.cost_service import (
    calculate_cost,
    calculate_drilling_unit,
    calculate_labor,
    resolve_materials_auto,
)
from api.services.legacy_references import current_legacy_references
from cost.v2.legacy_adapter import LegacyReferences

router = APIRouter(prefix="/cost", tags=["cost"])


@router.post("/calculate", response_model=AggregatedCostResultSchema)
def post_cost_calculate(
    request: CostCalculateRequest,
    legacy: LegacyReferences = Depends(current_legacy_references),
) -> AggregatedCostResultSchema:
    return calculate_cost(request, legacy)


@router.post("/drilling-unit", response_model=DrillingUnitCalculateResponse)
def post_drilling_unit(
    request: DrillingUnitCalculateRequest,
    legacy: LegacyReferences = Depends(current_legacy_references),
) -> DrillingUnitCalculateResponse:
    return calculate_drilling_unit(request, legacy)


@router.post("/labor", response_model=LaborCalculateResponse)
def post_labor(request: LaborCalculateRequest) -> LaborCalculateResponse:
    return calculate_labor(request)


@router.post("/materials-auto", response_model=MaterialsAutoResponse)
def post_materials_auto(
    request: MaterialsAutoRequest,
    legacy: LegacyReferences = Depends(current_legacy_references),
) -> MaterialsAutoResponse:
    return resolve_materials_auto(request, legacy)
```

`api/routers/blast.py`: заменить `from api.security import current_team_id` на `from api.services.legacy_references import current_legacy_references` и `from cost.v2.legacy_adapter import LegacyReferences`; в `post_blast_geometry` и `post_hole_scheme` параметр `team_id: str = Depends(current_team_id)` → `legacy: LegacyReferences = Depends(current_legacy_references)`, вызовы `compute_geometry(payload, team_id)` → `compute_geometry(payload, legacy)`.

`api/routers/design.py`, строки 252–254:

```python
@router.post("/cost", response_model=AggregatedCostResultSchema)
def post_design_cost(
    request: DesignCostRequest,
    legacy: LegacyReferences = Depends(current_legacy_references),
) -> AggregatedCostResultSchema:
    return design_service.estimate_design_cost(request, legacy)
```

с импортами `from api.services.legacy_references import current_legacy_references` и `from cost.v2.legacy_adapter import LegacyReferences`.

- [ ] **Step 8: Прогнать тесты**

Run: `.venv/bin/python -m pytest tests/test_api_cost_calculators.py tests/test_api_geometry.py tests/test_design_cost.py tests/test_api_lifecycle.py tests/test_api_passport.py -q`
Expected: PASS. Если `test_api_lifecycle` или `test_api_passport` создают `TestClient(app)` без БД и вызывают `/design/cost`, добавить в их фикстуру `app.dependency_overrides[get_economics_repository] = lambda: InMemoryEconomicsRepository()` по образцу `tests/test_api_economics.py`.

- [ ] **Step 9: Коммит**

```bash
git add api/services/legacy_references.py api/services/converters.py api/services/cost_service.py api/services/blast_service.py api/services/design_service.py api/routers/cost.py api/routers/blast.py api/routers/design.py tests/test_api_cost_calculators.py tests/test_api_geometry.py tests/test_design_cost.py tests/test_api_lifecycle.py tests/test_api_passport.py
git commit -m "refactor(api): смета, бурение и геометрия читают справочники из ревизии V2

Зависимость current_legacy_references заменяет чтение references.json в
сервисах расчёта; номенклатура, постоянные расходы и должности берутся из
справочников, если запрос их не переопределяет.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 5: Роутер `references` только для чтения

**Files:**
- Modify: `api/routers/references.py` (полностью)
- Test: `tests/test_api_team_scope.py`

**Interfaces:**
- Остаются `GET /references/{work-objects,drill-rigs,rocks,explosives,depreciation-assets,catalog}` с прежними схемами ответов; каждый принимает `legacy: LegacyReferences = Depends(current_legacy_references)`. `PUT`-маршруты удаляются.

- [ ] **Step 1: Переписать тест изоляции команд**

`tests/test_api_team_scope.py` заменить целиком:

```python
"""Справочники V1 читаются из опубликованной ревизии организации из сессии;
запись возможна только публикацией ревизии, PUT-маршрутов больше нет."""
import unittest

from fastapi import HTTPException

from api.routers import references as references_router
from api.security import require_reference_editor
from api.services.legacy_references import load_legacy_references
from cost.drilling_data import DEFAULT_WORK_OBJECTS
from cost.rock_data import DEFAULT_ROCKS
from cost.v2.models import ReferenceItem
from cost.v2.repository import InMemoryEconomicsRepository


def _publish(repository: InMemoryEconomicsRepository, organization_id: str, section: str, items: list[ReferenceItem]) -> None:
    current = repository.get_reference_snapshot(organization_id)
    sections = dict(current.sections)
    sections[section] = tuple(items)
    repository.publish_references(organization_id, "tester", current.revision_id, sections, "test")


class TeamScopedReferencesTests(unittest.TestCase):
    def setUp(self):
        self.repository = InMemoryEconomicsRepository()

    def test_published_sites_are_isolated_per_organization(self):
        _publish(
            self.repository,
            "team_b",
            "sites",
            [ReferenceItem("SITE_TEST", "Тестовый карьер", {"mobilization_km": "42", "diesel_price_ton_rub": "90000"})],
        )

        team_a = references_router.list_work_objects(legacy=load_legacy_references(self.repository, "team_a"))
        self.assertEqual([o.name for o in team_a.items], [o.name for o in DEFAULT_WORK_OBJECTS])

        team_b = references_router.list_work_objects(legacy=load_legacy_references(self.repository, "team_b"))
        self.assertEqual([o.name for o in team_b.items], ["Тестовый карьер"])
        self.assertEqual(team_b.default_name, "Тестовый карьер")
        self.assertEqual(team_b.items[0].mobilization_km, 42.0)

    def test_rocks_come_from_published_revision(self):
        _publish(
            self.repository,
            "team_c",
            "rocks",
            [ReferenceItem("ROCK_TEST", DEFAULT_ROCKS[0].name, {"density_t_m3": "9.99", "ucs_mpa": "100", "fissuring_ff": "1"})],
        )
        result = references_router.list_rocks(legacy=load_legacy_references(self.repository, "team_c"))
        self.assertEqual(result.items[0].density_t_m3, 9.99)
        self.assertEqual(result.default_name, DEFAULT_ROCKS[0].name)

    def test_put_routes_are_gone(self):
        methods = {method for route in references_router.router.routes for method in getattr(route, "methods", set())}
        self.assertEqual(methods, {"GET"})


class ReferenceEditorGateTests(unittest.TestCase):
    def test_user_role_forbidden(self):
        with self.assertRaises(HTTPException) as error:
            require_reference_editor({"role": "user"})
        self.assertEqual(error.exception.status_code, 403)

    def test_admin_and_editor_and_service_allowed(self):
        for role in ("admin", "reference_editor", "service"):
            session = {"role": role}
            self.assertIs(require_reference_editor(session), session)
```

- [ ] **Step 2: Убедиться, что тест падает**

Run: `.venv/bin/python -m pytest tests/test_api_team_scope.py -q`
Expected: FAIL, `TypeError: list_work_objects() got an unexpected keyword argument 'legacy'`.

- [ ] **Step 3: Переписать роутер**

`api/routers/references.py` заменить целиком:

```python
"""REST-роутеры справочников Cost V1: только чтение из опубликованной ревизии.

Редактирование — публикация ревизии на странице «Справочники»
(`/economics/references/publish`); отдельной записи у этих маршрутов нет.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends

from api.schemas.references import (
    CatalogItemSchema,
    CatalogListResponse,
    DrillRigListResponse,
    DrillRigSchema,
    ExplosiveCatalogSchema,
    ExplosiveListResponse,
    FixedAssetDepreciationListResponse,
    FixedAssetDepreciationSchema,
    RockListResponse,
    RockSchema,
    WorkObjectListResponse,
    WorkObjectSchema,
)
from api.services.legacy_references import current_legacy_references
from cost.drilling_data import DEFAULT_OBJECT_NAME, DEFAULT_RIG_NAME
from cost.explosive_data import DEFAULT_EXPLOSIVE_KEY
from cost.rock_data import DEFAULT_ROCK_NAME
from cost.v2.legacy_adapter import LegacyReferences

router = APIRouter(prefix="/references", tags=["references"])


@router.get("/work-objects", response_model=WorkObjectListResponse)
def list_work_objects(
    legacy: LegacyReferences = Depends(current_legacy_references),
) -> WorkObjectListResponse:
    items = list(legacy.work_objects)
    default_name = DEFAULT_OBJECT_NAME if any(o.name == DEFAULT_OBJECT_NAME for o in items) else items[0].name
    return WorkObjectListResponse(
        items=[WorkObjectSchema.model_validate(obj) for obj in items],
        default_name=default_name,
    )


@router.get("/drill-rigs", response_model=DrillRigListResponse)
def list_drill_rigs(
    legacy: LegacyReferences = Depends(current_legacy_references),
) -> DrillRigListResponse:
    items = list(legacy.drill_rigs)
    default_name = DEFAULT_RIG_NAME if any(r.name == DEFAULT_RIG_NAME for r in items) else items[0].name
    return DrillRigListResponse(
        items=[DrillRigSchema.model_validate(rig) for rig in items],
        default_name=default_name,
    )


@router.get("/rocks", response_model=RockListResponse)
def list_rocks(
    legacy: LegacyReferences = Depends(current_legacy_references),
) -> RockListResponse:
    items = list(legacy.rocks)
    default_name = DEFAULT_ROCK_NAME if any(r.name == DEFAULT_ROCK_NAME for r in items) else items[0].name
    return RockListResponse(
        items=[RockSchema.model_validate(rock) for rock in items],
        default_name=default_name,
    )


@router.get("/explosives", response_model=ExplosiveListResponse)
def list_explosives(
    legacy: LegacyReferences = Depends(current_legacy_references),
) -> ExplosiveListResponse:
    items = list(legacy.explosives)
    default_key = DEFAULT_EXPLOSIVE_KEY if any(e.key == DEFAULT_EXPLOSIVE_KEY for e in items) else items[0].key
    return ExplosiveListResponse(
        items=[ExplosiveCatalogSchema.model_validate(item) for item in items],
        default_key=default_key,
    )


@router.get("/depreciation-assets", response_model=FixedAssetDepreciationListResponse)
def list_depreciation_assets(
    legacy: LegacyReferences = Depends(current_legacy_references),
) -> FixedAssetDepreciationListResponse:
    return FixedAssetDepreciationListResponse(
        items=[FixedAssetDepreciationSchema.model_validate(asset) for asset in legacy.depreciation_assets],
    )


@router.get("/catalog", response_model=CatalogListResponse)
def list_catalog(
    legacy: LegacyReferences = Depends(current_legacy_references),
) -> CatalogListResponse:
    """Номенклатура и цены из разделов «Материалы» и «Стоимость материалов»."""

    return CatalogListResponse(items=[CatalogItemSchema.model_validate(item) for item in legacy.catalog])
```

- [ ] **Step 4: Прогнать тесты**

Run: `.venv/bin/python -m pytest tests/test_api_team_scope.py tests/test_api_security.py -q`
Expected: PASS. Если `test_api_security.py` дёргает `PUT /references/...`, заменить в нём проверку на `GET` (роль `user` теперь читает справочники, а запись проверяется на `/economics/references/publish`).

- [ ] **Step 5: Коммит**

```bash
git add api/routers/references.py tests/test_api_team_scope.py tests/test_api_security.py
git commit -m "refactor(api): справочники V1 доступны только для чтения из ревизии

PUT-маршруты /references/* удалены: единственная точка записи —
публикация ревизии на странице «Справочники».

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 6: Рабочее пространство через репозиторий

**Files:**
- Modify: `api/routers/workspace.py` (полностью)
- Modify: `api/schemas/workspace.py:53-57`
- Test: `tests/test_api_workspace.py` (создать)

**Interfaces:**
- `GET /workspace`, `PUT /workspace/snapshot`, `PUT /workspace/active-scenario`, `GET /workspace/defaults`, `GET /scenarios` — пути прежние.
- `SaveWorkspaceRequest` теряет поле `references`; поле `snapshot` принимается, но из него сохраняются только `scenario_id`, `labor_assignment_records`, `labor_shifts_per_month`, `drilling_calculator_input`, `scenario_phase_overrides`.
- В ответе `WorkspaceStateSchema.snapshot.cost_catalog_records`, `fixed_cost_records`, `labor_catalog_records` и `references.*` заполняет сервер из адаптера.

- [ ] **Step 1: Написать падающие API-тесты**

Создать `tests/test_api_workspace.py`:

```python
"""Рабочее пространство Cost V1 хранится в PostgreSQL через репозиторий;
справочники приходят из опубликованной ревизии, а не из файлов."""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routers import workspace
from api.services.economics_service import get_economics_repository
from cost.drilling_data import DEFAULT_OBJECT_NAME, DEFAULT_WORK_OBJECTS
from cost.labor import DEFAULT_LABOR_CATALOG
from cost.v2.models import ReferenceItem
from cost.v2.repository import InMemoryEconomicsRepository


def _client(monkeypatch) -> tuple[TestClient, InMemoryEconomicsRepository]:
    monkeypatch.setenv("BLASTEX_API_KEY", "test-api-key")
    monkeypatch.setenv("BLASTEX_SESSION_SECRET", "test-session-secret")
    repository = InMemoryEconomicsRepository()
    app = FastAPI()
    app.include_router(workspace.router, prefix="/api/v1")
    app.dependency_overrides[get_economics_repository] = lambda: repository
    return TestClient(app, headers={"X-API-Key": "test-api-key"}), repository


def test_fresh_organization_gets_defaults(monkeypatch) -> None:
    client, _ = _client(monkeypatch)
    response = client.get("/api/v1/workspace")
    assert response.status_code == 200
    state = response.json()
    assert state["settings"]["active_scenario_id"] == "drill_blast"
    assert state["settings"]["active_work_object_name"] == DEFAULT_OBJECT_NAME
    assert [o["name"] for o in state["references"]["work_object_records"]] == [o.name for o in DEFAULT_WORK_OBJECTS]
    assert [p["id"] for p in state["snapshot"]["labor_catalog_records"]] == [p.id for p in DEFAULT_LABOR_CATALOG]
    assert state["snapshot"]["cost_catalog_records"]
    assert state["snapshot"]["fixed_cost_records"]
    assert state["drilling_price_per_m"] > 0


def test_snapshot_and_active_object_are_persisted(monkeypatch) -> None:
    client, repository = _client(monkeypatch)
    state = client.get("/api/v1/workspace").json()
    snapshot = state["snapshot"]
    snapshot["labor_shifts_per_month"] = 9
    snapshot["labor_assignment_records"] = [
        {"id": "la_x", "position_id": "labor_master", "headcount": 2, "volume_m3": 100, "employee_shifts": 1}
    ]
    snapshot["drilling_calculator_input"] = {**snapshot["drilling_calculator_input"], "volume_m": 500}
    saved = client.put(
        "/api/v1/workspace/snapshot",
        json={"snapshot": snapshot, "active_work_object_name": DEFAULT_WORK_OBJECTS[1].name},
    )
    assert saved.status_code == 200
    body = saved.json()
    assert body["settings"]["active_work_object_name"] == DEFAULT_WORK_OBJECTS[1].name
    assert body["snapshot"]["labor_shifts_per_month"] == 9
    assert body["snapshot"]["labor_assignment_records"][0]["id"] == "la_x"
    assert body["snapshot"]["drilling_calculator_input"]["volume_m"] == 500

    stored = repository.get_legacy_scenario("default", "drill_blast")
    assert stored["labor_shifts_per_month"] == 9
    assert "cost_catalog_records" not in stored

    again = client.get("/api/v1/workspace").json()
    assert again["snapshot"]["labor_shifts_per_month"] == 9
    assert again["settings"]["active_work_object_name"] == DEFAULT_WORK_OBJECTS[1].name


def test_switching_scenario_keeps_each_scenario_state(monkeypatch) -> None:
    client, _ = _client(monkeypatch)
    state = client.get("/api/v1/workspace").json()
    snapshot = {**state["snapshot"], "labor_shifts_per_month": 3}
    client.put("/api/v1/workspace/snapshot", json={"snapshot": snapshot, "active_work_object_name": ""})

    switched = client.put("/api/v1/workspace/active-scenario", json={"scenario_id": "drilling"}).json()
    assert switched["settings"]["active_scenario_id"] == "drilling"
    assert switched["snapshot"]["scenario_id"] == "drilling"
    assert switched["snapshot"]["labor_shifts_per_month"] == 5.0

    back = client.put("/api/v1/workspace/active-scenario", json={"scenario_id": "drill_blast"}).json()
    assert back["snapshot"]["labor_shifts_per_month"] == 3


def test_published_sites_feed_the_workspace(monkeypatch) -> None:
    client, repository = _client(monkeypatch)
    current = repository.get_reference_snapshot("default")
    sections = dict(current.sections)
    sections["sites"] = (ReferenceItem("SITE_NEW", "Новый карьер", {"mobilization_km": "15"}),)
    repository.publish_references("default", "tester", current.revision_id, sections, "test")

    state = client.get("/api/v1/workspace").json()
    assert [o["name"] for o in state["references"]["work_object_records"]] == ["Новый карьер"]
```

- [ ] **Step 2: Убедиться, что тесты падают**

Run: `.venv/bin/python -m pytest tests/test_api_workspace.py -q`
Expected: FAIL (роутер читает файлы: `test_fresh_organization_gets_defaults` проходит на файлах, остальные падают на отсутствии `get_legacy_scenario` в хранилище или на поле `references`).

- [ ] **Step 3: Схема запроса**

В `api/schemas/workspace.py` класс `SaveWorkspaceRequest` заменить на:

```python
class SaveWorkspaceRequest(BaseModel):
    """Сохранение сценария сметы. Справочные записи в `snapshot` игнорируются:
    их источник — опубликованная ревизия."""

    snapshot: WorkspaceSnapshotSchema
    active_work_object_name: str = ""
```

- [ ] **Step 4: Переписать роутер**

`api/routers/workspace.py` заменить целиком:

```python
"""REST-роутер рабочего пространства Cost V1: настройки и сценарии сметы в БД,
справочники — из опубликованной ревизии."""
from __future__ import annotations

from dataclasses import asdict, replace

from fastapi import APIRouter, Depends

from api.schemas.cost import DrillingUnitCostInputSchema, FixedCostItemSchema, JobPositionSchema, LaborAssignmentSchema
from api.schemas.references import (
    CatalogItemSchema,
    DrillRigSchema,
    ExplosiveCatalogSchema,
    FixedAssetDepreciationSchema,
    RockSchema,
    WorkObjectSchema,
)
from api.schemas.workspace import (
    DefaultReferencesResponse,
    SaveWorkspaceRequest,
    ScenarioCalcProfileSchema,
    ScenarioListItemSchema,
    SwitchScenarioRequest,
    TeamReferencesSchema,
    TeamSettingsSchema,
    WorkspaceSnapshotSchema,
    WorkspaceStateSchema,
)
from api.security import current_team_id, require_internal_access
from api.services.economics_service import get_economics_repository
from api.services.legacy_references import load_legacy_references
from cost.catalog import DEFAULT_CATALOG, catalog_to_records
from cost.depreciation_data import DEFAULT_DEPRECIATION_ASSETS, depreciation_assets_to_records
from cost.drilling import DrillingUnitCostInput, calculate_drilling_unit_cost
from cost.drilling_data import (
    DEFAULT_DRILL_RIGS,
    DEFAULT_OBJECT_NAME,
    DEFAULT_WORK_OBJECTS,
    drill_rigs_to_records,
    find_object,
    work_objects_to_records,
)
from cost.explosive_data import DEFAULT_EXPLOSIVES, explosives_to_records
from cost.fixed_costs import DEFAULT_FIXED_COSTS, fixed_costs_to_records
from cost.labor import DEFAULT_LABOR_ASSIGNMENTS, DEFAULT_LABOR_CATALOG, labor_catalog_to_records
from cost.persistence import WorkspaceSnapshot, build_default_snapshot
from cost.rock_data import DEFAULT_ROCKS, rocks_to_records
from cost.scenarios import (
    DEFAULT_SCENARIO_ID,
    get_scenario_calc_profile,
    list_scenario_templates,
    normalize_scenario_id,
)
from cost.v2.legacy_adapter import LegacyReferences
from cost.v2.repository import EconomicsRepository, LegacyWorkspaceSettings

router = APIRouter(tags=["workspace"])

DEFAULT_TEAM_NAME = "Команда по умолчанию"

# Поля сценария, которые правит пользователь; справочные записи снапшота
# сервер каждый раз собирает заново из ревизии и не хранит.
_EDITABLE_SNAPSHOT_FIELDS = (
    "labor_assignment_records",
    "labor_shifts_per_month",
    "drilling_calculator_input",
    "scenario_phase_overrides",
)


def _default_settings() -> LegacyWorkspaceSettings:
    return LegacyWorkspaceSettings(
        team_name=DEFAULT_TEAM_NAME,
        active_scenario_id=DEFAULT_SCENARIO_ID,
        active_work_object_name=DEFAULT_OBJECT_NAME,
    )


def _settings(repository: EconomicsRepository, organization_id: str) -> LegacyWorkspaceSettings:
    stored = repository.get_legacy_workspace(organization_id)
    if stored is None:
        return _default_settings()
    return replace(stored, active_scenario_id=normalize_scenario_id(stored.active_scenario_id))


def _settings_schema(organization_id: str, settings: LegacyWorkspaceSettings) -> TeamSettingsSchema:
    return TeamSettingsSchema(
        team_id=organization_id,
        team_name=settings.team_name,
        active_scenario_id=settings.active_scenario_id,
        active_work_object_name=settings.active_work_object_name,
    )


def _scenario_snapshot(
    repository: EconomicsRepository,
    organization_id: str,
    scenario_id: str,
    legacy: LegacyReferences,
) -> WorkspaceSnapshot:
    snapshot = build_default_snapshot(scenario_id)
    stored = repository.get_legacy_scenario(organization_id, scenario_id)
    if stored:
        editable = {key: stored[key] for key in _EDITABLE_SNAPSHOT_FIELDS if key in stored}
        snapshot = WorkspaceSnapshot.from_dict({**snapshot.to_dict(), **editable, "scenario_id": scenario_id})
    return replace(
        snapshot,
        cost_catalog_records=catalog_to_records(list(legacy.catalog)),
        fixed_cost_records=fixed_costs_to_records(list(legacy.fixed_costs)),
        labor_catalog_records=labor_catalog_to_records(list(legacy.labor_catalog)),
    )


def _references_schema(legacy: LegacyReferences) -> TeamReferencesSchema:
    return TeamReferencesSchema(
        work_object_records=work_objects_to_records(legacy.work_objects),
        drill_rig_records=drill_rigs_to_records(legacy.drill_rigs),
        rock_records=rocks_to_records(legacy.rocks),
        explosive_records=explosives_to_records(legacy.explosives),
        depreciation_asset_records=depreciation_assets_to_records(legacy.depreciation_assets),
    )


def _drilling_price_per_m(snapshot: WorkspaceSnapshot, legacy: LegacyReferences, work_object_name: str) -> float:
    from cost.strategies.common import apply_work_object_to_drilling_input

    drilling_dict = dict(snapshot.drilling_calculator_input) or DrillingUnitCostInput().__dict__
    drilling_input = DrillingUnitCostInput(**drilling_dict)
    work_objects = list(legacy.work_objects)
    work_object = find_object(work_object_name, work_objects) or work_objects[0]
    drilling_input = apply_work_object_to_drilling_input(drilling_input, work_object.name)
    return calculate_drilling_unit_cost(
        drilling_input, work_objects=work_objects, drill_rigs=list(legacy.drill_rigs)
    ).price_per_m


def _load_state(repository: EconomicsRepository, organization_id: str) -> WorkspaceStateSchema:
    legacy = load_legacy_references(repository, organization_id)
    settings = _settings(repository, organization_id)
    snapshot = _scenario_snapshot(repository, organization_id, settings.active_scenario_id, legacy)
    return WorkspaceStateSchema(
        settings=_settings_schema(organization_id, settings),
        snapshot=WorkspaceSnapshotSchema(**asdict(snapshot)),
        references=_references_schema(legacy),
        drilling_price_per_m=_drilling_price_per_m(snapshot, legacy, settings.active_work_object_name),
    )


def _user_id(session: dict) -> str:
    return str(session.get("sub") or "unknown")


@router.get("/workspace", response_model=WorkspaceStateSchema)
def get_workspace(
    organization_id: str = Depends(current_team_id),
    repository: EconomicsRepository = Depends(get_economics_repository),
) -> WorkspaceStateSchema:
    return _load_state(repository, organization_id)


@router.put("/workspace/snapshot", response_model=WorkspaceStateSchema)
def put_workspace_snapshot(
    payload: SaveWorkspaceRequest,
    organization_id: str = Depends(current_team_id),
    session: dict = Depends(require_internal_access),
    repository: EconomicsRepository = Depends(get_economics_repository),
) -> WorkspaceStateSchema:
    scenario_id = normalize_scenario_id(payload.snapshot.scenario_id)
    user_id = _user_id(session)
    repository.import_legacy_scenarios(
        organization_id,
        user_id,
        {
            scenario_id: {
                "scenario_id": scenario_id,
                "labor_assignment_records": payload.snapshot.labor_assignment_records,
                "labor_shifts_per_month": payload.snapshot.labor_shifts_per_month,
                "drilling_calculator_input": payload.snapshot.drilling_calculator_input,
                "scenario_phase_overrides": payload.snapshot.scenario_phase_overrides,
            }
        },
    )
    settings = _settings(repository, organization_id)
    repository.import_legacy_workspace(
        organization_id,
        user_id,
        team_name=settings.team_name,
        active_scenario_id=scenario_id,
        active_work_object_name=payload.active_work_object_name or settings.active_work_object_name,
        reference_revision_id=settings.reference_revision_id,
    )
    return _load_state(repository, organization_id)


@router.put("/workspace/active-scenario", response_model=WorkspaceStateSchema)
def put_active_scenario(
    payload: SwitchScenarioRequest,
    organization_id: str = Depends(current_team_id),
    session: dict = Depends(require_internal_access),
    repository: EconomicsRepository = Depends(get_economics_repository),
) -> WorkspaceStateSchema:
    settings = _settings(repository, organization_id)
    repository.import_legacy_workspace(
        organization_id,
        _user_id(session),
        team_name=settings.team_name,
        active_scenario_id=normalize_scenario_id(payload.scenario_id),
        active_work_object_name=settings.active_work_object_name,
        reference_revision_id=settings.reference_revision_id,
    )
    return _load_state(repository, organization_id)


@router.get("/workspace/defaults", response_model=DefaultReferencesResponse)
def workspace_defaults() -> DefaultReferencesResponse:
    """Значения Cost V1 по умолчанию — для кнопок «Сбросить …» на вкладках расчёта."""
    return DefaultReferencesResponse(
        rocks=[RockSchema.model_validate(r) for r in DEFAULT_ROCKS],
        explosives=[ExplosiveCatalogSchema.model_validate(e) for e in DEFAULT_EXPLOSIVES],
        depreciation_assets=[
            FixedAssetDepreciationSchema.model_validate(a) for a in DEFAULT_DEPRECIATION_ASSETS
        ],
        work_objects=[WorkObjectSchema.model_validate(o) for o in DEFAULT_WORK_OBJECTS],
        drill_rigs=[DrillRigSchema.model_validate(r) for r in DEFAULT_DRILL_RIGS],
        catalog=[CatalogItemSchema.model_validate(i) for i in DEFAULT_CATALOG],
        fixed_costs=[FixedCostItemSchema.model_validate(i) for i in DEFAULT_FIXED_COSTS],
        labor_catalog=[JobPositionSchema.model_validate(i) for i in DEFAULT_LABOR_CATALOG],
        labor_assignments=[
            LaborAssignmentSchema.model_validate(i) for i in DEFAULT_LABOR_ASSIGNMENTS
        ],
        drilling_unit_cost_input=DrillingUnitCostInputSchema.model_validate(
            DrillingUnitCostInput().__dict__
        ),
    )


@router.get("/scenarios", response_model=list[ScenarioListItemSchema])
def list_scenarios() -> list[ScenarioListItemSchema]:
    items: list[ScenarioListItemSchema] = []
    for template in list_scenario_templates():
        profile = get_scenario_calc_profile(template.id)
        items.append(
            ScenarioListItemSchema(
                id=template.id,
                name=template.name,
                description=template.description,
                phases=[asdict(phase) for phase in template.phases],
                calc_profile=ScenarioCalcProfileSchema(
                    mode=profile.mode,
                    explosive_basis=profile.explosive_basis,
                    manual_type=profile.manual_type,
                    ui_caption=profile.ui_caption,
                    needs_blast_optimization=profile.needs_blast_optimization,
                    needs_bvr_geometry=profile.needs_bvr_geometry,
                    needs_charge_design=profile.needs_charge_design,
                    is_manual_input=profile.is_manual_input,
                ),
            )
        )
    return items
```

- [ ] **Step 5: Прогнать тесты**

Run: `.venv/bin/python -m pytest tests/test_api_workspace.py tests/test_api_scenarios.py -q`
Expected: PASS. `build_default_snapshot` пока живёт в `cost/persistence.py` и продолжает работать (Task 7 сократит модуль, но эту функцию оставит).

- [ ] **Step 6: Коммит**

```bash
git add api/routers/workspace.py api/schemas/workspace.py tests/test_api_workspace.py
git commit -m "feat(api): рабочее пространство Cost V1 хранится в PostgreSQL

Настройки команды и сценарии сметы читаются и пишутся через репозиторий;
справочные записи снапшота сервер собирает из опубликованной ревизии.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 7: Удаление файлового хранилища справочников

**Files:**
- Modify: `cost/persistence.py` (полностью)
- Delete: `cost/references_store.py`
- Modify: `cost/engine.py` (полностью)
- Modify: `README.md`, `CLAUDE.md`
- Test: `tests/test_no_streamlit_dependency.py` (добавить проверку)

**Interfaces:**
- В `cost/persistence.py` остаются: `WORKSPACE_VERSION`, `DEFAULT_TEAM_ID`, `WorkspaceSnapshot`, `project_root`, `data_root`, `team_dir`, `ensure_team_layout`, `build_default_snapshot`. Всё остальное удаляется.
- В `cost/engine.py` остаётся `CostEngine.calculate_with_context`.

- [ ] **Step 1: Тест на отсутствие чтения файлов**

В `tests/test_no_streamlit_dependency.py` добавить:

```python
def test_reference_files_are_not_read_anywhere() -> None:
    """Справочники живут только в PostgreSQL: `references.json` и
    `session_state` больше нигде не читаются (TASK-008, спецификация §7)."""
    import re
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent
    offenders: list[str] = []
    pattern = re.compile(r"references\.json|references_store|load_team_references|load_team_settings|load_scenario_snapshot")
    for path in list((root / "api").rglob("*.py")) + list((root / "cost").rglob("*.py")):
        if "import_v1" in path.name:
            continue
        if pattern.search(path.read_text(encoding="utf-8")):
            offenders.append(str(path.relative_to(root)))
    assert offenders == []
```

- [ ] **Step 2: Убедиться, что тест падает**

Run: `.venv/bin/python -m pytest tests/test_no_streamlit_dependency.py -q`
Expected: FAIL со списком `cost/persistence.py`, `cost/engine.py`, `cost/references_store.py`.

- [ ] **Step 3: Сократить `cost/persistence.py`**

Заменить файл целиком:

```python
"""Каталог данных команды и снапшот сценария сметы Cost V1.

Справочники, настройки и сценарии живут в PostgreSQL (`cost/v2/repository.py`).
Здесь остались пути `data/teams/<team>/`, которыми пользуются паспорта
проектирования и ML-слой, и структура снапшота сценария.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from cost.catalog import DEFAULT_CATALOG, catalog_to_records
from cost.drilling import DrillingUnitCostInput
from cost.fixed_costs import DEFAULT_FIXED_COSTS, fixed_costs_to_records
from cost.labor import (
    DEFAULT_LABOR_ASSIGNMENTS,
    DEFAULT_LABOR_CATALOG,
    labor_assignments_to_records,
    labor_catalog_to_records,
)
from cost.scenarios import DEFAULT_SCENARIO_ID, get_scenario_template, normalize_scenario_id

WORKSPACE_VERSION = 1
DEFAULT_TEAM_ID = "default"


@dataclass
class WorkspaceSnapshot:
    version: int = WORKSPACE_VERSION
    scenario_id: str = DEFAULT_SCENARIO_ID
    updated_at: str = ""
    cost_catalog_records: list[dict] = field(default_factory=list)
    fixed_cost_records: list[dict] = field(default_factory=list)
    labor_catalog_records: list[dict] = field(default_factory=list)
    labor_assignment_records: list[dict] = field(default_factory=list)
    labor_shifts_per_month: float = 5.0
    drilling_calculator_input: dict[str, Any] = field(default_factory=dict)
    scenario_phase_overrides: dict[str, bool] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> WorkspaceSnapshot:
        return cls(
            version=int(data.get("version", WORKSPACE_VERSION)),
            scenario_id=normalize_scenario_id(str(data.get("scenario_id", DEFAULT_SCENARIO_ID))),
            updated_at=str(data.get("updated_at", "")),
            cost_catalog_records=list(data.get("cost_catalog_records", [])),
            fixed_cost_records=list(data.get("fixed_cost_records", [])),
            labor_catalog_records=list(data.get("labor_catalog_records", [])),
            labor_assignment_records=list(data.get("labor_assignment_records", [])),
            labor_shifts_per_month=float(data.get("labor_shifts_per_month", 5.0)),
            drilling_calculator_input=dict(data.get("drilling_calculator_input", {})),
            scenario_phase_overrides={
                str(k): bool(v) for k, v in dict(data.get("scenario_phase_overrides", {})).items()
            },
        )


def project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def data_root() -> Path:
    return project_root() / "data"


def team_dir(team_id: str = DEFAULT_TEAM_ID) -> Path:
    return data_root() / "teams" / team_id


def ensure_team_layout(team_id: str = DEFAULT_TEAM_ID) -> None:
    team_dir(team_id).mkdir(parents=True, exist_ok=True)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def build_default_snapshot(scenario_id: str) -> WorkspaceSnapshot:
    template = get_scenario_template(scenario_id)
    phase_overrides = {}
    if template:
        phase_overrides = {phase.id: phase.enabled for phase in template.phases}

    return WorkspaceSnapshot(
        scenario_id=scenario_id,
        updated_at=_utc_now_iso(),
        cost_catalog_records=catalog_to_records(DEFAULT_CATALOG),
        fixed_cost_records=fixed_costs_to_records(DEFAULT_FIXED_COSTS),
        labor_catalog_records=labor_catalog_to_records(DEFAULT_LABOR_CATALOG),
        labor_assignment_records=labor_assignments_to_records(DEFAULT_LABOR_ASSIGNMENTS),
        labor_shifts_per_month=5.0,
        drilling_calculator_input=DrillingUnitCostInput().__dict__,
        scenario_phase_overrides=phase_overrides,
    )
```

Проверить, что `ensure_team_layout` нигде не ждёт подкаталога `scenarios`: `grep -rn "ensure_team_layout" --include=*.py design intelligence api cost`. Если вызовов нет, функцию тоже удалить.

- [ ] **Step 4: Удалить хранилище session_state и сократить движок**

```bash
git rm cost/references_store.py
```

`cost/engine.py` заменить целиком:

```python
"""Фасад расчёта сметы Cost V1: готовый контекст → стратегия сценария."""
from __future__ import annotations

from typing import Any

from cost.models import AggregatedCostResult, BlockCalculationInput, CalculationContext
from cost.scenarios import normalize_scenario_id
from cost.strategies.factory import ScenarioStrategyFactory


class CostEngine:
    """Делегирует расчёт стратегии сценария. Контекст собирает
    `api.services.converters.build_calculation_context`."""

    def calculate_with_context(
        self,
        *,
        context: CalculationContext,
        block_data: BlockCalculationInput | None = None,
        scenario_id: str,
        **kwargs: Any,
    ) -> AggregatedCostResult:
        scenario_id = normalize_scenario_id(scenario_id)
        strategy = ScenarioStrategyFactory.create(scenario_id)
        return strategy.calculate(block_data, context, **kwargs)
```

Проверить, что никто не вызывает удалённые методы: `grep -rn "build_context\|scenario_supports_module\|get_drilling_price_per_m\|engine.calculate(" --include=*.py api cost design tests | grep -v "calculate_with_context"`. Ожидается пусто.

- [ ] **Step 5: Документация**

В `README.md`:
- строку 11 заменить на: `- **Справочники организации** — породы, ВВ, амортизация ОС, объекты работ, бурстанки, номенклатура и цены; единственное хранилище — схема \`blastex\` в PostgreSQL, редактирование на странице «Справочники».`
- строку 69 заменить на: `├── data/teams/              # Паспорта проектирования (designs) и артефакты ML`
- в таблице страниц (строка 293) удалить строку «Справочники расчёта»; раздел «Подвкладки на «Справочники расчёта»» (строки 328–339) удалить, вместо него одна фраза: `Справочники расчёта БВР, бурения и сметы берутся из опубликованной ревизии на странице «Справочники»; без роли администратора или редактора справочников они доступны только для просмотра.`

В `CLAUDE.md` в раздел «Интерфейс» добавить абзац:

```
Справочники Cost V1 (породы, ВМ, станки, объекты, номенклатура, постоянные
расходы, должности) читаются из опубликованной ревизии V2 через
`cost/v2/legacy_adapter.py`; файловых справочников нет. Каталог `data/teams`
хранит только паспорта проектирования и артефакты ML.
```

- [ ] **Step 6: Прогнать весь набор**

Run: `.venv/bin/python -m pytest -q`
Expected: PASS. Тесты, которые патчат `cost.persistence.data_root` (проектирование, ML), продолжают работать: функция осталась.

- [ ] **Step 7: Коммит**

```bash
git add -A cost/persistence.py cost/references_store.py cost/engine.py README.md CLAUDE.md tests/test_no_streamlit_dependency.py
git commit -m "refactor(cost): справочники, настройки и сценарии больше не читаются из файлов

Удалены references_store и файловые загрузчики persistence; CostEngine
оставлен только с расчётом по готовому контексту.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 8: Перенос V1 → V2: объединение разделов, породы, `--sections`

**Files:**
- Modify: `cost/v2/import_v1.py`
- Modify: `scripts/import_cost_v1_to_project1.py`
- Test: `tests/test_cost_v2_import.py`

**Interfaces:**
- `build_import_sections(project_root, team_id, current)` — сигнатура прежняя; результат содержит существующие записи текущего снимка плюс импортированные (существующая запись побеждает при совпадении кода), раздел `rocks` из `rock_records`, у постоянных затрат `legacy_ref`.
- Скрипт: флаг `--sections a,b,c` публикует только перечисленные разделы поверх текущего снимка.

- [ ] **Step 1: Тесты**

В `tests/test_cost_v2_import.py` добавить:

```python
def test_import_merges_with_existing_records_and_keeps_rocks(tmp_path) -> None:
    from cost.v2.models import ReferenceItem, ReferenceSnapshot

    team_dir = tmp_path / "data" / "teams" / "north"
    (team_dir / "scenarios").mkdir(parents=True)
    (team_dir / "references.json").write_text(
        json.dumps(
            {
                "rock_records": [{"name": "Гранит", "density_t_m3": 2.65, "ucs_mpa": 150, "fissuring_ff": 2.0}],
                "work_object_records": [{"name": "Карьер 1", "mobilization_km": 12}],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (team_dir / "settings.json").write_text(json.dumps({"active_scenario_id": "drill_blast"}), encoding="utf-8")
    (team_dir / "scenarios" / "drill_blast.json").write_text(
        json.dumps(
            {
                "fixed_cost_records": [{"id": "fc_21_storage", "section": "2.1", "name": "Хранение", "amount_rub": 10}],
                "labor_catalog_records": [{"id": "labor_master", "name": "Мастер", "fixed_salary_monthly": 1}],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    current = default_reference_snapshot()
    sections = dict(current.sections)
    sections["positions"] = (ReferenceItem("POS_DRILLER", "Машинист БУ", {"category": "DIRECT", "operation_code": None}),)
    sections["production_units"] = (ReferenceItem("UNIT_1", "Юнит 1"),)
    sections["materials"] = (ReferenceItem("MAT_BIT", "Коронка", {"category": "TOOL"}),)
    current = ReferenceSnapshot(revision_id="R", sections=sections)

    result, _ = build_import_sections(tmp_path, "north", current)

    assert {item.code for item in result["positions"]} >= {"POS_DRILLER", "POSITION_LABOR_MASTER"}
    assert {item.code for item in result["production_units"]} == {"UNIT_1", "UNIT_NORTH"}
    assert {item.code for item in result["materials"]} >= {"MAT_BIT"}
    assert [item.name for item in result["rocks"]] == ["Гранит"]
    assert result["rocks"][0].payload["ucs_mpa"] == 150
    fixed = next(item for item in result["cost_items"] if item.payload.get("legacy_section") == "2.1")
    assert fixed.payload["legacy_ref"] == "fc_21_storage"
```

- [ ] **Step 2: Убедиться, что тест падает**

Run: `.venv/bin/python -m pytest tests/test_cost_v2_import.py -q`
Expected: FAIL, `POS_DRILLER` отсутствует (раздел заменён) и `KeyError: 'rocks'`.

- [ ] **Step 3: Объединение разделов и породы**

В `cost/v2/import_v1.py`:

1. Добавить после `_dedupe_items` функцию:

```python
def _merge_section(
    sections: dict[str, tuple[ReferenceItem, ...]],
    section: str,
    imported: list[ReferenceItem],
) -> None:
    """Дополнить раздел, не стирая записи организации: при совпадении кода
    побеждает существующая запись как более полная."""

    existing = sections.get(section, ())
    existing_codes = {item.code for item in existing}
    sections[section] = tuple(existing) + tuple(
        item for item in _dedupe_items(imported) if item.code not in existing_codes
    )
```

2. Заменить присваивания:
   - `sections["production_units"] = (ReferenceItem(...),)` → `_merge_section(sections, "production_units", [ReferenceItem(...)])` (тот же элемент);
   - `if sites: sections["sites"] = _dedupe_items(sites)` → `_merge_section(sections, "sites", sites)`;
   - блок `if equipment_types: ... sections["equipment_types"] = ...` → `_merge_section(sections, "equipment_types", equipment_types)`;
   - `if equipment: sections["equipment_assets"] = _dedupe_items(equipment)` → `_merge_section(sections, "equipment_assets", equipment)`;
   - `if materials: sections["materials"] = ...` и `if material_prices: ...` → `_merge_section(sections, "materials", materials)` и `_merge_section(sections, "material_prices", material_prices)`;
   - `if positions: ...` и `if labor_rates: ...` → `_merge_section(sections, "positions", positions)` и `_merge_section(sections, "labor_rates", labor_rates)`;
   - в блоке `if fixed_items:` заменить две строки `existing_system = ...` и `sections["cost_items"] = ...` на `_merge_section(sections, "cost_items", fixed_items)`, предупреждение оставить.

3. В цикле по `explosive_records` в payload добавить `"chart_label": row.get("chart_label") or None,` и `"material_kind": "ВВ",`.

4. В цикле по `fixed_cost_records` в payload добавить `"legacy_ref": row.get("id"),`.

5. После блока объектов (`_merge_section(sections, "sites", sites)`) добавить породы:

```python
    rocks: list[ReferenceItem] = []
    for row in references.get("rock_records", []):
        name = str(row.get("name", "Порода"))
        rocks.append(
            ReferenceItem(
                code=f"ROCK_{_code(name)}",
                name=name,
                source="Cost V1 references.json",
                payload={
                    "density_t_m3": row.get("density_t_m3"),
                    "ucs_mpa": row.get("ucs_mpa"),
                    "fissuring_ff": row.get("fissuring_ff"),
                },
            )
        )
    _merge_section(sections, "rocks", rocks)
```

Проверить `_code("Гранит")`: кириллица заменяется на `_`, результат `ITEM` — недопустимо для нескольких пород. Заменить `_code` на транслитерацию:

```python
_TRANSLIT = str.maketrans(
    "абвгдеёжзийклмнопрстуфхцчшщъыьэюя",
    "abvgdeejziyklmnoprstufhccss_y_eua",
)


def _code(value: str) -> str:
    latin = value.lower().translate(_TRANSLIT).upper()
    normalized = re.sub(r"[^A-Z0-9]+", "_", latin).strip("_")
    return (normalized or "ITEM")[:64]
```

Существующие коды в базе (`SITE_LOM`, `MAT_VV_GRANULIT`) образованы из латинских идентификаторов и не меняются. Обновить ожидания тестов, если они опираются на код с кириллицей: `grep -n "SITE_\|_code(" tests/test_cost_v2_import*.py`.

- [ ] **Step 4: Флаг `--sections` в скрипте**

В `scripts/import_cost_v1_to_project1.py`:
- после `parser.add_argument("--comment", ...)` добавить:

```python
    parser.add_argument(
        "--sections",
        default="",
        help="публиковать только перечисленные разделы через запятую, например sites,rocks",
    )
```

- после `sections, report = build_import_sections(root, args.team, current)` добавить:

```python
    only = {name.strip() for name in args.sections.split(",") if name.strip()}
    if only:
        unknown = only - set(sections)
        if unknown:
            raise SystemExit(f"Неизвестные разделы: {', '.join(sorted(unknown))}")
        sections = {
            key: (values if key in only else tuple(current.sections.get(key, ())))
            for key, values in sections.items()
        }
        output_sections = sorted(only)
    else:
        output_sections = sorted(sections)
```

- в словарь `output` добавить `"sections_published": output_sections,`.

- [ ] **Step 5: Прогнать тесты и сухой прогон**

Run: `.venv/bin/python -m pytest tests/test_cost_v2_import.py tests/test_cost_v2_import_units.py -q`
Expected: PASS.

Сухой прогон по локальной базе (пароль из `.claude/launch.json`, конфигурация `api-cost-v2`):

```bash
BLASTEX_DATABASE_URL="$(python3 -c "import json;print([c for c in json.load(open('.claude/launch.json'))['configurations'] if c['name']=='api-cost-v2'][0]['env']['BLASTEX_DATABASE_URL'])")" PYTHONPATH=. .venv/bin/python scripts/import_cost_v1_to_project1.py | python3 -c "import sys,json; d=json.load(sys.stdin); print('valid:', d['valid']); print([i for i in d['issues'] if i['level']=='error'])"
```

Expected: `valid: True` и пустой список ошибок. Если остались ошибки ссылок, вывести их и исправить сопоставление в `import_v1.py` по тексту ошибки; предупреждения о мощности ресурсов допустимы.

- [ ] **Step 6: Коммит**

```bash
git add cost/v2/import_v1.py scripts/import_cost_v1_to_project1.py tests/test_cost_v2_import.py
git commit -m "fix(import): перенос V1 дополняет разделы, переносит породы и публикует выборочно

Раздел больше не заменяется целиком, поэтому ссылки существующих записей
не рвутся; добавлены породы, ключи V1 у постоянных затрат и флаг --sections.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 9: Фронт без записи справочников V1

**Files:**
- Modify: `frontend/src/types.ts:154-176`, `frontend/src/api/endpoints.ts:148-175`, `frontend/src/app/useWorkspace.tsx`, `frontend/src/app/costContext.ts`, `frontend/src/app/AppShell.tsx`, `frontend/src/pages/LaborPage.tsx`
- Delete: `frontend/src/pages/ReferencesPage.tsx`, `frontend/src/pages/references/RocksSection.tsx`, `ExplosivesSection.tsx`, `DepreciationSection.tsx`, `OperationsSection.tsx`, `CatalogSection.tsx`, `FixedCostsSection.tsx`

**Interfaces:**
- `api.saveWorkspace({ snapshot, active_work_object_name })` без `references`.
- `useWorkspace()` без `updateReferences`; `state.references` и записи `snapshot.*_records` остаются как данные с сервера.

- [ ] **Step 1: Типы и эндпоинты**

В `frontend/src/types.ts` над `TeamReferences` добавить комментарий и оставить тип без изменений:

```ts
/** Справочники Cost V1, собранные сервером из опубликованной ревизии. Только чтение. */
```

В `frontend/src/api/endpoints.ts`:
- удалить `putRocks`, `putExplosives`, `putWorkObjects`, `putDrillRigs`, `putDepreciationAssets`;
- `saveWorkspace` заменить на:

```ts
  saveWorkspace: (payload: { snapshot: WorkspaceSnapshot; active_work_object_name: string }) =>
    put<WorkspaceState>(`${V1}/workspace/snapshot`, payload),
```

- убрать `TeamReferences` из импорта типов, если после правки он не используется в файле (`grep -n "TeamReferences" frontend/src/api/endpoints.ts`).

- [ ] **Step 2: Состояние рабочего пространства**

В `frontend/src/app/useWorkspace.tsx`:
- из `WorkspaceContextValue` удалить `updateReferences`;
- удалить функцию `updateReferences` и её место в `value`;
- в `load`, `save`, `switchScenario` ключ сохранённого состояния считать без справочников:

```ts
setSavedKey(JSON.stringify([normalized.snapshot, normalized.settings.active_work_object_name]));
```

- `dirty` считать так же:

```ts
  const dirty = useMemo(() => {
    if (!state) return false;
    return JSON.stringify([state.snapshot, state.settings.active_work_object_name]) !== savedKey;
  }, [state, savedKey]);
```

- вызов `api.saveWorkspace` без `references`;
- из импорта `./referenceRows` убрать `normalizeReferencePatch`; из импорта типов убрать `TeamReferences`.

В `frontend/src/app/referenceRows.ts` удалить функцию `normalizeReferencePatch` (осталась без вызовов).

В `frontend/src/app/costContext.ts` функцию `buildCostContext` заменить на:

```ts
/** Переопределения контекста сметы из снапшота: назначения персонала, ввод
 * бурения, смены и подэтапы. Номенклатуру, постоянные расходы и должности
 * сервер берёт из опубликованной ревизии (CalculationContextInputSchema). */
export function buildCostContext(state: WorkspaceState) {
  return {
    labor_assignments: state.snapshot.labor_assignment_records,
    drilling_input: state.snapshot.drilling_calculator_input,
    labor_settings: { shifts_per_month: state.snapshot.labor_shifts_per_month },
    scenario_phase_overrides: state.snapshot.scenario_phase_overrides,
  };
}
```

- [ ] **Step 3: Удалить страницу «Справочники расчёта»**

```bash
cd frontend && git rm src/pages/ReferencesPage.tsx src/pages/references/RocksSection.tsx src/pages/references/ExplosivesSection.tsx src/pages/references/DepreciationSection.tsx src/pages/references/OperationsSection.tsx src/pages/references/CatalogSection.tsx src/pages/references/FixedCostsSection.tsx
```

В `frontend/src/app/AppShell.tsx`:
- удалить импорт `import { ReferencesPage as CalcReferencesPage } from "../pages/ReferencesPage";`;
- из `PAGES` убрать `"Справочники расчёта"`; из словарей иконок (строка 24) и подписей (строка 34) убрать соответствующие записи;
- удалить строку `{page === "Справочники расчёта" && <CalcReferencesPage />}`.

- [ ] **Step 4: Должности на вкладке «ФОТ» только для чтения**

В `frontend/src/pages/LaborPage.tsx`:
- удалить константу `DEFAULT_LABOR_CATALOG` и импорт типа `JobPosition`, если он больше не нужен;
- `resetToDefaults` заменить на:

```ts
  function resetToDefaults() {
    updateSnapshot({
      labor_assignment_records: DEFAULT_LABOR_ASSIGNMENTS,
      labor_shifts_per_month: 5,
    });
  }
```

- блок `<h4>Справочник должностей</h4>` и следующий `<EditableTable<JobPosition> ...>` заменить на:

```tsx
      <h4>Справочник должностей</h4>
      <p className="page-caption">Должности и ставки редактируются на странице «Справочники» (разделы «Должности и ставки», «Ставки персонала»).</p>
      <table className="hole-metrics-table">
        <thead><tr><th>Код</th><th>Должность</th><th>Оклад, руб/мес</th><th>Сдельная, руб/м³</th></tr></thead>
        <tbody>
          {catalog.map((position) => (
            <tr key={position.row_id || position.id}>
              <td>{position.id}</td>
              <td>{position.name}</td>
              <td>{money(position.fixed_salary_monthly)}</td>
              <td>{position.piece_rate_per_m3}</td>
            </tr>
          ))}
        </tbody>
      </table>
```

- [ ] **Step 5: Сборка и тесты фронта**

Run:

```bash
cd frontend && npx tsc -b && npm test
```

Expected: `tsc` без ошибок; vitest PASS. Типичные остатки: неиспользуемый импорт `EditableTable` — оставить (используется для назначений), неиспользуемый `JobPosition` — удалить.

- [ ] **Step 6: Коммит**

```bash
git add -A frontend/src
git commit -m "refactor(frontend): страница «Справочники расчёта» удалена, справочники только с сервера

Сохранение рабочего пространства больше не отправляет справочники;
номенклатура, постоянные расходы и должности приходят из ревизии.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 10: Сверка «до копейки»: файлы V1 → импорт → адаптер

**Files:**
- Test: `tests/test_legacy_adapter_roundtrip.py` (создать)

**Interfaces:**
- Consumes: `build_import_sections`, `legacy_references_from_snapshot`, `default_legacy_references`, `calculate_cost`, `CostCalculateRequest`.

- [ ] **Step 1: Написать тест**

Создать `tests/test_legacy_adapter_roundtrip.py`:

```python
"""Справочники Cost V1 по умолчанию, пропущенные через импорт в V2 и адаптер,
дают те же структуры и ту же смету, что и до переезда (спецификация §6)."""
from __future__ import annotations

import json
from dataclasses import asdict

import pytest

from api.schemas.cost import CostCalculateRequest, ManualScenarioInputSchema
from api.services.cost_service import calculate_cost
from cost.catalog import DEFAULT_CATALOG, catalog_to_records
from cost.depreciation_data import DEFAULT_DEPRECIATION_ASSETS, depreciation_assets_to_records
from cost.drilling_data import DEFAULT_DRILL_RIGS, DEFAULT_WORK_OBJECTS, drill_rigs_to_records, work_objects_to_records
from cost.explosive_data import DEFAULT_EXPLOSIVES, explosives_to_records
from cost.fixed_costs import DEFAULT_FIXED_COSTS, fixed_costs_to_records
from cost.labor import DEFAULT_LABOR_CATALOG, labor_catalog_to_records
from cost.rock_data import DEFAULT_ROCKS, rocks_to_records
from cost.v2.import_v1 import build_import_sections
from cost.v2.legacy_adapter import default_legacy_references, legacy_references_from_snapshot
from cost.v2.models import ReferenceSnapshot
from cost.v2.references import default_reference_snapshot, has_validation_errors, validate_reference_sections


@pytest.fixture()
def imported_snapshot(tmp_path) -> ReferenceSnapshot:
    team_dir = tmp_path / "data" / "teams" / "default"
    (team_dir / "scenarios").mkdir(parents=True)
    (team_dir / "references.json").write_text(
        json.dumps(
            {
                "work_object_records": work_objects_to_records(DEFAULT_WORK_OBJECTS),
                "drill_rig_records": drill_rigs_to_records(DEFAULT_DRILL_RIGS),
                "rock_records": rocks_to_records(DEFAULT_ROCKS),
                "explosive_records": explosives_to_records(DEFAULT_EXPLOSIVES),
                "depreciation_asset_records": depreciation_assets_to_records(DEFAULT_DEPRECIATION_ASSETS),
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (team_dir / "settings.json").write_text(json.dumps({"active_scenario_id": "drill_blast"}), encoding="utf-8")
    (team_dir / "scenarios" / "drill_blast.json").write_text(
        json.dumps(
            {
                "cost_catalog_records": catalog_to_records(DEFAULT_CATALOG),
                "fixed_cost_records": fixed_costs_to_records(DEFAULT_FIXED_COSTS),
                "labor_catalog_records": labor_catalog_to_records(DEFAULT_LABOR_CATALOG),
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    sections, _ = build_import_sections(tmp_path, "default", default_reference_snapshot())
    assert not has_validation_errors(validate_reference_sections(sections))
    return ReferenceSnapshot(revision_id="IMPORTED", sections=sections)


def _plain(items):
    return [asdict(item) for item in items]


def test_structures_survive_import_and_adapter(imported_snapshot) -> None:
    legacy = legacy_references_from_snapshot(imported_snapshot)
    expected = default_legacy_references()

    assert not legacy.warnings, legacy.warnings
    assert _plain(legacy.work_objects) == _plain(expected.work_objects)
    assert _plain(legacy.drill_rigs) == _plain(expected.drill_rigs)
    assert _plain(legacy.rocks) == _plain(expected.rocks)
    assert _plain(legacy.explosives) == _plain(expected.explosives)
    assert _plain(legacy.catalog) == _plain(expected.catalog)
    assert _plain(legacy.fixed_costs) == _plain(expected.fixed_costs)
    assert _plain(legacy.labor_catalog) == _plain(expected.labor_catalog)
    for actual, wanted in zip(legacy.depreciation_assets, expected.depreciation_assets, strict=True):
        assert actual.name == wanted.name
        assert actual.depreciation_per_shift_rub == pytest.approx(wanted.depreciation_per_shift_rub)


def test_estimate_matches_to_the_kopeck(imported_snapshot) -> None:
    request = CostCalculateRequest(
        scenario_id="drill_blast",
        work_object_name=DEFAULT_WORK_OBJECTS[0].name,
        manual_input=ManualScenarioInputSchema(
            block_volume_m3=30_000,
            total_holes=150,
            drilling_footage_m=1_800,
            total_charge_mass_kg=24_000,
            production_volume_tons=0,
            explosive_key=DEFAULT_EXPLOSIVES[0].key,
        ),
    )
    before = calculate_cost(request, default_legacy_references()).model_dump()
    after = calculate_cost(request, legacy_references_from_snapshot(imported_snapshot)).model_dump()
    assert after == before
```

- [ ] **Step 2: Прогнать тест**

Run: `.venv/bin/python -m pytest tests/test_legacy_adapter_roundtrip.py -q`
Expected: PASS. Если `test_structures_survive_import_and_adapter` расходится:
- по `catalog[*].unit` — импорт хранит код единицы (`KG`, `PIECE`), адаптер восстанавливает символ из раздела `units` системного снимка; проверить, что `default_reference_snapshot()` содержит `KG` с `symbol: кг` и `PIECE` с `symbol: шт`;
- по `explosives[*].chart_label` — убедиться, что Task 8 пишет `chart_label` в payload;
- по `fixed_costs[*].id` — убедиться, что Task 8 пишет `legacy_ref`;
- по `catalog` из-за лишних материалов `EXP_*` — они помечены категорией `EXPLOSIVE` и в номенклатуру не попадают; если попали, проверить `_catalog_category`.

- [ ] **Step 3: Коммит**

```bash
git add tests/test_legacy_adapter_roundtrip.py
git commit -m "test(cost): смета после переезда справочников совпадает до копейки

Значения V1 по умолчанию проходят импорт в V2 и адаптер без потерь;
расчёт сценария «БВР» идентичен.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 11: Перенос данных локально и проверка в браузере

**Files:**
- Нет правок кода; при расхождениях — правки по месту с отдельным коммитом.

- [ ] **Step 1: Опубликовать данные V1 в локальную базу**

```bash
cp -r data/teams/default /private/tmp/claude-501/-Users-apple-Documents---------BlastEX/2267e90b-b560-4221-b8fb-2a910fbd1c69/scratchpad/teams-default-backup
BLASTEX_DATABASE_URL="$(python3 -c "import json;print([c for c in json.load(open('.claude/launch.json'))['configurations'] if c['name']=='api-cost-v2'][0]['env']['BLASTEX_DATABASE_URL'])")" PYTHONPATH=. .venv/bin/python scripts/import_cost_v1_to_project1.py --publish --comment "Перенос справочников Cost V1" | tail -20
```

Expected: `"published": true`, `"imported_scenarios"` со всеми семью сценариями.

Проверка в базе:

```bash
docker exec blastex-pg-dev psql -U blastex -d project1 -Atc "select count(*) from reference_items i join reference_revisions r on r.id=i.revision_id where i.section='sites' and r.sequence_no=(select max(sequence_no) from reference_revisions where organization_id='default');"
docker exec blastex-pg-dev psql -U blastex -d project1 -Atc "select active_work_object_name from legacy_workspace_settings; select scenario_key from legacy_cost_scenarios order by 1;"
```

Expected: 11 объектов (9 из V1 плюс SITE_LOM и SITE_MAIN), активный объект «карьер Ломовского месторождения», семь сценариев.

- [ ] **Step 2: Запустить API с базой и фронт**

Запустить конфигурации `api-cost-v2` и `frontend` из `.claude/launch.json` через Browser pane (`preview_start`), войти как `admin@example.ru` / `admin123` (см. память `local-dev-setup`).

- [ ] **Step 3: Проверить страницы**

Проверить и снять скриншоты:
1. Верхняя панель «Объект работ» показывает 11 объектов, среди них 9 названий из V1.
2. Пункта «Справочники расчёта» в меню нет.
3. «Бурение»: список станков из базы (6 станков V1), цена за метр совпадает с прежней при тех же вводах.
4. «ФОТ»: таблица должностей только для чтения, назначения редактируются и сохраняются кнопкой «Сохранить»; после перезагрузки страницы значения на месте.
5. «Расчёт»: панель схемы заряда предлагает ВВ «Гранулит-РП» и «ЭВЕРСИН Э-100»; смета считается без ошибок.
6. «Справочники» → «Карьеры и объекты»: 11 записей, у объектов V1 заполнены плечо мобилизации и цена ДТ.

Через `read_console_messages` и `preview_logs` убедиться, что ошибок нет.

- [ ] **Step 4: Удалить перенесённые файлы из локального каталога**

```bash
git rm -q --cached -r data/teams/default/scenarios data/teams/default/references.json data/teams/default/settings.json 2>/dev/null; rm -rf data/teams/default/scenarios data/teams/default/references.json data/teams/default/settings.json
ls data/teams/default
```

Expected: остаются `designs` и каталоги ML. Перезагрузить страницу «Расчёт»: всё работает без файлов.

- [ ] **Step 5: Полный прогон и финальный коммит**

```bash
.venv/bin/python -m pytest -q && cd frontend && npx tsc -b && npm test && cd ..
git status --short
```

Если появились правки по итогам проверки — закоммитить их одним коммитом `fix(...)` с описанием причины. Затем открыть PR из `feat/unified-references` в `main` с заголовком «Единые справочники, PR 1: адаптеры Cost V1 и рабочее пространство в БД» и описанием по спецификации §12, пункт 1, завершив описание строкой `🤖 Generated with [Claude Code](https://claude.com/claude-code)`.

---

## Самопроверка плана

- Спецификация §6 (адаптер, потребители, удаление страницы, критерий «до копейки») — Tasks 2, 4, 5, 9, 10.
- §7 (настройки и сценарии в БД, `data/teams` только `designs`) — Tasks 3, 6, 7, 11.
- §9 (перенос данных, `--sections`, исправленное сопоставление) — Tasks 8, 11.
- §11 (тесты адаптера, настроек, импорта, фронта, браузерная проверка) — Tasks 2, 3, 8, 9, 11.
- §4.2 поля для адаптера — Task 1.
- Типы: `LegacyReferences` (Task 2) используется в Tasks 4–6 с теми же именами полей; `LegacyWorkspaceSettings` (Task 3) — в Task 6; `load_legacy_references`/`current_legacy_references` (Task 4) — в Tasks 5–6; `default_legacy_references` (Task 2) — в Tasks 4, 5, 10.
