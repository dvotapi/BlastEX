# Модель Kuz-Ram, PR 1 (сервер) — план реализации

> **Для агентов-исполнителей:** обязательный навык — superpowers:subagent-driven-development (рекомендуется) или superpowers:executing-plans. Шаги отмечаются чекбоксами (`- [ ]`).

**Цель:** подбор удельного расхода q на листе «Расчёт» считает по исправленной модели Kuz-Ram (Каннингем) с настройками; старый расчёт остаётся рядом для сравнения; появляется подбор C(A) по фактическим взрывам.

**Архитектура:** формулы Каннингема — чистые функции в новом модуле `simulation/fragmentation/cunningham.py`. `Blast.py` собирает из них подбор q (`optimize_blast`), а прежний расчёт без изменений переезжает в `optimize_blast_legacy`. API `/blast/optimize` принимает необязательные настройки и отдаёт оба результата с разбором; новый `/blast/kuzram/calibrate` подбирает C(A).

**Стек:** Python 3.12, FastAPI, Pydantic v2, unittest (запуск через pytest).

**Спецификация:** `Docs/plans/2026-09-21-kuzram-model-design.md` — читать вместе с планом.

## Общие ограничения

- Рабочая копия: `/Users/apple/Documents/Проекты/BlastEX/.claude/worktrees/kuzram-model`, ветка `feat/kuzram-model`. Все команды — из её корня.
- Python: `../../../.venv/bin/python` (venv основного чекаута). Тесты: `../../../.venv/bin/python -m pytest <путь> -q -p no:cacheprovider`.
- Исправленная модель применяется **только** к подбору q. `simulation/fragmentation/kuzram.py`, `kuznetsov.py`, вкладка «Проектирование», отчёты и `intelligence/` не меняются.
- Версия модели — строка `kuzram-cunningham-1.0`.
- Умолчания настроек: `rmd50`, A вручную 6,0, JCF 1, JPA 20, C(A) 1,0, показатель `19/20`, σ 0, C(n) 1,0, верхняя граница q 2,0.
- Границы: A вручную 0,5–30; C(A) 0,1–10; σ 0–2 м; C(n) 0,5–2; верхняя граница q 0,5–5. JCF ∈ {1; 1,5; 2}, JPA ∈ {20; 30; 40}.
- Перебор q новой модели: от 0,10 до верхней границы с шагом 0,01; негабарит сравнивается с порогом без округления; n не ниже 0,1.
- Старая модель — побитово как сейчас: q от 0,30 до 1,50 через `q += 0.01`, сравнение `round(негабарит, 2) <= порог`, n ≥ 0,8, диаметр в n в метрах.
- Сообщения об ошибках — по-русски. Комментарии и docstring — по-русски, в стиле соседнего кода.
- Коммиты заканчиваются строкой `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`.
- Ответ `/blast/optimize` обратно совместим: все прежние поля остаются, фронт PR 1 не меняет.

## Карта файлов

| Файл | Что делает |
|---|---|
| `tests/fixtures/blast_legacy_golden.json` (новый) | Снимок результатов `Blast.py` **до** правки: 30 случаев × 3 коронки |
| `tests/fixtures/kuzram_cunningham_golden.json` (новый) | Эталон Kuz-Ram из независимой реализации: 40 случаев × 3 коронки |
| `simulation/fragmentation/cunningham.py` (новый) | Настройки, фактор породы A, x50, n, негабарит, подбор C(A) |
| `tests/test_fragmentation_cunningham.py` (новый) | Тесты формул модуля |
| `Blast.py` | `BlastPoint`, `QSelection`, `legacy_point`, `optimize_blast_legacy`, `kuzram_point`, `optimize_blast`, `calibrate_rock_factor` |
| `tests/test_blast_optimizer.py` (новый) | Эталоны старой и новой модели, пример габбро, граница q, калибровка |
| `tests/test_fragmentation_engine.py` | Регрессионный тест `BlastEngine` под новый тип результата |
| `api/schemas/blast.py` | Схемы настроек, разбора, «до исправления», калибровки |
| `api/services/blast_service.py` | Сборка ответа подбора и калибровки |
| `api/services/converters.py` | Преобразование запроса калибровки во входы движка |
| `api/routers/blast.py` | `POST /blast/kuzram/calibrate` |
| `tests/test_api_blast_optimize.py` (новый) | Первые API-тесты подбора и калибровки |
| `README.md`, `Docs/KUZRAM_MODEL.md` (новый) | Описание модели и API |

---

### Задача 1. Эталоны до правки

Снимок старой модели нужно снять **до** любого изменения `Blast.py`, иначе сравнивать будет не с чем.

**Файлы:**
- Создать: `tests/fixtures/blast_legacy_golden.json`, `tests/fixtures/kuzram_cunningham_golden.json`
- Временный генератор (не коммитится): `<scratchpad>/gen_golden.py`, где `<scratchpad>` — временная папка сессии из системного промпта (не `/tmp` и не папка репозитория).

**Интерфейсы:**
- Производит: JSON вида `{"source": str, "cases": [...]}`. В каждом случае: `rock` {`density_t_m3`, `ucs_mpa`, `fissuring_ff`}, `explosive` {`density_t_m3`, `power_mj_kg`}, `target` {`lump_size_mm`, `overdrill_m`, `hole_oversize_coeff`, `spacing_coeff_m`, `bench_height_m`}, `threshold`; у эталона Kuz-Ram ещё `settings` (поля `KuzRamSettings`). Строки `rows`:
  - старая модель: `crown_mm`, `q`, `burden_m`, `x50_mm`, `oversize_pct` (округлены так же, как в `Blast.py`), `reached`;
  - Kuz-Ram: `crown_mm`, `q`, `burden_m`, `x50_mm`, `n`, `oversize_pct`, `rock_factor_a` (без округления), `reached`.

- [ ] **Шаг 1. Проверить, что `Blast.py` ещё не тронут**

Run: `git diff --stat origin/main -- Blast.py`
Expected: пустой вывод.

- [ ] **Шаг 2. Сохранить генератор во временную папку**

```python
"""Эталоны для тестов подбора q (одноразовый генератор, в репозиторий не входит).

legacy — результаты Blast.py ДО правки, снимаются с настоящего кода.
kuzram — независимая реализация Kuz-Ram по Каннингему (сверена с симулятором
https://claude.ai/artifact/YRWRbE1JRgbgWNU3AhoRyG), в семантике сервиса:
q от 0,10, n не ниже 0,1, без «A как в коде» и без старых вариантов n.

Запуск из корня репозитория:
    python gen_golden.py legacy > tests/fixtures/blast_legacy_golden.json
    python gen_golden.py kuzram > tests/fixtures/kuzram_cunningham_golden.json
"""
import json
import math
import random
import sys

CROWNS = [110, 152, 250]
ROCKS = [(2.9, 168.0, 2.2), (2.65, 150.0, 2.0), (2.5, 80.0, 1.5), (2.4, 100.0, 1.8)]
EXPLOSIVES = [(0.85, 3.76), (1.12, 2.99)]


def random_case(rnd):
    rock = rnd.choice(ROCKS)
    ex = rnd.choice(EXPLOSIVES)
    return {
        "rock": {
            "density_t_m3": rnd.choice([rock[0], round(rnd.uniform(2.1, 3.3), 3)]),
            "ucs_mpa": rnd.choice([rock[1], round(rnd.uniform(30, 260), 1)]),
            "fissuring_ff": rnd.choice([rock[2], 0.0, round(rnd.uniform(0.3, 12), 2)]),
        },
        "explosive": {"density_t_m3": ex[0], "power_mj_kg": ex[1]},
        "target": {
            "lump_size_mm": rnd.choice([300.0, 400.0, 500.0, 800.0, 1000.0]),
            "overdrill_m": rnd.choice([0.5, 1.0, 1.5, 2.0]),
            "hole_oversize_coeff": rnd.choice([1.0, 1.05, 1.1]),
            "spacing_coeff_m": rnd.choice([1.0, 1.1, 1.25, 1.4]),
            "bench_height_m": rnd.choice([5.0, 8.0, 10.0, 12.0, 15.0]),
        },
        "threshold": rnd.choice([2.0, 3.0, 5.0, 8.0, 10.0]),
    }


def random_settings(rnd):
    return {
        "rock_factor_method": rnd.choice(["rmd50", "rmd10", "joint_factor", "manual"]),
        "rock_factor_manual": round(rnd.uniform(2, 12), 3),
        "joint_condition": rnd.choice([1.0, 1.5, 2.0]),
        "joint_angle": rnd.choice([20, 30, 40]),
        "rock_factor_correction": rnd.choice([1.0, round(rnd.uniform(0.5, 2), 3)]),
        "strength_exponent": rnd.choice(["19/20", "19/30"]),
        "drill_deviation_m": rnd.choice([0.0, 0.2, 0.5]),
        "uniformity_correction": rnd.choice([1.0, round(rnd.uniform(0.8, 1.2), 3)]),
        "q_max_kg_m3": rnd.choice([1.5, 2.0, 3.0]),
    }


def legacy_cases():
    sys.path.insert(0, ".")
    from Blast import BlastEngine, ExplosiveProperties, RockProperties, TargetParams

    rnd = random.Random(20260921)
    cases = []
    for _ in range(30):
        c = random_case(rnd)
        engine = BlastEngine(
            RockProperties("r", c["rock"]["density_t_m3"], c["rock"]["ucs_mpa"], c["rock"]["fissuring_ff"]),
            ExplosiveProperties("e", c["explosive"]["density_t_m3"], c["explosive"]["power_mj_kg"]),
            TargetParams(hole_diameter_mm=0, **c["target"]),
        )
        rows = []
        for crown in CROWNS:
            r = engine.optimize_blast(crown, max_oversize_threshold=c["threshold"])
            rows.append({
                "crown_mm": crown, "q": r["q"], "burden_m": r["W_m"], "x50_mm": r["x50_mm"],
                "oversize_pct": r["oversize_pct"], "reached": "target_q" in r,
            })
        c["rows"] = rows
        cases.append(c)
    return cases


def kuzram_point(c, s, crown, q):
    rock, ex, t = c["rock"], c["explosive"], c["target"]
    d_m = crown / 1000 * t["hole_oversize_coeff"]
    depth = t["bench_height_m"] + t["overdrill_m"]
    charge_len = depth * 0.8
    charge = math.pi * d_m ** 2 / 4 * ex["density_t_m3"] * 1000 * charge_len
    m = t["spacing_coeff_m"]
    w = math.sqrt(charge / q / (m * t["bench_height_m"]))
    rdi = 25 * rock["density_t_m3"] - 50
    hf = rock["ucs_mpa"] / 5
    method = s["rock_factor_method"]
    if method == "manual":
        base = s["rock_factor_manual"]
    else:
        if method == "rmd50":
            rmd = 50.0
        elif method == "rmd10":
            rmd = 10.0
        elif rock["fissuring_ff"] <= 0:
            rmd = 50.0
        else:
            js = 1 / rock["fissuring_ff"]
            p = w * math.sqrt(m)
            jps = 10 if js < 0.1 else 20 if js < 0.3 else 80 if js < 0.95 * p else 50
            rmd = s["joint_condition"] * jps + s["joint_angle"]
        base = 0.06 * (rmd + rdi + hf)
    a = base * s["rock_factor_correction"]
    e = 19 / 20 if s["strength_exponent"] == "19/20" else 19 / 30
    re = ex["power_mj_kg"] / 4.184
    x50 = a * q ** -0.8 * charge ** (1 / 6) * re ** -e * 10
    lh = min(1.0, charge_len / t["bench_height_m"])
    n_raw = ((2.2 - 14 * w / (d_m * 1000)) * math.sqrt((1 + m) / 2) * (1 - s["drill_deviation_m"] / w)
             * 1.1 ** 0.1 * lh * s["uniformity_correction"])
    n = max(0.1, n_raw)
    xc = x50 / math.log(2) ** (1 / n)
    over = math.exp(-((t["lump_size_mm"] / xc) ** n)) * 100
    return {"q": q, "burden_m": w, "x50_mm": x50, "n": n, "oversize_pct": over, "rock_factor_a": a}


def kuzram_cases():
    rnd = random.Random(20260922)
    cases = []
    for _ in range(40):
        c = random_case(rnd)
        s = random_settings(rnd)
        rows = []
        for crown in CROWNS:
            last = round(s["q_max_kg_m3"] * 100)
            found = None
            for i in range(10, last + 1):
                p = kuzram_point(c, s, crown, i / 100)
                if p["oversize_pct"] <= c["threshold"]:
                    found = {**p, "reached": True}
                    break
            if found is None:
                found = {**kuzram_point(c, s, crown, last / 100), "reached": False}
            rows.append({"crown_mm": crown, **found})
        c["settings"] = s
        c["rows"] = rows
        cases.append(c)
    return cases


SOURCES = {
    "legacy": "Blast.py до исправления модели Kuz-Ram (origin/main a826a2b), seed 20260921",
    "kuzram": "Независимая реализация Kuz-Ram по Каннингему (EFEE 2005), сверенная с симулятором; seed 20260922",
}

if __name__ == "__main__":
    kind = sys.argv[1]
    cases = legacy_cases() if kind == "legacy" else kuzram_cases()
    json.dump({"source": SOURCES[kind], "cases": cases}, sys.stdout, ensure_ascii=False, indent=1)
    sys.stdout.write("\n")
```

