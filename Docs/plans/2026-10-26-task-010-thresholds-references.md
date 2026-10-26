# TASK-010: пороги методики ФОТ — в справочники. План реализации

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** три порога, зашитые в коде методики ФОТ, правятся вручную в справочниках через обычные формы: доля списания простоев, множитель темпа выше потолка и верх шкалы крепости. Значения по умолчанию совпадают с нынешними, ни одна цифра расчёта не меняется.

**Architecture:** поля добавляются в схемы существующих разделов (`payroll_params`, `drilling_difficulty`) — формы, импорт и выгрузка строятся по каталогу схем сами (CLAUDE.md, «Справочники экономики»). Модель получает значения через `PayrollCalendar` и `DifficultyTables`; константы кода остаются значениями по умолчанию аргументов функций. Новых разделов, миграций и интерфейсных компонентов нет.

**Tech Stack:** Python 3.13, Decimal, pydantic 2, FastAPI, pytest.

**Spec:** `Docs/specs/2026-09-13-task-010-payroll-decisions.md` (§2.3 флаг 25 %, Т12 флаг темпа, §3 интервалы крепости: «f > 20 → коэффициент последней строки с предупреждением»); `Docs/REFERENCES_MODEL.md`, `Docs/PAYROLL_MODEL.md`. Решение владельца 26.10.2026: после выкатки все расценки и коэффициенты настраиваются вручную; пороги выносим в справочник.

## Global Constraints

- Значения по умолчанию равны нынешним константам: `write_off_flag_share = 0,25`, `pace_flag_ratio = 1,2`, `hardness_scale_max = 20`. Записи, опубликованные до PR, этих ключей не содержат и читаются с умолчаниями; публикация и расчёт на них не меняются.
- Поля описываются только схемой: `x-unit`, `title`, `description` (CLAUDE.md); новое поле входит в `SECTION_FIELDSETS`, иначе тест покрытия формы упадёт. Своих компонентов и JSON в интерфейсе нет.
- Пороги — флаги и предупреждения, расчёт они не блокируют (§2.3); отрицательные и нулевые значения схема не пропускает.
- Классы условий труда с 36-часовой неделей (ст. 92 ТК РФ) в код остаются: неделя у должности и так переопределяется полем `week_hours_override` справочника «Должности».
- Всё в Decimal; `cost/model` не импортирует `cost.drilling` и `cost.strategies`.
- Код флага `DOWNTIME_OVER_25` не переименовывается (ключ API); пояснение в тексте берёт порог из справочника.
- `pytest`, `cd frontend && npx tsc -b && npx vitest run` — на чистом чекауте без iCloud-дублей.

## Review Focus

- Запись без новых ключей (снимок до PR, `model_validate({})` с обязательными полями года) валидна и даёт прежние флаги.
- Порог доли списания 1,0 и выше: флаг не срабатывает никогда, расчёт не падает; 0 схема отклоняет.
- Множитель темпа меньше 1: схема отклоняет (темп ниже потолка флагом «выше потолка» не назовёшь).
- Верх шкалы крепости ниже последней конечной границы таблицы: предупреждение ревизии, а не ошибка.
- Расчёт блока и превью берут один и тот же год «Параметров ФОТ» для порогов и для МРОТ (при отсутствии года — запасной год с предупреждением, пороги из той же записи).
- Сид (`scripts/seed_payroll_references.py`) дописывает новые ключи в пустые поля существующих записей, заданные значения не трогает, повторный прогон ничего не меняет.

## Структура файлов

| Файл | Ответственность |
|---|---|
| `cost/v2/schemas/payroll.py`, `cost/v2/schemas/__init__.py` | поля порогов, проверки, группы формы |
| `cost/model/payroll.py` | `PayrollCalendar`, `DifficultyTables`, `effective_shifts`, `pace_flags`, `hardness_factor` принимают пороги |
| `cost/model/payroll_inputs.py`, `payroll_preview.py`, `pace.py` | передают пороги из календаря и таблиц |
| `cost/v2/payroll_checks.py` | предупреждение ревизии про верх шкалы крепости |
| `cost/v2/payroll_defaults.py` | умолчания сида |
| `Docs/REFERENCES_MODEL.md`, `Docs/PAYROLL_MODEL.md` | описание полей |

---

### Task 1: Поля порогов в схемах

**Files:**
- Modify: `cost/v2/schemas/payroll.py` (`PayrollParamsPayload`, `DrillingDifficultyPayload`), `cost/v2/schemas/__init__.py` (`SECTION_FIELDSETS`)
- Test: `tests/test_payroll_schemas.py`, `tests/test_api_reference_schema.py`

