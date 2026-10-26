# TASK-010 PR 3b — ФОТ по методике в интерфейсе экономики блока: план реализации

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** сметчик переключает источник ФОТ экипажа бурения (ставки или методика), видит разбивку методики — темп, приведённые метры, `c_var`, постоянную и переменную часть, цену метра с подписью базы, обе доли в марже и график шкалы машиниста по рядам сервера — и предупреждение о доле, не раскрывая блок.

**Architecture:** бэкенд PR 3a уже отдаёт `BlockEconomics.payroll`; PR 3b добавляет в него шкалу и ряды графика (одна кривая — та, по которой посчитана премия, Т6) и подключает интерфейс: переключатель и строки в `LaborSection`, новый `PayrollBreakdown` с SVG-графиком в разделе «Персонал», чистая модель вида в `payrollModel.ts`. Две отложенные из 3a мелочи (чувствительность `PIECE_RATE` в режиме методики, смена объекта в подсказке скорости) закрываются здесь.

**Tech Stack:** React 19 + TypeScript, vitest + Testing Library (jsdom), чистый SVG без библиотек графиков; бэкенд — Python 3.13, Decimal, pydantic 2, pytest.

**Spec:** `Docs/specs/2026-09-13-task-010-payroll-decisions.md` (§5 «PR 3b», Т6, Т13, Т14; §2.1–§2.2); `Docs/plans/2026-10-25-task-010-pr3a-block.md` и `Docs/PAYROLL_MODEL.md` («Экономика блока») — что отдаёт бэкенд; `Docs/BLOCK_ECONOMICS_UI.md` — устройство страницы.

## Global Constraints

- Интерфейс строит формы по каталогу схем и не показывает пользователю JSON (CLAUDE.md, «Справочники экономики»); разделоспецифичных компонентов в формах справочников не заводить. `PayrollBreakdown` — часть страницы экономики блока, не формы справочника.
- График рисуется только по рядам и узлам из ответа сервера (`payroll.series`, `payroll.scale`); своей формулы кривой на клиенте нет (Т6).
- Числа форматируются через `money` и `amount` из `frontend/src/pages/economics/format.ts`; подписи — по-русски, без кодов драйверов и полей.
- Каждый класс разметки вкладки имеет правило в `frontend/src/styles/economics.css` (`cssCoverage.test.ts`); цвета — через переменные дизайн-токенов, как у соседних блоков.
- Режим `RATES` не меняет ни одной цифры: `tests/test_model_regression_smeta_2026_01.py` проходит без правок; прогон без ключа `payroll` в сохранённом результате (`undefined`) показывается как «методики нет», не падает.
- Происхождение строк — `price_origin = "PAYROLL"`, подпись «Расчёт ФОТ» уже есть в `origin.ts`, класс `.origin-payroll` — в `economics.css`.
- Предупреждение о доле — одно, общее: текст флага уже приходит в `economics.warnings` (Т13); блок «Модель сообщает» его показывает, `PayrollBreakdown` его не дублирует, а выводит краткий индикатор рядом с долей.
- `pytest`, `cd frontend && npx tsc -b && npx vitest run` — на чистом чекауте без iCloud-дублей.

## Review Focus

- `economics.payroll` равен `null` при выбранной методике (откат на ставки, субподряд): раздел не показывает прошлого графика и объясняет, где причина (блок «Модель сообщает»).
- Главная должность без шкалы или повременная (`scale = null`, `series` пуст): график не рисуется, остальная разбивка есть.
- Статусы доли `NOT_CHECKED`, `NO_MARGIN`, `NOT_APPLICABLE`: вместо процентов — короткое объяснение, не «0 %» и не `NaN`.
- Плановый темп выше потолка шкалы (строка f 17 / Ø 250: 236 м/см против 184,6): маркер темпа не выходит за область графика, ось растягивается.
- Субподряд: переключатель источника ФОТ недоступен с подсказкой; сохранённый `PAYROLL` при субподряде не теряется.
- Старые прогоны без `payroll_source` и без `payroll` открываются; сравнение прогонов (`/economics/runs/compare`, строки по `cost_item_code`) и столбцы вариантов (`buildEstimate` по каждому варианту) не падают, когда режимы ФОТ разные (задача 5, шаги 1b и 2).
- Узкая ширина (1024 px): разбивка и график не наезжают на колонки сметы.