- [ ] **Шаг 3. Снять эталоны**

Run:
```bash
../../../.venv/bin/python <scratchpad>/gen_golden.py legacy > tests/fixtures/blast_legacy_golden.json
../../../.venv/bin/python <scratchpad>/gen_golden.py kuzram > tests/fixtures/kuzram_cunningham_golden.json
```
Expected: два файла, 20–60 КБ каждый. Проверить, что в обоих есть строки с `"reached": false` (в старой около 16, в Kuz-Ram около 19): `grep -c '"reached": false' tests/fixtures/*_golden.json`.

- [ ] **Шаг 4. Коммит**

```bash
git add tests/fixtures/blast_legacy_golden.json tests/fixtures/kuzram_cunningham_golden.json
git commit -m "Kuz-Ram: эталоны подбора q до правки и независимой реализации

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Задача 2. Модуль формул Каннингема

**Файлы:**
- Создать: `simulation/fragmentation/cunningham.py`
- Тест: `tests/test_fragmentation_cunningham.py`

**Интерфейсы:**
- Использует: `simulation.fragmentation.distributions.rosin_rammler_characteristic_mm(x50_mm, n)`, `rosin_rammler_oversize_pct(x50_mm, n, lump_size_mm)`; `simulation.fragmentation.units.fragment_mm_from_cm(size_cm)`.
- Производит (нужно задаче 3):
  - `MODEL_VERSION: str = "kuzram-cunningham-1.0"`, `Q_MIN_KG_M3 = 0.10`, `MIN_UNIFORMITY_N = 0.1`;
  - `KuzRamSettings` (frozen dataclass, поля и умолчания — из общих ограничений; свойство `exponent -> float`; `ValueError` с русским текстом при нарушении границ);
  - `RockFactorBreakdown` (frozen: `method`, `rmd`, `rdi`, `hf`, `joint_spacing_m`, `reduced_pattern_m`, `jps`, `base`, `correction`; свойство `value = base * correction`);
  - `rock_factor(settings, *, ucs_mpa, density_t_m3, fissuring_per_m, burden_m, spacing_m) -> RockFactorBreakdown`;
  - `mean_fragment_mm(rock_factor_a, powder_factor_kg_m3, charge_mass_kg, re_weight, exponent) -> float`;
  - `Uniformity` (frozen: `raw`, `value`, `charge_to_bench`);
  - `uniformity_index(*, burden_m, hole_diameter_mm, spacing_to_burden, drill_deviation_m, charge_length_m, bench_height_m, correction) -> Uniformity`;
  - `oversize(x50_mm, n, lump_size_mm) -> tuple[float, float]` — (xc, негабарит %);
  - `solve_rock_factor_correction(oversize_at: Callable[[float], float], target_pct: float) -> float | None`.

- [ ] **Шаг 1. Написать падающий тест**

`tests/test_fragmentation_cunningham.py`:

```python
"""Kuz-Ram по Каннингему (EFEE 2005): фактор породы, x50, n, подбор C(A)."""
import math
import unittest

from simulation.fragmentation import cunningham as kr


class SettingsTests(unittest.TestCase):
    def test_defaults_are_massive_rock(self):
        s = kr.KuzRamSettings()
        self.assertEqual(s.rock_factor_method, "rmd50")
        self.assertEqual(s.strength_exponent, "19/20")
        self.assertAlmostEqual(s.exponent, 0.95)
        self.assertEqual(s.q_max_kg_m3, 2.0)
        self.assertEqual(kr.MODEL_VERSION, "kuzram-cunningham-1.0")

    def test_out_of_range_value_has_russian_message(self):
        with self.assertRaisesRegex(ValueError, r"Поправка C\(A\) — от 0,1 до 10\."):
            kr.KuzRamSettings(rock_factor_correction=12)
        with self.assertRaisesRegex(ValueError, r"Верхняя граница перебора q, кг/м³ — от 0,5 до 5\."):
            kr.KuzRamSettings(q_max_kg_m3=0.2)

    def test_unknown_choice_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "JPA"):
            kr.KuzRamSettings(joint_angle=25)
        with self.assertRaisesRegex(ValueError, "JCF"):
            kr.KuzRamSettings(joint_condition=3)
        with self.assertRaisesRegex(ValueError, "19/20 или 19/30"):
            kr.KuzRamSettings(strength_exponent="1/2")
        with self.assertRaisesRegex(ValueError, "способ"):
            kr.KuzRamSettings(rock_factor_method="code")


class RockFactorTests(unittest.TestCase):
    ROCK = dict(ucs_mpa=168.0, density_t_m3=2.9, fissuring_per_m=2.2, burden_m=3.54, spacing_m=4.425)

    def test_massive_rock(self):
        a = kr.rock_factor(kr.KuzRamSettings(), **self.ROCK)
        self.assertAlmostEqual(a.rdi, 22.5)
        self.assertAlmostEqual(a.hf, 33.6)
        self.assertEqual(a.rmd, 50.0)
        self.assertAlmostEqual(a.value, 0.06 * (50 + 22.5 + 33.6))

    def test_friable_rock_and_correction(self):
        settings = kr.KuzRamSettings(rock_factor_method="rmd10", rock_factor_correction=1.5)
        a = kr.rock_factor(settings, **self.ROCK)
        self.assertAlmostEqual(a.base, 0.06 * (10 + 22.5 + 33.6))
        self.assertAlmostEqual(a.value, a.base * 1.5)

    def test_manual(self):
        settings = kr.KuzRamSettings(rock_factor_method="manual", rock_factor_manual=7.5)
        a = kr.rock_factor(settings, **self.ROCK)
        self.assertIsNone(a.rmd)
        self.assertAlmostEqual(a.value, 7.5)

    def test_joint_factor_uses_spacing_bands(self):
        settings = kr.KuzRamSettings(rock_factor_method="joint_factor", joint_condition=1.5, joint_angle=40)
        # P = √(3,54 · 4,425) ≈ 3,96 м; шаг трещин = 1 / трещиноватость
        for fissuring, jps in [(20.0, 10.0), (5.0, 20.0), (2.2, 80.0), (0.2, 50.0)]:
            with self.subTest(fissuring=fissuring):
                a = kr.rock_factor(settings, **{**self.ROCK, "fissuring_per_m": fissuring})
                self.assertEqual(a.jps, jps)
                self.assertAlmostEqual(a.rmd, 1.5 * jps + 40)
                self.assertAlmostEqual(a.joint_spacing_m, 1 / fissuring)
                self.assertAlmostEqual(a.reduced_pattern_m, math.sqrt(3.54 * 4.425))

    def test_joint_factor_without_fissuring_is_massive(self):
        settings = kr.KuzRamSettings(rock_factor_method="joint_factor")
        a = kr.rock_factor(settings, **{**self.ROCK, "fissuring_per_m": 0.0})
        self.assertEqual(a.rmd, 50.0)
        self.assertIsNone(a.jps)


