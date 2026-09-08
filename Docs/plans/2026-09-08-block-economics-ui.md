# Вкладка «Экономика блока»: смета как в Excel — разделы, нормы, варианты рядом

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Привести вкладку к тому, как сметчик читает смету на бумаге: строка показывает норму, цену и сумму; статьи сгруппированы по разделам сметы внутри слоёв; до четырёх вариантов расчёта считаются одновременно и стоят колонками рядом; итог идёт лестницей «производственная → полная → выручка».

**Architecture:** Раздел сметы и количество с ценой становятся полями `CostLine` — их проставляют те же модули домена, что создают строку, поэтому интерфейс ничего не выводит сам. Варианты расчёта — новый маршрут `/block-economics/variants`, считающий список наборов параметров на одной ревизии справочников; страница держит массив параметров и рисует структуру затрат колонками. Правка чисел остаётся там, где данные живут: цены в справочниках, нормы в модели, ручные величины на вкладке.

**Tech Stack:** Python 3.12, FastAPI, Pydantic v2, Decimal-арифметика; React 19 + TypeScript + Vite + vitest.

**Spec:** решения приняты в чате 2026-09-08 по скриншоту рабочей сметы БВР («на производство взрывных работ на объекте …»):
- варианты произвольные, до четырёх, у каждого свой полный набор параметров;
- группировка: слои остаются верхним уровнем, разделы сметы — внутри;
- в таблице сметы только показ; цены правятся в справочнике, нормы — в модели.

## Что в бумажной смете и чего не хватает вкладке

| В смете | Сейчас на вкладке |
|---|---|
| Четыре варианта колонками: БВР/ВР × сухие/обводнённые, неприменимая строка помечена «X» | Один расчёт; сравнение только между сохранёнными прогонами отдельной панелью |
| Строка: наименование · ед. изм. · норма · цена · сумма | Строка: наименование · сумма · ₽/м³; количество и цена спрятаны в текст формулы под кликом |
| Разделы 1.1 ВМ, 1.2 бурение, 2.1 хранение, 2.2 суточные, 2.3 ФОТ, 2.4 ГСМ, 2.5 амортизация, 2.6 общепроизводственные | Три слоя себестоимости; внутри слоя строки идут в порядке добавления |
| Амортизация по единицам техники с инвентарным номером и числом смен | «Амортизация: СЗМ 12 т» без единицы и смен |
| Производственная себестоимость → ОХР 10 % → полная → рентабельность 10 % → выручка без НДС | Маржинальная, полная, с ОХР и рентабельностью, с НДС, коридор для торга |

## Global Constraints

- Ветка `feat/block-economics-ui` от `main`. Задачи 1–4 — один PR (смета: разделы, нормы, итоги), 5–7 — второй (варианты).
- Перед слиянием любого PR — `/code-review`, затем ответ на замечания Codex.
- Нормы живут в `cost/model/`, цены — только в справочниках; поля payload описываются схемами в `cost/v2/schemas/` (`x-unit`, `x-ref`, `title`, `description`).
- Деньги и количества внутри модели — `Decimal`; `float` только в `to_dict()` на границе API.
- Пользователю не показывать JSON и коды там, где есть подпись.
- Тексты, комментарии, коммиты — на русском; коммиты завершаются `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`.
- Проверки: `.venv/bin/python -m pytest -q`; фронт — `cd frontend && npm test` и типы через временный `tsconfig.check.json` (`extends ./tsconfig.app.json`, `include: ["src"]`, `exclude: ["src/**/* 2.*", "src/**/* 3.*", "node_modules"]`, файл не коммитить).
- В рабочем каталоге лежат iCloud-дубликаты « 2»/« 3» — в `git add` только явные пути задачи.

---

## Структура файлов

