# TASK-010 PR 0b — ротационная численность экипажа

> **Для исполнителя-агента:** обязательный навык — superpowers:subagent-driven-development (рекомендуется) или
> superpowers:executing-plans. Шаги отмечаются чекбоксами (`- [ ]`).

**Цель:** ФОТ прямого персонала блока платит за каждый метр и каждую смену техники людям, которые в этой смене
работают, а не всему штату ротации. Месячный оклад штата экипажа техники распределяется по плановым сменам
машины.

**Архитектура:** правка одного модуля норм `cost/model/labor.py`. Численность в смене берётся из состава бригады,
штат на ротацию выводит модель. Цены по-прежнему только в справочниках (`labor_rates`, `organization_rates`).
Фронт получает новые натуральные величины через существующий `natural.values` и одну подпись в `LaborSection`.
API и схемы ответа не меняются.

**Стек:** Python 3.13 + Decimal, pytest; React 18 + TypeScript, vitest + @testing-library/react.

**Спецификация:** `Docs/specs/2026-09-13-task-010-payroll-decisions.md` — §3 Т20, §5 (PR 0b), §6 (риск «было/стало
расходится в разы»), §7 («регрессия не меняется, кроме осознанного сдвига PR 0b»). Задача —
`TASK-010 Зарплата персонала по объектам 3.md` (не в git). Модель — `Docs/COST_MODEL.md`.

## Контекст

Код проверен на `main` = `67e9d52`. В `cost/model/labor.py` у численности два смысла:

- явная `headcount > 0` из состава бригады (`crew_templates.members[].headcount`, параметр вкладки
  `crew[].headcount`) уже работает как «человек в смене»: умножается на смены блока (`:127`) и на драйвер
  сделки (`:322`);
- `headcount = 0` уходит в `_headcount` (`:254-275`), который возвращает **штат на ротацию**
  `⌈плановые смены техники / норм_смен человека⌉`. Это число подставляется туда же, как будто все три
  бурильщика ротации одновременно стоят в каждой смене станка.

Итог на фикстуре `tests/model_fixtures.py` (в шаблоне бурильщик записан как `"headcount": "0"`, так же в
`tests/conftest.py` API): 60 000 ₽/мес, норма 15 смен, станок 40 плановых смен, 13 953,488372 м за
116,2790698 смены, расценка 150 ₽/м.

| | Сейчас | После PR 0b |
| --- | --- | --- |
| Оклад | 60 000 / 15 × 116,28 × **3** = 1 395 348,84 | 60 000 × 3 / 40 × 116,28 = 523 255,81 |
| Сделка | 150 × 13 953,49 × **3** = 6 279 069,77 | 150 × 13 953,49 × 1 = 2 093 023,26 |
| `LABOR_POS_DRILLER` | 7 674 418,60 | 2 616 279,07 |
| Взносы 30,42 % (только бурильщик) | 2 334 558,14 | 795 872,09 |
| Резерв отпусков 20 % | 2 001 795,35 | 682 430,23 |
| **ФОТ бурильщика за блок** | **12 010 772,09** | **4 094 581,40** |
| Суточные при 1 000 + 1 000 ₽ | 697 674,42 | 232 558,14 |
| Маржинальная цена м³ (движок, бригада фикстуры) | 361,33 | 229,39 |

Каждый метр оплачивался 3 раза (450 ₽/м вместо 150), каждая смена станка — 3 окладами человеко-смены.

Кто читает затронутые значения:

- `crew_shifts.*` и `crew_headcount.*` (`labor.py:134-137`) пишутся в `natural.values`. Читают их только
  `tests/test_model_labor.py:37-42`, общая таблица вкладки «Ресурсы» (`ResourcesTab.tsx:13-17`, выводит все
  ключи как есть) и лист выгрузки xlsx (`export_xlsx.py:106`, тоже все ключи). `unit.py`, `markup.py`,
  `engine.py`, API и `LaborSection` их не читают.
- `LaborLine` (`labor.py:40-48`) возвращает только `labor.compute`; `engine.py:52` результат не использует.
- `sensitivity._scale_crew` масштабирует `headcount` состава — теперь это люди в смене; менять не нужно.
- Строки `LABOR_*`, `LABOR_CONTRIBUTIONS`, `LABOR_VACATION_RESERVE`, `LABOR_PER_DIEM` дальше идут в
  `markup.layer_totals` как обычный `PROJECT_DIRECT`: их формат не меняется.

Прогон всего `tests/` с кодом этого плана, подставленным в память: падают ровно два теста, оба с осознанным
сдвигом (Задача 1). Регрессия сметы проходит, но раздел 2.3 сдвигается на +0,57 % (Задача 2).

## Модель после правки

Решения владельца 13.09.2026 (заданы в чате планирования):

1. `headcount` в составе бригады — **человек в смене** `h`: сколько людей должности одновременно работает в
   одной смене (бурильщик 1, взрывники 2).
2. Оклад экипажа техники считается **по плановым сменам техники**: месячный ФОТ штата делится на плановые
   смены машины, как её амортизация (CLAUDE.md: «постоянные затраты техники — по её плановым сменам»; Т11).

Обозначения: `S` — смены на блок (`_shifts_per_block`, не меняется), `M` — оклад `labor_rates.fixed_monthly_rub`,
`n` — `positions.norm_shifts_per_month` (умолчание 21), `P` — плановые смены техники.

- `h = headcount`, если `headcount > 0`, иначе 1. Ноль остаётся прежним «по экипажу техники»: так записан
  бурильщик в фикстурах и API-тестах, а очистка поля на вкладке даёт `"0"` (`LaborSection.tsx:100`).
- **Экипаж техники** — должность, у операции которой есть техника в `CREW_EQUIPMENT_PARAM` (станок, СЗМ,
  доставщик, тягач эмульсии), и эта техника выбрана на вкладке.
