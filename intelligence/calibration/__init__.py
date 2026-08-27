"""BDX-012 site-specific residual correction of engineering models.

Hybrid path: physics/empirical baseline → ML residual → overlay recommendation.
Training reads only immutable snapshots from ``intelligence.datasets``.
"""
from intelligence.calibration.algorithms import available_algorithms, get_algorithm
from intelligence.calibration.features import residual_table, residual_value
from intelligence.calibration.persistence import (
    CalibrationNotFoundError,
    ImmutableCalibrationError,
    list_models,
    load_model,
    save_model,
    set_status,
)
from intelligence.calibration.prediction import apply_residual, baseline_without_model
from intelligence.calibration.training import train_from_snapshot
from intelligence.calibration.types import (
    MODEL_KUZRAM_RESIDUAL,
    MODEL_OVERSIZE_RESIDUAL,
    MODEL_PPV_RESIDUAL,
    MODEL_TYPES,
    STATUS_CANDIDATE,
    STATUS_PRODUCTION,
    CalibrationModel,
    CalibrationPrediction,
)

__all__ = [
    "CalibrationModel",
    "CalibrationNotFoundError",
    "CalibrationPrediction",
    "ImmutableCalibrationError",
    "MODEL_KUZRAM_RESIDUAL",
    "MODEL_OVERSIZE_RESIDUAL",
    "MODEL_PPV_RESIDUAL",
    "MODEL_TYPES",
    "STATUS_CANDIDATE",
    "STATUS_PRODUCTION",
    "apply_residual",
    "available_algorithms",
    "baseline_without_model",
    "get_algorithm",
    "list_models",
    "load_model",
    "residual_table",
    "residual_value",
    "save_model",
    "set_status",
    "train_from_snapshot",
]
