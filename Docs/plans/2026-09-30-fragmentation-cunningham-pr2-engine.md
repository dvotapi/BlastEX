# Движок кусковатости «Проектирования» на Каннингеме (PR 2) — план реализации

> **Для агентов-исполнителей:** обязательный навык — superpowers:subagent-driven-development (рекомендуется) или superpowers:executing-plans. Шаги отмечаются чекбоксами (`- [ ]`).

**Цель:** «Проектирование», паспорт БВР и сценарии считают кусковатость той же функцией `cunningham.predict_point`, что и лист «Расчёт», с настройками модели из объекта работ — чтобы при одинаковых входных величинах и настройках разделы давали одно и то же число.

**Архитектура:** новый модуль `simulation/fragmentation/base.py` переводит входные величины региона (`FragmentationInputs`) в аргументы `predict_point`; три модели движка (`kuznetsov`, `kuzram`, `swebrec`, версия 2.0.0) берут из него фактор A, x50 и n и различаются только кривой. Прежние модули переезжают в `simulation/fragmentation/legacy/` под именами `*_legacy` без правки формул. Движок получает параметр `settings: KuzRamSettings | None` и пишет снимок применённых настроек в ответ и в `provenance`; настройки достаёт API (`api/services/fragmentation_settings.py`) из записи `calc_object_inputs` объекта работ. ML-калибровки и пространственные признаки до PR 3 остаются на старой базе.

**Стек:** Python 3.11, FastAPI + pydantic 2, unittest через pytest; фронт — React + TypeScript, vitest.

**Спека:** `Docs/plans/2026-09-29-fragmentation-engine-cunningham-design.md` (разделы 4.2–4.4, 5, 6, 7 п. 2). Базовый коммит плана — `01ccf4d` (PR 1 слит).

## Отступления от спеки — подтверждены владельцем 2026-09-30

Все семь решений ниже владелец принял; исполнять план как написан.

1. **Запасной источник настроек — активный объект работ организации.** Спека (4.4, п. 2): явные настройки → объект из запроса → умолчания. План вставляет между последними двумя активный объект рабочего пространства (`LegacyWorkspaceSettings.active_work_object_name`). Причина: у `GET /design/plans/{id}/passport` и у базового сценария в сравнении нет тела запроса, и без этого шага один и тот же проект давал бы в панели «Кусковатость» одно число, а в паспорте — другое.
2. **ML до PR 3 остаётся на старой базе.** Спека (4.2) переводит `intelligence/spatial/features.py:305` на новый `kuzram`, а (4.4) велит ML брать снимок настроек из сохранённого прогноза. План в PR 2 делает обратное: baseline калибровки и физические признаки пространственной модели считаются моделью `kuzram_legacy`, а поправки калибровок кусковатости в сценариях к новым моделям не применяются. Причина: проверка базы артефакта калибровки появляется только в PR 3, а без неё после выката PR 2 старые поправки легли бы на новые прогнозы — это нарушает решение владельца № 3.
3. **Длина заряда — сумма взрывчатых дек.** Спека (4.3) ссылается на «скважина минус забойка» (`regions.py:197`). План берёт сумму длин взрывчатых дек, а «скважина минус забойка» — только если дек нет: при рассредоточенном заряде с воздушным промежутком первое выражение завышает L.
4. **Скважина с неполными данными пропускается с предупреждением,** а не роняет весь прогноз блока; если не считается сам блок — понятная ошибка «Прогноз кусковатости по блоку не посчитан: …» (422). Спека просит понятное поведение, но конкретного не задаёт.
5. **Испорченный блок `kuzram` в записи объекта** (например, поправка C(A) = 50) — умолчания и предупреждение. Фронт при чтении такие значения обрезает до границ, сервер не обрезает, а отказывается от них открыто.
6. **Поправки `Calibration.rock_factor_A` и `drill_deviation_m`** новые модели не применяют и пишут предупреждение: фактор породы и σ задаются настройками модели объекта. Поправки формы кривой (`uniformity_n`, `swebrec_b`, `xmax_mm`) работают как раньше.
7. **Датасеты ML.** После выката PR 2 новые прогнозы (версия 2.0.0), сохранённые в результатах взрывов, начнут попадать в датасеты как `predicted_x50_mm` рядом со старыми. PR 2 этого не блокирует (схема датасетов по спеке не меняется); обучение калибровок на смешанной базе нужно закрыть в PR 3 или не запускать до него.

## Общие ограничения

- Ветка от `origin/main`, работа в отдельном worktree. **Не пушить в `main` и ничего не сливать**: push в `main` сразу выкатывает прод (`.github/workflows/deploy.yml`).
- Python-команды из корня worktree: `../../../.venv/bin/python -m pytest <путь> -q -p no:cacheprovider`.
- Фронт: в свежем worktree сначала `npm --prefix frontend ci`; тесты — `npm --prefix frontend test -- <путь>`, типы и сборка — `npm --prefix frontend run build`.
- Комментарии, сообщения об ошибках, тексты интерфейса и коммиты — по-русски.
- Единицы в именах: длины — метры, диаметр скважины — миллиметры, плотность — т/м³, трещиноватость — 1/м, куски — мм.
- Формулы Каннингема, границы и умолчания `KuzRamSettings` не меняются. Числа листа «Расчёт» не меняются: `tests/fixtures/kuzram_cunningham_golden.json`, `tests/test_kuzram_control_example.py`, `tests/test_kuzram_frontend_contract.py` правке не подлежат.
- Старые модели считают ровно как до PR 2: это закрепляет `tests/fixtures/fragmentation_legacy_golden.json` (задача 4); править его после создания нельзя.
- Сохранённые прогнозы, датасеты и записи `calc_object_inputs` не пересчитываются и не переписываются; миграций базы нет.
- Идентификаторы моделей: `kuznetsov`, `kuzram`, `swebrec` (версия `2.0.0`) и `kuznetsov_legacy`, `kuzram_legacy`, `swebrec_legacy` (версия `1.0.0`). Умолчание везде — `kuzram`.
- Если после смены чисел падает существующий тест сценариев, оптимизации или рекомендаций, сначала понять, проверяет он поведение или старое число. Поведение не подгонять; ожидание старого числа поправить и перечислить такие правки в описании PR.

## На что смотреть ревью

Входные величины и условия, которые спека подразумевает, но ни один её тест не трогает. Тесты на них добавлены в задачи, которым принадлежит код.

1. **Паспорт пишет пустые величины нулём** — нулевая сила ВВ, масса заряда, высота уступа или длина заряда в одной скважине. Ожидание: скважина пропущена с предупреждением «Скважина 1-01: прогноз не посчитан — …», остальные посчитаны; L/H без длины заряда — предупреждение, а не ноль в n (задача 5).
2. **Прогноз без объекта работ** — панель, паспорт сохранённого плана, базовый сценарий. Ожидание: активный объект организации, иначе умолчания; источник виден пользователю (задачи 6–8, 10).
3. **Объект работ без сохранённого блока `kuzram` или с испорченным блоком.** Ожидание: умолчания; во втором случае — предупреждение с именем объекта (задача 6).
4. **Старая калибровка ML поверх нового прогноза.** Ожидание: не применяется, предупреждение «нужно переобучить» (задача 9).
5. **Сохранённый прогноз старого формата** (без `warnings`, `settings`, длины заряда) — читается без ошибки, как до PR 2 (задача 1).

---

### Задача 1: типы данных прогноза

**Файлы:**
- Изменить: `simulation/fragmentation/models.py` (константы моделей — строки 13–16; `FragmentationInputs` — 56–100; `ModelProvenance` — 103–130; `PredictedFragmentation` — 174–212)
- Изменить: `api/schemas/design.py` (`ModelProvenanceSchema` — 1245; `PredictedFragmentationSchema` — 1253; `FragmentationInputsSchema` — 1286)
- Создать тест: `tests/test_fragmentation_types.py`

**Интерфейсы:**
- Отдаёт: константы `MODEL_KUZNETSOV`, `MODEL_KUZRAM`, `MODEL_SWEBREC`, `MODEL_KUZNETSOV_LEGACY`, `MODEL_KUZRAM_LEGACY`, `MODEL_SWEBREC_LEGACY`, `LEGACY_MODEL_SUFFIX = "_legacy"`, `FRAGMENTATION_MODEL_IDS` (шесть); поля `FragmentationInputs.charge_length_m: float = 0.0`, `FragmentationInputs.hole_length_m: float = 0.0`, `ModelProvenance.settings: dict[str, Any]`, `PredictedFragmentation.warnings: list[str]`. Их используют задачи 2–10.

- [ ] **Шаг 1: Написать падающие тесты**

Создать `tests/test_fragmentation_types.py`:

```python
"""Типы кусковатости: новые поля читаются из старых записей и не теряются."""
import unittest

from api.schemas.design import FragmentationInputsSchema, PredictedFragmentationSchema
from simulation.fragmentation.models import (
    FRAGMENTATION_MODEL_IDS,
    LEGACY_MODEL_SUFFIX,
    FragmentationInputs,
    ModelProvenance,
    PredictedFragmentation,
)
from tests.test_fragmentation_kuzram import _inputs


class FragmentationTypesTests(unittest.TestCase):
    def test_six_model_ids(self):
        self.assertEqual(
            FRAGMENTATION_MODEL_IDS,
            ("kuznetsov", "kuzram", "swebrec", "kuznetsov_legacy", "kuzram_legacy", "swebrec_legacy"),
        )
        self.assertEqual(LEGACY_MODEL_SUFFIX, "_legacy")

    def test_old_inputs_payload_reads_zero_lengths(self):
        payload = _inputs().to_dict()
        payload.pop("charge_length_m")
        payload.pop("hole_length_m")

        inputs = FragmentationInputs.from_dict(payload)

        self.assertEqual(inputs.charge_length_m, 0.0)
        self.assertEqual(inputs.hole_length_m, 0.0)

    def test_inputs_lengths_round_trip(self):
        inputs = _inputs(charge_length_m=8.0, hole_length_m=11.0)

        restored = FragmentationInputs.from_dict(inputs.to_dict())

        self.assertEqual(restored.charge_length_m, 8.0)
        self.assertEqual(restored.hole_length_m, 11.0)
        self.assertEqual(FragmentationInputsSchema(**inputs.to_dict()).charge_length_m, 8.0)

    def test_old_prediction_payload_reads_without_warnings_and_settings(self):
        payload = {
            "x20_mm": 50.0,
            "x50_mm": 150.0,
            "x80_mm": 300.0,
            "oversize_pct": 4.0,
            "powder_factor_kg_m3": 0.7,
            "provenance": {"model": "kuzram", "model_version": "1.0.0"},
        }

        prediction = PredictedFragmentation.from_dict(payload)

        self.assertEqual(prediction.warnings, [])
        self.assertEqual(prediction.provenance.settings, {})
        self.assertEqual(PredictedFragmentationSchema(**prediction.to_dict()).warnings, [])

    def test_prediction_warnings_and_settings_round_trip(self):
        snapshot = {
            "source": "work_object",
            "work_object_name": "Карьер-1",
            "values": {"rock_factor_correction": 1.3},
            "warnings": [],
        }
        prediction = PredictedFragmentation(
            x20_mm=50.0,
            x50_mm=150.0,
            x80_mm=300.0,
            oversize_pct=4.0,
            powder_factor_kg_m3=0.7,
            provenance=ModelProvenance(model="kuzram", model_version="2.0.0", settings=snapshot),
            warnings=["Длина заряда не задана."],
        )

        payload = prediction.to_dict()
        restored = PredictedFragmentation.from_dict(payload)
        schema = PredictedFragmentationSchema(**payload)

        self.assertEqual(restored.warnings, ["Длина заряда не задана."])
        self.assertEqual(restored.provenance.settings, snapshot)
        self.assertEqual(schema.warnings, ["Длина заряда не задана."])
        self.assertEqual(schema.provenance.settings["work_object_name"], "Карьер-1")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Шаг 2: Убедиться, что тесты падают**

Запуск: `../../../.venv/bin/python -m pytest tests/test_fragmentation_types.py -q -p no:cacheprovider`
Ожидание: FAIL — `ImportError: cannot import name 'LEGACY_MODEL_SUFFIX'`.

- [ ] **Шаг 3: Константы моделей**

В `simulation/fragmentation/models.py` заменить строки 13–16 на:

```python
MODEL_KUZNETSOV = "kuznetsov"
MODEL_KUZRAM = "kuzram"
MODEL_SWEBREC = "swebrec"
# Прежние формулы (до PR 2 — Кузнецов с фактором A по Лилли) живут в
# simulation/fragmentation/legacy/ под этими именами.
LEGACY_MODEL_SUFFIX = "_legacy"
MODEL_KUZNETSOV_LEGACY = MODEL_KUZNETSOV + LEGACY_MODEL_SUFFIX
MODEL_KUZRAM_LEGACY = MODEL_KUZRAM + LEGACY_MODEL_SUFFIX
MODEL_SWEBREC_LEGACY = MODEL_SWEBREC + LEGACY_MODEL_SUFFIX
FRAGMENTATION_MODEL_IDS = (
    MODEL_KUZNETSOV,
    MODEL_KUZRAM,
    MODEL_SWEBREC,
    MODEL_KUZNETSOV_LEGACY,
    MODEL_KUZRAM_LEGACY,
    MODEL_SWEBREC_LEGACY,
)
```

- [ ] **Шаг 4: Длины заряда и скважины во входных величинах**

В `FragmentationInputs` после `influence_volume_m3: float = 0.0` добавить:

```python
    # Длина заряда нужна множителю L/H в n по Каннингему; 0 — не задана
    # (старые записи, неполный паспорт). Длина скважины — для справки.
    charge_length_m: float = 0.0
    hole_length_m: float = 0.0
```

В `FragmentationInputs.from_dict` после строки `influence_volume_m3=...` добавить:

```python
            charge_length_m=float(data.get("charge_length_m", 0.0) or 0.0),
            hole_length_m=float(data.get("hole_length_m", 0.0) or 0.0),
```

- [ ] **Шаг 5: Снимок настроек в provenance и предупреждения прогноза**

В `ModelProvenance` после `calibration: dict[str, Any] = field(default_factory=dict)` добавить:

```python
    # Снимок применённых настроек Kuz-Ram и их источник; у старых моделей и
    # у прогнозов до PR 2 пусто.
    settings: dict[str, Any] = field(default_factory=dict)
```

В `ModelProvenance.to_dict` после `"calibration": dict(self.calibration),` добавить `"settings": dict(self.settings),`, в `from_dict` после `calibration=...` добавить:

```python
            settings=dict(data.get("settings", {}) or {}),
```

В `PredictedFragmentation` между `provenance: ModelProvenance = ...` и `role: str = ROLE_PREDICTED` добавить:

```python
    warnings: list[str] = field(default_factory=list)
```

В `PredictedFragmentation.to_dict` после `"provenance": self.provenance.to_dict(),` добавить `"warnings": list(self.warnings),`, в `from_dict` после `provenance=...` добавить:

```python
            warnings=[str(item) for item in data.get("warnings", []) or []],
```

- [ ] **Шаг 6: Те же поля в схемах API**

В `api/schemas/design.py`:

```python
class ModelProvenanceSchema(BaseModel):
    model: str
    model_version: str
    inputs: dict[str, Any] = Field(default_factory=dict)
    parameters: dict[str, Any] = Field(default_factory=dict)
    calibration: dict[str, Any] = Field(default_factory=dict)
    settings: dict[str, Any] = Field(default_factory=dict)
```

В `PredictedFragmentationSchema` после `provenance: ModelProvenanceSchema` добавить `warnings: list[str] = Field(default_factory=list)`. В `FragmentationInputsSchema` после `influence_volume_m3: float = 0.0` добавить:

```python
    charge_length_m: float = 0.0
    hole_length_m: float = 0.0
```

- [ ] **Шаг 7: Убедиться, что тесты проходят, и прогнать соседние**

Запуск: `../../../.venv/bin/python -m pytest tests/test_fragmentation_types.py tests/test_fragmentation_engine.py tests/test_api_fragmentation.py tests/test_fragmentation_kuzram.py -q -p no:cacheprovider`
Ожидание: PASS.

- [ ] **Шаг 8: Коммит**

```bash
git add simulation/fragmentation/models.py api/schemas/design.py tests/test_fragmentation_types.py
git commit -m "Кусковатость: длина заряда, предупреждения и снимок настроек в типах прогноза"
```

---

### Задача 2: длина заряда в регионах влияния

**Файлы:**
- Изменить: `simulation/fragmentation/regions.py` (новая функция перед `_influence_volume_m3`; `FragmentationInputs(...)` в `collect_hole_regions` — 285–303; в `aggregate_region` — 347–365)
- Тест: `tests/test_fragmentation_engine.py`

**Интерфейсы:**
- Использует: `FragmentationInputs.charge_length_m`, `hole_length_m` из задачи 1.
- Отдаёт: регионы скважин, доменов и блока с заполненной длиной заряда — от неё зависит n новых моделей (задачи 3–5).

- [ ] **Шаг 1: Написать падающие тесты**

В `tests/test_fragmentation_engine.py` заменить импорт `from simulation.fragmentation.regions import ExplosiveSpec, RockSpec` на

```python
from simulation.fragmentation.regions import ExplosiveSpec, RockSpec, collect_regions
```

и добавить класс перед `BlastEngineRegressionTests`:

```python
class RegionLengthTests(unittest.TestCase):
    """Длина заряда нужна множителю L/H: без неё n новой модели берёт 1."""

    def _regions(self, design):
        return collect_regions(
            design,
            lump_size_mm=400.0,
            default_rock=RockSpec("Гранит", 2.65, 150.0, 2.0),
            default_explosive=ExplosiveSpec("АНФО", 0.82, 3.8),
        )

    def _hole_region(self, holes, hole_id):
        return next(region for region in holes if region.hole_ids == [hole_id])

    def test_charge_length_is_sum_of_explosive_decks(self):
        design = _design_with_charges()
        holes, _domains, site, _warnings = self._regions(design)

        region = self._hole_region(holes, design.loads[0].hole_id)

        # Скважина 11 м (уступ 10 + перебур 1), забойка 3 м, заряд 3–11 м.
        self.assertAlmostEqual(region.inputs.charge_length_m, 8.0)
        self.assertAlmostEqual(region.inputs.hole_length_m, 11.0)
        self.assertAlmostEqual(site.inputs.charge_length_m, 8.0)
        self.assertAlmostEqual(site.inputs.hole_length_m, 11.0)

    def test_air_gap_is_not_charge(self):
        design = _design_with_charges()
        charge = next(deck for deck in design.loads[0].decks if deck.kind == "charge")
        charge.to_m = 9.0  # заряд 3–9 м, ниже — пустота

        holes, *_ = self._regions(design)

        self.assertAlmostEqual(self._hole_region(holes, design.loads[0].hole_id).inputs.charge_length_m, 6.0)

    def test_without_decks_charge_is_hole_minus_stemming(self):
        design = _design_with_charges()
        hole_id = design.holes[0].id
        design.loads = []
        design.charge_rules = dict(design.charge_rules, stemming_m=2.5)

        holes, *_ = self._regions(design)

        self.assertAlmostEqual(self._hole_region(holes, hole_id).inputs.charge_length_m, 8.5)
