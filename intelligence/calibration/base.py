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
    version_major,  # noqa: F401 — реэкспорт: присланную версию сервис проверяет тем же правилом
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
    if (
        model_type == MODEL_OVERSIZE_RESIDUAL
        and artifact.legacy == prediction.legacy
        and artifact.model_version == prediction.model_version
    ):
        # База та же, другая только кривая: негабарит учится всегда на
        # kuzram, переобучение под другую модель не поможет.
        return (
            f"Калибровка негабарита обучена на кривой «{artifact.label()}» "
            f"и к прогнозу «{prediction.label()}» не применяется."
        )
    return (
        f"Калибровка обучена на прогнозах «{artifact.label()}» и к прогнозу «{prediction.label()}» "
        "не применяется — её нужно переобучить."
    )


def sample_baseline(group: Mapping[str, Any], model_type: str, artifact: FragmentationBase) -> float | None:
    """Baseline строки снимка, совместимый с базой артефакта; иначе None.

    Сначала baseline текущей базы (строки снимков PR 3), затем сохранённый
    прогноз; строка старого снимка без модели прогноза — старая база.
    baseline_* без читаемой версии — повреждённая строка: её пропускают, а
    не считают старой базой (пустая версия старой базой записана только у
    сохранённых прогнозов до PR 2).
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
        if key.startswith("baseline_") and version_major(str(version or "")) is None:
            continue
        try:
            base = prediction_base(str(model), str(version or ""))
        except ValueError:
            continue
        if not compatible(model_type, artifact, base):
            continue
        try:
            return float(value)
        except (TypeError, ValueError):
            # Нечисловое значение снимает только этого кандидата, а не канал дрейфа.
            continue
    return None


def raw_base_name(model: str, version: str) -> str:
    """Модель и версия неизвестной базы как записаны в файле: «<модель> <версия>».

    Реестр такую модель не знает, подписать её по-человечески нечем.
    """
    return f"{str(model or '').strip()} {str(version or '').strip()}".strip()


def _label(baseline_model: str, baseline_model_version: str, legacy_note: str) -> str:
    """Подпись базы артефакта; неизвестная модель в файле не роняет список и карточку."""
    try:
        base = artifact_base(baseline_model, baseline_model_version)
    except ValueError:
        return f"База: {raw_base_name(baseline_model, baseline_model_version)} — модель неизвестна"
    if base.legacy:
        return f"Старая база ({base.label()}) — {legacy_note}"
    return f"База: {base.label()}"


def base_label(model_type: str, baseline_model: str, baseline_model_version: str) -> str:
    """Подпись базы для списка и карточки калибровки; у PPV — пусто."""
    if model_type not in FRAGMENTATION_RESIDUALS:
        return ""
    return _label(baseline_model, baseline_model_version, "только для старых моделей")


def spatial_base_label(baseline_model: str, baseline_model_version: str) -> str:
    """Подпись базы пространственной модели: её физика считается этой моделью."""
    return _label(baseline_model, baseline_model_version, "физика считается старой моделью")
