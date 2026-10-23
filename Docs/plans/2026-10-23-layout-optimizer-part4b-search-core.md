# Ядро перебора раскладки — план реализации (часть 4б оптимизатора)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** по контуру блока и базовым параметрам сетки BlastEX перебирает
варианты раскладки и монтажа, отбраковывает недопустимые, ранжирует остальные
и возвращает три лучших. Укладывается в 2–3 минуты на блок.

**Architecture:** новый пакет `design/layout_search/`.
- `space.py` — пространство вариантов: какие параметры сетки и фланг вруба
  пробовать на каждом этапе.
- `evaluate.py` — оценка одного варианта: сетка → монтаж → ЛСП и проверки →
  темп отбойки → кортеж для сравнения.
- `search.py` — три этапа, бюджет времени, обратный вызов прогресса и
  остановки.

Генератор сетки получает один новый ключ — сдвиг начала сетки вдоль ряда.
Модуль чистый: без API и без интерфейса. Фон, кнопку и карточки добавляет 4в.

**Tech Stack:** Python 3, numpy, shapely; pytest/unittest.

**Spec:** `Docs/specs/2026-10-21-block-layout-optimizer-design.md`, раздел
«Часть 4: перебор (решено 22.10.2026)», пункт «4б».

## Global Constraints

- **Отбраковка:** коды `validate` `floor_beyond_toe`,
  `collar_too_close_to_crest`, `floor_row_gap_excess`.
- **Ранжирование** лексикографическое, меньше — лучше:
  1. `lsp_out` — скважины с ЛСП вне коридора `[0,8·W₀; 1,03·W₀]`;
  2. `fast_share`;
  3. `converging_length_m`;
  4. `outside_share`;
  5. `robust_spread` (None — хуже любого числа);
  6. `hole_count`.
- **Округление перед сравнением:** доли — до 0,01, длина стыков — до 0,5 м.
  Иначе шум генератора решает порядок.
- **Окно 8 мс** (наибольшее число скважин в любом окне 8 мс) и
  **внутрискважинное замедление** только показываются и в сравнении не
  участвуют.
- **W₀** — `burden_b_m` базовых параметров. У квадратной сетки — `spacing_a_m`
  (как `toe_line.design_burden_m`). Коридор вместе с перебором b не меняется.
- **Шаги a и b** — только в пределах ±3 % от базовых.
- **Азимут рядов** — направление бровки ±10°.
- **Монтаж** — `design.trunk_network.build_trunk_chains_network`, система СИНВ,
  магистраль 25 мс, цепочки 42 мс.
- **Бюджет по умолчанию** — 150 с. По истечении бюджета или по запросу
  остановки возвращается лучшее найденное.
- **Новый ключ** `grid_shift_along_m` пишется в `pattern_params` только когда
  он не 0. Без ключа сетка байт в байт прежняя: хэш утверждённых паспортов не
  меняется.
- **Ручные скважины** перебор не использует: сетка строится без
  `existing_holes`. Замена ручных правок — забота 4в.
- Тексты, комментарии, docstring — на русском, как в соседнем коде.

## Review Focus

1. **Ни один вариант не прошёл отбраковку** (узкий блок, всё упирается в
   подошву). Ожидается: возвращаются три лучших из отбракованных с флагом
   `rejected=True` и причинами, а не пустой ответ. Тест
   `test_all_rejected_returns_best_rejected` (задача 4).
2. **Контур без свободной поверхности** (`free_faces` пуст). Ожидается:
   азимут бровки не определён — перебор берёт базовый `row_azimuth_deg`,
   ЛСП-счётчик 0, без падения. Тест `test_no_free_face` (задача 4).
3. **Бюджет кончился посреди этапа 1.** Ожидается: результат не пустой,
   `stopped_early=True`, этапы 2–3 не запускались. Тест `test_budget_stops_early`
   (задача 4).
4. **Шахматная сетка.** Ожидается: этап 2 не предлагает «Плавный переход» —
   генератор его игнорирует, вариант был бы дублем. Тест
   `test_staggered_skips_taper` (задача 2).