- `P`: у станка `params.rig_plan_shifts or norm_shifts_per_month типа` — ровно как амортизация в
  `drilling.py:143`; у остальной техники `context.machine_plan_shifts(equipment)` — как в `equipment.py:40`.
- Штат на ротацию `N = ⌈P × h / n⌉`. Двое в смене при `P = 35`, `n = 15` дают `⌈4,67⌉ = 5`, а не `2 × 3 = 6`.

| Часть строки `LABOR_<должность>` | Экипаж техники, `P > 0` | Остальные должности; техника без плана |
| --- | --- | --- |
| Оклад | `M × N / P × S` | `M / n × S × h` |
| Сделка | `расценка × драйвер / piece_unit × h` | то же |
| Количество строки | `S × h` чел·см | то же |
| Суточные (`_per_diem`) | `S × h × (per_diem_rub + lodging_rub)` | то же |
| Взносы, резерв | на `Σ` строк, как сейчас | то же |
| NET-база | строка ÷ (1 − НДФЛ), как сейчас | то же |

- Выбранная техника без плановых смен (`P ≤ 0`, например `machine_plan_shifts = {"SZM_12T": 0}`) даёт
  предупреждение `Для техники SZM_12T не заданы плановые смены в месяц: оклад должности POS_SZM_DRIVER
  посчитан по норме смен человека.` и оклад по второй колонке — без исключения.
- Натуральные величины: `crew_shifts.<pos>` (как было), `crew_per_shift.<pos>` = `h`, `crew_rotation.<pos>` = `N`
  (только у экипажа техники с `P > 0`). Ключ `crew_headcount.<pos>` убирается: старые сохранённые прогоны
  показывают его со старым смыслом, а новый ключ не выдаёт себя за прежний.
- Строки по должностям без техники (мастер, взрывники) не меняются. Не меняется и экипаж, у которого
  `P = n` (водитель СЗМ фикстуры: 20 и 20).

Самостоятельные решения планировщика (в отчёт PR): ноль → один человек в смене; новые ключи вместо
переосмысления `crew_headcount`; «нет плана» — предупреждение и оклад по норме, а не ноль; единица в
`LaborSection` — «чел./см» и подпись «Штат на ротацию».

## Глобальные ограничения

- Нормы — только в `cost/model/`, цены — только в справочниках; новых полей справочников нет.
- Отсутствующие данные — предупреждение (`context.warn`) и нулевая или запасная строка, не исключение.
- Постоянные затраты техники — по её плановым сменам: база `P` та же, что у амортизации этой машины.
- Интерфейс не хранит знаний о полях справочников; подпись поля формы — `title` схемы. JSON пользователю не
  показывается.
- Все суммы в Decimal; в тестах сравнение через `quantize(Decimal("0.01"))`, без относительного допуска.
- Python — `.venv/bin/python -m pytest …` (в worktree `.venv` и `frontend/node_modules` — симлинки на основной
  чекаут).
- iCloud-дубли (`* 2.py`, `* 3.ts`) не трогать и не коммитить; `git add` — только перечисленных файлов.
- Сообщения коммитов — по-русски, с последней строкой `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`.

## Файлы

- Изменить: `cost/model/labor.py` — `LaborLine.rotation_headcount`, `CrewRotation`, `_per_shift_headcount`,
  `_crew_rotation`, `_equipment_plan_shifts`, `_fixed_amount`; `compute`, `_piece_amount`, `_per_diem` берут `h`;
  `_headcount` удаляется.
- Изменить: `tests/test_model_labor.py` — тест ротации вместо `:33-42`, тесты на сумму.
- Изменить: `tests/test_model_equipment_emulsion.py:102` — осознанный сдвиг оклада водителя тягача.
- Изменить: `tests/test_model_regression_smeta_2026_01.py` — docstring и тест сдвига раздела 2.3.
- Изменить: `tests/fixtures/smeta_2026_01/README.md` — расхождение 2.3.
- Изменить: `cost/v2/schemas/labor.py:78` — `title` «Человек в смене».
- Изменить: `tests/test_reference_schemas.py:172` — подпись в пути ошибки.
- Изменить: `frontend/src/pages/economics/sections/LaborSection.tsx`, `LaborSection.test.tsx`.
- Изменить: `Docs/COST_MODEL.md`, `Docs/specs/2026-09-13-task-010-payroll-decisions.md` (строка Т20).

---

### Задача 0: рабочее дерево

Ветка и worktree готовятся в чате планирования вместе с коммитом этого плана.

- [ ] **Шаг 1: проверить ветку и окружение**

```bash
git -C .claude/worktrees/task-010-pr0b branch --show-current
ls -l .claude/worktrees/task-010-pr0b/.venv .claude/worktrees/task-010-pr0b/frontend/node_modules
```

Expected: `feat/task-010-pr0b-rotation-headcount`; обе ссылки ведут в `/Users/apple/Documents/Проекты/BlastEX/…`.
Дальше все команды — из корня worktree.

- [ ] **Шаг 2: базовый прогон**

Run: `.venv/bin/python -m pytest tests/test_model_labor.py tests/test_model_equipment_emulsion.py tests/test_model_regression_smeta_2026_01.py -q`
Expected: PASS.

---

### Задача 1: люди в смене и штат на ротацию в `labor.py`

**Файлы:**
- Изменить: `cost/model/labor.py:39-48`, `:86-175`, `:254-275`, `:306-345`
- Тест: `tests/test_model_labor.py`, `tests/test_model_equipment_emulsion.py:98-102`

**Интерфейсы:**
- Использует: `ModelContext.value/set_value/warn/item/machine_plan_shifts`, `payload_number`, `CREW_EQUIPMENT_PARAM`.
- Даёт: `LaborLine.headcount` (человек в смене), `LaborLine.rotation_headcount: Decimal | None`;
  натуральные величины `crew_per_shift.<pos>`, `crew_rotation.<pos>`; формула строки экипажа техники
  `"{M} ₽/мес × {N} чел / {P} см × {S} см"`. Задачи 2–4 опираются на эти имена.

