"""Fragmentation prediction for a spatial blast design (phase BDX-006).

Three empirical models share the same Kuznetsov median and then differ in
how they turn that median into a size-distribution curve:

* ``kuznetsov`` — Kuznetsov x50 + Rosin–Rammler with a default n
* ``kuzram`` — Kuznetsov x50 + Cunningham n + Rosin–Rammler (Kuz-Ram)
* ``swebrec`` — Kuznetsov x50 + Swebrec function (Ouchterlony)

Predictions always carry role ``predicted``. Measured sieve data is a
separate type and is never written by this package (BDX-010).
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
