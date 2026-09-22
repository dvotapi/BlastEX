# TASK-010 PR 1 — справочники методики ФОТ

> **Для исполнителя-агента:** обязательный навык — superpowers:subagent-driven-development (рекомендуется) или
> superpowers:executing-plans. Шаги отмечаются чекбоксами (`- [ ]`).

**Цель:** справочники хранят всё, что нужно расчёту ФОТ по методике владельца: нормы должностей, плоскую шкалу
сдельной премии в ставке, доп. тариф взносов, вахту объекта, параметры года, коэффициенты сложности бурения и
причины простоев; ревизия проверяет их, сид дописывает данные файла владельца поверх опубликованного снимка.
Расчёт сметы не меняется.

**Архитектура:** поля payload — только pydantic-схемы `cost/v2/schemas/` (`title`, `description`, `x-unit`,
`x-ref`); правила одной записи — `model_validator` в схеме с путём до поля строки; правила по нескольким разделам —
новый модуль `cost/v2/payroll_checks.py`, который вызывает `validate_reference_sections`. Сид —
`cost/v2/payroll_defaults.py` по образцу `reclassify_positions` и скрипт с сухим прогоном. Форма, xlsx/JSON и
зеркала подхватывают разделы по каталогу схем; фронт получает только подписи перечислений и текстовые подсказки
кривой в существующем `derivedHints`.

**Стек:** Python 3.13 + pydantic 2 + Decimal, pytest; React 18 + TypeScript, vitest.

**Спецификация:** `Docs/specs/2026-09-13-task-010-payroll-decisions.md` — §1 (крепость f ≤ 0), §3 Т1, Т2, Т3, Т5,
Т6, Т7, Т8, Т10, Т15, Т16, Т17; §5 «PR 1 — справочники»; §6 (риск «сид затирает должности на проде»); §7
«Справочники и формы». Задача — `TASK-010 Зарплата персонала по объектам 3.md` (корень основного чекаута, не в git),
§2.2. Исходник данных — `~/Yandex.Disk.localized/001 ComplEX/003 Персонал/Штатное расписание/Расчет заработной платы.xlsx`
(в git кладётся в PR 2).

## Контекст

Код проверен на `main` = `a826a2b`. Прототип кода этого плана прогнан в worktree и откачен: весь `tests/` —
1375 passed, 32 skipped (как на `main`); новые тесты — зелёные; `tsc -b` чистый.

**Схемы и форма**

- `cost/v2/schemas/labor.py:57-73` — `LaborRatePayload` уже несёт `fixed_monthly_rub`, `piece_rate_rub`,
  `condition_code` (Т1). `PositionPayload` (`:17-54`) — только нормы блока.
- `cost/v2/schemas/organization.py:99-126` — `OrganizationRatesPayload`: НДФЛ 0,13, взносы 0,30, травматизм 0,0042,
  резерв 0,20, `shift_hours` 11 (`:126`). Доп. тарифа по классу условий труда нет (Т2).
- `cost/v2/schemas/organization.py:44-96` — `SitePayload` без полей вахты.
- `cost/v2/schemas/misc.py:78` — `RockPayload.hardness_f` уже есть, `ge=0`: ноль проходит, хотя §1 требует ошибку (Т7).
- `cost/v2/schemas/base.py:97-116` — `field_error` ставит `loc=(field,)` (`:112`): ошибку под подполем строки
  списка (`tiers.1.rate`) им не адресовать.
- `cost/v2/schemas/__init__.py:70-120` — `SECTION_FIELDSETS`, `:123-157` — `SECTION_SCHEMAS`;
  `cost/v2/references.py:26-139` — `REFERENCE_SECTION_DEFINITIONS`.
- `frontend/src/pages/references/schemaFields.ts:102-111` — поле с `$ref` без `type` получает вид `text` и
  показывается строкой «[object Object]»; `fields/ListField.tsx:88-126` рисует подполе строки только селектом ссылки,
  перечислением или текстом — флаг и дата стали бы текстом. **В PR 1 нет ни вложенных объектов, ни флагов и дат в
  строках списков** (шкала плоская по Т5; списки `tiers`, `hardness`, `diameter`, `geology`, `extra_tariffs` — числа,
  ссылки и перечисление), поэтому форма не меняется, а защитный тест (Задача 1) не пустит такое поле без доработки
  формы.
- `frontend/src/pages/references/schemaFields.ts:240-261` — нетронутая строка списка узнаётся по ссылке на объект.
  Черновик строки не клонирует (`importDraft.ts:17-20` копирует запись, не payload); PR 1 это не трогает.
- `frontend/src/pages/references/fields/EnumSegment.tsx:20` — до трёх значений и не `None` — сегменты, иначе селект
  с «не задано». `enumLabels.ts:8-65` — общий словарь подписей по коду значения: коды новых перечислений не должны
  совпадать с существующими (`NONE` — «Без класса хранения», `DRILLING` — «Расходы на бурение», `M3` — «На м³»).
- `frontend/src/lib/referenceDerived.ts:128-137` — `derivedHints` уже даёт текстовые подсказки для `positions` и
  `drilling_conditions`; сюда ложатся подсказки кривой (Т6), без разделоспецифичного компонента.

**Проверка и публикация**

- `cost/v2/references.py:305-401` — `validate_reference_sections` проверяет весь черновик;
  `api/routers/economics.py:310-328` — любая ошибка даёт 422 и блокирует публикацию всей организации (Т15).
- `cost/v2/references.py:404-426` — ошибка схемы уходит в `ValidationIssue.field` путём `members.0.headcount`;
  форма показывает её под подполем (PR 0).

**Файлы и зеркала**

- `cost/v2/reference_files.py:51-67, 91-103` — колонки листа строятся по схеме, список — JSON в ячейке; новые разделы
  попадут в xlsx и JSON без правок. Число из ячейки возвращается строкой без хвостовых нулей (`:330-339`: «0.70» →
  «0.7»), поэтому круг xlsx сравнивается через `model_validate`, круг JSON — точно (§7).
- `cost/v2/public_sync/settings.py:51-64` — новый раздел со схемой сам становится доступным для зеркала; таблица
  появляется только после флага администратора. `mirror.py:312-330` пишет payload, разобранный схемой; список —
  `jsonb`. `sites` зеркала не имеет: сопоставлен с `public.sites` через явный список общих полей
  (`public_sync/mapping.py:274-315`), новые поля объекта обмен не затрагивают.

**Данные и сид**

- `cost/v2/db_repository.py:369-372` — умолчания создаются только у организации без ревизий; `importDraft.ts:11-23`
  заменяет раздел целиком. Поэтому данные на проде дописывает функция поверх снимка (Т10), как
  `cost/v2/crew_defaults.py:79-128` + `scripts/reclassify_positions.py`.
- `cost/model/labor.py:392-410` — ставка выбирается «должность + условие → должность без условия → первая
  попавшаяся». Новая ставка без условия у должности, где были только ставки по условиям, сменила бы выбор в расчёте —
  сид таких ставок не заводит.
- Импорт Cost V1 заводит должности `POSITION_LABOR_*` косвенными (`tests/test_crew_defaults.py:13-40`);
  `hardness_f` у пород не приносит (`cost/v2/import_v1.py:107-121`).
- Файл владельца: лист «Список должностей и формы премирования» — 14 должностей по четырём участкам с системой
  оплаты; лист «Постоянная часть» — параметры машиниста (класс 3.2, вредность 4 %, доп. отпуск 7 дн, ночные 60 ч =
  15 × 8 × 0,5, вахта 15/15, дорога 2 дн, РК 0,15, МРОТ 27 093, 1 972 ч, 247 и 14 дн); «Годовая норма часов» —
  1 774,4 ч при 36-часовой неделе; «Переменная часть» — объект «Ломовское месторождение», пороги 1 500/1 800/2 400.

**Числа, проверенные расчётом**

- γ = ln(168,66 / 45) / ln(184,6154 / 115,3846) = 2,811088 → в подсказке «2,811»; p(норма) = 45 × 115,3846 =
  5 192,31 ₽; p(потолок) = 12 000,05 ₽ (§7). Линейная кривая: p(потолок) = 12 588,23 ₽ = 163 647 / 13 (§7).
- k диаметра = Ø / 152 до 0,01: 110 → 0,72; 127 → 0,84; 140 → 0,92; 152 → 1,00; 165 → 1,09; 190 → 1,25;
  215 → 1,41; 250 → 1,64; 171 → 1,13.
- Т16: доля ТОиР — смен ТОиР на рабочую смену, поэтому из вахты 15 смен на ТОиР уходит 15 × 0,14 / 1,14 = 1,84
  (в §3 записано «0,14 × 13 = 1,84», но 0,14 × 13 = 1,82; формула уточняется в документе решений, Задача 8).

## Ответы владельца 14.09.2026

1. **Сид и существующие записи.** У существующих должностей и ставок сид заполняет только пустые ключи payload;
   заданные значения, наименование, категория и операция не меняются. §7 «существующие записи не меняет» читается
   как «заданные значения не меняет».
2. **Сопоставление должностей файла.** Машинист буровой установки = `POSITION_LABOR_DRILLER`, помощник =
   `POSITION_LABOR_ASSISTANT`, водитель-оператор СЗМ = `POSITION_LABOR_DRIVER_SZM`, взрывник =
   `POSITION_LABOR_BLASTERS`, мастер-взрывник = `POSITION_LABOR_MASTER`, горнорабочий = `POSITION_LABOR_MINER`,
   водитель ДОПОГ = `POSITION_LABOR_DRIVER_DEL`. Остальные семь — новые записи.
3. **`sites.shift_hours`** переносится в PR 3a вместе с резолвером Т8: поле, которое до PR 3a ничего не меняет, в
   PR 1 не заводится.

## Решения планировщика (в отчёт PR)

- **Коды перечислений** уникальны в словаре подписей: участок `DRILLING_BLASTING / TRANSPORT / WAREHOUSE /
  MAINTENANCE`; система оплаты `PIECE_PROGRESSIVE / PIECE_BONUS / TIME_BONUS` (по умолчанию `TIME_BONUS`); чья
  выработка `OWN_OUTPUT / SECTION_OUTPUT`; приведение `PLAIN / NORMALIZED_METERS` (в задаче `none / drilling` — эти
  коды заняты); шкала `CURVE_POWER / CURVE_LINEAR / STEP`; класс условий труда — строки `"1" … "4"`; неделя вручную —
  `"40" / "36"`. Поле участка названо `department`, а не `section`: «раздел» в коде — раздел справочника.
- **Единица выработки** — ссылка на `units` (м, т, м³, рейс уже есть); сид добавляет `KM`.
- **Умолчания объекта** — значения задачи (график компании): 15/15, дорога 2, доля ночных 0,5, ТОиР 2, РК 0,15,
  северная 0, договорной k 1. Запись, заведённая до PR 1, считается по ним.
- **Оклад** остаётся в `labor_rates.fixed_monthly_rub`; «пусто → МРОТ» — это «у должности нет ставки», его учтёт
  PR 2. Новым должностям сид ставок не заводит.
- **Доп. тариф** — список `extra_tariffs` в ставках организации, по умолчанию пустой; сид заполняет его ставками
  ст. 428 НК РФ. Позиция вредного класса без строки тарифа — предупреждение.
- **Шкала** — у кривой обязательны все четыре узла; поля кривой рядом со ступенями и ступени рядом с кривой —
  ошибка (переключение типа требует очистить чужие поля: одна шкала — одна форма).
- **Доли геологии** — сумма 1 с допуском 0,001 (три породы по 0,333).
- **Потолок выше нормы станка** — сравнивается с лучшей базовой строкой матрицы (без породы и карьера):
  `tech_speed × (shift_hours организации − unproductive)`, только для должностей с `NORMALIZED_METERS`.
  На нынешней матрице (12 м/ч) предупреждение горит — так и задумано до правки данных Т19.
- **Т16** проверяется для каждого действующего станка с `maintenance_ratio > 0`; ожидаемое ТОиР —
  `shift_days_on × r / (1 + r)`, допуск 0,5 смены.
- **Коронка без диаметра** при заполненной таблице диаметров — предупреждение на материале, не ошибка.
- **Новые должности сида** — косвенные, без операции: в смету блока они попадут, только когда человек
  классифицирует их и включит в бригаду.
- **Флаги и даты в строках списков** в форму не добавляются (в PR 1 их нет); защитный тест требует доработать форму
  раньше, чем такое поле появится.
- **Подсказки кривой в форме** (Т6) входят в PR 1: γ и премия за смену на норме и потолке. График — только в
  `PayrollBreakdown` (PR 3b).
- **Ломовское месторождение** сид не трогает: умолчания объекта уже равны значениям файла, а долей пород в файле нет.

## Глобальные ограничения

- Поля payload — только схемы `cost/v2/schemas/`: подпись — `title`, пояснение — `description`, единица — `x-unit`
  (у безразмерного — `""`), ссылка — `x-ref`. Новый раздел — схема + `SECTION_SCHEMAS` + `REFERENCE_SECTION_DEFINITIONS`.
- Интерфейс не хранит знаний о полях: разделоспецифичных компонентов нет, JSON пользователю не показывается.
- Нормы — только в `cost/model/`, цены — только в справочниках. PR 1 не меняет ни одного модуля `cost/model/`.
- Раздел `staff` и поле `f` у пород не заводятся (Т3, Т7); ставки взносов и НДФЛ в `payroll_params` не кладутся (Т2).
- Проверяется весь черновик: пустой новый раздел — предупреждение, ошибка — только в заполненных данных (Т15).
- Сид не перезаписывает заданные значения, не заводит ставок без условия бурения и идемпотентен.
- Все суммы и доли — `Decimal`; в тестах — точное сравнение значений.
- Python — `.venv/bin/python -m pytest …`; фронт — `cd frontend && npx vitest run …`, `npx tsc -b`. В worktree
  `.venv` и `frontend/node_modules` — симлинки на основной чекаут.
- iCloud-дубли (`* 2.py`, `* 3.ts`) не трогать и не коммитить; `git add` — только перечисленных файлов.
- Сообщения коммитов — по-русски, последняя строка `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`.

## Файлы

- Изменить: `cost/v2/schemas/base.py` — `field_error` принимает путь.
- Изменить: `cost/v2/schemas/labor.py` — нормы оплаты должности, `ScaleTier`, шкала и КПЭ ставки, константы классов.
- Изменить: `cost/v2/schemas/organization.py` — `GeologyShare`, `ExtraTariff`, поля вахты объекта, `extra_tariffs`.
- Изменить: `cost/v2/schemas/misc.py` — `RockPayload`: f ≤ 0 — ошибка.
- Создать: `cost/v2/schemas/payroll.py` — `PayrollParamsPayload`, `DrillingDifficultyPayload`, `DowntimeReasonPayload`.
- Изменить: `cost/v2/schemas/__init__.py` — реестр и группы полей.
- Изменить: `cost/v2/references.py` — три раздела, колонки, вызов перекрёстных проверок.
- Создать: `cost/v2/payroll_checks.py` — проверки по нескольким разделам.
- Создать: `cost/v2/payroll_defaults.py` — сид.
- Создать: `scripts/seed_payroll_references.py` — сухой прогон и публикация сида.
- Изменить: `frontend/src/pages/references/enumLabels.ts`; создать `enumLabels.test.ts`.
- Изменить: `frontend/src/lib/referenceDerived.ts`, `referenceDerived.test.ts`.
- Тесты: изменить `tests/test_reference_schemas.py`, `tests/test_reference_files.py`,
  `tests/test_public_sync_mirror.py`; создать
  `tests/test_payroll_schemas.py`, `tests/test_payroll_checks.py`, `tests/test_payroll_defaults.py`,
  `tests/test_api_payroll_references.py`.
- Документы: `Docs/REFERENCES_MODEL.md`, `Docs/specs/2026-09-13-task-010-payroll-decisions.md`.

---

### Задача 0: рабочее дерево

Ветка, worktree и коммит плана готовятся в чате планирования.

- [ ] **Шаг 1: проверить ветку и окружение**

```bash
git -C .claude/worktrees/task-010-pr1 branch --show-current
ls -l .claude/worktrees/task-010-pr1/.venv .claude/worktrees/task-010-pr1/frontend/node_modules
```

Expected: `feat/task-010-pr1-references`; обе ссылки ведут в `/Users/apple/Documents/Проекты/BlastEX/…`. Дальше все
команды — из корня worktree.

- [ ] **Шаг 2: базовый прогон**

Run: `.venv/bin/python -m pytest tests -q`
Expected: 1375 passed, 32 skipped.

---

### Задача 1: путь ошибки внутри строки и защитный тест формы

**Файлы:**
- Изменить: `cost/v2/schemas/base.py:10-11`, `:97-116`
- Тест: `tests/test_reference_schemas.py`

**Интерфейсы:**
- Даёт: `field_error(model, field: str | Sequence[str | int], message, value=None) -> NoReturn`. Кортеж
  `("tiers", 1, "rate")` становится `ValidationIssue.field == "tiers.1.rate"` (`references.py:423`). Задачи 2–4
  опираются на это.

- [ ] **Шаг 1: падающие тесты**

В `tests/test_reference_schemas.py` дополнить импорты:

```python
from pydantic import ValidationError, model_validator

from cost.v2.schemas.base import ReferencePayload, field_error
```

(строку `from pydantic import ValidationError` заменить этой). После `_field_containers` добавить:

```python
class _ProbeRow(ReferencePayload):
    rate: int = 0


class _Probe(ReferencePayload):
    rows: list[_ProbeRow] = []

    @model_validator(mode="after")
    def _second_row_is_wrong(self) -> "_Probe":
        if len(self.rows) > 1:
            field_error(type(self), ("rows", 1, "rate"), "Ошибка во второй строке", self.rows[1].rate)
        return self


class TestFieldErrorPath:
    def test_error_inside_a_list_row_keeps_the_row_path(self):
        with pytest.raises(ValidationError) as exc:
            _Probe.model_validate({"rows": [{}, {"rate": 5}]})
        error = exc.value.errors()[0]
        assert (error["loc"], error["msg"]) == (("rows", 1, "rate"), "Ошибка во второй строке")

    def test_plain_field_name_still_works(self):
        with pytest.raises(ValidationError) as exc:
            field_error(_Probe, "rows", "Ошибка поля")
        assert exc.value.errors()[0]["loc"] == ("rows",)


def _variants(node: dict) -> list[dict]:
    return [variant for variant in (node.get("anyOf") or [node]) if isinstance(variant, dict)]
```

