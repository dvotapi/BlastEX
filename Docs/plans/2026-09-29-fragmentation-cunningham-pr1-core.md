# Общая функция прогноза Kuz-Ram (PR 1, ядро) — план реализации

> **Для агентов-исполнителей:** обязательный навык — superpowers:subagent-driven-development (рекомендуется) или superpowers:executing-plans. Шаги отмечаются чекбоксами (`- [ ]`).

**Цель:** в `simulation/fragmentation/cunningham.py` появляется одна функция полного прогноза точки, и лист «Расчёт» считает через неё — чтобы в PR 2 её же мог звать движок «Проектирования», и два раздела не разошлись снова.

**Архитектура:** `predict_point` складывает уже существующие функции модуля (`rock_factor`, `mean_fragment_mm`, `uniformity_index`, `oversize`) в фиксированном порядке, проверяет вырожденные входные величины и возвращает `KuzRamPoint`. `Blast.py::kuzram_point` перестаёт вызывать формулы по одной и собирает `BlastPoint` из результата. Поведение листа «Расчёт» не меняется: это проверяют golden-файл и контрольный пример.

**Стек:** Python 3.11, unittest через pytest. Фронт в этом PR не трогаем.

**Спека:** `Docs/plans/2026-09-29-fragmentation-engine-cunningham-design.md` (раздел 4.1).

## Общие ограничения

- Ветка от `origin/main`, работа в отдельном worktree. **Не пушить в `main` и ничего не сливать**: push в `main` сразу выкатывает прод (`.github/workflows/deploy.yml`).
- Python-команды из корня worktree: `../../../.venv/bin/python -m pytest <путь> -q -p no:cacheprovider`.
- Комментарии, сообщения об ошибках и текст коммитов — по-русски, как в остальном репозитории.
- Единицы измерения в именах аргументов: диаметр скважины — миллиметры, ЛНС и длины — метры, плотность — т/м³, трещиноватость — 1/м.
- Числа листа «Расчёт» меняться не должны: `tests/fixtures/kuzram_cunningham_golden.json`, `tests/test_kuzram_control_example.py` и `tests/test_kuzram_frontend_contract.py` правке не подлежат.
- Формулы Каннингема, границы и умолчания настроек в этом PR не меняются.

## На что смотреть ревью

Вырожденные входные величины, которые на листе «Расчёт» невозможны, а в неполном паспорте «Проектирования» встречаются. Спека о них молчит, но в PR 2 движок начнёт звать эту же функцию, поэтому поведение задаётся здесь и закрепляется тестами задачи 1:

1. ЛНС равна нулю — сейчас `uniformity_index` делит `σ/W` и падает с `ZeroDivisionError`; нужна понятная ошибка.
2. Длина заряда или высота уступа равны нулю — множитель L/H обнулил бы n или дал деление на ноль; берём 1 и пишем предупреждение.
3. Длина заряда больше высоты уступа — множитель не должен превышать 1 (в `uniformity_index` уже есть `min`, тест это закрепляет).
4. Удельный расход равен нулю — `q^−0,8` даёт бесконечность; нужна понятная ошибка.
5. Масса заряда равна нулю — x50 обращается в ноль, и негабарит теряет смысл; нужна понятная ошибка.

---

### Задача 1: `predict_point` в `cunningham.py`

**Файлы:**
- Изменить: `simulation/fragmentation/cunningham.py` (после `oversize`, конец файла)
- Тест: `tests/test_fragmentation_cunningham.py`

**Интерфейсы:**
- Использует: существующие `KuzRamSettings`, `rock_factor`, `mean_fragment_mm`, `uniformity_index`, `oversize`, `RockFactorBreakdown`, `Uniformity` того же модуля.
- Отдаёт: `KuzRamPoint` и `predict_point(...)` — их зовут задача 2 и движок в PR 2.

- [ ] **Шаг 1: Написать падающий тест на совпадение с пошаговым вызовом**