- [ ] **Шаг 1: написать падающие тесты**

В `tests/test_model_labor.py` заменить `test_driller_shifts_follow_rig_and_headcount_follows_plan` (`:33-42`) и
добавить после `_labor_lines`:

```python
def _money(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"))
```

```python
def test_driller_shifts_follow_rig_and_rotation_follows_plan() -> None:
    """Смены бурильщика — смены станка; в смене один человек, штат на ротацию — из плана станка."""

    context = _context()
    labor.compute(context)

    assert context.value("crew_shifts.POS_DRILLER") == context.value("rig_shifts")
    assert context.value("crew_per_shift.POS_DRILLER") == Decimal("1")
    # ⌈40 смен станка × 1 чел / 15 смен человека⌉
    assert context.value("crew_rotation.POS_DRILLER") == Decimal("3")
    assert context.lineage["crew_rotation.POS_DRILLER"] == "⌈40 см RIG_JK830 × 1 чел / 15 см человека⌉"

    fewer_shifts = _context(rig_plan_shifts=Decimal("25"))
    labor.compute(fewer_shifts)
    assert fewer_shifts.value("crew_rotation.POS_DRILLER") == Decimal("2")

    # Ноль в плане станка — норматив типа, как у амортизации станка в `drilling.py`.
    no_plan = _context(rig_plan_shifts=Decimal("0"))
    labor.compute(no_plan)
    assert no_plan.value("crew_rotation.POS_DRILLER") == Decimal("3")


def test_driller_block_payroll_pays_each_metre_once() -> None:
    """Блок 60 000 м³: 13 953,49 м за 116,28 смены станка, оклад 60 000 ₽, расценка 150 ₽/м.

    До TASK-010 PR 0b: 60 000 / 15 × 116,28 × 3 + 150 × 13 953,49 × 3 = 7 674 418,60 ₽ —
    каждый метр и каждая смена станка оплачивались трём людям ротации, ФОТ со
    взносами и резервом 12 010 772,09 ₽. Теперь оклад штата делится на плановые
    смены станка, а сделка идёт одному человеку в смене: 4 094 581,40 ₽.
    """

    context = _context(crew=(CrewMember("POS_DRILLER", Decimal("0")),))
    driller = labor.compute(context)[0]

    assert driller.headcount == Decimal("1")
    assert driller.rotation_headcount == Decimal("3")
    # 60 000 × 3 / 40 см × 116,28 см
    assert _money(driller.fixed_rub) == Decimal("523255.81")
    # 150 × 13 953,49 × 1
    assert _money(driller.piece_rub) == Decimal("2093023.26")

    line = _line(context, "LABOR_POS_DRILLER")
    assert _money(line.amount_rub) == Decimal("2616279.07")
    assert line.quantity == context.value("rig_shifts")
    assert line.formula.startswith("60000 ₽/мес × 3 чел / 40 см × ")
    contributions = _line(context, "LABOR_CONTRIBUTIONS").amount_rub
    reserve = _line(context, "LABOR_VACATION_RESERVE").amount_rub
    assert _money(contributions) == Decimal("795872.09")
    assert _money(reserve) == Decimal("682430.23")
    assert _money(line.amount_rub + contributions + reserve) == Decimal("4094581.40")


def test_rig_plan_shifts_move_the_fixed_part_only() -> None:
    """25 смен станка: штат 2, смена станка стоит 4 800 ₽ оклада вместо 4 500; сделка та же."""

    context = _context(crew=(CrewMember("POS_DRILLER", Decimal("0")),), rig_plan_shifts=Decimal("25"))
    driller = labor.compute(context)[0]

    assert driller.rotation_headcount == Decimal("2")
    assert _money(driller.fixed_rub) == Decimal("558139.53")
    assert _money(driller.piece_rub) == Decimal("2093023.26")
    assert _money(driller.accrued_rub) == Decimal("2651162.79")


def test_two_people_per_shift_share_one_rotation() -> None:
    """Двое в смене при 35 сменах станка: штат ⌈35 × 2 / 15⌉ = 5, а не 2 × ⌈35 / 15⌉ = 6."""

    context = _context(crew=(CrewMember("POS_DRILLER", Decimal("2")),), rig_plan_shifts=Decimal("35"))
    driller = labor.compute(context)[0]

    assert driller.rotation_headcount == Decimal("5")
    assert _money(driller.fixed_rub) == Decimal("996677.74")
    assert _money(driller.piece_rub) == Decimal("4186046.51")
    assert _line(context, "LABOR_POS_DRILLER").quantity == context.value("rig_shifts") * 2


def test_zero_headcount_is_one_person_per_shift() -> None:
    """0 в составе бригады — прежнее «по экипажу техники»: один человек в смене."""

    zero = _context(crew=(CrewMember("POS_DRILLER", Decimal("0")),))
    one = _context(crew=(CrewMember("POS_DRILLER", Decimal("1")),))

    assert labor.compute(zero)[0].accrued_rub == labor.compute(one)[0].accrued_rub
    assert zero.lineage["crew_per_shift.POS_DRILLER"] == "в составе 0 — один человек в смене"
    assert one.lineage["crew_per_shift.POS_DRILLER"] == "человек в смене"


def test_crew_fixed_part_follows_machine_plan_shifts() -> None:
    """Водитель СЗМ: оклад штата — на плановые смены СЗМ; без плана — по норме смен с предупреждением."""

    crew = (CrewMember("POS_SZM_DRIVER", Decimal("1"), Decimal("4")),)

    planned = _context(crew=crew, machine_plan_shifts={"SZM_12T": Decimal("10")})
    labor.compute(planned)
    # 50 000 × ⌈10 / 20⌉ / 10 см × 4 см + 200 × 42 000 / 1000
    assert _line(planned, "LABOR_POS_SZM_DRIVER").amount_rub == Decimal("28400")
    assert planned.value("crew_rotation.POS_SZM_DRIVER") == Decimal("1")
    assert not [warning for warning in planned.warnings if "оклад должности" in warning]

    no_plan = _context(crew=crew, machine_plan_shifts={"SZM_12T": Decimal("0")})
    labor.compute(no_plan)
    # 50 000 / 20 см × 4 см × 1 чел + 8 400
    assert _line(no_plan, "LABOR_POS_SZM_DRIVER").amount_rub == Decimal("18400")
    assert "crew_rotation.POS_SZM_DRIVER" not in no_plan.values
    assert (
        "Для техники SZM_12T не заданы плановые смены в месяц: "
        "оклад должности POS_SZM_DRIVER посчитан по норме смен человека."
    ) in no_plan.warnings


def test_per_diem_counts_people_in_shift_not_rotation() -> None:
    rates_item = fx.item(
        "ORG_RATES_DEFAULT",
        "Ставки организации",
        {"per_diem_rub": "1000", "lodging_rub": "1000"},
    )
    context = ModelContext(
        fx.references(organization_rates=(rates_item,)),
        fx.parameters(crew=(CrewMember("POS_DRILLER", Decimal("0")),)),
        fx.physical(),
    )
    drilling.compute(context)
    labor.compute(context)

    per_diem = _line(context, "LABOR_PER_DIEM")
    # 116,28 чел·см × 2 000 ₽; со штатом ротации было 697 674,42 ₽.
    assert per_diem.quantity == context.value("rig_shifts")
    assert _money(per_diem.amount_rub) == Decimal("232558.14")
```