```

- [ ] **Шаг 2: Убедиться, что тесты падают**

Запуск: `../../../.venv/bin/python -m pytest tests/test_fragmentation_engine.py -k RegionLength -q -p no:cacheprovider`
Ожидание: FAIL — `AssertionError: 0.0 != 8.0 within 7 places`.

- [ ] **Шаг 3: Реализация**

В `simulation/fragmentation/regions.py` перед `def _influence_volume_m3` добавить:

```python
def _charge_length_m(load: HoleLoad | None, hole: Hole, stemming_m: float) -> float:
    """Длина заряда, м: сумма взрывчатых дек, без дек — скважина минус забойка.

    Воздушный промежуток между деками зарядом не считается: для множителя
    L/H в n по Каннингему нужна длина ВВ, а не «скважина минус забойка».
    """
    if load is not None:
        length = sum(
            max(0.0, deck.to_m - deck.from_m)
            for deck in load.decks
            if is_explosive_deck_kind(deck.kind) and deck.mass_kg > 0
        )
        if length > 0:
            return length
    return max(0.0, hole.length_m - stemming_m)
```

В `collect_hole_regions`, в вызове `FragmentationInputs(...)`, после `influence_volume_m3=volume,` добавить:

```python
            charge_length_m=_charge_length_m(load, hole, stemming),
            hole_length_m=hole.length_m,
```

В `aggregate_region`, в вызове `FragmentationInputs(...)`, после `influence_volume_m3=volume,` добавить:

```python
        charge_length_m=avg(lambda inp: inp.charge_length_m),
        hole_length_m=avg(lambda inp: inp.hole_length_m),
```

- [ ] **Шаг 4: Убедиться, что тесты проходят**

Запуск: `../../../.venv/bin/python -m pytest tests/test_fragmentation_engine.py tests/test_api_fragmentation.py -q -p no:cacheprovider`
Ожидание: PASS.

- [ ] **Шаг 5: Коммит**

```bash
git add simulation/fragmentation/regions.py tests/test_fragmentation_engine.py
git commit -m "Кусковатость: длина заряда в регионах влияния — по взрывчатым декам"
```

---

### Задача 3: общая база — регион в `predict_point`

**Файлы:**
- Создать: `simulation/fragmentation/base.py`
- Создать тест: `tests/test_fragmentation_base.py`

**Интерфейсы:**
- Использует: `cunningham.KuzRamSettings`, `cunningham.KuzRamPoint`, `cunningham.predict_point` (PR 1); `FragmentationInputs.charge_length_m` (задача 1).
- Отдаёт:
  - `charged_diameter_mm(inputs: FragmentationInputs) -> float`
  - `region_point(inputs: FragmentationInputs, settings: KuzRamSettings | None = None) -> KuzRamPoint` — поднимает `ValueError` с русским текстом на вырожденных входах (контракт `predict_point`);
  - `base_parameters(point: KuzRamPoint, inputs: FragmentationInputs) -> dict[str, Any]`;
  - `calibration_warnings(calibration: Calibration) -> list[str]`.
  Их зовут новые модели (задача 4) и движок (задача 5).

- [ ] **Шаг 1: Написать падающие тесты**

Создать `tests/test_fragmentation_base.py`:

```python
"""Общая база «Проектирования» и лист «Расчёт» — одна функция прогноза.

Критерий успеха спеки: при одинаковых входных величинах и настройках числа
совпадают. Тест строит входные величины региона из точки листа «Расчёт» и
сравнивает прогноз до 1e-9.
"""
import unittest

from Blast import BlastEngine, ExplosiveProperties, RockProperties, TargetParams
from simulation.fragmentation.base import (
    base_parameters,
    calibration_warnings,
    charged_diameter_mm,
    region_point,
)
from simulation.fragmentation.cunningham import KuzRamSettings
from simulation.fragmentation.models import Calibration, FragmentationInputs
from tests.test_fragmentation_kuzram import _inputs

ROCKS = (
    RockProperties("Габбро-диабаз", 2.9, 168, 2.2),
    RockProperties("Гранит", 2.65, 150, 2.0),
    RockProperties("Известняк трещиноватый", 2.4, 60, 4.0),
)
SETTINGS = (
    KuzRamSettings(),
    KuzRamSettings(rock_factor_method="joint_factor", joint_condition=1.5, joint_angle=30),
    KuzRamSettings(rock_factor_method="rmd10", strength_exponent="19/30", drill_deviation_m=0.3, uniformity_correction=1.2),
    KuzRamSettings(rock_factor_method="manual", rock_factor_manual=8.0, rock_factor_correction=1.4),
)
CROWNS_MM = (110, 152, 250)
Q_KG_M3 = (0.6, 1.26)
SPACING_COEFFS = (1.0, 1.25)


def _inputs_from_point(engine: BlastEngine, crown_mm: float, point) -> FragmentationInputs:
    """Входные величины региона, равные тем, что лист «Расчёт» подал в predict_point."""
    return FragmentationInputs(
        burden_m=point.burden_m,
        spacing_m=point.spacing_m,
        bench_height_m=engine.target.bench_height_m,
        diameter_mm=crown_mm,
        charge_mass_kg=point.charge_mass_kg,
        powder_factor_kg_m3=point.q_kg_m3,
        stemming_m=0.0,
        explosive_name=engine.explosive.name,
        explosive_density_t_m3=engine.explosive.density_t_m3,
        explosive_energy_mj_kg=engine.explosive.power_mj_kg,
        rock_name=engine.rock.name,
        rock_density_t_m3=engine.rock.density_t_m3,
        rock_ucs_mpa=engine.rock.ucs_mpa,
        rock_fissuring=engine.rock.fissuring_ff,
        lump_size_mm=engine.target.lump_size_mm,
        hole_oversize_coeff=engine.target.hole_oversize_coeff,
        charge_length_m=point.charge_length_m,
        hole_length_m=engine.target.bench_height_m + engine.target.overdrill_m,
    )


class CalcSheetParityTests(unittest.TestCase):
    def test_region_point_matches_kuzram_point(self):
        explosive = ExplosiveProperties("ЭВЕРСИН Э-100", 1.12, 2.99)
        for rock in ROCKS:
            for spacing_coeff in SPACING_COEFFS:
                target = TargetParams(
                    lump_size_mm=400, hole_diameter_mm=0, bench_height_m=10.0, spacing_coeff_m=spacing_coeff
                )
                engine = BlastEngine(rock, explosive, target)
                for settings in SETTINGS:
                    for crown_mm in CROWNS_MM:
                        for q in Q_KG_M3:
                            with self.subTest(rock=rock.name, a_w=spacing_coeff, settings=settings, crown=crown_mm, q=q):
                                sheet = engine.kuzram_point(crown_mm, q, settings)
                                point = region_point(_inputs_from_point(engine, crown_mm, sheet), settings)
                                self.assertAlmostEqual(point.x50_mm, sheet.x50_mm, places=9)
                                self.assertAlmostEqual(point.uniformity.value, sheet.uniformity_n, places=9)
                                self.assertAlmostEqual(point.uniformity.raw, sheet.uniformity_n_raw, places=9)
                                self.assertAlmostEqual(point.oversize_pct, sheet.oversize_pct, places=9)
                                self.assertAlmostEqual(point.rock.value, sheet.rock_factor_a, places=9)
                                self.assertEqual(point.warnings, ())

    def test_charged_diameter_is_computed_like_calc_sheet(self):
        inputs = _inputs(diameter_mm=152.0, hole_oversize_coeff=1.05)
        # Blast.py::_charge: d_m = коронка / 1000 · коэффициент, затем d_m · 1000.
        self.assertEqual(charged_diameter_mm(inputs), 152.0 / 1000 * 1.05 * 1000)


class RegionPointTests(unittest.TestCase):
    def test_missing_charge_length_warns(self):
        point = region_point(_inputs(charge_length_m=0.0))

        self.assertEqual(point.uniformity.charge_to_bench, 1.0)
        self.assertEqual(len(point.warnings), 1)
        self.assertIn("L/H", point.warnings[0])

    def test_zero_explosive_energy_is_russian_error(self):
        with self.assertRaises(ValueError) as ctx:
            region_point(_inputs(explosive_energy_mj_kg=0.0, charge_length_m=7.0))

        self.assertIn("сила ВВ", str(ctx.exception))

    def test_base_parameters_are_unrounded(self):
        inputs = _inputs(charge_length_m=7.0)
        point = region_point(inputs)

        parameters = base_parameters(point, inputs)

        self.assertEqual(parameters["x50_mm"], point.x50_mm)
        self.assertEqual(parameters["rock_factor_A"], point.rock.value)
        self.assertEqual(parameters["uniformity_n_cunningham"], point.uniformity.value)
        self.assertEqual(parameters["rock_factor"]["method"], "rmd50")
        self.assertEqual(parameters["hole_diameter_mm"], charged_diameter_mm(inputs))

    def test_calibration_warnings_name_ignored_overrides(self):
        self.assertEqual(calibration_warnings(Calibration(uniformity_n=1.5, swebrec_b=2.0, xmax_mm=900.0)), [])

        warnings = calibration_warnings(Calibration(rock_factor_A=7.0, drill_deviation_m=0.2))

        self.assertEqual(len(warnings), 1)
        self.assertIn("фактор породы A", warnings[0])
        self.assertIn("отклонение бурения σ", warnings[0])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Шаг 2: Убедиться, что тесты падают**

Запуск: `../../../.venv/bin/python -m pytest tests/test_fragmentation_base.py -q -p no:cacheprovider`
Ожидание: FAIL — `ModuleNotFoundError: No module named 'simulation.fragmentation.base'`.

- [ ] **Шаг 3: Реализация**

Создать `simulation/fragmentation/base.py`:

```python
"""Общая база моделей кусковатости «Проектирования»: A, x50 и n по Каннингему.

Все три модели движка (kuznetsov, kuzram, swebrec) берут фактор породы,
средний кусок и индекс равномерности отсюда, а этот модуль — из
cunningham.predict_point, той же функции, что считает лист «Расчёт». Модели
различаются только кривой распределения. Здесь нет ни одной формулы: только
перевод входных величин региона в аргументы predict_point.
"""
from __future__ import annotations

from dataclasses import asdict
from typing import Any

from simulation.fragmentation.cunningham import KuzRamPoint, KuzRamSettings, predict_point
from simulation.fragmentation.models import Calibration, FragmentationInputs
from simulation.fragmentation.units import length_m_from_mm, length_mm_from_m, relative_weight_strength

# Поправки калибровки, которые новая база не применяет: фактор породы и
# отклонение бурения задают настройки модели объекта работ.
_IGNORED_CALIBRATION = (
    ("rock_factor_A", "фактор породы A"),
    ("drill_deviation_m", "отклонение бурения σ"),
)


def charged_diameter_mm(inputs: FragmentationInputs) -> float:
    """Диаметр скважины с коэффициентом разбуривания, мм.

    Порядок действий повторяет Blast.py::_charge (коронка / 1000 ·
    коэффициент, затем обратно в мм), чтобы числа совпадали до бита.
    """
    return length_mm_from_m(length_m_from_mm(inputs.diameter_mm) * inputs.hole_oversize_coeff)


def region_point(inputs: FragmentationInputs, settings: KuzRamSettings | None = None) -> KuzRamPoint:
    """Прогноз Kuz-Ram по Каннингему для одного региона влияния.

    Вырожденные величины (нуль, минус, NaN, inf) predict_point отклоняет
    ValueError с русским текстом; нулевая длина заряда или высота уступа
    дают предупреждение в KuzRamPoint.warnings.
    """
    return predict_point(
        settings or KuzRamSettings(),
        ucs_mpa=inputs.rock_ucs_mpa,
        density_t_m3=inputs.rock_density_t_m3,
        fissuring_per_m=inputs.rock_fissuring,
        burden_m=inputs.burden_m,
        spacing_m=inputs.spacing_m,
        hole_diameter_mm=charged_diameter_mm(inputs),
        powder_factor_kg_m3=inputs.powder_factor_kg_m3,
        charge_mass_kg=inputs.charge_mass_kg,
        re_weight=relative_weight_strength(inputs.explosive_energy_mj_kg),
        charge_length_m=inputs.charge_length_m,
        bench_height_m=inputs.bench_height_m,
        lump_size_mm=inputs.lump_size_mm,
    )


def base_parameters(point: KuzRamPoint, inputs: FragmentationInputs) -> dict[str, Any]:
    """Параметры базы для provenance — без округления, как их посчитала модель."""
    return {
        "rock_factor_A": point.rock.value,
        "rock_factor": asdict(point.rock),
        "re_weight": relative_weight_strength(inputs.explosive_energy_mj_kg),
        "x50_mm": point.x50_mm,
        "uniformity_n_raw": point.uniformity.raw,
        "uniformity_n_cunningham": point.uniformity.value,
        "charge_to_bench": point.uniformity.charge_to_bench,
        "hole_diameter_mm": charged_diameter_mm(inputs),
        "spacing_to_burden": inputs.spacing_m / inputs.burden_m,
    }


def calibration_warnings(calibration: Calibration) -> list[str]:
    """Предупреждение о поправках, которые новая база не применяет."""
    ignored = [label for name, label in _IGNORED_CALIBRATION if getattr(calibration, name) is not None]
    if not ignored:
        return []
    return [
        f"Поправки калибровки ({', '.join(ignored)}) новая модель не применяет: "
        "их задают настройки модели объекта работ."
    ]
```

- [ ] **Шаг 4: Убедиться, что тесты проходят**

Запуск: `../../../.venv/bin/python -m pytest tests/test_fragmentation_base.py -q -p no:cacheprovider`
Ожидание: PASS. Если `test_region_point_matches_kuzram_point` расходится в девятом знаке — ничего не подгонять: найти, где порядок действий отличается от `Blast.py::kuzram_point` (диаметр, `spacing_m / burden_m`, RE), и сообщить координатору.

- [ ] **Шаг 5: Коммит**

```bash
git add simulation/fragmentation/base.py tests/test_fragmentation_base.py
git commit -m "Кусковатость: общая база «Проектирования» зовёт predict_point листа «Расчёт»"
```

---

### Задача 4: шесть моделей — новые на общей базе, старые в `legacy/`

**Файлы:**
- Создать: `tests/fixtures/fragmentation_legacy_golden.json` (генерирует шаг 1), `tests/test_fragmentation_legacy.py`, `tests/test_fragmentation_new_models.py`
- Перенести: `simulation/fragmentation/{kuznetsov,kuzram,swebrec}.py` → `simulation/fragmentation/legacy/`; создать `simulation/fragmentation/legacy/__init__.py`
- Создать заново: `simulation/fragmentation/kuznetsov.py`, `simulation/fragmentation/kuzram.py`, `simulation/fragmentation/swebrec.py`
- Изменить: `simulation/fragmentation/distributions.py` (перенос `default_xmax_mm`), `simulation/fragmentation/engine.py` (строки 1–93 целиком и сигнатура `predict_design`), `api/schemas/design.py` (`FragmentationModelInfoSchema`), `Blast.py:9-10` и док-строка `_legacy_uniformity_raw`, `design/reporting/engine.py:34`, `design/scenarios/types.py:73,123`, `design/scenarios/engine.py:252`
- Изменить тесты: `tests/test_fragmentation_kuzram.py`, `tests/test_fragmentation_kuznetsov.py`, `tests/test_fragmentation_swebrec.py`, `tests/test_blast_optimizer.py:9-10`, `tests/test_fragmentation_engine.py`, `tests/test_api_fragmentation.py:52`

**Интерфейсы:**
- Использует: `region_point`, `base_parameters`, `calibration_warnings` (задача 3); константы моделей (задача 1).
- Отдаёт:
  - `predict_kuznetsov / predict_kuzram / predict_swebrec(inputs, calibration=None, settings=None) -> PredictedFragmentation` в новых модулях, `MODEL_VERSION = "2.0.0"`;
  - `simulation.fragmentation.legacy.{kuznetsov,kuzram,swebrec}` с прежними функциями, `MODEL_ID = "*_legacy"`, `MODEL_VERSION = "1.0.0"`;
  - в `engine.py`: `PredictFn = Callable[[FragmentationInputs, Calibration | None, KuzRamSettings | None], PredictedFragmentation]`, `FRAGMENTATION_MODELS` (шесть записей с ключами `id`, `version`, `label`, `distribution`, `legacy`), `list_models()`, `resolve_model(model) -> str`, `is_legacy_model(model) -> bool`, `predict_region(inputs, model, calibration, settings)`, `predict_design(..., settings=None)`;
  - `distributions.default_xmax_mm(burden_m, spacing_m, x50_mm) -> float`.

- [ ] **Шаг 1: Зафиксировать числа старых моделей до переноса**

Файлы ещё на старых местах. Из корня worktree:

```bash
../../../.venv/bin/python - <<'PY'
import json
from pathlib import Path

from simulation.fragmentation.kuznetsov import predict_kuznetsov
from simulation.fragmentation.kuzram import predict_kuzram
from simulation.fragmentation.models import Calibration
from simulation.fragmentation.swebrec import predict_swebrec
from tests.test_fragmentation_kuzram import _inputs

CASES = {
    "base": {},
    "tight_burden": {"burden_m": 2.5, "spacing_m": 3.0},
    "soft_rock": {"rock_ucs_mpa": 40.0, "rock_density_t_m3": 2.2, "powder_factor_kg_m3": 0.4},
    "big_hole": {"diameter_mm": 250.0, "charge_mass_kg": 400.0, "burden_m": 7.0, "spacing_m": 8.0},
}
CALIBRATIONS = {
    "none": {},
    "overrides": {"rock_factor_A": 7.5, "uniformity_n": 1.4, "swebrec_b": 2.5, "xmax_mm": 3000.0, "drill_deviation_m": 0.3},
}
PREDICTORS = {"kuznetsov": predict_kuznetsov, "kuzram": predict_kuzram, "swebrec": predict_swebrec}

rows = []
for model, predict in PREDICTORS.items():
    for case, overrides in CASES.items():
        for name, values in CALIBRATIONS.items():
            payload = predict(_inputs(**overrides), Calibration.from_dict(values)).to_dict()
            rows.append({
                "model": model,
                "case": case,
                "calibration": name,
                "x20_mm": payload["x20_mm"],
                "x50_mm": payload["x50_mm"],
                "x80_mm": payload["x80_mm"],
                "oversize_pct": payload["oversize_pct"],
                "curve": payload["curve"],
                "parameters": payload["provenance"]["parameters"],
            })
Path("tests/fixtures/fragmentation_legacy_golden.json").write_text(
    json.dumps({"cases": CASES, "calibrations": CALIBRATIONS, "rows": rows}, ensure_ascii=False, indent=1) + "\n",
    encoding="utf-8",
)
print(len(rows), "строк")
PY
```

Ожидание: `24 строк`. Коммит отдельно — чтобы ревьюер видел, что эталон снят со старого кода:

```bash
git add tests/fixtures/fragmentation_legacy_golden.json
git commit -m "Кусковатость: эталон чисел старых моделей до переноса в legacy/"
```

- [ ] **Шаг 2: Написать падающие тесты старых моделей**

Создать `tests/test_fragmentation_legacy.py`:

```python
"""Старые модели после переноса в legacy/ считают ровно как до PR 2."""
import json
import unittest
from pathlib import Path

from simulation.fragmentation.legacy import kuznetsov, kuzram, swebrec
from simulation.fragmentation.models import Calibration
from tests.test_fragmentation_kuzram import _inputs

GOLDEN = Path(__file__).parent / "fixtures" / "fragmentation_legacy_golden.json"
PREDICTORS = {
    "kuznetsov": kuznetsov.predict_kuznetsov,
    "kuzram": kuzram.predict_kuzram,
    "swebrec": swebrec.predict_swebrec,
}


class LegacyGoldenTests(unittest.TestCase):
    def test_numbers_match_pre_move_snapshot(self):
        data = json.loads(GOLDEN.read_text(encoding="utf-8"))
        for row in data["rows"]:
            with self.subTest(model=row["model"], case=row["case"], calibration=row["calibration"]):
                calibration = Calibration.from_dict(data["calibrations"][row["calibration"]])
                payload = PREDICTORS[row["model"]](_inputs(**data["cases"][row["case"]]), calibration).to_dict()
                for key in ("x20_mm", "x50_mm", "x80_mm", "oversize_pct", "curve"):
                    self.assertEqual(payload[key], row[key])
                self.assertEqual(payload["provenance"]["parameters"], row["parameters"])

    def test_ids_and_versions(self):
        self.assertEqual(
            (kuznetsov.MODEL_ID, kuzram.MODEL_ID, swebrec.MODEL_ID),
            ("kuznetsov_legacy", "kuzram_legacy", "swebrec_legacy"),
        )
        self.assertEqual({kuznetsov.MODEL_VERSION, kuzram.MODEL_VERSION, swebrec.MODEL_VERSION}, {"1.0.0"})


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Шаг 3: Написать падающие тесты новых моделей**

Создать `tests/test_fragmentation_new_models.py`:

```python
"""Новые модели движка: общая база Каннингема, различие — только кривая."""
import unittest

from simulation.fragmentation.base import region_point
from simulation.fragmentation.cunningham import KuzRamSettings
from simulation.fragmentation.distributions import DEFAULT_KUZNETSOV_N, rosin_rammler_oversize_pct
from simulation.fragmentation.kuznetsov import predict_kuznetsov
from simulation.fragmentation.kuzram import predict_kuzram
from simulation.fragmentation.models import Calibration
from simulation.fragmentation.swebrec import predict_swebrec
from tests.test_fragmentation_kuzram import _inputs

PREDICTORS = (predict_kuznetsov, predict_kuzram, predict_swebrec)


class NewModelsTests(unittest.TestCase):
    def test_kuzram_is_region_point(self):
        inputs = _inputs(charge_length_m=7.0)
        settings = KuzRamSettings(rock_factor_correction=1.2)
        point = region_point(inputs, settings)

        prediction = predict_kuzram(inputs, None, settings)

        self.assertEqual(prediction.x50_mm, round(point.x50_mm, 1))
        self.assertEqual(prediction.oversize_pct, round(point.oversize_pct, 2))
        self.assertEqual(prediction.provenance.parameters["uniformity_n"], point.uniformity.value)
        self.assertEqual(prediction.provenance.parameters["x50_mm"], point.x50_mm)
        self.assertEqual((prediction.provenance.model, prediction.provenance.model_version), ("kuzram", "2.0.0"))
        self.assertEqual(prediction.warnings, [])

    def test_three_models_share_base(self):
        inputs = _inputs(charge_length_m=7.0)

        predictions = [predict(inputs) for predict in PREDICTORS]

        self.assertEqual({item.x50_mm for item in predictions}, {predictions[0].x50_mm})
        self.assertEqual(
            {item.provenance.parameters["rock_factor_A"] for item in predictions},
            {predictions[0].provenance.parameters["rock_factor_A"]},
        )
        self.assertEqual([item.provenance.model for item in predictions], ["kuznetsov", "kuzram", "swebrec"])
        self.assertEqual({item.provenance.model_version for item in predictions}, {"2.0.0"})

    def test_kuznetsov_uses_fixed_n(self):
        prediction = predict_kuznetsov(_inputs(charge_length_m=7.0))

        self.assertEqual(prediction.provenance.parameters["uniformity_n"], DEFAULT_KUZNETSOV_N)
        self.assertEqual(prediction.provenance.parameters["distribution"], "rosin_rammler")

    def test_swebrec_curve_on_new_x50(self):
        prediction = predict_swebrec(_inputs(charge_length_m=7.0))

        self.assertEqual(prediction.provenance.parameters["distribution"], "swebrec")
        self.assertGreater(prediction.provenance.parameters["xmax_mm"], prediction.provenance.parameters["x50_mm"])

    def test_uniformity_override_is_applied(self):
        inputs = _inputs(charge_length_m=7.0)
        point = region_point(inputs)

        prediction = predict_kuzram(inputs, Calibration(uniformity_n=2.5))

        self.assertEqual(prediction.provenance.parameters["uniformity_n"], 2.5)
        self.assertEqual(prediction.oversize_pct, round(rosin_rammler_oversize_pct(point.x50_mm, 2.5, 400.0), 2))

    def test_rock_factor_override_is_ignored_with_warning(self):
        inputs = _inputs(charge_length_m=7.0)

        plain = predict_kuzram(inputs)
        overridden = predict_kuzram(inputs, Calibration(rock_factor_A=12.0))

        self.assertEqual(overridden.x50_mm, plain.x50_mm)
        self.assertTrue(any("фактор породы A" in item for item in overridden.warnings))

    def test_missing_charge_length_warns(self):
        prediction = predict_kuzram(_inputs())

        self.assertTrue(any("L/H" in item for item in prediction.warnings))

    def test_zero_charge_mass_is_russian_error(self):
        for predict in PREDICTORS:
            with self.subTest(model=predict.__name__):
                with self.assertRaises(ValueError) as ctx:
                    predict(_inputs(charge_mass_kg=0.0, charge_length_m=7.0))
                self.assertIn("Масса заряда", str(ctx.exception))

    def test_settings_change_numbers(self):
        inputs = _inputs(charge_length_m=7.0)

        plain = predict_kuzram(inputs)
        tuned = predict_kuzram(inputs, None, KuzRamSettings(rock_factor_correction=1.5))

        self.assertGreater(tuned.x50_mm, plain.x50_mm)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Шаг 4: Поправить тесты реестра и API под шесть моделей**

В `tests/test_fragmentation_engine.py` заменить импорт движка на

```python
from simulation.fragmentation.engine import is_legacy_model, list_models, predict_design, predict_region, resolve_model
```

и заменить `test_three_models_differ_in_distribution` на:

```python
    def _kwargs(self):
        return dict(
            lump_size_mm=400.0,
            default_rock=RockSpec("Гранит", 2.65, 150.0, 2.0),
            default_explosive=ExplosiveSpec("АНФО", 0.82, 3.8),
        )

    def test_new_models_share_cunningham_base(self):
        design = _design_with_charges()
        rows = {
            model: predict_design(design, model=model, **self._kwargs())["holes"][0]["prediction"]
            for model in ("kuznetsov", "kuzram", "swebrec")
        }
        self.assertEqual(len({row["x50_mm"] for row in rows.values()}), 1)
        self.assertEqual(len({row["provenance"]["parameters"]["rock_factor_A"] for row in rows.values()}), 1)
        self.assertNotEqual(rows["kuznetsov"]["x80_mm"], rows["kuzram"]["x80_mm"])
        self.assertEqual(rows["swebrec"]["provenance"]["parameters"]["distribution"], "swebrec")
        self.assertEqual({row["provenance"]["model_version"] for row in rows.values()}, {"2.0.0"})

    def test_legacy_models_keep_old_base(self):
        design = _design_with_charges()
        legacy = {
            model: predict_design(design, model=model, **self._kwargs())["holes"][0]["prediction"]
            for model in ("kuznetsov_legacy", "kuzram_legacy", "swebrec_legacy")
        }
        new = predict_design(design, model="kuzram", **self._kwargs())["holes"][0]["prediction"]
        self.assertEqual(len({row["x50_mm"] for row in legacy.values()}), 1)
        self.assertEqual({row["provenance"]["model_version"] for row in legacy.values()}, {"1.0.0"})
        self.assertNotEqual(legacy["kuzram_legacy"]["x50_mm"], new["x50_mm"])

    def test_model_version_has_one_source(self):
        design = _design_with_charges()
        for info in list_models():
            with self.subTest(model=info["id"]):
                result = predict_design(design, model=info["id"], **self._kwargs())
                self.assertEqual(result["model"], info["id"])
                self.assertEqual(result["model_version"], info["version"])
                self.assertEqual(result["site"]["prediction"]["provenance"]["model_version"], info["version"])

    def test_resolve_model_aliases(self):
        self.assertEqual(resolve_model("Kuz-Ram"), "kuzram")
        self.assertEqual(resolve_model(""), "kuzram")
        self.assertEqual(resolve_model("kuz-ram_legacy"), "kuzram_legacy")
        self.assertEqual(resolve_model("swebeck_legacy"), "swebrec_legacy")
        self.assertTrue(is_legacy_model("kuznetsov_legacy"))
        self.assertFalse(is_legacy_model("kuzram"))
        with self.assertRaises(ValueError) as ctx:
            resolve_model("ml-magic")
        self.assertIn("kuzram_legacy", str(ctx.exception))
```

В `tests/test_api_fragmentation.py` заменить `test_lists_three_models` на:

```python
    def test_lists_six_models(self):
        response = design_service.list_fragmentation_models()
        ids = [item.id for item in response.models]
        self.assertEqual(
            ids, ["kuznetsov", "kuzram", "swebrec", "kuznetsov_legacy", "kuzram_legacy", "swebrec_legacy"]
        )
        self.assertEqual([item.legacy for item in response.models], [False, False, False, True, True, True])
        self.assertEqual({item.version for item in response.models if not item.legacy}, {"2.0.0"})
```

- [ ] **Шаг 5: Убедиться, что тесты падают**

Запуск: `../../../.venv/bin/python -m pytest tests/test_fragmentation_legacy.py tests/test_fragmentation_new_models.py tests/test_fragmentation_engine.py tests/test_api_fragmentation.py -q -p no:cacheprovider`
Ожидание: FAIL — `ModuleNotFoundError: No module named 'simulation.fragmentation.legacy'` и `ImportError: cannot import name 'is_legacy_model'`.

- [ ] **Шаг 6: Перенести старые модули**

```bash
mkdir -p simulation/fragmentation/legacy
git mv simulation/fragmentation/kuznetsov.py simulation/fragmentation/legacy/kuznetsov.py
git mv simulation/fragmentation/kuzram.py simulation/fragmentation/legacy/kuzram.py
git mv simulation/fragmentation/swebrec.py simulation/fragmentation/legacy/swebrec.py
```

Создать `simulation/fragmentation/legacy/__init__.py`:

```python
"""Модели кусковатости до перевода на Каннингема (PR 2).

Формулы не меняются: фактор A по Лилли, x50 по Кузнецову с показателем
19/30, n ≥ 0,8 с диаметром в метрах. Модели доступны под именами
kuznetsov_legacy, kuzram_legacy и swebrec_legacy (версия 1.0.0), чтобы
сохранённые прогнозы можно было пересчитать тем же способом и сравнить с
новыми. Числа закреплены tests/fixtures/fragmentation_legacy_golden.json.
"""
```

Правки внутри перенесённых файлов — только имена и импорты, формулы не трогать:

- `legacy/kuznetsov.py`: `MODEL_ID = "kuznetsov_legacy"`.
- `legacy/kuzram.py`: `MODEL_ID = "kuzram_legacy"`; импорт `from simulation.fragmentation.kuznetsov import kuznetsov_x50_mm, rock_factor_A` → `from simulation.fragmentation.legacy.kuznetsov import kuznetsov_x50_mm, rock_factor_A`.
- `legacy/swebrec.py`: `MODEL_ID = "swebrec_legacy"`; тот же импорт Кузнецова → `legacy.kuznetsov`; функцию `default_xmax_mm` удалить, а импорт из `distributions` дополнить ею:

```python
from simulation.fragmentation.distributions import (
    DEFAULT_SWEBREC_B,
    default_xmax_mm,
    distribution_curve,
    swebrec_oversize_pct,
    swebrec_passing,
    swebrec_size_mm,
)
```

и убрать ставший лишним импорт `length_mm_from_m` (оставить `relative_weight_strength`).

В `simulation/fragmentation/distributions.py` добавить импорт `from simulation.fragmentation.units import length_mm_from_m` и после `swebrec_oversize_pct` перенести функцию без изменений:

```python
def default_xmax_mm(burden_m: float, spacing_m: float, x50_mm: float) -> float:
    """Largest free dimension of the burden prism, millimetres.

    Falls back to 2 × x50 when the prism is degenerate so x50 < xmax.
    """
    prism_mm = length_mm_from_m(max(burden_m, spacing_m, 0.0))
    floor = max(x50_mm * 2.0, x50_mm + 1.0)
    return max(prism_mm, floor)
```

- [ ] **Шаг 7: Новые модели**

Создать `simulation/fragmentation/kuzram.py`:

```python
"""Kuz-Ram: x50 и n по Каннингему — те же, что на листе «Расчёт», — и кривая Розина — Раммлера."""
from __future__ import annotations

from simulation.fragmentation.base import base_parameters, calibration_warnings, region_point
from simulation.fragmentation.cunningham import KuzRamSettings
from simulation.fragmentation.distributions import (
    distribution_curve,
    rosin_rammler_oversize_pct,
    rosin_rammler_passing,
    rosin_rammler_size_mm,
)
from simulation.fragmentation.models import (
    Calibration,
    FragmentationInputs,
    ModelProvenance,
    PredictedFragmentation,
)

MODEL_ID = "kuzram"
MODEL_VERSION = "2.0.0"


def predict_kuzram(
    inputs: FragmentationInputs,
    calibration: Calibration | None = None,
    settings: KuzRamSettings | None = None,
) -> PredictedFragmentation:
    """Прогноз одного региона. Без поправки n негабарит — ровно число predict_point."""
    calibration = calibration or Calibration()
    point = region_point(inputs, settings)
    x50_mm = point.x50_mm
    if calibration.uniformity_n:
        n = calibration.uniformity_n
        oversize = rosin_rammler_oversize_pct(x50_mm, n, inputs.lump_size_mm)
    else:
        n = point.uniformity.value
        oversize = point.oversize_pct
    x20_mm = rosin_rammler_size_mm(0.20, x50_mm, n)
    x80_mm = rosin_rammler_size_mm(0.80, x50_mm, n)
    curve = distribution_curve(
        lambda size: rosin_rammler_passing(size, x50_mm, n),
        extra_sizes_mm=(x20_mm, x50_mm, x80_mm, inputs.lump_size_mm),
    )
    return PredictedFragmentation(
        x20_mm=round(x20_mm, 1),
        x50_mm=round(x50_mm, 1),
        x80_mm=round(x80_mm, 1),
        oversize_pct=round(oversize, 2),
        powder_factor_kg_m3=round(inputs.powder_factor_kg_m3, 4),
        curve=curve,
        provenance=ModelProvenance(
            model=MODEL_ID,
            model_version=MODEL_VERSION,
            inputs=inputs.to_dict(),
            parameters={**base_parameters(point, inputs), "uniformity_n": n, "distribution": "rosin_rammler"},
            calibration=calibration.to_dict(),
        ),
        warnings=[*point.warnings, *calibration_warnings(calibration)],
    )
```

Создать `simulation/fragmentation/kuznetsov.py`:

```python
"""Кузнецов: x50 по Каннингему (общая база с листом «Расчёт») и Розин — Раммлер с фиксированным n."""
from __future__ import annotations

from simulation.fragmentation.base import base_parameters, calibration_warnings, region_point
from simulation.fragmentation.cunningham import KuzRamSettings
from simulation.fragmentation.distributions import (
    DEFAULT_KUZNETSOV_N,
    distribution_curve,
    rosin_rammler_oversize_pct,
    rosin_rammler_passing,
    rosin_rammler_size_mm,
)
from simulation.fragmentation.models import (
    Calibration,
    FragmentationInputs,
    ModelProvenance,
    PredictedFragmentation,
)

MODEL_ID = "kuznetsov"
MODEL_VERSION = "2.0.0"


def predict_kuznetsov(
    inputs: FragmentationInputs,
    calibration: Calibration | None = None,
    settings: KuzRamSettings | None = None,
) -> PredictedFragmentation:
    """x50 общей базы и кривая Розина — Раммлера с n = 1 (или из калибровки)."""
    calibration = calibration or Calibration()
    point = region_point(inputs, settings)
    x50_mm = point.x50_mm
    n = calibration.uniformity_n or DEFAULT_KUZNETSOV_N
    x20_mm = rosin_rammler_size_mm(0.20, x50_mm, n)
    x80_mm = rosin_rammler_size_mm(0.80, x50_mm, n)
    oversize = rosin_rammler_oversize_pct(x50_mm, n, inputs.lump_size_mm)
    curve = distribution_curve(
        lambda size: rosin_rammler_passing(size, x50_mm, n),
        extra_sizes_mm=(x20_mm, x50_mm, x80_mm, inputs.lump_size_mm),
    )
    return PredictedFragmentation(
        x20_mm=round(x20_mm, 1),
        x50_mm=round(x50_mm, 1),
        x80_mm=round(x80_mm, 1),
        oversize_pct=round(oversize, 2),
        powder_factor_kg_m3=round(inputs.powder_factor_kg_m3, 4),
        curve=curve,
        provenance=ModelProvenance(
            model=MODEL_ID,
            model_version=MODEL_VERSION,
            inputs=inputs.to_dict(),
            parameters={**base_parameters(point, inputs), "uniformity_n": n, "distribution": "rosin_rammler"},
            calibration=calibration.to_dict(),
        ),
        warnings=[*point.warnings, *calibration_warnings(calibration)],
    )
```

Создать `simulation/fragmentation/swebrec.py`:

```python
"""Swebrec (Оухтерлони) поверх x50 общей базы Каннингема."""
from __future__ import annotations

from simulation.fragmentation.base import base_parameters, calibration_warnings, region_point
from simulation.fragmentation.cunningham import KuzRamSettings
from simulation.fragmentation.distributions import (
    DEFAULT_SWEBREC_B,
    default_xmax_mm,
    distribution_curve,
    swebrec_oversize_pct,
    swebrec_passing,
    swebrec_size_mm,
)
from simulation.fragmentation.models import (
    Calibration,
    FragmentationInputs,
    ModelProvenance,
    PredictedFragmentation,
)

MODEL_ID = "swebrec"
MODEL_VERSION = "2.0.0"


def predict_swebrec(
    inputs: FragmentationInputs,
    calibration: Calibration | None = None,
    settings: KuzRamSettings | None = None,
) -> PredictedFragmentation:
    """Кривая Swebrec с x50 общей базы; xmax — наибольший размер призмы ЛНС × шаг."""
    calibration = calibration or Calibration()
    point = region_point(inputs, settings)
    x50_mm = point.x50_mm
    xmax_mm = calibration.xmax_mm or default_xmax_mm(inputs.burden_m, inputs.spacing_m, x50_mm)
    if xmax_mm <= x50_mm:
        xmax_mm = default_xmax_mm(inputs.burden_m, inputs.spacing_m, x50_mm)
    b = calibration.swebrec_b or DEFAULT_SWEBREC_B
    x20_mm = swebrec_size_mm(0.20, x50_mm, xmax_mm, b)
    x80_mm = swebrec_size_mm(0.80, x50_mm, xmax_mm, b)
    oversize = swebrec_oversize_pct(inputs.lump_size_mm, x50_mm, xmax_mm, b)
    curve = distribution_curve(
        lambda size: swebrec_passing(size, x50_mm, xmax_mm, b),
        extra_sizes_mm=(x20_mm, x50_mm, x80_mm, inputs.lump_size_mm, xmax_mm),
    )
    return PredictedFragmentation(
        x20_mm=round(x20_mm, 1),
        x50_mm=round(x50_mm, 1),
        x80_mm=round(x80_mm, 1),
        oversize_pct=round(oversize, 2),
        powder_factor_kg_m3=round(inputs.powder_factor_kg_m3, 4),
        curve=curve,
        provenance=ModelProvenance(
            model=MODEL_ID,
            model_version=MODEL_VERSION,
            inputs=inputs.to_dict(),
            parameters={
                **base_parameters(point, inputs),
                "swebrec_b": b,
                "xmax_mm": xmax_mm,
                "distribution": "swebrec",
            },
            calibration=calibration.to_dict(),
        ),
        warnings=[*point.warnings, *calibration_warnings(calibration)],
    )
```

- [ ] **Шаг 8: Реестр моделей в движке**

Заменить в `simulation/fragmentation/engine.py` всё от док-строки модуля до конца `predict_region` (строки 1–93) на:

```python
"""Прогноз кусковатости по проекту: реестр моделей и расчёт по регионам влияния.

Три модели (kuznetsov, kuzram, swebrec) считают на общей базе Каннингема
(simulation/fragmentation/base.py) и различаются только кривой. Прежние
формулы доступны под именами *_legacy.
"""
from __future__ import annotations

from typing import Any, Callable

from design.models import BlastDesign
from simulation.fragmentation import kuznetsov as kuznetsov_model
from simulation.fragmentation import kuzram as kuzram_model
from simulation.fragmentation import swebrec as swebrec_model
from simulation.fragmentation.cunningham import KuzRamSettings
from simulation.fragmentation.legacy import kuznetsov as kuznetsov_legacy
from simulation.fragmentation.legacy import kuzram as kuzram_legacy
from simulation.fragmentation.legacy import swebrec as swebrec_legacy
from simulation.fragmentation.maps import fragmentation_maps
from simulation.fragmentation.models import (
    LEGACY_MODEL_SUFFIX,
    MODEL_KUZNETSOV,
    MODEL_KUZRAM,
    MODEL_SWEBREC,
    ROLE_MEASURED,
    ROLE_PREDICTED,
    Calibration,
    DesignedFragmentationTarget,
    FragmentationInputs,
    MeasuredFragmentation,
    PredictedFragmentation,
)
from simulation.fragmentation.regions import (
    DEFAULT_EXPLOSIVE_DENSITY_T_M3,
    DEFAULT_EXPLOSIVE_ENERGY_MJ_KG,
    DEFAULT_ROCK_DENSITY_T_M3,
    DEFAULT_ROCK_FISSURING,
    DEFAULT_ROCK_UCS_MPA,
    ExplosiveSpec,
    InfluenceRegion,
    RockSpec,
    collect_regions,
)

PredictFn = Callable[[FragmentationInputs, Calibration | None, KuzRamSettings | None], PredictedFragmentation]
LegacyPredictFn = Callable[[FragmentationInputs, Calibration | None], PredictedFragmentation]


def _ignoring_settings(predict: LegacyPredictFn) -> PredictFn:
    """Старые модели настроек Каннингема не знают и считают ровно как до PR 2."""

    def run(
        inputs: FragmentationInputs,
        calibration: Calibration | None,
        settings: KuzRamSettings | None,
    ) -> PredictedFragmentation:
        return predict(inputs, calibration)

    return run


# (модуль, подпись, распределение, предиктор, старая ли модель). Версию и
# идентификатор реестр читает из модуля — тот же источник, что у provenance.
_MODELS = (
    (kuznetsov_model, "Кузнецов", "rosin_rammler", kuznetsov_model.predict_kuznetsov, False),
    (kuzram_model, "Kuz-Ram", "rosin_rammler", kuzram_model.predict_kuzram, False),
    (swebrec_model, "Swebrec", "swebrec", swebrec_model.predict_swebrec, False),
    (kuznetsov_legacy, "Кузнецов (старая)", "rosin_rammler", _ignoring_settings(kuznetsov_legacy.predict_kuznetsov), True),
    (kuzram_legacy, "Kuz-Ram (старая)", "rosin_rammler", _ignoring_settings(kuzram_legacy.predict_kuzram), True),
    (swebrec_legacy, "Swebrec (старая)", "swebrec", _ignoring_settings(swebrec_legacy.predict_swebrec), True),
)

FRAGMENTATION_MODELS: dict[str, dict[str, Any]] = {
    module.MODEL_ID: {
        "id": module.MODEL_ID,
        "version": module.MODEL_VERSION,
        "label": label,
        "distribution": distribution,
        "legacy": legacy,
    }
    for module, label, distribution, _predict, legacy in _MODELS
}

_PREDICTORS: dict[str, PredictFn] = {module.MODEL_ID: predict for module, _l, _d, predict, _legacy in _MODELS}

_ALIASES = {
    "kuz": MODEL_KUZNETSOV,
    "kuznetcov": MODEL_KUZNETSOV,
    "kuznetsov": MODEL_KUZNETSOV,
    "kuzram": MODEL_KUZRAM,
    "kuz_ram": MODEL_KUZRAM,
    "swebrec": MODEL_SWEBREC,
    "swebeck": MODEL_SWEBREC,
}


def list_models() -> list[dict[str, Any]]:
    return [dict(item) for item in FRAGMENTATION_MODELS.values()]


def resolve_model(model: str) -> str:
    """Имя модели из запроса → идентификатор реестра; пусто — kuzram."""
    key = str(model or MODEL_KUZRAM).strip().lower().replace("kuz-ram", "kuzram")
    legacy = key.endswith(LEGACY_MODEL_SUFFIX)
    base = key[: -len(LEGACY_MODEL_SUFFIX)] if legacy else key
    model_id = _ALIASES.get(base)
    if model_id is None:
        raise ValueError(f"Неизвестная модель дробления: {model}. Доступны: {', '.join(FRAGMENTATION_MODELS)}.")
    return model_id + LEGACY_MODEL_SUFFIX if legacy else model_id


def is_legacy_model(model: str) -> bool:
    """Модель считает прежними формулами (до перевода на Каннингема)."""
    return bool(FRAGMENTATION_MODELS[resolve_model(model)]["legacy"])


def predict_region(
    inputs: FragmentationInputs,
    model: str = MODEL_KUZRAM,
    calibration: Calibration | None = None,
    settings: KuzRamSettings | None = None,
) -> PredictedFragmentation:
    """Predict one region. Always returns role=predicted."""
    predictor = _PREDICTORS[resolve_model(model)]
    prediction = predictor(inputs, calibration, settings)
    prediction.role = ROLE_PREDICTED
    return prediction
```

В `predict_design`: в сигнатуре заменить `model: str = KUZRAM_ID` на `model: str = MODEL_KUZRAM` и после `measured: list[MeasuredFragmentation] | None = None,` добавить `settings: KuzRamSettings | None = None,`; в трёх вызовах `predict_region(..., model_id, calibration)` добавить четвёртый аргумент `settings`.

В `api/schemas/design.py`, `FragmentationModelInfoSchema`, после `distribution: str` добавить `legacy: bool = False`.

- [ ] **Шаг 9: Импорты старых модулей и умолчание `kuzram`**

`Blast.py`, строки 9–10:

```python
from simulation.fragmentation.legacy.kuznetsov import kuznetsov_x50_mm, rock_factor_A
from simulation.fragmentation.legacy.kuzram import cunningham_uniformity_n
```

В док-строке `_legacy_uniformity_raw` путь `simulation/fragmentation/kuzram.py::cunningham_uniformity_n` заменить на `simulation/fragmentation/legacy/kuzram.py::cunningham_uniformity_n`.

Тесты:
- `tests/test_blast_optimizer.py`, строки 9–10: `simulation.fragmentation.kuzram` → `simulation.fragmentation.legacy.kuzram`.
- `tests/test_fragmentation_kuzram.py:9`: `from simulation.fragmentation.legacy.kuzram import cunningham_uniformity_n, predict_kuzram`; строка 54: `"kuzram"` → `"kuzram_legacy"`; док-строку модуля заменить на `"""Старая модель Kuz-Ram (kuzram_legacy): n по Каннингему с диаметром в метрах."""`.
- `tests/test_fragmentation_kuznetsov.py:4`: `simulation.fragmentation.kuznetsov` → `simulation.fragmentation.legacy.kuznetsov`.
- `tests/test_fragmentation_swebrec.py:6`: `from simulation.fragmentation.legacy.swebrec import default_xmax_mm, predict_swebrec`; строка 27: `"swebrec"` → `"swebrec_legacy"`.

Умолчание — константой, а не литералом:
- `design/reporting/engine.py:34`: `DEFAULT_FRAG_MODEL = MODEL_KUZRAM`, импорт `from simulation.fragmentation.models import MODEL_KUZRAM`.
- `design/scenarios/types.py`: импорт `from simulation.fragmentation.models import MODEL_KUZRAM`; строка 73 — `fragmentation_model: str = MODEL_KUZRAM`; в `from_dict` — `fragmentation_model=str(data.get("fragmentation_model") or MODEL_KUZRAM),`.
- `design/scenarios/engine.py:252`: `model=params.fragmentation_model or MODEL_KUZRAM,` и тот же импорт.

- [ ] **Шаг 10: Убедиться, что тесты проходят**

Запуск: `../../../.venv/bin/python -m pytest tests/test_fragmentation_legacy.py tests/test_fragmentation_new_models.py tests/test_fragmentation_engine.py tests/test_api_fragmentation.py tests/test_fragmentation_kuzram.py tests/test_fragmentation_kuznetsov.py tests/test_fragmentation_swebrec.py tests/test_blast_optimizer.py tests/test_kuzram_control_example.py tests/test_kuzram_frontend_contract.py -q -p no:cacheprovider`
Ожидание: PASS; `git status` не показывает изменений в `tests/fixtures/fragmentation_legacy_golden.json` и `tests/fixtures/kuzram_cunningham_golden.json`.

- [ ] **Шаг 11: Прогнать весь набор**

Запуск: `../../../.venv/bin/python -m pytest -q -p no:cacheprovider`
Ожидание: PASS. Если падает тест сценариев, оптимизации или рекомендаций — действовать по правилу из «Общих ограничений» и записать правку в заметки для описания PR.

- [ ] **Шаг 12: Коммит**

```bash
git add -A simulation/fragmentation Blast.py api/schemas/design.py design/reporting/engine.py design/scenarios tests
git commit -m "Кусковатость: три модели на базе Каннингема, прежние — в legacy/ под именами *_legacy"
```

---

### Задача 5: настройки модели и неполные данные в движке

**Файлы:**
- Изменить: `simulation/fragmentation/base.py` (снимок настроек), `simulation/fragmentation/engine.py` (`predict_region`, `_region_payload`, `predict_design`)
- Тест: `tests/test_fragmentation_engine.py`

**Интерфейсы:**
- Использует: реестр и `predict_region` из задачи 4.
- Отдаёт:
  - в `base.py`: `SETTINGS_SOURCE_REQUEST = "request"`, `SETTINGS_SOURCE_WORK_OBJECT = "work_object"`, `SETTINGS_SOURCE_DEFAULTS = "defaults"`, `settings_snapshot(settings, source=None) -> dict` вида `{"source": str, "work_object_name": str, "values": dict, "warnings": list[str]}`, `settings_from_snapshot(snapshot) -> tuple[KuzRamSettings | None, dict]`;
  - `predict_region(inputs, model, calibration, settings, settings_source=None)`;
  - `predict_design(..., settings=None, settings_source=None)` — ключ ответа `"settings"` (снимок); новые модели кладут тот же снимок в `provenance.settings`; регион, на котором `predict_point` поднял `ValueError`, пропускается с предупреждением; если не считается блок — `ValueError("Прогноз кусковатости по блоку не посчитан: …")`.
  Задачи 6–8 передают сюда настройки и источник.

- [ ] **Шаг 1: Написать падающие тесты**

В `tests/test_fragmentation_engine.py` добавить импорты:

```python
from dataclasses import asdict

from simulation.fragmentation.base import settings_from_snapshot, settings_snapshot
from simulation.fragmentation.cunningham import KuzRamSettings
```

и перед `BlastEngineRegressionTests`:

```python
KW = dict(
    lump_size_mm=400.0,
    default_rock=RockSpec("Гранит", 2.65, 150.0, 2.0),
    default_explosive=ExplosiveSpec("АНФО", 0.82, 3.8),
)


class EngineSettingsTests(unittest.TestCase):
    def test_defaults_snapshot(self):
        result = predict_design(_design_with_charges(), model="kuzram", **KW)

        self.assertEqual(result["settings"]["source"], "defaults")
        self.assertEqual(result["settings"]["values"], asdict(KuzRamSettings()))
        self.assertEqual(result["site"]["prediction"]["provenance"]["settings"], result["settings"])

    def test_settings_change_prediction_and_are_recorded(self):
        design = _design_with_charges()
        plain = predict_design(design, model="kuzram", **KW)
        tuned = predict_design(
            design,
            model="kuzram",
            settings=KuzRamSettings(rock_factor_correction=1.5),
            settings_source={"source": "work_object", "work_object_name": "Карьер-1"},
            **KW,
        )

        self.assertGreater(tuned["site"]["prediction"]["x50_mm"], plain["site"]["prediction"]["x50_mm"])
        snapshot = tuned["holes"][0]["prediction"]["provenance"]["settings"]
        self.assertEqual(snapshot["source"], "work_object")
        self.assertEqual(snapshot["work_object_name"], "Карьер-1")
        self.assertEqual(snapshot["values"]["rock_factor_correction"], 1.5)

    def test_legacy_model_ignores_settings(self):
        design = _design_with_charges()
        plain = predict_design(design, model="kuzram_legacy", **KW)
        tuned = predict_design(design, model="kuzram_legacy", settings=KuzRamSettings(rock_factor_correction=1.5), **KW)

        self.assertEqual(tuned["site"]["prediction"]["x50_mm"], plain["site"]["prediction"]["x50_mm"])
        self.assertEqual(tuned["site"]["prediction"]["provenance"]["settings"], {})

    def test_resolution_warnings_reach_payload(self):
        result = predict_design(
            _design_with_charges(),
            model="kuzram",
            settings_source={"source": "defaults", "work_object_name": "Карьер-3", "warnings": ["Настройки не прочитаны."]},
            **KW,
        )

        self.assertIn("Настройки не прочитаны.", result["warnings"])

    def test_bad_hole_is_skipped_with_warning(self):
        design = _design_with_charges()
        load = design.loads[0]
        for deck in load.decks:
            if deck.kind == "charge":
                deck.explosive_key = "Пустышка"

        result = predict_design(
            design, model="kuzram", explosives={"Пустышка": ExplosiveSpec("Пустышка", 0.82, 0.0)}, **KW
        )

        self.assertNotIn(load.hole_id, [row["hole_ids"][0] for row in result["holes"]])
        self.assertEqual(len(result["holes"]), len(design.holes) - 1)
        self.assertTrue(
            any(
                item.startswith(f"Скважина {load.hole_id}: прогноз не посчитан") and "сила ВВ" in item
                for item in result["warnings"]
            )
        )

    def test_whole_block_failure_is_russian_error(self):
        with self.assertRaises(ValueError) as ctx:
            predict_design(
                _design_with_charges(),
                model="kuzram",
                lump_size_mm=400.0,
                default_rock=RockSpec("Гранит", 2.65, 150.0, 2.0),
                default_explosive=ExplosiveSpec("АНФО", 0.82, 0.0),
                explosives={"АНФО": ExplosiveSpec("АНФО", 0.82, 0.0)},
            )

        self.assertIn("по блоку не посчитан", str(ctx.exception))

    def test_missing_bench_height_warns_once(self):
        design = _design_with_charges()
        for hole in design.holes:
            hole.subdrill_m = hole.length_m  # паспорт без высоты уступа: H = 0

        result = predict_design(design, model="kuzram", **KW)

        lh = [item for item in result["warnings"] if "L/H" in item]
        self.assertEqual(len(lh), 1)
        self.assertIn(lh[0], result["holes"][0]["warnings"])

    def test_snapshot_round_trip(self):
        snapshot = settings_snapshot(
            KuzRamSettings(rock_factor_method="rmd10"), {"source": "work_object", "work_object_name": "Карьер-1"}
        )

        settings, source = settings_from_snapshot(snapshot)

        self.assertEqual(settings, KuzRamSettings(rock_factor_method="rmd10"))
        self.assertEqual(source, {"source": "work_object", "work_object_name": "Карьер-1", "warnings": []})
        self.assertEqual(settings_from_snapshot({}), (None, {}))
```