В `tests/test_fragmentation_cunningham.py` добавить класс:

```python
class PredictPointTests(unittest.TestCase):
    """predict_point — это те же четыре функции модуля в фиксированном порядке."""

    ARGS = dict(
        ucs_mpa=120.0,
        density_t_m3=2.9,
        fissuring_per_m=0.3,
        burden_m=3.5,
        spacing_m=4.375,
        hole_diameter_mm=159.6,
        powder_factor_kg_m3=1.26,
        charge_mass_kg=105.0,
        re_weight=0.9,
        charge_length_m=8.8,
        bench_height_m=10.0,
        lump_size_mm=800.0,
    )

    def test_matches_step_by_step_calls(self):
        settings = kr.KuzRamSettings()
        args = dict(self.ARGS)
        rock = kr.rock_factor(
            settings,
            ucs_mpa=args["ucs_mpa"],
            density_t_m3=args["density_t_m3"],
            fissuring_per_m=args["fissuring_per_m"],
            burden_m=args["burden_m"],
            spacing_m=args["spacing_m"],
        )
        x50 = kr.mean_fragment_mm(
            rock.value, args["powder_factor_kg_m3"], args["charge_mass_kg"],
            args["re_weight"], settings.exponent,
        )
        n = kr.uniformity_index(
            burden_m=args["burden_m"],
            hole_diameter_mm=args["hole_diameter_mm"],
            spacing_to_burden=args["spacing_m"] / args["burden_m"],
            drill_deviation_m=settings.drill_deviation_m,
            charge_length_m=args["charge_length_m"],
            bench_height_m=args["bench_height_m"],
            correction=settings.uniformity_correction,
        )
        xc, oversize_pct = kr.oversize(x50, n.value, args["lump_size_mm"])

        point = kr.predict_point(settings, **args)

        self.assertEqual(point.rock, rock)
        self.assertEqual(point.x50_mm, x50)
        self.assertEqual(point.uniformity, n)
        self.assertEqual(point.characteristic_size_mm, xc)
        self.assertEqual(point.oversize_pct, oversize_pct)
        self.assertEqual(point.warnings, ())
```

- [ ] **Шаг 2: Убедиться, что тест падает**

Запуск: `../../../.venv/bin/python -m pytest tests/test_fragmentation_cunningham.py -k PredictPoint -q -p no:cacheprovider`
Ожидание: FAIL, `AttributeError: module 'simulation.fragmentation.cunningham' has no attribute 'predict_point'`.

- [ ] **Шаг 3: Написать минимальную реализацию без проверок**

Проверки вырожденных величин добавляются в шаге 7, после своих тестов. В конец `simulation/fragmentation/cunningham.py`:

```python
@dataclass(frozen=True)
class KuzRamPoint:
    """Прогноз одной точки: фактор породы, средний кусок, равномерность, негабарит."""

    rock: RockFactorBreakdown
    x50_mm: float
    uniformity: Uniformity
    characteristic_size_mm: float
    oversize_pct: float
    warnings: tuple[str, ...] = ()


def predict_point(
    settings: KuzRamSettings,
    *,
    ucs_mpa: float,
    density_t_m3: float,
    fissuring_per_m: float,
    burden_m: float,
    spacing_m: float,
    hole_diameter_mm: float,
    powder_factor_kg_m3: float,
    charge_mass_kg: float,
    re_weight: float,
    charge_length_m: float,
    bench_height_m: float,
    lump_size_mm: float,
) -> KuzRamPoint:
    """Полный прогноз Kuz-Ram по Каннингему для одной точки.

    Единственное место, где формулы модуля собираются в прогноз: её зовут и
    подбор q на листе «Расчёт» (Blast.py), и движок «Проектирования», поэтому
    разделы не могут разойтись незаметно.
    """
    rock = rock_factor(
        settings,
        ucs_mpa=ucs_mpa,
        density_t_m3=density_t_m3,
        fissuring_per_m=fissuring_per_m,
        burden_m=burden_m,
        spacing_m=spacing_m,
    )
    x50_mm = mean_fragment_mm(
        rock.value, powder_factor_kg_m3, charge_mass_kg, re_weight, settings.exponent
    )
    warnings: list[str] = []
    length_m, height_m = charge_length_m, bench_height_m
    uniformity = uniformity_index(
        burden_m=burden_m,
        hole_diameter_mm=hole_diameter_mm,
        spacing_to_burden=spacing_m / burden_m,
        drill_deviation_m=settings.drill_deviation_m,
        charge_length_m=length_m,
        bench_height_m=height_m,
        correction=settings.uniformity_correction,
    )
    characteristic_size_mm, oversize_pct = oversize(x50_mm, uniformity.value, lump_size_mm)
    return KuzRamPoint(
        rock=rock,
        x50_mm=x50_mm,
        uniformity=uniformity,
        characteristic_size_mm=characteristic_size_mm,
        oversize_pct=oversize_pct,
        warnings=tuple(warnings),
    )
```

