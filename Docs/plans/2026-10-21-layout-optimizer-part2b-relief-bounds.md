# Рабочий диапазон темпа и сходящиеся фронты — план реализации (часть 2b оптимизатора раскладки)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Темп отбойки получает жёсткую нижнюю границу (3 мс/м по умолчанию, диапазон из справочника пород) и поиск сходящихся фронтов; оба показателя есть в API, на карте и в панели «Тайминг», готовые для перебора.

**Architecture:** `design/relief.py` считает долю площади быстрее нижней границы (и медленнее верхней, если она задана) и стыки соседних треугольников, где порода с двух сторон движется навстречу. Диапазон берётся из записи справочника `rocks` по `design.rock_name`; маршрут `/design/analyze` получает снимок справочников так же, как `/design/fragmentation`. Фронт выделяет быстрые треугольники и рисует стыки линиями.

**Tech Stack:** Python 3.13, numpy/scipy, pydantic, FastAPI; React + TypeScript, vitest.

**Spec:** `Docs/specs/2026-10-21-block-layout-optimizer-design.md`, раздел «Темп отбойки»: «Рабочий диапазон темпа», «Сходящиеся фронты», «Порядок оценки ровности в переборе».

## Global Constraints

- База — ветка `feat/burden-relief` (PR #121); работа идёт коммитами в неё же.
- Нижняя граница по умолчанию — `RELIEF_MIN_MS_M = 3.0`, жёсткая (дефект варианта). Верхней границы по умолчанию нет.
- Поля справочника пород: `relief_min_ms_m`, `relief_max_ms_m` — `UnitField("мс/м", …)`, необязательные, `gt=0`; подписи «Темп отбойки от», «Темп отбойки до»; если обе заданы, «до» больше «от» (ошибка через `field_error`, как в `cost/v2/schemas/organization.py`).
- Порода блока — `design.rock_name`, поиск записи `rocks` по имени (кода породы у проекта нет). Не нашли или поле пустое — умолчание 3,0 и без верхней.
- Сходящиеся фронты: направление движения породы в треугольнике `m = −∇t/|∇t|` (к скважинам, сработавшим раньше). Для двух треугольников с общим ребром и нормалью `n` от первого ко второму стык есть, когда `m1·n > 0`, `m2·n < 0` и угол между `m1` и `m2` не меньше `CONVERGING_MIN_ANGLE_DEG = 90`. Треугольники с темпом 0 не участвуют.
- Порядок оценки для перебора (часть 4): `fast_share` → `converging_length_m` → `outside_share` → `robust_spread`. В этой части — только показатели, без перебора.
- Подписи: «Быстрее {от} мс/м», «Медленнее {до} мс/м» (только если верхняя задана), «Стыки фронтов», единица «м». JSON пользователю не показывать.

## Review Focus

- Порода не найдена по имени или `rock_name` пуст — граница 3,0, без ошибок — Task 2.
- Одновременное срабатывание (темп 0 везде): `fast_share = 1`, стыков нет — Task 1.
- Ровная схема по рядам (плоскость времени): стыков нет, `fast_share = 0` при темпе выше 3 — Task 1.
- Вруб в центре (V: время растёт от средней линии): стык по средней линии есть; «конёк» (время убывает от средней линии) — стыка нет — Task 1.
- Старые записи справочника без новых полей читаются, форма показывает поля по схеме — Task 2.

---

### Task 1: Границы темпа и сходящиеся фронты в расчёте

**Files:**
- Modify: `design/relief.py`
- Test: `tests/test_relief.py`

**Interfaces:**
- Produces:
  - `RELIEF_MIN_MS_M = 3.0`, `CONVERGING_MIN_ANGLE_DEG = 90.0`
  - `ReliefStats`: новые поля `min_bound_ms_m: float`, `max_bound_ms_m: float | None`, `fast_share: float`, `slow_share: float` (0, если верхней нет), `converging_length_m: float`.
  - `BurdenRelief`: новое поле `converging: list[tuple[tuple[float, float], tuple[float, float]]]` — отрезки стыков.
  - `relief_stats(triangles, min_ms_m: float = RELIEF_MIN_MS_M, max_ms_m: float | None = None) -> ReliefStats | None`
  - `converging_edges(triangles) -> list[tuple[(x, y), (x, y)]]` — по общим рёбрам (по `hole_ids`).
  - `burden_relief(design, times, *, min_ms_m: float = RELIEF_MIN_MS_M, max_ms_m: float | None = None) -> BurdenRelief | None`
  - `to_dict` округляет новые поля: доли — 4 знака, длина — 2, границы — 2, отрезки — 3.

- [ ] **Step 1: Write the failing tests**

Сетка `grid_holes()` 3 × 4, `plane_times(25, 42)` — темп 15,33 мс/м (существующие помощники). V-сетка: 3 ряда × 5 столбцов, `a = 4`, `b = 3`, время `t = 25·|i − 2| + 42·j` (вруб — средний столбец i = 2).

```python
def test_plane_timing_is_not_fast_and_has_no_converging_fronts():
    relief = burden_relief(design_with(grid_holes(), pattern_params={"spacing_a_m": 4.0, "burden_b_m": 3.0}), plane_times(25, 42))
    assert relief.stats.fast_share == 0.0 and relief.converging == []
    assert relief.stats.min_bound_ms_m == 3.0 and relief.stats.max_bound_ms_m is None

def test_simultaneous_firing_is_all_fast_without_fronts():
    tris = relief_triangles(grid_holes(), {h.id: 500.0 for h in grid_holes()}, 6.4)
    assert relief_stats(tris).fast_share == 1.0
    assert converging_edges(tris) == []

def test_bounds_from_caller():
    stats = relief_stats(relief_triangles(grid_holes(), plane_times(25, 42), 6.4), min_ms_m=16.0, max_ms_m=15.0)
    assert stats.fast_share == 1.0 and stats.slow_share == 1.0

def test_v_cut_valley_gives_converging_line_along_cut():
    tris = relief_triangles(v_holes(), v_times(), 6.4)
    edges = converging_edges(tris)
    assert edges and all(abs(a[0] - 8.0) < 1e-6 and abs(b[0] - 8.0) < 1e-6 for a, b in edges)
    stats = burden_relief(design_with(v_holes(), pattern_params={"spacing_a_m": 4.0, "burden_b_m": 3.0}), v_times()).stats
    assert stats.converging_length_m == pytest.approx(6.0)  # средняя линия x = 8: два ребра по 3 м

def test_ridge_is_not_converging():
    tris = relief_triangles(v_holes(), {k: -v for k, v in v_times().items()}, 6.4)
    assert converging_edges(tris) == []
```

Помощники `v_holes` (устья `(4i, 3j)`) и `v_times` — в тестовом файле. Стороны ячеек регулярной сетки всегда входят в Делоне, поэтому средняя линия x = 8 — это два вертикальных ребра.

- [ ] **Step 2: Run tests — FAIL** (`.venv/bin/python -m pytest tests/test_relief.py -q`: нет `converging_edges`, нет полей).

- [ ] **Step 3: Implement.** Градиент треугольника уже считается в `relief_triangles`; сохранить в `ReliefTriangle` вектор `gradient: tuple[float, float]` (мс/м по x и y) — нужен для направления. Общие рёбра — словарь `frozenset(пары hole_ids) → [треугольники]`. Доли — по площади, как `outside_share`.

- [ ] **Step 4: Run tests — PASS**, затем `tests/test_relief_api.py`.

- [ ] **Step 5: Commit** — «Темп отбойки: нижняя граница 3 мс/м и сходящиеся фронты».

### Task 2: Диапазон темпа в справочнике пород и в анализе

**Files:**
- Modify: `cost/v2/schemas/misc.py` (`RockPayload`)
- Modify: `api/routers/design.py` (`post_analyze`), `api/services/design_service.py` (`analyze_design`), `api/schemas/design.py` (`ReliefStatsSchema`, `BurdenReliefSchema`)
- Test: `tests/test_reference_schemas.py`, `tests/test_relief_api.py`

**Interfaces:**
- Consumes: Task 1 (`burden_relief(..., min_ms_m=, max_ms_m=)`, новые поля).
- Produces:
  - `RockPayload.relief_min_ms_m`, `RockPayload.relief_max_ms_m`.
  - `analyze_design(request, *, organization_id: str | None = None, repository=None)` — без репозитория умолчание 3,0 (существующие вызовы и тесты работают).
  - `relief_bounds_for_rock(snapshot, rock_name: str) -> tuple[float, float | None]` в `api/services/design_service.py`.
  - Схемы: новые поля `ReliefStats` и `converging: list[list[list[float]]]` в `BurdenReliefSchema`.

- [ ] **Step 1: Write the failing tests**

```python
def test_rock_relief_range_fields():
    schema = section_json_schema("rocks")
    assert schema["properties"]["relief_min_ms_m"]["x-unit"] == "мс/м"
    assert RockPayload(relief_min_ms_m=Decimal("4"), relief_max_ms_m=Decimal("12")).relief_max_ms_m == Decimal("12")
    with pytest.raises(ValidationError):
        RockPayload(relief_min_ms_m=Decimal("8"), relief_max_ms_m=Decimal("5"))

def test_relief_bounds_from_rock_by_name():
    snapshot = snapshot_with_rock(name="Гранит", relief_min_ms_m="4", relief_max_ms_m="12")
    assert relief_bounds_for_rock(snapshot, "Гранит") == (4.0, 12.0)
    assert relief_bounds_for_rock(snapshot, "Нет такой") == (3.0, None)
    assert relief_bounds_for_rock(snapshot, "") == (3.0, None)

def test_analyze_uses_rock_bounds():
    # design.rock_name = "Гранит", снимок с relief_min_ms_m = 16 → весь блок 15,33 мс/м быстрее
    body = analyze_design(request_for(grid_design(rock_name="Гранит")), organization_id="org", repository=repo_with_rock(min=16))
    assert body.relief.stats.min_bound_ms_m == 16.0 and body.relief.stats.fast_share == 1.0
```

Снимок и репозиторий — `InMemoryEconomicsRepository` с опубликованной записью `rocks` (как в `tests/test_legacy_adapter_roundtrip.py`).

- [ ] **Step 2: Run tests — FAIL.**
- [ ] **Step 3: Implement.** Маршрут — зависимости как у `post_fragmentation` (`current_team_id`, `get_economics_repository`). Поиск — `snapshot.active_items("rocks")`, сравнение имени без учёта регистра и пробелов по краям.
- [ ] **Step 4: Run** `.venv/bin/python -m pytest tests/test_reference_schemas.py tests/test_relief.py tests/test_relief_api.py tests/test_api_timing.py -q` — PASS; затем весь набор.
- [ ] **Step 5: Commit** — «Темп отбойки: диапазон из справочника пород в анализе тайминга».

### Task 3: Быстрые участки и стыки на плане, строки в панели

**Files:**
- Modify: `frontend/src/types/design.ts`, `frontend/src/pages/design/PlanCanvas.tsx`, `frontend/src/pages/design/TimingPanel.tsx`, `frontend/src/styles/design.css`
- Test: `frontend/src/pages/design/TimingPanel.test.tsx`

**Interfaces:**
- Consumes: Task 2 (поля в ответе).
- Produces:
  - Треугольник быстрее нижней границы — штриховка поверх цвета зоны (паттерн SVG, тёмно-синий `#0C447C`, прозрачность 0,5), чтобы его было видно и в «ровной» зоне.
  - Стыки — линии `#A32D2D`, толщина 3 px, без пунктира, поверх треугольников и под скважинами.
  - Панель: «Быстрее {от} мс/м» — процент площади; «Медленнее {до} мс/м» — только если верхняя задана; «Стыки фронтов» — длина в м с одним знаком, «нет» при 0. Порядок строк: медиана, быстрее, стыки, вне коридора, устойчивый разброс.

- [ ] **Step 1: Write the failing tests** — заглушка `stats` с `min_bound_ms_m: 3, max_bound_ms_m: null, fast_share: 0.12, slow_share: 0, converging_length_m: 7.5`: видны «Быстрее 3 мс/м», «12 %», «Стыки фронтов», «7,5 м»; нет «Медленнее». Второй тест: `max_bound_ms_m: 12, slow_share: 0.3` → «Медленнее 12 мс/м», «30 %»; `converging_length_m: 0` → «нет».
- [ ] **Step 2: Run — FAIL.**
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** `cd frontend && npx vitest run && npx tsc --noEmit -p .` — PASS.
- [ ] **Step 5: Commit** — «Темп отбойки: быстрые участки и стыки фронтов на плане».

### Task 4: Документация и проверка на блоке №66

**Files:** `Docs/BURDEN_RELIEF.md`, `CLAUDE.md` (раздел «Темп отбойки»).

- [ ] **Step 1:** Полный прогон pytest и vitest + tsc.
- [ ] **Step 2:** Стенд, блок №66, схемы «Порядная» и «Клиновая»: записать «быстрее 3 мс/м», длину стыков; снимок карты.
- [ ] **Step 3:** Документ: нижняя граница и её смысл (зажатая порода), где задаётся диапазон, определение стыка и почему вруб в центре даёт стык, порядок оценки для перебора, цифры №66.
- [ ] **Step 4: Commit** — «Темп отбойки: описание границ и стыков фронтов».
