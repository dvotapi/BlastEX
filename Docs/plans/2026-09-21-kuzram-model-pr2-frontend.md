# Модель Kuz-Ram, PR 2 (фронт) — план реализации

> **Для агентов-исполнителей:** обязательный навык — superpowers:subagent-driven-development (рекомендуется) или superpowers:executing-plans. Шаги отмечаются чекбоксами (`- [ ]`).

**Цель:** на листе «Расчёт» появляется окно «Модель Kuz-Ram» — настройки модели подбора q, сравнение с расчётом «до исправления», график, разбор, фактические взрывы с подбором C(A) и справка с примерами; настройки и взрывы хранятся за объектом работ.

**Архитектура:** всё считает сервер PR 1 (`/blast/optimize` с блоком `kuzram`, `/blast/kuzram/calibrate`). Фронт хранит блок `kuzram` в настройках листа (`calc-inputs`), проверяет ввод по границам из `kuzramContract.json` (копия серверных констант, сверяется Python-тестом) и только показывает ответы API. Окно — нативный `<dialog>`, компоненты в `frontend/src/pages/calc/kuzram/`.

**Стек:** React 19 + TypeScript, Vitest + Testing Library (jsdom), самописный SVG; Python 3.12 + unittest (запуск через pytest) для тестов контракта и примеров.

**Спецификация:** `Docs/plans/2026-09-21-kuzram-model-design.md` (части 2–4) — читать вместе с планом. Образец плана — `Docs/plans/2026-09-21-kuzram-model-pr1-backend.md`, описание модели — `Docs/KUZRAM_MODEL.md`.

## Общие ограничения

