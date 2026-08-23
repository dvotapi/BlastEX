"""Flatten snapshot features and extract specialised outcome targets.

Direct prediction tables do not include an engineering baseline column.
Live designs are never read during table construction.
"""
from __future__ import annotations

from typing import Any

from intelligence.calibration.features import NUMERIC_FEATURE_KEYS, flatten_features
from intelligence.datasets.builder import DatasetSnapshot, TrainingSample
from intelligence.outcomes.types import (
    TARGET_TOE_RISK,
    TargetRow,
    TargetTable,
    normalize_model_type,
    spec_for,
)

TOE_CONDITION_RISK: dict[str, float] = {
    "none": 0.0,
    "clean": 0.0,
    "absent": 0.0,
    "ok": 0.0,
    "good": 0.0,
    "trace": 0.2,
    "minor": 0.35,
    "present": 0.7,
    "leftover": 0.8,
    "moderate": 0.6,
    "major": 0.9,
    "high": 0.85,
    "severe": 1.0,
    "toe": 0.75,
}


def feature_column_names() -> list[str]:
    return [f"{group}.{key}" for group, key in NUMERIC_FEATURE_KEYS]


def _as_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _impute_column(values: list[float | None]) -> list[float]:
    present = [item for item in values if item is not None]
    fill = (sum(present) / len(present)) if present else 0.0
    return [fill if item is None else float(item) for item in values]


def toe_probability_from_targets(targets: dict[str, dict[str, Any]] | None) -> float | None:
    """Derive a 0–1 toe-risk label from leftover height and/or condition."""
    targets = targets or {}
    blast = targets.get("BLAST") or {}
    performance = targets.get("PERFORMANCE") or {}
    leftover = _as_float(blast.get("leftover_height_m"))
    if leftover is None:
        leftover = _as_float(performance.get("leftover_height_m"))
    if leftover is not None:
        return float(min(1.0, max(0.0, leftover)))
    stored = _as_float(blast.get(TARGET_TOE_RISK))
    if stored is not None:
        return float(min(1.0, max(0.0, stored)))
    condition = str(blast.get("toe_condition") or "").strip().lower()
    if condition in TOE_CONDITION_RISK:
        return TOE_CONDITION_RISK[condition]
    return None


def measured_target(sample: TrainingSample, model_type: str, target_name: str) -> float | None:
    spec = spec_for(model_type)
    target = next((item for item in spec["targets"] if item["name"] == target_name), None)
    if target is None:
        return None
    if target.get("derived") and target_name == TARGET_TOE_RISK:
        return toe_probability_from_targets(sample.targets)
    group = sample.targets.get(target["group"]) or {}
    value = _as_float(group.get(target["field"]))
    if value is None:
        fallback = target.get("field_fallback")
        if fallback:
            value = _as_float(group.get(fallback))
    return value


def target_table(snapshot: DatasetSnapshot, model_type: str, target_name: str) -> TargetTable:
    """Build X/y for one specialised target. Live designs are never read."""
    model_type = normalize_model_type(model_type)
    names = feature_column_names()
    raw_rows: list[dict[str, float | None]] = []
    kept: list[tuple[TrainingSample, float]] = []
    for sample in snapshot.samples:
        y = measured_target(sample, model_type, target_name)
        if y is None:
            continue
        raw_rows.append(flatten_features(sample.features))
        kept.append((sample, float(y)))

    columns = {name: _impute_column([row.get(name) for row in raw_rows]) for name in names}
    rows: list[TargetRow] = []
    X: list[list[float]] = []
    y_values: list[float] = []
    source_ids: list[str] = []
    for index, (sample, y) in enumerate(kept):
        features = {name: columns[name][index] for name in names}
        rows.append(TargetRow(source_blast_id=sample.source_blast_id, features=features, y=y))
        X.append([features[name] for name in names])
        y_values.append(y)
        source_ids.append(sample.source_blast_id)

    return TargetTable(
        target_name=target_name,
        feature_names=names,
        rows=rows,
        X=X,
        y=y_values,
        source_blast_ids=source_ids,
    )


def target_tables(snapshot: DatasetSnapshot, model_type: str) -> dict[str, TargetTable]:
    model_type = normalize_model_type(model_type)
    return {
        item["name"]: target_table(snapshot, model_type, item["name"])
        for item in spec_for(model_type)["targets"]
    }


def vectorize_features(
    features: dict[str, Any],
    feature_names: list[str],
    *,
    fill: float = 0.0,
) -> list[float]:
    """Align a live feature dict to the columns stored on a trained model."""
    if "SITE" in features or "GEOLOGY" in features:
        flat: dict[str, float | None] = flatten_features(features)
    else:
        flat = {str(key): _as_float(value) for key, value in features.items()}
    vector: list[float] = []
    for name in feature_names:
        value = flat.get(name)
        vector.append(fill if value is None else float(value))
    return vector