## Структура файлов

| Файл | Ответственность |
|---|---|
| `cost/model/block_margin.py`, `api/schemas/block_economics.py` | в `payroll`: `scale`, `series`, `main_position_code` |
| `cost/model/sensitivity.py` | `PIECE_RATE` двигает и шкалы методики |
| `frontend/src/types/blockEconomics.ts` | типы `BlockPayroll` и вложенные, `BlockEconomics.payroll` |
| `frontend/src/pages/economics/payrollModel.ts` | чистая модель: подписи долей, статусы, геометрия графика |
| `frontend/src/pages/economics/PayrollChart.tsx`, `PayrollBreakdown.tsx` | график и свёрнутая разбивка |
| `frontend/src/pages/economics/sections/LaborSection.tsx` | переключатель источника, строки методики, вставка разбивки |
| `frontend/src/lib/referenceDerived.ts` | смена объекта в подсказке скорости |
| `frontend/src/styles/economics.css` | стили новых классов |
| `Docs/BLOCK_ECONOMICS_UI.md`, `Docs/PAYROLL_MODEL.md`, `frontend/src/pages/economics/EconomicsHelp.tsx` | описание и справка «?» |

---

### Task 1: Шкала и ряды графика в `BlockEconomics.payroll`

**Files:**
- Modify: `cost/model/block_margin.py` (`to_dict`; `DRILLING_OPERATION` импортируется из `cost/model/drilling.py` вместо дубля), `cost/model/block_payroll.py` (если нужны поля `BlockPayroll`), `api/schemas/block_economics.py` (`PayrollBlockSchema`)
- Test: `tests/test_model_block_payroll_margin.py`, `tests/test_api_block_economics.py`

**Interfaces:**
- Consumes: `payroll.scale_series(scale: Scale, pace: Decimal | None) -> tuple[ScalePoint, ...]` (`ScalePoint(pace, rate, per_shift)`), `BlockPayroll.main_scale`, `BlockPayroll.pace`.
- Produces: ключи `payroll.positions[].position_name: str` (название должности из справочника, `ReferenceItem.name`; пользователю коды не показываются), `payroll.main_position_code: str | None`, `payroll.scale: {scale_type, gamma, norm_per_shift, rate_norm, ceiling_per_shift, rate_ceiling} | None`, `payroll.series: [{pace, rate, per_shift}]` (пусто при `scale = None`) — те же поля и единицы, что у `_premium_dict`/`scale_series` в превью; `PayrollPositionSchema.position_name`, `PayrollScaleSchema`, `PayrollSeriesPointSchema`; `PayrollBlockSchema` получает необязательные `main_position_code`, `scale`, `series` (по умолчанию `None`/`[]`, старые прогоны валидируются).