В `tests/test_model_equipment_emulsion.py` заменить строку `:102`:

```python
    # Оклад штата делится на плановые смены тягача (норматив типа — 18), а не на
    # норму смен водителя (21): до TASK-010 PR 0b было 63 000 / 21 × 3 = 9 000 ₽.
    assert context.value("crew_rotation.POS_EMULSION_DRIVER") == Decimal("1")
    assert driver.amount_rub == Decimal("63000") * 1 / 18 * 3
```

- [ ] **Шаг 2: убедиться, что тесты падают**

Run: `.venv/bin/python -m pytest tests/test_model_labor.py tests/test_model_equipment_emulsion.py -q`
Expected: FAIL — `AttributeError: 'LaborLine' object has no attribute 'rotation_headcount'`,
`assert Decimal('0') == Decimal('3')` для `crew_rotation`, суммы 7674418.60 ≠ 2616279.07.

- [ ] **Шаг 3: реализация**

В `cost/model/labor.py` docstring модуля дополнить абзацем:

```python
"""ФОТ прямого персонала блока: постоянная часть, сделка, взносы и вахта.

Должность попадает в расчёт, только если её операция входит в пакет работ.
Косвенный персонал здесь не считается — он распределяется по объёму юнита
(`cost/model/unit.py`).

Численность двух видов: `headcount` состава бригады — люди в смене, им идут
сделка и суточные; штат на ротацию экипажа техники модель выводит из плановых
смен машины, и на него приходится только месячный оклад.
"""
```

`LaborLine` заменить и добавить `CrewRotation`:

```python
@dataclass(frozen=True)
class LaborLine:
    position_code: str
    position_name: str
    operation_code: str
    # Человек в смене: столько людей должности одновременно работает в одной смене.
    headcount: Decimal
    shifts_per_block: Decimal
    fixed_rub: Decimal
    piece_rub: Decimal
    accrued_rub: Decimal
    # Штат на ротацию экипажа техники; None — должность не экипаж техники или
    # у техники нет плановых смен.
    rotation_headcount: Decimal | None = None


@dataclass(frozen=True)
class CrewRotation:
    """Штат экипажа техники, закрывающий её плановые смены."""

    equipment_code: str
    plan_shifts: Decimal
    person_shifts: Decimal
    headcount: Decimal
```

В `compute` цикл по должностям от `shifts = _shifts_per_block(...)` (`:114`) до `results.append(...)`
(`:164-175`) заменить на:

```python
        shifts = _shifts_per_block(context, position, operation_code, manual_shifts)
        if shifts <= 0:
            continue
        per_shift = _per_shift_headcount(headcount)

        rate_item = _labor_rate(context, position_code)
        if rate_item is None:
            context.warn(f"Для должности {position_code} не задана ставка в «Ставках персонала».")
            continue

        fixed_monthly = payload_number(rate_item, "fixed_monthly_rub")
        rotation = _crew_rotation(context, position, operation_code, per_shift)
        fixed_block, fixed_formula = _fixed_amount(position, fixed_monthly, shifts, per_shift, rotation)
        piece_block, piece_formula = _piece_amount(context, position, rate_item, per_shift)
        accrued = fixed_block + piece_block
        if rates.salary_basis == "NET" and rates.income_tax_rate < 1:
            accrued = accrued / (Decimal("1") - rates.income_tax_rate)

        context.set_value(
            f"crew_shifts.{position_code}", shifts, f"смен на блок должности {position_code}"
        )
        context.set_value(
            f"crew_per_shift.{position_code}",
            per_shift,
            "человек в смене" if headcount > 0 else "в составе 0 — один человек в смене",
        )
        if rotation is not None:
            context.set_value(
                f"crew_rotation.{position_code}",
                rotation.headcount,
                f"⌈{rotation.plan_shifts} см {rotation.equipment_code} × {per_shift} чел / "
                f"{rotation.person_shifts} см человека⌉",
            )

        context.add_line(
            operation_code=operation_code,
            cost_item_code=f"LABOR_{position_code}",
            cost_item_name=f"ФОТ: {position.name}",
            layer=CostLayer.PROJECT_DIRECT,
            amount_rub=accrued,
            formula=(
                fixed_formula
                + (f" + {piece_formula}" if piece_formula else "")
                + (" ÷ (1 − НДФЛ)" if rates.salary_basis == "NET" else "")
            ),
            section="LABOR",
            # Цены за единицу нет: оклад, сдельная часть и НДФЛ дают разную
            # ставку за смену, одним числом её не назвать.
            quantity=shifts * per_shift,
            unit="чел·см",
            # Смены — ручная поправка вкладки, если сметчик её задал,
            # иначе норматив должности или производительность техники.
            quantity_origin="MANUAL" if manual_shifts is not None else "NORM",
        )
        accrued_total += accrued
        charge = _per_diem(context, position, shifts, per_shift)
        per_diem_total += charge
        if charge > 0:
            per_diem_shifts += shifts * per_shift
        results.append(
            LaborLine(
                position_code=position_code,
                position_name=position.name,
                operation_code=operation_code,
                headcount=per_shift,
                shifts_per_block=shifts,
                fixed_rub=fixed_block,
                piece_rub=piece_block,
                accrued_rub=accrued,
                rotation_headcount=rotation.headcount if rotation is not None else None,
            )
        )
```

