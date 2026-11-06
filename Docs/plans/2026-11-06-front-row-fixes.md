# Правки первого ряда у откоса — план (PR 1 из 3)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Глубина из параметров — по вертикали, минимальный отступ устья 0,5 м, наклонная пары — к откосу (±15° от столбца), угол пары поднимается до 30°, если ЛСП не в допуске.

**Architecture:** Правки в `design/geometry.py` (глубина), `design/toe_line.py` (умолчание отступа), `design/pattern.py` (`_face_pairs`, `_tilt_caps_m`). Перебор (`design/layout_search/`) берёт всё через генератор и отдельных правок не требует. Фронт — только подпись поля отступа.

**Tech Stack:** Python 3.12, shapely 2, pytest; React + TypeScript, vitest.

**Spec:** `Docs/specs/2026-11-06-back-anchored-pattern-design.md`, раздел «Правки первого ряда у откоса (оба шаблона)». Шаблон «от тыла» — планы PR 2 и PR 3, отдельно.

## Global Constraints

- Ключи `pattern_params` пишутся только когда заданы (хэш утверждённых паспортов); новых ключей этот PR не вводит.
- Умолчание бэкенда `face_angle_deg = 90` не трогать.
- Значение «Глубина» (`depth_m`, `contour_depth_m`, `presplit_depth_m`, `trim_depth_m`, `satellite_depth_m`, `stab_depth_m`) — глубина вертикальной скважины; у наклонной длина по оси = значение / cos α.
- Сохранённые черновики: автопересчёт (`design/hole_recompute.py`) длины при заданной глубине не меняет — меняет только новая генерация.
- `MIN_CREST_OFFSET_DEFAULT_M = 0.5`.
- Азимут наклонной пары отклоняется от линии столбца (`−advance_dir`) не больше 15°.
- Угол пары: предпочтительный — `front_rows_tilt_deg`; если с ним ЛСП > W + 3 %, поднимать до `FRONT_ROWS_TILT_MAX_DEG = 30°`, наименьший угол, при котором ЛСП ≤ W + 3 %; нижняя граница ЛСП max(0,8·W, 1 м) действует всегда.
- Плавный переход (`taper`) в этом PR не меняется.
- Общение и тексты — по-русски; справка/доки обновляются в том же PR.

## Review Focus

- Бровка под углом больше 15° к рядам: азимут пары упирается в предел 15°, а не уходит вдоль бровки — тест в Task 3.
- Предпочтительный угол уже даёт ЛСП в допуске: угол не поднимается выше `front_rows_tilt_deg` — тест в Task 4.
- Даже 30° не хватает: пара ставится с наибольшим допустимым углом, ЛСП остаётся с предупреждением `floor_burden_excess`, ничего не падает — тест в Task 4.
- Явная глубина и наклон 90° (cos α = 0): деление на ноль не возникает — тест в Task 1.
- Открытие старого черновика с `depth_m` и наклонными: длины не меняются при автопересчёте — тест в Task 1.

---

### Task 1: Глубина из параметров — по вертикали

**Files:**
- Modify: `design/geometry.py` (`hole_depth_m`, ~строки 300–340)
- Test: `tests/test_hole_depth_vertical.py` (новый)

**Interfaces:**
- Produces: `hole_depth_m(collar, angle_deg, azimuth_deg, subdrill_m, contour, surfaces=None, depth_m=None) -> float` — при `depth_m` возвращает `depth_m / cos α` (при |cos α| < 1e-9 — `depth_m`), без `depth_m` — как сейчас.

- [ ] **Step 1: Write the failing tests**

```python
def test_explicit_depth_is_vertical_for_inclined_hole():
    length = hole_depth_m(Point3(x=0, y=0, z=10), 30.0, 180.0, 1.0, CONTOUR, None, 10.0)
    assert length == pytest.approx(10.0 / math.cos(math.radians(30.0)))

def test_explicit_depth_unchanged_for_vertical_hole():
    assert hole_depth_m(Point3(x=0, y=0, z=10), 0.0, 0.0, 1.0, CONTOUR, None, 10.0) == pytest.approx(10.0)

def test_explicit_depth_at_ninety_degrees_does_not_divide_by_zero():
    assert hole_depth_m(Point3(x=0, y=0, z=10), 90.0, 0.0, 1.0, CONTOUR, None, 10.0) == pytest.approx(10.0)

def test_generated_inclined_grid_toe_at_same_elevation_as_vertical():
    # angle_deg = 20, depth_m = 11: забой каждой скважины на collar.z − 11.
    holes = generate_pattern(CONTOUR, {**PATTERN, "angle_deg": 20.0, "depth_m": 11.0})
    assert all(h.collar.z - h.toe.z == pytest.approx(11.0) for h in holes)

def test_recompute_keeps_length_of_saved_draft_with_explicit_depth():
    # Старый черновик: наклонная 20°, длина по оси 11 (прежний смысл).
    hole = inclined(angle=20.0, length=11.0)
    out = recompute_hole(hole, CONTOUR, None, {"depth_m": 11.0}).hole
    assert out.length_m == pytest.approx(11.0)
```

