"""BDX-023 movement / heave estimate.

Empirical kinematic overlay of muckpile throw and heave. The output is an
estimate (оценка / estimate), not a physics simulation. It lives on the
PREDICTED layer and never rewrites the designed pattern.
"""

from simulation.movement.engine import list_models, predict_design
from simulation.movement.maps import MOVEMENT_MAP_METRICS, movement_maps
from simulation.movement.models import (
    DISCLAIMER,
    IS_PHYSICS_SIMULATION,
    KIND_ESTIMATE,
    LABEL_EN,
    LABEL_RU,
    MODEL_ID,
    MODEL_VERSION,
    MeasuredMuckpileEcho,
    MovementInputs,
    PredictedHoleMovement,
    PredictedMuckpile,
    estimate_kind_payload,
)
from simulation.movement.units import (
    length_m_from_mm,
    length_mm_from_m,
    mass_kg_from_t,
    mass_t_from_kg,
)

__all__ = [
    "DISCLAIMER",
    "IS_PHYSICS_SIMULATION",
    "KIND_ESTIMATE",
    "LABEL_EN",
    "LABEL_RU",
    "MODEL_ID",
    "MODEL_VERSION",
    "MOVEMENT_MAP_METRICS",
    "MeasuredMuckpileEcho",
    "MovementInputs",
    "PredictedHoleMovement",
    "PredictedMuckpile",
    "estimate_kind_payload",
    "length_m_from_mm",
    "length_mm_from_m",
    "list_models",
    "mass_kg_from_t",
    "mass_t_from_kg",
    "movement_maps",
    "predict_design",
]
