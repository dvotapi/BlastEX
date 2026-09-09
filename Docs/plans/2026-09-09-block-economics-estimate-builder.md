# Экономика блока: смета-конструктор — план реализации

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Вкладка «Экономика блока» становится интерактивной сметой-конструктором: сметчик собирает производственную схему (ВМ и СИ, режим бурения, техника, бригада, услуги) из опубликованных справочников прямо в строках иерархической сметы, видит происхождение каждого числа, а справа — липкую структуру себестоимости кольцевой диаграммой и лестницу формирования цены.

**Architecture:** Расчёт остаётся на бэкенде (`cost/model/`, маршрут `/block-economics/variants`); фронт лишь выбирает коды из каталогов `model-defaults` и показывает строки `CostLine`. Бэкенд получает три минимальных дополнения: происхождение количества и цены у строки (`quantity_origin`, `price_origin`), выбор тарифа субподряда с ручной ставкой, и точечная публикация тарифа в справочник по образцу `services/to-reference`. Страница разбивается на компоненты `pages/economics/{estimate,sections,drilling,sidebar}`; чистые модули (группировка строк в инженерные разделы, геометрия диаграммы, состояние черновика) тестируются как функции, взаимодействия — компонентными тестами в jsdom.

**Tech Stack:** Python 3.12, FastAPI, Pydantic v2, Decimal; React 19 + TypeScript + Vite 7, vitest 3 (добавляются dev-зависимости `jsdom`, `@testing-library/react`, `@testing-library/user-event`), обычный CSS в `frontend/src/styles.css` (новый файл `frontend/src/styles/economics.css`), диаграмма — inline SVG без библиотек.

**Spec:** постановка задачи — сообщение владельца от 2026-09-09 «Redesign the Block Economics UI into an Interactive Estimate Builder»; визуальный референс — `Docs/design/economics_block_concept.png`; доменная модель — `Docs/ADR-001-economics-model.md`, `Docs/COST_MODEL.md`. Решения, принятые при составлении плана, — в разделе «Решения и допущения» ниже.

## Global Constraints

- Ветки от `main`: `feat/block-economics-origin-api` (задачи 1–3, бэкенд, один PR) и `feat/block-economics-estimate-builder` (задачи 4–12, фронт, один PR; при большом объёме — разбить после задачи 8). Перед слиянием любого PR — `/code-review`, затем ответ на замечания.
- Нормы живут в `cost/model/`, цены — только в справочниках; поля payload описываются схемами в `cost/v2/schemas/` (`x-unit`, `x-ref`, `title`, `description`). Пользователю не показывать JSON и коды там, где есть подпись.
- Формулы себестоимости в React не дублируются: фронт складывает только уже посчитанные `amount_rub` в итоги разделов и делит на `block_volume_m3` для колонки ₽/м³ (это оформление, как в `CostStructure.tsx` сейчас).
- Сохранённые прогоны `economics_runs` неизменяемы: сохранение всегда создаёт новый прогон; UPDATE/DELETE не добавлять.
- Новый тариф субподряда попадает в справочник только по явной кнопке «Сохранить тариф в справочник» (`require_reference_editor`), никогда — автоматически при правке ставки.
- Величины паспорта (объём, погонаж, скважины, масса ВВ, НСИ) — только для чтения; ручной ввод только там, где его допускает модель (`electric_detonators_qty`, `shifts_per_block`, `headcount`, `machine_plan_shifts`, `rig_plan_shifts`, `subcontract_rate_rub`, надбавки).
- Никаких новых runtime-зависимостей; из dev-зависимостей только три названные выше. Существующие тесты `*.test.ts` остаются в окружении `node`; компонентные тесты — файлы `*.test.tsx` с `// @vitest-environment jsdom`.
- Все существующие маршруты и возможности сохраняются: варианты колонками (до 4), чувствительность, сравнение прогонов, перенос услуги в правила затрат, выгрузка xlsx, вкладка «Экономика юнита» и страница «Бурение».
- Тексты интерфейса, комментарии, коммиты — на русском; коммиты `feat(...)`/`fix(...)` с трейлером `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`. В рабочем каталоге есть iCloud-дубликаты « 2»/« 3» — `git add` только по явным путям.
- Проверки: бэкенд `.venv/bin/python -m pytest -q`; фронт `cd frontend && npm test` и `npm run build` (`tsc -b && vite build`). Дубликаты « 2.tsx» в `tsc -b` не попадают, потому что не импортируются, но `tsconfig.app.json` их включает — при ошибках типов в дубликатах использовать временный `tsconfig.check.json` с `exclude: ["src/**/* 2.*", "src/**/* 3.*"]` (не коммитить).

---

## Что уже есть (по итогам разведки)

| Требование постановки | Состояние в репозитории |
| --- | --- |
| Пересчёт по параметрам, до 4 вариантов, debounce 300 мс | `BlockEconomicsPage.tsx` + `POST /block-economics/variants` — есть |
| Выбор номенклатуры ВМ/СИ из справочника с ценой и количеством из паспорта | `ModelDefaults.nomenclature[role]: MaterialOption[]` (цена, единица, количество, `quantity_label`) — есть; выбор через `<select>` без поиска |
| Бригада: шаблон пакета `crew_templates`, численность, смены | `crew: CrewMemberInput[]`, `CrewEditor.tsx` — есть; норматив показывается плейсхолдером, а не бейджем |
| Техника: станок, СЗМ, доставщик, тягач эмульсии; плановые смены | `rig_code`, `szm_code`, `delivery_truck_code`, `emulsion_truck_code`, `machine_plan_shifts` — есть; смены на блок модель выводит из драйверов (`rig_shifts`, `szm_shifts`, …) |
| Бурение своими силами: цена метра с происхождением нормы | `natural.values.drilling_rub_per_m` и `natural.lineage.drilling_condition`, панель `DrillingBreakdown.tsx` — есть |
| Бурение субподрядом | `drilling_executor="SUBCONTRACTOR"`; модель берёт **первую** запись `subcontract_rates` по операции — выбора подрядчика/тарифа и ручной ставки **нет** |
| Сохранение тарифа в справочник | нет; есть образец `POST /economics/services/to-reference` (публикует новую ревизию с одной записью) |
| Происхождение значений | `natural.lineage` по драйверам — есть; у строки `CostLine` поля происхождения **нет** |
| Лестница цены ОХР → рентабельность → НДС | `markup` и `price_per_m3` — есть (`PricePanel.tsx`) |
| Сценарии: сохранить, список, сравнение, xlsx | `POST/GET /runs`, `compare`, `export.xlsx` — есть; «дублировать» — дублирование варианта; индикатора «не сохранено» нет |
| Чувствительность | `SensitivityTable.tsx` — есть |
| Диаграмма структуры | библиотек графиков в проекте нет; рисуется inline SVG |
| Компонентные тесты | DOM-окружения нет (vitest `environment: node`, только `*.test.ts`) |
| Страница «Бурение» (`/cost/drilling-unit`) | калькулятор Cost V1 на снимке рабочего пространства, с экономикой блока не связан и считает по другим справочникам |

## Решения и допущения

1. **«Расчёт бурения» для режима «Собственными силами» — это модель `cost/model/drilling.py`**, а не страница «Бурение» (`/cost/drilling-unit`). Цена метра уже приходит в `natural.values.drilling_rub_per_m` с происхождением нормы; второй формулы не появляется. Бейдж — «РАСЧЁТ БУРЕНИЯ», кнопка «Открыть расчёт бурения →» раскрывает существующий `DrillingBreakdown` в выдвижной панели на этой же странице. Рядом — вторая ссылка «Перейти к расчёту бурения (Бурение) →», переключающая на существующую страницу «Бурение» (`DrillingPage`, калькулятор Cost V1): это отдельный инструмент оценки стоимости метра для расчётов вне паспорта, числа между ними не синхронизируются — переход навигационный, подтверждено владельцем (см. задачи 7 и 9).
2. **Инженерные разделы сметы строятся из `section`, `layer` и префикса `cost_item_code` строки** (чистая функция `estimateModel.ts`), без изменения бэкенда: ВМ ← `EXPLOSIVES`; Бурение ← `DRILLING`; Персонал ← `LABOR`, `PER_DIEM`; Техника ← `DEPRECIATION` и строки с кодами `SZM_*`, `VM_TRUCK_*`, `EMULSION_TRUCK_*`; ГСМ ← `FUEL`; Производственные услуги ← `VM_LOGISTICS` и ручные услуги вкладки (`services` с кодом `service_code(name)`); Постоянные и общепроизводственные ← всё остальное (`OVERHEAD`, слои `production` и `full`). Бумажная группировка «слой → раздел» остаётся на вкладке «Структура затрат».
3. **Происхождение — поле строки, а не догадка фронта.** `CostLine` получает `quantity_origin` и `price_origin` из перечисления `PASSPORT | CALC | REFERENCE | NORM | MANUAL | ""`, их проставляет модуль, создавший строку. Фронт рисует бейджи только по этим полям и по `natural.lineage`; ничего не выдумывает.
4. **Сценарии.** «Сценарий» в шапке — это сохранённый прогон либо черновик. Селектор показывает черновики (локальные варианты) и сохранённые прогоны паспорта; выбор прогона открывает его параметры новым черновиком «из сценария N». Черновик «грязный», если параметры отличаются от исходного прогона (или он никогда не сохранялся) — плашка «Черновик · не сохранено». «Сохранить» создаёт новый прогон; «Дублировать» — дублирует активный черновик (существующая `duplicateVariant`); «XLSX» доступна для сохранённого прогона (существующий `runs/{id}/export.xlsx`), для грязного черновика — недоступна с подсказкой «Сначала сохраните сценарий».
5. **Техника.** Модель знает четыре роли техники (станок, СЗМ, доставщик ВМ, тягач эмульсии) и выводит их смены на блок сама. Раздел «Техника и оборудование» — по строке на роль: выбор единицы из каталога, смены на блок (`РАСЧЁТ`, из `natural.values`), плановые смены в месяц (`НОРМАТИВ`/`РУЧНОЙ`), итог по строкам техники. «+ Добавить технику» предлагает роли, у которых единица ещё не выбрана; произвольного списка техники модель не поддерживает — это ограничение фиксируется в документации.
6. **Тесты взаимодействий требуют DOM.** Добавляются dev-зависимости `jsdom`, `@testing-library/react`, `@testing-library/user-event`; `vitest.config.ts` включает `src/**/*.test.tsx`, окружение задаётся по файлу. Существующие тесты не меняются.
7. **Диаграмма** — inline SVG (`<path>` по дугам), данные дублируются текстовой легендой и таблицей `<table class="sr-only">` для доступности.
8. Постановка называет папку `docs/design/`; в репозитории она `Docs/design/` (регистр файловой системы macOS скрывает разницу) — используется существующая.

## Решения владельца (2026-09-09)

- **Ссылка на «Бурение» нужна.** `OwnDrillingEditor` получает вторую ссылку «Перейти к расчёту бурения (Бурение) →» рядом с «Открыть расчёт бурения →»; клик переключает страницу на `DrillingPage` без переноса чисел (см. решение 1, задачи 7 и 9).
- **Подрядчики — `counterparties` с ролью `SUBCONTRACTOR`.** Пустой список — тариф вводится вручную, подрядчик «не указан» (уже заложено в задаче 7, `SubcontractDrillingEditor`).
- **Ставка в разделе «Персонал» — оклад в месяц из `labor_rates` с бейджем «Справочник»**, сумма строки — из модели (уже заложено в задаче 7, `LaborSection`).