class MeanFragmentTests(unittest.TestCase):
    def test_formula_and_exponent(self):
        re = 2.99 / 4.184
        x = kr.mean_fragment_mm(6.366, 1.0, 197.19, re, 19 / 20)
        self.assertAlmostEqual(x, 6.366 * 197.19 ** (1 / 6) * re ** (-19 / 20) * 10)
        older = kr.mean_fragment_mm(6.366, 1.0, 197.19, re, 19 / 30)
        self.assertLess(older, x)  # RE < 1: чем больше показатель, тем крупнее x50


class UniformityTests(unittest.TestCase):
    def test_diameter_in_millimetres(self):
        n = kr.uniformity_index(
            burden_m=3.54, hole_diameter_mm=159.6, spacing_to_burden=1.25,
            drill_deviation_m=0.0, charge_length_m=8.8, bench_height_m=10.0, correction=1.0,
        )
        expected = (2.2 - 14 * 3.54 / 159.6) * math.sqrt(2.25 / 2) * 1.1 ** 0.1 * 0.88
        self.assertAlmostEqual(n.raw, expected)
        self.assertAlmostEqual(n.value, expected)
        self.assertAlmostEqual(n.charge_to_bench, 0.88)
        self.assertGreater(n.value, 1.7)

    def test_charge_longer_than_bench_is_capped(self):
        n = kr.uniformity_index(
            burden_m=3.0, hole_diameter_mm=150.0, spacing_to_burden=1.0,
            drill_deviation_m=0.0, charge_length_m=12.0, bench_height_m=10.0, correction=1.0,
        )
        self.assertEqual(n.charge_to_bench, 1.0)

    def test_drill_deviation_and_floor(self):
        base = dict(burden_m=3.0, hole_diameter_mm=150.0, spacing_to_burden=1.25,
                    charge_length_m=8.0, bench_height_m=10.0, correction=1.0)
        without = kr.uniformity_index(drill_deviation_m=0.0, **base)
        with_dev = kr.uniformity_index(drill_deviation_m=0.3, **base)
        self.assertAlmostEqual(with_dev.raw, without.raw * 0.9)
        crushed = kr.uniformity_index(drill_deviation_m=3.0, **base)
        self.assertLessEqual(crushed.raw, 0.0)
        self.assertEqual(crushed.value, kr.MIN_UNIFORMITY_N)


class SolveCorrectionTests(unittest.TestCase):
    @staticmethod
    def _oversize_at(correction: float) -> float:
        # негабарит растёт с C(A): x50 пропорционален поправке
        return kr.oversize(176.0 * correction, 1.78, 400.0)[1]

    def test_round_trip(self):
        target = self._oversize_at(1.3)
        self.assertAlmostEqual(kr.solve_rock_factor_correction(self._oversize_at, target), 1.3, places=6)

    def test_outside_settings_bounds_returns_none(self):
        # при C(A) = 10 негабарит ≈ 95 %, при C(A) = 0,1 — около 6·10⁻⁷⁷ %
        self.assertIsNone(kr.solve_rock_factor_correction(self._oversize_at, 99.9))
        self.assertIsNone(kr.solve_rock_factor_correction(self._oversize_at, 1e-100))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Шаг 2. Убедиться, что тест падает**

Run: `../../../.venv/bin/python -m pytest tests/test_fragmentation_cunningham.py -q -p no:cacheprovider`
Expected: FAIL — `ImportError: cannot import name 'cunningham'`.

- [ ] **Шаг 3. Написать модуль**

`simulation/fragmentation/cunningham.py`:

```python
"""Kuz-Ram по Каннингему для подбора удельного расхода на листе «Расчёт».

Формулы — C. V. B. Cunningham, «The Kuz-Ram fragmentation model — 20 years
on», EFEE 2005: фактор породы A = 0,06·(RMD + RDI + HF), средний кусок по
Кузнецову с показателем 19/20 (или 19/30, вариант 1983 года), индекс
равномерности n по варианту 1987 года с диаметром в миллиметрах.

Модуль применяется только к подбору q в Blast.py. Прогнозы вкладки
«Проектирование» по-прежнему считает simulation.fragmentation.kuzram.
"""
from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass

from simulation.fragmentation.distributions import (
    rosin_rammler_characteristic_mm,
    rosin_rammler_oversize_pct,
)
from simulation.fragmentation.units import fragment_mm_from_cm

MODEL_VERSION = "kuzram-cunningham-1.0"

ROCK_FACTOR_METHODS = ("rmd50", "rmd10", "joint_factor", "manual")
JOINT_CONDITIONS = (1.0, 1.5, 2.0)
JOINT_ANGLES = (20, 30, 40)
STRENGTH_EXPONENTS = {"19/20": 19.0 / 20.0, "19/30": 19.0 / 30.0}

# Поле настроек → (нижняя граница, верхняя граница, подпись в сообщении).
NUMERIC_BOUNDS: dict[str, tuple[float, float, str]] = {
    "rock_factor_manual": (0.5, 30.0, "Фактор породы A"),
    "rock_factor_correction": (0.1, 10.0, "Поправка C(A)"),
    "drill_deviation_m": (0.0, 2.0, "Отклонение бурения σ, м"),
    "uniformity_correction": (0.5, 2.0, "Поправка C(n)"),
    "q_max_kg_m3": (0.5, 5.0, "Верхняя граница перебора q, кг/м³"),
}

Q_MIN_KG_M3 = 0.10
MIN_UNIFORMITY_N = 0.1
RMD_MASSIVE = 50.0
RMD_FRIABLE = 10.0
# Один заряд в скважине: множитель (|BCL − CCL|/L + 0,1)^0,1 при BCL = 0.
SINGLE_CHARGE_FACTOR = 1.1 ** 0.1


def _number(value: float) -> str:
    return f"{value:g}".replace(".", ",")


@dataclass(frozen=True)
class KuzRamSettings:
    """Настройки модели; умолчания — монолитный массив без поправок."""

    rock_factor_method: str = "rmd50"
    rock_factor_manual: float = 6.0
    joint_condition: float = 1.0
    joint_angle: int = 20
    rock_factor_correction: float = 1.0
    strength_exponent: str = "19/20"
    drill_deviation_m: float = 0.0
    uniformity_correction: float = 1.0
    q_max_kg_m3: float = 2.0

    def __post_init__(self) -> None:
        if self.rock_factor_method not in ROCK_FACTOR_METHODS:
            raise ValueError(f"Неизвестный способ расчёта фактора породы: {self.rock_factor_method}.")
        if self.strength_exponent not in STRENGTH_EXPONENTS:
            raise ValueError("Показатель при силе ВВ — 19/20 или 19/30.")
        if float(self.joint_condition) not in JOINT_CONDITIONS:
            raise ValueError("Состояние трещин JCF — 1; 1,5 или 2.")
        if float(self.joint_angle) not in JOINT_ANGLES:
            raise ValueError("Ориентация трещин JPA — 20, 30 или 40.")
        for name, (low, high, label) in NUMERIC_BOUNDS.items():
            value = float(getattr(self, name))
            if not math.isfinite(value) or not low <= value <= high:
                raise ValueError(f"{label} — от {_number(low)} до {_number(high)}.")

    @property
    def exponent(self) -> float:
        return STRENGTH_EXPONENTS[self.strength_exponent]


@dataclass(frozen=True)
class RockFactorBreakdown:
    """Состав фактора породы A: слагаемые, сумма до поправки и поправка C(A)."""

    method: str
    rmd: float | None
    rdi: float | None
    hf: float | None
    joint_spacing_m: float | None
    reduced_pattern_m: float | None
    jps: float | None
    base: float
    correction: float

    @property
    def value(self) -> float:
        return self.base * self.correction


def joint_plane_spacing_factor(joint_spacing_m: float, reduced_pattern_m: float) -> float:
    """JPS по Каннингему 2005: шаг трещин относительно приведённой сетки P."""
    if joint_spacing_m < 0.1:
        return 10.0
    if joint_spacing_m < 0.3:
        return 20.0
    if joint_spacing_m < 0.95 * reduced_pattern_m:
        return 80.0
    return 50.0


def rock_factor(
    settings: KuzRamSettings,
    *,
    ucs_mpa: float,
    density_t_m3: float,
    fissuring_per_m: float,
    burden_m: float,
    spacing_m: float,
) -> RockFactorBreakdown:
    """A = 0,06·(RMD + RDI + HF)·C(A); при ручном вводе A = заданное·C(A).

    RDI = 25·ρ − 50 (ρ в т/м³), HF = UCS/5 (модуля упругости в данных нет).
    Для трещиноватого массива RMD заменяет JF = JCF·JPS + JPA; без трещин —
    монолитный массив.
    """
    correction = float(settings.rock_factor_correction)
    if settings.rock_factor_method == "manual":
        return RockFactorBreakdown(
            "manual", None, None, None, None, None, None, float(settings.rock_factor_manual), correction
        )
    rdi = 25.0 * density_t_m3 - 50.0
    hf = ucs_mpa / 5.0
    joint_spacing = reduced_pattern = jps = None
    if settings.rock_factor_method == "rmd10":
        rmd = RMD_FRIABLE
    elif settings.rock_factor_method == "joint_factor" and fissuring_per_m > 0:
        joint_spacing = 1.0 / fissuring_per_m
        reduced_pattern = math.sqrt(burden_m * spacing_m)
        jps = joint_plane_spacing_factor(joint_spacing, reduced_pattern)
        rmd = float(settings.joint_condition) * jps + float(settings.joint_angle)
    else:
        rmd = RMD_MASSIVE
    return RockFactorBreakdown(
        settings.rock_factor_method, rmd, rdi, hf, joint_spacing, reduced_pattern, jps,
        0.06 * (rmd + rdi + hf), correction,
    )


def mean_fragment_mm(
    rock_factor_a: float,
    powder_factor_kg_m3: float,
    charge_mass_kg: float,
    re_weight: float,
    exponent: float,
) -> float:
    """x50 = A·q^−0,8·Q^(1/6)·RE^(−e): формула даёт сантиметры, результат — мм."""
    x50_cm = (
        rock_factor_a
        * powder_factor_kg_m3 ** -0.8
        * charge_mass_kg ** (1.0 / 6.0)
        * re_weight ** (-exponent)
    )
    return fragment_mm_from_cm(x50_cm)


@dataclass(frozen=True)
class Uniformity:
    """Индекс равномерности: по формуле, принятый (не ниже 0,1) и L/H."""

    raw: float
    value: float
    charge_to_bench: float


def uniformity_index(
    *,
    burden_m: float,
    hole_diameter_mm: float,
    spacing_to_burden: float,
    drill_deviation_m: float,
    charge_length_m: float,
    bench_height_m: float,
    correction: float,
) -> Uniformity:
    """n = (2,2 − 14·W/d)·√((1 + a/W)/2)·(1 − σ/W)·1,1^0,1·(L/H)·C(n).

    W, σ, L, H — метры, d — миллиметры (Каннингем 1987). L/H не больше 1.
    """
    charge_to_bench = min(1.0, charge_length_m / bench_height_m)
    raw = (
        (2.2 - 14.0 * burden_m / hole_diameter_mm)
        * math.sqrt((1.0 + spacing_to_burden) / 2.0)
        * (1.0 - drill_deviation_m / burden_m)
        * SINGLE_CHARGE_FACTOR
        * charge_to_bench
        * correction
    )
    return Uniformity(raw=raw, value=max(MIN_UNIFORMITY_N, raw), charge_to_bench=charge_to_bench)


def oversize(x50_mm: float, n: float, lump_size_mm: float) -> tuple[float, float]:
    """Характерный размер xc (мм) и доля кусков крупнее кондиционного, % (Розин–Раммлер)."""
    return (
        rosin_rammler_characteristic_mm(x50_mm, n),
        rosin_rammler_oversize_pct(x50_mm, n, lump_size_mm),
    )


def solve_rock_factor_correction(
    oversize_at: Callable[[float], float],
    target_pct: float,
    *,
    iterations: int = 80,
) -> float | None:
    """C(A), при котором oversize_at(C(A)) равен target_pct; None — если вне 0,1–10.

    Негабарит растёт с C(A) (средний кусок крупнее), поэтому достаточно
    бисекции по ln C(A) в границах поправки из настроек.
    """
    low, high, _label = NUMERIC_BOUNDS["rock_factor_correction"]
    if oversize_at(low) > target_pct or oversize_at(high) < target_pct:
        return None
    lo, hi = math.log(low), math.log(high)
    for _ in range(iterations):
        mid = (lo + hi) / 2.0
        if oversize_at(math.exp(mid)) > target_pct:
            hi = mid
        else:
            lo = mid
    return math.exp((lo + hi) / 2.0)
```