Функцию `_headcount` (`:254-275`) удалить, на её место:

```python
def _per_shift_headcount(explicit: Decimal) -> Decimal:
    """Человек в смене из состава бригады.

    Ноль — прежнее «по экипажу техники»: в смене один человек, а штат на
    ротацию модель выводит сама. Так записан бурильщик в шаблонах, и так же
    очищенное поле численности приходит с вкладки.
    """

    return explicit if explicit > 0 else Decimal("1")


def _crew_rotation(
    context: ModelContext,
    position: ReferenceItem,
    operation_code: str,
    per_shift: Decimal,
) -> CrewRotation | None:
    """Штат экипажа техники: ⌈плановые смены машины × человек в смене / норма смен человека⌉.

    None — у операции нет техники, техника не выбрана или у неё нет плановых
    смен: тогда оклад считается по норме смен должности.
    """

    param_name = CREW_EQUIPMENT_PARAM.get(operation_code)
    if not param_name:
        return None
    equipment = context.item("equipment_types", getattr(context.params, param_name, None))
    if equipment is None:
        return None
    plan_shifts = _equipment_plan_shifts(context, param_name, equipment)
    if plan_shifts <= 0:
        context.warn(
            f"Для техники {equipment.code} не заданы плановые смены в месяц: "
            f"оклад должности {position.code} посчитан по норме смен человека."
        )
        return None
    person_shifts = payload_number(position, "norm_shifts_per_month", Decimal("21"))
    if person_shifts <= 0:
        return None
    # Двое в смене при 35 сменах станка и норме 15 — пять человек, а не 2 × 3:
    # недобор смен одного закрывает другой.
    headcount = (plan_shifts * per_shift / person_shifts).to_integral_value(rounding=ROUND_CEILING)
    return CrewRotation(equipment.code, plan_shifts, person_shifts, headcount)


def _equipment_plan_shifts(context: ModelContext, param_name: str, equipment: ReferenceItem) -> Decimal:
    """Плановые смены машины — та же база, что у её амортизации.

    Станок: параметр вкладки, пусто и ноль — норматив типа (`drilling.py`).
    Остальная техника: `machine_plan_shifts`, ноль — «загрузки нет» (`equipment.py`).
    """

    if param_name == "rig_code":
        return context.params.rig_plan_shifts or payload_number(equipment, "norm_shifts_per_month")
    return context.machine_plan_shifts(equipment)


def _fixed_amount(
    position: ReferenceItem,
    fixed_monthly: Decimal,
    shifts: Decimal,
    per_shift: Decimal,
    rotation: CrewRotation | None,
) -> tuple[Decimal, str]:
    """Постоянная часть на блок.

    Экипаж техники получает оклад за месяц при любой загрузке машины, поэтому
    месячный ФОТ штата делится на плановые смены машины — как её амортизация.
    Остальным — ставка человеко-смены: оклад / норма смен.
    """

    if rotation is not None:
        return (
            fixed_monthly * rotation.headcount / rotation.plan_shifts * shifts,
            f"{fixed_monthly} ₽/мес × {rotation.headcount} чел / {rotation.plan_shifts} см × {shifts} см",
        )
    norm_shifts = payload_number(position, "norm_shifts_per_month", Decimal("21"))
    rate_per_shift = fixed_monthly / norm_shifts if norm_shifts > 0 else Decimal("0")
    return (
        rate_per_shift * shifts * per_shift,
        f"{fixed_monthly} ₽/мес / {norm_shifts} см × {shifts} см × {per_shift} чел",
    )
```

В `_piece_amount` переименовать параметр `headcount` → `per_shift` (в теле и формуле) и заменить docstring:

```python
    """Сдельная часть — каждому, кто работает в смене: расценка на человека.

    Штат на ротацию сюда не входит: метры блока бурит смена, а не весь штат.
    """
```

В `_per_diem` переименовать параметр `headcount` → `per_shift`: `return shifts * per_shift * per_shift_rate`
(локальную `per_shift` переименовать в `per_shift_rate`).

- [ ] **Шаг 4: убедиться, что тесты проходят**

Run: `.venv/bin/python -m pytest tests/test_model_labor.py tests/test_model_equipment_emulsion.py tests/test_model_origins.py tests/test_crew_defaults.py tests/test_api_block_economics.py -q`
Expected: PASS.

- [ ] **Шаг 5: коммит**

```bash
git add cost/model/labor.py tests/test_model_labor.py tests/test_model_equipment_emulsion.py
git commit -m "$(cat <<'EOF'
TASK-010 PR 0b: сделка и суточные — людям в смене, оклад штата — по плановым сменам техники

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
)"
```