- [ ] **Шаг 4: Убедиться, что тест проходит**

Запуск: `../../../.venv/bin/python -m pytest tests/test_fragmentation_cunningham.py -k PredictPoint -q -p no:cacheprovider`
Ожидание: PASS.

- [ ] **Шаг 5: Написать падающие тесты на вырожденные величины**

В тот же класс `PredictPointTests`:

```python
    def test_missing_charge_length_keeps_uniformity_and_warns(self):
        args = dict(self.ARGS, charge_length_m=0.0)

        point = kr.predict_point(kr.KuzRamSettings(), **args)

        self.assertEqual(point.uniformity.charge_to_bench, 1.0)
        self.assertGreater(point.uniformity.value, 0.5)
        self.assertEqual(len(point.warnings), 1)
        self.assertIn("L/H", point.warnings[0])

    def test_missing_bench_height_keeps_uniformity_and_warns(self):
        args = dict(self.ARGS, bench_height_m=0.0)

        point = kr.predict_point(kr.KuzRamSettings(), **args)

        self.assertEqual(point.uniformity.charge_to_bench, 1.0)
        self.assertEqual(len(point.warnings), 1)

    def test_charge_longer_than_bench_does_not_raise_uniformity(self):
        args = dict(self.ARGS, charge_length_m=15.0, bench_height_m=10.0)

        point = kr.predict_point(kr.KuzRamSettings(), **args)

        self.assertEqual(point.uniformity.charge_to_bench, 1.0)
        self.assertEqual(point.warnings, ())

    def test_zero_burden_is_rejected(self):
        args = dict(self.ARGS, burden_m=0.0)

        with self.assertRaises(ValueError) as ctx:
            kr.predict_point(kr.KuzRamSettings(), **args)

        self.assertIn("ЛНС", str(ctx.exception))

    def test_zero_powder_factor_is_rejected(self):
        args = dict(self.ARGS, powder_factor_kg_m3=0.0)

        with self.assertRaises(ValueError) as ctx:
            kr.predict_point(kr.KuzRamSettings(), **args)

        self.assertIn("Удельный расход", str(ctx.exception))

    def test_zero_charge_mass_is_rejected(self):
        args = dict(self.ARGS, charge_mass_kg=0.0)

        with self.assertRaises(ValueError) as ctx:
            kr.predict_point(kr.KuzRamSettings(), **args)

        self.assertIn("Масса заряда", str(ctx.exception))

    def test_diameter_in_metres_is_rejected(self):
        args = dict(self.ARGS, hole_diameter_mm=0.1596)

        with self.assertRaises(ValueError) as ctx:
            kr.predict_point(kr.KuzRamSettings(), **args)

        self.assertIn("миллиметрах", str(ctx.exception))
```

- [ ] **Шаг 6: Убедиться, что новые тесты падают**

