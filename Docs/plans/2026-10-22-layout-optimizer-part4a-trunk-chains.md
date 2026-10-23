# Монтаж «магистраль + цепочки» — план реализации (часть 4а оптимизатора раскладки)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** BlastEX строит типовой монтаж неэлектрической сети — вруб у фланга
первого ряда, магистраль 25 мс вдоль первого ряда, цепочки 42 мс назад по
столбцам — и сам выбирает внутрискважинное замедление блока из 500 / 700 /
1000 мс.

**Architecture:** Новый модуль `design/trunk_network.py` строит граф связей
только по скважинам. Ось ряда он восстанавливает по устьям, контур ему не
нужен. Схема `trunk_chains` добавляется в `SCHEME_TYPES`. Построение
вызывается из `build_template_network` (сценарии) и из `generate_tie` (API).
API вдобавок возвращает предупреждения. На фронте это новая кнопка в
«Коммутации» с выбором фланга вруба. Перебор (4б) потом зовёт построитель
напрямую.

**Tech Stack:** Python 3 (numpy), FastAPI/pydantic, React + TypeScript,
pytest/unittest, vitest, `tsc -b`.

**Spec:** `Docs/specs/2026-10-21-block-layout-optimizer-design.md`, раздел
«Часть 4: перебор (решено 22.10.2026)», пункт «4а».

## Global Constraints

- Ступени поверхностных замедлений — только из НСИ: `SURFACE_NSI_MS_OPTIONS =
  (17, 25, 42, 67, 109)`; магистраль 25 мс, цепочки 42 мс по умолчанию.
- Внутрискважинное замедление одно на блок, из `(500, 700, 1000)` мс:
  наименьшее, которое строго больше наибольшего поверхностного времени сети.
  Если такого нет — 1000 и предупреждение «Фронт инициирования отстаёт:
  поверхностная сеть длиннее 1000 мс — возможен подбой.»
- Пара у откоса (`face_toe`, партнёр — `design.models.face_pair_partner_id`)
  срабатывает одновременно со своей вертикальной: та же входящая связь с тем же
  замедлением, без связей 0 мс.
- Мостов нет. Каждая скважина получает ровно одну входящую связь, кроме вруба
  (и его пары): у них связей нет, они стартовые.
- Старые схемы (`row`, `echelon`, `diagonal_v`, `trapezoid`) не меняются:
  существующие тесты тайминга проходят без правок.
- Ключи `trunk_ms`, `chain_ms`, `cut_flank` пишутся в `timing_params` сети
  только у схемы `trunk_chains`. У старых схем хэш утверждённых паспортов не
  меняется.
- Пользователю в тексте — «Магистраль + цепочки», «Вруб у фланга: левого /
  правого». Без служебных имён.
- Тексты, комментарии, docstring — на русском, как в соседнем коде.

## Review Focus

1. **Ступенчатая бровка.** Головы столбцов лежат в разных рядах решётки.
   Ожидается: магистраль идёт по головам столбцов, а не по ряду 1. Тест
   `test_stepped_front_trunk_follows_column_heads` (задача 1).
2. **Шахматная сетка.** Столбцы через ряд смещены на a/2. Ожидается: у
   каждой скважины ровно одна входящая связь 42 мс к скважине предыдущего
   ряда, и ни одна не остаётся без времени. Тест
   `test_staggered_every_hole_timed_once` (задача 1).
3. **Одна строка или одна скважина.** Ось ряда не восстановить. Ожидается:
   ось по направлению с наибольшим разбросом устьев, для одной скважины —
   только стартовая, без падения. Тест `test_degenerate_layouts` (задача 1).
4. **Включённые стенки** (`include_contour=True`) и скважины вне столбцов
   (стабилизация, сателлиты, ручные). Ожидается: каждая получает связь 42 мс
   к ближайшей уже привязанной скважине. Тест `test_strays_tie_to_nearest`
   (задача 1).
5. **Система не СИНВ.** У электронной системы и ДШ внутрискважинное
   замедление не подбирается: берётся `DEFAULT_DOWNHOLE_MS[system]`, вид
   связей — по системе. Тест `test_non_nonel_system_keeps_default_downhole`
   (задача 2).

---

## Файлы

- Create: `design/trunk_network.py` — оси, столбцы, граф, выбор
  внутрискважинного замедления.
