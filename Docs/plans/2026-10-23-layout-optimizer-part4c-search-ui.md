# Подбор раскладки в фоне и карточки — план реализации (часть 4в оптимизатора)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** на вкладке «Сетка» кнопка «Подобрать раскладку» запускает перебор
(часть 4б) на сервере в фоне. Видно этап и ход выполнения, подбор можно
остановить. Результат — три карточки. Клик по карточке показывает вариант на
плане поверх текущего, «Применить» заменяет сетку и монтаж одним шагом
отмены. Последний подбор блока хранится и помечается «устарел», если
исходные данные изменились.

**Architecture:**
- **Сервер.** `design/layout_search/jobs.py` держит реестр задач в памяти
  процесса API. Прод запускает один процесс uvicorn без `--workers`
  (`scripts/start_api.py`), поэтому реестр в памяти работает. Сам перебор идёт
  в отдельном процессе (`multiprocessing`, контекст `spawn`): чистый Python
  держит GIL, и в потоке подбор тормозил бы остальные запросы. Ход
  выполнения приходит из дочернего процесса через очередь, остановка идёт
  через событие.
- **Хранение.** Готовый результат пишется JSON-файлом в свой каталог рядом
  с паспортами: `data/teams/{team}/designs/layout_search/{design_id}.json`
  (не суффиксом к имени паспорта — решение после ревью безопасности:
  коллизия имён). Так он переживает перезапуск сервера.
- **API** — три маршрута в роутере `/design`.
- **Фронт:**
  - хук `useLayoutSearch` опрашивает статус раз в секунду, пока подбор идёт;
  - блок «Подбор раскладки» в `PatternPanel` с карточками;
  - слой предпросмотра в `PlanCanvas`;
  - действие `APPLY_LAYOUT` в редьюсере — один шаг отмены.

**Tech Stack:** Python 3 (multiprocessing), FastAPI/pydantic, React +
TypeScript, pytest/unittest, vitest, `tsc -b`.

**Spec:** `Docs/specs/2026-10-21-block-layout-optimizer-design.md`, раздел
«Часть 4: перебор (решено 22.10.2026)», пункт «4в».

## Global Constraints

- **Ограничения запуска.** Один подбор на блок. На весь сервер одновременно
  не больше одного подбора: процессор один, а бюджет 150 с рассчитан на
  одно ядро. Второй запуск получает 409 с текстом «Подбор раскладки уже
  идёт: блок «{имя}». Дождитесь окончания или остановите его.»
- **Бюджет** — `search_layout(budget_s=150)`. Сервер дополнительно
  страхуется: если дочерний процесс не завершился за `budget_s + 60` с, он
  принудительно завершается, а статус становится «ошибка».
- **Статусы:**

  | Статус | Подпись |
  |---|---|
  | `idle` | нет подбора |
  | `running` | идёт |
  | `done` | готово |
  | `stopped` | остановлен, показано лучшее найденное |
  | `failed` | ошибка |

- **Этапы:**

  | Этап | Подпись |
  |---|---|
  | `geometry` | «Геометрия сетки» |
  | `front_rows` | «Первый ряд у откоса» |
  | `refine` | «Уточнение» |

- **Карточка варианта.** Заголовок: «Вариант 1/2/3».
  - Параметры: «Азимут рядов, °», «Шаги a × b, м», «Первый ряд»
    («вертикальный» / «пара N°» / «переход, N ряд(а), N°»), «Вруб у фланга»
    (левого / правого).
  - Показатели:
    - «ЛСП вне коридора»;
    - «Быстрее 3 мс/м, %»;
    - «Стыки фронтов, м»;
    - «Вне коридора ±25 %, %»;
    - «Разброс темпа»;
    - «Скважин»;
    - «В окне 8 мс (справочно)»;
    - «Замедление в скважине, мс».

  Отбракованный вариант помечается «не прошёл проверки» с причинами
  человеческим языком (через `holeHealth`/`validate`-подписи, без кодов).
- **Пометки результата:**
  - `all_rejected` — «Ни один вариант не прошёл проверки — показаны лучшие из
    отбракованных.»;
  - `stopped_early` — «Подбор остановлен — показано лучшее найденное.»;
  - предупреждения `SearchResult.warnings` — списком.
