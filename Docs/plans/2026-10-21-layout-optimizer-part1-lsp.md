# ЛСП скважин первых рядов — план реализации (часть 1 оптимизатора раскладки)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** BlastEX считает ЛСП (линию сопротивления по подошве) для скважин первых рядов, показывает его на плане как карту «ЛСП» и предупреждает, когда ЛСП больше допустимого.

**Architecture:** Новый модуль `design/toe_line.py` строит линию подошвы откоса (из съёмки нижней бровки или от верхней бровки по углу откоса) и считает ЛСП от точки оси скважины на уровне подошвы уступа. Результат попадает в существующие карты (`design/maps.py`, метрика `floor_burden`) и проверки (`design/analysis.py::validate`, код `floor_burden_excess`); фронт добавляет метрику на карту, код в «здоровье» скважины и поле угла откоса.

**Tech Stack:** Python 3.13, shapely ≥ 2 (уже в зависимостях), FastAPI/pydantic; React + TypeScript, vitest.

**Spec:** `Docs/specs/2026-10-21-block-layout-optimizer-design.md` (раздел «ЛСП», ограничение 2).

## Global Constraints

- База ветки — `fix/pattern-fill-whole-contour` (PR #117): нужен `design/editing.py::row_index`/`previous_row_distance`. Отдельный PR с этой базой; после слияния #117 — перебазировать на `main`.
- Допустимое ЛСП = W × 1,03. W — `pattern_params["burden_b_m"]` (так в проект приходит сопротивление из листа «Расчёт»: `line_of_least_resistance_m = grid_b_m`); для `pattern == "square"` без `burden_b_m` — `spacing_a_m`.
- Угол откоса по умолчанию — 15° от вертикали. В модели `BenchSurface.face_angle_deg` хранится **от горизонтали**: 15° от вертикали = 75.
- Умолчание `BenchSurface.face_angle_deg = 90.0` в бэкенде не меняется: от него зависит хэш утверждённых паспортов. Значение 90 означает вертикальный откос (линия подошвы = верхняя бровка).
- Подписи в интерфейсе: метрика «ЛСП», единица «м»; код здоровья — «ЛСП больше допустимого»; поле — «Угол откоса от вертикали, °».
- Пользователю не показывать JSON (`CLAUDE.md`).

## Review Focus

- Блок без свободной поверхности (`free_faces` пуст): ЛСП нет (None), предупреждений нет, ошибок нет — Task 1, Task 2.
- В чертеже есть `cad.bottom`, но ни одно его ребро не лежит у свободной поверхности: ЛСП строится от верхней бровки по углу, а не по ребру тыла — Task 1.
- Старый паспорт с `face_angle_deg = 90`: линия подошвы совпадает с верхней бровкой, расчёт не падает — Task 1.
- Паттерн `square` без `burden_b_m`: допустимое ЛСП берётся от `spacing_a_m`; без обоих — проверки нет, карта есть — Task 2.
- Отключённые скважины и стенки (контур, пресплит, буфер, подрезка) не получают ЛСП и не дают предупреждений — Task 2.

---

### Task 1: Линия подошвы откоса

**Files:**
- Create: `design/toe_line.py`
- Test: `tests/test_toe_line.py`

**Interfaces:**
- Consumes: `design/geometry.py::drawing_bottom(contour) -> list[Point2] | None`, `BlockContour.points_xy`, `BlockContour.free_faces`, `BenchSurface.height_m`, `BenchSurface.face_angle_deg`.
- Produces:
  - `slope_offset_m(bench: BenchSurface) -> float` — смещение подошвы от верхней бровки в плане: `height_m × tan(90° − face_angle_deg)`, не меньше 0.
  - `@dataclass(frozen=True) class ToeLine: polylines: list[list[tuple[float, float]]]; source: str` — `source` ∈ `"survey"`, `"built"`.
  - `toe_line(contour: BlockContour) -> ToeLine | None` — None, если нет свободных поверхностей.
  - `TOE_SEARCH_MARGIN_M = 1.0`.

- [ ] **Step 1: Write the failing tests**

Прямоугольник 40 × 22 м, вершины CCW `(0,0),(40,0),(40,22),(0,22)`, свободная поверхность — ребро `[0, 1]` (линия y = 0), `bench = BenchSurface(crest_z_m=0, toe_z_m=-10, face_angle_deg=75)`.

```python
def test_offset_for_15_degrees_from_vertical():
    assert slope_offset_m(BenchSurface(crest_z_m=0, toe_z_m=-10, face_angle_deg=75)) == pytest.approx(2.6795, abs=1e-4)

def test_vertical_face_has_zero_offset():
    assert slope_offset_m(BenchSurface(crest_z_m=0, toe_z_m=-10, face_angle_deg=90)) == pytest.approx(0.0)

def test_built_toe_line_lies_outside_block_at_offset():
    line = toe_line(rect_contour())
    assert line.source == "built"
    ys = [y for poly in line.polylines for _, y in poly]
    assert all(y == pytest.approx(-2.6795, abs=1e-3) for y in ys)

def test_survey_toe_line_uses_bottom_ring_edge_near_free_face():
    # cad.bottom — кольцо по нижней бровке: фронт на y = -3, тыл и фланги совпадают с контуром.
    contour = rect_contour(cad={"bottom": [[0, -3], [40, -3], [40, 22], [0, 22]]})
    line = toe_line(contour)
    assert line.source == "survey"
    ys = {round(y, 6) for poly in line.polylines for _, y in poly}
    assert ys == {-3.0}  # только фронтальное ребро, без тыла y = 22

def test_edited_contour_ignores_survey():
    contour = rect_contour(cad={"bottom": [[0, -3], [40, -3], [40, 22], [0, 22]], "edited": True})
    assert toe_line(contour).source == "built"

def test_survey_without_edge_near_face_falls_back_to_built():
    contour = rect_contour(cad={"bottom": [[0, -30], [40, -30], [40, 22], [0, 22]]})
    assert toe_line(contour).source == "built"

def test_no_free_faces_gives_none():
    assert toe_line(rect_contour(free_faces=[])) is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_toe_line.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'design.toe_line'`.

- [ ] **Step 3: Implement `design/toe_line.py`**

- Построенная линия: каждая полилиния свободной поверхности (индексы `free_faces` → точки `points_xy`) смещается `shapely.LineString.offset_curve(±offset)`; берётся та сторона, у которой средняя точка смещённой линии лежит **вне** полигона контура. При `offset == 0` — сама полилиния.
- Съёмка: рёбра кольца `drawing_bottom(contour)`, у которых середина ребра не дальше `slope_offset_m + TOE_SEARCH_MARGIN_M` от ближайшей полилинии свободной поверхности; соседние такие рёбра склеиваются в полилинию. Нет ни одного ребра — возврат к построенной линии.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_toe_line.py -q`
Expected: PASS (7 passed).

- [ ] **Step 5: Commit**

```bash
git add design/toe_line.py tests/test_toe_line.py
git commit -m "ЛСП: линия подошвы откоса — по съёмке нижней бровки или от верхней бровки по углу"
```

### Task 2: ЛСП скважины и допустимое значение

**Files:**
- Modify: `design/toe_line.py`
- Test: `tests/test_toe_line.py`

**Interfaces:**
- Consumes: Task 1 (`toe_line`, `ToeLine`); `design/editing.py::row_index(holes)`, `previous_row_distance(index, hole)`; `design/models.py::row_family`.
- Produces:
  - `TOE_BURDEN_TOLERANCE = 0.03`
  - `floor_point(hole: Hole) -> tuple[float, float]` — точка оси на уровне подошвы уступа: забой минус перебор вдоль оси (`toe − unit(toe − collar) × subdrill_m`), в плане.
  - `allowed_floor_burden_m(pattern_params: dict | None) -> float | None` — W × (1 + 0,03); W из `burden_b_m`, для `square` без него — `spacing_a_m`; иначе None.
  - `@dataclass(frozen=True) class FloorBurden: hole_id: str; value_m: float; allowed_m: float | None; excess: bool`
  - `floor_burdens(design: BlastDesign) -> dict[str, FloorBurden]` — только включённые скважины группы сетки (`row_family(kind) == "grid"`), которые стоят у откоса: соседнего ряда впереди нет (`previous_row_distance is None`) или ЛСП не больше расстояния до него.

- [ ] **Step 1: Write the failing tests**

Тот же прямоугольник (угол 75, H = 10 м, смещение 2,6795 м), `pattern_params={"pattern": "rectangular", "spacing_a_m": 4.0, "burden_b_m": 3.7}`.

```python
def test_vertical_hole_floor_burden_adds_slope_offset():
    hole = vertical_hole("1-01", x=10, y=3.7, row=0, subdrill=1.0)
    fb = floor_burdens(design_with([hole]))["1-01"]
    assert fb.value_m == pytest.approx(3.7 + 2.6795, abs=1e-3)
    assert fb.allowed_m == pytest.approx(3.811)
    assert fb.excess is True

def test_hole_inclined_15_degrees_to_face_cancels_offset():
    # Наклон 15° к откосу (азимут 180° — к линии y = 0): на глубине H = 10 м ось
    # уходит к откосу на 2,6795 м — ровно на смещение подошвы. ЛСП = расстоянию
    # от устья до верхней бровки.
    hole = inclined_hole("1-01", x=10, y=3.7, row=0, angle_deg=15, azimuth_deg=180, bench_h=10, subdrill=1.0)
    assert floor_burdens(design_with([hole]))["1-01"].value_m == pytest.approx(3.7, abs=1e-3)

def test_within_three_percent_is_not_excess():
    hole = vertical_hole("1-01", x=10, y=3.8 - 2.6795, row=0)
    assert floor_burdens(design_with([hole]))["1-01"].excess is False

def test_second_row_hole_has_no_floor_burden():
    first = vertical_hole("1-01", x=10, y=1.0, row=0)
    second = vertical_hole("2-01", x=10, y=4.7, row=1)
    result = floor_burdens(design_with([first, second]))
    assert "1-01" in result and "2-01" not in result

def test_walls_and_disabled_holes_are_skipped():
    wall = vertical_hole("K1-01", x=10, y=1.0, row=-1, kind="contour")
    off = vertical_hole("1-02", x=20, y=1.0, row=0, enabled=False)
    assert floor_burdens(design_with([wall, off])) == {}

def test_square_pattern_uses_spacing_as_w():
    assert allowed_floor_burden_m({"pattern": "square", "spacing_a_m": 4.0}) == pytest.approx(4.12)

def test_no_w_means_no_check():
    hole = vertical_hole("1-01", x=10, y=20.0, row=0)
    fb = floor_burdens(design_with([hole], pattern_params={}))["1-01"]
    assert fb.allowed_m is None and fb.excess is False
```

Вспомогательные `vertical_hole` / `inclined_hole` / `design_with` — в тестовом файле (Hole с collar на z = 0, toe по оси; `BlastDesign(design_id="t", contour=rect_contour(), holes=[...], pattern_params=...)`).

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_toe_line.py -q`
Expected: FAIL — `ImportError: cannot import name 'floor_burdens'`.

- [ ] **Step 3: Implement `floor_point`, `allowed_floor_burden_m`, `floor_burdens` in `design/toe_line.py`**

ЛСП — расстояние в плане от `floor_point(hole)` до ближайшей полилинии `toe_line(contour)`; индекс рядов `row_index(enabled)` строится один раз на вызов.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_toe_line.py -q`
Expected: PASS (14 passed).

- [ ] **Step 5: Commit**

```bash
git add design/toe_line.py tests/test_toe_line.py
git commit -m "ЛСП: расчёт для скважин у откоса и допустимое значение W + 3%"
```

### Task 3: Карта «ЛСП» и предупреждение о превышении в API

**Files:**
- Modify: `design/maps.py` (`MAP_METRICS`, `hole_map_record`, `engineering_maps`)
- Modify: `design/analysis.py` (`validate`)
- Modify: `api/schemas/design.py` (`HoleMapSampleSchema`)
- Test: `tests/test_design_maps.py`, `tests/test_design_analysis.py`, `tests/test_toe_line_api.py` (create)

**Interfaces:**
- Consumes: Task 2 (`floor_burdens(design) -> dict[str, FloorBurden]`).
- Produces:
  - Метрика `"floor_burden"` в `MAP_METRICS`; в записи скважины ключ `"floor_burden": float | None` (None — скважина не у откоса); в `stats["floor_burden"]` — по скважинам со значением.
  - `hole_map_record(hole, holes, contour, floor_burden: float | None = None)`.
  - Предупреждение `{"code": "floor_burden_excess", "hole_id": id, "message": "ЛСП {value} м больше допустимого {allowed} м (W + 3%)."}` — числа с одним знаком, запятая как разделитель (как в соседних сообщениях `validate`).
  - `HoleMapSampleSchema.floor_burden: float | None = None`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_design_maps.py
def test_engineering_maps_include_floor_burden_for_face_holes():
    maps = engineering_maps(face_design())  # прямоугольник Task 1, ряды 0 и 1
    assert "floor_burden" in maps["metrics"]
    by_id = {r["hole_id"]: r for r in maps["holes"]}
    assert by_id["1-01"]["floor_burden"] == pytest.approx(3.7 + 2.68, abs=0.01)
    assert by_id["2-01"]["floor_burden"] is None
    assert maps["stats"]["floor_burden"]["count"] == 1.0

# tests/test_design_analysis.py
def test_validate_warns_when_floor_burden_exceeds_w_plus_3_percent():
    warnings = validate(face_design())
    excess = [w for w in warnings if w["code"] == "floor_burden_excess"]
    assert [w["hole_id"] for w in excess] == ["1-01"]
    assert "ЛСП 6,4 м больше допустимого 3,8 м" in excess[0]["message"]

# tests/test_toe_line_api.py
def test_maps_endpoint_returns_floor_burden(client):
    body = client.post("/api/v1/design/maps", json={"design": face_design().to_dict()}).json()
    assert "floor_burden" in body["metrics"]
    assert any(h["floor_burden"] is not None for h in body["holes"])
```

Запрос `/design/maps` — по форме `EngineeringMapsRequest` (смотри `api/schemas/design.py:1052`); клиент — как в `tests/test_api_geometry.py`.

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_design_maps.py tests/test_design_analysis.py tests/test_toe_line_api.py -q`
Expected: FAIL — нет ключа `floor_burden`, нет кода `floor_burden_excess`.

- [ ] **Step 3: Implement**

`engineering_maps` вызывает `floor_burdens(design)` один раз и передаёт значение в `hole_map_record`; `validate` берёт превышения из того же `floor_burdens(design)`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_design_maps.py tests/test_design_analysis.py tests/test_toe_line_api.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add design/maps.py design/analysis.py api/schemas/design.py tests/test_design_maps.py tests/test_design_analysis.py tests/test_toe_line_api.py
git commit -m "ЛСП: метрика карты floor_burden и предупреждение floor_burden_excess"
```

### Task 4: ЛСП на плане и в «здоровье» скважины

**Files:**
- Modify: `frontend/src/types/design.ts` (`MapMetric`, `MAP_METRIC_LABELS`, `MAP_METRIC_UNITS`, `HoleMapSample`)
- Modify: `frontend/src/pages/design/holeHealth.ts` (`HoleHealthCode`, `HEALTH_LABELS`, `HEALTH_COLORS`, `WARNING_CODE_TO_HEALTH`)
- Test: `frontend/src/pages/design/holeHealth.test.ts`

**Interfaces:**
- Consumes: Task 3 (`floor_burden` в `HoleMapSample`, код `floor_burden_excess`).
- Produces: `MapMetric` включает `"floor_burden"` (подпись «ЛСП», единица «м»); `HoleHealthCode` включает `"floor_burden_excess"` (подпись «ЛСП больше допустимого», цвет `#c0392b`). В `severity()` новый код стоит на уровне `short_bench`: ниже «нет связи» и «нет заряда», выше «ok».

- [ ] **Step 1: Write the failing test**

По образцу теста «flags holes outside contour polygon» в `holeHealth.test.ts`: заряженная, связанная скважина внутри контура.

```ts
it("flags holes whose floor burden exceeds the allowed value", () => {
  const code = computeHoleHealth(hole, {
    load, network, contour,
    warnings: [{ code: "floor_burden_excess", hole_id: hole.id, message: "" }],
  });
  expect(code).toBe("floor_burden_excess");
  expect(HEALTH_LABELS.floor_burden_excess).toBe("ЛСП больше допустимого");
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/pages/design/holeHealth.test.ts`
Expected: FAIL.

- [ ] **Step 3: Implement** — добавить ключи в перечисленные записи; селектор «Карта» в `DesignPage.tsx` строится по `MAP_METRIC_LABELS` и подхватит метрику сам (проверь; если список метрик задан отдельно — добавь туда).

- [ ] **Step 4: Run tests and typecheck**

Run: `cd frontend && npx vitest run src/pages/design && npx tsc --noEmit -p .`
Expected: PASS, `tsc` без ошибок.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/types/design.ts frontend/src/pages/design/holeHealth.ts frontend/src/pages/design/holeHealth.test.ts
git commit -m "ЛСП: метрика на карте плана и код здоровья «ЛСП больше допустимого»"
```

### Task 5: Угол откоса — поле на блоке и умолчание объекта

**Files:**
- Modify: `frontend/src/pages/design/SurfacePanel.tsx` (секция «Бровки», рядом с полями отметок, ~строка 204)
- Modify: `frontend/src/pages/calc/calcInputs.ts` (`CalcInputs`: необязательное поле `face_angle_from_vertical_deg`, умолчание 15)
- Modify: `frontend/src/pages/design/DesignPage.tsx` (перенос варианта из «Расчёта», ~строки 507–515)
- Test: `frontend/src/pages/design/SurfacePanel.test.tsx`, тест переноса варианта рядом с существующими (`designParams.test.ts`)

**Interfaces:**
- Consumes: `BenchSurface.face_angle_deg` (от горизонтали), `onBenchChange(patch)`.
- Produces:
  - Поле «Угол откоса от вертикали, °», диапазон 0–60, значение `90 − face_angle_deg`; изменение пишет `face_angle_deg = 90 − value`.
  - `CalcInputs.face_angle_from_vertical_deg?: number` — в старых настройках поля нет, тогда 15.
  - При переносе варианта в проект: если у объекта задан угол (или умолчание 15), `contour.bench.face_angle_deg = 90 − угол` для нового проекта; у открытого проекта с уже заданным углом — не трогать.

- [ ] **Step 1: Write the failing tests**

```tsx
it("shows face angle from vertical and writes it back from horizontal", async () => {
  const onBenchChange = vi.fn();
  render(<SurfacePanel {...props} bench={{ crest_z_m: 0, toe_z_m: -10, face_angle_deg: 75 }} onBenchChange={onBenchChange} />);
  // секция «Бровки» свёрнута по умолчанию — раскрыть
  const input = screen.getByLabelText("Угол откоса от вертикали, °");
  expect(input).toHaveValue(15);
  fireEvent.change(input, { target: { value: "20" } });
  expect(onBenchChange).toHaveBeenCalledWith({ face_angle_deg: 70 });
});
```

```ts
it("old calc inputs without face angle default to 15 degrees from vertical", () => {
  expect(faceAngleFromVertical({ ...oldInputs })).toBe(15);
});
```

`faceAngleFromVertical(inputs: Partial<CalcInputs>) -> number` — экспорт из `calcInputs.ts`.

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd frontend && npx vitest run src/pages/design/SurfacePanel.test.tsx src/pages/calc`
Expected: FAIL.

- [ ] **Step 3: Implement** поле, `faceAngleFromVertical`, перенос при отправке варианта.

- [ ] **Step 4: Run tests and typecheck**

Run: `cd frontend && npx vitest run && npx tsc --noEmit -p .`
Expected: PASS.

- [ ] **Step 5: Full backend run and commit**

Run: `.venv/bin/python -m pytest tests -q --ignore-glob='tests/* [0-9].py'`
Expected: все тесты проходят (известный флейк `test_cad_block66_surface[scipy]` перезапустить отдельно).

```bash
git add frontend/src/pages/design/SurfacePanel.tsx frontend/src/pages/design/SurfacePanel.test.tsx frontend/src/pages/calc/calcInputs.ts frontend/src/pages/design/DesignPage.tsx
git commit -m "ЛСП: угол откоса от вертикали на блоке, умолчание 15° с объекта"
```