---

### Задача 2: осознанный сдвиг регрессии сметы

**Файлы:**
- Изменить: `tests/test_model_regression_smeta_2026_01.py:1-28`, конец файла
- Изменить: `tests/fixtures/smeta_2026_01/README.md`

**Интерфейсы:**
- Использует: формулу строки экипажа и `crew_rotation.<pos>` из Задачи 1.

Причина сдвига: в смете водитель СЗМ получает `60 000 / 21 × 4,2` (норма смен человека), модель делит месячный
оклад штата `⌈20 / 21⌉ = 1` на 20 плановых смен СЗМ: `60 000 × 1 / 20 × 4,2`. Разница 600 ₽ до НДФЛ, строка
23 724,46 → 24 430,34 ₽, раздел 2.3 — 193 018,38 → 194 123,11 ₽ (+0,57 %, в допуске 1 %). Бурильщик сметы
(`headcount 1`, оклад 0, сделка 150 ₽/м) не меняется: 373 266,88 ₽; доставщик в паспорте не выбран — его
оклад по норме смен, как раньше.

- [ ] **Шаг 1: тест сдвига**

В конец `tests/test_model_regression_smeta_2026_01.py`:

```python
def test_crew_salary_is_spread_over_machine_plan_shifts(result) -> None:
    """TASK-010 PR 0b: оклад экипажа техники — месячный ФОТ штата на плановые смены машины.

    Смета делит оклад водителя СЗМ на его 21 нормативную смену, модель — на
    20 плановых смен СЗМ при штате ⌈20 / 21⌉ = 1. Раздел 2.3 растёт на 0,57 %:
    193 018,38 → 194 123,11 ₽. Сделку бурильщика штат ротации не умножает.
    """

    economics, _ = result
    lines = {line.cost_item_code: line for line in economics.lines}

    driver = lines["LABOR_POS_SZM_DRIVER"]
    assert driver.formula.startswith("60000 ₽/мес × 1 чел / 20 см × 4.2 см")
    assert driver.amount_rub.quantize(Decimal("0.01")) == Decimal("24430.34")
    assert economics.natural.values["crew_rotation.POS_SZM_DRIVER"] == Decimal("1")

    assert lines["LABOR_POS_DRILLER"].amount_rub.quantize(Decimal("0.01")) == Decimal("373266.88")

    block_positions = _sum(
        economics,
        "LABOR_POS_MASTER",
        "LABOR_POS_BLASTER",
        "LABOR_POS_SZM_DRIVER",
        "LABOR_POS_DELIVERY_DRIVER",
    )
    section = block_positions * Decimal("1.3042") * Decimal("1.2")
    assert section.quantize(Decimal("0.01")) == Decimal("194123.11")
```

В docstring модуля после пункта «2.2 (суточные …)» добавить:

```
* 2.3 (+0,57 %) — оклад водителя СЗМ в смете делится на его 21 нормативную
  смену; в модели месячный оклад штата экипажа делится на 20 плановых смен
  СЗМ, как амортизация машины (TASK-010 PR 0b).
```

- [ ] **Шаг 2: прогон**

Run: `.venv/bin/python -m pytest tests/test_model_regression_smeta_2026_01.py -v`
Expected: PASS, 8 тестов.

- [ ] **Шаг 3: README фикстуры**

В `tests/fixtures/smeta_2026_01/README.md` строку таблицы 2.3 заменить на:

```
| 2.3 ФОТ блока | 193 018,38 ₽ | оклад штата экипажа техники / плановые смены машины, остальным — оклад / норматив смен; сделка, взносы, резерв |
```

В «Осознанные расхождения» после пункта «ФОТ бурильщиков» добавить:

```
- **2.3 ФОТ блока: водитель СЗМ (+0,57 %, 194 123,11 ₽).** Смета делит
  оклад водителя на его 21 нормативную смену. Модель делит месячный оклад
  штата экипажа (⌈20 / 21⌉ = 1 человек) на 20 плановых смен СЗМ — как
  амортизацию машины: 60 000 × 1 / 20 × 4,2 вместо 60 000 / 21 × 4,2.
```

- [ ] **Шаг 4: коммит**

```bash
git add tests/test_model_regression_smeta_2026_01.py tests/fixtures/smeta_2026_01/README.md
git commit -m "$(cat <<'EOF'
TASK-010 PR 0b: регрессия сметы — сдвиг раздела 2.3 на +0,57 % из-за оклада по плановым сменам СЗМ

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
)"
```

---

### Задача 3: подписи «человек в смене» и штат на вкладке

**Файлы:**
- Изменить: `cost/v2/schemas/labor.py:76-78`
- Изменить: `tests/test_reference_schemas.py:172`
- Изменить: `frontend/src/pages/economics/sections/LaborSection.tsx:78-103`
- Тест: `frontend/src/pages/economics/sections/LaborSection.test.tsx`

**Интерфейсы:**
- Использует: `economics.natural.values["crew_rotation.<pos>"]` (строка) из Задачи 1.
- Даёт: подпись поля формы «Человек в смене»; `aria-label` поля вкладки `Человек в смене: <должность>`.

- [ ] **Шаг 1: падающие тесты**

`tests/test_reference_schemas.py:172`:

```python
        assert "Состав бригады → строка 1 → Человек в смене" in message
```

В `LaborSection.test.tsx` в тесте «норматив становится ручным после правки численности» заменить
`screen.getByLabelText("Численность: Мастер БВР")` на `screen.getByLabelText("Человек в смене: Мастер БВР")` и
добавить в конец `describe`:

```tsx
  it("показывает штат на ротацию экипажа техники из расчёта", () => {
    const { params, defaults, economics, group } = setup();
    const withRotation = {
      ...economics,
      natural: {
        ...economics.natural,
        values: { ...economics.natural.values, "crew_rotation.MASTER_BVR": "3" },
      },
    };
    render(
      <LaborSection
        group={group}
        params={params}
        defaults={defaults}
        economics={withRotation}
        volume={economics.block_volume_m3}
        canEdit
        onChange={vi.fn()}
      />,
    );

    expect(screen.getByText(/Штат на ротацию: 3 чел\./)).toBeInTheDocument();
    // У взрывника техники нет — и подписи нет.
    expect(screen.getAllByText(/Штат на ротацию/)).toHaveLength(1);
  });
```

Run: `.venv/bin/python -m pytest tests/test_reference_schemas.py -q` и
`cd frontend && npx vitest run src/pages/economics/sections/LaborSection.test.tsx`
Expected: FAIL (подпись «Численность», нет «Штат на ротацию»).

- [ ] **Шаг 2: реализация**

`cost/v2/schemas/labor.py:76-78`:

```python
class CrewMember(ReferencePayload):
    position_code: str = RefField("positions", description="Должность")
    headcount: Decimal = UnitField(
        "чел",
        title="Человек в смене",
        description="Сколько человек должности работает в одной смене; штат на ротацию модель выводит из плановых смен техники",
        default=Decimal("1"),
        ge=0,
    )
```

`LaborSection.tsx`: после `const positionLabel = …` добавить

```tsx
        // Штат на ротацию модель выводит только экипажу техники — у остальных
        // должностей ключа нет, и подпись не показывается.
        const rotation = economics?.natural.values[`crew_rotation.${member.position_code}`];
```

`captions` заменить на

```tsx
            captions={[
              {
                label: "Смены на блок",
                // Без бейджа: происхождение записи бригады уже стоит в колонке
                // «Основание», а само слово «норматив» и есть ответ на вопрос,
                // откуда взялось число.
                value:
                  member.shifts_per_block === null || member.shifts_per_block === ""
                    ? "норматив"
                    : formatAmount(Number(member.shifts_per_block)),
              },
              ...(rotation === undefined
                ? []
                : [{ label: "Штат на ротацию", value: `${formatAmount(Number(rotation))} чел.` }]),
            ]}
```

`ariaLabel={`Численность: ${positionLabel}`}` → `ariaLabel={`Человек в смене: ${positionLabel}`}`;
`unit="чел."` → `unit="чел./см"`. В шапке-комментарии файла «численность и смены на блок правит сметчик» →
«людей в смене и смены на блок правит сметчик».

- [ ] **Шаг 3: прогон**

Run: `.venv/bin/python -m pytest tests/test_reference_schemas.py -q`
Run: `cd frontend && npx vitest run src/pages/economics src/pages/references`
Expected: PASS.

- [ ] **Шаг 4: коммит**

```bash
git add cost/v2/schemas/labor.py tests/test_reference_schemas.py frontend/src/pages/economics/sections/LaborSection.tsx frontend/src/pages/economics/sections/LaborSection.test.tsx
git commit -m "$(cat <<'EOF'
TASK-010 PR 0b: «человек в смене» в составе бригады и штат на ротацию на вкладке

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
)"
```

---

### Задача 4: документация модели и решений

**Файлы:**
- Изменить: `Docs/COST_MODEL.md:56-57`, `:84-86`, новый раздел после «Распределение постоянных затрат»
- Изменить: `Docs/specs/2026-09-13-task-010-payroll-decisions.md` — строка Т20 в §3

- [ ] **Шаг 1: `Docs/COST_MODEL.md`**

Строки таблицы натуральных величин `:56-57` заменить на:

```
| `crew_shifts.<должность>` | ручная поправка → смены техники → `норм_смен / норм_операций` | `labor` |
| `crew_per_shift.<должность>` | человек в смене из состава бригады; `0` — один человек | `labor` |
| `crew_rotation.<должность>` | `⌈плановые смены техники × человек в смене / норм_смен человека⌉`, только экипаж техники | `labor` |
```

Абзац `:84-86` заменить на:

```
Постоянные затраты техники распределяются по её **плановым сменам**: при 25
сменах станка вместо 40 постоянная часть метра растёт на 60 %, а штат
бурильщиков на ротацию падает с трёх до двух — смена станка стоит 4 800 ₽
оклада вместо 4 500 (60 000 × 2 / 25 против 60 000 × 3 / 40).
```

После раздела «Распределение постоянных затрат» добавить:

```
## ФОТ прямого персонала

Численность в модели двух видов:

- **человек в смене** `h` — поле `headcount` состава бригады
  (`crew_templates.members`, параметр вкладки `crew`): сколько людей должности
  одновременно работает в одной смене. `0` — один человек;
- **штат на ротацию** `N` — модель выводит только для экипажа техники
  (станок, СЗМ, доставщик ВМ, тягач эмульсии):
  `N = ⌈плановые смены техники × h / норм_смен человека⌉`. Плановые смены —
  та же база, что у амортизации машины: станок — `rig_plan_shifts` (пусто и 0 —
  норматив типа), остальная техника — `machine_plan_shifts`.

Строка `LABOR_<должность>`, `S` — смены на блок, `M` — оклад из «Ставок
персонала», `n` — норма смен должности:

| Часть | Экипаж техники | Остальные должности и техника без плана |
| --- | --- | --- |
| Оклад | `M × N / плановые смены × S` | `M / n × S × h` |
| Сделка | `расценка × драйвер / piece_unit × h` | то же |
| Суточные | `S × h × (суточные + проживание)` | то же |

Взносы и резерв отпусков начисляются на сумму строк, при `salary_basis = NET`
строка делится на `1 − НДФЛ`. Штат на ротацию входит только в месячный оклад:
метры блока бурит смена, поэтому сделка и суточные идут людям в смене. Если у
выбранной техники нет плановых смен, модель предупреждает и считает оклад по
норме смен должности.

Пример (`tests/model_fixtures.py`): бурильщик, 60 000 ₽/мес, норма 15 смен,
станок 40 плановых смен, 13 953,49 м за 116,28 смены, расценка 150 ₽/м.
`N = ⌈40 / 15⌉ = 3`; оклад `60 000 × 3 / 40 × 116,28 = 523 255,81 ₽`; сделка
`150 × 13 953,49 = 2 093 023,26 ₽`; строка 2 616 279,07 ₽. До TASK-010 PR 0b
оклад и сделка умножались на штат ротации — 7 674 418,60 ₽.
```

