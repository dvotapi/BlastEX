"""BDX-019 two-level learning: global/prior plus per-site adaptation.

Training reads only immutable snapshots from ``intelligence.datasets``.
Artifacts store ``team_id`` / ``site_id`` isolation keys. Cross-tenant
access fails. Models stay ``candidate`` until an explicit human-gated
promotion in ``intelligence.registry`` (BDX-020).
"""
from intelligence.calibration.algorithms import available_algorithms, get_algorithm
from intelligence.learning.isolation import (
    CrossTenantError,
    IsolationError,
    isolation_keys,
)
from intelligence.learning.persistence import (
    ImmutableLearningError,
    LearningNotFoundError,
    list_models,
    load_model,
    save_model,
    set_status,
)
from intelligence.learning.pooling import pool_snapshots
from intelligence.learning.prediction import apply_model, empty_prediction
from intelligence.learning.training import train_global, train_site
from intelligence.learning.types import (
    ADAPTATION_DIRECT,
    ADAPTATION_RESIDUAL,
    GLOBAL_SITE_ID,
    IsolationKeys,
    LearnedModel,
    LearningPrediction,
    SCOPE_GLOBAL,
    SCOPE_SITE,
    STATUS_CANDIDATE,
    STATUS_PRODUCTION,
    listed_model_types,
)

__all__ = [
    "ADAPTATION_DIRECT",
    "ADAPTATION_RESIDUAL",
    "CrossTenantError",
    "GLOBAL_SITE_ID",
    "ImmutableLearningError",
    "IsolationError",
    "IsolationKeys",
    "LearnedModel",
    "LearningNotFoundError",
    "LearningPrediction",
    "SCOPE_GLOBAL",
    "SCOPE_SITE",
    "STATUS_CANDIDATE",
    "STATUS_PRODUCTION",
    "apply_model",
    "available_algorithms",
    "empty_prediction",
    "get_algorithm",
    "isolation_keys",
    "list_models",
    "listed_model_types",
    "load_model",
    "pool_snapshots",
    "save_model",
    "set_status",
    "train_global",
    "train_site",
]
