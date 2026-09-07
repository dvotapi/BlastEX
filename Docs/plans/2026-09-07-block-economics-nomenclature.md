# Экономика блока: номенклатура, бурение, бригада, техника и услуги

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Вкладка «Экономика блока» перестаёт показывать нули: сметчик выбирает наименования ВВ, НСИ, промежуточных детонаторов и электродетонаторов, количества приходят из технического паспорта, цены — из справочника «Стоимость материалов»; бурение, ФОТ бригады, амортизация техники и ручные услуги дают полную себестоимость блока.

**Architecture:** Количества берутся только из драйверов технического паспорта (`cost/v2/technical_adapter.py`), а вкладка выбирает лишь номенклатуру; новый модуль `cost/model/materials.py` умножает драйвер на актуальную цену из раздела `material_prices`. Роль позиции в смете описывает новое поле схемы `nomenclature_role` — по нему интерфейс наполняет списки, а модель связывает выбор с драйвером. Бурение остаётся единственной моделью в `cost/model/drilling.py`, вкладка показывает разложение той же цифры. Ручные услуги живут в параметрах прогона и переносятся в справочник отдельной кнопкой.

**Tech Stack:** Python 3.12, FastAPI, Pydantic v2, Decimal-арифметика; React 19 + TypeScript + Vite + vitest; PostgreSQL 16 (JSONB), Alembic.

**Утверждённый дизайн (чат 2026-09-07):**
- количества норм не дублируются в справочнике — они уже посчитаны в техническом паспорте, вкладка подтягивает только актуальные цены выбранной номенклатуры;
- стоимость бурения считает одна модель, отдельная вкладка — её разложение;
- ручной ввод услуг сохраняется в параметрах прогона, отдельная кнопка переносит сумму в справочник;
- должности, импортированные из Cost V1, переклассифицируются в данных, модель не меняется.

## Диагноз, из которого вырос план

- `cost_rules` в опубликованной ревизии пуст (0 записей), а все линейные статьи начисляет только он — `cost/model/engine.py:108`. Отсюда 0,00 по всей вкладке.
- `ModelParameters` (`cost/model/inputs.py:70`) не содержит ни одного поля номенклатуры; `material_prices` читается только для буровой оснастки (`cost/model/drilling.py:90`).
- Условия бурения заведены для станка `RIG_JK830`; для станков из импорта Cost V1 (`TYPE_*`) их нет — `cost/model/drilling.py:55` возвращает пусто.
- Должности из импорта V1 (`POSITION_LABOR_*`) имеют `category=INDIRECT` и пустой `operation_code`, `cost/model/labor.py:96` их отбрасывает.
- Типы техники `kind=SZM` и `HAZMAT_TRUCK` есть только в демонстрационных записях; без них нет смен заряжания, ФОТ взрывников и амортизации.
- Аналогичная логика уже работает в Cost V1: `cost/materials.py:55` (`auto_materials_selection`, `calculate_variable_materials`) — образец поведения, но не кода: в V2 каталог другой.

## Global Constraints

- Ветка `feat/block-economics-nomenclature` от `main`. Задачи 1–5 — один PR (номенклатура), 6–10 — второй PR (бурение, бригада, техника, услуги, данные).
- Поля payload описываются только схемами в `cost/v2/schemas/`: единица — `x-unit`, ссылка на раздел — `x-ref`, подпись — `title`, пояснение — `description`. Новых разделоспецифичных компонентов на странице «Справочники» не заводить.
- Пользователю не показывать JSON — ни в поле ввода, ни в подсказке.
- Отсутствующая запись справочника даёт предупреждение и нулевую строку, а не исключение.
- Нормы живут в `cost/model/`, цены — только в справочниках. Новая статья вида «цена × существующий драйвер» — запись `cost_rules`, а не код.
- Деньги и количества — `Decimal`, никакого `float` внутри модели; `float` только в `to_dict()` на границе API.
- Тексты, комментарии, коммиты — на русском; коммиты завершаются `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`.
- Проверки: `.venv/bin/python -m pytest -q`; фронт — `cd frontend && npm test` и типы через временный `tsconfig.check.json` (`extends ./tsconfig.app.json`, `include: ["src"]`, `exclude: ["src/**/* 2.*", "src/**/* 3.*", "node_modules"]`, файл не коммитить).
- В рабочем каталоге лежат iCloud-дубликаты « 2»/« 3» — в `git add` только явные пути задачи.

---

## Структура файлов

| Файл | Ответственность |
|---|---|
| `cost/v2/schemas/materials.py` (изменить) | поле `nomenclature_role` у номенклатуры |
| `cost/model/prices.py` (создать) | `material_price`, `material_price_source` — цена «на дату расчёта» из `material_prices` |
| `cost/model/materials.py` (создать) | роли → драйверы → строки затрат ВМ и СИ |
| `cost/model/inputs.py` (изменить) | поля номенклатуры, ручных услуг и техники в `ModelParameters` |
| `cost/model/engine.py` (изменить) | вызов `materials.compute` и `services.compute` |
| `cost/model/services.py` (создать) | ручные услуги прогона (проживание, медосмотр, сторонние организации) |
| `cost/model/drilling.py` (изменить) | вынос `material_price` в `prices.py`, разложение метра в результат |
| `cost/model/equipment.py` (изменить) | третья машина: тягач с полуприцепом под эмульсию |
| `api/schemas/block_economics.py` (изменить) | поля номенклатуры, услуг, каталоги номенклатуры в ответе умолчаний |
| `api/routers/block_economics.py` (изменить) | автоподбор номенклатуры в `/model-defaults`, маршрут переноса услуги в справочник |
| `frontend/src/types/blockEconomics.ts` (изменить) | типы номенклатуры и услуг |
| `frontend/src/pages/economics/NomenclaturePanel.tsx` (создать) | выбор ВВ, НСИ, детонаторов с ценой и суммой |
| `frontend/src/pages/economics/ServicesPanel.tsx` (создать) | ручные услуги и кнопка «в справочник» |
| `frontend/src/pages/economics/DrillingBreakdown.tsx` (создать) | разложение стоимости метра бурения |
| `frontend/src/pages/economics/ParametersPanel.tsx` (изменить) | тягач эмульсии, плановые смены техники |
| `scripts/seed_cost_v2_reference.py` (создать) | эталонная ревизия: правила затрат, условия бурения, техника, ставки |
| `scripts/reclassify_positions.py` (создать) | должности БВР из импорта V1 → DIRECT с операциями, шаблон бригады |
| `tests/test_model_materials.py`, `tests/test_model_services.py`, `tests/test_model_equipment_emulsion.py` (создать) | тесты модели |
| `tests/model_fixtures.py` (изменить) | номенклатура с ролями и ценами в фикстуре |