- Рабочая копия: `/Users/apple/Documents/Проекты/BlastEX/.claude/worktrees/dazzling-antonelli-bfc24e`, ветка `feat/kuzram-model-ui` (от `origin/feat/kuzram-model` 7dbeec8, без upstream). Все команды — из её корня. Если PR 1 получит новые коммиты — `git fetch origin && git rebase origin/feat/kuzram-model` до начала следующей задачи.
- **Не пушить в `main` и ничего не сливать**: push в `main` сразу выкатывает прод (`.github/workflows/deploy.yml`). PR 2 — черновик с базой `feat/kuzram-model`; PR 1 (#88) и PR 2 сливаются вместе и только по решению владельца.
- Python: `../../../.venv/bin/python -m pytest <путь> -q -p no:cacheprovider`.
- Тесты фронта: `npm --prefix frontend test -- <путь от frontend/>` (все — без пути). Проверка типов: `frontend/node_modules/.bin/tsc -p frontend/tsconfig.app.json`. Зависимости уже поставлены (`npm --prefix frontend ci`).
- Тесты компонентов начинаются с `// @vitest-environment jsdom`; jsdom не умеет модальный `dialog` — `showModal`/`close` подменяются в `beforeAll`, как в `frontend/src/pages/calc/CalcHelp.test.tsx`.
- Правила `CLAUDE.md`: интерфейс — только `frontend/`; **формулы модели во фронте не считаются** (разрешены только форматирование и арифметика показа: разница q в процентах, отношение q в справке); пользователю не показывается JSON.
- Шрифты, размеры и цвета — из `frontend/src/styles.css`: текст `#17231d`, приглушённый `#6e7c75`/`#748079`, рамки `#d9e2dd`/`#e2e8e5`, акцент `#2d7556`, выбранная строка `#edf7f1`, ошибка `#9e3025` на `#fce9e7`, предупреждение `#684b17` на `#fff8e9` с рамкой `#ead39f`; переменные `--fs-*`, `--control-h`, `--radius-*`, `--font-weight-*`. Новые стили — в `frontend/src/styles/kuzram.css`.
- Числа в окне — с запятой (`ruNumber` из `frontend/src/lib/format.ts`, `trimmed` из `kuzramFormat.ts`); таблица вариантов на листе остаётся с точкой, как сейчас.
- Тексты интерфейса, комментарии и docstring — по-русски, в стиле соседнего кода.
- `git add` — только перечисленные файлы. Каталог `.claude/` (стенд, `launch.json`) не коммитится.
- Коммит заканчивается строкой `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`.

## Решения и отклонения от спецификации

1. **W/d (B/d у Каннингема)** — решение владельца 21.09.2026: предупреждать **только выше 35**, подбор не ограничивать. Ниже 25 не предупреждаем: для одобренного габбро-диабаза W/d = 20–23,5 на всех коронках. Предупреждение — в разборе расчёта и строкой под таблицей вариантов окна.
2. **Подписи JPA** — по Каннингему 2005, §4.1.1.3 («out of face» — плоскость трещины, продолженная из откоса, уходит вверх): 20 — «падение в сторону откоса», 30 — «простирание поперёк откоса», 40 — «падение в массив». В спецификации было наоборот; владелец 21.09.2026 выбрал вариант статьи. Формулировки отдаются на подтверждение технологу (пометка в описании PR и в спецификации).
3. **Границы и умолчания** — не запросом к серверу, а копией в `kuzramContract.json` с Python-тестом на совпадение с `cunningham.py` и схемами API. Причина: сохранённые настройки листа читаются синхронно при загрузке объекта; тест ловит расхождение так же надёжно, как общий источник.
4. **`loc` у ошибок настроек и `field_error`** не нужны: фронт проверяет те же границы до отправки (настройки, коронка факта 20–1000 мм, q и негабарит факта), поэтому 422 не ожидается. Коронки листа приходят из `/blast/options` (110–250 мм) и всегда в границах `CrownMm`. 400 при A ≤ 0 приходит строкой `detail` и показывается как есть (на листе и в окне).
5. **Пример скачка JF.** Цифры из ревью PR 1 (q 1,60 → 1,61, негабарит 7,53 → 1,79 %) не воспроизводятся по сохранённым данным. Справка показывает проверяемый тестом случай: габбро-диабаз с трещиноватостью 0,3 на 1 м, коронка 152 мм, JF: q 1,60 → 1,61, JPS 80 → 50, негабарит 11,48 → 4,00 %.
6. **Цвета графика**: Kuz-Ram — акцентный зелёный `#2d7556`, «до исправления» — серо-синий пунктир `#8a99a6` (в симуляторе были синий и оранжевый; оранжевого в палитре приложения нет).
7. **«≤» у q**: у Kuz-Ram от 0,10, у «до исправления» — от его нижней границы 0,30. Плашки над таблицей листа (`MetricChips`) не меняются.

## Карта файлов

| Файл | Что делает |
|---|---|
| `frontend/src/pages/calc/kuzram/kuzramContract.json` (новый) | Умолчания, границы и варианты настроек, границы фактов — копия серверных констант |
| `tests/test_kuzram_frontend_contract.py` (новый) | Сверка контракта с `cunningham.py` и `api/schemas/blast.py` |
| `frontend/src/pages/calc/kuzram/kuzramFormat.ts` (новый, + тест) | Формат чисел окна: q «≤ 0,10», негабарит «> порога», разница q, сетка |
| `frontend/src/pages/calc/kuzram/kuzramSettings.ts` (новый, + тест) | Блок `kuzram`: типы, умолчания, чтение, проверка ввода, подпись у кнопки |
| `frontend/src/types.ts` | Типы настроек, разбора, «до исправления», ответов подбора и калибровки |
| `frontend/src/api/endpoints.ts` (+ `endpoints.kuzram.test.ts`) | `optimize` с `kuzram`, новый `calibrateKuzram` |
| `frontend/src/pages/calc/calcInputs.ts` (+ тест) | Блок `kuzram` в настройках листа |
| `frontend/src/pages/calc/kuzram/testing/optimizeGabbro.json`, `fixtures.ts` (новые) | Ответ сервера PR 1 для тестов окна |
| `frontend/src/pages/calc/kuzram/KuzRamDialog.tsx` (новый, + тест) | Окно, вкладки «Расчёт» и «Как пользоваться» |
| `frontend/src/pages/calc/kuzram/KuzRamSettingsForm.tsx` (новый, + тест) | Настройки модели |
| `frontend/src/pages/calc/kuzram/ThresholdFlag.tsx` (новый) | Значок «!» — порог не достигнут |
| `frontend/src/pages/calc/kuzram/KuzRamComparison.tsx` (новый, + тест) | Сводка выбранной коронки и таблица по коронкам |
| `frontend/src/pages/calc/kuzram/KuzRamChart.tsx` (новый, + тест) | График q(d) на SVG |
| `frontend/src/pages/calc/kuzram/KuzRamBreakdown.tsx` (новый, + тест) | Разбор расчёта, предупреждение W/d |
| `frontend/src/pages/calc/kuzram/KuzRamFacts.tsx` (новый, + тест) | Фактические взрывы, подбор C(A) |
| `frontend/src/pages/calc/kuzram/KuzRamHelp.tsx` (новый, + тест), `helpExamples.json` (новый) | Справка с примерами |
| `tests/test_kuzram_help_examples.py` (новый) | Пересчёт примеров справки моделью |
| `frontend/src/pages/CalcPage.tsx` (+ `CalcPage.kuzram.test.tsx`) | Состояние блока, пересчёт по правке настроек, кнопка и подпись, «!» в таблице, окно |
| `frontend/src/styles/kuzram.css` (новый), `frontend/src/main.tsx` | Стили окна и значка |
| `frontend/src/pages/calc/CalcHelp.tsx` (+ тест) | Справка листа: q, модель, кнопка окна |
| `CLAUDE.md`, `Docs/KUZRAM_MODEL.md`, `Docs/plans/2026-09-21-kuzram-model-design.md` | Где живёт модель, интерфейс, решения по W/d и JPA |

---

### Task 1. Контракт настроек и модуль блока `kuzram`

Основа для всех следующих задач: умолчания и границы с проверкой на сервере, чтение сохранённого блока, проверка ввода, подпись у кнопки и формат чисел.

**Файлы:**
- Создать: `frontend/src/pages/calc/kuzram/kuzramContract.json`, `tests/test_kuzram_frontend_contract.py`
- Создать: `frontend/src/pages/calc/kuzram/kuzramFormat.ts`, `frontend/src/pages/calc/kuzram/kuzramFormat.test.ts`
- Создать: `frontend/src/pages/calc/kuzram/kuzramSettings.ts`, `frontend/src/pages/calc/kuzram/kuzramSettings.test.ts`
- Изменить: `frontend/src/types.ts` (добавить типы настроек после `BlastVariant`)

**Интерфейсы:**
- Производит (`types.ts`): `RockFactorMethod`, `StrengthExponent`, `KuzRamSettings` (9 полей API, snake_case), `KuzRamFactInput` (`crown_mm`, `q_kg_m3`, `oversize_pct` — числа).
- Производит (`kuzramFormat.ts`): `Q_MIN_KG_M3`, `LEGACY_Q_MIN_KG_M3`, `trimmed(value, maxDigits = 3): string`, `formatQ(q, decimal = ",", floor = Q_MIN_KG_M3): string`, `formatOversize(pct, reached, thresholdPct, digits = 2, decimal = ","): string`, `qDeltaText(newQ, legacyQ): string`, `gridText(aM, bM): string`.
- Производит (`kuzramSettings.ts`): типы `KuzRamFact`, `KuzRamBlock`, `NumericSetting`, `FactField`; константы `KUZRAM_DEFAULTS`, `ROCK_FACTOR_METHODS`, `JOINT_CONDITIONS`, `JOINT_ANGLES`, `STRENGTH_EXPONENTS`, `MAX_FACTS`, `FACT_FIELDS`, `FACT_LABELS`, `NUMERIC_LABELS`, `BURDEN_TO_DIAMETER_WARN_ABOVE`; функции `numericBounds`, `defaultKuzramBlock`, `readKuzramBlock`, `kuzramSettingsOf`, `copyKuzramBlock`, `sameSettings`, `settingsCaption`, `parseDecimal`, `settingError`, `factCellError`, `completeFacts`.

- [ ] **Шаг 1. Контракт и Python-тест**

`frontend/src/pages/calc/kuzram/kuzramContract.json`:

```json
{
  "defaults": {
    "rock_factor_method": "rmd50",
    "rock_factor_manual": 6,
    "joint_condition": 1,
    "joint_angle": 20,
    "rock_factor_correction": 1,
    "strength_exponent": "19/20",
    "drill_deviation_m": 0,
    "uniformity_correction": 1,
    "q_max_kg_m3": 2
  },
  "bounds": {
    "rock_factor_manual": [0.5, 30],
    "rock_factor_correction": [0.1, 10],
    "drill_deviation_m": [0, 2],
    "uniformity_correction": [0.5, 2],
    "q_max_kg_m3": [0.5, 5]
  },
  "rock_factor_methods": ["rmd50", "rmd10", "joint_factor", "manual"],
  "joint_conditions": [1, 1.5, 2],
  "joint_angles": [20, 30, 40],
  "strength_exponents": ["19/20", "19/30"],
  "q_min_kg_m3": 0.1,
  "fact_bounds": {
    "crown_mm": { "ge": 20, "le": 1000 },
    "q_kg_m3": { "gt": 0, "le": 10 },
    "oversize_pct": { "gt": 0, "lt": 100 }
  },
  "max_facts": 50
}
```

Коронка 20–1000 мм включительно — это `CrownMm` из `api/schemas/blast.py` (коммит 7dbeec8 PR 1): те же границы проверяются и у `crown_diameters_mm` подбора, вне их сервер отвечает 422.

`tests/test_kuzram_frontend_contract.py`:

```python
"""Умолчания и границы модели Kuz-Ram во фронте совпадают с сервером.

Фронт держит их в frontend/src/pages/calc/kuzram/kuzramContract.json, чтобы
читать сохранённые настройки листа и проверять ввод без запроса к API. Тест
не даёт этой копии разойтись с cunningham.py и схемами api/schemas/blast.py.
"""
from __future__ import annotations

import json
import unittest
from dataclasses import asdict
from pathlib import Path

from api.schemas.blast import CROWN_MM_MAX, CROWN_MM_MIN, KuzRamCalibrateRequest, KuzRamFactSchema
from simulation.fragmentation.cunningham import (
    JOINT_ANGLES,
    JOINT_CONDITIONS,
    NUMERIC_BOUNDS,
    Q_MIN_KG_M3,
    ROCK_FACTOR_METHODS,
    STRENGTH_EXPONENTS,
    KuzRamSettings,
)

CONTRACT = (
    Path(__file__).resolve().parents[1] / "frontend" / "src" / "pages" / "calc" / "kuzram" / "kuzramContract.json"
)


def _constraints(field) -> dict[str, float]:
    """Ограничения поля pydantic (gt, ge, lt, le, max_length) из его metadata."""
    found: dict[str, float] = {}
    for item in field.metadata:
        for key in ("gt", "ge", "lt", "le", "max_length"):
            value = getattr(item, key, None)
            if value is not None:
                found[key] = value
    return found


class KuzRamFrontendContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.contract = json.loads(CONTRACT.read_text(encoding="utf-8"))

    def test_defaults_match_settings_dataclass(self) -> None:
        self.assertEqual(self.contract["defaults"], asdict(KuzRamSettings()))

    def test_numeric_bounds_match(self) -> None:
        expected = {name: [low, high] for name, (low, high, _label) in NUMERIC_BOUNDS.items()}
        self.assertEqual(self.contract["bounds"], expected)

    def test_options_match(self) -> None:
        self.assertEqual(self.contract["rock_factor_methods"], list(ROCK_FACTOR_METHODS))
        self.assertEqual(self.contract["joint_conditions"], list(JOINT_CONDITIONS))
        self.assertEqual(self.contract["joint_angles"], list(JOINT_ANGLES))
        self.assertEqual(self.contract["strength_exponents"], list(STRENGTH_EXPONENTS))
        self.assertEqual(self.contract["q_min_kg_m3"], Q_MIN_KG_M3)

    def test_fact_bounds_match_api_schema(self) -> None:
        # Коронку проверяет валидатор CrownMm (границы — константы схемы), q и
        # негабарит — ограничения Field.
        expected = {name: _constraints(field) for name, field in KuzRamFactSchema.model_fields.items()}
        expected["crown_mm"] = {"ge": CROWN_MM_MIN, "le": CROWN_MM_MAX}
        self.assertEqual(self.contract["fact_bounds"], expected)
        facts_field = KuzRamCalibrateRequest.model_fields["facts"]
        self.assertEqual(self.contract["max_facts"], _constraints(facts_field)["max_length"])
```

Run: `../../../.venv/bin/python -m pytest tests/test_kuzram_frontend_contract.py -q -p no:cacheprovider`
Expected: 4 passed. Для проверки, что тест ловит расхождение, временно поменяйте в JSON `"q_max_kg_m3": 2` на `3` — `test_defaults_match_settings_dataclass` должен упасть; верните `2`.

- [ ] **Шаг 2. Типы настроек в `frontend/src/types.ts`**

Сразу после типа `BlastVariant` добавить:

```ts
/** Способ расчёта фактора породы A в модели Kuz-Ram (Каннингем, 2005). */
export type RockFactorMethod = "rmd50" | "rmd10" | "joint_factor" | "manual";

/** Показатель при силе ВВ в формуле среднего куска. */
export type StrengthExponent = "19/20" | "19/30";

/** Настройки модели Kuz-Ram — как `KuzRamSettingsSchema` в API. */
export type KuzRamSettings = {
  rock_factor_method: RockFactorMethod;
  rock_factor_manual: number;
  joint_condition: number;
  joint_angle: number;
  rock_factor_correction: number;
  strength_exponent: StrengthExponent;
  drill_deviation_m: number;
  uniformity_correction: number;
  q_max_kg_m3: number;
};

/** Фактический взрыв для подбора C(A) — как `KuzRamFactSchema` в API. */
export type KuzRamFactInput = { crown_mm: number; q_kg_m3: number; oversize_pct: number };
```

- [ ] **Шаг 3. Падающие тесты формата**

`frontend/src/pages/calc/kuzram/kuzramFormat.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { formatOversize, formatQ, gridText, LEGACY_Q_MIN_KG_M3, qDeltaText, trimmed } from "./kuzramFormat";

describe("kuzramFormat", () => {
  it("trimmed — запятая, без лишних нулей и разделителя тысяч", () => {
    expect(trimmed(1.127)).toBe("1,127");
    expect(trimmed(2)).toBe("2");
    expect(trimmed(0.5)).toBe("0,5");
    expect(trimmed(1.12345, 6)).toBe("1,12345");
    expect(trimmed(1000)).toBe("1000");
  });

  it("q на нижней границе перебора — «≤»", () => {
    expect(formatQ(1.26)).toBe("1,26");
    expect(formatQ(0.1)).toBe("≤ 0,10");
    expect(formatQ(0.1, ".")).toBe("≤ 0.10");
    expect(formatQ(0.3, ",", LEGACY_Q_MIN_KG_M3)).toBe("≤ 0,30");
    expect(formatQ(0.31, ",", LEGACY_Q_MIN_KG_M3)).toBe("0,31");
  });

  it("негабарит «> порога», когда порог не достигнут, а округление дало порог", () => {
    expect(formatOversize(4.98, true, 5)).toBe("4,98");
    expect(formatOversize(5.4, false, 5)).toBe("5,40");
    expect(formatOversize(5, false, 5)).toBe("> 5");
    expect(formatOversize(5.04, false, 5, 1, ".")).toBe("> 5");
    expect(formatOversize(5.04, false, 5, 2, ".")).toBe("5.04");
  });

  it("разница q в целых процентах со знаком", () => {
    expect(qDeltaText(1.26, 1.34)).toBe("−6 %");
    expect(qDeltaText(1.45, 1.34)).toBe("+8 %");
    expect(qDeltaText(1.34, 1.34)).toBe("0 %");
  });

  it("сетка a × b", () => {
    expect(gridText(4.42, 3.54)).toBe("4,42 × 3,54");
    expect(gridText(3.3, 4)).toBe("3,30 × 4,00");
  });
});
```

Run: `npm --prefix frontend test -- src/pages/calc/kuzram/kuzramFormat.test.ts`
Expected: FAIL — модуля `./kuzramFormat` нет.

- [ ] **Шаг 4. `kuzramFormat.ts`**

```ts
/**
 * Формат чисел окна «Модель Kuz-Ram» и таблицы вариантов листа. Только показ:
 * формул модели здесь нет, все величины приходят с сервера.
 */
import { ruNumber } from "../../../lib/format";
import contract from "./kuzramContract.json";

type Decimal = "," | ".";

/** Нижняя граница перебора q новой модели — меньшие значения модель не проверяет. */
export const Q_MIN_KG_M3: number = contract.q_min_kg_m3;

/** Перебор «до исправления» начинается с 0,30 (`Blast.py::optimize_blast_legacy`). */
export const LEGACY_Q_MIN_KG_M3 = 0.3;

function fixed(value: number, digits: number, decimal: Decimal): string {
  return decimal === "," ? ruNumber(value, digits) : value.toFixed(digits);
}

/** Число без лишних нулей и без разделителя тысяч: 1,127; 2; 0,5. */
export function trimmed(value: number, maxDigits = 3): string {
  return value.toLocaleString("ru-RU", { maximumFractionDigits: maxDigits, useGrouping: false });
}

/**
 * q с двумя знаками. На нижней границе перебора — «≤ 0,10»: порог выполнен
 * уже там, а меньшие q модель не проверяла.
 */
export function formatQ(q: number, decimal: Decimal = ",", floor = Q_MIN_KG_M3): string {
  const text = fixed(q, 2, decimal);
  return q <= floor + 1e-9 ? `≤ ${text}` : text;
}

/**
 * Негабарит с `digits` знаками. Если порог не достигнут, а округление дало
 * порог или меньше (на верхней границе q: 5,004 % → «5,00» при пороге 5 %),
 * показываем «> 5» — иначе цифра спорит со значком «!».
 */
export function formatOversize(
  pct: number,
  reached: boolean,
  thresholdPct: number,
  digits = 2,
  decimal: Decimal = ",",
): string {
  if (!reached && Number(pct.toFixed(digits)) <= thresholdPct) {
    return `> ${decimal === "," ? trimmed(thresholdPct) : String(thresholdPct)}`;
  }
  return fixed(pct, digits, decimal);
}

/** Разница q новой модели относительно «до исправления»: «−6 %», «+8 %», «0 %». */
export function qDeltaText(newQ: number, legacyQ: number): string {
  const delta = Math.round(((newQ - legacyQ) / legacyQ) * 100);
  if (delta === 0) return "0 %";
  return `${delta > 0 ? "+" : "−"}${Math.abs(delta)} %`;
}

/** Сетка a × b в метрах: «4,42 × 3,54». */
export function gridText(aM: number, bM: number): string {
  return `${ruNumber(aM, 2)} × ${ruNumber(bM, 2)}`;
}
```

Run: `npm --prefix frontend test -- src/pages/calc/kuzram/kuzramFormat.test.ts`
Expected: 5 passed.

- [ ] **Шаг 5. Падающие тесты модуля блока**

`frontend/src/pages/calc/kuzram/kuzramSettings.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import {
  completeFacts,
  defaultKuzramBlock,
  factCellError,
  KUZRAM_DEFAULTS,
  kuzramSettingsOf,
  MAX_FACTS,
  parseDecimal,
  readKuzramBlock,
  sameSettings,
  settingError,
  settingsCaption,
} from "./kuzramSettings";

describe("readKuzramBlock", () => {
  it("без блока — умолчания и пустые факты", () => {
    expect(defaultKuzramBlock()).toEqual({ ...KUZRAM_DEFAULTS, facts: [] });
    expect(readKuzramBlock(undefined)).toEqual(defaultKuzramBlock());
    expect(readKuzramBlock("мусор")).toEqual(defaultKuzramBlock());
  });

  it("числа обрезаются по границам, неизвестные варианты — умолчание", () => {
    const block = readKuzramBlock({
      rock_factor_method: "как в коде",
      rock_factor_manual: 100,
      joint_condition: 3,
      joint_angle: 30,
      rock_factor_correction: 0.01,
      strength_exponent: "19/30",
      drill_deviation_m: -1,
      uniformity_correction: "2",
      q_max_kg_m3: 1.5,
    });
    expect(block).toEqual({
      rock_factor_method: "rmd50",
      rock_factor_manual: 30,
      joint_condition: 1,
      joint_angle: 30,
      rock_factor_correction: 0.1,
      strength_exponent: "19/30",
      drill_deviation_m: 0,
      uniformity_correction: 1,
      q_max_kg_m3: 1.5,
      facts: [],
    });
  });

  it("незаполненные строки фактов хранятся, мусор в ячейке — пусто, не больше 50 строк", () => {
    const rows = Array.from({ length: 60 }, (_, index) => ({
      crown_mm: 152,
      q_kg_m3: index === 0 ? null : 1.2,
      oversize_pct: "6",
    }));
    const block = readKuzramBlock({ facts: rows });
    expect(block.facts).toHaveLength(MAX_FACTS);
    expect(block.facts[0]).toEqual({ crown_mm: 152, q_kg_m3: null, oversize_pct: null });
    expect(readKuzramBlock({ facts: [null] }).facts).toEqual([{ crown_mm: null, q_kg_m3: null, oversize_pct: null }]);
  });
});

describe("kuzramSettingsOf", () => {
  it("отрезает факты: схема API запрещает лишние поля", () => {
    const block = {
      ...defaultKuzramBlock(),
      rock_factor_correction: 1.2,
      facts: [{ crown_mm: 152, q_kg_m3: 1.2, oversize_pct: 6 }],
    };
    const settings = kuzramSettingsOf(block);
    expect(settings).toEqual({ ...KUZRAM_DEFAULTS, rock_factor_correction: 1.2 });
    expect(Object.keys(settings)).not.toContain("facts");
  });
});

describe("проверка ввода", () => {
  it("parseDecimal понимает запятую; пусто и мусор — null", () => {
    expect(parseDecimal("1,15")).toBe(1.15);
    expect(parseDecimal(" 2 ")).toBe(2);
    expect(parseDecimal("")).toBeNull();
    expect(parseDecimal("abc")).toBeNull();
  });

  it("settingError — тексты как у сервера", () => {
    expect(settingError("rock_factor_correction", 1.15)).toBeNull();
    expect(settingError("rock_factor_correction", 20)).toBe("Поправка C(A) — от 0,1 до 10.");
    expect(settingError("q_max_kg_m3", 0.4)).toBe("Верхняя граница перебора q, кг/м³ — от 0,5 до 5.");
    expect(settingError("drill_deviation_m", null)).toBe("Введите число.");
  });

  it("factCellError — границы схемы факта, пустая ячейка не ошибка", () => {
    expect(factCellError("crown_mm", null)).toBeNull();
    expect(factCellError("crown_mm", 152)).toBeNull();
    expect(factCellError("crown_mm", 20)).toBeNull();
    expect(factCellError("crown_mm", 19)).toBe("Коронка — от 20 до 1000 мм.");
    expect(factCellError("crown_mm", 1001)).toBe("Коронка — от 20 до 1000 мм.");
    expect(factCellError("q_kg_m3", 10)).toBeNull();
    expect(factCellError("q_kg_m3", 11)).toBe("Фактический q — больше 0 и не больше 10 кг/м³.");
    expect(factCellError("oversize_pct", 100)).toBe("Фактический негабарит — больше 0 и меньше 100 %.");
  });

  it("completeFacts — только заполненные строки в границах, с номерами строк", () => {
    const facts = [
      { crown_mm: 152, q_kg_m3: 1.3, oversize_pct: 8 },
      { crown_mm: 165, q_kg_m3: null, oversize_pct: 7 },
      { crown_mm: 130, q_kg_m3: 1.2, oversize_pct: 120 },
      { crown_mm: 110, q_kg_m3: 1.1, oversize_pct: 6 },
    ];
    expect(completeFacts(facts)).toEqual([
      { index: 0, fact: { crown_mm: 152, q_kg_m3: 1.3, oversize_pct: 8 } },
      { index: 3, fact: { crown_mm: 110, q_kg_m3: 1.1, oversize_pct: 6 } },
    ]);
  });
});

describe("settingsCaption", () => {
  it("на умолчаниях пусто", () => {
    expect(settingsCaption(KUZRAM_DEFAULTS)).toBe("");
    expect(sameSettings(KUZRAM_DEFAULTS, { ...KUZRAM_DEFAULTS })).toBe(true);
    expect(sameSettings(KUZRAM_DEFAULTS, { ...KUZRAM_DEFAULTS, joint_angle: 40 })).toBe(false);
  });

  it("кратко перечисляет отличия", () => {
    expect(
      settingsCaption({ ...KUZRAM_DEFAULTS, rock_factor_method: "joint_factor", rock_factor_correction: 1.15 }),
    ).toBe("JF · C(A) 1,15");
    expect(settingsCaption({ ...KUZRAM_DEFAULTS, rock_factor_method: "rmd10" })).toBe("RMD 10");
    expect(
      settingsCaption({
        ...KUZRAM_DEFAULTS,
        rock_factor_method: "manual",
        rock_factor_manual: 7.5,
        strength_exponent: "19/30",
        drill_deviation_m: 0.3,
        uniformity_correction: 0.9,
        q_max_kg_m3: 3,
      }),
    ).toBe("A 7,5 · 19/30 · σ 0,3 м · C(n) 0,9 · q до 3");
  });
});
```

Run: `npm --prefix frontend test -- src/pages/calc/kuzram/kuzramSettings.test.ts`
Expected: FAIL — модуля `./kuzramSettings` нет.

- [ ] **Шаг 6. `kuzramSettings.ts`**

```ts
/**
 * Блок `kuzram` в настройках листа «Расчёт»: настройки модели подбора q и
 * фактические взрывы для подбора C(A). Модуль чистый — ни запросов, ни React.
 *
 * Умолчания и границы — в `kuzramContract.json`, копии констант
 * `simulation/fragmentation/cunningham.py` и схем `api/schemas/blast.py`:
 * совпадение проверяет `tests/test_kuzram_frontend_contract.py`. Формул модели
 * здесь нет — только чтение сохранённого, проверка ввода и подпись у кнопки.
 */
import contract from "./kuzramContract.json";
import { trimmed } from "./kuzramFormat";
import type { KuzRamFactInput, KuzRamSettings, RockFactorMethod, StrengthExponent } from "../../../types";

/** Строка фактического взрыва; `null` — ячейка ещё не заполнена. */
export type KuzRamFact = { crown_mm: number | null; q_kg_m3: number | null; oversize_pct: number | null };

/** Блок в настройках листа: настройки модели и фактические взрывы. */
export type KuzRamBlock = KuzRamSettings & { facts: KuzRamFact[] };

export type NumericSetting = keyof typeof contract.bounds;
export type FactField = keyof KuzRamFact;

export const KUZRAM_DEFAULTS: KuzRamSettings = {
  ...contract.defaults,
  rock_factor_method: contract.defaults.rock_factor_method as RockFactorMethod,
  strength_exponent: contract.defaults.strength_exponent as StrengthExponent,
};
export const ROCK_FACTOR_METHODS = contract.rock_factor_methods as RockFactorMethod[];
export const JOINT_CONDITIONS: number[] = contract.joint_conditions;
export const JOINT_ANGLES: number[] = contract.joint_angles;
export const STRENGTH_EXPONENTS = contract.strength_exponents as StrengthExponent[];
export const MAX_FACTS: number = contract.max_facts;
export const FACT_FIELDS: FactField[] = ["crown_mm", "q_kg_m3", "oversize_pct"];

/**
 * Выше этого W/d (ЛНС к диаметру скважины) окно предупреждает: Каннингем
 * (2005) рекомендует 25–35. Ниже 25 молчим — для крепких пород это обычная
 * сетка (габбро-диабаз: 20–23,5 на коронках 110–250 мм). Подбор q порог не
 * ограничивает. Решение владельца от 21.09.2026.
 */
export const BURDEN_TO_DIAMETER_WARN_ABOVE = 35;

/** Подписи числовых настроек — как в сообщениях сервера (`NUMERIC_BOUNDS`). */
export const NUMERIC_LABELS: Record<NumericSetting, string> = {
  rock_factor_manual: "Фактор породы A",
  rock_factor_correction: "Поправка C(A)",
  drill_deviation_m: "Отклонение бурения σ, м",
  uniformity_correction: "Поправка C(n)",
  q_max_kg_m3: "Верхняя граница перебора q, кг/м³",
};

/** Подписи ячеек факта: название для ошибок и полей ввода, единица для ошибок. */
export const FACT_LABELS: Record<FactField, { label: string; unit: string }> = {
  crown_mm: { label: "Коронка", unit: " мм" },
  q_kg_m3: { label: "Фактический q", unit: " кг/м³" },
  oversize_pct: { label: "Фактический негабарит", unit: " %" },
};

export function numericBounds(field: NumericSetting): { min: number; max: number } {
  const [min, max] = contract.bounds[field];
  return { min, max };
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function numberSetting(value: unknown, field: NumericSetting): number {
  if (typeof value !== "number" || !Number.isFinite(value)) return KUZRAM_DEFAULTS[field];
  const { min, max } = numericBounds(field);
  return Math.min(max, Math.max(min, value));
}

function oneOf<T>(value: unknown, options: readonly T[], fallback: T): T {
  return options.find((option) => option === value) ?? fallback;
}

function factCell(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

export function defaultKuzramBlock(): KuzRamBlock {
  return { ...KUZRAM_DEFAULTS, facts: [] };
}

/**
 * Сохранённый блок → блок листа. Блока нет (настройки до модели Kuz-Ram) —
 * умолчания; числа вне границ обрезаются, неизвестные варианты — умолчание.
 * Строки фактов хранятся и незаполненными, но не больше `MAX_FACTS`.
 */
export function readKuzramBlock(raw: unknown): KuzRamBlock {
  const source = isRecord(raw) ? raw : {};
  const facts = Array.isArray(source.facts) ? source.facts.slice(0, MAX_FACTS) : [];
  return {
    rock_factor_method: oneOf(source.rock_factor_method, ROCK_FACTOR_METHODS, KUZRAM_DEFAULTS.rock_factor_method),
    rock_factor_manual: numberSetting(source.rock_factor_manual, "rock_factor_manual"),
    joint_condition: oneOf(source.joint_condition, JOINT_CONDITIONS, KUZRAM_DEFAULTS.joint_condition),
    joint_angle: oneOf(source.joint_angle, JOINT_ANGLES, KUZRAM_DEFAULTS.joint_angle),
    rock_factor_correction: numberSetting(source.rock_factor_correction, "rock_factor_correction"),
    strength_exponent: oneOf(source.strength_exponent, STRENGTH_EXPONENTS, KUZRAM_DEFAULTS.strength_exponent),
    drill_deviation_m: numberSetting(source.drill_deviation_m, "drill_deviation_m"),
    uniformity_correction: numberSetting(source.uniformity_correction, "uniformity_correction"),
    q_max_kg_m3: numberSetting(source.q_max_kg_m3, "q_max_kg_m3"),
    facts: facts.map((row) => {
      const cells = isRecord(row) ? row : {};
      return {
        crown_mm: factCell(cells.crown_mm),
        q_kg_m3: factCell(cells.q_kg_m3),
        oversize_pct: factCell(cells.oversize_pct),
      };
    }),
  };
}

/**
 * Ровно девять настроек — то, что принимает API (`extra=forbid`). Блок с
 * фактами тоже подходит под тип `KuzRamSettings`, поэтому поля перечислены явно.
 */
export function kuzramSettingsOf(settings: KuzRamSettings): KuzRamSettings {
  return {
    rock_factor_method: settings.rock_factor_method,
    rock_factor_manual: settings.rock_factor_manual,
    joint_condition: settings.joint_condition,
    joint_angle: settings.joint_angle,
    rock_factor_correction: settings.rock_factor_correction,
    strength_exponent: settings.strength_exponent,
    drill_deviation_m: settings.drill_deviation_m,
    uniformity_correction: settings.uniformity_correction,
    q_max_kg_m3: settings.q_max_kg_m3,
  };
}

/** Копия блока для записи: строки фактов — новые объекты. */
export function copyKuzramBlock(block: KuzRamBlock): KuzRamBlock {
  return { ...kuzramSettingsOf(block), facts: block.facts.map((row) => ({ ...row })) };
}

export function sameSettings(a: KuzRamSettings, b: KuzRamSettings): boolean {
  const left = kuzramSettingsOf(a);
  const right = kuzramSettingsOf(b);
  return (Object.keys(left) as (keyof KuzRamSettings)[]).every((key) => left[key] === right[key]);
}

/** Подпись у кнопки окна: чем настройки отличаются от умолчаний («JF · C(A) 1,15»). */
export function settingsCaption(settings: KuzRamSettings): string {
  const defaults = KUZRAM_DEFAULTS;
  const parts: string[] = [];
  if (settings.rock_factor_method === "rmd10") parts.push("RMD 10");
  if (settings.rock_factor_method === "joint_factor") parts.push("JF");
  if (settings.rock_factor_method === "manual") parts.push(`A ${trimmed(settings.rock_factor_manual)}`);
  if (settings.rock_factor_correction !== defaults.rock_factor_correction) {
    parts.push(`C(A) ${trimmed(settings.rock_factor_correction)}`);
  }
  if (settings.strength_exponent !== defaults.strength_exponent) parts.push(settings.strength_exponent);
  if (settings.drill_deviation_m !== defaults.drill_deviation_m) parts.push(`σ ${trimmed(settings.drill_deviation_m)} м`);
  if (settings.uniformity_correction !== defaults.uniformity_correction) {
    parts.push(`C(n) ${trimmed(settings.uniformity_correction)}`);
  }
  if (settings.q_max_kg_m3 !== defaults.q_max_kg_m3) parts.push(`q до ${trimmed(settings.q_max_kg_m3)}`);
  return parts.join(" · ");
}

/** Число из поля ввода: запятая или точка; пусто и мусор — `null`. */
export function parseDecimal(text: string): number | null {
  const normalized = text.trim().replace(",", ".");
  if (!normalized) return null;
  const value = Number(normalized);
  return Number.isFinite(value) ? value : null;
}

/** Ошибка числовой настройки или `null`; тексты — как у сервера. */
export function settingError(field: NumericSetting, value: number | null): string | null {
  if (value === null) return "Введите число.";
  const { min, max } = numericBounds(field);
  if (value < min || value > max) return `${NUMERIC_LABELS[field]} — от ${trimmed(min)} до ${trimmed(max)}.`;
  return null;
}

/** Границы ячейки факта — как ограничения pydantic: `ge`/`gt` снизу, `le`/`lt` сверху. */
type FactBounds = { ge?: number; gt?: number; le?: number; lt?: number };

/** Ошибка ячейки факта по границам `KuzRamFactSchema`; пустая ячейка — не ошибка. */
export function factCellError(field: FactField, value: number | null): string | null {
  if (value === null) return null;
  const bounds: FactBounds = contract.fact_bounds[field];
  const lowOk = bounds.ge !== undefined ? value >= bounds.ge : value > (bounds.gt ?? -Infinity);
  const highOk = bounds.le !== undefined ? value <= bounds.le : value < (bounds.lt ?? Infinity);
  if (lowOk && highOk) return null;
  const { label, unit } = FACT_LABELS[field];
  // Коронка: «от 20 до 1000 мм» — как в сообщении сервера (`CrownMm`).
  if (bounds.ge !== undefined && bounds.le !== undefined) {
    return `${label} — от ${trimmed(bounds.ge)} до ${trimmed(bounds.le)}${unit}.`;
  }
  const high = bounds.le !== undefined ? `не больше ${trimmed(bounds.le)}` : `меньше ${trimmed(bounds.lt ?? Infinity)}`;
  return `${label} — больше ${trimmed(bounds.gt ?? 0)} и ${high}${unit}.`;
}

/** Строки, пригодные для подбора C(A): все три значения заполнены и в границах. */
export function completeFacts(facts: KuzRamFact[]): { index: number; fact: KuzRamFactInput }[] {
  const complete: { index: number; fact: KuzRamFactInput }[] = [];
  facts.forEach((row, index) => {
    const { crown_mm, q_kg_m3, oversize_pct } = row;
    if (crown_mm === null || q_kg_m3 === null || oversize_pct === null) return;
    if (FACT_FIELDS.some((field) => factCellError(field, row[field]) !== null)) return;
    complete.push({ index, fact: { crown_mm, q_kg_m3, oversize_pct } });
  });
  return complete;
}
```

Run: `npm --prefix frontend test -- src/pages/calc/kuzram` и `frontend/node_modules/.bin/tsc -p frontend/tsconfig.app.json`
Expected: оба теста зелёные, типы без ошибок.

- [ ] **Шаг 7. Коммит**

```bash
git add frontend/src/pages/calc/kuzram/kuzramContract.json tests/test_kuzram_frontend_contract.py \
  frontend/src/pages/calc/kuzram/kuzramFormat.ts frontend/src/pages/calc/kuzram/kuzramFormat.test.ts \
  frontend/src/pages/calc/kuzram/kuzramSettings.ts frontend/src/pages/calc/kuzram/kuzramSettings.test.ts \
  frontend/src/types.ts
git commit -m "Kuz-Ram UI: контракт настроек и модуль блока kuzram

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 2. Типы ответа, вызовы API и блок `kuzram` в настройках листа

**Файлы:**
- Изменить: `frontend/src/types.ts` (тип `BlastVariant` и новые типы ответа)
- Изменить: `frontend/src/api/endpoints.ts` (`optimize`, новый `calibrateKuzram`)
- Создать: `frontend/src/api/endpoints.kuzram.test.ts`
- Изменить: `frontend/src/pages/calc/calcInputs.ts`, `frontend/src/pages/calc/calcInputs.test.ts`
- Создать: `frontend/src/pages/calc/kuzram/testing/optimizeGabbro.json`, `frontend/src/pages/calc/kuzram/testing/fixtures.ts`

**Интерфейсы:**
- Потребляет: `KuzRamSettings`, `KuzRamFactInput` (Task 1); `KuzRamBlock`, `defaultKuzramBlock`, `readKuzramBlock`, `copyKuzramBlock` (Task 1).
- Производит (`types.ts`): `RockFactorBreakdown`, `FragmentationDetails`, `LegacyBlastVariant`, поля `BlastVariant.reached`, `.details`, `.legacy`; `BlastOptimizeResponse`, `KuzRamCalibrationRow`, `KuzRamCalibrateResponse`.
- Производит (`endpoints.ts`): `api.optimize(input & { kuzram?: KuzRamSettings }): Promise<BlastOptimizeResponse>`, `api.calibrateKuzram(input & { kuzram: KuzRamSettings; facts: KuzRamFactInput[] }): Promise<KuzRamCalibrateResponse>`, где `input` — `{ rock, explosive, lumpSize, benchHeight, overdrill, oversizeCoeff, spacing }`.
- Производит (`calcInputs.ts`): поле `kuzram: KuzRamBlock` в `CalcInputs` и `SheetState`.
- Производит (`testing/fixtures.ts`): `OPTIMIZE_GABBRO: BlastOptimizeResponse`, `gabbroVariant(crownMm: 110 | 152 | 250, overrides?: Partial<BlastVariant>): BlastVariant`.

- [ ] **Шаг 1. Типы ответа в `frontend/src/types.ts`**

Заменить тип `BlastVariant` на:

```ts
/** Состав фактора породы A новой модели — как `RockFactorBreakdownSchema`. */
export type RockFactorBreakdown = {
  method: string;
  rmd: number | null;
  rdi: number | null;
  hf: number | null;
  joint_spacing_m: number | null;
  reduced_pattern_m: number | null;
  jps: number | null;
  base: number;
  correction: number;
  value: number;
};

/** Промежуточные величины расчёта коронки на подобранном q — как `FragmentationDetailsSchema`. */
export type FragmentationDetails = {
  q_kg_m3: number;
  hole_diameter_mm: number;
  charge_length_m: number;
  charge_mass_kg: number;
  volume_per_hole_m3: number;
  burden_m: number;
  spacing_m: number;
  burden_to_diameter: number;
  rock_factor_a: number;
  rock_factor: RockFactorBreakdown | null;
  re_weight: number;
  strength_exponent: string;
  x50_mm: number;
  uniformity_n_raw: number;
  uniformity_n: number;
  charge_to_bench: number | null;
  characteristic_size_mm: number;
  oversize_pct: number;
};

/** Расчёт «до исправления» — как `LegacyVariantSchema`. */
export type LegacyBlastVariant = {
  specific_q_kg_m3: number;
  line_of_least_resistance_m: number;
  grid_a_m: number;
  grid_b_m: number;
  grid_label: string;
  x50_mm: number;
  oversize_pct: number;
  reached: boolean;
  details: FragmentationDetails;
};

export type BlastVariant = {
  crown_mm: number;
  specific_q_kg_m3: number;
  line_of_least_resistance_m: number;
  grid_a_m: number;
  grid_b_m: number;
  grid_label: string;
  x50_mm: number;
  oversize_pct: number;
  target_q_kg_m3: number | null;
  /** Порог негабарита достигнут; иначе q — на верхней границе перебора. */
  reached: boolean;
  details: FragmentationDetails;
  legacy: LegacyBlastVariant;
};
```

После типов `KuzRamSettings` и `KuzRamFactInput` (Task 1) добавить:

```ts
/** Ответ `/blast/optimize`. */
export type BlastOptimizeResponse = {
  variants: BlastVariant[];
  max_oversize_threshold_pct: number;
  rock_name: string;
  explosive_name: string;
  model_version: string;
  /** Настройки, с которыми фактически посчитано. */
  kuzram: KuzRamSettings;
};

/** Строка ответа калибровки: прогнозы обеих моделей при фактическом q и C(A) строки. */
export type KuzRamCalibrationRow = {
  crown_mm: number;
  q_kg_m3: number;
  oversize_pct: number;
  legacy_oversize_pct: number;
  model_oversize_pct: number;
  rock_factor_correction: number | null;
  note: string | null;
};

/** Ответ `/blast/kuzram/calibrate`: C(A) — среднее геометрическое по решённым строкам. */
export type KuzRamCalibrateResponse = {
  rows: KuzRamCalibrationRow[];
  rock_factor_correction: number | null;
  used: number;
  skipped: number;
  model_version: string;
};
```

- [ ] **Шаг 2. Падающий тест вызовов API**

`frontend/src/api/endpoints.kuzram.test.ts`:

```ts
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { api } from "./endpoints";
import { KUZRAM_DEFAULTS } from "../pages/calc/kuzram/kuzramSettings";
import type { Explosive, Rock } from "../types";

const ROCK = { name: "Гранит", density_t_m3: 2.65, ucs_mpa: 150, fissuring_ff: 2 } as Rock;
const EXPLOSIVE = { key: "Э-100", name: "ЭВЕРСИН Э-100", density_t_m3: 1.12, power_mj_kg: 2.99 } as Explosive;
const SHEET = { rock: ROCK, explosive: EXPLOSIVE, lumpSize: 400, benchHeight: 10, overdrill: 1, oversizeCoeff: 1.05, spacing: 1.25 };
const TARGET = {
  lump_size_mm: 400,
  hole_diameter_mm: 0,
  overdrill_m: 1,
  hole_oversize_coeff: 1.05,
  spacing_coeff_m: 1.25,
  bench_height_m: 10,
};

const fetchMock = vi.fn();

beforeEach(() => {
  fetchMock.mockReset();
  fetchMock.mockImplementation(async () => new Response("{}", { status: 200, headers: { "Content-Type": "application/json" } }));
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => vi.unstubAllGlobals());

function lastRequest(): { path: string; body: Record<string, unknown> } {
  const [path, init] = fetchMock.mock.calls.at(-1) as [string, RequestInit];
  return { path, body: JSON.parse(String(init.body)) };
}

describe("api: подбор q и подбор C(A)", () => {
  it("optimize передаёт настройки модели; без них ключа kuzram нет", async () => {
    await api.optimize({ ...SHEET, threshold: 5, crownDiametersMm: [152], kuzram: KUZRAM_DEFAULTS });
    expect(lastRequest()).toEqual({
      path: "/api/v1/blast/optimize",
      body: {
        rock: ROCK,
        explosive: { name: "ЭВЕРСИН Э-100", density_t_m3: 1.12, power_mj_kg: 2.99 },
        target: TARGET,
        crown_diameters_mm: [152],
        max_oversize_threshold_pct: 5,
        kuzram: KUZRAM_DEFAULTS,
      },
    });
    await api.optimize({ ...SHEET, threshold: 5, crownDiametersMm: [152] });
    expect(lastRequest().body).not.toHaveProperty("kuzram");
  });

  it("calibrateKuzram шлёт породу, ВВ, уступ, настройки и факты", async () => {
    const facts = [{ crown_mm: 152, q_kg_m3: 1.3, oversize_pct: 8 }];
    await api.calibrateKuzram({ ...SHEET, kuzram: KUZRAM_DEFAULTS, facts });
    expect(lastRequest()).toEqual({
      path: "/api/v1/blast/kuzram/calibrate",
      body: {
        rock: ROCK,
        explosive: { name: "ЭВЕРСИН Э-100", density_t_m3: 1.12, power_mj_kg: 2.99 },
        target: TARGET,
        kuzram: KUZRAM_DEFAULTS,
        facts,
      },
    });
  });
});
```

Run: `npm --prefix frontend test -- src/api/endpoints.kuzram.test.ts`
Expected: FAIL — нет `calibrateKuzram`, у `optimize` нет `kuzram`.

- [ ] **Шаг 3. `endpoints.ts`**

В импорт типов из `../types` добавить `BlastOptimizeResponse`, `KuzRamCalibrateResponse`, `KuzRamFactInput`, `KuzRamSettings` (по алфавиту в списке). Перед `export const api = {` добавить:

```ts
/** Порода, ВВ и уступ листа — общая часть запросов подбора q и подбора C(A). */
type BlastSheetInput = {
  rock: Rock;
  explosive: Explosive;
  lumpSize: number;
  benchHeight: number;
  overdrill: number;
  oversizeCoeff: number;
  spacing: number;
};

function blastSheetPayload(input: BlastSheetInput) {
  return {
    rock: input.rock,
    explosive: {
      name: input.explosive.name,
      density_t_m3: input.explosive.density_t_m3,
      power_mj_kg: input.explosive.power_mj_kg,
    },
    target: {
      lump_size_mm: input.lumpSize,
      hole_diameter_mm: 0,
      overdrill_m: input.overdrill,
      hole_oversize_coeff: input.oversizeCoeff,
      spacing_coeff_m: input.spacing,
      bench_height_m: input.benchHeight,
    },
  };
}
```

Заменить `optimize: (input: {...}) => post<...>(...)` целиком на:

```ts
  optimize: (input: BlastSheetInput & { threshold: number; crownDiametersMm: number[]; kuzram?: KuzRamSettings }) =>
    post<BlastOptimizeResponse>(`${V1}/blast/optimize`, {
      ...blastSheetPayload(input),
      crown_diameters_mm: input.crownDiametersMm,
      max_oversize_threshold_pct: input.threshold,
      ...(input.kuzram ? { kuzram: input.kuzram } : {}),
    }),
  /** Подбор C(A) по фактическим взрывам: сервер только считает, ничего не сохраняет. */
  calibrateKuzram: (input: BlastSheetInput & { kuzram: KuzRamSettings; facts: KuzRamFactInput[] }) =>
    post<KuzRamCalibrateResponse>(`${V1}/blast/kuzram/calibrate`, {
      ...blastSheetPayload(input),
      kuzram: input.kuzram,
      facts: input.facts,
    }),
```

Если `BlastVariant` больше нигде в `endpoints.ts` не используется — убрать его из импорта.

Run: `npm --prefix frontend test -- src/api/endpoints.kuzram.test.ts`
Expected: 2 passed.

- [ ] **Шаг 4. Падающие тесты блока в настройках листа**

В `frontend/src/pages/calc/calcInputs.test.ts`:

1. В импорт добавить `import { defaultKuzramBlock, KUZRAM_DEFAULTS } from "./kuzram/kuzramSettings";`.
2. В хелпер `sheet()` перед `...overrides` добавить строку `kuzram: defaultKuzramBlock(),`.
3. В `describe("collectCalcInputs / applyCalcInputs", …)` добавить:

```ts
  it("блок kuzram записывается и читается обратно вместе с незаполненными строками фактов", () => {
    const original = sheet({
      kuzram: {
        ...KUZRAM_DEFAULTS,
        rock_factor_method: "joint_factor",
        rock_factor_correction: 1.15,
        facts: [
          { crown_mm: 152, q_kg_m3: 1.3, oversize_pct: 8 },
          { crown_mm: 165, q_kg_m3: null, oversize_pct: null },
        ],
      },
    });
    const saved = collectCalcInputs(original);
    expect(saved.kuzram).toEqual(original.kuzram);
    expect(applyCalcInputs(saved, CATALOGS)?.kuzram).toEqual(original.kuzram);
  });

  it("настройки без блока kuzram (до модели) открываются с умолчаниями модели", () => {
    const { kuzram: _omitted, ...legacy } = collectCalcInputs(sheet());
    expect(applyCalcInputs(legacy, CATALOGS)?.kuzram).toEqual(defaultKuzramBlock());
  });

  it("collectCalcInputs копирует строки фактов, а не делит их с листом", () => {
    const original = sheet({ kuzram: { ...KUZRAM_DEFAULTS, facts: [{ crown_mm: 152, q_kg_m3: 1.3, oversize_pct: 8 }] } });
    const saved = collectCalcInputs(original);
    saved.kuzram.facts[0].q_kg_m3 = 2;
    expect(original.kuzram.facts[0].q_kg_m3).toBe(1.3);
  });
```

Run: `npm --prefix frontend test -- src/pages/calc/calcInputs.test.ts`
Expected: FAIL — в `SheetState` и `CalcInputs` нет `kuzram`.

- [ ] **Шаг 5. `calcInputs.ts`**

1. Импорт вверху файла (после комментария модуля):

```ts
import { copyKuzramBlock, defaultKuzramBlock, readKuzramBlock, type KuzRamBlock } from "./kuzram/kuzramSettings";
```

2. В тип `CalcInputs` перед `panels` добавить:

```ts
  /** Модель Kuz-Ram: настройки подбора q и фактические взрывы. Поле появилось
   * позже версии 1; в старых настройках его нет — тогда умолчания модели. */
  kuzram: KuzRamBlock;
```

3. В тип `SheetState` перед `panels` добавить `kuzram: KuzRamBlock;`.
4. В `defaultCalcSheet` перед `panels:` добавить `kuzram: defaultKuzramBlock(),`.
5. В `collectCalcInputs` перед `panels:` добавить `kuzram: copyKuzramBlock(sheet.kuzram),`.
6. В `applyCalcInputs` перед `panels:` добавить `kuzram: readKuzramBlock(raw.kuzram),`.
7. В docstring `isOptimizationResultStale` в перечень полей «порода, ВВ, … выбранные коронки» дописать «, настройки модели Kuz-Ram».

Run: `npm --prefix frontend test -- src/pages/calc/calcInputs.test.ts` и `frontend/node_modules/.bin/tsc -p frontend/tsconfig.app.json`
Expected: тесты зелёные. `tsc` может указать на `CalcPage.tsx` (объект `sheet` без `kuzram`) — это чинится в Task 4; сейчас временно добавьте в `useMemo` листа в `CalcPage.tsx` строку `kuzram: defaultKuzramBlock(),` с импортом `defaultKuzramBlock` из `./calc/kuzram/kuzramSettings`, чтобы ветка собиралась (Task 4 заменит её на состояние).

- [ ] **Шаг 6. Фикстура ответа сервера для тестов окна**

Временный генератор `<scratchpad>/gen_optimize_fixture.py` (`<scratchpad>` — временная папка сессии из системного промпта; файл не коммитится):

```python
"""Фикстура ответа /blast/optimize для тестов окна Kuz-Ram."""
import json
import sys

from api.schemas.blast import BlastOptimizeRequest
from api.services.blast_service import optimize_blast

request = BlastOptimizeRequest(
    rock={"name": "Габбро-диабаз", "density_t_m3": 2.9, "ucs_mpa": 168, "fissuring_ff": 2.2},
    explosive={"name": "ЭВЕРСИН Э-100", "density_t_m3": 1.12, "power_mj_kg": 2.99},
    target={
        "lump_size_mm": 400,
        "overdrill_m": 1.0,
        "hole_oversize_coeff": 1.05,
        "spacing_coeff_m": 1.25,
        "bench_height_m": 10.0,
    },
    crown_diameters_mm=[110, 152, 250],
    max_oversize_threshold_pct=5,
    kuzram={"q_max_kg_m3": 1.5},
)


def rounded(value):
    if isinstance(value, float):
        return round(value, 4)
    if isinstance(value, dict):
        return {key: rounded(item) for key, item in value.items()}
    if isinstance(value, list):
        return [rounded(item) for item in value]
    return value


json.dump(rounded(optimize_blast(request).model_dump()), sys.stdout, ensure_ascii=False, indent=2)
sys.stdout.write("\n")
```

Run: `mkdir -p frontend/src/pages/calc/kuzram/testing && PYTHONPATH=. ../../../.venv/bin/python <scratchpad>/gen_optimize_fixture.py > frontend/src/pages/calc/kuzram/testing/optimizeGabbro.json`
Expected: JSON ~7 КБ; у коронки 152 мм `specific_q_kg_m3` 1.26, `grid_label` "4.42 × 3.54"; у 250 мм `reached` false, q 1.5, `oversize_pct` 5.4; `legacy` у 250 мм — q 1.5, негабарит 5.96, `reached` false.

`frontend/src/pages/calc/kuzram/testing/fixtures.ts`:

```ts
import type { BlastOptimizeResponse, BlastVariant } from "../../../../types";
import response from "./optimizeGabbro.json";

/**
 * Ответ `/blast/optimize` сервера PR 1 для тестов окна Kuz-Ram: габбро-диабаз,
 * ЭВЕРСИН Э-100, кусок 400 мм, порог 5 %, коронки 110, 152 и 250 мм, верхняя
 * граница q 1,5 — у коронки 250 мм порог не достигнут обеими моделями.
 */
export const OPTIMIZE_GABBRO = response as unknown as BlastOptimizeResponse;

/** Вариант коронки из фикстуры — глубокая копия, её можно менять в тесте. */
export function gabbroVariant(crownMm: 110 | 152 | 250, overrides: Partial<BlastVariant> = {}): BlastVariant {
  const found = OPTIMIZE_GABBRO.variants.find((variant) => variant.crown_mm === crownMm);
  if (!found) throw new Error(`В фикстуре нет коронки ${crownMm} мм`);
  return { ...(JSON.parse(JSON.stringify(found)) as BlastVariant), ...overrides };
}
```

Run: `frontend/node_modules/.bin/tsc -p frontend/tsconfig.app.json` и `npm --prefix frontend test`
Expected: без ошибок типов; все тесты фронта зелёные.

- [ ] **Шаг 7. Коммит**

```bash
git add frontend/src/types.ts frontend/src/api/endpoints.ts frontend/src/api/endpoints.kuzram.test.ts \
  frontend/src/pages/calc/calcInputs.ts frontend/src/pages/calc/calcInputs.test.ts \
  frontend/src/pages/calc/kuzram/testing/optimizeGabbro.json frontend/src/pages/calc/kuzram/testing/fixtures.ts \
  frontend/src/pages/CalcPage.tsx
git commit -m "Kuz-Ram UI: типы ответа, вызовы API и блок kuzram в настройках листа

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 3. Окно модели и форма настроек

Каркас окна: заголовок, «Закрыть», слева — настройки и строка исходных данных, справа — статус пересчёта и ошибка. Результаты добавят Task 5–7, вкладку справки — Task 8.

**Файлы:**
- Создать: `frontend/src/pages/calc/kuzram/KuzRamSettingsForm.tsx`, `KuzRamSettingsForm.test.tsx`
- Создать: `frontend/src/pages/calc/kuzram/KuzRamDialog.tsx`, `KuzRamDialog.test.tsx`
- Создать: `frontend/src/styles/kuzram.css`
- Изменить: `frontend/src/main.tsx` (импорт стилей)

**Интерфейсы:**
- Потребляет: `KuzRamBlock`, `KUZRAM_DEFAULTS`, `ROCK_FACTOR_METHODS`, `STRENGTH_EXPONENTS`, `parseDecimal`, `settingError`, `sameSettings`, `NumericSetting` (Task 1); `trimmed` (Task 1).
- Производит: `KuzRamSettingsForm({ settings: KuzRamSettings; onChange(next: KuzRamSettings) })`; `KuzRamDialog(props: KuzRamDialogProps)`, тип `KuzRamSource = { rockName; explosiveName; benchHeightM; overdrillM; lumpSizeMm; thresholdPct }`, тип `KuzRamDialogProps = { open; onClose; block: KuzRamBlock; onSettingsChange(next: KuzRamSettings); source: KuzRamSource; busy: boolean; error: string }`.

- [ ] **Шаг 1. Падающие тесты формы**

`frontend/src/pages/calc/kuzram/KuzRamSettingsForm.test.tsx`:

```tsx
// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { KuzRamSettings } from "../../../types";
import { KuzRamSettingsForm } from "./KuzRamSettingsForm";
import { KUZRAM_DEFAULTS } from "./kuzramSettings";

afterEach(cleanup);

/** Форма с настоящим состоянием: как в окне, правка сразу возвращается в поля. */
function renderForm(initial: KuzRamSettings = KUZRAM_DEFAULTS) {
  const onChange = vi.fn();
  function Harness() {
    const [settings, setSettings] = useState(initial);
    return (
      <KuzRamSettingsForm
        settings={settings}
        onChange={(next) => {
          onChange(next);
          setSettings(next);
        }}
      />
    );
  }
  render(<Harness />);
  return onChange;
}

describe("KuzRamSettingsForm", () => {
  it("JCF и JPA — только при способе JF, A вручную — только при ручном вводе", () => {
    renderForm();
    expect(screen.queryByLabelText("Состояние трещин JCF")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("A вручную")).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Фактор породы A"), { target: { value: "joint_factor" } });
    expect(screen.getByLabelText("Состояние трещин JCF")).toHaveDisplayValue("плотные — 1");
    expect(screen.getByLabelText("Ориентация трещин JPA")).toHaveDisplayValue("падение в сторону откоса — 20");
    fireEvent.change(screen.getByLabelText("Фактор породы A"), { target: { value: "manual" } });
    expect(screen.queryByLabelText("Состояние трещин JCF")).not.toBeInTheDocument();
    expect(screen.getByLabelText("A вручную")).toHaveValue("6");
  });

  it("верное значение сразу уходит в настройки, запятая допустима", () => {
    const onChange = renderForm();
    fireEvent.change(screen.getByLabelText("Поправка C(A)"), { target: { value: "1,15" } });
    expect(onChange).toHaveBeenLastCalledWith({ ...KUZRAM_DEFAULTS, rock_factor_correction: 1.15 });
  });

  it("неверное значение подсвечивается и в расчёт не идёт", () => {
    const onChange = renderForm();
    const input = screen.getByLabelText("Поправка C(A)");
    fireEvent.change(input, { target: { value: "20" } });
    expect(onChange).not.toHaveBeenCalled();
    expect(input).toHaveAttribute("aria-invalid", "true");
    expect(input).toHaveAccessibleDescription(/Поправка C\(A\) — от 0,1 до 10\./);
    fireEvent.change(input, { target: { value: "" } });
    expect(screen.getByText("Введите число.")).toBeInTheDocument();
    expect(onChange).not.toHaveBeenCalled();
  });

  it("значение, пришедшее снаружи (подбор C(A)), показывается в поле", () => {
    const { rerender } = render(<KuzRamSettingsForm settings={KUZRAM_DEFAULTS} onChange={() => {}} />);
    rerender(<KuzRamSettingsForm settings={{ ...KUZRAM_DEFAULTS, rock_factor_correction: 1.127 }} onChange={() => {}} />);
    expect(screen.getByLabelText("Поправка C(A)")).toHaveValue("1,127");
  });

  it("«Сбросить к умолчаниям» возвращает умолчания и выключена на них", () => {
    const onChange = renderForm({ ...KUZRAM_DEFAULTS, rock_factor_method: "rmd10", q_max_kg_m3: 3 });
    fireEvent.click(screen.getByRole("button", { name: "Сбросить к умолчаниям" }));
    expect(onChange).toHaveBeenLastCalledWith(KUZRAM_DEFAULTS);
    expect(screen.getByRole("button", { name: "Сбросить к умолчаниям" })).toBeDisabled();
    expect(screen.getByLabelText("Верхняя граница перебора q, кг/м³")).toHaveValue("2");
  });
});
```

Run: `npm --prefix frontend test -- src/pages/calc/kuzram/KuzRamSettingsForm.test.tsx`
Expected: FAIL — компонента нет.

- [ ] **Шаг 2. `KuzRamSettingsForm.tsx`**

```tsx
import { useEffect, useId, useState } from "react";
import type { KuzRamSettings, RockFactorMethod, StrengthExponent } from "../../../types";
import { trimmed } from "./kuzramFormat";
import { KUZRAM_DEFAULTS, parseDecimal, sameSettings, settingError, type NumericSetting } from "./kuzramSettings";

type Option<T> = { value: T; label: string };

const METHOD_OPTIONS: Option<RockFactorMethod>[] = [
  { value: "rmd50", label: "Монолитный массив (RMD 50)" },
  { value: "rmd10", label: "Раздробленная порода (RMD 10)" },
  { value: "joint_factor", label: "По трещиноватости (JF)" },
  { value: "manual", label: "Задать вручную" },
];

const JOINT_CONDITION_OPTIONS: Option<number>[] = [
  { value: 1, label: "плотные — 1" },
  { value: 1.5, label: "раскрытые — 1,5" },
  { value: 2, label: "с заполнителем — 2" },
];

// Каннингем 2005, §4.1.1.3: «dip out of face» (40) — плоскость трещины,
// продолженная из откоса, уходит вверх, то есть трещины падают в массив.
// Формулировки — на подтверждение технологу (решение владельца 21.09.2026).
const JOINT_ANGLE_OPTIONS: Option<number>[] = [
  { value: 20, label: "падение в сторону откоса — 20" },
  { value: 30, label: "простирание поперёк откоса — 30" },
  { value: 40, label: "падение в массив — 40" },
];

const EXPONENT_OPTIONS: Option<StrengthExponent>[] = [
  { value: "19/20", label: "19/20 — Каннингем, 1987" },
  { value: "19/30", label: "19/30 — как до исправления (1983)" },
];

function SelectField<T extends string | number>({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: T;
  options: Option<T>[];
  onChange: (value: T) => void;
}) {
  const id = useId();
  return (
    <div className="kuzram-field">
      <label htmlFor={id}>{label}</label>
      <select
        id={id}
        value={String(value)}
        onChange={(event) => {
          const picked = options.find((option) => String(option.value) === event.target.value);
          if (picked) onChange(picked.value);
        }}
      >
        {options.map((option) => (
          <option key={String(option.value)} value={String(option.value)}>
            {option.label}
          </option>
        ))}
      </select>
    </div>
  );
}

/**
 * Числовая настройка. Поле хранит набранный текст: верное значение сразу уходит
 * в настройки, неверное подсвечивается и в расчёт не идёт — там остаётся
 * последнее верное.
 */
function NumberSetting({
  field,
  label,
  hint,
  value,
  onCommit,
}: {
  field: NumericSetting;
  label: string;
  hint: string;
  value: number;
  onCommit: (value: number) => void;
}) {
  const id = useId();
  const [draft, setDraft] = useState(() => trimmed(value, 6));
  // Значение сменилось снаружи (сброс, подбор C(A)) — показываем его; свой
  // незаконченный ввод («1,» при значении 1) не трогаем.
  useEffect(() => {
    setDraft((current) => (parseDecimal(current) === value ? current : trimmed(value, 6)));
  }, [value]);
  const error = settingError(field, parseDecimal(draft));
  const describedBy = [`${id}-hint`, error ? `${id}-error` : ""].filter(Boolean).join(" ");

  function change(text: string) {
    setDraft(text);
    const parsed = parseDecimal(text);
    if (parsed !== null && settingError(field, parsed) === null && parsed !== value) onCommit(parsed);
  }

  return (
    <div className="kuzram-field">
      <label htmlFor={id}>{label}</label>
      <small id={`${id}-hint`}>{hint}</small>
      <input
        id={id}
        type="text"
        inputMode="decimal"
        autoComplete="off"
        value={draft}
        aria-invalid={error ? true : undefined}
        aria-describedby={describedBy}
        onChange={(event) => change(event.target.value)}
      />
      {error && (
        <small id={`${id}-error`} className="kuzram-field-error">
          {error}
        </small>
      )}
    </div>
  );
}

/** Настройки модели Kuz-Ram. Поля JCF и JPA — только при способе JF, A — только при ручном вводе. */
export function KuzRamSettingsForm({
  settings,
  onChange,
}: {
  settings: KuzRamSettings;
  onChange: (next: KuzRamSettings) => void;
}) {
  function set<K extends keyof KuzRamSettings>(key: K, value: KuzRamSettings[K]) {
    onChange({ ...settings, [key]: value });
  }
  const method = settings.rock_factor_method;

  return (
    <fieldset className="kuzram-settings">
      <legend>Настройки модели</legend>
      <SelectField label="Фактор породы A" value={method} options={METHOD_OPTIONS} onChange={(value) => set("rock_factor_method", value)} />
      {method === "manual" && (
        <NumberSetting
          field="rock_factor_manual"
          label="A вручную"
          hint="из опыта или отчёта, от 0,5 до 30"
          value={settings.rock_factor_manual}
          onCommit={(value) => set("rock_factor_manual", value)}
        />
      )}
      {method === "joint_factor" && (
        <>
          <SelectField
            label="Состояние трещин JCF"
            value={settings.joint_condition}
            options={JOINT_CONDITION_OPTIONS}
            onChange={(value) => set("joint_condition", value)}
          />
          <SelectField
            label="Ориентация трещин JPA"
            value={settings.joint_angle}
            options={JOINT_ANGLE_OPTIONS}
            onChange={(value) => set("joint_angle", value)}
          />
        </>
      )}
      <NumberSetting
        field="rock_factor_correction"
        label="Поправка C(A)"
        hint="1 — без поправки; подбирается по фактическим взрывам"
        value={settings.rock_factor_correction}
        onCommit={(value) => set("rock_factor_correction", value)}
      />
      <SelectField
        label="Показатель при силе ВВ"
        value={settings.strength_exponent}
        options={EXPONENT_OPTIONS}
        onChange={(value) => set("strength_exponent", value)}
      />
      <NumberSetting
        field="drill_deviation_m"
        label="Отклонение бурения σ, м"
        hint="стандартное отклонение забоя скважины от проекта"
        value={settings.drill_deviation_m}
        onCommit={(value) => set("drill_deviation_m", value)}
      />
      <NumberSetting
        field="uniformity_correction"
        label="Поправка C(n)"
        hint="множитель к индексу равномерности n"
        value={settings.uniformity_correction}
        onCommit={(value) => set("uniformity_correction", value)}
      />
      <NumberSetting
        field="q_max_kg_m3"
        label="Верхняя граница перебора q, кг/м³"
        hint="перебор идёт от 0,10 с шагом 0,01"
        value={settings.q_max_kg_m3}
        onCommit={(value) => set("q_max_kg_m3", value)}
      />
      <button
        type="button"
        className="secondary-button"
        disabled={sameSettings(settings, KUZRAM_DEFAULTS)}
        onClick={() => onChange({ ...KUZRAM_DEFAULTS })}
      >
        Сбросить к умолчаниям
      </button>
    </fieldset>
  );
}
```

Run: `npm --prefix frontend test -- src/pages/calc/kuzram/KuzRamSettingsForm.test.tsx`
Expected: 5 passed.

- [ ] **Шаг 3. Падающие тесты окна**

`frontend/src/pages/calc/kuzram/KuzRamDialog.test.tsx`:

```tsx
// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { KuzRamDialog, type KuzRamDialogProps } from "./KuzRamDialog";
import { defaultKuzramBlock } from "./kuzramSettings";

afterEach(cleanup);

beforeAll(() => {
  // jsdom не реализует модальный `dialog`.
  HTMLDialogElement.prototype.showModal = vi.fn(function (this: HTMLDialogElement) {
    this.open = true;
  });
  HTMLDialogElement.prototype.close = vi.fn(function (this: HTMLDialogElement) {
    this.open = false;
  });
});

const SOURCE = {
  rockName: "Габбро-диабаз",
  explosiveName: "ЭВЕРСИН Э-100",
  benchHeightM: 10,
  overdrillM: 1,
  lumpSizeMm: 400,
  thresholdPct: 5,
};

function renderDialog(overrides: Partial<KuzRamDialogProps> = {}) {
  const props: KuzRamDialogProps = {
    open: true,
    onClose: vi.fn(),
    block: defaultKuzramBlock(),
    onSettingsChange: vi.fn(),
    source: SOURCE,
    busy: false,
    error: "",
    ...overrides,
  };
  render(<KuzRamDialog {...props} />);
  return props;
}

describe("KuzRamDialog", () => {
  it("открывается модально и закрывается кнопкой", () => {
    const props = renderDialog();
    expect(HTMLDialogElement.prototype.showModal).toHaveBeenCalled();
    expect(screen.getByRole("dialog", { name: "Модель Kuz-Ram" })).toHaveAttribute("open");
    fireEvent.click(screen.getByRole("button", { name: "Закрыть" }));
    expect(props.onClose).toHaveBeenCalled();
  });

  it("закрытое окно не рисует содержимое", () => {
    renderDialog({ open: false });
    expect(screen.queryByLabelText("Поправка C(A)")).not.toBeInTheDocument();
  });

  it("исходные данные — строкой с листа", () => {
    renderDialog();
    expect(
      screen.getByText(/Габбро-диабаз · ЭВЕРСИН Э-100 · уступ 10 м, перебур 1 м · кусок 400 мм · допустимый негабарит 5 %/),
    ).toBeInTheDocument();
  });

  it("правка настроек уходит листу", () => {
    const props = renderDialog();
    fireEvent.change(screen.getByLabelText("Поправка C(A)"), { target: { value: "1,2" } });
    expect(props.onSettingsChange).toHaveBeenCalledWith(expect.objectContaining({ rock_factor_correction: 1.2 }));
  });

  it("пока идёт пересчёт — «Пересчёт…», ошибка расчёта видна в окне", () => {
    renderDialog({ busy: true, error: "Фактор породы A = −0,5 — он должен быть больше нуля." });
    const dialog = screen.getByRole("dialog", { name: "Модель Kuz-Ram" });
    expect(within(dialog).getByRole("status")).toHaveTextContent("Пересчёт…");
    expect(within(dialog).getByRole("alert")).toHaveTextContent("Фактор породы A = −0,5");
  });
});
```

Run: `npm --prefix frontend test -- src/pages/calc/kuzram/KuzRamDialog.test.tsx`
Expected: FAIL — компонента нет.

- [ ] **Шаг 4. `KuzRamDialog.tsx`**

```tsx
import { useEffect, useRef, type MouseEvent } from "react";
import type { KuzRamSettings } from "../../../types";
import { KuzRamSettingsForm } from "./KuzRamSettingsForm";
import { trimmed } from "./kuzramFormat";
import type { KuzRamBlock } from "./kuzramSettings";

/** Исходные данные листа — в окне только строкой, правятся на листе. */
export type KuzRamSource = {
  rockName: string;
  explosiveName: string;
  benchHeightM: number;
  overdrillM: number;
  lumpSizeMm: number;
  thresholdPct: number;
};

export type KuzRamDialogProps = {
  open: boolean;
  onClose: () => void;
  /** Блок модели объекта: настройки и фактические взрывы. */
  block: KuzRamBlock;
  /** Правка настроек: лист сохраняет их и пересчитывает варианты. */
  onSettingsChange: (next: KuzRamSettings) => void;
  source: KuzRamSource;
  /** Идёт подбор q (или пауза перед ним после правки) — прежние цифры приглушены. */
  busy: boolean;
  /** Ошибка последнего подбора — та же, что на листе. */
  error: string;
};

/**
 * Окно «Модель Kuz-Ram» листа «Расчёт». Нативный `dialog` с `showModal()`,
 * как у `CalcHelp`: Esc и щелчок по подложке закрывают окно. Всё считает
 * сервер: окно показывает ответ `/blast/optimize` и отдаёт правки листу.
 * Содержимое рисуется только у открытого окна — при каждом открытии поля
 * заново берут сохранённые значения.
 */
export function KuzRamDialog(props: KuzRamDialogProps) {
  const { open, onClose } = props;
  const ref = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    if (open && !dialog.open) dialog.showModal();
    if (!open && dialog.open) dialog.close();
  }, [open]);

  // Щелчок по подложке приходит в сам `dialog`, по содержимому — во вложенные элементы.
  function onBackdropClick(event: MouseEvent<HTMLDialogElement>) {
    if (event.target === ref.current) onClose();
  }

  return (
    <dialog
      ref={ref}
      className="kuzram-dialog"
      aria-labelledby="kuzram-dialog-title"
      onClose={onClose}
      onClick={onBackdropClick}
    >
      <header>
        <b id="kuzram-dialog-title">Модель Kuz-Ram</b>
        <button type="button" className="kuzram-close" aria-label="Закрыть" onClick={onClose}>
          ×
        </button>
      </header>
      {open && <CalcTab {...props} />}
    </dialog>
  );
}

function CalcTab({ block, onSettingsChange, source, busy, error }: KuzRamDialogProps) {
  return (
    <div className="kuzram-body kuzram-calc">
      <aside className="kuzram-side">
        <KuzRamSettingsForm settings={block} onChange={onSettingsChange} />
        <p className="kuzram-source">
          <b>С листа:</b> {source.rockName} · {source.explosiveName} · уступ {trimmed(source.benchHeightM)} м, перебур{" "}
          {trimmed(source.overdrillM)} м · кусок {trimmed(source.lumpSizeMm)} мм · допустимый негабарит{" "}
          {trimmed(source.thresholdPct)} %. Исходные данные меняются на листе.
        </p>
      </aside>
      <div className={`kuzram-results${busy ? " is-pending" : ""}`} aria-busy={busy}>
        <p className="kuzram-status" role="status">
          {busy ? "Пересчёт…" : ""}
        </p>
        {error && (
          <div className="page-error" role="alert">
            {error}
          </div>
        )}
      </div>
    </div>
  );
}
```

Run: `npm --prefix frontend test -- src/pages/calc/kuzram/KuzRamDialog.test.tsx`
Expected: 5 passed. Если регулярка строки исходных данных не совпала из-за переносов JSX, проверьте, что соседние выражения разделены ровно одним пробелом (`{" "}` там, где строка переносится).

- [ ] **Шаг 5. Стили**

`frontend/src/styles/kuzram.css`:

```css
/* Окно «Модель Kuz-Ram» листа «Расчёт» (pages/calc/kuzram): рамка и подложка —
   как у справки листа, но окно шире и делится на настройки и результаты. */
.kuzram-dialog { width:min(1180px,calc(100vw - 32px)); max-width:none; max-height:90vh; padding:0; border:1px solid #d9e2dd; border-radius:16px; color:#17231d; box-shadow:0 30px 80px rgba(15,35,26,.18); }
.kuzram-dialog[open] { display:flex; flex-direction:column; }
.kuzram-dialog::backdrop { background:rgba(15,26,20,.45); }
.kuzram-dialog > header { display:flex; flex-wrap:wrap; align-items:center; gap:10px 16px; padding:12px 16px; border-bottom:1px solid #e2e8e5; background:#fff; }
.kuzram-dialog > header b { font-size:15px; }
.kuzram-close { width:28px; height:28px; margin-left:auto; border:0; border-radius:8px; background:transparent; color:#6e7c75; font-size:16px; line-height:1; }
.kuzram-close:hover { background:#f0f4f2; }
.kuzram-body { flex:1 1 auto; min-height:0; overflow:auto; padding:14px 16px 18px; font-size:12px; line-height:1.5; }
.kuzram-calc { display:grid; grid-template-columns:280px minmax(0,1fr); gap:16px; align-items:start; }
.kuzram-side { position:sticky; top:0; display:grid; gap:12px; }
.kuzram-settings { display:grid; gap:9px; min-width:0; margin:0; padding:0; border:0; }
.kuzram-settings legend { margin-bottom:6px; padding:0; color:#7b8982; font-size:9.5px; letter-spacing:.3px; text-transform:uppercase; }
.kuzram-settings .secondary-button { justify-self:start; }
.kuzram-field { display:grid; gap:3px; }
.kuzram-field label { font-size:var(--fs-label); }
.kuzram-field > small { color:#7b8982; font-size:var(--fs-small); }
.kuzram-field input, .kuzram-field select { height:var(--control-h); min-width:0; padding:0 8px; border:1px solid #ced9d3; border-radius:var(--radius-control); background:#fff; color:#17231d; font-size:12px; }
.kuzram-field input { text-align:right; font-variant-numeric:tabular-nums; }
.kuzram-field input[aria-invalid="true"], .kuzram-facts input[aria-invalid="true"] { border-color:#c0564b; background:#fff8f7; }
.kuzram-field-error { display:block; color:#9e3025; font-size:var(--fs-small); }
.kuzram-source { margin:0; padding:10px 12px; border-radius:10px; background:#f3f6f4; color:#3b4b43; font-size:11px; }
.kuzram-results { display:grid; gap:14px; min-width:0; }
.kuzram-results.is-pending > :not(.kuzram-status) { opacity:.55; transition:opacity .15s; }
.kuzram-status { margin:0; color:#2d7556; font-size:11px; font-weight:var(--font-weight-strong); }
.kuzram-status:empty { display:none; }
@media (max-width:760px) {
  .kuzram-dialog { width:calc(100vw - 16px); max-height:calc(100vh - 16px); border-radius:12px; }
  .kuzram-calc { grid-template-columns:minmax(0,1fr); }
  .kuzram-side { position:static; }
}
```

В `frontend/src/main.tsx` после `import "./styles/economics.css";` добавить `import "./styles/kuzram.css";`.

Run: `frontend/node_modules/.bin/tsc -p frontend/tsconfig.app.json` и `npm --prefix frontend test -- src/pages/calc/kuzram`
Expected: без ошибок.

- [ ] **Шаг 6. Коммит**

```bash
git add frontend/src/pages/calc/kuzram/KuzRamSettingsForm.tsx frontend/src/pages/calc/kuzram/KuzRamSettingsForm.test.tsx \
  frontend/src/pages/calc/kuzram/KuzRamDialog.tsx frontend/src/pages/calc/kuzram/KuzRamDialog.test.tsx \
  frontend/src/styles/kuzram.css frontend/src/main.tsx
git commit -m "Kuz-Ram UI: окно модели и форма настроек

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 4. Лист: кнопка окна, подпись, пересчёт по настройкам и значок «!»

**Файлы:**
- Создать: `frontend/src/pages/calc/kuzram/ThresholdFlag.tsx`
- Изменить: `frontend/src/pages/CalcPage.tsx`
- Создать: `frontend/src/pages/CalcPage.kuzram.test.tsx`
- Изменить: `frontend/src/styles/kuzram.css`

**Интерфейсы:**
- Потребляет: `KuzRamDialog`, `KuzRamSource` (Task 3); `defaultKuzramBlock`, `kuzramSettingsOf`, `settingsCaption`, `KuzRamBlock` (Task 1); `formatQ`, `formatOversize` (Task 1); `api.optimize` с `kuzram` (Task 2); `OPTIMIZE_GABBRO`, `gabbroVariant` (Task 2).
- Производит: `ThresholdFlag({ title?: string })` — `<span role="img" aria-label="Порог негабарита не достигнут">!</span>`; в `CalcPage` — состояние `kuzram: KuzRamBlock`, `setKuzramSettings(next: KuzRamSettings)`, `variantsThresholdPct`, `KUZRAM_RECALC_DELAY_MS = 300`.

- [ ] **Шаг 1. Падающие тесты листа**

`frontend/src/pages/CalcPage.kuzram.test.tsx`:

```tsx
// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { WorkspaceContext } from "../app/useWorkspace";
import { CalcPage } from "./CalcPage";
import { KUZRAM_DEFAULTS, type KuzRamBlock } from "./calc/kuzram/kuzramSettings";
import { gabbroVariant, OPTIMIZE_GABBRO } from "./calc/kuzram/testing/fixtures";

/**
 * Модель Kuz-Ram на листе «Расчёт»: кнопка окна и подпись настроек, пересчёт
 * по правке настроек (без фактов в запросе), автосохранение блока `kuzram`,
 * значок «!» в таблице вариантов.
 */

const api = vi.hoisted(() => ({
  rocks: vi.fn(),
  explosives: vi.fn(),
  blastOptions: vi.fn(),
  productionUnits: vi.fn(),
  calcInputs: vi.fn(),
  saveCalcInputs: vi.fn(),
  optimize: vi.fn(),
  calibrateKuzram: vi.fn(),
  geometry: vi.fn(),
  economics: { referenceSnapshot: vi.fn(), technicalPassports: vi.fn() },
}));
vi.mock("../api/endpoints", () => ({ api }));

const OBJECT = { name: "Карьер Анна", mobilization_km: 1, diesel_price_ton_rub: null, production_unit_code: "UNIT_PERM" };
const PANEL = {
  explosive_key: "ПВВ Гранулит-РП",
  undercharge_m: 2,
  intermediate_detonators_per_hole: 1,
  nsi_per_hole: 1,
  nsi_length_1_m: 12,
  nsi_length_2_m: 6,
  detonator_delay_ms: 500,
};

function savedInputs(kuzram?: KuzRamBlock) {
  return {
    version: 1,
    rock_name: "Гранит",
    explosive_key: "ПВВ Гранулит-РП",
    lump_size_mm: 400,
    bench_height_m: 10,
    overdrill_m: 1,
    oversize_coeff: 1.05,
    spacing_coeff: 1.25,
    oversize_threshold_pct: 5,
    selected_crowns_mm: [110, 152, 250],
    selected_crown_mm: 152,
    block_volume_m3: 30000,
    additional_holes_pct: 3,
    production_unit_code: "UNIT_PERM",
    panels: { left: PANEL, right: PANEL },
    ...(kuzram ? { kuzram } : {}),
  };
}

function Workspace({ children }: { children: ReactNode }) {
  const value = {
    loading: false,
    error: "",
    state: {
      settings: { team_id: "t", team_name: "Команда", active_scenario_id: "drill_blast", active_work_object_name: OBJECT.name },
      references: { work_object_records: [OBJECT] },
      warnings: [],
    } as never,
    scenarios: [],
    activeScenario: null,
    dirty: false,
    saving: false,
    blastContext: null,
    setBlastContext: () => {},
    updateSnapshot: () => {},
    setActiveWorkObjectName: async () => {},
    save: async () => {},
    reload: async () => {},
    canEdit: true,
  };
  return <WorkspaceContext.Provider value={value}>{children}</WorkspaceContext.Provider>;
}

const renderSheet = () =>
  render(
    <Workspace>
      <CalcPage />
    </Workspace>,
  );

// Под нагрузкой полного прогона лист грузится дольше секунды по умолчанию.
const SLOW = { timeout: 3000 };
/** Дождаться, пока отложенная запись автосохранения (800 мс) точно успела бы уйти. */
const autosaveWindow = () => act(() => new Promise((resolve) => setTimeout(resolve, 1100)));

async function loaded() {
  await waitFor(() => expect(screen.getByRole("button", { name: "Рассчитать варианты" })).toBeEnabled(), SLOW);
  await waitFor(() => expect(api.optimize).toHaveBeenCalledTimes(1), SLOW);
}

const lastSaved = () => api.saveCalcInputs.mock.calls.at(-1)?.[1] as { kuzram: KuzRamBlock } | undefined;
const dialog = () => screen.getByRole("dialog", { name: "Модель Kuz-Ram" });

beforeAll(() => {
  // jsdom не реализует модальный `dialog`.
  HTMLDialogElement.prototype.showModal = vi.fn(function (this: HTMLDialogElement) {
    this.open = true;
  });
  HTMLDialogElement.prototype.close = vi.fn(function (this: HTMLDialogElement) {
    this.open = false;
  });
});

beforeEach(() => {
  vi.clearAllMocks();
  api.rocks.mockResolvedValue({ items: [{ name: "Гранит", density_t_m3: 2.65, ucs_mpa: 150, fissuring_ff: 2 }], default_name: "Гранит" });
  api.explosives.mockResolvedValue({
    items: [{ key: "ПВВ Гранулит-РП", name: "Гранулит-РП", density_t_m3: 0.9, power_mj_kg: 3.8, chart_label: "ГРАНУЛИТ-РП" }],
    default_key: "ПВВ Гранулит-РП",
  });
  api.blastOptions.mockResolvedValue({ crown_diameters_mm: [110, 152, 250], nsi_length_options_m: [6, 12], detonator_delay_ms_options: [500] });
  api.productionUnits.mockResolvedValue({ items: [{ code: "UNIT_PERM", name: "Юнит Пермь" }] });
  api.calcInputs.mockResolvedValue({ work_object_name: OBJECT.name, inputs: savedInputs(), updated_at: "then" });
  api.optimize.mockResolvedValue(OPTIMIZE_GABBRO);
  // Схемы заряда здесь не проверяются: запрос висит, карточки — в загрузке.
  api.geometry.mockReturnValue(new Promise(() => {}));
  api.economics.referenceSnapshot.mockResolvedValue({ revision_id: "REV", sections: { sites: [] } });
  api.economics.technicalPassports.mockResolvedValue([]);
  api.saveCalcInputs.mockImplementation(async (name: string, inputs: object) => ({ work_object_name: name, inputs, updated_at: "now" }));
});
afterEach(cleanup);

describe("CalcPage: модель Kuz-Ram", () => {
  it("настройки без блока kuzram — подбор с умолчаниями модели, подписи нет, при открытии ничего не пишется", async () => {
    renderSheet();
    await loaded();
    expect(api.optimize.mock.calls[0][0].kuzram).toEqual(KUZRAM_DEFAULTS);
    expect(document.querySelector(".kuzram-caption")).toBeNull();
    await autosaveWindow();
    expect(api.saveCalcInputs).not.toHaveBeenCalled();
  });

  it("«!» у q, «≤ 0.10» и «> 5%» в таблице вариантов", async () => {
    api.optimize.mockResolvedValue({
      ...OPTIMIZE_GABBRO,
      variants: [gabbroVariant(110, { specific_q_kg_m3: 0.1 }), gabbroVariant(152), gabbroVariant(250, { oversize_pct: 5 })],
    });
    renderSheet();
    await loaded();
    const rowOf = async (crown: number) => (await screen.findByText(`Ø ${crown}`, undefined, SLOW)).closest("tr")!;
    const row250 = await rowOf(250);
    expect(within(row250).getByRole("img", { name: "Порог негабарита не достигнут" })).toHaveAttribute(
      "title",
      expect.stringContaining("верхней границе перебора"),
    );
    expect(row250).toHaveTextContent("1.50");
    expect(row250).toHaveTextContent("> 5%");
    expect(await rowOf(110)).toHaveTextContent("≤ 0.10");
    expect(within(await rowOf(152)).queryByRole("img", { name: "Порог негабарита не достигнут" })).not.toBeInTheDocument();
  });

  it("правка C(A) в окне пересчитывает варианты без фактов, показывает подпись и сохраняет блок", async () => {
    const facts = [{ crown_mm: 152, q_kg_m3: 1.3, oversize_pct: 8 }];
    api.calcInputs.mockResolvedValue({ work_object_name: OBJECT.name, inputs: savedInputs({ ...KUZRAM_DEFAULTS, facts }), updated_at: "then" });
    renderSheet();
    await loaded();
    fireEvent.click(screen.getByRole("button", { name: "Модель Kuz-Ram" }));
    fireEvent.change(within(dialog()).getByLabelText("Поправка C(A)"), { target: { value: "1,2" } });
    await waitFor(() => expect(api.optimize).toHaveBeenCalledTimes(2), SLOW);
    expect(api.optimize.mock.calls[1][0].kuzram).toEqual({ ...KUZRAM_DEFAULTS, rock_factor_correction: 1.2 });
    expect(document.querySelector(".kuzram-caption")).toHaveTextContent("C(A) 1,2");
    await waitFor(() => expect(lastSaved()?.kuzram).toEqual({ ...KUZRAM_DEFAULTS, rock_factor_correction: 1.2, facts }), SLOW);
  });

  it("пока идёт пересчёт, окно показывает «Пересчёт…»", async () => {
    renderSheet();
    await loaded();
    let release: (value: unknown) => void = () => {};
    api.optimize.mockImplementationOnce(() => new Promise((resolve) => { release = resolve; }));
    fireEvent.click(screen.getByRole("button", { name: "Модель Kuz-Ram" }));
    fireEvent.change(within(dialog()).getByLabelText("Поправка C(A)"), { target: { value: "1,3" } });
    expect(within(dialog()).getByRole("status")).toHaveTextContent("Пересчёт…");
    await waitFor(() => expect(api.optimize).toHaveBeenCalledTimes(2), SLOW);
    await act(async () => release(OPTIMIZE_GABBRO));
    await waitFor(() => expect(within(dialog()).getByRole("status")).toBeEmptyDOMElement(), SLOW);
  });
});
```

Run: `npm --prefix frontend test -- src/pages/CalcPage.kuzram.test.tsx`
Expected: FAIL — нет кнопки «Модель Kuz-Ram», `kuzram` в запросе нет.

- [ ] **Шаг 2. `ThresholdFlag.tsx`**

```tsx
const DEFAULT_TITLE =
  "Порог негабарита не достигнут: q на верхней границе перебора. " +
  "Поднимите границу в окне «Модель Kuz-Ram» или возьмите меньшую коронку.";

/** Значок «!» у q: порог негабарита не достигнут даже на верхней границе перебора. */
export function ThresholdFlag({ title = DEFAULT_TITLE }: { title?: string }) {
  return (
    <span className="threshold-flag" role="img" aria-label="Порог негабарита не достигнут" title={title}>
      !
    </span>
  );
}
```

- [ ] **Шаг 3. `CalcPage.tsx`**

1. Импорты. Строку `import type { BlastVariant, Explosive, ProductionUnit, Rock } from "../types";` заменить на `import type { BlastVariant, Explosive, KuzRamSettings, ProductionUnit, Rock } from "../types";`. Импорт `defaultKuzramBlock`, добавленный в Task 2, заменить блоком после `import { useCalcInputsAutosave } from "./calc/useCalcInputsAutosave";`:

```ts
import { KuzRamDialog, type KuzRamSource } from "./calc/kuzram/KuzRamDialog";
import { ThresholdFlag } from "./calc/kuzram/ThresholdFlag";
import { formatOversize, formatQ } from "./calc/kuzram/kuzramFormat";
import { defaultKuzramBlock, kuzramSettingsOf, settingsCaption, type KuzRamBlock } from "./calc/kuzram/kuzramSettings";
```

2. Перед `function FullBvrCalc(` добавить:

```ts
/** Пауза перед пересчётом после правки настроек модели: набор «1,15» по
 * цифрам не должен слать запрос на каждую. */
const KUZRAM_RECALC_DELAY_MS = 300;
```

3. В комментарии над `optimizeGenerationRef` в перечень полей дописать «, настройки модели Kuz-Ram». Сразу после `bumpOptimizeGeneration` добавить:

```ts
  // Номер последнего запущенного подбора: флаг «идёт расчёт» снимает только
  // он — иначе ранний ответ погасил бы «Пересчёт…», пока летит новый запрос.
  const optimizeRunRef = useRef(0);
```

4. После `setSelectedCrowns` (перед `const [nsiLengthOptions, …]`) добавить:

```ts
  // Блок модели Kuz-Ram объекта: настройки подбора q и фактические взрывы.
  const [kuzram, setKuzram] = useState<KuzRamBlock>(defaultKuzramBlock);
  // Растёт при каждой правке настроек модели в окне — эффект ниже
  // перезапускает подбор. Загрузка листа её не трогает: там подбор идёт сам.
  const [kuzramRevision, setKuzramRevision] = useState(0);
  // До какой ревизии подбор уже досчитан: пока отстаёт, окно пишет «Пересчёт…»
  // (и в паузе перед запросом).
  const [calculatedKuzramRevision, setCalculatedKuzramRevision] = useState(0);
  const [kuzramOpen, setKuzramOpen] = useState(false);
  const setKuzramSettings = useCallback(
    (next: KuzRamSettings) => {
      setKuzram((current) => ({ ...kuzramSettingsOf(next), facts: current.facts }));
      bumpOptimizeGeneration();
      setKuzramRevision((value) => value + 1);
    },
    [bumpOptimizeGeneration],
  );
```

5. После `const [variants, setVariants] = useState<BlastVariant[]>([]);` добавить:

```ts
  // Порог, с которым посчитаны варианты: «> порога» сравнивается с ним, а не
  // с ползунком, который могли сдвинуть без пересчёта.
  const [variantsThresholdPct, setVariantsThresholdPct] = useState<number | null>(null);
```

6. В `useMemo` листа строку `kuzram: defaultKuzramBlock(),` (из Task 2) заменить на `kuzram,`, в массив зависимостей после `panelInputs` добавить `kuzram`.

7. В `applySheet` после `setPanelInputs(next.panels);` добавить `setKuzram(next.kuzram);`.

8. В `runOptimize`: перед `setBusy(true);` добавить `const run = ++optimizeRunRef.current;`; в вызов `api.optimize({...})` после `crownDiametersMm: source.selectedCrownsMm,` добавить `kuzram: kuzramSettingsOf(source.kuzram),`; после `setVariants(result.variants);` добавить `setVariantsThresholdPct(result.max_oversize_threshold_pct);`; блок `finally` заменить на:

```ts
    } finally {
      // Параллельный подбор (правка настроек модели, пока летел прошлый) сам
      // снимет флаг — ранний ответ не должен гасить «идёт расчёт».
      if (run === optimizeRunRef.current) setBusy(false);
    }
```

9. После функции `calculate()` добавить:

```ts
  // Правка настроек модели в окне пересчитывает варианты сама — с паузой,
  // чтобы набор числа по цифрам не слал запрос на каждую. `calculate` из
  // рендера с новой ревизией уже видит новые настройки в `sheet`.
  useEffect(() => {
    if (kuzramRevision === 0) return;
    const revision = kuzramRevision;
    const timer = window.setTimeout(() => {
      void calculate().finally(() => setCalculatedKuzramRevision((done) => Math.max(done, revision)));
    }, KUZRAM_RECALC_DELAY_MS);
    return () => window.clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [kuzramRevision]);
```

10. После объявления `metrics` добавить:

```ts
  const kuzramCaption = settingsCaption(kuzram);
  const kuzramSource: KuzRamSource = {
    rockName,
    explosiveName: explosive?.name ?? explosiveKey,
    benchHeightM: benchHeight,
    overdrillM: overdrill,
    lumpSizeMm: lumpSize,
    thresholdPct: threshold,
  };
```

11. В заголовке панели «Варианты сетки» строку `<span>Куз–Рам</span>` заменить на:

```tsx
              <button
                type="button"
                className="secondary-button"
                disabled={!ready}
                aria-describedby={kuzramCaption ? "kuzram-caption" : undefined}
                onClick={() => setKuzramOpen(true)}
              >
                Модель Kuz-Ram
              </button>
              {kuzramCaption && (
                <span id="kuzram-caption" className="kuzram-caption" title={`Настройки модели: ${kuzramCaption}`}>
                  {kuzramCaption}
                </span>
              )}
```

12. В строке таблицы вариантов две ячейки `q` и `Негаб.` заменить на:

```tsx
                      <td className="num">
                        {!item.reached && <ThresholdFlag />}
                        {formatQ(item.specific_q_kg_m3, ".")}
                      </td>
                      <td className="num">
                        {formatOversize(item.oversize_pct, item.reached, variantsThresholdPct ?? threshold, 1, ".")}%
                      </td>
```

13. Перед закрывающим `</div>` корневого `calc-sheet` (после блока `ChargeComparison`/заглушки) добавить:

```tsx
      <KuzRamDialog
        open={kuzramOpen}
        onClose={() => setKuzramOpen(false)}
        block={kuzram}
        onSettingsChange={setKuzramSettings}
        source={kuzramSource}
        busy={busy || calculatedKuzramRevision < kuzramRevision}
        error={error}
      />
```

- [ ] **Шаг 4. Стили значка и подписи**

В конец `frontend/src/styles/kuzram.css`:

```css
/* Значок «!» у q: порог негабарита не достигнут (таблица листа и окно). */
.threshold-flag { display:inline-grid; place-items:center; width:13px; height:13px; margin-right:4px; border-radius:50%; background:#f0b43c; color:#3a2600; font-size:9px; font-weight:var(--font-weight-title); line-height:1; vertical-align:1px; cursor:help; }
/* Подпись у кнопки окна: чем настройки модели отличаются от умолчаний. */
.kuzram-caption { overflow:hidden; max-width:180px; color:#6e7c75; font-size:10px; white-space:nowrap; text-overflow:ellipsis; }
@media (max-width:760px) { .kuzram-caption { max-width:110px; } }
```

- [ ] **Шаг 5. Прогон**

Run: `npm --prefix frontend test -- src/pages/CalcPage.kuzram.test.tsx src/pages/CalcPage.unit.test.tsx` и `frontend/node_modules/.bin/tsc -p frontend/tsconfig.app.json`
Expected: оба файла зелёные (прежние тесты листа не сломаны), типы без ошибок. Затем `npm --prefix frontend test` — всё зелёное.

- [ ] **Шаг 6. Коммит**

```bash
git add frontend/src/pages/calc/kuzram/ThresholdFlag.tsx frontend/src/pages/CalcPage.tsx \
  frontend/src/pages/CalcPage.kuzram.test.tsx frontend/src/styles/kuzram.css
git commit -m "Kuz-Ram UI: кнопка на листе, пересчёт по настройкам, значок «!»

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 5. Сводка, таблица и график q(d)

**Файлы:**
- Создать: `frontend/src/pages/calc/kuzram/KuzRamComparison.tsx`, `KuzRamComparison.test.tsx`
- Создать: `frontend/src/pages/calc/kuzram/KuzRamChart.tsx`, `KuzRamChart.test.tsx`
- Изменить: `frontend/src/pages/calc/kuzram/KuzRamDialog.tsx`, `KuzRamDialog.test.tsx`
- Изменить: `frontend/src/pages/CalcPage.tsx` (новые свойства окна)
- Изменить: `frontend/src/styles/kuzram.css`

**Интерфейсы:**
- Потребляет: `ThresholdFlag` (Task 4); `formatQ`, `formatOversize`, `gridText`, `qDeltaText`, `trimmed`, `Q_MIN_KG_M3`, `LEGACY_Q_MIN_KG_M3` (Task 1); `completeFacts` (Task 1); `gabbroVariant` (Task 2).
- Производит: `KuzRamComparison({ variants: BlastVariant[]; selectedIndex: number; onSelect(index: number); thresholdPct: number })`; `KuzRamChart({ variants; facts: KuzRamFactInput[]; selectedIndex; onSelect })`, `niceStep(maxValue: number): number`; новые свойства `KuzRamDialogProps`: `variants`, `selectedIndex`, `onSelect`, `thresholdPct`.

- [ ] **Шаг 1. Падающие тесты сводки и таблицы**

`frontend/src/pages/calc/kuzram/KuzRamComparison.test.tsx`:

```tsx
// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { KuzRamComparison } from "./KuzRamComparison";
import { gabbroVariant } from "./testing/fixtures";

afterEach(cleanup);

const VARIANTS = [gabbroVariant(110), gabbroVariant(152), gabbroVariant(250)];
const FLAG = { name: "Порог негабарита не достигнут" };

describe("KuzRamComparison", () => {
  it("сводка выбранной коронки: обе модели и разница q", () => {
    render(<KuzRamComparison variants={VARIANTS} selectedIndex={1} onSelect={vi.fn()} thresholdPct={5} />);
    const summary = screen.getByRole("region", { name: "Коронка 152 мм" });
    expect(within(summary).getByText("1,26")).toBeInTheDocument();
    expect(within(summary).getByText("1,34")).toBeInTheDocument();
    expect(summary).toHaveTextContent("сетка 4,42 × 3,54 м · негабарит 4,98 %");
    expect(summary).toHaveTextContent("сетка 4,29 × 3,43 м · негабарит 5,00 %");
    expect(summary).toHaveTextContent("−6 %");
  });

  it("таблица: строка на коронку, «!» у обеих моделей, выбор мышью и клавиатурой", () => {
    const onSelect = vi.fn();
    render(<KuzRamComparison variants={VARIANTS} selectedIndex={1} onSelect={onSelect} thresholdPct={5} />);
    const rows = within(screen.getByRole("table")).getAllByRole("row").slice(2);
    expect(rows).toHaveLength(3);
    expect(rows[1]).toHaveAttribute("aria-selected", "true");
    expect(within(rows[2]).getAllByRole("img", FLAG)).toHaveLength(2);
    expect(within(rows[0]).queryByRole("img", FLAG)).not.toBeInTheDocument();
    fireEvent.click(rows[0]);
    expect(onSelect).toHaveBeenLastCalledWith(0);
    fireEvent.keyDown(rows[2], { key: "Enter" });
    expect(onSelect).toHaveBeenLastCalledWith(2);
  });

  it("округлённый негабарит на пороге при недостигнутом пороге — «> 5»", () => {
    render(
      <KuzRamComparison variants={[gabbroVariant(250, { oversize_pct: 5 })]} selectedIndex={0} onSelect={vi.fn()} thresholdPct={5} />,
    );
    const row = within(screen.getByRole("table")).getAllByRole("row")[2];
    expect(row).toHaveTextContent("> 5");
  });

  it("без расчёта — подсказка вместо таблицы", () => {
    render(<KuzRamComparison variants={[]} selectedIndex={0} onSelect={vi.fn()} thresholdPct={5} />);
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
    expect(screen.getByText(/Нет расчёта/)).toBeInTheDocument();
  });
});
```

Run: `npm --prefix frontend test -- src/pages/calc/kuzram/KuzRamComparison.test.tsx`
Expected: FAIL — компонента нет.

- [ ] **Шаг 2. `KuzRamComparison.tsx`**

```tsx
import { ruNumber } from "../../../lib/format";
import type { BlastVariant } from "../../../types";
import { ThresholdFlag } from "./ThresholdFlag";
import { formatOversize, formatQ, gridText, LEGACY_Q_MIN_KG_M3, Q_MIN_KG_M3, qDeltaText, trimmed } from "./kuzramFormat";

/** Результат одной модели в строке — чтобы сводка и таблица рисовали обе модели одинаково. */
type ModelResult = {
  q: number;
  qFloor: number;
  gridA: number;
  gridB: number;
  x50: number;
  n: number;
  oversize: number;
  reached: boolean;
};

function kuzramResult(variant: BlastVariant): ModelResult {
  return {
    q: variant.specific_q_kg_m3,
    qFloor: Q_MIN_KG_M3,
    gridA: variant.grid_a_m,
    gridB: variant.grid_b_m,
    x50: variant.x50_mm,
    n: variant.details.uniformity_n,
    oversize: variant.oversize_pct,
    reached: variant.reached,
  };
}

function legacyResult(variant: BlastVariant): ModelResult {
  const legacy = variant.legacy;
  return {
    q: legacy.specific_q_kg_m3,
    qFloor: LEGACY_Q_MIN_KG_M3,
    gridA: legacy.grid_a_m,
    gridB: legacy.grid_b_m,
    x50: legacy.x50_mm,
    n: legacy.details.uniformity_n,
    oversize: legacy.oversize_pct,
    reached: legacy.reached,
  };
}

function QValue({ result }: { result: ModelResult }) {
  return (
    <>
      {!result.reached && <ThresholdFlag />}
      {formatQ(result.q, ",", result.qFloor)}
    </>
  );
}

function Stat({ title, tone, result, thresholdPct }: { title: string; tone: "new" | "legacy"; result: ModelResult; thresholdPct: number }) {
  return (
    <div className="kuzram-stat">
      <span className="kuzram-stat-title">
        <i className={tone} aria-hidden="true" />
        {title}
      </span>
      <span>
        <b className="kuzram-stat-q">
          <QValue result={result} />
        </b>{" "}
        <small>кг/м³</small>
      </span>
      <span className="kuzram-stat-line">
        сетка {gridText(result.gridA, result.gridB)} м · негабарит {formatOversize(result.oversize, result.reached, thresholdPct)} %
      </span>
    </div>
  );
}

function ModelCells({ result, thresholdPct }: { result: ModelResult; thresholdPct: number }) {
  return (
    <>
      <td className="sep">
        <QValue result={result} />
      </td>
      <td>{gridText(result.gridA, result.gridB)}</td>
      <td>{ruNumber(result.x50, 1)}</td>
      <td>{ruNumber(result.n, 2)}</td>
      <td>{formatOversize(result.oversize, result.reached, thresholdPct)}</td>
    </>
  );
}

const MODEL_COLUMNS = ["q, кг/м³", "Сетка a × b, м", "x50, мм", "n", "Негабарит, %"];

/**
 * Сводка выбранной коронки и таблица по коронкам: Kuz-Ram рядом с расчётом
 * «до исправления». Выбор строки — тот же, что в таблице листа.
 */
export function KuzRamComparison({
  variants,
  selectedIndex,
  onSelect,
  thresholdPct,
}: {
  variants: BlastVariant[];
  selectedIndex: number;
  onSelect: (index: number) => void;
  thresholdPct: number;
}) {
  if (!variants.length) {
    return <p className="kuzram-empty">Нет расчёта: задайте исходные данные на листе и нажмите «Рассчитать варианты».</p>;
  }
  const selected = variants[selectedIndex] ?? variants[0];

  return (
    <>
      <section className="kuzram-card" aria-labelledby="kuzram-summary-title">
        <h3 id="kuzram-summary-title">Коронка {trimmed(selected.crown_mm)} мм</h3>
        <div className="kuzram-summary">
          <Stat title="Kuz-Ram" tone="new" result={kuzramResult(selected)} thresholdPct={thresholdPct} />
          <Stat title="До исправления" tone="legacy" result={legacyResult(selected)} thresholdPct={thresholdPct} />
          <div className="kuzram-stat">
            <span className="kuzram-stat-title">Разница q</span>
            <b className="kuzram-stat-q">{qDeltaText(selected.specific_q_kg_m3, selected.legacy.specific_q_kg_m3)}</b>
            <span className="kuzram-stat-line">Kuz-Ram относительно «до исправления»</span>
          </div>
        </div>
      </section>

      <section className="kuzram-card" aria-labelledby="kuzram-table-title">
        <h3 id="kuzram-table-title">Варианты сетки</h3>
        <div className="kuzram-table-scroll">
          <table className="kuzram-table">
            <caption>Строка на коронку; выбор строки меняет выбранную коронку и на листе. «!» — порог негабарита не достигнут.</caption>
            <thead>
              <tr className="groups">
                <th aria-hidden="true" />
                <th colSpan={5} scope="colgroup" className="sep g-new">Kuz-Ram</th>
                <th colSpan={5} scope="colgroup" className="sep g-legacy">До исправления</th>
                <th aria-hidden="true" className="sep" />
              </tr>
              <tr>
                <th scope="col">Коронка, мм</th>
                {["new", "legacy"].map((model) =>
                  MODEL_COLUMNS.map((title, index) => (
                    <th key={`${model}-${title}`} scope="col" className={index === 0 ? "sep" : undefined}>
                      {title}
                    </th>
                  )),
                )}
                <th scope="col" className="sep">Разница q</th>
              </tr>
            </thead>
            <tbody>
              {variants.map((variant, index) => (
                <tr
                  key={variant.crown_mm}
                  aria-selected={index === selectedIndex}
                  tabIndex={0}
                  onClick={() => onSelect(index)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter" || event.key === " ") {
                      event.preventDefault();
                      onSelect(index);
                    }
                  }}
                >
                  <td>{trimmed(variant.crown_mm)}</td>
                  <ModelCells result={kuzramResult(variant)} thresholdPct={thresholdPct} />
                  <ModelCells result={legacyResult(variant)} thresholdPct={thresholdPct} />
                  <td className="sep">{qDeltaText(variant.specific_q_kg_m3, variant.legacy.specific_q_kg_m3)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </>
  );
}
```

Run: `npm --prefix frontend test -- src/pages/calc/kuzram/KuzRamComparison.test.tsx`
Expected: 4 passed.

- [ ] **Шаг 3. Падающие тесты графика**

`frontend/src/pages/calc/kuzram/KuzRamChart.test.tsx`:

```tsx
// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { KuzRamChart, niceStep } from "./KuzRamChart";
import { gabbroVariant } from "./testing/fixtures";

afterEach(cleanup);

const VARIANTS = [gabbroVariant(110), gabbroVariant(152), gabbroVariant(250)];
const FACTS = [{ crown_mm: 152, q_kg_m3: 1.3, oversize_pct: 8 }];

describe("KuzRamChart", () => {
  it("шаг делений оси — круглый", () => {
    expect(niceStep(1.53)).toBe(0.25);
    expect(niceStep(2)).toBe(0.5);
    expect(niceStep(0.74)).toBe(0.1);
  });

  it("две линии, полые точки там, где порог не достигнут, ромбы фактов", () => {
    const { container } = render(<KuzRamChart variants={VARIANTS} facts={FACTS} selectedIndex={1} onSelect={vi.fn()} />);
    expect(screen.getByRole("img", { name: /Удельный расход q по диаметрам коронок/ })).toBeInTheDocument();
    expect(container.querySelectorAll("polyline")).toHaveLength(2);
    expect(container.querySelectorAll("circle.open")).toHaveLength(2);
    expect(container.querySelectorAll(".kuzram-chart-fact")).toHaveLength(1);
    expect(screen.getByText("фактический взрыв")).toBeInTheDocument();
  });

  it("наведение показывает подсказку, щелчок выбирает коронку", () => {
    const onSelect = vi.fn();
    const { container } = render(<KuzRamChart variants={VARIANTS} facts={FACTS} selectedIndex={1} onSelect={onSelect} />);
    const zones = container.querySelectorAll(".kuzram-chart-hit");
    fireEvent.mouseEnter(zones[2]);
    const tip = screen.getByRole("tooltip");
    expect(tip).toHaveTextContent("Коронка 250 мм");
    expect(tip).toHaveTextContent("Kuz-Ram 1,50 кг/м³");
    expect(tip).toHaveTextContent("До исправления 1,50 кг/м³");
    expect(tip).toHaveTextContent("порог не достигнут: Kuz-Ram, до исправления");
    fireEvent.mouseLeave(zones[2]);
    expect(screen.queryByRole("tooltip")).not.toBeInTheDocument();
    fireEvent.mouseEnter(zones[1]);
    expect(screen.getByRole("tooltip")).toHaveTextContent("Факт 1,30 кг/м³");
    fireEvent.click(zones[0]);
    expect(onSelect).toHaveBeenCalledWith(0);
  });
});
```

`niceStep`: 1,53/5 = 0,306 → мантисса 3,06 → 2,5 × 0,1 = 0,25; 2/5 = 0,4 → 5 × 0,1 = 0,5; 0,74/5 = 0,148 → 1,48 → 1 × 0,1 = 0,1.

Run: `npm --prefix frontend test -- src/pages/calc/kuzram/KuzRamChart.test.tsx`
Expected: FAIL — компонента нет.

- [ ] **Шаг 4. `KuzRamChart.tsx`**

```tsx
import { useState } from "react";
import { ruNumber } from "../../../lib/format";
import type { BlastVariant, KuzRamFactInput } from "../../../types";
import { formatQ, LEGACY_Q_MIN_KG_M3, trimmed } from "./kuzramFormat";

const WIDTH = 640;
const HEIGHT = 240;
const PAD = { left: 46, right: 14, top: 12, bottom: 36 };
const INNER_W = WIDTH - PAD.left - PAD.right;
const INNER_H = HEIGHT - PAD.top - PAD.bottom;

/** Шаг делений оси q: 1, 2, 2,5, 5 или 10 × 10ⁿ — около пяти делений на всю высоту. */
export function niceStep(maxValue: number): number {
  const raw = maxValue / 5;
  const power = 10 ** Math.floor(Math.log10(raw));
  const mantissa = raw / power;
  const nice = mantissa < 1.5 ? 1 : mantissa < 2.5 ? 2 : mantissa < 3.5 ? 2.5 : mantissa < 7.5 ? 5 : 10;
  return Number((nice * power).toPrecision(6));
}

type Point = { x: number; y: number; reached: boolean };

function Series({ className, points }: { className: string; points: Point[] }) {
  return (
    <g className={className}>
      <polyline points={points.map((point) => `${point.x.toFixed(1)},${point.y.toFixed(1)}`).join(" ")} />
      {points.map((point, index) => (
        <circle key={index} cx={point.x} cy={point.y} r={4} className={point.reached ? undefined : "open"} />
      ))}
    </g>
  );
}

/**
 * q по диаметрам коронок обеих моделей — самописный SVG, как `ResultsChart`.
 * Полая точка — порог негабарита не достигнут, ромб — фактический взрыв.
 * Наведение показывает подсказку, щелчок выбирает коронку (как строка таблицы).
 */
export function KuzRamChart({
  variants,
  facts,
  selectedIndex,
  onSelect,
}: {
  variants: BlastVariant[];
  facts: KuzRamFactInput[];
  selectedIndex: number;
  onSelect: (index: number) => void;
}) {
  const [hover, setHover] = useState<number | null>(null);
  if (!variants.length) return null;

  const crowns = variants.map((variant) => variant.crown_mm);
  const allCrowns = [...crowns, ...facts.map((fact) => fact.crown_mm)];
  const xPad = Math.max(8, (Math.max(...allCrowns) - Math.min(...allCrowns)) * 0.04);
  const x0 = Math.min(...allCrowns) - xPad;
  const x1 = Math.max(...allCrowns) + xPad;
  const qValues = [
    ...variants.flatMap((variant) => [variant.specific_q_kg_m3, variant.legacy.specific_q_kg_m3]),
    ...facts.map((fact) => fact.q_kg_m3),
  ];
  const qMax = Math.max(...qValues);
  const step = niceStep(qMax);
  const yMax = Math.ceil((qMax * 1.08) / step) * step;
  const x = (mm: number) => PAD.left + ((mm - x0) / (x1 - x0)) * INNER_W;
  const y = (q: number) => PAD.top + INNER_H - (q / yMax) * INNER_H;
  const ticks = Array.from({ length: Math.round(yMax / step) + 1 }, (_, index) => index * step);
  // Подписи коронок без наложения: следующая — не ближе 26 единиц к прошлой.
  let lastLabelX = -Infinity;
  const labelled = crowns.map((mm) => {
    if (x(mm) - lastLabelX < 26) return false;
    lastLabelX = x(mm);
    return true;
  });
  // Зона наведения коронки — до середины между соседними точками.
  const zones = crowns.map((mm, index) => {
    const from = index === 0 ? PAD.left : (x(crowns[index - 1]) + x(mm)) / 2;
    const to = index === crowns.length - 1 ? WIDTH - PAD.right : (x(mm) + x(crowns[index + 1])) / 2;
    return { from, width: Math.max(0, to - from) };
  });
  const selected = variants[selectedIndex];
  const hovered = hover === null ? null : variants[hover] ?? null;
  const tipLeftPct = hovered ? (x(hovered.crown_mm) / WIDTH) * 100 : 0;
  const bottom = HEIGHT - PAD.bottom;

  return (
    <div className="kuzram-chart">
      <svg viewBox={`0 0 ${WIDTH} ${HEIGHT}`} role="img" aria-label="Удельный расход q по диаметрам коронок: Kuz-Ram и «до исправления»">
        {ticks.map((tick) => (
          <g key={tick}>
            <line className="grid-line" x1={PAD.left} x2={WIDTH - PAD.right} y1={y(tick)} y2={y(tick)} />
            <text x={PAD.left - 6} y={y(tick)} textAnchor="end" dominantBaseline="middle">
              {ruNumber(tick, step < 1 ? 2 : 0)}
            </text>
          </g>
        ))}
        <line className="axis-line" x1={PAD.left} x2={WIDTH - PAD.right} y1={bottom} y2={bottom} />
        {crowns.map((mm, index) =>
          labelled[index] ? (
            <text key={mm} x={x(mm)} y={bottom + 15} textAnchor="middle">
              {trimmed(mm)}
            </text>
          ) : null,
        )}
        <text className="axis-title" x={PAD.left + INNER_W / 2} y={HEIGHT - 4} textAnchor="middle">
          Диаметр коронки, мм
        </text>
        <text className="axis-title" x={12} y={PAD.top + INNER_H / 2} textAnchor="middle" transform={`rotate(-90 12 ${PAD.top + INNER_H / 2})`}>
          q, кг/м³
        </text>
        {selected && <line className="kuzram-chart-selected" x1={x(selected.crown_mm)} x2={x(selected.crown_mm)} y1={PAD.top} y2={bottom} />}
        {hovered && <line className="kuzram-chart-hover" x1={x(hovered.crown_mm)} x2={x(hovered.crown_mm)} y1={PAD.top} y2={bottom} />}
        <Series
          className="series-legacy"
          points={variants.map((variant) => ({ x: x(variant.crown_mm), y: y(variant.legacy.specific_q_kg_m3), reached: variant.legacy.reached }))}
        />
        <Series
          className="series-new"
          points={variants.map((variant) => ({ x: x(variant.crown_mm), y: y(variant.specific_q_kg_m3), reached: variant.reached }))}
        />
        {facts.map((fact, index) => {
          const cx = x(fact.crown_mm);
          const cy = y(fact.q_kg_m3);
          return (
            <rect key={index} className="kuzram-chart-fact" x={cx - 4.5} y={cy - 4.5} width={9} height={9} transform={`rotate(45 ${cx} ${cy})`} />
          );
        })}
        {zones.map((zone, index) => (
          <rect
            key={crowns[index]}
            className="kuzram-chart-hit"
            x={zone.from}
            y={PAD.top}
            width={zone.width}
            height={INNER_H}
            onMouseEnter={() => setHover(index)}
            onMouseLeave={() => setHover(null)}
            onClick={() => onSelect(index)}
          />
        ))}
      </svg>
      {hovered && (
        <div className={`kuzram-chart-tip${tipLeftPct > 60 ? " left" : ""}`} role="tooltip" style={{ left: `${tipLeftPct}%` }}>
          <b>Коронка {trimmed(hovered.crown_mm)} мм</b>
          <span>
            <i className="new" aria-hidden="true" />
            Kuz-Ram {formatQ(hovered.specific_q_kg_m3)} кг/м³
          </span>
          <span>
            <i className="legacy" aria-hidden="true" />
            До исправления {formatQ(hovered.legacy.specific_q_kg_m3, ",", LEGACY_Q_MIN_KG_M3)} кг/м³
          </span>
          {facts
            .filter((fact) => fact.crown_mm === hovered.crown_mm)
            .map((fact, index) => (
              <span key={index}>
                <i className="fact" aria-hidden="true" />
                Факт {ruNumber(fact.q_kg_m3, 2)} кг/м³
              </span>
            ))}
          {(!hovered.reached || !hovered.legacy.reached) && (
            <span className="kuzram-chart-tip-flag">
              порог не достигнут: {[!hovered.reached ? "Kuz-Ram" : "", !hovered.legacy.reached ? "до исправления" : ""].filter(Boolean).join(", ")}
            </span>
          )}
        </div>
      )}
      <ul className="kuzram-legend" aria-label="Обозначения графика">
        <li><i className="new" aria-hidden="true" />Kuz-Ram</li>
        <li><i className="legacy" aria-hidden="true" />До исправления</li>
        <li><i className="open" aria-hidden="true" />порог не достигнут</li>
        {facts.length > 0 && <li><i className="fact" aria-hidden="true" />фактический взрыв</li>}
      </ul>
    </div>
  );
}
```

Run: `npm --prefix frontend test -- src/pages/calc/kuzram/KuzRamChart.test.tsx`
Expected: 3 passed.

- [ ] **Шаг 5. Окно показывает сводку, таблицу и график**

`KuzRamDialog.tsx`:
1. Импорты: `import type { BlastVariant, KuzRamSettings } from "../../../types";`, `import { KuzRamChart } from "./KuzRamChart";`, `import { KuzRamComparison } from "./KuzRamComparison";`, `import { completeFacts, type KuzRamBlock } from "./kuzramSettings";` (заменяет прежний импорт типа).
2. В `KuzRamDialogProps` после `error` добавить:

```ts
  /** Варианты последнего подбора: Kuz-Ram, «до исправления» и разбор. */
  variants: BlastVariant[];
  /** Выбранная коронка — общая с таблицей листа. */
  selectedIndex: number;
  onSelect: (index: number) => void;
  /** Порог негабарита, с которым посчитаны варианты. */
  thresholdPct: number;
```

3. `CalcTab` заменить на:

```tsx
function CalcTab({ block, onSettingsChange, source, busy, error, variants, selectedIndex, onSelect, thresholdPct }: KuzRamDialogProps) {
  const chartFacts = completeFacts(block.facts).map((row) => row.fact);
  return (
    <div className="kuzram-body kuzram-calc">
      <aside className="kuzram-side">
        <KuzRamSettingsForm settings={block} onChange={onSettingsChange} />
        <p className="kuzram-source">
          <b>С листа:</b> {source.rockName} · {source.explosiveName} · уступ {trimmed(source.benchHeightM)} м, перебур{" "}
          {trimmed(source.overdrillM)} м · кусок {trimmed(source.lumpSizeMm)} мм · допустимый негабарит{" "}
          {trimmed(source.thresholdPct)} %. Исходные данные меняются на листе.
        </p>
      </aside>
      <div className={`kuzram-results${busy ? " is-pending" : ""}`} aria-busy={busy}>
        <p className="kuzram-status" role="status">
          {busy ? "Пересчёт…" : ""}
        </p>
        {error && (
          <div className="page-error" role="alert">
            {error}
          </div>
        )}
        <KuzRamComparison variants={variants} selectedIndex={selectedIndex} onSelect={onSelect} thresholdPct={thresholdPct} />
        {variants.length > 0 && (
          <section className="kuzram-card" aria-labelledby="kuzram-chart-title">
            <h3 id="kuzram-chart-title">Удельный расход по диаметрам коронок</h3>
            <KuzRamChart variants={variants} facts={chartFacts} selectedIndex={selectedIndex} onSelect={onSelect} />
          </section>
        )}
      </div>
    </div>
  );
}
```

4. В `KuzRamDialog.test.tsx` в объект `props` хелпера `renderDialog` после `error: "",` добавить `variants: [], selectedIndex: 0, onSelect: vi.fn(), thresholdPct: 5,`, импорт `import { gabbroVariant } from "./testing/fixtures";` и тест:

```tsx
  it("показывает сводку, таблицу и график; выбор строки уходит листу", () => {
    const props = renderDialog({ variants: [gabbroVariant(110), gabbroVariant(152), gabbroVariant(250)], selectedIndex: 1 });
    expect(screen.getByRole("region", { name: "Коронка 152 мм" })).toBeInTheDocument();
    expect(screen.getByRole("img", { name: /Удельный расход q по диаметрам коронок/ })).toBeInTheDocument();
    // Таблиц в окне несколько (разбор, факты) — берём таблицу вариантов по её карточке.
    const table = within(screen.getByRole("region", { name: "Варианты сетки" })).getByRole("table");
    fireEvent.click(within(table).getAllByRole("row")[2]);
    expect(props.onSelect).toHaveBeenCalledWith(0);
  });
```

5. В `CalcPage.tsx` в `<KuzRamDialog …>` добавить свойства:

```tsx
        variants={variants}
        selectedIndex={selectedIndex}
        onSelect={setSelectedIndex}
        thresholdPct={variantsThresholdPct ?? threshold}
```

- [ ] **Шаг 6. Стили**

В конец `frontend/src/styles/kuzram.css`:

```css
/* Карточки результатов: сводка, таблица, график, разбор, фактические взрывы. */
.kuzram-card { display:grid; gap:10px; min-width:0; padding:12px 14px; border:1px solid #e2e8e5; border-radius:var(--radius-panel); background:#fff; }
.kuzram-card h3 { margin:0; font-size:12px; font-weight:var(--font-weight-strong); }
.kuzram-empty { margin:0; color:#6e7c75; }
.kuzram-summary { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:10px 20px; }
.kuzram-stat { display:grid; gap:2px; min-width:0; }
.kuzram-stat-title { display:inline-flex; align-items:center; gap:6px; color:#6e7c75; font-size:10.5px; }
.kuzram-stat-q { font-size:22px; letter-spacing:-.3px; font-variant-numeric:tabular-nums; }
.kuzram-stat small { color:#6e7c75; }
.kuzram-stat-line { color:#3b4b43; font-size:11px; }
.kuzram-dialog i.new, .kuzram-dialog i.legacy { display:inline-block; width:14px; height:3px; border-radius:2px; }
.kuzram-dialog i.new { background:#2d7556; }
.kuzram-dialog i.legacy { background:repeating-linear-gradient(90deg,#8a99a6 0 5px,transparent 5px 8px); }
.kuzram-table-scroll { overflow-x:auto; min-width:0; }
.kuzram-table { width:100%; border-collapse:collapse; font-size:11px; font-variant-numeric:tabular-nums; }
.kuzram-table caption { padding-bottom:6px; color:#6e7c75; font-size:10.5px; text-align:left; caption-side:top; }
.kuzram-table th, .kuzram-table td { padding:5px 8px; border-bottom:1px solid #edf1ef; text-align:right; white-space:nowrap; }
.kuzram-table th:first-child, .kuzram-table td:first-child { text-align:left; }
.kuzram-table th { color:#748079; font-size:10px; }
.kuzram-table thead tr.groups th { padding-bottom:2px; border-bottom:0; color:#3b4b43; letter-spacing:.3px; text-transform:uppercase; }
.kuzram-table .groups .g-new { box-shadow:inset 0 -2px 0 #2d7556; }
.kuzram-table .groups .g-legacy { box-shadow:inset 0 -2px 0 #8a99a6; }
.kuzram-table .sep { border-left:1px solid #e2e8e5; }
.kuzram-table tbody tr[aria-selected] { cursor:pointer; }
.kuzram-table tbody tr[aria-selected]:hover { background:#f5f9f7; }
.kuzram-table tbody tr[aria-selected="true"] { background:#edf7f1; }
.kuzram-table tbody tr:focus-visible { outline:2px solid #2d7556; outline-offset:-2px; }
/* График q(d): Kuz-Ram — акцентный зелёный, «до исправления» — серо-синий пунктир. */
.kuzram-chart { position:relative; }
.kuzram-chart svg { display:block; width:100%; height:auto; }
.kuzram-chart .grid-line { stroke:#edf1ef; stroke-width:1; }
.kuzram-chart .axis-line { stroke:#cfd9d4; stroke-width:1; }
.kuzram-chart text { fill:#748079; font-size:10.5px; }
.kuzram-chart .axis-title { fill:#3b4b43; font-size:11px; }
.kuzram-chart polyline { fill:none; stroke-width:2; stroke-linejoin:round; stroke-linecap:round; }
.kuzram-chart .series-new polyline { stroke:#2d7556; }
.kuzram-chart .series-legacy polyline { stroke:#8a99a6; stroke-dasharray:5 4; }
.kuzram-chart .series-new circle { fill:#2d7556; stroke:#fff; stroke-width:1.5; }
.kuzram-chart .series-legacy circle { fill:#8a99a6; stroke:#fff; stroke-width:1.5; }
.kuzram-chart .series-new circle.open { fill:#fff; stroke:#2d7556; stroke-width:2; }
.kuzram-chart .series-legacy circle.open { fill:#fff; stroke:#8a99a6; stroke-width:2; }
.kuzram-chart-fact { fill:#17231d; stroke:#fff; stroke-width:1.5; }
.kuzram-chart-selected { stroke:#2d7556; stroke-width:1; stroke-dasharray:3 3; opacity:.7; }
.kuzram-chart-hover { stroke:#9aa8a1; stroke-width:1; }
.kuzram-chart-hit { fill:transparent; cursor:pointer; }
.kuzram-chart-tip { position:absolute; top:8px; z-index:2; display:grid; gap:3px; min-width:170px; padding:8px 10px; border:1px solid #d9e2dd; border-radius:8px; background:#fff; box-shadow:0 8px 24px rgba(15,35,26,.14); color:#17231d; font-size:11px; pointer-events:none; transform:translateX(12px); }
.kuzram-chart-tip.left { transform:translateX(calc(-100% - 12px)); }
.kuzram-chart-tip span { display:flex; align-items:center; gap:6px; }
.kuzram-chart-tip-flag { color:#745014; }
.kuzram-legend { display:flex; flex-wrap:wrap; gap:4px 16px; margin:6px 0 0; padding:0; list-style:none; color:#3b4b43; font-size:11px; }
.kuzram-legend li { display:inline-flex; align-items:center; gap:6px; }
.kuzram-legend i.open { display:inline-block; width:9px; height:9px; border:2px solid #748079; border-radius:50%; background:#fff; }
.kuzram-dialog i.fact { display:inline-block; width:8px; height:8px; border-radius:1px; background:#17231d; transform:rotate(45deg); }
@media (max-width:760px) { .kuzram-summary { grid-template-columns:minmax(0,1fr) minmax(0,1fr); } }
```

- [ ] **Шаг 7. Прогон и коммит**

Run: `npm --prefix frontend test` и `frontend/node_modules/.bin/tsc -p frontend/tsconfig.app.json`
Expected: всё зелёное.

```bash
git add frontend/src/pages/calc/kuzram/KuzRamComparison.tsx frontend/src/pages/calc/kuzram/KuzRamComparison.test.tsx \
  frontend/src/pages/calc/kuzram/KuzRamChart.tsx frontend/src/pages/calc/kuzram/KuzRamChart.test.tsx \
  frontend/src/pages/calc/kuzram/KuzRamDialog.tsx frontend/src/pages/calc/kuzram/KuzRamDialog.test.tsx \
  frontend/src/pages/CalcPage.tsx frontend/src/styles/kuzram.css
git commit -m "Kuz-Ram UI: сводка, таблица и график q(d)

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 6. Разбор расчёта и предупреждение W/d

**Файлы:**
- Создать: `frontend/src/pages/calc/kuzram/KuzRamBreakdown.tsx`, `KuzRamBreakdown.test.tsx`
- Изменить: `frontend/src/pages/calc/kuzram/KuzRamComparison.tsx`, `KuzRamComparison.test.tsx` (строка про W/d под таблицей)
- Изменить: `frontend/src/pages/calc/kuzram/KuzRamDialog.tsx`, `KuzRamDialog.test.tsx`
- Изменить: `frontend/src/styles/kuzram.css`

**Интерфейсы:**
- Потребляет: `BURDEN_TO_DIAMETER_WARN_ABOVE` (Task 1), `ThresholdFlag` (Task 4), `formatQ`, `formatOversize`, `gridText`, `trimmed`, `LEGACY_Q_MIN_KG_M3` (Task 1), `gabbroVariant` (Task 2).
- Производит: `KuzRamBreakdown({ variant: BlastVariant; thresholdPct: number })`, `rockFactorLines(breakdown: RockFactorBreakdown | null): string[]`, `uniformityText(details: FragmentationDetails): string`.

- [ ] **Шаг 1. Падающие тесты**

`frontend/src/pages/calc/kuzram/KuzRamBreakdown.test.tsx`:

```tsx
// @vitest-environment jsdom
import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { KuzRamBreakdown, rockFactorLines, uniformityText } from "./KuzRamBreakdown";
import { gabbroVariant } from "./testing/fixtures";

afterEach(cleanup);

const rowOf = (name: RegExp) => screen.getByRole("rowheader", { name }).closest("tr")!;
/** Ячейки строки разбора: Kuz-Ram и «до исправления» (заголовок строки — не ячейка). */
const cellsOf = (name: RegExp) => within(rowOf(name)).getAllByRole("cell").map((cell) => cell.textContent);

describe("KuzRamBreakdown", () => {
  it("величины обеих моделей для выбранной коронки", () => {
    render(<KuzRamBreakdown variant={gabbroVariant(152)} thresholdPct={5} />);
    expect(screen.getByText("Коронка 152 мм — каждая модель на своём подобранном q.")).toBeInTheDocument();
    expect(cellsOf(/^Удельный расход q/)).toEqual(["1,26", "1,34"]);
    expect(rowOf(/^Фактор породы A/)).toHaveTextContent("0,06·(RMD 50 + RDI 22,5 + HF 33,6)");
    expect(cellsOf(/^Фактор породы A/)).toEqual(["6,37", "2,72"]);
    expect(rowOf(/^Индекс равномерности n/)).toHaveTextContent("→ принято 0,80");
    expect(rowOf(/^W\/d/)).not.toHaveTextContent("выше 35");
    expect(screen.queryByText(/Каннингем рекомендует 25–35/)).not.toBeInTheDocument();
  });

  it("W/d выше 35 — предупреждение, подбор при этом не ограничен", () => {
    const variant = gabbroVariant(152);
    variant.details.burden_to_diameter = 40.9;
    render(<KuzRamBreakdown variant={variant} thresholdPct={5} />);
    expect(rowOf(/^W\/d/)).toHaveTextContent("выше 35");
    expect(screen.getByText(/W\/d = 40,9 — выше 35: сетка редкая для этого диаметра/)).toBeInTheDocument();
  });

  it("состав A: JF с шагом трещин, массив без трещин, ручной ввод", () => {
    expect(
      rockFactorLines({
        method: "joint_factor", rmd: 100, rdi: 22.5, hf: 33.6, joint_spacing_m: 0.4545, reduced_pattern_m: 3.15,
        jps: 80, base: 9.366, correction: 1.15, value: 10.77,
      }),
    ).toEqual([
      "0,06·(JF 100 + RDI 22,5 + HF 33,6) · C(A) 1,15",
      "JF = JCF·JPS + JPA; JPS 80 при шаге трещин 0,45 м и приведённой сетке P = 3,15 м",
    ]);
    expect(
      rockFactorLines({
        method: "joint_factor", rmd: 50, rdi: 22.5, hf: 33.6, joint_spacing_m: null, reduced_pattern_m: null,
        jps: null, base: 6.366, correction: 1, value: 6.366,
      }),
    ).toEqual(["0,06·(RMD 50 + RDI 22,5 + HF 33,6)", "массив без трещин — RMD 50"]);
    expect(
      rockFactorLines({
        method: "manual", rmd: null, rdi: null, hf: null, joint_spacing_m: null, reduced_pattern_m: null,
        jps: null, base: 6, correction: 1.2, value: 7.2,
      }),
    ).toEqual(["задан вручную: 6 · C(A) 1,2"]);
    expect(rockFactorLines(null)).toEqual([]);
  });

  it("n: сырое → принятое и L/H", () => {
    const variant = gabbroVariant(152);
    expect(uniformityText(variant.details)).toBe("1,78 (L/H 0,88)");
    expect(uniformityText(variant.legacy.details)).toMatch(/^-317,54 → принято 0,80$/);
  });
});
```

У коронки 152 мм порог достигнут обеими моделями, поэтому значка «!» в ячейках q нет. Легаси A габбро-диабаза = 0,12·(168/20 + 2,5·2,9 + 7) = 2,718.

В `KuzRamComparison.test.tsx` добавить тест:

```tsx
  it("под таблицей — коронки с W/d выше 35", () => {
    const wide = gabbroVariant(110);
    wide.details.burden_to_diameter = 40.9;
    render(<KuzRamComparison variants={[wide, gabbroVariant(152)]} selectedIndex={1} onSelect={vi.fn()} thresholdPct={5} />);
    expect(screen.getByText(/W\/d выше 35 у коронок 110 мм/)).toBeInTheDocument();
  });
```

Run: `npm --prefix frontend test -- src/pages/calc/kuzram/KuzRamBreakdown.test.tsx src/pages/calc/kuzram/KuzRamComparison.test.tsx`
Expected: FAIL.

- [ ] **Шаг 2. `KuzRamBreakdown.tsx`**

```tsx
import type { ReactNode } from "react";
import { ruNumber } from "../../../lib/format";
import type { BlastVariant, FragmentationDetails, RockFactorBreakdown } from "../../../types";
import { ThresholdFlag } from "./ThresholdFlag";
import { formatOversize, formatQ, gridText, LEGACY_Q_MIN_KG_M3, trimmed } from "./kuzramFormat";
import { BURDEN_TO_DIAMETER_WARN_ABOVE } from "./kuzramSettings";

/** Состав фактора породы A новой модели — строками для подписи в разборе. */
export function rockFactorLines(breakdown: RockFactorBreakdown | null): string[] {
  if (!breakdown) return [];
  const correction = breakdown.correction !== 1 ? ` · C(A) ${trimmed(breakdown.correction)}` : "";
  if (breakdown.method === "manual") return [`задан вручную: ${trimmed(breakdown.base)}${correction}`];
  const rdi = trimmed(breakdown.rdi ?? 0, 1);
  const hf = trimmed(breakdown.hf ?? 0, 1);
  const rmd = trimmed(breakdown.rmd ?? 0, 1);
  if (breakdown.jps !== null) {
    return [
      `0,06·(JF ${rmd} + RDI ${rdi} + HF ${hf})${correction}`,
      `JF = JCF·JPS + JPA; JPS ${trimmed(breakdown.jps)} при шаге трещин ${ruNumber(breakdown.joint_spacing_m ?? 0, 2)} м ` +
        `и приведённой сетке P = ${ruNumber(breakdown.reduced_pattern_m ?? 0, 2)} м`,
    ];
  }
  const lines = [`0,06·(RMD ${rmd} + RDI ${rdi} + HF ${hf})${correction}`];
  if (breakdown.method === "joint_factor") lines.push(`массив без трещин — RMD ${rmd}`);
  return lines;
}

/** Индекс равномерности: «сырое → принятое» (если формула дала меньше нижней границы) и L/H. */
export function uniformityText(details: FragmentationDetails): string {
  const accepted =
    Math.abs(details.uniformity_n - details.uniformity_n_raw) > 1e-9 ? ` → принято ${ruNumber(details.uniformity_n, 2)}` : "";
  const chargeToBench = details.charge_to_bench !== null ? ` (L/H ${ruNumber(details.charge_to_bench, 2)})` : "";
  return `${ruNumber(details.uniformity_n_raw, 2)}${accepted}${chargeToBench}`;
}

type Row = { label: ReactNode; now: ReactNode; old: ReactNode; key?: boolean };

/**
 * Разбор расчёта выбранной коронки: промежуточные величины обеих моделей на
 * их подобранном q. Всё приходит с сервера (`details`), окно только подписывает.
 */
export function KuzRamBreakdown({ variant, thresholdPct }: { variant: BlastVariant; thresholdPct: number }) {
  const now = variant.details;
  const old = variant.legacy.details;
  const wide = now.burden_to_diameter > BURDEN_TO_DIAMETER_WARN_ABOVE;
  const rows: Row[] = [
    { label: "Диаметр скважины d, мм", now: ruNumber(now.hole_diameter_mm, 1), old: ruNumber(old.hole_diameter_mm, 1) },
    { label: "Длина заряда L, м", now: ruNumber(now.charge_length_m, 2), old: ruNumber(old.charge_length_m, 2) },
    { label: "Масса заряда Q, кг", now: ruNumber(now.charge_mass_kg, 1), old: ruNumber(old.charge_mass_kg, 1) },
    {
      label: "Удельный расход q, кг/м³",
      now: (
        <>
          {!variant.reached && <ThresholdFlag />}
          {formatQ(now.q_kg_m3)}
        </>
      ),
      old: (
        <>
          {!variant.legacy.reached && <ThresholdFlag />}
          {formatQ(old.q_kg_m3, ",", LEGACY_Q_MIN_KG_M3)}
        </>
      ),
      key: true,
    },
    { label: "Объём на скважину V = Q/q, м³", now: ruNumber(now.volume_per_hole_m3, 1), old: ruNumber(old.volume_per_hole_m3, 1) },
    {
      label: "ЛНС W · сетка a × b, м",
      now: `${ruNumber(now.burden_m, 2)} · ${gridText(now.spacing_m, now.burden_m)}`,
      old: `${ruNumber(old.burden_m, 2)} · ${gridText(old.spacing_m, old.burden_m)}`,
    },
    {
      label: "W/d — ЛНС к диаметру скважины",
      now: (
        <>
          {ruNumber(now.burden_to_diameter, 1)}
          {wide && <span className="kuzram-warning-mark">выше {BURDEN_TO_DIAMETER_WARN_ABOVE}</span>}
        </>
      ),
      old: ruNumber(old.burden_to_diameter, 1),
    },
    {
      label: (
        <>
          Фактор породы A
          {rockFactorLines(now.rock_factor).map((line) => (
            <small key={line}>Kuz-Ram: {line}</small>
          ))}
          <small>до исправления: 0,12·(UCS/20 + 2,5ρ + 7)</small>
        </>
      ),
      now: ruNumber(now.rock_factor_a, 2),
      old: ruNumber(old.rock_factor_a, 2),
    },
    {
      label: "Сила ВВ RE (к тротилу) · показатель",
      now: `${ruNumber(now.re_weight, 3)} · ${now.strength_exponent}`,
      old: `${ruNumber(old.re_weight, 3)} · ${old.strength_exponent}`,
    },
    { label: "Средний кусок x50, мм", now: ruNumber(now.x50_mm, 1), old: ruNumber(old.x50_mm, 1) },
    { label: "Индекс равномерности n", now: uniformityText(now), old: uniformityText(old) },
    { label: "Характерный размер xc, мм", now: ruNumber(now.characteristic_size_mm, 1), old: ruNumber(old.characteristic_size_mm, 1) },
    {
      label: "Негабарит, %",
      now: formatOversize(now.oversize_pct, variant.reached, thresholdPct),
      old: formatOversize(old.oversize_pct, variant.legacy.reached, thresholdPct),
      key: true,
    },
  ];

  return (
    <section className="kuzram-card" aria-labelledby="kuzram-breakdown-title">
      <h3 id="kuzram-breakdown-title">Разбор расчёта</h3>
      <div className="kuzram-table-scroll">
        <table className="kuzram-table kuzram-breakdown">
          <caption>Коронка {trimmed(variant.crown_mm)} мм — каждая модель на своём подобранном q.</caption>
          <thead>
            <tr>
              <th scope="col">Величина</th>
              <th scope="col" className="sep">Kuz-Ram</th>
              <th scope="col" className="sep">До исправления</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row, index) => (
              <tr key={index} className={row.key ? "key" : undefined}>
                <th scope="row">{row.label}</th>
                <td className="sep">{row.now}</td>
                <td className="sep">{row.old}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {wide && (
        <p className="kuzram-warning">
          W/d = {ruNumber(now.burden_to_diameter, 1)} — выше {BURDEN_TO_DIAMETER_WARN_ABOVE}: сетка редкая для этого диаметра,
          Каннингем рекомендует 25–35. Прогноз модели здесь менее надёжен; подбор q это не ограничивает.
        </p>
      )}
    </section>
  );
}
```

Run: `npm --prefix frontend test -- src/pages/calc/kuzram/KuzRamBreakdown.test.tsx`
Expected: 4 passed.

- [ ] **Шаг 3. Строка про W/d в сравнении**

В `KuzRamComparison.tsx`: импорт `import { BURDEN_TO_DIAMETER_WARN_ABOVE } from "./kuzramSettings";`; перед `return (` (после `const selected = …`) добавить:

```ts
  const wide = variants.filter((variant) => variant.details.burden_to_diameter > BURDEN_TO_DIAMETER_WARN_ABOVE);
```

в карточке таблицы после `</div>` блока `kuzram-table-scroll` добавить:

```tsx
        {wide.length > 0 && (
          <p className="kuzram-warning">
            W/d выше {BURDEN_TO_DIAMETER_WARN_ABOVE} у коронок {wide.map((variant) => trimmed(variant.crown_mm)).join(", ")} мм —
            сетка редкая для диаметра: Каннингем рекомендует 25–35. Подробности — в разборе расчёта.
          </p>
        )}
```

- [ ] **Шаг 4. Окно показывает разбор**

В `KuzRamDialog.tsx`: импорт `import { KuzRamBreakdown } from "./KuzRamBreakdown";`; в `CalcTab` перед `return (` добавить `const selected = variants[selectedIndex];`, после секции графика добавить:

```tsx
        {selected && <KuzRamBreakdown variant={selected} thresholdPct={thresholdPct} />}
```

В `KuzRamDialog.test.tsx` в тест «показывает сводку, таблицу и график…» добавить `expect(screen.getByRole("region", { name: "Разбор расчёта" })).toBeInTheDocument();`.

- [ ] **Шаг 5. Стили**

В конец `frontend/src/styles/kuzram.css`:

```css
.kuzram-breakdown th[scope="row"] { min-width:200px; color:#3b4b43; font-weight:var(--font-weight-body); text-align:left; white-space:normal; }
.kuzram-breakdown th[scope="row"] small { display:block; color:#7b8982; font-size:10px; }
.kuzram-breakdown tr.key th, .kuzram-breakdown tr.key td { color:#17231d; font-weight:var(--font-weight-strong); }
.kuzram-warning-mark { margin-left:6px; padding:0 6px; border-radius:999px; background:#fdf3e2; color:#745014; font-size:10px; }
.kuzram-warning { margin:0; padding:8px 10px; border:1px solid #ead39f; border-radius:9px; background:#fff8e9; color:#684b17; font-size:11px; }
```

- [ ] **Шаг 6. Прогон и коммит**

Run: `npm --prefix frontend test` и `frontend/node_modules/.bin/tsc -p frontend/tsconfig.app.json`
Expected: всё зелёное.

```bash
git add frontend/src/pages/calc/kuzram/KuzRamBreakdown.tsx frontend/src/pages/calc/kuzram/KuzRamBreakdown.test.tsx \
  frontend/src/pages/calc/kuzram/KuzRamComparison.tsx frontend/src/pages/calc/kuzram/KuzRamComparison.test.tsx \
  frontend/src/pages/calc/kuzram/KuzRamDialog.tsx frontend/src/pages/calc/kuzram/KuzRamDialog.test.tsx \
  frontend/src/styles/kuzram.css
git commit -m "Kuz-Ram UI: разбор расчёта и предупреждение W/d

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 7. Фактические взрывы и подбор C(A)

**Файлы:**
- Создать: `frontend/src/pages/calc/kuzram/KuzRamFacts.tsx`, `KuzRamFacts.test.tsx`
- Изменить: `frontend/src/pages/calc/kuzram/KuzRamDialog.tsx`, `KuzRamDialog.test.tsx`
- Изменить: `frontend/src/pages/CalcPage.tsx`, `frontend/src/pages/CalcPage.kuzram.test.tsx`
- Изменить: `frontend/src/styles/kuzram.css`

**Интерфейсы:**
- Потребляет: `KuzRamFact`, `FACT_FIELDS`, `FACT_LABELS`, `MAX_FACTS`, `completeFacts`, `factCellError`, `parseDecimal`, `kuzramSettingsOf` (Task 1); `trimmed` (Task 1); `api.calibrateKuzram` (Task 2).
- Производит: `KuzRamFacts({ facts; onChange(next: KuzRamFact[]); defaultCrownMm: number | null; onCalibrate(facts: KuzRamFactInput[]): Promise<KuzRamCalibrateResponse>; onApplyCorrection(value: number) })`; новые свойства окна `onFactsChange(next: KuzRamFact[])`, `onCalibrate(facts)`.

- [ ] **Шаг 1. Падающие тесты таблицы фактов**

`frontend/src/pages/calc/kuzram/KuzRamFacts.test.tsx`:

```tsx
// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { useState } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { KuzRamCalibrateResponse } from "../../../types";
import { KuzRamFacts } from "./KuzRamFacts";
import type { KuzRamFact } from "./kuzramSettings";

afterEach(cleanup);

function renderFacts(initial: KuzRamFact[], onCalibrate = vi.fn()) {
  const onApplyCorrection = vi.fn();
  const changes: KuzRamFact[][] = [];
  function Harness() {
    const [facts, setFacts] = useState(initial);
    return (
      <KuzRamFacts
        facts={facts}
        onChange={(next) => {
          changes.push(next);
          setFacts(next);
        }}
        defaultCrownMm={152}
        onCalibrate={onCalibrate}
        onApplyCorrection={onApplyCorrection}
      />
    );
  }
  render(<Harness />);
  return { onCalibrate, onApplyCorrection, changes };
}

const calibrateButton = () => screen.getByRole("button", { name: "Подобрать C(A) по факту" });

function response(overrides: Partial<KuzRamCalibrateResponse>): KuzRamCalibrateResponse {
  return { rows: [], rock_factor_correction: null, used: 0, skipped: 0, model_version: "kuzram-cunningham-1.0", ...overrides };
}

describe("KuzRamFacts", () => {
  it("«Добавить взрыв» — пустая строка с выбранной коронкой; без полных строк подбор выключен", () => {
    const { changes } = renderFacts([]);
    expect(screen.getByText("Фактических взрывов пока нет.")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Добавить взрыв" }));
    expect(changes.at(-1)).toEqual([{ crown_mm: 152, q_kg_m3: null, oversize_pct: null }]);
    expect(screen.getByLabelText("Коронка, строка 1")).toHaveValue("152");
    expect(calibrateButton()).toBeDisabled();
  });

  it("неверное значение подсвечивается, строка в подбор не идёт", () => {
    renderFacts([{ crown_mm: 152, q_kg_m3: 1.3, oversize_pct: null }]);
    const oversize = screen.getByLabelText("Фактический негабарит, строка 1");
    fireEvent.change(oversize, { target: { value: "120" } });
    expect(oversize).toHaveAttribute("aria-invalid", "true");
    expect(screen.getByText("Фактический негабарит — больше 0 и меньше 100 %.")).toBeInTheDocument();
    expect(calibrateButton()).toBeDisabled();
    fireEvent.change(oversize, { target: { value: "8,0" } });
    expect(oversize).not.toHaveAttribute("aria-invalid");
    expect(calibrateButton()).toBeEnabled();
  });

  it("удаление строки сдвигает следующие", () => {
    renderFacts([
      { crown_mm: 152, q_kg_m3: 1.3, oversize_pct: 8 },
      { crown_mm: 165, q_kg_m3: 1.35, oversize_pct: 7.5 },
    ]);
    fireEvent.click(screen.getByRole("button", { name: "Удалить взрыв 1" }));
    expect(screen.getByLabelText("Коронка, строка 1")).toHaveValue("165");
    expect(screen.queryByLabelText("Коронка, строка 2")).not.toBeInTheDocument();
  });

  it("подбор C(A): только полные строки, C(A) записывается, по строкам видны прогнозы", async () => {
    const onCalibrate = vi.fn().mockResolvedValue(
      response({
        rows: [
          { crown_mm: 152, q_kg_m3: 1.3, oversize_pct: 8, legacy_oversize_pct: 5.3, model_oversize_pct: 4.29, rock_factor_correction: 1.132, note: null },
          { crown_mm: 130, q_kg_m3: 1.2, oversize_pct: 60, legacy_oversize_pct: 5.45, model_oversize_pct: 4.72, rock_factor_correction: null, note: "Фактический негабарит не получается ни при каком C(A) от 0,1 до 10." },
        ],
        rock_factor_correction: 1.132,
        used: 1,
        skipped: 1,
      }),
    );
    const { onApplyCorrection } = renderFacts(
      [
        { crown_mm: 152, q_kg_m3: 1.3, oversize_pct: 8 },
        { crown_mm: 165, q_kg_m3: null, oversize_pct: 7 },
        { crown_mm: 130, q_kg_m3: 1.2, oversize_pct: 60 },
      ],
      onCalibrate,
    );
    fireEvent.click(calibrateButton());
    await waitFor(() => expect(onApplyCorrection).toHaveBeenCalledWith(1.132));
    expect(onCalibrate).toHaveBeenCalledWith([
      { crown_mm: 152, q_kg_m3: 1.3, oversize_pct: 8 },
      { crown_mm: 130, q_kg_m3: 1.2, oversize_pct: 60 },
    ]);
    expect(screen.getByRole("status")).toHaveTextContent(
      "C(A) = 1,132 записана в настройки — посчитано по строкам: 1 из 2. Пропущено строк: 1 — для них нет C(A) от 0,1 до 10. Неполные или неверные строки не учитывались: 1.",
    );
    const rows = within(screen.getByRole("table")).getAllByRole("row").slice(1);
    expect(rows[0]).toHaveTextContent("5,304,291,132");
    expect(rows[1]).toHaveTextContent("———");
    expect(within(rows[2]).getByText("нет")).toHaveAttribute("title", expect.stringContaining("ни при каком C(A)"));
  });

  it("ни одна строка не решилась — C(A) не меняется", async () => {
    const onCalibrate = vi.fn().mockResolvedValue(response({ rock_factor_correction: null, used: 0, skipped: 1, rows: [
      { crown_mm: 152, q_kg_m3: 1.3, oversize_pct: 90, legacy_oversize_pct: 5.3, model_oversize_pct: 4.29, rock_factor_correction: null, note: "вне 0,1–10" },
    ] }));
    const { onApplyCorrection } = renderFacts([{ crown_mm: 152, q_kg_m3: 1.3, oversize_pct: 90 }], onCalibrate);
    fireEvent.click(calibrateButton());
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("поправка не изменена"));
    expect(onApplyCorrection).not.toHaveBeenCalled();
  });

  it("ошибка сервера видна, правка строки сбрасывает прошлый результат", async () => {
    const onCalibrate = vi.fn().mockRejectedValueOnce(new Error("Фактор породы A = −0,5 — он должен быть больше нуля."));
    renderFacts([{ crown_mm: 152, q_kg_m3: 1.3, oversize_pct: 8 }], onCalibrate);
    fireEvent.click(calibrateButton());
    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent("Фактор породы A = −0,5"));
    fireEvent.change(screen.getByLabelText("Фактический q, строка 1"), { target: { value: "1,4" } });
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });
});
```

Run: `npm --prefix frontend test -- src/pages/calc/kuzram/KuzRamFacts.test.tsx`
Expected: FAIL — компонента нет.

- [ ] **Шаг 2. `KuzRamFacts.tsx`**

```tsx
import { useEffect, useId, useRef, useState } from "react";
import { ruNumber } from "../../../lib/format";
import type { KuzRamCalibrateResponse, KuzRamCalibrationRow, KuzRamFactInput } from "../../../types";
import { trimmed } from "./kuzramFormat";
import {
  completeFacts,
  FACT_FIELDS,
  FACT_LABELS,
  factCellError,
  MAX_FACTS,
  parseDecimal,
  type FactField,
  type KuzRamFact,
} from "./kuzramSettings";

type Message = { tone: "ok" | "warn" | "error"; text: string };

/**
 * Ячейка факта. Хранит набранный текст: пустая ячейка допустима (строка просто
 * не идёт в подбор), неверное число подсвечивается и в подбор тоже не идёт.
 */
function FactCell({
  field,
  value,
  rowNumber,
  onCommit,
}: {
  field: FactField;
  value: number | null;
  rowNumber: number;
  onCommit: (value: number | null) => void;
}) {
  const id = useId();
  const [draft, setDraft] = useState(() => (value === null ? "" : trimmed(value, 6)));
  // Значение сменилось снаружи (удалили строку выше) — показываем новое;
  // свой незаконченный ввод не трогаем.
  useEffect(() => {
    setDraft((current) => (parseDecimal(current) === value ? current : value === null ? "" : trimmed(value, 6)));
  }, [value]);
  const error = draft.trim() !== "" && parseDecimal(draft) === null ? "Введите число." : factCellError(field, value);

  function change(text: string) {
    setDraft(text);
    const next = parseDecimal(text);
    if (next !== value) onCommit(next);
  }

  return (
    <>
      <input
        type="text"
        inputMode="decimal"
        autoComplete="off"
        aria-label={`${FACT_LABELS[field].label}, строка ${rowNumber}`}
        value={draft}
        aria-invalid={error ? true : undefined}
        aria-describedby={error ? `${id}-error` : undefined}
        onChange={(event) => change(event.target.value)}
      />
      {error && (
        <small id={`${id}-error`} className="kuzram-field-error">
          {error}
        </small>
      )}
    </>
  );
}

/**
 * Фактические взрывы объекта и подбор C(A). Строки хранятся за объектом вместе
 * с настройками и подбор сетки не запускают; «Подобрать C(A) по факту» шлёт
 * полные строки на сервер и записывает среднюю поправку в настройки.
 */
export function KuzRamFacts({
  facts,
  onChange,
  defaultCrownMm,
  onCalibrate,
  onApplyCorrection,
}: {
  facts: KuzRamFact[];
  onChange: (next: KuzRamFact[]) => void;
  /** Коронка новой строки — выбранная на листе. */
  defaultCrownMm: number | null;
  onCalibrate: (facts: KuzRamFactInput[]) => Promise<KuzRamCalibrateResponse>;
  /** Записать подобранную C(A) в настройки объекта. */
  onApplyCorrection: (value: number) => void;
}) {
  const [calibration, setCalibration] = useState<Map<number, KuzRamCalibrationRow> | null>(null);
  const [message, setMessage] = useState<Message | null>(null);
  const [pending, setPending] = useState(false);
  // Растёт при каждой правке строк: ответ подбора, начатого до правки, уже не про эти строки.
  const editRef = useRef(0);
  const complete = completeFacts(facts);

  function update(next: KuzRamFact[]) {
    editRef.current += 1;
    setCalibration(null);
    setMessage(null);
    onChange(next);
  }

  async function calibrate() {
    const rows = completeFacts(facts);
    if (!rows.length) return;
    const edit = editRef.current;
    setPending(true);
    setMessage(null);
    try {
      const response = await onCalibrate(rows.map((row) => row.fact));
      if (edit !== editRef.current) return;
      setCalibration(new Map(rows.map((row, index) => [row.index, response.rows[index]])));
      const skippedRows = facts.length - rows.length;
      const tail = skippedRows ? ` Неполные или неверные строки не учитывались: ${skippedRows}.` : "";
      if (response.rock_factor_correction === null) {
        setMessage({
          tone: "warn",
          text: `Ни одна строка не совпала с моделью при C(A) от 0,1 до 10 — поправка не изменена. Проверьте фактические данные.${tail}`,
        });
        return;
      }
      onApplyCorrection(response.rock_factor_correction);
      const skipped = response.skipped ? ` Пропущено строк: ${response.skipped} — для них нет C(A) от 0,1 до 10.` : "";
      setMessage({
        tone: "ok",
        text:
          `C(A) = ${trimmed(response.rock_factor_correction)} записана в настройки — посчитано по строкам: ` +
          `${response.used} из ${rows.length}.${skipped}${tail}`,
      });
    } catch (reason) {
      if (edit !== editRef.current) return;
      setMessage({ tone: "error", text: reason instanceof Error ? reason.message : "Не удалось подобрать C(A)." });
    } finally {
      setPending(false);
    }
  }

  return (
    <section className="kuzram-card" aria-labelledby="kuzram-facts-title">
      <h3 id="kuzram-facts-title">Фактические взрывы и подбор C(A)</h3>
      <p className="kuzram-facts-hint">
        Коронка, фактический удельный расход и фактический негабарит; порода, ВВ и уступ — с листа. Строки сохраняются
        за объектом и варианты сетки не пересчитывают — это делает только «Подобрать C(A) по факту».
      </p>
      <div className="kuzram-table-scroll">
        <table className="kuzram-table kuzram-facts">
          <thead>
            <tr>
              <th scope="col">Коронка, мм</th>
              <th scope="col">q факт, кг/м³</th>
              <th scope="col">Негабарит факт, %</th>
              <th scope="col" className="sep">До исправления, %</th>
              <th scope="col">Kuz-Ram, %</th>
              <th scope="col">C(A) строки</th>
              <th aria-label="Удалить" />
            </tr>
          </thead>
          <tbody>
            {facts.map((row, index) => {
              const result = calibration?.get(index);
              return (
                <tr key={index}>
                  {FACT_FIELDS.map((field) => (
                    <td key={field}>
                      <FactCell
                        field={field}
                        value={row[field]}
                        rowNumber={index + 1}
                        onCommit={(value) => update(facts.map((item, i) => (i === index ? { ...item, [field]: value } : item)))}
                      />
                    </td>
                  ))}
                  <td className="sep">{result ? ruNumber(result.legacy_oversize_pct, 2) : "—"}</td>
                  <td>{result ? ruNumber(result.model_oversize_pct, 2) : "—"}</td>
                  <td>
                    {!result ? "—" : result.rock_factor_correction === null ? (
                      <span title={result.note ?? undefined}>нет</span>
                    ) : (
                      trimmed(result.rock_factor_correction)
                    )}
                  </td>
                  <td>
                    <button
                      type="button"
                      className="kuzram-row-remove"
                      aria-label={`Удалить взрыв ${index + 1}`}
                      onClick={() => update(facts.filter((_, i) => i !== index))}
                    >
                      ×
                    </button>
                  </td>
                </tr>
              );
            })}
            {!facts.length && (
              <tr>
                <td colSpan={7} className="kuzram-empty">
                  Фактических взрывов пока нет.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
      {calibration && <p className="kuzram-facts-hint">Прогнозы моделей — при фактическом q и C(A), действовавшей до подбора.</p>}
      <div className="kuzram-facts-actions">
        <button
          type="button"
          className="secondary-button"
          disabled={facts.length >= MAX_FACTS}
          onClick={() => update([...facts, { crown_mm: defaultCrownMm, q_kg_m3: null, oversize_pct: null }])}
        >
          Добавить взрыв
        </button>
        <button type="button" className="primary-button" disabled={!complete.length || pending} onClick={() => void calibrate()}>
          {pending ? "Подбор C(A)…" : "Подобрать C(A) по факту"}
        </button>
        {facts.length >= MAX_FACTS && <span className="kuzram-facts-hint">Не больше {MAX_FACTS} строк.</span>}
      </div>
      {message && (
        <p className={`kuzram-message ${message.tone}`} role={message.tone === "error" ? "alert" : "status"}>
          {message.text}
        </p>
      )}
    </section>
  );
}
```

Run: `npm --prefix frontend test -- src/pages/calc/kuzram/KuzRamFacts.test.tsx`
Expected: 6 passed. Кнопка «Подобрать C(A) по факту» в ожидании меняет имя на «Подбор C(A)…» — в тестах к ней обращаются до нажатия.

- [ ] **Шаг 3. Окно показывает факты**

`KuzRamDialog.tsx`:
1. Импорты: `import type { BlastVariant, KuzRamCalibrateResponse, KuzRamFactInput, KuzRamSettings } from "../../../types";`, `import { KuzRamFacts } from "./KuzRamFacts";`, `import { completeFacts, kuzramSettingsOf, type KuzRamBlock, type KuzRamFact } from "./kuzramSettings";`.
2. В `KuzRamDialogProps` добавить:

```ts
  /** Правка строк фактов: лист сохраняет их, подбор q не запускается. */
  onFactsChange: (next: KuzRamFact[]) => void;
  /** Подбор C(A) по полным строкам — запрос `/blast/kuzram/calibrate` с данными листа. */
  onCalibrate: (facts: KuzRamFactInput[]) => Promise<KuzRamCalibrateResponse>;
```

3. В сигнатуру `CalcTab` добавить `onFactsChange, onCalibrate`; после `KuzRamBreakdown` добавить:

```tsx
        <KuzRamFacts
          facts={block.facts}
          onChange={onFactsChange}
          defaultCrownMm={selected?.crown_mm ?? null}
          onCalibrate={onCalibrate}
          onApplyCorrection={(value) => onSettingsChange({ ...kuzramSettingsOf(block), rock_factor_correction: value })}
        />
```

4. В `KuzRamDialog.test.tsx` в объект `props` хелпера добавить `onFactsChange: vi.fn(), onCalibrate: vi.fn(),` и тест:

```tsx
  it("фактические взрывы — в окне, правка строк уходит листу", () => {
    const props = renderDialog();
    fireEvent.click(screen.getByRole("button", { name: "Добавить взрыв" }));
    expect(props.onFactsChange).toHaveBeenCalledWith([{ crown_mm: null, q_kg_m3: null, oversize_pct: null }]);
  });
```

(в этом тесте `variants` пуст, поэтому коронка новой строки — `null`).

- [ ] **Шаг 4. Лист: сохранение фактов и подбор C(A)**

В `CalcPage.tsx`:
1. В импорт типов добавить `KuzRamFactInput`; в импорт из `./calc/kuzram/kuzramSettings` добавить `type KuzRamFact`.
2. После `setKuzramSettings` добавить:

```ts
  const setKuzramFacts = useCallback((facts: KuzRamFact[]) => {
    // Факты подбор не трогают: ни счётчик поколений, ни ревизия настроек не растут.
    setKuzram((current) => ({ ...current, facts }));
  }, []);
```

3. После `kuzramSource` добавить:

```ts
  const calibrateKuzram = (facts: KuzRamFactInput[]) => {
    if (!rock || !explosive) return Promise.reject(new Error("Выберите породу и ВВ на листе."));
    return api.calibrateKuzram({
      rock,
      explosive,
      lumpSize,
      benchHeight,
      overdrill,
      oversizeCoeff,
      spacing,
      kuzram: kuzramSettingsOf(kuzram),
      facts,
    });
  };
```

4. В `<KuzRamDialog …>` добавить `onFactsChange={setKuzramFacts}` и `onCalibrate={calibrateKuzram}`.

В `CalcPage.kuzram.test.tsx` добавить:

```tsx
describe("CalcPage: фактические взрывы", () => {
  it("правка фактов сохраняется за объектом и подбор не запускает", async () => {
    renderSheet();
    await loaded();
    fireEvent.click(screen.getByRole("button", { name: "Модель Kuz-Ram" }));
    fireEvent.click(within(dialog()).getByRole("button", { name: "Добавить взрыв" }));
    fireEvent.change(within(dialog()).getByLabelText("Фактический q, строка 1"), { target: { value: "1,3" } });
    await waitFor(() => expect(lastSaved()?.kuzram.facts).toEqual([{ crown_mm: 152, q_kg_m3: 1.3, oversize_pct: null }]), SLOW);
    await autosaveWindow();
    expect(api.optimize).toHaveBeenCalledTimes(1);
  });

  it("«Подобрать C(A) по факту» шлёт только полные строки и пересчитывает варианты с новой поправкой", async () => {
    const facts = [
      { crown_mm: 152, q_kg_m3: 1.3, oversize_pct: 8 },
      { crown_mm: 165, q_kg_m3: null, oversize_pct: null },
    ];
    api.calcInputs.mockResolvedValue({ work_object_name: OBJECT.name, inputs: savedInputs({ ...KUZRAM_DEFAULTS, facts }), updated_at: "then" });
    api.calibrateKuzram.mockResolvedValue({
      rows: [{ crown_mm: 152, q_kg_m3: 1.3, oversize_pct: 8, legacy_oversize_pct: 5.3, model_oversize_pct: 4.29, rock_factor_correction: 1.132, note: null }],
      rock_factor_correction: 1.132,
      used: 1,
      skipped: 0,
      model_version: "kuzram-cunningham-1.0",
    });
    renderSheet();
    await loaded();
    fireEvent.click(screen.getByRole("button", { name: "Модель Kuz-Ram" }));
    fireEvent.click(within(dialog()).getByRole("button", { name: "Подобрать C(A) по факту" }));
    await waitFor(() => expect(api.calibrateKuzram).toHaveBeenCalledTimes(1));
    const request = api.calibrateKuzram.mock.calls[0][0];
    expect(request.kuzram).toEqual(KUZRAM_DEFAULTS);
    expect(request.facts).toEqual([{ crown_mm: 152, q_kg_m3: 1.3, oversize_pct: 8 }]);
    await waitFor(() => expect(api.optimize).toHaveBeenCalledTimes(2), SLOW);
    expect(api.optimize.mock.calls[1][0].kuzram).toEqual({ ...KUZRAM_DEFAULTS, rock_factor_correction: 1.132 });
    expect(within(dialog()).getByText(/C\(A\) = 1,132 записана в настройки/)).toBeInTheDocument();
    expect(document.querySelector(".kuzram-caption")).toHaveTextContent("C(A) 1,132");
  });
});
```

- [ ] **Шаг 5. Стили**

В конец `frontend/src/styles/kuzram.css`:

```css
/* Фактические взрывы: правка на месте, подбор C(A). */
.kuzram-facts td { vertical-align:top; }
.kuzram-facts input { width:78px; height:26px; padding:0 6px; border:1px solid #ced9d3; border-radius:6px; background:#fff; color:#17231d; font-size:11px; text-align:right; font-variant-numeric:tabular-nums; }
.kuzram-facts .kuzram-field-error { max-width:160px; white-space:normal; text-align:left; }
.kuzram-row-remove { width:24px; height:24px; border:0; border-radius:6px; background:transparent; color:#9aa8a1; font-size:14px; line-height:1; }
.kuzram-row-remove:hover { background:#fce9e7; color:#9e3025; }
.kuzram-facts-hint { margin:0; color:#6e7c75; font-size:11px; }
.kuzram-facts-actions { display:flex; flex-wrap:wrap; align-items:center; gap:8px; }
.kuzram-message { margin:0; font-size:11px; }
.kuzram-message.ok { color:#1c5c40; }
.kuzram-message.warn { color:#745014; }
.kuzram-message.error { color:#9e3025; }
```

- [ ] **Шаг 6. Прогон и коммит**

Run: `npm --prefix frontend test` и `frontend/node_modules/.bin/tsc -p frontend/tsconfig.app.json`
Expected: всё зелёное.

```bash
git add frontend/src/pages/calc/kuzram/KuzRamFacts.tsx frontend/src/pages/calc/kuzram/KuzRamFacts.test.tsx \
  frontend/src/pages/calc/kuzram/KuzRamDialog.tsx frontend/src/pages/calc/kuzram/KuzRamDialog.test.tsx \
  frontend/src/pages/CalcPage.tsx frontend/src/pages/CalcPage.kuzram.test.tsx frontend/src/styles/kuzram.css
git commit -m "Kuz-Ram UI: фактические взрывы и подбор C(A)

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 8. Вкладка «Как пользоваться» и проверка примеров

**Файлы:**
- Создать: `frontend/src/pages/calc/kuzram/helpExamples.json`, `tests/test_kuzram_help_examples.py`
- Создать: `frontend/src/pages/calc/kuzram/KuzRamHelp.tsx`, `KuzRamHelp.test.tsx`
- Изменить: `frontend/src/pages/calc/kuzram/KuzRamDialog.tsx`, `KuzRamDialog.test.tsx` (вкладки)
- Изменить: `frontend/src/styles/kuzram.css`

**Интерфейсы:**
- Потребляет: `ruNumber`, `trimmed`, `gridText`, `qDeltaText` (Task 1).
- Производит: `KuzRamHelp()`; вкладки окна с `role="tab"`/`role="tabpanel"` и именами «Расчёт», «Как пользоваться».

- [ ] **Шаг 1. Примеры и Python-тест**

`frontend/src/pages/calc/kuzram/helpExamples.json` (цифры сверены с моделью PR 1 при подготовке плана):

```json
{
  "source": {
    "rock": { "name": "Габбро-диабаз", "density_t_m3": 2.9, "ucs_mpa": 168, "fissuring_ff": 2.2 },
    "explosive": { "name": "ЭВЕРСИН Э-100", "density_t_m3": 1.12, "power_mj_kg": 2.99 },
    "target": { "lump_size_mm": 400, "overdrill_m": 1, "hole_oversize_coeff": 1.05, "spacing_coeff_m": 1.25, "bench_height_m": 10 },
    "max_oversize_threshold_pct": 5
  },
  "basic": {
    "crown_mm": 152,
    "kuzram": { "q_kg_m3": 1.26, "grid_a_m": 4.42, "grid_b_m": 3.54, "oversize_pct": 4.98, "reached": true },
    "legacy": { "q_kg_m3": 1.34, "grid_a_m": 4.29, "grid_b_m": 3.43, "oversize_pct": 5.0, "reached": true }
  },
  "calibration": {
    "facts": [
      { "crown_mm": 130, "q_kg_m3": 1.2, "oversize_pct": 8.5 },
      { "crown_mm": 152, "q_kg_m3": 1.3, "oversize_pct": 8.0 },
      { "crown_mm": 165, "q_kg_m3": 1.35, "oversize_pct": 7.5 }
    ],
    "rows": [
      { "model_oversize_pct": 4.72, "rock_factor_correction": 1.128 },
      { "model_oversize_pct": 4.29, "rock_factor_correction": 1.132 },
      { "model_oversize_pct": 4.16, "rock_factor_correction": 1.121 }
    ],
    "rock_factor_correction": 1.127,
    "crown_mm": 152,
    "after": { "q_kg_m3": 1.45, "grid_a_m": 4.12, "grid_b_m": 3.3 }
  },
  "methods": {
    "crown_mm": 152,
    "rows": [
      { "rock_factor_method": "rmd50", "rmd": 50, "rock_factor_a": 6.37, "q_kg_m3": 1.26, "grid_a_m": 4.42, "grid_b_m": 3.54 },
      { "rock_factor_method": "rmd10", "rmd": 10, "rock_factor_a": 3.97, "q_kg_m3": 0.74, "grid_a_m": 5.78, "grid_b_m": 4.62 },
      { "rock_factor_method": "joint_factor", "rmd": 100, "rock_factor_a": 9.37, "q_kg_m3": 1.98, "grid_a_m": 3.52, "grid_b_m": 2.82 }
    ]
  },
  "not_reached": {
    "crown_mm": 250,
    "low": { "q_max_kg_m3": 1.5, "q_kg_m3": 1.5, "oversize_pct": 5.4, "reached": false },
    "raised": { "q_max_kg_m3": 2, "q_kg_m3": 1.53, "oversize_pct": 4.93, "reached": true }
  },
  "joint_switch": {
    "fissuring_ff": 0.3,
    "crown_mm": 152,
    "joint_spacing_m": 3.33,
    "before": { "q_kg_m3": 1.6, "reduced_pattern_m": 3.51, "jps": 80, "rock_factor_a": 9.37, "oversize_pct": 11.48 },
    "after": { "q_kg_m3": 1.61, "reduced_pattern_m": 3.5, "jps": 50, "rock_factor_a": 7.57, "oversize_pct": 4.0 }
  }
}
```

`tests/test_kuzram_help_examples.py`:

```python
"""Цифры примеров справки «Модель Kuz-Ram» совпадают с моделью.

Вкладка «Как пользоваться» (frontend/src/pages/calc/kuzram/KuzRamHelp.tsx)
показывает примеры из helpExamples.json; тест пересчитывает каждый пример
сервисом подбора и калибровки. Изменилась модель — тест падает, и справка
не расходится с расчётом.
"""
from __future__ import annotations

import json
import unittest
from pathlib import Path

from api.schemas.blast import BlastOptimizeRequest, BlastOptimizeVariant, KuzRamCalibrateRequest
from api.services.blast_service import calibrate_kuzram, optimize_blast
from api.services.converters import blast_request_to_engine_inputs
from Blast import BlastEngine
from simulation.fragmentation.cunningham import KuzRamSettings

EXAMPLES = (
    Path(__file__).resolve().parents[1] / "frontend" / "src" / "pages" / "calc" / "kuzram" / "helpExamples.json"
)


class KuzRamHelpExamplesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.examples = json.loads(EXAMPLES.read_text(encoding="utf-8"))
        cls.source = cls.examples["source"]

    def _request(self, crown_mm: float, kuzram: dict | None = None, rock: dict | None = None) -> BlastOptimizeRequest:
        return BlastOptimizeRequest(
            rock=rock or self.source["rock"],
            explosive=self.source["explosive"],
            target=self.source["target"],
            crown_diameters_mm=[crown_mm],
            max_oversize_threshold_pct=self.source["max_oversize_threshold_pct"],
            kuzram=kuzram,
        )

    def _variant(self, crown_mm: float, kuzram: dict | None = None, rock: dict | None = None) -> BlastOptimizeVariant:
        return optimize_blast(self._request(crown_mm, kuzram, rock)).variants[0]

    def test_basic_example(self) -> None:
        example = self.examples["basic"]
        variant = self._variant(example["crown_mm"])
        legacy = variant.legacy
        self.assertEqual(
            {
                "q_kg_m3": variant.specific_q_kg_m3,
                "grid_a_m": variant.grid_a_m,
                "grid_b_m": variant.grid_b_m,
                "oversize_pct": variant.oversize_pct,
                "reached": variant.reached,
            },
            example["kuzram"],
        )
        self.assertEqual(
            {
                "q_kg_m3": legacy.specific_q_kg_m3,
                "grid_a_m": legacy.grid_a_m,
                "grid_b_m": legacy.grid_b_m,
                "oversize_pct": legacy.oversize_pct,
                "reached": legacy.reached,
            },
            example["legacy"],
        )

    def test_calibration_example(self) -> None:
        example = self.examples["calibration"]
        # Справка показывает «до подбора» по базовому примеру — коронка должна совпадать.
        self.assertEqual(example["crown_mm"], self.examples["basic"]["crown_mm"])
        response = calibrate_kuzram(
            KuzRamCalibrateRequest(
                rock=self.source["rock"],
                explosive=self.source["explosive"],
                target=self.source["target"],
                facts=example["facts"],
            )
        )
        self.assertEqual(
            [
                {"model_oversize_pct": row.model_oversize_pct, "rock_factor_correction": row.rock_factor_correction}
                for row in response.rows
            ],
            example["rows"],
        )
        self.assertEqual(response.rock_factor_correction, example["rock_factor_correction"])
        self.assertEqual(response.skipped, 0)
        after = self._variant(example["crown_mm"], {"rock_factor_correction": response.rock_factor_correction})
        self.assertEqual(
            {"q_kg_m3": after.specific_q_kg_m3, "grid_a_m": after.grid_a_m, "grid_b_m": after.grid_b_m},
            example["after"],
        )

    def test_rock_factor_methods_example(self) -> None:
        example = self.examples["methods"]
        for row in example["rows"]:
            with self.subTest(method=row["rock_factor_method"]):
                variant = self._variant(example["crown_mm"], {"rock_factor_method": row["rock_factor_method"]})
                self.assertEqual(
                    {
                        "rock_factor_method": row["rock_factor_method"],
                        "rmd": variant.details.rock_factor.rmd,
                        "rock_factor_a": round(variant.details.rock_factor_a, 2),
                        "q_kg_m3": variant.specific_q_kg_m3,
                        "grid_a_m": variant.grid_a_m,
                        "grid_b_m": variant.grid_b_m,
                    },
                    row,
                )

    def test_not_reached_example(self) -> None:
        example = self.examples["not_reached"]
        for key in ("low", "raised"):
            expected = example[key]
            with self.subTest(case=key):
                variant = self._variant(example["crown_mm"], {"q_max_kg_m3": expected["q_max_kg_m3"]})
                self.assertEqual(
                    {
                        "q_max_kg_m3": expected["q_max_kg_m3"],
                        "q_kg_m3": variant.specific_q_kg_m3,
                        "oversize_pct": variant.oversize_pct,
                        "reached": variant.reached,
                    },
                    expected,
                )

    def test_joint_switch_example(self) -> None:
        example = self.examples["joint_switch"]
        rock = {**self.source["rock"], "fissuring_ff": example["fissuring_ff"]}
        settings = {"rock_factor_method": "joint_factor"}
        after = self._variant(example["crown_mm"], settings, rock)
        breakdown = after.details.rock_factor
        self.assertEqual(round(breakdown.joint_spacing_m, 2), example["joint_spacing_m"])
        self.assertEqual(
            {
                "q_kg_m3": after.specific_q_kg_m3,
                "reduced_pattern_m": round(breakdown.reduced_pattern_m, 2),
                "jps": breakdown.jps,
                "rock_factor_a": round(after.details.rock_factor_a, 2),
                "oversize_pct": after.oversize_pct,
            },
            example["after"],
        )
        # Шаг перебора назад: та же коронка при q на 0,01 меньше — до переключения JPS.
        engine = BlastEngine(*blast_request_to_engine_inputs(self._request(example["crown_mm"], settings, rock)))
        before_q = round(after.specific_q_kg_m3 - 0.01, 2)
        point = engine.kuzram_point(example["crown_mm"], before_q, KuzRamSettings(**settings))
        self.assertEqual(
            {
                "q_kg_m3": before_q,
                "reduced_pattern_m": round(point.rock_factor.reduced_pattern_m, 2),
                "jps": point.rock_factor.jps,
                "rock_factor_a": round(point.rock_factor_a, 2),
                "oversize_pct": round(point.oversize_pct, 2),
            },
            example["before"],
        )
```

Run: `../../../.venv/bin/python -m pytest tests/test_kuzram_help_examples.py -q -p no:cacheprovider`
Expected: 5 passed (5 subtests). Проверка, что тест ловит расхождение: временно поменяйте `"q_kg_m3": 1.26` в `basic.kuzram` на `1.27` — `test_basic_example` падает; верните.

- [ ] **Шаг 2. Падающие тесты справки и вкладок**

`frontend/src/pages/calc/kuzram/KuzRamHelp.test.tsx`:

```tsx
// @vitest-environment jsdom
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { ruNumber } from "../../../lib/format";
import { KuzRamHelp } from "./KuzRamHelp";
import examples from "./helpExamples.json";
import { gridText, trimmed } from "./kuzramFormat";

afterEach(cleanup);

describe("KuzRamHelp", () => {
  it("разделы справки", () => {
    render(<KuzRamHelp />);
    for (const title of ["Что делает модель", "Порядок работы", "Настройки", "Как читать результаты", "Примеры"]) {
      expect(screen.getByRole("heading", { name: title })).toBeInTheDocument();
    }
    expect(screen.getByText("Формулы и источники")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /20 years on/ })).toHaveAttribute("href", expect.stringContaining("smctesting.com"));
  });

  it("цифры примеров — из helpExamples.json", () => {
    render(<KuzRamHelp />);
    const basic = screen.getByRole("region", { name: "Базовый расчёт" });
    expect(basic).toHaveTextContent(`q ${ruNumber(examples.basic.kuzram.q_kg_m3, 2)} кг/м³`);
    expect(basic).toHaveTextContent("q 1,26 кг/м³, сетка 4,42 × 3,54 м");
    expect(basic).toHaveTextContent("−6 %");

    const calibration = screen.getByRole("region", { name: "Подбор C(A) по фактическим взрывам" });
    expect(calibration).toHaveTextContent("условные");
    expect(calibration).toHaveTextContent(`C(A) = ${trimmed(examples.calibration.rock_factor_correction)}`);
    expect(calibration).toHaveTextContent(`${gridText(examples.basic.kuzram.grid_a_m, examples.basic.kuzram.grid_b_m)} → 4,12 × 3,30 м`);

    const methods = screen.getByRole("region", { name: "Выбор способа расчёта A" });
    expect(methods).toHaveTextContent("По трещиноватости (JF)");
    expect(methods).toHaveTextContent("1,98");

    const notReached = screen.getByRole("region", { name: "Порог не достигнут" });
    expect(notReached).toHaveTextContent("негабарит 5,40 %");
    expect(notReached).toHaveTextContent("q 1,53 и негабарит 4,93 %");

    const jointSwitch = screen.getByRole("region", { name: "Скачок при способе JF" });
    expect(jointSwitch).toHaveTextContent("11,48 %");
    expect(jointSwitch).toHaveTextContent("4,00 %");
    expect(jointSwitch).toHaveTextContent("JPS падает до 50");
  });
});
```

В `KuzRamDialog.test.tsx` добавить тест:

```tsx
  it("вкладка «Как пользоваться» показывает справку", () => {
    renderDialog();
    expect(screen.getByRole("tab", { name: "Расчёт" })).toHaveAttribute("aria-selected", "true");
    fireEvent.click(screen.getByRole("tab", { name: "Как пользоваться" }));
    expect(screen.getByRole("tab", { name: "Как пользоваться" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("tabpanel", { name: "Как пользоваться" })).toHaveTextContent("Что делает модель");
    expect(screen.queryByLabelText("Поправка C(A)")).not.toBeInTheDocument();
  });
```

Run: `npm --prefix frontend test -- src/pages/calc/kuzram/KuzRamHelp.test.tsx src/pages/calc/kuzram/KuzRamDialog.test.tsx`
Expected: FAIL.

- [ ] **Шаг 3. `KuzRamHelp.tsx`**

```tsx
import { ruNumber } from "../../../lib/format";
import examples from "./helpExamples.json";
import { gridText, qDeltaText, trimmed } from "./kuzramFormat";

const SOURCE_URL =
  "https://www.smctesting.com/documents/mine-to-mill/The%20kuz%20ram%20fragmentation%20model%2020%20years%20on.pdf";

const METHOD_NAMES: Record<string, string> = {
  rmd50: "Монолитный массив (RMD 50)",
  rmd10: "Раздробленная порода (RMD 10)",
  joint_factor: "По трещиноватости (JF)",
};

const FORMULAS = `d   = коронка / 1000 · коэффициент разбуривания          [м]
L   = 0,8 · (H + перебур)                                   [м]
Q   = π·d²/4 · ρВВ · 1000 · L                               [кг]
V   = Q / q;   W = √(V / (a/W · H));   a = a/W · W;   b = W
RE  = теплота взрыва / 4,184                                (к тротилу)

RDI = 25·ρ − 50;   HF = UCS / 5
RMD = 50 | 10 | JF;   JF = JCF·JPS + JPA
JPS = 10 при s < 0,1 м; 20 при s < 0,3 м; 80 при s < 0,95·P; иначе 50
      s = 1 / трещиноватость;   P = √(a·b)
A   = 0,06 · (RMD + RDI + HF) · C(A)
x50 = A · q^−0,8 · Q^(1/6) · RE^(−e) · 10                  [мм], e = 19/20 или 19/30
n   = (2,2 − 14·W/d[мм]) · √((1 + a/W)/2) · (1 − σ/W) · 1,1^0,1 · min(1, L/H) · C(n),  n ≥ 0,1
xc  = x50 / (ln 2)^(1/n)
негабарит = exp(−(кусок / xc)^n) · 100 %`;

/**
 * Вкладка «Как пользоваться» окна «Модель Kuz-Ram». Цифры примеров — из
 * helpExamples.json; tests/test_kuzram_help_examples.py пересчитывает их
 * моделью, поэтому текст не расходится с расчётом. Меняя пример, меняйте
 * JSON, а не цифры в тексте.
 */
export function KuzRamHelp() {
  const { source, basic, calibration, methods, not_reached: notReached, joint_switch: jointSwitch } = examples;
  const methodQs = methods.rows.map((row) => row.q_kg_m3);
  const jf = methods.rows.find((row) => row.rock_factor_method === "joint_factor");

  return (
    <div className="kuzram-help">
      <section aria-labelledby="kuzram-help-what">
        <h3 id="kuzram-help-what">Что делает модель</h3>
        <p>
          Для каждой выбранной коронки модель ищет наименьший удельный расход ВВ q, при котором доля негабарита не
          превышает допустимую. q перебирается с шагом 0,01 кг/м³ от 0,10 до верхней границы перебора (по умолчанию 2,0).
        </p>
        <p>
          При каждом q считаются заряд скважины Q, объём на скважину V = Q/q и сетка: линия наименьшего сопротивления W и
          шаг a = a/W · W. Затем по формулам Kuz-Ram — средний кусок x50 (половина массы взорванной породы мельче него),
          индекс равномерности n (чем он больше, тем однороднее куски) и негабарит — доля кусков крупнее кондиционного.
        </p>
        <p>
          Формулы — по статье К. Каннингема «The Kuz-Ram fragmentation model — 20 years on» (2005). Всё считает сервер;
          окно показывает результат и хранит настройки за объектом работ.
        </p>
      </section>

      <section aria-labelledby="kuzram-help-order">
        <h3 id="kuzram-help-order">Порядок работы</h3>
        <ol>
          <li>На листе задайте породу, ВВ, уступ, перебур, кондиционный кусок, допустимый негабарит и коронки — окно берёт исходные данные оттуда.</li>
          <li>Выберите способ расчёта фактора породы A. Без документации трещин оставьте «Монолитный массив (RMD 50)».</li>
          <li>Сравните столбцы «Kuz-Ram» и «До исправления». Большая разница — повод проверить свойства породы.</li>
          <li>Внесите фактические взрывы: коронку, фактический удельный расход и фактический негабарит.</li>
          <li>Нажмите «Подобрать C(A) по факту» — поправка запишется в настройки объекта, варианты пересчитаются.</li>
          <li>Проверьте сетку выбранной коронки и разбор расчёта.</li>
          <li>Нажмите «Перенести в проект» или сохраните паспорт — как обычно на листе.</li>
        </ol>
      </section>

      <section aria-labelledby="kuzram-help-settings">
        <h3 id="kuzram-help-settings">Настройки</h3>
        <dl>
          <dt>Фактор породы A</dt>
          <dd>
            Насколько порода сопротивляется дроблению: A = 0,06·(RMD + RDI + HF). RDI = 25·ρ − 50 учитывает плотность,
            HF = UCS/5 — прочность на сжатие. RMD описывает массив: 50 — монолитный (трещины реже скважин), 10 —
            раздробленный; JF — по трещиноватости из справочника пород. «Задать вручную» — A из опыта или отчёта, от 0,5
            до 30. Умолчание — RMD 50.
          </dd>
          <dt>Как выбрать способ A</dt>
          <dd>
            Без достоверной документации трещин и их ориентации оставляйте RMD 50 и уточняйте поправку C(A) по
            фактическим взрывам. JF выбирайте, только когда трещины задокументированы: способ чувствителен к шагу трещин
            и может дать q заметно выше (пример ниже).
          </dd>
          <dt>Состояние трещин JCF и ориентация JPA</dt>
          <dd>
            Только для способа JF: JF = JCF·JPS + JPA. JCF: плотные — 1, раскрытые — 1,5, с заполнителем — 2. JPA — по
            Каннингему: падение трещин в сторону откоса — 20, простирание поперёк откоса — 30, падение в массив — 40.
            JPS модель берёт из шага трещин и сетки.
          </dd>
          <dt>Поправка C(A)</dt>
          <dd>
            Множитель к A, от 0,1 до 10, умолчание 1 — без поправки. Больше 1 — порода дробится хуже, чем предсказывает
            формула, и q растёт. Подбирается по фактическим взрывам.
          </dd>
          <dt>Показатель при силе ВВ</dt>
          <dd>19/20 — Каннингем, 1987 (умолчание); 19/30 — вариант 1983 года, как в расчёте «до исправления». С 19/30 сила ВВ меньше влияет на средний кусок.</dd>
          <dt>Отклонение бурения σ, м</dt>
          <dd>Стандартное отклонение забоя скважины от проекта, от 0 до 2 м, умолчание 0. Чем больше σ, тем неоднороднее куски и тем выше q.</dd>
          <dt>Поправка C(n)</dt>
          <dd>Множитель к индексу равномерности n, от 0,5 до 2, умолчание 1. Меняйте, только если есть данные рассева.</dd>
          <dt>Верхняя граница перебора q</dt>
          <dd>От 0,5 до 5 кг/м³, умолчание 2,0. Если порог негабарита не достигнут и на ней, q остаётся на границе, а в таблицах появляется значок «!».</dd>
        </dl>
      </section>

      <section aria-labelledby="kuzram-help-read">
        <h3 id="kuzram-help-read">Как читать результаты</h3>
        <ul>
          <li><b>Сводка</b> — выбранная коронка: q, сетка и негабарит обеих моделей и разница q в процентах (Kuz-Ram относительно «до исправления»).</li>
          <li><b>Таблица</b> — строка на коронку; выбор строки меняет выбранную коронку и на листе.</li>
          <li><b>«До исправления»</b> — прежний расчёт: фактор A по формуле 1983 года, диаметр в индексе n в метрах (n всегда 0,8), перебор q от 0,30 до 1,50. Нужен на переходный период, чтобы видеть, насколько изменились рекомендации.</li>
          <li><b>Значок «!»</b> — порог негабарита не достигнут даже на верхней границе перебора q. Если округлённый негабарит совпал с порогом, вместо числа стоит «> порога».</li>
          <li><b>«≤ 0,10»</b> — порог выполнен уже при наименьшем q; меньшие значения модель не проверяет.</li>
          <li><b>График</b> — q по коронкам обеих моделей; полая точка — порог не достигнут, ромб — фактический взрыв.</li>
          <li><b>Разбор расчёта</b> — промежуточные величины выбранной коронки для обеих моделей. У n два числа «сырое → принятое»: если формула даёт меньше 0,1 (нереальная геометрия или σ не меньше W), принимается 0,1; в расчёте «до исправления» n не бывает меньше 0,8.</li>
          <li><b>W/d</b> — ЛНС к диаметру скважины. Каннингем рекомендует 25–35; выше 35 окно предупреждает, что сетка редкая для этого диаметра и прогноз менее надёжен. Подбор q это не ограничивает, а ниже 25 для крепких пород — обычная сетка.</li>
        </ul>
      </section>

      <section aria-labelledby="kuzram-help-examples">
        <h3 id="kuzram-help-examples">Примеры</h3>
        <p>
          Во всех примерах, кроме последнего: {source.rock.name}, {source.explosive.name}, уступ {trimmed(source.target.bench_height_m)} м,
          перебур {trimmed(source.target.overdrill_m)} м, кондиционный кусок {trimmed(source.target.lump_size_mm)} мм, допустимый
          негабарит {trimmed(source.max_oversize_threshold_pct)} %.
        </p>

        <section aria-labelledby="kuzram-example-basic">
          <h4 id="kuzram-example-basic">Базовый расчёт</h4>
          <p>
            Коронка {trimmed(basic.crown_mm)} мм. Kuz-Ram: q {ruNumber(basic.kuzram.q_kg_m3, 2)} кг/м³, сетка{" "}
            {gridText(basic.kuzram.grid_a_m, basic.kuzram.grid_b_m)} м, негабарит {ruNumber(basic.kuzram.oversize_pct, 2)} %. До
            исправления: q {ruNumber(basic.legacy.q_kg_m3, 2)} кг/м³, сетка {gridText(basic.legacy.grid_a_m, basic.legacy.grid_b_m)} м,
            негабарит {ruNumber(basic.legacy.oversize_pct, 2)} %. Разница q — {qDeltaText(basic.kuzram.q_kg_m3, basic.legacy.q_kg_m3)}:
            две главные ошибки прежнего расчёта почти гасят друг друга, поэтому для монолитного массива рекомендации меняются мало.
          </p>
        </section>

        <section aria-labelledby="kuzram-example-calibration">
          <h4 id="kuzram-example-calibration">Подбор C(A) по фактическим взрывам</h4>
          <p className="example-note">Взрывы условные — только для иллюстрации.</p>
          <table className="kuzram-table">
            <thead>
              <tr>
                <th scope="col">Коронка, мм</th>
                <th scope="col">q факт, кг/м³</th>
                <th scope="col">Негабарит факт, %</th>
                <th scope="col">Kuz-Ram при C(A) = 1, %</th>
                <th scope="col">C(A) строки</th>
              </tr>
            </thead>
            <tbody>
              {calibration.facts.map((fact, index) => (
                <tr key={index}>
                  <td>{trimmed(fact.crown_mm)}</td>
                  <td>{ruNumber(fact.q_kg_m3, 2)}</td>
                  <td>{ruNumber(fact.oversize_pct, 1)}</td>
                  <td>{ruNumber(calibration.rows[index].model_oversize_pct, 2)}</td>
                  <td>{trimmed(calibration.rows[index].rock_factor_correction)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p>
            Фактический негабарит выше прогноза — порода дробится хуже, чем по формуле, поэтому C(A) больше 1. Итог —
            среднее геометрическое по строкам: C(A) = {trimmed(calibration.rock_factor_correction)}. После подбора коронка{" "}
            {trimmed(calibration.crown_mm)} мм: q {ruNumber(basic.kuzram.q_kg_m3, 2)} → {ruNumber(calibration.after.q_kg_m3, 2)} кг/м³,
            сетка {gridText(basic.kuzram.grid_a_m, basic.kuzram.grid_b_m)} → {gridText(calibration.after.grid_a_m, calibration.after.grid_b_m)} м.
          </p>
        </section>

        <section aria-labelledby="kuzram-example-methods">
          <h4 id="kuzram-example-methods">Выбор способа расчёта A</h4>
          <table className="kuzram-table">
            <thead>
              <tr>
                <th scope="col">Способ</th>
                <th scope="col">RMD или JF</th>
                <th scope="col">A</th>
                <th scope="col">q, кг/м³</th>
                <th scope="col">Сетка a × b, м</th>
              </tr>
            </thead>
            <tbody>
              {methods.rows.map((row) => (
                <tr key={row.rock_factor_method}>
                  <td>{METHOD_NAMES[row.rock_factor_method]}</td>
                  <td>{trimmed(row.rmd)}</td>
                  <td>{ruNumber(row.rock_factor_a, 2)}</td>
                  <td>{ruNumber(row.q_kg_m3, 2)}</td>
                  <td>{gridText(row.grid_a_m, row.grid_b_m)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p>
            Коронка {trimmed(methods.crown_mm)} мм, те же исходные данные — а q различается в{" "}
            {trimmed(Math.max(...methodQs) / Math.min(...methodQs), 1)} раза: всё решает оценка массива. Трещиноватость{" "}
            {trimmed(source.rock.fissuring_ff)} на 1 м из справочника даёт JF = {trimmed(jf?.rmd ?? 0)} против RMD 50 у
            монолитного массива. Без документации трещин надёжнее RMD 50 и поправка C(A) по фактическим взрывам.
          </p>
        </section>

        <section aria-labelledby="kuzram-example-not-reached">
          <h4 id="kuzram-example-not-reached">Порог не достигнут</h4>
          <p>
            Коронка {trimmed(notReached.crown_mm)} мм, верхняя граница перебора {trimmed(notReached.low.q_max_kg_m3)} кг/м³: даже при q{" "}
            {ruNumber(notReached.low.q_kg_m3, 2)} негабарит {ruNumber(notReached.low.oversize_pct, 2)} % больше допустимых{" "}
            {trimmed(source.max_oversize_threshold_pct)} % — в таблицах значок «!», точка на графике полая. Что делать: поднять
            верхнюю границу (при {trimmed(notReached.raised.q_max_kg_m3)} подбор даёт q {ruNumber(notReached.raised.q_kg_m3, 2)} и
            негабарит {ruNumber(notReached.raised.oversize_pct, 2)} %), взять меньшую коронку или проверить порог и кондиционный кусок.
          </p>
        </section>

        <section aria-labelledby="kuzram-example-joint-switch">
          <h4 id="kuzram-example-joint-switch">Скачок при способе JF</h4>
          <p>
            Тот же {source.rock.name.toLowerCase()}, но с редкими трещинами — {trimmed(jointSwitch.fissuring_ff)} на 1 м (шаг{" "}
            {ruNumber(jointSwitch.joint_spacing_m, 2)} м), коронка {trimmed(jointSwitch.crown_mm)} мм, способ JF. При q{" "}
            {ruNumber(jointSwitch.before.q_kg_m3, 2)} приведённая сетка P = {ruNumber(jointSwitch.before.reduced_pattern_m, 2)} м,
            шаг трещин меньше 0,95·P — JPS = {trimmed(jointSwitch.before.jps)}, A = {ruNumber(jointSwitch.before.rock_factor_a, 2)},
            негабарит {ruNumber(jointSwitch.before.oversize_pct, 2)} %. При q {ruNumber(jointSwitch.after.q_kg_m3, 2)} сетка чуть
            плотнее, P = {ruNumber(jointSwitch.after.reduced_pattern_m, 2)} м, и 0,95·P становится меньше шага трещин: JPS падает до{" "}
            {trimmed(jointSwitch.after.jps)}, A — до {ruNumber(jointSwitch.after.rock_factor_a, 2)}, и негабарит скачком падает до{" "}
            {ruNumber(jointSwitch.after.oversize_pct, 2)} %. Подбор останавливается на {ruNumber(jointSwitch.after.q_kg_m3, 2)}:
            негабарит заметно ниже порога, а q соседних коронок может отличаться сильнее обычного. Это свойство ступенчатой
            таблицы JPS у Каннингема, а не ошибка расчёта.
          </p>
        </section>
      </section>

      <details>
        <summary>Формулы и источники</summary>
        <pre>{FORMULAS}</pre>
        <p>
          Источник: C. V. B. Cunningham,{" "}
          <a href={SOURCE_URL} target="_blank" rel="noreferrer">
            «The Kuz-Ram fragmentation model — 20 years on»
          </a>
          , EFEE, 2005. Вкладка «Проектирование», отчёты и ML-калибровка пока считают по прежней модели.
        </p>
      </details>
    </div>
  );
}
```

Регион примера называется по заголовку `h4` через `aria-labelledby`; в тесте имена регионов: «Базовый расчёт», «Подбор C(A) по фактическим взрывам», «Выбор способа расчёта A», «Порог не достигнут», «Скачок при способе JF». Проверка «q 1,26 кг/м³, сетка 4,42 × 3,54 м» зависит от пробелов между выражениями JSX: `{" "}` стоит там, где строка переносится между словом и выражением.

- [ ] **Шаг 4. Вкладки окна**

`KuzRamDialog.tsx`:
1. Импорты: `import { useEffect, useId, useRef, useState, type MouseEvent } from "react";`, `import { KuzRamHelp } from "./KuzRamHelp";`.
2. В `KuzRamDialog` после `const ref = …` добавить:

```ts
  const [tab, setTab] = useState<"calc" | "help">("calc");
  const ids = useId();
  const tabId = (name: "calc" | "help") => `${ids}-tab-${name}`;
  const panelId = (name: "calc" | "help") => `${ids}-panel-${name}`;
```

3. Заголовок окна заменить на:

```tsx
      <header>
        <b id="kuzram-dialog-title">Модель Kuz-Ram</b>
        <div className="kuzram-tabs" role="tablist" aria-label="Разделы окна">
          {(["calc", "help"] as const).map((name) => (
            <button
              key={name}
              type="button"
              role="tab"
              id={tabId(name)}
              aria-controls={panelId(name)}
              aria-selected={tab === name}
              onClick={() => setTab(name)}
            >
              {name === "calc" ? "Расчёт" : "Как пользоваться"}
            </button>
          ))}
        </div>
        <button type="button" className="kuzram-close" aria-label="Закрыть" onClick={onClose}>
          ×
        </button>
      </header>
```

4. Строку `{open && <CalcTab {...props} />}` заменить на:

```tsx
      {open &&
        (tab === "calc" ? (
          <div role="tabpanel" id={panelId("calc")} aria-labelledby={tabId("calc")} className="kuzram-body kuzram-calc">
            <CalcTab {...props} />
          </div>
        ) : (
          <div role="tabpanel" id={panelId("help")} aria-labelledby={tabId("help")} className="kuzram-body">
            <KuzRamHelp />
          </div>
        ))}
```

5. В `CalcTab` внешний `<div className="kuzram-body kuzram-calc">` заменить фрагментом `<>…</>` (обёртка теперь — панель вкладки).

- [ ] **Шаг 5. Стили**

В конец `frontend/src/styles/kuzram.css`:

```css
/* Вкладки окна и справка «Как пользоваться». */
.kuzram-tabs { display:flex; gap:4px; padding:3px; border-radius:9px; background:#f0f4f2; }
.kuzram-tabs [role="tab"] { height:26px; padding:0 12px; border:0; border-radius:7px; background:transparent; color:#3b4b43; font-size:11.5px; }
.kuzram-tabs [role="tab"][aria-selected="true"] { background:#fff; color:#17231d; box-shadow:0 1px 3px rgba(15,35,26,.12); }
.kuzram-help { max-width:860px; color:#3b4b43; font-size:12.5px; line-height:1.6; }
.kuzram-help h3 { margin:18px 0 6px; color:#17231d; font-size:13px; }
.kuzram-help section:first-child > h3 { margin-top:0; }
.kuzram-help h4 { margin:12px 0 4px; color:#17231d; font-size:12px; }
.kuzram-help p { margin:0 0 8px; }
.kuzram-help ul, .kuzram-help ol { display:grid; gap:5px; margin:0 0 8px; padding-left:20px; }
.kuzram-help dl { display:grid; gap:4px; margin:0 0 8px; }
.kuzram-help dt { margin-top:6px; color:#17231d; font-weight:var(--font-weight-strong); }
.kuzram-help dd { margin:0; }
.kuzram-help .kuzram-table { width:auto; margin:6px 0 10px; }
.kuzram-help .example-note { color:#745014; }
.kuzram-help details { margin-top:14px; }
.kuzram-help summary { color:#17231d; cursor:pointer; font-weight:var(--font-weight-strong); }
.kuzram-help pre { margin:8px 0; padding:10px 12px; overflow-x:auto; border:1px solid #e2e8e5; border-radius:8px; background:#f6f9f7; color:#17231d; font:11.5px/1.6 ui-monospace,SFMono-Regular,Menlo,monospace; }
@media (max-width:760px) { .kuzram-tabs { order:3; width:100%; } .kuzram-tabs [role="tab"] { flex:1; } }
```

- [ ] **Шаг 6. Прогон и коммит**

Run: `npm --prefix frontend test`, `frontend/node_modules/.bin/tsc -p frontend/tsconfig.app.json`, `../../../.venv/bin/python -m pytest tests/test_kuzram_help_examples.py tests/test_kuzram_frontend_contract.py -q -p no:cacheprovider`
Expected: всё зелёное.

```bash
git add frontend/src/pages/calc/kuzram/helpExamples.json tests/test_kuzram_help_examples.py \
  frontend/src/pages/calc/kuzram/KuzRamHelp.tsx frontend/src/pages/calc/kuzram/KuzRamHelp.test.tsx \
  frontend/src/pages/calc/kuzram/KuzRamDialog.tsx frontend/src/pages/calc/kuzram/KuzRamDialog.test.tsx \
  frontend/src/styles/kuzram.css
git commit -m "Kuz-Ram UI: вкладка «Как пользоваться» и проверка примеров

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 9. Справка листа, CLAUDE.md и документация

**Файлы:**
- Изменить: `frontend/src/pages/calc/CalcHelp.tsx`, `frontend/src/pages/calc/CalcHelp.test.tsx`
- Изменить: `CLAUDE.md`, `Docs/KUZRAM_MODEL.md`, `Docs/plans/2026-09-21-kuzram-model-design.md`

- [ ] **Шаг 1. Падающий тест справки листа**

В `CalcHelp.test.tsx` добавить:

```tsx
  it("описывает модель Kuz-Ram, кнопку окна и значок «!»", () => {
    render(<CalcHelp />);
    expect(screen.getByText(/Кнопка в заголовке панели «Варианты сетки» открывает окно/)).toBeInTheDocument();
    expect(screen.getByText(/вкладке окна «Как пользоваться»/)).toBeInTheDocument();
    expect(screen.getByText(/значок «!» — порог не\s+достигнут даже на верхней/)).toBeInTheDocument();
  });
```

Run: `npm --prefix frontend test -- src/pages/calc/CalcHelp.test.tsx`
Expected: FAIL.

- [ ] **Шаг 2. `CalcHelp.tsx`**

1. В docstring последнюю фразу заменить на: «Формулировки про q и негабарит пересказывают `Blast.py::optimize_blast` (модель Kuz-Ram по Каннингему, окно `calc/kuzram/`) — при изменении подбора сверьте текст.»
2. После пункта «Варианты сетки.» добавить:

```tsx
            <li>
              <b>Модель Kuz-Ram.</b> Кнопка в заголовке панели «Варианты сетки» открывает окно
              модели подбора q: способ расчёта фактора породы и поправки, сравнение с расчётом
              «до исправления», график, разбор расчёта и фактические взрывы для подбора поправки
              C(A). Настройки и взрывы сохраняются за объектом; если настройки отличаются от
              умолчаний, рядом с кнопкой видна их краткая подпись. Подробная справка с примерами —
              на вкладке окна «Как пользоваться».
            </li>
```

3. Пункт про q заменить на:

```tsx
            <li>
              <b>q, кг/м³</b> — удельный расход ВВ: наименьший, при котором доля
              негабарита не превышает допустимую. Подбирается по модели Kuz-Ram (Каннингем,
              2005) с шагом 0,01 от 0,10 до верхней границы перебора; «≤ 0.10» — порог выполнен
              уже на нижней границе, значок «!» — порог не достигнут даже на верхней.
            </li>
```

4. Пункт про негабарит дополнить: «Доля кусков крупнее кондиционного размера; «> 5» — порог не достигнут, хотя округлённое значение с ним совпадает.»

Run: `npm --prefix frontend test -- src/pages/calc/CalcHelp.test.tsx`
Expected: 3 passed.

- [ ] **Шаг 3. `CLAUDE.md`**

После раздела «Модель себестоимости блока (TASK-007)» добавить:

```markdown
## Модель подбора q (Kuz-Ram)

Лист «Расчёт» подбирает q по Каннингему: формулы — `simulation/fragmentation/cunningham.py`, подбор — `Blast.py::optimize_blast`, окно «Модель Kuz-Ram» — `frontend/src/pages/calc/kuzram/`; «Проектирование», отчёты и ML пока на `simulation/fragmentation/kuzram.py`, подробности — `Docs/KUZRAM_MODEL.md`.
```

- [ ] **Шаг 4. `Docs/KUZRAM_MODEL.md`**

В конец файла добавить раздел:

```markdown
## Окно на листе «Расчёт»

Кнопка «Модель Kuz-Ram» в панели «Варианты сетки» открывает окно
(`frontend/src/pages/calc/kuzram/`): настройки, сравнение с расчётом «до
исправления», график q(d), разбор расчёта, фактические взрывы с подбором C(A)
и справка «Как пользоваться».

- Настройки и фактические взрывы хранятся за объектом работ — блок `kuzram` в
  настройках листа (`calc-inputs`, `version` 1). Без блока — умолчания; числа
  при чтении приводятся к границам. Перед `/blast/optimize` и
  `/blast/kuzram/calibrate` фронт отрезает `facts` (схема настроек —
  `extra=forbid`), в калибровку идут только полные строки в границах.
- Правка настроек перезапускает подбор (пауза 300 мс), правка фактов — нет.
- Умолчания и границы фронт берёт из `kuzramContract.json`; совпадение с
  `cunningham.py` и схемами API проверяет `tests/test_kuzram_frontend_contract.py`.
- Цифры примеров справки — `helpExamples.json`, их пересчитывает моделью
  `tests/test_kuzram_help_examples.py`.
- W/d (B/d у Каннингема) выше 35 — предупреждение в окне; подбор q не
  ограничивается. Ниже 25 не предупреждаем: для крепких пород это обычная
  сетка (решение владельца от 21.09.2026).
- JPA по Каннингему 2005, §4.1.1.3: 20 — падение трещин в сторону откоса, 30 —
  простирание поперёк откоса, 40 — падение в массив («out of face» —
  плоскость трещины, продолженная из откоса, уходит вверх). Формулировки ждут
  подтверждения технолога.
```

- [ ] **Шаг 5. Спецификация**

В `Docs/plans/2026-09-21-kuzram-model-design.md` абзац «Подписи JPA (формулировка — на подтверждение технологу): 40 — …, 30 — …, 20 — ….» заменить на:

```markdown
Подписи JPA — по Каннингему 2005, §4.1.1.3 («out of face» — плоскость трещины,
продолженная из откоса, уходит вверх): 20 — «падение трещин в сторону откоса»,
30 — «простирание поперёк откоса», 40 — «падение трещин в массив». Первая
редакция спецификации давала их наоборот; владелец 21.09.2026 выбрал вариант
статьи. Формулировки — на подтверждение технологу.
```

В разделе «Решения владельца» добавить пункт 7:

```markdown
7. W/d (B/d у Каннингема) — **предупреждать только выше 35**, подбор q не
   ограничивать (21.09.2026): для габбро-диабаза W/d = 20–23,5 на всех
   коронках, и предупреждение «ниже 25» горело бы всегда.
```

- [ ] **Шаг 6. Прогон и коммит**

Run: `npm --prefix frontend test -- src/pages/calc/CalcHelp.test.tsx`
Expected: зелёный.

```bash
git add frontend/src/pages/calc/CalcHelp.tsx frontend/src/pages/calc/CalcHelp.test.tsx CLAUDE.md \
  Docs/KUZRAM_MODEL.md Docs/plans/2026-09-21-kuzram-model-design.md
git commit -m "Kuz-Ram UI: справка листа, CLAUDE.md и документация

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 10. Проверка на стенде, ревью и черновик PR

Выполняет координатор, не субагент: нужны согласие пользователя на правку `.claude/`, браузер, `/code-review` и решения по PR.

- [ ] **Шаг 1. Полный прогон**

```bash
../../../.venv/bin/python -m pytest tests -q -p no:cacheprovider
npm --prefix frontend test
npm --prefix frontend run build
```

Expected: все Python-тесты зелёные (в PR 1 на 7dbeec8 — 1436, плюс 9 новых), все тесты фронта зелёные, сборка без ошибок.

- [ ] **Шаг 2. Стенд из worktree (с согласия пользователя)**

`preview_start` читает `.claude/launch.json` каталога, из которого запущена сессия, — это корень этого worktree. Спросить пользователя и после согласия:
1. Скопировать `/Users/apple/Documents/Проекты/BlastEX/.claude/stand/stand_app.py` в `.claude/stand/stand_app.py` этого worktree и заменить `REPO = Path("/Users/apple/Documents/Проекты/BlastEX")` на `REPO = Path(__file__).resolve().parents[2]`.
2. Проверить порты: `lsof -iTCP:8020 -sTCP:LISTEN` и `lsof -iTCP:5181 -sTCP:LISTEN`; если заняты — 8021/5182.
3. Создать `.claude/launch.json`:

```json
{
  "version": "0.0.1",
  "configurations": [
    {
      "name": "api-stand",
      "runtimeExecutable": "/Users/apple/Documents/Проекты/BlastEX/.venv/bin/python",
      "runtimeArgs": ["/Users/apple/Documents/Проекты/BlastEX/.claude/worktrees/dazzling-antonelli-bfc24e/.claude/stand/stand_app.py"],
      "port": 8020
    },
    {
      "name": "frontend-stand",
      "runtimeExecutable": "npm",
      "runtimeArgs": ["--prefix", "/Users/apple/Documents/Проекты/BlastEX/.claude/worktrees/dazzling-antonelli-bfc24e/frontend", "run", "dev", "--", "--port", "5181", "--strictPort"],
      "env": { "BLASTEX_API_URL": "http://127.0.0.1:8020" },
      "port": 5181
    }
  ]
}
```

4. `preview_start` с `api-stand`, затем `frontend-stand`.

- [ ] **Шаг 3. Сценарии в браузере — компьютер (1440 × 900) и телефон (375 × 812)**

1. Лист «Расчёт», объект, «Рассчитать варианты»: у «Модель Kuz-Ram» нет подписи; в таблице q без «!».
2. Окно: сводка, таблица, график, разбор; выбор строки в окне меняет выбранную строку на листе.
3. Способ JF → «Пересчёт…», цифры приглушены, затем новые; у кнопки подпись «JF».
4. Верхняя граница q 1,5 → у крупных коронок «!» в таблице листа и окна, полые точки на графике.
5. Порода «Известняк» (на листе) + RMD 10 → предупреждение W/d выше 35 под таблицей и в разборе.
6. Два факта + «Подобрать C(A) по факту» → сообщение, C(A) в поле и в подписи, варианты пересчитаны.
7. Вкладка «Как пользоваться»: разделы, примеры, формулы раскрываются.
8. Перезагрузка страницы → настройки и факты на месте.
9. Телефон: окно в одну колонку, таблицы прокручиваются внутри карточек, нет горизонтальной прокрутки страницы.

После проверки: `preview_stop` обоих серверов; удалить `.claude/launch.json` и `.claude/stand/` этого worktree (или оставить с согласия пользователя) — в git они не попадают.

- [ ] **Шаг 4. `/code-review` по всей ветке**

`/code-review` на диапазон `origin/feat/kuzram-model..HEAD`; всё найденное исправить отдельными коммитами, повторить полный прогон шага 1.

- [ ] **Шаг 5. Черновик PR и Codex**

```bash
git push -u origin feat/kuzram-model-ui
gh pr create --draft --base feat/kuzram-model --head feat/kuzram-model-ui --title "Модель Kuz-Ram, PR 2: окно на листе «Расчёт»"
```

Описание PR (по-русски): что сделано; решения владельца (W/d только выше 35; JPA по Каннингему — **на подтверждение технологу**); пример скачка JF с проверяемыми цифрами вместо 7,53 → 1,79; порядок слияния — PR 2 в `feat/kuzram-model`, затем #88 в `main` одной выкаткой; **не сливать без решения владельца**; последняя строка — `🤖 Generated with [Claude Code](https://claude.com/claude-code)`.

Затем комментарий `@codex review` (`gh pr comment <N> --body "@codex review"`) и чтение ответа: `gh api repos/dvotapi/BlastEX/pulls/<N>/comments` и `gh pr view <N> --comments`. Замечания разобрать (навык superpowers:receiving-code-review), исправить подтверждённые.

- [ ] **Шаг 6. Память**

Обновить `/Users/apple/.claude/projects/-Users-apple-Documents---------BlastEX/memory/kuzram-n-units-pr82.md` (номер PR 2, состояние, решения по W/d и JPA) и строку в `MEMORY.md`.