- **«Устарел».** Отпечаток исходных данных — SHA-256 стабильной JSON-строки:
  контур, поверхности, домены, `pattern_params`, `rock_name`. Считает его
  фронт, сервер только хранит. Если текущий отпечаток не совпадает с
  сохранённым — пометка «Устарел: контур, съёмка или параметры изменились
  после подбора», а «Применить» спрашивает подтверждение.
- **«Применить»:**
  - заменяет скважины, сеть и `pattern_params` одним действием
    `APPLY_LAYOUT` — один шаг «Отменить»;
  - если в блоке есть ручные скважины (`source === "manual"`), сначала
    подтверждение «Ручные правки (N) будут потеряны. Применить вариант?»;
  - после применения «Коммутация» показывает схему «Магистраль + цепочки» с
    флангом варианта;
  - заблокировано, как и остальные правки, при статусе паспорта
    «утверждён» и дальше (`rejectLocked("designed")`).
- **Клик по карточке** показывает вариант на плане поверх текущего:
  полупрозрачные устья и связи, без применения. Повторный клик или «Скрыть»
  убирает показ.
- **Границы темпа** — по породе блока (`relief_bounds_for_rock`), как в
  `analyze`. Предупреждение о породе идёт в `warnings` результата.
- **Пользователю** — без служебных имён и JSON.
- Тексты, комментарии, docstring — на русском, как в соседнем коде.

## Review Focus

1. **Сервер перезапустился во время подбора.** Ожидается: статус `idle` или
   прежний сохранённый результат, без «вечного» `running`. Тест
   `test_restart_forgets_running` (задача 1).
2. **Дочерний процесс упал** (исключение в `search_layout`). Ожидается:
   статус `failed` с текстом «Подбор раскладки завершился с ошибкой: …»,
   реестр освобождён, следующий запуск возможен. Тест `test_child_failure`
   (задача 1).
3. **Паспорт без `design_id`** (новый, ещё не сохранённый). Ожидается: кнопка
   неактивна, подсказка «Сохраните паспорт, чтобы подобрать раскладку».
   Тест в задаче 4.
4. **Пользователь ушёл со страницы и вернулся.** Ожидается: хук подхватывает
   идущий подбор по `design_id` и продолжает опрос. Тест `useLayoutSearch`
   (задача 3).
5. **Применение при открытом предпросмотре другого варианта.** Ожидается:
   применяется тот вариант, чья кнопка «Применить» нажата; предпросмотр
   после применения снимается. Тест в задаче 4.

---

## Файлы

- Create: `design/layout_search/serialize.py`, `design/layout_search/jobs.py`.
- Modify: `design/persistence.py` (путь файла подбора), `api/schemas/design.py`,
  `api/services/design_service.py`, `api/routers/design.py`.
- Frontend:
  - Create: `frontend/src/pages/design/useLayoutSearch.ts`,
    `frontend/src/pages/design/LayoutSearchPanel.tsx`.
  - Modify: `frontend/src/types/design.ts`, `frontend/src/api/endpoints.ts`,
    `designReducer.ts`, `PatternPanel.tsx` (вставка блока), `PlanCanvas.tsx`
    (предпросмотр), `DesignPage.tsx`, `styles/design.css`.
- Docs: `Docs/LAYOUT_SEARCH.md`, `CLAUDE.md`, спецификация.
- Tests:
  - `tests/test_layout_search_jobs.py`, `tests/test_api_layout_search.py`;
  - `useLayoutSearch.test.ts`, `LayoutSearchPanel.test.tsx`,
    `designReducer.layout.test.ts`, `PlanCanvas` (по образцу существующих).

---

### Task 1: Сериализация и фоновые задачи

**Files:** `design/layout_search/serialize.py`, `design/layout_search/jobs.py`,
`design/persistence.py`, `tests/test_layout_search_jobs.py`

**Interfaces — Produces:**
- `evaluation_to_dict(e: Evaluation) -> dict` — `params`, `cut_flank`,
  `holes` (`Hole.to_dict`), `network` (`InitiationNetwork.to_dict`),
  `rejected`, `reject_codes`, все показатели из Global Constraints
  (`inf` → None).
