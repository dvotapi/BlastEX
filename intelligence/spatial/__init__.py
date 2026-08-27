"""BDX-022 spatial / hole-level ML.

Predictions and residuals at hole or neighborhood scale. Maps of predicted
X50 / oversize / toe / residual. The overlay is ROLE_PREDICTED only and never
overwrites designed charges or the approved pattern. Training reads immutable
snapshots only.
"""
from intelligence.spatial.features import extract_hole_observations, hole_rows_from_payload
from intelligence.spatial.maps import spatial_maps
from intelligence.spatial.persistence import (
    ImmutableSpatialError,
    InvalidSpatialError,
    SpatialNotFoundError,
    list_models,
    load_model,
    save_model,
    set_status,
)
from intelligence.spatial.prediction import apply_model, empty_overlay
from intelligence.spatial.training import train_from_snapshot
from intelligence.spatial.types import (
    APPLIED_AS_OVERLAY,
    CLASS_SPATIAL,
    DATA_ROLES,
    ROLE_DESIGNED,
    ROLE_EXECUTED,
    ROLE_MEASURED,
    ROLE_PREDICTED,
    SPATIAL_MAP_METRICS,
    HoleObservation,
    HolePrediction,
    NeighborhoodPrediction,
    SpatialModel,
    SpatialOverlay,
    listed_map_metrics,
    listed_metrics,
)

__all__ = [
    "APPLIED_AS_OVERLAY",
    "CLASS_SPATIAL",
    "DATA_ROLES",
    "ROLE_DESIGNED",
    "ROLE_EXECUTED",
    "ROLE_MEASURED",
    "ROLE_PREDICTED",
    "SPATIAL_MAP_METRICS",
    "HoleObservation",
    "HolePrediction",
    "ImmutableSpatialError",
    "InvalidSpatialError",
    "NeighborhoodPrediction",
    "SpatialModel",
    "SpatialNotFoundError",
    "SpatialOverlay",
    "apply_model",
    "empty_overlay",
    "extract_hole_observations",
    "hole_rows_from_payload",
    "list_models",
    "listed_map_metrics",
    "listed_metrics",
    "load_model",
    "save_model",
    "set_status",
    "spatial_maps",
    "train_from_snapshot",
]
