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

from simulation.fragmentation.engine import (
    FRAGMENTATION_MODELS,
    predict_design,
    predict_region,
)
from simulation.fragmentation.maps import FRAGMENTATION_MAP_METRICS, fragmentation_maps
from simulation.fragmentation.models import (
    ROLE_DESIGNED,
    ROLE_MEASURED,
    ROLE_PREDICTED,
    Calibration,
    DesignedFragmentationTarget,
    DistributionPoint,
    FragmentationInputs,
    MeasuredFragmentation,
    ModelProvenance,
    PredictedFragmentation,
)

__all__ = [
    "FRAGMENTATION_MODELS",
    "FRAGMENTATION_MAP_METRICS",
    "ROLE_DESIGNED",
    "ROLE_MEASURED",
    "ROLE_PREDICTED",
    "Calibration",
    "DesignedFragmentationTarget",
    "DistributionPoint",
    "FragmentationInputs",
    "MeasuredFragmentation",
    "ModelProvenance",
    "PredictedFragmentation",
    "fragmentation_maps",
    "predict_design",
    "predict_region",
]