---

## Структура файлов

### Бэкенд

| Файл | Ответственность |
| --- | --- |
| `cost/v2/models.py` (изменить) | `ValueOrigin`, поля `quantity_origin`, `price_origin` у `CostLine` и в `to_dict` |
| `cost/model/inputs.py` (изменить) | `ModelContext.add_line` принимает происхождения; `ModelParameters.subcontract_rate_code`, `subcontract_rate_rub` |
| `cost/model/{materials,drilling,labor,equipment,logistics,services,unit}.py` (изменить) | каждая строка называет происхождение количества и цены |
| `cost/model/drilling.py` (изменить) | `_subcontract_lines`: выбранный тариф, ручная ставка, происхождение |
| `api/schemas/block_economics.py` (изменить) | поля происхождения в `CostLineSchema`; параметры субподряда; каталоги `subcontract_rates`, `counterparties`; `positions` с окладом и нормой смен; `SubcontractRateToReferenceRequest/Response` |
| `api/routers/block_economics.py` (изменить) | каталоги в `model-defaults`; `POST /economics/subcontract-rates/to-reference` |
| `tests/test_model_origins.py`, `tests/test_model_drilling.py`, `tests/test_api_block_economics.py` (создать/дополнить) | тесты происхождения, выбора тарифа, публикации тарифа |

### Фронтенд (`frontend/src/pages/economics/`)

| Файл | Ответственность |
| --- | --- |
| `BlockEconomicsPage.tsx` (переписать, ≤ 250 строк) | загрузка, состояние черновиков, пересчёт, раскладка «шапка · рабочая область · сайдбар»; вся вёрстка разделов — в дочерних компонентах |
| `EconomicsHeader.tsx` (создать) | заголовок, контекст, селектор сценария, «Сохранить», «Дублировать», «XLSX», индикатор черновика |
| `PassportStrip.tsx` (изменить) | компактная полоса паспорта без поля имени сценария и кнопки сохранения (они уходят в шапку) |
| `EconomicsTabs.tsx` (создать) | вкладки «Смета · Структура затрат · Ресурсы · Чувствительность · Сравнение сценариев · История» |
| `estimateModel.ts` + `.test.ts` (создать) | инженерные разделы из `BlockCostLine[]`: коды, подписи, строки, итоги, доли, ₽/м³ |
| `origin.ts` + `.test.ts` (создать) | подписи и классы бейджей происхождения; происхождение строк бригады и техники из параметров |
| `scenario.ts` + `.test.ts` (создать) | черновик из прогона, признак «грязный», подпись селектора |
| `donut.ts` + `.test.ts` (создать) | сегменты кольца: доли, дуги SVG, цвета разделов |
| `estimate/OriginBadge.tsx` (создать) | бейдж «ПАСПОРТ / РАСЧЁТ / СПРАВОЧНИК / НОРМАТИВ / РУЧНОЙ / РАСЧЁТ БУРЕНИЯ» |
| `estimate/CatalogSelect.tsx` + `.test.tsx` (создать) | комбобокс с поиском: имя, цена, единица; клавиатура; `aria-*` |
| `estimate/EstimateBuilder.tsx` (создать) | таблица сметы: липкая шапка колонок, «Развернуть всё / Свернуть всё», порядок разделов |
| `estimate/EstimateSection.tsx` (создать) | раскрывающийся раздел: номер, название, итог, ₽/м³, %; содержимое — редактор раздела или строки |
| `estimate/EstimateLine.tsx` (создать) | строка сметы: №, статья, бейдж, кол-во, ед., цена, сумма, ₽/м³, %, меню «⋯» |
| `estimate/RowMenu.tsx` (создать) | меню строки: «Формула», «Убрать», «Сбросить к нормативу» |
| `sections/ExplosivesSection.tsx` (создать) | строки по ролям номенклатуры с `CatalogSelect`; «+ Добавить материал» |
| `sections/DrillingSection.tsx` (создать) | переключатель режима; `drilling/OwnDrillingEditor.tsx`, `drilling/SubcontractDrillingEditor.tsx`, `drilling/DrillingDrawer.tsx` |
| `sections/LaborSection.tsx` (создать) | конструктор бригады, бейджи НОРМАТИВ/РУЧНОЙ, «+ Добавить должность» |
| `sections/EquipmentSection.tsx` (создать) | строки по ролям техники, плановые смены, «+ Добавить технику» |
| `sections/FuelSection.tsx`, `sections/ServicesSection.tsx`, `sections/FixedCostsSection.tsx` (создать) | строки только для чтения; услуги — с существующим `ServicesPanel` внутри |
| `sidebar/CostStructureDonut.tsx` (создать) | кольцо + легенда; hover, клик → раздел |
| `sidebar/PriceFormation.tsx` (создать) | лестница «Себестоимость → ОХР → … → Цена с НДС» |
| `sidebar/EconomicsTotals.tsx` (создать) | четыре итога |
| `sidebar/EconomicsSidebar.tsx` (создать) | липкая колонка из трёх блоков |
| `ResourcesTab.tsx` (создать) | натуральные величины с происхождением, предупреждения мощностей и модели (`ModelWarnings`) |
| `HistoryTab.tsx` (создать) | список прогонов паспорта, открыть черновиком, xlsx |
| `CostStructure.tsx`, `SensitivityTable.tsx`, `RunsCompare.tsx`, `VariantTabs.tsx`, `ServicesPanel.tsx`, `DrillingBreakdown.tsx`, `ModelWarnings.tsx` (сохранить) | переиспользуются внутри вкладок |
| `ParametersPanel.tsx`, `NomenclaturePanel.tsx`, `CrewEditor.tsx`, `PricePanel.tsx` (удалить после задачи 9) | заменены разделами сметы и сайдбаром |
| `frontend/src/types/blockEconomics.ts` (изменить) | новые поля контрактов |
| `frontend/src/api/endpoints.ts` (изменить) | `subcontractRateToReference` |
| `frontend/src/styles/economics.css` (создать), `styles.css` (изменить) | стили сметы, сайдбара, бейджей, комбобокса; удаление мёртвых правил |
| `frontend/vitest.config.ts`, `package.json` (изменить) | jsdom и testing-library |
| `README.md`, `Docs/COST_MODEL.md`, `Docs/BLOCK_ECONOMICS_UI.md` (создать) | документация |

---

## Задача 1: Происхождение количества и цены у строки затрат

**Files:**
- Modify: `cost/v2/models.py:444-500`, `cost/model/inputs.py:464-498`, `cost/model/materials.py`, `cost/model/drilling.py`, `cost/model/labor.py`, `cost/model/equipment.py`, `cost/model/logistics.py`, `cost/model/services.py`, `cost/model/unit.py`, `api/schemas/block_economics.py:85-135`
- Test: `tests/test_model_origins.py`

**Interfaces:**
- Produces: `ValueOrigin = Literal["PASSPORT", "CALC", "REFERENCE", "NORM", "MANUAL", ""]`; `CostLine.quantity_origin: ValueOrigin = ""`, `CostLine.price_origin: ValueOrigin = ""`; те же поля в `to_dict()` и `CostLineSchema`.

Правила простановки (модуль, создающий строку, знает происхождение лучше всех):

| Модуль / строка | `quantity_origin` | `price_origin` |
| --- | --- | --- |
| `materials` — роли с драйвером паспорта | `PASSPORT` | `REFERENCE` |
| `materials` — электродетонаторы (`electric_detonators_qty`) | `MANUAL` | `REFERENCE` |
| `drilling` — DRILL_TOOLING, DRILL_FUEL, DRILL_SPARE_PARTS, DRILL_MAINTENANCE, DRILL_INSPECTION | `CALC` | `REFERENCE` |
| `drilling` — DRILL_DEPRECIATION, DRILL_INSURANCE | `CALC` | `CALC` (месячная сумма / плановые смены) |
| `drilling` — DRILL_SUBCONTRACT | `PASSPORT` | `REFERENCE` (задача 2 добавит `MANUAL`) |
| `labor` — ФОТ должности | `MANUAL`, если `shifts_per_block` задан вручную, иначе `NORM` | `""` |
| `labor` — взносы, резерв, суточные | `CALC` | `REFERENCE` |
| `equipment` — амортизация, страховка, ТОиР, выпуск, запчасти | `CALC` | `REFERENCE` (амортизация и страховка — `CALC`) |
| `logistics` — ГСМ транспорта, доставка, мобилизация | `CALC` | `REFERENCE` |
| `services` — ручная услуга | `MANUAL` | `MANUAL` |
| `cost_rules` (`services.py`, правило затрат) | `CALC` | `REFERENCE` |
| `unit` — постоянные затраты юнита, склад | `CALC` | `REFERENCE` |

- [ ] **Шаг 1: Падающий тест**

```python
# tests/test_model_origins.py
from tests import model_fixtures as fx
from cost.model.engine import compute_block_economics

NOMENCLATURE = {"EXPLOSIVE": "MAT_GRANULIT", "NSI_DOWNHOLE": "MAT_NSI_DOWNHOLE"}


def _lines():
    result = compute_block_economics(fx.snapshot(), fx.parameters(nomenclature=NOMENCLATURE), fx.references())
    return {line.cost_item_code: line for line in result.lines}


def test_material_quantity_comes_from_passport_and_price_from_reference() -> None:
    line = _lines()["MATERIAL_EXPLOSIVE"]
    assert line.quantity_origin == "PASSPORT"
    assert line.price_origin == "REFERENCE"


def test_crew_shifts_are_normative_until_edited() -> None:
    normative = _lines()["LABOR_POSITION_LABOR_BLASTERS"]
    assert normative.quantity_origin == "NORM"

    edited = compute_block_economics(
        fx.snapshot(),
        fx.parameters(
            nomenclature=NOMENCLATURE,
            crew=[{"position_code": "POSITION_LABOR_BLASTERS", "headcount": "2", "shifts_per_block": "4"}],
        ),
        fx.references(),
    )
    line = next(row for row in edited.lines if row.cost_item_code == "LABOR_POSITION_LABOR_BLASTERS")
    assert line.quantity_origin == "MANUAL"


def test_every_line_serializes_its_origins() -> None:
    for line in _lines().values():
        payload = line.to_dict()
        assert "quantity_origin" in payload and "price_origin" in payload
```

Коды материалов и должностей взять из `tests/model_fixtures.py` (`references()`): перед написанием теста открыть фикстуру и подставить реальные коды.

- [ ] **Шаг 2: Убедиться, что тест падает**

Run: `.venv/bin/python -m pytest tests/test_model_origins.py -q`
Expected: FAIL — `AttributeError: 'CostLine' object has no attribute 'quantity_origin'`.

- [ ] **Шаг 3: Поля модели и `add_line`**

```python
# cost/v2/models.py (рядом с EstimateSection)
ValueOrigin = Literal["PASSPORT", "CALC", "REFERENCE", "NORM", "MANUAL", ""]

@dataclass
class CostLine:
    ...
    role_label: str | None = None
    # Откуда взяты количество и цена строки: паспорт, расчёт модели,
    # справочник, норматив или ручной ввод сметчика. Пусто — величины нет
    # (доля постоянных затрат юнита не имеет «количества»).
    quantity_origin: ValueOrigin = ""
    price_origin: ValueOrigin = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            ...,
            "quantity_origin": self.quantity_origin,
            "price_origin": self.price_origin,
        }
```

