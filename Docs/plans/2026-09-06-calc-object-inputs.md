# Лист «Расчёт»: компактная шапка, плашки вверху, настройки листа по объекту

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** На вкладке «Расчёт» вместо общей шапки — одна компактная полоса: команда, объект, четыре маленькие плашки результата. Сценарий из интерфейса уходит (лист всегда — комплекс БВР). Всё, что сметчик вводит на листе, автоматически сохраняется на сервере за выбранным объектом и поднимается при его выборе, после чего расчёт вариантов запускается сам.

**Architecture:** Новая таблица `blastex.calc_object_inputs` (организация × имя объекта → JSON настроек листа) с методами репозитория и двумя маршрутами API; смена активного объекта получает отдельный маршрут и сохраняется сразу. На фронте чистый модуль `calcInputs.ts` (собрать настройки с листа / применить к листу / сравнить), хук автосохранения с задержкой, панели «Вариант 1/2» получают начальные значения и сообщают наверх об изменениях. Сценарий: выпадающий список и диалог переключения удаляются, `CalcPage` всегда рендерит комплекс БВР; в настройках команды `active_scenario_id` остаётся, сервер его нормализует.

**Tech Stack:** FastAPI, SQLAlchemy 2, Alembic, PostgreSQL 16 (JSONB); React 19 + TypeScript + Vite + vitest.

**Утверждённый дизайн (чат 2026-09-06):** сценарий убирается из интерфейса совсем; настройки по объекту — автоматически, на сервере, для всей команды; плашки «Удельный расход / ЛНС W / Средний кусок x50 / Негабарит» маленькие, в верхней полосе; дубль подписи «Комплекс БВР…» убирается.

## Global Constraints