Запуск: `../../../.venv/bin/python -m pytest tests/test_fragmentation_cunningham.py -k PredictPoint -q -p no:cacheprovider`
Ожидание: FAIL у шести новых тестов. Нулевая ЛНС и нулевой удельный расход падают с `ZeroDivisionError` вместо `ValueError`, нулевая масса заряда даёт x50 = 0 и не поднимает ошибку, нулевая длина заряда и нулевая высота уступа дают `charge_to_bench = 0` или `ZeroDivisionError`. Проходит только `test_charge_longer_than_bench_does_not_raise_uniformity` (в `uniformity_index` уже есть `min`) и `test_diameter_in_metres_is_rejected` (проверку диаметра `uniformity_index` уже делает).

- [ ] **Шаг 7: Добавить проверки и запасной множитель L/H**

В `predict_point`, сразу после док-строки:

```python
    if burden_m <= 0:
        raise ValueError("ЛНС для прогноза Kuz-Ram должна быть больше нуля.")
    if powder_factor_kg_m3 <= 0:
        raise ValueError("Удельный расход для прогноза Kuz-Ram должен быть больше нуля.")
    if charge_mass_kg <= 0:
        raise ValueError("Масса заряда для прогноза Kuz-Ram должна быть больше нуля.")
```

И перед вызовом `uniformity_index` заменить строку `length_m, height_m = charge_length_m, bench_height_m` на:

```python
    length_m, height_m = charge_length_m, bench_height_m
    if length_m <= 0 or height_m <= 0:
        # Неполный паспорт: множитель L/H обнулил бы n или дал деление на
        # ноль. Берём 1 — заряд на всю высоту уступа — и говорим об этом
        # вслух.
        length_m = height_m = 1.0
        warnings.append("Длина заряда или высота уступа не заданы: множитель L/H не применён.")
```

- [ ] **Шаг 8: Убедиться, что новые тесты проходят**

Запуск: `../../../.venv/bin/python -m pytest tests/test_fragmentation_cunningham.py -k PredictPoint -q -p no:cacheprovider`
Ожидание: PASS, семь тестов.

- [ ] **Шаг 9: Прогнать весь файл тестов модуля**

Запуск: `../../../.venv/bin/python -m pytest tests/test_fragmentation_cunningham.py -q -p no:cacheprovider`
Ожидание: PASS, ни один существующий тест не изменился.

- [ ] **Шаг 10: Коммит**

```bash
git add simulation/fragmentation/cunningham.py tests/test_fragmentation_cunningham.py
git commit -m "Kuz-Ram: общая функция прогноза точки в cunningham.py"
```

---

### Задача 2: лист «Расчёт» считает через общую функцию

**Файлы:**
- Изменить: `Blast.py:162-192` (`kuzram_point`), док-строка модуля `simulation/fragmentation/cunningham.py:1-9`, `CLAUDE.md` (раздел «Модель подбора q (Kuz-Ram)»)
- Тест: `tests/test_blast_optimizer.py`

**Интерфейсы:**
- Использует: `cunningham.predict_point` и `cunningham.KuzRamPoint` из задачи 1.
- Отдаёт: `BlastEngine.kuzram_point` с прежней сигнатурой и прежними полями `BlastPoint` — от него зависят `optimize_blast`, `calibrate_rock_factor` и `api/services/blast_service.py`.

- [ ] **Шаг 1: Написать падающий тест на совпадение листа «Расчёт» с общей функцией**

В `tests/test_blast_optimizer.py`, в класс `KuzRamOptimizerTests`:

```python
    def test_point_matches_predict_point(self):
        """kuzram_point обязан быть той же функцией прогноза, что и у движка.

        Тест переживёт PR 2: движок «Проектирования» зовёт predict_point, и
        расхождение разделов ловится здесь.
        """
        cases = [
            (_gabbro(), 152, 1.26, kr.KuzRamSettings()),
            (_gabbro(), 110, 0.8, kr.KuzRamSettings(rock_factor_method="rmd10")),
            (_gabbro(), 250, 1.5, kr.KuzRamSettings(rock_factor_correction=1.3)),
            (_gabbro(), 152, 1.1, kr.KuzRamSettings(strength_exponent="19/30", drill_deviation_m=0.2)),
        ]
        for engine, crown_mm, q, settings in cases:
            with self.subTest(crown=crown_mm, q=q):
                point = engine.kuzram_point(crown_mm, q, settings)
                expected = kr.predict_point(
                    settings,
                    ucs_mpa=engine.rock.ucs_mpa,
                    density_t_m3=engine.rock.density_t_m3,
                    fissuring_per_m=engine.rock.fissuring_ff,
                    burden_m=point.burden_m,
                    spacing_m=point.spacing_m,
                    hole_diameter_mm=point.hole_diameter_mm,
                    powder_factor_kg_m3=q,
                    charge_mass_kg=point.charge_mass_kg,
                    re_weight=point.re_weight,
                    charge_length_m=point.charge_length_m,
                    bench_height_m=engine.target.bench_height_m,
                    lump_size_mm=engine.target.lump_size_mm,
                )
                self.assertAlmostEqual(point.x50_mm, expected.x50_mm, places=9)
                self.assertAlmostEqual(point.uniformity_n, expected.uniformity.value, places=9)
                self.assertAlmostEqual(point.oversize_pct, expected.oversize_pct, places=9)
                self.assertAlmostEqual(point.rock_factor_a, expected.rock.value, places=9)
                self.assertEqual(point.rock_factor, expected.rock)
```

- [ ] **Шаг 2: Убедиться, что тест падает или проходит по случайности**

Запуск: `../../../.venv/bin/python -m pytest tests/test_blast_optimizer.py -k predict_point -q -p no:cacheprovider`
Ожидание: FAIL с `AttributeError`, если задача 1 ещё не слита в рабочую копию. Если задача 1 уже на месте, тест пройдёт и до правки `Blast.py` — это ожидаемо: он закрепляет равенство, которое правка не должна сломать. В этом случае убедиться, что он падает при намеренной порче: временно заменить в `kuzram_point` аргумент `settings.exponent` на `0.5`, увидеть FAIL, вернуть как было.

- [ ] **Шаг 3: Перевести `kuzram_point` на общую функцию**

Заменить тело `Blast.py::kuzram_point` (строки 162-192) на:

```python
    def kuzram_point(self, diameter_mm: float, q: float, settings: kr.KuzRamSettings) -> BlastPoint:
        """Расчёт коронки при заданном q по Kuz-Ram (Каннингем, EFEE 2005).

        Формулы не вызываются по отдельности: прогноз считает
        cunningham.predict_point — та же функция, что и у движка
        «Проектирования».
        """
        d_m, charge_length, charge_mass, v_hole, W, m = self._hole(diameter_mm, q)
        re_weight = self._get_re_weight()
        point = kr.predict_point(
            settings,
            ucs_mpa=self.rock.ucs_mpa,
            density_t_m3=self.rock.density_t_m3,
            fissuring_per_m=self.rock.fissuring_ff,
            burden_m=W,
            spacing_m=m * W,
            hole_diameter_mm=d_m * 1000,
            powder_factor_kg_m3=q,
            charge_mass_kg=charge_mass,
            re_weight=re_weight,
            charge_length_m=charge_length,
            bench_height_m=self.target.bench_height_m,
            lump_size_mm=self.target.lump_size_mm,
        )
        return BlastPoint(
            q_kg_m3=q, hole_diameter_mm=d_m * 1000, charge_length_m=charge_length,
            charge_mass_kg=charge_mass, volume_per_hole_m3=v_hole, burden_m=W, spacing_m=m * W,
            burden_to_diameter=W / d_m,
            rock_factor_a=point.rock.value, rock_factor=point.rock, re_weight=re_weight,
            strength_exponent=settings.strength_exponent, x50_mm=point.x50_mm,
            uniformity_n_raw=point.uniformity.raw, uniformity_n=point.uniformity.value,
            charge_to_bench=point.uniformity.charge_to_bench,
            characteristic_size_mm=point.characteristic_size_mm, oversize_pct=point.oversize_pct,
        )
```

