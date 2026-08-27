"""BDX-013 specialised blast-outcome prediction.

Separate tree models (Fragmentation / Vibration / Oversize / ToeRisk), not one
universal net. Training reads only immutable snapshots from
``intelligence.datasets``. Predictions are overlays with model version.
"""
from intelligence.calibration.algorithms import available_algorithms, get_algorithm
from intelligence.outcomes.features import target_table, target_tables, toe_probability_from_targets
from intelligence.outcomes.persistence import (
    ImmutableOutcomeError,
    OutcomeNotFoundError,
    list_models,
    load_model,
    save_model,
    set_status,
)
from intelligence.outcomes.prediction import apply_model, empty_prediction
from intelligence.outcomes.training import train_from_snapshot
from intelligence.outcomes.types import (
    CLASS_FRAGMENTATION,
    CLASS_OVERSIZE,
    CLASS_TOE_RISK,
    CLASS_VIBRATION,
    MODEL_FRAGMENTATION,
    MODEL_OVERSIZE,
    MODEL_TOE_RISK,
    MODEL_TYPES,
    MODEL_VIBRATION,
    STATUS_CANDIDATE,
    STATUS_PRODUCTION,
    OutcomeModel,
    OutcomePrediction,
    listed_model_types,
)

__all__ = [
    "CLASS_FRAGMENTATION",
    "CLASS_OVERSIZE",
    "CLASS_TOE_RISK",
    "CLASS_VIBRATION",
    "ImmutableOutcomeError",
    "MODEL_FRAGMENTATION",
    "MODEL_OVERSIZE",
    "MODEL_TOE_RISK",
    "MODEL_TYPES",
    "MODEL_VIBRATION",
    "OutcomeModel",
    "OutcomeNotFoundError",
    "OutcomePrediction",
    "STATUS_CANDIDATE",
    "STATUS_PRODUCTION",
    "apply_model",
    "available_algorithms",
    "empty_prediction",
    "get_algorithm",
    "list_models",
    "listed_model_types",
    "load_model",
    "save_model",
    "set_status",
    "target_table",
    "target_tables",
    "toe_probability_from_targets",
    "train_from_snapshot",
]