`CONTOUR`, `PATTERN` — прямоугольник 40×30 с откосом, уступ 10 м (как в `tests/front_rows_fixtures.py::rect_contour` и `PATTERN`); `inclined` — `front_rows_fixtures.inclined_hole` с заданной длиной.

- [ ] **Step 2: Run to verify fail** — `pytest tests/test_hole_depth_vertical.py -v`; первые и четвёртый тест FAIL (длина 10 вместо 11,547; разница отметок 10,34 вместо 11).
- [ ] **Step 3: Implement** — в `hole_depth_m` ветка `depth_m is not None`; докстринг: «явная глубина — по вертикали». Остальные вызовы (`drape_collar`, `editing.insert_manual_hole`) правок не требуют.
- [ ] **Step 4: Run** — `pytest tests/test_hole_depth_vertical.py tests/test_hole_recompute.py tests/test_design_pattern*.py -q`; всё PASS (тесты, ожидавшие длину по оси при наклоне, поправить на новое правило с комментарием).
- [ ] **Step 5: Commit** — `git commit -m "Глубина из параметров сетки — по вертикали: у наклонной длина = глубина / cos α"`

### Task 2: Минимальный отступ устья от бровки — 0,5 м

**Files:**
- Modify: `design/toe_line.py:75` (`MIN_CREST_OFFSET_DEFAULT_M = 0.5`), `design/analysis.py:263` (докстринг «без ключа — 0,5 м»)
- Modify: `frontend/src/pages/design/PatternPanel.tsx:240-247` (title «Пусто — 0,5 м.», placeholder `"0,5"`)
- Test: `tests/test_design_pattern_face_pair.py` (`test_constants`, `test_no_pair_when_collar_too_close_to_crest`), `frontend/src/pages/design/PatternPanel.test.tsx`

**Interfaces:**
- Produces: `MIN_CREST_OFFSET_DEFAULT_M == 0.5`; `min_crest_offset_m({}) == 0.5`.

- [ ] **Step 1: Update tests** — `test_constants`: `MIN_CREST_OFFSET_DEFAULT_M == 0.5`. `test_no_pair_when_collar_too_close_to_crest`: первый ряд в 1,4 м — устье пары 0,4 м < 0,5 м, пар нет; при `min_crest_offset_m: 0.3` — пара у каждой скважины первого ряда. Во фронт-тесте — placeholder `"0,5"`.
- [ ] **Step 2: Run to verify fail** — `pytest tests/test_design_pattern_face_pair.py -k "constants or too_close" -v` FAIL.
- [ ] **Step 3: Implement** — константа, докстринги, подпись и placeholder поля.
- [ ] **Step 4: Run** — `pytest tests/ -q -k "crest or face_pair or layout_search or front"` и `npx vitest run src/pages/design/PatternPanel.test.tsx`; PASS. Перебор этап 1 теперь начинает отступ с 0,5 м (`space.stage1`, `o0`) — тесты `tests/test_layout_search*` поправить там, где ожидали 1 м.
- [ ] **Step 5: Commit** — `git commit -m "Минимальный отступ устья от бровки по умолчанию — 0,5 м"`

### Task 3: Азимут наклонной пары — к откосу, не дальше 15° от столбца

**Files:**
- Modify: `design/pattern.py` (`_face_pairs` ~743–870, `_tilt_caps_m` ~610–673; новая константа рядом с `FACE_PAIR_OFFSET_M`)
- Test: `tests/test_design_pattern_face_pair.py`

**Interfaces:**
- Produces: `FACE_PAIR_AZIMUTH_MAX_DEVIATION_DEG = 15.0`; `_tilt_caps_m(contour, collars, heights, directions: list[tuple[float, float]], tilt_deg, target_m)` — направление на каждую скважину (вызов из `_taper_front_rows` передаёт `[direction] * n`, поведение перехода не меняется).
- Направление пары: единичный вектор от устья пары к ближайшей точке линии подошвы (`toe_positions(...).toe_point` по точке устья пары); если угол к `−advance_dir` больше 15° — повернуть до 15° в ту же сторону. Устье пары — как сейчас, на 1 м по `−advance_dir`.

- [ ] **Step 1: Write the failing tests**

```python
def test_pair_tilts_toward_slanted_face_within_limit():
    # Бровка повёрнута на 10° к рядам (ряды — азимут 90°): нормаль к бровке — 170°.
    holes = generate_pattern(slanted_contour(10.0), BASE)
    assert _pairs(holes)
    for pair in _pairs(holes):
        assert pair.azimuth_deg == pytest.approx(170.0, abs=0.5)

def test_pair_azimuth_clamped_to_fifteen_degrees_from_column():
    holes = generate_pattern(slanted_contour(30.0), BASE)
    for pair in _pairs(holes):
        assert pair.azimuth_deg == pytest.approx(165.0, abs=0.5)

def test_pair_on_straight_face_keeps_column_azimuth():
    holes = generate_pattern(CONTOUR, BASE)
    assert all(p.azimuth_deg == pytest.approx(180.0, abs=1e-6) for p in _pairs(holes))
```