| Файл | Ответственность |
|---|---|
| `cost/v2/models.py` (изменить) | `EstimateSection`, поля `section`, `quantity`, `unit`, `unit_price_rub` у `CostLine` |
| `cost/model/inputs.py` (изменить) | `ModelContext.add_line` принимает раздел, количество, единицу и цену |
| `cost/model/{materials,drilling,logistics,labor,equipment,unit,services,engine}.py` (изменить) | каждая строка называет свой раздел сметы и, где есть, количество с ценой |
| `cost/v2/schemas/costs.py` (изменить) | `estimate_section` у правила затрат |
| `api/schemas/block_economics.py` (изменить) | поля строки в `CostLineSchema`; `VariantsRequest`, `VariantsResponse` |
| `api/routers/block_economics.py` (изменить) | маршрут `POST /economics/block-economics/variants` |
| `frontend/src/pages/economics/estimateSections.ts` (+ `.test.ts`, создать) | порядок и подписи разделов, сборка дерева «слой → раздел → строки» |
| `frontend/src/pages/economics/CostStructure.tsx` (изменить) | разделы внутри слоёв, колонки нормы и цены, колонки вариантов |
| `frontend/src/pages/economics/PricePanel.tsx` (изменить) | лестница «производственная → полная → выручка» |
| `frontend/src/pages/economics/variants.ts` (+ `.test.ts`, создать) | состояние вариантов: добавить, дублировать, удалить, переименовать |
| `frontend/src/pages/economics/VariantTabs.tsx` (создать) | переключатель редактируемого варианта |
| `frontend/src/pages/economics/BlockEconomicsPage.tsx` (изменить) | массив параметров вместо одного набора, пересчёт вариантов одним запросом |
| `tests/test_model_estimate_sections.py`, `tests/test_api_variants.py` (создать) | тесты раздела сметы и маршрута вариантов |

---

### Task 1: Раздел сметы у строки затрат

**Files:**
- Modify: `cost/v2/models.py`, `cost/model/inputs.py`, все модули `cost/model/*.py`, `cost/v2/schemas/costs.py`
- Test: `tests/test_model_estimate_sections.py`

**Interfaces:**
- Produces: `EstimateSection` — `Literal["EXPLOSIVES", "DRILLING", "VM_LOGISTICS", "PER_DIEM", "LABOR", "FUEL", "DEPRECIATION", "OVERHEAD"]`; `CostLine.section: EstimateSection`; `CostRulePayload.estimate_section`.

Раздел — свойство статьи, как и слой: его знает тот модуль, который строку создаёт. Правило затрат называет раздел полем схемы, по умолчанию `OVERHEAD`.

- [ ] **Step 1: Написать падающий тест**

```python
def test_every_line_names_its_estimate_section() -> None:
    result = compute_block_economics(fx.snapshot(), fx.parameters(nomenclature=NOMENCLATURE), fx.references())

    sections = {line.cost_item_code: line.section for line in result.lines}
    assert sections["MATERIAL_EXPLOSIVE"] == "EXPLOSIVES"
    assert sections["DRILL_TOOLING"] == "DRILLING"
    assert sections["VM_DELIVERY"] == "VM_LOGISTICS"
    assert sections["LABOR_POS_BLASTER"] == "LABOR"
    assert sections["LABOR_PER_DIEM"] == "PER_DIEM"
    assert sections["SZM_FUEL"] == "FUEL"
    assert sections["SZM_DEPRECIATION"] == "DEPRECIATION"
    assert sections["UNIT_PPE"] == "OVERHEAD"
    assert all(line.section for line in result.lines)


def test_cost_rule_names_its_section_and_falls_back_to_overhead() -> None:
    rule = fx.item("RULE_X", "Прочее", {"operation_code": "STEMMING", "driver": "holes", "rate_rub": "60"})
    stemming = fx.item("RULE_S", "Забойка", {
        "operation_code": "STEMMING", "driver": "holes", "rate_rub": "60", "estimate_section": "EXPLOSIVES",
    })
    result = compute_block_economics(
        fx.snapshot(), fx.parameters(), fx.references(cost_rules=(rule, stemming))
    )
    by_code = {line.cost_item_code: line.section for line in result.lines}
    assert by_code["RULE_X"] == "OVERHEAD"
    assert by_code["RULE_S"] == "EXPLOSIVES"
```

- [ ] **Step 2: Запустить и убедиться, что падает**

Run: `.venv/bin/python -m pytest tests/test_model_estimate_sections.py -q`
Expected: FAIL — у `CostLine` нет поля `section`.

- [ ] **Step 3: Добавить раздел в строку и проставить его в модулях**

```python
# cost/v2/models.py
EstimateSection = Literal[
    "EXPLOSIVES", "DRILLING", "VM_LOGISTICS", "PER_DIEM", "LABOR", "FUEL", "DEPRECIATION", "OVERHEAD",
]


@dataclass(frozen=True)
class CostLine:
    ...
    # Раздел бумажной сметы: сметчик ищет строку глазами по нему, а не по слою.
    section: EstimateSection = "OVERHEAD"
```

