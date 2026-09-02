# TASK-007 — Модель себестоимости БВР и вкладка «Экономика»

## Статус

- Приоритет: P0.
- Зависит от: TASK-006 (схемы и разделы справочников).
- Статус требований: согласовано; методика по доменам (ФОТ, бурение, юнит, материалы) зафиксирована в `Docs/ADR-001-economics-model.md`, поля справочников — в `Docs/REFERENCES_MODEL.md`.
- Обязательное условие: не дублировать движок Cost V2. Новый код считает **натуральные величины** (нормы), Cost V2 умножает их на цены, распределяет постоянные затраты и раскладывает по слоям. Технологический расчёт (`Blast.py`, `/blast/geometry`, техпаспорт) не меняется.

## 1. Контекст и цель

BlastEX считает технический паспорт блока (сетка, глубина, удельный расход, погонаж, масса ВВ) и имеет экономику юнита Cost V2 (операции, пакеты, правила затрат, слои себестоимости, распределение). Между ними нет слоя, который превращал бы паспорт в смены станка, человеко-смены бригады, литры ДТ, коронки и тонно-километры по инженерным формулам сметы. Из-за этого экономика блока сейчас считается только тем, что пользователь ввёл руками в правила затрат.

Цель: вкладка «Экономика», которая по выбранному техническому паспорту и пакету работ показывает две цены блока (маржинальную и полную), структуру затрат по слоям, сравнение сценариев и чувствительность — за секунды, без ручного ввода норм. Владелец использует её для ценообразования в тендерах.

## 2. Принятые решения

- Архитектура «нормы в коде, цены в данных» (ADR-001, вариант 3). Новый пакет `cost/model/` — чистые функции без доступа к БД и HTTP.
- Вход модели — `TechnicalDriverSnapshot` (уже есть в `cost/v2/technical_adapter.py`) + пакет работ + параметры модели + `ReferenceSnapshot`. Геометрия на вкладке read-only, с `lineage`.
- Выход модели — список `CostLine` Cost V2 с заполненными `layer`, `operation_code`, `cost_item_code`, `formula`; итоги по слоям `variable → project_direct → production → full`; цена м³ на каждом слое; надбавки ОХР → рентабельность → НДС отдельным шагом.
- Сценарии сметы Excel (четыре столбца) не воспроизводятся: сухой/обводнённый — из паспорта, передел — из пакета.
- Постоянные затраты юнита и косвенный персонал распределяются **только по плановому объёму юнита** (параметр модели, по умолчанию из `production_units`).
- Постоянные затраты техники (амортизация, страховка, постоянная часть ФОТ экипажа) — по плановым сменам техники (параметр модели, по умолчанию `norm_shifts_per_month` типа техники).
- Смены станка, СЗМ, доставщика и численность их экипажей **выводятся** из погонажа / массы и производительности. Смены взрывной бригады — норматив `norm_shifts / norm_operations` с ручной поправкой на блок.
- ФОТ аддитивный: постоянная часть через нормативы должности + сделка по драйверу должности; взносы, НС, резерв — из `organization_rates`; НДФЛ-пересчёт только при `salary_basis = NET`.
- Каждый прогон сохраняется как снимок: паспорт, пакет, ревизия справочников, параметры модели, результат. Сравнение — между снимками.
- Чувствительность — детерминированный перебор ±10 % по фиксированному списку параметров, без оптимизации.
- Регрессии «Тарифной сетки» из Excel не переносятся.

## 3. Целевой пользовательский процесс

1. На «Расчёте БВР» пользователь нажимает «Экономика» у сохранённого технического паспорта — открывается вкладка с этим паспортом и пакетом, выбранным на первой вкладке.
2. Слева — параметры модели: объект работ, станок, состав бригады (из шаблона пакета, с правкой численности и смен), плановый объём юнита, плановые смены станка/СЗМ, ревизия справочников, исполнитель бурения (свой / субподряд), ОХР / рентабельность / НДС.
3. В центре — две цены на м³ (маржинальная и полная) крупно, под ними цена с прибылью и с НДС; структура затрат по слоям и по статьям с формулами по клику; предупреждения модели (нет нормы бурения для станка на этой породе, склад не вмещает план, пакет не содержит операцию должности).
4. «Сохранить сценарий» — снимок с именем. Панель сравнения показывает до трёх снимков рядом с дельтой по статьям и по цене м³.
5. «Чувствительность» — таблица: параметр, −10 %, +10 %, Δ цены м³; отсортирована по модулю влияния.
6. Экспорт xlsx текущего сценария в структуре разделов сметы (для заказчика, которому привычен Excel).

## 4. Границы MVP

### 4.1. Входит в MVP