- [ ] **Step 1: Tests.** `test_payroll_block_has_scale_and_series_for_curve_scale` (фикстура с кривой X: `scale.scale_type == "CURVE_POWER"`, `norm_per_shift` 115,3846, `ceiling_per_shift` 184,6154, `rate_norm` 45, `rate_ceiling` 168,66; ряды отсортированы по `pace`, содержат узлы нормы и потолка и плановый темп блока, `rate` и `per_shift` совпадают с `Scale.rate_at/per_shift` в этих точках); `test_positions_carry_names_from_reference` (в `payroll.positions` у каждой должности `position_name` равен названию записи справочника, не коду; `main_position_code` указывает на одну из них); `test_series_empty_when_main_has_no_scale` (экипаж из повременщиков → `scale is None`, `series == []`); API: `/economics/run` в режиме `PAYROLL` возвращает `payroll.series` с ≥ 2 точками, прогон без ключей валидируется; `test_drilling_operation_constant_is_shared` (`block_margin.DRILLING_OPERATION is drilling.DRILLING_OPERATION`).
- [ ] **Step 2:** `.venv/bin/python -m pytest tests/test_model_block_payroll_margin.py tests/test_api_block_economics.py -q` — FAIL.
- [ ] **Step 3: Implement** в `block_margin.to_dict` ключи `main_position_code` (код первой сдельной должности экипажа — как `main_scale`; добавить в `BlockPayroll` поле, если его нет); `PositionPayroll` получает `position_name` (из `position.name` в `_position_payroll`), `scale`, `series` через `scale_series(payroll.main_scale, payroll.pace.pace)`; float как в остальном `to_dict`; схемы API зеркалят поля; константу `DRILLING_OPERATION` импортировать из `cost.model.drilling`.
- [ ] **Step 4:** те же тесты + `tests/test_model_regression_smeta_2026_01.py` — PASS.
- [ ] **Step 5: Commit** — `TASK-010 PR 3b: шкала и ряды графика в блоке payroll`.

### Task 2: Чувствительность `PIECE_RATE` в режиме методики

**Files:**
- Modify: `cost/model/sensitivity.py`
- Test: тесты чувствительности лежат в `tests/test_model_engine.py` и `tests/test_api_block_economics.py` (искать `sensitivity`); новые — отдельным файлом `tests/test_model_sensitivity_payroll.py`

**Interfaces:**
- Consumes: поля шкалы `labor_rates`: `rate_norm`, `rate_ceiling`, `tiers[].rate` (`cost/v2/schemas/labor.py`).
- Produces: фактор `PIECE_RATE` («Сдельные расценки») масштабирует `piece_rate_rub` и, дополнительно, `rate_norm`, `rate_ceiling` и ставки ступеней `tiers[].rate` во всех записях `labor_rates`; остальные факторы не меняются.

- [ ] **Step 1: Tests.** `test_piece_rate_moves_payroll_crew` (блок `PAYROLL` на фикстуре: строка `PIECE_RATE` при +10 % даёт ненулевое изменение `price_per_m3["with_margin"]` — цены с ОХР и рентабельностью; эффект = 10 % × Σ `payroll.positions[].variable_rub` × (1 + ОХР) × (1 + рентабельность) / `block_volume_m3`, допуск 1 % от эффекта; ставки ОХР и рентабельности берутся из `economics.markup`); `test_piece_rate_in_rates_mode_unchanged` (режим `RATES`: результат строки `PIECE_RATE` тот же, что на `origin/main` — закреплённые числа из существующего теста); `test_piece_rate_scales_tier_rates` (запись со ступенями: ставки ступеней ×1,1, пороги не меняются).
- [ ] **Step 2:** запуск — FAIL.
- [ ] **Step 3: Implement** `_scale_piece_rates(inputs, factor) -> Inputs` рядом с `_scale_reference`, зарегистрировать в `PARAMETERS` вместо прямого `_scale_reference("labor_rates", "piece_rate_rub")`; пустые и отсутствующие поля пропускаются, как в `_scale_reference`; `tiers` — список словарей, копируется, не изменяется на месте.
- [ ] **Step 4:** тесты + регрессия сметы — PASS.
- [ ] **Step 5: Commit** — `TASK-010 PR 3b: чувствительность PIECE_RATE двигает шкалы методики`.

### Task 3: Типы и модель вида разбивки

**Files:**
- Modify: `frontend/src/types/blockEconomics.ts` (`BlockPayroll` и вложенные, `BlockEconomics.payroll?: BlockPayroll | null`), `frontend/src/pages/economics/testFixtures.ts` (`payrollFixture()`, `economicsFixture` принимает `payroll`)
- Create: `frontend/src/pages/economics/payrollModel.ts`
- Test: `frontend/src/pages/economics/payrollModel.test.ts`