Отношение сетки к ЛНС теперь считается внутри `predict_point` как `spacing_m / burden_m`, то есть `(m·W)/W` вместо переданного раньше `m`. В double это может отличаться на последний бит; допуск golden-файла — `rel_tol=1e-9`, так что числа сойдутся. Если golden-тест всё же упадёт, ничего не подгонять: сообщить владельцу, потому что это будет означать, что подбор q стоял ровно на границе порога.

- [ ] **Шаг 4: Прогнать тесты листа «Расчёт»**

Запуск: `../../../.venv/bin/python -m pytest tests/test_blast_optimizer.py tests/test_kuzram_control_example.py tests/test_fragmentation_cunningham.py -q -p no:cacheprovider`
Ожидание: PASS, включая `test_matches_reference_implementation` и `test_gabbro_example` без правки golden-файла.

- [ ] **Шаг 5: Обновить док-строку модуля и CLAUDE.md**

В `simulation/fragmentation/cunningham.py` заменить последний абзац док-строки модуля (сейчас: «Модуль применяется только к подбору q в Blast.py. Прогнозы вкладки „Проектирование" по-прежнему считает simulation.fragmentation.kuzram.») на:

```
Полный прогноз одной точки собирает predict_point — её зовёт подбор q в
Blast.py. Прогнозы вкладки «Проектирование» пока считает
simulation.fragmentation.kuzram; перевод движка — PR 2, см.
Docs/plans/2026-09-29-fragmentation-engine-cunningham-design.md.
```

В `CLAUDE.md`, раздел «Модель подбора q (Kuz-Ram)», после первой фразы добавить:

```
Прогноз одной точки собирает `cunningham.predict_point` — единственное место,
где формулы складываются вместе.
```

- [ ] **Шаг 6: Прогнать весь набор Python-тестов**

Запуск: `../../../.venv/bin/python -m pytest -q -p no:cacheprovider`
Ожидание: PASS, число тестов на 7 больше исходного (шесть из задачи 1 и один из задачи 2).

- [ ] **Шаг 7: Коммит**

```bash
git add Blast.py simulation/fragmentation/cunningham.py CLAUDE.md tests/test_blast_optimizer.py
git commit -m "Kuz-Ram: лист «Расчёт» считает через общую функцию прогноза"
```

---

### Задача 3: сдача PR (координатор, не субагент)

**Файлы:** нет правок кода; работа с ветками и PR.

- [ ] **Шаг 1: Прогнать весь набор и линтеры**

```bash
../../../.venv/bin/python -m pytest -q -p no:cacheprovider
```

Тесты фронта не нужны: `frontend/` в этом PR не менялся.

- [ ] **Шаг 2: Код-ревью**

Запустить `/code-review high origin/main...HEAD`, исправить найденное, перезапустить тесты.

- [ ] **Шаг 3: Открыть PR**

База — `main`, заголовок и описание по-русски. В описании: что было (две реализации формул), что стало (одна функция), почему числа прода не меняются (golden-файл и контрольный пример без правок), и что PR 2 переведёт движок.

- [ ] **Шаг 4: Дождаться ревью Codex**

Codex ревьюит при открытии PR и по комментарию `@codex review`. Ответить на замечания, исправить, обновить описание.

- [ ] **Шаг 5: Слияние — только по решению владельца**

Слияние в `main` выкатывает прод (17–50 минут). Числа не меняются, но выкат всё равно за владельцем.

---

## Что дальше

PR 2 (движок «Проектирования», модели и настройки из объекта работ) и PR 3 (калибровки и пометки) получают отдельные планы после слияния PR 1 — тогда их можно писать поверх уже существующей `predict_point`.