- `cost/model/`: labor, drilling, logistics, equipment, unit allocation, markup, sensitivity, engine;
- API: расчёт, сохранение/список/сравнение снимков, чувствительность, экспорт xlsx;
- вкладка «Экономика» с параметрами, двумя ценами, структурой, сравнением и чувствительностью;
- кнопка «Экономика» на `CalcPage`;
- регрессионный тест на числах сметы «Смета новая от 29.01.2026.xlsx» (блок 60 000 м³, сетка 3,5×3,5 и 4,5×4,5, глубина 11,5, перебур 1,2).

### 4.2. Не входит в MVP

- помесячный план юнита (один норматив);
- оптимизация параметров и Парето (остаётся в `design/optimization`, отключено флагом TASK-008);
- многовалютность, прогрессивный НДФЛ;
- импорт сметы Excel как сценария;
- изменения технологического расчёта и паспорта.

## 5. Модель

### 5.1. Типы

```python
# cost/model/inputs.py
@dataclass(frozen=True)
class ModelParameters:
    package_code: str
    site_code: str
    reference_revision_id: str
    unit_plan_volume_m3: Decimal          # план юнита, м³/мес
    rig_code: str | None                  # equipment_types (DRILL_RIG)
    rig_plan_shifts: Decimal | None       # по умолчанию norm_shifts_per_month
    szm_code: str | None
    crew: tuple[CrewMember, ...]          # (position_code, headcount, shifts_per_block | None)
    drilling_executor: Literal["OWN", "SUBCONTRACTOR"] = "OWN"
    overhead_rate: Decimal | None = None  # None → organization_rates
    target_margin_rate: Decimal | None = None
    vat_rate: Decimal | None = None

@dataclass(frozen=True)
class NaturalDrivers:                      # расширение TechnicalDriverSnapshot.physical
    values: dict[str, Decimal]            # rig_shifts, crew_shifts[position], diesel_l, bits_pcs, trip_km, vm_tkm, ...
    lineage: dict[str, str]               # driver → формула/источник нормы
    warnings: tuple[str, ...]

@dataclass(frozen=True)
class BlockEconomics:
    lines: tuple[CostLine, ...]
    layer_totals: dict[CostLayer, Decimal]
    price_per_m3: dict[str, Decimal]      # marginal, full, with_margin, with_vat
    natural: NaturalDrivers
    capacity: tuple[CapacityWarning, ...] # склад, станок, СЗМ
    warnings: tuple[str, ...]
```

### 5.2. Модули и формулы

`cost/model/labor.py` — по каждой должности состава бригады, если `operation_code` входит в пакет:

```
rate_per_shift   = fixed_monthly_rub / norm_shifts_per_month
shifts_per_block = crew.shifts_per_block ?? derived(operation) ?? norm_shifts_per_month / norm_operations_per_month
fixed_block      = rate_per_shift × shifts_per_block × headcount
piece_block      = piece_rate_rub × driver[piece_driver] / piece_unit
accrued          = fixed_block + piece_block            (÷ (1 − income_tax_rate), если salary_basis = NET)
contributions    = accrued × (social_contribution_rate + injury_insurance_rate)
vacation_reserve = (accrued + contributions) × vacation_reserve_rate
per_diem         = shifts_per_block × headcount × (per_diem_rub + lodging_rub), если per_diem_applies и site.is_remote
```

`derived(operation)`: для `PRODUCTION_DRILLING` — смены станка; для `BULK_CHARGING_SZM` — смены СЗМ; для `VM_DELIVERY_SITE` — смены доставщика; иначе `None`. Численность экипажа техники: `ceil(equipment.norm_shifts_per_month / position.norm_shifts_per_month)`, если в составе бригады не задана явно.

`cost/model/drilling.py`:

```
condition        = pick(drilling_conditions, rig, rock_code, site_code)   # приоритет: станок+карьер → станок+порода → станок
v_commercial     = condition.tech_speed_m_per_h × (shift_hours − condition.unproductive_h_per_shift)
rig_shifts       = drilling_m / v_commercial
maintenance      = rig_shifts × equipment_type.maintenance_ratio
plan_metres      = rig_plan_shifts × v_commercial
variable_per_m   = Σ price_i / life_i (коронка, ППУ, оснастка) + casing_m_per_m × price_casing
                 + fuel_l_per_m × diesel_price_l + spare_parts + consumables
fixed_per_m      = (depreciation_month + insurance_month + maintenance_cost_month) / plan_metres
```

Строки: материалы бурения (`variable`), ДТ бурения (`variable`), амортизация и страховка станка (`project_direct`, через `rig_shifts × per_shift`), ТОиР (`project_direct`). При `drilling_executor = SUBCONTRACTOR` вместо всего этого — одна строка `subcontract_rates × drilling_m`, а собственные постоянные станка уходят в «нераспределённые затраты юнита» с предупреждением.