5. **Порода не найдена в справочнике.** Ожидается: границы темпа по умолчанию
   (3 мс/м, без верхней), предупреждение идёт в результат. Тест
   `test_relief_bounds_passed_through` (задача 3).

---

## Файлы

- Modify: `design/geometry.py` — `crest_azimuth_deg(contour) -> float | None`.
- Modify: `design/pattern.py` — ключ `grid_shift_along_m`.
- Create: `design/layout_search/__init__.py`, `space.py`, `evaluate.py`,
  `search.py`.
- Create: `Docs/LAYOUT_SEARCH.md`; Modify: `CLAUDE.md`, спецификация.
- Tests: `tests/test_pattern_shift.py`, `tests/test_layout_search_space.py`,
  `tests/test_layout_search_evaluate.py`, `tests/test_layout_search.py`.

---

### Task 1: Азимут бровки и сдвиг сетки вдоль ряда

**Files:** `design/geometry.py`, `design/pattern.py`, `tests/test_pattern_shift.py`

**Interfaces — Produces:**
- `crest_azimuth_deg(contour: BlockContour) -> float | None`. Азимут линии
  бровки в градусах [0, 180), 0° = +Y, по часовой — как `row_azimuth_deg`.
  Считается как направление, усреднённое по длинам отрезков свободных
  поверхностей (`free_faces`): удвоенные углы, сумма векторов, половина
  угла. Без свободных поверхностей — None.
- `generate_pattern` читает `grid_shift_along_m` (м, по умолчанию 0):
  узлы рядов сдвигаются вдоль `row_dir` на `shift mod a` — к началу
  `u = u_min + ...` в обоих местах, где ряд раскладывается (основная решётка
  и ряды впереди первого). Ряд вдоль бровки (`first_row_follow_face`) не
  сдвигается. В docstring параметров — строка о ключе.

- [ ] **Step 1: Падающие тесты:**
  - `test_crest_azimuth_straight_face` — свободная грань по оси X → 90°;
    по оси Y → 0°.
  - `test_crest_azimuth_none_without_faces`.
  - `test_shift_zero_is_identical` — `grid_shift_along_m=0` и отсутствие
    ключа дают одинаковые скважины (id, устья).
  - `test_shift_moves_columns` — сдвиг 1,0 м при a = 4: каждая проекция устья
    на ось ряда смещена на 1,0 м по модулю a.
  - `test_shift_wraps_by_spacing` — сдвиг 5 м при a = 4 даёт то же, что 1 м.
- [ ] **Step 2: Запустить — падают.**
- [ ] **Step 3: Реализовать.**
- [ ] **Step 4:** `.venv/bin/python -m pytest tests/test_pattern_shift.py tests/test_design_pattern*.py tests/test_front_rows*.py -q` — PASS
  (существующий `REFERENCE_SIGNATURE` не меняется).
- [ ] **Step 5: Commit** — `Сетка: сдвиг вдоль ряда и азимут бровки`.

---

### Task 2: Пространство вариантов

**Files:** `design/layout_search/__init__.py`, `design/layout_search/space.py`,
`tests/test_layout_search_space.py`

**Interfaces:**
- Consumes: `crest_azimuth_deg` (задача 1).
- Produces:
  - `@dataclass(frozen=True) class Candidate: params: dict[str, Any];
    cut_flank: str` — полный `pattern_params` варианта и фланг вруба.
    Ключ дедупликации — `key() -> tuple`: отсортированные пары params
    (числа округлены до 0,01) плюс фланг.
  - `stage1(base: dict, contour: BlockContour) -> list[Candidate]`
  - `stage2(seeds: list[Candidate], base: dict) -> list[Candidate]`
  - `stage3(seeds: list[Candidate], base: dict) -> list[Candidate]`

Значения (из спецификации и решений):
- **Азимут.** Опорный — `crest_azimuth_deg(contour)`; если None —
  `base["row_azimuth_deg"]` (или 0). Этап 1: опорный + k·2,5°, k = −4…4
  (9 значений). Этап 3: ±1,25° вокруг семени.