В класс `TestRegistry` добавить:

```python
    def test_forms_get_only_flat_fields_and_lists_of_flat_rows(self):
        """Форма справочника рисует плоские поля и списки плоских строк.

        Вложенный объект она превратила бы в строку «[object Object]», а флаг
        или дату в строке списка — в текстовое поле (открытые вопросы после
        TASK-010 PR 0). Новая схема с такими полями сначала учит форму.
        """

        problems: list[str] = []
        for section in SECTION_SCHEMAS:
            schema = section_json_schema(section)
            for name, node in (schema.get("properties") or {}).items():
                if any("$ref" in variant for variant in _variants(node)):
                    problems.append(f"{section}.{name}: вложенный объект")
            for model_name, model in (schema.get("$defs") or {}).items():
                for name, node in (model.get("properties") or {}).items():
                    if node.get("x-internal"):
                        continue
                    if any(
                        variant.get("type") in {"array", "object", "boolean"}
                        or "$ref" in variant
                        or variant.get("format") == "date"
                        for variant in _variants(node)
                    ):
                        problems.append(f"{section}.{model_name}.{name}: подполе строки списка")
        assert problems == []
```

- [ ] **Шаг 2: убедиться, что падает**

Run: `.venv/bin/python -m pytest tests/test_reference_schemas.py -q`
Expected: FAIL в `test_error_inside_a_list_row_keeps_the_row_path` — `loc` получается одной строкой
`("('rows', 1, 'rate')",)`; защитный тест проходит (на `main` таких полей нет).

- [ ] **Шаг 3: реализация**

`cost/v2/schemas/base.py`: `from typing import Any, NoReturn` → `from typing import Any, NoReturn, Sequence`;
функцию заменить на

```python
def field_error(
    model: type[BaseModel],
    field: str | Sequence[str | int],
    message: str,
    value: Any = None,
) -> NoReturn:
    """Ошибка перекрёстной проверки, привязанная к полю.

    `raise ValueError` в `model_validator` даёт ошибку без имени поля, и
    интерфейс показывает её общим списком над формой. Сметчику нужно видеть
    ошибку под тем полем, которое он забыл заполнить, поэтому собираем ошибку
    с явным `loc`. Путь внутрь списка — кортеж `("tiers", 1, "rate")`: форма
    покажет ошибку под подполем нужной строки.
    """

    loc = (field,) if isinstance(field, str) else tuple(field)
    raise ValidationError.from_exception_data(
        model.__name__,
        [
            InitErrorDetails(
                # Текст подставляется через контекст: шаблон должен быть литералом.
                type=PydanticCustomError("value_error", "{message}", {"message": message}),
                loc=loc,
                input=value,
            )
        ],
    )
```

- [ ] **Шаг 4: прогон**

Run: `.venv/bin/python -m pytest tests/test_reference_schemas.py -q`
Expected: PASS.

- [ ] **Шаг 5: коммит**

```bash
git add cost/v2/schemas/base.py tests/test_reference_schemas.py
git commit -m "$(cat <<'EOF'
TASK-010 PR 1: ошибка схемы под подполем строки списка и защитный тест плоских форм

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
)"
```

---

### Задача 2: должности и ставки — нормы оплаты и плоская шкала

**Файлы:**
- Изменить: `cost/v2/schemas/labor.py` (весь модуль)
- Изменить: `cost/v2/schemas/__init__.py:71-81` — группы `positions`, `labor_rates`
- Изменить: `cost/v2/references.py:70-77` — колонки
- Тест: создать `tests/test_payroll_schemas.py`

**Интерфейсы:**
- Использует: `field_error` с путём (Задача 1), `RateField`, `RefField`, `UnitField`.
- Даёт: `WorkConditionsClass`, `WORK_CONDITIONS_CLASSES`, `HAZARDOUS_CLASSES = ("3.1", "3.2", "3.3", "3.4", "4")`,
  `CURVE_SCALES = ("CURVE_POWER", "CURVE_LINEAR")`, `ScaleTier`; поля `PositionPayload`: `department`, `pay_system`,
  `work_conditions_class`, `week_hours_override`, `hazard_pct`, `extra_vacation_days`, `night_hours_per_shift`,
  `output_unit`, `output_source`, `difficulty`; поля `LaborRatePayload`: `kpi_bonus_pct`, `scale_type`,
  `norm_per_shift`, `rate_norm`, `ceiling_per_shift`, `rate_ceiling`, `tiers`. Задачи 3, 5, 6, 7 опираются на эти
  имена и коды.

- [ ] **Шаг 1: падающие тесты**

Создать `tests/test_payroll_schemas.py`:

```python
"""Схемы справочников методики ФОТ (TASK-010 PR 1): поля, умолчания, правила записи."""
from __future__ import annotations

from decimal import Decimal

import pytest
from pydantic import ValidationError

from cost.v2.schemas import section_json_schema
from cost.v2.schemas.labor import LaborRatePayload, PositionPayload


def _error(exc: pytest.ExceptionInfo[ValidationError]) -> tuple[str, str]:
    error = exc.value.errors()[0]
    return ".".join(str(part) for part in error["loc"]), error["msg"]


CURVE = {
    "position_code": "POSITION_LABOR_DRILLER",
    "scale_type": "CURVE_POWER",
    "norm_per_shift": "115.3846",
    "rate_norm": "45",
    "ceiling_per_shift": "184.6154",
    "rate_ceiling": "168.66",
}
STEP = {
    "position_code": "POSITION_LABOR_DRIVER",
    "scale_type": "STEP",
    "tiers": [
        {"upto_per_shift": "115.3846", "rate": "45"},
        {"upto_per_shift": "138.4615", "rate": "75"},
        {"upto_per_shift": "184.6154", "rate": "110"},
        {"upto_per_shift": None, "rate": "140"},
    ],
}


class TestPositionNorms:
    def test_old_position_reads_with_neutral_defaults(self):
        position = PositionPayload.model_validate({"category": "INDIRECT"})
        assert position.pay_system == "TIME_BONUS"
        assert position.work_conditions_class is None
        assert position.week_hours_override is None
        assert position.hazard_pct == Decimal("0")
        assert position.difficulty == "PLAIN"
        assert position.output_source == "OWN_OUTPUT"

    def test_machinist_norms_from_the_owner_file(self):
        position = PositionPayload.model_validate({
            "category": "DIRECT",
            "operation_code": "PRODUCTION_DRILLING",
            "department": "DRILLING_BLASTING",
            "pay_system": "PIECE_PROGRESSIVE",
            "work_conditions_class": "3.2",
            "hazard_pct": "0.04",
            "extra_vacation_days": "7",
            "night_hours_per_shift": "8",
            "output_unit": "M",
            "difficulty": "NORMALIZED_METERS",
        })
        assert position.work_conditions_class == "3.2"
        assert position.night_hours_per_shift == Decimal("8")

    def test_week_override_is_36_or_40_only(self):
        with pytest.raises(ValidationError):
            PositionPayload.model_validate({"category": "INDIRECT", "week_hours_override": "35"})

    def test_labels_and_units_reach_the_form(self):
        properties = section_json_schema("positions")["properties"]
        assert properties["work_conditions_class"]["title"] == "Класс условий труда"
        assert properties["extra_vacation_days"]["x-unit"] == "дн"
        assert properties["output_unit"]["x-ref"] == "units"


class TestLaborRateScale:
    def test_rate_without_a_scale_stays_valid(self):
        rate = LaborRatePayload.model_validate({"position_code": "P", "fixed_monthly_rub": "60000", "piece_rate_rub": "150"})
        assert rate.scale_type is None
        assert rate.tiers == []
        assert rate.kpi_bonus_pct == Decimal("0")

    def test_power_curve_of_the_machinist(self):
        rate = LaborRatePayload.model_validate(CURVE)
        assert rate.ceiling_per_shift == Decimal("184.6154")

    def test_curve_fields_without_a_scale_type_are_rejected(self):
        with pytest.raises(ValidationError) as exc:
            LaborRatePayload.model_validate({**CURVE, "scale_type": None})
        assert _error(exc) == ("norm_per_shift", "Поле заполняется только вместе с типом шкалы сдельной премии")

    def test_scale_with_a_drilling_condition_is_rejected(self):
        with pytest.raises(ValidationError) as exc:
            LaborRatePayload.model_validate({**CURVE, "condition_code": "COND_GRANITE"})
        assert _error(exc) == (
            "condition_code",
            "Шкала сдельной премии задаётся ставкой без условия бурения: породу учитывают приведённые метры",
        )

    @pytest.mark.parametrize(
        ("patch", "expected"),
        [
            ({"rate_ceiling": None}, ("rate_ceiling", "Для кривой нужны норма, потолок и обе расценки")),
            ({"ceiling_per_shift": "115.3846"}, ("ceiling_per_shift", "Потолок должен быть выше нормы")),
            ({"rate_ceiling": "40"}, ("rate_ceiling", "Расценка на потолке не может быть ниже расценки на норме")),
            ({"rate_norm": "0"}, ("rate_norm", "Расценка на норме должна быть больше нуля")),
            ({"tiers": [{"rate": "45"}]}, ("tiers", "У кривой ступени не заполняются")),
        ],
    )
    def test_broken_curve_is_reported_under_its_field(self, patch, expected):
        with pytest.raises(ValidationError) as exc:
            LaborRatePayload.model_validate({**CURVE, **patch})
        assert _error(exc) == expected

    def test_equal_rates_make_a_flat_curve(self):
        assert LaborRatePayload.model_validate({**CURVE, "rate_ceiling": "45"}).rate_ceiling == Decimal("45")

    def test_step_scale_with_the_owner_tiers(self):
        rate = LaborRatePayload.model_validate(STEP)
        assert [tier.rate for tier in rate.tiers] == [Decimal("45"), Decimal("75"), Decimal("110"), Decimal("140")]
        assert LaborRatePayload.model_validate({**STEP, "tiers": [{"rate": "45"}]}).tiers[0].upto_per_shift is None

    @pytest.mark.parametrize(
        ("tiers", "expected"),
        [
            ([], ("tiers", "Для шкалы «Ступени» нужна хотя бы одна ступень")),
            (
                [{"upto_per_shift": "0", "rate": "45"}, {"rate": "75"}],
                ("tiers.0.upto_per_shift", "Граница первой ступени должна быть больше нуля"),
            ),
            (
                [{"upto_per_shift": None, "rate": "45"}, {"rate": "75"}],
                ("tiers.0.upto_per_shift", "Верхняя граница не задаётся только у последней ступени"),
            ),
            (
                [{"upto_per_shift": "115", "rate": "45"}, {"upto_per_shift": "200", "rate": "75"}],
                ("tiers.1.upto_per_shift", "У последней ступени верхней границы нет: выше неё действует её расценка"),
            ),
            (
                [{"upto_per_shift": "115", "rate": "45"}, {"upto_per_shift": "100", "rate": "75"}, {"rate": "140"}],
                ("tiers.1.upto_per_shift", "Границы ступеней должны возрастать"),
            ),
            (
                [{"upto_per_shift": "115", "rate": "45"}, {"upto_per_shift": "138", "rate": "40"}, {"rate": "140"}],
                ("tiers.1.rate", "Расценка ступени не может быть ниже предыдущей"),
            ),
        ],
    )
    def test_broken_tiers_are_reported_under_the_row(self, tiers, expected):
        with pytest.raises(ValidationError) as exc:
            LaborRatePayload.model_validate({**STEP, "tiers": tiers})
        assert _error(exc) == expected

    def test_step_scale_rejects_curve_fields(self):
        with pytest.raises(ValidationError) as exc:
            LaborRatePayload.model_validate({**STEP, "norm_per_shift": "115"})
        assert _error(exc) == ("norm_per_shift", "У шкалы «Ступени» поля кривой не заполняются")
```

- [ ] **Шаг 2: убедиться, что падает**

Run: `.venv/bin/python -m pytest tests/test_payroll_schemas.py -q`
Expected: FAIL — `AttributeError: 'PositionPayload' object has no attribute 'pay_system'`, «extra_forbidden» для
`scale_type`.

- [ ] **Шаг 3: реализация**

`cost/v2/schemas/labor.py` заменить целиком:

```python
"""Схемы разделов «Персонал»: должности, ставки, составы бригад."""
from __future__ import annotations

from decimal import Decimal
from typing import Literal

from pydantic import Field, model_validator

from cost.v2.schemas.base import RateField, RefField, ReferencePayload, UnitField, field_error

__all__ = [
    "PositionPayload",
    "LaborRatePayload",
    "CrewTemplatePayload",
    "ScaleTier",
    "WorkConditionsClass",
    "PIECE_DRIVERS",
    "WORK_CONDITIONS_CLASSES",
    "HAZARDOUS_CLASSES",
    "CURVE_SCALES",
]

PieceDriver = Literal["rock_volume_m3", "explosive_kg", "drilling_m", "holes"]
PIECE_DRIVERS: tuple[str, ...] = ("rock_volume_m3", "explosive_kg", "drilling_m", "holes")

WorkConditionsClass = Literal["1", "2", "3.1", "3.2", "3.3", "3.4", "4"]
WORK_CONDITIONS_CLASSES: tuple[str, ...] = ("1", "2", "3.1", "3.2", "3.3", "3.4", "4")
# Классы, за которые платится дополнительный тариф взносов (ст. 428 НК РФ):
# у оптимального и допустимого классов его нет.
HAZARDOUS_CLASSES: tuple[str, ...] = ("3.1", "3.2", "3.3", "3.4", "4")

ScaleType = Literal["CURVE_POWER", "CURVE_LINEAR", "STEP"]
CURVE_SCALES: tuple[str, ...] = ("CURVE_POWER", "CURVE_LINEAR")
_CURVE_FIELDS: tuple[str, ...] = ("norm_per_shift", "rate_norm", "ceiling_per_shift", "rate_ceiling")


class PositionPayload(ReferencePayload):
    category: Literal["DIRECT", "INDIRECT"] = Field(
        default="DIRECT", title="Категория", description="Прямой персонал блока или косвенный персонал юнита"
    )
    operation_code: str | None = RefField(
        "operations",
        title="Операция пакета",
        description="Операция пакета, к которой привязан норматив (только для прямого персонала)",
        default=None,
    )
    norm_shifts_per_month: Decimal = UnitField(
        "см/мес", description="Нормативных смен в месяц", default=Decimal("21")
    )
    norm_operations_per_month: Decimal | None = UnitField(
        "оп/мес", description="Нормативных операций (взрывов, зарядок) в месяц", default=None
    )
    piece_driver: PieceDriver | None = Field(
        default=None, description="Драйвер сдельной оплаты"
    )
    piece_unit: Decimal = UnitField(
        "ед.", title="За единиц драйвера", description="Расценка задаётся за столько единиц драйвера", default=Decimal("1"), ge=0
    )
    per_diem_applies: bool = Field(default=True, title="Суточные и проживание", description="Начисляются суточные и проживание")
    # Методика ФОТ (TASK-010): нормы должности. Деньги — оклад, шкала, КПЭ —
    # живут в «Ставках персонала».
    department: Literal["DRILLING_BLASTING", "TRANSPORT", "WAREHOUSE", "MAINTENANCE"] | None = Field(
        default=None,
        title="Участок",
        description="Участок штатного расписания: буровзрывной, транспорт и спецтехника, склад и производство, техобслуживание",
    )
    pay_system: Literal["PIECE_PROGRESSIVE", "PIECE_BONUS", "TIME_BONUS"] = Field(
        default="TIME_BONUS",
        title="Система оплаты",
        description=(
            "Сдельно-прогрессивная и сдельно-премиальная — премия по шкале ставки; "
            "повременно-премиальная — без сдельной премии"
        ),
    )
    work_conditions_class: WorkConditionsClass | None = Field(
        default=None,
        title="Класс условий труда",
        description="Класс по СОУТ: задаёт доп. тариф взносов, а 3.3, 3.4 и 4 — 36-часовую неделю (ст. 92 ТК РФ)",
    )
    week_hours_override: Literal["40", "36"] | None = Field(
        default=None,
        title="Рабочая неделя вручную",
        description="Пусто — неделя выводится из класса условий труда: 3.3, 3.4 и 4 — 36 ч, остальные — 40 ч",
    )
    hazard_pct: Decimal = RateField(
        title="Надбавка за вредность", description="Доля оклада", default=Decimal("0")
    )
    extra_vacation_days: Decimal = UnitField(
        "дн",
        title="Дополнительный отпуск",
        description="Дней дополнительного отпуска в год — база резерва",
        default=Decimal("0"),
        le=366,
    )
    night_hours_per_shift: Decimal = UnitField(
        "ч/см", title="Ночных часов в смене", description="Ночных часов в ночную смену", default=Decimal("0"), le=24
    )
    output_unit: str | None = RefField(
        "units",
        title="Единица выработки",
        description="В чём считается сдельная выработка: м, км, рейс, т, м³",
        default=None,
    )
    output_source: Literal["OWN_OUTPUT", "SECTION_OUTPUT"] = Field(
        default="OWN_OUTPUT",
        title="Чья выработка",
        description="Своя выработка или выработка участка (горнорабочий); в плане выработка участка — выработка юнита",
    )
    difficulty: Literal["PLAIN", "NORMALIZED_METERS"] = Field(
        default="PLAIN",
        title="Приведение выработки",
        description="Приведённые метры — метры бурения × коэффициенты крепости породы и диаметра коронки",
    )

    @model_validator(mode="after")
    def _direct_needs_operation(self) -> "PositionPayload":
        # Прямой персонал попадает в себестоимость блока через операцию пакета:
        # без неё модель не знает, к какому этапу отнести человеко-смены.
        if self.category == "DIRECT" and not self.operation_code:
            field_error(type(self), "operation_code", "У прямого персонала должна быть указана операция пакета")
        if self.category == "INDIRECT" and self.operation_code:
            field_error(
                type(self),
                "operation_code",
                "Косвенный персонал не привязывается к операции — он распределяется по объёму юнита",
                self.operation_code,
            )
        return self


class ScaleTier(ReferencePayload):
    upto_per_shift: Decimal | None = UnitField(
        "ед./см",
        title="До выработки за смену",
        description="Верхняя граница ступени; у последней ступени пусто",
        default=None,
    )
    rate: Decimal = UnitField(
        "₽/ед.", title="Расценка", description="Цена единицы выработки внутри ступени", default=Decimal("0")
    )


class LaborRatePayload(ReferencePayload):
    position_code: str = RefField("positions", description="Должность")
    fixed_monthly_rub: Decimal = UnitField(
        "₽/мес", description="Постоянная часть оплаты", default=Decimal("0")
    )
    piece_rate_rub: Decimal = UnitField(
        "₽",
        title="Сдельная расценка",
        description="Сдельная расценка за piece_unit единиц драйвера должности",
        default=Decimal("0"),
    )
    condition_code: str | None = RefField(
        "drilling_conditions",
        title="Условие бурения",
        description="Условие бурения, если расценка зависит от породы",
        default=None,
    )
    kpi_bonus_pct: Decimal = RateField(
        title="Премия КПЭ",
        description="Премия за ОРД и КПЭ при выполнении плана на 100 %, доля оклада",
        default=Decimal("0"),
    )
    # Шкала лежит плоско, а не вложенным объектом: форма справочника не умеет
    # вложенный объект, а объединение вариантов затёрла бы строкой (Т5).
    scale_type: ScaleType | None = Field(
        default=None,
        title="Шкала сдельной премии",
        description="Степенная или линейная кривая цены единицы между нормой и потолком либо ступени; пусто — шкалы нет",
    )
    norm_per_shift: Decimal | None = UnitField(
        "ед./см",
        title="Норма за смену",
        description=(
            "До нормы цена единицы равна расценке на норме. Норма и потолок — загрузка станка: "
            "метры на смену = скорость бурения × чистое время; у машиниста — приведённые метры при f 10 и Ø 152 мм"
        ),
        default=None,
    )
    rate_norm: Decimal | None = UnitField(
        "₽/ед.", title="Расценка на норме", description="Цена единицы выработки до нормы", default=None
    )
    ceiling_per_shift: Decimal | None = UnitField(
        "ед./см",
        title="Потолок за смену",
        description="Выработка, при которой станок бурит всю смену; выше потолка цена единицы постоянна",
        default=None,
    )
    rate_ceiling: Decimal | None = UnitField(
        "₽/ед.", title="Расценка на потолке", description="Цена единицы на потолке и выше", default=None
    )
    tiers: list[ScaleTier] = Field(
        default_factory=list,
        title="Ступени шкалы",
        description="Ступени по выработке за смену для шкалы «Ступени»; расценки не убывают",
    )

    @model_validator(mode="after")
    def _scale_is_consistent(self) -> "LaborRatePayload":
        if self.scale_type is None:
            for name in _CURVE_FIELDS:
                if getattr(self, name) is not None:
                    field_error(
                        type(self), name, "Поле заполняется только вместе с типом шкалы сдельной премии", getattr(self, name)
                    )
            if self.tiers:
                field_error(type(self), "tiers", "Ступени заполняются только у шкалы «Ступени»")
            return self
        if self.condition_code:
            # Коэффициент породы уже в приведённых метрах: расценка по условию
            # бурения учла бы породу второй раз (Т1).
            field_error(
                type(self),
                "condition_code",
                "Шкала сдельной премии задаётся ставкой без условия бурения: породу учитывают приведённые метры",
                self.condition_code,
            )
        if self.scale_type == "STEP":
            self._check_tiers()
        else:
            self._check_curve()
        return self

    def _check_curve(self) -> None:
        if self.tiers:
            field_error(type(self), "tiers", "У кривой ступени не заполняются")
        norm, rate_norm = self.norm_per_shift, self.rate_norm
        ceiling, rate_ceiling = self.ceiling_per_shift, self.rate_ceiling
        if norm is None or rate_norm is None or ceiling is None or rate_ceiling is None:
            missing = next(name for name in _CURVE_FIELDS if getattr(self, name) is None)
            field_error(type(self), missing, "Для кривой нужны норма, потолок и обе расценки")
        if norm <= 0:
            field_error(type(self), "norm_per_shift", "Норма должна быть больше нуля", norm)
        if ceiling <= norm:
            field_error(type(self), "ceiling_per_shift", "Потолок должен быть выше нормы", ceiling)
        if rate_norm <= 0:
            field_error(type(self), "rate_norm", "Расценка на норме должна быть больше нуля", rate_norm)
        if rate_ceiling < rate_norm:
            field_error(type(self), "rate_ceiling", "Расценка на потолке не может быть ниже расценки на норме", rate_ceiling)

    def _check_tiers(self) -> None:
        for name in _CURVE_FIELDS:
            if getattr(self, name) is not None:
                field_error(type(self), name, "У шкалы «Ступени» поля кривой не заполняются", getattr(self, name))
        if not self.tiers:
            field_error(type(self), "tiers", "Для шкалы «Ступени» нужна хотя бы одна ступень")
        last = len(self.tiers) - 1
        for index, tier in enumerate(self.tiers):
            where = ("tiers", index, "upto_per_shift")
            if index < last and tier.upto_per_shift is None:
                field_error(type(self), where, "Верхняя граница не задаётся только у последней ступени")
            if index == last and tier.upto_per_shift is not None:
                field_error(
                    type(self), where, "У последней ступени верхней границы нет: выше неё действует её расценка",
                    tier.upto_per_shift,
                )
            if index == 0:
                if tier.upto_per_shift is not None and tier.upto_per_shift <= 0:
                    field_error(type(self), where, "Граница первой ступени должна быть больше нуля", tier.upto_per_shift)
                continue
            previous = self.tiers[index - 1]
            # Граница предыдущей ступени задана: пустую отсекла проверка выше.
            if (
                previous.upto_per_shift is not None
                and tier.upto_per_shift is not None
                and tier.upto_per_shift <= previous.upto_per_shift
            ):
                field_error(type(self), where, "Границы ступеней должны возрастать", tier.upto_per_shift)
            if tier.rate < previous.rate:
                # Убывающая расценка ломает выпуклость: премия за смену перестала
                # бы расти ускоренно.
                field_error(
                    type(self), ("tiers", index, "rate"), "Расценка ступени не может быть ниже предыдущей", tier.rate
                )


class CrewMember(ReferencePayload):
    position_code: str = RefField("positions", description="Должность")
    headcount: Decimal = UnitField(
        "чел",
        title="Человек в смене",
        description="Сколько человек должности работает в одной смене; штат на ротацию модель выводит из плановых смен техники",
        default=Decimal("1"),
        ge=0,
    )


class CrewTemplatePayload(ReferencePayload):
    package_code: str = RefField("work_packages", description="Пакет работ")
    members: list[CrewMember] = Field(default_factory=list, description="Состав бригады")
```

`cost/v2/schemas/__init__.py`, группы `positions` и `labor_rates` (`:71-81`) заменить на:

```python
    "positions": (
        ("Роль", ("category", "department", "operation_code")),
        ("Нормативы", ("norm_shifts_per_month", "norm_operations_per_month")),
        ("Сдельная часть", ("piece_driver", "piece_unit")),
        ("Оплата труда", ("pay_system", "output_unit", "output_source", "difficulty")),
        ("Условия труда", (
            "work_conditions_class", "week_hours_override", "hazard_pct",
            "extra_vacation_days", "night_hours_per_shift",
        )),
        ("Прочее", ("per_diem_applies",)),
    ),
    "labor_rates": (
        ("Должность", ("position_code", "condition_code")),
        ("Постоянная часть", ("fixed_monthly_rub", "kpi_bonus_pct")),
        ("Сдельная часть", ("piece_rate_rub",)),
        ("Шкала сдельной премии", (
            "scale_type", "norm_per_shift", "rate_norm", "ceiling_per_shift", "rate_ceiling", "tiers",
        )),
    ),
```

`cost/v2/references.py`: колонки `positions` — `["name", "category", "operation_code", "pay_system",
"norm_shifts_per_month"]`; колонки `labor_rates` — `["name", "position_code", "fixed_monthly_rub",
"piece_rate_rub", "scale_type"]`.

- [ ] **Шаг 4: прогон**

Run: `.venv/bin/python -m pytest tests/test_payroll_schemas.py tests/test_reference_schemas.py tests/test_api_reference_schema.py tests/test_crew_defaults.py tests/test_model_labor.py -q`
Expected: PASS.

- [ ] **Шаг 5: коммит**

```bash
git add cost/v2/schemas/labor.py cost/v2/schemas/__init__.py cost/v2/references.py tests/test_payroll_schemas.py
git commit -m "$(cat <<'EOF'
TASK-010 PR 1: нормы оплаты должности и плоская шкала сдельной премии в ставке

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
)"
```

---

### Задача 3: объекты, ставки организации, крепость породы

**Файлы:**
- Изменить: `cost/v2/schemas/organization.py`
- Изменить: `cost/v2/schemas/misc.py:12-14`, `:76-85`
- Изменить: `cost/v2/schemas/__init__.py:82-89` (группа «Налоги и взносы»), `:107-114` (группы `sites`)
- Тест: `tests/test_payroll_schemas.py`

**Интерфейсы:**
- Использует: `WorkConditionsClass` (Задача 2), `field_error` с путём.
- Даёт: `GeologyShare{rock_code, share}`, `ExtraTariff{work_conditions_class, rate}`, `GEOLOGY_TOLERANCE`;
  поля `SitePayload`: `shift_days_on` 15, `shift_days_off` 15, `travel_days` 2, `night_shift_share` 0,5,
  `maintenance_shifts` 2, `regional_coefficient` 0,15, `northern_pct` 0, `contract_k` 1, `geology`;
  `OrganizationRatesPayload.extra_tariffs`. Задачи 5 и 6 читают `SitePayload.model_fields[...].default` и
  `extra_tariffs`.

- [ ] **Шаг 1: падающие тесты**

В `tests/test_payroll_schemas.py` дополнить импорты:

```python
from cost.v2.schemas.misc import RockPayload
from cost.v2.schemas.organization import OrganizationRatesPayload, SitePayload
```

и добавить в конец файла:

```python
class TestSitePayroll:
    def test_old_site_reads_with_the_company_schedule(self):
        site = SitePayload.model_validate({})
        assert (site.shift_days_on, site.shift_days_off, site.travel_days) == (Decimal("15"), Decimal("15"), Decimal("2"))
        assert site.maintenance_shifts == Decimal("2")
        assert site.night_shift_share == Decimal("0.5")
        assert site.regional_coefficient == Decimal("0.15")
        assert site.northern_pct == Decimal("0")
        assert site.contract_k == Decimal("1")
        assert site.geology == []
        # Длительность смены объекта заводится в PR 3a вместе с резолвером.
        assert "shift_hours" not in SitePayload.model_fields

    def test_geology_shares_sum_to_one_within_a_thousandth(self):
        thirds = [{"rock_code": code, "share": "0.333"} for code in ("R1", "R2", "R3")]
        assert len(SitePayload.model_validate({"geology": thirds}).geology) == 3
        with pytest.raises(ValidationError) as exc:
            SitePayload.model_validate({"geology": [{"rock_code": "R1", "share": "0.5"}, {"rock_code": "R2", "share": "0.4"}]})
        assert _error(exc) == ("geology", "Сумма долей пород — 0.9, а должна быть 1")

    def test_rock_is_listed_once(self):
        with pytest.raises(ValidationError) as exc:
            SitePayload.model_validate({"geology": [{"rock_code": "R1", "share": "0.5"}, {"rock_code": "R1", "share": "0.5"}]})
        assert _error(exc) == ("geology.1.rock_code", "Порода уже есть в плановой геологии")

    def test_maintenance_cannot_take_the_whole_rotation(self):
        with pytest.raises(ValidationError) as exc:
            SitePayload.model_validate({"shift_days_on": "2", "maintenance_shifts": "2"})
        assert _error(exc) == (
            "maintenance_shifts", "Плановое ТОиР не может занимать всю вахту: эффективных смен не останется"
        )

    def test_contract_factor_is_positive(self):
        with pytest.raises(ValidationError) as exc:
            SitePayload.model_validate({"contract_k": "0"})
        assert _error(exc) == ("contract_k", "Договорной коэффициент должен быть больше нуля")


class TestOrganizationTariffs:
    def test_extra_tariffs_default_to_empty_and_accept_the_law_table(self):
        assert OrganizationRatesPayload().extra_tariffs == []
        rates = OrganizationRatesPayload.model_validate(
            {"extra_tariffs": [{"work_conditions_class": "3.2", "rate": "0.04"}, {"work_conditions_class": "4", "rate": "0.08"}]}
        )
        assert rates.extra_tariffs[1].rate == Decimal("0.08")

    def test_class_is_listed_once(self):
        with pytest.raises(ValidationError) as exc:
            OrganizationRatesPayload.model_validate(
                {"extra_tariffs": [{"work_conditions_class": "3.2", "rate": "0.04"}, {"work_conditions_class": "3.2", "rate": "0.05"}]}
            )
        assert _error(exc) == ("extra_tariffs.1.work_conditions_class", "Класс условий труда уже есть в таблице")


class TestRockHardness:
    def test_empty_hardness_is_allowed(self):
        assert RockPayload.model_validate({}).hardness_f is None

    def test_zero_hardness_is_rejected(self):
        # Отрицательное значение отсекает ещё `ge=0` поля; нуль — только эта проверка.
        with pytest.raises(ValidationError) as exc:
            RockPayload.model_validate({"hardness_f": "0"})
        assert _error(exc) == (
            "hardness_f", "Крепость по Протодьяконову должна быть больше нуля; не знаете — оставьте поле пустым"
        )
```

- [ ] **Шаг 2: убедиться, что падает**

Run: `.venv/bin/python -m pytest tests/test_payroll_schemas.py -q`
Expected: FAIL — нет атрибута `shift_days_on`, «extra_forbidden» для `geology` и `extra_tariffs`, `hardness_f = 0`
проходит.

- [ ] **Шаг 3: реализация**

`cost/v2/schemas/organization.py`: шапку модуля до `class ProductionUnitPayload` заменить на

```python
"""Схемы разделов «Организация»: юниты, контрагенты, карьеры, ставки организации."""
from __future__ import annotations

from decimal import Decimal
from typing import Literal

from pydantic import Field, model_validator

from cost.v2.schemas.base import RUB, RateField, RefField, ReferencePayload, UnitField, field_error
from cost.v2.schemas.labor import WorkConditionsClass

__all__ = [
    "ProductionUnitPayload",
    "CounterpartyPayload",
    "SitePayload",
    "OrganizationRatesPayload",
    "GeologyShare",
    "ExtraTariff",
    "GEOLOGY_TOLERANCE",
]

# Доли вида 1/3 точной десятичной записи не имеют: сумма 0,333 × 3 = 0,999
# должна проходить.
GEOLOGY_TOLERANCE = Decimal("0.001")


class GeologyShare(ReferencePayload):
    rock_code: str = RefField("rocks", title="Порода", description="Порода объекта")
    share: Decimal = RateField(title="Доля", description="Доля породы в плановом объёме бурения", default=Decimal("0"))


class ExtraTariff(ReferencePayload):
    work_conditions_class: WorkConditionsClass = Field(title="Класс условий труда", description="Класс по СОУТ")
    rate: Decimal = RateField(
        title="Доп. тариф", description="Дополнительный тариф страховых взносов", default=Decimal("0")
    )
```

В `SitePayload` после поля `is_remote` добавить:

```python
    # Вахта и оплата труда (TASK-010). Умолчания — график компании 15/15:
    # запись, заведённая до появления полей, считается по нему.
    shift_days_on: Decimal = UnitField(
        "дн", title="Дней вахты", description="Рабочих дней за вахту, включая плановое ТОиР", default=Decimal("15")
    )
    shift_days_off: Decimal = UnitField(
        "дн", title="Дней межвахты", description="Дней межвахтового отдыха", default=Decimal("15")
    )
    travel_days: Decimal = UnitField(
        "дн", title="Дней в дороге", description="Дней в пути на вахту и обратно", default=Decimal("2")
    )
    night_shift_share: Decimal = RateField(
        title="Доля ночных смен", description="Доля смен вахты, приходящихся на ночь", default=Decimal("0.5")
    )
    maintenance_shifts: Decimal = UnitField(
        "см",
        title="Плановое ТОиР за вахту",
        description="Смен вахты, которые уходят на плановое ТОиР станка",
        default=Decimal("2"),
    )
    regional_coefficient: Decimal = RateField(
        title="Районный коэффициент", description="Надбавка к начислениям: 0,15 — коэффициент 1,15", default=Decimal("0.15")
    )
    northern_pct: Decimal = RateField(
        title="Северная надбавка", description="Процентная надбавка за стаж в районах Крайнего Севера, доля", default=Decimal("0")
    )
    contract_k: Decimal = UnitField(
        "", title="Договорной коэффициент", description="Множитель приведённых метров по договору объекта", default=Decimal("1")
    )
    geology: list[GeologyShare] = Field(
        default_factory=list,
        title="Плановая геология",
        description="Доли пород объекта — запасной путь, когда у блоков нет паспортов; сумма долей равна 1",
    )

    @model_validator(mode="after")
    def _payroll_fields_are_consistent(self) -> "SitePayload":
        if self.maintenance_shifts >= self.shift_days_on:
            field_error(
                type(self),
                "maintenance_shifts",
                "Плановое ТОиР не может занимать всю вахту: эффективных смен не останется",
                self.maintenance_shifts,
            )
        if self.contract_k <= 0:
            field_error(type(self), "contract_k", "Договорной коэффициент должен быть больше нуля", self.contract_k)
        rocks: set[str] = set()
        for index, row in enumerate(self.geology):
            if row.rock_code in rocks:
                field_error(type(self), ("geology", index, "rock_code"), "Порода уже есть в плановой геологии", row.rock_code)
            rocks.add(row.rock_code)
        total = sum((row.share for row in self.geology), Decimal("0"))
        if self.geology and abs(total - 1) > GEOLOGY_TOLERANCE:
            field_error(type(self), "geology", f"Сумма долей пород — {total}, а должна быть 1", total)
        return self
```

В `OrganizationRatesPayload` после `shift_hours` добавить:

```python
    extra_tariffs: list[ExtraTariff] = Field(
        default_factory=list,
        title="Доп. тариф по классам условий труда",
        description="Дополнительный тариф взносов по классу условий труда (ст. 428 НК РФ); у классов 1 и 2 его нет",
    )

    @model_validator(mode="after")
    def _one_tariff_per_class(self) -> "OrganizationRatesPayload":
        seen: set[str] = set()
        for index, tariff in enumerate(self.extra_tariffs):
            if tariff.work_conditions_class in seen:
                field_error(
                    type(self),
                    ("extra_tariffs", index, "work_conditions_class"),
                    "Класс условий труда уже есть в таблице",
                    tariff.work_conditions_class,
                )
            seen.add(tariff.work_conditions_class)
        return self
```

