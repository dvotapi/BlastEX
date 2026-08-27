"""BDX-024 official blast passport / report.

Engineer-facing document: designed parameters, predicted outcomes
(clearly labelled), cost, vibration and fragmentation. Roles stay
DESIGNED / EXECUTED / PREDICTED / MEASURED. The document never
auto-approves the design.
"""

from design.reporting.engine import build_passport
from design.reporting.html import passport_html, render_passport_html
from design.reporting.types import (
    AUTO_APPROVED,
    DISCLAIMER,
    PASSPORT_KIND,
    ROLE_LABELS_EN,
    ROLE_LABELS_RU,
    BlastPassport,
    DesignedParameters,
    ExecutedSnapshot,
    MeasuredOutcomes,
    MetricRow,
    PlannedCostSnapshot,
    PredictedOutcomes,
    roles_payload,
)
from design.reporting.units import (
    length_m_from_mm,
    length_mm_from_m,
    mass_kg_from_t,
    mass_t_from_kg,
    time_ms_from_s,
    time_s_from_ms,
)

__all__ = [
    "AUTO_APPROVED",
    "DISCLAIMER",
    "PASSPORT_KIND",
    "ROLE_LABELS_EN",
    "ROLE_LABELS_RU",
    "BlastPassport",
    "DesignedParameters",
    "ExecutedSnapshot",
    "MeasuredOutcomes",
    "MetricRow",
    "PlannedCostSnapshot",
    "PredictedOutcomes",
    "build_passport",
    "length_m_from_mm",
    "length_mm_from_m",
    "mass_kg_from_t",
    "mass_t_from_kg",
    "passport_html",
    "render_passport_html",
    "roles_payload",
    "time_ms_from_s",
    "time_s_from_ms",
]
