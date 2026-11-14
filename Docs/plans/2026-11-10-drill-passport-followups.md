# Паспорт на бурение: доработки после выкатки — план

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** перенумеровать скважины сохранённого проекта по правилу эшелонов без перестроения сетки; проверка первого ряда паспорта — по данным проекта блока, без ручных c и Wпред; поле «Блок» нового паспорта — не «Блок».

**Architecture:** перенумерация — чистая функция `design/numbering.py::renumber_map` (старый id → новый) и маршрут `POST /design/holes/renumber`; фронт применяет соответствие одним шагом отмены (`RENUMBER_HOLES`) ко всем ссылкам документа. Проверка первого ряда в `design/drilling_passport.py` берёт c — расстояние устья до верхней бровки (`toe_line.crest_geometry`), W и Wпред — `toe_line.floor_burdens` (ЛСП у подошвы и W проекта + 3 %).

**Tech Stack:** Python (shapely), FastAPI, React + TS, pytest, vitest.

**Spec:** решения владельца 10.11.2026 в этой сессии (номера блока 67 по старому правилу; «эта часть интерфейса очень сложная» — проверка первого ряда); `CLAUDE.md` — «Нумерация скважин», «Паспорт на бурение (TASK-015)».

## Global Constraints

- Полей в `BlastDesign` не добавлять; перенумерация — только в черновике (`canEditDesigned`).
- Перенумерация не двигает скважины: меняются только `id` и ссылки на них.
- Ручные скважины (`source == "manual"`) номер не меняют; пара у откоса — номер вертикальной + «T»; стенки P/K/B/T/SAT/S/I — прежнее правило рядов.
- В паспорт печатается только s; c, c_min, W, Wпред — для инженера.
- JSON пользователю не показывать; тексты — по-русски.

## Review Focus

1. Перенумерация переставляет номера (старый «5-08» становится номером другой скважины): ссылки переименовываются одновременно по соответствию, без каскада. Тест — задача 2.
2. Сеть: производные id (`det-…`, `sc-…`, `dh-…`, `st-…`, `ch-…`, `fire-…`) пересобираются с новым номером — иначе путаница и коллизии. Тест — задача 2.
3. Блок без бровки: c и W по проекту не измерить — проверка говорит об этом, а не показывает нули. Тест — задача 3.
4. Старые черновики с `first_row_offset_m` / `w_max_m` в payload открываются и сохраняются (лишние ключи игнорируются). Тест — задача 3.
5. Перенумерация после неё же — тот же результат (идемпотентно), блок 67 из фикстуры получает «1-01» у бровки на южном (левом с откоса) фланге. Тест — задача 1.

---

### Task 1: `renumber_map` и маршрут `POST /design/holes/renumber`

**Files:** `design/numbering.py`, `api/routers/design.py`, `api/schemas/design.py`, `api/services/design_service.py`; тесты `tests/test_numbering.py` (или существующий файл нумерации), `tests/test_api_design.py`.

**Interfaces:**
- `renumber_map(holes: list[Hole], contour: BlockContour, pattern_params: Mapping) -> dict[str, str]` — только изменившиеся id. `deep_dir` — `pattern_origin(contour, *local_basis(row_azimuth_deg))[1]` (как у генератора: от бровки вглубь); позиции — устья (`positions=None`); пары — по старому id (`partners=None`).
- `POST /api/v1/design/holes/renumber`: запрос `{holes, contour, params}` (схемы как у `/holes/recompute`), ответ `{mapping: {старый: новый}}`.

- [ ] Тесты: блок 67 (`tests/test_block67_back_layout.py` / фикстура) с номерами по старому правилу (ряды) → «1-01» у бровки на левом фланге с откоса; повторный вызов на результате — пустое соответствие; ручная скважина и пара «…T» — по правилу; маршрут отдаёт соответствие, 422 на пустой список.
- [ ] Реализация, тесты зелёные, коммит.

### Task 2: фронт — `RENUMBER_HOLES` и кнопка «Перенумеровать скважины»

**Files:** `frontend/src/pages/design/designReducer.ts` (+ `renameHoleIds` рядом с `pruneLoadsAndNetwork`), `frontend/src/api/endpoints.ts`, `frontend/src/pages/design/PatternPanel.tsx` (кнопка), `frontend/src/pages/design/DesignPage.tsx` (вызов, сброс выделения); тесты `designReducer.renumber.test.ts`, `PatternPanel.test.tsx`.