**Interfaces:**
- Produces (`payrollModel.ts`): `type ShareView = {label: string; value: string; tone: "ok" | "warn" | "muted"}`; `shareView(point: PayrollSharePoint | null, status: PayrollMarginStatus, threshold: number): ShareView` — процент через `percent`, `warn` при превышении порога, для `NOT_CHECKED` / `NO_MARGIN` / `NOT_APPLICABLE` текст-объяснение («доля не проверена: нет цены метра» и т. п.) и `muted`; `chartGeometry(series: PayrollSeriesPoint[], scale: PayrollScale, pace: number, size: {width: number; height: number; padding: number}): ChartGeometry | null` — `{ratePath: string; perShiftPath: string; xAxis: Tick[]; yAxis: Tick[]; markers: {norm; ceiling; pace}}`, `null` при `series.length < 2`; проценты — готовая `percent(share)` из `format.ts` (доля 1,043 → «104,3 %»), своей не заводить.
- Типы: `BlockPayroll {pace; normalized_meters; effective_shifts; positions[] (с `position_name`); price_rub_per_m; variable_rub_per_m; margin; main_position_code; scale; series; lineage}` — ровно поля `PayrollBlockSchema` после задачи 1.

- [ ] **Step 1: Tests.** `payrollModel.test.ts`: `shareView` для `CHECKED` ниже и выше порога (`104,3 %` и тон `warn`), для трёх нештатных статусов (текст не содержит `NaN`, тон `muted`); `chartGeometry`: узлы нормы и потолка попадают на оси внутри области, маркер темпа выше потолка (236 при потолке 184,6) не выходит за область (ось растягивается), `null` при пустом ряду, монотонность x для отсортированного ряда, путь начинается с `M`.
- [ ] **Step 2:** `cd frontend && npx vitest run src/pages/economics/payrollModel.test.ts` — FAIL.
- [ ] **Step 3: Implement** типы, фикстуру (значения: кривая X, `m_plan` 120, доли 29,98 % и 100,65 %) и `payrollModel.ts` (чистые функции, без DOM); `economicsFixture()` без аргумента по-прежнему даёт `payroll: null`.
- [ ] **Step 4:** vitest файла + `npx tsc -b` — PASS.
- [ ] **Step 5: Commit** — `TASK-010 PR 3b: типы блока payroll и модель вида разбивки`.

### Task 4: `PayrollChart` и `PayrollBreakdown`

**Files:**
- Create: `frontend/src/pages/economics/PayrollChart.tsx`, `frontend/src/pages/economics/PayrollBreakdown.tsx`
- Modify: `frontend/src/styles/economics.css`
- Test: `frontend/src/pages/economics/PayrollBreakdown.test.tsx`

**Interfaces:**
- Consumes: `chartGeometry`, `shareView` (задача 3), `money`, `amount` из `format.ts`, `OriginBadge`.
- Produces: `PayrollChart({payroll}: {payroll: BlockPayroll}): ReactElement | null` — `<svg role="img" aria-label="График шкалы сдельной премии">`: подпись над графиком называет должность, чья шкала нарисована (`positions[]` по `main_position_code` → `position_name`); линия цены единицы, линия премии за смену, вертикальные маркеры «норма», «потолок», «плановый темп», подписи осей; `null`, если `chartGeometry` вернул `null`. `PayrollBreakdown({payroll}: {payroll: BlockPayroll})` — `<details>` с заголовком «ФОТ по методике» (закрыт по умолчанию), в закрытом виде на строке `summary`: цена метра, доля на потолке (`shareView`, тон `warn` выделен), флаг-индикатор; внутри: плановый темп (м/см, строка матрицы, `k` крепости и диаметра), приведённые метры блока и их множитель к погонным, план вахты (`effective_shifts`), таблица должностей — по названию (`position_name`), не по коду (человек в смене, `c_var`, постоянная часть, переменная часть, итог), цена метра с подписью «по себестоимости с надбавками» (строка `margin.lineage.price_rub_per_m`) и переменные метра, маржа метра, две доли (плановый темп и потолок) + «получает машинист», порог, график.