`cost/v2/schemas/misc.py`: импорты `from pydantic import Field, model_validator` и
`from cost.v2.schemas.base import RefField, ReferencePayload, UnitField, field_error`; в `RockPayload` после
`fissuring_ff`:

```python
    @model_validator(mode="after")
    def _hardness_is_positive(self) -> "RockPayload":
        # Нуль — не «мягкая порода», а незаполненное поле: коэффициент
        # крепости для него не выбрать (решение владельца 13.09.2026).
        if self.hardness_f is not None and self.hardness_f <= 0:
            field_error(
                type(self),
                "hardness_f",
                "Крепость по Протодьяконову должна быть больше нуля; не знаете — оставьте поле пустым",
                self.hardness_f,
            )
        return self
```

`cost/v2/schemas/__init__.py`: в группе «Налоги и взносы» `organization_rates` после `"salary_basis"` добавить
`"extra_tariffs"`; в группах `sites` после «Условия» добавить:

```python
        ("Вахта и оплата труда", (
            "shift_days_on", "shift_days_off", "travel_days", "night_shift_share", "maintenance_shifts",
            "regional_coefficient", "northern_pct", "contract_k",
        )),
        ("Геология", ("geology",)),
```

- [ ] **Шаг 4: прогон**

Run: `.venv/bin/python -m pytest tests/test_payroll_schemas.py tests/test_reference_schemas.py tests/test_api_reference_schema.py tests/test_public_sync_mapping.py tests/test_public_sync_delta.py tests/test_legacy_adapter_roundtrip.py -q`
Expected: PASS.

- [ ] **Шаг 5: коммит**

```bash
git add cost/v2/schemas/organization.py cost/v2/schemas/misc.py cost/v2/schemas/__init__.py tests/test_payroll_schemas.py
git commit -m "$(cat <<'EOF'
TASK-010 PR 1: вахта и геология объекта, доп. тариф взносов, крепость породы больше нуля

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
)"
```

---

### Задача 4: разделы параметров года, сложности бурения и простоев

**Файлы:**
- Создать: `cost/v2/schemas/payroll.py`
- Изменить: `cost/v2/schemas/__init__.py` — импорт, `SECTION_FIELDSETS["payroll_params"]`, `SECTION_SCHEMAS`
- Изменить: `cost/v2/references.py:78`, `:101-105` — три раздела
- Тест: `tests/test_payroll_schemas.py`, `tests/test_reference_files.py`, создать `tests/test_api_payroll_references.py`

**Интерфейсы:**
- Даёт разделы `payroll_params` (`PayrollParamsPayload`: `year`, `mrot`, `annual_hours_40`, `annual_hours_36`,
  `work_days_year`, `holidays_year`, `night_pct`, `vacation_days_base`, `margin_share_warn`), `drilling_difficulty`
  (`hardness [{f_from, f_to, k}]`, `diameter [{diameter_mm, k}]`), `downtime_reasons` (`excusable`,
  `planned_maintenance`). Задачи 5 и 6 читают эти ключи.

- [ ] **Шаг 1: падающие тесты**

В `tests/test_payroll_schemas.py` добавить импорт
`from cost.v2.schemas.payroll import DowntimeReasonPayload, DrillingDifficultyPayload, PayrollParamsPayload` и в
конец файла:

```python
PARAMS = {
    "year": "2026",
    "mrot": "27093",
    "annual_hours_40": "1972",
    "annual_hours_36": "1774.4",
    "work_days_year": "247",
    "holidays_year": "14",
}


class TestPayrollParams:
    def test_year_2026_from_the_owner_file(self):
        params = PayrollParamsPayload.model_validate(PARAMS)
        assert params.year == 2026
        assert params.night_pct == Decimal("0.20")
        assert params.vacation_days_base == Decimal("28")
        assert params.margin_share_warn == Decimal("0.70")

    def test_calendar_fields_are_required(self):
        with pytest.raises(ValidationError) as exc:
            PayrollParamsPayload.model_validate({"year": "2026"})
        assert {error["loc"][0] for error in exc.value.errors()} == {
            "mrot", "annual_hours_40", "annual_hours_36", "work_days_year", "holidays_year",
        }

    def test_36_hour_norm_is_not_above_40_hour_norm(self):
        with pytest.raises(ValidationError) as exc:
            PayrollParamsPayload.model_validate({**PARAMS, "annual_hours_36": "2000"})
        assert _error(exc) == (
            "annual_hours_36", "Норма при 36-часовой неделе больше нуля и не больше нормы при 40-часовой"
        )


HARDNESS = [
    {"f_from": None, "f_to": "8", "k": "0.9"},
    {"f_from": "8", "f_to": "12", "k": "1.0"},
    {"f_from": "12", "f_to": "16", "k": "1.1"},
    {"f_from": "16", "f_to": "18", "k": "1.2"},
    {"f_from": "18", "f_to": None, "k": "1.3"},
]


class TestDrillingDifficulty:
    def test_owner_tables_are_valid(self):
        difficulty = DrillingDifficultyPayload.model_validate(
            {"hardness": HARDNESS, "diameter": [{"diameter_mm": "152", "k": "1.00"}, {"diameter_mm": "250", "k": "1.64"}]}
        )
        assert difficulty.hardness[3].k == Decimal("1.2")

    @pytest.mark.parametrize(
        ("rows", "expected"),
        [
            (
                [{"f_from": "0", "f_to": "8", "k": "0.9"}, {"f_from": "8", "f_to": None, "k": "1"}],
                ("hardness.0.f_from", "У первой строки нижней границы нет: она охватывает всю крепость до верхней границы"),
            ),
            (
                [{"f_from": None, "f_to": "8", "k": "0.9"}, {"f_from": "8", "f_to": "20", "k": "1"}],
                ("hardness.1.f_to", "У последней строки верхней границы нет: крепость выше шкалы берёт её коэффициент"),
            ),
            (
                [{"f_from": None, "f_to": "8", "k": "0.9"}, {"f_from": "9", "f_to": None, "k": "1"}],
                (
                    "hardness.1.f_from",
                    "Интервалы крепости идут без разрыва: нижняя граница равна верхней границе предыдущей строки (8)",
                ),
            ),
            (
                [{"f_from": None, "f_to": "8", "k": "0"}],
                ("hardness.0.k", "Коэффициент должен быть больше нуля"),
            ),
        ],
    )
    def test_broken_hardness_table_is_reported_under_the_row(self, rows, expected):
        with pytest.raises(ValidationError) as exc:
            DrillingDifficultyPayload.model_validate({"hardness": rows})
        assert _error(exc) == expected

    def test_diameter_is_listed_once(self):
        with pytest.raises(ValidationError) as exc:
            DrillingDifficultyPayload.model_validate(
                {"diameter": [{"diameter_mm": "152", "k": "1"}, {"diameter_mm": "152.0", "k": "1"}]}
            )
        assert _error(exc) == ("diameter.1.diameter_mm", "Диаметр уже есть в таблице")


class TestDowntimeReasons:
    def test_planned_maintenance_is_excusable(self):
        assert DowntimeReasonPayload.model_validate({"excusable": True, "planned_maintenance": True}).planned_maintenance
        with pytest.raises(ValidationError) as exc:
            DowntimeReasonPayload.model_validate({"planned_maintenance": True})
        assert _error(exc) == (
            "planned_maintenance", "Плановое ТОиР — простой не по вине машиниста: отметьте оба признака"
        )
```

В конец `tests/test_reference_files.py` добавить:

```python
class TestPayrollSectionsRoundTrip:
    """Списки шкалы, крепости и диаметров переживают круг «файл → черновик» (TASK-010 PR 1)."""

    RATES = (
        ReferenceItem(
            code="RATE_CURVE",
            name="Машинист",
            payload={
                "position_code": "POSITION_LABOR_DRILLER",
                "scale_type": "CURVE_POWER",
                "norm_per_shift": "115.3846",
                "rate_norm": "45",
                "ceiling_per_shift": "184.6154",
                "rate_ceiling": "168.66",
                "kpi_bonus_pct": "0.10",
            },
        ),
        ReferenceItem(
            code="RATE_STEP",
            name="Водитель",
            payload={
                "position_code": "POSITION_LABOR_DRIVER",
                "scale_type": "STEP",
                "tiers": [
                    {"upto_per_shift": "115.3846", "rate": "45"},
                    {"upto_per_shift": "138.4615", "rate": "75"},
                    {"upto_per_shift": None, "rate": "140"},
                ],
            },
        ),
    )
    DIFFICULTY = ReferenceItem(
        code="DRILLING_DIFFICULTY_BASE",
        name="Сложность бурения",
        payload={
            "hardness": [{"f_from": None, "f_to": "8", "k": "0.9"}, {"f_from": "8", "f_to": None, "k": "1.0"}],
            "diameter": [{"diameter_mm": "152", "k": "1.00"}, {"diameter_mm": "250", "k": "1.64"}],
        },
    )

    def test_xlsx_round_trip_keeps_curve_and_step_scales(self):
        from cost.v2.reference_files import export_xlsx, import_xlsx

        snapshot = _snapshot(labor_rates=self.RATES, drilling_difficulty=(self.DIFFICULTY,))
        imported = import_xlsx(export_xlsx(snapshot))

        for section, originals in (("labor_rates", self.RATES), ("drilling_difficulty", (self.DIFFICULTY,))):
            model = SECTION_SCHEMAS[section]
            back = {item.code: item.payload for item in imported[section]}
            for item in originals:
                # Число из ячейки возвращается без хвостовых нулей («0.10» → «0.1»):
                # сравниваем разобранные схемой значения, а не строки.
                assert model.model_validate(back[item.code]) == model.model_validate(item.payload)
        step = next(item for item in imported["labor_rates"] if item.code == "RATE_STEP")
        assert step.payload["tiers"][2] == {"upto_per_shift": None, "rate": "140"}

    def test_json_round_trip_is_exact(self):
        from cost.v2.reference_files import export_json, import_json

        snapshot = _snapshot(labor_rates=self.RATES, drilling_difficulty=(self.DIFFICULTY,))
        imported = import_json(json.dumps(export_json(snapshot), ensure_ascii=False).encode("utf-8"))
        assert tuple(imported["labor_rates"]) == self.RATES
        assert tuple(imported["drilling_difficulty"]) == (self.DIFFICULTY,)
```

В конец `tests/test_public_sync_mirror.py` добавить:

```python
def test_payroll_sections_can_be_mirrored() -> None:
    """TASK-010 PR 1: новые разделы доступны зеркалу, списки уходят в jsonb."""

    from cost.v2.public_sync.settings import mirrorable_sections

    assert {"payroll_params", "drilling_difficulty", "downtime_reasons"} <= set(mirrorable_sections())
    assert column("drilling_difficulty", "hardness").sql_type == "jsonb"
    assert column("payroll_params", "mrot").sql_type == "numeric"
    assert column("downtime_reasons", "excusable").sql_type == "boolean"
    assert column("labor_rates", "tiers").sql_type == "jsonb"
    assert column("labor_rates", "scale_type").sql_type == "text"
```

Создать `tests/test_api_payroll_references.py`:

```python
"""Публикация справочников методики ФОТ через API (TASK-010 PR 1)."""
from __future__ import annotations

from tests.test_api_economics import _client


def _record(code: str, name: str, payload: dict) -> dict:
    return {
        "code": code,
        "name": name,
        "payload": payload,
        "is_active": True,
        "valid_from": None,
        "valid_to": None,
        "source": "test",
        "comment": "",
        "revision": 1,
    }


CURVE = {
    "position_code": "POSITION_LABOR_DRILLER",
    "fixed_monthly_rub": "27093",
    "scale_type": "CURVE_POWER",
    "norm_per_shift": "115.3846",
    "rate_norm": "45",
    "ceiling_per_shift": "184.6154",
    "rate_ceiling": "168.66",
}


def _sections(snapshot: dict, rate: dict) -> dict:
    sections = snapshot["sections"]
    sections["production_units"] = [_record("UNIT_1", "Юнит 1", {})]
    sections["positions"] = [
        _record(
            "POSITION_LABOR_DRILLER",
            "Машинист буровой установки",
            {"category": "INDIRECT", "pay_system": "PIECE_PROGRESSIVE", "difficulty": "NORMALIZED_METERS"},
        )
    ]
    sections["labor_rates"] = [_record("RATE_DRILLER", "Машинист", rate)]
    sections["payroll_params"] = [
        _record(
            "PAYROLL_PARAMS_2026",
            "Параметры ФОТ 2026",
            {
                "year": "2026",
                "mrot": "27093",
                "annual_hours_40": "1972",
                "annual_hours_36": "1774.4",
                "work_days_year": "247",
                "holidays_year": "14",
            },
        )
    ]
    sections["downtime_reasons"] = [
        _record("DT_PLANNED_MAINTENANCE", "Плановое ТОиР", {"excusable": True, "planned_maintenance": True})
    ]
    sections["drilling_difficulty"] = [
        _record(
            "DRILLING_DIFFICULTY_BASE",
            "Сложность бурения",
            {
                "hardness": [{"f_from": None, "f_to": "12", "k": "1"}, {"f_from": "12", "f_to": None, "k": "1.2"}],
                "diameter": [{"diameter_mm": "152", "k": "1.00"}],
            },
        )
    ]
    return sections


def test_payroll_sections_are_published_and_read_back(monkeypatch) -> None:
    client, _ = _client(monkeypatch)
    snapshot = client.get("/api/v1/economics/references/snapshot").json()
    sections = _sections(snapshot, CURVE)

    published = client.post(
        "/api/v1/economics/references/publish",
        json={"base_revision": snapshot["revision_id"], "sections": sections, "comment": "ФОТ"},
    )

    assert published.status_code == 200, published.text
    stored = client.get("/api/v1/economics/references/snapshot").json()["sections"]
    assert stored["labor_rates"][0]["payload"]["ceiling_per_shift"] == "184.6154"
    assert stored["drilling_difficulty"][0]["payload"]["hardness"][1] == {"f_from": "12", "f_to": None, "k": "1.2"}
    assert [item["code"] for item in stored["payroll_params"]] == ["PAYROLL_PARAMS_2026"]


def test_broken_scale_blocks_publication_under_its_field(monkeypatch) -> None:
    client, _ = _client(monkeypatch)
    snapshot = client.get("/api/v1/economics/references/snapshot").json()
    sections = _sections(snapshot, {**CURVE, "rate_ceiling": "40"})

    response = client.post(
        "/api/v1/economics/references/publish",
        json={"base_revision": snapshot["revision_id"], "sections": sections, "comment": "ФОТ"},
    )

    assert response.status_code == 422
    issues = response.json()["detail"]["issues"]
    assert {
        "level": "error",
        "section": "labor_rates",
        "code": "RATE_DRILLER",
        "message": "Расценка на потолке не может быть ниже расценки на норме",
        "field": "rate_ceiling",
    } in issues
```

- [ ] **Шаг 2: убедиться, что падает**

Run: `.venv/bin/python -m pytest tests/test_payroll_schemas.py tests/test_reference_files.py tests/test_api_payroll_references.py -q`
Run: `.venv/bin/python -m pytest tests/test_public_sync_mirror.py -q`
Expected: FAIL — `ModuleNotFoundError: cost.v2.schemas.payroll`; в круге xlsx `KeyError: 'drilling_difficulty'`;
в API — 422 с «Неизвестный раздел справочника.»; в зеркале — разделов нет среди доступных.

- [ ] **Шаг 3: реализация**

Создать `cost/v2/schemas/payroll.py`:

```python
"""Схемы разделов методики ФОТ (TASK-010): параметры года, сложность бурения, простои.

Ставки взносов, травматизма и НДФЛ здесь не хранятся — они в «Ставках и
надбавках организации» (Т2); оклад, шкала и КПЭ — в «Ставках персонала» (Т1).
"""
from __future__ import annotations

from decimal import Decimal

from pydantic import Field, model_validator

from cost.v2.schemas.base import RateField, ReferencePayload, UnitField, field_error

__all__ = [
    "PayrollParamsPayload",
    "HardnessBand",
    "DiameterFactor",
    "DrillingDifficultyPayload",
    "DowntimeReasonPayload",
]


class PayrollParamsPayload(ReferencePayload):
    """Параметры года: календарь, МРОТ, годовые нормы часов, порог доли в марже."""

    year: int = UnitField("год", title="Год", description="Год производственного календаря", ge=2000, le=2100)
    mrot: Decimal = UnitField(
        "₽/мес", title="МРОТ", description="Минимальный размер оплаты труда — оклад должности без ставки"
    )
    annual_hours_40: Decimal = UnitField(
        "ч", title="Годовая норма при 40 ч/нед", description="Годовая норма часов при 40-часовой неделе"
    )
    annual_hours_36: Decimal = UnitField(
        "ч", title="Годовая норма при 36 ч/нед", description="Годовая норма часов при 36-часовой неделе (ст. 92 ТК РФ)"
    )
    work_days_year: Decimal = UnitField(
        "дн",
        title="Рабочих дней в году",
        description="По производственному календарю; делитель межвахтового отдыха — рабочих дней / 12",
        le=366,
    )
    holidays_year: Decimal = UnitField(
        "дн", title="Праздничных дней в году", description="Нерабочих праздничных дней по календарю", le=366
    )
    night_pct: Decimal = RateField(
        title="Доплата за ночные", description="Доля часовой ставки за ночной час", default=Decimal("0.20")
    )
    vacation_days_base: Decimal = UnitField(
        "дн",
        title="Основной отпуск",
        description="Дней основного оплачиваемого отпуска — база резерва",
        default=Decimal("28"),
        le=366,
    )
    margin_share_warn: Decimal = RateField(
        title="Порог доли в марже",
        description=(
            "Предупреждение, если стоимость последнего метра по экипажу станка с начислениями "
            "выше этой доли маржи метра"
        ),
        default=Decimal("0.70"),
    )

    @model_validator(mode="after")
    def _calendar_is_consistent(self) -> "PayrollParamsPayload":
        if self.work_days_year <= 0:
            field_error(type(self), "work_days_year", "Рабочих дней в году должно быть больше нуля", self.work_days_year)
        if self.annual_hours_40 <= 0:
            field_error(type(self), "annual_hours_40", "Годовая норма часов должна быть больше нуля", self.annual_hours_40)
        if self.annual_hours_36 <= 0 or self.annual_hours_36 > self.annual_hours_40:
            field_error(
                type(self),
                "annual_hours_36",
                "Норма при 36-часовой неделе больше нуля и не больше нормы при 40-часовой",
                self.annual_hours_36,
            )
        return self


class HardnessBand(ReferencePayload):
    f_from: Decimal | None = UnitField(
        "f", title="Крепость от", description="Нижняя граница, не включается; у первой строки пусто", default=None
    )
    f_to: Decimal | None = UnitField(
        "f", title="Крепость до", description="Верхняя граница, включается; у последней строки пусто", default=None
    )
    k: Decimal = UnitField("", title="Коэффициент", description="Множитель приведённых метров", default=Decimal("1"))


class DiameterFactor(ReferencePayload):
    diameter_mm: Decimal = UnitField("мм", title="Диаметр коронки", description="Диаметр коронки")
    k: Decimal = UnitField(
        "", title="Коэффициент", description="Множитель приведённых метров; стартовое значение Ø / 152", default=Decimal("1")
    )


class DrillingDifficultyPayload(ReferencePayload):
    """Коэффициенты приведения метров к базовым условиям: f = 10, Ø 152 мм, k = 1."""

    hardness: list[HardnessBand] = Field(
        default_factory=list,
        title="Крепость породы",
        description=(
            "Интервалы f_from < f ≤ f_to по возрастанию, без разрывов; база f = 10 → k = 1. "
            "Первая строка без нижней границы, последняя без верхней"
        ),
    )
    diameter: list[DiameterFactor] = Field(
        default_factory=list,
        title="Диаметр коронки",
        description="Коэффициент на каждый диаметр коронок из условий бурения; база Ø 152 мм → k = 1",
    )

    @model_validator(mode="after")
    def _tables_are_consistent(self) -> "DrillingDifficultyPayload":
        self._check_hardness()
        seen: set[Decimal] = set()
        for index, row in enumerate(self.diameter):
            if row.diameter_mm <= 0:
                field_error(type(self), ("diameter", index, "diameter_mm"), "Диаметр должен быть больше нуля", row.diameter_mm)
            if row.diameter_mm in seen:
                field_error(type(self), ("diameter", index, "diameter_mm"), "Диаметр уже есть в таблице", row.diameter_mm)
            seen.add(row.diameter_mm)
            if row.k <= 0:
                field_error(type(self), ("diameter", index, "k"), "Коэффициент должен быть больше нуля", row.k)
        return self

    def _check_hardness(self) -> None:
        last = len(self.hardness) - 1
        for index, band in enumerate(self.hardness):
            if band.k <= 0:
                field_error(type(self), ("hardness", index, "k"), "Коэффициент должен быть больше нуля", band.k)
            if index == 0 and band.f_from is not None:
                field_error(
                    type(self),
                    ("hardness", 0, "f_from"),
                    "У первой строки нижней границы нет: она охватывает всю крепость до верхней границы",
                    band.f_from,
                )
            if index == last and band.f_to is not None:
                field_error(
                    type(self),
                    ("hardness", index, "f_to"),
                    "У последней строки верхней границы нет: крепость выше шкалы берёт её коэффициент",
                    band.f_to,
                )
            if index < last and band.f_to is None:
                field_error(type(self), ("hardness", index, "f_to"), "Верхняя граница не задаётся только у последней строки")
            if index > 0:
                previous_to = self.hardness[index - 1].f_to
                if band.f_from is None or band.f_from != previous_to:
                    field_error(
                        type(self),
                        ("hardness", index, "f_from"),
                        f"Интервалы крепости идут без разрыва: нижняя граница равна верхней границе предыдущей строки ({previous_to})",
                        band.f_from,
                    )
            if band.f_from is not None and band.f_to is not None and band.f_to <= band.f_from:
                field_error(type(self), ("hardness", index, "f_to"), "Верхняя граница должна быть больше нижней", band.f_to)


class DowntimeReasonPayload(ReferencePayload):
    """Код простоя. Часы простоя не по вине машиниста вычитаются из эффективных смен вахты."""

    excusable: bool = Field(
        default=False,
        title="Не по вине машиниста",
        description="Часы простоя вычитаются из эффективных смен и не снижают темп машиниста",
    )
    planned_maintenance: bool = Field(
        default=False,
        title="Плановое ТОиР",
        description="Плановое ТОиР станка: в проверку «списано больше 25 % часов вахты» не входит",
    )

    @model_validator(mode="after")
    def _maintenance_is_excusable(self) -> "DowntimeReasonPayload":
        if self.planned_maintenance and not self.excusable:
            field_error(type(self), "planned_maintenance", "Плановое ТОиР — простой не по вине машиниста: отметьте оба признака")
        return self
```

`cost/v2/schemas/__init__.py`: после импорта из `organization` добавить

```python
from cost.v2.schemas.payroll import (
    DowntimeReasonPayload,
    DrillingDifficultyPayload,
    PayrollParamsPayload,
)
```

в `SECTION_FIELDSETS` после группы `labor_rates`:

```python
    "payroll_params": (
        ("Календарь", ("year", "work_days_year", "holidays_year", "annual_hours_40", "annual_hours_36")),
        ("Оплата", ("mrot", "night_pct", "vacation_days_base")),
        ("Контроль", ("margin_share_warn",)),
    ),
```

в `SECTION_SCHEMAS` после `"crew_templates"` — `"payroll_params": PayrollParamsPayload,` и
`"downtime_reasons": DowntimeReasonPayload,`; после `"drilling_conditions"` —
`"drilling_difficulty": DrillingDifficultyPayload,`.

`cost/v2/references.py`: после `"crew_templates"` (`:78`)

```python
    "payroll_params": {
        "group": "labor", "label": "Параметры года для ФОТ",
        "columns": ["name", "year", "mrot", "work_days_year", "margin_share_warn"],
    },
    "downtime_reasons": {
        "group": "labor", "label": "Причины простоев",
        "columns": ["name", "excusable", "planned_maintenance"],
    },
```

после записи `"drilling_conditions"` (`:101-105`)

```python
    "drilling_difficulty": {
        "group": "drilling", "label": "Сложность бурения",
        "columns": ["name", "hardness", "diameter"],
    },
```

- [ ] **Шаг 4: прогон**

Run: `.venv/bin/python -m pytest tests/test_payroll_schemas.py tests/test_reference_files.py tests/test_api_payroll_references.py tests/test_reference_schemas.py tests/test_api_reference_schema.py tests/test_api_reference_files.py tests/test_public_sync_mirror.py tests/test_api_public_settings.py -q`
Expected: PASS. Каталог схем отдаёт три раздела, группы покрывают все поля, листы xlsx ≤ 31 символа.

- [ ] **Шаг 5: коммит**

```bash
git add cost/v2/schemas/payroll.py cost/v2/schemas/__init__.py cost/v2/references.py tests/test_payroll_schemas.py tests/test_reference_files.py tests/test_public_sync_mirror.py tests/test_api_payroll_references.py
git commit -m "$(cat <<'EOF'
TASK-010 PR 1: разделы «Параметры года для ФОТ», «Сложность бурения», «Причины простоев»

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
)"
```

---

### Задача 5: перекрёстные проверки ревизии

**Файлы:**
- Создать: `cost/v2/payroll_checks.py`
- Изменить: `cost/v2/references.py:338-339` — вызов
- Тест: создать `tests/test_payroll_checks.py`

**Интерфейсы:**
- Использует: `ValidationIssue` (`references.py:164-181`), `CURVE_SCALES`, `HAZARDOUS_CLASSES`, `SitePayload`.
- Даёт: `payroll_issues(sections: Mapping[str, Sequence[ReferenceItem]]) -> list[ValidationIssue]`.

- [ ] **Шаг 1: падающие тесты**

Создать `tests/test_payroll_checks.py`:

```python
"""Проверки ревизии для методики ФОТ по нескольким разделам сразу (TASK-010 PR 1, Т15, Т16)."""
from __future__ import annotations

from cost.v2.models import ReferenceItem
from cost.v2.references import ValidationIssue, default_reference_sections, validate_reference_sections


def _item(code: str, payload: dict, name: str = "Запись") -> ReferenceItem:
    return ReferenceItem(code=code, name=name, payload=payload)


def _issues(**sections) -> list[ValidationIssue]:
    merged = dict(default_reference_sections())
    merged.update(sections)
    return validate_reference_sections(merged)


def _about(issues: list[ValidationIssue], section: str) -> list[tuple[str, str, str, str]]:
    return [(issue.level, issue.code, issue.field, issue.message) for issue in issues if issue.section == section]


PARAMS = {
    "year": "2026",
    "mrot": "27093",
    "annual_hours_40": "1972",
    "annual_hours_36": "1774.4",
    "work_days_year": "247",
    "holidays_year": "14",
}
CURVE = {
    "position_code": "POS_DRILLER",
    "scale_type": "CURVE_POWER",
    "norm_per_shift": "115.3846",
    "rate_norm": "45",
    "ceiling_per_shift": "184.6154",
    "rate_ceiling": "168.66",
}


def test_empty_new_sections_are_warnings_not_errors():
    issues = _issues()
    assert ("warning", "", "", "Не заведены параметры года: ФОТ по методике не рассчитается.") in _about(issues, "payroll_params")
    assert _about(issues, "drilling_difficulty") == [
        ("warning", "", "", "Не заведены коэффициенты сложности бурения: приведённые метры не посчитать.")
    ]
    assert _about(issues, "downtime_reasons") == [
        ("warning", "", "", "Не заведены причины простоев: простой не по вине машиниста не списать.")
    ]
    assert not [issue for issue in issues if issue.level == "error"]


def test_one_parameter_record_per_year():
    issues = _issues(payroll_params=(_item("P1", PARAMS), _item("P2", {**PARAMS, "year": 2026})))
    assert _about(issues, "payroll_params") == [
        ("error", "P2", "year", "Параметры 2026 года уже заведены записью P1.")
    ]


def test_one_active_difficulty_record():
    issues = _issues(drilling_difficulty=(_item("DD1", {}), _item("DD2", {})))
    assert _about(issues, "drilling_difficulty") == [
        ("error", "DD2", "", "Действует одна запись коэффициентов сложности бурения, уже есть DD1.")
    ]


def _bits(material: dict, diameters: list[str]) -> dict:
    return {
        "materials": (_item("MAT_BIT", material, name="Коронка 165"),),
        "equipment_types": (_item("RIG", {"kind": "DRILL_RIG"}),),
        "drilling_conditions": (_item("COND", {"equipment_type_code": "RIG", "bit_material_code": "MAT_BIT"}),),
        "drilling_difficulty": (
            _item("DD", {"diameter": [{"diameter_mm": value, "k": "1"} for value in diameters]}),
        ),
    }


def test_every_bit_diameter_needs_a_factor():
    issues = _issues(**_bits({"diameter_mm": "165"}, ["152"]))
    assert _about(issues, "drilling_difficulty") == [
        ("error", "DD", "diameter", "Нет коэффициента для коронки Ø 165 мм (Коронка 165).")
    ]
    assert _about(_issues(**_bits({"diameter_mm": "165.0"}, ["152", "165"])), "drilling_difficulty") == []


def test_bit_without_a_diameter_is_a_warning_on_the_material():
    issues = _issues(**_bits({}, ["152"]))
    assert _about(issues, "materials") == [
        (
            "warning",
            "MAT_BIT",
            "diameter_mm",
            "У коронки из условий бурения не задан диаметр: коэффициент диаметра для неё не проверен.",
        )
    ]


def test_bit_diameters_are_not_checked_while_the_section_is_empty():
    sections = _bits({"diameter_mm": "165"}, [])
    sections["drilling_difficulty"] = ()
    assert [issue for issue in _issues(**sections) if issue.level == "error"] == []


def _drilling_rate(**conditions) -> dict:
    return {
        "positions": (_item("POS_DRILLER", {"category": "INDIRECT", "difficulty": "NORMALIZED_METERS"}),),
        "labor_rates": (_item("RATE_DRILLER", CURVE),),
        "equipment_types": (_item("RIG", {"kind": "DRILL_RIG"}),),
        "drilling_conditions": tuple(
            _item(code, {"equipment_type_code": "RIG", **payload}) for code, payload in conditions.items()
        ),
    }


def test_ceiling_above_what_a_rig_drills_in_a_shift_is_a_warning():
    # Базовая строка 10 м/ч × (11 − 1) ч = 100 м/смену; строка по породе в сравнение не входит.
    issues = _issues(
        **_drilling_rate(
            COND_BASE={"tech_speed_m_per_h": "10", "unproductive_h_per_shift": "1"},
            COND_GRANITE={"rock_code": "ROCK", "tech_speed_m_per_h": "30"},
        ),
        rocks=(_item("ROCK", {}),),
    )
    assert _about(issues, "labor_rates") == [
        (
            "warning",
            "RATE_DRILLER",
            "ceiling_per_shift",
            "Потолок 184.6154 м/смену выше производительности станков по базовым условиям бурения "
            "(до 100 м/смену): машинист не дойдёт до потолка.",
        )
    ]


def test_ceiling_within_rig_capacity_passes():
    # 20 м/ч × 10 ч = 200 м/смену.
    issues = _issues(**_drilling_rate(COND_BASE={"tech_speed_m_per_h": "20", "unproductive_h_per_shift": "1"}))
    assert _about(issues, "labor_rates") == []


def test_rotation_maintenance_against_rig_maintenance_ratio():
    rig = (_item("RIG", {"kind": "DRILL_RIG", "maintenance_ratio": "0.14"}, name="JK830"),)
    # 15 × 0,14 / 1,14 = 1,84 смены: 2 в пределах полусмены, 3 — нет.
    assert _about(_issues(equipment_types=rig, sites=(_item("S", {}),)), "sites") == []
    issues = _issues(equipment_types=rig, sites=(_item("S", {"maintenance_shifts": "3"}),))
    assert _about(issues, "sites") == [
        (
            "warning",
            "S",
            "maintenance_shifts",
            "Плановое ТОиР 3 см за вахту расходится с долей ТОиР станка JK830: "
            "0.14 смены ТОиР на рабочую смену дают 1.84 см из 15.",
        )
    ]


def test_hazardous_class_needs_an_extra_tariff():
    position = (_item("POS_X", {"category": "INDIRECT", "work_conditions_class": "3.3"}),)
    issues = _issues(positions=position)
    assert _about(issues, "positions") == [
        (
            "warning",
            "POS_X",
            "work_conditions_class",
            "Для класса условий труда 3.3 в «Ставках и надбавках организации» не задан доп. тариф взносов: "
            "расчёт ФОТ возьмёт 0.",
        )
    ]
    sections = dict(default_reference_sections())
    rates = sections["organization_rates"][0]
    covered = ReferenceItem(
        code=rates.code,
        name=rates.name,
        payload={**rates.payload, "extra_tariffs": [{"work_conditions_class": "3.3", "rate": "0.06"}]},
    )
    assert _about(_issues(positions=position, organization_rates=(covered,)), "positions") == []
    assert _about(_issues(positions=(_item("POS_Y", {"category": "INDIRECT", "work_conditions_class": "2"}),)), "positions") == []


def test_schema_errors_inside_lists_carry_the_row_path():
    issues = _issues(
        positions=(_item("POS_DRILLER", {"category": "INDIRECT"}),),
        labor_rates=(
            _item(
                "RATE_STEP",
                {
                    "position_code": "POS_DRILLER",
                    "scale_type": "STEP",
                    "tiers": [{"upto_per_shift": "115", "rate": "45"}, {"upto_per_shift": "138", "rate": "40"}, {"rate": "140"}],
                },
            ),
        ),
    )
    assert _about(issues, "labor_rates") == [
        ("error", "RATE_STEP", "tiers.1.rate", "Расценка ступени не может быть ниже предыдущей")
    ]
```

- [ ] **Шаг 2: убедиться, что падает**

Run: `.venv/bin/python -m pytest tests/test_payroll_checks.py -q`
Expected: FAIL — нет предупреждений о пустых разделах, дублей года и второй записи сложности, ошибки коронки,
предупреждений о потолке, ТОиР и доп. тарифе. Тесты «проблем нет» (`…_passes`, `…_while_the_section_is_empty`) и
`test_schema_errors_inside_lists_carry_the_row_path` проходят уже сейчас.

- [ ] **Шаг 3: реализация**

Создать `cost/v2/payroll_checks.py`:

```python
"""Перекрёстные проверки ревизии для методики ФОТ (TASK-010).

Правила внутри одной записи — шкала ставки, интервалы крепости, доли геологии —
живут в схемах разделов. Здесь то, что видно только по нескольким разделам
сразу. Проверяется весь черновик, и ошибка блокирует публикацию любых правок
организации, поэтому пустой новый раздел — предупреждение, а ошибка возможна
только в заполненном (Т15).
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any, Mapping, Sequence

from cost.v2.models import ReferenceItem
from cost.v2.references import ValidationIssue
from cost.v2.schemas.labor import CURVE_SCALES, HAZARDOUS_CLASSES
from cost.v2.schemas.organization import SitePayload

__all__ = ["payroll_issues"]

EMPTY_SECTION_MESSAGES: dict[str, str] = {
    "payroll_params": "Не заведены параметры года: ФОТ по методике не рассчитается.",
    "drilling_difficulty": "Не заведены коэффициенты сложности бурения: приведённые метры не посчитать.",
    "downtime_reasons": "Не заведены причины простоев: простой не по вине машиниста не списать.",
}

# Расхождение планового ТОиР объекта с долей ТОиР станка, после которого
# источники считаются разными (Т16).
MAINTENANCE_TOLERANCE_SHIFTS = Decimal("0.5")
DEFAULT_SHIFT_HOURS = Decimal("11")


def payroll_issues(sections: Mapping[str, Sequence[ReferenceItem]]) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    issues.extend(_empty_sections(sections))
    issues.extend(_duplicate_years(sections))
    issues.extend(_single_difficulty(sections))
    issues.extend(_bit_diameters(sections))
    issues.extend(_ceiling_above_rigs(sections))
    issues.extend(_maintenance_against_rigs(sections))
    issues.extend(_missing_extra_tariffs(sections))
    return issues


def _active(sections: Mapping[str, Sequence[ReferenceItem]], section: str) -> list[ReferenceItem]:
    return [item for item in sections.get(section, ()) if item.is_active]


def _decimal(value: Any) -> Decimal | None:
    if value is None or value == "" or isinstance(value, bool):
        return None
    try:
        return Decimal(str(value))
    except InvalidOperation:
        return None


def _plain(value: Decimal) -> str:
    return format(value.normalize(), "f")


def _empty_sections(sections: Mapping[str, Sequence[ReferenceItem]]) -> list[ValidationIssue]:
    return [
        ValidationIssue("warning", section, "", message)
        for section, message in EMPTY_SECTION_MESSAGES.items()
        if not _active(sections, section)
    ]


def _duplicate_years(sections: Mapping[str, Sequence[ReferenceItem]]) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    first: dict[Decimal, str] = {}
    for item in _active(sections, "payroll_params"):
        year = _decimal(item.payload.get("year"))
        if year is None:
            continue
        if year in first:
            issues.append(
                ValidationIssue(
                    "error",
                    "payroll_params",
                    item.code,
                    f"Параметры {_plain(year)} года уже заведены записью {first[year]}.",
                    field="year",
                )
            )
            continue
        first[year] = item.code
    return issues


def _single_difficulty(sections: Mapping[str, Sequence[ReferenceItem]]) -> list[ValidationIssue]:
    items = _active(sections, "drilling_difficulty")
    return [
        ValidationIssue(
            "error",
            "drilling_difficulty",
            item.code,
            f"Действует одна запись коэффициентов сложности бурения, уже есть {items[0].code}.",
        )
        for item in items[1:]
    ]


def _bit_diameters(sections: Mapping[str, Sequence[ReferenceItem]]) -> list[ValidationIssue]:
    """Каждая коронка из условий бурения должна иметь коэффициент диаметра."""

    difficulty = next(iter(_active(sections, "drilling_difficulty")), None)
    if difficulty is None:
        return []
    table = {
        diameter
        for row in difficulty.payload.get("diameter") or ()
        if isinstance(row, Mapping) and (diameter := _decimal(row.get("diameter_mm"))) is not None
    }
    materials = {item.code: item for item in _active(sections, "materials")}
    issues: list[ValidationIssue] = []
    reported: set[str] = set()
    for condition in _active(sections, "drilling_conditions"):
        material = materials.get(str(condition.payload.get("bit_material_code") or ""))
        if material is None or material.code in reported:
            continue
        reported.add(material.code)
        diameter = _decimal(material.payload.get("diameter_mm"))
        if diameter is None:
            issues.append(
                ValidationIssue(
                    "warning",
                    "materials",
                    material.code,
                    "У коронки из условий бурения не задан диаметр: коэффициент диаметра для неё не проверен.",
                    field="diameter_mm",
                )
            )
        elif diameter not in table:
            issues.append(
                ValidationIssue(
                    "error",
                    "drilling_difficulty",
                    difficulty.code,
                    f"Нет коэффициента для коронки Ø {_plain(diameter)} мм ({material.name}).",
                    field="diameter",
                )
            )
    return issues


def _ceiling_above_rigs(sections: Mapping[str, Sequence[ReferenceItem]]) -> list[ValidationIssue]:
    """Потолок шкалы машиниста выше того, что станок бурит за смену по базовым условиям."""

    rates = next(iter(_active(sections, "organization_rates")), None)
    shift_hours = _decimal(rates.payload.get("shift_hours")) if rates is not None else None
    shift_hours = shift_hours or DEFAULT_SHIFT_HOURS
    per_shift = [
        speed * max(shift_hours - (_decimal(item.payload.get("unproductive_h_per_shift")) or Decimal("0")), Decimal("0"))
        for item in _active(sections, "drilling_conditions")
        # Базовая строка — без породы и карьера: шкала задана для базовых условий.
        if not item.payload.get("rock_code") and not item.payload.get("site_code")
        and (speed := _decimal(item.payload.get("tech_speed_m_per_h"))) is not None
    ]
    if not per_shift:
        return []
    best = max(per_shift)
    normalized = {
        item.code for item in _active(sections, "positions") if item.payload.get("difficulty") == "NORMALIZED_METERS"
    }
    issues: list[ValidationIssue] = []
    for item in _active(sections, "labor_rates"):
        if item.payload.get("scale_type") not in CURVE_SCALES:
            continue
        if str(item.payload.get("position_code") or "") not in normalized:
            continue
        ceiling = _decimal(item.payload.get("ceiling_per_shift"))
        if ceiling is None or ceiling <= best:
            continue
        issues.append(
            ValidationIssue(
                "warning",
                "labor_rates",
                item.code,
                f"Потолок {_plain(ceiling)} м/смену выше производительности станков по базовым условиям бурения "
                f"(до {_plain(best)} м/смену): машинист не дойдёт до потолка.",
                field="ceiling_per_shift",
            )
        )
    return issues


def _maintenance_against_rigs(sections: Mapping[str, Sequence[ReferenceItem]]) -> list[ValidationIssue]:
    """Плановое ТОиР объекта против доли ТОиР станка (Т16).

    Доля ТОиР — смен ТОиР на рабочую смену, поэтому из вахты в `N` смен на
    ТОиР уходит `N × r / (1 + r)`: при 15 сменах и 0,14 — 1,84 смены.
    """

    rigs = [
        (item, ratio)
        for item in _active(sections, "equipment_types")
        if str(item.payload.get("kind") or "DRILL_RIG") == "DRILL_RIG"
        and (ratio := _decimal(item.payload.get("maintenance_ratio"))) is not None
        and ratio > 0
    ]
    if not rigs:
        return []
    default_days = SitePayload.model_fields["shift_days_on"].default
    default_shifts = SitePayload.model_fields["maintenance_shifts"].default
    issues: list[ValidationIssue] = []
    for site in _active(sections, "sites"):
        days = _decimal(site.payload.get("shift_days_on")) or default_days
        planned = _decimal(site.payload.get("maintenance_shifts"))
        planned = default_shifts if planned is None else planned
        for rig, ratio in rigs:
            expected = days * ratio / (1 + ratio)
            if abs(expected - planned) <= MAINTENANCE_TOLERANCE_SHIFTS:
                continue
            issues.append(
                ValidationIssue(
                    "warning",
                    "sites",
                    site.code,
                    f"Плановое ТОиР {_plain(planned)} см за вахту расходится с долей ТОиР станка {rig.name}: "
                    f"{_plain(ratio)} смены ТОиР на рабочую смену дают "
                    f"{_plain(expected.quantize(Decimal('0.01')))} см из {_plain(days)}.",
                    field="maintenance_shifts",
                )
            )
    return issues


def _missing_extra_tariffs(sections: Mapping[str, Sequence[ReferenceItem]]) -> list[ValidationIssue]:
    rates = next(iter(_active(sections, "organization_rates")), None)
    covered = {
        str(row.get("work_conditions_class"))
        for row in (rates.payload.get("extra_tariffs") or () if rates is not None else ())
        if isinstance(row, Mapping)
    }
    issues: list[ValidationIssue] = []
    for item in _active(sections, "positions"):
        work_class = item.payload.get("work_conditions_class")
        if work_class not in HAZARDOUS_CLASSES or work_class in covered:
            continue
        issues.append(
            ValidationIssue(
                "warning",
                "positions",
                item.code,
                f"Для класса условий труда {work_class} в «Ставках и надбавках организации» "
                "не задан доп. тариф взносов: расчёт ФОТ возьмёт 0.",
                field="work_conditions_class",
            )
        )
    return issues
```

`cost/v2/references.py:338-339` заменить на:

```python
    issues.extend(_schema_issues(sections))
    issues.extend(_reference_issues(sections))
    # Локальный импорт: модуль проверок сам берёт `ValidationIssue` отсюда.
    from cost.v2.payroll_checks import payroll_issues

    issues.extend(payroll_issues(sections))
```

- [ ] **Шаг 4: прогон**

Run: `.venv/bin/python -m pytest tests/test_payroll_checks.py tests/test_reference_schemas.py tests/test_seed_defaults.py tests/test_crew_defaults.py tests/test_api_economics.py tests/test_api_payroll_references.py -q`
Expected: PASS. `test_default_sections_are_valid` остаётся зелёным: у пустых разделов только предупреждения.

- [ ] **Шаг 5: коммит**

```bash
git add cost/v2/payroll_checks.py cost/v2/references.py tests/test_payroll_checks.py
git commit -m "$(cat <<'EOF'
TASK-010 PR 1: проверки ревизии по разделам ФОТ — коронки, потолок, ТОиР, доп. тариф

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
)"
```

---

### Задача 6: сид по файлу владельца и скрипт

**Файлы:**
- Создать: `cost/v2/payroll_defaults.py`
- Создать: `scripts/seed_payroll_references.py`
- Тест: создать `tests/test_payroll_defaults.py`

**Интерфейсы:**
- Использует: `normalize_sections`, `validate_reference_sections`, коды перечислений Задачи 2, поля Задач 3–4;
  `tests.test_crew_defaults.imported_snapshot` (снимок после импорта V1: шесть косвенных `POSITION_LABOR_*` со
  ставками `RATE_<код>` 60 000 ₽ и 0,25 ₽, без помощника).
- Даёт: `seed_payroll_references(snapshot) -> tuple[dict[str, list[ReferenceItem]], PayrollSeedReport]`,
  `PayrollSeedReport{added, filled, skipped}.to_dict()`.

- [ ] **Шаг 1: падающие тесты**

Создать `tests/test_payroll_defaults.py`:

```python
"""Сид справочников методики ФОТ поверх опубликованного снимка (TASK-010 PR 1, Т10)."""
from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

from cost.model.engine import compute_block_economics
from cost.model.inputs import CrewMember
from cost.v2.crew_defaults import DEFAULT_CREW_CODE, reclassify_positions
from cost.v2.models import ReferenceItem, ReferenceSnapshot
from cost.v2.payroll_defaults import seed_payroll_references
from cost.v2.references import has_validation_errors, validate_reference_sections
from tests import model_fixtures as fx
from tests.test_crew_defaults import imported_snapshot


def _as_snapshot(base: ReferenceSnapshot, sections: dict[str, list[ReferenceItem]]) -> ReferenceSnapshot:
    return replace(base, sections={name: tuple(items) for name, items in sections.items()})


def _by_code(sections: dict[str, list[ReferenceItem]], section: str) -> dict[str, ReferenceItem]:
    return {item.code: item for item in sections[section]}


def test_seed_over_imported_positions_is_valid_and_complete():
    sections, report = seed_payroll_references(imported_snapshot())

    positions = _by_code(sections, "positions")
    assert len([code for code in positions if code.startswith("POSITION_LABOR_")]) == 14
    driller = positions["POSITION_LABOR_DRILLER"]
    # Наименование и заданная категория существующей записи не меняются.
    assert driller.name == "Бурильщик"
    assert driller.payload["category"] == "INDIRECT"
    assert driller.payload["pay_system"] == "PIECE_PROGRESSIVE"
    assert driller.payload["work_conditions_class"] == "3.2"
    assert driller.payload["difficulty"] == "NORMALIZED_METERS"
    assert positions["POSITION_LABOR_MINER"].payload["output_source"] == "SECTION_OUTPUT"
    storekeeper = positions["POSITION_LABOR_STOREKEEPER"]
    assert (storekeeper.source, storekeeper.payload["category"], storekeeper.payload["pay_system"]) == (
        "payroll_seed", "INDIRECT", "TIME_BONUS",
    )

    rate = _by_code(sections, "labor_rates")["RATE_POSITION_LABOR_DRILLER"]
    assert rate.payload["fixed_monthly_rub"] == "60000"
    assert {key: rate.payload[key] for key in ("scale_type", "norm_per_shift", "rate_norm", "ceiling_per_shift", "rate_ceiling")} == {
        "scale_type": "CURVE_POWER",
        "norm_per_shift": "115.3846",
        "rate_norm": "45",
        "ceiling_per_shift": "184.6154",
        "rate_ceiling": "168.66",
    }
    # У помощника в этом снимке нет ставки — новую не заводим.
    assert "labor_rates:POSITION_LABOR_ASSISTANT: нет ставки без условия бурения, шкала не заведена" in report.skipped

    params = _by_code(sections, "payroll_params")["PAYROLL_PARAMS_2026"].payload
    assert (params["mrot"], params["annual_hours_36"], params["work_days_year"]) == ("27093", "1774.4", "247")
    difficulty = _by_code(sections, "drilling_difficulty")["DRILLING_DIFFICULTY_BASE"].payload
    assert [row["k"] for row in difficulty["hardness"]] == ["0.9", "1.0", "1.1", "1.2", "1.3"]
    assert difficulty["diameter"] == [
        {"diameter_mm": diameter, "k": k}
        for diameter, k in (
            ("110", "0.72"), ("127", "0.84"), ("140", "0.92"), ("152", "1.00"),
            ("165", "1.09"), ("190", "1.25"), ("215", "1.41"), ("250", "1.64"),
        )
    ]
    reasons = _by_code(sections, "downtime_reasons")
    assert len(reasons) == 10
    assert reasons["DT_PLANNED_MAINTENANCE"].payload == {"excusable": True, "planned_maintenance": True}
    assert reasons["DT_LATE"].payload == {"excusable": False, "planned_maintenance": False}
    rates = sections["organization_rates"][0].payload
    assert rates["extra_tariffs"][1] == {"work_conditions_class": "3.2", "rate": "0.04"}
    assert rates["social_contribution_rate"] == "0.30"
    assert "units:KM" in report.added

    assert not has_validation_errors(validate_reference_sections(sections))


def test_second_run_changes_nothing():
    first, _ = seed_payroll_references(imported_snapshot())
    again, report = seed_payroll_references(_as_snapshot(imported_snapshot(), first))
    assert again == first
    assert report.added == [] and report.filled == []


def test_filled_values_are_never_overwritten():
    base = imported_snapshot()
    positions = tuple(
        replace(item, payload={**item.payload, "pay_system": "TIME_BONUS", "work_conditions_class": "3.3"})
        if item.code == "POSITION_LABOR_DRILLER"
        else item
        for item in base.sections["positions"]
    )
    rates = tuple(
        replace(item, payload={**item.payload, "scale_type": "STEP", "tiers": [{"rate": "100"}]})
        if item.code == "RATE_POSITION_LABOR_DRILLER"
        else item
        for item in base.sections["labor_rates"]
    )
    sections, _ = seed_payroll_references(replace(base, sections={**base.sections, "positions": positions, "labor_rates": rates}))

    driller = _by_code(sections, "positions")["POSITION_LABOR_DRILLER"].payload
    assert (driller["pay_system"], driller["work_conditions_class"]) == ("TIME_BONUS", "3.3")
    assert driller["hazard_pct"] == "0.04"
    rate = _by_code(sections, "labor_rates")["RATE_POSITION_LABOR_DRILLER"].payload
    assert rate["scale_type"] == "STEP" and "norm_per_shift" not in rate


def test_bit_diameters_from_drilling_conditions_join_the_owner_list():
    snapshot = fx.references(
        materials=tuple(
            replace(item, payload={**item.payload, "diameter_mm": "171"}) if item.code == "MAT_BIT" else item
            for item in fx.MATERIALS
        )
    )
    sections, _ = seed_payroll_references(snapshot)
    diameters = _by_code(sections, "drilling_difficulty")["DRILLING_DIFFICULTY_BASE"].payload["diameter"]
    assert {"diameter_mm": "171", "k": "1.13"} in diameters
    assert not has_validation_errors(validate_reference_sections(sections))


def test_rates_based_block_economics_do_not_move():
    """Расчёт по ставкам новых ключей не читает: смета до и после сида одна."""

    reclassified, _ = reclassify_positions(imported_snapshot())
    before = _as_snapshot(imported_snapshot(), reclassified)
    crew = tuple(
        CrewMember(member["position_code"], Decimal(member["headcount"]))
        for item in reclassified["crew_templates"]
        if item.code == DEFAULT_CREW_CODE
        for member in item.payload["members"]
    ) + (CrewMember("POSITION_LABOR_DRILLER", Decimal("1")),)
    seeded, _ = seed_payroll_references(before)
    after = _as_snapshot(before, seeded)

    parameters = fx.parameters(crew=crew)
    lines_before = compute_block_economics(fx.snapshot(), parameters, before).lines
    lines_after = compute_block_economics(fx.snapshot(), parameters, after).lines

    assert [(line.cost_item_code, line.amount_rub) for line in lines_after] == [
        (line.cost_item_code, line.amount_rub) for line in lines_before
    ]
    assert any(line.cost_item_code == "LABOR_POSITION_LABOR_DRILLER" for line in lines_after)
```

- [ ] **Шаг 2: убедиться, что падает**

Run: `.venv/bin/python -m pytest tests/test_payroll_defaults.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'cost.v2.payroll_defaults'`.

- [ ] **Шаг 3: реализация**

Создать `cost/v2/payroll_defaults.py`:

```python
"""Справочники методики ФОТ по файлу владельца «Расчёт заработной платы» (TASK-010).

Функция «опубликованный снимок → дополненные разделы» (Т10), как
`reclassify_positions`: импорт xlsx заменяет раздел целиком и затёр бы
должности организации, поэтому на проде данные дописываются отсюда. Правила:

- записи, которой нет, заводится новая с источником `payroll_seed`;
- у записи, которая уже есть, заполняются только пустые ключи payload —
  заданные значения не меняются (решение владельца 14.09.2026);
- повторный прогон ничего не меняет.

Расчёт по ставкам (`labor.compute`) новых ключей не читает, поэтому смета
после сида та же.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Mapping

from cost.v2.models import ReferenceItem, ReferenceSnapshot
from cost.v2.references import normalize_sections

SOURCE = "payroll_seed"
_COMMENT = "Файл «Расчёт заработной платы» 2026: уточните по штатному расписанию и СОУТ."

PAYROLL_YEAR = "2026"
PAYROLL_PARAMS: dict[str, str] = {
    "year": PAYROLL_YEAR,
    "mrot": "27093",
    "annual_hours_40": "1972",
    "annual_hours_36": "1774.4",
    "work_days_year": "247",
    "holidays_year": "14",
    "night_pct": "0.20",
    "vacation_days_base": "28",
    "margin_share_warn": "0.70",
}

# Кривая машиниста и помощника: 45 ₽ на норме 1 500 м за 13 смен, 168,66 ₽ на
# потолке 2 400 м. Узлы с четырьмя знаками: с двумя премия при 2 400 м
# расходится с методикой на 0,24 ₽ (решения, §1).
DRILLER_SCALE: dict[str, str] = {
    "scale_type": "CURVE_POWER",
    "norm_per_shift": "115.3846",
    "rate_norm": "45",
    "ceiling_per_shift": "184.6154",
    "rate_ceiling": "168.66",
}

# Доп. тариф взносов по классу условий труда, ст. 428 НК РФ.
EXTRA_TARIFFS: tuple[dict[str, str], ...] = (
    {"work_conditions_class": "3.1", "rate": "0.02"},
    {"work_conditions_class": "3.2", "rate": "0.04"},
    {"work_conditions_class": "3.3", "rate": "0.06"},
    {"work_conditions_class": "3.4", "rate": "0.07"},
    {"work_conditions_class": "4", "rate": "0.08"},
)

HARDNESS_BANDS: tuple[dict[str, str | None], ...] = (
    {"f_from": None, "f_to": "8", "k": "0.9"},
    {"f_from": "8", "f_to": "12", "k": "1.0"},
    {"f_from": "12", "f_to": "16", "k": "1.1"},
    {"f_from": "16", "f_to": "18", "k": "1.2"},
    {"f_from": "18", "f_to": None, "k": "1.3"},
)
BASE_DIAMETER_MM = Decimal("152")
OWNER_DIAMETERS_MM: tuple[str, ...] = ("110", "127", "140", "152", "165", "190", "215", "250")

DOWNTIME_REASONS: tuple[tuple[str, str, bool, bool], ...] = (
    # код, наименование, не по вине машиниста, плановое ТОиР
    ("DT_WAIT_BLOCK", "Ожидание готовности блока", True, False),
    ("DT_RIG_REPAIR", "Ремонт станка не по вине машиниста", True, False),
    ("DT_BLASTING", "Взрывные работы", True, False),
    ("DT_WEATHER", "Погодные условия", True, False),
    ("DT_NO_SUPPLY", "Нет воды, топлива или энергии", True, False),
    ("DT_RELOCATION_ORDER", "Перегон по распоряжению", True, False),
    ("DT_PLANNED_MAINTENANCE", "Плановое ТОиР", True, True),
    ("DT_LATE", "Опоздание", False, False),
    ("DT_FAULT_BREAKDOWN", "Поломка по вине машиниста", False, False),
    ("DT_ABSENCE", "Отсутствие на смене", False, False),
)

_DRILLING = {
    "department": "DRILLING_BLASTING",
    "pay_system": "PIECE_PROGRESSIVE",
    "work_conditions_class": "3.2",
    "hazard_pct": "0.04",
    "extra_vacation_days": "7",
    "night_hours_per_shift": "8",
    "output_unit": "M",
    "output_source": "OWN_OUTPUT",
    "difficulty": "NORMALIZED_METERS",
}
_BLASTING = {"department": "DRILLING_BLASTING", "pay_system": "PIECE_PROGRESSIVE"}

# 14 должностей листа «Список должностей и формы премирования». Первые семь
# уже заведены импортом Cost V1 под этими кодами (сопоставление утвердил
# владелец 14.09.2026); наименование существующей записи сид не меняет.
POSITIONS: tuple[tuple[str, str, dict[str, str]], ...] = (
    ("POSITION_LABOR_DRILLER", "Машинист буровой установки", _DRILLING),
    ("POSITION_LABOR_ASSISTANT", "Помощник машиниста буровой установки", _DRILLING),
    ("POSITION_LABOR_DRIVER_SZM", "Водитель-оператор СЗМ", _BLASTING),
    ("POSITION_LABOR_BLASTERS", "Взрывник", _BLASTING),
    ("POSITION_LABOR_MASTER", "Мастер-взрывник", _BLASTING),
    ("POSITION_LABOR_MINER", "Горнорабочий", {**_BLASTING, "output_source": "SECTION_OUTPUT"}),
    ("POSITION_LABOR_DRIVER_DEL", "Водитель ДОПОГ (кат. B, C, E)", {"department": "TRANSPORT", "pay_system": "PIECE_BONUS"}),
    ("POSITION_LABOR_SENIOR_BLASTER", "Старший взрывник", _BLASTING),
    ("POSITION_LABOR_DRIVER", "Водитель (все категории)", {"department": "TRANSPORT", "pay_system": "PIECE_BONUS", "output_unit": "KM"}),
    ("POSITION_LABOR_LOADER_DRIVER", "Водитель погрузчика", {"department": "TRANSPORT", "pay_system": "PIECE_BONUS", "output_unit": "M3"}),
    ("POSITION_LABOR_VM_DISPENSER", "Раздатчик ВМ", {"department": "WAREHOUSE", "pay_system": "TIME_BONUS"}),
    ("POSITION_LABOR_STOREKEEPER", "Кладовщик", {"department": "WAREHOUSE", "pay_system": "TIME_BONUS"}),
    ("POSITION_LABOR_EMULSION_OPERATOR", "Аппаратчик линии ЭВВ", {"department": "WAREHOUSE", "pay_system": "PIECE_BONUS", "output_unit": "T"}),
    ("POSITION_LABOR_REPAIR_FITTER", "Слесарь по ремонту оборудования и автомобилей", {"department": "MAINTENANCE", "pay_system": "TIME_BONUS"}),
)
SCALED_POSITIONS: tuple[str, ...] = ("POSITION_LABOR_DRILLER", "POSITION_LABOR_ASSISTANT")

KM_UNIT = ReferenceItem(
    code="KM",
    name="Километр",
    payload={"symbol": "км", "dimension": "length", "factor_to_base": 1000},
    source=SOURCE,
)


@dataclass
class PayrollSeedReport:
    added: list[str] = field(default_factory=list)
    filled: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"added": list(self.added), "filled": list(self.filled), "skipped": list(self.skipped)}


def seed_payroll_references(
    snapshot: ReferenceSnapshot,
) -> tuple[dict[str, list[ReferenceItem]], PayrollSeedReport]:
    sections = {name: list(items) for name, items in normalize_sections(snapshot.sections).items()}
    report = PayrollSeedReport()
    _units(sections, report)
    _positions(sections, report)
    _driller_scales(sections, report)
    _extra_tariffs(sections, report)
    _payroll_params(sections, report)
    _drilling_difficulty(sections, report)
    _downtime_reasons(sections, report)
    return sections, report


def _empty(value: Any) -> bool:
    return value is None or value == "" or value == []


def _fill(item: ReferenceItem, values: Mapping[str, Any]) -> tuple[ReferenceItem, list[str]]:
    """Запись с заполненными пустыми ключами и список этих ключей."""

    filled = [key for key in values if _empty(item.payload.get(key))]
    if not filled:
        return item, []
    return replace(item, payload={**item.payload, **{key: values[key] for key in filled}}), filled


def _new(code: str, name: str, payload: Mapping[str, Any]) -> ReferenceItem:
    return ReferenceItem(code=code, name=name, payload=dict(payload), source=SOURCE, comment=_COMMENT)


def _units(sections: dict[str, list[ReferenceItem]], report: PayrollSeedReport) -> None:
    if any(item.code == KM_UNIT.code for item in sections["units"]):
        return
    sections["units"].append(KM_UNIT)
    report.added.append(f"units:{KM_UNIT.code}")


def _positions(sections: dict[str, list[ReferenceItem]], report: PayrollSeedReport) -> None:
    by_code = {item.code: index for index, item in enumerate(sections["positions"])}
    for code, name, values in POSITIONS:
        index = by_code.get(code)
        if index is None:
            # Новая должность — косвенная: в смету блока она попадёт, только
            # когда человек классифицирует её и включит в состав бригады.
            sections["positions"].append(_new(code, name, {"category": "INDIRECT", **values}))
            report.added.append(f"positions:{code}")
            continue
        updated, filled = _fill(sections["positions"][index], values)
        if filled:
            sections["positions"][index] = updated
            report.filled.append(f"positions:{code}: {', '.join(filled)}")


def _driller_scales(sections: dict[str, list[ReferenceItem]], report: PayrollSeedReport) -> None:
    for code in SCALED_POSITIONS:
        index = next(
            (
                i
                for i, item in enumerate(sections["labor_rates"])
                if item.is_active
                and item.payload.get("position_code") == code
                and _empty(item.payload.get("condition_code"))
            ),
            None,
        )
        if index is None:
            # Новая ставка без условия бурения сменила бы выбор ставки в
            # расчёте по ставкам (`labor._labor_rate`) — не заводим.
            report.skipped.append(f"labor_rates:{code}: нет ставки без условия бурения, шкала не заведена")
            continue
        rate = sections["labor_rates"][index]
        if not _empty(rate.payload.get("scale_type")):
            continue
        updated, filled = _fill(rate, DRILLER_SCALE)
        sections["labor_rates"][index] = updated
        report.filled.append(f"labor_rates:{rate.code}: {', '.join(filled)}")


def _extra_tariffs(sections: dict[str, list[ReferenceItem]], report: PayrollSeedReport) -> None:
    index = next((i for i, item in enumerate(sections["organization_rates"]) if item.is_active), None)
    if index is None:
        report.skipped.append("organization_rates: нет действующей записи, доп. тариф не заведён")
        return
    updated, filled = _fill(
        sections["organization_rates"][index], {"extra_tariffs": [dict(row) for row in EXTRA_TARIFFS]}
    )
    if filled:
        sections["organization_rates"][index] = updated
        report.filled.append(f"organization_rates:{updated.code}: extra_tariffs")


def _payroll_params(sections: dict[str, list[ReferenceItem]], report: PayrollSeedReport) -> None:
    if any(str(item.payload.get("year")) == PAYROLL_YEAR for item in sections["payroll_params"] if item.is_active):
        return
    code = f"PAYROLL_PARAMS_{PAYROLL_YEAR}"
    sections["payroll_params"].append(_new(code, f"Параметры ФОТ {PAYROLL_YEAR}", PAYROLL_PARAMS))
    report.added.append(f"payroll_params:{code}")


def _bit_diameters(sections: dict[str, list[ReferenceItem]]) -> set[Decimal]:
    materials = {item.code: item for item in sections["materials"] if item.is_active}
    found: set[Decimal] = set()
    for condition in sections["drilling_conditions"]:
        if not condition.is_active:
            continue
        material = materials.get(str(condition.payload.get("bit_material_code") or ""))
        raw = material.payload.get("diameter_mm") if material is not None else None
        if _empty(raw):
            continue
        found.add(Decimal(str(raw)).normalize())
    return found


def _drilling_difficulty(sections: dict[str, list[ReferenceItem]], report: PayrollSeedReport) -> None:
    if any(item.is_active for item in sections["drilling_difficulty"]):
        return
    diameters = sorted({Decimal(value) for value in OWNER_DIAMETERS_MM} | _bit_diameters(sections))
    payload = {
        "hardness": [dict(row) for row in HARDNESS_BANDS],
        # Стартовое k = Ø / 152 (показатель 1) до калибровки по факту.
        "diameter": [
            {
                "diameter_mm": format(diameter, "f"),
                "k": format((diameter / BASE_DIAMETER_MM).quantize(Decimal("0.01"), ROUND_HALF_UP), "f"),
            }
            for diameter in diameters
        ],
    }
    code = "DRILLING_DIFFICULTY_BASE"
    sections["drilling_difficulty"].append(_new(code, "Сложность бурения: база f 10, Ø 152 мм", payload))
    report.added.append(f"drilling_difficulty:{code}")


def _downtime_reasons(sections: dict[str, list[ReferenceItem]], report: PayrollSeedReport) -> None:
    known = {item.code for item in sections["downtime_reasons"]}
    for code, name, excusable, planned in DOWNTIME_REASONS:
        if code in known:
            continue
        sections["downtime_reasons"].append(
            _new(code, name, {"excusable": excusable, "planned_maintenance": planned})
        )
        report.added.append(f"downtime_reasons:{code}")


__all__ = ["PayrollSeedReport", "seed_payroll_references"]
```

Создать `scripts/seed_payroll_references.py`:

```python
"""Справочники методики ФОТ по файлу владельца поверх текущей ревизии (TASK-010).

По умолчанию — сухой прогон: печатает отчёт, ошибки и предупреждения проверки
и ничего не пишет; публикация новой ревизии — с `--publish`, только если
ошибок нет. Правила сида — в `cost/v2/payroll_defaults.py`.
Локально: PYTHONPATH=. BLASTEX_DATABASE_URL=... python scripts/seed_payroll_references.py
На проде: docker exec -w /app -e PYTHONPATH=/app blastex-api python scripts/seed_payroll_references.py --publish
"""
from __future__ import annotations

import argparse
import json
import os

from cost.v2.db_repository import PostgresEconomicsRepository
from cost.v2.payroll_defaults import seed_payroll_references
from cost.v2.references import has_validation_errors, validate_reference_sections


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--organization", default="default")
    parser.add_argument("--publish", action="store_true", help="опубликовать новую ревизию")
    parser.add_argument("--comment", default="Справочники методики ФОТ по файлу «Расчёт заработной платы» 2026")
    args = parser.parse_args()

    database_url = os.getenv("BLASTEX_DATABASE_URL", "").strip()
    if not database_url:
        raise SystemExit("Задайте BLASTEX_DATABASE_URL для базы project1.")

    repository = PostgresEconomicsRepository(database_url)
    current = repository.get_reference_snapshot(args.organization)
    sections, report = seed_payroll_references(current)
    issues = validate_reference_sections(sections)
    output = {
        "base_revision": current.revision_id,
        "report": report.to_dict(),
        "valid": not has_validation_errors(issues),
        "issues": [issue.to_dict() for issue in issues if issue.level == "error"],
        "warnings": [issue.to_dict() for issue in issues if issue.level == "warning"],
    }
    if args.publish and output["valid"]:
        published = repository.publish_references(
            args.organization,
            "seed_payroll_references",
            current.revision_id,
            {name: [item.to_dict() for item in items] for name, items in sections.items()},
            args.comment,
        )
        output["published_revision"] = published.revision_id
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
```

- [ ] **Шаг 4: прогон**

Run: `.venv/bin/python -m pytest tests/test_payroll_defaults.py tests/test_crew_defaults.py tests/test_seed_defaults.py -q`
Expected: PASS.

Run: `env -u BLASTEX_DATABASE_URL PYTHONPATH=. .venv/bin/python scripts/seed_payroll_references.py`
Expected: выход с сообщением `Задайте BLASTEX_DATABASE_URL для базы project1.` (скрипт импортируется без ошибок).

- [ ] **Шаг 5: коммит**

```bash
git add cost/v2/payroll_defaults.py scripts/seed_payroll_references.py tests/test_payroll_defaults.py
git commit -m "$(cat <<'EOF'
TASK-010 PR 1: сид справочников ФОТ по файлу владельца — только пустые поля, идемпотентно

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
)"
```

---

### Задача 7: подписи перечислений и подсказки кривой в форме

**Файлы:**
- Изменить: `frontend/src/pages/references/enumLabels.ts:15-17`
- Создать: `frontend/src/pages/references/enumLabels.test.ts`
- Изменить: `frontend/src/lib/referenceDerived.ts:26-27`, `:128-137`
- Тест: `frontend/src/lib/referenceDerived.test.ts`

**Интерфейсы:**
- Использует: коды Задачи 2; ключи `scale_type`, `norm_per_shift`, `rate_norm`, `ceiling_per_shift`, `rate_ceiling`.
- Даёт: `enumLabel` для 15 новых кодов; `derivedHints("labor_rates", …)` — подсказки «Показатель кривой γ» и
  «Премия за смену: норма · потолок».

- [ ] **Шаг 1: падающие тесты**

Создать `frontend/src/pages/references/enumLabels.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { enumLabel } from "./enumLabels";

describe("подписи перечислений методики ФОТ", () => {
  it("коды должностей и шкалы подписаны по-русски", () => {
    expect(enumLabel("PIECE_PROGRESSIVE")).toBe("Сдельно-прогрессивная");
    expect(enumLabel("NORMALIZED_METERS")).toBe("Приведённые метры бурения");
    expect(enumLabel("CURVE_POWER")).toBe("Степенная кривая");
    expect(enumLabel("SECTION_OUTPUT")).toBe("Выработка участка");
    expect(enumLabel("DRILLING_BLASTING")).toBe("Буровзрывной участок");
  });

  it("класс условий труда показывается как есть", () => {
    expect(enumLabel("3.2")).toBe("3.2");
  });
});
```

В `frontend/src/lib/referenceDerived.test.ts` перед `describe("ставки организации", …)` добавить:

```ts
describe("подсказки шкалы сдельной премии", () => {
  const ctx = context({});
  const curve = {
    scale_type: "CURVE_POWER",
    norm_per_shift: "115.3846",
    rate_norm: "45",
    ceiling_per_shift: "184.6154",
    rate_ceiling: "168.66",
  };

  it("степенная кривая: γ и премия за смену на норме и потолке", () => {
    const hints = derivedHints("labor_rates", "RATE_DRILLER", curve, ctx);
    expect(hints.map((hint) => hint.label)).toEqual(["Показатель кривой γ", "Премия за смену: норма · потолок"]);
    expect(hints[0].value).toBe("2,811");
    expect(hints[1].value.replace(/\s/g, " ")).toBe("5 192,31 ₽ · 12 000,05 ₽");
  });

  it("линейная кривая: трапеция между узлами, без γ", () => {
    const hints = derivedHints("labor_rates", "RATE_DRILLER", { ...curve, scale_type: "CURVE_LINEAR" }, ctx);
    expect(hints).toHaveLength(1);
    // 12 588,23 × 13 смен = 163 647 ₽ — эталон линейной кривой при 2 400 м (решения, §7).
    expect(hints[0].value.replace(/\s/g, " ")).toBe("5 192,31 ₽ · 12 588,23 ₽");
  });

  it("без полного набора узлов, у ступеней и у несогласованной кривой подсказки нет", () => {
    expect(derivedHints("labor_rates", "R", { ...curve, rate_ceiling: "" }, ctx)).toEqual([]);
    expect(derivedHints("labor_rates", "R", { scale_type: "STEP", tiers: [] }, ctx)).toEqual([]);
    expect(derivedHints("labor_rates", "R", { ...curve, ceiling_per_shift: "100" }, ctx)).toEqual([]);
  });
});
```

- [ ] **Шаг 2: убедиться, что падает**

Run: `cd frontend && npx vitest run src/pages/references/enumLabels.test.ts src/lib/referenceDerived.test.ts`
Expected: FAIL — `enumLabel("PIECE_PROGRESSIVE")` возвращает код; `derivedHints("labor_rates", …)` — `[]`.

- [ ] **Шаг 3: реализация**

`enumLabels.ts`: после `NET: "На руки",` добавить