- **Сдвиг вдоль** (`grid_shift_along_m`). Этап 1: k·a/4, k = 0…3. Этап 3:
  ±a/8 от семени.
- **Сдвиг поперёк** (`offset_from_face_m`). o₀ =
  `toe_line.min_crest_offset_m(base)`. Этап 1: o₀ + k·b/4, k = 0…3.
  Этап 3: ±b/8 от семени, но не меньше o₀. `first_row_burden_m` из базы
  убирается: иначе он перекрывает отступ.
- **Шаги a, b.** Этап 1 — базовые. Этап 3 — множители {0,97; 1; 1,03} для a
  и для b. У квадратной сетки a = b, один множитель.
- **Фланг.** Этап 1: `"left"`, `"right"`. Этапы 2 и 3 фланг семени не
  меняют.
- **Объём:** этап 1 — 288; этап 2 — до 20·9 = 180; этап 3 — 3·(3·3·3·9) = 729
  (у квадратной 3·81 = 243). Итого ≈ 1200 оценок — в бюджет 150 с при
  50–120 мс на вариант.
- **Первый ряд.** Этап 1 — без ключей схемы (вертикальная у кромки).
  Этап 2, для каждого семени:
  - пара: `front_rows_mode="pair"`, `front_rows_tilt_count=1`,
    `front_rows_tilt_deg` ∈ {15, 20, 25, 30};
  - переход: `front_rows_mode="taper"`, `front_rows_tilt_count` ∈ {1, 2},
    `front_rows_tilt_deg` ∈ {15, 30} — кроме `pattern == "staggered"`;
  - семя без схемы.

  Этап 3 сохраняет схему семени.
- Каждый этап удаляет дубли по `Candidate.key()`.

- [ ] **Step 1: Падающие тесты:**
  - `test_stage1_size` — прямоугольная база, контур с гранью: 9·4·4·2 = 288
    кандидатов, азимуты в [опорный−10; опорный+10].
  - `test_stage1_without_face_uses_base_azimuth`.
  - `test_stage2_variants_per_seed` — прямоугольная: семя + 4 пары + 4
    перехода = 9 на семя.
  - `test_staggered_skips_taper` — шахматная: 5 на семя, ни одного
    `"taper"`.
  - `test_stage3_steps_within_3_percent` — все a, b в [0,97; 1,03] от базовых;
    `offset_from_face_m ≥ o₀`; схема семени сохранена.
  - `test_square_single_multiplier` — у квадратной a == b во всех вариантах.
  - `test_dedup`.
- [ ] **Step 2: Запустить — падают.**
- [ ] **Step 3: Реализовать.**
- [ ] **Step 4:** `.venv/bin/python -m pytest tests/test_layout_search_space.py -q` — PASS.
- [ ] **Step 5: Commit** — `Перебор раскладки: пространство вариантов`.

---

### Task 3: Оценка варианта

**Files:** `design/layout_search/evaluate.py`, `tests/test_layout_search_evaluate.py`

**Interfaces:**
- Consumes: `Candidate` (задача 2), `build_trunk_chains_network`
  (`design/trunk_network.py`), `generate_pattern`, `validate`
  (`design/analysis.py`), `floor_report` (`design/toe_line.py`),
  `burden_relief` (`design/relief.py`), `resolve_times` (`design/timing.py`).
- Produces:
  - `@dataclass(frozen=True) class SearchContext: design: BlastDesign;
    w0_m: float | None; relief_min_ms_m: float = 3.0;
    relief_max_ms_m: float | None = None` — базовый паспорт (контур, поверхности,
    домены, `pattern_params`), W₀, границы темпа.
    `SearchContext.from_design(design, *, relief_min_ms_m=3.0,
    relief_max_ms_m=None)` считает W₀ через `toe_line.design_burden_m`.
  - `@dataclass class Evaluation: candidate: Candidate; holes: list[Hole];
    network: InitiationNetwork; rejected: bool; reject_codes: list[str];
    lsp_out: int; fast_share: float; converging_length_m: float;
    outside_share: float; robust_spread: float | None; hole_count: int;
    window8_max_holes: int; downhole_ms: float; warnings: list[str]`
    и `rank_key() -> tuple` по Global Constraints (с округлением;
    `robust_spread` None → `math.inf`; отбракованные всегда хуже любого
    прошедшего — первым элементом `rejected`).
  - `evaluate(ctx: SearchContext, candidate: Candidate) -> Evaluation`