**Interfaces:** действие `{ type: "RENUMBER_HOLES"; mapping: Record<string, string> }` в `UNDOABLE`; `renameHoleIds(document, mapping)` переименовывает `holes[].id`, `loads[].hole_id`, все поля `network` (2.0 и старые, ключи `downhole_delay_ms`/`electronic_times_ms`, `selected_hole_ids`, производные id), `as_drilled/as_charged/as_fired[].design_hole_id` (и детонатор).

- [ ] Тесты: перестановка «5-08»↔«5-09» без каскада; связи, заряды, времена, исполнение — по новым номерам; производные id пересобраны; одна отмена возвращает всё.
- [ ] Кнопка во вкладке «Сетка»: «Перенумеровать скважины по правилу» (недоступна не в черновике), подтверждение «Номера скважин изменятся; заряды, связи и исполнение сохранятся. Паспорт на бурение возьмёт новые номера после новой ревизии»; после — сообщение «Перенумеровано N скважин» или «Номера уже по правилу».
- [ ] Реализация, тесты, коммит.

### Task 3: проверка первого ряда — по проекту блока

**Files:** `design/drilling_passport.py` (`first_row_check`, `resolve_inputs`, `passport_context`), `api/schemas/drilling_passport.py` (убрать `first_row_offset_m`, `w_max_m`), `api/services/drilling_passport_prefill.py` (не переносить `w_max_m`), фронт `form.ts` (убрать поля, `checkRows` — 3 строки), `DrillPassportHelp.tsx`; тесты `tests/test_drilling_passport.py`, `tests/test_api_drilling_passport.py`, `form.test.ts`, `DrillPassportDialog.test.tsx`.

**Interfaces:** `FirstRowCheck`: `s_m`, `hs_m`, `hs_source`, `h1_m`, `c_min_m`, `c_min_measured_m`, `c_max_measured_m`, `w_m` (наибольшая ЛСП у подошвы по первому ряду), `w_max_m` (W проекта + 3 %, `FloorBurden.allowed_m`), `issues`. c — расстояние устья скважины первого ряда до верхней бровки; W — `floor_burdens(design)[id].value_m`.

- [ ] Тесты: блок 66 — c и W из проекта (числа по фикстуре), `first_row_too_close` при c < s − e со списком скважин; `first_row_burden` при W > W + 3 % проекта; без бровки — `first_row_not_measured` (c и W не посчитаны); W проекта не задана — `w_max_missing` с текстом «W не задана в проекте блока»; старый payload с `w_max_m` сохраняется (ключ игнорируется).
- [ ] Фронт: строки «Безопасное расстояние s», «Первый ряд от бровки — 0,2…0,6 м, нужно ≥ c_min», «ЛСПП у подошвы — до W, допустимая Wпред»; Hs/H₁ — строкой только при `bench_above_design`; полей c и Wпред нет.
- [ ] Реализация, тесты, коммит.

### Task 4: поле «Блок» нового паспорта

**Files:** `api/services/drilling_passport_service.py` (`create_passport`), тест в `tests/test_api_drilling_passport.py`.

**Interfaces:** `block_label(design) -> str`: имя контура, если не «Блок» по умолчанию; иначе номер из названия проекта («Блок 67» → «67»); иначе название проекта; не длиннее 40.

- [ ] Тест: контур «Блок», проект «Блок 67» → «67»; контур «66» → «66»; проект «Уступ 120» → «Уступ 120».
- [ ] Реализация, коммит.

### Task 5: стенд, документация, проверки

- [ ] Стенд: блок 67 из фикстуры со старыми номерами → «Перенумеровать» → паспорт с номерами по правилу; окно — три строки проверки.
- [ ] `CLAUDE.md` («Нумерация скважин», «Паспорт на бурение»), `Docs/plans/TASK-015-progress.md` (PR 6 — слит 10.11.2026 (#171, 2180534); раздел доработок).
- [ ] Полный pytest, `npx tsc -b`, vitest; коммит; push и PR — с согласия владельца; /code-review и «@codex review».
