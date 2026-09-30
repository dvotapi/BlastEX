"""Общая база моделей кусковатости «Проектирования»: A, x50 и n по Каннингему.

Все три модели движка (kuznetsov, kuzram, swebrec) берут фактор породы,
средний кусок и индекс равномерности отсюда, а этот модуль — из
cunningham.predict_point, той же функции, что считает лист «Расчёт». Модели
различаются только кривой распределения. Здесь нет ни одной формулы: только
перевод входных величин региона в аргументы predict_point.
"""
from __future__ import annotations

from collections.abc import Mapping
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


def settings_source_label(model: str, snapshot: Mapping[str, Any] | None) -> str:
    """Подпись «откуда настройки модели» для панели «Кусковатость» и паспорта.

    Единственное место с этими словами: фронт показывает settings_label из
    ответа API. Старый паспорт без снимка настроек строки не получает.
    """
    if model.endswith("_legacy"):
        return "Старая модель: настройки объекта не применяются"
    if not snapshot:
        return ""
    source = snapshot.get("source")
    name = str(snapshot.get("work_object_name") or "")
    if source == SETTINGS_SOURCE_REQUEST:
        return "Настройки модели: заданы в запросе"
    if source == SETTINGS_SOURCE_WORK_OBJECT:
        return f"Настройки модели: объект работ «{name}»"
    if name:
        if snapshot.get("warnings"):
            return f"Настройки модели: умолчания — настройки объекта «{name}» не прочитаны"
        return f"Настройки модели: умолчания — у объекта «{name}» они не сохранены"
    return "Настройки модели: умолчания"


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