- `result_to_dict(r: SearchResult) -> dict` — `best`, `evaluated`,
  `rejected`, `stopped_early`, `elapsed_s`, `all_rejected`, `warnings`.
- `layout_search_path(team_id: str, design_id: str) -> Path` в
  `persistence.py` — та же проверка `design_id`, что `design_path`, файл
  `layout_search/{design_id}.json` в каталоге паспортов.
- `class LayoutSearchJobs` в `jobs.py`:
  - `__init__(self, *, runner: str = "process", budget_s: float = 150.0,
    grace_s: float = 60.0)`; `runner` — `"process"` или `"thread"`, второй
    только для тестов;
  - `start(team_id, design_id, design_name, inputs: dict, fingerprint: str,
    relief_min_ms_m: float, relief_max_ms_m: float | None,
    warnings: list[str]) -> None` — `inputs` — словарь `BlastDesign`
    (`to_dict`); при занятости бросает `LayoutSearchBusyError(message)`;
  - `status(team_id, design_id) -> dict` — `{"state", "stage", "done",
    "total", "elapsed_s", "fingerprint", "result"}`. При `running` —
    без `result`. Иначе читает файл; файла нет — `idle`;
  - `stop(team_id, design_id) -> bool`.
- `get_layout_search_jobs() -> LayoutSearchJobs` — один экземпляр на процесс
  (для `Depends` и подмены в тестах).

Решения:
- Дочерняя функция — модульная (для `spawn`). Она восстанавливает
  `BlastDesign.from_dict(inputs)`, строит `SearchContext.from_design` с
  границами темпа и зовёт `search_layout` с `progress` → очередь и
  `should_stop` → `Event.is_set()`. Итог отдаёт в очередь как
  `result_to_dict` плюс предупреждения.
- Поток-наблюдатель в родителе читает очередь, обновляет реестр, при
  результате пишет файл
  `{"fingerprint", "state", "finished_at", "result"}` (`state` — `done` или
  `stopped`) и освобождает слот.
- Ошибка ребёнка — в очередь уходит текст, статус `failed`, файл не
  пишется, предыдущий результат остаётся. Выход ребёнка без результата
  (убит) тоже даёт `failed`.
- Сторож по `budget_s + grace_s` — `terminate()`, `failed`.

- [ ] **Step 1: Падающие тесты** (`runner="thread"`, малый контур 40×30 с
  гранью, `budget_s` 20):
  - `test_start_status_done` — после старта `running` с этапом, потом `done`;
    файл записан; в `result.best` до 3 вариантов со скважинами и сетью.
  - `test_busy_same_and_other_block` — второй старт того же и другого блока
    во время работы → `LayoutSearchBusyError`, в тексте имя блока.
  - `test_stop` — `stop` сразу после старта → `stopped`, результат с
    лучшим найденным или пометкой из `NOTHING_EVALUATED`.
  - `test_child_failure` — подменённая функция поиска бросает исключение →
    `failed` с текстом, слот свободен.
  - `test_restart_forgets_running` — новый экземпляр реестра: при файле —
    его состояние, без файла — `idle`.
  - `test_path_rejects_traversal` — `layout_search_path("t", "../x")` →
    `DesignNotFoundError`.
  - один тест с `runner="process"` на крошечном контуре: доходит до `done`
    (проверка, что `spawn` и сериализация работают).
- [ ] **Step 2: Запустить — падают.**
- [ ] **Step 3: Реализовать.**
- [ ] **Step 4:** `.venv/bin/python -m pytest tests/test_layout_search_jobs.py tests/test_layout_search*.py -q` — PASS, вывод без висящих процессов.
- [ ] **Step 5: Commit** — `Подбор раскладки: фоновые задачи и хранение`.

---

### Task 2: API

**Files:** `api/schemas/design.py`, `api/services/design_service.py`,
`api/routers/design.py`, `tests/test_api_layout_search.py`

**Interfaces:**
- Consumes: `LayoutSearchJobs`, `get_layout_search_jobs`,
  `LayoutSearchBusyError` (задача 1), `relief_bounds_for_rock`.