---

### Task 1: Роль номенклатуры в справочнике материалов

**Files:**
- Modify: `cost/v2/schemas/materials.py:15-40`
- Test: `tests/test_reference_schemas.py`

**Interfaces:**
- Produces: `MaterialPayload.nomenclature_role` — `Literal["EXPLOSIVE", "BOOSTER", "NSI_DOWNHOLE", "NSI_SURFACE", "NSI_START", "DETONATOR_ELECTRIC", "DRILL_TOOL", "OTHER"]`, значение по умолчанию `"OTHER"`.

Существующее поле `material_kind` — свободный текст из Cost V1 («ВВ», «СИ», «ТМЦ», у 23 записей пусто), машинной роли из него не вывести. Новое поле — единственный признак, по которому вкладка наполняет списки, а модель связывает выбор с драйвером паспорта.

- [ ] **Step 1: Написать падающий тест**

```python
def test_material_role_is_machine_readable() -> None:
    payload = MaterialPayload.model_validate({"nomenclature_role": "EXPLOSIVE"})
    assert payload.nomenclature_role == "EXPLOSIVE"
    schema = section_json_schema("materials")
    assert schema["properties"]["nomenclature_role"]["title"] == "Роль в смете"


def test_material_role_defaults_to_other() -> None:
    assert MaterialPayload.model_validate({}).nomenclature_role == "OTHER"
```

- [ ] **Step 2: Запустить тест и убедиться, что он падает**

Run: `.venv/bin/python -m pytest tests/test_reference_schemas.py -k role -q`
Expected: FAIL — `nomenclature_role` не существует.

- [ ] **Step 3: Добавить поле в схему**

```python
NomenclatureRole = Literal[
    "EXPLOSIVE",
    "BOOSTER",
    "NSI_DOWNHOLE",
    "NSI_SURFACE",
    "NSI_START",
    "DETONATOR_ELECTRIC",
    "DRILL_TOOL",
    "OTHER",
]


class MaterialPayload(ReferencePayload):
    ...
    nomenclature_role: NomenclatureRole = Field(
        default="OTHER",
        title="Роль в смете",
        description=(
            "Что это в расчёте блока: основное ВВ, промежуточный детонатор, "
            "скважинное, поверхностное или стартовое НСИ, электродетонатор, "
            "буровой инструмент"
        ),
    )
```

- [ ] **Step 4: Запустить тесты**

Run: `.venv/bin/python -m pytest tests/test_reference_schemas.py -q`
Expected: PASS

- [ ] **Step 5: Коммит**

```bash
git add cost/v2/schemas/materials.py tests/test_reference_schemas.py
git commit -m "feat(references): роль номенклатуры в смете у материалов"
```

---

### Task 2: Цена материала на дату расчёта

**Files:**
- Create: `cost/model/prices.py`
- Modify: `cost/model/drilling.py:88-101` (удалить `material_price`, импортировать из `prices`)
- Test: `tests/test_model_prices.py`

**Interfaces:**
- Consumes: `ModelContext.items("material_prices")`.
- Produces: `material_price(context, material_code) -> Decimal` — цена плюс доставка последней по `valid_from` записи; `price_source(context, material_code) -> str` — код записи цены для колонки происхождения.

- [ ] **Step 1: Написать падающий тест**

```python
def test_price_takes_latest_valid_from_and_adds_delivery() -> None:
    context = build_context(
        material_prices=(
            item("P_OLD", "Цена 2025", {"material_code": "MAT_VV_EVERSIN", "price_rub": "40"}, valid_from="2025-01-01"),
            item("P_NEW", "Цена 2026", {"material_code": "MAT_VV_EVERSIN", "price_rub": "48.9", "delivery_rub": "1.1"}, valid_from="2026-01-01"),
        )
    )
    assert material_price(context, "MAT_VV_EVERSIN") == Decimal("50.0")
    assert price_source(context, "MAT_VV_EVERSIN") == "material_prices.P_NEW"


def test_price_of_unknown_material_is_zero() -> None:
    assert material_price(build_context(), "MAT_NONE") == Decimal("0")
```

- [ ] **Step 2: Запустить и убедиться в падении**

Run: `.venv/bin/python -m pytest tests/test_model_prices.py -q`
Expected: FAIL — модуля `cost.model.prices` нет.

- [ ] **Step 3: Перенести функцию из `drilling.py`**

```python
"""Цены материалов: единственное место, где модель читает `material_prices`."""
from __future__ import annotations

from decimal import Decimal

from cost.model.inputs import ModelContext, payload_number, payload_text
from cost.v2.models import ReferenceItem


def _latest(context: ModelContext, material_code: str) -> ReferenceItem | None:
    prices = [
        item
        for item in context.items("material_prices")
        if payload_text(item, "material_code") == material_code
    ]
    if not prices:
        return None
    # Последняя по valid_from запись — цена «на дату расчёта».
    prices.sort(key=lambda item: (item.valid_from is not None, item.valid_from or ""), reverse=True)
    return prices[0]


def material_price(context: ModelContext, material_code: str) -> Decimal:
    """Цена материала: цена плюс доставка, включённая в цену."""

    row = _latest(context, material_code)
    if row is None:
        return Decimal("0")
    return payload_number(row, "price_rub") + payload_number(row, "delivery_rub")


def price_source(context: ModelContext, material_code: str) -> str:
    row = _latest(context, material_code)
    return f"material_prices.{row.code}" if row is not None else ""
```