`ModelContext.add_line` получает параметр `section` и передаёт его в `CostLine`. Дальше по модулям: `materials` — `EXPLOSIVES`; `drilling` — `DRILLING` для всех строк станка, включая его амортизацию (в смете бурение показано одной строкой стоимости метра); `logistics` — `VM_LOGISTICS` для доставки и мобилизации, `FUEL` для ДТ машин; `labor` — `LABOR`, а суточные и проживание `PER_DIEM`; `equipment` — `DEPRECIATION` для амортизации и страховки, `OVERHEAD` для ТОиР, запчастей и допуска к работе; `unit` — `OVERHEAD`; `services` — раздел из самой услуги (по умолчанию `OVERHEAD`).

- [ ] **Step 4: Запустить тесты**

Run: `.venv/bin/python -m pytest -q`
Expected: PASS

- [ ] **Step 5: Коммит**

```bash
git add cost/v2/models.py cost/model/ cost/v2/schemas/costs.py tests/test_model_estimate_sections.py
git commit -m "feat(model): раздел бумажной сметы у строки затрат"
```

---

### Task 2: Количество, единица и цена в строке

**Files:**
- Modify: `cost/v2/models.py`, `cost/model/inputs.py`, `cost/model/{materials,drilling,logistics,labor,equipment}.py`
- Test: `tests/test_model_estimate_sections.py`

**Interfaces:**
- Produces: `CostLine.quantity: Decimal | None`, `CostLine.unit: str`, `CostLine.unit_price_rub: Decimal | None`.

Формула остаётся: она объясняет вывод. Но количество и цену интерфейс должен получать числами, а не разбирать текст.

- [ ] **Step 1: Написать падающий тест**

```python
def test_material_line_carries_quantity_unit_and_price() -> None:
    ctx = context(nomenclature={"EXPLOSIVE": "MAT_EVERSIN"}, explosive_kg="29038.86")
    run(ctx)

    line = next(row for row in ctx.lines if row.cost_item_code == "MATERIAL_EXPLOSIVE")
    assert line.quantity == Decimal("29038.86")
    assert line.unit == "кг"
    assert line.unit_price_rub == Decimal("48.9")
    assert line.amount_rub == line.quantity * line.unit_price_rub


def test_labor_line_counts_people_not_money() -> None:
    """У ФОТ единица — человеко-смены: цена за единицу теряет смысл, её нет."""

    result = compute_block_economics(fx.snapshot(), fx.parameters(), fx.references())
    line = next(row for row in result.lines if row.cost_item_code == "LABOR_POS_BLASTER")
    assert line.unit == "чел·см"
    assert line.unit_price_rub is None
```

- [ ] **Step 2: Запустить и убедиться в падении**

Run: `.venv/bin/python -m pytest tests/test_model_estimate_sections.py -k quantity -q`
Expected: FAIL — полей нет.

- [ ] **Step 3: Заполнить поля там, где количество осмысленно**

Материалы — количество в единицах цены и сама цена (уже вычислены в `_role_line`). Бурение — погонные метры и цена метра из `drilling_rub_per_m`. Оснастка — штуки. ДТ — литры и цена литра. Амортизация и ТОиР — смены и ставка за смену. ФОТ — человеко-смены без цены. Постоянные юнита — доля блока без единицы.

- [ ] **Step 4: Запустить тесты**

Run: `.venv/bin/python -m pytest -q`
Expected: PASS

- [ ] **Step 5: Коммит**

```bash
git add cost/v2/models.py cost/model/ tests/test_model_estimate_sections.py
git commit -m "feat(model): количество, единица и цена в строке затрат"
```

---

### Task 3: Разделы и нормы в структуре затрат

**Files:**
- Create: `frontend/src/pages/economics/estimateSections.ts`, `estimateSections.test.ts`
- Modify: `frontend/src/pages/economics/CostStructure.tsx`, `frontend/src/types/blockEconomics.ts`, `frontend/src/styles.css`

**Interfaces:**
- Consumes: `BlockCostLine.section`, `.quantity`, `.unit`, `.unit_price_rub`.
- Produces: `groupByLayerAndSection(lines) -> LayerGroup[]`, где `LayerGroup = { layer, label, hint, total, sections: SectionGroup[] }`.

Слой остаётся верхним уровнем — от него считается маржинальная цена. Раздел — второй уровень, с нумерацией как в смете.

- [ ] **Step 1: Написать падающий тест**