- [ ] **Шаг 4. Тест проходит**

Run: `../../../.venv/bin/python -m pytest tests/test_fragmentation_cunningham.py -q -p no:cacheprovider`
Expected: PASS, 14 тестов.

- [ ] **Шаг 5. Коммит**

```bash
git add simulation/fragmentation/cunningham.py tests/test_fragmentation_cunningham.py
git commit -m "Kuz-Ram: формулы Каннингема для подбора q (фактор A, x50, n, C(A))

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Задача 3. Подбор q в `Blast.py`: новая модель и расчёт «до исправления»

**Файлы:**
- Изменить: `Blast.py` (весь движок, строки 1–160)
- Создать тест: `tests/test_blast_optimizer.py`
- Изменить: `tests/test_fragmentation_engine.py:193-205` (класс `BlastEngineRegressionTests`)

**Интерфейсы:**
- Использует из задачи 2: `KuzRamSettings`, `rock_factor`, `mean_fragment_mm`, `uniformity_index`, `oversize`, `solve_rock_factor_correction`, `Q_MIN_KG_M3`, `RockFactorBreakdown`.
- Производит (нужно задаче 4):
  - `BlastPoint` (frozen): `q_kg_m3`, `hole_diameter_mm`, `charge_length_m`, `charge_mass_kg`, `volume_per_hole_m3`, `burden_m`, `spacing_m`, `rock_factor_a`, `rock_factor: RockFactorBreakdown | None`, `re_weight`, `strength_exponent: str`, `x50_mm`, `uniformity_n_raw`, `uniformity_n`, `charge_to_bench: float | None`, `characteristic_size_mm`, `oversize_pct` — все без округления;
  - `QSelection` (frozen): `point: BlastPoint`, `reached: bool`;
  - `BlastEngine.legacy_point(diameter_mm, q) -> BlastPoint`;
  - `BlastEngine.optimize_blast_legacy(diameter_mm, max_oversize_threshold=5.0) -> QSelection`;
  - `BlastEngine.kuzram_point(diameter_mm, q, settings) -> BlastPoint`;
  - `BlastEngine.optimize_blast(diameter_mm, max_oversize_threshold=5.0, settings=None) -> QSelection`;
  - `BlastEngine.calibrate_rock_factor(diameter_mm, q, oversize_pct, settings) -> float | None`.

- [ ] **Шаг 1. Написать падающий тест**

`tests/test_blast_optimizer.py`:

```python
"""Подбор q в Blast.py: Kuz-Ram по Каннингему и расчёт «до исправления»."""
import json
import math
import unittest
from pathlib import Path

from Blast import BlastEngine, ExplosiveProperties, RockProperties, TargetParams
from simulation.fragmentation import cunningham as kr

FIXTURES = Path(__file__).parent / "fixtures"


def _engine(case: dict) -> BlastEngine:
    rock, ex = case["rock"], case["explosive"]
    return BlastEngine(
        RockProperties("r", rock["density_t_m3"], rock["ucs_mpa"], rock["fissuring_ff"]),
        ExplosiveProperties("e", ex["density_t_m3"], ex["power_mj_kg"]),
        TargetParams(hole_diameter_mm=0, **case["target"]),
    )


def _gabbro() -> BlastEngine:
    return BlastEngine(
        RockProperties("Габбро-диабаз", 2.9, 168, 2.2),
        ExplosiveProperties("ЭВЕРСИН Э-100", 1.12, 2.99),
        TargetParams(lump_size_mm=400, hole_diameter_mm=0, bench_height_m=10.0),
    )


class LegacyOptimizerTests(unittest.TestCase):
    def test_matches_blast_py_before_the_fix(self):
        data = json.loads((FIXTURES / "blast_legacy_golden.json").read_text(encoding="utf-8"))
        for case in data["cases"]:
            engine = _engine(case)
            for row in case["rows"]:
                with self.subTest(crown=row["crown_mm"], target=case["target"]):
                    result = engine.optimize_blast_legacy(row["crown_mm"], case["threshold"])
                    self.assertEqual(round(result.point.q_kg_m3, 2), row["q"])
                    self.assertEqual(round(result.point.burden_m, 2), row["burden_m"])
                    self.assertEqual(round(result.point.x50_mm, 1), row["x50_mm"])
                    self.assertEqual(round(result.point.oversize_pct, 2), row["oversize_pct"])
                    self.assertEqual(result.reached, row["reached"])

    def test_legacy_n_is_clamped_by_metre_diameter(self):
        result = _gabbro().optimize_blast_legacy(152, 5.0)
        self.assertEqual(result.point.uniformity_n, 0.8)
        self.assertLess(result.point.uniformity_n_raw, -300)
        self.assertEqual(round(result.point.q_kg_m3, 2), 1.34)
        self.assertIsNone(result.point.rock_factor)
        self.assertEqual(result.point.strength_exponent, "19/30")


class KuzRamOptimizerTests(unittest.TestCase):
    FIELDS = [
        ("burden_m", "burden_m"),
        ("x50_mm", "x50_mm"),
        ("uniformity_n", "n"),
        ("oversize_pct", "oversize_pct"),
        ("rock_factor_a", "rock_factor_a"),
    ]

    def test_matches_reference_implementation(self):
        data = json.loads((FIXTURES / "kuzram_cunningham_golden.json").read_text(encoding="utf-8"))
        for case in data["cases"]:
            engine = _engine(case)
            settings = kr.KuzRamSettings(**case["settings"])
            for row in case["rows"]:
                with self.subTest(crown=row["crown_mm"], settings=case["settings"]):
                    result = engine.optimize_blast(row["crown_mm"], case["threshold"], settings)
                    self.assertAlmostEqual(result.point.q_kg_m3, row["q"], places=9)
                    self.assertEqual(result.reached, row["reached"])
                    for field, key in self.FIELDS:
                        self.assertTrue(
                            math.isclose(getattr(result.point, field), row[key], rel_tol=1e-9, abs_tol=1e-12),
                            f"{field}: {getattr(result.point, field)} != {row[key]}",
                        )

    def test_gabbro_example(self):
        result = _gabbro().optimize_blast(152, 5.0)
        point = result.point
        self.assertTrue(result.reached)
        self.assertEqual(round(point.q_kg_m3, 2), 1.26)
        self.assertEqual(round(point.burden_m, 2), 3.54)
        self.assertAlmostEqual(point.rock_factor_a, 6.366)
        self.assertEqual(point.rock_factor.method, "rmd50")
        self.assertEqual(point.strength_exponent, "19/20")
        self.assertAlmostEqual(point.charge_to_bench, 0.88)
        self.assertAlmostEqual(point.hole_diameter_mm, 159.6)

    def test_q_can_go_below_old_floor(self):
        soft = BlastEngine(
            RockProperties("Песчаник", 2.4, 100, 1.8),
            ExplosiveProperties("Гранулит-РП", 0.85, 3.76),
            TargetParams(lump_size_mm=800, hole_diameter_mm=0, bench_height_m=10.0),
        )
        result = soft.optimize_blast(110, 10.0, kr.KuzRamSettings(rock_factor_method="rmd10"))
        self.assertTrue(result.reached)
        self.assertAlmostEqual(result.point.q_kg_m3, 0.12)

    def test_not_reached_returns_upper_bound(self):
        result = _gabbro().optimize_blast(250, 5.0, kr.KuzRamSettings(q_max_kg_m3=1.5))
        self.assertFalse(result.reached)
        self.assertEqual(result.point.q_kg_m3, 1.5)
        self.assertAlmostEqual(result.point.oversize_pct, 5.40, places=2)

    def test_calibration_round_trip(self):
        engine = _gabbro()
        truth = kr.KuzRamSettings(rock_factor_correction=1.3)
        oversize = engine.kuzram_point(152, 1.1, truth).oversize_pct
        found = engine.calibrate_rock_factor(152, 1.1, oversize, kr.KuzRamSettings())
        self.assertAlmostEqual(found, 1.3, places=6)

    def test_calibration_outside_bounds(self):
        self.assertIsNone(_gabbro().calibrate_rock_factor(152, 1.1, 99.99, kr.KuzRamSettings()))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Шаг 2. Убедиться, что тест падает**