В `cost/model/drilling.py` удалить определение `material_price` и заменить импортом `from cost.model.prices import material_price`.

- [ ] **Step 4: Запустить тесты**

Run: `.venv/bin/python -m pytest tests/test_model_prices.py tests/test_model_engine.py -q`
Expected: PASS — расчёт бурения не изменился.

- [ ] **Step 5: Коммит**

```bash
git add cost/model/prices.py cost/model/drilling.py tests/test_model_prices.py
git commit -m "refactor(model): цена материала — общий модуль prices"
```

---

### Task 3: Номенклатура в параметрах модели

**Files:**
- Modify: `cost/model/inputs.py:66-125` (`ModelParameters`)
- Modify: `api/schemas/block_economics.py:22-40` (`ModelParametersSchema`)
- Test: `tests/test_model_inputs.py`, `tests/test_api_block_economics.py`

**Interfaces:**
- Produces: `ModelParameters.nomenclature: Mapping[str, str]` — роль → код материала; `ModelParameters.electric_detonators_qty: Decimal` — количество ЭД на блок (в паспорте такого драйвера нет, это ручное число).

Отдельные поля под каждую роль не заводим: ролей семь, и каждая новая роль иначе означала бы правку трёх слоёв. Ключ словаря проверяется по списку ролей схемы.

- [ ] **Step 1: Написать падающий тест**

```python
def test_parameters_carry_nomenclature_selection() -> None:
    params = ModelParameters.from_dict(
        {
            "package_code": "DRILL_AND_BLAST",
            "nomenclature": {"EXPLOSIVE": "MAT_VV_EVERSIN", "NSI_DOWNHOLE": "MAT_NSI_90"},
            "electric_detonators_qty": "2",
        }
    )
    assert params.nomenclature["EXPLOSIVE"] == "MAT_VV_EVERSIN"
    assert params.electric_detonators_qty == Decimal("2")
    assert params.to_dict()["nomenclature"]["NSI_DOWNHOLE"] == "MAT_NSI_90"
```

- [ ] **Step 2: Запустить и убедиться в падении**

Run: `.venv/bin/python -m pytest tests/test_model_inputs.py -k nomenclature -q`
Expected: FAIL — `ModelParameters` не принимает `nomenclature`.

- [ ] **Step 3: Добавить поля**

В `cost/model/inputs.py`:

```python
@dataclass(frozen=True)
class ModelParameters:
    ...
    nomenclature: Mapping[str, str] = field(default_factory=dict)
    electric_detonators_qty: Decimal = Decimal("0")
```

В `from_dict`:

```python
            nomenclature={
                str(role): str(code)
                for role, code in dict(data.get("nomenclature") or {}).items()
                if code not in (None, "")
            },
            electric_detonators_qty=decimal_value(data.get("electric_detonators_qty")),
```

В `to_dict`:

```python
            "nomenclature": dict(self.nomenclature),
            "electric_detonators_qty": str(self.electric_detonators_qty),
```

В `api/schemas/block_economics.py`:

```python
    nomenclature: dict[str, str] = Field(default_factory=dict)
    electric_detonators_qty: Decimal = Field(Decimal("0"), ge=0)
```

- [ ] **Step 4: Запустить тесты**

Run: `.venv/bin/python -m pytest tests/test_model_inputs.py tests/test_api_block_economics.py -q`
Expected: PASS

- [ ] **Step 5: Коммит**

```bash
git add cost/model/inputs.py api/schemas/block_economics.py tests/test_model_inputs.py
git commit -m "feat(model): выбор номенклатуры и количество ЭД в параметрах модели"
```

---

### Task 4: Строки затрат по выбранной номенклатуре

**Files:**
- Create: `cost/model/materials.py`
- Modify: `cost/model/engine.py:40-46` (порядок вызовов)
- Modify: `tests/model_fixtures.py` (материалы с ролями и цены)
- Test: `tests/test_model_materials.py`

**Interfaces:**
- Consumes: `material_price`, `price_source` из `cost.model.prices`; драйверы паспорта `explosive_kg`, `intermediate_detonators`, `downhole_nsi`, `surface_nsi`, `start_nsi`.
- Produces: `compute(context) -> None` — добавляет строки слоя `VARIABLE`; натуральные величины `nsi_pieces.<роль>` для колонки происхождения.

Соответствие ролей драйверам и операциям фиксировано — это способ считать смету, а не настройка:

| Роль | Драйвер паспорта | Операция | Единица |
|---|---|---|---|
| `EXPLOSIVE` | `explosive_kg` | `EVV_MANUFACTURE_ON_SITE` | кг |
| `BOOSTER` | `intermediate_detonators` × `mass_kg` номенклатуры | `PRIMER_ASSEMBLY` | кг |
| `NSI_DOWNHOLE` | `downhole_nsi` | `PRIMER_ASSEMBLY` | шт |
| `NSI_SURFACE` | `surface_nsi` | `INITIATION_NETWORK` | шт |
| `NSI_START` | `start_nsi` | `INITIATION_NETWORK` | шт |
| `DETONATOR_ELECTRIC` | `electric_detonators_qty` (параметр) | `BLAST_EXECUTION` | шт |

- [ ] **Step 1: Написать падающий тест**

