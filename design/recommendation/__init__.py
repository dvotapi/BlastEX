"""ML design recommendation (BDX-018).

Suggests a profile-weighted overlay from BDX-016 scenarios and BDX-017 Pareto.
The approved BlastDesign is not replaced, approved or auto-applied. This is
not global+site learning (BDX-019).
"""
from design.recommendation.engine import (
    RecommendationError,
    default_bounds,
    new_recommendation_id,
    recommend,
)
from design.recommendation.persistence import (
    RecommendationNotFoundError,
    list_recommendations,
    load_recommendation,
    save_recommendation,
)
from design.recommendation.profiles import (
    UnknownProfileError,
    pick_for_profile,
    profile_spec,
    profile_winners,
)
from design.recommendation.types import (
    APPLIED_AS,
    METHOD_PROFILE_PARETO,
    PROFILE_BALANCED,
    PROFILE_FINE_FRAGMENTATION,
    PROFILE_KEYS,
    PROFILE_LOW_COST,
    PROFILE_LOW_VIBRATION,
    PROFILES,
    DesignRecommendation,
    RecommendationAssessment,
    RecommendationProfile,
    RecommendationReason,
)
from design.recommendation.why import build_reasons

__all__ = [
    "APPLIED_AS",
    "METHOD_PROFILE_PARETO",
    "PROFILE_BALANCED",
    "PROFILE_FINE_FRAGMENTATION",
    "PROFILE_KEYS",
    "PROFILE_LOW_COST",
    "PROFILE_LOW_VIBRATION",
    "PROFILES",
    "DesignRecommendation",
    "RecommendationAssessment",
    "RecommendationError",
    "RecommendationNotFoundError",
    "RecommendationProfile",
    "RecommendationReason",
    "UnknownProfileError",
    "build_reasons",
    "default_bounds",
    "list_recommendations",
    "load_recommendation",
    "new_recommendation_id",
    "pick_for_profile",
    "profile_spec",
    "profile_winners",
    "recommend",
    "save_recommendation",
]