- [ ] **Step 1: Tests.** Рендер на `payrollFixture()`: `details` закрыт по умолчанию (`open === false`) и после `userEvent.click` по `summary` открывается (`open === true`); `summary` показывает цену метра и долю на потолке; график лежит внутри `details` (проверка `details.contains(chart)`, а не видимость: jsdom содержимое закрытого `<details>` не скрывает); таблица должностей содержит строку на каждую `positions[]` с отформатированными суммами; для `margin.status = "NO_MARGIN"` вместо долей — пояснение, графика нет при `series = []`; выше порога у индикатора класс `payroll-share-warn`; индикатор в `summary` строится только из `payroll.margin` (`shareView`): его текст — короткая формулировка «доля на потолке 104,3 % при пороге 70 %», он не совпадает с текстом флага из `economics.warnings` (проверка: `payroll.margin.flags[0].message` не встречается в `container.textContent`) — полный текст остаётся за блоком «Модель сообщает».
- [ ] **Step 2:** запуск — FAIL.
- [ ] **Step 3: Implement** компоненты; классы `payroll-breakdown`, `payroll-summary`, `payroll-share`, `payroll-share-warn`, `payroll-table`, `payroll-chart` и т. п. описать в `economics.css` (токены цвета и размеры как у `drilling-card`); линии графика — через `currentColor`/переменные темы.
- [ ] **Step 4:** `npx vitest run src/pages/economics/PayrollBreakdown.test.tsx src/pages/economics/cssCoverage.test.ts` + `npx tsc -b` — PASS.
- [ ] **Step 5: Commit** — `TASK-010 PR 3b: разбивка ФОТ по методике и график шкалы`.

### Task 5: Переключатель источника и строки методики в «Персонале»

**Files:**
- Modify: `frontend/src/pages/economics/sections/LaborSection.tsx`, `frontend/src/styles/economics.css`
- Test: `frontend/src/pages/economics/sections/LaborSection.test.tsx`, `frontend/src/pages/economics/estimateModel.test.ts`, `frontend/src/pages/economics/variants.test.ts`, `tests/test_api_block_economics.py`

**Interfaces:**
- Consumes: `params.payroll_source`, `params.drilling_executor`, `economics.payroll`, `PayrollBreakdown` (задача 4).
- Produces: в `LaborSection` — `<fieldset className="labor-source">` «Источник ФОТ экипажа бурения» с радиокнопками «Ставки» / «Методика ФОТ» (`onChange({payroll_source})`), `disabled` при `!canEdit`; при `drilling_executor = "SUBCONTRACTOR"` обе кнопки недоступны с подсказкой «Бурение на субподряде: ФОТ экипажа считает подрядчик»; для должностей из `economics.payroll.positions` вместо оклада в колонке цены — подписи `captions`: «ФОТ по методике», «c_var … ₽/прив. м», «Постоянная … ₽ · переменная … ₽»; ниже строк — `<PayrollBreakdown>` (когда `economics?.payroll` есть); при выбранной методике и `economics?.payroll == null` (откат, расчёт идёт) — строка-пояснение «Методика не применена — причина в блоке «Модель сообщает»» (не при `economics === null`).