```python
def test_explosive_line_is_mass_times_current_price() -> None:
    context = build_context(
        params=params(nomenclature={"EXPLOSIVE": "MAT_VV_EVERSIN"}),
        physical={"explosive_kg": Decimal("29038.86")},
    )
    materials.compute(context)
    line = next(row for row in context.lines if row.cost_item_code == "MATERIAL_EXPLOSIVE")
    assert line.amount_rub == Decimal("29038.86") * Decimal("48.9")
    assert line.layer is CostLayer.VARIABLE
    assert "48.9 ₽/кг" in line.formula


def test_booster_pieces_are_converted_to_kilograms() -> None:
    context = build_context(
        params=params(nomenclature={"BOOSTER": "MAT_SV_SFERIT_08"}),
        physical={"intermediate_detonators": Decimal("189")},
    )
    materials.compute(context)
    line = next(row for row in context.lines if row.cost_item_code == "MATERIAL_BOOSTER")
    assert line.amount_rub == Decimal("189") * Decimal("0.8") * Decimal("150")


def test_missing_selection_warns_and_adds_no_line() -> None:
    context = build_context(physical={"explosive_kg": Decimal("100")})
    materials.compute(context)
    assert context.lines == []
    assert any("Не выбрано основное ВВ" in text for text in context.warnings)


def test_missing_price_warns_and_adds_no_line() -> None:
    context = build_context(
        params=params(nomenclature={"EXPLOSIVE": "MAT_VV_NO_PRICE"}),
        physical={"explosive_kg": Decimal("100")},
    )
    materials.compute(context)
    assert context.lines == []
    assert any("нет цены" in text for text in context.warnings)


def test_role_outside_package_is_skipped() -> None:
    context = build_context(
        package_operations=("PRODUCTION_DRILLING",),
        params=params(nomenclature={"EXPLOSIVE": "MAT_VV_EVERSIN"}),
        physical={"explosive_kg": Decimal("100")},
    )
    materials.compute(context)
    assert context.lines == []
```

- [ ] **Step 2: Запустить и убедиться в падении**

Run: `.venv/bin/python -m pytest tests/test_model_materials.py -q`
Expected: FAIL — модуля `cost.model.materials` нет.

- [ ] **Step 3: Написать модуль**

```python
"""Стоимость ВМ и средств инициирования по выбранной номенклатуре.

Количество берётся из технического паспорта, цена — из справочника
«Стоимость материалов». Модель не хранит норм расхода: их посчитал
технический расчёт блока.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from cost.model.inputs import ModelContext, payload_number
from cost.model.prices import material_price, price_source
from cost.v2.models import CostLayer


@dataclass(frozen=True)
class Role:
    code: str
    driver: str
    operation_code: str
    cost_item_code: str
    unit: str
    missing_message: str
    per_piece_mass: bool = False


ROLES: tuple[Role, ...] = (
    Role("EXPLOSIVE", "explosive_kg", "EVV_MANUFACTURE_ON_SITE", "MATERIAL_EXPLOSIVE", "кг",
         "Не выбрано основное ВВ: масса заряда не оценена в деньгах."),
    Role("BOOSTER", "intermediate_detonators", "PRIMER_ASSEMBLY", "MATERIAL_BOOSTER", "кг",
         "Не выбран промежуточный детонатор: боевики не оценены в деньгах.",
         per_piece_mass=True),
    Role("NSI_DOWNHOLE", "downhole_nsi", "PRIMER_ASSEMBLY", "MATERIAL_NSI_DOWNHOLE", "шт",
         "Не выбрано скважинное НСИ: внутрискважинная сеть не оценена в деньгах."),
    Role("NSI_SURFACE", "surface_nsi", "INITIATION_NETWORK", "MATERIAL_NSI_SURFACE", "шт",
         "Не выбрано поверхностное НСИ: поверхностная сеть не оценена в деньгах."),
    Role("NSI_START", "start_nsi", "INITIATION_NETWORK", "MATERIAL_NSI_START", "шт",
         "Не выбрано стартовое устройство: запуск сети не оценён в деньгах."),
    Role("DETONATOR_ELECTRIC", "electric_detonators", "BLAST_EXECUTION", "MATERIAL_DETONATOR", "шт",
         "Не выбран электродетонатор: указано количество, но нет наименования."),
)


def compute(context: ModelContext) -> None:
    # Электродетонаторов в паспорте нет: их число задаёт сметчик на вкладке.
    context.set_value(
        "electric_detonators",
        context.params.electric_detonators_qty,
        "количество задано на вкладке",
    )
    for role in ROLES:
        _role_line(context, role)


def _role_line(context: ModelContext, role: Role) -> None:
    if not context.has_operation(role.operation_code):
        return
    quantity = context.value(role.driver)
    if quantity <= 0:
        return
    code = context.params.nomenclature.get(role.code, "")
    if not code:
        context.warn(role.missing_message)
        return
    material = context.item("materials", code)
    if material is None:
        context.warn(f"Номенклатура {code} не найдена в справочнике материалов.")
        return
    if role.per_piece_mass:
        mass_kg = payload_number(material, "mass_kg")
        if mass_kg <= 0:
            context.warn(
                f"У номенклатуры {material.name} не задана масса единицы: "
                "штуки не переведены в килограммы."
            )
            return
        pieces, quantity = quantity, quantity * mass_kg
        quantity_formula = f"{pieces} шт × {mass_kg} кг"
    else:
        quantity_formula = f"{quantity} {role.unit}"
    price = material_price(context, code)
    if price <= 0:
        context.warn(f"Для номенклатуры {material.name} нет цены в разделе «Стоимость материалов».")
        return
    context.set_value(f"nomenclature.{role.code}", quantity, quantity_formula)
    context.add_line(
        operation_code=role.operation_code,
        cost_item_code=role.cost_item_code,
        cost_item_name=material.name,
        layer=CostLayer.VARIABLE,
        amount_rub=quantity * price,
        formula=f"{quantity_formula} × {price} ₽/{role.unit} ({price_source(context, code)})",
        resource_code=code,
    )
```

В `cost/model/engine.py` вызвать модуль сразу после логистики — до `labor`, чтобы предупреждения шли в порядке сметы:

```python
    drilling.compute(context)
    logistics.compute(context)
    materials.compute(context)
    labor.compute(context)
```

В `tests/model_fixtures.py` добавить в раздел `materials` записи с `nomenclature_role` и `mass_kg`, в `material_prices` — цены к ним (Эверсин 48,9 ₽/кг; «Сферит ДП» 150 ₽/кг при `mass_kg = 0.8`; скважинное НСИ 99,91 ₽/шт).

- [ ] **Step 4: Запустить тесты**