Run: `../../../.venv/bin/python -m pytest tests/test_blast_optimizer.py -q -p no:cacheprovider`
Expected: FAIL — `AttributeError: 'BlastEngine' object has no attribute 'optimize_blast_legacy'`.

- [ ] **Шаг 3. Переписать движок `Blast.py`**

Блок описания данных (`RockProperties`, `ExplosiveProperties`, `TargetParams`, `CROWNS_MM`) не меняется. Импорты в начале файла заменить на:

```python
import math  # Импортируем модуль математики (нужен для ПИ и возведения в степень)
from dataclasses import dataclass, replace  # Структуры данных и копия с изменённым полем

from simulation.fragmentation import cunningham as kr
from simulation.fragmentation.distributions import (
    rosin_rammler_characteristic_mm,
    rosin_rammler_oversize_pct,
)
from simulation.fragmentation.kuznetsov import kuznetsov_x50_mm, rock_factor_A
from simulation.fragmentation.kuzram import cunningham_uniformity_n
from simulation.fragmentation.units import relative_weight_strength
```

Комментарий у `power_mj_kg` исправить (в коде RE = Q/4,184, а не 4,184/Q):

```python
    power_mj_kg: float            # Теплота взрыва Q_exp (МДж/кг). RE_weight = Q_exp/4,184 — сила ВВ относительно тротила
```

После `CROWNS_MM` добавить структуры результата:

```python
# Доля скважины, занятая зарядом (как в смете).
FILL_RATIO = 0.8


@dataclass(frozen=True)
class BlastPoint:
    """Расчёт одной коронки при заданном q — все промежуточные величины без округления."""

    q_kg_m3: float
    hole_diameter_mm: float
    charge_length_m: float
    charge_mass_kg: float
    volume_per_hole_m3: float
    burden_m: float
    spacing_m: float
    rock_factor_a: float
    rock_factor: kr.RockFactorBreakdown | None  # None — расчёт «до исправления»
    re_weight: float
    strength_exponent: str
    x50_mm: float
    uniformity_n_raw: float
    uniformity_n: float
    charge_to_bench: float | None  # L/H; в расчёте «до исправления» не участвует
    characteristic_size_mm: float
    oversize_pct: float


@dataclass(frozen=True)
class QSelection:
    """Подобранный q: расчёт в этой точке и достигнут ли порог негабарита."""

    point: BlastPoint
    reached: bool
```

Класс `BlastEngine` целиком заменить на:

```python
class BlastEngine:
    # Метод-приемщик: срабатывает один раз при создании "движка", инициализирует данные об объектах
    def __init__(self, rock: RockProperties, explosive: ExplosiveProperties, target: TargetParams):
        self.rock = rock            # Запоминаем данные о породе внутри объекта
        self.explosive = explosive  # Запоминаем данные о взрывчатке
        self.target = target        # Запоминаем целевые настройки

    # Rock factor A and RE_weight live in simulation.fragmentation (BDX-006).
    def _get_rock_factor(self):
        return rock_factor_A(self.rock.ucs_mpa, self.rock.density_t_m3)

    def _get_re_weight(self) -> float:
        return relative_weight_strength(self.explosive.power_mj_kg)

    def _charge(self, diameter_mm: float) -> tuple[float, float, float]:
        """Диаметр скважины (м), длина заряда (м) и масса заряда (кг) для коронки."""
        d_m = diameter_mm / 1000 * self.target.hole_oversize_coeff  # фактический диаметр скважины
        total_depth_m = self.target.bench_height_m + self.target.overdrill_m  # общая глубина скважины
        cap_m = (math.pi * (d_m ** 2) / 4) * (self.explosive.density_t_m3 * 1000)  # вместимость 1 п.м.
        charge_mass = cap_m * total_depth_m * FILL_RATIO
        return d_m, total_depth_m * FILL_RATIO, charge_mass

    def _burden(self, charge_mass: float, q: float) -> tuple[float, float]:
        """Объём породы на скважину V = Q/q и ЛНС W = √(V / (a/W · H))."""
        v_hole = charge_mass / q
        W = math.sqrt(v_hole / (self.target.spacing_coeff_m * self.target.bench_height_m))
        return v_hole, W

    # --- Расчёт «до исправления»: только для сравнения на переходный период ---

    def legacy_point(self, diameter_mm: float, q: float) -> BlastPoint:
        """Прежняя модель: A не по Каннингему, показатель 19/30, n с диаметром в метрах (n ≥ 0,8)."""
        d_m, charge_length, charge_mass = self._charge(diameter_mm)
        v_hole, W = self._burden(charge_mass, q)
        A = self._get_rock_factor()
        re_weight = self._get_re_weight()
        x50_mm = kuznetsov_x50_mm(A, q, charge_mass, re_weight)
        m = self.target.spacing_coeff_m
        n_raw = (2.2 - 14.0 * (W / d_m)) * (1.0 + (m - 1.0) / 2.0)
        n = cunningham_uniformity_n(W, d_m, m)
        return BlastPoint(
            q_kg_m3=q, hole_diameter_mm=d_m * 1000, charge_length_m=charge_length,
            charge_mass_kg=charge_mass, volume_per_hole_m3=v_hole, burden_m=W, spacing_m=m * W,
            rock_factor_a=A, rock_factor=None, re_weight=re_weight, strength_exponent="19/30",
            x50_mm=x50_mm, uniformity_n_raw=n_raw, uniformity_n=n, charge_to_bench=None,
            characteristic_size_mm=rosin_rammler_characteristic_mm(x50_mm, n),
            oversize_pct=rosin_rammler_oversize_pct(x50_mm, n, self.target.lump_size_mm),
        )

    def optimize_blast_legacy(self, diameter_mm: float, max_oversize_threshold: float = 5.0) -> QSelection:
        """Прежний подбор: q от 0,30 до 1,50, негабарит округляется до сотых перед сравнением."""
        q = 0.3
        step = 0.01
        while q <= 1.5:
            point = self.legacy_point(diameter_mm, q)
            if round(point.oversize_pct, 2) <= max_oversize_threshold:
                return QSelection(point, True)
            q += step
        return QSelection(self.legacy_point(diameter_mm, 1.5), False)  # Если предел достигнут

    # --- Kuz-Ram по Каннингему ---

    def kuzram_point(self, diameter_mm: float, q: float, settings: kr.KuzRamSettings) -> BlastPoint:
        """Расчёт коронки при заданном q по Kuz-Ram (Каннингем, EFEE 2005)."""
        d_m, charge_length, charge_mass = self._charge(diameter_mm)
        v_hole, W = self._burden(charge_mass, q)
        m = self.target.spacing_coeff_m
        rock = kr.rock_factor(
            settings,
            ucs_mpa=self.rock.ucs_mpa,
            density_t_m3=self.rock.density_t_m3,
            fissuring_per_m=self.rock.fissuring_ff,
            burden_m=W,
            spacing_m=m * W,
        )
        re_weight = self._get_re_weight()
        x50_mm = kr.mean_fragment_mm(rock.value, q, charge_mass, re_weight, settings.exponent)
        n = kr.uniformity_index(
            burden_m=W,
            hole_diameter_mm=d_m * 1000,
            spacing_to_burden=m,
            drill_deviation_m=settings.drill_deviation_m,
            charge_length_m=charge_length,
            bench_height_m=self.target.bench_height_m,
            correction=settings.uniformity_correction,
        )
        xc, oversize_pct = kr.oversize(x50_mm, n.value, self.target.lump_size_mm)
        return BlastPoint(
            q_kg_m3=q, hole_diameter_mm=d_m * 1000, charge_length_m=charge_length,
            charge_mass_kg=charge_mass, volume_per_hole_m3=v_hole, burden_m=W, spacing_m=m * W,
            rock_factor_a=rock.value, rock_factor=rock, re_weight=re_weight,
            strength_exponent=settings.strength_exponent, x50_mm=x50_mm,
            uniformity_n_raw=n.raw, uniformity_n=n.value, charge_to_bench=n.charge_to_bench,
            characteristic_size_mm=xc, oversize_pct=oversize_pct,
        )

    def optimize_blast(
        self,
        diameter_mm: float,
        max_oversize_threshold: float = 5.0,
        settings: kr.KuzRamSettings | None = None,
    ) -> QSelection:
        """Наименьший q (шаг 0,01 от 0,10 до верхней границы), при котором негабарит не больше порога."""
        settings = settings or kr.KuzRamSettings()
        first = round(kr.Q_MIN_KG_M3 * 100)
        last = round(settings.q_max_kg_m3 * 100)
        for i in range(first, last + 1):
            point = self.kuzram_point(diameter_mm, i / 100, settings)
            if point.oversize_pct <= max_oversize_threshold:
                return QSelection(point, True)
        return QSelection(self.kuzram_point(diameter_mm, last / 100, settings), False)

    def calibrate_rock_factor(
        self,
        diameter_mm: float,
        q: float,
        oversize_pct: float,
        settings: kr.KuzRamSettings,
    ) -> float | None:
        """C(A), при котором Kuz-Ram при фактическом q даёт фактический негабарит; None — вне 0,1–10."""

        def oversize_at(correction: float) -> float:
            trial = replace(settings, rock_factor_correction=correction)
            return self.kuzram_point(diameter_mm, q, trial).oversize_pct

        return kr.solve_rock_factor_correction(oversize_at, oversize_pct)
```