```python
# cost/model/inputs.py — ModelContext.add_line
    def add_line(self, *, ..., role_label: str | None = None,
                 quantity_origin: ValueOrigin = "", price_origin: ValueOrigin = "") -> None:
        self.lines.append(CostLine(..., quantity_origin=quantity_origin, price_origin=price_origin))
```

Затем пройти по всем вызовам `context.add_line(` (`grep -n "add_line(" cost/model/*.py`, дубликаты « 2.py» пропускать) и проставить пары по таблице выше. В `labor.py` происхождение смен известно из `manual_shifts`:

```python
        context.add_line(
            ...,
            quantity_origin="MANUAL" if manual_shifts is not None else "NORM",
        )
```

- [ ] **Шаг 4: Схема API**

```python
# api/schemas/block_economics.py — CostLineSchema
    quantity_origin: Literal["PASSPORT", "CALC", "REFERENCE", "NORM", "MANUAL", ""] = ""
    price_origin: Literal["PASSPORT", "CALC", "REFERENCE", "NORM", "MANUAL", ""] = ""
```

- [ ] **Шаг 5: Прогнать тесты**

Run: `.venv/bin/python -m pytest -q`
Expected: PASS, включая `tests/test_model_regression_smeta_2026_01.py` (суммы не менялись).

- [ ] **Шаг 6: Коммит**

```bash
git add cost/v2/models.py cost/model/inputs.py cost/model/materials.py cost/model/drilling.py cost/model/labor.py cost/model/equipment.py cost/model/logistics.py cost/model/services.py cost/model/unit.py api/schemas/block_economics.py tests/test_model_origins.py
git commit -m "feat(cost): происхождение количества и цены у строки затрат"
```

---

## Задача 2: Выбор тарифа субподряда и ручная ставка; каталоги для конструктора

**Files:**
- Modify: `cost/model/inputs.py:179-240` (`ModelParameters`), `cost/model/drilling.py:443-497`, `api/schemas/block_economics.py:46-72, 239-254`, `api/routers/block_economics.py:317-399`
- Test: `tests/test_model_drilling.py`, `tests/test_api_block_economics.py`

**Interfaces:**
- Produces: `ModelParameters.subcontract_rate_code: str | None`, `ModelParameters.subcontract_rate_rub: Decimal | None`; `ModelDefaultsResponse.subcontract_rates: list[SubcontractRateOption]`, `ModelDefaultsResponse.counterparties: list[CodeName]`, `ModelDefaultsResponse.positions: list[PositionOption]`.

```python
class SubcontractRateOption(BaseModel):
    code: str
    name: str
    counterparty_code: str
    counterparty_name: str
    operation_code: str
    unit: str
    rate_rub: float

class PositionOption(BaseModel):
    code: str
    name: str
    fixed_monthly_rub: float      # из labor_rates; 0 — ставки нет
    norm_shifts_per_month: float  # из positions
    category: Literal["DIRECT", "INDIRECT"]
```

Приоритет ставки в `_subcontract_lines`: `subcontract_rate_rub` (ручная, `price_origin="MANUAL"`) → запись `subcontract_rates` с кодом `subcontract_rate_code` (`REFERENCE`) → первая запись по операции `PRODUCTION_DRILLING` (`REFERENCE`, прежнее поведение) → ноль с предупреждением.

- [ ] **Шаг 1: Падающие тесты модели**

```python
# tests/test_model_drilling.py (дополнить)
def test_subcontract_uses_the_chosen_rate() -> None:
    references = fx.references(subcontract_rates=[
        fx.item("RATE_A", "БурСервис Ø140", operation_code="PRODUCTION_DRILLING", unit="UNIT_M", rate_rub="150"),
        fx.item("RATE_B", "БурСервис Ø152", operation_code="PRODUCTION_DRILLING", unit="UNIT_M", rate_rub="185"),
    ])
    result = compute_block_economics(
        fx.snapshot(),
        fx.parameters(drilling_executor="SUBCONTRACTOR", subcontract_rate_code="RATE_B"),
        references,
    )
    line = next(row for row in result.lines if row.cost_item_code == "DRILL_SUBCONTRACT")
    assert line.unit_price_rub == Decimal("185")
    assert line.price_origin == "REFERENCE"


def test_manual_subcontract_rate_wins_and_is_marked_manual() -> None:
    result = compute_block_economics(
        fx.snapshot(),
        fx.parameters(drilling_executor="SUBCONTRACTOR", subcontract_rate_rub="199.5"),
        fx.references(),
    )
    line = next(row for row in result.lines if row.cost_item_code == "DRILL_SUBCONTRACT")
    assert line.unit_price_rub == Decimal("199.5")
    assert line.price_origin == "MANUAL"
    assert line.quantity_origin == "PASSPORT"
```

Имя помощника для записи справочника (`fx.item` или аналог) сверить с `tests/model_fixtures.py`.

- [ ] **Шаг 2: Убедиться, что тесты падают**

Run: `.venv/bin/python -m pytest tests/test_model_drilling.py -q`
Expected: FAIL — `TypeError: parameters() got an unexpected keyword argument 'subcontract_rate_code'` либо `AssertionError`.

- [ ] **Шаг 3: Параметры модели**

```python
# cost/model/inputs.py — ModelParameters
    subcontract_rate_code: str | None = None
    # Ручная ставка за метр: сметчик проверяет предложение подрядчика, которого
    # ещё нет в справочнике. В справочник попадает только явной кнопкой.
    subcontract_rate_rub: Decimal | None = None
```

В `from_dict` / `to_dict` добавить оба поля (`Decimal` через существующий помощник `decimal_value`/`_decimal_or_none` — как у `rig_plan_shifts`).

- [ ] **Шаг 4: Выбор ставки в модели**

```python
# cost/model/drilling.py
def _subcontract_lines(context: ModelContext, drilling_m: Decimal) -> None:
    params = context.params
    rate, price_origin, rate_source = _subcontract_rate(context)
    if rate <= 0:
        context.warn("Не задана субподрядная ставка бурения: строка субподряда нулевая.")
    context.set_value("rig_shifts", Decimal("0"), "бурение на субподряде")
    context.set_value("drilling_rub_per_m", rate, rate_source)
    context.add_line(
        operation_code=DRILLING_OPERATION,
        cost_item_code="DRILL_SUBCONTRACT",
        cost_item_name="Субподряд: бурение",
        layer=CostLayer.VARIABLE,
        amount_rub=drilling_m * rate,
        formula=f"{drilling_m} м × {rate} ₽/м",
        section="DRILLING",
        quantity=drilling_m,
        unit="п.м.",
        unit_price_rub=rate,
        quantity_origin="PASSPORT",
        price_origin=price_origin,
    )
    ...  # DRILL_UNALLOCATED_FIXED без изменений


def _subcontract_rate(context: ModelContext) -> tuple[Decimal, ValueOrigin, str]:
    params = context.params
    if params.subcontract_rate_rub is not None:
        return params.subcontract_rate_rub, "MANUAL", "ставка введена на вкладке"
    items = [
        item for item in context.items("subcontract_rates")
        if payload_text(item, "operation_code") == DRILLING_OPERATION
    ]
    chosen = next((item for item in items if item.code == params.subcontract_rate_code), None)
    if chosen is None and params.subcontract_rate_code:
        context.warn(f"Тариф субподряда {params.subcontract_rate_code} не найден: взята первая ставка по операции.")
    chosen = chosen or (items[0] if items else None)
    if chosen is None:
        return Decimal("0"), "", "тариф субподряда не найден"
    return payload_number(chosen, "rate_rub"), "REFERENCE", f"subcontract_rates.{chosen.code}"
```

- [ ] **Шаг 5: Тест и код API**

```python
# tests/test_api_block_economics.py (дополнить)
def test_defaults_offer_subcontract_rates_with_counterparties(client) -> None:
    passport_id = _passport(client)   # уже используемый в файле помощник
    response = client.get(f"/api/v1/economics/model-defaults?technical_passport_id={passport_id}")
    assert response.status_code == 200
    body = response.json()
    assert body["subcontract_rates"], "в фикстуре должна быть ставка бурения"
    rate = body["subcontract_rates"][0]
    assert set(rate) >= {"code", "name", "counterparty_code", "counterparty_name", "operation_code", "unit", "rate_rub"}
    assert body["counterparties"]
    position = body["positions"][0]
    assert set(position) >= {"code", "name", "fixed_monthly_rub", "norm_shifts_per_month", "category"}
    assert body["parameters"]["subcontract_rate_code"] is None
```

```python
# api/schemas/block_economics.py — ModelParametersSchema
    subcontract_rate_code: str | None = None
    subcontract_rate_rub: Decimal | None = Field(None, ge=0)
```

```python
# api/routers/block_economics.py — model_defaults
    "subcontract_rates": _subcontract_rates(references),
    "counterparties": [
        {"code": item.code, "name": item.name}
        for item in references.active_items("counterparties")
        if payload_text(item, "role") == "SUBCONTRACTOR"
    ],
    "positions": _positions(references),


def _subcontract_rates(references: ReferenceSnapshot) -> list[dict[str, Any]]:
    names = {item.code: item.name for item in references.active_items("counterparties")}
    units = {item.code: item.name for item in references.active_items("units")}
    rows = []
    for item in references.active_items("subcontract_rates"):
        counterparty = payload_text(item, "counterparty_code")
        rows.append({
            "code": item.code,
            "name": item.name,
            "counterparty_code": counterparty,
            "counterparty_name": names.get(counterparty, counterparty),
            "operation_code": payload_text(item, "operation_code"),
            "unit": units.get(payload_text(item, "unit"), payload_text(item, "unit")),
            "rate_rub": float(payload_number(item, "rate_rub")),
        })
    return sorted(rows, key=lambda row: (row["counterparty_name"], row["name"]))


def _positions(references: ReferenceSnapshot) -> list[dict[str, Any]]:
    rates = {payload_text(item, "position_code"): item for item in references.active_items("labor_rates")}
    return [
        {
            "code": item.code,
            "name": item.name,
            "category": payload_text(item, "category", "DIRECT"),
            "norm_shifts_per_month": float(payload_number(item, "norm_shifts_per_month", Decimal("21"))),
            "fixed_monthly_rub": float(payload_number(rates.get(item.code), "fixed_monthly_rub")),
        }
        for item in references.active_items("positions")
    ]
```

Схему `ModelDefaultsResponse` расширить полями `subcontract_rates: list[SubcontractRateOption]`, `counterparties: list[CodeName]`, `positions: list[PositionOption]` (вместо `list[CodeName]`). Если в фикстурах `tests/conftest.py` нет ставки субподряда или подрядчика — добавить по одной записи в `references()` фикстуры (`subcontract_rates`, `counterparties` с `role="SUBCONTRACTOR"`).

- [ ] **Шаг 6: Прогнать все тесты**

Run: `.venv/bin/python -m pytest -q`
Expected: PASS.

- [ ] **Шаг 7: Коммит**

```bash
git add cost/model/inputs.py cost/model/drilling.py api/schemas/block_economics.py api/routers/block_economics.py tests/test_model_drilling.py tests/test_api_block_economics.py tests/model_fixtures.py tests/conftest.py
git commit -m "feat(economics): выбор тарифа субподряда, ручная ставка и каталоги конструктора"
```

---

## Задача 3: Явное сохранение тарифа субподряда в справочник