Run: `.venv/bin/python -m pytest tests/test_model_materials.py tests/test_model_engine.py -q`
Expected: PASS

- [ ] **Step 5: Коммит**

```bash
git add cost/model/materials.py cost/model/engine.py tests/test_model_materials.py tests/model_fixtures.py
git commit -m "feat(model): стоимость ВМ и СИ по выбранной номенклатуре"
```

---

### Task 5: Автоподбор номенклатуры и панель выбора

**Files:**
- Modify: `api/routers/block_economics.py:256-331` (`/model-defaults`)
- Modify: `api/schemas/block_economics.py` (`ModelDefaultsResponse.nomenclature`)
- Create: `frontend/src/pages/economics/NomenclaturePanel.tsx`
- Modify: `frontend/src/types/blockEconomics.ts`, `frontend/src/pages/economics/BlockEconomicsPage.tsx:290-292`
- Test: `tests/test_api_block_economics.py`, `frontend/src/pages/economics/NomenclaturePanel.test.tsx`

**Interfaces:**
- Produces: `ModelDefaultsResponse.nomenclature: dict[str, list[MaterialOption]]`, где `MaterialOption = {code, name, unit, price_rub}`; `ModelParametersSchema.nomenclature` заполняется автоподбором.

Автоподбор повторяет поведение Cost V1 (`cost/materials.py:55`): первая активная позиция роли, а скважинное НСИ — ближайшее по длине к драйверу `nsi_length_m` паспорта, делённому на число скважин.

- [ ] **Step 1: Написать падающий тест API**

```python
def test_defaults_offer_nomenclature_with_prices() -> None:
    response = client.get("/economics/model-defaults", params={"technical_passport_id": passport_id})
    body = response.json()
    explosives = body["nomenclature"]["EXPLOSIVE"]
    assert {"code", "name", "unit", "price_rub"} <= set(explosives[0])
    assert body["parameters"]["nomenclature"]["EXPLOSIVE"] == explosives[0]["code"]


def test_downhole_nsi_default_is_closest_by_length() -> None:
    # В паспорте 189 скважин и 1701 м НСИ — 9 м на скважину.
    response = client.get("/economics/model-defaults", params={"technical_passport_id": passport_id})
    assert response.json()["parameters"]["nomenclature"]["NSI_DOWNHOLE"] == "MAT_NSI_90"
```

- [ ] **Step 2: Запустить и убедиться в падении**

Run: `.venv/bin/python -m pytest tests/test_api_block_economics.py -k nomenclature -q`
Expected: FAIL — ключа `nomenclature` в ответе нет.

- [ ] **Step 3: Реализовать автоподбор и панель**

В `api/routers/block_economics.py`:

```python
def _nomenclature(references: ReferenceSnapshot) -> dict[str, list[dict[str, Any]]]:
    catalog: dict[str, list[dict[str, Any]]] = {}
    for item in references.active_items("materials"):
        role = payload_text(item, "nomenclature_role", "OTHER")
        if role in ("OTHER", "DRILL_TOOL"):
            continue
        catalog.setdefault(role, []).append(
            {
                "code": item.code,
                "name": item.name,
                "unit": payload_text(item, "unit"),
                "price_rub": float(_price(references, item.code)),
                "length_m": float(payload_number(item, "length_m")),
            }
        )
    return catalog


def _default_nomenclature(
    catalog: dict[str, list[dict[str, Any]]], passport: StoredTechnicalPassport
) -> dict[str, str]:
    chosen = {role: options[0]["code"] for role, options in catalog.items() if options}
    holes = decimal_value(passport.physical.get("holes"))
    nsi_length = decimal_value(passport.physical.get("nsi_length_m"))
    downhole = catalog.get("NSI_DOWNHOLE") or []
    if holes > 0 and nsi_length > 0 and downhole:
        target = float(nsi_length / holes)
        # Ближайшее по длине НСИ: короче скважины сеть не смонтировать.
        closest = min(
            (row for row in downhole if row["length_m"] > 0),
            key=lambda row: abs(row["length_m"] - target),
            default=None,
        )
        if closest is not None:
            chosen["NSI_DOWNHOLE"] = closest["code"]
    return chosen
```

`_price` — обёртка над `cost.model.prices.material_price`, принимающая снимок справочников напрямую.

Компонент `NomenclaturePanel.tsx`:

```tsx
const ROLE_LABELS: Array<{ role: string; label: string; hint: string }> = [
  { role: "EXPLOSIVE", label: "Основное ВВ", hint: "масса заряда из паспорта" },
  { role: "BOOSTER", label: "Промежуточный детонатор", hint: "боевики из паспорта" },
  { role: "NSI_DOWNHOLE", label: "Скважинные НСИ", hint: "по числу скважин" },
  { role: "NSI_SURFACE", label: "Поверхностные НСИ", hint: "из схемы монтажа" },
  { role: "NSI_START", label: "Стартовые НСИ", hint: "из схемы монтажа" },
  { role: "DETONATOR_ELECTRIC", label: "Электродетонаторы", hint: "количество вручную" },
];

export function NomenclaturePanel({ params, defaults, onChange }: Props) {
  return (
    <section className="panel block-economics-nomenclature">
      <header><b>Номенклатура блока</b><span>цены из справочника</span></header>
      <div className="panel-body">
        {ROLE_LABELS.map(({ role, label, hint }) => {
          const options = defaults.nomenclature[role] ?? [];
          const selected = options.find((item) => item.code === params.nomenclature[role]);
          return (
            <label key={role}>
              {label}
              <select
                value={params.nomenclature[role] ?? ""}
                onChange={(event) =>
                  onChange({ nomenclature: { ...params.nomenclature, [role]: event.target.value } })
                }
              >
                <option value="">не выбрано</option>
                {options.map((item) => (
                  <option key={item.code} value={item.code}>{item.name}</option>
                ))}
              </select>
              <small>{selected ? `${formatPrice(selected.price_rub)} ₽/${selected.unit}` : hint}</small>
            </label>
          );
        })}
      </div>
    </section>
  );
}
```