Порядок оценки:
1. Сетка — `generate_pattern(contour, candidate.params, None, surfaces,
   domains)`. Поверхности и домены брать из `ctx.design` так же, как их
   переводит в объекты `api/services/design_service.py` перед
   `run_generate_pattern`. Пустая сетка — `rejected` с кодом `empty`.
2. Монтаж — `build_trunk_chains_network(holes, {"system": "nonel",
   "cut_flank": candidate.cut_flank})`.
3. Паспорт варианта — копия `ctx.design` с `holes`, `network`,
   `pattern_params=candidate.params` (`dataclasses.replace`).
4. Отбраковка — `validate(design)`, коды из Global Constraints.
5. `lsp_out` — по `floor_report(design)[0]`: значения `value_m` вне
   `[0,8·W₀; 1,03·W₀]` или `beyond_toe`. При W₀ None — 0.
6. Темп — `resolve_times(network, holes)`, `burden_relief(design, times,
   min_ms_m, max_ms_m)`; при None — доли 0, разброс None.
7. Окно 8 мс — наибольшее число включённых скважин, у которых время
   срабатывания укладывается в любое окно 8 мс.

- [ ] **Step 1: Падающие тесты** (прямоугольный контур 40×30 с гранью и уступом
  10 м, базовые a = b = 4):
  - `test_evaluate_basic` — не отбракован, `hole_count` равно числу
    скважин, `downhole_ms` ∈ {500, 700, 1000}, `fast_share == 0`.
  - `test_w0_fixed` — вариант с b·1,03: `lsp_out` считается по W₀ базы, а не
    по b варианта. Сравнить с ручным подсчётом по `floor_report`.
  - `test_reject_collar_too_close` — `min_crest_offset_m` 3 м в базе и
    `offset_from_face_m` 1 м у кандидата → `rejected`,
    `"collar_too_close_to_crest" in reject_codes`.
  - `test_rank_key_order` — отбракованный хуже любого прошедшего; при равных
    прочих меньше скважин — лучше; `robust_spread` None хуже 0,5.
  - `test_relief_bounds_passed_through` — `relief_min_ms_m=20` даёт
    `fast_share > 0` на той же сетке.
  - `test_window8` — на сетке 4×4 одна скважина в окне (магистраль 25 мс,
    цепочки 42 мс) → `window8_max_holes == 1`.
- [ ] **Step 2: Запустить — падают.**
- [ ] **Step 3: Реализовать.** Замерить время `evaluate` на №66 и на 480
  скважинах и записать в отчёт.
- [ ] **Step 4:** `.venv/bin/python -m pytest tests/test_layout_search_evaluate.py -q` — PASS.
- [ ] **Step 5: Commit** — `Перебор раскладки: оценка варианта`.

---

### Task 4: Поиск по этапам

**Files:** `design/layout_search/search.py`, `tests/test_layout_search.py`

**Interfaces:**
- Consumes: `stage1/2/3` (задача 2), `SearchContext`, `evaluate`,
  `Evaluation` (задача 3).
- Produces:
  - `@dataclass class SearchResult: best: list[Evaluation]; evaluated: int;
    rejected: int; stopped_early: bool; elapsed_s: float;
    all_rejected: bool; warnings: list[str]`
  - `search_layout(ctx: SearchContext, *, budget_s: float = 150.0,
    top_n: int = 3, stage2_seeds: int = 20, stage3_seeds: int = 3,
    progress: Callable[[str, int, int], None] | None = None,
    should_stop: Callable[[], bool] | None = None,
    clock: Callable[[], float] = time.monotonic) -> SearchResult`.
    `progress(stage, done, total)`; имена этапов — `"geometry"`,
    `"front_rows"`, `"refine"`.