- [ ] **Step 1: Tests.** выбор «Методика ФОТ» зовёт `onChange({payroll_source: "PAYROLL"})`; при `canEdit = false` и при субподряде радиокнопки недоступны; строки должностей методики показывают подписи `c_var` и разделение частей, а должности вне `positions[]` остаются как были; при `payroll_source = "PAYROLL"` и `economics.payroll = null` — пояснение, при `economics = null` — нет; существующие тесты секции проходят без правок.
- [ ] **Step 1b: Tests сравнения режимов.** Бэкенд: `test_compare_runs_with_different_payroll_modes` в `tests/test_api_block_economics.py` (два сохранённых прогона, `RATES` и `PAYROLL`: строки сравнения — объединение кодов, у прогона без строки сумма 0, `LABOR_CONTRIBUTIONS` у `PAYROLL` меньше, ответ 200). Фронт: в `estimateModel.test.ts` — `buildEstimate` на `economicsFixture()` без `payroll` и с `payrollFixture()` строит группу «Персонал» без ошибок, строки `LABOR_*` с `price_origin = "PAYROLL"` попадают в неё; в `variants.test.ts` — вариант с `payroll_source: "PAYROLL"` дублируется вместе с полем.
- [ ] **Step 2:** `npx vitest run src/pages/economics/sections/LaborSection.test.tsx src/pages/economics/estimateModel.test.ts src/pages/economics/variants.test.ts` и `.venv/bin/python -m pytest tests/test_api_block_economics.py -q` — FAIL.
- [ ] **Step 3: Implement.** Переключатель по образцу `fieldset.drilling-executor` из `DrillingSection`; не заводить второй способ хранить выбор: он живёт в `ModelParameters.payroll_source`, которое уже уходит в расчёт и сохраняется (`draftFromRun`, 3a).
- [ ] **Step 4:** `npx vitest run src/pages/economics` + `npx tsc -b` — PASS.
- [ ] **Step 5: Commit** — `TASK-010 PR 3b: переключатель источника ФОТ и строки методики в разделе «Персонал»`.

### Task 6: Смена объекта в подсказке скорости

**Files:**
- Modify: `frontend/src/lib/referenceDerived.ts` (`shiftHours` и вызов на `:87`)
- Test: `frontend/src/lib/referenceDerived.test.ts`

**Interfaces:**
- Produces: `shiftHours(context: DerivedContext, siteCode?: string | null): number` — смена записи объекта `sites.<siteCode>.shift_hours`, если она > 0, иначе смена организации, иначе умолчание; подсказка коммерческой скорости строки условий бурения передаёт `site_code` строки.

- [ ] **Step 1: Tests.** `shiftHours` с объектом на 12 ч и организацией на 11 → 12; объект без значения или 0 → 11; неизвестный объект → 11; подсказка строки с `site_code` объекта на 12 ч считает `v_коммерч` по 12 ч, без `site_code` — по 11 ч.
- [ ] **Step 2:** `npx vitest run src/lib/referenceDerived.test.ts` — FAIL.
- [ ] **Step 3: Implement** (правило то же, что `resolve_shift_hours` на бэкенде: значение объекта, если оно > 0; иначе организации).
- [ ] **Step 4:** vitest файла + `npx tsc -b` — PASS.
- [ ] **Step 5: Commit** — `TASK-010 PR 3b: подсказка скорости учитывает смену объекта`.

### Task 7: Документация и справка

**Files:**
- Modify: `Docs/BLOCK_ECONOMICS_UI.md` (разделы «Смета-конструктор» и «Изменения API»), `Docs/PAYROLL_MODEL.md` (раздел об интерфейсе), `frontend/src/pages/economics/EconomicsHelp.tsx`, `frontend/src/pages/economics/EconomicsHelp.test.tsx` (если есть тест справки)

- [ ] **Step 1:** описать переключатель, разбивку, график (откуда ряды), статусы доли, поведение при откате и субподряде; в «Изменения API» — ключи `payroll.scale`, `payroll.series`, `payroll.main_position_code`; в справке «?» — абзац «Источник ФОТ» простым языком (без кодов и JSON).
- [ ] **Step 2:** `npx vitest run src/pages/economics` + `npx tsc -b` — PASS (теста у `EconomicsHelp` нет; достаточно, что страница рендерится в существующих тестах).
- [ ] **Step 3: Commit** — `TASK-010 PR 3b: документация и справка по ФОТ в блоке`.

