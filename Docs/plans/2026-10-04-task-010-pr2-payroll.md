# TASK-010 PR 2 — модель ФОТ и превью: план реализации

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** затраты на персонал по должности × объект × месяц считаются из справочников по методике TASK-010 —
приведённые метры, эффективные смены, сдельная премия по шкале, месячный ФОТ, доля в марже метра — и
показываются превью `POST /api/v1/economics/payroll/preview`.

**Architecture:** чистые функции в Decimal — `cost/model/payroll.py` (нормы), чтение справочников через схемы
разделов — `cost/model/payroll_inputs.py`, сборка превью одной должности — `cost/model/payroll_preview.py`,
эндпоинт — в `api/routers/block_economics.py`. Экономика блока не меняется (это PR 3a); меняется только смета
V1: должность без ставки получает МРОТ года.

**Tech Stack:** Python 3.13, Decimal, pydantic 2, FastAPI, pytest; matplotlib — только для PNG кривой.

**Spec:** `Docs/specs/2026-09-13-task-010-payroll-decisions.md` (решения владельца 13.09.2026; при расхождении с
`TASK-010 Зарплата персонала по объектам 3.md` действует он). Справочники уже в main (PR 1, #83), сид
опубликован на проде (ревизия d874e8a4).

**Прототип.** Код плана прогнан во временной копии репозитория: pytest целиком — 2462 passed, 50 skipped;
задачи 1–5 проверены по отдельности в порядке плана. Копия удалена, в ветке только план.

## Вопросы владельцу (до старта)

**Ответы владельца 04.10.2026:** 1 — вариант А (xlsx не класть); 2 — вариант А (МРОТ, одна строка). Исполнение — inline.

1. **Excel владельца в публичном репозитории.** Спека (§5, PR 2) велит положить `Расчёт заработной платы.xlsx` в
   `Docs/specs/payroll/`. Репозиторий `dvotapi/BlastEX` публичный: файл со шкалой оплаты, МРОТ-окладами и
   названием «Ломовское месторождение» попадёт в открытый доступ навсегда (история git).
   - **А (рекомендую):** xlsx не класть. Методика и все числа файла — в `Docs/PAYROLL_MODEL.md` и в регрессии,
     график — PNG, который строится кодом модели.
   - Б: положить xlsx, как в спеке.
2. **Семь предупреждений листа «Расчёт» «нет ставки, принят 0»** (новые должности сида без ставок).
   - **А (рекомендую):** лист «Расчёт» (смета V1) берёт для должности без ставки МРОТ «Параметров ФОТ» года —
     то же правило, что методика (TASK-010 §2.2). Семь строк сворачиваются в одну: «Оклад по МРОТ 2026 года
     (27 093 ₽): нет ставки у должностей …». Числа сметы меняются, только если такую должность добавить в
     расчёт (сейчас её там нет). Задача 9.
   - Б: оклад остаётся 0, семь строк сворачиваются в одну.
   - В: ничего не менять до заведения ставок вручную (задачу 9 выбросить).

**На заметку (данные, не код):** превью берёт взносы из «Ставок и надбавок организации». Умолчание там —
СФР 30 % и травматизм 0,42 %, в файле — 15 % и 2,1 %; вахтовая надбавка — поле «Суточные» (`per_diem_rub`), в
файле 700 ₽/день. Что сейчас на проде — не проверял (чтение прода — только с согласия). Если значения другие,
превью разойдётся с файлом, это не ошибка модели. Льготный тариф МСП (30 % до 1,5 МРОТ, 15 % сверху) методика
не моделирует — одна ставка, как в файле.

## Решения планировщика (в отчёт PR)

- **План и факт.** `shifts` не задан — план: `S_эфф = shift_days_on − maintenance_shifts`. Задан — факт:
  `S_эфф = shifts − Σ excusable / shift_hours`, ТОиР на факте — код простоя. `downtime` без `shifts` — 422.
- **Знаменатель флага 25 %** на факте — `shifts × shift_hours − часы ТОиР из простоев` (а не ТОиР объекта):
  так «13 смен + 40 ч» и «15 смен + ТОиР 22 ч + 40 ч» дают одинаковые 27,97 %, как в тест-плане спеки.
- **`meters_total`** — приведённые метры одной суммой: договорной k к ней не применяется, приведённых метров на
  погонный — 1.
- **Крепость метров** — из породы справочника (`rock_code`) или числом `f`, не обоими сразу.
- **Оклад не задан** (нет ставки или `fixed_monthly_rub = 0`) — МРОТ года с предупреждением. Ставка — без
  условия бурения; есть только с условием — первая с предупреждением.
- **Год параметров** — по месяцу; нет — ближайший прошлый (иначе будущий) с предупреждением; нет ни одной
  записи — 422.
- **Отсутствующие разделы:** нет ставок организации — умолчания схемы с предупреждением; нет «Сложности
  бурения» или пустая таблица — k = 1 с предупреждением; диаметра нет в заполненной таблице — 422 (спека).
- **Резервы отпусков** — по дням (`d / (d + рабочих дней)`), `vacation_reserve_rate` методика не читает.
  `salary_basis = NET` — предупреждение: методика считает оклад до НДФЛ.
- **Экипаж для доли** — из запроса; по умолчанию все сдельщики с приведёнными метрами и шкалой (машинист и
  помощник), по одному в смене; у остальных сдельщиков — сама должность.
- **Доля в марже** — на погонный метр: `Σ чел × r(m) × затраты на рубль премии × M / п.м. / маржа`. У ступеней
  потолка нет — предупреждение по плановому темпу. Статусы: `CHECKED`, `NOT_CHECKED` (нет цены),
  `NO_MARGIN` (маржа ≤ 0), `NOT_APPLICABLE` (у должности нет шкалы).
- **Затраты на рубль премии** — аналитически (выражение линейно по премии); тест сверяет с конечной
  разностью `cost(170 001) − cost(170 000)`.
- **Флаги** — коды `DOWNTIME_OVER_25`, `PACE_ABOVE_CEILING` (только у кривых), `MARGIN_SHARE_ABOVE_WARN`;
  предупреждения — строки. Ни то ни другое расчёт не блокирует.
- **Ряды графика** — 61 точка от 0 до 1,3 потолка (или 1,1 темпа, если он выше) плюс узлы и темп точно.
- **Числа ответа** — `float`, как у экономики блока; модель считает в Decimal.
- **Исправления тест-плана спеки:** `1,2 × P(2 000)` = 123 365,50 (в спеке 123 365,49 — округление до умножения);
  посменная сумма `6 × p(100) + 6 × p(230)` = 144 927,72 (в спеке ,73); γ для хранимых узлов 115,3846 / 184,6154 —
  2,811088, для точных 1500/13 и 2400/13 — 2,811090.
- **PNG** — строится скриптом `scripts/plot_payroll_curve.py` из той же модели; файла с графиком в репозитории
  до сих пор не было.

## Global Constraints

- Нормы — только в `cost/model/`, цены и параметры — только в справочниках; `cost/model` не импортирует
  `cost.drilling` и `cost.strategies` (`tests/test_model_*` это проверяют).
- Экономика блока (`cost/model/engine.py`, `labor.py`, `unit.py`) в PR 2 не меняется: регрессия
  `tests/test_model_regression_smeta_2026_01.py` проходит без правок.
- Все суммы и доли — `Decimal`; в тестах — сравнение до копейки (`cents`) или с явным допуском.
- Схемы справочников (`cost/v2/schemas/`) не меняются; входы читаются через `model_validate` схем разделов.
- Интерфейс в PR 2 не меняется (фронт — PR 3b).
- Python — `../../../.venv/bin/python` из корня worktree; pytest — с `--ignore-glob="* 2.py"` (iCloud-дубли).
- iCloud-дубли (`* 2.py`, `* 2`) не трогать и не коммитить; `git add` — только перечисленных файлов.
- Сообщения коммитов — по-русски, последняя строка `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- В main не пушить; PR не сливать — сливает владелец после `/code-review` и ревью Codex.

## Review Focus

Входы, которые спека подразумевает, но легко сломать; тест на каждый — в задаче-владельце:

1. Диаметр записан иначе, чем в таблице («152.0» против «152») — тот же диаметр, k = 1 (задача 1).
2. Порода из справочника без крепости в превью — k = 1 и предупреждение, не ошибка (задача 7).
3. Сдельщик без приведения (водитель, км) со списком метров — выработка суммой, без коэффициентов и без
   ошибки «диаметра нет в таблице» (задача 7).
4. Неизвестная должность в экипаже запроса — 422 с её кодом, а не 500 (задача 7).
5. Битая опубликованная запись (кривая без узла) — 422 с кодом записи, а не 500 (задача 6).

## Файлы

- Создать: `cost/model/payroll.py` — формулы методики (задачи 1–5).
- Создать: `cost/v2/payroll_params.py` — выбор записи «Параметров ФОТ» по году (задача 6).
- Создать: `cost/model/payroll_inputs.py` — входы из снимка справочников (задача 6).
- Создать: `cost/model/payroll_preview.py` — превью одной должности (задача 7).
- Создать: `api/schemas/payroll.py` — схемы запроса и ответа (задача 8).
- Изменить: `api/routers/block_economics.py` — эндпоинт превью (задача 8).
- Изменить: `cost/v2/legacy_adapter.py` — МРОТ для должности без ставки (задача 9, по ответу на вопрос 2).
- Создать: `scripts/plot_payroll_curve.py`, `Docs/specs/payroll/Шкала машиниста — степенная кривая.png`,
  `Docs/PAYROLL_MODEL.md`; изменить `Docs/ADR-001-economics-model.md`, `Docs/COST_MODEL.md`, `CLAUDE.md` (задача 10).
- Тесты: `tests/payroll_fixtures.py`, `tests/test_payroll_meters.py`, `tests/test_payroll_curve.py`,
  `tests/test_payroll_shifts.py`, `tests/test_payroll_regression_2026_09.py`, `tests/test_payroll_margin.py`,
  `tests/test_payroll_inputs.py`, `tests/test_payroll_preview.py`, `tests/test_api_payroll_preview.py`,
  `tests/test_legacy_adapter.py`.

---

### Задача 1: приведённые метры

**Files:**
- Create: `cost/model/payroll.py`
- Create: `tests/payroll_fixtures.py`
- Test: `tests/test_payroll_meters.py`

**Interfaces:**
- Produces: `PayrollInputError(ValueError)`; `fn(Decimal) -> str`, `percent(Decimal) -> str`;
  `HardnessBand(f_from, f_to, k)`, `DifficultyTables(hardness, diameter: Mapping[Decimal, Decimal], source)`,
  `MeterItem(meters, diameter_mm, f=None, label="")`, `NormalizedRow`, `NormalizedMeters(total, physical,
  contract_k, rows, lineage, warnings)` с `.factor`; `hardness_factor(f, bands) -> (k, note, warning)`;
  `normalized_meters(items, tables, contract_k=1) -> NormalizedMeters`. Константы `ZERO`, `ONE`, `HUNDRED`,
  `PROTODYAKONOV_MAX`, `WRITE_OFF_FLAG_SHARE`, `PACE_FLAG_RATIO`, `SHORT_WEEK_CLASSES`, `CURVE_SCALES`,
  `SERIES_SPAN`, `SERIES_STEPS`.
- Fixture: `CENT`, `cents(Decimal)`, `DIAMETERS`, `TABLES`.

- [ ] **Step 1: фикстура.** Создать `tests/payroll_fixtures.py`:

```python
"""Справочники методики ФОТ для тестов: параметры файла «Расчёт заработной платы» 2026.

Ставки взносов — из файла (СФР 15 %, травматизм 2,1 %), а не умолчания
организации: регрессия по файлу передаёт их явно (решения, Т2).
"""
from __future__ import annotations

from decimal import Decimal

from cost.model.payroll import DifficultyTables, HardnessBand
from cost.v2.payroll_defaults import HARDNESS_BANDS

CENT = Decimal("0.01")

DIAMETERS = {
    Decimal("110"): Decimal("0.72"),
    Decimal("127"): Decimal("0.84"),
    Decimal("140"): Decimal("0.92"),
    Decimal("152"): Decimal("1"),
    Decimal("165"): Decimal("1.09"),
    Decimal("190"): Decimal("1.25"),
    Decimal("215"): Decimal("1.41"),
    Decimal("250"): Decimal("1.64"),
}
TABLES = DifficultyTables(
    hardness=tuple(
        HardnessBand(
            Decimal(band["f_from"]) if band["f_from"] else None,
            Decimal(band["f_to"]) if band["f_to"] else None,
            Decimal(band["k"]),
        )
        for band in HARDNESS_BANDS
    ),
    diameter=DIAMETERS,
    source="drilling_difficulty.DD_MAIN",
)


def cents(value: Decimal) -> Decimal:
    return value.quantize(CENT)
```

- [ ] **Step 2: падающий тест.** Создать `tests/test_payroll_meters.py`:

```python
"""Приведённые метры: коэффициенты крепости и диаметра, договорной коэффициент (TASK-010 §2.1)."""
from __future__ import annotations

from decimal import Decimal

import pytest

from cost.model.payroll import DifficultyTables, MeterItem, PayrollInputError, hardness_factor, normalized_meters
from tests.payroll_fixtures import TABLES

D = Decimal
TWO_ROCKS = [MeterItem(D("800"), D("152"), D("10")), MeterItem(D("900"), D("250"), D("17"))]


def test_two_rocks_on_one_site_need_no_manual_averaging() -> None:
    meters = normalized_meters(TWO_ROCKS, TABLES)
    assert meters.total == D("2571.2")
    assert meters.physical == D("1700")
    assert [(row.k_f, row.k_d) for row in meters.rows] == [(D("1.0"), D("1")), (D("1.2"), D("1.64"))]
    assert meters.factor == D("2571.2") / D("1700")
    assert "16 < f ≤ 18 → 1,2" in meters.lineage["k_f.1"]
    assert "Ø 250 мм → 1,64" in meters.lineage["k_d.1"]


def test_contract_coefficient_multiplies_the_normalized_meters() -> None:
    assert normalized_meters(TWO_ROCKS, TABLES, D("1.1")).total == D("2571.2") * D("1.1")


def test_diameter_missing_from_the_table_is_an_input_error() -> None:
    with pytest.raises(PayrollInputError, match="133"):
        normalized_meters([MeterItem(D("100"), D("133"), D("10"))], TABLES)


def test_empty_tables_give_one_with_a_warning() -> None:
    meters = normalized_meters([MeterItem(D("100"), D("133"), D("17"))], DifficultyTables())
    assert meters.total == D("100")
    assert len(meters.warnings) == 2


@pytest.mark.parametrize(
    ("f", "k"),
    [("7.99", "0.9"), ("8", "0.9"), ("8.01", "1.0"), ("12", "1.0"), ("16.01", "1.2"), ("18", "1.2"), ("18.5", "1.3"), ("20", "1.3")],
)
def test_upper_bound_of_a_hardness_band_is_included(f: str, k: str) -> None:
    factor, _, warning = hardness_factor(D(f), TABLES.hardness)
    assert factor == D(k)
    assert warning == ""


def test_hardness_above_the_scale_takes_the_last_band_with_a_warning() -> None:
    factor, _, warning = hardness_factor(D("25"), TABLES.hardness)
    assert factor == D("1.3")
    assert "выше шкалы" in warning


def test_rock_without_hardness_gives_one_with_a_warning() -> None:
    factor, _, warning = hardness_factor(None, TABLES.hardness)
    assert factor == D("1")
    assert "не задана крепость" in warning


def test_diameter_written_with_a_trailing_zero_is_the_same_diameter() -> None:
    meters = normalized_meters([MeterItem(D("100"), D("152.0"), D("10"))], TABLES)
    assert meters.total == D("100")
```

- [ ] **Step 3: убедиться, что падает.**

Run: `../../../.venv/bin/python -m pytest tests/test_payroll_meters.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'cost.model.payroll'`.

- [ ] **Step 4: реализация.** Создать `cost/model/payroll.py`:

```python
"""Методика ФОТ по объектам (TASK-010): приведённые метры, эффективные смены,
сдельная премия по шкале и месячный ФОТ должности.

Функции чистые: справочники уже прочитаны (`cost/model/payroll_inputs.py`),
здесь только нормы — формулы файла владельца «Расчёт заработной платы» с
исправлениями методики (`Docs/PAYROLL_MODEL.md`). Всё считается в Decimal, а
каждая величина возвращается вместе с формулой, по которой получена.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Mapping, Sequence

from cost.model.inputs import formula_number

ZERO = Decimal("0")
ONE = Decimal("1")
HUNDRED = Decimal("100")

# Верх шкалы Протодьяконова. Крепость выше берёт коэффициент последней строки
# таблицы, но такое значение скорее ошибка ввода — предупреждаем.
PROTODYAKONOV_MAX = Decimal("20")
# Флаги на проверку начальнику участка (TASK-010 §2.3): расчёт не блокируют.
WRITE_OFF_FLAG_SHARE = Decimal("0.25")
PACE_FLAG_RATIO = Decimal("1.2")
# Классы условий труда с 36-часовой неделей (ст. 92 ТК РФ).
SHORT_WEEK_CLASSES = frozenset({"3.3", "3.4", "4"})
CURVE_SCALES = frozenset({"CURVE_POWER", "CURVE_LINEAR"})
# График шкалы: до 1,3 потолка — видно и рост, и постоянную цену выше потолка.
SERIES_SPAN = Decimal("1.3")
SERIES_STEPS = 60


class PayrollInputError(ValueError):
    """Вход, на котором методика не считается: 422 в превью."""


def fn(value: Decimal) -> str:
    return formula_number(value)


def percent(share: Decimal) -> str:
    return f"{fn(share * HUNDRED)} %"


# --- Приведённые метры ------------------------------------------------------


@dataclass(frozen=True)
class HardnessBand:
    """Интервал крепости `f_from < f ≤ f_to`; у первой строки нет низа, у последней — верха."""

    f_from: Decimal | None
    f_to: Decimal | None
    k: Decimal

    def contains(self, f: Decimal) -> bool:
        return (self.f_from is None or f > self.f_from) and (self.f_to is None or f <= self.f_to)

    def label(self) -> str:
        if self.f_from is None and self.f_to is None:
            return "любая f"
        if self.f_from is None:
            return f"f ≤ {fn(self.f_to)}"
        if self.f_to is None:
            return f"f > {fn(self.f_from)}"
        return f"{fn(self.f_from)} < f ≤ {fn(self.f_to)}"


@dataclass(frozen=True)
class DifficultyTables:
    """Коэффициенты приведения метров к базовым условиям: f = 10, Ø 152 мм."""

    hardness: tuple[HardnessBand, ...] = ()
    diameter: Mapping[Decimal, Decimal] = field(default_factory=dict)
    source: str = "drilling_difficulty"


@dataclass(frozen=True)
class MeterItem:
    meters: Decimal
    diameter_mm: Decimal
    f: Decimal | None = None
    label: str = ""


@dataclass(frozen=True)
class NormalizedRow:
    label: str
    meters: Decimal
    f: Decimal | None
    k_f: Decimal
    diameter_mm: Decimal
    k_d: Decimal
    normalized: Decimal


@dataclass(frozen=True)
class NormalizedMeters:
    # M — приведённые метры, аргумент шкалы.
    total: Decimal
    # Погонные метры без коэффициентов.
    physical: Decimal
    contract_k: Decimal = ONE
    rows: tuple[NormalizedRow, ...] = ()
    lineage: Mapping[str, str] = field(default_factory=dict)
    warnings: tuple[str, ...] = ()

    @property
    def factor(self) -> Decimal:
        """Приведённых метров на погонный: договорной k × средний коэффициент; без метров — 1."""

        return self.total / self.physical if self.physical > 0 else ONE


def hardness_factor(f: Decimal | None, bands: Sequence[HardnessBand]) -> tuple[Decimal, str, str]:
    """Коэффициент крепости, пояснение для происхождения и предупреждение (пусто — нет)."""

    if f is None:
        return ONE, "крепость не задана → 1", "У породы не задана крепость f: коэффициент крепости принят 1."
    if not bands:
        return ONE, "таблица крепости пуста → 1", "В «Сложности бурения» нет таблицы крепости: коэффициент крепости принят 1."
    band = next((band for band in bands if band.contains(f)), None)
    if band is None:
        # Разрывы не пропускает проверка ревизии; на битой таблице — 1, а не падение.
        return ONE, f"f = {fn(f)} вне таблицы → 1", f"Крепость f = {fn(f)} не попала ни в одну строку таблицы крепости: коэффициент принят 1."
    warning = ""
    if f > PROTODYAKONOV_MAX:
        warning = (
            f"Крепость f = {fn(f)} выше шкалы Протодьяконова (до {fn(PROTODYAKONOV_MAX)}): "
            "взят коэффициент последней строки таблицы."
        )
    return band.k, f"{band.label()} → {fn(band.k)}", warning


def normalized_meters(
    items: Sequence[MeterItem], tables: DifficultyTables, contract_k: Decimal = ONE
) -> NormalizedMeters:
    """M = contract_k × Σ mᵢ × k_f(fᵢ) × k_d(Øᵢ) (TASK-010 §2.1).

    Коэффициент не меняет цену метра, а увеличивает зачтённые метры: на объекте
    с несколькими породами не нужно решать, какие метры в какую ступень попали.
    Диаметра нет в заполненной таблице — ошибка (проверка ревизии такого не
    пускает); пустая таблица — коэффициент 1 с предупреждением.
    """

    rows: list[NormalizedRow] = []
    lineage: dict[str, str] = {}
    warnings: list[str] = []
    for index, entry in enumerate(items):
        k_f, f_note, warning = hardness_factor(entry.f, tables.hardness)
        if warning and warning not in warnings:
            warnings.append(warning)
        if tables.diameter:
            k_d = tables.diameter.get(entry.diameter_mm)
            if k_d is None:
                raise PayrollInputError(
                    f"Диаметра коронки {fn(entry.diameter_mm)} мм нет в таблице «Сложность бурения»."
                )
            d_note = f"Ø {fn(entry.diameter_mm)} мм → {fn(k_d)}"
        else:
            k_d = ONE
            d_note = "таблица диаметров пуста → 1"
            message = "В «Сложности бурения» нет таблицы диаметров: коэффициент диаметра принят 1."
            if message not in warnings:
                warnings.append(message)
        label = entry.label or f"строка {index + 1}"
        rows.append(NormalizedRow(label, entry.meters, entry.f, k_f, entry.diameter_mm, k_d, entry.meters * k_f * k_d))
        lineage[f"k_f.{index}"] = f"{tables.source}: {f_note}"
        lineage[f"k_d.{index}"] = f"{tables.source}: {d_note}"
    physical = sum((row.meters for row in rows), ZERO)
    total = contract_k * sum((row.normalized for row in rows), ZERO)
    lineage["normalized_meters"] = f"{fn(contract_k)} × Σ м × k_f × k_d = {fn(total)}"
    return NormalizedMeters(total, physical, contract_k, tuple(rows), lineage, tuple(warnings))
```

- [ ] **Step 5: тест проходит.**

Run: `../../../.venv/bin/python -m pytest tests/test_payroll_meters.py -q`
Expected: PASS (15 passed).

- [ ] **Step 6: коммит.**

```bash
git add cost/model/payroll.py tests/payroll_fixtures.py tests/test_payroll_meters.py
git commit -m "ФОТ (TASK-010 PR 2): приведённые метры по крепости и диаметру

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Задача 2: шкала, сдельная премия, ряды графика

**Files:**
- Modify: `cost/model/payroll.py` (дописать в конец)
- Modify: `tests/payroll_fixtures.py`
- Test: `tests/test_payroll_curve.py`

**Interfaces:**
- Consumes: `fn`, `percent`, `ZERO`, `HUNDRED`, `PayrollInputError`, константы задачи 1.
- Produces: `PayrollFlag(code, message)`; `ScaleTier(upto_per_shift, rate)`; `Scale(scale_type, norm_per_shift,
  rate_norm, ceiling_per_shift, rate_ceiling, tiers, source)` с `.is_curve`, `.gamma`, `.rate_at(pace)`,
  `.per_shift(pace)`, `.tier_split(pace)`, `.breakpoints()`; `PremiumTier`, `PiecePremium(total, output,
  effective_shifts, pace, per_shift, last_rate, mean_rate, tiers, lineage)`; `gamma_text(Decimal)`;
  `piece_premium(output, scale, effective) -> PiecePremium`; `pace_flags(scale, pace) -> tuple[PayrollFlag, ...]`;
  `ScalePoint(pace, rate, per_shift)`; `scale_series(scale, pace=None) -> tuple[ScalePoint, ...]`.
- Fixture: `CURVE_X`.

- [ ] **Step 1: фикстура.** В `tests/payroll_fixtures.py` заменить импорт из `cost.model.payroll` на

```python
from cost.model.payroll import DifficultyTables, HardnessBand, Scale
```

и дописать в конец:

```python
CURVE_X = Scale(
    "CURVE_POWER",
    norm_per_shift=Decimal("115.3846"),
    rate_norm=Decimal("45"),
    ceiling_per_shift=Decimal("184.6154"),
    rate_ceiling=Decimal("168.66"),
)
```

- [ ] **Step 2: падающий тест.** Создать `tests/test_payroll_curve.py`:

```python
"""Шкала сдельной премии: кривая X машиниста, линейная кривая, ступени (TASK-010 §2.3)."""
from __future__ import annotations

from decimal import Decimal

import pytest

from cost.model.payroll import PayrollInputError, Scale, ScaleTier, pace_flags, piece_premium, scale_series
from tests.payroll_fixtures import CURVE_X, cents

D = Decimal
THIRTEEN = D("13")


def premium(meters: str | int, shifts: str | int = 13, scale: Scale = CURVE_X) -> Decimal:
    return piece_premium(D(meters), scale, D(shifts)).total


@pytest.mark.parametrize(
    ("meters", "expected"),
    [(1500, "67500.00"), (1800, "85271.62"), (2000, "102804.58"), (2400, "156000.67"), (3000, "257196.67")],
)
def test_curve_x_premium_for_a_13_shift_rotation(meters: int, expected: str) -> None:
    assert cents(premium(meters)) == D(expected)


def test_nodes_with_four_digits_match_the_exact_nodes() -> None:
    exact = Scale("CURVE_POWER", D(1500) / THIRTEEN, D("45"), D(2400) / THIRTEEN, D("168.66"))
    for meters in (1500, 1800, 2000, 2400, 3000):
        assert abs(premium(meters) - premium(meters, scale=exact)) <= D("0.01")


def test_rounded_nodes_and_169_rub_drift_from_the_method() -> None:
    rounded = Scale("CURVE_POWER", D("115.4"), D("45"), D("184.6"), D("169"))
    assert cents(premium(2400, scale=rounded)) == D("156116.59")


def test_gamma_is_derived_from_the_nodes() -> None:
    assert CURVE_X.gamma.quantize(D("0.000001")) == D("2.811088")
    exact = Scale("CURVE_POWER", D(1500) / THIRTEEN, D("45"), D(2400) / THIRTEEN, D("168.66"))
    assert exact.gamma.quantize(D("0.000001")) == D("2.811090")


def test_premium_per_shift_at_norm_and_ceiling() -> None:
    assert cents(CURVE_X.per_shift(CURVE_X.norm_per_shift)) == D("5192.31")
    assert cents(CURVE_X.per_shift(CURVE_X.ceiling_per_shift)) == D("12000.05")


def test_meter_price_grows_faster_with_every_200_meters() -> None:
    def rate(meters: int) -> Decimal:
        return CURVE_X.rate_at(D(meters) / THIRTEEN)

    steps = [rate(2000) - rate(1800), rate(2200) - rate(2000), rate(2400) - rate(2200)]
    for step, expected in zip(steps, (D("25.8971"), D("31.0397"), D("36.5958"))):
        assert abs(step - expected) <= D("0.05")
    assert steps[0] < steps[1] < steps[2]


def test_meter_price_is_constant_above_the_ceiling() -> None:
    assert CURVE_X.rate_at(CURVE_X.ceiling_per_shift) == D("168.66")
    assert CURVE_X.rate_at(D(3000) / THIRTEEN) == D("168.66")


@pytest.mark.parametrize("scale_type", ["CURVE_POWER", "CURVE_LINEAR"])
def test_premium_and_price_are_continuous_at_the_nodes(scale_type: str) -> None:
    scale = Scale(scale_type, CURVE_X.norm_per_shift, D("45"), CURVE_X.ceiling_per_shift, D("168.66"))
    eps = D("0.000001")
    for node in (scale.norm_per_shift, scale.ceiling_per_shift):
        assert abs(scale.per_shift(node + eps) - scale.per_shift(node - eps)) < D("0.001")
        assert abs(scale.rate_at(node + eps) - scale.rate_at(node - eps)) < D("0.01")


@pytest.mark.parametrize("scale_type", ["CURVE_POWER", "CURVE_LINEAR"])
def test_premium_per_shift_is_convex(scale_type: str) -> None:
    scale = Scale(scale_type, CURVE_X.norm_per_shift, D("45"), CURVE_X.ceiling_per_shift, D("168.66"))
    values = [scale.per_shift(D(pace)) for pace in range(0, 260, 5)]
    second = [values[i + 1] - 2 * values[i] + values[i - 1] for i in range(1, len(values) - 1)]
    assert all(diff >= D("-0.000001") for diff in second)


STEP = Scale(
    "STEP",
    tiers=(
        ScaleTier(D(1500) / THIRTEEN, D("45")),
        ScaleTier(D(1800) / THIRTEEN, D("75")),
        ScaleTier(D(2400) / THIRTEEN, D("110")),
        ScaleTier(None, D("140")),
    ),
)
LINEAR = Scale("CURVE_LINEAR", CURVE_X.norm_per_shift, D("45"), CURVE_X.ceiling_per_shift, D("168.66"))


def test_every_shape_pays_rate_norm_below_the_norm() -> None:
    for scale in (CURVE_X, LINEAR, STEP):
        assert scale.per_shift(D("100")) == D("4500")


@pytest.mark.parametrize(("meters", "expected"), [(1800, 87183), (2000, 107175), (2400, 163647), (3000, 264843)])
def test_linear_curve_is_a_trapezoid(meters: int, expected: int) -> None:
    assert premium(meters, scale=LINEAR).quantize(D("1")) == D(expected)


@pytest.mark.parametrize(
    ("meters", "expected"),
    [(1500, "67500"), (1800, "90000"), (2000, "112000"), (2400, "156000"), (3000, "240000")],
)
def test_step_scale_sums_the_tiers(meters: int, expected: str) -> None:
    result = piece_premium(D(meters), STEP, THIRTEEN)
    assert cents(result.total) == D(expected)
    assert cents(sum((tier.amount for tier in result.tiers), D("0"))) == D(expected)
    assert cents(sum((tier.units for tier in result.tiers), D("0"))) == D(meters)


def test_premium_is_paid_on_the_mean_pace_not_per_shift() -> None:
    assert cents(premium(1980, 12)) == D("109857.35")
    per_shift = 6 * CURVE_X.per_shift(D("100")) + 6 * CURVE_X.per_shift(D("230"))
    assert cents(per_shift) == D("144927.72")


def test_premium_is_proportional_only_below_the_norm() -> None:
    assert premium(2400) != D("1.2") * premium(2000)
    assert cents(D("1.2") * premium(2000)) == D("123365.50")
    assert cents(premium(1200)) == cents(D("1.2") * premium(1000)) == D("54000")


def test_breakdown_shows_pace_rates_and_mean_price() -> None:
    result = piece_premium(D("2000"), CURVE_X, THIRTEEN)
    assert result.pace == D("2000") / THIRTEEN
    assert cents(result.last_rate) == D("101.02")
    assert result.mean_rate == result.total / D("2000")
    assert "gamma" in result.lineage and "2,811088" in result.lineage["gamma"]


def test_zero_output_pays_nothing() -> None:
    result = piece_premium(D("0"), CURVE_X, THIRTEEN)
    assert result.total == 0
    assert result.mean_rate is None


def test_zero_effective_shifts_is_an_input_error() -> None:
    with pytest.raises(PayrollInputError):
        piece_premium(D("100"), CURVE_X, D("0"))


def test_pace_flag_above_one_and_a_fifth_of_the_ceiling() -> None:
    assert [flag.code for flag in pace_flags(CURVE_X, D("230"))] == ["PACE_ABOVE_CEILING"]
    assert pace_flags(CURVE_X, D("220")) == ()
    assert pace_flags(STEP, D("500")) == ()


def test_series_contains_nodes_pace_and_reaches_beyond_the_ceiling() -> None:
    pace = D("2000") / THIRTEEN
    series = scale_series(CURVE_X, pace)
    paces = [point.pace for point in series]
    assert {CURVE_X.norm_per_shift, CURVE_X.ceiling_per_shift, pace} <= set(paces)
    assert paces == sorted(paces)
    assert series[0].pace == 0 and series[0].per_shift == 0
    assert paces[-1] == CURVE_X.ceiling_per_shift * D("1.3")
    rates = [point.rate for point in series]
    assert rates == sorted(rates)
    assert series[-1].rate == D("168.66")
```

- [ ] **Step 3: убедиться, что падает.**

Run: `../../../.venv/bin/python -m pytest tests/test_payroll_curve.py -q`
Expected: FAIL — `ImportError: cannot import name 'Scale' from 'cost.model.payroll'`.

- [ ] **Step 4: реализация.** Дописать в конец `cost/model/payroll.py`:

```python
# --- Шкала и сдельная премия ------------------------------------------------

@dataclass(frozen=True)
class PayrollFlag:
    """Сигнал на проверку начальнику участка; расчёт он не блокирует."""

    code: str
    message: str


@dataclass(frozen=True)
class ScaleTier:
    upto_per_shift: Decimal | None
    rate: Decimal


@dataclass(frozen=True)
class Scale:
    """Шкала сдельной премии ставки: кривая цены единицы или ступени (Т5).

    Согласованность полей проверяет схема ставки (`LaborRatePayload`), здесь
    шкала уже корректна: у кривой есть все четыре узла, у ступеней — верх у
    всех, кроме последней.
    """

    scale_type: str
    norm_per_shift: Decimal | None = None
    rate_norm: Decimal | None = None
    ceiling_per_shift: Decimal | None = None
    rate_ceiling: Decimal | None = None
    tiers: tuple[ScaleTier, ...] = ()
    source: str = ""

    @property
    def is_curve(self) -> bool:
        return self.scale_type in CURVE_SCALES

    @property
    def gamma(self) -> Decimal | None:
        """Показатель степенной кривой: ln(r_потолок / r_норма) / ln(потолок / норма)."""

        if self.scale_type != "CURVE_POWER":
            return None
        return (self.rate_ceiling / self.rate_norm).ln() / (self.ceiling_per_shift / self.norm_per_shift).ln()

    def rate_at(self, pace: Decimal) -> Decimal:
        """Цена единицы при темпе `pace` за смену — цена последнего метра r(m)."""

        if self.scale_type == "STEP":
            for tier in self.tiers:
                if tier.upto_per_shift is None or pace <= tier.upto_per_shift:
                    return tier.rate
            return self.tiers[-1].rate
        if pace <= self.norm_per_shift:
            return self.rate_norm
        if pace >= self.ceiling_per_shift:
            return self.rate_ceiling
        if self.scale_type == "CURVE_POWER":
            return self.rate_norm * (pace / self.norm_per_shift) ** self.gamma
        return self.rate_norm + (self.rate_ceiling - self.rate_norm) * (pace - self.norm_per_shift) / (
            self.ceiling_per_shift - self.norm_per_shift
        )

    def per_shift(self, pace: Decimal) -> Decimal:
        """Премия за смену p(m) — интеграл цены единицы от 0 до m в замкнутом виде."""

        if pace <= 0:
            return ZERO
        if self.scale_type == "STEP":
            return sum((units * rate for _, _, units, rate in self.tier_split(pace)), ZERO)
        norm, ceiling = self.norm_per_shift, self.ceiling_per_shift
        if pace <= norm:
            return self.rate_norm * pace
        top = min(pace, ceiling)
        if self.scale_type == "CURVE_POWER":
            power = self.gamma + 1
            rising = self.rate_norm * norm * ((top / norm) ** power - 1) / power
        else:
            rising = (top - norm) * (self.rate_norm + self.rate_at(top)) / 2
        above = self.rate_ceiling * (pace - ceiling) if pace > ceiling else ZERO
        return self.rate_norm * norm + rising + above

    def tier_split(self, pace: Decimal) -> tuple[tuple[Decimal, Decimal | None, Decimal, Decimal], ...]:
        """Ступени при темпе `pace`: (низ, верх, единиц за смену в ступени, расценка)."""

        rows: list[tuple[Decimal, Decimal | None, Decimal, Decimal]] = []
        lower = ZERO
        for tier in self.tiers:
            upper = tier.upto_per_shift
            top = pace if upper is None else min(pace, upper)
            rows.append((lower, upper, max(ZERO, top - lower), tier.rate))
            if upper is None or pace <= upper:
                break
            lower = upper
        return tuple(rows)

    def breakpoints(self) -> tuple[Decimal, ...]:
        if self.is_curve:
            return (self.norm_per_shift, self.ceiling_per_shift)
        return tuple(tier.upto_per_shift for tier in self.tiers if tier.upto_per_shift is not None)


@dataclass(frozen=True)
class PremiumTier:
    lower: Decimal
    upper: Decimal | None
    rate: Decimal
    # Единиц и рублей за вахту.
    units: Decimal
    amount: Decimal


@dataclass(frozen=True)
class PiecePremium:
    total: Decimal
    output: Decimal
    effective_shifts: Decimal
    pace: Decimal
    per_shift: Decimal
    last_rate: Decimal
    mean_rate: Decimal | None
    tiers: tuple[PremiumTier, ...] = ()
    lineage: Mapping[str, str] = field(default_factory=dict)


def gamma_text(gamma: Decimal) -> str:
    return format(gamma.quantize(Decimal("0.000001")), "f").replace(".", ",")


def piece_premium(output: Decimal, scale: Scale, effective: Decimal) -> PiecePremium:
    """Премия за вахту P = S_эфф × p(M / S_эфф) — на одном темпе вахты (TASK-010 §2.3).

    Посменный расчёт запрещён: кривая выпукла, и рваный ритм (6 смен по 100 м и
    6 по 230) дал бы больше ровного (12 по 165) при тех же метрах.
    """

    if effective <= 0:
        raise PayrollInputError("Эффективных смен должно быть больше нуля.")
    pace = output / effective
    per_shift = scale.per_shift(pace)
    total = effective * per_shift
    tiers: tuple[PremiumTier, ...] = ()
    if scale.scale_type == "STEP":
        tiers = tuple(
            PremiumTier(lower, upper, rate, units * effective, units * effective * rate)
            for lower, upper, units, rate in scale.tier_split(pace)
        )
    lineage = {
        "pace": f"{fn(output)} / {fn(effective)} см = {fn(pace)} за смену",
        "premium": f"{fn(effective)} см × p({fn(pace)}) = {fn(effective)} × {fn(per_shift)} ₽ = {fn(total)} ₽",
    }
    if scale.gamma is not None:
        lineage["gamma"] = (
            f"ln({fn(scale.rate_ceiling)} / {fn(scale.rate_norm)}) / "
            f"ln({fn(scale.ceiling_per_shift)} / {fn(scale.norm_per_shift)}) = {gamma_text(scale.gamma)}"
        )
    return PiecePremium(
        total=total,
        output=output,
        effective_shifts=effective,
        pace=pace,
        per_shift=per_shift,
        last_rate=scale.rate_at(pace),
        mean_rate=total / output if output > 0 else None,
        tiers=tiers,
        lineage=lineage,
    )


def pace_flags(scale: Scale, pace: Decimal) -> tuple[PayrollFlag, ...]:
    """Темп выше 1,2 потолка — сигнал проверить метры или списанные простои."""

    if not scale.is_curve or pace <= PACE_FLAG_RATIO * scale.ceiling_per_shift:
        return ()
    return (
        PayrollFlag(
            "PACE_ABOVE_CEILING",
            f"Темп {fn(pace)} за смену выше {fn(PACE_FLAG_RATIO)} × потолка ({fn(scale.ceiling_per_shift)}): "
            "проверьте метры и списанные простои.",
        ),
    )


# --- График шкалы -----------------------------------------------------------


@dataclass(frozen=True)
class ScalePoint:
    pace: Decimal
    rate: Decimal
    per_shift: Decimal


def scale_series(scale: Scale, pace: Decimal | None = None) -> tuple[ScalePoint, ...]:
    """Точки графика шкалы: цена единицы r(m) и премия за смену p(m).

    Интерфейс рисует график по этим точкам, а не своей формулой (Т6): кривая
    одна — та, по которой посчитана премия. Узлы шкалы и темп входят точно,
    чтобы излом и маркер стояли на своих местах.
    """

    anchors = scale.breakpoints()
    anchor = max(anchors) if anchors else (pace or HUNDRED)
    upper = anchor * SERIES_SPAN
    if pace is not None and pace > upper:
        upper = pace * Decimal("1.1")
    paces = {upper * step / SERIES_STEPS for step in range(SERIES_STEPS + 1)}
    paces.update(anchors)
    if pace is not None:
        paces.add(pace)
    return tuple(ScalePoint(m, scale.rate_at(m), scale.per_shift(m)) for m in sorted(paces))
```

- [ ] **Step 5: тест проходит.**

Run: `../../../.venv/bin/python -m pytest tests/test_payroll_curve.py tests/test_payroll_meters.py -q`
Expected: PASS (47 passed).

- [ ] **Step 6: коммит.**

```bash
git add cost/model/payroll.py tests/payroll_fixtures.py tests/test_payroll_curve.py
git commit -m "ФОТ (TASK-010 PR 2): шкала сдельной премии — кривая, ступени, ряды графика

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Задача 3: эффективные смены, флаг простоев, защита входа

**Files:**
- Modify: `cost/model/payroll.py` (дописать в конец)
- Modify: `tests/payroll_fixtures.py`
- Test: `tests/test_payroll_shifts.py`

**Interfaces:**
- Consumes: `PayrollFlag`, `piece_premium` (задача 2), `WRITE_OFF_FLAG_SHARE`.
- Produces: `DowntimeReason(code, name, excusable, planned_maintenance)`, `DowntimeEntry(code, hours)`,
  `EffectiveShifts(shifts, effective, excusable_hours, maintenance_hours, written_off_share, flags, lineage)`;
  `plan_effective_shifts(shift_days_on, maintenance_shifts)`; `effective_shifts(shifts, shift_hours, downtime,
  reasons: Mapping[str, DowntimeReason])`.
- Fixture: `REASONS`.

- [ ] **Step 1: фикстура.** В `tests/payroll_fixtures.py` заменить импорты из `cost.model.payroll` и
  `cost.v2.payroll_defaults` на

```python
from cost.model.payroll import DifficultyTables, DowntimeReason, HardnessBand, Scale
from cost.v2.payroll_defaults import DOWNTIME_REASONS, HARDNESS_BANDS
```

и дописать в конец:

```python
REASONS = {code: DowntimeReason(code, name, excusable, maintenance) for code, name, excusable, maintenance in DOWNTIME_REASONS}
```

- [ ] **Step 2: падающий тест.** Создать `tests/test_payroll_shifts.py`:

```python
"""Эффективные смены, флаги простоев и защита входа (TASK-010 §2.3, решения §2.3, Т12)."""
from __future__ import annotations

from decimal import Decimal

import pytest

from cost.model.payroll import (
    DowntimeEntry,
    PayrollInputError,
    effective_shifts,
    piece_premium,
    plan_effective_shifts,
)
from tests.payroll_fixtures import CURVE_X, REASONS, cents

D = Decimal


def fact(shifts: str | int, *downtime: tuple[str, str | int]):
    return effective_shifts(D(shifts), D("11"), [DowntimeEntry(code, D(hours)) for code, hours in downtime], REASONS)


def premium(meters: Decimal, shifts: Decimal) -> Decimal:
    return piece_premium(meters, CURVE_X, shifts).total


def test_plan_is_rotation_minus_planned_maintenance() -> None:
    plan = plan_effective_shifts(D("15"), D("2"))
    assert plan.effective == D("13")
    assert plan.flags == ()
    assert cents(premium(D("2400"), plan.effective)) == D("156000.67")


def test_three_idle_shifts_not_by_drillers_fault() -> None:
    shifts = fact(13, ("DT_RIG_REPAIR", 33))
    assert shifts.effective == D("10")
    assert cents(premium(D(24000) / D(13), shifts.effective)) == D("120000.52")


def test_seven_idle_hours_raise_the_premium_for_the_same_meters() -> None:
    shifts = fact(13, ("DT_WEATHER", 7))
    assert shifts.effective == D("13") - D("7") / D("11")
    assert cents(premium(D("2000"), shifts.effective)) == D("108400.68")
    assert cents(premium(D("2000"), D("11"))) == D("126920.54")


def test_downtime_by_drillers_fault_is_not_written_off() -> None:
    shifts = fact(13, ("DT_FAULT_BREAKDOWN", 7))
    assert shifts.effective == D("13")
    assert shifts.excusable_hours == 0
    assert cents(premium(D("2000"), shifts.effective)) == D("102804.58")


def test_writing_off_more_than_a_quarter_raises_a_flag() -> None:
    shifts = fact(13, ("DT_WAIT_BLOCK", 40))
    assert shifts.written_off_share == D("40") / D("143")
    assert [flag.code for flag in shifts.flags] == ["DOWNTIME_OVER_25"]
    assert "27,97 %" in shifts.flags[0].message
    assert shifts.effective == D("13") - D("40") / D("11")


def test_planned_maintenance_neither_raises_nor_hides_the_flag() -> None:
    with_maintenance = fact(15, ("DT_PLANNED_MAINTENANCE", 22), ("DT_WAIT_BLOCK", 40))
    assert with_maintenance.written_off_share == D("40") / D("143")
    assert [flag.code for flag in with_maintenance.flags] == ["DOWNTIME_OVER_25"]
    assert with_maintenance.maintenance_hours == D("22")
    only_maintenance = fact(15, ("DT_PLANNED_MAINTENANCE", 22))
    assert only_maintenance.flags == ()
    assert only_maintenance.effective == D("13")


@pytest.mark.parametrize("hours", [143, 150])
def test_downtime_for_the_whole_rotation_is_an_input_error(hours: int) -> None:
    with pytest.raises(PayrollInputError):
        fact(13, ("DT_RIG_REPAIR", hours))


def test_unknown_downtime_code_is_an_input_error() -> None:
    with pytest.raises(PayrollInputError, match="DT_NOPE"):
        fact(13, ("DT_NOPE", 5))


def test_maintenance_for_the_whole_rotation_is_an_input_error() -> None:
    with pytest.raises(PayrollInputError):
        plan_effective_shifts(D("2"), D("2"))
```

- [ ] **Step 3: убедиться, что падает.**

Run: `../../../.venv/bin/python -m pytest tests/test_payroll_shifts.py -q`
Expected: FAIL — `ImportError: cannot import name 'DowntimeReason' from 'cost.model.payroll'`.

- [ ] **Step 4: реализация.** Дописать в конец `cost/model/payroll.py`:

```python
# --- Эффективные смены ------------------------------------------------------


@dataclass(frozen=True)
class DowntimeReason:
    code: str
    name: str
    excusable: bool
    planned_maintenance: bool


@dataclass(frozen=True)
class DowntimeEntry:
    code: str
    hours: Decimal


@dataclass(frozen=True)
class EffectiveShifts:
    shifts: Decimal
    effective: Decimal
    excusable_hours: Decimal = ZERO
    maintenance_hours: Decimal = ZERO
    # Доля часов вахты, списанных не по вине машиниста, без планового ТОиР.
    written_off_share: Decimal | None = None
    flags: tuple[PayrollFlag, ...] = ()
    lineage: Mapping[str, str] = field(default_factory=dict)


def plan_effective_shifts(shift_days_on: Decimal, maintenance_shifts: Decimal) -> EffectiveShifts:
    """План: S_эфф = смены вахты − плановое ТОиР (решение владельца 13.09: 15 − 2 = 13)."""

    effective = shift_days_on - maintenance_shifts
    if effective <= 0:
        raise PayrollInputError("Плановое ТОиР занимает всю вахту: эффективных смен не осталось.")
    return EffectiveShifts(
        shifts=shift_days_on,
        effective=effective,
        lineage={"effective_shifts": f"{fn(shift_days_on)} см − {fn(maintenance_shifts)} см ТОиР = {fn(effective)} см"},
    )


def effective_shifts(
    shifts: Decimal,
    shift_hours: Decimal,
    downtime: Sequence[DowntimeEntry],
    reasons: Mapping[str, DowntimeReason],
) -> EffectiveShifts:
    """Факт: S_эфф = смены − Σ часов простоя не по вине машиниста / часы смены.

    Простой по вине машиниста не вычитается. Предела списания нет (решение
    владельца), но вход проверяется: больше часов, чем в вахте, или ноль
    эффективных смен — ошибка, а не деление на ноль и не премия «45 × M».
    """

    if shift_hours <= 0:
        raise PayrollInputError("Продолжительность смены должна быть больше нуля.")
    excusable = ZERO
    maintenance = ZERO
    for entry in downtime:
        reason = reasons.get(entry.code)
        if reason is None:
            raise PayrollInputError(f"Код простоя {entry.code} не найден в справочнике «Причины простоев».")
        if not reason.excusable:
            continue
        excusable += entry.hours
        if reason.planned_maintenance:
            maintenance += entry.hours
    available = shifts * shift_hours
    if excusable > available:
        raise PayrollInputError(
            f"Простоев не по вине машиниста {fn(excusable)} ч — больше часов вахты ({fn(available)} ч)."
        )
    effective = shifts - excusable / shift_hours
    if effective <= 0:
        raise PayrollInputError("Простои не по вине машиниста заняли всю вахту: эффективных смен не осталось.")
    # Знаменатель — часы вахты без планового ТОиР: ТОиР списывается всегда и
    # долю «подозрительных» списаний не должен ни раздувать, ни прятать.
    base = available - maintenance
    share = (excusable - maintenance) / base if base > 0 else None
    flags: list[PayrollFlag] = []
    if share is not None and share > WRITE_OFF_FLAG_SHARE:
        flags.append(
            PayrollFlag(
                "DOWNTIME_OVER_25",
                f"Списано {percent(share)} часов вахты не по вине машиниста (без планового ТОиР) — "
                f"больше {percent(WRITE_OFF_FLAG_SHARE)}: проверьте коды простоев.",
            )
        )
    return EffectiveShifts(
        shifts=shifts,
        effective=effective,
        excusable_hours=excusable,
        maintenance_hours=maintenance,
        written_off_share=share,
        flags=tuple(flags),
        lineage={
            "effective_shifts": f"{fn(shifts)} см − {fn(excusable)} ч / {fn(shift_hours)} ч = {fn(effective)} см"
        },
    )
```

- [ ] **Step 5: тест проходит.**

Run: `../../../.venv/bin/python -m pytest tests/test_payroll_shifts.py -q`
Expected: PASS (10 passed).

- [ ] **Step 6: коммит.**

```bash
git add cost/model/payroll.py tests/payroll_fixtures.py tests/test_payroll_shifts.py
git commit -m "ФОТ (TASK-010 PR 2): эффективные смены, флаг простоев и защита входа

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Задача 4: месячный ФОТ должности и регрессия по файлу

**Files:**
- Modify: `cost/model/payroll.py` (дописать в конец)
- Modify: `tests/payroll_fixtures.py`
- Test: `tests/test_payroll_regression_2026_09.py`

**Interfaces:**
- Consumes: `Scale` (задача 2), `fn`, `SHORT_WEEK_CLASSES`.
- Produces: `PayrollCalendar(year, mrot, annual_hours_40, annual_hours_36, work_days_year, holidays_year,
  night_pct, vacation_days_base, margin_share_warn, source)`; `PositionPay(code, name, salary, salary_source,
  week_hours, work_conditions_class, hazard_pct, night_hours_per_shift, extra_vacation_days, pay_system,
  difficulty, kpi_bonus_pct, scale)`; `SiteSchedule(code, name, shift_days_on, shift_days_off, travel_days,
  night_shift_share, maintenance_shifts, regional_coefficient, northern_pct, contract_k)`;
  `PayrollRates(ndfl_rate, sfr_rate, injury_rate, shift_allowance_per_day, shift_hours, extra_tariffs, source)`;
  `PayrollInputs(calendar, position, site, rates)`; `PayrollRow(code, name, kind, amount, formula)`;
  `PayrollResult(rows, warnings)` с `.amount(code)`, `.gross`, `.company_cost`; `week_hours_for(class, override)
  -> int`; `extra_tariff_rate(position, rates) -> (rate, warning)`; `payroll_month(inputs, premium=0, *,
  work_days_month=None) -> PayrollResult`; `premium_cost_factor(inputs) -> (Decimal, str)`.
- Fixture: `file_inputs(**position_overrides) -> PayrollInputs`.

- [ ] **Step 1: фикстура.** В `tests/payroll_fixtures.py` заменить блок импортов (между `from __future__` и
  `CENT = `) на

```python
from decimal import Decimal
from typing import Any

from cost.model.payroll import (
    DifficultyTables,
    DowntimeReason,
    HardnessBand,
    PayrollCalendar,
    PayrollInputs,
    PayrollRates,
    PositionPay,
    Scale,
    SiteSchedule,
)
from cost.v2.payroll_defaults import DOWNTIME_REASONS, EXTRA_TARIFFS, HARDNESS_BANDS
```

и дописать в конец:

```python
def file_inputs(**position_overrides: Any) -> PayrollInputs:
    """Машинист из файла: МРОТ, класс 3.2, вредность 4 %, доп. отпуск 7 дн, 8 ночных часов."""

    position = {
        "code": "P_DRILLER",
        "name": "Машинист буровой установки",
        "salary": Decimal("27093"),
        "salary_source": "labor_rates.LR_DRILLER",
        "week_hours": 40,
        "work_conditions_class": "3.2",
        "hazard_pct": Decimal("0.04"),
        "night_hours_per_shift": Decimal("8"),
        "extra_vacation_days": Decimal("7"),
        "pay_system": "PIECE_PROGRESSIVE",
        "difficulty": "NORMALIZED_METERS",
        "scale": CURVE_X,
    }
    position.update(position_overrides)
    return PayrollInputs(
        calendar=PayrollCalendar(
            year=2026,
            mrot=Decimal("27093"),
            annual_hours_40=Decimal("1972"),
            annual_hours_36=Decimal("1774.4"),
            work_days_year=Decimal("247"),
            holidays_year=Decimal("14"),
            night_pct=Decimal("0.20"),
            vacation_days_base=Decimal("28"),
            margin_share_warn=Decimal("0.70"),
        ),
        position=PositionPay(**position),
        site=SiteSchedule(code="SITE_LOM", name="Ломовское месторождение"),
        rates=PayrollRates(
            ndfl_rate=Decimal("0.13"),
            sfr_rate=Decimal("0.15"),
            injury_rate=Decimal("0.021"),
            shift_allowance_per_day=Decimal("700"),
            shift_hours=Decimal("11"),
            extra_tariffs={row["work_conditions_class"]: Decimal(row["rate"]) for row in EXTRA_TARIFFS},
        ),
    )
```

- [ ] **Step 2: падающий тест.** Создать `tests/test_payroll_regression_2026_09.py`:

```python
"""Регрессия по файлу владельца «Расчёт заработной платы» (лист «Постоянная часть»).

Премия 170 000 ₽ — как в файле (2 000 м × 85 ₽). Затраты компании без НДФЛ:
358 103,01 ₽ против 391 010,22 ₽ в файле, где НДФЛ прибавлен к начисленному.
"""
from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

import pytest

from cost.model.payroll import (
    extra_tariff_rate,
    payroll_month,
    piece_premium,
    premium_cost_factor,
    week_hours_for,
)
from tests.payroll_fixtures import CURVE_X, cents, file_inputs

D = Decimal
FILE_PREMIUM = D("170000")


def test_file_with_its_divisor_21_5() -> None:
    result = payroll_month(file_inputs(), FILE_PREMIUM, work_days_month=D("21.5"))
    assert cents(result.amount("INTERSHIFT_REST")) == D("18902.09")
    assert cents(result.gross) == D("253132.36")
    assert cents(result.amount("NDFL")) == D("32907.21")
    assert cents(result.amount("NET")) == D("232125.16")
    assert cents(result.company_cost) == D("358103.01")


def test_calendar_divisor_is_work_days_over_twelve() -> None:
    result = payroll_month(file_inputs(), FILE_PREMIUM)
    assert cents(result.amount("INTERSHIFT_REST")) == D("19743.89")
    assert cents(result.gross) == D("254100.42")
    assert cents(result.company_cost) == D("359427.01")


def test_income_tax_is_withheld_not_added_to_company_cost() -> None:
    result = payroll_month(file_inputs(), FILE_PREMIUM, work_days_month=D("21.5"))
    cost_rows = sum((row.amount for row in result.rows if row.kind == "COST"), D("0"))
    assert abs(result.company_cost - (result.gross + cost_rows)) < D("1e-18")
    assert cents(result.company_cost + result.amount("NDFL")) == D("391010.22")
    assert {row.code for row in result.rows if row.kind == "INFO"} == {"NDFL", "NET"}


def test_rows_follow_the_file_order() -> None:
    codes = [row.code for row in payroll_month(file_inputs(), FILE_PREMIUM).rows]
    assert codes == [
        "SALARY", "HAZARD", "NIGHT", "HOLIDAYS", "INTERSHIFT_REST", "PIECE_PREMIUM", "KPI_BONUS",
        "REGIONAL", "NORTHERN", "GROSS", "NDFL", "SHIFT_ALLOWANCE", "NET", "SFR", "EXTRA_TARIFF",
        "INJURY", "RESERVE_EXTRA_VACATION", "RESERVE_VACATION", "COMPANY_COST",
    ]


def test_cost_per_premium_ruble_matches_the_finite_difference() -> None:
    inputs = file_inputs()
    factor, formula = premium_cost_factor(inputs)
    difference = payroll_month(inputs, D("170001")).company_cost - payroll_month(inputs, FILE_PREMIUM).company_cost
    assert abs(factor - difference) < D("1e-9")
    assert abs(factor - D("1.572827209")) < D("1e-9")
    assert cents(D("168.66") * factor) == D("265.27")
    assert "1,572827" in formula


def test_curve_premium_enters_every_derived_row() -> None:
    inputs = file_inputs()
    premium = piece_premium(D("2000"), CURVE_X, D("13")).total
    factor, _ = premium_cost_factor(inputs)
    with_premium = payroll_month(inputs, premium)
    without = payroll_month(inputs, D("0"))
    assert with_premium.amount("PIECE_PREMIUM") == premium
    assert abs(with_premium.company_cost - without.company_cost - premium * factor) < D("1e-6")
    assert with_premium.amount("SFR") > without.amount("SFR")


def test_kpi_bonus_is_a_share_of_the_salary() -> None:
    result = payroll_month(file_inputs(kpi_bonus_pct=D("0.1")), D("0"))
    assert result.amount("KPI_BONUS") == D("2709.3")
    assert result.gross > payroll_month(file_inputs(), D("0")).gross


@pytest.mark.parametrize(
    ("work_class", "override", "hours"),
    [("3.2", None, 40), ("3.3", None, 36), ("3.4", None, 36), ("4", None, 36), (None, None, 40), ("3.3", "40", 40), ("3.2", "36", 36)],
)
def test_week_hours_follow_the_work_conditions_class(work_class: str | None, override: str | None, hours: int) -> None:
    assert week_hours_for(work_class, override) == hours


def test_short_week_raises_the_hour_rate() -> None:
    forty = payroll_month(file_inputs(), D("0")).amount("NIGHT")
    thirty_six = payroll_month(file_inputs(week_hours=36), D("0")).amount("NIGHT")
    assert abs(thirty_six - forty * D("1972") / D("1774.4")) < D("1e-18")


def test_classes_one_and_two_pay_no_extra_tariff() -> None:
    result = payroll_month(file_inputs(work_conditions_class="2"), FILE_PREMIUM)
    assert result.amount("EXTRA_TARIFF") == 0
    assert result.warnings == ()


def test_hazardous_class_without_tariff_row_warns() -> None:
    inputs = file_inputs()
    inputs = replace(inputs, rates=replace(inputs.rates, extra_tariffs={}))
    rate, warning = extra_tariff_rate(inputs.position, inputs.rates)
    assert rate == 0
    assert "3.2" in warning
    assert payroll_month(inputs, FILE_PREMIUM).warnings == (warning,)
```

- [ ] **Step 3: убедиться, что падает.**

Run: `../../../.venv/bin/python -m pytest tests/test_payroll_regression_2026_09.py -q`
Expected: FAIL — `ImportError: cannot import name 'PayrollCalendar' from 'cost.model.payroll'`.

- [ ] **Step 4: реализация.** Дописать в конец `cost/model/payroll.py`:

```python
# --- Месячный ФОТ должности -------------------------------------------------


@dataclass(frozen=True)
class PayrollCalendar:
    """Параметры года из «Параметров ФОТ»."""

    year: int
    mrot: Decimal
    annual_hours_40: Decimal
    annual_hours_36: Decimal
    work_days_year: Decimal
    holidays_year: Decimal
    night_pct: Decimal
    vacation_days_base: Decimal
    margin_share_warn: Decimal
    source: str = "payroll_params"


@dataclass(frozen=True)
class PositionPay:
    """Должность для методики: нормы из «Должностей», деньги из «Ставок персонала»."""

    code: str
    name: str
    salary: Decimal
    salary_source: str
    week_hours: int
    work_conditions_class: str | None = None
    hazard_pct: Decimal = ZERO
    night_hours_per_shift: Decimal = ZERO
    extra_vacation_days: Decimal = ZERO
    pay_system: str = "TIME_BONUS"
    difficulty: str = "PLAIN"
    kpi_bonus_pct: Decimal = ZERO
    scale: Scale | None = None


@dataclass(frozen=True)
class SiteSchedule:
    """Вахта и надбавки объекта."""

    code: str
    name: str
    shift_days_on: Decimal = Decimal("15")
    shift_days_off: Decimal = Decimal("15")
    travel_days: Decimal = Decimal("2")
    night_shift_share: Decimal = Decimal("0.5")
    maintenance_shifts: Decimal = Decimal("2")
    regional_coefficient: Decimal = Decimal("0.15")
    northern_pct: Decimal = ZERO
    contract_k: Decimal = ONE


@dataclass(frozen=True)
class PayrollRates:
    """Ставки организации, которые нужны методике (Т2, Т8)."""

    ndfl_rate: Decimal
    sfr_rate: Decimal
    injury_rate: Decimal
    shift_allowance_per_day: Decimal
    shift_hours: Decimal
    extra_tariffs: Mapping[str, Decimal] = field(default_factory=dict)
    source: str = "organization_rates"


@dataclass(frozen=True)
class PayrollInputs:
    calendar: PayrollCalendar
    position: PositionPay
    site: SiteSchedule
    rates: PayrollRates


@dataclass(frozen=True)
class PayrollRow:
    code: str
    name: str
    # ACCRUAL — входит в начисленное; SUBTOTAL — итог начисленного; INFO —
    # справочно, в затраты не входит; COST — затраты сверх начисленного;
    # TOTAL — затраты компании.
    kind: str
    amount: Decimal
    formula: str


@dataclass(frozen=True)
class PayrollResult:
    rows: tuple[PayrollRow, ...]
    warnings: tuple[str, ...] = ()

    def amount(self, code: str) -> Decimal:
        return next(row.amount for row in self.rows if row.code == code)

    @property
    def gross(self) -> Decimal:
        return self.amount("GROSS")

    @property
    def company_cost(self) -> Decimal:
        return self.amount("COMPANY_COST")


def week_hours_for(work_conditions_class: str | None, override: str | None) -> int:
    """Рабочая неделя: переопределение, иначе по классу условий труда (ст. 92 ТК РФ)."""

    if override:
        return int(override)
    return 36 if work_conditions_class in SHORT_WEEK_CLASSES else 40


def extra_tariff_rate(position: PositionPay, rates: PayrollRates) -> tuple[Decimal, str]:
    """Доп. тариф взносов по классу должности и предупреждение (пусто — нет).

    У классов 1 и 2 тарифа нет (ст. 428 НК РФ); у вредного класса без строки в
    таблице организации — 0 с предупреждением, как в проверке ревизии.
    """

    cls = position.work_conditions_class
    if cls is None or cls in ("1", "2"):
        return ZERO, ""
    rate = rates.extra_tariffs.get(cls)
    if rate is None:
        return ZERO, (
            f"Класс условий труда {cls} у должности «{position.name}»: доп. тариф не задан "
            "в «Ставках и надбавках организации», принят 0."
        )
    return rate, ""


def payroll_month(
    inputs: PayrollInputs, premium: Decimal = ZERO, *, work_days_month: Decimal | None = None
) -> PayrollResult:
    """Месячный ФОТ должности на объекте — строки файла владельца в его порядке.

    `premium` — сдельная премия за вахту (`piece_premium`). `work_days_month` —
    делитель межвахтового отдыха; по умолчанию рабочих дней года / 12 (решение
    владельца 13.09), регрессия по файлу подставляет 21,5.

    Отличие от файла: НДФЛ удерживается из начисленного и в затраты компании не
    входит (в файле 391 010 ₽ вместо 358 103 ₽). Постоянная часть от простоев
    не зависит: машинист за чужой простой не платит.
    """

    calendar, position, site, rates = inputs.calendar, inputs.position, inputs.site, inputs.rates
    annual_hours = calendar.annual_hours_40 if position.week_hours == 40 else calendar.annual_hours_36
    hours_month = annual_hours / 12
    salary = position.salary
    hour_rate = salary / hours_month
    rows: list[PayrollRow] = []

    def add(code: str, name: str, kind: str, amount: Decimal, formula: str) -> Decimal:
        rows.append(PayrollRow(code, name, kind, amount, formula))
        return amount

    add("SALARY", "Оклад", "ACCRUAL", salary, f"{position.salary_source}: {fn(salary)} ₽")
    hazard = add(
        "HAZARD", "Надбавка за вредность", "ACCRUAL", salary * position.hazard_pct,
        f"{fn(salary)} ₽ × {fn(position.hazard_pct)}",
    )
    night_hours = site.shift_days_on * position.night_hours_per_shift * site.night_shift_share
    night = add(
        "NIGHT", "Доплата за ночные", "ACCRUAL", night_hours * hour_rate * calendar.night_pct,
        f"{fn(site.shift_days_on)} см × {fn(position.night_hours_per_shift)} ч × {fn(site.night_shift_share)} "
        f"× {fn(hour_rate)} ₽/ч × {fn(calendar.night_pct)}",
    )
    days = site.shift_days_on + site.shift_days_off
    holiday_share = site.shift_days_on / days if days > 0 else ZERO
    holidays = add(
        "HOLIDAYS", "Оплата праздников", "ACCRUAL",
        calendar.holidays_year * holiday_share * rates.shift_hours / 12 * hour_rate,
        f"{fn(calendar.holidays_year)} дн × {fn(holiday_share)} × {fn(rates.shift_hours)} ч / 12 × {fn(hour_rate)} ₽/ч",
    )
    divisor = work_days_month if work_days_month is not None else calendar.work_days_year / 12
    rest = add(
        "INTERSHIFT_REST", "Межвахтовый отдых", "ACCRUAL", salary / divisor * site.shift_days_off,
        f"{fn(salary)} ₽ / {fn(divisor)} дн × {fn(site.shift_days_off)} дн",
    )
    add("PIECE_PREMIUM", "Сдельная премия", "ACCRUAL", premium, f"{fn(premium)} ₽ по шкале ставки")
    kpi = add(
        "KPI_BONUS", "Премия КПЭ", "ACCRUAL", salary * position.kpi_bonus_pct,
        f"{fn(salary)} ₽ × {fn(position.kpi_bonus_pct)}",
    )
    rk_base = salary + hazard + night + holidays + rest + premium + kpi
    regional = add(
        "REGIONAL", "Районный коэффициент", "ACCRUAL", rk_base * site.regional_coefficient,
        f"{fn(rk_base)} ₽ × {fn(site.regional_coefficient)}",
    )
    northern = add(
        "NORTHERN", "Северная надбавка", "ACCRUAL", rk_base * site.northern_pct,
        f"{fn(rk_base)} ₽ × {fn(site.northern_pct)}",
    )
    gross = add("GROSS", "Итого начислено", "SUBTOTAL", rk_base + regional + northern, f"{fn(rk_base)} + {fn(regional)} + {fn(northern)} ₽")
    ndfl = add(
        "NDFL", "НДФЛ (удерживается из начисленного)", "INFO", gross * rates.ndfl_rate,
        f"{fn(gross)} ₽ × {fn(rates.ndfl_rate)}",
    )
    allowance_days = site.shift_days_on + site.travel_days
    allowance = add(
        "SHIFT_ALLOWANCE", "Надбавка за вахту", "COST", rates.shift_allowance_per_day * allowance_days,
        f"{fn(rates.shift_allowance_per_day)} ₽ × ({fn(site.shift_days_on)} + {fn(site.travel_days)}) дн",
    )
    add("NET", "К выплате на руки", "INFO", gross - ndfl + allowance, f"{fn(gross)} − {fn(ndfl)} + {fn(allowance)} ₽")
    sfr = add("SFR", "Страховые взносы", "COST", gross * rates.sfr_rate, f"{fn(gross)} ₽ × {fn(rates.sfr_rate)}")
    extra_rate, warning = extra_tariff_rate(position, rates)
    extra = add(
        "EXTRA_TARIFF", "Доп. тариф за класс условий труда", "COST", gross * extra_rate,
        f"{fn(gross)} ₽ × {fn(extra_rate)}",
    )
    injury = add("INJURY", "Взносы на травматизм", "COST", gross * rates.injury_rate, f"{fn(gross)} ₽ × {fn(rates.injury_rate)}")
    reserve_base = gross + sfr + extra + injury
    work_days = calendar.work_days_year
    extra_days = position.extra_vacation_days
    base_days = calendar.vacation_days_base
    reserve_extra = add(
        "RESERVE_EXTRA_VACATION", "Резерв дополнительного отпуска", "COST",
        reserve_base * extra_days / (extra_days + work_days),
        f"{fn(reserve_base)} ₽ × {fn(extra_days)} / ({fn(extra_days)} + {fn(work_days)})",
    )
    reserve_main = add(
        "RESERVE_VACATION", "Резерв основного отпуска", "COST",
        reserve_base * base_days / (base_days + work_days),
        f"{fn(reserve_base)} ₽ × {fn(base_days)} / ({fn(base_days)} + {fn(work_days)})",
    )
    add(
        "COMPANY_COST", "Затраты компании", "TOTAL",
        gross + allowance + sfr + extra + injury + reserve_extra + reserve_main,
        "начислено + вахта + взносы + доп. тариф + травматизм + резервы отпусков (без НДФЛ)",
    )
    return PayrollResult(tuple(rows), (warning,) if warning else ())


def premium_cost_factor(inputs: PayrollInputs) -> tuple[Decimal, str]:
    """Затраты компании на рубль сдельной премии: dЗатраты / dПремия.

    Премия входит в базу районного коэффициента, взносы считаются с
    начисленного, резервы — с начисленного и взносов; вахтовая надбавка от
    премии не зависит. По параметрам файла — 1,572827209.
    """

    position, site, rates, calendar = inputs.position, inputs.site, inputs.rates, inputs.calendar
    extra_rate, _ = extra_tariff_rate(position, rates)
    accrual = ONE + site.regional_coefficient + site.northern_pct
    contributions = ONE + rates.sfr_rate + extra_rate + rates.injury_rate
    work_days = calendar.work_days_year
    reserves = (
        ONE
        + position.extra_vacation_days / (position.extra_vacation_days + work_days)
        + calendar.vacation_days_base / (calendar.vacation_days_base + work_days)
    )
    factor = accrual * contributions * reserves
    formula = (
        f"(1 + {fn(site.regional_coefficient)} + {fn(site.northern_pct)}) × "
        f"(1 + {fn(rates.sfr_rate)} + {fn(extra_rate)} + {fn(rates.injury_rate)}) × "
        f"(1 + {fn(position.extra_vacation_days)} / {fn(position.extra_vacation_days + work_days)} + "
        f"{fn(calendar.vacation_days_base)} / {fn(calendar.vacation_days_base + work_days)}) = "
        f"{format(factor.quantize(Decimal('0.000001')), 'f').replace('.', ',')}"
    )
    return factor, formula
```

- [ ] **Step 5: тест проходит.**

Run: `../../../.venv/bin/python -m pytest tests/test_payroll_regression_2026_09.py -q`
Expected: PASS (17 passed).

- [ ] **Step 6: коммит.**

```bash
git add cost/model/payroll.py tests/payroll_fixtures.py tests/test_payroll_regression_2026_09.py
git commit -m "ФОТ (TASK-010 PR 2): месячный ФОТ должности, регрессия по файлу владельца

НДФЛ удерживается из начисленного и в затраты компании не входит:
358 103,01 ₽ вместо 391 010,22 ₽ файла.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Задача 5: доля стоимости последнего метра в марже

**Files:**
- Modify: `cost/model/payroll.py` (дописать в конец)
- Test: `tests/test_payroll_margin.py`

**Interfaces:**
- Consumes: `Scale`, `PayrollFlag`, `percent`, `premium_cost_factor` (тест).
- Produces: `CrewCost(position_code, name, headcount, scale, cost_factor)`; `SharePoint(pace, crew_share,
  main_share)`; `MarginCheck(status, threshold, price, variable, margin, plan, ceiling, crew, flags, warnings,
  lineage)`; `margin_check(*, main_scale, crew, pace, meters_factor, price, variable, threshold) -> MarginCheck`.

- [ ] **Step 1: падающий тест.** Создать `tests/test_payroll_margin.py`:

```python
"""Доля стоимости последнего метра в марже метра (решения §2.2)."""
from __future__ import annotations

from decimal import Decimal

from cost.model.payroll import CrewCost, Scale, ScaleTier, margin_check, premium_cost_factor
from tests.payroll_fixtures import CURVE_X, cents, file_inputs

D = Decimal
FACTOR, _ = premium_cost_factor(file_inputs())
CREW = (
    CrewCost("P_DRILLER", "Машинист", D("1"), CURVE_X, FACTOR),
    CrewCost("P_ASSISTANT", "Помощник", D("1"), CURVE_X, FACTOR),
)
PLAN_PACE = D("2000") / D("13")


def check(**overrides):
    fields = {
        "main_scale": CURVE_X,
        "crew": CREW,
        "pace": PLAN_PACE,
        "meters_factor": D("1"),
        "price": D("800"),
        "variable": D("250"),
        "threshold": D("0.70"),
        **overrides,
    }
    return margin_check(**fields)


def test_crew_of_two_on_curve_x() -> None:
    result = check()
    assert result.status == "CHECKED"
    assert result.margin == D("550")
    assert cents(result.ceiling.crew_share * 100) == D("96.46")
    assert cents(result.plan.crew_share * 100) == D("57.78")
    assert cents(result.ceiling.main_share * 100) == D("30.67")
    assert [flag.code for flag in result.flags] == ["MARGIN_SHARE_ABOVE_WARN"]
    assert "на потолке" in result.flags[0].message


def test_more_normalized_meters_per_physical_meter_raise_the_share() -> None:
    result = check(meters_factor=D("1.2"))
    assert abs(result.ceiling.crew_share - check().ceiling.crew_share * D("1.2")) < D("1e-20")


def test_headcount_multiplies_the_crew_cost() -> None:
    two_drillers = (CrewCost("P_DRILLER", "Машинист", D("2"), CURVE_X, FACTOR),)
    assert abs(check(crew=two_drillers).ceiling.crew_share - check().ceiling.crew_share) < D("1e-20")


def test_without_price_the_share_is_not_checked() -> None:
    result = check(price=None)
    assert result.status == "NOT_CHECKED"
    assert result.plan is None and result.ceiling is None and result.flags == ()


def test_non_positive_margin_gives_a_warning_and_no_share() -> None:
    result = check(price=D("250"))
    assert result.status == "NO_MARGIN"
    assert result.plan is None
    assert result.warnings


def test_position_without_a_scale_is_not_applicable() -> None:
    assert check(main_scale=None).status == "NOT_APPLICABLE"


def test_step_scale_has_no_ceiling_and_warns_by_the_plan_pace() -> None:
    step = Scale("STEP", tiers=(ScaleTier(D("100"), D("45")), ScaleTier(None, D("400"))))
    crew = (CrewCost("P_DRILLER", "Машинист", D("1"), step, FACTOR),)
    result = check(main_scale=step, crew=crew)
    assert result.ceiling is None
    assert cents(result.plan.crew_share * 100) == cents(D("400") * FACTOR / D("550") * 100)
    assert "при плановом темпе" in result.flags[0].message
```

- [ ] **Step 2: убедиться, что падает.**

Run: `../../../.venv/bin/python -m pytest tests/test_payroll_margin.py -q`
Expected: FAIL — `ImportError: cannot import name 'CrewCost' from 'cost.model.payroll'`.

- [ ] **Step 3: реализация.** Дописать в конец `cost/model/payroll.py`:

```python
# --- Доля в марже метра -----------------------------------------------------


@dataclass(frozen=True)
class CrewCost:
    """Сдельщик экипажа на тех же метрах: его шкала и затраты на рубль премии."""

    position_code: str
    name: str
    headcount: Decimal
    scale: Scale
    cost_factor: Decimal


@dataclass(frozen=True)
class SharePoint:
    pace: Decimal
    # Стоимость последнего метра по экипажу с начислениями / маржа метра.
    crew_share: Decimal
    # Цена последнего метра машиниста без начислений / маржа — «получает машинист».
    main_share: Decimal


@dataclass(frozen=True)
class MarginCheck:
    # CHECKED — посчитано; NOT_CHECKED — нет цены или переменных затрат метра;
    # NO_MARGIN — маржа метра не положительна; NOT_APPLICABLE — у должности нет шкалы.
    status: str
    threshold: Decimal
    price: Decimal | None = None
    variable: Decimal | None = None
    margin: Decimal | None = None
    plan: SharePoint | None = None
    ceiling: SharePoint | None = None
    crew: tuple[CrewCost, ...] = ()
    flags: tuple[PayrollFlag, ...] = ()
    warnings: tuple[str, ...] = ()
    lineage: Mapping[str, str] = field(default_factory=dict)


def margin_check(
    *,
    main_scale: Scale | None,
    crew: Sequence[CrewCost],
    pace: Decimal,
    meters_factor: Decimal,
    price: Decimal | None,
    variable: Decimal | None,
    threshold: Decimal,
) -> MarginCheck:
    """Доля стоимости последнего метра в марже метра (решения §2.2).

    share(m) = Σ чел × r(m) × затраты на рубль премии × приведённых на п.м. / маржа.
    Две точки — плановый темп и потолок; предупреждение — по потолку (у
    ступеней потолка нет — по плановому темпу).
    """

    if main_scale is None:
        return MarginCheck("NOT_APPLICABLE", threshold, price, variable, crew=tuple(crew))
    if price is None or variable is None:
        return MarginCheck("NOT_CHECKED", threshold, price, variable, crew=tuple(crew))
    margin = price - variable
    if margin <= 0:
        return MarginCheck(
            "NO_MARGIN",
            threshold,
            price,
            variable,
            margin,
            crew=tuple(crew),
            warnings=(f"Маржа метра {fn(price)} − {fn(variable)} = {fn(margin)} ₽ не положительна: доля в марже не считается.",),
        )

    def point(at: Decimal) -> SharePoint:
        crew_cost = sum((member.headcount * member.scale.rate_at(at) * member.cost_factor for member in crew), ZERO)
        return SharePoint(at, crew_cost * meters_factor / margin, main_scale.rate_at(at) * meters_factor / margin)

    plan = point(pace)
    ceiling = point(main_scale.ceiling_per_shift) if main_scale.is_curve else None
    checked = ceiling or plan
    flags: tuple[PayrollFlag, ...] = ()
    if checked.crew_share > threshold:
        where = "на потолке" if ceiling is not None else "при плановом темпе"
        flags = (
            PayrollFlag(
                "MARGIN_SHARE_ABOVE_WARN",
                f"Стоимость последнего метра по экипажу с начислениями — {percent(checked.crew_share)} маржи метра "
                f"{where}, порог {percent(threshold)}.",
            ),
        )
    lineage = {
        "margin": f"{fn(price)} − {fn(variable)} = {fn(margin)} ₽/м",
        "share": (
            "Σ чел × r(m) × затраты на рубль премии × "
            f"{fn(meters_factor)} прив. м/п.м. / {fn(margin)} ₽"
        ),
    }
    return MarginCheck("CHECKED", threshold, price, variable, margin, plan, ceiling, tuple(crew), flags, (), lineage)
```

- [ ] **Step 4: тест проходит.**

Run: `../../../.venv/bin/python -m pytest tests/test_payroll_margin.py tests/test_payroll_meters.py tests/test_payroll_curve.py tests/test_payroll_shifts.py tests/test_payroll_regression_2026_09.py -q`
Expected: PASS (81 passed).

- [ ] **Step 5: коммит.**

```bash
git add cost/model/payroll.py tests/test_payroll_margin.py
git commit -m "ФОТ (TASK-010 PR 2): доля стоимости последнего метра в марже, две точки

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Задача 6: входы методики из справочников

**Files:**
- Create: `cost/v2/payroll_params.py`
- Create: `cost/model/payroll_inputs.py`
- Modify: `tests/payroll_fixtures.py`
- Test: `tests/test_payroll_inputs.py`

**Interfaces:**
- Consumes: всё из `cost/model/payroll.py`; схемы `PositionPayload`, `LaborRatePayload`, `SitePayload`,
  `OrganizationRatesPayload`, `DrillingDifficultyPayload`, `DowntimeReasonPayload`, `RockPayload`,
  `PayrollParamsPayload`.
- Produces: `PayrollParamsChoice(item, params, note)`, `payroll_params_for_year(items, year) ->
  PayrollParamsChoice | None` (`cost/v2/payroll_params.py`); `PIECE_PAY_SYSTEMS`; `PayrollContext(calendar, site,
  rates, warnings, lineage)`; `payroll_context(snapshot, *, site_code, year)`; `position_pay(snapshot,
  position_code, calendar) -> (PositionPay, warnings)`; `payroll_inputs(snapshot, *, position_code, site_code,
  year) -> (PayrollInputs, PayrollContext, warnings)`; `difficulty_tables(snapshot)`, `downtime_reasons(snapshot)`,
  `rock_hardness(snapshot, rock_code)`.
- Fixture: `PAYROLL_SECTIONS`, `payroll_references(**overrides) -> ReferenceSnapshot`.

- [ ] **Step 1: фикстура.** В `tests/payroll_fixtures.py` заменить блок импортов на

```python
from decimal import Decimal
from typing import Any

from cost.model.payroll import (
    DifficultyTables,
    DowntimeReason,
    HardnessBand,
    PayrollCalendar,
    PayrollInputs,
    PayrollRates,
    PositionPay,
    Scale,
    SiteSchedule,
)
from cost.v2.models import ReferenceSnapshot
from cost.v2.payroll_defaults import (
    DOWNTIME_REASONS,
    DRILLER_SCALE,
    EXTRA_TARIFFS,
    HARDNESS_BANDS,
    PAYROLL_PARAMS,
)
from tests import model_fixtures as fx
```

и дописать в конец:

```python
_DRILLING_POSITION = {
    "category": "DIRECT",
    "operation_code": "PRODUCTION_DRILLING",
    "department": "DRILLING_BLASTING",
    "pay_system": "PIECE_PROGRESSIVE",
    "work_conditions_class": "3.2",
    "hazard_pct": "0.04",
    "extra_vacation_days": "7",
    "night_hours_per_shift": "8",
    "output_source": "OWN_OUTPUT",
    "difficulty": "NORMALIZED_METERS",
}

PAYROLL_SECTIONS: dict[str, tuple] = {
    "payroll_params": (fx.item("PAYROLL_PARAMS_2026", "Параметры ФОТ 2026", PAYROLL_PARAMS),),
    "organization_rates": (
        fx.item(
            "ORG_RATES",
            "Ставки организации",
            {
                "income_tax_rate": "0.13",
                "social_contribution_rate": "0.15",
                "injury_insurance_rate": "0.021",
                "per_diem_rub": "700",
                "shift_hours": "11",
                "extra_tariffs": [dict(row) for row in EXTRA_TARIFFS],
            },
        ),
    ),
    "positions": (
        fx.item("P_DRILLER", "Машинист буровой установки", _DRILLING_POSITION),
        fx.item("P_ASSISTANT", "Помощник машиниста", _DRILLING_POSITION),
        fx.item(
            "P_STOREKEEPER",
            "Кладовщик",
            {"category": "INDIRECT", "department": "WAREHOUSE", "pay_system": "TIME_BONUS"},
        ),
    ),
    "labor_rates": (
        fx.item("LR_DRILLER", "Машинист", {"position_code": "P_DRILLER", "fixed_monthly_rub": "27093", **DRILLER_SCALE}),
        fx.item("LR_ASSISTANT", "Помощник", {"position_code": "P_ASSISTANT", "fixed_monthly_rub": "27093", **DRILLER_SCALE}),
    ),
    "sites": (fx.item("SITE_LOM", "Ломовское месторождение", {"is_remote": True}),),
    "rocks": (
        fx.item("ROCK_F10", "Порода f10", {"hardness_f": "10"}),
        fx.item("ROCK_F17", "Порода f17", {"hardness_f": "17"}),
        fx.item("ROCK_NO_F", "Порода без крепости", {}),
    ),
    "drilling_difficulty": (
        fx.item(
            "DD_MAIN",
            "Сложность бурения",
            {
                "hardness": [dict(band) for band in HARDNESS_BANDS],
                "diameter": [{"diameter_mm": format(d, "f"), "k": format(k, "f")} for d, k in DIAMETERS.items()],
            },
        ),
    ),
    "downtime_reasons": tuple(
        fx.item(code, name, {"excusable": excusable, "planned_maintenance": maintenance})
        for code, name, excusable, maintenance in DOWNTIME_REASONS
    ),
}


def payroll_references(**overrides: Any) -> ReferenceSnapshot:
    """Снимок с разделами методики ФОТ; любой раздел можно подменить."""

    return fx.references(**{**PAYROLL_SECTIONS, **overrides})
```

- [ ] **Step 2: падающий тест.** Создать `tests/test_payroll_inputs.py`:

```python
"""Входы методики ФОТ из снимка справочников (TASK-010): год, оклад, объект, ставки."""
from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

import pytest

from cost.model.payroll import PayrollInputError, payroll_month
from cost.model.payroll_inputs import difficulty_tables, downtime_reasons, payroll_inputs, rock_hardness
from cost.v2.payroll_params import payroll_params_for_year
from cost.v2.payroll_defaults import PAYROLL_PARAMS
from tests import model_fixtures as fx
from tests.payroll_fixtures import cents, payroll_references

D = Decimal


def read(position: str = "P_DRILLER", site: str = "SITE_LOM", year: int = 2026, **sections):
    return payroll_inputs(payroll_references(**sections), position_code=position, site_code=site, year=year)


def test_file_regression_through_the_references() -> None:
    inputs, _, warnings = read()
    assert warnings == ()
    assert inputs.position.salary == D("27093")
    assert inputs.position.week_hours == 40
    assert inputs.position.scale.scale_type == "CURVE_POWER"
    assert inputs.site.shift_days_on == D("15") and inputs.site.maintenance_shifts == D("2")
    assert inputs.rates.extra_tariffs["3.2"] == D("0.04")
    result = payroll_month(inputs, D("170000"), work_days_month=D("21.5"))
    assert cents(result.company_cost) == D("358103.01")


def test_position_without_a_rate_gets_the_minimum_wage() -> None:
    inputs, _, warnings = read("P_STOREKEEPER")
    assert inputs.position.salary == D("27093")
    assert inputs.position.scale is None
    assert any("МРОТ 27" in warning for warning in warnings)


def test_zero_salary_in_the_rate_is_a_blank_too() -> None:
    rates = (fx.item("LR_DRILLER", "Машинист", {"position_code": "P_DRILLER", "fixed_monthly_rub": "0"}),)
    inputs, _, warnings = read(labor_rates=rates)
    assert inputs.position.salary == D("27093")
    assert any("МРОТ" in warning for warning in warnings)


def test_rate_with_a_drilling_condition_only_is_used_with_a_warning() -> None:
    rates = (
        fx.item(
            "LR_DRILLER",
            "Машинист",
            {"position_code": "P_DRILLER", "fixed_monthly_rub": "60000", "condition_code": "COND_1"},
        ),
    )
    inputs, _, warnings = read(labor_rates=rates)
    assert inputs.position.salary == D("60000")
    assert any("COND_1" in warning for warning in warnings)


def test_missing_year_falls_back_to_the_latest_past_year() -> None:
    inputs, _, warnings = read(year=2027)
    assert inputs.calendar.year == 2026
    assert "Параметров ФОТ за 2027 год нет — взяты за 2026 год." in warnings


def test_no_payroll_params_is_an_input_error() -> None:
    with pytest.raises(PayrollInputError, match="Параметры ФОТ"):
        read(payroll_params=())


@pytest.mark.parametrize(("position", "site"), [("NOPE", "SITE_LOM"), ("P_DRILLER", "NOPE")])
def test_unknown_position_or_site_is_an_input_error(position: str, site: str) -> None:
    with pytest.raises(PayrollInputError, match="NOPE"):
        read(position, site)


def test_site_from_before_the_payroll_fields_uses_the_company_schedule() -> None:
    inputs, _, _ = read(sites=(fx.item("SITE_LOM", "Ломовское", {}),))
    assert (inputs.site.shift_days_on, inputs.site.shift_days_off, inputs.site.travel_days) == (D("15"), D("15"), D("2"))
    assert inputs.site.regional_coefficient == D("0.15")


def test_missing_organization_rates_warn_and_use_defaults() -> None:
    inputs, _, warnings = read(organization_rates=())
    assert inputs.rates.sfr_rate == D("0.30")
    assert inputs.rates.shift_hours == D("11")
    assert any("Ставки и надбавки организации" in warning for warning in warnings)


def test_tables_reasons_and_rock_hardness_are_read_from_the_snapshot() -> None:
    snapshot = payroll_references()
    tables = difficulty_tables(snapshot)
    assert tables.diameter[D("250")] == D("1.64")
    assert tables.hardness[0].f_from is None and tables.hardness[-1].f_to is None
    reasons = downtime_reasons(snapshot)
    assert reasons["DT_PLANNED_MAINTENANCE"].planned_maintenance is True
    assert reasons["DT_LATE"].excusable is False
    assert rock_hardness(snapshot, "ROCK_F17") == D("17")
    assert rock_hardness(snapshot, "ROCK_NO_F") is None
    with pytest.raises(PayrollInputError):
        rock_hardness(snapshot, "NOPE")


def test_snapshot_without_difficulty_gives_empty_tables() -> None:
    tables = difficulty_tables(payroll_references(drilling_difficulty=()))
    assert tables.hardness == () and dict(tables.diameter) == {}


def _params(code: str, year: str, *, active: bool = True):
    item = fx.item(code, code, {**PAYROLL_PARAMS, "year": year})
    return item if active else replace(item, is_active=False)


def test_payroll_params_choice_prefers_exact_then_past_then_future() -> None:
    items = [_params("P2025", "2025"), _params("P2026", "2026"), _params("P2028", "2028")]
    assert payroll_params_for_year(items, 2026).item.code == "P2026"
    assert payroll_params_for_year(items, 2027).item.code == "P2026"
    assert payroll_params_for_year(items, 2027).note
    assert payroll_params_for_year(items[2:], 2026).item.code == "P2028"


def test_payroll_params_choice_skips_inactive_and_invalid_records() -> None:
    broken = fx.item("BROKEN", "Битая", {"year": "2026"})
    assert payroll_params_for_year([broken, _params("OFF", "2026", active=False)], 2026) is None


def test_broken_published_record_is_an_input_error_with_its_code() -> None:
    rates = (fx.item("LR_DRILLER", "Машинист", {"position_code": "P_DRILLER", "scale_type": "CURVE_POWER", "rate_norm": "45"}),)
    with pytest.raises(PayrollInputError, match="LR_DRILLER"):
        read(labor_rates=rates)
```

- [ ] **Step 3: убедиться, что падает.**

Run: `../../../.venv/bin/python -m pytest tests/test_payroll_inputs.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'cost.model.payroll_inputs'`.

- [ ] **Step 4: выбор года.** Создать `cost/v2/payroll_params.py`:

```python
"""Параметры ФОТ года (TASK-010): какая запись `payroll_params` действует.

Общая для методики ФОТ (`cost/model/payroll_inputs.py`) и сметы V1
(`cost/v2/legacy_adapter.py`): оба места должны брать один и тот же МРОТ.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from pydantic import ValidationError

from cost.v2.models import ReferenceItem
from cost.v2.schemas.payroll import PayrollParamsPayload

__all__ = ["PayrollParamsChoice", "payroll_params_for_year"]


@dataclass(frozen=True)
class PayrollParamsChoice:
    item: ReferenceItem
    params: PayrollParamsPayload
    # Пусто — взят запрошенный год; иначе пояснение, какой год взят вместо него.
    note: str = ""


def payroll_params_for_year(items: Iterable[ReferenceItem], year: int) -> PayrollParamsChoice | None:
    """Параметры запрошенного года, иначе ближайшего прошлого, иначе ближайшего будущего.

    Запись, которая не проходит схему, пропускается: публикация такую не
    пропустит, а снимок до TASK-010 раздела не содержит вовсе. None — ни одной
    годной записи.
    """

    valid: list[tuple[ReferenceItem, PayrollParamsPayload]] = []
    for item in items:
        if not item.is_active:
            continue
        try:
            valid.append((item, PayrollParamsPayload.model_validate(item.payload)))
        except ValidationError:
            continue
    if not valid:
        return None
    exact = next((pair for pair in valid if pair[1].year == year), None)
    if exact is not None:
        return PayrollParamsChoice(*exact)
    past = [pair for pair in valid if pair[1].year < year]
    item, params = (
        max(past, key=lambda pair: pair[1].year) if past else min(valid, key=lambda pair: pair[1].year)
    )
    return PayrollParamsChoice(item, params, f"Параметров ФОТ за {year} год нет — взяты за {params.year} год.")
```

- [ ] **Step 5: входы.** Создать `cost/model/payroll_inputs.py`:

```python
"""Входы методики ФОТ из снимка справочников (TASK-010).

Записи читаются через схемы разделов: умолчания полей те же, что у формы
справочника, поэтому объект, заведённый до TASK-010, считается по графику
компании 15/15. Нет должности, объекта или параметров года — ошибка входа
(методика без них не считается); нет ставки, ставок организации или таблиц
сложности — предупреждение и значение по умолчанию.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Mapping

from pydantic import BaseModel, ValidationError

from cost.model.payroll import (
    ZERO,
    DifficultyTables,
    DowntimeReason,
    HardnessBand,
    PayrollCalendar,
    PayrollInputError,
    PayrollInputs,
    PayrollRates,
    PositionPay,
    Scale,
    ScaleTier,
    SiteSchedule,
    fn,
    week_hours_for,
)
from cost.v2.models import ReferenceItem, ReferenceSnapshot
from cost.v2.payroll_params import payroll_params_for_year
from cost.v2.schemas.labor import LaborRatePayload, PositionPayload
from cost.v2.schemas.misc import RockPayload
from cost.v2.schemas.organization import OrganizationRatesPayload, SitePayload
from cost.v2.schemas.payroll import DowntimeReasonPayload, DrillingDifficultyPayload

PIECE_PAY_SYSTEMS = frozenset({"PIECE_PROGRESSIVE", "PIECE_BONUS"})


@dataclass(frozen=True)
class PayrollContext:
    """Общее для всех должностей одного расчёта: год, объект, ставки организации."""

    calendar: PayrollCalendar
    site: SiteSchedule
    rates: PayrollRates
    warnings: tuple[str, ...] = ()
    lineage: Mapping[str, str] = field(default_factory=dict)


def _first_error(exc: ValidationError) -> str:
    error = exc.errors()[0]
    where = ".".join(str(part) for part in error.get("loc", ()))
    return f"{where}: {error.get('msg', '')}" if where else str(error.get("msg", ""))


def _parse(model: type[BaseModel], item: ReferenceItem, what: str) -> BaseModel:
    try:
        return model.model_validate(item.payload)
    except ValidationError as exc:
        raise PayrollInputError(f"{what} {item.code} не проходит проверку справочника ({_first_error(exc)}).") from exc


def payroll_context(snapshot: ReferenceSnapshot, *, site_code: str, year: int) -> PayrollContext:
    warnings: list[str] = []
    lineage: dict[str, str] = {}

    choice = payroll_params_for_year(snapshot.sections.get("payroll_params", ()), year)
    if choice is None:
        raise PayrollInputError("Нет параметров ФОТ года (раздел «Параметры ФОТ»): методика не считается.")
    if choice.note:
        warnings.append(choice.note)
    params = choice.params
    calendar = PayrollCalendar(
        year=params.year,
        mrot=params.mrot,
        annual_hours_40=params.annual_hours_40,
        annual_hours_36=params.annual_hours_36,
        work_days_year=params.work_days_year,
        holidays_year=params.holidays_year,
        night_pct=params.night_pct,
        vacation_days_base=params.vacation_days_base,
        margin_share_warn=params.margin_share_warn,
        source=f"payroll_params.{choice.item.code}",
    )
    lineage["calendar"] = f"{calendar.source} ({calendar.year} год)"

    site_item = snapshot.item("sites", site_code)
    if site_item is None:
        raise PayrollInputError(f"Объект работ {site_code} не найден в справочнике.")
    site_payload = _parse(SitePayload, site_item, "Объект работ")
    site = SiteSchedule(
        code=site_item.code,
        name=site_item.name,
        shift_days_on=site_payload.shift_days_on,
        shift_days_off=site_payload.shift_days_off,
        travel_days=site_payload.travel_days,
        night_shift_share=site_payload.night_shift_share,
        maintenance_shifts=site_payload.maintenance_shifts,
        regional_coefficient=site_payload.regional_coefficient,
        northern_pct=site_payload.northern_pct,
        contract_k=site_payload.contract_k,
    )
    lineage["site"] = f"sites.{site.code}"

    rates_item = next(iter(snapshot.active_items("organization_rates")), None)
    if rates_item is None:
        warnings.append(
            "Не заполнен раздел «Ставки и надбавки организации»: взносы, НДФЛ, вахтовая надбавка "
            "и длительность смены взяты по умолчанию."
        )
        rates_payload = OrganizationRatesPayload()
        rates_source = "organization_rates (умолчания)"
    else:
        rates_payload = _parse(OrganizationRatesPayload, rates_item, "Ставки организации")
        rates_source = f"organization_rates.{rates_item.code}"
    if rates_payload.salary_basis == "NET":
        warnings.append("Оклады заданы на руки, а методика ФОТ считает оклад до НДФЛ: проверьте оклады должностей.")
    rates = PayrollRates(
        ndfl_rate=rates_payload.income_tax_rate,
        sfr_rate=rates_payload.social_contribution_rate,
        injury_rate=rates_payload.injury_insurance_rate,
        shift_allowance_per_day=rates_payload.per_diem_rub,
        shift_hours=rates_payload.shift_hours,
        extra_tariffs={row.work_conditions_class: row.rate for row in rates_payload.extra_tariffs},
        source=rates_source,
    )
    lineage["rates"] = rates_source
    return PayrollContext(calendar, site, rates, tuple(warnings), lineage)


def _labor_rate(snapshot: ReferenceSnapshot, position_code: str) -> tuple[ReferenceItem | None, str]:
    """Ставка без условия бурения; иначе первая ставка должности с предупреждением.

    Шкала задаётся только ставкой без условия (Т1): порода уже в приведённых метрах.
    """

    rows = [
        item
        for item in snapshot.active_items("labor_rates")
        if str(item.payload.get("position_code") or "") == position_code
    ]
    plain = next((item for item in rows if not item.payload.get("condition_code")), None)
    if plain is not None:
        return plain, ""
    if rows:
        return rows[0], (
            f"Ставка должности {position_code} взята по условию бурения "
            f"{rows[0].payload.get('condition_code')}: ставки без условия нет."
        )
    return None, ""


def _scale(rate: LaborRatePayload, source: str) -> Scale | None:
    if rate.scale_type is None:
        return None
    return Scale(
        scale_type=rate.scale_type,
        norm_per_shift=rate.norm_per_shift,
        rate_norm=rate.rate_norm,
        ceiling_per_shift=rate.ceiling_per_shift,
        rate_ceiling=rate.rate_ceiling,
        tiers=tuple(ScaleTier(tier.upto_per_shift, tier.rate) for tier in rate.tiers),
        source=source,
    )


def position_pay(
    snapshot: ReferenceSnapshot, position_code: str, calendar: PayrollCalendar
) -> tuple[PositionPay, tuple[str, ...]]:
    """Должность с окладом, неделей и шкалой; оклад не задан — МРОТ года (TASK-010 §2.2)."""

    item = snapshot.item("positions", position_code)
    if item is None:
        raise PayrollInputError(f"Должность {position_code} не найдена в справочнике.")
    position = _parse(PositionPayload, item, "Должность")
    warnings: list[str] = []
    rate_item, note = _labor_rate(snapshot, position_code)
    if note:
        warnings.append(note)
    rate = _parse(LaborRatePayload, rate_item, "Ставка") if rate_item is not None else None
    if rate is not None and rate.fixed_monthly_rub > 0:
        salary, salary_source = rate.fixed_monthly_rub, f"labor_rates.{rate_item.code}"
    else:
        # Пустой оклад ставки — тот же пробел, что отсутствие ставки: уровень I
        # методики — оклад не ниже МРОТ.
        salary, salary_source = calendar.mrot, f"МРОТ {calendar.year} ({calendar.source})"
        warnings.append(
            f"Оклад должности «{item.name}» не задан в «Ставках персонала»: взят МРОТ {fn(calendar.mrot)} ₽."
        )
    scale = _scale(rate, f"labor_rates.{rate_item.code}") if rate is not None else None
    return (
        PositionPay(
            code=item.code,
            name=item.name,
            salary=salary,
            salary_source=salary_source,
            week_hours=week_hours_for(position.work_conditions_class, position.week_hours_override),
            work_conditions_class=position.work_conditions_class,
            hazard_pct=position.hazard_pct,
            night_hours_per_shift=position.night_hours_per_shift,
            extra_vacation_days=position.extra_vacation_days,
            pay_system=position.pay_system,
            difficulty=position.difficulty,
            kpi_bonus_pct=rate.kpi_bonus_pct if rate is not None else ZERO,
            scale=scale,
        ),
        tuple(warnings),
    )


def payroll_inputs(
    snapshot: ReferenceSnapshot, *, position_code: str, site_code: str, year: int
) -> tuple[PayrollInputs, PayrollContext, tuple[str, ...]]:
    """Входы `payroll_month` для должности на объекте и предупреждения чтения."""

    context = payroll_context(snapshot, site_code=site_code, year=year)
    position, warnings = position_pay(snapshot, position_code, context.calendar)
    inputs = PayrollInputs(context.calendar, position, context.site, context.rates)
    return inputs, context, (*context.warnings, *warnings)


def difficulty_tables(snapshot: ReferenceSnapshot) -> DifficultyTables:
    """Таблицы «Сложности бурения»; записи нет — пустые таблицы (коэффициенты 1 с предупреждением)."""

    item = next(iter(snapshot.active_items("drilling_difficulty")), None)
    if item is None:
        return DifficultyTables(source="drilling_difficulty (нет записи)")
    payload = _parse(DrillingDifficultyPayload, item, "Сложность бурения")
    return DifficultyTables(
        hardness=tuple(HardnessBand(band.f_from, band.f_to, band.k) for band in payload.hardness),
        diameter={row.diameter_mm: row.k for row in payload.diameter},
        source=f"drilling_difficulty.{item.code}",
    )


def downtime_reasons(snapshot: ReferenceSnapshot) -> dict[str, DowntimeReason]:
    reasons: dict[str, DowntimeReason] = {}
    for item in snapshot.active_items("downtime_reasons"):
        payload = _parse(DowntimeReasonPayload, item, "Причина простоя")
        reasons[item.code] = DowntimeReason(item.code, item.name, payload.excusable, payload.planned_maintenance)
    return reasons


def rock_hardness(snapshot: ReferenceSnapshot, rock_code: str) -> Decimal | None:
    item = snapshot.item("rocks", rock_code)
    if item is None:
        raise PayrollInputError(f"Порода {rock_code} не найдена в справочнике.")
    return _parse(RockPayload, item, "Порода").hardness_f
```

- [ ] **Step 6: тест проходит.**

Run: `../../../.venv/bin/python -m pytest tests/test_payroll_inputs.py -q`
Expected: PASS (15 passed).

- [ ] **Step 7: коммит.**

```bash
git add cost/v2/payroll_params.py cost/model/payroll_inputs.py tests/payroll_fixtures.py tests/test_payroll_inputs.py
git commit -m "ФОТ (TASK-010 PR 2): входы методики из справочников, МРОТ без оклада

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Задача 7: превью одной должности

**Files:**
- Create: `cost/model/payroll_preview.py`
- Test: `tests/test_payroll_preview.py`

**Interfaces:**
- Consumes: задачи 1–6.
- Produces: `PreviewItem(meters, diameter_mm, rock_code=None, f=None)`; `PreviewRequest(position_code, site_code,
  year, shifts=None, downtime=(), items=(), meters_total=None, crew=(), price_rub_per_m=None,
  variable_rub_per_m=None)`; `PayrollPreview` с `.to_dict()` (ключи ответа API, числа — `float`);
  `payroll_preview(snapshot, request) -> PayrollPreview`.

- [ ] **Step 1: падающий тест.** Создать `tests/test_payroll_preview.py`:

```python
"""Превью ФОТ должности: план и факт, приведённые метры, доля в марже, график (TASK-010)."""
from __future__ import annotations

from decimal import Decimal

import pytest

from cost.model.payroll import DowntimeEntry, PayrollInputError
from cost.model.payroll_preview import PreviewItem, PreviewRequest, payroll_preview
from tests import model_fixtures as fx
from tests.payroll_fixtures import cents, payroll_references

D = Decimal
FIXED_ROWS = ("SALARY", "HAZARD", "NIGHT", "HOLIDAYS", "INTERSHIFT_REST", "SHIFT_ALLOWANCE")


def preview(snapshot=None, **fields):
    request = PreviewRequest(**{"position_code": "P_DRILLER", "site_code": "SITE_LOM", "year": 2026, **fields})
    return payroll_preview(snapshot or payroll_references(), request)


def test_plan_takes_the_site_rotation_minus_maintenance() -> None:
    result = preview(meters_total=D("2400"))
    assert result.shifts.effective == D("13")
    assert cents(result.premium.total) == D("156000.67")
    assert result.result.amount("PIECE_PREMIUM") == result.premium.total
    assert result.flags == ()
    assert result.margin.status == "NOT_CHECKED"
    assert result.margin.plan is None


def test_margin_share_in_two_points_with_the_warning_on_the_ceiling() -> None:
    result = preview(meters_total=D("2000"), price_rub_per_m=D("800"), variable_rub_per_m=D("250"))
    margin = result.margin
    assert margin.status == "CHECKED"
    assert [member.position_code for member in margin.crew] == ["P_DRILLER", "P_ASSISTANT"]
    assert cents(margin.ceiling.crew_share * 100) == D("96.46")
    assert cents(margin.plan.crew_share * 100) == D("57.78")
    assert cents(margin.ceiling.main_share * 100) == D("30.67")
    assert [flag.code for flag in result.flags] == ["MARGIN_SHARE_ABOVE_WARN"]


def test_explicit_crew_replaces_the_default() -> None:
    result = preview(
        meters_total=D("2000"), price_rub_per_m=D("800"), variable_rub_per_m=D("250"), crew=(("P_DRILLER", D("1")),)
    )
    assert cents(result.margin.ceiling.crew_share * 100) == D("48.23")
    assert result.flags == ()


def test_no_price_means_the_share_is_not_checked() -> None:
    result = preview(meters_total=D("2000"))
    assert result.margin.status == "NOT_CHECKED"
    assert result.margin.ceiling is None


def test_non_positive_margin_gives_no_share_and_a_warning() -> None:
    result = preview(meters_total=D("2000"), price_rub_per_m=D("200"), variable_rub_per_m=D("250"))
    assert result.margin.status == "NO_MARGIN"
    assert result.margin.plan is None
    assert any("Маржа метра" in warning for warning in result.warnings)


def test_meters_by_rock_and_diameter() -> None:
    items = (PreviewItem(D("800"), D("152"), rock_code="ROCK_F10"), PreviewItem(D("900"), D("250"), rock_code="ROCK_F17"))
    result = preview(items=items, price_rub_per_m=D("800"), variable_rub_per_m=D("250"))
    assert result.meters.total == D("2571.2")
    assert result.meters.factor == D("2571.2") / D("1700")
    plan_pace = D("2571.2") / D("13")
    assert result.premium.pace == plan_pace
    # Стоимость последнего погонного метра — приведённых метров на погонный больше.
    expected = 2 * result.margin.crew[0].cost_factor * D("168.66") * result.meters.factor / D("550")
    assert result.margin.ceiling.crew_share == expected


def test_contract_coefficient_of_the_site_enters_the_meters() -> None:
    sites = (fx.item("SITE_LOM", "Ломовское", {"contract_k": "1.1"}),)
    items = (PreviewItem(D("1000"), D("152"), f=D("10")),)
    result = preview(payroll_references(sites=sites), items=items)
    assert result.meters.total == D("1100")
    assert "contract_k" in result.lineage


def test_fact_with_downtime_keeps_the_fixed_part() -> None:
    plan = preview(meters_total=D(24000) / D(13))
    fact = preview(
        meters_total=D(24000) / D(13), shifts=D("13"), downtime=(DowntimeEntry("DT_RIG_REPAIR", D("33")),)
    )
    assert fact.shifts.effective == D("10")
    assert cents(fact.premium.total) == D("120000.52")
    for code in FIXED_ROWS:
        assert fact.result.amount(code) == plan.result.amount(code)


def test_downtime_for_the_whole_rotation_is_an_input_error() -> None:
    with pytest.raises(PayrollInputError):
        preview(meters_total=D("2000"), shifts=D("13"), downtime=(DowntimeEntry("DT_RIG_REPAIR", D("143")),))


def test_downtime_without_shifts_is_an_input_error() -> None:
    with pytest.raises(PayrollInputError):
        preview(meters_total=D("2000"), downtime=(DowntimeEntry("DT_RIG_REPAIR", D("11")),))


def test_flags_for_downtime_and_pace() -> None:
    result = preview(meters_total=D("3000"), shifts=D("13"), downtime=(DowntimeEntry("DT_WAIT_BLOCK", D("40")),))
    assert [flag.code for flag in result.flags] == ["DOWNTIME_OVER_25", "PACE_ABOVE_CEILING"]


def test_time_bonus_position_has_no_premium() -> None:
    result = preview(position_code="P_STOREKEEPER", meters_total=D("100"))
    assert result.premium is None
    assert result.margin.status == "NOT_APPLICABLE"
    assert result.result.amount("PIECE_PREMIUM") == 0
    assert result.series == ()
    assert any("Повременная" in warning for warning in result.warnings)
    assert any("МРОТ" in warning for warning in result.warnings)


def test_missing_output_pays_no_premium_with_a_warning() -> None:
    result = preview()
    assert result.premium.total == 0
    assert any("Выработка не задана" in warning for warning in result.warnings)


def test_series_and_dict_for_the_api() -> None:
    body = preview(meters_total=D("2000"), price_rub_per_m=D("800"), variable_rub_per_m=D("250")).to_dict()
    assert body["premium"]["gamma"] == pytest.approx(2.811088, abs=1e-6)
    assert body["series"][0] == {"pace": 0.0, "rate": 45.0, "per_shift": 0.0}
    assert body["margin"]["ceiling"]["crew_share"] == pytest.approx(0.9646, abs=1e-4)
    assert body["rows"][-1]["code"] == "COMPANY_COST"
    assert body["flags"][0]["code"] == "MARGIN_SHARE_ABOVE_WARN"
    assert "premium_cost_factor" in body["lineage"]


def test_rock_without_hardness_counts_with_one_and_a_warning() -> None:
    result = preview(items=(PreviewItem(D("1000"), D("152"), rock_code="ROCK_NO_F"),))
    assert result.meters.total == D("1000")
    assert any("не задана крепость" in warning for warning in result.warnings)


def test_piece_bonus_position_counts_plain_output() -> None:
    snapshot = payroll_references(
        positions=(
            *payroll_references().sections["positions"],
            fx.item("P_DRIVER", "Водитель", {"category": "INDIRECT", "pay_system": "PIECE_BONUS", "output_unit": "KM"}),
        ),
        labor_rates=(
            *payroll_references().sections["labor_rates"],
            fx.item(
                "LR_DRIVER",
                "Водитель",
                {
                    "position_code": "P_DRIVER",
                    "fixed_monthly_rub": "40000",
                    "scale_type": "STEP",
                    "tiers": [{"upto_per_shift": "200", "rate": "10"}, {"upto_per_shift": None, "rate": "15"}],
                },
            ),
        ),
    )
    items = (PreviewItem(D("2000"), D("152")), PreviewItem(D("1250"), D("110")))
    result = preview(snapshot, position_code="P_DRIVER", items=items)
    assert result.meters.total == D("3250")
    assert result.meters.rows == ()
    assert result.premium.pace == D("250")
    assert result.premium.total == D("13") * (D("200") * 10 + D("50") * 15)
    assert [member.position_code for member in result.margin.crew] == ["P_DRIVER"]


def test_unknown_crew_member_is_an_input_error() -> None:
    with pytest.raises(PayrollInputError, match="NOPE"):
        preview(meters_total=D("2000"), crew=(("NOPE", D("1")),))
```

- [ ] **Step 2: убедиться, что падает.**

Run: `../../../.venv/bin/python -m pytest tests/test_payroll_preview.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'cost.model.payroll_preview'`.

- [ ] **Step 3: реализация.** Создать `cost/model/payroll_preview.py`:

```python
"""Превью ФОТ должности на объекте (TASK-010): строки, сдельная часть, доля в марже, график.

Собирает функции `cost/model/payroll.py` в один расчёт для эндпоинта
`POST /economics/payroll/preview`. План (смены не заданы) — вахта объекта
минус плановое ТОиР; факт — заданные смены минус простои не по вине машиниста.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Mapping

from cost.model.payroll import (
    ZERO,
    CrewCost,
    DowntimeEntry,
    EffectiveShifts,
    MarginCheck,
    MeterItem,
    NormalizedMeters,
    PayrollFlag,
    PayrollInputError,
    PayrollInputs,
    PayrollResult,
    PiecePremium,
    PositionPay,
    ScalePoint,
    SharePoint,
    SiteSchedule,
    effective_shifts,
    fn,
    margin_check,
    normalized_meters,
    pace_flags,
    payroll_month,
    piece_premium,
    plan_effective_shifts,
    premium_cost_factor,
    scale_series,
)
from cost.model.payroll_inputs import (
    PIECE_PAY_SYSTEMS,
    PayrollContext,
    difficulty_tables,
    downtime_reasons,
    payroll_inputs,
    position_pay,
    rock_hardness,
)
from cost.v2.models import ReferenceSnapshot


@dataclass(frozen=True)
class PreviewItem:
    meters: Decimal
    diameter_mm: Decimal
    rock_code: str | None = None
    f: Decimal | None = None


@dataclass(frozen=True)
class PreviewRequest:
    position_code: str
    site_code: str
    year: int
    # Пусто — план: вахта объекта минус плановое ТОиР.
    shifts: Decimal | None = None
    downtime: tuple[DowntimeEntry, ...] = ()
    items: tuple[PreviewItem, ...] = ()
    # Приведённые метры (выработка) одной суммой, без разбивки по породам.
    meters_total: Decimal | None = None
    # Сдельщики экипажа на тех же метрах: (должность, человек в смене).
    crew: tuple[tuple[str, Decimal], ...] = ()
    price_rub_per_m: Decimal | None = None
    variable_rub_per_m: Decimal | None = None


@dataclass(frozen=True)
class PayrollPreview:
    position: PositionPay
    site: SiteSchedule
    year: int
    shifts: EffectiveShifts
    result: PayrollResult
    premium_cost_factor: Decimal
    premium_cost_factor_formula: str
    margin: MarginCheck
    meters: NormalizedMeters | None = None
    premium: PiecePremium | None = None
    series: tuple[ScalePoint, ...] = ()
    flags: tuple[PayrollFlag, ...] = ()
    warnings: tuple[str, ...] = ()
    lineage: Mapping[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        scale = self.position.scale
        return {
            "position_code": self.position.code,
            "position_name": self.position.name,
            "site_code": self.site.code,
            "year": self.year,
            "rows": [
                {"code": row.code, "name": row.name, "kind": row.kind, "amount_rub": float(row.amount), "formula": row.formula}
                for row in self.result.rows
            ],
            "gross_rub": float(self.result.gross),
            "company_cost_rub": float(self.result.company_cost),
            "meters": _meters_dict(self.meters),
            "shifts": {
                "shifts": float(self.shifts.shifts),
                "effective": float(self.shifts.effective),
                "excusable_hours": float(self.shifts.excusable_hours),
                "maintenance_hours": float(self.shifts.maintenance_hours),
                "written_off_share": _num(self.shifts.written_off_share),
            },
            "premium": _premium_dict(self.premium, scale),
            "premium_cost_factor": float(self.premium_cost_factor),
            "premium_cost_factor_formula": self.premium_cost_factor_formula,
            "margin": _margin_dict(self.margin),
            "series": [
                {"pace": float(point.pace), "rate": float(point.rate), "per_shift": float(point.per_shift)}
                for point in self.series
            ],
            "flags": [{"code": flag.code, "message": flag.message} for flag in self.flags],
            "warnings": list(self.warnings),
            "lineage": dict(self.lineage),
        }


def _num(value: Decimal | None) -> float | None:
    return None if value is None else float(value)


def _meters_dict(meters: NormalizedMeters | None) -> dict[str, Any] | None:
    if meters is None:
        return None
    return {
        "total": float(meters.total),
        "physical": float(meters.physical),
        "contract_k": float(meters.contract_k),
        "factor": float(meters.factor),
        "rows": [
            {
                "label": row.label,
                "meters": float(row.meters),
                "f": _num(row.f),
                "k_f": float(row.k_f),
                "diameter_mm": float(row.diameter_mm),
                "k_d": float(row.k_d),
                "normalized": float(row.normalized),
            }
            for row in meters.rows
        ],
    }


def _premium_dict(premium: PiecePremium | None, scale: Any) -> dict[str, Any] | None:
    if premium is None or scale is None:
        return None
    return {
        "scale_type": scale.scale_type,
        "gamma": _num(scale.gamma),
        "norm_per_shift": _num(scale.norm_per_shift),
        "rate_norm": _num(scale.rate_norm),
        "ceiling_per_shift": _num(scale.ceiling_per_shift),
        "rate_ceiling": _num(scale.rate_ceiling),
        "output": float(premium.output),
        "effective_shifts": float(premium.effective_shifts),
        "pace": float(premium.pace),
        "per_shift": float(premium.per_shift),
        "last_rate": float(premium.last_rate),
        "mean_rate": _num(premium.mean_rate),
        "total": float(premium.total),
        "tiers": [
            {
                "lower": float(tier.lower),
                "upper": _num(tier.upper),
                "rate": float(tier.rate),
                "units": float(tier.units),
                "amount": float(tier.amount),
            }
            for tier in premium.tiers
        ],
    }


def _point_dict(point: SharePoint | None) -> dict[str, Any] | None:
    if point is None:
        return None
    return {"pace": float(point.pace), "crew_share": float(point.crew_share), "main_share": float(point.main_share)}


def _margin_dict(margin: MarginCheck) -> dict[str, Any]:
    return {
        "status": margin.status,
        "threshold": float(margin.threshold),
        "price_rub_per_m": _num(margin.price),
        "variable_rub_per_m": _num(margin.variable),
        "margin_rub_per_m": _num(margin.margin),
        "plan": _point_dict(margin.plan),
        "ceiling": _point_dict(margin.ceiling),
        "crew": [
            {
                "position_code": member.position_code,
                "name": member.name,
                "headcount": float(member.headcount),
                "cost_factor": float(member.cost_factor),
            }
            for member in margin.crew
        ],
    }


def _shifts(snapshot: ReferenceSnapshot, request: PreviewRequest, context: PayrollContext) -> EffectiveShifts:
    if request.shifts is None:
        if request.downtime:
            raise PayrollInputError("Простои задаются вместе с фактическими сменами вахты.")
        return plan_effective_shifts(context.site.shift_days_on, context.site.maintenance_shifts)
    return effective_shifts(request.shifts, context.rates.shift_hours, request.downtime, downtime_reasons(snapshot))


def _output(
    snapshot: ReferenceSnapshot, request: PreviewRequest, position: PositionPay, site: SiteSchedule
) -> tuple[NormalizedMeters, list[str]]:
    """Выработка для шкалы: приведённые метры по породам, сумма метров или сумма запроса."""

    if request.meters_total is not None:
        return (
            NormalizedMeters(
                total=request.meters_total,
                physical=request.meters_total,
                lineage={"normalized_meters": f"задано суммой: {fn(request.meters_total)}"},
            ),
            [],
        )
    if not request.items:
        return NormalizedMeters(ZERO, ZERO), ["Выработка не задана: сдельная премия 0."]
    if position.difficulty != "NORMALIZED_METERS":
        total = sum((item.meters for item in request.items), ZERO)
        return (
            NormalizedMeters(total, total, lineage={"normalized_meters": f"Σ выработки = {fn(total)} (без приведения)"}),
            [],
        )
    items = []
    for index, item in enumerate(request.items):
        f = rock_hardness(snapshot, item.rock_code) if item.rock_code else item.f
        label = f"{item.rock_code or 'порода'}, Ø {fn(item.diameter_mm)} мм"
        items.append(MeterItem(item.meters, item.diameter_mm, f, label))
    meters = normalized_meters(items, difficulty_tables(snapshot), site.contract_k)
    return meters, list(meters.warnings)


def _crew(
    snapshot: ReferenceSnapshot, request: PreviewRequest, main: PositionPay, inputs: PayrollInputs
) -> tuple[list[CrewCost], list[str]]:
    """Сдельщики экипажа: из запроса, иначе все сдельщики с приведёнными метрами и шкалой.

    У машиниста по умолчанию экипаж — машинист и помощник, по одному в смене:
    оба получают премию по шкале на те же приведённые метры.
    """

    warnings: list[str] = []
    if request.crew:
        members = list(request.crew)
    elif main.difficulty == "NORMALIZED_METERS":
        members = [
            (item.code, Decimal("1"))
            for item in snapshot.active_items("positions")
            if item.payload.get("difficulty") == "NORMALIZED_METERS"
            and item.payload.get("pay_system") in PIECE_PAY_SYSTEMS
        ]
    else:
        members = [(main.code, Decimal("1"))]
    crew: list[CrewCost] = []
    for code, headcount in members:
        if code == main.code:
            position = main
        else:
            # Предупреждения чтения соседа по экипажу (оклад по МРОТ) здесь
            # лишние: долю в марже считает шкала, а не оклад.
            position, _ = position_pay(snapshot, code, inputs.calendar)
        if position.scale is None:
            warnings.append(f"Должность «{position.name}» в экипаже без шкалы сдельной премии: в долю в марже не входит.")
            continue
        factor, _ = premium_cost_factor(PayrollInputs(inputs.calendar, position, inputs.site, inputs.rates))
        crew.append(CrewCost(position.code, position.name, headcount, position.scale, factor))
    return crew, warnings


def payroll_preview(snapshot: ReferenceSnapshot, request: PreviewRequest) -> PayrollPreview:
    inputs, context, read_warnings = payroll_inputs(
        snapshot, position_code=request.position_code, site_code=request.site_code, year=request.year
    )
    position = inputs.position
    warnings: list[str] = list(read_warnings)
    lineage: dict[str, str] = dict(context.lineage)
    shifts = _shifts(snapshot, request, context)
    lineage.update(shifts.lineage)
    flags: list[PayrollFlag] = list(shifts.flags)

    meters: NormalizedMeters | None = None
    premium: PiecePremium | None = None
    scale = position.scale
    if position.pay_system not in PIECE_PAY_SYSTEMS:
        if request.items or request.meters_total is not None:
            warnings.append("Повременная оплата: выработка в премию не входит.")
        scale = None
    elif scale is None:
        warnings.append(f"У ставки должности «{position.name}» нет шкалы сдельной премии: премия 0.")
    else:
        meters, meter_warnings = _output(snapshot, request, position, context.site)
        warnings.extend(meter_warnings)
        lineage.update(meters.lineage)
        if meters.contract_k != 1:
            lineage["contract_k"] = f"sites.{context.site.code}.contract_k = {fn(meters.contract_k)}"
        premium = piece_premium(meters.total, scale, shifts.effective)
        lineage.update(premium.lineage)
        flags.extend(pace_flags(scale, premium.pace))

    result = payroll_month(inputs, premium.total if premium is not None else ZERO)
    warnings.extend(result.warnings)
    factor, factor_formula = premium_cost_factor(inputs)
    lineage["premium_cost_factor"] = factor_formula

    if premium is not None:
        crew, crew_warnings = _crew(snapshot, request, position, inputs)
        warnings.extend(crew_warnings)
        margin = margin_check(
            main_scale=scale,
            crew=crew,
            pace=premium.pace,
            meters_factor=meters.factor if meters is not None else Decimal("1"),
            price=request.price_rub_per_m,
            variable=request.variable_rub_per_m,
            threshold=inputs.calendar.margin_share_warn,
        )
    else:
        margin = MarginCheck("NOT_APPLICABLE", inputs.calendar.margin_share_warn)
    warnings.extend(margin.warnings)
    flags.extend(margin.flags)
    lineage.update(margin.lineage)

    unique: list[str] = []
    for warning in warnings:
        if warning not in unique:
            unique.append(warning)
    return PayrollPreview(
        position=position,
        site=context.site,
        year=inputs.calendar.year,
        shifts=shifts,
        result=result,
        premium_cost_factor=factor,
        premium_cost_factor_formula=factor_formula,
        margin=margin,
        meters=meters,
        premium=premium,
        series=scale_series(scale, premium.pace) if scale is not None and premium is not None else (),
        flags=tuple(flags),
        warnings=tuple(unique),
        lineage=lineage,
    )
```

- [ ] **Step 4: тест проходит.**

Run: `../../../.venv/bin/python -m pytest tests/test_payroll_preview.py -q`
Expected: PASS (17 passed).

- [ ] **Step 5: коммит.**

```bash
git add cost/model/payroll_preview.py tests/test_payroll_preview.py
git commit -m "ФОТ (TASK-010 PR 2): превью должности — план и факт, доля в марже, график

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Задача 8: эндпоинт `POST /economics/payroll/preview`

**Files:**
- Create: `api/schemas/payroll.py`
- Modify: `api/routers/block_economics.py` (импорты; эндпоинт — перед `@router.post("/runs", …)`)
- Test: `tests/test_api_payroll_preview.py`

**Interfaces:**
- Consumes: `payroll_preview`, `PreviewRequest`, `PreviewItem`, `DowntimeEntry`, `PayrollInputError`.
- Produces: `PayrollPreviewRequest`, `PayrollPreviewResponse` (`api/schemas/payroll.py`); маршрут
  `POST /api/v1/economics/payroll/preview` (доступ `require_internal_access`, как у расчёта блока).

- [ ] **Step 1: падающий тест.** Создать `tests/test_api_payroll_preview.py`:

```python
"""`POST /api/v1/economics/payroll/preview` на in-memory репозитории (TASK-010)."""
from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routers import block_economics
from api.services.economics_service import get_economics_repository
from cost.v2.repository import InMemoryEconomicsRepository
from tests.payroll_fixtures import payroll_references

URL = "/api/v1/economics/payroll/preview"


@pytest.fixture
def api(monkeypatch) -> TestClient:
    monkeypatch.setenv("BLASTEX_API_KEY", "test-api-key")
    monkeypatch.setenv("BLASTEX_SESSION_SECRET", "test-session-secret")
    repository = InMemoryEconomicsRepository()
    references = payroll_references()
    repository.publish_references(
        "default",
        "tester",
        repository.list_reference_revisions("default")[0].id,
        {section: list(items) for section, items in references.sections.items()},
        "фикстура ФОТ",
    )
    app = FastAPI()
    app.include_router(block_economics.router, prefix="/api/v1")
    app.dependency_overrides[get_economics_repository] = lambda: repository
    return TestClient(app, headers={"X-API-Key": "test-api-key"})


def body(**fields) -> dict:
    return {"position_code": "P_DRILLER", "site_code": "SITE_LOM", "month": "2026-09", **fields}


def test_plan_preview_without_price_returns_200_and_no_share(api: TestClient) -> None:
    response = api.post(URL, json=body(meters_total="2400"))
    assert response.status_code == 200
    data = response.json()
    assert data["reference_revision_id"]
    assert data["premium"]["total"] == pytest.approx(156000.67, abs=0.01)
    assert data["shifts"]["effective"] == 13
    assert data["margin"]["status"] == "NOT_CHECKED"
    assert data["margin"]["ceiling"] is None
    assert data["rows"][-1]["code"] == "COMPANY_COST"
    assert data["series"]


def test_share_in_two_points_and_the_warning_flag(api: TestClient) -> None:
    response = api.post(URL, json=body(meters_total="2000", price_rub_per_m="800", variable_rub_per_m="250"))
    assert response.status_code == 200
    margin = response.json()["margin"]
    assert margin["ceiling"]["crew_share"] == pytest.approx(0.9646, abs=1e-4)
    assert margin["plan"]["crew_share"] == pytest.approx(0.5778, abs=1e-4)
    assert margin["ceiling"]["main_share"] == pytest.approx(0.3067, abs=1e-4)
    assert [flag["code"] for flag in response.json()["flags"]] == ["MARGIN_SHARE_ABOVE_WARN"]


def test_meters_by_rock_and_downtime_flags(api: TestClient) -> None:
    response = api.post(
        URL,
        json=body(
            items=[
                {"meters": "800", "diameter_mm": "152", "rock_code": "ROCK_F10"},
                {"meters": "900", "diameter_mm": "250", "rock_code": "ROCK_F17"},
            ],
            shifts="13",
            downtime=[{"code": "DT_WAIT_BLOCK", "hours": "40"}],
        ),
    )
    assert response.status_code == 200
    data = response.json()
    assert data["meters"]["total"] == pytest.approx(2571.2)
    assert data["shifts"]["written_off_share"] == pytest.approx(40 / 143)
    assert "DOWNTIME_OVER_25" in [flag["code"] for flag in data["flags"]]


@pytest.mark.parametrize("hours", ["143", "150"])
def test_downtime_for_the_whole_rotation_is_422(api: TestClient, hours: str) -> None:
    response = api.post(
        URL, json=body(meters_total="2000", shifts="13", downtime=[{"code": "DT_RIG_REPAIR", "hours": hours}])
    )
    assert response.status_code == 422
    assert "вахт" in response.json()["detail"]


def test_unknown_position_is_422(api: TestClient) -> None:
    response = api.post(URL, json=body(position_code="NOPE"))
    assert response.status_code == 422
    assert "NOPE" in response.json()["detail"]


@pytest.mark.parametrize(
    "fields",
    [
        {"meters_total": "100", "items": [{"meters": "100", "diameter_mm": "152"}]},
        {"downtime": [{"code": "DT_RIG_REPAIR", "hours": "5"}]},
        {"month": "2026-13"},
        {"items": [{"meters": "100", "diameter_mm": "152", "rock_code": "ROCK_F10", "f": "10"}]},
    ],
)
def test_inconsistent_request_is_rejected_by_the_schema(api: TestClient, fields: dict) -> None:
    assert api.post(URL, json=body(**fields)).status_code == 422
```

- [ ] **Step 2: убедиться, что падает.**

Run: `../../../.venv/bin/python -m pytest tests/test_api_payroll_preview.py -q`
Expected: FAIL — 404 на `/api/v1/economics/payroll/preview`.

- [ ] **Step 3: схемы.** Создать `api/schemas/payroll.py`:

```python
"""Схемы превью ФОТ должности (TASK-010): `POST /economics/payroll/preview`."""
from __future__ import annotations

from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, model_validator


class PayrollMeterItemSchema(BaseModel):
    """Метры одной породы и диаметра: крепость — из породы справочника или числом."""

    meters: Decimal = Field(..., ge=0)
    diameter_mm: Decimal = Field(..., gt=0)
    rock_code: str | None = Field(None, min_length=1, max_length=80)
    f: Decimal | None = Field(None, gt=0)

    @model_validator(mode="after")
    def _one_hardness_source(self) -> "PayrollMeterItemSchema":
        if self.rock_code is not None and self.f is not None:
            raise ValueError("Крепость задаётся породой или числом f, не обоими сразу.")
        return self


class PayrollDowntimeSchema(BaseModel):
    code: str = Field(..., min_length=1, max_length=80)
    hours: Decimal = Field(..., ge=0)


class PayrollCrewMemberSchema(BaseModel):
    position_code: str = Field(..., min_length=1, max_length=80)
    headcount: Decimal = Field(Decimal("1"), gt=0)


class PayrollPreviewRequest(BaseModel):
    position_code: str = Field(..., min_length=1, max_length=80)
    site_code: str = Field(..., min_length=1, max_length=80)
    # Месяц расчёта «ГГГГ-ММ»: по его году выбираются параметры ФОТ.
    month: str = Field(..., pattern=r"^\d{4}-(0[1-9]|1[0-2])$")
    # Пусто — актуальная опубликованная ревизия справочников.
    reference_revision_id: str = ""
    # Пусто — план: вахта объекта минус плановое ТОиР.
    shifts: Decimal | None = Field(None, gt=0)
    downtime: list[PayrollDowntimeSchema] = Field(default_factory=list)
    items: list[PayrollMeterItemSchema] = Field(default_factory=list)
    # Приведённые метры (выработка) одной суммой.
    meters_total: Decimal | None = Field(None, ge=0)
    crew: list[PayrollCrewMemberSchema] = Field(default_factory=list)
    price_rub_per_m: Decimal | None = Field(None, ge=0)
    variable_rub_per_m: Decimal | None = Field(None, ge=0)

    @model_validator(mode="after")
    def _consistent(self) -> "PayrollPreviewRequest":
        if self.items and self.meters_total is not None:
            raise ValueError("Метры задаются списком по породам или одной суммой, не обоими сразу.")
        if self.downtime and self.shifts is None:
            raise ValueError("Простои задаются вместе с фактическими сменами вахты.")
        return self


class PayrollRowSchema(BaseModel):
    code: str
    name: str
    kind: Literal["ACCRUAL", "SUBTOTAL", "INFO", "COST", "TOTAL"]
    amount_rub: float
    formula: str


class PayrollMeterRowSchema(BaseModel):
    label: str
    meters: float
    f: float | None
    k_f: float
    diameter_mm: float
    k_d: float
    normalized: float


class PayrollMetersSchema(BaseModel):
    total: float
    physical: float
    contract_k: float
    factor: float
    rows: list[PayrollMeterRowSchema]


class PayrollShiftsSchema(BaseModel):
    shifts: float
    effective: float
    excusable_hours: float
    maintenance_hours: float
    written_off_share: float | None


class PayrollTierSchema(BaseModel):
    lower: float
    upper: float | None
    rate: float
    units: float
    amount: float


class PayrollPremiumSchema(BaseModel):
    scale_type: str
    gamma: float | None
    norm_per_shift: float | None
    rate_norm: float | None
    ceiling_per_shift: float | None
    rate_ceiling: float | None
    output: float
    effective_shifts: float
    pace: float
    per_shift: float
    last_rate: float
    mean_rate: float | None
    total: float
    tiers: list[PayrollTierSchema]


class PayrollSharePointSchema(BaseModel):
    pace: float
    crew_share: float
    main_share: float


class PayrollCrewCostSchema(BaseModel):
    position_code: str
    name: str
    headcount: float
    cost_factor: float


class PayrollMarginSchema(BaseModel):
    status: Literal["CHECKED", "NOT_CHECKED", "NO_MARGIN", "NOT_APPLICABLE"]
    threshold: float
    price_rub_per_m: float | None
    variable_rub_per_m: float | None
    margin_rub_per_m: float | None
    plan: PayrollSharePointSchema | None
    ceiling: PayrollSharePointSchema | None
    crew: list[PayrollCrewCostSchema]


class PayrollSeriesPointSchema(BaseModel):
    pace: float
    rate: float
    per_shift: float


class PayrollFlagSchema(BaseModel):
    code: Literal["DOWNTIME_OVER_25", "PACE_ABOVE_CEILING", "MARGIN_SHARE_ABOVE_WARN"]
    message: str


class PayrollPreviewResponse(BaseModel):
    reference_revision_id: str
    position_code: str
    position_name: str
    site_code: str
    year: int
    rows: list[PayrollRowSchema]
    gross_rub: float
    company_cost_rub: float
    meters: PayrollMetersSchema | None
    shifts: PayrollShiftsSchema
    premium: PayrollPremiumSchema | None
    premium_cost_factor: float
    premium_cost_factor_formula: str
    margin: PayrollMarginSchema
    series: list[PayrollSeriesPointSchema]
    flags: list[PayrollFlagSchema]
    warnings: list[str]
    lineage: dict[str, str]
```

- [ ] **Step 4: эндпоинт.** В `api/routers/block_economics.py` после импорта `from api.schemas.block_economics
  import (…)` добавить

```python
from api.schemas.payroll import PayrollPreviewRequest, PayrollPreviewResponse
```

после `from cost.model.materials import ROLES, quantity_in_price_units` добавить

```python
from cost.model.payroll import DowntimeEntry, PayrollInputError
from cost.model.payroll_preview import PreviewItem, PreviewRequest, payroll_preview
```

и перед `@router.post("/runs", response_model=EconomicsRunSchema, status_code=status.HTTP_201_CREATED)` вставить:

```python
@router.post("/payroll/preview", response_model=PayrollPreviewResponse)
def payroll_preview_endpoint(
    payload: PayrollPreviewRequest,
    session: dict[str, object] = Depends(require_internal_access),
    repository: EconomicsRepository = Depends(get_economics_repository),
) -> PayrollPreviewResponse:
    """ФОТ должности на объекте за месяц по методике TASK-010: строки, премия, доля в марже.

    Вход, на котором методика не считается (простоев больше часов вахты,
    нет параметров года, неизвестная должность), — 422 с объяснением, а не
    деление на ноль. Без цены метра доля в марже не проверяется, ответ 200.
    """

    organization_id, _ = _identity(session)
    try:
        references = repository.get_reference_snapshot(organization_id, payload.reference_revision_id or None)
    except Exception as exc:
        raise repository_error(exc) from exc
    try:
        preview = payroll_preview(references, _payroll_request(payload))
    except PayrollInputError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return PayrollPreviewResponse.model_validate(
        {**preview.to_dict(), "reference_revision_id": references.revision_id}
    )


def _payroll_request(payload: PayrollPreviewRequest) -> PreviewRequest:
    return PreviewRequest(
        position_code=payload.position_code,
        site_code=payload.site_code,
        year=int(payload.month[:4]),
        shifts=payload.shifts,
        downtime=tuple(DowntimeEntry(entry.code, entry.hours) for entry in payload.downtime),
        items=tuple(PreviewItem(item.meters, item.diameter_mm, item.rock_code, item.f) for item in payload.items),
        meters_total=payload.meters_total,
        crew=tuple((member.position_code, member.headcount) for member in payload.crew),
        price_rub_per_m=payload.price_rub_per_m,
        variable_rub_per_m=payload.variable_rub_per_m,
    )
```

`status_code=422` числом, как в `api/routers/cad.py`: константа `HTTP_422_UNPROCESSABLE_ENTITY` в установленном
Starlette устарела и даёт предупреждение.

- [ ] **Step 5: тест проходит.**

Run: `../../../.venv/bin/python -m pytest tests/test_api_payroll_preview.py tests/test_api_block_economics.py -q`
Expected: PASS.

- [ ] **Step 6: коммит.**

```bash
git add api/schemas/payroll.py api/routers/block_economics.py tests/test_api_payroll_preview.py
git commit -m "ФОТ (TASK-010 PR 2): POST /economics/payroll/preview

Ошибка входа (простоев больше часов вахты, нет параметров года,
неизвестная должность) — 422 с объяснением; без цены метра доля
в марже не проверяется, ответ 200.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Задача 9: смета V1 — МРОТ для должности без ставки (по ответу на вопрос 2)

Вариант А. При варианте Б — оставить `mrot = 0.0` и вторую ветку предупреждения; при варианте В задачу
пропустить.

**Files:**
- Modify: `cost/v2/legacy_adapter.py`
- Test: `tests/test_legacy_adapter.py`

**Interfaces:**
- Consumes: `payroll_params_for_year`, `PayrollParamsChoice` (задача 6).

- [ ] **Step 1: падающий тест.** Дописать в конец `tests/test_legacy_adapter.py`:

```python
class TestPositionsWithoutRate:
    """Должность без ставки — оклад по МРОТ года одной строкой (TASK-010 PR 2)."""

    PARAMS = _item(
        "PAYROLL_PARAMS_2026",
        "Параметры ФОТ 2026",
        {"year": "2026", "mrot": "27093", "annual_hours_40": "1972", "annual_hours_36": "1774.4",
         "work_days_year": "247", "holidays_year": "14"},
    )

    def _legacy(self, **sections):
        return legacy_references_from_snapshot(
            _snapshot(
                positions=[
                    _item("POSITION_MASTER", "Мастер", {}),
                    _item("POSITION_LABOR_STOREKEEPER", "Кладовщик", {}),
                    _item("POSITION_LABOR_DRIVER", "Водитель", {}),
                ],
                labor_rates=[_item("RATE_MASTER", "Ставка", {"position_code": "POSITION_MASTER", "fixed_monthly_rub": "80000"})],
                **sections,
            )
        )

    def test_minimum_wage_and_one_warning(self):
        legacy = self._legacy(payroll_params=[self.PARAMS])
        positions = {item.id: item for item in legacy.labor_catalog}
        assert positions["POSITION_MASTER"].fixed_salary_monthly == 80_000.0
        assert positions["POSITION_LABOR_STOREKEEPER"].fixed_salary_monthly == 27_093.0
        assert positions["POSITION_LABOR_DRIVER"].fixed_salary_monthly == 27_093.0
        about_rates = [warning for warning in legacy.warnings if "Ставки персонала" in warning]
        assert about_rates == [
            "Оклад по МРОТ 2026 года (27 093 ₽): в разделе «Ставки персонала» нет ставки у должностей "
            "«Кладовщик», «Водитель»."
        ]

    def test_without_payroll_params_salary_stays_zero(self):
        legacy = self._legacy()
        positions = {item.id: item for item in legacy.labor_catalog}
        assert positions["POSITION_LABOR_DRIVER"].fixed_salary_monthly == 0.0
        assert [warning for warning in legacy.warnings if "Ставки персонала" in warning] == [
            "В разделе «Ставки персонала» нет ставки у должностей «Кладовщик», «Водитель»: оклад принят 0."
        ]
```

Существующий `TestFallbacks.test_fixed_costs_and_positions` остаётся без правок: имя «Машинист» и «ставк» есть
в новой строке.

- [ ] **Step 2: убедиться, что падает.**

Run: `../../../.venv/bin/python -m pytest tests/test_legacy_adapter.py -q`
Expected: FAIL — `test_minimum_wage_and_one_warning`: оклад 0.0 вместо 27 093.

- [ ] **Step 3: реализация.** В `cost/v2/legacy_adapter.py`:

добавить импорт после `from cost.v2.models import ReferenceItem, ReferenceSnapshot`:

```python
from cost.v2.payroll_params import PayrollParamsChoice, payroll_params_for_year
```

в `legacy_references_from_snapshot` заменить сборку `labor`:

```python
    labor = _fallback(
        "Раздел «Должности и ставки» пуст",
        _positions(
            snapshot.active_items("positions"),
            rates,
            payroll_params_for_year(snapshot.sections.get("payroll_params", ()), date.today().year),
            warnings,
        ),
        DEFAULT_LABOR_CATALOG,
        warnings,
    )
```

заменить функцию `_position` целиком на:

```python
def _positions(
    items: Iterable[ReferenceItem],
    rates: dict[str, ReferenceItem],
    params: PayrollParamsChoice | None,
    warnings: list[str],
) -> list[JobPosition]:
    """Должности сметы V1. Без ставки — оклад по МРОТ года (методика ФОТ, TASK-010 §2.2).

    Должности без ставки называются одной строкой, а не строкой на каждую: после
    сида методики их семь, и предупреждения заслоняли остальные.
    """

    mrot = float(params.params.mrot) if params is not None else 0.0
    positions: list[JobPosition] = []
    without_rate: list[str] = []
    for item in items:
        rate = rates.get(item.code)
        if rate is None:
            without_rate.append(f"«{item.name}»")
        positions.append(
            JobPosition(
                id=_legacy_id(item),
                name=item.name,
                fixed_salary_monthly=_number(rate.payload.get("fixed_monthly_rub")) if rate else mrot,
                piece_rate_per_m3=_number(rate.payload.get("piece_rate_rub")) if rate else 0.0,
            )
        )
    if without_rate:
        names = ", ".join(without_rate)
        if params is None:
            warnings.append(f"В разделе «Ставки персонала» нет ставки у должностей {names}: оклад принят 0.")
        else:
            warnings.append(
                f"Оклад по МРОТ {params.params.year} года ({_rub(params.params.mrot)} ₽): в разделе "
                f"«Ставки персонала» нет ставки у должностей {names}."
            )
    return positions
```

и перед `def _optional_number` добавить:

```python
def _rub(value: Decimal) -> str:
    """Рубли для текста предупреждения: «27 093», «27 093,50»."""

    text = format(value.quantize(Decimal("0.01")), ",f").replace(",", "\u00a0").replace(".", ",")
    return text.removesuffix(",00")
```

- [ ] **Step 4: тест проходит.**

Run: `../../../.venv/bin/python -m pytest tests/test_legacy_adapter.py tests/test_legacy_adapter_roundtrip.py tests/test_api_workspace.py -q`
Expected: PASS.

- [ ] **Step 5: коммит.**

```bash
git add cost/v2/legacy_adapter.py tests/test_legacy_adapter.py
git commit -m "Смета V1: должность без ставки — оклад по МРОТ года одной строкой

Семь предупреждений «нет ставки, принят 0» после сида методики ФОТ
сворачиваются в одно; правило то же, что у методики (TASK-010 §2.2).

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Задача 10: документация и график кривой

**Files:**
- Create: `scripts/plot_payroll_curve.py`
- Create: `Docs/specs/payroll/Шкала машиниста — степенная кривая.png` (выход скрипта)
- Create: `Docs/PAYROLL_MODEL.md`
- Modify: `Docs/ADR-001-economics-model.md`, `Docs/COST_MODEL.md`, `CLAUDE.md`
- (Только при ответе Б на вопрос 1) Create: `Docs/specs/payroll/Расчёт заработной платы 2026-09.xlsx` — копия
  `~/Yandex.Disk.localized/001 ComplEX/003 Персонал/Штатное расписание/Расчет заработной платы.xlsx`.

- [ ] **Step 1: скрипт графика.** Создать `scripts/plot_payroll_curve.py`:

```python
"""График кривой машиниста (TASK-010) для `Docs/specs/payroll/`.

Строится теми же функциями, что считают премию (`cost.model.payroll`), — картинка
не расходится с моделью. Запуск из корня репозитория:

    .venv/bin/python scripts/plot_payroll_curve.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import matplotlib  # noqa: E402

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from cost.model.payroll import Scale, scale_series  # noqa: E402
from cost.v2.payroll_defaults import DRILLER_SCALE  # noqa: E402
from decimal import Decimal  # noqa: E402

OUTPUT = ROOT / "Docs" / "specs" / "payroll" / "Шкала машиниста — степенная кривая.png"


def main() -> None:
    scale = Scale(
        DRILLER_SCALE["scale_type"],
        norm_per_shift=Decimal(DRILLER_SCALE["norm_per_shift"]),
        rate_norm=Decimal(DRILLER_SCALE["rate_norm"]),
        ceiling_per_shift=Decimal(DRILLER_SCALE["ceiling_per_shift"]),
        rate_ceiling=Decimal(DRILLER_SCALE["rate_ceiling"]),
    )
    points = scale_series(scale)
    paces = [float(point.pace) for point in points]
    figure, (rate_axis, premium_axis) = plt.subplots(1, 2, figsize=(11, 4.2), dpi=150)
    rate_axis.plot(paces, [float(point.rate) for point in points], color="#1f5fa8", linewidth=2)
    rate_axis.set_title("Цена приведённого метра r(m), ₽")
    premium_axis.plot(paces, [float(point.per_shift) for point in points], color="#b5562a", linewidth=2)
    premium_axis.set_title("Премия за смену p(m), ₽")
    for axis in (rate_axis, premium_axis):
        for node, label in ((scale.norm_per_shift, "норма"), (scale.ceiling_per_shift, "потолок")):
            axis.axvline(float(node), color="#888888", linestyle="--", linewidth=1)
            axis.annotate(f"{label} {float(node):.1f}", (float(node), axis.get_ylim()[1]), rotation=90,
                          va="top", ha="right", fontsize=8, color="#555555")
        axis.set_xlabel("приведённых м за эффективную смену")
        axis.grid(alpha=0.3)
    figure.suptitle(f"Кривая машиниста: 45 ₽ на норме, 168,66 ₽ на потолке, γ = {format(float(scale.gamma), '.3f').replace('.', ',')}")
    figure.tight_layout()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(OUTPUT)
    print(OUTPUT.relative_to(ROOT))


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: построить PNG.**

Run: `../../../.venv/bin/python scripts/plot_payroll_curve.py`
Expected: печатает `Docs/specs/payroll/Шкала машиниста — степенная кривая.png`; на левом графике цена 45 ₽ до
нормы 115,4, рост до 168,66 ₽ на потолке 184,6, дальше постоянна; на правом — выпуклая премия за смену.

- [ ] **Step 3: описание модели.** Создать `Docs/PAYROLL_MODEL.md`:

````markdown
# Модель ФОТ по объектам (TASK-010)

Затраты на персонал по должности × объект × месяц из справочников, без ручных
сумм. Методика — файл владельца «Расчёт заработной платы» с исправлениями и
решениями от 13.09.2026 (`Docs/specs/2026-09-13-task-010-payroll-decisions.md`).

| Что | Где |
|---|---|
| Формулы (нормы) | `cost/model/payroll.py` |
| Чтение справочников | `cost/model/payroll_inputs.py`, год — `cost/v2/payroll_params.py` |
| Превью одной должности | `cost/model/payroll_preview.py`, `POST /api/v1/economics/payroll/preview` |
| График кривой машиниста | `Docs/specs/payroll/Шкала машиниста — степенная кривая.png` (`scripts/plot_payroll_curve.py`) |

В экономику блока методика входит в PR 3a (переключатель источника ФОТ,
`c_var`, цена метра); до этого блок считает ФОТ по ставкам (`Docs/COST_MODEL.md`).

## Входы

| Величина | Раздел справочника | Поле |
|---|---|---|
| МРОТ, годовые нормы часов, рабочие и праздничные дни, ночные, основной отпуск, порог доли | «Параметры ФОТ» года | `mrot`, `annual_hours_40/36`, `work_days_year`, `holidays_year`, `night_pct`, `vacation_days_base`, `margin_share_warn` |
| Класс условий, неделя, вредность, ночные часы, доп. отпуск, система оплаты, приведение | «Должности» | `work_conditions_class`, `week_hours_override`, `hazard_pct`, `night_hours_per_shift`, `extra_vacation_days`, `pay_system`, `difficulty` |
| Оклад, КПЭ, шкала | «Ставки персонала» (ставка без условия бурения) | `fixed_monthly_rub`, `kpi_bonus_pct`, `scale_type` и узлы, `tiers` |
| Вахта, ТОиР, РК, северная, договорной k | «Карьеры и объекты» | `shift_days_on/off`, `travel_days`, `night_shift_share`, `maintenance_shifts`, `regional_coefficient`, `northern_pct`, `contract_k` |
| НДФЛ, СФР, травматизм, доп. тариф, вахтовая надбавка, смена | «Ставки и надбавки организации» | `income_tax_rate`, `social_contribution_rate`, `injury_insurance_rate`, `extra_tariffs`, `per_diem_rub`, `shift_hours` |
| Коэффициенты крепости и диаметра | «Сложность бурения» | `hardness`, `diameter` |
| Коды простоев | «Причины простоев» | `excusable`, `planned_maintenance` |

Год — по месяцу расчёта; записи года нет — ближайший прошлый год (иначе
ближайший будущий) с предупреждением. Оклад не задан (нет ставки или 0) — МРОТ
года с предупреждением. Нет должности, объекта или ни одной записи «Параметров
ФОТ» — ошибка входа (422 в превью). Нет ставок организации — умолчания схемы с
предупреждением. Объект, заведённый до TASK-010, считается по умолчаниям
схемы: вахта 15/15, дорога 2 дня, ТОиР 2 смены, РК 0,15.

Резервы отпусков методика считает по дням (`d / (d + рабочих дней)`), а не
ставкой `vacation_reserve_rate` — та остаётся у расчёта по ставкам.

## Приведённые метры
```
M = contract_k × Σ mᵢ × k_f(fᵢ) × k_d(Øᵢ)
```

Коэффициент не меняет цену метра, а увеличивает зачтённые метры: при
нескольких породах не надо решать, какие метры в какую ступень попали.
Интервалы крепости `f_from < f ≤ f_to` (верх включён). Крепость не задана — k = 1
с предупреждением; f > 20 — коэффициент последней строки с предупреждением.
Диаметра нет в заполненной таблице — ошибка; пустая таблица — k = 1 с
предупреждением. Приведение — только у должностей «Приведённые метры»; у
остальных сдельщиков выработка — сумма как есть.

800 м (f 10, Ø 152) + 900 м (f 17, Ø 250): 800 × 1 × 1 + 900 × 1,2 × 1,64 = 2 571,2.

## Эффективные смены

- План: `S_эфф = shift_days_on − maintenance_shifts` (15 − 2 = 13).
- Факт: `S_эфф = смены − Σ часов простоя excusable / shift_hours`; простой по
  вине машиниста не вычитается.
- Защита входа: часов excusable больше `смены × shift_hours` или `S_эфф ≤ 0` —
  ошибка входа, а не деление на ноль.
- Флаги без блокировки: «списано больше 25 %» (часы excusable без планового
  ТОиР / часы вахты без ТОиР: 40 ч из 143 = 27,97 %), «темп выше 1,2 × потолка».

Постоянная часть ФОТ от простоев не зависит.

## Сдельная премия

Один темп на вахту: `m = M / S_эфф`, премия `P = S_эфф × p(m)`, где `p(m)` —
интеграл цены единицы `r(m)`:

- степенная кривая: `r = r_н × (m / н)^γ` между нормой и потолком,
  `γ = ln(r_п / r_н) / ln(п / н)`;
  `p(m) = r_н × н × (1 + ((m / н)^(γ+1) − 1) / (γ + 1))`;
- линейная: `r` линейна между узлами, `p` — трапеция;
- ступени: `p(m) = Σ rₜ × max(0, min(m, Tₜ) − Tₜ₋₁)`;
- до нормы `p = r_н × m`, выше потолка `r = r_п`.

Посменный расчёт запрещён: кривая выпукла, рваный ритм (6 смен по 100 м и 6 по
230 — 144 927,72 ₽) оплачивался бы выше ровного (12 по 165 — 109 857,35 ₽).

Кривая X машиниста и помощника: норма 115,3846 м/смену (1 500 м за 13 смен),
45 ₽; потолок 184,6154 (2 400 м), 168,66 ₽; γ = 2,811088. Узлы хранятся с
четырьмя знаками: с двумя премия при 2 400 м расходится на 0,24 ₽.

| М за 13 смен | 1 500 | 1 800 | 2 000 | 2 400 | 3 000 |
|---|---|---|---|---|---|
| Премия, ₽ | 67 500,00 | 85 271,62 | 102 804,58 | 156 000,67 | 257 196,67 |

## Месячный ФОТ должности

Строки в порядке файла (`payroll_month`):

1. Оклад; вредность `оклад × hazard_pct`.
2. Ночные `смены × ночных часов × доля ночных × часовая ставка × night_pct`,
   часовая ставка `оклад / (годовая норма недели / 12)`.
3. Праздники `праздничных дней × смены / (смены + межвахта) × shift_hours / 12 × часовая ставка`.
4. Межвахтовый отдых `оклад / (рабочих дней / 12) × дней межвахты` (в файле делитель 21,5).
5. Сдельная премия, премия КПЭ `оклад × kpi_bonus_pct`.
6. Районный и северная — от суммы строк 1–5; начислено (gross).
7. НДФЛ `gross × ставка` и «к выплате» — справочно, в затраты не входят.
8. Надбавка за вахту `per_diem_rub × (смены + дорога)` — без НДФЛ и взносов.
9. Взносы, доп. тариф по классу (у классов 1–2 нет), травматизм — от gross.
10. Резервы доп. и основного отпуска `(gross + взносы) × d / (d + рабочих дней)`.
11. Затраты компании = gross + вахта + взносы + доп. тариф + травматизм + резервы.

Исправление файла: в файле затраты компании прибавляют НДФЛ к начисленному —
391 010,22 ₽ вместо 358 103,01 ₽.

Регрессия по файлу (премия 170 000 ₽, делитель 21,5): межвахтовый 18 902,09;
gross 253 132,36; НДФЛ 32 907,21; к выплате 232 125,16; затраты 358 103,01. С
календарным делителем 247 / 12: межвахтовый 19 743,89; gross 254 100,42;
затраты 359 427,01.

## Затраты на рубль премии и доля в марже
```
затраты на рубль премии = (1 + РК + северная) × (1 + СФР + доп. тариф + травматизм)
                          × (1 + d_доп / (d_доп + W) + d_осн / (d_осн + W))
share(m) = Σ чел × r(m) × затраты на рубль премии × приведённых м на п.м. / (цена − переменные)
```

По параметрам файла затраты на рубль премии — 1,572827: 168,66 ₽ на потолке
стоят компании 265,27 ₽. Доля считается в двух точках — плановый темп и
потолок; предупреждение — по потолку (у ступеней — по плановому темпу), порог
`margin_share_warn`. Отдельно — «получает машинист»: цена его последнего метра
без начислений к марже. Экипаж по умолчанию — все сдельщики с приведёнными
метрами и шкалой (машинист и помощник) по одному в смене.

Цена 800 ₽/м, переменные 250 ₽/м, экипаж из двух на кривой X: потолок 96,46 %
(предупреждение), 2 000 м за 13 смен — 57,78 %, машинист без начислений на
потолке — 30,67 %. Без цены доля не проверяется; маржа ≤ 0 — доли нет,
предупреждение.

## Превью

`POST /api/v1/economics/payroll/preview`:

```json
{"position_code": "POSITION_LABOR_DRILLER", "site_code": "SITE", "month": "2026-09",
 "shifts": null, "downtime": [], "items": [{"meters": 800, "diameter_mm": 152, "rock_code": "ROCK"}],
 "meters_total": null, "crew": [], "price_rub_per_m": 800, "variable_rub_per_m": 250}
```

- `shifts` пусто — план; задан — факт, `downtime` только вместе с ним.
- `items` (крепость породой или числом `f`) или `meters_total` (приведённые
  метры суммой), не оба.
- Ответ: строки ФОТ, приведённые метры, смены, разбивка премии (темп, γ,
  премия за смену, цена последнего метра, средняя цена, ступени), затраты на
  рубль премии, доля в марже, ряды графика `series` (r и p от 0 до 1,3 потолка,
  узлы и темп — точно), флаги, предупреждения, происхождение величин.
- 422 — ошибка входа с объяснением: простоев больше часов вахты, нет должности,
  объекта или параметров года, неизвестный код простоя, диаметр вне таблицы.

## Смета V1

Лист «Расчёт» (Cost V1) для должности без ставки берёт МРОТ «Параметров ФОТ»
текущего года и называет такие должности одной строкой предупреждения. Без
«Параметров ФОТ» оклад по-прежнему 0.
````

- [ ] **Step 4: ссылки.** В `Docs/ADR-001-economics-model.md` в конец раздела «### Модель ФОТ» (после абзаца
  «**Косвенный персонал юнита** …») добавить абзац:

```markdown
**Методика ФОТ по объектам (TASK-010).** Сдельная часть по приведённым метрам и шкале, месячный ФОТ должности
с отчислениями и резервами, доля последнего метра в марже — `cost/model/payroll.py`, описание —
`Docs/PAYROLL_MODEL.md`. В экономику блока входит переключателем источника ФОТ (PR 3a TASK-010).
```

В `Docs/COST_MODEL.md` в конец раздела «## ФОТ прямого персонала» добавить строку:

```markdown
Методика ФОТ по объектам (оклад, сдельная премия по шкале, отчисления и резервы по дням) — отдельная модель,
`Docs/PAYROLL_MODEL.md`; блок переходит на неё переключателем источника ФОТ в PR 3a TASK-010.
```

В `CLAUDE.md` после раздела «## Модель себестоимости блока (TASK-007)» вставить раздел:

```markdown
## Модель ФОТ по объектам (TASK-010)

Формулы — `cost/model/payroll.py` (приведённые метры, эффективные смены,
сдельная премия, месячный ФОТ, доля в марже), чтение справочников —
`cost/model/payroll_inputs.py`, превью — `POST /economics/payroll/preview`
(`cost/model/payroll_preview.py`). Премия — только на среднем темпе вахты, не
посменно; НДФЛ в затраты компании не входит; взносы — из ставок организации,
календарь и МРОТ — из «Параметров ФОТ» года. Подробности — `Docs/PAYROLL_MODEL.md`.
```

- [ ] **Step 5: коммит.**

```bash
git add scripts/plot_payroll_curve.py "Docs/specs/payroll/Шкала машиниста — степенная кривая.png" Docs/PAYROLL_MODEL.md Docs/ADR-001-economics-model.md Docs/COST_MODEL.md CLAUDE.md
git commit -m "ФОТ (TASK-010 PR 2): описание модели, график кривой машиниста

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Задача 11: проверка, ревью, PR

- [ ] **Step 1: весь pytest.**

Run: `../../../.venv/bin/python -m pytest -q --ignore-glob="* 2.py"`
Expected: PASS, без новых предупреждений `StarletteDeprecationWarning` из `block_economics.py`.
`tests/test_model_regression_smeta_2026_01.py` проходит без правок.

- [ ] **Step 2: ручная проверка превью** на тестовом стенде (`local-test-stand`: `api-stand`, без входа):
  опубликовать сид методики через `POST /api/v1/economics/references/publish` и вызвать превью машиниста
  (`meters_total = 2400`, без цены) — премия 156 000,67 ₽, доля «не проверена»; с ценой 800 / переменными 250 —
  флаг доли на потолке. Числа и предупреждения — в описание PR.

- [ ] **Step 3: `/code-review`** на диапазоне ветки, исправить найденное (правило `review-before-merge`).

- [ ] **Step 4: PR** в main: `gh pr create --base main` с описанием — что сделано, решения планировщика (раздел
  выше), ответы владельца на вопросы 1–2, проверка. Последняя строка описания —
  `🤖 Generated with [Claude Code](https://claude.com/claude-code)`.

- [ ] **Step 5: Codex.** Позвать `@codex review`, прочитать `gh api repos/dvotapi/BlastEX/pulls/<N>/reviews` и
  `.../comments`, ответить на замечания. Не сливать — сливает владелец.
