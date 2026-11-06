# Шаблон «от тыла» в генераторе сетки — план (PR 2 из 3)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `generate_pattern` по ключу `layout_anchor = "back"` строит одну прямоугольную сетку от тыла: приконтурный ряд лесенкой в 0,5–0,8·b от наиболее длинной несвободной стороны, эшелоны к бровке, конец эшелона по ЛСП (ничего → наклон → скважина на остатке); вкладка «Сетка» умеет включить шаблон.

**Architecture:** Новый модуль `design/back_layout.py` — тыл, азимут тыла, решётка от тыла, конец эшелона. `design/pattern.py::generate_pattern` в режиме «от тыла» вместо рядов от бровки зовёт `back_layout.back_grid`, дальше — те же стенки, стабилизация, сателлиты, нумерация. Наклон к откосу — общий помощник, вынесенный из `_face_pairs`. Азимут рядов остаётся параметром `row_azimuth_deg`: фронт при выборе «от тыла» ставит его по тылу через `POST /design/back-azimuth` (все потребители — нумерация, разрыв у подошвы, сечение — читают тот же параметр). Перебор — PR 3.

**Tech Stack:** Python 3.12, shapely 2, FastAPI, pytest; React + TypeScript, vitest.

**Spec:** `Docs/specs/2026-11-06-back-anchored-pattern-design.md`, разделы «Шаблон «от тыла»», «Ограничения», «Проверка».

## Global Constraints

- Ключи `pattern_params` пишутся только когда заданы: `layout_anchor` — только `"back"`, `back_offset_m` — только когда введён. Без ключей вывод `generate_pattern` побитно прежний (`REFERENCE_SIGNATURE`).
- Шаблон «от тыла» — только `pattern` `square` и `rectangular`; у `staggered`, `variable`, `domain_dependent` ключ игнорируется (раскладка от бровки).
- Сетка одна: ряды параллельны `row_azimuth_deg`, эшелоны (столбцы) перпендикулярны, столбцы на одной прямой; веера нет.
- Тыл — наиболее длинная сторона среди несвободных; сторона — серия подряд несвободных рёбер, излом больше 45° делит стороны.
- Отступ приконтурного ряда от тыла — `back_offset_m`, нет ключа — 0,65·b; допустимый диапазон 0,5–0,8·b.
- Конец эшелона: ЛСП последней ≤ W + 3 % — ничего; иначе наклон к откосу (азимут ≤ 15° от столбца, угол до 30°, ЛСП ≥ max(0,8·W, 1 м)); не хватило — вертикальная на остатке: ЛСП ≈ W, устье не ближе `min_crest_offset_m` (умолчание 0,5 м) к бровке и не ближе 1 м к предыдущей скважине эшелона. Последняя регулярная с ЛСП < 0,8·W или устьем ближе отступа к бровке убирается.
- Скважина на остатке — член основной сетки своего столбца (вид основной сетки, `row`/`col` столбца).
- `front_rows_mode`/`front_rows_tilt_count` в режиме «от тыла» не применяются: конец эшелона их заменяет; `front_rows_tilt_deg` — предпочтительный угол наклона, как у пары.
- Без W (`allowed_floor_burden_m` None) — только регулярные узлы, без наклона и остатка.
- Чертёж блока 67 — в тесты со сдвигом координат (решение владельца 06.11.2026).

## Review Focus

- Тыл — дуга из мелких рёбер: одна сторона, приконтурный ряд лесенкой, а не обрыв на каждом ребре — тест в Task 1 и Task 2.
- Контур без несвободных сторон (весь по бровке) или без свободных: шаблон не ломается — без тыла раскладка от бровки, без бровки — без конца эшелона — тесты в Task 1 и Task 5.
- Эшелон, в который не влезает ни одного регулярного узла (узкий выступ у фланга): без скважин и без ошибок — тест в Task 4.
- Скважина на остатке ближе 1 м к предыдущей: не ставится, вместо неё наклон с наибольшим углом и предупреждение ЛСП — тест в Task 4.
- Переключение «от тыла» без контура (меньше 3 вершин): кнопка азимута недоступна, генерация не падает — тест в Task 6.

---

### Task 1: Тыл и его азимут