```ts
  // Методика ФОТ
  DRILLING_BLASTING: "Буровзрывной участок",
  TRANSPORT: "Транспорт и спецтехника",
  WAREHOUSE: "Склад и производство",
  MAINTENANCE: "Техническое обслуживание",
  PIECE_PROGRESSIVE: "Сдельно-прогрессивная",
  PIECE_BONUS: "Сдельно-премиальная",
  TIME_BONUS: "Повременно-премиальная",
  OWN_OUTPUT: "Своя выработка",
  SECTION_OUTPUT: "Выработка участка",
  PLAIN: "Без приведения",
  NORMALIZED_METERS: "Приведённые метры бурения",
  CURVE_POWER: "Степенная кривая",
  CURVE_LINEAR: "Линейная кривая",
  STEP: "Ступени",
```

`referenceDerived.ts`: после `const DEFAULT_VAT_RATE = 0.2;` добавить

```ts
// Премия за смену — рубли с копейками: узлы кривой хранятся с четырьмя знаками.
const RUBLES = new Intl.NumberFormat("ru-RU", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
```

перед `export function derivedHints(` добавить

```ts
/**
 * Кривая сдельной премии: показатель γ и премия за смену на норме и потолке.
 *
 * Формулы — те же, что у модели ФОТ (TASK-010 §2.3): на норме
 * p = rate_norm × norm; степенная кривая r(m) = rate_norm × (m / norm)^γ даёт
 * на потолке p = rate_norm × norm × (1 + ((ceiling / norm)^(γ+1) − 1) / (γ + 1)),
 * линейная — трапецию. Владелец видит, что меняет каждая правка узлов.
 */
function laborRateHints(payload: Record<string, unknown>): DerivedHint[] {
  const shape = payload.scale_type;
  if (shape !== "CURVE_POWER" && shape !== "CURVE_LINEAR") return [];
  const norm = parseNumber(payload.norm_per_shift);
  const rateNorm = parseNumber(payload.rate_norm);
  const ceiling = parseNumber(payload.ceiling_per_shift);
  const rateCeiling = parseNumber(payload.rate_ceiling);
  if (norm === null || rateNorm === null || ceiling === null || rateCeiling === null) return [];
  if (norm <= 0 || rateNorm <= 0 || ceiling <= norm || rateCeiling < rateNorm) return [];

  const atNorm = rateNorm * norm;
  if (shape === "CURVE_LINEAR") {
    const atCeiling = atNorm + ((ceiling - norm) * (rateNorm + rateCeiling)) / 2;
    return [{ label: "Премия за смену: норма · потолок", value: `${RUBLES.format(atNorm)} ₽ · ${RUBLES.format(atCeiling)} ₽` }];
  }
  const gamma = Math.log(rateCeiling / rateNorm) / Math.log(ceiling / norm);
  const atCeiling = atNorm * (1 + (Math.pow(ceiling / norm, gamma + 1) - 1) / (gamma + 1));
  return [
    { label: "Показатель кривой γ", value: formatNumber(gamma) },
    { label: "Премия за смену: норма · потолок", value: `${RUBLES.format(atNorm)} ₽ · ${RUBLES.format(atCeiling)} ₽` },
  ];
}
```

в `derivedHints` после строки `drilling_conditions` добавить
`  if (section === "labor_rates") return laborRateHints(payload);`.

- [ ] **Шаг 4: прогон**

Run: `cd frontend && npx vitest run src/pages/references src/lib && npx tsc -b`
Expected: PASS, `tsc` без вывода.

- [ ] **Шаг 5: коммит**

```bash
git add frontend/src/pages/references/enumLabels.ts frontend/src/pages/references/enumLabels.test.ts frontend/src/lib/referenceDerived.ts frontend/src/lib/referenceDerived.test.ts
git commit -m "$(cat <<'EOF'
TASK-010 PR 1: подписи кодов оплаты труда и подсказки γ и премии за смену в форме ставки

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
)"
```

---

### Задача 8: документация

**Файлы:**
- Изменить: `Docs/REFERENCES_MODEL.md` — §2, §3, §4, §5, §9
- Изменить: `Docs/specs/2026-09-13-task-010-payroll-decisions.md` — Т8, Т10, Т16, §5 PR 1, §7

- [ ] **Шаг 1: `Docs/REFERENCES_MODEL.md`**

В таблицу §2 после строки `shift_hours` добавить:

```
| `extra_tariffs` | список `{work_conditions_class, rate}` | 3.2 → 0,04 | доп. тариф взносов по классу условий труда (ст. 428 НК РФ); у классов 1 и 2 нет |
```

В §3 после таблицы `positions` добавить:

```
Нормы оплаты труда (TASK-010):

| Поле | Тип | Пример | Комментарий |
| --- | --- | --- | --- |
| `department` | `DRILLING_BLASTING` / `TRANSPORT` / `WAREHOUSE` / `MAINTENANCE` | DRILLING_BLASTING | участок штатного расписания |
| `pay_system` | `PIECE_PROGRESSIVE` / `PIECE_BONUS` / `TIME_BONUS` | PIECE_PROGRESSIVE | по умолчанию повременно-премиальная |
| `work_conditions_class` | `1` … `4` | 3.2 | класс СОУТ: доп. тариф, 36-часовая неделя для 3.3, 3.4, 4 |
| `week_hours_override` | `40` / `36` | — | пусто — неделя из класса |
| `hazard_pct` | доля оклада | 0,04 | надбавка за вредность |
| `extra_vacation_days` | дн | 7 | база резерва доп. отпуска |
| `night_hours_per_shift` | ч/см | 8 | ночных часов в ночную смену |
| `output_unit` | ссылка на `units` | `M` | единица выработки |
| `output_source` | `OWN_OUTPUT` / `SECTION_OUTPUT` | OWN_OUTPUT | горнорабочий — от выработки участка |
| `difficulty` | `PLAIN` / `NORMALIZED_METERS` | NORMALIZED_METERS | приведённые метры: метры × k крепости × k диаметра |
```

В §3 после таблицы `labor_rates` добавить:

```
Шкала сдельной премии и КПЭ (TASK-010) лежат в ставке плоско — форма не умеет вложенный объект:

| Поле | Тип | Пример |
| --- | --- | --- |
| `kpi_bonus_pct` | доля оклада | 0 — премия КПЭ при плане 100 % |
| `scale_type` | `CURVE_POWER` / `CURVE_LINEAR` / `STEP`, пусто — шкалы нет | CURVE_POWER |
| `norm_per_shift`, `rate_norm` | ед./см, ₽/ед. | 115,3846 прив. м/см, 45 ₽ |
| `ceiling_per_shift`, `rate_ceiling` | ед./см, ₽/ед. | 184,6154 прив. м/см, 168,66 ₽ |
| `tiers` | список `{upto_per_shift, rate}` | для `STEP`; у последней ступени границы нет |

Норма и потолок — загрузка станка: метры на смену = скорость бурения × чистое время. Потолок 184,6 м/смену при
~20 м/ч — 9,2 ч бурения из 11, выше станок почти не бурит. γ = ln(rate_ceiling / rate_norm) /
ln(ceiling / norm) вычисляется, не вводится; форма показывает γ и премию за смену на норме и потолке.

Проверки: у кривой заданы все узлы, потолок выше нормы, расценка на потолке не ниже расценки на норме; у ступеней
границы возрастают, расценки не убывают. Ставка со шкалой — без `condition_code`: породу учитывают приведённые
метры. Потолок выше производительности станков по базовым условиям бурения — предупреждение.

### `payroll_params` — параметры года для ФОТ (новый)

| Поле | Тип | 2026 |
| --- | --- | --- |
| `year` | год | 2026 — одна действующая запись на год |
| `mrot` | ₽/мес | 27 093 — оклад должности без ставки |
| `annual_hours_40`, `annual_hours_36` | ч | 1 972 / 1 774,4 |
| `work_days_year`, `holidays_year` | дн | 247 / 14 |
| `night_pct` | доля | 0,20 |
| `vacation_days_base` | дн | 28 |
| `margin_share_warn` | доля | 0,70 |

Ставки взносов, травматизма и НДФЛ — в `organization_rates`, не здесь.

### `downtime_reasons` — причины простоев (новый)

`excusable` — простой не по вине машиниста, часы вычитаются из эффективных смен; `planned_maintenance` — плановое
ТОиР (всегда вместе с `excusable`), в проверку «списано больше 25 % часов вахты» не входит. Стартовый набор —
10 кодов: ожидание блока, ремонт станка не по вине, взрывные работы, погода, нет воды/топлива/энергии, перегон по
распоряжению, плановое ТОиР; опоздание, поломка по вине, отсутствие.
```

В §4 после `drilling_conditions` добавить:

```
### `drilling_difficulty` — сложность бурения (новый)

Одна действующая запись, база f = 10, Ø 152 мм, k = 1:

- `hardness` — `{f_from, f_to, k}`, интервал `f_from < f ≤ f_to`, строки по возрастанию без разрывов, первая без
  нижней границы, последняя без верхней: ≤ 8 → 0,9; 8–12 → 1,0; 12–16 → 1,1; 16–18 → 1,2; > 18 → 1,3.
- `diameter` — `{diameter_mm, k}`, стартовое k = Ø / 152: 110 → 0,72 … 250 → 1,64. Каждая коронка из
  `drilling_conditions.bit_material_code` с диаметром должна быть в таблице (иначе ошибка ревизии), коронка без
  диаметра — предупреждение.

Порода с `hardness_f ≤ 0` — ошибка ревизии; пустая крепость допустима.
```

В §5 в таблицу `sites` добавить:

```
| `shift_days_on` / `shift_days_off` | дн | 15 / 15 — график вахты |
| `travel_days` | дн | 2 |
| `night_shift_share` | доля | 0,5 |
| `maintenance_shifts` | см за вахту | 2 — сверяется с долей ТОиР станка: 15 × 0,14 / 1,14 = 1,84, расхождение больше 0,5 — предупреждение |
| `regional_coefficient` / `northern_pct` | доля | 0,15 / 0 |
| `contract_k` | число | 1 — множитель приведённых метров по договору |
| `geology` | список `{rock_code, share}` | доли пород, сумма 1 ± 0,001; запасной путь без паспортов |
```

и под таблицей: `Умолчания полей вахты — график компании: запись, заведённая раньше, считается по ним.
Длительность смены объекта — в PR 3a TASK-010 вместе с общим резолвером.`

В §9 добавить строку:

```
| Расчёт заработной платы (штатное расписание) | `positions` + `labor_rates` (шкала) + `payroll_params` + `drilling_difficulty` + `downtime_reasons` + поля `sites`; на проде — `scripts/seed_payroll_references.py`, не импорт xlsx |
```

- [ ] **Шаг 2: документ решений**

В таблице §3:

- Т8, колонка «Решение»: дописать в конец «`sites.shift_hours` заводится в PR 3a вместе с резолвером (решение
  владельца 14.09.2026)».
- Т10: дописать «У существующих записей заполняются только пустые ключи payload, заданные значения не меняются;
  семь должностей файла сопоставлены с `POSITION_LABOR_*` (решение владельца 14.09.2026, план
  `Docs/plans/2026-09-14-task-010-pr1-references.md`)».
- Т16, колонка «Причина»: «(0,14 × 13 = 1,84 смены)» → «(из вахты 15 смен на ТОиР уходит 15 × 0,14 / 1,14 =
  1,84 смены)».

В §5 абзац «PR 1 — справочники»: `` `maintenance_shifts`, `geology`, `shift_hours: None`); `` →
`` `maintenance_shifts`, `geology`; `shift_hours: None` — в PR 3a); ``.

В §7 «Справочники и формы»: «идемпотентен, существующие записи не меняет» → «идемпотентен, заданные значения
существующих записей не меняет».

- [ ] **Шаг 3: коммит**

```bash
git add Docs/REFERENCES_MODEL.md Docs/specs/2026-09-13-task-010-payroll-decisions.md
git commit -m "$(cat <<'EOF'
TASK-010 PR 1: справочники методики ФОТ в модели справочников, уточнения Т8, Т10, Т16

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
)"
```

---

### Задача 9: проверка, стенд, PR и ревью

- [ ] **Шаг 1: полный прогон**

```bash
.venv/bin/python -m pytest tests -q
```

Expected: 0 failed. На `main` было 1375 passed, 32 skipped; новых — 66 (с параметризацией).

```bash
cd frontend && npx vitest run && npx tsc -b
```

Expected: всё зелёное. `git status` чистый, iCloud-дублей в ветке нет (`git diff --stat origin/main...HEAD`).

- [ ] **Шаг 2: стенд (api-stand :8020 / frontend-stand :5181)**

`preview_start` читает `.claude/launch.json` только основного чекаута, а `.claude/stand/stand_app.py` держит `REPO`
на основном чекауте. Порядок:

1. Скопировать (не коммитить) `.claude/stand/` из основного чекаута в worktree; в копии `stand_app.py` —
   `REPO = Path(__file__).resolve().parents[2]`.
2. **Спросить пользователя** и только после согласия временно добавить в `.claude/launch.json` основного чекаута
   конфигурации `api-stand-pr1` (порт 8020) и `frontend-stand-pr1` (vite 5181, `BLASTEX_API_URL=http://127.0.0.1:8020`)
   с абсолютными путями worktree; после проверки убрать.
3. Опубликовать сид на стенде: `GET /api/v1/economics/references/snapshot`, прогнать снимок через
   `seed_payroll_references` (однострочный скрипт из worktree), `POST /api/v1/economics/references/publish`.

Проверить в интерфейсе справочников:

- «Персонал и бригады» показывает «Параметры года для ФОТ» и «Причины простоев», «Бурение и условия блока» —
  «Сложность бурения»; бейджи предупреждений у пустых разделов до публикации сида.
- Форма ставки машиниста: группа «Шкала сдельной премии», селект «Степенная кривая», подсказки «Показатель кривой γ
  2,811» и «Премия за смену: норма · потолок 5 192,31 ₽ · 12 000,05 ₽»; «Применить» без правок не меняет черновик.
- Ставка: расценка на потолке 40 → ошибка под полем «Расценка на потолке»; ступени с убывающей расценкой → ошибка
  под «Расценка» второй строки.
- Форма «Сложность бурения»: пять строк крепости и восемь диаметров карточками; разрыв интервала → ошибка под
  «Крепость от» нужной строки.
- Объект: группа «Вахта и оплата труда» со значениями 15 / 15 / 2 / 0,5 / 2 / 0,15 / 0 / 1; «Плановая геология»
  0,5 + 0,4 → ошибка «Сумма долей пород — 0.9, а должна быть 1».
- Должность: сегменты «Система оплаты» с русскими подписями, селект «Класс условий труда».
- Выгрузка xlsx → загрузка того же файла → «Применить» → проверка ревизии без ошибок.

Скриншоты формы ставки и «Сложности бурения» — в PR (ветка `assets/task-010-pr1`, как у PR 0).

- [ ] **Шаг 3: PR**

```bash
git push -u origin feat/task-010-pr1-references
gh pr create --title "TASK-010 PR 1: справочники методики ФОТ" --body "$(cat <<'EOF'
Справочники для расчёта ФОТ по методике владельца (Docs/specs/2026-09-13-task-010-payroll-decisions.md, §5 PR 1). Расчёт сметы не меняется: `cost/model/` не тронут, тест сметы до и после сида совпадает.

**Схемы**
- `positions`: участок, система оплаты, класс условий труда, неделя вручную, вредность, доп. отпуск, ночные часы, единица и источник выработки, приведение метров.
- `labor_rates`: премия КПЭ и плоская шкала сдельной премии (Т5) — `scale_type` CURVE_POWER / CURVE_LINEAR / STEP, узлы кривой, `tiers`. Шкала рядом с условием бурения — ошибка (Т1).
- `organization_rates.extra_tariffs` — доп. тариф взносов по классу (Т2).
- `sites`: вахта 15/15, дорога, доля ночных, плановое ТОиР, РК, северная, договорной k, плановая геология. Длительность смены объекта — в PR 3a (решение владельца).
- `rocks.hardness_f ≤ 0` — ошибка (§1, Т7).
- Новые разделы: «Параметры года для ФОТ», «Сложность бурения», «Причины простоев» (Т17).

**Проверки ревизии** (Т15, Т16): пустой новый раздел — предупреждение; дубли года и второй записи сложности, коронка без коэффициента диаметра — ошибка; потолок выше производительности станка по базовым условиям, плановое ТОиР против доли ТОиР станка, вредный класс без доп. тарифа, коронка без диаметра — предупреждения. Ошибки внутри списков адресованы подполю строки (`tiers.1.rate`).

**Сид** (Т10): `scripts/seed_payroll_references.py` — сухой прогон по умолчанию, `--publish` только без ошибок. Заполняет пустые ключи существующих записей, заданные значения не меняет, идемпотентен. 14 должностей файла (7 сопоставлены с `POSITION_LABOR_*`), кривая машиниста и помощника в ставке без условия бурения, параметры 2026, таблицы крепости и диаметров, 10 причин простоев, доп. тариф ст. 428 НК РФ, единица KM.

**Интерфейс**: подписи новых кодов; подсказки γ и премии за смену в форме ставки (Т6). Разделоспецифичных компонентов нет; защитный тест не пустит в схемы вложенный объект или флаг/дату в строке списка, пока форма их не умеет.

Решения планировщика — в плане, раздел «Решения планировщика». На нынешней матрице условий (12 м/ч) предупреждение «потолок выше производительности» горит — ожидаемо до правки данных Т19.

После деплоя: сухой прогон сида на проде и публикация — по согласованию; если в породах есть `hardness_f = 0`, сухой прогон покажет ошибку и публиковать нельзя до правки пород.

План: Docs/plans/2026-09-14-task-010-pr1-references.md.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

- [ ] **Шаг 4: ревью** — `/code-review` на диапазоне PR; найденное исправить отдельными коммитами. Затем прочитать
замечания Codex: `gh api repos/dvotapi/BlastEX/pulls/<N>/comments` (бот `chatgpt-codex-connector`) и закрыть
каждое до просьбы о слиянии.

- [ ] **Шаг 5: после слияния** — деплой идёт сам (сборка на VPS около 50 минут, миграций нет). Сид на проде
запускается только с согласия пользователя: сначала сухой прогон
`docker exec -w /app -e PYTHONPATH=/app blastex-api python scripts/seed_payroll_references.py`, отчёт — пользователю,
затем `--publish`.