`cost/model/logistics.py` — рейсы и смены СЗМ/доставщика из массы и грузоподъёмности; `vm_tkm = mass_t × distance_from_warehouse_km` для патронов и НСИ, `component_tkm` для насыпных; `trip_km` для мобилизации по `blocks_per_mobilization`; ДТ транспорта `km × fuel_l_per_km × price`.

`cost/model/equipment.py` — амортизация и страховка за смену для СЗМ, доставщика, тягача: `monthly / norm_shifts_per_month × shifts`; техосмотр и медосмотр `per_shift × shifts`; ТОиР по `maintenance_mode`.

`cost/model/unit.py` — постоянные затраты юнита: `unit_fixed_costs` (для `INDIRECT_LABOR` — из `labor_rates` × headcount с взносами) + аренда склада (`resource_pools` с ёмкостью: требуемая площадь `⌈max(nsi_month/300, cartridge_kg_month/220)⌉` по плану) → `share = block_volume / unit_plan_volume_m3` → строки слоя `production`.

`cost/model/markup.py` — `full_cost → × (1 + overhead_rate) → × (1 + target_margin_rate) → × (1 + vat_rate)`; четыре цены м³.

`cost/model/sensitivity.py` — параметры: цена основного ВВ, `q` (через пересчёт паспорта не входит — берётся `explosive_kg` ±10 %), `drilling_m`, `unit_plan_volume_m3`, `rig_plan_shifts`, численность бригады, цена ДТ, расценка сделки. Для каждого — два прогона `engine.compute` и Δ полной цены м³.

`cost/model/engine.py` — `compute_block_economics(snapshot, package, params, references) -> BlockEconomics`. Порядок: natural drivers → строки по модулям → распределение юнита → итоги по слоям → надбавки. Все константы — только из справочников; при отсутствии записи — предупреждение и нулевая строка, не исключение.

### 5.3. Хранение

Таблица `blastex.economics_runs`: `id`, `organization_id`, `name`, `technical_passport_id`, `package_code`, `reference_revision_id`, `parameters` (JSON), `result` (JSON: lines, layer_totals, price_per_m3, warnings), `created_at`, `created_by`. Индекс по `(organization_id, technical_passport_id)`.

## 6. API

- `POST /api/v1/economics/block-economics` — `{technical_passport_id | block, package_code, parameters}` → `BlockEconomics`. Без сохранения.
- `POST /api/v1/economics/runs` — то же + `name` → сохранённый снимок.
- `GET /api/v1/economics/runs?technical_passport_id=` — список.
- `GET /api/v1/economics/runs/{id}`.
- `POST /api/v1/economics/runs/compare` — `{run_ids: [...]}` → строки, выровненные по `cost_item_code`, с дельтами (использовать `_delta_view` V2).
- `POST /api/v1/economics/block-economics/sensitivity` — таблица чувствительности.
- `GET /api/v1/economics/runs/{id}/export.xlsx` — openpyxl, листы «Итоги», «Структура», «Натуральные показатели», «Параметры».
- `GET /api/v1/economics/model-defaults?technical_passport_id=&package_code=` — параметры по умолчанию (шаблон бригады, станок объекта, план юнита, ставки организации).

Все под `require_internal_access`; сохранение — `require_internal_access` (не `reference_editor`: сценарии считает любой пользователь).

## 7. Файлы

Создать:

- `cost/model/__init__.py`, `inputs.py`, `labor.py`, `drilling.py`, `logistics.py`, `equipment.py`, `unit.py`, `markup.py`, `sensitivity.py`, `engine.py`, `export_xlsx.py`
- `migrations/versions/20260903_0005_economics_runs.py`
- `api/routers/block_economics.py`, `api/schemas/block_economics.py`
- `frontend/src/pages/economics/BlockEconomicsPage.tsx`
- `frontend/src/pages/economics/ParametersPanel.tsx`, `CrewEditor.tsx`, `PricePanel.tsx`, `CostStructure.tsx`, `RunsCompare.tsx`, `SensitivityTable.tsx`, `ModelWarnings.tsx`
- `frontend/src/types/blockEconomics.ts`
- `tests/test_model_labor.py`, `test_model_drilling.py`, `test_model_logistics.py`, `test_model_unit.py`, `test_model_engine.py`, `test_model_regression_smeta_2026_01.py`, `test_api_block_economics.py`
- `tests/fixtures/smeta_2026_01/` — справочники и паспорт для регрессионного теста

Изменить:

- `cost/v2/repository.py`, `cost/v2/db_repository.py` — методы для `economics_runs`
- `cost/v2/technical_adapter.py` — добавить в `physical` массу патронов и НСИ раздельно (`cartridge_kg`, `bulk_kg`, `downhole_nsi`, `surface_nsi`), если их ещё нет
- `api/main.py` — подключить роутер
- `frontend/src/app/AppShell.tsx` — пункт «Экономика» ведёт на `BlockEconomicsPage`; существующая `EconomicsPage` (экономика юнита) переезжает в подпункт «Экономика юнита»
- `frontend/src/pages/CalcPage.tsx` — кнопка «Экономика» у паспорта
- `frontend/src/api/endpoints.ts`
- `README.md`, `Docs/` — `COST_MODEL.md` (граница «норма / цена», слои, распределение)

## 8. Этапы реализации

### Этап A. Натуральные величины

1. `inputs.py`, `NaturalDrivers`, выбор условия бурения `pick()` с `lineage`.
2. `drilling.py` — смены станка, план метров, расход на метр; тесты на 12 м/ч, 11 ч, 1 ч → 120 м/смену; 60 000 м³ при выходе 4,3 м³/п.м. → погонаж и смены.
3. `logistics.py` — рейсы, тонно-километры, мобилизация.
4. `labor.py` — по формулам §5.2; тесты: взрывник 55 000 / 21 / 10 / 700 → 5 500 + 700·V/1000; бурильщик 60 000 / 15 при 13,3 сменах станка; косвенная должность в прямом расчёте не появляется; должность без операции в пакете не появляется.

### Этап B. Деньги и слои

1. `equipment.py`, `unit.py` (в том числе склад с ёмкостью и ступенькой), `markup.py`.
2. `engine.py`: сборка `CostLine` с `layer`, итоги, четыре цены. Все предупреждения — в `warnings`, не исключения.
3. Регрессионный тест на смете 29.01.2026: сид справочников из Excel в `tests/fixtures/smeta_2026_01/`; сравнить итоги по разделам 1.1, 1.2, 2.3, 2.4, 2.5 с Excel с допуском 1 %; расхождения по 2.1, 2.2, 2.6 (константы Excel против модели) задокументировать в тесте с причиной.

### Этап C. Хранение и API

1. Миграция `economics_runs`, методы репозитория (in-memory и PostgreSQL).
2. Роутер: расчёт, снимки, сравнение, чувствительность, экспорт, параметры по умолчанию.
3. Тесты API на in-memory репозитории.

### Этап D. Вкладка

1. `BlockEconomicsPage`: параметры слева (по `model-defaults`), результат в центре; пересчёт с debounce 300 мс при изменении параметра.
2. `PricePanel`: две цены крупно, с прибылью и с НДС мельче; `CostStructure`: слои → статьи → формула по клику.
3. `RunsCompare` и `SensitivityTable`.
4. Кнопка «Экономика» на `CalcPage`.

### Этап E. Документация

1. `Docs/COST_MODEL.md`; README — раздел «Экономика блока».
2. `CLAUDE.md`: «нормы — только в `cost/model/`, цены — только в справочниках; новая статья вида цена × драйвер — правило затрат, не код».

## 9. Критерии приёмки

- При изменении плана юнита с 600 000 до 400 000 м³ полная цена м³ растёт, маржинальная не меняется.
- При изменении плановых смен станка с 40 до 25 постоянная часть метра растёт на 60 %, численность бурильщиков падает с 3 до 2.
- Для пакета «Поставка ВМ франко-скважина» строки взрывников и бурения отсутствуют, предупреждений о них нет.
- Для станка без условия на породе блока модель берёт норму по умолчанию и пишет это в `lineage`; для станка без нормы по умолчанию — предупреждение и нулевые строки бурения.
- Аренда склада при плане, превышающем 10 м², даёт ступеньку и предупреждение с требуемой площадью.
- Субподряд бурения заменяет строки бурения одной ставкой и показывает нераспределённые постоянные станка.
- Регрессионный тест на смете проходит по разделам 1.1, 1.2, 2.3–2.5 с допуском 1 %.
- Сравнение двух снимков показывает дельту по каждой статье и по цене м³.
- Таблица чувствительности отсортирована по |Δ| и содержит все параметры из §5.2.
- Экспорт xlsx открывается в Excel, суммы разделов равны итогам вкладки.
- Вкладка на русском; все единицы измерения подписаны; геометрия read-only с ссылкой на паспорт.

## 10. Условия завершения

Задача закрыта, когда владелец на реальном паспорте блока может за пять минут: получить две цены м³; сравнить «гранулит против эмульсии» и «свой станок против субподряда»; увидеть, что при плане 400 000 м³ полная цена выше на X %; понять по таблице чувствительности, какие три параметра двигают цену сильнее всего; выгрузить xlsx заказчику.