### Task 8: Проверка на стенде и скриншоты

**Files:**
- Create: ветка `assets/task-010-pr3b` с PNG (по прецеденту `assets/task-010-pr0` и `assets/task-010-pr1`), в репозиторий кода скриншоты не кладутся

- [ ] **Step 1:** поднять стенд ветки (`api-stand` и `frontend-stand`, память «Тестовый стенд без входа»; `stand_app.py` в worktree — `REPO = Path(__file__).resolve().parents[2]`; запуск и правка `launch.json` — только с согласия владельца), опубликовать ревизию справочников (`POST /api/v1/economics/references/publish`), набрав записи из готовых данных: шкала машиниста (кривая X), «Параметры ФОТ» года, таблицы крепости, причины простоев — `cost/v2/payroll_defaults.py` (`DRILLER_SCALE`, `PAYROLL_PARAMS`, `HARDNESS_BANDS`, `DOWNTIME_REASONS`, `EXTRA_TARIFFS`); прямые должности (машинист, помощник), ставки, станок, строка условий бурения и объект с вахтой — как в `tests/model_fixtures.py` и `tests/payroll_fixtures.py` (`references()`).
- [ ] **Step 2:** прогнать сценарии и снять скриншоты (headless Chromium, `playwright-core`): (а) `RATES` → `PAYROLL` → строки и свёрнутая разбивка; (б) раскрытая разбивка с графиком; (в) доля на потолке выше порога — индикатор и блок «Модель сообщает»; (г) субподряд — переключатель недоступен; (д) методика выбрана, но нет «Параметров ФОТ» года — пояснение вместо разбивки; (е) ширина 1024 px.
- [ ] **Step 3:** `pytest -q` (без падений, кроме известного флака тайминга `tests/test_cad_surface.py::test_flat_protection_without_other_levels_is_bounded` — перезапустить отдельно), `cd frontend && npx tsc -b && npx vitest run`.
- [ ] **Step 4:** в теле PR — скриншоты (ссылки на `assets/task-010-pr3b`), перечень решений без владельца и оговорки.

---

## Не входит в PR

Правка матрицы условий бурения (Т19, данные); помесячный ФОТ юнита Cost V2 (Т18); учёт факта (TASK-010 §2.8); начисление проживания в режиме методики (в 3a — только предупреждение); флаг темпа выше потолка в блоке (есть в превью; в блоке сигнал даёт флаг доли); перенос дополнительных должностей (водитель, ТОиР) на методику; сравнение прогонов по режимам ФОТ (`RunsCompare` показывает суммы строк как есть).

## Self-review

- Покрытие: `ORIGIN_LABELS` — уже в 3a (бейдж «Расчёт ФОТ», класс); `LaborSection` — задача 5; `PayrollBreakdown` с общим SVG-графиком по рядам сервера — задачи 1, 3, 4; обе доли, база цены, предупреждение вне свёрнутого блока — задача 4 (индикатор в `summary`); `Docs/BLOCK_ECONOMICS_UI.md` — задача 7; отложенное из 3a — задачи 1 (константа), 2, 6.
- Имена согласованы: `BlockPayroll`/`PayrollSeriesPoint`/`PayrollScale` (3→4, 5), `shareView`/`chartGeometry` (3→4), `payroll.series` (1→3→4), `PayrollBreakdown` (4→5).
- Числа в тестах: кривая X (115,3846 / 184,6154, 45 / 168,66), `m_plan` 120 и 236,16, доли 29,98 % / 100,65 % / 104,27 % — из таблицы «до/после» PR #130; ряды и пути графика проверяются относительными свойствами (узлы на осях, монотонность), а не посимвольно.
