# Темп отбойки в мс/м — план реализации (часть 2 оптимизатора раскладки)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** BlastEX считает темп отбойки (мс/м) по треугольникам между соседними скважинами из времени срабатывания сети инициирования, показывает его на плане цветными зонами, как в ShotPlus, и даёт показатель ровности темпа для будущего перебора.

**Architecture:** Новый модуль `design/relief.py`: триангуляция Делоне по устьям скважин сетки (scipy), отбраковка длинных рёбер, темп треугольника — модуль градиента времени по плоскости через три скважины (мс на метр «кажущегося сопротивления», как у Datamine), сводка ровности по площади. `analyze_design` добавляет в ответ поле `relief`; фронт рисует треугольники слоем «Темп отбойки», раскрашивая их по отклонению от медианы, а в панели «Тайминг» показывает медиану и разброс.

**Tech Stack:** Python 3.13, scipy 1.17 (уже в `requirements.txt`), FastAPI/pydantic; React + TypeScript, vitest.

**Spec:** `Docs/specs/2026-10-21-block-layout-optimizer-design.md` (разделы «Темп отбойки», «Решения автора документа» — темп по треугольникам; «Порядок работ», п. 2).

## Global Constraints

- База ветки — `feat/lsp-floor-burden` (PR #120). После слияния #117 и #120 — перебазировать на `main`.
- Определение (Datamine DataBlast Pro, «Initiation analysis»): темп — время замедления в мс на метр кажущегося сопротивления, триангулированное между скважинами. В BlastEX: время срабатывания по плоскости через три скважины треугольника, темп = |∇t|, мс/м. Направление ∇t — направление движения фронта, `1/|∇t|` — скорость фронта.
- Время срабатывания — `resolve_network(...).times_ms` (с внутрискважинным замедлением; оно одно на блок и в разности не входит).
- Точка скважины — устье в плане (как у изолиний времени). Решение плана: по забою темп будет считаться в части 3 (наклон 1–2 ряда), если владелец попросит.
- В триангуляцию идут только включённые скважины группы сетки (`row_family(kind) == "grid"`) со временем. Стенки (контур, пресплит, буфер, подрезка) не входят.
- Ребро треугольника не длиннее `RELIEF_EDGE_FACTOR × max(a, b)`, `RELIEF_EDGE_FACTOR = 1.6` (тот же предел соседства, что в `timing_diagnostics`); `a`, `b` — `spacing_a_m`, `burden_b_m` из `pattern_params`, умолчания 5,0 и 4,0 как там же.
- Главный показатель ровности — **разброс** `cv = σ / среднее` по площади треугольников, в процентах в интерфейсе. Дополнительно — **доля площади вне коридора ±25 % от медианы** (`RELIEF_CORRIDOR = 0.25`). Абсолютное значение (медиана) показывается, но вторично.
- Цветовые зоны карты — по отклонению от медианы: `< −25 %`, `−25…−10 %`, `±10 %`, `+10…+25 %`, `> +25 %`. Подписи легенды — в мс/м, числа с запятой.
- Подписи в интерфейсе: слой «Темп отбойки»; в панели «Тайминг» — «Темп отбойки, мс/м (медиана)», «Разброс темпа», «Вне коридора ±25 %». Единица — «мс/м».
- Пользователю не показывать JSON (`CLAUDE.md`).

## Review Focus

- Все скважины срабатывают одновременно (одно время у всех): темп 0 во всех треугольниках, `cv = None`, ничего не падает; на плане зоны одного цвета — Task 1, Task 4.
- Меньше трёх скважин со временем или все на одной прямой (один ряд): треугольников нет, `relief = None` в ответе, слой пуст, панель пишет «нет треугольников» — Task 1, Task 3, Task 4.
- Неподключённая скважина (нет времени): в триангуляцию не идёт, соседние треугольники строятся по остальным — Task 1.
- Вогнутый контур («мыс»): Делоне соединяет скважины через вырез; рёбра длиннее 1,6 × max(a, b) отбрасываются — Task 1.
- Пресплит/контурные скважины со своим временем рядом с сеткой: не искажают темп — Task 1.

---

### Task 1: Темп отбойки по треугольникам и сводка ровности

**Files:**
- Create: `design/relief.py`
- Test: `tests/test_relief.py`

**Interfaces:**
- Consumes: `design/models.py::row_family(kind)`, `Hole`, `BlastDesign.pattern_params`; `scipy.spatial.Delaunay`.
- Produces:
  - `RELIEF_EDGE_FACTOR = 1.6`, `RELIEF_CORRIDOR = 0.25`
  - `@dataclass(frozen=True) class ReliefTriangle: hole_ids: tuple[str, str, str]; points: tuple[tuple[float, float], tuple[float, float], tuple[float, float]]; relief_ms_m: float; area_m2: float`
  - `@dataclass(frozen=True) class ReliefStats: triangles: int; median_ms_m: float; mean_ms_m: float; min_ms_m: float; max_ms_m: float; cv: float | None; outside_share: float` — среднее, σ, медиана и доля — взвешенные по площади; `cv = None` при среднем 0.
  - `relief_triangles(holes: list[Hole], times: dict[str, float], max_edge_m: float) -> list[ReliefTriangle]`
  - `relief_stats(triangles: list[ReliefTriangle]) -> ReliefStats | None` — None при пустом списке.
  - `@dataclass(frozen=True) class BurdenRelief: triangles: list[ReliefTriangle]; stats: ReliefStats | None` и `to_dict()` (ключи как в полях; `points` — списки `[x, y]`).
  - `burden_relief(design: BlastDesign, times: dict[str, float]) -> BurdenRelief | None` — None, если треугольников нет.

- [ ] **Step 1: Write the failing tests**

Сетка 3 ряда × 4 скважины, `a = 4` (вдоль x), `b = 3` (вдоль y), устья `(4i, 3j)`, kind по умолчанию (сетка). Время `t = 25·i + 42·j` (стандарт объекта: 25 мс между скважинами, 42 мс между рядами).

```python
def test_plane_timing_gives_constant_relief():
    tris = relief_triangles(grid_holes(), plane_times(25, 42), max_edge_m=1.6 * 4)
    assert len(tris) == 12  # 3 × 2 ячейки, по 2 треугольника
    expected = math.hypot(25 / 4, 42 / 3)  # 15,33 мс/м
    assert all(t.relief_ms_m == pytest.approx(expected, abs=1e-6) for t in tris)

def test_constant_relief_has_zero_spread():
    stats = relief_stats(relief_triangles(grid_holes(), plane_times(25, 42), 6.4))
    assert stats.cv == pytest.approx(0.0, abs=1e-9)
    assert stats.outside_share == pytest.approx(0.0)
    assert stats.median_ms_m == pytest.approx(math.hypot(25 / 4, 42 / 3))

def test_simultaneous_firing_gives_zero_relief_and_no_cv():
    stats = relief_stats(relief_triangles(grid_holes(), {h.id: 500.0 for h in grid_holes()}, 6.4))
    assert stats.mean_ms_m == 0.0 and stats.cv is None

def test_slow_corner_raises_spread_and_outside_share():
    times = plane_times(25, 42)
    times["3-04"] += 67  # угловая скважина задержана лишней ступенью
    stats = relief_stats(relief_triangles(grid_holes(), times, 6.4))
    assert stats.cv > 0.05
    assert 0 < stats.outside_share < 0.5

def test_long_edges_are_dropped():
    holes = grid_holes() + [hole("far", 40.0, 0.0)]
    times = plane_times(25, 42) | {"far": 300.0}
    tris = relief_triangles(holes, times, 6.4)
    assert all("far" not in t.hole_ids for t in tris)

def test_holes_without_time_and_walls_are_skipped():
    holes = grid_holes() + [hole("K1-01", 6.0, -1.0, kind="presplit")]
    times = plane_times(25, 42) | {"K1-01": 0.0}
    del times["2-02"]
    ids = {i for t in relief_triangles(holes, times, 6.4) for i in t.hole_ids}
    assert "K1-01" not in ids and "2-02" not in ids

def test_single_row_has_no_triangles():
    row = [hole(f"1-0{i}", 4.0 * i, 0.0) for i in range(4)]
    assert relief_triangles(row, {h.id: 25.0 * i for i, h in enumerate(row)}, 6.4) == []
    assert relief_stats([]) is None

def test_burden_relief_uses_pattern_spacing_for_edge_limit():
    design = design_with(grid_holes(), pattern_params={"spacing_a_m": 4.0, "burden_b_m": 3.0})
    result = burden_relief(design, plane_times(25, 42))
    assert result.stats.triangles == 12
    assert burden_relief(design_with([]), {}) is None
```

Вспомогательные `hole`, `grid_holes`, `plane_times`, `design_with` — в тестовом файле (id `"{j+1}-{i+1:02d}"`, вертикальные скважины, `BlastDesign(design_id="t", contour=..., holes=..., pattern_params=...)`).

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_relief.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'design.relief'`.

- [ ] **Step 3: Implement `design/relief.py`**

- Делоне — `scipy.spatial.Delaunay` по устьям; меньше трёх точек или все на одной прямой (`QhullError`) — пустой список.
- Треугольник отбрасывается, если любое ребро длиннее `max_edge_m` или площадь меньше `1e-6` м².
- Градиент плоскости `t = αx + βy + γ` по трём точкам — решение системы 2×2 на разностях (без `lstsq`); темп `hypot(α, β)`.
- Медиана по площади — значение, на котором накопленная площадь (по возрастанию темпа) доходит до половины.
- `outside_share` — доля площади, где `|r − медиана| > RELIEF_CORRIDOR × медиана`; при медиане 0 — доля площади с `r > 0`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_relief.py -q`
Expected: PASS (8 passed).

- [ ] **Step 5: Commit**

```bash
git add design/relief.py tests/test_relief.py
git commit -m "Темп отбойки: мс/м по треугольникам между скважинами и разброс по площади"
```

### Task 2: Темп отбойки в ответе анализа

**Files:**
- Modify: `api/schemas/design.py` (`AnalyzeResponse`, новые `ReliefTriangleSchema`, `ReliefStatsSchema`, `BurdenReliefSchema`)
- Modify: `api/services/design_service.py::analyze_design`
- Test: `tests/test_api_timing.py` (или новый `tests/test_relief_api.py` — по образцу клиента в `tests/test_api_timing.py`)

**Interfaces:**
- Consumes: Task 1 (`burden_relief(design, times) -> BurdenRelief | None`, `BurdenRelief.to_dict()`).
- Produces: `AnalyzeResponse.relief: BurdenReliefSchema | None = None`; схема повторяет поля Task 1 (`triangles[].hole_ids`, `points: list[list[float]]`, `relief_ms_m`, `area_m2`; `stats` — все поля `ReliefStats`, `cv: float | None`). Значения округлены: мс/м — 2 знака, площадь — 2, координаты — 3, `cv` и `outside_share` — 4.

- [ ] **Step 1: Write the failing test**

```python
def test_analyze_returns_burden_relief(client):
    design = grid_design_with_row_network()  # 3 × 4, шаблон "row", nonel 25/42
    body = client.post("/api/v1/design/analyze", json={"design": design.to_dict()}).json()
    relief = body["relief"]
    assert relief["stats"]["triangles"] > 0
    assert relief["stats"]["median_ms_m"] > 0
    assert len(relief["triangles"][0]["points"]) == 3

def test_analyze_without_triangles_returns_null_relief(client):
    body = client.post("/api/v1/design/analyze", json={"design": single_row_design().to_dict()}).json()
    assert body["relief"] is None
```

Сеть — `build_template_network(holes, "row", {...})`, параметры шаблона — как в существующих тестах `tests/test_api_timing.py`.

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_relief_api.py -q`
Expected: FAIL — `KeyError: 'relief'`.

- [ ] **Step 3: Implement** — `analyze_design` вызывает `burden_relief(design, times)` с уже посчитанными `times` и кладёт `to_dict()` (или None) в ответ.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_relief_api.py tests/test_api_timing.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add api/schemas/design.py api/services/design_service.py tests/test_relief_api.py
git commit -m "Темп отбойки: поле relief в ответе анализа тайминга"
```

### Task 3: Зоны темпа — раскраска и легенда (фронт, чистые функции)

**Files:**
- Modify: `frontend/src/types/design.ts` (`ReliefTriangle`, `ReliefStats`, `BurdenRelief`; `AnalyzeResponse.relief?: BurdenRelief | null`)
- Create: `frontend/src/pages/design/relief.ts`
- Test: `frontend/src/pages/design/relief.test.ts`

**Interfaces:**
- Consumes: Task 2 (поле `relief` ответа анализа).
- Produces:
  - `RELIEF_BANDS: { id: ReliefBand; from: number | null; to: number | null; color: string }[]` — пять зон по отклонению от медианы (`-0.25`, `-0.10`, `0.10`, `0.25`); цвета: `#2f6fb3`, `#7fb2de`, `#3a9d5d`, `#f0a43a`, `#c0392b`.
  - `type ReliefBand = "much_faster" | "faster" | "even" | "slower" | "much_slower"` (меньше мс/м — фронт быстрее).
  - `reliefBand(value: number, median: number) -> ReliefBand` — при медиане 0: `0` → `"even"`, иначе `"much_slower"`.
  - `reliefLegend(median: number) -> { band: ReliefBand; color: string; label: string }[]` — подписи в мс/м с одним знаком и запятой: `"до 11,5"`, `"11,5–13,8"`, `"13,8–16,9"`, `"16,9–19,2"`, `"больше 19,2"` для медианы 15,33.
  - `formatSpread(cv: number | null) -> string` — `"7 %"`, при null — `"—"`.

- [ ] **Step 1: Write the failing tests**

```ts
it("puts values within ±10 % of the median into the even band", () => {
  expect(reliefBand(15.33, 15.33)).toBe("even");
  expect(reliefBand(16.8, 15.33)).toBe("even");
  expect(reliefBand(18.0, 15.33)).toBe("slower");
  expect(reliefBand(20.0, 15.33)).toBe("much_slower");
  expect(reliefBand(11.0, 15.33)).toBe("much_faster");
});

it("treats zero median as simultaneous firing", () => {
  expect(reliefBand(0, 0)).toBe("even");
  expect(reliefBand(3, 0)).toBe("much_slower");
});

it("labels legend bands in ms/m with a comma", () => {
  expect(reliefLegend(15.33).map((b) => b.label)).toEqual(["до 11,5", "11,5–13,8", "13,8–16,9", "16,9–19,2", "больше 19,2"]);
});

it("formats spread as percent", () => {
  expect(formatSpread(0.0712)).toBe("7 %");
  expect(formatSpread(null)).toBe("—");
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/pages/design/relief.test.ts`
Expected: FAIL — модуль не найден.

- [ ] **Step 3: Implement** типы и `relief.ts` (форматирование чисел — существующий `ruNumber`, если он даёт запятую; проверь, где он объявлен).

- [ ] **Step 4: Run test and typecheck**

Run: `cd frontend && npx vitest run src/pages/design/relief.test.ts && npx tsc --noEmit -p .`
Expected: PASS, `tsc` без ошибок.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/types/design.ts frontend/src/pages/design/relief.ts frontend/src/pages/design/relief.test.ts
git commit -m "Темп отбойки: зоны по отклонению от медианы и легенда в мс/м"
```

### Task 4: Слой «Темп отбойки» на плане и сводка в панели «Тайминг»

**Files:**
- Modify: `frontend/src/pages/design/viewPresets.ts` (`LayerId` + `"relief"`, `LAYER_DEFS`, пресеты)
- Modify: `frontend/src/pages/design/PlanCanvas.tsx` (проп `relief?: BurdenRelief`, отрисовка под скважинами и изолиниями, рядом с блоком изолиний ~строка 1345)
- Modify: `frontend/src/pages/design/DesignPage.tsx` (передать `analysis?.relief` при включённом слое, ~строка 3227; команда палитры по образцу `isolines` ~строка 2569)
- Modify: `frontend/src/pages/design/TimingPanel.tsx` (сводка и легенда)
- Modify: `frontend/src/styles/design.css` (`.legend-swatch.relief`, класс треугольника)
- Test: `frontend/src/pages/design/viewPresets.test.ts`, `frontend/src/pages/design/TimingPanel.test.tsx` (create)

**Interfaces:**
- Consumes: Task 3 (`reliefBand`, `reliefLegend`, `formatSpread`, `RELIEF_BANDS`, тип `BurdenRelief`).
- Produces:
  - Слой `{ id: "relief", label: "Темп отбойки", group: "analysis", swatch: "relief", keywords: ["темп", "отбойка", "мс/м", "relief"] }`; включён в пресете `timing`, выключен в остальных (как `isolines`).
  - На плане — заливка каждого треугольника цветом зоны, прозрачность 0,45, без обводки; `<title>` треугольника — `"{темп} мс/м"`.
  - В панели «Тайминг» после расчёта: «Темп отбойки, мс/м (медиана)» — число с одним знаком; «Разброс темпа» — `formatSpread(cv)`; «Вне коридора ±25 %» — процент площади; легенда из `reliefLegend`. Без `relief` — строка «Темп отбойки: нет треугольников (меньше трёх скважин в два ряда)».

- [ ] **Step 1: Write the failing tests**

```ts
// viewPresets.test.ts
it("timing preset shows burden relief, review hides it", () => {
  expect(applyViewPreset("timing").layers.relief).toBe(true);
  expect(applyViewPreset("review").layers.relief).toBe(false);
});

// TimingPanel.test.tsx
it("shows relief median, spread and legend after analysis", () => {
  render(<TimingPanel {...props} analysis={{ ...analysis, relief: { triangles: [], stats: { triangles: 12, median_ms_m: 15.33, mean_ms_m: 15.4, min_ms_m: 14, max_ms_m: 17, cv: 0.0712, outside_share: 0.05 } } }} />);
  expect(screen.getByText("Темп отбойки, мс/м (медиана)")).toBeInTheDocument();
  expect(screen.getByText("15,3")).toBeInTheDocument();
  expect(screen.getByText("7 %")).toBeInTheDocument();
  expect(screen.getByText("13,8–16,9")).toBeInTheDocument();
});

it("explains missing relief", () => {
  render(<TimingPanel {...props} analysis={{ ...analysis, relief: null }} />);
  expect(screen.getByText(/нет треугольников/)).toBeInTheDocument();
});
```

`props` и `analysis` — минимальные заглушки по пропсам `TimingPanel`.

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd frontend && npx vitest run src/pages/design/viewPresets.test.ts src/pages/design/TimingPanel.test.tsx`
Expected: FAIL.

- [ ] **Step 3: Implement** слой, отрисовку, сводку, CSS.

- [ ] **Step 4: Run tests and typecheck**

Run: `cd frontend && npx vitest run && npx tsc --noEmit -p .`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/design/viewPresets.ts frontend/src/pages/design/viewPresets.test.ts frontend/src/pages/design/PlanCanvas.tsx frontend/src/pages/design/DesignPage.tsx frontend/src/pages/design/TimingPanel.tsx frontend/src/pages/design/TimingPanel.test.tsx frontend/src/styles/design.css
git commit -m "Темп отбойки: слой зон на плане и медиана с разбросом в панели «Тайминг»"
```

### Task 5: Проверка на блоке №66 и документация

**Files:**
- Create: `Docs/BURDEN_RELIEF.md`
- Modify: `CLAUDE.md` (короткий раздел «Темп отбойки» со ссылкой на модуль и документ)

- [ ] **Step 1: Full test run**

Run: `.venv/bin/python -m pytest tests -q --ignore-glob='tests/* [0-9].py'` и `cd frontend && npx vitest run && npx tsc --noEmit -p .`
Expected: всё зелёное (известный флейк `test_cad_block66_surface[scipy]` перезапустить отдельно).

- [ ] **Step 2: Блок №66 на стенде**

Тестовый стенд ветки (api-stand :8020 / frontend-stand :5181, без входа): импорт `tests/fixtures/cad/block66.dxf`, сетка из «Расчёта», шаблон «по рядам» НСИ 25/42, «Рассчитать тайминг», слой «Темп отбойки». Снимок плана с зонами и панелью — в PR. Записать медиану, разброс и долю вне коридора.

Expected: у мыса видны зоны другого цвета (стык цепочек), на прямой части — зона «ровно».

- [ ] **Step 3: Документ** `Docs/BURDEN_RELIEF.md`: определение и ссылка на Datamine, формула треугольника, отбраковка рёбер, показатели ровности (что значит `cv`, коридор ±25 %), зоны карты, цифры блока №66; что будет использовать перебор (часть 4: `ReliefStats.cv` и `outside_share`).

- [ ] **Step 4: Commit**

```bash
git add Docs/BURDEN_RELIEF.md CLAUDE.md
git commit -m "Темп отбойки: описание метрики и проверка на блоке №66"
```