- [ ] **Шаг 2: Убедиться, что тесты падают**

Запуск: `../../../.venv/bin/python -m pytest tests/test_fragmentation_engine.py -k EngineSettings -q -p no:cacheprovider`
Ожидание: FAIL — `ImportError: cannot import name 'settings_from_snapshot'`.

- [ ] **Шаг 3: Снимок настроек в `base.py`**

К импортам `simulation/fragmentation/base.py` добавить `from collections.abc import Mapping`, в конец файла:

```python
SETTINGS_SOURCE_REQUEST = "request"
SETTINGS_SOURCE_WORK_OBJECT = "work_object"
SETTINGS_SOURCE_DEFAULTS = "defaults"


def settings_snapshot(
    settings: KuzRamSettings | None,
    source: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Применённые настройки и откуда они взяты — для ответа и provenance.

    source — {"source", "work_object_name", "warnings"} от API; без него
    явные настройки считаются заданными в запросе, а их отсутствие —
    умолчаниями.
    """
    meta = dict(source or {})
    fallback = SETTINGS_SOURCE_DEFAULTS if settings is None else SETTINGS_SOURCE_REQUEST
    return {
        "source": str(meta.get("source") or fallback),
        "work_object_name": str(meta.get("work_object_name") or ""),
        "values": asdict(settings or KuzRamSettings()),
        "warnings": [str(item) for item in meta.get("warnings") or ()],
    }


def settings_from_snapshot(snapshot: Mapping[str, Any] | None) -> tuple[KuzRamSettings | None, dict[str, Any]]:
    """Снимок → настройки и источник. Пустой снимок — умолчания движка."""
    if not snapshot:
        return None, {}
    values = dict(snapshot.get("values") or {})
    settings = KuzRamSettings(**values) if values else None
    source = {
        "source": snapshot.get("source") or "",
        "work_object_name": snapshot.get("work_object_name") or "",
        "warnings": list(snapshot.get("warnings") or []),
    }
    return settings, source
```

- [ ] **Шаг 4: Движок — настройки, снимок, пропуск неполных регионов**

В `simulation/fragmentation/engine.py` добавить импорты `from collections.abc import Mapping` и `from simulation.fragmentation.base import settings_snapshot`. Заменить `predict_region` и `_region_payload` на:

```python
def predict_region(
    inputs: FragmentationInputs,
    model: str = MODEL_KUZRAM,
    calibration: Calibration | None = None,
    settings: KuzRamSettings | None = None,
    settings_source: Mapping[str, Any] | None = None,
) -> PredictedFragmentation:
    """Прогноз одного региона (role=predicted).

    Новые модели кладут в provenance снимок применённых настроек; старые
    настроек не знают, и снимка у них нет.
    """
    model_id = resolve_model(model)
    prediction = _PREDICTORS[model_id](inputs, calibration, settings)
    prediction.role = ROLE_PREDICTED
    if not FRAGMENTATION_MODELS[model_id]["legacy"]:
        prediction.provenance.settings = settings_snapshot(settings, settings_source)
    return prediction


def _merge_warnings(target: list[str], items: list[str] | tuple[str, ...]) -> None:
    for item in items:
        if item not in target:
            target.append(item)


def _region_payload(region: InfluenceRegion, prediction: PredictedFragmentation) -> dict[str, Any]:
    warnings = list(region.warnings)
    _merge_warnings(warnings, prediction.warnings)
    return {
        "id": region.id,
        "kind": region.kind,
        "hole_ids": list(region.hole_ids),
        "x": region.x,
        "y": region.y,
        "hole_kind": region.hole_kind,
        "inputs": region.inputs.to_dict(),
        "prediction": prediction.to_dict(),
        "warnings": warnings,
    }


def _predict_rows(
    regions: list[InfluenceRegion],
    predict: Callable[[InfluenceRegion], PredictedFragmentation],
    warnings: list[str],
    label: str,
) -> list[dict[str, Any]]:
    """Регион с неполными данными пропускается с предупреждением.

    Паспорт пишет пустые величины нулём; одна такая скважина не должна
    ронять прогноз всего блока.
    """
    rows: list[dict[str, Any]] = []
    for region in regions:
        try:
            prediction = predict(region)
        except ValueError as exc:
            name = region.id.split(":", 1)[-1]
            _merge_warnings(warnings, [f"{label} {name}: прогноз не посчитан — {exc}"])
            continue
        _merge_warnings(warnings, prediction.warnings)
        rows.append(_region_payload(region, prediction))
    return rows
```

В `predict_design`: в сигнатуре после `settings: KuzRamSettings | None = None,` добавить `settings_source: Mapping[str, Any] | None = None,`; заменить три строки `hole_rows = ...`, `domain_rows = ...`, `site_prediction = ...` на:

```python
    snapshot = settings_snapshot(settings, settings_source)
    _merge_warnings(warnings, snapshot["warnings"])

    def predict(region: InfluenceRegion) -> PredictedFragmentation:
        return predict_region(region.inputs, model_id, calibration, settings, settings_source)

    hole_rows = _predict_rows(holes, predict, warnings, "Скважина")
    domain_rows = _predict_rows(domains, predict, warnings, "Домен")
    try:
        site_prediction = predict(site_region)
    except ValueError as exc:
        raise ValueError(f"Прогноз кусковатости по блоку не посчитан: {exc}") from exc
    _merge_warnings(warnings, site_prediction.warnings)
```

и в возвращаемый словарь после `"calibration": calibration.to_dict(),` добавить `"settings": snapshot,`.

- [ ] **Шаг 5: Убедиться, что тесты проходят**

Запуск: `../../../.venv/bin/python -m pytest tests/test_fragmentation_engine.py tests/test_fragmentation_new_models.py tests/test_api_fragmentation.py -q -p no:cacheprovider`
Ожидание: PASS.

- [ ] **Шаг 6: Коммит**

```bash
git add simulation/fragmentation/base.py simulation/fragmentation/engine.py tests/test_fragmentation_engine.py
git commit -m "Кусковатость: движок принимает настройки модели и не падает на неполной скважине"
```

---

### Задача 6: настройки из объекта работ — API панели «Кусковатость»

**Файлы:**
- Создать: `api/services/fragmentation_settings.py`
- Изменить: `api/schemas/design.py` (`FragmentationPredictRequest` — 1346, `FragmentationPredictResponse` — 1359, импорты), `api/services/design_service.py:637` (`predict_fragmentation`), `api/routers/design.py:100` (`post_fragmentation`)
- Создать тест: `tests/test_api_fragmentation_settings.py`

**Интерфейсы:**
- Использует: `settings_snapshot` и константы источников из задачи 5; `KuzRamSettingsSchema` (`api/schemas/blast.py:71`); `EconomicsRepository.get_calc_inputs`, `get_legacy_workspace`.
- Отдаёт:
  - `ResolvedSettings(settings: KuzRamSettings, source: str, work_object_name: str = "", warnings: tuple[str, ...] = ())` с методом `source_payload() -> dict`;
  - `resolve_kuzram_settings(*, explicit: KuzRamSettings | None, work_object_name: str, organization_id: str | None, repository: EconomicsRepository | None) -> ResolvedSettings`;
  - `FragmentationSettingsSnapshotSchema`; поля запроса `work_object_name`, `kuzram`; поле ответа `settings`;
  - `design_service.predict_fragmentation(request, *, organization_id=None, repository=None)`.
  Задачи 7 и 8 зовут `resolve_kuzram_settings`.

- [ ] **Шаг 1: Написать падающие тесты**

Создать `tests/test_api_fragmentation_settings.py`:

```python
"""«Проектирование» берёт настройки Kuz-Ram из объекта работ — там же, где лист «Расчёт»."""
import os
import unittest
from dataclasses import asdict
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routers import design as design_router
from api.schemas.blast import KuzRamSettingsSchema
from api.schemas.design import FragmentationPredictRequest
from api.services import design_service
from api.services.economics_service import get_economics_repository
from api.services.fragmentation_settings import resolve_kuzram_settings
from cost.v2.repository import EconomicsRepositoryError, InMemoryEconomicsRepository
from simulation.fragmentation.cunningham import KuzRamSettings
from tests.test_api_fragmentation import FragmentationApiTests

ORG = "org-frag"
OBJECT = "Карьер-1"
TUNED = {"rock_factor_correction": 1.6, "strength_exponent": "19/30"}
ROCK = {"name": "Гранит", "density_t_m3": 2.65, "ucs_mpa": 150.0, "fissuring_ff": 2.0}
EXPLOSIVE = {"name": "АНФО", "density_t_m3": 0.82, "power_mj_kg": 3.8}


def _block(**values) -> dict:
    """Блок kuzram, как его сохраняет лист «Расчёт»: настройки и факты взрывов."""
    return {**asdict(KuzRamSettings()), **values, "facts": [{"crown_mm": 152, "q_kg_m3": 1.2, "oversize_pct": 4.0}]}


def _repository(organization: str = ORG, *, active: str = "") -> InMemoryEconomicsRepository:
    repository = InMemoryEconomicsRepository()
    repository.save_calc_inputs(organization, "tester", OBJECT, {"version": 1, "kuzram": _block(**TUNED)})
    if active:
        repository.import_legacy_workspace(
            organization,
            "tester",
            team_name="Команда",
            active_scenario_id="drill_blast",
            active_work_object_name=active,
        )
    return repository


def _design() -> dict:
    return FragmentationApiTests._charged_design(None)


class ResolveSettingsTests(unittest.TestCase):
    def test_explicit_settings_win(self):
        explicit = KuzRamSettings(rock_factor_correction=2.0)

        resolved = resolve_kuzram_settings(
            explicit=explicit, work_object_name=OBJECT, organization_id=ORG, repository=_repository()
        )

        self.assertEqual((resolved.source, resolved.settings), ("request", explicit))

    def test_named_work_object(self):
        resolved = resolve_kuzram_settings(
            explicit=None, work_object_name=OBJECT, organization_id=ORG, repository=_repository()
        )

        self.assertEqual(resolved.source, "work_object")
        self.assertEqual(resolved.work_object_name, OBJECT)
        self.assertEqual(resolved.settings, KuzRamSettings(**TUNED))
        self.assertEqual(resolved.warnings, ())

    def test_active_work_object_fallback(self):
        resolved = resolve_kuzram_settings(
            explicit=None, work_object_name="", organization_id=ORG, repository=_repository(active=OBJECT)
        )

        self.assertEqual((resolved.source, resolved.work_object_name), ("work_object", OBJECT))

    def test_no_organization_means_defaults(self):
        resolved = resolve_kuzram_settings(
            explicit=None, work_object_name=OBJECT, organization_id=None, repository=_repository()
        )

        self.assertEqual((resolved.source, resolved.settings), ("defaults", KuzRamSettings()))

    def test_object_without_block_is_defaults_with_name(self):
        repository = _repository()
        repository.save_calc_inputs(ORG, "tester", "Карьер-2", {"version": 1})

        resolved = resolve_kuzram_settings(
            explicit=None, work_object_name="Карьер-2", organization_id=ORG, repository=repository
        )

        self.assertEqual((resolved.source, resolved.work_object_name), ("defaults", "Карьер-2"))
        self.assertEqual(resolved.warnings, ())

    def test_invalid_block_is_defaults_with_warning(self):
        repository = _repository()
        repository.save_calc_inputs(ORG, "tester", "Карьер-3", {"kuzram": _block(rock_factor_correction=50.0)})

        resolved = resolve_kuzram_settings(
            explicit=None, work_object_name="Карьер-3", organization_id=ORG, repository=repository
        )

        self.assertEqual((resolved.source, resolved.settings), ("defaults", KuzRamSettings()))
        self.assertEqual(len(resolved.warnings), 1)
        self.assertIn("Карьер-3", resolved.warnings[0])
        self.assertIn("Поправка C(A)", resolved.warnings[0])

    def test_repository_error_is_warning(self):
        class Broken(InMemoryEconomicsRepository):
            def get_calc_inputs(self, organization_id, work_object_name):
                raise EconomicsRepositoryError("БД недоступна")

        resolved = resolve_kuzram_settings(
            explicit=None, work_object_name=OBJECT, organization_id=ORG, repository=Broken()
        )

        self.assertEqual(resolved.source, "defaults")
        self.assertIn("БД недоступна", resolved.warnings[0])


class PredictFragmentationSettingsTests(unittest.TestCase):
    def _request(self, **extra) -> FragmentationPredictRequest:
        return FragmentationPredictRequest(
            design=_design(), model="kuzram", lump_size_mm=400.0, rock=ROCK, explosive=EXPLOSIVE, **extra
        )

    def test_work_object_settings_equal_explicit_ones(self):
        tuned = design_service.predict_fragmentation(
            self._request(work_object_name=OBJECT), organization_id=ORG, repository=_repository()
        )
        explicit = design_service.predict_fragmentation(
            self._request(kuzram=KuzRamSettingsSchema(**{**asdict(KuzRamSettings()), **TUNED}))
        )
        plain = design_service.predict_fragmentation(self._request())

        self.assertEqual(tuned.settings.source, "work_object")
        self.assertEqual(tuned.settings.work_object_name, OBJECT)
        self.assertEqual(explicit.settings.source, "request")
        self.assertEqual(plain.settings.source, "defaults")
        self.assertEqual(tuned.site.prediction.x50_mm, explicit.site.prediction.x50_mm)
        self.assertNotEqual(tuned.site.prediction.x50_mm, plain.site.prediction.x50_mm)
        self.assertEqual(tuned.site.prediction.provenance.settings["work_object_name"], OBJECT)


class FragmentationRouteTests(unittest.TestCase):
    def test_route_reads_organization_work_object(self):
        # Сервисный API-ключ даёт организацию «default».
        repository = _repository("default")
        app = FastAPI()
        app.include_router(design_router.router, prefix="/api/v1")
        app.dependency_overrides[get_economics_repository] = lambda: repository

        with patch.dict(os.environ, {"BLASTEX_API_KEY": "test-api-key", "BLASTEX_SESSION_SECRET": "test-secret"}):
            client = TestClient(app, headers={"X-API-Key": "test-api-key"})
            response = client.post(
                "/api/v1/design/fragmentation",
                json={"design": _design(), "model": "kuzram", "work_object_name": OBJECT},
            )

        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["settings"]["source"], "work_object")
        self.assertEqual(body["settings"]["values"]["rock_factor_correction"], 1.6)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Шаг 2: Убедиться, что тесты падают**

Запуск: `../../../.venv/bin/python -m pytest tests/test_api_fragmentation_settings.py -q -p no:cacheprovider`
Ожидание: FAIL — `ModuleNotFoundError: No module named 'api.services.fragmentation_settings'`.

- [ ] **Шаг 3: Выбор источника настроек**

Создать `api/services/fragmentation_settings.py`:

```python
"""Настройки модели Kuz-Ram для прогнозов «Проектирования»: откуда их взять.

Расчётный слой в базу не ходит — настройки достаёт API. Порядок: явные
настройки из запроса → блок kuzram черновика листа «Расчёт» (таблица
calc_object_inputs) для объекта из запроса, а без него — для активного
объекта организации → умолчания. Третьего набора настроек нет: C(A) и
остальное «Проектирование» берёт ровно оттуда, откуда их берёт лист «Расчёт».
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError

from api.schemas.blast import KuzRamSettingsSchema
from cost.v2.repository import EconomicsRepository, EconomicsRepositoryError
from simulation.fragmentation.base import (
    SETTINGS_SOURCE_DEFAULTS,
    SETTINGS_SOURCE_REQUEST,
    SETTINGS_SOURCE_WORK_OBJECT,
)
from simulation.fragmentation.cunningham import KuzRamSettings


@dataclass(frozen=True)
class ResolvedSettings:
    settings: KuzRamSettings
    source: str
    work_object_name: str = ""
    warnings: tuple[str, ...] = ()

    def source_payload(self) -> dict[str, Any]:
        """Источник для settings_snapshot движка."""
        return {"source": self.source, "work_object_name": self.work_object_name, "warnings": list(self.warnings)}


def _defaults(work_object_name: str = "", warning: str = "") -> ResolvedSettings:
    return ResolvedSettings(
        KuzRamSettings(), SETTINGS_SOURCE_DEFAULTS, work_object_name, (warning,) if warning else ()
    )


def _settings_from_block(block: dict[str, Any]) -> KuzRamSettings:
    """Блок kuzram листа → настройки. Факты взрывов и прочие ключи отбрасываются."""
    values = {key: block[key] for key in KuzRamSettingsSchema.model_fields if key in block}
    return KuzRamSettingsSchema(**values).to_settings()


def resolve_kuzram_settings(
    *,
    explicit: KuzRamSettings | None,
    work_object_name: str,
    organization_id: str | None,
    repository: EconomicsRepository | None,
) -> ResolvedSettings:
    """Настройки для прогноза и их источник; ошибки хранилища — предупреждение, не отказ."""
    if explicit is not None:
        return ResolvedSettings(explicit, SETTINGS_SOURCE_REQUEST)
    if not organization_id or repository is None:
        return _defaults()
    name = (work_object_name or "").strip()
    try:
        if not name:
            workspace = repository.get_legacy_workspace(organization_id)
            name = (workspace.active_work_object_name if workspace else "").strip()
        if not name:
            return _defaults()
        stored = repository.get_calc_inputs(organization_id, name)
    except (EconomicsRepositoryError, SQLAlchemyError) as exc:
        label = f"объекта работ «{name}»" if name else "активного объекта работ"
        return _defaults(name, f"Настройки модели {label} недоступны: {exc}. Взяты умолчания.")
    block = (stored.inputs or {}).get("kuzram") if stored is not None else None
    if not isinstance(block, dict):
        # У объекта нет сохранённых настроек модели: лист «Расчёт» в этом
        # случае тоже считает по умолчаниям.
        return _defaults(name)
    try:
        settings = _settings_from_block(block)
    except ValidationError as exc:
        reason = "; ".join(str(error["msg"]) for error in exc.errors())
        return _defaults(name, f"Настройки модели объекта работ «{name}» не прочитаны ({reason}). Взяты умолчания.")
    return ResolvedSettings(settings, SETTINGS_SOURCE_WORK_OBJECT, name)
```

- [ ] **Шаг 4: Поля запроса и ответа**

В `api/schemas/design.py` заменить `from typing import Any` на `from typing import Any, Literal`, импорт из `api.schemas.blast` дополнить `KuzRamSettingsSchema`. Перед `FragmentationPredictRequest` добавить:

```python
class FragmentationSettingsSnapshotSchema(BaseModel):
    """Какие настройки Kuz-Ram применены к прогнозу и откуда они взяты."""

    source: Literal["request", "work_object", "defaults"] = "defaults"
    work_object_name: str = ""
    values: KuzRamSettingsSchema = Field(default_factory=KuzRamSettingsSchema)
    warnings: list[str] = Field(default_factory=list)
```

В `FragmentationPredictRequest` после `measured: ...` добавить:

```python
    # Объект работ, чьи настройки модели брать; пусто — активный объект
    # организации. Явные настройки kuzram важнее объекта.
    work_object_name: str | None = Field(None, max_length=300)
    kuzram: KuzRamSettingsSchema | None = None
```

В `FragmentationPredictResponse` после `calibration: ...` добавить:

```python
    settings: FragmentationSettingsSnapshotSchema = Field(default_factory=FragmentationSettingsSnapshotSchema)
```

- [ ] **Шаг 5: Сервис и роутер**

В `api/services/design_service.py` добавить импорт `from cost.v2.repository import EconomicsRepository`. Сигнатуру `predict_fragmentation` заменить на

```python
def predict_fragmentation(
    request: FragmentationPredictRequest,
    *,
    organization_id: str | None = None,
    repository: EconomicsRepository | None = None,
) -> FragmentationPredictResponse:
```

к её локальным импортам добавить `from api.services.fragmentation_settings import resolve_kuzram_settings`, перед `try:` вставить

```python
    resolved = resolve_kuzram_settings(
        explicit=request.kuzram.to_settings() if request.kuzram is not None else None,
        work_object_name=request.work_object_name or "",
        organization_id=organization_id,
        repository=repository,
    )
```

а в вызов `predict_design(...)` после `measured=measured,` добавить:

```python
            settings=resolved.settings,
            settings_source=resolved.source_payload(),
```

В `api/routers/design.py` импорт `from api.security import require_internal_access` заменить на `from api.security import current_team_id, require_internal_access`, добавить `from api.services.economics_service import get_economics_repository` и `from cost.v2.repository import EconomicsRepository`, заменить `post_fragmentation`:

```python
@router.post("/fragmentation", response_model=FragmentationPredictResponse)
def post_fragmentation(
    request: FragmentationPredictRequest,
    organization_id: str = Depends(current_team_id),
    repository: EconomicsRepository = Depends(get_economics_repository),
) -> FragmentationPredictResponse:
    return design_service.predict_fragmentation(
        request, organization_id=organization_id, repository=repository
    )
```

- [ ] **Шаг 6: Убедиться, что тесты проходят**

Запуск: `../../../.venv/bin/python -m pytest tests/test_api_fragmentation_settings.py tests/test_api_fragmentation.py -q -p no:cacheprovider`
Ожидание: PASS.

- [ ] **Шаг 7: Коммит**

```bash
git add api/services/fragmentation_settings.py api/schemas/design.py api/services/design_service.py api/routers/design.py tests/test_api_fragmentation_settings.py
git commit -m "Кусковатость: «Проектирование» берёт настройки Kuz-Ram из объекта работ"
```

---

### Задача 7: паспорт БВР — те же настройки

**Файлы:**
- Изменить: `api/schemas/reporting.py:23` (`PassportBuildRequest`), `design/reporting/types.py:233` (`PredictedOutcomes`), `design/reporting/engine.py:185-235` (`_collect_predicted`) и `:480` (`build_passport`), `api/services/reporting_service.py`, `api/routers/design.py:354-377`
- Тест: `tests/test_api_passport.py`

**Интерфейсы:**
- Использует: `resolve_kuzram_settings` (задача 6), `predict_design(..., settings, settings_source)` (задача 5).
- Отдаёт: `build_passport(..., kuzram_settings: KuzRamSettings | None = None, kuzram_settings_source: dict | None = None)`; `PredictedOutcomes.fragmentation_settings: dict`; сервисы паспорта с `organization_id` / `repository`.

- [ ] **Шаг 1: Написать падающие тесты**

В `tests/test_api_passport.py` добавить импорт `from cost.v2.repository import InMemoryEconomicsRepository` и методы в `PassportApiTests`:

```python
    def _repository(self, *, active: bool = False) -> InMemoryEconomicsRepository:
        repository = InMemoryEconomicsRepository()
        repository.save_calc_inputs(TEAM_ID, "tester", "Карьер-1", {"kuzram": {"rock_factor_correction": 1.6}})
        if active:
            repository.import_legacy_workspace(
                TEAM_ID, "tester", team_name="Команда", active_scenario_id="drill_blast", active_work_object_name="Карьер-1"
            )
        return repository

    def test_passport_prediction_uses_work_object_settings(self):
        payload = BlastDesignSchema(**charged_design("api-passport-settings").to_dict())

        tuned = reporting_service.build_from_request(
            PassportBuildRequest(design=payload, work_object_name="Карьер-1"),
            organization_id=TEAM_ID,
            repository=self._repository(),
        )
        plain = reporting_service.build_from_request(PassportBuildRequest(design=payload))

        self.assertEqual(tuned.predicted["fragmentation_settings"]["source"], "work_object")
        self.assertEqual(plain.predicted["fragmentation_settings"]["source"], "defaults")
        self.assertGreater(tuned.predicted["x50_mm"], plain.predicted["x50_mm"])

    def test_saved_plan_passport_uses_active_work_object(self):
        design = save_design(TEAM_ID, charged_design("api-passport-active"))

        document = reporting_service.get_plan_passport(
            TEAM_ID, design.design_id, repository=self._repository(active=True)
        )

        settings = document.predicted["fragmentation_settings"]
        self.assertEqual((settings["source"], settings["work_object_name"]), ("work_object", "Карьер-1"))
```

- [ ] **Шаг 2: Убедиться, что тесты падают**

Запуск: `../../../.venv/bin/python -m pytest tests/test_api_passport.py -q -p no:cacheprovider`
Ожидание: FAIL — `TypeError: build_from_request() got an unexpected keyword argument 'organization_id'`.

- [ ] **Шаг 3: Поле снимка в прогнозной части паспорта**

В `design/reporting/types.py`, `PredictedOutcomes`, после `fragmentation_model_version: str = ""` добавить:

```python
    # Снимок настроек Kuz-Ram, с которыми посчитан прогноз кусковатости.
    fragmentation_settings: dict[str, Any] = field(default_factory=dict)
```

в `to_dict` после `"fragmentation_model_version": ...` добавить `"fragmentation_settings": dict(self.fragmentation_settings),`, в `from_dict` после `fragmentation_model_version=...`:

```python
            fragmentation_settings=dict(data.get("fragmentation_settings") or {}),
```

- [ ] **Шаг 4: Настройки в сборке паспорта**

В `design/reporting/engine.py` добавить импорт `from simulation.fragmentation.cunningham import KuzRamSettings`. В `_collect_predicted` после `fragmentation_model: str,` добавить параметры

```python
    kuzram_settings: KuzRamSettings | None,
    kuzram_settings_source: dict[str, Any] | None,
```

в ветке `if stored_frag is not None:` после строки `predicted.fragmentation_model_version = ...` добавить

```python
        predicted.fragmentation_settings = dict(getattr(stored_frag.provenance, "settings", {}) or {})
```

в вызов `predict_fragmentation(...)` после `hole_oversize_coeff=...,` добавить

```python
                settings=kuzram_settings,
                settings_source=kuzram_settings_source,
```

а после `predicted.fragmentation_model_version = str(payload.get("model_version") or "")`:

```python
            predicted.fragmentation_settings = dict(payload.get("settings") or {})
```

В `build_passport` после `predicted_cost: Any = None,` добавить

```python
    kuzram_settings: KuzRamSettings | None = None,
    kuzram_settings_source: dict[str, Any] | None = None,
```

и в вызов `_collect_predicted(...)` после `fragmentation_model=fragmentation_model,`:

```python
            kuzram_settings=kuzram_settings,
            kuzram_settings_source=kuzram_settings_source,
```

В `api/schemas/reporting.py` добавить импорт `from api.schemas.blast import KuzRamSettingsSchema` и в `PassportBuildRequest` после `predicted_cost: ...`:

```python
    work_object_name: str | None = Field(None, max_length=300)
    kuzram: KuzRamSettingsSchema | None = None
```

- [ ] **Шаг 5: Сервис и роутер паспорта**

В `api/services/reporting_service.py` добавить импорты `from typing import Any` и `from cost.v2.repository import EconomicsRepository`, после `list_roles`:

```python
def _settings_kwargs(
    request: PassportBuildRequest | None,
    *,
    organization_id: str | None,
    repository: EconomicsRepository | None,
) -> dict[str, Any]:
    from api.services.fragmentation_settings import resolve_kuzram_settings

    resolved = resolve_kuzram_settings(
        explicit=request.kuzram.to_settings() if request is not None and request.kuzram is not None else None,
        work_object_name=(request.work_object_name if request is not None else "") or "",
        organization_id=organization_id,
        repository=repository,
    )
    return {"kuzram_settings": resolved.settings, "kuzram_settings_source": resolved.source_payload()}
```

и заменить функции сборки на:

```python
def _document_from_design(
    design: BlastDesign,
    request: PassportBuildRequest | None = None,
    *,
    organization_id: str | None = None,
    repository: EconomicsRepository | None = None,
) -> PassportDocumentSchema:
    kwargs: dict = _settings_kwargs(request, organization_id=organization_id, repository=repository)
    if request is not None:
        kwargs.update(
            {
                "lump_size_mm": request.lump_size_mm,
                "max_oversize_pct": request.max_oversize_pct,
                "fragmentation_model": request.fragmentation_model,
                "include_predictions": request.include_predictions,
                "planned_cost": request.planned_cost.model_dump() if request.planned_cost else None,
                "predicted_cost": request.predicted_cost.model_dump() if request.predicted_cost else None,
            }
        )
    try:
        document = build_passport(design, **kwargs)
    except ValueError as exc:
        raise InvalidDesignError(str(exc)) from exc
    payload = document.to_dict()
    if payload.get("approved") or payload.get("auto_approved"):
        raise InvalidDesignError("Паспорт не должен утверждаться автоматически.")
    return PassportDocumentSchema(**payload)


def build_from_request(
    request: PassportBuildRequest,
    *,
    organization_id: str | None = None,
    repository: EconomicsRepository | None = None,
) -> PassportDocumentSchema:
    design = BlastDesign.from_dict(request.design.model_dump())
    before_holes = [hole.to_dict() for hole in design.holes]
    before_loads = [load.to_dict() for load in design.loads]
    document = _document_from_design(design, request, organization_id=organization_id, repository=repository)
    if [hole.to_dict() for hole in design.holes] != before_holes:
        raise InvalidDesignError("Сборка паспорта не должна менять проектные скважины.")
    if [load.to_dict() for load in design.loads] != before_loads:
        raise InvalidDesignError("Сборка паспорта не должна менять проектный заряд.")
    return document


def render_from_request(
    request: PassportBuildRequest,
    *,
    organization_id: str | None = None,
    repository: EconomicsRepository | None = None,
) -> str:
    design = BlastDesign.from_dict(request.design.model_dump())
    try:
        return passport_html(
            design,
            lump_size_mm=request.lump_size_mm,
            max_oversize_pct=request.max_oversize_pct,
            fragmentation_model=request.fragmentation_model,
            include_predictions=request.include_predictions,
            planned_cost=request.planned_cost.model_dump() if request.planned_cost else None,
            predicted_cost=request.predicted_cost.model_dump() if request.predicted_cost else None,
            **_settings_kwargs(request, organization_id=organization_id, repository=repository),
        )
    except ValueError as exc:
        raise InvalidDesignError(str(exc)) from exc


def get_plan_passport(
    team_id: str, design_id: str, *, repository: EconomicsRepository | None = None
) -> PassportDocumentSchema:
    try:
        design = design_persistence.load_design(team_id, design_id)
    except design_persistence.DesignNotFoundError as exc:
        raise DesignNotFoundError(design_id) from exc
    return _document_from_design(design, organization_id=team_id, repository=repository)


def export_plan_passport_html(
    team_id: str, design_id: str, *, repository: EconomicsRepository | None = None
) -> str:
    try:
        design = design_persistence.load_design(team_id, design_id)
    except design_persistence.DesignNotFoundError as exc:
        raise DesignNotFoundError(design_id) from exc
    document = build_passport(design, **_settings_kwargs(None, organization_id=team_id, repository=repository))
    return render_passport_html(document)
```

В `api/routers/design.py` заменить четыре маршрута паспорта:

```python
@router.post("/passport", response_model=PassportDocumentSchema)
def post_passport(
    request: PassportBuildRequest,
    organization_id: str = Depends(current_team_id),
    repository: EconomicsRepository = Depends(get_economics_repository),
) -> PassportDocumentSchema:
    return reporting_service.build_from_request(request, organization_id=organization_id, repository=repository)


@router.post("/passport.html")
def post_passport_html(
    request: PassportBuildRequest,
    organization_id: str = Depends(current_team_id),
    repository: EconomicsRepository = Depends(get_economics_repository),
) -> Response:
    html_text = reporting_service.render_from_request(
        request, organization_id=organization_id, repository=repository
    )
    return Response(content=html_text, media_type="text/html")


@router.get("/plans/{design_id}/passport", response_model=PassportDocumentSchema)
def get_plan_passport(
    design_id: str,
    session: dict = Depends(require_internal_access),
    repository: EconomicsRepository = Depends(get_economics_repository),
) -> PassportDocumentSchema:
    return reporting_service.get_plan_passport(session["org"], design_id, repository=repository)


@router.get("/plans/{design_id}/passport.html")
def export_plan_passport(
    design_id: str,
    session: dict = Depends(require_internal_access),
    repository: EconomicsRepository = Depends(get_economics_repository),
) -> Response:
    html_text = reporting_service.export_plan_passport_html(session["org"], design_id, repository=repository)
    return Response(content=html_text, media_type="text/html")
```

- [ ] **Шаг 6: Убедиться, что тесты проходят**

Запуск: `../../../.venv/bin/python -m pytest tests/test_api_passport.py tests/test_reporting_engine.py tests/test_reporting_models.py tests/test_reporting_isolation.py -q -p no:cacheprovider`
Ожидание: PASS.

- [ ] **Шаг 7: Коммит**

```bash
git add api/schemas/reporting.py design/reporting api/services/reporting_service.py api/routers/design.py tests/test_api_passport.py
git commit -m "Паспорт БВР: прогноз кусковатости по настройкам модели объекта работ"
```

---

### Задача 8: сценарии, поиск Парето и рекомендации — те же настройки

**Файлы:**
- Изменить: `design/scenarios/types.py` (`ScenarioParams`), `design/scenarios/engine.py:246` (`_fragmentation_outcomes`), `api/schemas/scenarios.py` (`ScenarioParamsSchema`, `ScenarioCompareRequest`), `api/services/fragmentation_settings.py` (новая функция), `api/services/scenario_service.py` (`create_scenario`, `compare_plan_scenarios`), `api/services/optimization_service.py` (`run_optimization`, `promote_candidate`), `api/services/recommendation_service.py` (`run_recommendation`, `promote_recommendation`), роутеры `api/routers/scenarios.py`, `api/routers/optimization.py`, `api/routers/recommendation.py`
- Тесты: `tests/test_api_scenarios.py`, `tests/test_scenario_models.py`

**Интерфейсы:**
- Использует: `resolve_kuzram_settings` (задача 6), `settings_snapshot` / `settings_from_snapshot` (задача 5).
- Отдаёт: поля `ScenarioParams.work_object_name: str`, `kuzram: dict` (явные настройки из запроса; пустой словарь — не заданы), `kuzram_settings: dict` (снимок, заполняет только сервер); `with_scenario_settings(params, *, organization_id, repository) -> ScenarioParams`; сервисы с `repository=None`.

- [ ] **Шаг 1: Написать падающие тесты**

В `tests/test_scenario_models.py` (импорт `from design.scenarios.types import ScenarioParams`, если его нет) добавить класс:

```python
class ScenarioParamsSettingsTests(unittest.TestCase):
    def test_settings_fields_round_trip(self):
        params = ScenarioParams(
            work_object_name="Карьер-1",
            kuzram={"rock_factor_correction": 1.4},
            kuzram_settings={"source": "request", "values": {"rock_factor_correction": 1.4}},
        )

        restored = ScenarioParams.from_dict(params.to_dict())

        self.assertEqual(restored.work_object_name, "Карьер-1")
        self.assertEqual(restored.kuzram, {"rock_factor_correction": 1.4})
        self.assertEqual(restored.kuzram_settings["source"], "request")

    def test_empty_explicit_settings_stay_empty(self):
        # Пустые явные настройки не должны превратиться в «умолчания из запроса»
        # после круга to_dict → схема API → from_dict (продвижение кандидата).
        self.assertIsNone(ScenarioParams().to_dict()["kuzram"])

    def test_old_params_read_without_settings(self):
        restored = ScenarioParams.from_dict({"diameter_mm": 165.0})

        self.assertEqual((restored.work_object_name, restored.kuzram, restored.kuzram_settings), ("", {}, {}))
```

В `tests/test_api_scenarios.py` добавить импорт `from cost.v2.repository import InMemoryEconomicsRepository` и методы в `ScenarioApiTests`:

```python
    def _repository(self, *, active: bool = False) -> InMemoryEconomicsRepository:
        repository = InMemoryEconomicsRepository()
        repository.save_calc_inputs(TEAM_ID, "tester", "Карьер-1", {"kuzram": {"rock_factor_correction": 1.6}})
        if active:
            repository.import_legacy_workspace(
                TEAM_ID, "tester", team_name="Команда", active_scenario_id="drill_blast", active_work_object_name="Карьер-1"
            )
        return repository

    def test_scenario_uses_work_object_settings_and_records_snapshot(self):
        payload = BlastDesignSchema(**self._plan().to_dict())
        repository = self._repository()

        tuned = scenario_service.create_scenario(
            TEAM_ID,
            ScenarioCreateRequest(
                design=payload, name="Объект", persist=False, params=ScenarioParamsSchema(work_object_name="Карьер-1")
            ),
            repository=repository,
        )
        plain = scenario_service.create_scenario(
            TEAM_ID, ScenarioCreateRequest(design=payload, name="Умолчания", persist=False), repository=repository
        )

        self.assertEqual(tuned.params.kuzram_settings["source"], "work_object")
        self.assertEqual(tuned.params.kuzram_settings["values"]["rock_factor_correction"], 1.6)
        self.assertEqual(plain.params.kuzram_settings["source"], "defaults")
        self.assertGreater(tuned.outcomes.x50_mm, plain.outcomes.x50_mm)

    def test_client_snapshot_is_overwritten(self):
        payload = BlastDesignSchema(**self._plan().to_dict())

        created = scenario_service.create_scenario(
            TEAM_ID,
            ScenarioCreateRequest(
                design=payload,
                name="Подмена",
                persist=False,
                params=ScenarioParamsSchema(
                    kuzram_settings={"source": "request", "values": {"rock_factor_correction": 9.0}}
                ),
            ),
        )

        self.assertEqual(created.params.kuzram_settings["source"], "defaults")
        self.assertEqual(created.params.kuzram_settings["values"]["rock_factor_correction"], 1.0)

    def test_compare_baseline_uses_active_work_object(self):
        design = self._plan()
        repository = self._repository(active=True)
        scenario_service.create_scenario(
            TEAM_ID,
            ScenarioCreateRequest(design=BlastDesignSchema(**design.to_dict()), name="A", params=ScenarioParamsSchema()),
            repository=repository,
        )

        with patch.object(
            scenario_service, "_baseline_scenario", wraps=scenario_service._baseline_scenario
        ) as baseline:
            scenario_service.compare_plan_scenarios(
                TEAM_ID, ScenarioCompareRequest(design_id=design.design_id, include_baseline=True), repository=repository
            )

        params = baseline.call_args.args[2]
        self.assertEqual(params.kuzram_settings["source"], "work_object")
        self.assertEqual(params.kuzram_settings["work_object_name"], "Карьер-1")
```

- [ ] **Шаг 2: Убедиться, что тесты падают**

Запуск: `../../../.venv/bin/python -m pytest tests/test_scenario_models.py tests/test_api_scenarios.py -q -p no:cacheprovider`
Ожидание: FAIL — `TypeError: ScenarioParams.__init__() got an unexpected keyword argument 'work_object_name'`.

- [ ] **Шаг 3: Поля параметров сценария**

В `design/scenarios/types.py`, `ScenarioParams`, после `calibration_model_ids: ...` добавить:

```python
    # Объект работ, чьи настройки Kuz-Ram брать (пусто — активный объект).
    work_object_name: str = ""
    # Явные настройки Kuz-Ram из запроса (значения KuzRamSettings); пусто — не заданы.
    kuzram: dict[str, Any] = field(default_factory=dict)
    # Снимок применённых настроек; заполняет только сервер
    # (api/services/fragmentation_settings.py), присланный клиентом затирается.
    kuzram_settings: dict[str, Any] = field(default_factory=dict)
```

в `to_dict` после `"calibration_model_ids": ...` добавить

```python
            "work_object_name": self.work_object_name,
            # None, а не {}: схема API превратила бы {} в полный набор умолчаний,
            # и сервер принял бы их за явные настройки из запроса.
            "kuzram": dict(self.kuzram) or None,
            "kuzram_settings": dict(self.kuzram_settings),
```

в `from_dict` после `calibration_model_ids=...` добавить

```python
            work_object_name=str(data.get("work_object_name") or ""),
            kuzram=dict(data.get("kuzram") or {}),
            kuzram_settings=dict(data.get("kuzram_settings") or {}),
```

В `api/schemas/scenarios.py` добавить импорт `from api.schemas.blast import KuzRamSettingsSchema`, в `ScenarioParamsSchema` после `calibration_model_ids: ...`:

```python
    work_object_name: str = Field("", max_length=300)
    kuzram: KuzRamSettingsSchema | None = None
    kuzram_settings: dict[str, Any] = Field(default_factory=dict)
```

в `ScenarioCompareRequest` после `inline: ...`:

```python
    work_object_name: str = Field("", max_length=300)
```

- [ ] **Шаг 4: Движок сценария считает по снимку**

В `design/scenarios/engine.py`, `_fragmentation_outcomes`, заменить начало функции до `except ValueError as exc:` на:

```python
def _fragmentation_outcomes(overlay: BlastDesign, params: ScenarioParams, outcomes: ScenarioOutcomes) -> None:
    from simulation.fragmentation.base import settings_from_snapshot
    from simulation.fragmentation.engine import predict_design

    settings, settings_source = settings_from_snapshot(params.kuzram_settings)
    try:
        payload = predict_design(
            overlay,
            model=params.fragmentation_model or MODEL_KUZRAM,
            lump_size_mm=params.lump_size_mm,
            hole_oversize_coeff=(overlay.charge_rules or {}).get("hole_oversize_coeff"),
            settings=settings,
            settings_source=settings_source,
        )
```

- [ ] **Шаг 5: Выбор настроек для сценария**

В `api/services/fragmentation_settings.py` к импортам добавить `from dataclasses import dataclass, replace` (вместо `from dataclasses import dataclass`), `from design.scenarios.types import ScenarioParams` и `settings_snapshot` в импорт из `simulation.fragmentation.base`; в конец файла:

```python
def with_scenario_settings(
    params: ScenarioParams,
    *,
    organization_id: str | None,
    repository: EconomicsRepository | None,
) -> ScenarioParams:
    """Параметры сценария со снимком применённых настроек Kuz-Ram.

    Снимок всегда пересчитывается: присланному клиентом сервер не доверяет,
    явные настройки клиент передаёт полем kuzram.
    """
    explicit = KuzRamSettingsSchema(**params.kuzram).to_settings() if params.kuzram else None
    resolved = resolve_kuzram_settings(
        explicit=explicit,
        work_object_name=params.work_object_name,
        organization_id=organization_id,
        repository=repository,
    )
    return replace(params, kuzram_settings=settings_snapshot(resolved.settings, resolved.source_payload()))
```

- [ ] **Шаг 6: Сервисы и роутеры**

`api/services/scenario_service.py` — импорты `from api.services.fragmentation_settings import with_scenario_settings` и `from cost.v2.repository import EconomicsRepository`:
- сигнатура `def create_scenario(team_id: str, request: ScenarioCreateRequest, *, repository: EconomicsRepository | None = None)`; строку `params = ScenarioParams.from_dict(request.params.model_dump())` заменить на

```python
    params = with_scenario_settings(
        ScenarioParams.from_dict(request.params.model_dump()), organization_id=team_id, repository=repository
    )
```

- сигнатура `def compare_plan_scenarios(team_id: str, request: ScenarioCompareRequest, *, repository: EconomicsRepository | None = None)`; строку `scenarios = [_baseline_scenario(team_id, design)] + scenarios` заменить на

```python
            baseline_params = with_scenario_settings(
                ScenarioParams(work_object_name=request.work_object_name),
                organization_id=team_id,
                repository=repository,
            )
            scenarios = [_baseline_scenario(team_id, design, baseline_params)] + scenarios
```

`api/services/optimization_service.py` — те же импорты:
- `def run_optimization(team_id: str, request: OptimizationRequest, *, repository: EconomicsRepository | None = None)`; строку `params = ScenarioParams.from_dict(request.params.model_dump())` заменить тем же вызовом `with_scenario_settings(...)`, что в `create_scenario`;
- `def promote_candidate(team_id: str, request: OptimizationPromoteRequest, *, repository: EconomicsRepository | None = None)`; в вызов `create_scenario(...)` добавить `repository=repository`.

`api/services/recommendation_service.py` — те же импорты и те же две правки в `run_recommendation` (строка `params = ScenarioParams.from_dict(...)` → `with_scenario_settings(...)`) и `promote_recommendation` (вызов `create_scenario(...)` получает `repository=repository`).

Роутеры `api/routers/scenarios.py`, `optimization.py`, `recommendation.py`: добавить импорты `from api.services.economics_service import get_economics_repository` и `from cost.v2.repository import EconomicsRepository`; в `create_scenario`, `compare_scenarios`, `run_optimization`, `promote_candidate`, `run_recommendation`, `promote_recommendation` добавить параметр `repository: EconomicsRepository = Depends(get_economics_repository),` и передать его в сервис как `repository=repository`. Пример:

```python
@router.post("/scenarios", response_model=ScenarioCreateResponse, status_code=201)
def create_scenario(
    request: ScenarioCreateRequest,
    session: dict = Depends(require_internal_access),
    repository: EconomicsRepository = Depends(get_economics_repository),
) -> ScenarioCreateResponse:
    return scenario_service.create_scenario(session["org"], request, repository=repository)
```

- [ ] **Шаг 7: Убедиться, что тесты проходят**

Запуск: `../../../.venv/bin/python -m pytest tests/test_scenario_models.py tests/test_api_scenarios.py tests/test_scenario_engine.py tests/test_scenario_compare.py tests/test_api_optimization.py tests/test_api_recommendation.py tests/test_optimization_engine.py tests/test_recommendation_engine.py -q -p no:cacheprovider`
Ожидание: PASS.

- [ ] **Шаг 8: Коммит**

```bash
git add design/scenarios api/schemas/scenarios.py api/services api/routers tests/test_scenario_models.py tests/test_api_scenarios.py
git commit -m "Сценарии и поиск Парето: кусковатость по настройкам модели объекта работ"
```

---

### Задача 9: ML остаётся на старой базе до PR 3

**Файлы:**
- Изменить: `intelligence/calibration/prediction.py:192-219` (`_stored_predicted`, `_compute_empirical`), `intelligence/spatial/features.py:305`, `api/services/scenario_service.py:161-200` (цикл поправок калибровок в `_apply_ml_overlays`)
- Создать тест: `tests/test_fragmentation_ml_baseline.py`

**Интерфейсы:**
- Использует: `MODEL_KUZRAM_LEGACY`, `LEGACY_MODEL_SUFFIX` (задача 1), `is_legacy_model` (задача 4).
- Отдаёт: `intelligence.calibration.prediction._old_base(provenance) -> bool`, `CALIBRATION_BASELINE_MODEL`. PR 3 заменит эти заглушки проверкой базы по артефакту калибровки.

- [ ] **Шаг 1: Написать падающие тесты**

Создать `tests/test_fragmentation_ml_baseline.py`:

```python
"""До PR 3 ML-калибровки и пространственные признаки живут на старой базе Kuz-Ram 1.0.0.