- Modify: `design/timing.py` — схема `trunk_chains` в `SCHEME_TYPES`,
  ветка в `build_template_network`.
- Modify: `api/schemas/design.py` — поле `warnings` в `TieGenerateResponse`.
- Modify: `api/services/design_service.py::generate_tie`.
- Modify: `frontend/src/types/design.ts`, `frontend/src/pages/design/TiePanel.tsx`,
  `frontend/src/pages/design/DesignPage.tsx`, `frontend/src/api/endpoints.ts`
  (тип ответа).
- Create: `Docs/TRUNK_CHAINS.md`; Modify: `CLAUDE.md`, спецификация (отметка
  «сделано»).
- Tests: `tests/test_trunk_network.py`, `tests/test_api_timing.py`,
  `frontend/src/pages/design/TiePanel.test.tsx` (создать, если нет).

---

### Task 1: Построитель графа «магистраль + цепочки»

**Files:**
- Create: `design/trunk_network.py`
- Test: `tests/test_trunk_network.py`

**Interfaces:**
- Produces:
  - `TRUNK_SCHEME = "trunk_chains"`
  - `DOWNHOLE_CHOICES_MS = (500.0, 700.0, 1000.0)`
  - `@dataclass(frozen=True) class TrunkPlan: starters: list[str];
    ties: list[tuple[str, str, float]]` (откуда, куда, мс)`;
    surface_ms: dict[str, float]; warnings: list[str]`
  - `row_axis(holes: list[Hole]) -> tuple[tuple[float, float], tuple[float, float]]`
    — (ось ряда, направление «от откоса вглубь»), единичные векторы.
  - `plan_trunk_chains(holes: list[Hole], *, trunk_ms: float = 25.0,
    chain_ms: float = 42.0, cut_flank: str = "left") -> TrunkPlan`
    — `holes` уже отфильтрованы (включённые; стенки — по `include_contour`).
    `cut_flank` — `"left"` или `"right"`; иначе `"left"`.

Алгоритм (решения, которых нет в сигнатуре):

1. **Члены столбцов** — `row_family(kind) == "grid"` и вид не в
   `{"stab", "satellite", FACE_TOE_KIND}`. Остальные — «прочие».
2. **Ось ряда** (`row_axis`). Группируем члены по `logical_row(hole.row)`.
   Для каждой группы из ≥ 2 скважин берём главную ось устьев (SVD
   центрированных координат), знак — к общей первой оси. Итог — среднее,
   взвешенное числом скважин группы. Если групп ≥ 2 нет — главная ось всех
   устьев. «Вглубь» — перпендикуляр, знак которого даёт положительную
   корреляцию проекции с `logical_row`; при одной строке — любой из двух.
3. **Шаг ряда a** — медиана расстояний между соседними по оси скважинами
   одного логического ряда.
4. **Предшественник в цепочке.** Для члена — скважина предыдущего
   логического ряда с наименьшим смещением по оси, если смещение ≤ 0,75·a.
   На прямоугольной сетке это сосед по столбцу, на шахматной — ближайший
   по диагонали. Связь — `chain_ms`. **Голова** — член без предшественника.
   На ступенчатой бровке головы лежат в разных рядах решётки.
5. **Вруб и магистраль.** Головы сортируются по проекции на ось ряда.
   Ось направлена так, что вглубь = ось, повёрнутая на +90°. Тогда
   наименьшая проекция — «левый» фланг, если смотреть с откоса вглубь
   блока. Вруб — крайняя голова выбранного фланга. Магистраль — связи
   между соседними по порядку головами от вруба, `trunk_ms` каждая.
6. **Пара.** `face_toe` получает копию входящей связи своей вертикальной.
   Если вертикальная — вруб, пара тоже в `starters`.
7. **Прочие.** По возрастанию расстояния до ближайшей уже привязанной —
   связь `chain_ms` от ближайшей привязанной скважины.
8. `surface_ms` — время каждой скважины от вруба (0) по связям.
9. Шаги снапаются к `SURFACE_NSI_MS_OPTIONS` (`timing._snap`).

- [ ] **Step 1: Написать падающие тесты** в `tests/test_trunk_network.py`
  (стиль — `unittest`, сетки — `generate_pattern`, как в
  `tests/test_design_timing.py`):