**Files:**
- Modify: `api/routers/block_economics.py:493-590` (рядом с `service_to_reference`), `api/schemas/block_economics.py`
- Test: `tests/test_api_block_economics.py`

**Interfaces:**
- Produces: `POST /api/v1/economics/subcontract-rates/to-reference` (201, `require_reference_editor`).

```python
class SubcontractRateToReferenceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    counterparty_code: str = Field(..., min_length=1)
    operation_code: str = Field("PRODUCTION_DRILLING", min_length=1)
    name: str = Field(..., min_length=1, max_length=200)   # «Бурение Ø140 мм»
    unit: str = Field("UNIT_M", min_length=1)
    rate_rub: Decimal = Field(..., gt=0)

class SubcontractRateToReferenceResponse(BaseModel):
    section: Literal["subcontract_rates"] = "subcontract_rates"
    code: str
    created: bool
    reference_revision_id: str
```

Код записи: `f"RATE_{counterparty_code}_{operation_code}_{slug(name)}"` тем же транслитом, что `service_code` (`cost/model/services.py:43`) — вынести общий `reference_code(prefix, *parts)` в `cost/model/services.py` и переиспользовать. Повторная публикация с тем же кодом обновляет ставку (`created=False`), как у услуг. Публикация — через тот же путь, что `service_to_reference` (снимок → upsert → `validate` → `publish` с комментарием «Тариф субподряда с вкладки «Экономика блока»»), чтобы ревизия создавалась одинаково.

- [ ] **Шаг 1: Падающий тест**

```python
def test_subcontract_rate_is_published_only_by_explicit_request(client) -> None:
    passport_id = _passport(client)
    before = client.get(f"/api/v1/economics/model-defaults?technical_passport_id={passport_id}").json()
    # Ручная ставка в расчёте справочник не трогает.
    computed = client.post("/api/v1/economics/block-economics", json={
        "technical_passport_id": passport_id,
        "parameters": {**before["parameters"], "drilling_executor": "SUBCONTRACTOR", "subcontract_rate_rub": "185"},
    })
    assert computed.status_code == 200
    unchanged = client.get(f"/api/v1/economics/model-defaults?technical_passport_id={passport_id}").json()
    assert unchanged["reference_revision_id"] == before["reference_revision_id"]

    saved = client.post("/api/v1/economics/subcontract-rates/to-reference", json={
        "counterparty_code": before["counterparties"][0]["code"],
        "name": "Бурение Ø140 мм",
        "rate_rub": "185",
    })
    assert saved.status_code == 201
    body = saved.json()
    assert body["created"] is True
    after = client.get(f"/api/v1/economics/model-defaults?technical_passport_id={passport_id}").json()
    assert after["reference_revision_id"] != before["reference_revision_id"]
    assert any(rate["code"] == body["code"] and rate["rate_rub"] == 185.0 for rate in after["subcontract_rates"])

    again = client.post("/api/v1/economics/subcontract-rates/to-reference", json={
        "counterparty_code": before["counterparties"][0]["code"],
        "name": "Бурение Ø140 мм",
        "rate_rub": "190",
    })
    assert again.status_code == 201 and again.json()["created"] is False
```

- [ ] **Шаг 2: Убедиться, что тест падает**

Run: `.venv/bin/python -m pytest tests/test_api_block_economics.py -q -k subcontract_rate_is_published`
Expected: FAIL — 404 на новом маршруте.

- [ ] **Шаг 3: Маршрут**

Реализовать по образцу `service_to_reference` (`block_economics.py:498-590`): та же последовательность `get_reference_snapshot → upsert записи в sections["subcontract_rates"] → validate → publish`. Вынести общий кусок «опубликовать снимок с одной изменённой записью» в функцию `_publish_single_item(repository, reader, organization_id, user_id, sections, comment)` и использовать её из обоих маршрутов, чтобы не дублировать обработку 409 и ошибок валидации.

- [ ] **Шаг 4: Прогнать тесты**

Run: `.venv/bin/python -m pytest -q`
Expected: PASS.

- [ ] **Шаг 5: Коммит и PR**

```bash
git add api/routers/block_economics.py api/schemas/block_economics.py cost/model/services.py tests/test_api_block_economics.py
git commit -m "feat(economics): публикация тарифа субподряда в справочник по явной кнопке"
```

Открыть PR «Экономика блока: происхождение строк, тариф субподряда и каталоги конструктора», пройти `/code-review`.

---

## Задача 4: Окружение для компонентных тестов

**Files:**
- Modify: `frontend/package.json`, `frontend/vitest.config.ts`
- Create: `frontend/src/test/setup.ts`, `frontend/src/test/render.tsx`, `frontend/src/pages/economics/estimate/OriginBadge.tsx`, `frontend/src/pages/economics/estimate/OriginBadge.test.tsx`

**Interfaces:**
- Produces: `renderWithWorkspace(ui, {canEdit = true})` — обёртка над `render` из testing-library, подменяющая `useWorkspace` (через `WorkspaceContext` провайдер с минимальным значением); `OriginBadge({origin, label?})`.

- [ ] **Шаг 1: Зависимости и конфигурация**

```bash
cd frontend && npm install --save-dev jsdom@^26 @testing-library/react@^16 @testing-library/user-event@^14 @testing-library/jest-dom@^6
```

```ts
// frontend/vitest.config.ts
import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    environment: "node",
    include: ["src/**/*.test.ts", "src/**/*.test.tsx"],
    exclude: ["**/* 2.*", "**/* 3.*", "node_modules/**"],
    setupFiles: ["src/test/setup.ts"],
  },
});
```

```ts
// frontend/src/test/setup.ts
import "@testing-library/jest-dom/vitest";
```

Компонентные тесты начинаются строкой `// @vitest-environment jsdom`.

- [ ] **Шаг 2: Падающий тест бейджа**

```tsx
// frontend/src/pages/economics/estimate/OriginBadge.test.tsx
// @vitest-environment jsdom
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { OriginBadge } from "./OriginBadge";

describe("OriginBadge", () => {
  it("подписывает происхождение словом, а не кодом", () => {
    render(<OriginBadge origin="PASSPORT" />);
    expect(screen.getByText("Паспорт")).toHaveAttribute("title", "Величина из технического паспорта");
  });
  it("ничего не рисует без происхождения", () => {
    const { container } = render(<OriginBadge origin="" />);
    expect(container).toBeEmptyDOMElement();
  });
});
```

- [ ] **Шаг 3: Убедиться, что тест падает**

Run: `cd frontend && npx vitest run src/pages/economics/estimate/OriginBadge.test.tsx`
Expected: FAIL — модуль не найден.

- [ ] **Шаг 4: Реализация**

```ts
// frontend/src/pages/economics/origin.ts
import type { ValueOrigin } from "../../types/blockEconomics";

export const ORIGIN_LABELS: Record<Exclude<ValueOrigin, "">, { label: string; title: string }> = {
  PASSPORT: { label: "Паспорт", title: "Величина из технического паспорта" },
  CALC: { label: "Расчёт", title: "Посчитано моделью себестоимости" },
  REFERENCE: { label: "Справочник", title: "Из опубликованной ревизии справочников" },
  NORM: { label: "Норматив", title: "Норматив справочника, не изменялся" },
  MANUAL: { label: "Ручной", title: "Введено на вкладке" },
};
```

```tsx
// frontend/src/pages/economics/estimate/OriginBadge.tsx
import { ORIGIN_LABELS } from "../origin";
import type { ValueOrigin } from "../../../types/blockEconomics";

/** Бейдж происхождения величины. `label` переопределяет текст: «Расчёт бурения». */
export function OriginBadge({ origin, label }: { origin: ValueOrigin; label?: string }) {
  if (!origin) return null;
  const meta = ORIGIN_LABELS[origin];
  return (
    <span className={`origin-badge origin-${origin.toLowerCase()}`} title={meta.title}>
      {label ?? meta.label}
    </span>
  );
}
```

В `frontend/src/types/blockEconomics.ts` добавить `export type ValueOrigin = "PASSPORT" | "CALC" | "REFERENCE" | "NORM" | "MANUAL" | "";` и поля `quantity_origin`, `price_origin` в `BlockCostLine`; `subcontract_rate_code`, `subcontract_rate_rub` в `ModelParameters`; `SubcontractRateOption`, `PositionOption` и новые поля `ModelDefaults` (задача 2).

- [ ] **Шаг 5: Прогнать тесты и сборку**

Run: `cd frontend && npm test && npm run build`
Expected: PASS; существующие 204 теста не тронуты.

- [ ] **Шаг 6: Коммит**

```bash
git add frontend/package.json frontend/package-lock.json frontend/vitest.config.ts frontend/src/test/setup.ts frontend/src/pages/economics/origin.ts frontend/src/pages/economics/estimate/OriginBadge.tsx frontend/src/pages/economics/estimate/OriginBadge.test.tsx frontend/src/types/blockEconomics.ts
git commit -m "test(frontend): jsdom и testing-library для компонентных тестов экономики блока"
```

---

## Задача 5: Чистые модули: инженерные разделы, диаграмма, черновик сценария

**Files:**
- Create: `frontend/src/pages/economics/estimateModel.ts` + `.test.ts`, `donut.ts` + `.test.ts`, `scenario.ts` + `.test.ts`

**Interfaces:**

```ts
// estimateModel.ts
export type EstimateGroupCode =
  | "EXPLOSIVES" | "DRILLING" | "LABOR" | "EQUIPMENT" | "FUEL" | "SERVICES" | "FIXED";

export type EstimateGroup = {
  code: EstimateGroupCode;
  number: number;              // 1..7
  label: string;               // «Взрывчатые материалы» …
  lines: BlockCostLine[];
  total: number;
  perM3: number | null;        // null при нулевом объёме
  share: number;               // доля в себестоимости, 0..1
};

export const ESTIMATE_GROUPS: ReadonlyArray<{ code: EstimateGroupCode; label: string }>;
export function groupOf(line: BlockCostLine): EstimateGroupCode;
export function buildEstimate(economics: BlockEconomics): EstimateGroup[];   // всегда 7 групп, пустые с total 0
export function lineNumber(group: EstimateGroup, index: number): string;     // «1.3»
```

```ts
// donut.ts
export type DonutSegment = { code: EstimateGroupCode; label: string; value: number; share: number; perM3: number | null; path: string; color: string };
export function donutSegments(groups: EstimateGroup[], radius: number, thickness: number): DonutSegment[];
export const GROUP_COLORS: Record<EstimateGroupCode, string>;
```

```ts
// scenario.ts
export type Draft = Variant & { sourceRunId: string | null; savedKey: string };
export function draftFromDefaults(name: string, parameters: ModelParameters): Draft;
export function draftFromRun(run: EconomicsRun, name: string): Draft;
export function isDirty(draft: Draft): boolean;                    // JSON параметров ≠ savedKey
export function markSaved(draft: Draft, runId: string): Draft;
export function scenarioLabel(draft: Draft, runs: EconomicsRunSummary[]): string;   // «Сценарий 4 · черновик»
```

Правило `groupOf` (см. «Решения», п. 2):