Методы `_get_E_for_kuznetsov`, `_calculate_with_q` и `calculate_for_diameter` удаляются: первый нигде не вызывается, второй заменён `legacy_point`, третий (с `target_q = 1.4`) из API не вызывается. Перед удалением проверить: `grep -rn "_get_E_for_kuznetsov\|_calculate_with_q\|calculate_for_diameter" --include='*.py' .` — совпадения только в `Blast.py`.

Исполняемый блок `if __name__ == "__main__":` привести к новому результату — цикл по коронкам заменить на:

```python
    for d in crowns:
        result = engine.optimize_blast(d, max_oversize_threshold=MAX_OVERSIZE)
        point = result.point
        w_val = round(point.burden_m, 2)
        # Сетка: a — расстояние между скважинами в ряду, b = W (ЛНС)
        a_m = round(engine.target.spacing_coeff_m * w_val, 2)
        grid_str = f"{a_m} × {w_val}"
        mark = "" if result.reached else " (порог не достигнут)"
        print(f"{d:<10} | {round(point.q_kg_m3, 2):<10} | {w_val:<10} | {grid_str:<18} | {round(point.x50_mm, 1):<10}{mark}")
```

- [ ] **Шаг 4. Обновить регрессионный тест движка**

В `tests/test_fragmentation_engine.py` метод `BlastEngineRegressionTests.test_optimize_still_returns_x50_and_oversize` заменить на:

```python
    def test_optimize_still_returns_x50_and_oversize(self):
        engine = BlastEngine(
            RockProperties("Габбро-диабаз", 2.9, 168, 2.2),
            ExplosiveProperties("ЭВЕРСИН Э-100", 1.12, 2.99),
            TargetParams(lump_size_mm=400, hole_diameter_mm=0, bench_height_m=10.0),
        )
        result = engine.optimize_blast(152, max_oversize_threshold=5.0)
        self.assertTrue(result.reached)
        self.assertGreater(result.point.x50_mm, 0)
        self.assertGreaterEqual(result.point.oversize_pct, 0)
```

- [ ] **Шаг 5. Тесты проходят**

Run: `../../../.venv/bin/python -m pytest tests/test_blast_optimizer.py tests/test_fragmentation_engine.py tests/test_fragmentation_cunningham.py -q -p no:cacheprovider`
Expected: PASS.

Затем `../../../.venv/bin/python Blast.py` — таблица по 11 коронкам, для 152 мм q = 1,26.

- [ ] **Шаг 6. Коммит**

```bash
git add Blast.py tests/test_blast_optimizer.py tests/test_fragmentation_engine.py
git commit -m "Kuz-Ram: подбор q по Каннингему, прежний расчёт — optimize_blast_legacy

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Задача 4. API: настройки, разбор, «до исправления» и калибровка

**Файлы:**
- Изменить: `api/schemas/blast.py` (после `TargetParamsSchema` и в `BlastOptimizeRequest` / `BlastOptimizeVariant` / `BlastOptimizeResponse`)
- Изменить: `api/services/blast_service.py:15-57`
- Изменить: `api/services/converters.py:62-70`
- Изменить: `api/routers/blast.py`
- Создать тест: `tests/test_api_blast_optimize.py`

**Интерфейсы:**
- Использует из задачи 3: `BlastEngine.optimize_blast`, `optimize_blast_legacy`, `legacy_point`, `kuzram_point`, `calibrate_rock_factor`, `BlastPoint`, `QSelection`; из задачи 2: `KuzRamSettings`, `MODEL_VERSION`.
- Производит (нужно PR 2, фронт): JSON-контракт ниже.

- [ ] **Шаг 1. Написать падающий тест**

`tests/test_api_blast_optimize.py`:

```python
"""API подбора q: /blast/optimize (Kuz-Ram и «до исправления») и /blast/kuzram/calibrate."""
import unittest

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routers import blast
from Blast import BlastEngine, ExplosiveProperties, RockProperties, TargetParams
from simulation.fragmentation import cunningham as kr

GABBRO = {
    "rock": {"name": "Габбро-диабаз", "density_t_m3": 2.9, "ucs_mpa": 168, "fissuring_ff": 2.2},
    "explosive": {"name": "ЭВЕРСИН Э-100", "density_t_m3": 1.12, "power_mj_kg": 2.99},
    "target": {
        "lump_size_mm": 400, "bench_height_m": 10, "overdrill_m": 1,
        "hole_oversize_coeff": 1.05, "spacing_coeff_m": 1.25,
    },
}


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(blast.router, prefix="/api/v1")
    return TestClient(app)


def _optimize(**extra) -> dict:
    response = _client().post("/api/v1/blast/optimize", json={**GABBRO, **extra})
    assert response.status_code == 200, response.text
    return response.json()


class OptimizeEndpointTests(unittest.TestCase):
    def test_defaults_to_massive_rock_model(self):
        body = _optimize(crown_diameters_mm=[152])
        self.assertEqual(body["model_version"], "kuzram-cunningham-1.0")
        self.assertEqual(body["kuzram"]["rock_factor_method"], "rmd50")
        self.assertEqual(body["kuzram"]["q_max_kg_m3"], 2.0)
        variant = body["variants"][0]
        self.assertEqual(variant["specific_q_kg_m3"], 1.26)
        self.assertEqual(variant["grid_label"], "4.42 × 3.54")
        self.assertTrue(variant["reached"])
        self.assertEqual(variant["target_q_kg_m3"], 1.26)
        self.assertAlmostEqual(variant["details"]["rock_factor"]["value"], 6.366)
        self.assertAlmostEqual(variant["details"]["rock_factor"]["rdi"], 22.5)
        self.assertEqual(variant["details"]["strength_exponent"], "19/20")

    def test_legacy_block_matches_old_response(self):
        legacy = _optimize(crown_diameters_mm=[152])["variants"][0]["legacy"]
        self.assertEqual(legacy["specific_q_kg_m3"], 1.34)
        self.assertEqual(legacy["grid_label"], "4.29 × 3.43")
        self.assertEqual(legacy["x50_mm"], 64.2)
        self.assertEqual(legacy["oversize_pct"], 5.0)
        self.assertTrue(legacy["reached"])
        self.assertEqual(legacy["details"]["uniformity_n"], 0.8)
        self.assertIsNone(legacy["details"]["rock_factor"])

    def test_settings_change_the_result(self):
        body = _optimize(crown_diameters_mm=[152], kuzram={"rock_factor_method": "rmd10"})
        self.assertEqual(body["variants"][0]["specific_q_kg_m3"], 0.74)
        self.assertEqual(body["kuzram"]["rock_factor_method"], "rmd10")

    def test_not_reached_has_no_target_q(self):
        variant = _optimize(crown_diameters_mm=[250], kuzram={"q_max_kg_m3": 1.5})["variants"][0]
        self.assertFalse(variant["reached"])
        self.assertIsNone(variant["target_q_kg_m3"])
        self.assertEqual(variant["specific_q_kg_m3"], 1.5)

    def test_out_of_range_setting_is_422_with_russian_message(self):
        response = _client().post("/api/v1/blast/optimize", json={**GABBRO, "kuzram": {"rock_factor_correction": 50}})
        self.assertEqual(response.status_code, 422)
        messages = " ".join(error["msg"] for error in response.json()["detail"])
        self.assertIn("Поправка C(A) — от 0,1 до 10.", messages)

    def test_unknown_setting_is_rejected(self):
        response = _client().post("/api/v1/blast/optimize", json={**GABBRO, "kuzram": {"a_method": "code"}})
        self.assertEqual(response.status_code, 422)


class CalibrateEndpointTests(unittest.TestCase):
    def test_round_trip_and_skipped_rows(self):
        engine = BlastEngine(
            RockProperties("Габбро-диабаз", 2.9, 168, 2.2),
            ExplosiveProperties("ЭВЕРСИН Э-100", 1.12, 2.99),
            TargetParams(lump_size_mm=400, hole_diameter_mm=0, bench_height_m=10.0),
        )
        truth = kr.KuzRamSettings(rock_factor_correction=1.2)
        facts = [
            {"crown_mm": crown, "q_kg_m3": q, "oversize_pct": engine.kuzram_point(crown, q, truth).oversize_pct}
            for crown, q in [(110, 1.0), (152, 1.1), (171, 1.2)]
        ]
        facts.append({"crown_mm": 152, "q_kg_m3": 1.1, "oversize_pct": 99.99})
        response = _client().post("/api/v1/blast/kuzram/calibrate", json={**GABBRO, "facts": facts})
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["used"], 3)
        self.assertEqual(body["skipped"], 1)
        self.assertAlmostEqual(body["rock_factor_correction"], 1.2, places=3)
        self.assertEqual(body["model_version"], "kuzram-cunningham-1.0")
        self.assertAlmostEqual(body["rows"][0]["rock_factor_correction"], 1.2, places=3)
        self.assertGreater(body["rows"][0]["legacy_oversize_pct"], 0)
        self.assertIsNone(body["rows"][3]["rock_factor_correction"])
        self.assertIn("C(A) от 0,1 до 10", body["rows"][3]["note"])

    def test_nothing_solved_gives_null(self):
        facts = [{"crown_mm": 152, "q_kg_m3": 1.1, "oversize_pct": 99.99}]
        body = _client().post("/api/v1/blast/kuzram/calibrate", json={**GABBRO, "facts": facts}).json()
        self.assertIsNone(body["rock_factor_correction"])
        self.assertEqual(body["used"], 0)

    def test_facts_are_required(self):
        response = _client().post("/api/v1/blast/kuzram/calibrate", json={**GABBRO, "facts": []})
        self.assertEqual(response.status_code, 422)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Шаг 2. Убедиться, что тест падает**