**Files:**
- Create: `design/back_layout.py`
- Test: `tests/test_back_layout.py`

**Interfaces:**
- Produces: `BACK_SPLIT_TURN_DEG = 45.0`; `back_side(contour: BlockContour) -> list[tuple[float, float]] | None` — вершины тыла по обходу контура, None без несвободных рёбер; `back_azimuth_deg(contour) -> float | None` — азимут хорды тыла в [0, 180), как `geometry.crest_azimuth_deg` (0° = +Y, по часовой).

- [ ] **Step 1: Failing tests**

```python
def test_back_of_rectangle_is_the_long_side_opposite_the_face():
    c = rect(40, 22, free=[[0, 1]])          # бровка — нижнее ребро
    assert back_side(c) == [(40.0, 22.0), (0.0, 22.0)]
    assert back_azimuth_deg(c) == pytest.approx(90.0)

def test_arc_back_is_one_side():
    c = arc_back_block()                       # тыл — дуга из 12 рёбер, излом < 45°
    assert len(back_side(c)) == 13

def test_sharp_corner_splits_sides_longest_wins():
    c = l_shaped_back()                         # несвободная цепь с изломом 90°: 30 м и 12 м
    side = back_side(c)
    assert math.dist(side[0], side[-1]) == pytest.approx(30.0)

def test_no_back_when_whole_contour_is_free():
    assert back_side(rect(40, 22, free=[[0, 1], [1, 2], [2, 3], [3, 0]])) is None
```

Помощники `rect`, `arc_back_block`, `l_shaped_back` — в тестовом файле (откос 75°, уступ 10 м).

- [ ] **Step 2:** `pytest tests/test_back_layout.py -v` — FAIL (модуля нет).
- [ ] **Step 3:** реализовать по Interfaces; несвободные рёбра — дополнение `contour.free_faces`; серии — по обходу кольца, разрыв — излом > 45° между соседними рёбрами; сторона длиннее — по сумме длин рёбер.
- [ ] **Step 4:** тесты PASS.
- [ ] **Step 5:** `git commit -m "Тыл блока и его азимут для шаблона «от тыла»"`

### Task 2: Решётка от тыла

**Files:**
- Modify: `design/back_layout.py`
- Test: `tests/test_back_layout.py`

**Interfaces:**
- Consumes: `back_side` (Task 1).
- Produces: `BACK_OFFSET_DEFAULT_RATIO = 0.65`, `BACK_OFFSET_RANGE = (0.5, 0.8)`; `back_offset_m(params: dict, burden_b: float) -> float`; `back_columns(contour, boundary, row_azimuth_deg, spacing_a, burden_b, back_offset, shift_along) -> list[list[tuple[float, float]]]` — узлы каждого эшелона от тыла к бровке (регулярные, шаг b), только внутри `boundary`.
- Узлы — одна решётка: `local_basis(row_azimuth_deg)`; начало по v — линия тыла (хорда), сдвинутая внутрь на `back_offset`; по u — фаза `shift_along` mod a. Первый узел эшелона — узел решётки, ближайший к линии отступа от тыла вдоль этого эшелона (тыл, смещённый внутрь на `back_offset` через `offset_curve`), с расстоянием до тыла в [0,5·b; 0,8·b], иначе ближайший к диапазону изнутри блока.

- [ ] **Step 1: Failing tests** — `test_straight_back_first_row_at_offset` (прямоугольник: все первые узлы в 0,65·b от тыла, ровно на прямой); `test_arc_back_first_row_is_a_staircase` (дуга: расстояние первого узла до тыла в [0,5·b; 0,8·b] у всех эшелонов, первые узлы не на одной прямой); `test_columns_are_parallel_and_step_b` (в каждом эшелоне соседние узлы на расстоянии b вдоль `advance`, смещение вдоль ряда 0); `test_back_offset_key` (`back_offset_m({}, 4) == 2.6`, `back_offset_m({"back_offset_m": 3}, 4) == 3`).
- [ ] **Step 2–4:** RED → реализовать → GREEN.
- [ ] **Step 5:** `git commit -m "Решётка от тыла: приконтурный ряд лесенкой, эшелоны с шагом b"`

### Task 3: Наклон к откосу — общий помощник