```ts
const MACHINE_PREFIXES = ["SZM_", "VM_TRUCK_", "EMULSION_TRUCK_"];
export function groupOf(line: BlockCostLine): EstimateGroupCode {
  if (line.section === "EXPLOSIVES") return "EXPLOSIVES";
  if (line.section === "DRILLING") return "DRILLING";
  if (line.section === "LABOR" || line.section === "PER_DIEM") return "LABOR";
  if (line.section === "DEPRECIATION") return "EQUIPMENT";
  if (MACHINE_PREFIXES.some((prefix) => line.cost_item_code.startsWith(prefix))) return "EQUIPMENT";
  if (line.section === "FUEL") return "FUEL";
  if (line.section === "VM_LOGISTICS") return "SERVICES";
  if (line.quantity_origin === "MANUAL" && line.price_origin === "MANUAL") return "SERVICES"; // услуга с вкладки
  return "FIXED";
}
```

- [ ] **Шаг 1: Падающие тесты**

```ts
// estimateModel.test.ts
import { describe, expect, it } from "vitest";
import { buildEstimate, groupOf } from "./estimateModel";
import type { BlockCostLine, BlockEconomics } from "../../types/blockEconomics";

const line = (patch: Partial<BlockCostLine>): BlockCostLine => ({
  month: "", service_line_id: "", service_line_name: "", operation_code: "", cost_item_code: "X",
  cost_item_name: "x", layer: "variable", amount_rub: 0, formula: "", resource_code: "",
  section: "OVERHEAD", quantity: null, unit: "", unit_price_rub: null, role_label: null,
  quantity_origin: "", price_origin: "", ...patch,
});

describe("groupOf", () => {
  it("ТОиР СЗМ относится к технике, хотя в бумажной смете это общепроизводственные", () => {
    expect(groupOf(line({ section: "OVERHEAD", cost_item_code: "SZM_MAINTENANCE" }))).toBe("EQUIPMENT");
  });
  it("суточные идут к персоналу", () => {
    expect(groupOf(line({ section: "PER_DIEM" }))).toBe("LABOR");
  });
  it("услуга с вкладки — производственная услуга", () => {
    expect(groupOf(line({ quantity_origin: "MANUAL", price_origin: "MANUAL" }))).toBe("SERVICES");
  });
});

describe("buildEstimate", () => {
  const economics = {
    block_volume_m3: 1000,
    lines: [
      line({ section: "EXPLOSIVES", amount_rub: 600 }),
      line({ section: "DRILLING", amount_rub: 400 }),
    ],
  } as BlockEconomics;
  it("всегда возвращает семь разделов по порядку, пустые — нулями", () => {
    const groups = buildEstimate(economics);
    expect(groups.map((g) => g.number)).toEqual([1, 2, 3, 4, 5, 6, 7]);
    expect(groups[2].total).toBe(0);
  });
  it("считает долю и ₽/м³ от объёма блока", () => {
    const [explosives] = buildEstimate(economics);
    expect(explosives.share).toBeCloseTo(0.6);
    expect(explosives.perM3).toBeCloseTo(0.6);
  });
  it("при нулевом объёме ₽/м³ — null, а не Infinity", () => {
    const [explosives] = buildEstimate({ ...economics, block_volume_m3: 0 });
    expect(explosives.perM3).toBeNull();
  });
});
```

```ts
// donut.test.ts
it("сегменты покрывают полный круг и пропускают нулевые разделы", () => {
  const segments = donutSegments(buildEstimate(economics), 80, 22);
  expect(segments.map((s) => s.code)).toEqual(["EXPLOSIVES", "DRILLING"]);
  expect(segments.reduce((sum, s) => sum + s.share, 0)).toBeCloseTo(1);
  expect(segments[0].path).toMatch(/^M .* A .* Z$/);
});
it("один сегмент рисуется полным кольцом без вырожденной дуги", () => { ... expect(path).not.toContain("NaN"); });
```

```ts
// scenario.test.ts
it("черновик из прогона чист, пока параметры не тронули", () => {
  const draft = draftFromRun(run, "Сценарий 2");
  expect(isDirty(draft)).toBe(false);
  expect(isDirty({ ...draft, parameters: { ...draft.parameters, vat_rate: 0 } })).toBe(true);
});
it("новый черновик из умолчаний считается несохранённым", () => {
  expect(isDirty(draftFromDefaults("Вариант 1", parameters))).toBe(true);
});
```

- [ ] **Шаг 2: Убедиться, что тесты падают**

Run: `cd frontend && npx vitest run src/pages/economics/estimateModel.test.ts src/pages/economics/donut.test.ts src/pages/economics/scenario.test.ts`
Expected: FAIL — модули не найдены.

- [ ] **Шаг 3: Реализация**

`buildEstimate`: один проход по `lines`, `Map<EstimateGroupCode, BlockCostLine[]>`, затем `ESTIMATE_GROUPS.map(...)`; итог себестоимости — сумма всех `amount_rub` (совпадает с `markup.full_cost_rub`); доля — `total / costTotal` (0 при нулевой себестоимости). `donutSegments`: угол от −90°, дуга `A r r 0 largeArc 1 x y`, кольцо через внешнюю и внутреннюю дуги; сегмент с долей ≥ 0,9999 рисуется двумя полудугами. `GROUP_COLORS` — палитра концепта: `#1f7a5c`, `#3b82f6`, `#f2a93b`, `#f28c5f`, `#8b7cf6`, `#5cc4d8`, `#9aa5b1`. `scenario.ts`: `savedKey = JSON.stringify(parameters)`; `draftFromRun` берёт `run.parameters` как `ModelParameters` и `sourceRunId = run.id`.

- [ ] **Шаг 4: Прогнать тесты**

Run: `cd frontend && npm test`
Expected: PASS.

- [ ] **Шаг 5: Коммит**

```bash
git add frontend/src/pages/economics/estimateModel.ts frontend/src/pages/economics/estimateModel.test.ts frontend/src/pages/economics/donut.ts frontend/src/pages/economics/donut.test.ts frontend/src/pages/economics/scenario.ts frontend/src/pages/economics/scenario.test.ts
git commit -m "feat(frontend): инженерные разделы сметы, сегменты диаграммы и состояние черновика"
```

---

## Задача 6: Комбобокс справочника и каркас таблицы сметы

**Files:**
- Create: `frontend/src/pages/economics/estimate/CatalogSelect.tsx` + `.test.tsx`, `EstimateBuilder.tsx`, `EstimateSection.tsx`, `EstimateLine.tsx`, `RowMenu.tsx`, `frontend/src/styles/economics.css`
- Modify: `frontend/src/main.tsx` (импорт `styles/economics.css` рядом с остальными)

**Interfaces:**

```tsx
export type CatalogOption = { code: string; name: string; caption?: string; price?: number; unit?: string; disabled?: boolean };
export function CatalogSelect(props: {
  id: string; label: string;                // label — aria-label кнопки, видимого текста нет (в строке сметы)
  value: string; options: CatalogOption[];
  placeholder?: string;                    // «не выбрано»
  onChange: (code: string) => void;
  disabled?: boolean;
}): JSX.Element;
```

Поведение: кнопка `role="combobox"` показывает имя выбранного; по клику/Enter/Space/ArrowDown открывается поповер с полем поиска (автофокус) и `ul role="listbox"`; фильтр по подстроке без учёта регистра по имени и подписи; ArrowUp/Down — активный элемент (`aria-activedescendant`), Enter — выбор, Escape — закрыть, клик вне — закрыть; у опции справа цена `46,00 ₽/кг` (`money(price)` + `unit`). Логика клавиатуры — как в `pages/design/CommandPalette.tsx`.

```tsx
export function EstimateBuilder(props: {
  groups: EstimateGroup[]; volume: number | null; expanded: Set<EstimateGroupCode>;
  onToggle: (code: EstimateGroupCode) => void; onExpandAll: () => void; onCollapseAll: () => void;
  highlighted: EstimateGroupCode | null;            // от клика по диаграмме
  renderGroup: (group: EstimateGroup) => ReactNode;  // редактор раздела (задача 7)
  busy: boolean;                                     // пересчёт: таблица тускнеет, но не перестраивается
}): JSX.Element;

export function EstimateSection(props: { group: EstimateGroup; volume: number | null; open: boolean; highlighted: boolean; onToggle: () => void; children: ReactNode }): JSX.Element;
// id секции: `estimate-section-${code}` — для прокрутки от диаграммы

export function EstimateLine(props: {
  number: string; name: ReactNode; origin: ValueOrigin; originLabel?: string;
  quantity: number | null; unit: string; price: number | null; amount: number; volume: number | null; share: number;
  actions?: ReactNode; formula?: string;
}): JSX.Element;
// колонки: № · статья · основание · кол-во · ед. · цена · сумма · ₽/м³ · % · ⋯ ; числа через reconcilingColumns/money/perM3 из format.ts

export function RowMenu(props: { items: Array<{ label: string; onSelect: () => void; danger?: boolean }> ; label: string }): JSX.Element;
```

- [ ] **Шаг 1: Падающие тесты комбобокса**

```tsx
// CatalogSelect.test.tsx
// @vitest-environment jsdom
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { CatalogSelect } from "./CatalogSelect";

const options = [
  { code: "GRANULIT", name: "Гранулит РП", price: 46, unit: "кг" },
  { code: "SFERIT", name: "Сферит ДТ", price: 150, unit: "кг" },
  { code: "BEREZIT", name: "Березит Э-100", price: 54.2, unit: "кг" },
];

describe("CatalogSelect", () => {
  it("ищет по подстроке и выбирает клавиатурой", async () => {
    const onChange = vi.fn();
    render(<CatalogSelect id="ex" label="Основное ВВ" value="GRANULIT" options={options} onChange={onChange} />);
    const user = userEvent.setup();
    await user.click(screen.getByRole("combobox", { name: "Основное ВВ" }));
    await user.type(screen.getByRole("searchbox"), "сфер");
    expect(screen.getAllByRole("option")).toHaveLength(1);
    await user.keyboard("{ArrowDown}{Enter}");
    expect(onChange).toHaveBeenCalledWith("SFERIT");
    expect(screen.queryByRole("listbox")).not.toBeInTheDocument();
  });
  it("показывает цену и единицу у каждой позиции", async () => {
    render(<CatalogSelect id="ex" label="Основное ВВ" value="" options={options} onChange={() => {}} />);
    await userEvent.click(screen.getByRole("combobox"));
    expect(screen.getByText("150,00 ₽/кг")).toBeInTheDocument();
  });
  it("Escape закрывает список и возвращает фокус кнопке", async () => { ... });
});
```

- [ ] **Шаг 2: Убедиться, что тесты падают**

Run: `cd frontend && npx vitest run src/pages/economics/estimate/CatalogSelect.test.tsx`
Expected: FAIL.

- [ ] **Шаг 3: Реализация комбобокса и каркаса**

Реализовать `CatalogSelect` (состояние `open`, `query`, `active`; `useEffect` на `mousedown` документа для закрытия; `useRef` кнопки для возврата фокуса). `EstimateBuilder` — `<div role="table">` с CSS-grid строками (`grid-template-columns: 44px minmax(0,1fr) 110px 96px 48px 96px 120px 76px 60px 32px`), липкая шапка `position: sticky; top: var(--passport-strip-h)`; при `busy` класс `is-recalculating` (opacity .7, `aria-busy`). `EstimateSection` — `<section id=…>` с заголовком-кнопкой `aria-expanded`; итоги раздела всегда видимы. `EstimateLine` — строка `role="row"`, формула раскрывается пунктом меню «Формула» в `<details>` под строкой.