- Produces (все с `organization_id=Depends(current_team_id)`):
  - `POST /design/layout-search` — тело
    `LayoutSearchStartRequest {design_id: str, design: BlastDesignSchema
    (как в AnalyzeRequest), fingerprint: str}` → 202
    `LayoutSearchStatusResponse`. Занято — 409 с текстом из Global
    Constraints. Нужен `Depends(get_economics_repository)` для породы.
  - `GET /design/layout-search/{design_id}` → `LayoutSearchStatusResponse`.
  - `POST /design/layout-search/{design_id}/stop` →
    `LayoutSearchStatusResponse`.
  - `LayoutSearchStatusResponse {state, stage: str | None, done: int,
    total: int, elapsed_s: float, fingerprint: str | None,
    result: LayoutSearchResultSchema | None}`; варианты — `holes:
    list[HoleSchema]`, `network: InitiationNetworkSchema`, `params: dict`,
    `cut_flank`, показатели.
- Порода: `relief_bounds_for_rock(snapshot, design.rock_name)` с теми же
  предупреждениями, что в `analyze_design` (вынести их сборку в общую
  функцию, `analyze_design` зовёт её же — поведение без изменений).

- [ ] **Step 1: Падающие тесты** — `TestClient` по образцу
  `tests/test_api_cad.py`: подменить `require_internal_access`,
  `current_team_id` (org-a), `get_economics_repository`,
  `get_layout_search_jobs` (`runner="thread"`, малый бюджет):
  - старт → 202, `running`;
  - опрос до `done`;
  - результат с 1–3 вариантами;
  - второй старт → 409 с текстом;
  - stop → `stopped`;
  - чужая организация не видит результат (`idle`);
  - `design_id` с `..` → 404;
  - `analyze` после выноса предупреждений о породе отвечает как раньше.
- [ ] **Step 2: Запустить — падают.**
- [ ] **Step 3: Реализовать.**
- [ ] **Step 4:** `.venv/bin/python -m pytest tests/test_api_layout_search.py tests/test_api_*.py -q` — PASS.
- [ ] **Step 5: Commit** — `API подбора раскладки`.

---

### Task 3: Клиент API и хук опроса

**Files:** `frontend/src/types/design.ts`, `frontend/src/api/endpoints.ts`,
`frontend/src/pages/design/useLayoutSearch.ts`, `useLayoutSearch.test.ts`

**Interfaces — Produces:**
- Типы: `LayoutSearchState`, `LayoutSearchVariant`, `LayoutSearchResult`,
  `LayoutSearchStatus` — зеркало схем задачи 2.
- `api.design.layoutSearchStart(designId, design, fingerprint)`,
  `layoutSearchStatus(designId)`, `layoutSearchStop(designId)`.
- `layoutFingerprint(input: {contour, surfaces, domains, pattern_params,
  rock_name}) -> Promise<string>`: стабильный JSON (ключи по алфавиту,
  рекурсивно) → SHA-256 (`crypto.subtle`) → hex.
- `useLayoutSearch(designId: string | null, fingerprint: string | null)
  -> { status, start(design), stop(), error, stale: boolean }`:
  - при монтировании и смене `designId` — один запрос статуса;
  - пока `running` — повтор через 1000 мс (`setTimeout`, не `setInterval`);
  - запоздалые ответы старого `designId` отбрасываются (счётчик поколений,
    как в `useStaleAnalysis`);
  - `stale` — есть результат и его `fingerprint` ≠ текущему;
  - 409 → `error` с текстом сервера.

- [ ] **Step 1: Падающие тесты** (vitest, фальшивые таймеры, подменённый
  `api`):
  - старт → опрос до `done`;
  - остановка;
  - возврат на страницу при идущем подборе продолжает опрос;
  - смена `designId` отбрасывает старый ответ;
  - `stale`;
  - отпечаток не зависит от порядка ключей и меняется при правке контура;
  - 409 → `error`.
- [ ] **Step 2: Запустить — падают.**
- [ ] **Step 3: Реализовать.**
- [ ] **Step 4:** `cd frontend && npx vitest run src/pages/design/useLayoutSearch.test.ts && npx tsc -b` — PASS.
- [ ] **Step 5: Commit** — `Подбор раскладки: клиент и опрос`.

---