`slanted_contour(deg)` — четырёхугольник (0, 0), (40, 40·tg deg), (40, 30), (0, 30); свободное — ребро [0, 1], его наружная нормаль — азимут 180° − deg; откос 75°, уступ 10 м. Помощник — в тестовом файле.

- [ ] **Step 2: Run to verify fail** — первые два FAIL (азимут 180°).
- [ ] **Step 3: Implement** — направления на каждую пару, `_tilt_caps_m` с `directions`, `drape_collar` с азимутом своей пары.
- [ ] **Step 4: Run** — `pytest tests/test_design_pattern_face_pair.py tests/test_design_pattern_front_tilt.py tests/test_front_rows_consumers.py -q` PASS.
- [ ] **Step 5: Commit** — `git commit -m "Наклонная пары — к откосу, не дальше 15° от линии столбца"`

### Task 4: Угол пары поднимается до 30°, если ЛСП не в допуске

**Files:**
- Modify: `design/pattern.py` (`_face_pairs`)
- Test: `tests/test_design_pattern_face_pair.py`

**Interfaces:**
- Consumes: Task 3 (`directions`).
- Produces: угол пары = как сейчас при `front_rows_tilt_deg`; если ЛСП построенной пары > `allowed_m` (W + 3 %), — наименьший угол в (tilt_deg, 30°], при котором ЛСП ≤ `allowed_m`, но не больше наибольшего угла, при котором ЛСП ≥ `target_m` и забой не за подошвой; проверка по построенной скважине (`_verified_angles` / `_tilt_holds`).

- [ ] **Step 1: Write the failing tests**

```python
def test_pair_angle_raised_above_preferred_when_lsp_exceeds():
    # α = 5°: ЛСП 4,68 − 10·tg 5° = 3,81 > 3,605 → угол поднимается до tg α = (4,68 − 3,605)/10.
    holes = generate_pattern(CONTOUR, BASE | {"front_rows_tilt_deg": 5})
    expected = math.degrees(math.atan((2.0 + SLOPE_M - 3.5 * 1.03) / H))
    assert all(p.angle_deg == pytest.approx(expected, abs=0.05) for p in _pairs(holes))

def test_preferred_angle_kept_when_lsp_fits():
    # BASE (15°): угол ограничен ЛСП ≥ 2,8 — как в test_pair_added_one_metre_closer_along_column.
    holes = generate_pattern(CONTOUR, BASE)
    expected = math.degrees(math.atan((2.0 + SLOPE_M - 2.8) / H))
    assert all(p.angle_deg == pytest.approx(expected, abs=1e-3) for p in _pairs(holes))

def test_pair_capped_at_thirty_degrees_when_even_that_is_not_enough():
    # Первый ряд в 9 м: устье пары в 8 м, ЛСП при 30° = 8 + 2,68 − 10·tg 30° = 4,91 > 3,605.
    holes = generate_pattern(CONTOUR, BASE | {"offset_from_face_m": 9.0})
    pairs = _pairs(holes)
    assert pairs and all(p.angle_deg == pytest.approx(30.0, abs=0.05) for p in pairs)
    codes = {w["code"] for w in validate(_design(holes))}
    assert "floor_burden_excess" in codes
```

`test_pair_angle_capped_by_max_tilt` удалить: его ожидание (5°) противоречит решению владельца.

- [ ] **Step 2: Run to verify fail** — первый и третий FAIL.
- [ ] **Step 3: Implement** в `_face_pairs`.
- [ ] **Step 4: Run** — `pytest tests/ -q -k "face_pair or front or layout_search or toe_line"` PASS.
- [ ] **Step 5: Commit** — `git commit -m "Угол пары поднимается до 30°, если ЛСП больше W + 3 %"`

### Task 5: Документация и полная проверка

**Files:**
- Modify: `CLAUDE.md` (раздел «Первый ряд у откоса»: «`min_crest_offset_m` (умолчание 0,5 м)», азимут пары к откосу ≤ 15°, подъём угла до 30°; раздел перебора: «без ключа — 0,5 м»), `Docs/FRONT_ROWS_TILT.md` (таблица параметров, схема 2), `Docs/LAYOUT_SEARCH.md` (отступ с 0,5 м), справка вкладки «Сетка», если в ней есть эти числа (`git grep -n "1 м" frontend/src/pages/design/*Help*`).

- [ ] **Step 1:** обновить тексты.
- [ ] **Step 2:** `pytest tests/ -q` — все PASS; `cd frontend && npx tsc -b && npx vitest run` — PASS (тесты экономики, нестабильные под нагрузкой, перезапустить отдельно).
- [ ] **Step 3:** `git commit -m "Документация: первый ряд у откоса — 0,5 м, азимут к откосу, подъём угла"`