Калибровки обучены на прогнозах старой модели; поправка, наложенная на
новую формулу, противоречит решению владельца № 3 из спеки.
"""
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from api.services import scenario_service
from design.scenarios.types import ScenarioOutcomes, ScenarioParams
from intelligence.calibration import prediction as calibration_prediction
from intelligence.calibration.types import MODEL_KUZRAM_RESIDUAL
from simulation.fragmentation import engine as fragmentation_engine
from simulation.fragmentation.models import ModelProvenance
from tests.scenario_fixtures import charged_design


class CalibrationBaselineTests(unittest.TestCase):
    def test_empirical_baseline_uses_legacy_model(self):
        with patch.object(fragmentation_engine, "predict_design", wraps=fragmentation_engine.predict_design) as spy:
            value = calibration_prediction._compute_empirical(charged_design("ml-base"), MODEL_KUZRAM_RESIDUAL)

        self.assertIsNotNone(value)
        self.assertEqual(spy.call_args.kwargs["model"], "kuzram_legacy")

    def test_only_old_base_predictions_are_baselines(self):
        old_base = calibration_prediction._old_base
        self.assertTrue(old_base(ModelProvenance(model="kuzram", model_version="1.0.0")))
        self.assertTrue(old_base(ModelProvenance(model="kuzram", model_version="")))
        self.assertTrue(old_base(ModelProvenance(model="kuzram_legacy", model_version="1.0.0")))
        self.assertFalse(old_base(ModelProvenance(model="kuzram", model_version="2.0.0")))
        self.assertFalse(old_base(ModelProvenance(model="swebrec", model_version="2.0.0")))


class SpatialPhysicsTests(unittest.TestCase):
    def test_physics_predictions_use_legacy_model(self):
        from intelligence.spatial.features import extract_hole_observations

        with patch.object(fragmentation_engine, "predict_region", wraps=fragmentation_engine.predict_region) as spy:
            extract_hole_observations(charged_design("ml-spatial"))

        self.assertTrue(spy.call_args_list)
        self.assertEqual({call.kwargs["model"] for call in spy.call_args_list}, {"kuzram_legacy"})


class ScenarioResidualGuardTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        patcher = patch("cost.persistence.data_root", return_value=Path(self._tmp.name))
        patcher.start()
        self.addCleanup(patcher.stop)

    def _run(self, fragmentation_model: str):
        outcomes = ScenarioOutcomes(
            x50_mm=200.0, x50_engineering_mm=200.0, oversize_pct=5.0, oversize_engineering_pct=5.0
        )
        params = ScenarioParams(
            fragmentation_model=fragmentation_model, calibration_model_ids={"kuzram_residual": "cal-1"}
        )
        with patch("intelligence.calibration.persistence.load_model", return_value=object()), patch(
            "intelligence.calibration.prediction.apply_residual", return_value=SimpleNamespace(calibrated=150.0)
        ) as apply:
            scenario_service._apply_ml_overlays("team-ml", charged_design("ml-guard"), params, outcomes)
        return outcomes, apply

    def test_new_model_skips_old_residual(self):
        outcomes, apply = self._run("kuzram")

        apply.assert_not_called()
        self.assertEqual(outcomes.x50_mm, 200.0)
        self.assertTrue(any("переобучить" in item for item in outcomes.warnings))

    def test_legacy_model_keeps_residual(self):
        outcomes, apply = self._run("kuzram_legacy")

        apply.assert_called_once()
        self.assertEqual(outcomes.x50_mm, 150.0)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Шаг 2: Убедиться, что тесты падают**

Запуск: `../../../.venv/bin/python -m pytest tests/test_fragmentation_ml_baseline.py -q -p no:cacheprovider`
Ожидание: FAIL — модель в вызове `kuzram` вместо `kuzram_legacy`, `AttributeError: ... has no attribute '_old_base'`, `apply_residual` вызван для новой модели.

- [ ] **Шаг 3: Baseline калибровки — старая модель**

В `intelligence/calibration/prediction.py` добавить импорт `from simulation.fragmentation.models import LEGACY_MODEL_SUFFIX, MODEL_KUZRAM_LEGACY, ModelProvenance` и перед `_stored_predicted`:

```python
# Калибровки обучены на прогнозах Kuz-Ram 1.0.0 (формулы до перевода на
# Каннингема). Пока артефакт не хранит свою базу (PR 3), baseline для них
# считается той же старой моделью — иначе поправка ляжет на чужую формулу.
CALIBRATION_BASELINE_MODEL = MODEL_KUZRAM_LEGACY


def _old_base(provenance: ModelProvenance) -> bool:
    """Прогноз посчитан старой базой — той, на которой обучены калибровки."""
    return provenance.model.endswith(LEGACY_MODEL_SUFFIX) or not provenance.model_version.startswith("2.")
```

В `_stored_predicted` заменить

```python
        predicted = result.basis.predicted_fragmentation
        if predicted is None:
            return None
```

на

```python
        predicted = result.basis.predicted_fragmentation
        if predicted is None or not _old_base(predicted.provenance):
            return None
```

В `_compute_empirical` заменить `payload = predict_design(design, model="kuzram")` на `payload = predict_design(design, model=CALIBRATION_BASELINE_MODEL)`.

- [ ] **Шаг 4: Физические признаки пространственной модели — старая модель**

В `intelligence/spatial/features.py`, `attach_physics_predictions`, к локальным импортам добавить `from simulation.fragmentation.models import MODEL_KUZRAM_LEGACY` и заменить `prediction = predict_region(region.inputs, model="kuzram")` на

```python
            # Пространственные модели обучены на признаках старой базы;
            # переход на новую — вместе с проверкой базы в PR 3.
            prediction = predict_region(region.inputs, model=MODEL_KUZRAM_LEGACY)
```

- [ ] **Шаг 5: Поправки калибровок в сценарии не ложатся на новую модель**

В `api/services/scenario_service.py`, `_apply_ml_overlays`, во втором блоке `try` к локальным импортам добавить `from simulation.fragmentation.engine import is_legacy_model`; перед `for model_type, field, baseline_field in mapping:`:

```python
        # Поправки кусковатости обучены на Kuz-Ram 1.0.0; к новой модели их
        # не применяем, пока PR 3 не научит артефакт помнить свою базу.
        new_base = not is_legacy_model(params.fragmentation_model)
        fragmentation_residuals = {MODEL_KUZRAM_RESIDUAL, MODEL_OVERSIZE_RESIDUAL}
        skipped_residuals = False
```

первой строкой тела цикла:

```python
            if new_base and model_type in fragmentation_residuals:
                skipped_residuals = skipped_residuals or bool(
                    params.calibration_model_ids.get(model_type) or params.use_production_overlays
                )
                continue
```

и после цикла:

```python
        if skipped_residuals:
            outcomes.warnings.append(
                "Калибровки кусковатости обучены на старой модели Kuz-Ram 1.0.0 и к новой модели "
                "не применяются — их нужно переобучить."
            )
```

- [ ] **Шаг 6: Убедиться, что тесты проходят**

Запуск: `../../../.venv/bin/python -m pytest tests/test_fragmentation_ml_baseline.py tests/test_api_calibration.py tests/test_api_scenarios.py -q -p no:cacheprovider`
Ожидание: PASS.

- [ ] **Шаг 7: Коммит**

```bash
git add intelligence/calibration/prediction.py intelligence/spatial/features.py api/services/scenario_service.py tests/test_fragmentation_ml_baseline.py
git commit -m "ML: калибровки и пространственные признаки до PR 3 остаются на старой базе Kuz-Ram"
```

---

### Задача 10: фронт — шесть моделей и строка источника настроек

**Файлы:**
- Изменить: `frontend/src/types/design.ts` (`FRAGMENTATION_MODELS` — 1893; `FragmentationModelId`; `ModelProvenance`; `PredictedFragmentation`; `FragmentationInputs`; `FragmentationPredictResponse`; `DesignScenarioParams` — 2490), `frontend/src/api/endpoints.ts` (`fragmentation` — 448, `compareScenarios` — 787, `buildPassport` — 856), `frontend/src/pages/design/FragmentationPanel.tsx`, `frontend/src/pages/design/DesignPage.tsx` (727, 1983, 2035, 2110, 2189, 2220)
- Создать: `frontend/src/pages/design/fragmentationSettings.ts`, `frontend/src/pages/design/FragmentationPanel.test.tsx`

**Интерфейсы:**
- Использует: поля ответа `settings`, `model` (задача 6), параметры запросов `work_object_name` (задачи 6–8).
- Отдаёт: `settingsSourceLabel(result: Pick<FragmentationPredictResponse, "model" | "settings">): string`, `isLegacyFragmentationModel(model: string): boolean`.

- [ ] **Шаг 1: Написать падающие тесты**

Создать `frontend/src/pages/design/FragmentationPanel.test.tsx`:

```tsx
// @vitest-environment jsdom
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import type { FragmentationPredictResponse, FragmentationRegion } from "../../types/design";
import { FragmentationPanel } from "./FragmentationPanel";
import { settingsSourceLabel } from "./fragmentationSettings";

afterEach(cleanup);

function region(): FragmentationRegion {
  return {
    id: "site",
    kind: "site",
    hole_ids: [],
    x: 0,
    y: 0,
    hole_kind: "site",
    inputs: {
      burden_m: 4,
      spacing_m: 5,
      bench_height_m: 10,
      diameter_mm: 152,
      charge_mass_kg: 131,
      powder_factor_kg_m3: 0.656,
      stemming_m: 3,
      explosive_name: "АНФО",
      explosive_density_t_m3: 0.82,
      explosive_energy_mj_kg: 3.8,
      rock_name: "Гранит",
      rock_density_t_m3: 2.65,
      rock_ucs_mpa: 150,
      rock_fissuring: 2,
      lump_size_mm: 400,
      hole_oversize_coeff: 1.05,
      influence_volume_m3: 200,
      charge_length_m: 8,
      hole_length_m: 11,
    },
    prediction: {
      role: "predicted",
      x20_mm: 60,
      x50_mm: 200,
      x80_mm: 420,
      oversize_pct: 15.9,
      powder_factor_kg_m3: 0.656,
      curve: [
        { size_mm: 100, passing_pct: 20 },
        { size_mm: 400, passing_pct: 84 },
      ],
      provenance: { model: "kuzram", model_version: "2.0.0", inputs: {}, parameters: {}, calibration: {} },
      warnings: [],
    },
    warnings: [],
  };
}

function result(overrides: Partial<FragmentationPredictResponse> = {}): FragmentationPredictResponse {
  return {
    model: "kuzram",
    model_version: "2.0.0",
    target: { role: "designed", lump_size_mm: 400, max_oversize_pct: 5 },
    site: region(),
    holes: [],
    regions: [],
    maps: { metrics: [], holes: [], stats: {} },
    warnings: [],
    measured: [],
    calibration: {},
    settings: { source: "work_object", work_object_name: "Карьер-1", values: {}, warnings: [] },
    ...overrides,
  };
}

const noop = () => undefined;

function renderPanel(value: FragmentationPredictResponse | null) {
  render(
    <FragmentationPanel
      model="kuzram"
      onModelChange={noop}
      lumpSizeMm={400}
      onLumpSizeChange={noop}
      onPredict={noop}
      busy={false}
      result={value}
      selectedHoleId={null}
    />,
  );
}

describe("FragmentationPanel", () => {
  it("шесть моделей в списке, старые подписаны", () => {
    renderPanel(null);
    expect(screen.getAllByRole("option").map((option) => option.textContent)).toEqual([
      "Кузнецов",
      "Kuz-Ram",
      "Swebrec",
      "Кузнецов (старая)",
      "Kuz-Ram (старая)",
      "Swebrec (старая)",
    ]);
  });

  it("строка источника настроек рядом с моделью", () => {
    renderPanel(result());
    expect(screen.getByText("Настройки модели: объект работ «Карьер-1»")).toBeInTheDocument();
  });
});

describe("settingsSourceLabel", () => {
  it.each([
    [result(), "Настройки модели: объект работ «Карьер-1»"],
    [
      result({ settings: { source: "request", work_object_name: "", values: {}, warnings: [] } }),
      "Настройки модели: заданы в запросе",
    ],
    [
      result({ settings: { source: "defaults", work_object_name: "", values: {}, warnings: [] } }),
      "Настройки модели: умолчания",
    ],
    [
      result({ settings: { source: "defaults", work_object_name: "Карьер-2", values: {}, warnings: [] } }),
      "Настройки модели: умолчания — у объекта «Карьер-2» они не сохранены",
    ],
    [
      result({ settings: { source: "defaults", work_object_name: "Карьер-3", values: {}, warnings: ["x"] } }),
      "Настройки модели: умолчания — настройки объекта «Карьер-3» не прочитаны",
    ],
    [result({ model: "kuzram_legacy", model_version: "1.0.0" }), "Старая модель: настройки объекта не применяются"],
  ])("вариант %#", (value, label) => {
    expect(settingsSourceLabel(value)).toBe(label);
  });
});
```

- [ ] **Шаг 2: Убедиться, что тесты падают**

Запуск: `npm --prefix frontend test -- src/pages/design/FragmentationPanel.test.tsx`
Ожидание: FAIL — `Failed to resolve import "./fragmentationSettings"`.

- [ ] **Шаг 3: Типы и запросы**

В `frontend/src/types/design.ts`:

```ts
export const FRAGMENTATION_MODELS: { value: FragmentationModelId; label: string }[] = [
  { value: "kuznetsov", label: "Кузнецов" },
  { value: "kuzram", label: "Kuz-Ram" },
  { value: "swebrec", label: "Swebrec" },
  { value: "kuznetsov_legacy", label: "Кузнецов (старая)" },
  { value: "kuzram_legacy", label: "Kuz-Ram (старая)" },
  { value: "swebrec_legacy", label: "Swebrec (старая)" },
];

export type FragmentationModelId =
  | "kuznetsov"
  | "kuzram"
  | "swebrec"
  | "kuznetsov_legacy"
  | "kuzram_legacy"
  | "swebrec_legacy";

/** Откуда взяты настройки Kuz-Ram прогноза. Значения настроек интерфейс не показывает. */
export type FragmentationSettingsSnapshot = {
  source: "request" | "work_object" | "defaults";
  work_object_name: string;
  values: Record<string, unknown>;
  warnings: string[];
};
```

В `ModelProvenance` добавить `settings?: Partial<FragmentationSettingsSnapshot>;`, в `PredictedFragmentation` — `warnings?: string[];`, в `FragmentationInputs` — `charge_length_m?: number;` и `hole_length_m?: number;` (необязательные: сохранённые прогнозы до PR 2 их не несут), в `FragmentationPredictResponse` — `settings: FragmentationSettingsSnapshot;`, в `DesignScenarioParams` — `work_object_name?: string;` и `kuzram_settings?: Partial<FragmentationSettingsSnapshot>;`.

В `frontend/src/api/endpoints.ts` в типы тела `fragmentation`, `buildPassport` и `compareScenarios` добавить `work_object_name?: string;`.

- [ ] **Шаг 4: Подпись источника и панель**

Создать `frontend/src/pages/design/fragmentationSettings.ts`:

```ts
/**
 * Подпись «откуда настройки модели» для панели «Кусковатость». Сами настройки
 * живут на листе «Расчёт» за объектом работ; «Проектирование» их только
 * читает, поэтому здесь нет полей ввода — только строка источника.
 */
import type { FragmentationPredictResponse } from "../../types/design";

export function isLegacyFragmentationModel(model: string): boolean {
  return model.endsWith("_legacy");
}

export function settingsSourceLabel(result: Pick<FragmentationPredictResponse, "model" | "settings">): string {
  if (isLegacyFragmentationModel(result.model)) return "Старая модель: настройки объекта не применяются";
  const settings = result.settings;
  if (settings?.source === "request") return "Настройки модели: заданы в запросе";
  if (settings?.source === "work_object") return `Настройки модели: объект работ «${settings.work_object_name}»`;
  if (settings?.work_object_name) {
    return settings.warnings.length > 0
      ? `Настройки модели: умолчания — настройки объекта «${settings.work_object_name}» не прочитаны`
      : `Настройки модели: умолчания — у объекта «${settings.work_object_name}» они не сохранены`;
  }
  return "Настройки модели: умолчания";
}
```

В `frontend/src/pages/design/FragmentationPanel.tsx` добавить импорт `import { settingsSourceLabel } from "./fragmentationSettings";` и сразу после блока `<div className="frag-caption">…</div>` вставить:

```tsx
            <small className="frag-settings">{settingsSourceLabel(result)}</small>
```

- [ ] **Шаг 5: Активный объект работ в запросах «Проектирования»**

В `frontend/src/pages/design/DesignPage.tsx` добавить импорт `import { useWorkspace } from "../../app/useWorkspace";` и в начале компонента, рядом с остальными хуками состояния:

```tsx
  // Настройки модели Kuz-Ram «Проектирование» берёт у объекта работ из шапки —
  // там же, где их берёт лист «Расчёт».
  const { state: workspaceState } = useWorkspace();
  const workObjectName = workspaceState?.settings.active_work_object_name ?? "";
```

Добавить `work_object_name: workObjectName` в:
- тело `api.design.fragmentation({...})` в `predictFragmentation` (после `hole_oversize_coeff`);
- `params` в `createDesignScenario`, `runOptimization`, `runRecommendation`;
- тело `api.design.compareScenarios({...})`;
- тело `api.design.buildPassport({...})` в `assemblePassport`.

- [ ] **Шаг 6: Убедиться, что тесты и сборка проходят**

Запуск: `npm --prefix frontend test -- src/pages/design/FragmentationPanel.test.tsx`
Ожидание: PASS.
Запуск: `npm --prefix frontend test`
Ожидание: PASS, весь набор.
Запуск: `npm --prefix frontend run build`
Ожидание: сборка без ошибок типов.

- [ ] **Шаг 7: Коммит**

```bash
git add frontend/src/types/design.ts frontend/src/api/endpoints.ts frontend/src/pages/design
git commit -m "Проектирование: шесть моделей кусковатости и строка источника настроек модели"
```

---

### Задача 11: документация

**Файлы:**
- Изменить: `Docs/KUZRAM_MODEL.md`, `CLAUDE.md` (раздел «Модель подбора q (Kuz-Ram)»), `simulation/fragmentation/cunningham.py:8-11` (док-строка модуля), `simulation/fragmentation/__init__.py:1-12` (док-строка пакета)

- [ ] **Шаг 1: Док-строки кода**

В `simulation/fragmentation/cunningham.py` последний абзац док-строки модуля заменить на:

```
Полный прогноз одной точки собирает predict_point — её зовут подбор q в
Blast.py и все три модели движка «Проектирования» через
simulation.fragmentation.base.region_point. Прежние формулы движка —
simulation.fragmentation.legacy.
```

Док-строку пакета `simulation/fragmentation/__init__.py` заменить на:

```python
"""Прогноз кусковатости по пространственному проекту.