```typescript
describe("группировка сметы", () => {
  it("складывает строки в разделы внутри слоёв и держит порядок сметы", () => {
    const groups = groupByLayerAndSection([
      line("MATERIAL_EXPLOSIVE", "variable", "EXPLOSIVES", 100),
      line("SZM_FUEL", "variable", "FUEL", 10),
      line("DRILL_TOOLING", "variable", "DRILLING", 50),
      line("LABOR_X", "project_direct", "LABOR", 70),
    ]);

    expect(groups.map((g) => g.layer)).toEqual(["variable", "project_direct"]);
    expect(groups[0].sections.map((s) => s.label)).toEqual([
      "Расходы на ВМ", "Расходы на бурение", "ГСМ",
    ]);
    expect(groups[0].total).toBe(160);
    expect(groups[0].sections[0].total).toBe(100);
  });

  it("пустых разделов не показывает", () => {
    const groups = groupByLayerAndSection([line("LABOR_X", "project_direct", "LABOR", 70)]);
    expect(groups[0].sections).toHaveLength(1);
  });
});
```

- [ ] **Step 2: Запустить и убедиться в падении**

Run: `cd frontend && npx vitest run src/pages/economics/estimateSections.test.ts`
Expected: FAIL — модуля нет.

- [ ] **Step 3: Написать модуль и переписать таблицу**

Порядок разделов — как в смете: `EXPLOSIVES` (Расходы на ВМ), `DRILLING` (Расходы на бурение), `VM_LOGISTICS` (Хранение, производство и доставка ВМ), `PER_DIEM` (Суточные, вахтовые, проживание), `LABOR` (Фонд оплаты труда), `FUEL` (ГСМ), `DEPRECIATION` (Амортизация), `OVERHEAD` (Общепроизводственные затраты).

Строка получает колонки: наименование · ед. изм. · количество · цена · сумма · ₽/м³. Пустые ячейки — прочерк, а не ноль: в смете «X» означает «здесь этого нет». Формула остаётся под кликом.

- [ ] **Step 4: Запустить проверки**

Run: `cd frontend && npm test` и `npx tsc -p tsconfig.check.json --noEmit`
Expected: PASS

- [ ] **Step 5: Коммит**

```bash
git add frontend/src/pages/economics/estimateSections.ts frontend/src/pages/economics/estimateSections.test.ts frontend/src/pages/economics/CostStructure.tsx frontend/src/types/blockEconomics.ts frontend/src/styles.css
git commit -m "feat(economics): разделы сметы и нормы в структуре затрат"
```

---

### Task 4: Лестница итогов как в смете

**Files:**
- Modify: `frontend/src/pages/economics/PricePanel.tsx`, `frontend/src/styles.css`

**Interfaces:**
- Consumes: `economics.price_per_m3`, `economics.markup` (`full_cost_rub`, `overhead_rub`, `margin_rub`, `price_rub`, `vat_rub`).

Сметчик читает итог сверху вниз: производственная себестоимость, ОХР процентом, полная, рентабельность процентом, выручка без НДС. Наши «маржинальная» и «коридор для торга» остаются рядом — это то, чего в бумаге нет, и ради чего вкладку делали.

- [ ] **Step 1: Переписать панель**

```tsx
const LADDER = [
  { label: "Производственная себестоимость", value: markup.full_cost_rub, perM3: prices.full },
  { label: `Общехозяйственные расходы, ${percent(markup.overhead_rate)}`, value: markup.overhead_rub },
  { label: "Полная себестоимость", value: markup.full_cost_rub + markup.overhead_rub, strong: true },
  { label: `Рентабельность, ${percent(markup.target_margin_rate)}`, value: markup.margin_rub },
  { label: "Выручка без НДС", value: markup.price_rub, perM3: prices.with_margin, strong: true },
];
```

Маржинальная себестоимость и коридор для торга — отдельной парой плашек с подписью «пол цены: ниже блок убыточен сам по себе».

- [ ] **Step 2: Проверить в браузере**

Открыть вкладку на dev, сверить лестницу с сохранённым прогоном: производственная + ОХР = полная, полная + рентабельность = выручка.

- [ ] **Step 3: Коммит**

```bash
git add frontend/src/pages/economics/PricePanel.tsx frontend/src/styles.css
git commit -m "feat(economics): итоги вкладки лестницей бумажной сметы"
```

---

### Task 5: Расчёт вариантов одним запросом

