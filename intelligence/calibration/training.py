"""Train residual-correction models from immutable dataset snapshots."""
from __future__ import annotations

import uuid
from typing import Any

import numpy as np

from intelligence.calibration.algorithms import DEFAULT_ALGORITHM, get_algorithm
from intelligence.calibration.features import residual_table
from intelligence.calibration.types import (
    MIN_TRAINING_SAMPLES,
    MODEL_SPECS,
    STATUS_CANDIDATE,
    CalibrationModel,
    ResidualTable,
    normalize_model_type,
    utc_now_iso,
)
from intelligence.datasets.builder import DatasetSnapshot
from intelligence.datasets.features import FEATURE_SCHEMA_VERSION
from intelligence.uncertainty.domain import compute_feature_ranges
from intelligence.uncertainty.types import ranges_to_dict


def next_model_version(existing_versions: list[int]) -> int:
    versions = [int(item) for item in existing_versions]
    return (max(versions) + 1) if versions else 1


def _metrics(y_true: np.ndarray, y_pred: np.ndarray) -> dict[str, float]:
    residual = y_true - y_pred
    mae = float(np.mean(np.abs(residual)))
    rmse = float(np.sqrt(np.mean(residual**2)))
    denom = float(np.sum((y_true - np.mean(y_true)) ** 2))
    r2 = 1.0 - float(np.sum(residual**2) / denom) if denom > 1e-12 else 0.0
    return {"mae": round(mae, 6), "rmse": round(rmse, 6), "r2": round(r2, 6)}


def evaluate_table(estimator: Any, algorithm_name: str, table: ResidualTable) -> dict[str, Any]:
    algo = get_algorithm(algorithm_name)
    X = np.asarray(table.X, dtype=float)
    y = np.asarray(table.y, dtype=float)
    measured = np.asarray(table.measured, dtype=float)
    baselines = np.asarray(table.baselines, dtype=float)
    in_sample = algo.predict(estimator, X)
    calibrated = baselines + in_sample
    baseline_err = _metrics(measured, baselines)
    calibrated_err = _metrics(measured, calibrated)
    residual_err = _metrics(y, in_sample)

    loo: dict[str, float] | None = None
    n = len(y)
    if n >= 5:
        preds = np.zeros(n, dtype=float)
        for index in range(n):
            mask = np.ones(n, dtype=bool)
            mask[index] = False
            fold = algo.fit(X[mask], y[mask], random_state=42)
            preds[index] = float(algo.predict(fold, X[index : index + 1])[0])
        loo = _metrics(measured, baselines + preds)

    return {
        "n_samples": n,
        "mae": residual_err["mae"],
        "rmse": residual_err["rmse"],
        "r2": residual_err["r2"],
        "baseline_mae": baseline_err["mae"],
        "baseline_rmse": baseline_err["rmse"],
        "calibrated_mae": calibrated_err["mae"],
        "calibrated_rmse": calibrated_err["rmse"],
        "metrics_split": "in_sample",
        "leave_one_out": loo,
    }


def train_from_snapshot(
    snapshot: DatasetSnapshot,
    *,
    model_type: str,
    algorithm: str = DEFAULT_ALGORITHM,
    model_id: str = "",
    model_version: int = 1,
    site_id: str = "",
    training_date: str = "",
) -> CalibrationModel:
    """Fit a residual model on a frozen snapshot. Never reads live designs."""
    if not snapshot.immutable:
        raise ValueError("Обучение разрешено только по неизменяемому снимку датасета.")
    model_type = normalize_model_type(model_type)
    spec = MODEL_SPECS[model_type]
    site = (site_id or snapshot.site_id).strip()
    if not site:
        raise ValueError("Для модели калибровки нужен site_id.")
    if snapshot.site_id and site != snapshot.site_id:
        raise ValueError("site_id модели не совпадает с площадкой снимка датасета.")

    table = residual_table(snapshot, model_type)
    if len(table.y) < MIN_TRAINING_SAMPLES:
        raise ValueError(
            f"Для обучения «{model_type}» нужно не меньше {MIN_TRAINING_SAMPLES} образцов "
            f"с базовым прогнозом и замером, в снимке {len(table.y)}."
        )

    algo = get_algorithm(algorithm)
    X = np.asarray(table.X, dtype=float)
    y = np.asarray(table.y, dtype=float)
    estimator = algo.fit(X, y, random_state=42)
    metrics = evaluate_table(estimator, algo.name, table)
    ranges = ranges_to_dict(compute_feature_ranges(table.X, table.feature_names))

    return CalibrationModel(
        model_id=str(model_id or "").strip() or uuid.uuid4().hex[:12],
        site_id=site,
        model_type=model_type,
        model_version=int(model_version),
        training_dataset_id=snapshot.dataset_id,
        training_dataset_version=int(snapshot.dataset_version),
        feature_schema_version=snapshot.feature_schema_version or FEATURE_SCHEMA_VERSION,
        training_date=training_date or utc_now_iso(),
        metrics=metrics,
        status=STATUS_CANDIDATE,
        algorithm=algo.name,
        feature_names=list(table.feature_names),
        target_name=spec["measured_field"],
        baseline_field=spec["baseline_field"],
        measured_field=spec["measured_field"],
        sample_count=len(table.y),
        source_blast_ids=list(table.source_blast_ids),
        feature_ranges=ranges,
        training_matrix=[list(row) for row in table.X],
        estimator=estimator,
    )
