# Калибровки ML на новой базе кусковатости (PR 3) — план реализации

> **Для агентов-исполнителей:** обязательный навык — superpowers:subagent-driven-development (рекомендуется) или superpowers:executing-plans. Шаги отмечаются чекбоксами (`- [ ]`).

**Цель:** каждая калибровка кусковатости и пространственная модель знает базу (модель и версию), на которой обучена, и не ложится молча на прогноз другой формулы; снимок датасета несёт baseline текущей базы, чтобы калибровки можно было переобучить на истории; прогнозы старой модели помечены.

**Архитектура:** модуль `intelligence/calibration/base.py` описывает базу (`FragmentationBase`) и решает совместимость калибровки с прогнозом; его зовут `/calibration/predict`, сценарии, дрейф и пространственная модель. Модуль `intelligence/datasets/baseline.py` считает baseline движком для строки снимка и для `/calibration/predict` без присланного baseline. Артефакты получают поля `baseline_model` и `baseline_model_version` (пусто — старая база). Правило «старая модель» — `simulation/fragmentation/models.py::is_old_model`.

**Стек:** Python 3.11, FastAPI + pydantic 2, unittest через pytest; фронт — React + TypeScript, vitest.

**Спека:** `Docs/plans/2026-09-30-fragmentation-cunningham-pr3-calibration-design.md` (утверждена владельцем 2026-09-30). Родительская — `Docs/plans/2026-09-29-fragmentation-engine-cunningham-design.md`. Базовый коммит плана — `b59e9e0` (ветка `feat/fragmentation-cunningham-engine`, PR #101 не слит).

## Отступления от спеки

1. **`is_old_model` живёт в `simulation/fragmentation/models.py`, а не в `intelligence/calibration/base.py`** (спека 4.3). Причина: его зовёт `simulation/fragmentation/base.py::settings_source_label`, а расчётный слой не импортирует `intelligence`.
2. **База снимка хранится ещё и на уровне снимка** — поле `DatasetSnapshot.fragmentation_base` рядом с полями строки из спеки (4.4). Обучение берёт базу оттуда; поля строки нужны дрейфу и разбору.
3. **Пересчёт baseline без присланного значения в `/calibration/predict` идёт той же функцией, что и снимок** (`fragmentation_baseline`): порода и ВВ — из входных величин сохранённого прогноза. Сейчас `_compute_empirical` берёт умолчания. Причина: baseline применения и baseline обучения должны считаться одинаково.
4. **Ответ `/calibration/predict` базу артефакта не несёт** (спека 4.2: «в `provenance`»). Пользователь видит базу в списке и карточке калибровки (`base_label`), а отказ — предупреждением ответа; отдельное поле в ответе никто не читает. Пространственный ответ базу несёт (`physics_model`, `base_label`): там это сама модель расчёта физики.
5. **Сбой загрузки одной калибровки в сценарии снимает только её** с предупреждением, а не весь калибровочный слой (сейчас одно исключение снимает и PPV). Нужно, потому что проверка базы теперь загружает артефакт кусковатости и для новых моделей.

## Общие ограничения

- **Не пушить в `main` и ничего не сливать**: push в `main` сразу выкатывает прод (`.github/workflows/deploy.yml`).
- Задача 0 выполняется в ветке `feat/fragmentation-cunningham-engine` (PR #101) до его слияния, в отдельном worktree от `origin/feat/fragmentation-cunningham-engine`. Задачи 1–13 — в ветке `feat/fragmentation-cunningham-calibration` от ветки PR 2 после задачи 0; после слияния #101 ветка перебазируется на `origin/main`.
- Python-команды из корня worktree: `../../../.venv/bin/python -m pytest <путь> -q -p no:cacheprovider`.
- Фронт: в свежем worktree сначала `npm --prefix frontend ci`; тесты — `npm --prefix frontend test -- <путь>`, типы и сборка — `npm --prefix frontend run build`.
- Комментарии, сообщения об ошибках, тексты интерфейса и коммиты — по-русски.
- Сохранённые прогнозы, снимки датасетов и артефакты калибровок и пространственных моделей не переписываются; миграций базы нет.
- Формулы движка и Каннингема не меняются: `tests/fixtures/kuzram_cunningham_golden.json`, `tests/fixtures/fragmentation_legacy_golden.json`, `tests/test_kuzram_control_example.py`, `tests/test_kuzram_frontend_contract.py` правке не подлежат.
- Текущая база — `kuzram` версии `FRAGMENTATION_MODELS["kuzram"]["version"]` (сейчас `2.0.0`); старая — `kuzram_legacy` `1.0.0`. Версию в коде не писать литералом, кроме тестов.
- Предупреждение отказа содержит слово «переобучить».
- `ppv_residual` ведёт себя как раньше во всех точках.
- Фронт показывает подписи базы с сервера (`base_label`), своей логики «старая/новая» у фронта нет.

## На что смотреть ревью

1. **Сохранённый прогноз с нулевыми или отсутствующими входными величинами** (прогнозы до PR 2 без `charge_length_m`, паспорт с нулём прочности). Ожидание: недостающая величина породы или ВВ берётся умолчанием, baseline посчитан (задача 4).
2. **Взрыв, который движок не считает** (нет зарядов). Ожидание: снимок собирается, `baseline_*` пустые с предупреждением, строка не идёт в обучение кусковатости (задачи 4, 6).
3. **Новые строковые поля цели кусковатости** (`predicted_model`, `baseline_model`) не делают группу FRAGMENTATION «заполненной» у взрыва без замеров (задача 4).
4. **Присланный baseline с неизвестной моделью** (`"abc"`) или без модели. Ожидание: поправка не применена, предупреждение, не 500 (задачи 0, 7).
5. **Старый файл артефакта** (без полей базы) грузится с прежней контрольной суммой и меняет статус (задача 3).

---

### Задача 0: заплатка в PR 2 — присланный baseline несёт свою модель

Выполняется в ветке `feat/fragmentation-cunningham-engine`, отдельным коммитом; после неё — /code-review и новый раунд Codex по #101 (координатор).

**Файлы:**
- Изменить: `api/schemas/calibration.py:122-129` (`CalibrationPredictRequest`)
- Изменить: `api/services/calibration_service.py:137-205` (`predict_calibration`)
- Создать: `frontend/src/pages/design/calibrationBaseline.ts`, тест `frontend/src/pages/design/calibrationBaseline.test.ts`
- Изменить: `frontend/src/pages/design/DesignPage.tsx:1495-1520` (`overlayBaseline`, `applyCalibrationOverlay`), `frontend/src/api/endpoints.ts:619-627` (`predictCalibration`)
- Изменить тесты: `tests/test_api_calibration.py` (запросы на строках 46, 75, 94, 116), `tests/test_explainability.py:333`
- Создать тест: `tests/test_api_calibration_provided_baseline.py`

**Интерфейсы:**
- Отдаёт: поля запроса `baseline_model: str = ""`, `baseline_model_version: str = ""`; функцию фронта `calibrationBaseline(type, fragmentation, vibration) -> { baseline, baseline_model?, baseline_model_version? }`. Задача 7 заменяет серверную проверку на `refusal_reason`.

- [ ] **Шаг 1: Падающий тест сервера**

Создать `tests/test_api_calibration_provided_baseline.py`:

```python
"""Присланный клиентом baseline кусковатости принимается только вместе с моделью.

Калибровки обучены на Kuz-Ram 1.0.0; x50 модели 2.0.0, наложенный без
проверки, нарушает решение владельца № 3.
"""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from api.schemas.calibration import CalibrationPredictRequest, CalibrationTrainRequest
from api.services import calibration_service
from intelligence.datasets.persistence import save_snapshot
from tests.calibration_fixtures import synthetic_snapshot

TEAM_ID = "api-cal-provided"


class ProvidedBaselineTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        patcher = patch("cost.persistence.data_root", return_value=Path(self._tmp.name))
        patcher.start()
        self.addCleanup(patcher.stop)
        self.snapshot = save_snapshot(TEAM_ID, synthetic_snapshot())

    def _predict(self, model_type: str, **fields):
        trained = calibration_service.train_calibration(
            TEAM_ID, CalibrationTrainRequest(dataset_id=self.snapshot.dataset_id, model_type=model_type)
        )
        return calibration_service.predict_calibration(
            TEAM_ID,
            CalibrationPredictRequest(
                model_type=model_type,
                model_id=trained.model_id,
                site_id="quarry-1",
                baseline=150.0,
                features=self.snapshot.samples[-1].features,
                **fields,
            ),
        )

    def test_new_model_baseline_is_refused(self):
        result = self._predict("kuzram_residual", baseline_model="kuzram", baseline_model_version="2.0.0")

        self.assertFalse(result.calibration_applied)
        self.assertEqual(result.calibrated, 150.0)
        self.assertIn("переобучить", result.warnings[0])

    def test_old_model_baseline_is_calibrated(self):
        for model, version in (("kuzram_legacy", "1.0.0"), ("kuzram", "1.0.0")):
            with self.subTest(model=model):
                result = self._predict("kuzram_residual", baseline_model=model, baseline_model_version=version)

                self.assertTrue(result.calibration_applied)

    def test_baseline_without_model_is_refused(self):
        result = self._predict("oversize_residual")

        self.assertFalse(result.calibration_applied)
        self.assertIn("Не указано", result.warnings[0])

    def test_ppv_needs_no_model(self):
        result = self._predict("ppv_residual")

        self.assertTrue(result.calibration_applied)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Шаг 2: Убедиться, что тест падает**

Запуск: `../../../.venv/bin/python -m pytest tests/test_api_calibration_provided_baseline.py -q -p no:cacheprovider`
Ожидание: FAIL — `CalibrationPredictRequest` не знает `baseline_model`; без модели калибровка применяется.

- [ ] **Шаг 3: Поля запроса**

В `api/schemas/calibration.py`, класс `CalibrationPredictRequest`, после `baseline: float | None = None`:

```python
    # Модель и версия, которыми посчитан присланный baseline кусковатости:
    # без них сервер не знает, на какую формулу ляжет поправка.
    baseline_model: str = ""
    baseline_model_version: str = ""
```

- [ ] **Шаг 4: Проверка на сервере**

В `api/services/calibration_service.py` добавить импорты:

```python
from intelligence.calibration.prediction import _old_base
from intelligence.calibration.types import MODEL_KUZRAM_RESIDUAL, MODEL_OVERSIZE_RESIDUAL
from simulation.fragmentation.models import ModelProvenance
```

(`STATUS_CANDIDATE, normalize_model_type` уже импортируются из `intelligence.calibration.types` — дописать в тот же импорт.) Перед `predict_calibration`:

```python
def _provided_base_refusal(request: CalibrationPredictRequest, model_type: str) -> str:
    """Причина не накладывать калибровку на присланный baseline; пусто — можно.

    До PR 3 все калибровки кусковатости обучены на старой базе Kuz-Ram 1.0.0,
    поэтому присланный baseline принимается, только если он посчитан ею.
    """
    if model_type not in {MODEL_KUZRAM_RESIDUAL, MODEL_OVERSIZE_RESIDUAL}:
        return ""
    model = request.baseline_model.strip()
    if not model:
        return "Не указано, какой моделью посчитан baseline, — калибровка кусковатости не применена."
    if _old_base(ModelProvenance(model=model, model_version=request.baseline_model_version.strip())):
        return ""
    return (
        "Калибровка обучена на старой модели Kuz-Ram 1.0.0 и к прогнозу новой модели "
        "не применяется — её нужно переобучить."
    )
```

В `predict_calibration` после проверки `if model.model_type != model_type: ...` и перед `try: prediction = apply_residual(`:

```python
    refusal = _provided_base_refusal(request, model_type) if baseline_source == "provided" else ""
    if refusal:
        payload = baseline_without_model(
            baseline=float(baseline),
            model_type=model_type,
            site_id=site_id,
            baseline_source=baseline_source,
            reason=refusal,
        )
        return _predict_schema(payload.to_dict())
```

- [ ] **Шаг 5: Существующие тесты шлют старую базу**

Калибровки фикстур обучены на прогнозах 1.0.0. В `tests/test_api_calibration.py` в каждом `CalibrationPredictRequest(` с `model_type="kuzram_residual"` и `baseline=150.0` (строки 46, 75, 94, 116) и в `tests/test_explainability.py:333` дописать:

```python
                baseline_model="kuzram_legacy",
                baseline_model_version="1.0.0",
```

- [ ] **Шаг 6: Тесты сервера проходят**

Запуск: `../../../.venv/bin/python -m pytest tests/test_api_calibration_provided_baseline.py tests/test_api_calibration.py tests/test_explainability.py -q -p no:cacheprovider`
Ожидание: PASS.

- [ ] **Шаг 7: Падающий тест фронта**

Создать `frontend/src/pages/design/calibrationBaseline.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import type { FragmentationPredictResponse } from "../../types/design";
import { calibrationBaseline } from "./calibrationBaseline";

const fragmentation = {
  model: "kuzram",
  model_version: "2.0.0",
  site: { prediction: { x50_mm: 210, oversize_pct: 7.5 } },
} as unknown as FragmentationPredictResponse;

describe("calibrationBaseline", () => {
  it("x50 несёт модель и версию прогноза", () => {
    expect(calibrationBaseline("kuzram_residual", fragmentation, null)).toEqual({
      baseline: 210,
      baseline_model: "kuzram",
      baseline_model_version: "2.0.0",
    });
  });

  it("негабарит — тоже с моделью", () => {
    expect(calibrationBaseline("oversize_residual", fragmentation, null).baseline).toBe(7.5);
  });

  it("без прогноза кусковатости baseline пустой", () => {
    expect(calibrationBaseline("kuzram_residual", null, null)).toEqual({ baseline: null });
  });

  it("PPV — максимум по приёмникам, без модели", () => {
    const vibration = { predictions: [{ ppv_mm_s: 3 }, { ppv_mm_s: null }, { ppv_mm_s: 5 }] };
    expect(calibrationBaseline("ppv_residual", fragmentation, vibration)).toEqual({ baseline: 5 });
  });
});
```

Запуск: `npm --prefix frontend test -- src/pages/design/calibrationBaseline.test.ts`
Ожидание: FAIL — модуль не найден.

- [ ] **Шаг 8: Функция фронта**

Создать `frontend/src/pages/design/calibrationBaseline.ts`:

```ts
import type { CalibrationModelType, FragmentationPredictResponse } from "../../types/design";

type VibrationLike = { predictions?: { ppv_mm_s: number | null }[] } | null | undefined;

export type CalibrationBaseline = {
  baseline: number | null;
  baseline_model?: string;
  baseline_model_version?: string;
};

/**
 * Baseline для калибровки. Для кусковатости — вместе с моделью и версией
 * прогноза: сервер накладывает поправку, только если она обучена на той же базе.
 */
export function calibrationBaseline(
  type: CalibrationModelType | string,
  fragmentation: FragmentationPredictResponse | null | undefined,
  vibration: VibrationLike,
): CalibrationBaseline {
  if (type === "ppv_residual") {
    const values = (vibration?.predictions ?? [])
      .map((item) => item.ppv_mm_s)
      .filter((value): value is number => value != null);
    return { baseline: values.length ? Math.max(...values) : null };
  }
  const prediction = fragmentation?.site.prediction;
  if (!fragmentation || !prediction) return { baseline: null };
  return {
    baseline: type === "oversize_residual" ? prediction.oversize_pct : prediction.x50_mm,
    baseline_model: fragmentation.model,
    baseline_model_version: fragmentation.model_version,
  };
}
```

В `frontend/src/api/endpoints.ts`, тип payload `predictCalibration`, после `baseline?: number | null;`:

```ts
      baseline_model?: string;
      baseline_model_version?: string;
```

В `frontend/src/pages/design/DesignPage.tsx` удалить функцию `overlayBaseline` (строки 1495–1504; других вызовов у неё нет — проверить `grep -n "overlayBaseline" frontend/src/pages/design/DesignPage.tsx`), добавить импорт `import { calibrationBaseline } from "./calibrationBaseline";` и в `applyCalibrationOverlay` заменить строку `baseline: overlayBaseline(),` на:

```ts
        ...calibrationBaseline(calibrationType, fragResult, vibResult),
```

- [ ] **Шаг 9: Тест и сборка фронта**

Запуск: `npm --prefix frontend test -- src/pages/design/calibrationBaseline.test.ts` и `npm --prefix frontend run build`
Ожидание: PASS, сборка без ошибок типов. Если тип `vibResult` не совместим с `VibrationLike`, расширить `VibrationLike` до фактического типа `vibResult` (поле `predictions[].ppv_mm_s`), не приводя типы через `any`.

- [ ] **Шаг 10: Коммит**

```bash
git add api/schemas/calibration.py api/services/calibration_service.py tests/test_api_calibration_provided_baseline.py tests/test_api_calibration.py tests/test_explainability.py frontend/src/pages/design/calibrationBaseline.ts frontend/src/pages/design/calibrationBaseline.test.ts frontend/src/pages/design/DesignPage.tsx frontend/src/api/endpoints.ts
git commit -m "Калибровка: присланный baseline кусковатости принимается только с моделью старой базы"
```

---

### Задача 1: правило «старая модель» и подпись с версией

**Файлы:**
- Изменить: `simulation/fragmentation/models.py` (после констант моделей)
- Изменить: `simulation/fragmentation/base.py:111-134` (`settings_source_label`)
- Изменить: `api/services/design_service.py:715`, `design/reporting/html.py:86-91`
- Изменить тест: `tests/test_fragmentation_base.py:125-154` (`SettingsSourceLabelTests`)
- Создать тест: `tests/test_fragmentation_old_model.py`

**Интерфейсы:**
- Отдаёт: `simulation.fragmentation.models.is_old_model(model: str, version: str) -> bool`; `settings_source_label(model: str, model_version: str, snapshot: Mapping | None) -> str` (версия — второй обязательный аргумент).

- [ ] **Шаг 1: Падающие тесты**

Создать `tests/test_fragmentation_old_model.py`:

```python
"""«Старая модель» — прежние формулы: *_legacy или версия ниже 2.0.0."""
import unittest

from design.reporting.html import _model_version_line
from design.reporting.types import PredictedOutcomes
from simulation.fragmentation.models import is_old_model


class IsOldModelTests(unittest.TestCase):
    def test_cases(self):
        cases = (
            ("kuzram", "2.0.0", False),
            ("swebrec", "2.1.0", False),
            ("kuzram", "1.0.0", True),
            ("kuzram", "1", True),
            ("kuzram", "", True),
            ("kuzram", "abc", True),
            ("kuzram_legacy", "1.0.0", True),
            ("kuzram_legacy", "2.0.0", True),
        )
        for model, version, old in cases:
            with self.subTest(model=model, version=version):
                self.assertIs(is_old_model(model, version), old)


class PassportLineTests(unittest.TestCase):
    def test_saved_prediction_before_pr2_is_marked(self):
        predicted = PredictedOutcomes()
        predicted.fragmentation_model = "kuzram"
        predicted.fragmentation_model_version = "1.0.0"

        self.assertIn("Старая модель", _model_version_line(predicted))

    def test_new_prediction_without_snapshot_is_not_marked(self):
        predicted = PredictedOutcomes()
        predicted.fragmentation_model = "kuzram"
        predicted.fragmentation_model_version = "2.0.0"

        self.assertNotIn("Старая модель", _model_version_line(predicted))


if __name__ == "__main__":
    unittest.main()
```

Если `PredictedOutcomes()` требует обязательных аргументов, создать его так же, как это делают тесты в `tests/test_reporting*.py` (`grep -rn "PredictedOutcomes(" tests | head -3`).

В `tests/test_fragmentation_base.py`, `SettingsSourceLabelTests.test_labels`, каждый кортеж получает версию вторым элементом и вызов становится `settings_source_label(model, version, snapshot)`:

```python
        cases = (
            ("kuzram", "2.0.0", snap("work_object", "Карьер-1"), "Настройки модели: объект работ «Карьер-1»"),
            ("kuzram", "2.0.0", snap("request"), "Настройки модели: заданы в запросе"),
            ("kuzram", "2.0.0", snap("defaults"), "Настройки модели: умолчания"),
            (
                "kuzram",
                "2.0.0",
                snap("defaults", "Карьер-2"),
                "Настройки модели: умолчания — у объекта «Карьер-2» они не сохранены",
            ),
            (
                "kuzram",
                "2.0.0",
                snap("defaults", "Карьер-3", ["x"]),
                "Настройки модели: умолчания — настройки объекта «Карьер-3» не прочитаны",
            ),
            ("kuzram_legacy", "1.0.0", snap("work_object", "Карьер-1"), "Старая модель: настройки объекта не применяются"),
            ("kuzram_legacy", "1.0.0", None, "Старая модель: настройки объекта не применяются"),
            # Прогноз, сохранённый до PR 2, — тоже старая модель.
            ("kuzram", "1.0.0", None, "Старая модель: настройки объекта не применяются"),
            ("kuzram", "", {}, "Старая модель: настройки объекта не применяются"),
            # Новый прогноз без снимка строки не получает.
            ("kuzram", "2.0.0", {}, ""),
            ("kuzram", "2.0.0", None, ""),
        )
        for model, version, snapshot, label in cases:
            with self.subTest(model=model, version=version, snapshot=snapshot):
                self.assertEqual(settings_source_label(model, version, snapshot), label)
```

- [ ] **Шаг 2: Убедиться, что тесты падают**

Запуск: `../../../.venv/bin/python -m pytest tests/test_fragmentation_old_model.py tests/test_fragmentation_base.py -q -p no:cacheprovider`
Ожидание: FAIL — `ImportError: cannot import name 'is_old_model'`, `settings_source_label` не принимает версию.

- [ ] **Шаг 3: Реализация**

В `simulation/fragmentation/models.py` после `LEGACY_MODEL_SUFFIX` и констант моделей:

```python
def is_old_model(model: str, version: str) -> bool:
    """Прогноз посчитан прежними формулами (до перевода на Каннингема).

    Старые — модели *_legacy и любая модель версии ниже 2.0.0. Пустая или
    нечитаемая версия — тоже старая: так записаны прогнозы до PR 2.
    """
    if str(model or "").endswith(LEGACY_MODEL_SUFFIX):
        return True
    major = str(version or "").strip().split(".", 1)[0]
    return not major.isdigit() or int(major) < 2
```

В `simulation/fragmentation/base.py` импорт `from simulation.fragmentation.models import Calibration, FragmentationInputs, is_old_model` и начало `settings_source_label`:

```python
def settings_source_label(model: str, model_version: str, snapshot: Mapping[str, Any] | None) -> str:
    """Подпись «откуда настройки модели» для панели «Кусковатость» и паспорта.

    Единственное место с этими словами: фронт показывает settings_label из
    ответа API. Прогноз старой модели — *_legacy или сохранённый до PR 2
    с версией 1.0.0 — помечается «старая модель».
    """
    if is_old_model(model, model_version):
        return "Старая модель: настройки объекта не применяются"
```

(остальное тело без изменений).

В `api/services/design_service.py:715`: `label = settings_source_label(payload["model"], payload["model_version"], payload["settings"])`.

В `design/reporting/html.py`, `_model_version_line`:

```python
        settings_source_label(
            predicted.fragmentation_model,
            predicted.fragmentation_model_version,
            predicted.fragmentation_settings,
        ),
```

Паспорт без модели (`fragmentation_model == ""`) раньше строки источника не получал; чтобы так и осталось, в `_model_version_line` звать подпись только при непустой модели:

```python
def _model_version_line(predicted: PredictedOutcomes) -> str:
    label = ""
    if predicted.fragmentation_model:
        label = settings_source_label(
            predicted.fragmentation_model,
            predicted.fragmentation_model_version,
            predicted.fragmentation_settings,
        )
    parts = [predicted.fragmentation_model_version, label]
    return " · ".join(part for part in parts if part) or "—"
```

Проверить, что других вызовов нет: `grep -rn "settings_source_label(" api design simulation intelligence`.

- [ ] **Шаг 4: Тесты проходят**

Запуск: `../../../.venv/bin/python -m pytest tests/test_fragmentation_old_model.py tests/test_fragmentation_base.py tests/test_api_fragmentation.py tests/test_api_fragmentation_settings.py -q -p no:cacheprovider` и `../../../.venv/bin/python -m pytest tests -q -p no:cacheprovider -k "report or passport"`
Ожидание: PASS.

- [ ] **Шаг 5: Коммит**

```bash
git add simulation/fragmentation/models.py simulation/fragmentation/base.py api/services/design_service.py design/reporting/html.py tests/test_fragmentation_old_model.py tests/test_fragmentation_base.py
git commit -m "Кусковатость: прогноз версии 1.0.0 помечается старой моделью в панели и паспорте"
```

---

### Задача 2: база калибровок и правило совместимости

**Файлы:**
- Создать: `intelligence/calibration/base.py`
- Создать тест: `tests/test_calibration_base.py`

**Интерфейсы:**
- Использует: `is_old_model` (задача 1), `FRAGMENTATION_MODELS`, `resolve_model` (`simulation/fragmentation/engine.py`).
- Отдаёт: `FragmentationBase(model, model_version)` с `.legacy`, `.label()`, `.to_dict()`; `LEGACY_BASE`, `CURRENT_BASE`; `FRAGMENTATION_RESIDUALS`; `BASELINE_FIELDS: dict[str, str]`; `prediction_base(model, version) -> FragmentationBase` (ValueError на неизвестной модели); `artifact_base(baseline_model, baseline_model_version) -> FragmentationBase`; `snapshot_base(fragmentation_base: Mapping) -> FragmentationBase | None`; `compatible(model_type, artifact, prediction) -> bool`; `refusal_reason(model_type, artifact, prediction | None) -> str`; `sample_baseline(group: Mapping, model_type, artifact) -> float | None`; `base_label(model_type, baseline_model, baseline_model_version) -> str`; `spatial_base_label(baseline_model, baseline_model_version) -> str`.

- [ ] **Шаг 1: Падающие тесты**

Создать `tests/test_calibration_base.py`:

```python
"""База калибровки: к какому прогнозу можно наложить поправку."""
import unittest

from intelligence.calibration.base import (
    CURRENT_BASE,
    LEGACY_BASE,
    FragmentationBase,
    artifact_base,
    base_label,
    compatible,
    prediction_base,
    refusal_reason,
    sample_baseline,
    snapshot_base,
    spatial_base_label,
)

X50 = "kuzram_residual"
OVERSIZE = "oversize_residual"
PPV = "ppv_residual"
NEW_SWEBREC = FragmentationBase("swebrec", "2.0.0")


class PredictionBaseTests(unittest.TestCase):
    def test_current_and_legacy(self):
        self.assertEqual(CURRENT_BASE, FragmentationBase("kuzram", "2.0.0"))
        self.assertEqual(LEGACY_BASE, FragmentationBase("kuzram_legacy", "1.0.0"))

    def test_saved_before_pr2_is_legacy(self):
        for version in ("1.0.0", "1", ""):
            with self.subTest(version=version):
                self.assertEqual(prediction_base("kuzram", version), LEGACY_BASE)
        self.assertEqual(prediction_base("swebrec", "1.0.0"), FragmentationBase("swebrec_legacy", "1.0.0"))

    def test_new_and_aliases(self):
        self.assertEqual(prediction_base("Kuz-Ram", "2.0.0"), CURRENT_BASE)
        self.assertEqual(prediction_base("swebrec_legacy", "1.0.0"), FragmentationBase("swebrec_legacy", "1.0.0"))

    def test_unknown_model(self):
        with self.assertRaises(ValueError):
            prediction_base("abc", "2.0.0")

    def test_artifact_without_fields_is_legacy(self):
        self.assertEqual(artifact_base("", ""), LEGACY_BASE)
        self.assertEqual(artifact_base("kuzram", "2.0.0"), CURRENT_BASE)

    def test_snapshot_base(self):
        self.assertIsNone(snapshot_base({}))
        self.assertEqual(snapshot_base({"model": "kuzram", "model_version": "2.0.0"}), CURRENT_BASE)


class CompatibilityTests(unittest.TestCase):
    def test_x50_fits_any_model_of_same_base(self):
        self.assertTrue(compatible(X50, CURRENT_BASE, NEW_SWEBREC))
        self.assertTrue(compatible(X50, LEGACY_BASE, FragmentationBase("kuznetsov_legacy", "1.0.0")))
        self.assertFalse(compatible(X50, LEGACY_BASE, CURRENT_BASE))
        self.assertFalse(compatible(X50, CURRENT_BASE, LEGACY_BASE))

    def test_oversize_needs_same_model(self):
        self.assertTrue(compatible(OVERSIZE, CURRENT_BASE, CURRENT_BASE))
        self.assertFalse(compatible(OVERSIZE, CURRENT_BASE, NEW_SWEBREC))

    def test_ppv_always(self):
        self.assertTrue(compatible(PPV, CURRENT_BASE, LEGACY_BASE))
        self.assertEqual(refusal_reason(PPV, LEGACY_BASE, None), "")

    def test_refusal_names_both_bases(self):
        reason = refusal_reason(X50, LEGACY_BASE, CURRENT_BASE)

        self.assertIn("Kuz-Ram (старая) 1.0.0", reason)
        self.assertIn("Kuz-Ram 2.0.0", reason)
        self.assertIn("переобучить", reason)
        self.assertEqual(refusal_reason(X50, CURRENT_BASE, NEW_SWEBREC), "")

    def test_unknown_prediction_base_is_refused(self):
        self.assertIn("Не указано", refusal_reason(OVERSIZE, CURRENT_BASE, None))


class SampleBaselineTests(unittest.TestCase):
    def test_new_row_gives_baseline_for_new_artifact(self):
        row = {
            "predicted_x50_mm": 120.0,
            "predicted_model": "kuzram",
            "predicted_model_version": "1.0.0",
            "baseline_x50_mm": 150.0,
            "baseline_model": "kuzram",
            "baseline_model_version": "2.0.0",
        }
        self.assertEqual(sample_baseline(row, X50, CURRENT_BASE), 150.0)
        self.assertEqual(sample_baseline(row, X50, LEGACY_BASE), 120.0)

    def test_old_row_is_legacy(self):
        row = {"predicted_x50_mm": 120.0, "predicted_oversize_pct": 4.0}
        self.assertEqual(sample_baseline(row, OVERSIZE, LEGACY_BASE), 4.0)
        self.assertIsNone(sample_baseline(row, X50, CURRENT_BASE))

    def test_new_prediction_is_not_old_baseline(self):
        row = {"predicted_x50_mm": 120.0, "predicted_model": "kuzram", "predicted_model_version": "2.0.0"}
        self.assertIsNone(sample_baseline(row, X50, LEGACY_BASE))


class LabelTests(unittest.TestCase):
    def test_labels(self):
        self.assertEqual(base_label(X50, "kuzram", "2.0.0"), "База: Kuz-Ram 2.0.0")
        self.assertEqual(
            base_label(OVERSIZE, "", ""), "Старая база (Kuz-Ram (старая) 1.0.0) — только для старых моделей"
        )
        self.assertEqual(base_label(PPV, "", ""), "")
        self.assertEqual(spatial_base_label("kuzram", "2.0.0"), "База: Kuz-Ram 2.0.0")
        self.assertEqual(
            spatial_base_label("", ""), "Старая база (Kuz-Ram (старая) 1.0.0) — физика считается старой моделью"
        )


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Шаг 2: Убедиться, что тесты падают**

Запуск: `../../../.venv/bin/python -m pytest tests/test_calibration_base.py -q -p no:cacheprovider`
Ожидание: FAIL — `ModuleNotFoundError: intelligence.calibration.base`.

- [ ] **Шаг 3: Реализация**

Создать `intelligence/calibration/base.py`:

```python
"""База калибровок кусковатости: какой моделью посчитан baseline.

Калибровка — поправка к конкретной формуле. Артефакт помнит модель и
версию baseline, на котором обучен, а здесь решается, можно ли наложить
его на прогноз. Одно место для /calibration/predict, сценариев, дрейфа и
пространственной модели.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from intelligence.calibration.types import MODEL_KUZRAM_RESIDUAL, MODEL_OVERSIZE_RESIDUAL
from simulation.fragmentation.engine import FRAGMENTATION_MODELS, resolve_model
from simulation.fragmentation.models import (
    LEGACY_MODEL_SUFFIX,
    MODEL_KUZRAM,
    MODEL_KUZRAM_LEGACY,
    is_old_model,
)

FRAGMENTATION_RESIDUALS = frozenset({MODEL_KUZRAM_RESIDUAL, MODEL_OVERSIZE_RESIDUAL})
LEGACY_VERSION = "1.0.0"

# Поле строки снимка с baseline текущей базы для каждого типа калибровки.
BASELINE_FIELDS = {
    MODEL_KUZRAM_RESIDUAL: "baseline_x50_mm",
    MODEL_OVERSIZE_RESIDUAL: "baseline_oversize_pct",
}
_VALUE_FIELDS = {MODEL_KUZRAM_RESIDUAL: "x50_mm", MODEL_OVERSIZE_RESIDUAL: "oversize_pct"}


@dataclass(frozen=True)
class FragmentationBase:
    """Модель движка и версия, которыми посчитан baseline."""

    model: str
    model_version: str

    @property
    def legacy(self) -> bool:
        return self.model.endswith(LEGACY_MODEL_SUFFIX)

    def label(self) -> str:
        entry = FRAGMENTATION_MODELS.get(self.model)
        name = entry["label"] if entry else self.model
        return f"{name} {self.model_version}"

    def to_dict(self) -> dict[str, str]:
        return {"model": self.model, "model_version": self.model_version}


LEGACY_BASE = FragmentationBase(MODEL_KUZRAM_LEGACY, LEGACY_VERSION)
CURRENT_BASE = FragmentationBase(MODEL_KUZRAM, str(FRAGMENTATION_MODELS[MODEL_KUZRAM]["version"]))


def prediction_base(model: str, version: str) -> FragmentationBase:
    """База прогноза по имени модели и версии, как они записаны в прогнозе.

    Прогнозы до PR 2 записаны как «kuzram 1.0.0» — это та же старая
    формула, что теперь зовётся kuzram_legacy; все старые версии сводятся
    к 1.0.0. Неизвестное имя модели — ValueError.
    """
    model_id = resolve_model(model)
    if is_old_model(model_id, version):
        if not model_id.endswith(LEGACY_MODEL_SUFFIX):
            model_id += LEGACY_MODEL_SUFFIX
        return FragmentationBase(model_id, LEGACY_VERSION)
    return FragmentationBase(model_id, str(version).strip())


def artifact_base(baseline_model: str, baseline_model_version: str) -> FragmentationBase:
    """База артефакта; пустые поля — артефакт обучен до PR 3, на старой базе."""
    if not str(baseline_model or "").strip():
        return LEGACY_BASE
    return prediction_base(baseline_model, baseline_model_version)


def snapshot_base(fragmentation_base: Mapping[str, Any] | None) -> FragmentationBase | None:
    """База снимка датасета; None — снимок собран до PR 3."""
    model = str((fragmentation_base or {}).get("model") or "").strip()
    if not model:
        return None
    return prediction_base(model, str((fragmentation_base or {}).get("model_version") or ""))


def compatible(model_type: str, artifact: FragmentationBase, prediction: FragmentationBase) -> bool:
    """Можно ли наложить калибровку model_type, обученную на artifact, на прогноз prediction.

    У трёх моделей одной базы x50 одинаковый (различается только кривая),
    поэтому поправка x50 подходит к любой из них; негабарит зависит от
    кривой — только та же модель и версия.
    """
    if model_type == MODEL_KUZRAM_RESIDUAL:
        return artifact.legacy == prediction.legacy and artifact.model_version == prediction.model_version
    if model_type == MODEL_OVERSIZE_RESIDUAL:
        return artifact == prediction
    return True


def refusal_reason(
    model_type: str,
    artifact: FragmentationBase,
    prediction: FragmentationBase | None,
) -> str:
    """Почему калибровку нельзя наложить на прогноз; пустая строка — можно."""
    if model_type not in FRAGMENTATION_RESIDUALS:
        return ""
    if prediction is None:
        return "Не указано, какой моделью посчитан baseline, — калибровка кусковатости не применена."
    if compatible(model_type, artifact, prediction):
        return ""
    return (
        f"Калибровка обучена на прогнозах «{artifact.label()}» и к прогнозу «{prediction.label()}» "
        "не применяется — её нужно переобучить."
    )


def sample_baseline(group: Mapping[str, Any], model_type: str, artifact: FragmentationBase) -> float | None:
    """Baseline строки снимка, совместимый с базой артефакта; иначе None.

    Сначала baseline текущей базы (строки снимков PR 3), затем сохранённый
    прогноз; строка старого снимка без модели прогноза — старая база.
    """
    value_field = _VALUE_FIELDS.get(model_type)
    if value_field is None:
        return None
    candidates = (
        (f"baseline_{value_field}", group.get("baseline_model"), group.get("baseline_model_version")),
        (
            f"predicted_{value_field}",
            group.get("predicted_model") or MODEL_KUZRAM,
            group.get("predicted_model_version") or "",
        ),
    )
    for key, model, version in candidates:
        value = group.get(key)
        if value is None or not model:
            continue
        try:
            base = prediction_base(str(model), str(version or ""))
        except ValueError:
            continue
        if compatible(model_type, artifact, base):
            return float(value)
    return None


def base_label(model_type: str, baseline_model: str, baseline_model_version: str) -> str:
    """Подпись базы для списка и карточки калибровки; у PPV — пусто."""
    if model_type not in FRAGMENTATION_RESIDUALS:
        return ""
    base = artifact_base(baseline_model, baseline_model_version)
    if base.legacy:
        return f"Старая база ({base.label()}) — только для старых моделей"
    return f"База: {base.label()}"


def spatial_base_label(baseline_model: str, baseline_model_version: str) -> str:
    """Подпись базы пространственной модели: её физика считается этой моделью."""
    base = artifact_base(baseline_model, baseline_model_version)
    if base.legacy:
        return f"Старая база ({base.label()}) — физика считается старой моделью"
    return f"База: {base.label()}"
```

- [ ] **Шаг 4: Тесты проходят**

Запуск: `../../../.venv/bin/python -m pytest tests/test_calibration_base.py -q -p no:cacheprovider`
Ожидание: PASS.

- [ ] **Шаг 5: Коммит**

```bash
git add intelligence/calibration/base.py tests/test_calibration_base.py
git commit -m "Калибровки: база прогноза и правило совместимости поправки с моделью"
```

---

### Задача 3: база в артефактах калибровки и пространственной модели

**Файлы:**
- Изменить: `intelligence/calibration/types.py:122-207` (`CalibrationModel`)
- Изменить: `intelligence/calibration/persistence.py:38-50, 117-142` (`CalibrationSummary`, `list_models`)
- Изменить: `api/schemas/calibration.py:66-106` (`CalibrationModelSchema`, `CalibrationSummarySchema`)
- Изменить: `api/services/calibration_service.py` (`_model_schema`)
- Изменить: `intelligence/spatial/types.py:369-455` (`SpatialModel`), `intelligence/spatial/persistence.py:42-56, 129-165` (`SpatialSummary`, `list_models`)
- Изменить: `api/schemas/spatial.py` (`SpatialModelSchema`, `SpatialSummarySchema`), `api/services/spatial_service.py:56` (`_model_schema`)
- Создать тест: `tests/test_calibration_artifact_base.py`

**Интерфейсы:**
- Использует: `base_label`, `spatial_base_label` (задача 2).
- Отдаёт: поля `baseline_model: str = ""`, `baseline_model_version: str = ""` у `CalibrationModel` и `SpatialModel` (в `to_dict`/`from_dict`); поля `baseline_model`, `baseline_model_version`, `base_label` у сводок и схем API.

- [ ] **Шаг 1: Падающие тесты**

Создать `tests/test_calibration_artifact_base.py`:

```python
"""Артефакты помнят базу; файлы до PR 3 грузятся и меняют статус как раньше."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from api.services import calibration_service, spatial_service
from intelligence.calibration import persistence as calibration_store
from intelligence.calibration.training import train_from_snapshot
from intelligence.spatial import persistence as spatial_store
from intelligence.spatial.training import train_from_snapshot as train_spatial
from tests.calibration_fixtures import synthetic_snapshot
from tests.spatial_fixtures import synthetic_spatial_snapshot

TEAM_ID = "artifact-base"


def _strip_base(path: Path, integrity_hash) -> None:
    """Файл как до PR 3: без полей базы, с пересчитанной контрольной суммой."""
    data = json.loads(path.read_text(encoding="utf-8"))
    data.pop("baseline_model", None)
    data.pop("baseline_model_version", None)
    data["integrity_sha256"] = integrity_hash(data)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


class ArtifactBaseTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        patcher = patch("cost.persistence.data_root", return_value=Path(self._tmp.name))
        patcher.start()
        self.addCleanup(patcher.stop)

    def _calibration(self, model_id: str, base: tuple[str, str]):
        model = train_from_snapshot(synthetic_snapshot(), model_type="kuzram_residual", model_id=model_id)
        model.baseline_model, model.baseline_model_version = base
        return calibration_store.save_model(TEAM_ID, model)

    def test_fields_round_trip(self):
        saved = self._calibration("cal-new", ("kuzram", "2.0.0"))

        loaded = calibration_store.load_model(TEAM_ID, saved.model_id)

        self.assertEqual((loaded.baseline_model, loaded.baseline_model_version), ("kuzram", "2.0.0"))

    def test_file_before_pr3_loads_and_changes_status(self):
        saved = self._calibration("cal-old", ("kuzram", "2.0.0"))
        _strip_base(calibration_store.metadata_path(TEAM_ID, saved.model_id), calibration_store.integrity_hash)

        loaded = calibration_store.load_model(TEAM_ID, saved.model_id)
        promoted = calibration_store.set_status(TEAM_ID, saved.model_id, "production")

        self.assertEqual(loaded.baseline_model, "")
        self.assertEqual(promoted.status, "production")

    def test_labels_in_list_and_card(self):
        self._calibration("cal-new", ("kuzram", "2.0.0"))
        self._calibration("cal-old", ("", ""))

        labels = {item.model_id: item.base_label for item in calibration_service.list_calibration_models(TEAM_ID).items}
        card = calibration_service.get_calibration_model(TEAM_ID, "cal-old")

        self.assertEqual(labels["cal-new"], "База: Kuz-Ram 2.0.0")
        self.assertIn("Старая база", labels["cal-old"])
        self.assertIn("Старая база", card.base_label)

    def test_spatial_model_file_before_pr3(self):
        model = train_spatial(synthetic_spatial_snapshot(), team_id=TEAM_ID, model_id="sp-old")
        saved = spatial_store.save_model(TEAM_ID, model)
        _strip_base(spatial_store.metadata_path(TEAM_ID, saved.model_id), spatial_store.integrity_hash)

        loaded = spatial_store.load_model(TEAM_ID, saved.model_id)
        listed = spatial_service.list_spatial_models(TEAM_ID)

        self.assertEqual(loaded.baseline_model, "")
        self.assertIn("Старая база", listed.items[0].base_label)


if __name__ == "__main__":
    unittest.main()
```

Сверить имена перед запуском: `grep -n "^def \|^from\|^import" intelligence/spatial/persistence.py | head -30` (функции `metadata_path`, `integrity_hash`, `save_model`, `load_model`) и `grep -n "^def " api/services/spatial_service.py` (имя функции списка). Если имя отличается — поправить тест под фактическое, логику не менять.

- [ ] **Шаг 2: Убедиться, что тесты падают**

Запуск: `../../../.venv/bin/python -m pytest tests/test_calibration_artifact_base.py -q -p no:cacheprovider`
Ожидание: FAIL — у `CalibrationModel` нет `baseline_model`, у схем нет `base_label`.

- [ ] **Шаг 3: Поля `CalibrationModel`**

В `intelligence/calibration/types.py`, класс `CalibrationModel`, после `measured_field: str = ""`:

```python
    # Модель и версия движка, которыми посчитан baseline обучения. Пусто —
    # артефакт обучен до PR 3 на старой базе Kuz-Ram 1.0.0.
    baseline_model: str = ""
    baseline_model_version: str = ""
```

В `to_dict` после `"measured_field": ...`:

```python
            "baseline_model": self.baseline_model,
            "baseline_model_version": self.baseline_model_version,
```

В `from_dict` после `measured_field=...`:

```python
            baseline_model=str(data.get("baseline_model", "") or ""),
            baseline_model_version=str(data.get("baseline_model_version", "") or ""),
```

- [ ] **Шаг 4: Сводка и схемы калибровки**

В `intelligence/calibration/persistence.py` добавить импорт `from intelligence.calibration.base import base_label`; в `CalibrationSummary` после `sample_count: int`:

```python
    baseline_model: str = ""
    baseline_model_version: str = ""
    base_label: str = ""
```

В `list_models`, в конструкторе `CalibrationSummary(...)` после `sample_count=...`:

```python
                baseline_model=str(data.get("baseline_model", "") or ""),
                baseline_model_version=str(data.get("baseline_model_version", "") or ""),
                base_label=base_label(
                    str(data.get("model_type", "")),
                    str(data.get("baseline_model", "") or ""),
                    str(data.get("baseline_model_version", "") or ""),
                ),
```

В `api/schemas/calibration.py` в `CalibrationModelSchema` и `CalibrationSummarySchema` добавить в конец:

```python
    baseline_model: str = ""
    baseline_model_version: str = ""
    # Подпись базы с сервера: «База: Kuz-Ram 2.0.0» или «Старая база …».
    base_label: str = ""
```

В `api/services/calibration_service.py` импорт `from intelligence.calibration.base import base_label` и `_model_schema`:

```python
def _model_schema(model) -> CalibrationModelSchema:
    payload = model.to_dict()
    payload.pop("estimator", None)
    payload.pop("training_matrix", None)
    payload["base_label"] = base_label(model.model_type, model.baseline_model, model.baseline_model_version)
    return CalibrationModelSchema(**payload)
```

- [ ] **Шаг 5: Пространственная модель**

В `intelligence/spatial/types.py`, класс `SpatialModel`, после `data_roles`:

```python
    # База физики, на которой обучена модель; пусто — до PR 3, kuzram_legacy.
    baseline_model: str = ""
    baseline_model_version: str = ""
```

(поле `estimators` остаётся последним). В `to_dict` после `"data_roles": ...` — `"baseline_model": self.baseline_model, "baseline_model_version": self.baseline_model_version,`; в `from_dict` — `baseline_model=str(data.get("baseline_model", "") or ""), baseline_model_version=str(data.get("baseline_model_version", "") or ""),`.

В `intelligence/spatial/persistence.py`: импорт `from intelligence.calibration.base import spatial_base_label`; `SpatialSummary` получает `baseline_model: str = ""`, `baseline_model_version: str = ""`, `base_label: str = ""`; `list_models` заполняет их так же, как в шаге 4, но `base_label=spatial_base_label(model, version)`.

В `api/schemas/spatial.py` в `SpatialModelSchema` и `SpatialSummarySchema` добавить те же три поля, что в шаге 4. В `api/services/spatial_service.py`, `_model_schema`, перед созданием схемы: `payload["base_label"] = spatial_base_label(model.baseline_model, model.baseline_model_version)` (импорт `from intelligence.calibration.base import spatial_base_label`; если `_model_schema` строит схему не из `payload`, добавить ключ в тот словарь, из которого она строится).

- [ ] **Шаг 6: Тесты проходят**

Запуск: `../../../.venv/bin/python -m pytest tests/test_calibration_artifact_base.py tests/test_calibration_persistence.py tests/test_api_calibration.py tests/test_api_spatial.py tests/test_spatial_training.py -q -p no:cacheprovider`
Ожидание: PASS.

- [ ] **Шаг 7: Коммит**

```bash
git add intelligence/calibration/types.py intelligence/calibration/persistence.py api/schemas/calibration.py api/services/calibration_service.py intelligence/spatial/types.py intelligence/spatial/persistence.py api/schemas/spatial.py api/services/spatial_service.py tests/test_calibration_artifact_base.py
git commit -m "Артефакты калибровки и пространственной модели хранят базу baseline"
```

---

### Задача 4: снимок датасета — baseline текущей базой

**Файлы:**
- Создать: `intelligence/datasets/baseline.py`
- Изменить: `intelligence/datasets/targets.py:24-45` (`extract_fragmentation_targets`), `:151-170` (`target_group_has_values`)
- Изменить: `intelligence/datasets/builder.py` (`_extract_snapshot_holes`, `build_sample`, `DatasetSnapshot`, `build_snapshot`)
- Изменить: `intelligence/spatial/features.py:227-321` (`extract_hole_observations`, `attach_physics_predictions`)
- Изменить: `api/schemas/datasets.py:40-55` (`DatasetSnapshotSchema`)
- Изменить тест: `tests/test_fragmentation_ml_baseline.py` — удалить класс `SpatialPhysicsTests` (его заменяет тест ниже)
- Создать тест: `tests/test_dataset_baseline.py`

**Интерфейсы:**
- Отдаёт: `intelligence.datasets.baseline.BASELINE_MODEL = "kuzram"`; `stored_prediction(design) -> PredictedFragmentation | None`; `baseline_settings(design, fallback_settings, fallback_source) -> tuple[KuzRamSettings | None, dict]`; `fragmentation_baseline(design, *, model=BASELINE_MODEL, fallback_settings=None, fallback_source=None) -> dict` с ключами `baseline_x50_mm`, `baseline_oversize_pct`, `baseline_model`, `baseline_model_version`, `baseline_settings`, `baseline_warnings`; `build_sample(design, *, site_id, fallback_settings=None, fallback_source=None)`; `build_snapshot(..., fallback_settings=None, fallback_source=None)`; `DatasetSnapshot.fragmentation_base: dict[str, str]`; `extract_hole_observations(..., physics_model=MODEL_KUZRAM, settings=None, settings_source=None)`.

- [ ] **Шаг 1: Падающие тесты**

Создать `tests/test_dataset_baseline.py`:

```python
"""Строка снимка: сохранённый прогноз как есть и baseline текущей базы рядом."""
import unittest
from dataclasses import asdict
from unittest.mock import patch

from intelligence.datasets.baseline import fragmentation_baseline
from intelligence.datasets.builder import DatasetSnapshot, build_sample, build_snapshot
from intelligence.datasets.targets import target_group_has_values
from simulation.fragmentation import engine as fragmentation_engine
from simulation.fragmentation.cunningham import KuzRamSettings
from simulation.fragmentation.engine import predict_design
from simulation.fragmentation.regions import ExplosiveSpec, RockSpec
from tests.dataset_fixtures import closed_design

ROCK = RockSpec(name="Гранит", density_t_m3=2.65, ucs_mpa=150.0, fissuring_ff=2.0)
EXPLOSIVE = ExplosiveSpec(name="АНФО", density_t_m3=0.82, power_mj_kg=3.8)
FALLBACK = KuzRamSettings(rock_factor_correction=0.8)
FALLBACK_SOURCE = {"source": "work_object", "work_object_name": "Карьер-2", "warnings": []}


def _site_x50(design, **kwargs) -> float:
    return predict_design(design, model="kuzram", **kwargs)["site"]["prediction"]["x50_mm"]


def _with_stored_inputs(design):
    """Сохранённый прогноз с входными величинами — как у панели «Кусковатость»."""
    site = predict_design(design, model="kuzram_legacy", default_rock=ROCK, default_explosive=EXPLOSIVE)["site"]
    design.blast_result.basis.predicted_fragmentation.provenance.inputs = dict(site["inputs"])
    return design


class RowTests(unittest.TestCase):
    def test_stored_prediction_kept_and_current_baseline_added(self):
        design = closed_design("b-1")

        frag = build_sample(design, site_id="quarry-1").targets["FRAGMENTATION"]

        self.assertEqual(frag["predicted_x50_mm"], 150.0)
        self.assertEqual((frag["predicted_model"], frag["predicted_model_version"]), ("kuzram", "1"))
        self.assertEqual((frag["baseline_model"], frag["baseline_model_version"]), ("kuzram", "2.0.0"))
        self.assertAlmostEqual(frag["baseline_x50_mm"], _site_x50(design), places=9)
        self.assertIn("умолчания", frag["baseline_warnings"][0])

    def test_rock_and_explosive_from_stored_inputs(self):
        design = _with_stored_inputs(closed_design("b-2"))

        result = fragmentation_baseline(design)

        self.assertAlmostEqual(
            result["baseline_x50_mm"], _site_x50(design, default_rock=ROCK, default_explosive=EXPLOSIVE), places=9
        )
        self.assertFalse(any("умолчания" in item for item in result["baseline_warnings"]))

    def test_zero_stored_inputs_fall_back_to_defaults(self):
        design = closed_design("b-3")
        design.blast_result.basis.predicted_fragmentation.provenance.inputs = {
            "rock_ucs_mpa": 0.0,
            "rock_density_t_m3": 0.0,
            "explosive_energy_mj_kg": 0.0,
        }

        result = fragmentation_baseline(design)

        self.assertAlmostEqual(result["baseline_x50_mm"], _site_x50(design), places=9)

    def test_settings_snapshot_of_stored_prediction_wins(self):
        design = closed_design("b-4")
        design.blast_result.basis.predicted_fragmentation.provenance.settings = {
            "source": "work_object",
            "work_object_name": "Карьер-1",
            "values": asdict(KuzRamSettings(rock_factor_correction=1.3)),
            "warnings": [],
        }

        result = fragmentation_baseline(design, fallback_settings=FALLBACK, fallback_source=FALLBACK_SOURCE)

        self.assertEqual(result["baseline_settings"]["values"]["rock_factor_correction"], 1.3)
        self.assertEqual(result["baseline_settings"]["work_object_name"], "Карьер-1")

    def test_fallback_settings_without_snapshot(self):
        result = fragmentation_baseline(
            closed_design("b-5"), fallback_settings=FALLBACK, fallback_source=FALLBACK_SOURCE
        )

        self.assertEqual(result["baseline_settings"]["values"]["rock_factor_correction"], 0.8)
        self.assertEqual(result["baseline_settings"]["work_object_name"], "Карьер-2")

    def test_engine_failure_keeps_row(self):
        design = closed_design("b-6")
        design.loads = []

        frag = build_sample(design, site_id="quarry-1").targets["FRAGMENTATION"]

        self.assertIsNone(frag["baseline_x50_mm"])
        self.assertIn("не посчитан", frag["baseline_warnings"][-1])

    def test_string_fields_do_not_complete_group(self):
        group = {
            "predicted_model": "kuzram",
            "predicted_model_version": "2.0.0",
            "baseline_model": "kuzram",
            "baseline_model_version": "2.0.0",
            "baseline_x50_mm": 150.0,
            "baseline_settings": {"source": "defaults"},
            "baseline_warnings": ["x"],
        }
        self.assertFalse(target_group_has_values(group))


class SnapshotTests(unittest.TestCase):
    def test_snapshot_records_base(self):
        snapshot = build_snapshot([closed_design("s-1")], site_id="quarry-1", dataset_id="s", dataset_version=1)

        self.assertEqual(snapshot.fragmentation_base, {"model": "kuzram", "model_version": "2.0.0"})
        restored = DatasetSnapshot.from_dict(snapshot.to_dict())
        self.assertEqual(restored.fragmentation_base, snapshot.fragmentation_base)

    def test_old_snapshot_has_no_base(self):
        payload = build_snapshot([closed_design("s-2")], site_id="quarry-1", dataset_id="s", dataset_version=1).to_dict()
        payload.pop("fragmentation_base")

        self.assertEqual(DatasetSnapshot.from_dict(payload).fragmentation_base, {})

    def test_hole_physics_uses_current_model(self):
        with patch.object(
            fragmentation_engine, "predict_region", wraps=fragmentation_engine.predict_region
        ) as spy:
            build_sample(closed_design("s-3"), site_id="quarry-1")

        self.assertTrue(spy.call_args_list)
        models = {call.kwargs.get("model", call.args[1] if len(call.args) > 1 else None) for call in spy.call_args_list}
        self.assertEqual(models, {"kuzram"})


if __name__ == "__main__":
    unittest.main()
```

В `tests/test_fragmentation_ml_baseline.py` удалить класс `SpatialPhysicsTests` целиком.

- [ ] **Шаг 2: Убедиться, что тесты падают**

Запуск: `../../../.venv/bin/python -m pytest tests/test_dataset_baseline.py -q -p no:cacheprovider`
Ожидание: FAIL — `ModuleNotFoundError: intelligence.datasets.baseline`.

- [ ] **Шаг 3: Модуль baseline**

Создать `intelligence/datasets/baseline.py`:

```python
"""Baseline кусковатости текущей базой — для снимка датасета и калибровки.

Калибровка учится на разнице «замер − baseline» и потом накладывается на
прогноз текущей модели, поэтому baseline считается той же моделью, что и
прогноз сегодня, а не берётся из прогноза, сохранённого при взрыве: тот мог
быть посчитан старой формулой. Сохранённый прогноз остаётся в строке снимка
рядом как есть.
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from design.models import BlastDesign
from simulation.fragmentation.base import settings_from_snapshot
from simulation.fragmentation.cunningham import KuzRamSettings
from simulation.fragmentation.engine import FRAGMENTATION_MODELS, predict_design, resolve_model
from simulation.fragmentation.models import MODEL_KUZRAM, FragmentationInputs, PredictedFragmentation
from simulation.fragmentation.regions import (
    DEFAULT_EXPLOSIVE_DENSITY_T_M3,
    DEFAULT_EXPLOSIVE_ENERGY_MJ_KG,
    DEFAULT_ROCK_DENSITY_T_M3,
    DEFAULT_ROCK_FISSURING,
    DEFAULT_ROCK_UCS_MPA,
    ExplosiveSpec,
    RockSpec,
)

BASELINE_MODEL = MODEL_KUZRAM


def stored_prediction(design: BlastDesign) -> PredictedFragmentation | None:
    """Прогноз, сохранённый в результате взрыва; None — его нет."""
    result = design.blast_result
    basis = getattr(result, "basis", None) if result is not None else None
    return getattr(basis, "predicted_fragmentation", None) if basis is not None else None


def baseline_settings(
    design: BlastDesign,
    fallback_settings: KuzRamSettings | None = None,
    fallback_source: Mapping[str, Any] | None = None,
) -> tuple[KuzRamSettings | None, dict[str, Any]]:
    """Снимок настроек сохранённого прогноза, иначе запасные (объект работ или умолчания)."""
    stored = stored_prediction(design)
    snapshot = stored.provenance.settings if stored is not None else {}
    if snapshot:
        return settings_from_snapshot(snapshot)
    return fallback_settings, dict(fallback_source or {})


def _positive(value: float, default: float) -> float:
    """Нулевая или отрицательная величина сохранённого прогноза — умолчание."""
    return value if value > 0 else default


def _specs(design: BlastDesign, inputs: FragmentationInputs) -> dict[str, Any]:
    """Порода и ВВ из входных величин сохранённого прогноза — то, что видел инженер."""
    kwargs: dict[str, Any] = {
        "default_rock": RockSpec(
            name=inputs.rock_name or design.rock_name or "порода",
            density_t_m3=_positive(inputs.rock_density_t_m3, DEFAULT_ROCK_DENSITY_T_M3),
            ucs_mpa=_positive(inputs.rock_ucs_mpa, DEFAULT_ROCK_UCS_MPA),
            fissuring_ff=_positive(inputs.rock_fissuring, DEFAULT_ROCK_FISSURING),
        ),
        "default_explosive": ExplosiveSpec(
            name=inputs.explosive_name or design.explosive_key or "ВВ",
            density_t_m3=_positive(inputs.explosive_density_t_m3, DEFAULT_EXPLOSIVE_DENSITY_T_M3),
            power_mj_kg=_positive(inputs.explosive_energy_mj_kg, DEFAULT_EXPLOSIVE_ENERGY_MJ_KG),
        ),
    }
    if inputs.lump_size_mm > 0:
        kwargs["lump_size_mm"] = inputs.lump_size_mm
    return kwargs


def fragmentation_baseline(
    design: BlastDesign,
    *,
    model: str = BASELINE_MODEL,
    fallback_settings: KuzRamSettings | None = None,
    fallback_source: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Baseline x50 и негабарита моделью model по паспорту взрыва.

    Не посчиталось — значения None и причина в baseline_warnings: один
    неполный взрыв не должен ронять сборку снимка.
    """
    model_id = resolve_model(model)
    out: dict[str, Any] = {
        "baseline_x50_mm": None,
        "baseline_oversize_pct": None,
        "baseline_model": model_id,
        "baseline_model_version": str(FRAGMENTATION_MODELS[model_id]["version"]),
        "baseline_settings": {},
        "baseline_warnings": [],
    }
    warnings: list[str] = []
    stored = stored_prediction(design)
    kwargs: dict[str, Any] = {}
    if stored is not None and stored.provenance.inputs:
        kwargs = _specs(design, FragmentationInputs.from_dict(stored.provenance.inputs))
    else:
        warnings.append("Сохранённого прогноза нет: порода и ВВ для baseline — умолчания.")
    settings, source = baseline_settings(design, fallback_settings, fallback_source)
    try:
        payload = predict_design(
            design,
            model=model_id,
            hole_oversize_coeff=(design.charge_rules or {}).get("hole_oversize_coeff"),
            settings=settings,
            settings_source=source,
            **kwargs,
        )
    except Exception as exc:  # noqa: BLE001 — снимок не должен падать из-за одного взрыва
        warnings.append(f"Baseline кусковатости не посчитан: {exc}")
        out["baseline_warnings"] = warnings
        return out
    site = (payload.get("site") or {}).get("prediction") or {}
    out["baseline_x50_mm"] = site.get("x50_mm")
    out["baseline_oversize_pct"] = site.get("oversize_pct")
    out["baseline_settings"] = dict(payload.get("settings") or {})
    out["baseline_warnings"] = warnings + [str(item) for item in payload.get("warnings") or []]
    return out
```

- [ ] **Шаг 4: Цели и валидация**

В `intelligence/datasets/targets.py`, `extract_fragmentation_targets`, после `"predicted_oversize_pct": ...`:

```python
        "predicted_model": predicted.provenance.model if predicted else "",
        "predicted_model_version": predicted.provenance.model_version if predicted else "",
```

В `target_group_has_values` условие генератора:

```python
            if key not in skip
            and not str(key).endswith("_role")
            and not str(key).endswith("_count")
            # Модель прогноза и baseline текущей базы — контекст, а не цель:
            # взрыв без замеров от них заполненным не становится.
            and not str(key).startswith("baseline_")
            and key not in {"predicted_model", "predicted_model_version"}
```

- [ ] **Шаг 5: Физика скважин — модель и настройки параметром**

В `intelligence/spatial/features.py`:

```python
def extract_hole_observations(
    design: BlastDesign,
    *,
    site_id: str = "",
    neighbor_k: int = DEFAULT_NEIGHBOR_K,
    include_physics: bool = True,
    physics_model: str = "kuzram",
    settings: Any = None,
    settings_source: Mapping[str, Any] | None = None,
) -> list[HoleObservation]:
```

(`Mapping` импортировать из `collections.abc`, `Any` — из `typing`, если ещё нет), и вызов `attach_physics_predictions(design, rows, physics_model=physics_model, settings=settings, settings_source=settings_source)`.

`attach_physics_predictions` получает те же три именованных параметра (`physics_model: str = "kuzram"`), из локальных импортов убрать `MODEL_KUZRAM_LEGACY`, а вызов прогноза заменить на:

```python
            # Физика считается базой, на которой обучена (или будет обучена)
            # пространственная модель: снимок — текущей, применение — базой артефакта.
            prediction = predict_region(
                region.inputs,
                model=physics_model,
                settings=settings,
                settings_source=settings_source,
            )
```

Строковое умолчание `"kuzram"` вместо импорта константы — чтобы модуль не тянул `simulation` при импорте (локальные импорты там сделаны намеренно).

- [ ] **Шаг 6: Сборщик снимка**

В `intelligence/datasets/builder.py`:

```python
from collections.abc import Mapping

from intelligence.datasets.baseline import BASELINE_MODEL, baseline_settings, fragmentation_baseline
from simulation.fragmentation.engine import FRAGMENTATION_MODELS
```

`_extract_snapshot_holes`:

```python
def _extract_snapshot_holes(
    design: BlastDesign,
    *,
    site_id: str,
    settings: Any = None,
    settings_source: Mapping[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Freeze hole-level rows at snapshot time. Training never rereads the live design."""
    try:
        from intelligence.spatial.features import extract_hole_observations, snapshot_hole_payload

        return snapshot_hole_payload(
            extract_hole_observations(
                design,
                site_id=site_id,
                include_physics=True,
                physics_model=BASELINE_MODEL,
                settings=settings,
                settings_source=settings_source,
            )
        )
    except Exception:
        return []
```

`build_sample`:

```python
def build_sample(
    design: BlastDesign,
    *,
    site_id: str,
    fallback_settings: Any = None,
    fallback_source: Mapping[str, Any] | None = None,
) -> TrainingSample:
    """Extract a candidate sample. Inclusion is decided by validate_sample."""
    features = extract_features(design, site_id=site_id)
    fired_coverage = (features.get("EXECUTION") or {}).get("fired_coverage")
    targets = extract_targets(design.blast_result, fired_coverage=fired_coverage)
    provenance = sample_provenance(design, site_id=site_id)
    settings, source = baseline_settings(design, fallback_settings, fallback_source)
    holes = _extract_snapshot_holes(design, site_id=site_id, settings=settings, settings_source=source)
    validation = validate_sample(
        design=design,
        features=features,
        targets=targets,
        provenance=provenance,
        site_id=site_id,
    )
    # Baseline текущей базы — после проверки: это контекст для калибровки,
    # а не цель, и на допуск образца он не влияет.
    targets["FRAGMENTATION"].update(
        fragmentation_baseline(design, fallback_settings=fallback_settings, fallback_source=fallback_source)
    )
    return TrainingSample(
        ...  # без изменений
    )
```

`DatasetSnapshot`: поле после `immutable` —

```python
    # Модель и версия, которыми посчитаны baseline_* строк и физика скважин.
    # Пусто — снимок собран до PR 3: там только сохранённые прогнозы старой базы.
    fragmentation_base: dict[str, str] = field(default_factory=dict)
```

В `to_dict` и `summary` — `"fragmentation_base": dict(self.fragmentation_base),`; в `from_dict` — `fragmentation_base={str(k): str(v) for k, v in (data.get("fragmentation_base") or {}).items()},`.

`build_snapshot` получает `fallback_settings: Any = None, fallback_source: Mapping[str, Any] | None = None`, передаёт их в `build_sample(design, site_id=site_id, fallback_settings=fallback_settings, fallback_source=fallback_source)` и создаёт снимок с

```python
        fragmentation_base={
            "model": BASELINE_MODEL,
            "model_version": str(FRAGMENTATION_MODELS[BASELINE_MODEL]["version"]),
        },
```

В `api/schemas/datasets.py`, `DatasetSnapshotSchema`, после `immutable`: `fragmentation_base: dict[str, str] = Field(default_factory=dict)`.

Если импорт `intelligence.datasets.baseline` в `builder.py` даёт цикл (`simulation` → `design` → `intelligence`), перенести его внутрь `build_sample` и `build_snapshot` локальным импортом.

- [ ] **Шаг 7: Тесты проходят**

Запуск: `../../../.venv/bin/python -m pytest tests/test_dataset_baseline.py tests/test_fragmentation_ml_baseline.py tests/test_dataset_builder.py tests/test_dataset_targets.py tests/test_dataset_validation.py tests/test_dataset_persistence.py tests/test_api_datasets.py tests/test_spatial_hole_features.py -q -p no:cacheprovider`
Ожидание: PASS. Если тест датасетов сравнивает группу FRAGMENTATION целиком со словарём, дописать в ожидание новые ключи (перечислить такие правки в описании PR).

- [ ] **Шаг 8: Коммит**

```bash
git add intelligence/datasets/baseline.py intelligence/datasets/targets.py intelligence/datasets/builder.py intelligence/spatial/features.py api/schemas/datasets.py tests/test_dataset_baseline.py tests/test_fragmentation_ml_baseline.py
git commit -m "Снимок датасета: baseline кусковатости текущей базой рядом с сохранённым прогнозом"
```

---

### Задача 5: сервис датасетов — настройки объекта работ

**Файлы:**
- Изменить: `api/services/dataset_service.py:63-87` (`build_snapshot_for_team`)
- Изменить: `api/routers/datasets.py:25-30` (`build_dataset`)
- Создать тест: `tests/test_api_dataset_settings.py`

**Интерфейсы:**
- Использует: `resolve_kuzram_settings` (`api/services/fragmentation_settings.py`), `build_snapshot(..., fallback_settings, fallback_source)` (задача 4).
- Отдаёт: `build_snapshot_for_team(team_id, request, *, repository: EconomicsRepository | None = None)`.

- [ ] **Шаг 1: Падающий тест**

Создать `tests/test_api_dataset_settings.py`:

```python
"""Снимок берёт настройки модели активного объекта работ, если у прогноза нет своих."""
import tempfile
import unittest
from dataclasses import asdict
from pathlib import Path
from unittest.mock import patch

from api.schemas.datasets import DatasetBuildRequest
from api.services import dataset_service
from cost.v2.repository import InMemoryEconomicsRepository
from design.persistence import save_design
from simulation.fragmentation.cunningham import KuzRamSettings
from tests.dataset_fixtures import closed_design

ORG = "org-ds"
OBJECT = "Карьер-1"


def _repository() -> InMemoryEconomicsRepository:
    repository = InMemoryEconomicsRepository()
    block = {**asdict(KuzRamSettings()), "rock_factor_correction": 1.4}
    repository.save_calc_inputs(ORG, "tester", OBJECT, {"version": 1, "kuzram": block})
    repository.import_legacy_workspace(
        ORG, "tester", team_name="Команда", active_scenario_id="drill_blast", active_work_object_name=OBJECT
    )
    return repository


class DatasetSettingsTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        patcher = patch("cost.persistence.data_root", return_value=Path(self._tmp.name))
        patcher.start()
        self.addCleanup(patcher.stop)
        save_design(ORG, closed_design("ds-1"))

    def _frag(self, repository):
        snapshot = dataset_service.build_snapshot_for_team(
            ORG, DatasetBuildRequest(site_id="quarry-1", design_ids=["ds-1"]), repository=repository
        )
        return snapshot.samples[0].targets["FRAGMENTATION"]

    def test_active_work_object_settings(self):
        frag = self._frag(_repository())

        self.assertEqual(frag["baseline_settings"]["source"], "work_object")
        self.assertEqual(frag["baseline_settings"]["work_object_name"], OBJECT)
        self.assertEqual(frag["baseline_settings"]["values"]["rock_factor_correction"], 1.4)

    def test_without_repository_defaults(self):
        frag = self._frag(None)

        self.assertEqual(frag["baseline_settings"]["source"], "defaults")


if __name__ == "__main__":
    unittest.main()
```

Если `closed_design` не проходит валидацию снимка (образец в `rejected`), взять `varied_closed_designs(1)[0]` из `tests/calibration_fixtures.py` — его `test_train_from_closed_blast_snapshot` уже собирает в снимок.

- [ ] **Шаг 2: Убедиться, что тест падает**

Запуск: `../../../.venv/bin/python -m pytest tests/test_api_dataset_settings.py -q -p no:cacheprovider`
Ожидание: FAIL — `build_snapshot_for_team() got an unexpected keyword argument 'repository'`.

- [ ] **Шаг 3: Реализация**

В `api/services/dataset_service.py`:

```python
from api.services.fragmentation_settings import resolve_kuzram_settings
from cost.v2.repository import EconomicsRepository
```

`build_snapshot_for_team(team_id: str, request: DatasetBuildRequest, *, repository: EconomicsRepository | None = None)`; перед `snapshot = build_snapshot(`:

```python
    # Настройки модели для взрывов, чей прогноз не хранит своего снимка
    # (прогнозы до PR 2): активный объект работ организации, иначе умолчания.
    resolved = resolve_kuzram_settings(
        explicit=None, work_object_name="", organization_id=team_id, repository=repository
    )
```

и в вызов `build_snapshot(...)` добавить `fallback_settings=resolved.settings, fallback_source=resolved.source_payload(),`.

В `api/routers/datasets.py`:

```python
from api.services.economics_service import get_economics_repository
from cost.v2.repository import EconomicsRepository
```

```python
@router.post("", response_model=DatasetSnapshotSchema, status_code=201)
def build_dataset(
    request: DatasetBuildRequest,
    session: dict = Depends(require_internal_access),
    repository: EconomicsRepository = Depends(get_economics_repository),
) -> DatasetSnapshotSchema:
    return dataset_service.build_snapshot_for_team(session["org"], request, repository=repository)
```

- [ ] **Шаг 4: Тесты проходят**

Запуск: `../../../.venv/bin/python -m pytest tests/test_api_dataset_settings.py tests/test_api_datasets.py tests/test_api_feature_flags.py -q -p no:cacheprovider`
Ожидание: PASS. Если тест с `TestClient` на `/datasets` падает на подключении к PostgreSQL, добавить в него `app.dependency_overrides[get_economics_repository] = lambda: InMemoryEconomicsRepository()` — так сделано в `tests/conftest.py:43`.

- [ ] **Шаг 5: Коммит**

```bash
git add api/services/dataset_service.py api/routers/datasets.py tests/test_api_dataset_settings.py
git commit -m "Снимок датасета: настройки модели активного объекта работ для baseline"
```

---

### Задача 6: обучение на базе снимка

**Файлы:**
- Изменить: `intelligence/calibration/features.py:57-66, 84-130` (`measured_and_baseline`, `residual_table`)
- Изменить: `intelligence/calibration/training.py:77-133` (`train_from_snapshot`)
- Изменить: `intelligence/spatial/training.py:66-129` (`train_from_snapshot`)
- Изменить: `tests/calibration_fixtures.py` (`synthetic_snapshot`, новый `with_current_base`), `tests/test_explainability.py:121` (`explained_calibration_snapshot`)
- Создать тест: `tests/test_calibration_training_base.py`

**Интерфейсы:**
- Использует: `snapshot_base`, `BASELINE_FIELDS`, `FRAGMENTATION_RESIDUALS` (задача 2); `DatasetSnapshot.fragmentation_base` (задача 4).
- Отдаёт: `residual_table(snapshot, model_type, *, baseline_field: str | None = None)`; `measured_and_baseline(sample, model_type, baseline_field: str | None = None)`; `OLD_SNAPSHOT_MESSAGE`; фикстуры `synthetic_snapshot(..., legacy: bool = False)` и `with_current_base(snapshot)`.

- [ ] **Шаг 1: Фикстуры**

В `tests/calibration_fixtures.py`:

```python
CURRENT_BASE_FIELDS = {"baseline_model": "kuzram", "baseline_model_version": "2.0.0"}


def with_current_base(snapshot: DatasetSnapshot) -> DatasetSnapshot:
    """Снимок как после PR 3: baseline текущей базы рядом с сохранённым прогнозом."""
    for sample in snapshot.samples:
        frag = sample.targets.setdefault("FRAGMENTATION", {})
        frag.setdefault("baseline_x50_mm", frag.get("predicted_x50_mm"))
        frag.setdefault("baseline_oversize_pct", frag.get("predicted_oversize_pct"))
        frag.update(CURRENT_BASE_FIELDS)
    snapshot.fragmentation_base = {"model": "kuzram", "model_version": "2.0.0"}
    return snapshot
```

`synthetic_snapshot` получает параметр `legacy: bool = False` и в конце:

```python
    snapshot = DatasetSnapshot(...)  # как было
    return snapshot if legacy else with_current_base(snapshot)
```

В `tests/test_explainability.py`, `explained_calibration_snapshot`, обернуть возвращаемый снимок: `return with_current_base(DatasetSnapshot(...))` (импорт `from tests.calibration_fixtures import with_current_base`).

- [ ] **Шаг 2: Падающие тесты**

Создать `tests/test_calibration_training_base.py`:

```python
"""Калибровки кусковатости учатся на baseline текущей базы и запоминают её."""
import unittest

from intelligence.calibration.features import residual_table
from intelligence.calibration.training import train_from_snapshot
from intelligence.spatial.training import train_from_snapshot as train_spatial
from tests.calibration_fixtures import synthetic_snapshot
from tests.spatial_fixtures import synthetic_spatial_snapshot


class CalibrationTrainingBaseTests(unittest.TestCase):
    def test_artifact_records_snapshot_base(self):
        for model_type, field in (("kuzram_residual", "baseline_x50_mm"), ("oversize_residual", "baseline_oversize_pct")):
            with self.subTest(model_type=model_type):
                model = train_from_snapshot(synthetic_snapshot(), model_type=model_type)

                self.assertEqual((model.baseline_model, model.baseline_model_version), ("kuzram", "2.0.0"))
                self.assertEqual(model.baseline_field, field)

    def test_trains_on_current_baseline_not_stored_prediction(self):
        snapshot = synthetic_snapshot()
        for sample in snapshot.samples:
            sample.targets["FRAGMENTATION"]["predicted_x50_mm"] = 999.0

        table = residual_table(snapshot, "kuzram_residual", baseline_field="baseline_x50_mm")

        self.assertEqual(set(table.baselines), {150.0})

    def test_row_without_baseline_is_skipped(self):
        snapshot = synthetic_snapshot()
        snapshot.samples[0].targets["FRAGMENTATION"]["baseline_x50_mm"] = None

        model = train_from_snapshot(snapshot, model_type="kuzram_residual")

        self.assertEqual(model.sample_count, snapshot.sample_count - 1)

    def test_old_snapshot_is_refused_for_fragmentation(self):
        for model_type in ("kuzram_residual", "oversize_residual"):
            with self.subTest(model_type=model_type), self.assertRaisesRegex(ValueError, "соберите новый снимок"):
                train_from_snapshot(synthetic_snapshot(legacy=True), model_type=model_type)

    def test_old_snapshot_still_trains_ppv(self):
        model = train_from_snapshot(synthetic_snapshot(legacy=True), model_type="ppv_residual")

        self.assertEqual(model.baseline_model, "")
        self.assertEqual(model.baseline_field, "predicted_max_ppv_mm_s")


class SpatialTrainingBaseTests(unittest.TestCase):
    def test_base_from_snapshot(self):
        snapshot = synthetic_spatial_snapshot()
        snapshot.fragmentation_base = {"model": "kuzram", "model_version": "2.0.0"}

        model = train_spatial(snapshot, team_id="sp-base")

        self.assertEqual((model.baseline_model, model.baseline_model_version), ("kuzram", "2.0.0"))

    def test_old_snapshot_gives_old_base(self):
        model = train_spatial(synthetic_spatial_snapshot(), team_id="sp-base")

        self.assertEqual(model.baseline_model, "")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Шаг 3: Убедиться, что тесты падают**

Запуск: `../../../.venv/bin/python -m pytest tests/test_calibration_training_base.py -q -p no:cacheprovider`
Ожидание: FAIL — артефакт без базы, `residual_table` не знает `baseline_field`, старый снимок обучается.

- [ ] **Шаг 4: Реализация**

В `intelligence/calibration/features.py`:

```python
def measured_and_baseline(
    sample: TrainingSample,
    model_type: str,
    baseline_field: str | None = None,
) -> tuple[float | None, float | None]:
    spec = MODEL_SPECS[normalize_model_type(model_type)]
    group = sample.targets.get(spec["target_group"]) or {}
    measured = _as_float(group.get(spec["measured_field"]))
    if measured is None:
        fallback = spec.get("measured_field_fallback")
        if fallback:
            measured = _as_float(group.get(fallback))
    baseline = _as_float(group.get(baseline_field or spec["baseline_field"]))
    return measured, baseline
```

`residual_table(snapshot: DatasetSnapshot, model_type: str, *, baseline_field: str | None = None)` и в цикле `measured, baseline = measured_and_baseline(sample, model_type, baseline_field)`.

В `intelligence/calibration/training.py`:

```python
from intelligence.calibration.base import BASELINE_FIELDS, FRAGMENTATION_RESIDUALS, snapshot_base

OLD_SNAPSHOT_MESSAGE = (
    "Снимок собран до перехода на новую модель кусковатости: в нём только прогнозы старой "
    "формулы — соберите новый снимок."
)
```

В `train_from_snapshot` после проверок `site_id`:

```python
    base = None
    baseline_field = spec["baseline_field"]
    if model_type in FRAGMENTATION_RESIDUALS:
        base = snapshot_base(snapshot.fragmentation_base)
        if base is None:
            raise ValueError(OLD_SNAPSHOT_MESSAGE)
        baseline_field = BASELINE_FIELDS[model_type]

    table = residual_table(snapshot, model_type, baseline_field=baseline_field)
```

и в конструкторе `CalibrationModel(...)` заменить `baseline_field=spec["baseline_field"],` на:

```python
        baseline_field=baseline_field,
        baseline_model=base.model if base is not None else "",
        baseline_model_version=base.model_version if base is not None else "",
```

В `intelligence/spatial/training.py`, в конструкторе `SpatialModel(...)`:

```python
        baseline_model=str((snapshot.fragmentation_base or {}).get("model") or ""),
        baseline_model_version=str((snapshot.fragmentation_base or {}).get("model_version") or ""),
```

- [ ] **Шаг 5: Тесты проходят**

Запуск: `../../../.venv/bin/python -m pytest tests/test_calibration_training_base.py tests/test_calibration_training.py tests/test_calibration_persistence.py tests/test_calibration_algorithms.py tests/test_explainability.py tests/test_uncertainty.py tests/test_registry_lifecycle.py tests/test_api_calibration.py tests/test_spatial_training.py -q -p no:cacheprovider`
Ожидание: PASS. Запросы `/calibration/predict` в тестах пока шлют `kuzram_legacy 1.0.0` и проходят: проверка задачи 0 смотрит только на присланную модель, не на артефакт; их перевод на новую базу — в задаче 7. Любой другой тест, собирающий снимок вручную для обучения `kuzram_residual`/`oversize_residual`, обернуть в `with_current_base`.

- [ ] **Шаг 6: Коммит**

```bash
git add intelligence/calibration/features.py intelligence/calibration/training.py intelligence/spatial/training.py tests/calibration_fixtures.py tests/test_explainability.py tests/test_calibration_training_base.py
git commit -m "Обучение калибровок кусковатости на baseline текущей базы; старый снимок — отказ"
```

---

### Задача 7: `/calibration/predict` по базе артефакта

**Файлы:**
- Изменить: `intelligence/calibration/prediction.py:180-232` (`empirical_baseline`, `_stored_predicted`, `_compute_empirical`; удалить `CALIBRATION_BASELINE_MODEL`, `_old_base`)
- Изменить: `api/services/calibration_service.py` (`predict_calibration`; удалить `_provided_base_refusal` из задачи 0)
- Изменить: `api/routers/calibration.py:57-61`
- Изменить тест: `tests/test_fragmentation_ml_baseline.py` — удалить класс `CalibrationBaselineTests`; `tests/test_api_calibration_provided_baseline.py` — ожидания под новую базу фикстур (шаг 1)
- Создать тест: `tests/test_api_calibration_base.py`

**Интерфейсы:**
- Использует: `artifact_base`, `prediction_base`, `refusal_reason`, `compatible`, `CURRENT_BASE`, `FRAGMENTATION_RESIDUALS` (задача 2); `fragmentation_baseline`, `stored_prediction`, `baseline_settings` (задача 4).
- Отдаёт: `empirical_baseline(design, model_type, *, base=CURRENT_BASE, fallback_settings=None, fallback_source=None) -> tuple[float | None, str]`; `predict_calibration(team_id, request, *, repository=None)`.

- [ ] **Шаг 1: Падающие тесты**

Создать `tests/test_api_calibration_base.py`:

```python
"""/calibration/predict накладывает поправку только на прогноз той же базы."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from api.schemas.calibration import CalibrationPredictRequest
from api.services import calibration_service
from intelligence.calibration.persistence import new_model_id, save_model
from intelligence.calibration.training import train_from_snapshot
from intelligence.datasets.baseline import fragmentation_baseline
from tests.calibration_fixtures import synthetic_snapshot
from tests.dataset_fixtures import closed_design

TEAM_ID = "api-cal-base"


class CalibrationBaseApiTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        patcher = patch("cost.persistence.data_root", return_value=Path(self._tmp.name))
        patcher.start()
        self.addCleanup(patcher.stop)
        self.snapshot = synthetic_snapshot()

    def _artifact(self, model_type: str = "kuzram_residual", *, legacy: bool = False) -> str:
        model = train_from_snapshot(self.snapshot, model_type=model_type, model_id=new_model_id())
        if legacy:
            # Артефакт до PR 3: без базы, baseline — сохранённый прогноз.
            model.baseline_model = ""
            model.baseline_model_version = ""
            model.baseline_field = "predicted_x50_mm"
        return save_model(TEAM_ID, model).model_id

    def _predict(self, model_id: str, model_type: str = "kuzram_residual", **fields):
        payload = {"features": self.snapshot.samples[-1].features, **fields}
        return calibration_service.predict_calibration(
            TEAM_ID,
            CalibrationPredictRequest(model_type=model_type, model_id=model_id, site_id="quarry-1", **payload),
        )

    def test_old_artifact_refuses_new_prediction(self):
        result = self._predict(
            self._artifact(legacy=True), baseline=150.0, baseline_model="kuzram", baseline_model_version="2.0.0"
        )

        self.assertFalse(result.calibration_applied)
        self.assertEqual(result.calibrated, 150.0)
        self.assertIn("переобучить", result.warnings[0])
        self.assertIn("Kuz-Ram 2.0.0", result.warnings[0])

    def test_old_artifact_calibrates_old_prediction(self):
        model_id = self._artifact(legacy=True)
        for model, version in (("kuzram_legacy", "1.0.0"), ("kuzram", "1.0.0"), ("kuznetsov_legacy", "1.0.0")):
            with self.subTest(model=model):
                result = self._predict(model_id, baseline=150.0, baseline_model=model, baseline_model_version=version)

                self.assertTrue(result.calibration_applied)

    def test_new_x50_fits_any_new_model(self):
        result = self._predict(
            self._artifact(), baseline=150.0, baseline_model="swebrec", baseline_model_version="2.0.0"
        )

        self.assertTrue(result.calibration_applied)

    def test_new_oversize_needs_same_model(self):
        result = self._predict(
            self._artifact("oversize_residual"),
            "oversize_residual",
            baseline=4.0,
            baseline_model="swebrec",
            baseline_model_version="2.0.0",
        )

        self.assertFalse(result.calibration_applied)

    def test_missing_or_unknown_model_is_refused(self):
        model_id = self._artifact()
        for fields in ({}, {"baseline_model": "abc", "baseline_model_version": "2.0.0"}):
            with self.subTest(fields=fields):
                result = self._predict(model_id, baseline=150.0, **fields)

                self.assertFalse(result.calibration_applied)
                self.assertIn("Не указано", result.warnings[0])

    def test_ppv_needs_no_model(self):
        result = self._predict(self._artifact("ppv_residual"), "ppv_residual", baseline=5.0)

        self.assertTrue(result.calibration_applied)

    def test_design_baseline_for_old_artifact_uses_stored_old_prediction(self):
        design = closed_design("cal-old-design")  # сохранённый прогноз kuzram «1», x50 = 150

        result = self._predict(self._artifact(legacy=True), design=design.to_dict())

        self.assertEqual((result.baseline, result.baseline_source), (150.0, "stored_predicted"))

    def test_design_baseline_for_new_artifact_is_recomputed(self):
        design = closed_design("cal-new-design")

        result = self._predict(self._artifact(), design=design.to_dict())

        self.assertAlmostEqual(result.baseline, fragmentation_baseline(design)["baseline_x50_mm"], places=6)
        self.assertEqual(result.baseline_source, "kuzram")

    def test_design_baseline_for_new_artifact_uses_stored_new_prediction(self):
        design = closed_design("cal-new-stored")
        stored = design.blast_result.basis.predicted_fragmentation
        stored.provenance.model, stored.provenance.model_version = "swebrec", "2.0.0"

        result = self._predict(self._artifact(), design=design.to_dict())

        self.assertEqual((result.baseline, result.baseline_source), (150.0, "stored_predicted"))


if __name__ == "__main__":
    unittest.main()
```

Калибровки фикстур после задачи 6 обучены на новой базе, поэтому в `tests/test_api_calibration.py` (все пять `CalibrationPredictRequest(` с `baseline=`) и в `tests/test_explainability.py:333` заменить `baseline_model="kuzram_legacy", baseline_model_version="1.0.0"` на `baseline_model="kuzram", baseline_model_version="2.0.0"`; запрос `test_predict_does_not_mutate_design`, если он без этих полей, их получает.

В `tests/test_api_calibration_provided_baseline.py` (задача 0) калибровки фикстуры теперь новой базы: в `test_new_model_baseline_is_refused` заменить ожидания на `self.assertTrue(result.calibration_applied)` и переименовать тест в `test_new_model_baseline_is_calibrated`; `test_old_model_baseline_is_calibrated` переименовать в `test_old_model_baseline_is_refused` и ожидать `assertFalse(result.calibration_applied)` и «переобучить» в `warnings[0]`. В `tests/test_fragmentation_ml_baseline.py` удалить класс `CalibrationBaselineTests`.

- [ ] **Шаг 2: Убедиться, что тесты падают**

Запуск: `../../../.venv/bin/python -m pytest tests/test_api_calibration_base.py tests/test_api_calibration_provided_baseline.py -q -p no:cacheprovider`
Ожидание: FAIL — старый артефакт накладывается на 2.0.0 только через заглушку PR 2, новая калибровка отклоняет 2.0.0, пересчёт идёт `kuzram_legacy`.

- [ ] **Шаг 3: Baseline по базе артефакта**

В `intelligence/calibration/prediction.py` удалить `CALIBRATION_BASELINE_MODEL`, `_old_base`, `_compute_empirical` и импорт из `simulation.fragmentation.models`; добавить:

```python
from intelligence.calibration.base import (
    CURRENT_BASE,
    FRAGMENTATION_RESIDUALS,
    FragmentationBase,
    compatible,
    prediction_base,
)
from intelligence.datasets.baseline import fragmentation_baseline, stored_prediction
```

и заменить `empirical_baseline`, `_stored_predicted`:

```python
def empirical_baseline(
    design: BlastDesign,
    model_type: str,
    *,
    base: FragmentationBase = CURRENT_BASE,
    fallback_settings: Any = None,
    fallback_source: dict[str, Any] | None = None,
) -> tuple[float | None, str]:
    """Baseline для калибровки по паспорту, не меняя его.

    Кусковатость — базой артефакта: сохранённый прогноз берётся, только если
    посчитан совместимой моделью, иначе пересчёт той же функцией, что строит
    baseline снимка датасета.
    """
    model_type = normalize_model_type(model_type)
    if model_type in FRAGMENTATION_RESIDUALS:
        return _fragmentation_baseline(design, model_type, base, fallback_settings, fallback_source)
    stored = _stored_ppv(design)
    if stored is not None:
        return stored, "stored_predicted"
    computed = _compute_ppv(design)
    if computed is not None:
        return computed, MODEL_SPECS[model_type]["baseline_source"]
    return None, ""


def _fragmentation_baseline(
    design: BlastDesign,
    model_type: str,
    base: FragmentationBase,
    fallback_settings: Any,
    fallback_source: dict[str, Any] | None,
) -> tuple[float | None, str]:
    key = "x50_mm" if model_type == MODEL_KUZRAM_RESIDUAL else "oversize_pct"
    stored = stored_prediction(design)
    if stored is not None and getattr(stored, key) is not None:
        try:
            stored_base = prediction_base(stored.provenance.model, stored.provenance.model_version)
        except ValueError:
            stored_base = None
        if stored_base is not None and compatible(model_type, base, stored_base):
            return float(getattr(stored, key)), "stored_predicted"
    computed = fragmentation_baseline(
        design, model=base.model, fallback_settings=fallback_settings, fallback_source=fallback_source
    )
    value = computed[f"baseline_{key}"]
    return (float(value), base.model) if value is not None else (None, "")


def _stored_ppv(design: BlastDesign) -> float | None:
    result = design.blast_result
    if result is None or result.basis is None:
        return None
    values = [item.ppv_mm_s for item in result.basis.predicted_vibration or [] if item.ppv_mm_s is not None]
    return max(values) if values else None


def _compute_ppv(design: BlastDesign) -> float | None:
    from design.vibration import predict_design as predict_ppv_design

    try:
        payload = predict_ppv_design(design)
    except ValueError:
        return None
    values = [row.get("ppv_mm_s") for row in payload.get("predictions") or [] if row.get("ppv_mm_s") is not None]
    return max(float(item) for item in values) if values else None
```

Проверить, что других вызовов удалённых имён нет: `grep -rn "_old_base\|CALIBRATION_BASELINE_MODEL\|_compute_empirical\|_stored_predicted\|empirical_baseline(" api intelligence design tests`.

- [ ] **Шаг 4: Сервис**

В `api/services/calibration_service.py` удалить `_provided_base_refusal` и импорты задачи 0 (`_old_base`, `ModelProvenance`, `MODEL_KUZRAM_RESIDUAL`, `MODEL_OVERSIZE_RESIDUAL`); добавить:

```python
from api.services.fragmentation_settings import resolve_kuzram_settings
from cost.v2.repository import EconomicsRepository
from intelligence.calibration.base import (
    CURRENT_BASE,
    FRAGMENTATION_RESIDUALS,
    FragmentationBase,
    artifact_base,
    prediction_base,
    refusal_reason,
)
```

Перед `predict_calibration`:

```python
def _provided_base(request: CalibrationPredictRequest) -> FragmentationBase | None:
    """База присланного baseline; None — модель не указана или неизвестна."""
    model = request.baseline_model.strip()
    if not model:
        return None
    try:
        return prediction_base(model, request.baseline_model_version.strip())
    except ValueError:
        return None


def _load_requested_model(team_id: str, request: CalibrationPredictRequest, model_type: str, site_id: str):
    try:
        if request.model_id.strip():
            return load_model(team_id, request.model_id.strip())
        if request.use_production:
            if not site_id:
                raise InvalidCalibrationError("Для производственной модели нужен site_id.")
            return production_model(team_id, site_id, model_type)
    except StoreNotFound as exc:
        raise CalibrationNotFoundError(request.model_id) from exc
    except StoreImmutable as exc:
        raise ImmutableCalibrationError(str(exc)) from exc
    return None
```

Тело `predict_calibration` (сигнатура `def predict_calibration(team_id: str, request: CalibrationPredictRequest, *, repository: EconomicsRepository | None = None)`):

```python
    try:
        model_type = normalize_model_type(request.model_type)
    except ValueError as exc:
        raise InvalidCalibrationError(str(exc)) from exc

    design = _design_from_request(request)
    site_id = request.site_id.strip()
    if not site_id and design is not None:
        site_id = str((request.features or {}).get("SITE", {}).get("site_id") or "")

    model = _load_requested_model(team_id, request, model_type, site_id)
    fragmentation = model_type in FRAGMENTATION_RESIDUALS
    # База, которой считается baseline: артефакта, а без артефакта — текущая.
    base = artifact_base(model.baseline_model, model.baseline_model_version) if model is not None else CURRENT_BASE

    baseline = request.baseline
    baseline_source = "provided" if baseline is not None else ""
    refusal = ""
    if baseline is not None:
        if model is not None:
            refusal = refusal_reason(model_type, base, _provided_base(request))
    elif design is not None:
        fallback_settings, fallback_source = None, None
        if fragmentation and not base.legacy:
            resolved = resolve_kuzram_settings(
                explicit=None, work_object_name="", organization_id=team_id, repository=repository
            )
            fallback_settings, fallback_source = resolved.settings, resolved.source_payload()
        baseline, baseline_source = empirical_baseline(
            design,
            model_type,
            base=base,
            fallback_settings=fallback_settings,
            fallback_source=fallback_source,
        )
    if baseline is None:
        raise InvalidCalibrationError(
            "Для прогноза калибровки нужен baseline (Kuz-Ram / PPV) или паспорт с эмпирическим прогнозом."
        )

    features: dict[str, Any] = dict(request.features or {})
    if not features and design is not None:
        features = features_from_design(design, site_id=site_id or "unknown")

    if model is None:
        reason = "Нет выбранной модели калибровки."
        if request.use_production:
            reason = f"Нет production-модели «{model_type}» для площадки «{site_id}»."
        payload = baseline_without_model(
            baseline=float(baseline),
            model_type=model_type,
            site_id=site_id,
            baseline_source=baseline_source,
            reason=reason,
        )
        return _predict_schema(payload.to_dict())

    if site_id and model.site_id != site_id:
        raise InvalidCalibrationError("site_id запроса не совпадает с площадкой модели.")
    if model.model_type != model_type:
        raise InvalidCalibrationError("Тип модели не совпадает с запросом прогноза.")
    if refusal:
        payload = baseline_without_model(
            baseline=float(baseline),
            model_type=model_type,
            site_id=site_id,
            baseline_source=baseline_source,
            reason=refusal,
        )
        return _predict_schema(payload.to_dict())

    try:
        prediction = apply_residual(
            model,
            features=features,
            baseline=float(baseline),
            baseline_source=baseline_source,
        )
    except ValueError as exc:
        raise InvalidCalibrationError(str(exc)) from exc
    payload = prediction.to_dict()
    payload["modifies_design"] = False
    return _predict_schema(payload)
```

В `api/routers/calibration.py`:

```python
from api.services.economics_service import get_economics_repository
from cost.v2.repository import EconomicsRepository
```

```python
@router.post("/predict", response_model=CalibrationPredictResponse)
def predict_with_calibration(
    request: CalibrationPredictRequest,
    session: dict = Depends(require_internal_access),
    repository: EconomicsRepository = Depends(get_economics_repository),
) -> CalibrationPredictResponse:
    return calibration_service.predict_calibration(session["org"], request, repository=repository)
```

- [ ] **Шаг 5: Тесты проходят**

Запуск: `../../../.venv/bin/python -m pytest tests/test_api_calibration_base.py tests/test_api_calibration_provided_baseline.py tests/test_api_calibration.py tests/test_explainability.py tests/test_fragmentation_ml_baseline.py tests/test_api_feature_flags.py -q -p no:cacheprovider`
Ожидание: PASS.

- [ ] **Шаг 6: Коммит**

```bash
git add intelligence/calibration/prediction.py api/services/calibration_service.py api/routers/calibration.py tests/test_api_calibration_base.py tests/test_api_calibration_provided_baseline.py tests/test_api_calibration.py tests/test_explainability.py tests/test_fragmentation_ml_baseline.py
git commit -m "Калибровка: baseline и проверка по базе артефакта вместо заглушки PR 2"
```

---

### Задача 8: сценарии — проверка базы по артефакту

**Файлы:**
- Изменить: `api/services/scenario_service.py:160-242` (второй блок `_apply_ml_overlays`)
- Изменить тест: `tests/test_fragmentation_ml_baseline.py` — класс `ScenarioResidualGuardTests`

**Интерфейсы:**
- Использует: `artifact_base`, `prediction_base`, `refusal_reason`, `FRAGMENTATION_RESIDUALS` (задача 2); `FRAGMENTATION_MODELS`, `resolve_model` (движок).

- [ ] **Шаг 1: Падающие тесты**

Заменить класс `ScenarioResidualGuardTests` в `tests/test_fragmentation_ml_baseline.py` (и docstring модуля — на «Сценарии накладывают калибровки только на прогноз той же базы»):

```python
class ScenarioResidualGuardTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        patcher = patch("cost.persistence.data_root", return_value=Path(self._tmp.name))
        patcher.start()
        self.addCleanup(patcher.stop)

    def _run(self, fragmentation_model: str, models: dict, *, load_error: str = ""):
        outcomes = ScenarioOutcomes(
            x50_mm=200.0,
            x50_engineering_mm=200.0,
            oversize_pct=5.0,
            oversize_engineering_pct=5.0,
            ppv_mm_s=4.0,
            ppv_engineering_mm_s=4.0,
        )
        params = ScenarioParams(
            fragmentation_model=fragmentation_model,
            calibration_model_ids={model_type: model_type for model_type in models},
        )

        def load(team_id, model_id):
            if model_id == load_error:
                raise RuntimeError("файл повреждён")
            base = models[model_id]
            return SimpleNamespace(model_type=model_id, baseline_model=base[0], baseline_model_version=base[1])

        def apply(model, *, features, baseline, baseline_source):
            return SimpleNamespace(calibrated=baseline + 1.0)

        with patch("intelligence.calibration.persistence.load_model", side_effect=load), patch(
            "intelligence.calibration.prediction.apply_residual", side_effect=apply
        ):
            scenario_service._apply_ml_overlays("team-ml", charged_design("ml-guard"), params, outcomes)
        return outcomes

    OLD = ("", "")
    NEW = ("kuzram", "2.0.0")

    def test_old_calibration_skips_new_model(self):
        outcomes = self._run("kuzram", {"kuzram_residual": self.OLD})

        self.assertEqual(outcomes.x50_mm, 200.0)
        self.assertTrue(any("переобучить" in item for item in outcomes.warnings))

    def test_old_calibration_keeps_legacy_model(self):
        outcomes = self._run("kuzram_legacy", {"kuzram_residual": self.OLD})

        self.assertEqual(outcomes.x50_mm, 201.0)

    def test_new_x50_calibration_fits_swebrec(self):
        outcomes = self._run("swebrec", {"kuzram_residual": self.NEW})

        self.assertEqual(outcomes.x50_mm, 201.0)

    def test_new_oversize_calibration_needs_same_model(self):
        outcomes = self._run("swebrec", {"oversize_residual": self.NEW})

        self.assertEqual(outcomes.oversize_pct, 5.0)
        self.assertTrue(any("переобучить" in item for item in outcomes.warnings))

    def test_broken_fragmentation_calibration_keeps_ppv(self):
        outcomes = self._run(
            "kuzram", {"oversize_residual": self.NEW, "ppv_residual": self.OLD}, load_error="oversize_residual"
        )

        self.assertEqual(outcomes.ppv_mm_s, 5.0)
        self.assertTrue(any("oversize_residual" in item for item in outcomes.warnings))
```

Если у `ScenarioOutcomes` нет поля `ppv_engineering_mm_s` с таким именем, взять фактическое из `mapping` в `_apply_ml_overlays`. Импорты модуля, которые после удаления классов задач 4 и 7 и замены этого класса не используются (`calibration_prediction`, `fragmentation_engine`, `ModelProvenance`, `MODEL_KUZRAM_RESIDUAL`), удалить.

- [ ] **Шаг 2: Убедиться, что тесты падают**

Запуск: `../../../.venv/bin/python -m pytest tests/test_fragmentation_ml_baseline.py -q -p no:cacheprovider`
Ожидание: FAIL — новая калибровка к `swebrec` не применяется (заглушка PR 2), сбой загрузки снимает PPV.

- [ ] **Шаг 3: Реализация**

В `api/services/scenario_service.py` заменить всё от комментария «Поправки кусковатости обучены на Kuz-Ram 1.0.0…» до строки `outcomes.ml_overlay_applied = applied` (не включая её) на:

```python
    from intelligence.calibration.base import (
        FRAGMENTATION_RESIDUALS,
        artifact_base,
        prediction_base,
        refusal_reason,
    )
    from simulation.fragmentation.engine import FRAGMENTATION_MODELS, resolve_model

    # База прогноза сценария: калибровка кусковатости накладывается, только
    # если обучена на ней. Неизвестное имя модели отклонит движок; здесь
    # поправки кусковатости тогда просто не накладываются.
    try:
        model_id = resolve_model(params.fragmentation_model)
        scenario_base = prediction_base(model_id, str(FRAGMENTATION_MODELS[model_id]["version"]))
    except ValueError:
        scenario_base = None

    try:
        from intelligence.calibration.persistence import load_model, production_model
        from intelligence.calibration.prediction import apply_residual, features_from_design
        from intelligence.calibration.types import (
            MODEL_KUZRAM_RESIDUAL,
            MODEL_OVERSIZE_RESIDUAL,
            MODEL_PPV_RESIDUAL,
        )

        features = features_from_design(overlay, site_id=site_id or "unknown")
        mapping = (
            (MODEL_KUZRAM_RESIDUAL, "x50_mm", "x50_engineering_mm"),
            (MODEL_OVERSIZE_RESIDUAL, "oversize_pct", "oversize_engineering_pct"),
            (MODEL_PPV_RESIDUAL, "ppv_mm_s", "ppv_engineering_mm_s"),
        )
        for model_type, field, baseline_field in mapping:
            model_id = str(params.calibration_model_ids.get(model_type) or "").strip()
            fragmentation = model_type in FRAGMENTATION_RESIDUALS
            if fragmentation and scenario_base is None:
                continue
            # Сбой загрузки одной калибровки снимает только её.
            try:
                model = None
                if model_id:
                    model = load_model(team_id, model_id)
                elif params.use_production_overlays and site_id:
                    model = production_model(team_id, site_id, model_type)
            except Exception as exc:  # noqa: BLE001 — любой сбой хранилища
                outcomes.warnings.append(f"Калибровка «{model_type}» пропущена: {exc}")
                continue
            if model is None:
                continue
            if fragmentation:
                reason = refusal_reason(
                    model_type,
                    artifact_base(model.baseline_model, model.baseline_model_version),
                    scenario_base,
                )
                if reason:
                    if reason not in outcomes.warnings:
                        outcomes.warnings.append(reason)
                    continue
            baseline = getattr(outcomes, baseline_field)
            if baseline is None:
                continue
            prediction = apply_residual(
                model,
                features=features,
                baseline=float(baseline),
                baseline_source="engineering",
            )
            calibrated = float(prediction.calibrated)
            setattr(outcomes, field, calibrated)
            applied = True
            if field in {"x50_mm", "x80_mm"}:
                outcomes.fragmentation_source = SOURCE_CALIBRATION
            if field == "ppv_mm_s":
                outcomes.vibration_source = SOURCE_CALIBRATION
    except Exception as exc:
        outcomes.warnings.append(f"Калибровочный оверлей пропущен: {exc}")

```

Проверить, что `is_legacy_model` в файле больше не используется: `grep -n "is_legacy_model" api/services/scenario_service.py` — пусто.

- [ ] **Шаг 4: Тесты проходят**

Запуск: `../../../.venv/bin/python -m pytest tests/test_fragmentation_ml_baseline.py tests/test_api_scenarios.py -q -p no:cacheprovider` и `../../../.venv/bin/python -m pytest tests -q -p no:cacheprovider -k "scenario or pareto or recommend"`
Ожидание: PASS.

- [ ] **Шаг 5: Коммит**

```bash
git add api/services/scenario_service.py tests/test_fragmentation_ml_baseline.py
git commit -m "Сценарии: калибровка кусковатости сверяется с базой модели сценария"
```

---

### Задача 9: дрейф — baseline строки по базе артефакта

**Файлы:**
- Изменить: `intelligence/drift/scoring.py:77-107` (`_score_calibration`)
- Создать тест: `tests/test_drift_calibration_base.py`

**Интерфейсы:**
- Использует: `artifact_base`, `sample_baseline`, `FRAGMENTATION_RESIDUALS` (задача 2).

- [ ] **Шаг 1: Падающий тест**

Создать `tests/test_drift_calibration_base.py`:

```python
"""Дрейф калибровки считается только на строках той же базы, что и артефакт."""
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from intelligence.drift.scoring import _score_calibration

KEY = "prediction.calibrated_x50_mm"
OLD_ROW = {"x50_mm": 160.0, "predicted_x50_mm": 150.0}
NEW_STORED_ROW = {"x50_mm": 160.0, "predicted_x50_mm": 150.0, "predicted_model": "kuzram", "predicted_model_version": "2.0.0"}
NEW_ROW = {**NEW_STORED_ROW, "baseline_x50_mm": 140.0, "baseline_model": "kuzram", "baseline_model_version": "2.0.0"}


def _samples(*rows):
    return [SimpleNamespace(targets={"FRAGMENTATION": row}, features={}) for row in rows]


def _score(base: tuple[str, str], *rows):
    model = SimpleNamespace(
        model_type="kuzram_residual", baseline_model=base[0], baseline_model_version=base[1]
    )
    with patch("intelligence.calibration.persistence.load_model", return_value=model), patch(
        "intelligence.calibration.prediction.apply_residual",
        side_effect=lambda model, *, features, baseline, baseline_source: SimpleNamespace(calibrated=baseline),
    ):
        return _score_calibration("team", "cal", _samples(*rows)).get(KEY, [])


class DriftBaseTests(unittest.TestCase):
    def test_old_artifact_scores_only_old_rows(self):
        self.assertEqual(_score(("", ""), OLD_ROW, NEW_STORED_ROW), [150.0])

    def test_new_artifact_scores_current_baseline(self):
        self.assertEqual(_score(("kuzram", "2.0.0"), OLD_ROW, NEW_ROW), [140.0])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Шаг 2: Убедиться, что тест падает**

Запуск: `../../../.venv/bin/python -m pytest tests/test_drift_calibration_base.py -q -p no:cacheprovider`
Ожидание: FAIL — дрейф берёт `predicted_x50_mm` всех строк.

- [ ] **Шаг 3: Реализация**

В `intelligence/drift/scoring.py`, `_score_calibration`:

```python
    from intelligence.calibration.base import FRAGMENTATION_RESIDUALS, artifact_base, sample_baseline
    from intelligence.calibration.persistence import load_model
    from intelligence.calibration.prediction import apply_residual
    from intelligence.calibration.types import MODEL_SPECS, normalize_model_type

    model = load_model(team_id, model_id)
    model_type = normalize_model_type(model.model_type)
    spec = MODEL_SPECS[model_type]
    group = spec["target_group"]
    baseline_field = spec["baseline_field"]
    base = (
        artifact_base(model.baseline_model, model.baseline_model_version)
        if model_type in FRAGMENTATION_RESIDUALS
        else None
    )
    unit = spec.get("unit") or ""
    buckets: dict[str, list[float]] = {}
    key = f"prediction.calibrated_{spec['measured_field']}"
    for sample in samples:
        payload = (sample.targets or {}).get(group) or {}
        # Кусковатость — только строки той же базы, что и артефакт.
        baseline = sample_baseline(payload, model_type, base) if base is not None else payload.get(baseline_field)
        if baseline is None:
            continue
```

(остальное тело без изменений).

- [ ] **Шаг 4: Тесты проходят**

Запуск: `../../../.venv/bin/python -m pytest tests/test_drift_calibration_base.py tests/test_drift_engine.py tests/test_drift_isolation.py tests/test_api_drift.py -q -p no:cacheprovider`
Ожидание: PASS.

- [ ] **Шаг 5: Коммит**

```bash
git add intelligence/drift/scoring.py tests/test_drift_calibration_base.py
git commit -m "Дрейф калибровки: строки снимка сверяются с базой артефакта"
```

---

### Задача 10: пространственный прогноз — физика базой артефакта

**Файлы:**
- Изменить: `intelligence/spatial/prediction.py:73-138` (`apply_model`)
- Изменить: `intelligence/spatial/types.py:462-520` (`SpatialOverlay`: поля и `to_dict`)
- Изменить: `api/schemas/spatial.py:139-160` (`SpatialPredictResponse`)
- Изменить: `api/services/spatial_service.py:162-200` (`predict_spatial`), `api/routers/spatial.py:66-72`
- Создать тест: `tests/test_spatial_base.py`

**Интерфейсы:**
- Использует: `artifact_base`, `CURRENT_BASE`, `spatial_base_label` (задача 2); `extract_hole_observations(..., physics_model, settings, settings_source)` (задача 4); `baseline_settings` (задача 4).
- Отдаёт: `apply_model(design, *, model=None, site_id="", block=None, neighbor_k=None, settings=None, settings_source=None)`; поля ответа `physics_model`, `physics_model_version`, `base_label`; `predict_spatial(team_id, request, *, repository=None)`.

- [ ] **Шаг 1: Падающий тест**

Создать `tests/test_spatial_base.py`:

```python
"""Физика пространственного прогноза считается базой своей модели."""
import unittest
from unittest.mock import patch

from intelligence.spatial.prediction import apply_model
from intelligence.spatial.training import train_from_snapshot
from simulation.fragmentation import engine as fragmentation_engine
from tests.spatial_fixtures import multi_hole_design, synthetic_spatial_snapshot


def _physics_models(model):
    with patch.object(fragmentation_engine, "predict_region", wraps=fragmentation_engine.predict_region) as spy:
        overlay = apply_model(multi_hole_design(), model=model)
    return {call.kwargs.get("model") for call in spy.call_args_list}, overlay


class SpatialBaseTests(unittest.TestCase):
    def test_without_model_current_base(self):
        models, overlay = _physics_models(None)

        self.assertEqual(models, {"kuzram"})
        self.assertEqual((overlay.physics_model, overlay.physics_model_version), ("kuzram", "2.0.0"))
        self.assertEqual(overlay.base_label, "")

    def test_old_model_keeps_old_physics(self):
        model = train_from_snapshot(synthetic_spatial_snapshot(), team_id="sp")

        models, overlay = _physics_models(model)

        self.assertEqual(models, {"kuzram_legacy"})
        self.assertIn("Старая база", overlay.base_label)

    def test_new_model_current_physics(self):
        model = train_from_snapshot(synthetic_spatial_snapshot(), team_id="sp")
        model.baseline_model, model.baseline_model_version = "kuzram", "2.0.0"

        models, overlay = _physics_models(model)

        self.assertEqual(models, {"kuzram"})
        self.assertEqual(overlay.base_label, "База: Kuz-Ram 2.0.0")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Шаг 2: Убедиться, что тест падает**

Запуск: `../../../.venv/bin/python -m pytest tests/test_spatial_base.py -q -p no:cacheprovider`
Ожидание: FAIL — у `SpatialOverlay` нет `physics_model`, старая модель считает физику `kuzram`.

- [ ] **Шаг 3: Реализация**

В `intelligence/spatial/types.py`, `SpatialOverlay`, после `data_roles`:

```python
    # Модель, которой посчитана физика скважин, и подпись базы модели.
    physics_model: str = ""
    physics_model_version: str = ""
    base_label: str = ""
```

и в `to_dict` — `"physics_model": self.physics_model, "physics_model_version": self.physics_model_version, "base_label": self.base_label,`. В `api/schemas/spatial.py`, `SpatialPredictResponse`, после `data_roles`: `physics_model: str = ""`, `physics_model_version: str = ""`, `base_label: str = ""`.

В `intelligence/spatial/prediction.py`:

```python
from intelligence.calibration.base import CURRENT_BASE, artifact_base, spatial_base_label
```

`apply_model` получает `settings: Any = None, settings_source: Mapping[str, Any] | None = None`; перед `observations = extract_hole_observations(`:

```python
    # Физика — базой, на которой модель обучена; без модели — текущей.
    base = artifact_base(model.baseline_model, model.baseline_model_version) if model is not None else CURRENT_BASE
```

в вызов `extract_hole_observations(...)` добавить `physics_model=base.model, settings=settings, settings_source=settings_source,`; в `SpatialOverlay(...)` добавить:

```python
        physics_model=base.model,
        physics_model_version=base.model_version,
        base_label=spatial_base_label(model.baseline_model, model.baseline_model_version) if model else "",
```

В `api/services/spatial_service.py`:

```python
from api.services.fragmentation_settings import resolve_kuzram_settings
from cost.v2.repository import EconomicsRepository
from intelligence.calibration.base import artifact_base
from intelligence.datasets.baseline import baseline_settings
```

`predict_spatial(team_id: str, request: SpatialPredictRequest, *, repository: EconomicsRepository | None = None)`; перед `overlay = apply_model(`:

```python
    settings, settings_source = None, None
    legacy = model is not None and artifact_base(model.baseline_model, model.baseline_model_version).legacy
    if not legacy:
        # Настройки модели — снимок сохранённого прогноза паспорта, иначе
        # активный объект работ организации, иначе умолчания.
        resolved = resolve_kuzram_settings(
            explicit=None, work_object_name="", organization_id=team_id, repository=repository
        )
        settings, settings_source = baseline_settings(design, resolved.settings, resolved.source_payload())
```

и в `apply_model(...)` — `settings=settings, settings_source=settings_source,`.

В `api/routers/spatial.py`, `predict_spatial`: добавить `repository: EconomicsRepository = Depends(get_economics_repository)` и передать `repository=repository` (импорты — как в задаче 5).

- [ ] **Шаг 4: Тесты проходят**

Запуск: `../../../.venv/bin/python -m pytest tests/test_spatial_base.py tests/test_spatial_prediction.py tests/test_api_spatial.py tests/test_spatial_isolation.py tests/test_spatial_residuals.py -q -p no:cacheprovider`
Ожидание: PASS.

- [ ] **Шаг 5: Коммит**

```bash
git add intelligence/spatial/prediction.py intelligence/spatial/types.py api/schemas/spatial.py api/services/spatial_service.py api/routers/spatial.py tests/test_spatial_base.py
git commit -m "Пространственный прогноз: физика скважин считается базой своей модели"
```

---

### Задача 11: фронт — подписи базы

**Файлы:**
- Изменить: `frontend/src/types/design.ts:2230-2260` (`CalibrationModel`, `CalibrationSummary`), типы пространственной модели и ответа (`grep -n "SpatialSummary = \|SpatialModel = \|SpatialPredictResponse = " frontend/src/types/design.ts`)
- Изменить: `frontend/src/pages/design/CalibrationPanel.tsx:95-115`, `frontend/src/pages/design/SpatialPanel.tsx:60-80`
- Создать тест: `frontend/src/pages/design/CalibrationPanel.test.tsx`

**Интерфейсы:**
- Использует: поля API `baseline_model`, `baseline_model_version`, `base_label` (задачи 3, 10).

- [ ] **Шаг 1: Падающий тест**

Создать `frontend/src/pages/design/CalibrationPanel.test.tsx`:

```tsx
// @vitest-environment jsdom
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import type { CalibrationModel, CalibrationSummary } from "../../types/design";
import { CalibrationPanel } from "./CalibrationPanel";

afterEach(cleanup);

const summary = {
  model_id: "cal-1",
  site_id: "quarry-1",
  model_type: "kuzram_residual",
  model_version: 3,
  training_dataset_id: "snap",
  training_dataset_version: 2,
  feature_schema_version: "1",
  training_date: "",
  metrics: {},
  status: "production",
  algorithm: "random_forest",
  sample_count: 8,
  baseline_model: "",
  baseline_model_version: "",
  base_label: "Старая база (Kuz-Ram (старая) 1.0.0) — только для старых моделей",
} as CalibrationSummary;

const noop = () => undefined;

function renderPanel(selected: CalibrationModel | null) {
  render(
    <CalibrationPanel
      siteId="quarry-1"
      datasetId="snap"
      datasetLabel="снимок v2"
      modelType="kuzram_residual"
      onModelTypeChange={noop}
      algorithm="random_forest"
      onAlgorithmChange={noop}
      algorithms={[]}
      models={[summary]}
      selected={selected}
      overlay={null}
      busy={false}
      onRefresh={noop}
      onTrain={noop}
      onOpen={noop}
      onMarkProduction={noop}
      onApplyOverlay={noop}
    />,
  );
}

describe("CalibrationPanel — база калибровки", () => {
  it("в списке видна старая база", () => {
    renderPanel(null);
    expect(screen.getByText(/Старая база/)).toBeTruthy();
  });

  it("в карточке — подпись базы", () => {
    const selected = { ...summary, base_label: "База: Kuz-Ram 2.0.0" } as unknown as CalibrationModel;
    renderPanel(selected);
    expect(screen.getByText("База: Kuz-Ram 2.0.0")).toBeTruthy();
  });
});
```

Если у `CalibrationPanel` другие обязательные props (сверить с сигнатурой в файле), дописать их заглушками тех же типов.

- [ ] **Шаг 2: Убедиться, что тест падает**

Запуск: `npm --prefix frontend test -- src/pages/design/CalibrationPanel.test.tsx`
Ожидание: FAIL — подписи базы на панели нет (и ошибка типов `base_label`).

- [ ] **Шаг 3: Типы и панели**

В `frontend/src/types/design.ts` в `CalibrationModel` и `CalibrationSummary`, а также в типах пространственной модели и её сводки:

```ts
  baseline_model: string;
  baseline_model_version: string;
  /** Подпись базы с сервера: «База: Kuz-Ram 2.0.0» или «Старая база …». */
  base_label: string;
```

в типе ответа пространственного прогноза:

```ts
  physics_model: string;
  physics_model_version: string;
  base_label: string;
```

В `CalibrationPanel.tsx`, в элементе списка после `<small>{statusLabel(item.status)} · …</small>`:

```tsx
                  {item.base_label && <small className="frag-settings">{item.base_label}</small>}
```

в карточке после `<small>Схема признаков: …</small>`:

```tsx
            {selected.base_label && <small className="frag-settings">{selected.base_label}</small>}
```

В `SpatialPanel.tsx` — то же для элемента списка (`item.base_label`) и карточки (`selected.base_label`), тем же классом.

- [ ] **Шаг 4: Тесты и сборка**

Запуск: `npm --prefix frontend test -- src/pages/design` и `npm --prefix frontend run build`
Ожидание: PASS, сборка без ошибок типов. Если фикстуры других тестов строят эти типы литералом и сборка падает на отсутствии новых полей, дописать поля в фикстуры.

- [ ] **Шаг 5: Коммит**

```bash
git add frontend/src/types/design.ts frontend/src/pages/design/CalibrationPanel.tsx frontend/src/pages/design/SpatialPanel.tsx frontend/src/pages/design/CalibrationPanel.test.tsx
git commit -m "Панели калибровок и пространственной модели показывают базу"
```

---

### Задача 12: документация

**Файлы:**
- Изменить: `Docs/KUZRAM_MODEL.md` (абзац «**ML.**» в разделе «Проектирование: движок кусковатости»)

- [ ] **Шаг 1: Текст**

Заменить абзац, начинающийся «**ML.** До PR 3 калибровки…», на:

```markdown
**ML.** Калибровка кусковатости — поправка к конкретной формуле, поэтому
артефакт хранит базу: модель и версию baseline, на котором обучен
(`baseline_model`, `baseline_model_version`; пусто — старая база Kuz-Ram
1.0.0). Совместимость решает `intelligence/calibration/base.py`: поправка
x50 подходит к любой модели той же базы, поправка негабарита — только к той
же модели. Несовместимая калибровка не применяется, ответ несёт
предупреждение «нужно переобучить»; так работают `/calibration/predict`,
сценарии и дрейф. Старые калибровки по-прежнему применяются к моделям
`*_legacy`.

Снимок датасета хранит сохранённый прогноз взрыва как есть (с моделью и
версией) и рядом baseline текущей базы (`baseline_*`), пересчитанный при
сборке: порода и ВВ — из входных величин сохранённого прогноза, настройки —
его снимок, иначе активный объект работ, иначе умолчания
(`intelligence/datasets/baseline.py`). Калибровки кусковатости учатся на
`baseline_*`; снимок, собранный до перехода, для них не годится — нужно
собрать новый. Пространственная модель считает физику скважин базой, на
которой обучена; без модели — текущей.

Прогноз модели `*_legacy` или версии ниже 2.0.0 в панели «Кусковатость» и в
паспорте подписан «Старая модель».
```

- [ ] **Шаг 2: Коммит**

```bash
git add Docs/KUZRAM_MODEL.md
git commit -m "Документация: калибровки ML на базе модели кусковатости"
```

---

### Задача 13: сдача PR (координатор, не субагент)

- [ ] **Шаг 1: Полный прогон**

Запуск: `../../../.venv/bin/python -m pytest tests -q -p no:cacheprovider`, `npm --prefix frontend test`, `npm --prefix frontend run build`
Ожидание: всё зелёное; число тестов записать для описания PR. Golden-файлы (`git diff --stat origin/feat/fragmentation-cunningham-engine -- tests/fixtures`) не изменены.

- [ ] **Шаг 2: Ревью**

/code-review по ветке; находки исправить отдельными коммитами.

- [ ] **Шаг 3: PR**

Если #101 уже слит — перебазировать ветку на `origin/main` и прогнать шаг 1 заново. Запушить `feat/fragmentation-cunningham-calibration`, открыть PR в `main` с описанием: что меняется, отступления от спеки (раздел выше), правки ожиданий существующих тестов, напоминание владельцу о переобучении калибровок по площадкам после выката. Не сливать.

- [ ] **Шаг 4: Codex**

Ревью Codex по правилам памяти `review-before-merge`: после каждого исправления — новый раунд, до 👍 без замечаний.

## Что дальше

После выката — переобучение калибровок кусковатости и пространственных моделей по площадкам (владелец): собрать новый снимок, обучить, перевести в production. Числа старых калибровок в `*_legacy` остаются доступными до их вывода из эксплуатации.
