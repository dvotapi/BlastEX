"""BDX-015 explainability: feature importance, SHAP-style drivers, design deltas.

Predictions must not be a lone number. The engineer sees which features
drove X50 / PPV / oversize and how a small lever (burden, powder factor)
would move the overlay. Not a scenario engine (BDX-016) and not an optimiser
(BDX-017).
"""
from intelligence.explainability.explain import driver_summary, explain_estimator
from intelligence.explainability.importance import global_feature_importance
from intelligence.explainability.labels import feature_label_en, format_expected_delta
from intelligence.explainability.recommendations import recommendation_deltas
from intelligence.explainability.shap_values import local_shap_values, sklearn_trees, tree_path_contributions
from intelligence.explainability.types import (
    METHOD_IMPORTANCE,
    METHOD_NONE,
    METHOD_PERMUTATION,
    METHOD_TREE_PATH,
    FeatureDriver,
    PredictionExplanation,
    RecommendationHint,
    empty_explanation,
    explanation_from_payload,
)

__all__ = [
    "METHOD_IMPORTANCE",
    "METHOD_NONE",
    "METHOD_PERMUTATION",
    "METHOD_TREE_PATH",
    "FeatureDriver",
    "PredictionExplanation",
    "RecommendationHint",
    "driver_summary",
    "empty_explanation",
    "explain_estimator",
    "explanation_from_payload",
    "feature_label_en",
    "format_expected_delta",
    "global_feature_importance",
    "local_shap_values",
    "recommendation_deltas",
    "sklearn_trees",
    "tree_path_contributions",
]
