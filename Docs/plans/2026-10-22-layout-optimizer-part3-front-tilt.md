# Наклон скважин 1–2 ряда у откоса — план реализации (часть 3 оптимизатора раскладки)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Генератор сетки умеет наклонять скважины 1–2 ряда у откоса отдельно от остальных рядов: к откосу, перпендикулярно ближайшему участку верхней бровки, на заданный угол (0–30°, по умолчанию 15°). ЛСП этих скважин уменьшается за счёт сдвига точки на подошве к откосу.

**Architecture:** В `design/geometry.py` — новая функция азимута «к откосу» для точки в плане. `design/pattern.py::generate_pattern` читает два новых ключа параметров и задаёт угол и азимут скважинам основной сетки в рядах 1–2 у откоса; остальные ряды, стенки, стабилизация и сателлиты — как сейчас. Фронт добавляет два поля во вкладку «Сетка». ЛСП (`design/toe_line.py::floor_point`) уже учитывает наклон и не меняется.

**Tech Stack:** Python 3.13, shapely ≥ 2; React + TypeScript, vitest.

**Spec:** `Docs/specs/2026-10-21-block-layout-optimizer-design.md` — ограничение 4 («Наклон скважин 1–2 ряда — не более 30° от вертикали, предпочтительно 15°. Остальные ряды — как в паспорте»), «Порядок работ», п. 3; решения владельца 22.10.2026 (в чате): см. Global Constraints.

## Global Constraints