**Files:**
- Modify: `api/schemas/block_economics.py`, `api/routers/block_economics.py`
- Test: `tests/test_api_variants.py`

**Interfaces:**
- Produces: `POST /economics/block-economics/variants` с телом `{technical_passport_id, variants: [{name, parameters}]}` → `{reference_revision_id, variants: [{name, economics}]}`.

Один запрос, а не четыре: все варианты считаются на одной ревизии справочников, иначе колонки разъедутся, если коллега опубликует ревизию между запросами.

- [ ] **Step 1: Написать падающий тест**

```python
def test_variants_are_computed_on_one_revision(client) -> None:
    test_client, _, passport_id = client
    response = test_client.post(
        "/api/v1/economics/block-economics/variants",
        json={
            "technical_passport_id": passport_id,
            "variants": [
                {"name": "БВР сухие", "parameters": _parameters(passport_id, nomenclature={"EXPLOSIVE": "MAT_ANFO"})["parameters"]},
                {"name": "БВР обводнённые", "parameters": _parameters(passport_id, nomenclature={"EXPLOSIVE": "MAT_EVERSIN"})["parameters"]},
            ],
        },
    )

    body = response.json()
    assert [v["name"] for v in body["variants"]] == ["БВР сухие", "БВР обводнённые"]
    dry, wet = (v["economics"] for v in body["variants"])
    assert dry["price_per_m3"]["full"] < wet["price_per_m3"]["full"]
    assert body["reference_revision_id"]
    assert all(v["economics"]["reference_revision_id"] == body["reference_revision_id"] for v in body["variants"])


def test_variants_are_limited_to_four(client) -> None:
    test_client, _, passport_id = client
    one = {"name": "В", "parameters": _parameters(passport_id)["parameters"]}
    response = test_client.post(
        "/api/v1/economics/block-economics/variants",
        json={"technical_passport_id": passport_id, "variants": [one] * 5},
    )
    assert response.status_code == 422
```

- [ ] **Step 2: Запустить и убедиться в падении**

Run: `.venv/bin/python -m pytest tests/test_api_variants.py -q`
Expected: FAIL — маршрута нет.

- [ ] **Step 3: Добавить схемы и маршрут**

```python
class VariantRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., min_length=1, max_length=120)
    parameters: ModelParametersSchema


class VariantsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    technical_passport_id: str = Field(..., min_length=1)
    # Четыре колонки — предел читаемой таблицы и предел бумажной сметы.
    variants: list[VariantRequest] = Field(..., min_length=1, max_length=4)
```

Маршрут грузит паспорт и ревизию один раз, затем считает каждый вариант тем же `_compute`.

- [ ] **Step 4: Запустить тесты**

Run: `.venv/bin/python -m pytest -q`
Expected: PASS

- [ ] **Step 5: Коммит**

```bash
git add api/schemas/block_economics.py api/routers/block_economics.py tests/test_api_variants.py
git commit -m "feat(api): расчёт нескольких вариантов блока одним запросом"
```

---

### Task 6: Варианты на вкладке

**Files:**
- Create: `frontend/src/pages/economics/variants.ts`, `variants.test.ts`, `VariantTabs.tsx`
- Modify: `frontend/src/pages/economics/BlockEconomicsPage.tsx`, `CostStructure.tsx`, `frontend/src/api/endpoints.ts`, `frontend/src/types/blockEconomics.ts`

**Interfaces:**
- Produces: `Variant = { id, name, parameters }`; `addVariant`, `duplicateVariant`, `removeVariant`, `renameVariant`, `patchVariant` — чистые функции над массивом.

Панели параметров и номенклатуры правят активный вариант; структура затрат показывает все колонками. Новый вариант создаётся копией активного — так сметчик меняет одно поле и сравнивает.

- [ ] **Step 1: Написать падающий тест**

```typescript
describe("варианты расчёта", () => {
  it("дублирует активный вариант с новым именем и своим набором параметров", () => {
    const [base] = makeVariants();
    const next = duplicateVariant([base], base.id);

    expect(next).toHaveLength(2);
    expect(next[1].name).toBe("Вариант 2");
    expect(next[1].id).not.toBe(base.id);
    expect(next[1].parameters).toEqual(base.parameters);
    expect(next[1].parameters).not.toBe(base.parameters);
  });

  it("не даёт больше четырёх", () => {
    const four = [1, 2, 3, 4].map((n) => ({ ...makeVariants()[0], id: `v${n}` }));
    expect(duplicateVariant(four, "v1")).toHaveLength(4);
  });

  it("последний вариант не удаляется", () => {
    const [base] = makeVariants();
    expect(removeVariant([base], base.id)).toHaveLength(1);
  });
});
```

