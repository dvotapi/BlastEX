"""BDX-020 model registry: versions, checksum, lineage, human-gated promotion.

Wraps candidate models from calibration (BDX-012), outcomes (BDX-013) and
two-level learning (BDX-019). Promotion is explicit. There is no auto-deploy
and no training from live designs.
"""
from intelligence.registry.catalog import RegistryNotFoundError
from intelligence.registry.lifecycle import InvalidPromotionError, plan_promotion
from intelligence.registry.persistence import (
    ImmutableRegistryError,
    get_record,
    list_records,
    promote,
)
from intelligence.registry.types import (
    DATA_ROLES,
    FAMILY_CALIBRATION,
    FAMILY_LEARNING,
    FAMILY_OUTCOMES,
    MODEL_FAMILIES,
    REGISTRY_STATUSES,
    ROLE_DESIGNED,
    ROLE_EXECUTED,
    ROLE_MEASURED,
    ROLE_PREDICTED,
    STATUS_ARCHIVED,
    STATUS_CANDIDATE,
    STATUS_PRODUCTION,
    STATUS_RETIRED,
    STATUS_STAGING,
    DatasetLineage,
    PromotionEvent,
    RegistryRecord,
    allowed_transitions,
    listed_families,
    listed_statuses,
    normalize_family,
    normalize_status,
)

__all__ = [
    "DATA_ROLES",
    "FAMILY_CALIBRATION",
    "FAMILY_LEARNING",
    "FAMILY_OUTCOMES",
    "ImmutableRegistryError",
    "InvalidPromotionError",
    "MODEL_FAMILIES",
    "REGISTRY_STATUSES",
    "ROLE_DESIGNED",
    "ROLE_EXECUTED",
    "ROLE_MEASURED",
    "ROLE_PREDICTED",
    "RegistryNotFoundError",
    "RegistryRecord",
    "DatasetLineage",
    "PromotionEvent",
    "STATUS_ARCHIVED",
    "STATUS_CANDIDATE",
    "STATUS_PRODUCTION",
    "STATUS_RETIRED",
    "STATUS_STAGING",
    "allowed_transitions",
    "get_record",
    "list_records",
    "listed_families",
    "listed_statuses",
    "normalize_family",
    "normalize_status",
    "plan_promotion",
    "promote",
]