- База ветки — `feat/burden-relief` (PR #121); ветка `feat/front-rows-tilt`, отдельный PR с этой базой.
- Ключи `pattern_params` (имена фиксированы):
  - `front_rows_tilt_count` — 0, 1 или 2; нет ключа — 0 (сетка как сейчас).
  - `front_rows_tilt_deg` — угол от вертикали, 0–30, нет ключа — 15; значения вне диапазона приводятся к границам (`FRONT_ROWS_TILT_MAX_DEG = 30`, `FRONT_ROWS_TILT_DEFAULT_DEG = 15`).
- Ключи пишутся в паспорт только когда заданы: во фронте их нет в `DEFAULT_PATTERN_PARAMS`; без них вывод `generate_pattern` побитно совпадает с текущим (хэш утверждённых паспортов не меняется).
- Ряд 1 — ряд, ближайший к откосу: ряд вдоль бровки, если он включён (`first_row_follow_face`); иначе первый ряд решётки вместе с рядами впереди него (номера ниже `FRONT_ROW_BASE`). Ряд 2 — следующий ряд решётки за рядом 1.
- Наклоняются только скважины основной сетки (вид основной сетки: production или `default_kind`), в т. ч. в переменной сетке (`variable`) и в обходе доменов. Стенки (контур, пресплит, подрезка, буфер), стабилизация и сателлиты не меняются.
- Азимут — направление от устья к откосу: перпендикуляр к ближайшему отрезку свободной поверхности (`contour.free_faces`), наружу из блока; 0° — север (+Y), по часовой (как `Hole.azimuth_deg`). Нет свободных поверхностей — наклон не применяется.
- Устья не сдвигаются; длина — прежняя формула `L = (S − Z)/cos α + Δ` (`geometry.hole_depth_m` через `drape_collar`).
- Подписи в интерфейсе: «Наклонных рядов у откоса» (0 / 1 / 2), «Наклон рядов у откоса, ° от вертикали» (0–30). JSON пользователю не показывать.

## Review Focus

- Параметров нет — список скважин тот же, что до изменения (координаты, углы, номера) — Task 2.
- Изогнутая бровка: соседние скважины ряда 1 получают разные азимуты, каждый перпендикулярен своему участку бровки и смотрит наружу — Task 1, Task 2.
- Угол 45 в параметрах — приводится к 30; отрицательный — к 0; `front_rows_tilt_count = 5` — к 2 — Task 2.
- Ряд вдоль бровки включён: он — ряд 1, первый ряд решётки — ряд 2 — Task 2.
- Пересчёт глубин после генерации (`hole_recompute`) сохраняет наклон и азимут — Task 2.

---

### Task 1: Азимут «к откосу» для точки в плане

**Files:**
- Modify: `design/geometry.py`
- Test: `tests/test_design_geometry.py`

**Interfaces:**
- Produces: `face_azimuth_deg(point_xy: tuple[float, float], contour: BlockContour) -> float | None` — азимут (0° = +Y, по часовой) перпендикуляра от точки к ближайшему отрезку свободных поверхностей, направленного наружу из блока; None без свободных поверхностей. Для точки, чья проекция падает на вершину стыка двух отрезков, — нормаль ближайшего отрезка (биссектриса не нужна).

- [ ] **Step 1: Write the failing tests**

```python
def test_face_azimuth_points_out_of_block_to_south_face():
    contour = rect_contour(40, 22, free_faces=[[0, 1]])  # бровка y = 0, блок выше
    assert face_azimuth_deg((10.0, 5.0), contour) == pytest.approx(180.0)

def test_face_azimuth_east_face():
    contour = rect_contour(40, 22, free_faces=[[1, 2]])  # бровка x = 40
    assert face_azimuth_deg((30.0, 10.0), contour) == pytest.approx(90.0)

def test_face_azimuth_follows_nearest_segment_of_bent_crest():
    # бровка из двух отрезков под углом: у каждого свой перпендикуляр
    contour = bent_face_contour()
    a1 = face_azimuth_deg(point_near_first_segment, contour)
    a2 = face_azimuth_deg(point_near_second_segment, contour)
    assert a1 != pytest.approx(a2)

def test_face_azimuth_none_without_free_faces():
    assert face_azimuth_deg((10.0, 5.0), rect_contour(40, 22, free_faces=[])) is None
```

Помощники (`rect_contour` с параметром `free_faces`, `bent_face_contour`) — в тестовом файле или по образцу `tests/test_toe_line.py`.

- [ ] **Step 2: Run tests — FAIL** (`.venv/bin/python -m pytest tests/test_design_geometry.py -q -k face_azimuth`).
- [ ] **Step 3: Implement** — ближайший отрезок через `point_to_segment_distance`; направление «наружу» — от точки к ближайшей точке отрезка, а если точка лежит на отрезке — внешняя нормаль (по ориентации контура, `ensure_ccw`).
- [ ] **Step 4: Run tests — PASS.**
- [ ] **Step 5: Commit** — «Геометрия: азимут к откосу для точки в плане».

### Task 2: Наклон 1–2 ряда в генераторе сетки

**Files:**
- Modify: `design/pattern.py` (`generate_pattern`, `place_row`, `_generate_face_following_row`, `_walk_domain_row`)
- Test: `tests/test_design_pattern_front_tilt.py` (create)

**Interfaces:**
- Consumes: Task 1 (`face_azimuth_deg`).
- Produces: `FRONT_ROWS_TILT_MAX_DEG = 30.0`, `FRONT_ROWS_TILT_DEFAULT_DEG = 15.0`; ключи `front_rows_tilt_count`, `front_rows_tilt_deg` в `generate_pattern`.

- [ ] **Step 1: Write the failing tests** (прямоугольник `_rect_contour(40, 30)` из `tests/test_design_pattern.py`, свободная поверхность — нижнее ребро y = 0, `row_azimuth_deg` такой, чтобы ряды шли вдоль бровки; a = 4, b = 3,5, отступ от откоса 2 м)

```python
def test_without_keys_pattern_is_unchanged():
    plain = generate_pattern(contour, base)
    assert holes_signature(plain) == holes_signature(generate_pattern(contour, base | {"front_rows_tilt_count": 0}))
    assert all(h.angle_deg == pytest.approx(0.0) for h in plain)
    assert holes_signature(plain) == REFERENCE_SIGNATURE  # снят на ветке до изменения и вписан в тест

def test_first_row_tilted_toward_face():
    holes = generate_pattern(contour, base | {"front_rows_tilt_count": 1})
    first, second = rows(holes)[0], rows(holes)[1]
    assert all(h.angle_deg == pytest.approx(15.0) and h.azimuth_deg == pytest.approx(180.0) for h in first)
    assert all(h.angle_deg == pytest.approx(0.0) for h in second)

def test_two_rows_tilted_with_custom_angle_and_clamp():
    holes = generate_pattern(contour, base | {"front_rows_tilt_count": 2, "front_rows_tilt_deg": 45})
    assert all(h.angle_deg == pytest.approx(30.0) for h in rows(holes)[0] + rows(holes)[1])
    assert all(h.angle_deg == pytest.approx(0.0) for h in rows(holes)[2])

def test_count_is_clamped():
    holes = generate_pattern(contour, base | {"front_rows_tilt_count": 5})
    assert all(h.angle_deg == pytest.approx(0.0) for h in rows(holes)[2])

def test_tilt_moves_floor_point_toward_face():
    from design.toe_line import floor_point
    vertical = rows(generate_pattern(contour, base))[0][0]
    tilted = rows(generate_pattern(contour, base | {"front_rows_tilt_count": 1}))[0][0]
    shift = floor_point(vertical)[1] - floor_point(tilted)[1]
    assert shift == pytest.approx(10.0 * math.tan(math.radians(15)), abs=0.05)  # H = 10 м

def test_face_following_row_is_row_one():
    holes = generate_pattern(contour, base | {"first_row_follow_face": True, "front_rows_tilt_count": 1})
    # ряд вдоль бровки наклонён, первый ряд решётки — нет

def test_walls_and_stab_keep_their_angles():
    # контурные/пресплит/стабилизация с включённым наклоном рядов — углы как без него

def test_recompute_keeps_tilt():
    # design.hole_recompute.recompute_hole на наклонной скважине — угол и азимут сохраняются
```

`rows(holes)` — скважины основной сетки, сгруппированные по `logical_row(row)` по возрастанию. `holes_signature` — кортежи (id, collar, toe) с округлением.

- [ ] **Step 2: Run tests — FAIL.**
- [ ] **Step 3: Implement.** Ранг ряда считается по `lattice_row` относительно `first_lattice_row` (ряд вдоль бровки — ранг 1, решётка за ним — ранг 2 и т. д.; ряды впереди первого — ранг 1). Для скважин с рангом ≤ `front_rows_tilt_count` угол — `front_rows_tilt_deg`, азимут — `face_azimuth_deg(устье)`; если азимут None — общий угол и азимут.
- [ ] **Step 4: Run** `.venv/bin/python -m pytest tests/test_design_pattern*.py tests/test_toe_line.py -q` — PASS; затем весь набор.
- [ ] **Step 5: Commit** — «Сетка: наклон 1–2 ряда у откоса отдельно от остальных».

### Task 3: Поля наклона во вкладке «Сетка»

**Files:**
- Modify: `frontend/src/pages/design/PatternPanel.tsx` (рядом с «Угол от вертикали», ~строка 156), `frontend/src/types/design.ts` (`PatternParams`)
- Test: `frontend/src/pages/design/PatternPanel.test.tsx` (create или дополнить), `frontend/src/pages/design/designParams.test.ts`

**Interfaces:**
- Produces: `PatternParams.front_rows_tilt_count?: 0 | 1 | 2`, `PatternParams.front_rows_tilt_deg?: number`; в `DEFAULT_PATTERN_PARAMS` их нет.

- [ ] **Step 1: Write the failing tests**
  - Поле «Наклонных рядов у откоса» — выбор 0 / 1 / 2, по умолчанию 0; выбор 2 пишет `front_rows_tilt_count: 2`.
  - Поле «Наклон рядов у откоса, ° от вертикали» видно при числе рядов > 0, значение по умолчанию 15, ввод 40 записывается как 30.
  - `designWithParams` у паспорта без новых ключей их не добавляет (сравнение с `DEFAULT_PATTERN_PARAMS`, как в существующих тестах `designParams.test.ts`).
- [ ] **Step 2: Run — FAIL** (`cd frontend && npx vitest run src/pages/design/PatternPanel.test.tsx src/pages/design/designParams.test.ts`).
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** `cd frontend && npx vitest run && npx tsc --noEmit -p .` — PASS.
- [ ] **Step 5: Commit** — «Сетка: поля наклона рядов у откоса».

### Task 4: Проверка на блоке №66 и документация

**Files:** документ модели ЛСП/сетки, где описана часть 1 (найти по «ЛСП» в `Docs/`), `CLAUDE.md` (кратко, если там описан генератор), спецификация — только отметка «часть 3 сделана».

- [ ] **Step 1:** Полный прогон pytest и vitest + tsc.
- [ ] **Step 2:** Скрипт воспроизведения №66 (`/private/tmp/claude-501/-Users-apple-Documents---------BlastEX--claude-worktrees-jolly-ritchie-825c41/95998a04-c978-45de-8d22-ebcef5e6be6d/scratchpad/lsp66.py` из разбора 21.10; при отсутствии — по образцу `tests/test_cad_block66*.py`): сетка 4,41 × 3,53, наклон 1 и 2 ряда, углы 15° и 30°, отступы от бровки 2 м и 1 м. Таблица ЛСП по участкам (юг, середина, север) и число скважин в допуске 3,64 м.
- [ ] **Step 3:** Документ: ключи, определение рядов 1–2, азимут к откосу, что не меняется, таблица №66.
- [ ] **Step 4: Commit** — «Сетка: наклон рядов у откоса — описание и проверка на блоке №66».