- [ ] **Шаг 2: строка Т20 в решениях**

В таблице §3 `Docs/specs/2026-09-13-task-010-payroll-decisions.md` строку Т20 заменить на:

```
| Т20 | Ротационная численность — отдельный PR 0b. `headcount` состава бригады — человек в смене; штат на ротацию `⌈плановые смены техники × h / норма смен⌉` выводит модель. Оклад экипажа техники — `оклад × штат / плановые смены техники × смены блока`, сделка и суточные — людям в смене (решение владельца 13.09.2026, план `Docs/plans/2026-09-13-task-010-pr0b-rotation-headcount.md`) | `cost/model/labor.py:127, 322` — каждый метр оплачивается `headcount` раз |
```

- [ ] **Шаг 3: коммит**

```bash
git add Docs/COST_MODEL.md Docs/specs/2026-09-13-task-010-payroll-decisions.md
git commit -m "$(cat <<'EOF'
TASK-010 PR 0b: описание ФОТ прямого персонала и решение Т20

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
)"
```

---

### Задача 5: проверка, PR и ревью

- [ ] **Шаг 1: полный прогон**

```bash
.venv/bin/python -m pytest tests -q
```

Expected: 0 failed. На `main` было 1362 passed, 32 skipped; новых тестов 7.

```bash
cd frontend && npx vitest run && npx tsc -b
```

Expected: всё зелёное. Worktree чистый, iCloud-дублей в нём нет.

- [ ] **Шаг 2: стенд (api-stand :8020 / frontend-stand :5181)**

Скопировать в worktree (не коммитить) `.claude/stand/` и `.claude/launch.json` из основного чекаута, поднять
`api-stand` и `frontend-stand` через `preview_start`. На вкладке «Экономика блока» паспорта стенда добавить
прямую должность бурения, если её нет в составе. Ожидание: в строке должности единица «чел./см» и подпись
«Штат на ротацию: N чел.»; на вкладке «Ресурсы» есть `crew_per_shift.*` и `crew_rotation.*`, нет
`crew_headcount.*`; строка ФОТ бурильщика равна `оклад × N / план × смены + расценка × м`. Скриншот — в PR.
Если в справочниках стенда нет прямой должности бурения, так и написать в PR: подпись проверена vitest.

- [ ] **Шаг 3: PR**

```bash
git push -u origin feat/task-010-pr0b-rotation-headcount
gh pr create --title "TASK-010 PR 0b: ротационная численность экипажа" --body "$(cat <<'EOF'
Решение Т20 (Docs/specs/2026-09-13-task-010-payroll-decisions.md). Дефект: при `headcount = 0` модель подставляла штат ротации (⌈смены станка / норма смен человека⌉ = 3) в формулу «на человека», и каждый метр и каждая смена станка оплачивались трём людям.

Модель после правки (решения владельца 13.09):
- `headcount` состава бригады — человек в смене; 0 — один человек (как записан бурильщик в шаблонах).
- Штат на ротацию `N = ⌈плановые смены техники × h / норма смен⌉` выводит модель для экипажа техники.
- Оклад экипажа техники — `оклад × N / плановые смены техники × смены блока`, та же база, что у амортизации машины. Остальным — `оклад / норма смен × смены × h`.
- Сделка и суточные — людям в смене. Взносы и резерв — от суммы, как раньше.
- У техники без плановых смен — предупреждение и оклад по норме смен.
- Натуральные величины: `crew_per_shift.*`, `crew_rotation.*` вместо `crew_headcount.*`.

Суммы на фикстуре `tests/model_fixtures.py` (бурильщик, 60 000 ₽/мес, норма 15, станок 40 смен, 13 953,49 м, 150 ₽/м):

| | было | стало |
|---|---|---|
| Оклад | 1 395 348,84 | 523 255,81 |
| Сделка | 6 279 069,77 | 2 093 023,26 |
| ФОТ бурильщика со взносами и резервом | 12 010 772,09 | 4 094 581,40 |
| Суточные (1 000 + 1 000 ₽) | 697 674,42 | 232 558,14 |
| Маржинальная цена м³ | 361,33 | 229,39 |

Осознанные сдвиги тестов:
- Регрессия сметы, раздел 2.3: 193 018,38 → 194 123,11 ₽ (+0,57 %, в допуске 1 %). Смета делит оклад водителя СЗМ на его 21 нормативную смену, модель — на 20 плановых смен СЗМ. Бурильщик сметы не меняется (оклад 0, в смене один). Пояснение — в README фикстуры и отдельном тесте.
- Водитель тягача эмульсии: 9 000 → 10 500 ₽ (делитель — 18 плановых смен тягача вместо 21 смены водителя).

Интерфейс: поле состава бригады подписано «Человек в смене», на вкладке — единица «чел./см» и подпись «Штат на ротацию».

План: Docs/plans/2026-09-13-task-010-pr0b-rotation-headcount.md. Описание модели — Docs/COST_MODEL.md, раздел «ФОТ прямого персонала».

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

- [ ] **Шаг 4: ревью** — `/code-review` на диапазоне PR; найденное исправить отдельными коммитами. Затем прочитать
замечания Codex: `gh api repos/dvotapi/BlastEX/pulls/<N>/comments` (бот `chatgpt-codex-connector`) и закрыть
каждое до просьбы о слиянии.