Три модели считают на общей базе Каннингема — фактор A, x50 и n дают
cunningham.predict_point, та же функция, что у листа «Расчёт» — и
различаются только кривой распределения:

* ``kuznetsov`` — Розин — Раммлер с фиксированным n;
* ``kuzram`` — Розин — Раммлер с n по Каннингему;
* ``swebrec`` — функция Swebrec (Оухтерлони).

Прежние формулы доступны как ``kuznetsov_legacy``, ``kuzram_legacy`` и
``swebrec_legacy`` (simulation/fragmentation/legacy/). Прогноз всегда несёт
роль ``predicted``; измеренную кусковатость пакет не пишет (BDX-010).
"""
```

- [ ] **Шаг 2: `CLAUDE.md`**

В разделе «Модель подбора q (Kuz-Ram)» заменить фразу, начинающуюся с «„Проектирование", отчёты и ML пока на `simulation/fragmentation/kuzram.py`», на:

```
Движок «Проектирования» (`simulation/fragmentation/engine.py`) зовёт её во
всех трёх моделях через `simulation/fragmentation/base.py::region_point`;
прежние формулы — `simulation/fragmentation/legacy/` под именами `*_legacy`.
Настройки модели «Проектирование» берёт из объекта работ
(`api/services/fragmentation_settings.py`). ML-калибровки и пространственные
признаки до PR 3 считают базу старой моделью `kuzram_legacy`; подробности —
`Docs/KUZRAM_MODEL.md`.
```

- [ ] **Шаг 3: `Docs/KUZRAM_MODEL.md`**

В конец файла добавить раздел:

```markdown
## «Проектирование»: движок кусковатости

С версии моделей 2.0.0 «Проектирование», паспорт БВР, сценарии, поиск Парето
и рекомендации считают кусковатость той же функцией `predict_point`, что и
лист «Расчёт». Входные величины региона влияния переводит в её аргументы
`simulation/fragmentation/base.py::region_point`:

- диаметр — диаметр скважины × коэффициент разбуривания, мм (как в
  `Blast.py::_charge`);
- длина заряда — сумма длин взрывчатых дек, без дек — скважина минус забойка;
  высота уступа — по оси скважины без перебура;
- сила ВВ — теплота взрыва / 4,184, для смеси ВВ — средняя по массе.

Три модели различаются только кривой: `kuznetsov` — Розин — Раммлер с n = 1,
`kuzram` — с n по Каннингему, `swebrec` — функция Swebrec поверх того же x50.
Прежние формулы (A по Лилли, 19/30, n ≥ 0,8) доступны как `*_legacy`, версия
1.0.0; сохранённые прогнозы не пересчитываются.

**Настройки модели.** Отдельных настроек в «Проектировании» нет: сервер берёт
блок `kuzram` черновика листа «Расчёт» (`calc_object_inputs`) для объекта
работ из запроса, без него — для активного объекта организации, а если блока
нет — умолчания. Источник пишется в ответ и в `provenance.settings` прогноза.

**Неполный паспорт.** Скважина с нулевой массой заряда, силой ВВ или сеткой
пропускается с предупреждением; нулевая длина заряда или высота уступа —
множитель L/H = 1 и предупреждение.

**ML.** До PR 3 калибровки и пространственные признаки считают базу старой
моделью `kuzram_legacy`, а поправки калибровок к новым моделям в сценариях не
применяются.
```

- [ ] **Шаг 4: Коммит**

```bash
git add Docs/KUZRAM_MODEL.md CLAUDE.md simulation/fragmentation/cunningham.py simulation/fragmentation/__init__.py
git commit -m "Документация: движок «Проектирования» на общей базе Каннингема"
```

---

### Задача 12: сдача PR (координатор, не субагент)

**Файлы:** нет правок кода; работа с веткой и PR.

- [ ] **Шаг 1: Прогнать всё**

```bash
../../../.venv/bin/python -m pytest -q -p no:cacheprovider
```

```bash
npm --prefix frontend test
```

```bash
npm --prefix frontend run build
```

`git diff origin/main -- tests/fixtures/kuzram_cunningham_golden.json` — пусто; `tests/fixtures/fragmentation_legacy_golden.json` менялся только коммитом задачи 4, шаг 1.

- [ ] **Шаг 2: Проверить на стенде**

Поднять стенд ветки (API и фронт из этого worktree), открыть «Проектирование» на демо-блоке и посчитать кусковатость моделью Kuz-Ram при объекте, у которого на листе «Расчёт» задана поправка C(A). Убедиться: строка «Настройки модели: объект работ «…»» видна; x50 блока меняется вслед за C(A) на листе «Расчёт»; модель «Kuz-Ram (старая)» даёт прежние числа.

- [ ] **Шаг 3: Код-ревью**

Запустить `/code-review high origin/main...HEAD`, исправить найденное, перезапустить тесты.

- [ ] **Шаг 4: Открыть PR — по команде владельца**

База — `main`, заголовок и описание по-русски. В описании: что было (два разных прогноза по одному блоку), что стало (одна функция, настройки объекта), что числа «Проектирования» меняются намеренно, список отступлений от спеки (подтверждены владельцем 30.09), правки ожиданий существующих тестов (если были), что ML остаётся на старой базе до PR 3.

- [ ] **Шаг 5: Ревью Codex**

Codex ревьюит при открытии PR и по комментарию `@codex review`; после перевода PR в «ready» — дождаться нового ревью. Ответить на замечания, исправить, обновить описание.

- [ ] **Шаг 6: Слияние — только по решению владельца**

Слияние в `main` выкатывает прод (17–50 минут), и числа «Проектирования» меняются для всех. До слияния владелец объявляет это команде (риск 2 спеки). PR 3 лучше выкатывать вскоре после PR 2: пока его нет, поправки калибровок кусковатости к новой модели не применяются.

---

## Что дальше

PR 3 — калибровки и пометки: база (имя и версия модели) в артефакте калибровки, отказ применять старые с предупреждением «нужно переобучить», перевод baseline калибровки и пространственных признаков на новую модель с чтением снимка настроек из сохранённого прогноза, пометка «старая модель» в панели и паспорте, решение по датасетам со смешанной базой (отступление № 7).