**Files:**
- Modify: `design/pattern.py` (`_face_pairs`)
- Test: `tests/test_design_pattern_face_pair.py` (существующие — без изменений)

**Interfaces:**
- Produces: `face_tilts(contour, holes: list[Hole], collars_xy: list[tuple[float, float]], base_direction, tilt_deg, target_m, allowed_m, subdrill_m, surfaces, depth_override) -> list[tuple[float, float]]` — (угол, азимут) на каждое устье; `holes[k]` — скважина, из которой строится наклонная в `collars_xy[k]` (`replace` устья и забоя): направление к ближайшей точке подошвы с пределом 15°, предпочтительный угол, подъём до 30° (`_raised_angles`), проверка `_verified_angles`. `_face_pairs` зовёт его вместо своего кода.

- [ ] **Step 1:** `pytest tests/test_design_pattern_face_pair.py tests/test_design_pattern_front_tilt.py -q` — зафиксировать PASS до правки.
- [ ] **Step 2:** вынести код из `_face_pairs` в `face_tilts` без изменения поведения.
- [ ] **Step 3:** те же тесты PASS, `REFERENCE_SIGNATURE` не изменился.
- [ ] **Step 4:** `git commit -m "Наклон к откосу — общий помощник face_tilts"`

### Task 4: Конец эшелона у бровки

**Files:**
- Modify: `design/back_layout.py`
- Test: `tests/test_back_layout.py`

**Interfaces:**
- Consumes: `back_columns` (Task 2), `face_tilts` (Task 3), `toe_positions`, `allowed_floor_burden_m`, `tilt_floor_burden_target_m`, `design_burden_m`, `min_crest_offset_m`.
- Produces: `back_grid(contour, params, boundary, surfaces, ...) -> list[Hole]` — регулярные узлы как вертикальные скважины (вид `default_kind`, `row` — номер узла от тыла, `col` — номер эшелона) плюс конец каждого эшелона по правилам Global Constraints.
- ЛСП вертикальной — `toe_positions(contour, [xy], [H])`. Остаток: точка на линии эшелона между последней и бровкой, где ЛСП = W (деление пополам), не ближе `min_crest_offset_m` к бровке и 1 м к последней.

- [ ] **Step 1: Failing tests** (прямоугольник 40×30, уступ 10, откос 75°, a = 4, W = b = 3,5; отступ от тыла подобран так, чтобы последний узел встал на нужном месте):
  - `test_last_hole_fits_nothing_added` — ЛСП последней ≤ 3,605: в эшелоне только регулярные, все вертикальные;
  - `test_last_hole_tilted_toward_face` — ЛСП последней 4,5: она наклонена (угол > 0, ≤ 30°, азимут к бровке), ЛСП ≤ 3,605, лишней скважины нет;
  - `test_remainder_hole_added_when_tilt_is_not_enough` — ЛСП последней 7,5: последняя вертикальная, добавлена вертикальная на остатке, её ЛСП ≈ 3,5, шаг от последней < b и ≥ 1 м, устье ≥ 0,5 м от бровки;
  - `test_last_regular_too_close_is_dropped` — узел в 0,3 м от бровки убран, конец эшелона считается от предыдущего;
  - `test_echelon_without_nodes_is_empty` — узкий выступ: эшелон пустой, без ошибок;
  - `test_remainder_closer_than_one_metre_falls_back_to_max_tilt` — места для остатка нет: последняя с наибольшим углом.
- [ ] **Step 2–4:** RED → реализовать → GREEN.
- [ ] **Step 5:** `git commit -m "Конец эшелона у бровки: ничего, наклон или скважина на остатке"`

### Task 5: Режим «от тыла» в generate_pattern

**Files:**
- Modify: `design/pattern.py` (`generate_pattern`: константа `LAYOUT_ANCHOR_BACK = "back"`, ветка перед раскладкой рядов)
- Test: `tests/test_back_layout.py`, `tests/test_design_pattern.py` (сигнатура без ключа)

**Interfaces:**
- Consumes: `back_grid` (Task 4).
- Produces: при `layout_anchor == "back"` и `pattern` ∈ {square, rectangular} и найденном тыле основная сетка — `back_grid`; ряд вдоль бровки, ряды впереди, пары и переход не строятся; стенки, буфер, стабилизация, сателлиты, вставки, нумерация — как сейчас. Иначе — прежняя раскладка.