```python
def test_rectangular_grid_trunk_and_chains(self):
    # прямоугольник 20×16, a = b = 4, бровка снизу (ряд 1 у y≈0)
    plan = plan_trunk_chains(holes, cut_flank="left")
    self.assertEqual(len(plan.starters), 1)
    starter = by_id[plan.starters[0]]
    self.assertEqual(logical_row(starter.row), min_row)       # вруб в первом ряду
    self.assertEqual(starter.collar.x, min(h.collar.x for h in first_row))  # левый фланг
    # каждая не-стартовая — ровно одна входящая связь
    incoming = Counter(to for _, to, _ in plan.ties)
    self.assertTrue(all(incoming[h.id] == 1 for h in holes if h.id not in plan.starters))
    # время = 25·(номер столбца от вруба) + 42·(номер ряда от первого)
    for h in holes:
        self.assertAlmostEqual(plan.surface_ms[h.id], 25 * col_rank[h.id] + 42 * row_rank[h.id])

def test_right_flank_mirrors(self):
    plan = plan_trunk_chains(holes, cut_flank="right")
    self.assertEqual(by_id[plan.starters[0]].collar.x, max(h.collar.x for h in first_row))

def test_stepped_front_trunk_follows_column_heads(self):
    # сетка, у которой в левой половине убран ряд 1 (ступень бровки)
    plan = plan_trunk_chains(stepped, cut_flank="left")
    trunk_targets = {to for frm, to, ms in plan.ties if ms == 25.0}
    self.assertEqual(trunk_targets | set(plan.starters), column_heads)  # головы, а не ряд 1

def test_face_pair_fires_with_vertical(self):
    # generate_pattern с front_rows_mode="pair" на контуре с откосом
    plan = plan_trunk_chains(holes)
    for toe in (h for h in holes if h.kind == "face_toe"):
        self.assertEqual(plan.surface_ms[toe.id], plan.surface_ms[face_pair_partner_id(toe)])
    self.assertFalse(any(ms == 0.0 for _, _, ms in plan.ties))

def test_staggered_every_hole_timed_once(self):
    plan = plan_trunk_chains(staggered)
    self.assertEqual(set(plan.surface_ms), {h.id for h in staggered})
    self.assertTrue(all(ms in (25.0, 42.0) for _, _, ms in plan.ties))

def test_strays_tie_to_nearest(self):
    # сетка + одна скважина kind="stab" вне столбцов + стенки include_contour
    plan = plan_trunk_chains(holes_with_strays)
    for stray in strays:
        frm = next(f for f, t, _ in plan.ties if t == stray.id)
        self.assertEqual(frm, nearest_timed_neighbour_id(stray))   # считается в тесте
        self.assertIn(stray.id, plan.surface_ms)

def test_degenerate_layouts(self):
    self.assertEqual(plan_trunk_chains([single]).starters, [single.id])
    one_row = plan_trunk_chains(row_of_five)
    self.assertEqual(len(one_row.ties), 4)

def test_only_nsi_delays(self):
    plan = plan_trunk_chains(holes, trunk_ms=24.0, chain_ms=40.0)
    self.assertEqual({ms for *_, ms in plan.ties}, {25.0, 42.0})
```

- [ ] **Step 2: Запустить — падают** (`ModuleNotFoundError: design.trunk_network`).
  Run: `.venv/bin/python -m pytest tests/test_trunk_network.py -q`
- [ ] **Step 3: Реализовать `design/trunk_network.py`** по алгоритму выше.
- [ ] **Step 4: Тесты проходят.**
  Run: `.venv/bin/python -m pytest tests/test_trunk_network.py -q` — все PASS.
- [ ] **Step 5: Commit** — `Монтаж «магистраль + цепочки»: построитель графа`.

---

### Task 2: Внутрискважинное замедление и схема в сети

**Files:**
- Modify: `design/trunk_network.py`, `design/timing.py`
- Test: `tests/test_trunk_network.py`