Панель встаёт в `BlockEconomicsPage.tsx` над `ParametersPanel`: номенклатура — первое, что выбирает сметчик после переноса паспорта.

- [ ] **Step 4: Запустить тесты**

Run: `.venv/bin/python -m pytest tests/test_api_block_economics.py -q` и `cd frontend && npm test`
Expected: PASS

- [ ] **Step 5: Коммит**

```bash
git add api/routers/block_economics.py api/schemas/block_economics.py frontend/src/pages/economics/NomenclaturePanel.tsx frontend/src/pages/economics/BlockEconomicsPage.tsx frontend/src/types/blockEconomics.ts tests/test_api_block_economics.py
git commit -m "feat(economics): выбор номенклатуры блока с ценами из справочника"
```

---

### Task 6: Разложение стоимости бурения

**Files:**
- Modify: `cost/model/drilling.py:100-200` (вернуть разложение в результат), `cost/model/inputs.py` (`BlockEconomics.drilling`)
- Create: `frontend/src/pages/economics/DrillingBreakdown.tsx`
- Test: `tests/test_model_drilling_breakdown.py`

**Interfaces:**
- Produces: `BlockEconomics.drilling: DrillingBreakdown | None` со свойствами `condition_code`, `condition_source`, `tech_speed_m_per_h`, `commercial_speed_m_per_shift`, `rig_shifts`, `plan_shifts`, `variable_rub_per_m`, `fixed_rub_per_m`, `tooling: tuple[ToolingLine, ...]`.

Кода расчёта не добавляем: `DrillingNorms` уже содержит все величины, не хватает только их передачи наружу и экрана. Предупреждение о ненайденном условии дополняется подсказкой, что завести.

- [ ] **Step 1: Написать падающий тест**

```python
def test_result_carries_drilling_breakdown() -> None:
    result = compute_block_economics(snapshot, params(), references)
    assert result.drilling is not None
    assert result.drilling.condition_source.startswith("drilling_conditions.")
    assert result.drilling.variable_rub_per_m > 0
    assert result.drilling.fixed_rub_per_m > 0


def test_missing_condition_names_the_rig_in_warning() -> None:
    result = compute_block_economics(snapshot, params(rig_code="TYPE_JK_830_2"), references)
    assert result.drilling is None
    assert any(
        "TYPE_JK_830_2" in text and "«Условия бурения»" in text for text in result.warnings
    )
```

- [ ] **Step 2: Запустить и убедиться в падении**

Run: `.venv/bin/python -m pytest tests/test_model_drilling_breakdown.py -q`
Expected: FAIL — у результата нет поля `drilling`.

- [ ] **Step 3: Пробросить разложение и нарисовать экран**

`drilling.compute` уже возвращает `DrillingNorms`; в `engine.compute_block_economics` сохранить его в результат, а `BlockEconomics.to_dict` добавить ключ `drilling`. Текст предупреждения в `pick_condition` изменить на: `нет условий бурения для станка {rig_code}: заведите запись в разделе «Условия бурения»`.

`DrillingBreakdown.tsx` — таблица: норма (код записи и по какому признаку подобрана), техническая скорость м/ч, коммерческая м/см, смены на блок, ₽/м переменная часть, ₽/м постоянная часть, итог ₽/м и ₽ на блок; отдельным блоком — износ коронки, ППУ, штанг с ценой и количеством.

- [ ] **Step 4: Запустить тесты**

Run: `.venv/bin/python -m pytest tests/test_model_drilling_breakdown.py -q` и `cd frontend && npm test`
Expected: PASS

- [ ] **Step 5: Коммит**

```bash
git add cost/model/drilling.py cost/model/inputs.py cost/model/engine.py frontend/src/pages/economics/DrillingBreakdown.tsx tests/test_model_drilling_breakdown.py
git commit -m "feat(economics): разложение стоимости метра бурения на вкладке"
```

---

### Task 7: Должности БВР и бригада по умолчанию

**Files:**
- Create: `scripts/reclassify_positions.py`
- Test: `tests/test_reclassify_positions.py`

**Interfaces:**
- Produces: скрипт публикует новую ревизию справочников, в которой должности блока — `category=DIRECT` с операцией, нормой смен и сдельным драйвером, а `crew_templates.CREW_DRILL_AND_BLAST` содержит состав по умолчанию.

Состав по умолчанию — из задачи заказчика: мастер БВР 1, взрывник 2, водитель-оператор СЗМ 1, водитель ДОПОГ кат. E 1, горнорабочий 2.

| Должность | Операция | Драйвер сдельной части |
|---|---|---|
| `POSITION_LABOR_MASTER` | `BLAST_EXECUTION` | `rock_volume_m3` |
| `POSITION_LABOR_BLASTERS` | `BLAST_EXECUTION` | `rock_volume_m3` |
| `POSITION_LABOR_DRIVER_SZM` | `BULK_CHARGING_SZM` | `explosive_kg` |
| `POSITION_LABOR_DRIVER_DEL` | `VM_DELIVERY_SITE` | `rock_volume_m3` |
| `POSITION_LABOR_MINER` | `CHARGING_HOSE_ASSISTANCE` | `rock_volume_m3` |
| `POSITION_LABOR_DRILLER` | `PRODUCTION_DRILLING` | `drilling_m` |
| `POSITION_LABOR_ASSISTANT` | `PRODUCTION_DRILLING` | `drilling_m` |

Всем прямым должностям задаётся `norm_shifts_per_month` (21 для сменного персонала, 15 для бурильщиков — как у демонстрационных `POS_*`) и `norm_operations_per_month` — норма взрывов в месяц, без неё `labor.py:210` считает одну смену на блок и предупреждает.

- [ ] **Step 1: Написать падающий тест**

