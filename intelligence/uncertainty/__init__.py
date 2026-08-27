"""BDX-014 uncertainty: intervals, confidence, similarity, applicability.

Predictions must not present a lone point estimate as if it were exact.
"""
from intelligence.uncertainty.assess import assess_vector, unavailable
from intelligence.uncertainty.domain import (
    check_domain,
    compute_feature_ranges,
    format_applicability_warning,
    similarity_to_training,
)
from intelligence.uncertainty.types import (
    CONFIDENCE_HIGH,
    CONFIDENCE_LOW,
    CONFIDENCE_MEDIUM,
    PredictionAssessment,
    empty_assessment,
    ranges_from_dict,
    ranges_to_dict,
)

__all__ = [
    "CONFIDENCE_HIGH",
    "CONFIDENCE_LOW",
    "CONFIDENCE_MEDIUM",
    "PredictionAssessment",
    "assess_vector",
    "check_domain",
    "compute_feature_ranges",
    "empty_assessment",
    "format_applicability_warning",
    "ranges_from_dict",
    "ranges_to_dict",
    "similarity_to_training",
    "unavailable",
]