**Interfaces:**
- Produces: `PayrollParamsPayload.write_off_flag_share: Decimal` (`RateField`, умолчание `0.25`, `gt=0`), `PayrollParamsPayload.pace_flag_ratio: Decimal` (`UnitField("", …)`, умолчание `1.2`, `ge=1`); `DrillingDifficultyPayload.hardness_scale_max: Decimal` (`UnitField("f", …)`, умолчание `20`, `gt=0`). В `SECTION_FIELDSETS["payroll_params"]` группа «Контроль» дополняется обоими полями; у `drilling_difficulty` групп в `SECTION_FIELDSETS` нет — поле добавляется в схему без группы, перед таблицей крепости (порядок полей схемы), `SECTION_FIELDSETS` для него не заводить.

- [ ] **Step 1: Tests.** `test_thresholds_default_to_the_former_constants` (`PayrollParamsPayload` и `DrillingDifficultyPayload` без новых ключей: `0.25`, `1.2`, `20`); `test_old_record_without_thresholds_still_validates` (минимальная запись года из `PAYROLL_PARAMS` без трёх ключей валидна); `test_write_off_share_must_be_positive` (0 и −0,1 → ошибка, 1 и 1,5 → валидно); `test_pace_ratio_below_one_is_rejected` (0,9 → ошибка, 1 → валидно); `test_hardness_scale_max_must_be_positive`; `test_thresholds_have_unit_title_and_description` (у каждого поля непустые `title`, `description`, `x-unit`); в `tests/test_api_reference_schema.py` проходит существующий `test_fieldsets_cover_all_visible_fields`.
- [ ] **Step 2:** `.venv/bin/python -m pytest tests/test_payroll_schemas.py tests/test_api_reference_schema.py -q` — FAIL.
- [ ] **Step 3: Implement** поля и группы формы; описания по-русски без кодов («Доля часов вахты, списанных не по вине машиниста, выше которой — предупреждение», «Во сколько раз темп может превысить потолок шкалы, прежде чем предупреждать», «Верх шкалы крепости: выше берётся коэффициент последней строки и выводится предупреждение»).
- [ ] **Step 4:** те же тесты — PASS.
- [ ] **Step 5: Commit** — `TASK-010: пороги методики ФОТ в схемах справочников`.

### Task 2: Модель берёт пороги из справочников

**Files:**
- Modify: `cost/model/payroll.py` (`PayrollCalendar`, `DifficultyTables`, `effective_shifts`, `pace_flags`, `hardness_factor`, `normalized_meters`), `cost/model/payroll_inputs.py` (`payroll_context`, `difficulty_tables`), `cost/model/payroll_preview.py` (вызовы `effective_shifts`, `pace_flags`), `cost/model/pace.py` (вызов `hardness_factor`)
- Test: `tests/test_payroll_shifts.py`, `tests/test_payroll_curve.py`, `tests/test_payroll_meters.py`, `tests/test_payroll_inputs.py`, `tests/test_api_payroll_preview.py`, `tests/test_model_pace.py`

**Interfaces:**
- Consumes: поля задачи 1.
- Produces: `PayrollCalendar.write_off_flag_share: Decimal = WRITE_OFF_FLAG_SHARE` и `PayrollCalendar.pace_flag_ratio: Decimal = PACE_FLAG_RATIO` (поля с умолчаниями — прямые конструкторы в фикстурах не ломаются); `DifficultyTables.hardness_scale_max: Decimal = PROTODYAKONOV_MAX`; `effective_shifts(shifts, shift_hours, downtime, reasons, *, flag_share: Decimal = WRITE_OFF_FLAG_SHARE)`; `pace_flags(scale, pace, *, ratio: Decimal = PACE_FLAG_RATIO)`; `hardness_factor(f, bands, max_f: Decimal = PROTODYAKONOV_MAX)`. Константы остаются в `payroll.py` как значения по умолчанию.

- [ ] **Step 1: Tests.** `effective_shifts`: при `flag_share=0.40` те же 40 ч из 143 (27,97 %) флага не дают, при `0.20` дают, текст флага называет порог из аргумента («больше 20 %»); `pace_flags`: при `ratio=1.5` темп 230 (1,2461 × потолка) флага нет, при `ratio=1.0` темп 190 флаг есть, текст берёт множитель из аргумента; `hardness_factor`: f = 25 при `max_f=30` — без предупреждения, f = 25 при `max_f=20` — предупреждение с «до 20»; `payroll_context` собирает `PayrollCalendar` с порогами записи года (запись с `write_off_flag_share = 0.5` → календарь 0,5; запись без ключа → 0,25); `difficulty_tables` читает `hardness_scale_max`; API: `POST /api/v1/economics/payroll/preview` на ревизии с `pace_flag_ratio = 1.5` не возвращает флаг темпа там, где умолчание его вернуло бы, а с `write_off_flag_share = 0.40` — флага списания; `planned_pace` и `normalized_meters` передают `tables.hardness_scale_max` (f = 25 при верхе 30 — предупреждения нет, коэффициент последней строки).
- [ ] **Step 2:** запуск перечисленных файлов — FAIL.
- [ ] **Step 3: Implement.** Значение по умолчанию аргумента — константа; вызывающие передают поле календаря или таблиц. Расчёт без порогов в аргументах остаётся побайтово прежним.
- [ ] **Step 4:** перечисленные файлы + `tests/test_model_block_payroll*.py`, `tests/test_payroll_regression_2026_09.py`, `tests/test_model_regression_smeta_2026_01.py` — PASS без правок существующих ожиданий.
- [ ] **Step 5: Commit** — `TASK-010: модель ФОТ берёт пороги флагов и верх шкалы крепости из справочников`.