Run: `../../../.venv/bin/python -m pytest tests/test_api_blast_optimize.py -q -p no:cacheprovider`
Expected: FAIL — в ответе нет `model_version` (KeyError), а у калибровки 404.

- [ ] **Шаг 3. Схемы**

В `api/schemas/blast.py` импорты:

```python
from dataclasses import asdict
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from api.schemas.cost import BlockGeometrySchema, HoleGeometrySchema, InitiationConfigSchema
from simulation.fragmentation.cunningham import KuzRamSettings
```

После `TargetParamsSchema` добавить:

```python
class KuzRamSettingsSchema(BaseModel):
    """Настройки модели Kuz-Ram. Границы и тексты ошибок — в KuzRamSettings."""

    model_config = ConfigDict(extra="forbid")

    rock_factor_method: Literal["rmd50", "rmd10", "joint_factor", "manual"] = "rmd50"
    rock_factor_manual: float = 6.0
    joint_condition: float = 1.0
    joint_angle: int = 20
    rock_factor_correction: float = 1.0
    strength_exponent: Literal["19/20", "19/30"] = "19/20"
    drill_deviation_m: float = 0.0
    uniformity_correction: float = 1.0
    q_max_kg_m3: float = 2.0

    @model_validator(mode="after")
    def _within_bounds(self) -> "KuzRamSettingsSchema":
        self.to_settings()
        return self

    def to_settings(self) -> KuzRamSettings:
        return KuzRamSettings(**self.model_dump())

    @classmethod
    def from_settings(cls, settings: KuzRamSettings) -> "KuzRamSettingsSchema":
        return cls(**asdict(settings))


class RockFactorBreakdownSchema(BaseModel):
    """Состав фактора породы A (только новая модель)."""

    model_config = ConfigDict(from_attributes=True)

    method: str
    rmd: float | None
    rdi: float | None
    hf: float | None
    joint_spacing_m: float | None
    reduced_pattern_m: float | None
    jps: float | None
    base: float
    correction: float
    value: float


class FragmentationDetailsSchema(BaseModel):
    """Промежуточные величины расчёта коронки при подобранном q — для разбора."""

    model_config = ConfigDict(from_attributes=True)

    q_kg_m3: float
    hole_diameter_mm: float
    charge_length_m: float
    charge_mass_kg: float
    volume_per_hole_m3: float
    burden_m: float
    spacing_m: float
    rock_factor_a: float
    rock_factor: RockFactorBreakdownSchema | None
    re_weight: float
    strength_exponent: str
    x50_mm: float
    uniformity_n_raw: float
    uniformity_n: float
    charge_to_bench: float | None
    characteristic_size_mm: float
    oversize_pct: float


class LegacyVariantSchema(BaseModel):
    """Результат расчёта «до исправления» — для сравнения на переходный период."""

    specific_q_kg_m3: float
    line_of_least_resistance_m: float
    grid_a_m: float
    grid_b_m: float
    grid_label: str
    x50_mm: float
    oversize_pct: float
    reached: bool
    details: FragmentationDetailsSchema
```

В `BlastOptimizeRequest` добавить поле:

```python
    kuzram: KuzRamSettingsSchema | None = None
```

В `BlastOptimizeVariant` после `target_q_kg_m3` добавить:

```python
    reached: bool
    details: FragmentationDetailsSchema
    legacy: LegacyVariantSchema
```

В `BlastOptimizeResponse` добавить:

```python
    model_version: str
    kuzram: KuzRamSettingsSchema
```

После `BlastOptimizeResponse` добавить схемы калибровки:

```python
class KuzRamFactSchema(BaseModel):
    crown_mm: float = Field(..., gt=0)
    q_kg_m3: float = Field(..., gt=0)
    oversize_pct: float = Field(..., gt=0, lt=100)


class KuzRamCalibrateRequest(BaseModel):
    rock: RockPropertiesSchema
    explosive: ExplosivePropertiesSchema
    target: TargetParamsSchema
    kuzram: KuzRamSettingsSchema = Field(default_factory=KuzRamSettingsSchema)
    facts: list[KuzRamFactSchema] = Field(..., min_length=1, max_length=50)


class KuzRamCalibrationRow(BaseModel):
    crown_mm: float
    q_kg_m3: float
    oversize_pct: float
    legacy_oversize_pct: float
    model_oversize_pct: float
    rock_factor_correction: float | None
    note: str | None = None


class KuzRamCalibrateResponse(BaseModel):
    rows: list[KuzRamCalibrationRow]
    rock_factor_correction: float | None
    used: int
    skipped: int
    model_version: str
```

- [ ] **Шаг 4. Преобразование входов**

В `api/services/converters.py` импорт схем дополнить `KuzRamCalibrateRequest`, а подпись функции заменить (тело не меняется):

```python
def blast_request_to_engine_inputs(
    request: BlastOptimizeRequest | KuzRamCalibrateRequest,
) -> tuple[RockProperties, ExplosiveProperties, TargetParams]:
```

- [ ] **Шаг 5. Сервис**

В `api/services/blast_service.py` импорты:

```python
import math

from Blast import BlastEngine, BlastPoint
from api.exceptions import InvalidGeometryError
from api.schemas.blast import (
    BlastOptimizeRequest,
    BlastOptimizeResponse,
    BlastOptimizeVariant,
    FragmentationDetailsSchema,
    KuzRamCalibrateRequest,
    KuzRamCalibrateResponse,
    KuzRamCalibrationRow,
    KuzRamSettingsSchema,
    LegacyVariantSchema,
)
from api.services.converters import blast_request_to_engine_inputs
from cost.v2.legacy_adapter import LegacyReferences
from simulation.fragmentation.cunningham import MODEL_VERSION
```

Функцию `optimize_blast` заменить на:

```python
def _grid(point: BlastPoint, spacing_coeff_m: float) -> tuple[float, float, str]:
    """Сетка a × b с округлением, как в прежнем ответе: a считается от округлённого W."""
    b_m = round(point.burden_m, 2)
    a_m = round(spacing_coeff_m * b_m, 2)
    return a_m, b_m, f"{a_m} × {b_m}"


def optimize_blast(request: BlastOptimizeRequest) -> BlastOptimizeResponse:
    rock, explosive, target = blast_request_to_engine_inputs(request)

    if target.bench_height_m <= 0:
        raise InvalidGeometryError("Высота уступа должна быть больше нуля.")
    if not request.crown_diameters_mm:
        raise InvalidGeometryError("Укажите хотя бы один диаметр коронки.")

    settings_schema = request.kuzram or KuzRamSettingsSchema()
    settings = settings_schema.to_settings()
    engine = BlastEngine(rock, explosive, target)
    threshold = request.max_oversize_threshold_pct
    variants: list[BlastOptimizeVariant] = []

    for diameter_mm in sorted(request.crown_diameters_mm):
        if diameter_mm <= 0:
            raise InvalidGeometryError(f"Некорректный диаметр коронки: {diameter_mm} мм.")

        current = engine.optimize_blast(diameter_mm, threshold, settings)
        legacy = engine.optimize_blast_legacy(diameter_mm, threshold)
        a_m, b_m, label = _grid(current.point, target.spacing_coeff_m)
        legacy_a, legacy_b, legacy_label = _grid(legacy.point, target.spacing_coeff_m)
        q = round(current.point.q_kg_m3, 2)

        variants.append(
            BlastOptimizeVariant(
                crown_mm=diameter_mm,
                specific_q_kg_m3=q,
                line_of_least_resistance_m=b_m,
                grid_a_m=a_m,
                grid_b_m=b_m,
                grid_label=label,
                x50_mm=round(current.point.x50_mm, 1),
                oversize_pct=round(current.point.oversize_pct, 2),
                target_q_kg_m3=q if current.reached else None,
                reached=current.reached,
                details=FragmentationDetailsSchema.model_validate(current.point),
                legacy=LegacyVariantSchema(
                    specific_q_kg_m3=round(legacy.point.q_kg_m3, 2),
                    line_of_least_resistance_m=legacy_b,
                    grid_a_m=legacy_a,
                    grid_b_m=legacy_b,
                    grid_label=legacy_label,
                    x50_mm=round(legacy.point.x50_mm, 1),
                    oversize_pct=round(legacy.point.oversize_pct, 2),
                    reached=legacy.reached,
                    details=FragmentationDetailsSchema.model_validate(legacy.point),
                ),
            )
        )

    return BlastOptimizeResponse(
        variants=variants,
        max_oversize_threshold_pct=threshold,
        rock_name=rock.name,
        explosive_name=explosive.name,
        model_version=MODEL_VERSION,
        kuzram=KuzRamSettingsSchema.from_settings(settings),
    )


def calibrate_kuzram(request: KuzRamCalibrateRequest) -> KuzRamCalibrateResponse:
    """C(A) по фактическим взрывам: для каждой строки и среднее геометрическое по решённым."""
    rock, explosive, target = blast_request_to_engine_inputs(request)
    settings = request.kuzram.to_settings()
    engine = BlastEngine(rock, explosive, target)
    rows: list[KuzRamCalibrationRow] = []
    solved: list[float] = []

    for fact in request.facts:
        correction = engine.calibrate_rock_factor(fact.crown_mm, fact.q_kg_m3, fact.oversize_pct, settings)
        if correction is not None:
            solved.append(correction)
        rows.append(
            KuzRamCalibrationRow(
                crown_mm=fact.crown_mm,
                q_kg_m3=fact.q_kg_m3,
                oversize_pct=fact.oversize_pct,
                legacy_oversize_pct=round(engine.legacy_point(fact.crown_mm, fact.q_kg_m3).oversize_pct, 2),
                model_oversize_pct=round(
                    engine.kuzram_point(fact.crown_mm, fact.q_kg_m3, settings).oversize_pct, 2
                ),
                rock_factor_correction=None if correction is None else round(correction, 3),
                note=None
                if correction is not None
                else "Фактический негабарит не получается ни при каком C(A) от 0,1 до 10.",
            )
        )

    mean = math.exp(sum(math.log(value) for value in solved) / len(solved)) if solved else None
    return KuzRamCalibrateResponse(
        rows=rows,
        rock_factor_correction=None if mean is None else round(mean, 3),
        used=len(solved),
        skipped=len(rows) - len(solved),
        model_version=MODEL_VERSION,
    )
```