```python
def test_reclassified_positions_produce_labor_lines() -> None:
    references = reclassify(fixture_snapshot())
    context = ModelContext(references, params(crew=DEFAULT_CREW), physical(), passport_name="Блок")
    labor.compute(context)
    codes = {line.cost_item_code for line in context.lines}
    assert "LABOR_POSITION_LABOR_MASTER" in codes
    assert "LABOR_CONTRIBUTIONS" in codes
    assert "LABOR_VACATION_RESERVE" in codes


def test_default_crew_template_has_seven_people() -> None:
    references = reclassify(fixture_snapshot())
    template = references.item("crew_templates", "CREW_DRILL_AND_BLAST")
    assert sum(Decimal(str(m["headcount"])) for m in template.payload["members"]) == Decimal("7")
```

- [ ] **Step 2: Запустить и убедиться в падении**

Run: `.venv/bin/python -m pytest tests/test_reclassify_positions.py -q`
Expected: FAIL — скрипта нет.

- [ ] **Step 3: Написать скрипт**

Скрипт читает актуальную ревизию через `EconomicsRepository`, применяет таблицу выше к разделу `positions`, дописывает `crew_templates` и публикует новую ревизию с комментарием «Классификация должностей БВР». Запуск: `.venv/bin/python scripts/reclassify_positions.py --organization default --publish`. Должности, которых нет в таблице, не трогаются — они остаются косвенными затратами юнита.

- [ ] **Step 4: Запустить тесты и скрипт на dev-базе**

Run: `.venv/bin/python -m pytest tests/test_reclassify_positions.py -q`
Expected: PASS

- [ ] **Step 5: Коммит**

```bash
git add scripts/reclassify_positions.py tests/test_reclassify_positions.py
git commit -m "feat(references): должности БВР как прямой персонал и бригада по умолчанию"
```

---

### Task 8: Тягач с полуприцепом под эмульсию

**Files:**
- Modify: `cost/model/equipment.py:16-30` (`MACHINES`), `cost/model/inputs.py` (`emulsion_truck_code`, `machine_plan_shifts`)
- Modify: `frontend/src/pages/economics/ParametersPanel.tsx`
- Test: `tests/test_model_equipment_emulsion.py`

**Interfaces:**
- Produces: `ModelParameters.emulsion_truck_code: str | None`, `ModelParameters.machine_plan_shifts: Mapping[str, Decimal]` — нормативные смены по коду техники, заданные вручную.

Тягач возит компоненты эмульсии — драйвер смен уже есть: `delivery_shifts` считается для доставщика ВМ, для тягача нужен собственный, выведенный из `bulk_kg` и грузоподъёмности; операция — `COMPONENT_DELIVERY`.

- [ ] **Step 1: Написать падающий тест**

```python
def test_emulsion_truck_gets_depreciation_from_manual_plan_shifts() -> None:
    context = build_context(
        params=params(emulsion_truck_code="TRUCK_EMULSION_20T", machine_plan_shifts={"TRUCK_EMULSION_20T": Decimal("18")}),
        physical={"bulk_kg": Decimal("29038.86")},
    )
    logistics.compute(context)
    equipment.compute(context)
    line = next(row for row in context.lines if row.cost_item_code == "EMULSION_TRUCK_DEPRECIATION")
    assert line.amount_rub > 0
    assert "18 см" in line.formula
```

- [ ] **Step 2: Запустить и убедиться в падении**

Run: `.venv/bin/python -m pytest tests/test_model_equipment_emulsion.py -q`
Expected: FAIL — параметра `emulsion_truck_code` нет.

- [ ] **Step 3: Добавить машину**

В `logistics.py` рассчитать `emulsion_trips` и `emulsion_shifts` по грузоподъёмности тягача из `bulk_kg` — тем же способом, что и `_szm`. В `equipment.py` добавить строку в `MACHINES`:

```python
    ("emulsion_truck_code", "emulsion_shifts", "COMPONENT_DELIVERY", "EMULSION_TRUCK"),
```

Плановые смены `_machine_lines` берёт из `norm_shifts_per_month` типа техники; ручное значение
из `machine_plan_shifts` перекрывает справочник — оно параметр вкладки, как и плановые смены
станка. В `/model-defaults` состав техники по умолчанию — первая активная запись каждого вида:
СЗМ, доставщик ВМ (Sollers Atlant) и тягач с полуприцепом; сметчик меняет выбор списком.

- [ ] **Step 4: Запустить тесты**

Run: `.venv/bin/python -m pytest tests/test_model_equipment_emulsion.py tests/test_model_engine.py -q`
Expected: PASS

- [ ] **Step 5: Коммит**

```bash
git add cost/model/equipment.py cost/model/logistics.py cost/model/inputs.py frontend/src/pages/economics/ParametersPanel.tsx tests/test_model_equipment_emulsion.py
git commit -m "feat(model): тягач с полуприцепом под эмульсию и ручные плановые смены техники"
```

---

### Task 9: Ручные услуги прогона

**Files:**
- Create: `cost/model/services.py`
- Modify: `cost/model/inputs.py` (`ModelParameters.services`), `cost/model/engine.py`
- Create: `frontend/src/pages/economics/ServicesPanel.tsx`
- Modify: `api/routers/block_economics.py` (маршрут `POST /economics/services/to-reference`)
- Test: `tests/test_model_services.py`, `tests/test_api_services_to_reference.py`

**Interfaces:**
- Produces: `ServiceCharge(name, amount_rub, layer, operation_code, per_shift)` в параметрах; строки затрат с формулой «введено на вкладке»; маршрут переноса услуги в черновик раздела `cost_rules` (разовая сумма — `fixed_rub`) или `unit_fixed_costs` (ежемесячная).

Услуга, введённая руками, остаётся в снимке прогона — смета воспроизводима без справочника. Кнопка «Сохранить в справочник» — отдельное осознанное действие, публикацию ревизии оно не делает.

- [ ] **Step 1: Написать падающий тест**

```python
def test_manual_service_becomes_a_cost_line() -> None:
    context = build_context(
        params=params(services=(ServiceCharge("Проживание и питание", Decimal("120000"), "project_direct", "", False),))
    )
    services.compute(context)
    line = context.lines[0]
    assert line.cost_item_name == "Проживание и питание"
    assert line.amount_rub == Decimal("120000")
    assert line.formula == "введено на вкладке"


def test_per_shift_service_multiplies_by_crew_shifts() -> None:
    context = build_context(
        params=params(services=(ServiceCharge("Предрейсовый медосмотр", Decimal("350"), "project_direct", "BULK_CHARGING_SZM", True),)),
        physical={"szm_shifts": Decimal("4")},
    )
    services.compute(context)
    assert context.lines[0].amount_rub == Decimal("1400")
```