- Ветка `feat/calc-object-inputs` от `fix/passport-labels` (PR #55, ещё не слит): PR открывать на `main` только после слияния #55, иначе базой ветки будет `fix/passport-labels`.
- Каждый метод `EconomicsRepository` без подчёркивания принимает `organization_id` первым аргументом; данные одной организации не видны другой (тест `test_every_repository_method_takes_organization_first` и изоляция).
- Настройки листа — JSON-объект, ключ — имя объекта работ (как `active_work_object_name`), размер ≤ 32 КиБ; `version: 1` внутри. Сервер содержимое не интерпретирует, только хранит и ограничивает размер и тип.
- Прямых SQL-записей в `blastex.*` нет: только миграция и репозиторий.
- Сценарий: `active_scenario_id` в настройках остаётся, `normalize_scenario_id` продолжает работать; маршрут `PUT /workspace/active-scenario` и `api.scenarios()` не удалять (совместимость), но фронт их больше не вызывает.
- Автосохранение: задержка 800 мс после последнего изменения, не пишет, если настройки равны последним сохранённым, не пишет до того, как настройки текущего объекта загружены с сервера (иначе умолчания затрут сохранённое). При смене объекта — сначала дописать старый (немедленно), затем загрузить новый.
- После загрузки сохранённых настроек, если порода, ВВ и хотя бы один диаметр валидны, расчёт вариантов (`api.optimize`) запускается автоматически; без сохранённых настроек лист остаётся на умолчаниях без автозапуска.
- Пользователю не показывать JSON; тексты, комментарии, коммиты — на русском; коммиты завершаются `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`; в `git add` только файлы задачи (посторонние untracked-файлы с суффиксами « 2»/« 3» не трогать).
- Проверки: `.venv/bin/python -m pytest -q` (плюс pg-тесты с `BLASTEX_TEST_DATABASE_URL` на `project1_test`, никогда `project1`); фронт — `cd frontend && npm test` и типы через временный `tsconfig.check.json` (`extends ./tsconfig.app.json`, `include: ["src"]`, `exclude: ["src/**/* 2.*", "src/**/* 3.*", "node_modules"]`, файл не коммитить).

---

## Структура файлов

| Файл | Ответственность |
|---|---|
| `migrations/versions/20260906_0007_calc_object_inputs.py` (создать) | таблица `blastex.calc_object_inputs` |
| `cost/v2/repository.py`, `cost/v2/db_repository.py` (изменить) | `CalcObjectInputs`, `get_calc_inputs`, `save_calc_inputs` (протокол, in-memory, PostgreSQL) |
| `api/schemas/workspace.py`, `api/routers/workspace.py` (изменить) | `GET/PUT /workspace/calc-inputs`, `PUT /workspace/active-object` |
| `frontend/src/api/endpoints.ts`, `frontend/src/types.ts` (изменить) | вызовы и типы |
| `frontend/src/app/useWorkspace.tsx`, `WorkspaceBar.tsx`, `AppShell.tsx` (изменить) | смена объекта сохраняется сразу; сценарий убран; на «Расчёте» общая шапка не показывается |
| `frontend/src/pages/calc/calcInputs.ts` (+ `.test.ts`, создать) | тип `CalcInputs`, `collectCalcInputs`, `applyCalcInputs`, `calcInputsEqual` |
| `frontend/src/pages/calc/useCalcInputsAutosave.ts` (создать) | автосохранение с задержкой и статусом |
| `frontend/src/pages/calc/CalcTopStrip.tsx` (создать) | компактная полоса: команда, объект, статус, плашки |
| `frontend/src/pages/CalcPage.tsx`, `frontend/src/pages/calc/HolePanel.tsx` (изменить) | всегда комплекс БВР; сбор/применение настроек; панели с начальными значениями |
| `frontend/src/pages/calc/ManualScenarioPage.tsx`, `DrillingGeometryPage.tsx` (удалить, если больше никто не импортирует) | режимы сценария |
| `frontend/src/styles.css` (изменить) | `.calc-top-strip`, `.metric-chips` |
| `tests/test_repository_organization_isolation.py`, `tests/test_repository_calc_inputs_pg.py` (создать), `tests/test_api_workspace.py` | тесты |

---

### Task 1: Хранение настроек листа по объекту

**Files:** миграция `20260906_0007_calc_object_inputs.py`, `cost/v2/repository.py`, `cost/v2/db_repository.py`, `tests/test_repository_organization_isolation.py`, `tests/test_repository_calc_inputs_pg.py`.

Таблица `blastex.calc_object_inputs`: `organization_id varchar(120)`, `work_object_name varchar(300)`, PK по паре; `inputs JSONB NOT NULL`; `updated_at timestamptz NOT NULL`, `updated_by varchar(320) NOT NULL`. Миграция по образцу `20260904_0006` (`revision = "20260906_0007"`, `down_revision = "20260904_0006"`, схема `blastex`, downgrade удаляет таблицу).

```python
@dataclass(frozen=True)
class CalcObjectInputs:
    work_object_name: str
    inputs: dict[str, Any]
    updated_at: datetime | None = None

# EconomicsRepository
def get_calc_inputs(self, organization_id: str, work_object_name: str) -> CalcObjectInputs | None: ...
def save_calc_inputs(self, organization_id: str, user_id: str, work_object_name: str, inputs: Mapping[str, Any]) -> CalcObjectInputs: ...
```

`save_calc_inputs` — upsert по (organization_id, work_object_name), возвращает сохранённое; пустое имя объекта → `EconomicsRepositoryError`. Тесты: in-memory — round-trip, перезапись, изоляция организаций (`ORG_A` не видит `ORG_B`), пустое имя; pg (`requires_pg`, `public_db`) — round-trip и перезапись обновляет `updated_at`.

- [ ] Тесты → падают → миграция и реализация → `pytest tests/test_repository_organization_isolation.py tests/test_cost_v2_repository.py -q` и pg-тест → коммит `feat(repository): настройки листа расчёта по объекту работ`.

---

### Task 2: API настроек листа и смены объекта

**Files:** `api/schemas/workspace.py`, `api/routers/workspace.py`, `tests/test_api_workspace.py`.

- `GET /workspace/calc-inputs?work_object_name=…` → `{ "work_object_name": str, "inputs": object | null, "updated_at": str | null }` (`require_internal_access`).
- `PUT /workspace/calc-inputs` с телом `{ "work_object_name": str, "inputs": object }` → то же; `inputs` обязан быть объектом (не списком), сериализованный размер ≤ 32 768 байт, иначе 422 `{"detail": {"message": "Настройки листа слишком большие."}}`; пустое имя → 422.
- `PUT /workspace/active-object` с телом `{ "work_object_name": str }` → `WorkspaceStateSchema` (как `active-scenario`): сохраняет только активный объект, снимок не трогает; неизвестное имя допускается (сервер и так подменяет через `resolve_work_object_name` при загрузке).
- Ошибки репозитория → `repository_error`.

Тесты: GET без записи → `inputs: null`; PUT затем GET; PUT со списком → 422; PUT больше лимита → 422; `active-object` меняет `settings.active_work_object_name` и не меняет снимок; изоляция организаций через два ключа сессии (образец в `test_api_team_scope.py`).

- [ ] Коммит `feat(api): настройки листа по объекту и смена активного объекта без сохранения снимка`.

---

### Task 3: Сценарий уходит из интерфейса, объект сохраняется сразу

**Files:** `frontend/src/app/WorkspaceBar.tsx`, `frontend/src/app/useWorkspace.tsx`, `frontend/src/api/endpoints.ts`, `frontend/src/pages/CalcPage.tsx`, `frontend/src/pages/calc/ManualScenarioPage.tsx`, `DrillingGeometryPage.tsx`, `frontend/src/types.ts`.

- `WorkspaceBar`: убрать поле «Сценарий» и диалог «Есть несохранённые изменения… переключить»; оставить «Команда», «Объект работ», «Статус», «Сохранить», предупреждения справочников и блок фаз сценария (он относится к комплексу БВР и нужен «Бурению»/«ФОТ»).
- `useWorkspace`: `setActiveWorkObjectName(name)` теперь сразу вызывает новый `api.setActiveWorkObject(name)` (`PUT /workspace/active-object`), обновляет состояние ответом и `savedKey`; `dirty` считается только по снимку. `switchScenario` и `pendingScenario` удалить; `scenarios`/`activeScenario` оставить (нужны `CostPanel`, блоку фаз).
- `CalcPage`: без ветвления по `calc_profile` — всегда `FullBvrCalc` с `explosiveBasis="per_m3"`; заглушка «Выберите сценарий» уходит; подпись под заголовком одна: «Комплекс БВР: оптимизация q, сетка, схема заряда». Если `ManualScenarioPage`/`DrillingGeometryPage` больше никто не импортирует — удалить файлы.
- Типы: `api.switchScenario` можно оставить в `endpoints.ts`, но неиспользуемые импорты убрать; vitest и типы зелёные.

- [ ] Коммит `feat(frontend): сценарий убран из шапки, лист «Расчёт» всегда комплекс БВР, объект сохраняется сразу`.

---

### Task 4: Настройки листа: сбор, применение, автосохранение

**Files:** `frontend/src/pages/calc/calcInputs.ts` (+ `calcInputs.test.ts`), `useCalcInputsAutosave.ts`, `frontend/src/pages/calc/HolePanel.tsx`, `frontend/src/pages/CalcPage.tsx`, `frontend/src/api/endpoints.ts`, `frontend/src/types.ts`.

```ts
export type PanelInputs = { explosive_key: string; undercharge_m: number; intermediate_detonators_per_hole: number; nsi_per_hole: number; nsi_length_1_m: number; nsi_length_2_m: number; detonator_delay_ms: number };
export type CalcInputs = { version: 1; rock_name: string; explosive_key: string; lump_size_mm: number; bench_height_m: number; overdrill_m: number; oversize_coeff: number; spacing_coeff: number; oversize_threshold_pct: number; selected_crowns_mm: number[]; selected_crown_mm: number | null; block_volume_m3: number; additional_holes_pct: number; panels: { left: PanelInputs; right: PanelInputs } };
export function collectCalcInputs(sheet: SheetState): CalcInputs;
export function applyCalcInputs(raw: unknown, catalogs: { rocks: string[]; explosiveKeys: string[]; crowns: number[] }): SheetState | null;   // null — если raw не похож на CalcInputs; неизвестная порода/ВВ/диаметр заменяются первым доступным, числа вне диапазона обрезаются по границам полей
export function calcInputsEqual(a: CalcInputs | null, b: CalcInputs | null): boolean;
```

- `HolePanel`: новые пропсы `initialInputs?: PanelInputs`, `onInputsChange?: (inputs: PanelInputs) => void`; начальное состояние берётся из `initialInputs`, любое изменение полей вызывает `onInputsChange`. Чтобы при смене объекта панель пересобралась, `FullBvrCalc` даёт ей `key={`${objectName}-left`}`.
- `useCalcInputsAutosave({ objectName, inputs, ready })`: задержка 800 мс, сравнение с последним сохранённым (`calcInputsEqual`), статус `"idle" | "saving" | "saved" | "error"`; `flush()` для немедленной записи перед сменой объекта; ошибка не блокирует лист (статус «ошибка сохранения» и повтор при следующем изменении).
- `FullBvrCalc`: при монтировании и при смене `state.settings.active_work_object_name` — `api.calcInputs(objectName)`; если есть — `applyCalcInputs` в состояние и `calculate()` автоматически; если нет — умолчания (`rocks.default_name`, `explosives.default_key`, все диаметры, панели по `DEFAULT_EXPLOSIVE_*`); флаг `ready` ставится после ответа. Выбранный диаметр (`selected_crown_mm`) после автозапуска расчёта восстанавливается, если такой вариант есть.
- vitest: `collect ↔ apply` round-trip; `apply` с чужим ВВ и диаметром подменяет доступными; `apply` мусора даёт `null`; `calcInputsEqual` не зависит от порядка ключей; поведение задержки — вынести чистую функцию `nextAutosaveAction(prevSaved, current, elapsedMs)` или тестировать хук через `vi.useFakeTimers` с подменой `api`.

- [ ] Коммит `feat(frontend): настройки листа расчёта по объекту с автосохранением`.

---

### Task 5: Компактная полоса и плашки

**Files:** `frontend/src/pages/calc/CalcTopStrip.tsx`, `frontend/src/pages/CalcPage.tsx`, `frontend/src/app/AppShell.tsx`, `frontend/src/styles.css`.

- `AppShell`: `WorkspaceBar` не рендерится на «Расчёте» (добавить в список исключений).
- `CalcTopStrip` (внутри `FullBvrCalc`, над сеткой): слева «Команда: <имя>» текстом и список «Объект работ» (значение из `useWorkspace`, смена → `setActiveWorkObjectName`), рядом мелкий статус автосохранения («сохранено», «сохранение…», «ошибка сохранения»), справа четыре плашки `.metric-chip` (подпись 10 px, значение 15 px, единица 10 px; «—» без расчёта). На ширине < 900 px плашки переносятся на вторую строку, список — на всю ширину. Старый `.metrics-grid` из колонки результатов удаляется; предупреждения справочников (`state.warnings`) показываются под полосой сворачиваемым блоком, как раньше в шапке.
- CSS: `.calc-top-strip { display:flex; flex-wrap:wrap; align-items:center; gap:14px; margin:0 0 14px; padding:10px 14px; border:1px solid #d9e2dd; border-radius:12px; background:#fff; }`, `.metric-chips { display:flex; gap:8px; margin-left:auto; }`, `.metric-chip { padding:6px 10px; border:1px solid #dce4e0; border-radius:10px; min-width:96px; }`.
- Типы и vitest зелёные.

- [ ] Коммит `feat(frontend): компактная полоса «Расчёта» с объектом и плашками результата`.

---

### Task 6: Проверка в браузере и PR (контроллер)

- [ ] Локально: `alembic upgrade head` на dev-базе; открыть «Расчёт»: полоса вверху, сценария нет; изменить уступ и ВВ, подождать, перезагрузить страницу — значения на месте, расчёт выполнен сам, плашки с цифрами; сменить объект — умолчания; вернуться — сохранённые; на «Бурении» шапка без сценария, «Сохранить» работает. Скриншот. PR на `main` после слияния #55 (или с базой `fix/passport-labels`).

## Самопроверка плана

- Пункт 1 пользователя (объект и команда вверху, без сценария) — Task 3, 5; пункт 2 (плашки меньше и вверху) — Task 5; пункт 3 (настройки по объекту) — Task 1, 2, 4.
- Интерфейсы: `CalcObjectInputs`/методы (T1) → маршруты (T2) → `api.calcInputs`/`api.saveCalcInputs` (T4); `setActiveWorkObjectName` с немедленным сохранением (T3) → полоса (T5); `PanelInputs` (T4) → `HolePanel`; `collect/apply` (T4) — чистые функции с тестами.
- Риски: панель пересоздаётся ключом при смене объекта — иначе состояние `useState` не сбросится; автосохранение не пишет до загрузки (`ready`), иначе умолчания затирают сохранённое.
