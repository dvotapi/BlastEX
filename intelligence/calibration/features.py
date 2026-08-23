"""Flatten snapshot feature groups into numeric columns for residual models."""
from __future__ import annotations

from typing import Any

from intelligence.calibration.types import MODEL_SPECS, ResidualRow, ResidualTable, normalize_model_type
from intelligence.datasets.builder import DatasetSnapshot, TrainingSample

NUMERIC_FEATURE_KEYS: tuple[tuple[str, str], ...] = (
    ("GEOLOGY", "mean_density_kg_m3"),
    ("GEOLOGY", "mean_ucs_mpa"),
    ("GEOLOGY", "mean_rqd_pct"),
    ("GEOMETRY", "mean_spacing_m"),
    ("GEOMETRY", "mean_burden_m"),
    ("GEOMETRY", "mean_diameter_mm"),
    ("GEOMETRY", "mean_depth_m"),
    ("GEOMETRY", "mean_subdrill_m"),
    ("CHARGING", "mean_charge_kg"),
    ("CHARGING", "mean_powder_factor_kg_m3"),
    ("CHARGING", "mean_stemming_m"),
    ("TIMING", "mean_delay_ms"),
    ("EXECUTION", "mean_collar_offset_m"),
    ("EXECUTION", "fired_coverage"),
    ("ENVIRONMENT", "wet_hole_fraction"),
    ("ENVIRONMENT", "nearest_receptor_distance_m"),
    ("ENVIRONMENT", "vibration_model_k"),
    ("ENVIRONMENT", "vibration_model_n"),
)

BASELINE_FEATURE = "baseline"


def feature_column_names() -> list[str]:
    names = [f"{group}.{key}" for group, key in NUMERIC_FEATURE_KEYS]
    names.append(BASELINE_FEATURE)
    return names


def _as_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def flatten_features(features: dict[str, dict[str, Any]] | None) -> dict[str, float | None]:
    features = features or {}
    flat: dict[str, float | None] = {}
    for group, key in NUMERIC_FEATURE_KEYS:
        group_data = features.get(group) or {}
        flat[f"{group}.{key}"] = _as_float(group_data.get(key))
    return flat


def measured_and_baseline(sample: TrainingSample, model_type: str) -> tuple[float | None, float | None]:
    spec = MODEL_SPECS[normalize_model_type(model_type)]
    group = sample.targets.get(spec["target_group"]) or {}
    measured = _as_float(group.get(spec["measured_field"]))
    if measured is None:
        fallback = spec.get("measured_field_fallback")
        if fallback:
            measured = _as_float(group.get(fallback))
    baseline = _as_float(group.get(spec["baseline_field"]))
    return measured, baseline


def residual_value(measured: float, baseline: float) -> float:
    """Engineering residual: measured minus empirical/physics baseline."""
    return float(measured) - float(baseline)


def _impute_column(values: list[float | None]) -> list[float]:
    present = [item for item in values if item is not None]
    fill = (sum(present) / len(present)) if present else 0.0
    return [fill if item is None else float(item) for item in values]


def residual_table(snapshot: DatasetSnapshot, model_type: str) -> ResidualTable:
    """Build X/y from an immutable snapshot. Live designs are never read."""
    model_type = normalize_model_type(model_type)
    names = feature_column_names()
    raw_rows: list[dict[str, float | None]] = []
    kept: list[tuple[TrainingSample, float, float, float]] = []
    for sample in snapshot.samples:
        measured, baseline = measured_and_baseline(sample, model_type)
        if measured is None or baseline is None:
            continue
        residual = residual_value(measured, baseline)
        flat = flatten_features(sample.features)
        flat[BASELINE_FEATURE] = baseline
        raw_rows.append(flat)
        kept.append((sample, baseline, measured, residual))

    columns = {name: _impute_column([row.get(name) for row in raw_rows]) for name in names}
    rows: list[ResidualRow] = []
    X: list[list[float]] = []
    y: list[float] = []
    baselines: list[float] = []
    measured_values: list[float] = []
    source_ids: list[str] = []
    for index, (sample, baseline, measured, residual) in enumerate(kept):
        features = {name: columns[name][index] for name in names}
        vector = [features[name] for name in names]
        rows.append(
            ResidualRow(
                source_blast_id=sample.source_blast_id,
                features=features,
                baseline=baseline,
                measured=measured,
                residual=residual,
            )
        )
        X.append(vector)
        y.append(residual)
        baselines.append(baseline)
        measured_values.append(measured)
        source_ids.append(sample.source_blast_id)

    return ResidualTable(
        feature_names=names,
        rows=rows,
        X=X,
        y=y,
        baselines=baselines,
        measured=measured_values,
        source_blast_ids=source_ids,
    )


def vectorize_features(
    features: dict[str, Any],
    feature_names: list[str],
    baseline: float,
    *,
    fill: float = 0.0,
) -> list[float]:
    """Align a live feature dict to the columns stored on a trained model."""
    if "SITE" in features or "GEOLOGY" in features:
        flat: dict[str, float | None] = flatten_features(features)
    else:
        flat = {str(key): _as_float(value) for key, value in features.items()}
    flat[BASELINE_FEATURE] = float(baseline)
    vector: list[float] = []
    for name in feature_names:
        value = flat.get(name)
        vector.append(fill if value is None else float(value))
    return vector