- [ ] **Step 2: Запустить и убедиться в падении**

Run: `.venv/bin/python -m pytest tests/test_model_services.py -q`
Expected: FAIL — модуля `cost.model.services` нет.

- [ ] **Step 3: Написать модуль, панель и маршрут**

Модуль обходит `context.params.services`, для `per_shift=True` умножает на смены операции (по той же таблице `DERIVED_SHIFT_DRIVERS`, что и `labor.py:17`), иначе берёт сумму как есть. Панель — таблица со строками «название / сумма / за смену / слой» и кнопкой «В справочник» у каждой строки. Маршрут `POST /economics/services/to-reference` создаёт запись черновика соответствующего раздела и возвращает её код; повторное нажатие обновляет ту же запись.

- [ ] **Step 4: Запустить тесты**

Run: `.venv/bin/python -m pytest tests/test_model_services.py tests/test_api_services_to_reference.py -q` и `cd frontend && npm test`
Expected: PASS

- [ ] **Step 5: Коммит**

```bash
git add cost/model/services.py cost/model/inputs.py cost/model/engine.py api/routers/block_economics.py frontend/src/pages/economics/ServicesPanel.tsx tests/test_model_services.py tests/test_api_services_to_reference.py
git commit -m "feat(economics): ручные услуги прогона и перенос суммы в справочник"
```

---

### Task 10: Эталонная ревизия справочников

**Files:**
- Create: `scripts/seed_cost_v2_reference.py`
- Test: `tests/test_seed_cost_v2_reference.py`

**Interfaces:**
- Produces: скрипт наполняет и публикует ревизию, после которой вкладка считает без предупреждений на демонстрационном паспорте.

Наполняются разделы, которых сегодня нет или в которых нет нужных записей:

- `cost_rules` — доставка ВМ (`vm_tkm`), доставка компонентов (`component_tkm`), забойка (`holes`), комплектация ВМ на складе (`explosive_kg`); ставки материалов сюда не попадают — их считает `cost/model/materials.py`;
- `drilling_conditions` — по записи на каждый станок из `equipment_types` с `kind=DRILL_RIG`: техническая скорость, ресурс коронки, ППУ, штанг, коды материалов оснастки;
- `equipment_types` — СЗМ, доставщик ВМ и тягач эмульсии с грузоподъёмностью, нормой смен, расходом ДТ, режимом ТОиР, стоимостью выпуска на линию и медосмотра за смену;
- `equipment_assets` — первоначальная стоимость и срок службы для каждой машины (иначе `equipment.py:69` предупреждает и не начисляет амортизацию);
- `materials` — проставить `nomenclature_role` существующим 34 позициям (ВВ, НСИ, детонаторы, буровой инструмент);
- `unit_fixed_costs` — СИЗ и охрана труда категории `PPE`;
- `organization_rates` — `salary_basis=NET` (оклады в справочнике заданы «на руки», модель
  доначисляет НДФЛ), ставка НДФЛ, взносы, страхование от НС, резерв отпусков, суточные и
  проживание за человеко-смену — без них `labor.py:150` не считает вахтовые и командировочные.

- [ ] **Step 1: Написать падающий тест**

```python
def test_seeded_revision_computes_block_without_warnings() -> None:
    references = seed(empty_snapshot())
    result = compute_block_economics(demo_snapshot(), demo_params(), references)
    assert result.warnings == ()
    assert result.price_per_m3["full"] > 0
    assert {line.cost_item_code for line in result.lines} >= {
        "MATERIAL_EXPLOSIVE",
        "MATERIAL_NSI_DOWNHOLE",
        "DRILLING_TOOLING_BIT",
        "LABOR_CONTRIBUTIONS",
        "SZM_DEPRECIATION",
    }
```

- [ ] **Step 2: Запустить и убедиться в падении**

Run: `.venv/bin/python -m pytest tests/test_seed_cost_v2_reference.py -q`
Expected: FAIL — скрипта нет.

- [ ] **Step 3: Написать скрипт**

Запуск: `.venv/bin/python scripts/seed_cost_v2_reference.py --organization default --publish`. Скрипт идемпотентен: запись с существующим кодом обновляется, а не дублируется. На проде выполняется тем же способом, что и импорт Cost V1: `docker exec -w /app -e PYTHONPATH=/app blastex-api python scripts/seed_cost_v2_reference.py`.

- [ ] **Step 4: Запустить тесты и прогнать на dev-базе**

Run: `.venv/bin/python -m pytest tests/test_seed_cost_v2_reference.py -q`
Expected: PASS; после прогона на dev-базе вкладка «Экономика блока» показывает ненулевую себестоимость.

- [ ] **Step 5: Коммит**

```bash
git add scripts/seed_cost_v2_reference.py tests/test_seed_cost_v2_reference.py
git commit -m "feat(references): эталонная ревизия справочников для модели блока"
```

---

## Проверка результата

После задач 1–10 на демонстрационном блоке (29 038,86 кг ВВ, 189 скважин, 189 поверхностных НСИ, 30 000 м³):

1. Панель «Номенклатура блока» подставляет ЭВВ, скважинное НСИ по длине, поверхностное и стартовое НСИ, промежуточный детонатор; под каждым — актуальная цена.
2. «Структура затрат» содержит строки ВМ и СИ, бурения с износом оснастки, ФОТ бригады со взносами и резервом отпусков, амортизацию и ТОиР техники, услуги, СИЗ.
3. «Модель сообщает» пусто либо называет ровно ту запись справочника, которой не хватает.
4. «Цена блока» показывает маржинальную и полную себестоимость, цену с ОХР и рентабельностью, с НДС и коридор для торга.