`resolve_explosive_item` и `compute_geometry` не меняются.

- [ ] **Шаг 6. Роутер**

В `api/routers/blast.py` импорт схем дополнить `KuzRamCalibrateRequest`, `KuzRamCalibrateResponse`, импорт сервиса — `calibrate_kuzram`, и после `post_blast_optimize` добавить:

```python
@router.post("/kuzram/calibrate", response_model=KuzRamCalibrateResponse)
def post_kuzram_calibrate(request: KuzRamCalibrateRequest) -> KuzRamCalibrateResponse:
    return calibrate_kuzram(request)
```

- [ ] **Шаг 7. Тесты проходят**

Run: `../../../.venv/bin/python -m pytest tests/test_api_blast_optimize.py tests/test_api_geometry.py -q -p no:cacheprovider`
Expected: PASS.

- [ ] **Шаг 8. Коммит**

```bash
git add api/schemas/blast.py api/services/blast_service.py api/services/converters.py api/routers/blast.py tests/test_api_blast_optimize.py
git commit -m "Kuz-Ram: /blast/optimize с настройками, разбором и «до исправления»; /blast/kuzram/calibrate

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Задача 5. Документация

**Файлы:**
- Создать: `Docs/KUZRAM_MODEL.md`
- Изменить: `README.md` (строки 3–4, 25, 416, 597–613)

- [ ] **Шаг 1. `Docs/KUZRAM_MODEL.md`**

````markdown
# Модель Kuz-Ram для подбора удельного расхода

Лист «Расчёт» подбирает для каждой коронки наименьший удельный расход q
(кг/м³), при котором доля кусков крупнее кондиционного (негабарит) не
превышает допустимую. Прогноз дробления — модель Kuz-Ram по Каннингему:
C. V. B. Cunningham, «The Kuz-Ram fragmentation model — 20 years on»,
EFEE 2005.

Код: `simulation/fragmentation/cunningham.py` (формулы) и
`Blast.py::BlastEngine.optimize_blast` (подбор). Версия модели —
`kuzram-cunningham-1.0`.

## Геометрия скважины

```
d  = коронка/1000 · коэф. разбуривания              [м]
L  = 0,8 · (H + перебур)                             [м] длина заряда
Q  = π·d²/4 · ρВВ·1000 · L                           [кг]
V  = Q / q;  W = √(V / (a/W · H));  a = a/W · W;  b = W
RE = теплота взрыва / 4,184                          сила ВВ к тротилу
```

## Дробление

```
RDI = 25·ρ − 50                  HF = UCS/5
A   = 0,06·(RMD + RDI + HF)·C(A)
x50 = A · q^−0,8 · Q^(1/6) · RE^(−e) · 10            [мм], e = 19/20 (или 19/30)
n   = (2,2 − 14·W/d_мм) · √((1 + a/W)/2) · (1 − σ/W) · 1,1^0,1 · min(1, L/H) · C(n)
xc  = x50 / (ln 2)^(1/n)
негабарит = exp(−(кусок/xc)^n) · 100 %
```

RMD — описание массива: 50 — монолитный, 10 — рыхлый. Для трещиноватого
массива вместо RMD берётся JF = JCF·JPS + JPA: шаг трещин s = 1/трещиноватость,
приведённая сетка P = √(a·b); JPS = 10 при s < 0,1 м, 20 при s < 0,3 м,
80 при s < 0,95·P, иначе 50. HF = UCS/5, потому что модуля упругости в
данных нет. n ниже 0,1 принимается равным 0,1.

## Подбор q

q перебирается от 0,10 до верхней границы (по умолчанию 2,0) с шагом 0,01;
берётся первое значение, при котором негабарит не больше допустимого. Если
такого нет, возвращается расчёт на верхней границе с признаком «порог не
достигнут».

## Настройки

| Настройка | Умолчание | Границы |
|---|---|---|
| Способ A | монолитный массив (RMD 50) | RMD 10, JF, вручную (0,5–30) |
| C(A) | 1,0 | 0,1–10 |
| Показатель при силе ВВ | 19/20 | 19/30 |
| σ, м | 0 | 0–2 |
| C(n) | 1,0 | 0,5–2 |
| Верхняя граница q, кг/м³ | 2,0 | 0,5–5 |

Без достоверных данных о трещиноватости и ориентации трещин оставляйте
монолитный массив и уточняйте C(A) по фактическим взрывам:
`POST /api/v1/blast/kuzram/calibrate` ищет C(A), при котором модель при
фактическом q даёт фактический негабарит (бисекция по ln C(A) на 0,1–10),
и усредняет решённые строки геометрически.

## Что считалось раньше

До сентября 2026 года подбор использовал A = 0,12·(UCS/20 + 2,5ρ + 7),
показатель 19/30 и индекс n с диаметром в метрах — из-за этого n всегда
упирался в 0,8. Две ошибки почти компенсировали друг друга: для
монолитного массива прежний и новый q близки (габбро-диабаз, 152 мм:
1,34 и 1,26 кг/м³). Прежний расчёт сохранён как
`BlastEngine.optimize_blast_legacy` и отдаётся в блоке `legacy` ответа
`/blast/optimize` на переходный период.

Прогноз дробления на вкладке «Проектирование», в отчётах и базис
ML-калибровки пока считает старый `simulation/fragmentation/kuzram.py`.
````

- [ ] **Шаг 2. README**

Строки 3–4 заменить на:

```markdown
Калькулятор параметров взрывных работ и сметы БВР: новый React-интерфейс,
подбор сетки скважин по модели Kuz-Ram (Каннингем), интерактивная схема заряда,
```

Строку 25 (`├── Blast.py ...`) заменить на:

```markdown
├── Blast.py                 # Технологический движок: подбор q и ЛНС по Kuz-Ram (Каннингем)
```

Строку таблицы API `/blast/optimize` (около строки 416) заменить на две:

```markdown
| POST | `/blast/optimize` | Подбор q и сетки по коронкам (Kuz-Ram с настройками; блок `legacy` — расчёт до исправления) |
| POST | `/blast/kuzram/calibrate` | Поправка C(A) по фактическим взрывам |
```

Раздел «Модуль `Blast.py` — технология» (строки 597–613) заменить на:

```markdown
## Модуль `Blast.py` — технология

Движок `BlastEngine` подбирает для каждой коронки наименьший удельный расход `q` (кг/м³), при котором негабарит не превышает порог. Формулы — модель Kuz-Ram по Каннингему (`simulation/fragmentation/cunningham.py`), подробности — [Docs/KUZRAM_MODEL.md](Docs/KUZRAM_MODEL.md).

**Входные данные:**

| Класс | Поля |
|-------|------|
| `RockProperties` | порода, плотность, UCS, трещиноватость |
| `ExplosiveProperties` | название, плотность заряжания, теплота взрыва |
| `TargetParams` | размер негабарита, высота уступа, перебур, коэфф. сетки a/W |
| `KuzRamSettings` | способ расчёта фактора породы A, поправки C(A) и C(n), показатель при силе ВВ, отклонение бурения, верхняя граница q |

**Выход:** `QSelection` — расчёт в подобранной точке (`BlastPoint`: q, ЛНС `W`, сетка, `x50`, `n`, негабарит и промежуточные величины) и признак, достигнут ли порог. Прежний расчёт — `optimize_blast_legacy`.

Породы и ВВ в UI берутся из справочников команды (вкладка «Справочники»), а не из констант в коде.
```

- [ ] **Шаг 3. Коммит**

```bash
git add Docs/KUZRAM_MODEL.md README.md
git commit -m "Kuz-Ram: описание модели подбора q и API

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Задача 6. Проверка, ревью и PR

- [ ] **Шаг 1. Все тесты**

Run: `../../../.venv/bin/python -m pytest -q -p no:cacheprovider`
Expected: всё зелёное; до работы было 1375 passed, 32 skipped — стало больше на новые тесты, падений нет.

- [ ] **Шаг 2. Никто не опирается на старый словарь `optimize_blast`**

Run: `grep -rn "\.optimize_blast(\|\[\"target_q\"\]\|\[\"W_m\"\]" --include='*.py' . | grep -v "tests/\|Blast.py\|blast_service.py"`
Expected: пусто — вызовы движка есть только в сервисе, тестах и самом `Blast.py`, а ключи прежнего словаря нигде не читаются.

- [ ] **Шаг 3. Ревью**

Запустить `/code-review` по ветке, исправить подтверждённые замечания отдельными коммитами.

- [ ] **Шаг 4. PR**

```bash
git push -u origin feat/kuzram-model
gh pr create --title "Kuz-Ram PR 1: подбор q по Каннингему, настройки модели и калибровка C(A) (сервер)" --body-file <scratchpad>/pr1-body.md
```

Описание PR: зачем (ссылка на спецификацию и закрытый #82), что изменилось в API (новые поля, новый эндпоинт, обратная совместимость), таблица «было / стало» для габбро-диабаза (110/152/250 мм: 1,18/1,34/1,50 → 1,12/1,26/1,53 кг/м³), что не трогали (Проектирование, отчёты, ML), как проверено. В конце — строка `🤖 Generated with [Claude Code](https://claude.com/claude-code)`.

- [ ] **Шаг 5. Замечания Codex**

Прочитать комментарии Codex к PR (`gh pr view --comments`, `gh api repos/dvotapi/BlastEX/pulls/<номер>/comments`), исправить подтверждённые.