**Interfaces:**
- Consumes: `plan_trunk_chains`, `TrunkPlan`, `DOWNHOLE_CHOICES_MS` (задача 1).
- Produces:
  - `pick_downhole_ms(max_surface_ms: float) -> tuple[float, list[str]]`
  - `build_trunk_chains_network(holes: list[Hole], params: dict[str, Any])
    -> tuple[InitiationNetwork, list[str]]` — фильтрует скважины, как
    `timing._eligible_holes`. Читает `system`, `include_contour`, `trunk_ms`,
    `chain_ms`, `cut_flank`. У `nonel` замедление из `pick_downhole_ms`, у
    других систем — `DEFAULT_DOWNHOLE_MS[system]` без предупреждения.
    Сеть собирает через `timing._populate_v2_from_graph`.
    `timing_params = {"scheme": "trunk_chains", "trunk_ms", "chain_ms",
    "cut_flank", "downhole_delay_ms"}`.
  - `timing.SCHEME_TYPES` дополнен `"trunk_chains"`;
    `build_template_network(holes, "trunk_chains", params)` возвращает
    `build_trunk_chains_network(...)[0]`.

- [ ] **Step 1: Падающие тесты:**

```python
def test_pick_downhole_smallest_safe(self):
    self.assertEqual(pick_downhole_ms(320.0), (500.0, []))
    self.assertEqual(pick_downhole_ms(500.0), (700.0, []))     # строго больше
    self.assertEqual(pick_downhole_ms(999.0)[0], 1000.0)
    ms, warnings = pick_downhole_ms(1000.0)
    self.assertEqual(ms, 1000.0)
    self.assertIn("Фронт инициирования отстаёт", warnings[0])

def test_network_resolves_to_plan_times(self):
    network, warnings = build_trunk_chains_network(holes, {"system": "nonel"})
    times, resolve_warnings = resolve_times(network, holes)
    plan = plan_trunk_chains(holes)
    for h in holes:
        self.assertAlmostEqual(times[h.id], plan.surface_ms[h.id] + 500.0)
    self.assertEqual(network.timing_params["scheme"], "trunk_chains")

def test_template_entry_point(self):
    network = build_template_network(holes, "trunk_chains", {"system": "nonel", "cut_flank": "right"})
    self.assertEqual(network.timing_params["cut_flank"], "right")

def test_non_nonel_system_keeps_default_downhole(self):
    network, warnings = build_trunk_chains_network(holes, {"system": "electronic"})
    self.assertEqual(network.downhole_connectors, [])
    self.assertEqual(warnings, [])
```

  Плюс тест длинного блока: сетка 40 столбцов × 12 рядов, (39·25 + 11·42 =
  1437 мс) → 1000 и предупреждение.
- [ ] **Step 2: Запустить — падают.**
- [ ] **Step 3: Реализовать.** `resolve_times` прибавляет внутрискважинное
  замедление к поверхностному времени — проверь это на
  `test_network_resolves_to_plan_times`, а не предполагай.
- [ ] **Step 4: Прогон:** `.venv/bin/python -m pytest tests/test_trunk_network.py
  tests/test_design_timing.py tests/test_timing_block_order.py
  tests/test_timing_connection_delays.py tests/test_timing_diagnostics.py -q`
  — всё PASS.
- [ ] **Step 5: Commit** — `Магистраль + цепочки: подбор внутрискважинного замедления`.

---

### Task 3: API — предупреждения построения

**Files:**
- Modify: `api/schemas/design.py` (`TieGenerateResponse.warnings: list[str] =
  Field(default_factory=list)`), `api/services/design_service.py::generate_tie`
- Test: `tests/test_api_timing.py`

**Interfaces:**
- Consumes: `build_trunk_chains_network` (задача 2), `TRUNK_SCHEME`.
- Produces: `POST /design/tie/generate` со `scheme="trunk_chains"` отвечает
  `{network, starters_count, connectors_count, warnings}`. Остальные схемы
  отвечают `warnings=[]`.

- [ ] **Step 1: Падающий тест** (по образцу существующих в
  `tests/test_api_timing.py`): длинный блок со `scheme="trunk_chains"` —
  статус 200, `warnings[0]` содержит «Фронт инициирования отстаёт»,
  `network.timing_params.downhole_delay_ms == 1000`. Схема `row` —
  `warnings == []`.
- [ ] **Step 2: Запустить — падает** (`KeyError: 'warnings'`).
- [ ] **Step 3: Реализовать:** в `generate_tie` для `TRUNK_SCHEME` вызвать
  `build_trunk_chains_network`, иначе — как было.
- [ ] **Step 4:** `.venv/bin/python -m pytest tests/test_api_timing.py -q` — PASS.
- [ ] **Step 5: Commit** — `API коммутации: предупреждения построения`.

---

### Task 4: Интерфейс «Коммутации»