### Task 4: Панель, предпросмотр и «Применить»

**Files:** `LayoutSearchPanel.tsx` (+ test), `PatternPanel.tsx`,
`PlanCanvas.tsx`, `designReducer.ts` (+ `designReducer.layout.test.ts`),
`DesignPage.tsx`, `styles/design.css`

**Interfaces:**
- Consumes: `useLayoutSearch`, типы (задача 3).
- Produces:
  - `APPLY_LAYOUT { holes, network, pattern_params }` в `UNDOABLE`;
  - `PlanCanvas` получает `preview?: { holes: Hole[]; network:
    InitiationNetwork } | null` — рисуется поверх, полупрозрачно (устья и
    связи), не участвует в выборе и подсказках;
  - `LayoutSearchPanel` получает `{ designId, status, stale, error,
    manualCount, locked, previewIndex, onStart, onStop, onPreview(index |
    null), onApply(variant) }`.

Поведение — по Global Constraints:
- **Кнопка «Подобрать раскладку»:**
  - при `locked` неактивна;
  - при `designId == null` неактивна с подсказкой «Сохраните паспорт, чтобы
    подобрать раскладку».
- **Во время подбора** — полоса прогресса «{этап}: {done} из {total}»,
  время, кнопка «Остановить».
- **Результат** — пометки и три карточки.
- **Применение** — `DesignPage` диспатчит `APPLY_LAYOUT`, ставит
  `tieScheme = "trunk_chains"` и фланг в `tieParams`, снимает предпросмотр.

- [ ] **Step 1: Падающие тесты:**
  - редьюсер: `APPLY_LAYOUT` заменяет скважины, сеть и параметры, один `UNDO`
    возвращает всё;
  - панель:
    - подписи этапов;
    - карточки с подписями показателей;
    - отбракованная карточка с причинами;
    - пометки `all_rejected`, `stopped_early`, «Устарел»;
    - подтверждение при ручных скважинах (`window.confirm` подменён);
    - неактивная кнопка без `designId` и при `locked`;
    - клик по карточке → `onPreview(i)`, повторный → `onPreview(null)`;
    - «Применить» на варианте 2 при предпросмотре варианта 1 →
      `onApply(вариант 2)`;
  - `PlanCanvas`: при `preview` рисуется дополнительный слой (по образцу
    существующих тестов холста).
- [ ] **Step 2: Запустить — падают.**
- [ ] **Step 3: Реализовать.**
- [ ] **Step 4:** `cd frontend && npx vitest run && npx tsc -b` — PASS.
- [ ] **Step 5: Commit** — `Подбор раскладки: панель, предпросмотр и применение`.

---

### Task 5: Проверка на стенде №66 и документация

- [ ] **Step 1: Стенд.** Поднять стенд ветки (`.claude/stand`,
  `.claude/launch.json`: api-stand-relief :8020, frontend-stand-relief
  :5181). Добавить в `stand_app.py` роутер `/design` с реестром подбора;
  `stand_app.py` не коммитится.
  - Загрузить чертёж №66 (как в части 2: `frontend/public` + DataTransfer),
    построить сетку 4,41 × 3,53.
  - Сохранить паспорт, нажать «Подобрать раскладку».
  - Проверить:
    - ход по этапам;
    - «Остановить» на этапе 1 показывает лучшее найденное;
    - полный подбор даёт три карточки;
    - предпросмотр на плане;
    - «Применить», затем «Отменить»;
    - пометку «Устарел» после смены шага a.
  - Скриншоты сохранить в scratchpad.
  - Убрать DXF из `frontend/public`.
- [ ] **Step 2: Документация.**
  - `Docs/LAYOUT_SEARCH.md` — раздел «В интерфейсе» (запуск, статусы,
    карточки, применение, хранение, ограничение «один подбор на сервер»).
  - `CLAUDE.md` — дополнить раздел «Перебор раскладки».
  - Спецификация — 4в «Сделано», дата.
- [ ] **Step 3:** полный прогон: `.venv/bin/python -m pytest -q -x` (в фоне),
  `cd frontend && npx vitest run && npx tsc -b` — без ошибок.
- [ ] **Step 4: Commit** — `Подбор раскладки: проверка на стенде и документация`.