Правила:
- Этапы по порядку. Семена следующего этапа — лучшие по `rank_key`
  среди всех оценённых (не только текущего этапа). Отбракованные в семена не
  идут, пока есть прошедшие.
- Перед каждым `evaluate` проверяются бюджет и `should_stop`. При
  срабатывании — `stopped_early=True`, возврат.
- `best` — `top_n` лучших по `rank_key` с разными сетками: варианты с
  одинаковым набором устьев (округление до 0,01 м) и одинаковым флангом
  считаются одним.
- Если прошедших нет, `best` — лучшие отбракованные, `all_rejected=True`.
- Последовательно, без процессов и потоков: параллельность — решение 4в.

- [ ] **Step 1: Падающие тесты** (контур как в задаче 3; `evaluate` в тестах
  на скорость — через фальшивые часы `clock`):
  - `test_returns_top3_sorted` — три результата, `rank_key` не убывает, сетки
    разные.
  - `test_budget_stops_early` — часы, которые после 10 оценок показывают
    > бюджета: `stopped_early`, `evaluated == 10`, `best` не пуст.
  - `test_should_stop` — остановка по флагу после этапа 1.
  - `test_progress_reports_stages` — порядок этапов geometry → front_rows →
    refine, `done ≤ total`.
  - `test_all_rejected_returns_best_rejected` — `min_crest_offset_m` больше
    любого `offset_from_face_m` → `all_rejected`, `best` из 3.
  - `test_no_free_face` — контур без `free_faces`: без падения, `lsp_out == 0`
    у всех.
- [ ] **Step 2: Запустить — падают.**
- [ ] **Step 3: Реализовать.**
- [ ] **Step 4:** `.venv/bin/python -m pytest tests/test_layout_search*.py -q` — PASS.
- [ ] **Step 5: Commit** — `Перебор раскладки: поиск по этапам`.

---

### Task 5: Проверка на №66 и документация

**Files:** `Docs/LAYOUT_SEARCH.md`, `CLAUDE.md`, спецификация,
`tests/test_layout_search.py` (тест №66)

- [ ] **Step 1: Тест №66** — контур и съёмка как в `Block66Tests`
  (`tests/test_trunk_network.py`), база: прямоугольная, a = 4,41, b = 3,53,
  `budget_s=150`. Утверждать:
  - `best` из 3, у всех `rejected` ложь;
  - `rank_key` лучшего не хуже базового варианта без перебора (база,
    оценённая `evaluate`, фланг лучший из двух).

  Пометить тест как медленный тем же механизмом, что уже есть в проекте
  (поискать `slow` в `tests/` и `pytest.ini`/`pyproject.toml`). Если механизма
  нет — `@unittest.skipUnless(os.environ.get("BLASTEX_SLOW"), ...)`.
- [ ] **Step 2: Сравнение для PR** — скрипт в scratchpad, не в репозитории.
  - Строки таблицы: база (без перебора) и три лучших.
  - Столбцы: азимут, сдвиги, a, b, схема первого ряда, фланг, `lsp_out`,
    быстрые, стыки, вне ±25 %, разброс, скважин, окно 8 мс, замедление,
    время подбора, число оценённых.
  - Плюс картинка плана лучшего варианта с картой темпа: стенд
    `.claude/stand`, как для части 2, или matplotlib.
- [ ] **Step 3:** `Docs/LAYOUT_SEARCH.md` — что перебирается, как
  отбраковывается и сравнивается, бюджет, таблица №66. `CLAUDE.md` — раздел
  «Перебор раскладки (часть 4б)» в стиле соседних. Спецификация — 4б
  «Сделано», дата.
- [ ] **Step 4:** `.venv/bin/python -m pytest -q -x` (в фоне) — без ошибок.
- [ ] **Step 5: Commit** — `Перебор раскладки: проверка на №66 и документация`.