CSS (`styles/economics.css`): таблица, шапка, строки (`font-variant-numeric: tabular-nums`, высота 34 px, hover `#f7faf8`), итог раздела жирный на фоне `#f5f8f6`, бейджи (`.origin-badge` — 10 px, радиус 6 px; цвета: паспорт `#e8f1fb/#1f4e8c`, расчёт `#eef3f1/#31483d`, справочник `#eaf6ef/#1f6a4a`, норматив `#f3f0fb/#4f3d9e`, ручной `#fff4e5/#8a5a10`), комбобокс, поповер, меню строки.

- [ ] **Шаг 4: Прогнать тесты и сборку**

Run: `cd frontend && npm test && npm run build`
Expected: PASS.

- [ ] **Шаг 5: Коммит**

```bash
git add frontend/src/pages/economics/estimate frontend/src/styles/economics.css frontend/src/main.tsx
git commit -m "feat(frontend): комбобокс справочника и каркас иерархической таблицы сметы"
```

---

## Задача 7: Редакторы разделов сметы

**Files:**
- Create: `frontend/src/pages/economics/sections/ExplosivesSection.tsx` (+ `.test.tsx`), `LaborSection.tsx` (+ `.test.tsx`), `EquipmentSection.tsx` (+ `.test.tsx`), `FuelSection.tsx`, `ServicesSection.tsx`, `FixedCostsSection.tsx`, `DrillingSection.tsx` (+ `.test.tsx`), `frontend/src/pages/economics/drilling/OwnDrillingEditor.tsx`, `SubcontractDrillingEditor.tsx`, `DrillingDrawer.tsx`
- Modify: `frontend/src/api/endpoints.ts` (`subcontractRateToReference`), `frontend/src/pages/economics/origin.ts`

**Interfaces (общие пропсы редакторов):**

```ts
export type SectionEditorProps = {
  group: EstimateGroup;
  params: ModelParameters;
  defaults: ModelDefaults;
  economics: BlockEconomics | null;   // null до первого ответа
  volume: number | null;
  canEdit: boolean;
  onChange: (patch: Partial<ModelParameters>) => void;
};
```

**ExplosivesSection.** Строка на роль из `NOMENCLATURE_ROLES` (`nomenclature.ts`), видимую по `isRoleVisible`; название — `CatalogSelect` c опциями `defaults.nomenclature[role]` (`caption` = `quantity_label`, цена, единица); количество, ед., цена, сумма — из строки модели с `cost_item_code === role.cost_item_code` (сопоставление по `role_label`, как в `groupVariantsByLayerAndSection`); бейдж количества — `quantity_origin` строки, у электродетонаторов — `NumericInput` с бейджем «Ручной». Скрытые роли (нулевое количество в паспорте) предлагаются кнопкой «+ Добавить материал» через `RowMenu`-подобный список; убрать добавленную роль — меню строки «Убрать» (ставит `nomenclature[role] = ""`). Пока ответа нет — суммы «—».

**DrillingSection.** Радио-группа `fieldset` «Исполнение»: `● Собственными силами / ○ Субподряд` → `drilling_executor`. Пропс `onOpenDrillingPage: () => void` пробрасывается из `BlockEconomicsPage` (задача 9) в `DrillingSection` → `OwnDrillingEditor`.
- `OwnDrillingEditor`: `CatalogSelect` станка (`defaults.rigs`), объём бурения `passport.physical.drilling_m` + `OriginBadge origin="PASSPORT"`, стоимость метра `natural.values.drilling_rub_per_m` + бейдж «Расчёт бурения» (`origin="CALC"`, `label="Расчёт бурения"`, `title` = `natural.lineage.drilling_condition`), итог — сумма строк раздела, ₽/м³, две ссылки рядом: «Открыть расчёт бурения →» открывает `DrillingDrawer` (aside с `role="dialog"`, `aria-modal="false"`, внутри `DrillingBreakdown`), и «Перейти к расчёту бурения (Бурение) →» — `<button type="button" onClick={onOpenDrillingPage}>` без переноса чисел (отдельный калькулятор Cost V1, см. «Решения и допущения», п. 1); плановые смены станка — `NumericInput` (`rig_plan_shifts`) с бейджем `НОРМАТИВ`/`РУЧНОЙ` по сравнению с `defaults.parameters.rig_plan_shifts`.
- `SubcontractDrillingEditor`: подрядчик — `CatalogSelect` по `defaults.counterparties`; услуга — `CatalogSelect` по тарифам выбранного подрядчика (`defaults.subcontract_rates.filter(counterparty_code)`), `onChange` ставит `subcontract_rate_code` и сбрасывает `subcontract_rate_rub = null`; цена — `NumericInput` (значение: `subcontract_rate_rub ?? rate.rate_rub`), правка ставит `subcontract_rate_rub` и бейдж «Ручной»; объём — паспорт; итог — строка `DRILL_SUBCONTRACT`. Если `subcontract_rate_rub !== null` и `canEdit` — кнопка «Сохранить тариф в справочник» открывает встроенную форму (название услуги, подрядчик уже выбран) и зовёт `api.blockEconomics.subcontractRateToReference`; после ответа перезагрузить `defaults` (`modelDefaults`) и выставить `subcontract_rate_code = response.code`, `subcontract_rate_rub = null`, статус «Тариф … опубликован ревизией …».

**LaborSection.** Строка на `params.crew[i]`: должность — `CatalogSelect` по `defaults.positions` (только `category === "DIRECT"`, `caption` = `«${money(fixed_monthly_rub,0)} ₽/мес · ${norm_shifts_per_month} см/мес»`); кол-во — `NumericInput headcount`; смены на блок — `NumericInput shifts_per_block` (пусто = норматив); цена — оклад в месяц из `PositionOption` (бейдж «Справочник»); сумма/₽/м³/% — строка `LABOR_${position_code}` из модели. Бейдж строки: «Норматив», если запись совпадает с `defaults.parameters.crew` (та же должность, численность, `shifts_per_block === null`), иначе «Ручной» (`origin.ts: crewOrigin(member, template)`). Меню строки: «Сбросить к нормативу» (вернуть запись шаблона), «Убрать». «+ Добавить должность» — как в `CrewEditor.add`. Строки взносов, резерва и суточных показываются под должностями только для чтения. `CrewEditor.tsx` после этого не используется.

**EquipmentSection.** Четыре роли: `[{param: "rig_code", label: "Буровая установка", options: defaults.rigs, shiftsKey: "rig_shifts"}, {param: "szm_code", label: "СЗМ", options: defaults.szm, shiftsKey: "szm_shifts"}, {param: "delivery_truck_code", label: "Доставщик ВМ", options: defaults.delivery_trucks, shiftsKey: "delivery_shifts"}, {param: "emulsion_truck_code", label: "Тягач эмульсии", options: defaults.emulsion_trucks, shiftsKey: "emulsion_shifts"}]`. Строка роли: `CatalogSelect`, смены на блок из `natural.values[shiftsKey]` с бейджем «Расчёт» (`title` = `natural.lineage[shiftsKey]`), плановые смены в месяц — `NumericInput` (`machine_plan_shifts[code]`, для станка `rig_plan_shifts`) с бейджем «Норматив»/«Ручной», сумма — строки модели с префиксом роли (`DRILL_DEPRECIATION|DRILL_INSURANCE`, `SZM_*`, `VM_TRUCK_*`, `EMULSION_TRUCK_*`), под строкой роли — её статьи только для чтения (амортизация, ТОиР, страхование…). «+ Добавить технику» перечисляет роли с пустым кодом; «Убрать» — `code = null`. Станок при субподряде показывается с пометкой «постоянные затраты станка не распределены на блок» (строка `DRILL_UNALLOCATED_FIXED`).

**FuelSection / FixedCostsSection** — только `EstimateLine` по строкам группы. **ServicesSection** — строки `VM_LOGISTICS` и услуг вкладки, под ними существующий `ServicesPanel` (перенос в справочник — как сейчас).

- [ ] **Шаг 1: Падающие тесты разделов**

```tsx
// ExplosivesSection.test.tsx — «смена номенклатуры вызывает onChange с новым кодом роли»
await user.click(screen.getByRole("combobox", { name: "Основное ВВ" }));
await user.click(screen.getByRole("option", { name: /Сферит ДТ/ }));
expect(onChange).toHaveBeenCalledWith({ nomenclature: { ...params.nomenclature, EXPLOSIVE: "SFERIT" } });

// DrillingSection.test.tsx
it("переключает режим и показывает источник ставки собственного бурения", async () => {
  render(<DrillingSection {...props} />);
  expect(screen.getByText("Расчёт бурения")).toHaveAttribute("title", "drilling_conditions.COND_GRANITE (станок + порода)");
  await user.click(screen.getByRole("radio", { name: "Субподряд" }));
  expect(onChange).toHaveBeenCalledWith({ drilling_executor: "SUBCONTRACTOR" });
});
it("выбор тарифа подрядчика ставит код и сбрасывает ручную ставку", async () => { ... expect(onChange).toHaveBeenCalledWith({ subcontract_rate_code: "RATE_B", subcontract_rate_rub: null }); });
it("ручная ставка помечается «Ручной» и предлагает сохранить в справочник", async () => {
  ... await user.clear(price); await user.type(price, "185");
  expect(onChange).toHaveBeenLastCalledWith({ subcontract_rate_rub: "185" });
  rerender(<DrillingSection {...props} params={{ ...params, drilling_executor: "SUBCONTRACTOR", subcontract_rate_rub: "185" }} />);
  expect(screen.getByRole("button", { name: "Сохранить тариф в справочник" })).toBeEnabled();
});

// LaborSection.test.tsx — «добавить должность», «изменить должность», «норматив → ручной после правки численности»
// EquipmentSection.test.tsx — «выбор СЗМ вызывает onChange({szm_code})», «плановые смены с бейджем Норматив пока пусты»
```

Фикстуры для тестов вынести в `frontend/src/pages/economics/testFixtures.ts`: `defaultsFixture()`, `paramsFixture()`, `economicsFixture()` — минимальные объекты типов `ModelDefaults`, `ModelParameters`, `BlockEconomics` со строками ВМ, бурения, ФОТ, СЗМ, ГСМ.

- [ ] **Шаг 2: Убедиться, что тесты падают** — `cd frontend && npx vitest run src/pages/economics/sections`

- [ ] **Шаг 3: Реализация** по описанию выше. `api/endpoints.ts`:

```ts
    subcontractRateToReference: (payload: { counterparty_code: string; operation_code?: string; name: string; unit?: string; rate_rub: Numeric }) =>
      post<SubcontractRateToReference>(`${V1}/economics/subcontract-rates/to-reference`, payload),
```

- [ ] **Шаг 4: Тесты и сборка** — `cd frontend && npm test && npm run build`, ожидается PASS.

- [ ] **Шаг 5: Коммит**

```bash
git add frontend/src/pages/economics/sections frontend/src/pages/economics/drilling frontend/src/pages/economics/testFixtures.ts frontend/src/pages/economics/origin.ts frontend/src/api/endpoints.ts frontend/src/types/blockEconomics.ts
git commit -m "feat(frontend): редакторы разделов сметы — ВМ, бурение, бригада, техника, услуги"
```

---

## Задача 8: Липкий сайдбар: кольцо структуры, формирование цены, итоги

**Files:**
- Create: `frontend/src/pages/economics/sidebar/CostStructureDonut.tsx` (+ `.test.tsx`), `PriceFormation.tsx`, `EconomicsTotals.tsx`, `EconomicsSidebar.tsx`
- Modify: `frontend/src/styles/economics.css`