### Task 3: Проверка ревизии и сид

**Files:**
- Modify: `cost/v2/payroll_checks.py`, `cost/v2/payroll_defaults.py` (`PAYROLL_PARAMS` и данные таблицы сложности)
- Test: `tests/test_payroll_checks.py`, `tests/test_payroll_defaults.py`, `tests/test_seed_payroll_references_script_pg.py` (если сид покрыт — дописать)

**Interfaces:**
- Produces: проверка `_hardness_scale_max_below_bands` — предупреждение ревизии (не ошибка), если `hardness_scale_max` не больше наибольшей конечной границы `f_to` таблицы крепости («верх шкалы крепости ниже границ таблицы: предупреждение о f выше шкалы будет срабатывать на строках таблицы»); `PAYROLL_PARAMS` получает ключи `write_off_flag_share = "0.25"`, `pace_flag_ratio = "1.2"`; запись таблицы сложности в сиде получает `hardness_scale_max = "20"`.

- [ ] **Step 1: Tests.** `test_hardness_scale_max_below_last_band_warns` (верх 15 при границах 8/12/16/18 → одно предупреждение, публикация не блокируется); `test_hardness_scale_max_above_bands_is_silent`; `test_seed_fills_new_threshold_keys_only_when_empty` (запись с `write_off_flag_share = "0.40"` остаётся 0,40, пустой ключ получает 0,25); `test_seed_is_idempotent_with_thresholds` (повторный прогон: «изменений нет»).
- [ ] **Step 2:** запуск — FAIL.
- [ ] **Step 3: Implement** проверку по образцу соседних (`ValidationIssue` уровня предупреждения) и ключи сида; запись для чужих/чужого года сид по-прежнему не гибридизирует.
- [ ] **Step 4:** тесты файлов + `.venv/bin/python -m pytest tests/test_payroll_checks.py tests/test_payroll_defaults.py -q` — PASS.
- [ ] **Step 5: Commit** — `TASK-010: проверка верха шкалы крепости и умолчания сида`.

### Task 4: Документация и полный прогон

**Files:**
- Modify: `Docs/REFERENCES_MODEL.md` (таблицы полей `payroll_params` и `drilling_difficulty`), `Docs/PAYROLL_MODEL.md` (раздел «Входы» и описание флагов), `CLAUDE.md` — не менять

- [ ] **Step 1:** в `Docs/REFERENCES_MODEL.md` дописать три поля с единицами, умолчаниями и пояснением «пусто в старых записях = умолчание»; в `Docs/PAYROLL_MODEL.md` флаги «списано больше 25 %» и «темп выше 1,2 × потолка» описать как настраиваемые («по умолчанию»), верх шкалы крепости — там же в разделе приведённых метров; отдельно записать, что остаётся в коде и почему: классы короткой недели (закон, переопределяется у должности), форма кривой, расчёт «основной» шкалы по порядку состава бригады.
- [ ] **Step 2:** полный прогон: `.venv/bin/python -m pytest -q` (в фоне, с выводом в файл) — без падений, кроме известного флака тайминга `tests/test_cad_surface.py::test_flat_protection_without_other_levels_is_bounded` (перезапустить отдельно); `cd frontend && npx tsc -b && npx vitest run`.
- [ ] **Step 3: Commit** — `TASK-010: документация порогов методики ФОТ`.

---

## Не входит в PR

Переключатель источника ФОТ и разбивка в интерфейсе (PR 3b, план слит: `Docs/plans/2026-10-26-task-010-pr3b-frontend.md`); начисление проживания в режиме методики; выбор «основной» должности для доли «получает машинист» полем справочника; ширина графика шкалы (`SERIES_SPAN`, чисто оформление); правка матрицы условий бурения (Т19, данные — после проверки реальных цифр прода).

## Self-review

- Покрытие запроса «вручную настроить все расценки и коэффициенты»: расценки и коэффициенты методики уже в справочниках (PR 1); этот PR закрывает пороги в коде — три из пяти зашитых значений; остальные два (классы короткой недели, правило основной шкалы) вынесены осознанно, причины в задаче 4 и «Не входит».
- Имена согласованы: `write_off_flag_share`, `pace_flag_ratio`, `hardness_scale_max` (1→2→3); аргументы функций `flag_share`, `ratio`, `max_f` (2).
- Числа в тестах взяты из спеки: 40 ч из 143 = 27,97 %; темп 230 при потолке 184,6154 = 1,2459 × потолка.