- [ ] **Step 1: Failing tests** — `test_back_mode_generates_back_grid` (генератор отдаёт то же, что `back_grid`, плюс нумерация); `test_back_mode_ignored_for_staggered`; `test_back_mode_without_back_falls_back`; `test_back_mode_passes_validate_rejects` (на прямоугольнике нет `floor_beyond_toe`, `floor_row_gap_excess`, `collar_too_close_to_crest`); существующий `REFERENCE_SIGNATURE` — без изменений.
- [ ] **Step 2–4:** RED → реализовать → GREEN; `pytest tests/ -q -k "pattern or front or toe_line or layout_search or back_layout"`.
- [ ] **Step 5:** `git commit -m "Генератор: шаблон «от тыла» по ключу layout_anchor"`

### Task 6: API азимута тыла и вкладка «Сетка»

**Files:**
- Modify: `api/routers/design.py`, `api/schemas/design.py`, `api/services/design_service.py` (`POST /design/back-azimuth`: `{contour}` → `{azimuth_deg: float | null}`)
- Modify: `frontend/src/api/endpoints.ts` (`design.backAzimuth`), `frontend/src/types/design.ts` (`layout_anchor?: "back"`, `back_offset_m?: number`), `frontend/src/pages/design/PatternPanel.tsx`
- Test: `tests/test_api_back_azimuth.py`, `frontend/src/pages/design/PatternPanel.test.tsx`

**Interfaces:**
- На вкладке «Сетка» (только square/rectangular): выбор «Опора сетки: от бровки / от тыла» (`layout_anchor`: «от бровки» — ключ убирается); при выборе «от тыла» — запрос азимута, `row_azimuth_deg` ставится по ответу; поле «Отступ от тыла, м» (placeholder `0,65·b` числом, пусто — ключ убирается); при «от тыла» блок «Первый ряд у откоса» показывает только «Предпочтительный наклон».

- [ ] **Step 1: Failing tests** — API: прямоугольник → 90°, контур целиком по бровке → null, меньше 3 вершин → 422. Фронт: выбор «от тыла» пишет `layout_anchor: "back"` и `row_azimuth_deg` из ответа заглушки; «от бровки» пишет `layout_anchor: undefined`; у шахматки выбора нет; без контура выбор «от тыла» недоступен.
- [ ] **Step 2–4:** RED → реализовать → GREEN; `npx tsc -b`.
- [ ] **Step 5:** `git commit -m "Вкладка «Сетка»: опора сетки «от тыла», азимут по тылу, отступ от тыла"`

### Task 7: Блок 67 в тестах и документация

**Files:**
- Create: `tests/fixtures/cad/block67_lines.json` — контур, верхняя и нижняя бровки блока 67 со сдвигом координат (начало — минимум x, y контура; отметки — как есть), `tests/test_block67_back_layout.py`
- Modify: `Docs/FRONT_ROWS_TILT.md` (раздел «Шаблон «от тыла»»), `CLAUDE.md` (раздел «Первый ряд у откоса»: ключи `layout_anchor`, `back_offset_m`, модуль `design/back_layout.py`), справка вкладки, если описывает схемы первого ряда.

- [ ] **Step 1: Failing test** `test_block67_back_layout_beats_crest_layout`: контур из фикстуры, нижний контур — `two_contours` (замыкание фланга, PR #149), W = b = 3,8, a = 3,811, H = 8,83, откос 75°. Шаблон «от тыла» против нынешнего («от бровки», `front_rows_mode: pair`, тот же азимут): медиана расстояния устья первого ряда до бровки меньше; наклонных не больше; нет `floor_beyond_toe`/`floor_row_gap_excess`/`collar_too_close_to_crest`; доля ЛСП в коридоре не меньше.
- [ ] **Step 2–4:** RED (модуль/фикстуры нет) → фикстура и тест → GREEN.
- [ ] **Step 5:** документация; `pytest tests/ -q` и `cd frontend && npx tsc -b && npx vitest run` — PASS.
- [ ] **Step 6:** `git commit -m "Блок 67 в тестах шаблона «от тыла», документация"`