**Interfaces:**

```tsx
export function CostStructureDonut(props: {
  groups: EstimateGroup[]; costPerM3: number | null; unit: "₽" | "₽/м³";
  onUnitChange: (unit: "₽" | "₽/м³") => void;
  highlighted: EstimateGroupCode | null; onSelect: (code: EstimateGroupCode) => void;
}): JSX.Element;
export function PriceFormation({ economics }: { economics: BlockEconomics }): JSX.Element;
export function EconomicsTotals({ economics }: { economics: BlockEconomics }): JSX.Element;
export function EconomicsSidebar(props: {...все выше}): JSX.Element;   // <aside className="economics-sidebar">
```

`CostStructureDonut`: `<svg viewBox="0 0 200 200" role="img" aria-labelledby>`; сегменты из `donutSegments`; центр — `money(costPerM3)` / «₽/м³» / «Себестоимость»; hover — `<title>` внутри `<path>` и всплывающая подпись (`amount`, `perM3`, `share`); клик — `onSelect(code)`; выделенный сегмент — `stroke` толще, остальные `opacity .55`; легенда `<ol>` со строками «цвет · название · % · ₽/м³»; под ней `<table className="sr-only">` с теми же числами. Переключатель «₽ | ₽/м³» меняет числа легенды. `PriceFormation`: лестница из `markup` и `price_per_m3` в порядке `Себестоимость → + ОХР (x%) → Итого с ОХР → + Рентабельность (y%) → Цена без НДС → + НДС (z%) → Цена с НДС`; последняя строка `.strong` с зелёным фоном. `EconomicsTotals`: четыре плашки «Себестоимость, ₽», «Цена без НДС, ₽», «Цена без НДС, ₽/м³», «Цена с НДС, ₽/м³». `PricePanel.tsx` больше не нужен (маржинальная цена и коридор переезжают на вкладку «Ресурсы»).

- [ ] **Шаг 1: Падающий тест**

```tsx
// CostStructureDonut.test.tsx
it("рисует по сегменту на непустой раздел и зовёт onSelect по клику", async () => {
  const onSelect = vi.fn();
  render(<CostStructureDonut groups={buildEstimate(economicsFixture())} costPerM3={93.5} unit="₽/м³" onUnitChange={() => {}} highlighted={null} onSelect={onSelect} />);
  const segments = screen.getAllByRole("button", { name: /Взрывчатые материалы|Бурение|Персонал/ });
  expect(segments.length).toBeGreaterThan(1);
  await userEvent.click(segments[0]);
  expect(onSelect).toHaveBeenCalledWith("EXPLOSIVES");
  expect(screen.getByRole("table", { hidden: true })).toBeInTheDocument();
});
it("доли легенды совпадают с итогами разделов", () => { ... expect(screen.getByText("60,0 %")) ... });
```

- [ ] **Шаг 2: Убедиться, что тест падает** — `npx vitest run src/pages/economics/sidebar`
- [ ] **Шаг 3: Реализация** по описанию; сегменты — `<path role="button" tabIndex={0} aria-label=…>` с `onKeyDown` Enter/Space.
- [ ] **Шаг 4: Тесты и сборка** — PASS.
- [ ] **Шаг 5: Коммит**

```bash
git add frontend/src/pages/economics/sidebar frontend/src/styles/economics.css
git commit -m "feat(frontend): сайдбар экономики — кольцо структуры, лестница цены, итоги"
```

---

## Задача 9: Шапка, сценарии, вкладки и сборка страницы

**Files:**
- Create: `frontend/src/pages/economics/EconomicsHeader.tsx` (+ `.test.tsx`), `EconomicsTabs.tsx`, `ResourcesTab.tsx`, `HistoryTab.tsx`
- Modify: `frontend/src/pages/economics/BlockEconomicsPage.tsx` (переписать), `PassportStrip.tsx`, `frontend/src/styles.css`, `frontend/src/styles/economics.css`, `frontend/src/app/AppShell.tsx:139` (проброс `onOpenDrilling`)
- Delete: `ParametersPanel.tsx`, `NomenclaturePanel.tsx`, `CrewEditor.tsx`, `PricePanel.tsx` (после того как ничто их не импортирует; дубликаты « 2.tsx» не трогать)
- Test: `frontend/src/pages/economics/BlockEconomicsPage.test.tsx`

**Interfaces:**

```tsx
export function EconomicsHeader(props: {
  context: { site: string; passport: string; revision: string };
  drafts: Draft[]; runs: EconomicsRunSummary[]; activeId: string;
  onSelectDraft: (id: string) => void; onOpenRun: (runId: string) => void;
  dirty: boolean; onSave: (name: string) => void; onDuplicate: () => void;
  exportUrl: string | null;    // null — черновик не сохранён
  busy: boolean; status: string; error: string;
}): JSX.Element;

export type EconomicsTab = "estimate" | "structure" | "resources" | "sensitivity" | "compare" | "history";
export function EconomicsTabs({ active, onChange }: {...}): JSX.Element;   // role="tablist", стрелки влево/вправо
```

Шапка: `h1` «Экономика блока» + плашка «Черновик · не сохранено» (при `dirty`) или «Сохранён как «…»»; строка контекста «Объект · Паспорт вер. N · Ревизия M от даты»; селектор `<select aria-label="Сценарий">` с `optgroup` «Черновики» и «Сохранённые сценарии»; кнопки «Сохранить» (`primary-button`, при нажатии — имя из `prompt`-подобного инлайн-поля: поле имени появляется рядом с кнопкой, Enter сохраняет), «Дублировать», «XLSX» (`<a href={exportUrl} download>` или `disabled` с `title="Сначала сохраните сценарий"`).

`BlockEconomicsPage` (новая структура):

```
state: passports, selectedPassport, defaults, drafts: Draft[], activeId, results, resultsForIds,
       runs, tab, expanded: Set<EstimateGroupCode>, highlighted, busy, error, status
эффекты: как сейчас (загрузка паспортов, defaults, debounce-пересчёт вариантов, смена пакета)
действия: patchActive (помечает грязным по isDirty), saveRun → markSaved, duplicate, openRun (api.blockEconomics.run(id) → draftFromRun), 
          selectGroupFromChart (expanded.add + scrollIntoView + highlighted на 1.5 с)
раскладка:
  <EconomicsHeader/>
  <PassportStrip compact/>            — без имени сценария и кнопки; плашки: объём, погонаж, скважины, средний расход ВВ (explosive_kg / drilling_m, кг/м), дата паспорта
  <div class="economics-workspace">
    <div class="economics-main">
      <EconomicsTabs/>
      tab === "estimate"   → <EstimateBuilder renderGroup={renderEstimateGroup}/>   // см. renderEstimateGroup ниже
      tab === "structure"  → <VariantTabs/> + <CostStructure results/>   (бумажная группировка и колонки вариантов, как сейчас)
      tab === "resources"  → <ResourcesTab economics/>  (natural.values + lineage таблицей, capacity, ModelWarnings, маржинальная цена и коридор)
      tab === "sensitivity"→ <SensitivityTable/>
      tab === "compare"    → <RunsCompare/>
      tab === "history"    → <HistoryTab runs onOpen={openRun}/>
    </div>
    <EconomicsSidebar/>                — sticky: top = высота полосы паспорта + 14px
  </div>
```

`renderEstimateGroup` — одна функция, маршрутизирующая раздел на его редактор (все семь кодов `EstimateGroupCode` один в один с редакторами задачи 7):

```tsx
function renderEstimateGroup(group: EstimateGroup): ReactNode {
  const common = { group, params: activeVariant!.parameters, defaults: defaults!, economics: activeEconomics, volume, canEdit, onChange: patchActive };
  switch (group.code) {
    case "EXPLOSIVES": return <ExplosivesSection {...common} />;
    case "DRILLING": return <DrillingSection {...common} onOpenDrillingPage={onOpenDrilling} />;
    case "LABOR": return <LaborSection {...common} />;
    case "EQUIPMENT": return <EquipmentSection {...common} />;
    case "FUEL": return <FuelSection {...common} />;
    case "SERVICES": return <ServicesSection {...common} operations={defaults!.operations} busyCode={movingService} onMove={moveServiceToReference} />;
    case "FIXED": return <FixedCostsSection {...common} />;
  }
}
```

Ошибка пересчёта показывается баннером над таблицей; прежний `results` остаётся на экране, форма не сбрасывается. `PassportStrip` теряет пропсы `runName/onRunName/onSave/saveDisabled/status`, плашки берутся из `passportSummary.ts` (добавить «Средний расход ВВ» = `explosive_kg / drilling_m`, кг/м, и «Паспорт от …» из `created_at`).

`BlockEconomicsPage` принимает новый пропс `onOpenDrilling: () => void` (сигнатура как у существующего `onOpenEconomics` в `CalcPage`) и пробрасывает его в `DrillingSection` как `onOpenDrillingPage`. В `AppShell.tsx:139` заменить `{page === "Экономика" && <BlockEconomicsPage passportId={economicsPassportId} />}` на `{page === "Экономика" && <BlockEconomicsPage passportId={economicsPassportId} onOpenDrilling={() => setPage("Бурение")} />}` — тот же паттерн, что `sendToDesign`/`openEconomics` (`AppShell.tsx:55-61`).

CSS: `.economics-workspace { display:grid; grid-template-columns:minmax(0,1fr) 340px; gap:16px }`, при `max-width:1280px` — `300px`, при `max-width:1050px` — одна колонка, сайдбар под сметой, `position:static`; таблица сметы в `.table-scroll` с `min-width: 960px`. Удалить из `styles.css` мёртвые правила `.block-economics-parameters`, `.block-economics-nomenclature`, `.crew-editor*`, `.price-panel-secondary`, `.price-ladder*` (последние переезжают в `economics.css` под `PriceFormation`).

- [ ] **Шаг 1: Падающие тесты страницы**

