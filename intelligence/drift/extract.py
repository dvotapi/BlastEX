"""Pull numeric series from immutable snapshots without mixing data roles.

Designed features, executed features, measured targets and predicted scores
stay on separate channels. Field names keep their unit suffix; this module
does not convert units.
"""
from __future__ import annotations

from typing import Any, Iterable

from intelligence.datasets.builder import DatasetSnapshot, TrainingSample
from intelligence.drift.statistics import as_floats, unit_from_name
from intelligence.drift.types import (
    KIND_FEATURE,
    KIND_PREDICTION,
    KIND_TARGET,
    ROLE_DESIGNED,
    ROLE_EXECUTED,
    ROLE_MEASURED,
    ROLE_PREDICTED,
)

FEATURE_GROUP_ROLES = {
    "SITE": ROLE_DESIGNED,
    "GEOLOGY": ROLE_DESIGNED,
    "GEOMETRY": ROLE_DESIGNED,
    "CHARGING": ROLE_DESIGNED,
    "TIMING": ROLE_DESIGNED,
    "ENVIRONMENT": ROLE_DESIGNED,
    "EXECUTION": ROLE_EXECUTED,
}

SKIP_KEYS = frozenset(
    {
        "role",
        "group",
        "source",
        "method",
        "label",
        "predicted_role",
        "designed_role",
        "site_id",
        "design_id",
        "design_name",
        "rock_name",
        "coordinate_system_name",
        "units",
        "contour_name",
        "toe_condition",
        "receptor_id",
        "name",
        "kind",
        "class_name",
        "feature_schema_version",
        "source_blast_id",
        "epsg",
    }
)

PREDICTED_PREFIX = "predicted_"
DESIGNED_PREFIX = "designed_"


def _iter_numeric(payload: dict[str, Any], *, prefix: str = "") -> Iterable[tuple[str, float]]:
    for key, value in (payload or {}).items():
        name = str(key or "").strip()
        if not name or name in SKIP_KEYS:
            continue
        path = f"{prefix}.{name}" if prefix else name
        if isinstance(value, dict):
            yield from _iter_numeric(value, prefix=path)
            continue
        numbers = as_floats([value])
        if numbers:
            yield path, numbers[0]


def _samples(snapshots: Iterable[DatasetSnapshot]) -> list[TrainingSample]:
    out: list[TrainingSample] = []
    for snapshot in snapshots:
        out.extend(snapshot.samples)
    return out


def feature_series(snapshots: Iterable[DatasetSnapshot]) -> dict[str, dict[str, Any]]:
    """Designed / executed numeric features, keyed by group.field."""
    buckets: dict[str, list[float]] = {}
    roles: dict[str, str] = {}
    for sample in _samples(snapshots):
        for group, payload in (sample.features or {}).items():
            role = FEATURE_GROUP_ROLES.get(str(group), ROLE_DESIGNED)
            if not isinstance(payload, dict):
                continue
            for field, number in _iter_numeric(payload):
                key = f"{group}.{field}"
                buckets.setdefault(key, []).append(number)
                roles[key] = role
    return {
        key: {"values": values, "role": roles[key], "kind": KIND_FEATURE, "unit": unit_from_name(key)}
        for key, values in buckets.items()
    }


def target_series(snapshots: Iterable[DatasetSnapshot]) -> dict[str, dict[str, Any]]:
    """Measured targets only. Predicted / designed context columns are skipped."""
    buckets: dict[str, list[float]] = {}
    for sample in _samples(snapshots):
        for group, payload in (sample.targets or {}).items():
            if not isinstance(payload, dict):
                continue
            for field, number in _iter_numeric(payload):
                leaf = field.rsplit(".", 1)[-1]
                if leaf.startswith(PREDICTED_PREFIX) or leaf.startswith(DESIGNED_PREFIX):
                    continue
                key = f"{group}.{field}"
                buckets.setdefault(key, []).append(number)
    return {
        key: {"values": values, "role": ROLE_MEASURED, "kind": KIND_TARGET, "unit": unit_from_name(key)}
        for key, values in buckets.items()
    }


def stored_prediction_series(snapshots: Iterable[DatasetSnapshot]) -> dict[str, dict[str, Any]]:
    """ROLE_PREDICTED context already frozen on the snapshot (no unit conversion)."""
    buckets: dict[str, list[float]] = {}
    for sample in _samples(snapshots):
        for group, payload in (sample.targets or {}).items():
            if not isinstance(payload, dict):
                continue
            for field, number in _iter_numeric(payload):
                leaf = field.rsplit(".", 1)[-1]
                if not leaf.startswith(PREDICTED_PREFIX):
                    continue
                key = f"{group}.{field}"
                buckets.setdefault(key, []).append(number)
    return {
        key: {"values": values, "role": ROLE_PREDICTED, "kind": KIND_PREDICTION, "unit": unit_from_name(key)}
        for key, values in buckets.items()
    }


def prediction_series(scores: dict[str, list[float]]) -> dict[str, dict[str, Any]]:
    return {
        name: {
            "values": list(values),
            "role": ROLE_PREDICTED,
            "kind": KIND_PREDICTION,
            "unit": unit_from_name(name),
        }
        for name, values in (scores or {}).items()
        if values
    }