**Files:**
- Modify: `frontend/src/types/design.ts` (`SchemeType` + `"trunk_chains"`;
  `TieParams` + `trunk_ms: number`, `chain_ms: number`,
  `cut_flank: "left" | "right"`; `DEFAULT_TIE_PARAMS`: 25, 42, `"left"`),
  `frontend/src/api/endpoints.ts` (тип ответа + `warnings: string[]`),
  `TiePanel.tsx`, `DesignPage.tsx`
- Test: `frontend/src/pages/design/TiePanel.test.tsx`

**Interfaces:**
- Consumes: ответ API из задачи 3.
- Produces: `TiePanel` получает проп `warnings: string[]`.

Поведение:
- Кнопка шаблона «Магистраль + цепочки», подсказка «вруб у фланга, 25 / 42 мс».
- При этой схеме вместо «Интервал замедления» — два списка из ступеней НСИ:
  «Магистраль, мс» (по умолчанию 25) и «Цепочки, мс» (по умолчанию 42). Плюс
  переключатель «Вруб у фланга: левого / правого» с подсказкой «если смотреть
  с откоса на блок».
- У системы СИНВ поле «Внутрискважинное замедление» неактивно. Подсказка:
  «подбирается: наименьшее из 500 / 700 / 1000 мс, при котором сеть успевает
  до первого взрыва».
- Предупреждения последнего построения показываются под кнопкой «Построить»
  и очищаются при следующем построении.

- [ ] **Step 1: Падающие тесты vitest:** выбор «Магистраль + цепочки» вызывает
  `onSchemeChange("trunk_chains")`. При этой схеме видны «Магистраль, мс»,
  «Цепочки, мс», «Вруб у фланга», а поле внутрискважинного замедления
  `disabled`. Переданные `warnings` выводятся текстом.
- [ ] **Step 2: Запустить — падают.**
  Run: `cd frontend && npx vitest run src/pages/design/TiePanel.test.tsx`
- [ ] **Step 3: Реализовать.**
- [ ] **Step 4:** `cd frontend && npx vitest run && npx tsc -b` — без ошибок.
- [ ] **Step 5: Commit** — `Коммутация: шаблон «Магистраль + цепочки»`.

---

### Task 5: Проверка на №66 и документация

**Files:**
- Create: `Docs/TRUNK_CHAINS.md`
- Modify: `CLAUDE.md` (раздел «Монтаж „магистраль + цепочки“ (часть 4а)»:
  модуль, вход в `build_template_network`, правило внутрискважинного
  замедления, пара одновременно, ссылка на док), спецификация (пункт 4а —
  «Сделано», дата)
- Test: `tests/test_trunk_network.py` (тест на фикстуре №66)

- [ ] **Step 1: Тест на №66.** Контур берём, как в `tests/test_cad_block66*.py`.
  Сетка — `generate_pattern` с a = 3,5, b = 3,5 (параметры, как в
  существующих тестах №66). Строим `trunk_chains` для обоих флангов.
  Проверяем:
  - каждая включённая скважина имеет время;
  - все поверхностные связи — 25 или 42 мс;
  - вруб лежит в голове крайнего столбца.

  `fast_share` в тесте не утверждаем. Если он не нулевой, это показывает
  сравнение (шаг 2), а не правится подгонкой.
- [ ] **Step 2: Сравнение для PR** — скрипт в scratchpad, не в репозитории.
  На той же сетке №66 сравниваем схемы `row`, `echelon` и `trunk_chains`
  (левый и правый фланг):
  - `fast_share`, `converging_length_m`, `outside_share`, `robust_spread`;
  - наибольшее число скважин в окне 8 мс;
  - выбранное внутрискважинное замедление.

  Таблицу — в описание PR. Монтаж ShotPlus из паспорта
  (`24.09.2026 Блок 66 проект-проект блок66.pdf`) машинно не читается.
  Контролёр сверяет схему с картинкой паспорта глазами: вруб у фланга,
  магистраль по первому ряду, цепочки назад.
- [ ] **Step 3:** `Docs/TRUNK_CHAINS.md` — правила из Global Constraints и
  алгоритма задачи 1 простым языком и таблица сравнения.
- [ ] **Step 4:** полный прогон `.venv/bin/python -m pytest -q -x` и
  `cd frontend && npx vitest run && npx tsc -b` — без ошибок.
- [ ] **Step 5: Commit** — `Магистраль + цепочки: проверка на №66 и документация`.