```tsx
// BlockEconomicsPage.test.tsx
// @vitest-environment jsdom
vi.mock("../../api/endpoints", () => ({ api: { economics: { technicalPassports: vi.fn(), revisions: vi.fn(), referenceSnapshot: vi.fn() }, blockEconomics: { modelDefaults: vi.fn(), runs: vi.fn(), variants: vi.fn(), saveRun: vi.fn(), run: vi.fn(), sensitivity: vi.fn(), compare: vi.fn(), exportUrl: (id: string) => `/x/${id}` } } }));

it("смета строится из ответа API: семь разделов и итог себестоимости", async () => {
  ...mock returns defaultsFixture(), [] runs, { variants: [{ name, economics: economicsFixture() }] }
  renderWithWorkspace(<BlockEconomicsPage passportId="P1" />);
  expect(await screen.findByRole("heading", { name: "Экономика блока" })).toBeInTheDocument();
  expect(await screen.findByText("Взрывчатые материалы")).toBeInTheDocument();
  expect(screen.getByText("Постоянные и общепроизводственные расходы")).toBeInTheDocument();
});
it("смена ВВ вызывает пересчёт и обновляет сумму строки", async () => {
  variants.mockResolvedValueOnce(first).mockResolvedValueOnce(second);   // во втором ответе другая сумма
  ...выбрать «Сферит ДТ» в комбобоксе
  await waitFor(() => expect(variants).toHaveBeenCalledTimes(2));
  expect(variants.mock.calls[1][1][0].parameters.nomenclature.EXPLOSIVE).toBe("SFERIT");
  expect(await screen.findByText("1 500 000")).toBeInTheDocument();
  expect(screen.getByText("Черновик · не сохранено")).toBeInTheDocument();
});
it("сохранение сценария создаёт прогон и снимает признак черновика", async () => {
  saveRun.mockResolvedValue({ id: "R1", ... }); runs.mockResolvedValue([summary]);
  await user.click(screen.getByRole("button", { name: "Сохранить" }));
  await user.type(screen.getByRole("textbox", { name: "Имя сценария" }), "Базовый{Enter}");
  await waitFor(() => expect(saveRun).toHaveBeenCalledWith("P1", expect.any(Object), "Базовый"));
  expect(await screen.findByText(/Сохранён как «Базовый»/)).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "XLSX" })).toHaveAttribute("href", "/x/R1");
});
it("ошибка пересчёта не стирает форму и прежние числа", async () => {
  variants.mockResolvedValueOnce(first).mockRejectedValueOnce(new Error("Сервис недоступен"));
  ...правка
  expect(await screen.findByRole("alert")).toHaveTextContent("Сервис недоступен");
  expect(screen.getByRole("combobox", { name: "Основное ВВ" })).toHaveTextContent("Сферит ДТ");
  expect(screen.getByText("1 335 382")).toBeInTheDocument();
});
it("клик по сегменту диаграммы раскрывает раздел", async () => { ... expect(section).toHaveAttribute("aria-expanded", "true") });
it("ссылка «Перейти к расчёту бурения» зовёт onOpenDrilling без изменения параметров", async () => {
  const onOpenDrilling = vi.fn();
  renderWithWorkspace(<BlockEconomicsPage passportId="P1" onOpenDrilling={onOpenDrilling} />);
  await user.click(await screen.findByRole("button", { name: "Перейти к расчёту бурения (Бурение) →" }));
  expect(onOpenDrilling).toHaveBeenCalledTimes(1);
  expect(variants).not.toHaveBeenCalledTimes(3);   // навигация не запускает лишний пересчёт
});
it("вкладки «Чувствительность», «Сравнение сценариев» и «История» открываются", async () => { ... });
```

`window.HTMLElement.prototype.scrollIntoView = vi.fn()` в `setup.ts` (jsdom его не реализует).

- [ ] **Шаг 2: Убедиться, что тесты падают** — `npx vitest run src/pages/economics/BlockEconomicsPage.test.tsx`
- [ ] **Шаг 3: Реализация** шапки, вкладок, страницы; удаление неиспользуемых панелей; правка `PassportStrip` и `passportSummary.ts` (+ тест на «средний расход ВВ»: 33 000 кг / 2 079 м = 15,9 кг/м; при нулевом погонаже — «—»).
- [ ] **Шаг 4: Тесты, типы, сборка** — `cd frontend && npm test && npm run build`, PASS. Проверить, что `AppShell.tsx` по-прежнему рендерит `BlockEconomicsPage`, `EconomicsPage`, `DrillingPage` без изменений.
- [ ] **Шаг 5: Ручная проверка в браузере** (dev-сервер из `.claude/launch.json`, учётка из памяти проекта): ширины 1440 и 1920 — сайдбар липкий, шапка колонок липкая; 1024 — сайдбар под сметой, таблица прокручивается горизонтально; клавиатура: Tab по комбобоксам, Enter/Escape; экран без паспортов — прежнее сообщение.
- [ ] **Шаг 6: Коммит**

```bash
git add frontend/src/pages/economics/BlockEconomicsPage.tsx frontend/src/pages/economics/BlockEconomicsPage.test.tsx frontend/src/pages/economics/EconomicsHeader.tsx frontend/src/pages/economics/EconomicsHeader.test.tsx frontend/src/pages/economics/EconomicsTabs.tsx frontend/src/pages/economics/ResourcesTab.tsx frontend/src/pages/economics/HistoryTab.tsx frontend/src/pages/economics/PassportStrip.tsx frontend/src/pages/economics/passportSummary.ts frontend/src/pages/economics/passportSummary.test.ts frontend/src/test/setup.ts frontend/src/test/render.tsx frontend/src/styles.css frontend/src/styles/economics.css frontend/src/app/AppShell.tsx
git rm frontend/src/pages/economics/ParametersPanel.tsx frontend/src/pages/economics/NomenclaturePanel.tsx frontend/src/pages/economics/CrewEditor.tsx frontend/src/pages/economics/PricePanel.tsx
git commit -m "feat(frontend): экономика блока как смета-конструктор — шапка сценариев, вкладки, сайдбар"
```

---

## Задача 10: Полировка взаимодействий и доступности

**Files:**
- Modify: `frontend/src/pages/economics/estimate/*.tsx`, `sections/*.tsx`, `styles/economics.css`

- [ ] **Шаг 1:** Стабильность таблицы при пересчёте: числовые ячейки фиксированной ширины (`min-width` + `tabular-nums`), во время `busy` — значения не заменяются на «…», только `aria-busy` и лёгкое затемнение; ответ с другим набором строк не сбрасывает `expanded`.
- [ ] **Шаг 2:** Debounce 300 мс сохраняется; для `NumericInput` в строках — то же (уже так: правка параметров → эффект пересчёта).
- [ ] **Шаг 3:** Фокус: видимая обводка `:focus-visible` (`box-shadow: 0 0 0 3px rgba(45,117,86,.25)`) у комбобоксов, кнопок разделов, сегментов диаграммы, пунктов меню; `aria-expanded` у заголовков разделов; `aria-live="polite"` у статуса сохранения; иконки кнопок «⋯», «+» с `aria-label`.
- [ ] **Шаг 4:** Контраст бейджей и подписей ≥ 4,5:1 (проверить пары цветов из задачи 6; подпись `#6e7b75` на белом — 4,6:1, оставить).
- [ ] **Шаг 5:** «Развернуть всё / Свернуть всё» и запоминание раскрытых разделов в `sessionStorage` (`blastex.economics.expanded`), обёрнуто в `try/catch`.
- [ ] **Шаг 6:** Тесты и сборка — PASS; коммит `fix(frontend): устойчивость таблицы сметы при пересчёте и доступность конструктора`.

---

## Задача 11: Сквозные проверки по списку постановки

Сопоставление пунктов §23 постановки с тестами (все должны существовать и проходить):

| № | Проверка | Тест |
| --- | --- | --- |
| 1 | смета строится из данных API | `BlockEconomicsPage.test.tsx` «семь разделов» |
| 2 | смена номенклатуры ВВ | `ExplosivesSection.test.tsx` |
| 3 | цены и итоги обновляются после смены | `BlockEconomicsPage.test.tsx` «смена ВВ вызывает пересчёт» |
| 4 | переключение свой/субподряд | `DrillingSection.test.tsx` |
| 5 | источник ставки собственного бурения | `DrillingSection.test.tsx` («Расчёт бурения» + lineage) |
| 6 | субподряд принимает/выбирает тариф | `DrillingSection.test.tsx` + `tests/test_model_drilling.py` |
| 7 | добавить/изменить должность | `LaborSection.test.tsx` |
| 8 | выбор техники | `EquipmentSection.test.tsx` |
| 9 | диаграмма по итогам разделов | `CostStructureDonut.test.tsx`, `donut.test.ts` |
| 10 | сохранение сценария | `BlockEconomicsPage.test.tsx` «сохранение сценария» + `tests/test_api_block_economics.py::test_run_is_saved_listed_and_read_back` |
| 11 | ошибка не стирает форму | `BlockEconomicsPage.test.tsx` «ошибка пересчёта» |
| 12 | прежние маршруты экономики | `tests/test_api_block_economics.py`, `tests/test_api_variants.py`, `tests/test_api_economics.py` без изменений проходят |

- [ ] **Шаг 1:** `cd frontend && npm test && npm run build`
- [ ] **Шаг 2:** `.venv/bin/python -m pytest -q`
- [ ] **Шаг 3:** Ручная проверка в браузере против бэкенда с реальной ревизией: выбрать ВМ, переключить субподряд, ввести ставку, сохранить тариф (под `reference_editor`), убедиться, что на странице «Справочники» появилась запись и новая ревизия; сохранить сценарий, открыть его из «Истории», сравнить два прогона, выгрузить xlsx.

---

## Задача 12: Документация

**Files:**
- Create: `Docs/BLOCK_ECONOMICS_UI.md`
- Modify: `README.md:659-690` («Экономика блока»: путь пользователя и ссылка на новый документ; таблица маршрутов — новый `POST /economics/subcontract-rates/to-reference`), `Docs/COST_MODEL.md` (раздел «Происхождение величин»: поля `quantity_origin`/`price_origin` и правила простановки; «Субподряд бурения»: приоритет ручной ставки → выбранного тарифа → первого по операции), `Docs/README-DOCS.md` (ссылка), `Docs/design/README.md` (описание `economics_block_concept.png`)

`Docs/BLOCK_ECONOMICS_UI.md` — разделы: «Устройство страницы» (шапка, полоса паспорта, вкладки, сайдбар); «Смета-конструктор» (семь инженерных разделов и правило отнесения строк; что редактируется, что только читается); «Бурение: свои силы и субподряд» (откуда ставка, бейдж «Расчёт бурения», выдвижная панель, явное сохранение тарифа); «Выбор из справочников» (комбобокс, опубликованная ревизия, неактивные записи не показываются — `active_items`); «Бейджи происхождения» (таблица значений); «Структура себестоимости» (кольцо, легенда, связь с разделами); «Сценарии» (черновик, сохранение, дублирование, история, неизменяемость прогонов, xlsx); «Ограничения» (техника — четыре роли модели, количество единиц не параметр; связь с калькулятором «Бурение» V1 не реализована); «Изменения API» (поля и маршрут из задач 1–3).

- [ ] **Шаг 1:** Написать документ и правки; проверить ссылки.
- [ ] **Шаг 2:** Коммит `docs: смета-конструктор экономики блока`; открыть PR «Экономика блока: смета-конструктор», пройти `/code-review`.

---

## Самопроверка плана

- **Покрытие постановки.** Шапка (задача 9), паспорт read-only (9), рабочая область 70/30 (9), колонки таблицы (6), семь разделов + лестница (5, 8), ВМ с поиском и «+ Добавить материал» (6, 7), бейджи (1, 4), бурение два режима + источник ставки + явное сохранение тарифа (2, 3, 7), бригада НОРМАТИВ/РУЧНОЙ (7), техника (7, ограничение зафиксировано), сайдбар липкий с кольцом/лестницей/итогами (8, 9), вкладки (9), сценарии и грязное состояние (5, 9), debounce/ошибки/стабильность (9, 10), справочники без хардкода (7), адаптивность (9), доступность (8, 10), тесты (11), документация (12).
- **Не покрыто намеренно:** произвольный список техники с количеством единиц (модель не поддерживает) и синхронизация чисел с калькулятором «Бурение» V1 (навигация без переноса чисел — решение владельца, задачи 7 и 9) — оба зафиксированы в «Решениях и допущениях» и в документации ограничений.
- **Согласованность имён:** `ValueOrigin`, `quantity_origin`/`price_origin`, `subcontract_rate_code`/`subcontract_rate_rub`, `EstimateGroupCode`, `buildEstimate`, `donutSegments`, `Draft`/`isDirty`, `CatalogSelect`, `OriginBadge` используются одинаково во всех задачах.