- [ ] **Step 2: Запустить и убедиться в падении**

Run: `cd frontend && npx vitest run src/pages/economics/variants.test.ts`
Expected: FAIL — модуля нет.

- [ ] **Step 3: Состояние, вкладки и колонки**

`VariantTabs` — строка вкладок с именем варианта (переименование по двойному клику), кнопкой «Дублировать» и крестиком. Страница держит `variants: Variant[]` и `activeId`; пересчёт по задержке отправляет весь массив одним запросом. `CostStructure` получает `results: Array<{ name, economics }>` и рисует колонку на вариант; строка, которой в варианте нет, показывает прочерк. Активная колонка подсвечена — видно, какой набор параметров правится.

- [ ] **Step 4: Проверить в браузере**

На dev собрать два варианта — «сухие» с гранулитом и «обводнённые» с эмульсией — убедиться, что колонки различаются ценой ВВ, а остальные строки совпадают.

- [ ] **Step 5: Коммит**

```bash
git add frontend/src/pages/economics/variants.ts frontend/src/pages/economics/variants.test.ts frontend/src/pages/economics/VariantTabs.tsx frontend/src/pages/economics/BlockEconomicsPage.tsx frontend/src/pages/economics/CostStructure.tsx frontend/src/api/endpoints.ts frontend/src/types/blockEconomics.ts
git commit -m "feat(economics): до четырёх вариантов расчёта колонками рядом"
```

---

### Task 7: Амортизация по единицам техники

**Files:**
- Modify: `cost/model/equipment.py`, `cost/model/drilling.py`
- Test: `tests/test_model_equipment_emulsion.py`

**Interfaces:**
- Consumes: `equipment_assets` — `inventory_number`, `serial_number`.

В смете амортизация названа единицей с инвентарным номером и числом смен: «Специализированный автомобиль ГАЗ 5796М1 (VIN ***5212) · 2,00 смены · 4 984,32 ₽/смена». У нас — тип техники без единицы.

- [ ] **Step 1: Написать падающий тест**

```python
def test_depreciation_names_the_unit_and_its_shifts() -> None:
    assets = (fx.item("ASSET_SZM", "СЗМ инв. 002", {
        "equipment_type_code": "SZM_12T", "inventory_number": "002",
        "initial_cost_rub": "12000000", "useful_life_months": "60",
    }),)
    context = _context()
    logistics.compute(context)
    equipment.compute(context)

    line = _line(context, "SZM_DEPRECIATION")
    assert "инв. 002" in line.cost_item_name
    assert line.quantity == Decimal("4")
    assert line.unit == "см"
```

- [ ] **Step 2: Запустить и убедиться в падении**

Run: `.venv/bin/python -m pytest tests/test_model_equipment_emulsion.py -k depreciation -q`
Expected: FAIL — в названии нет инвентарного номера.

- [ ] **Step 3: Назвать строку единицей техники**

Название строки — имя основного средства, если оно есть, иначе имя типа. Количество — смены на блок, цена за единицу — амортизация за смену.

- [ ] **Step 4: Запустить тесты**

Run: `.venv/bin/python -m pytest -q`
Expected: PASS

- [ ] **Step 5: Коммит**

```bash
git add cost/model/equipment.py cost/model/drilling.py tests/test_model_equipment_emulsion.py
git commit -m "feat(model): амортизация названа единицей техники и её сменами"
```

---

## Чего этот план намеренно не делает

**Не разрешает правку цен и норм в таблице сметы.** Решение чата: цены живут в справочниках, нормы — в модели, смета остаётся воспроизводимой. В строке будет ссылка «править в справочнике».

**Не сводит бурение в одну строку**, как в бумаге («Потребность в бурении · 14,1832 · 1 009 ₽»). У нас метр разложен на оснастку, ДТ, запчасти и амортизацию, и это разложение — ценность вкладки; в разделе «Расходы на бурение» строки останутся, а итог раздела даст ту самую цифру.

**Не трогает `RunsCompare`.** Варианты — рабочий инструмент «здесь и сейчас», сравнение прогонов — история сохранённых сценариев. После задачи 6 стоит посмотреть, нужна ли панель в прежнем виде.
