"""Train specialised outcome models from immutable dataset snapshots."""
from __future__ import annotations

import uuid
from typing import Any

import numpy as np

from intelligence.calibration.algorithms import DEFAULT_ALGORITHM, get_algorithm
from intelligence.datasets.builder import DatasetSnapshot
from intelligence.datasets.features import FEATURE_SCHEMA_VERSION
from intelligence.outcomes.features import target_tables
from intelligence.outcomes.types import (
    MIN_TRAINING_SAMPLES,
    STATUS_CANDIDATE,
    OutcomeModel,
    TargetTable,
    normalize_model_type,
    spec_for,
    utc_now_iso,
)
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


def evaluate_table(estimator: Any, algorithm_name: str, table: TargetTable) -> dict[str, Any]:
    algo = get_algorithm(algorithm_name)
    X = np.asarray(table.X, dtype=float)
    y = np.asarray(table.y, dtype=float)
    in_sample = algo.predict(estimator, X)
    err = _metrics(y, in_sample)

    loo: dict[str, float] | None = None
    n = len(y)
    if n >= 5:
        preds = np.zeros(n, dtype=float)
        for index in range(n):
            mask = np.ones(n, dtype=bool)
            mask[index] = False
            fold = algo.fit(X[mask], y[mask], random_state=42)
            preds[index] = float(algo.predict(fold, X[index : index + 1])[0])
        loo = _metrics(y, preds)

    return {
        "n_samples": n,
        "mae": err["mae"],
        "rmse": err["rmse"],
        "r2": err["r2"],
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
) -> OutcomeModel:
    """Fit specialised tree models on a frozen snapshot. Never reads live designs."""
    if not snapshot.immutable:
        raise ValueError("Обучение разрешено только по неизменяемому снимку датасета.")
    model_type = normalize_model_type(model_type)
    spec = spec_for(model_type)
    site = (site_id or snapshot.site_id).strip()
    if not site:
        raise ValueError("Для модели исхода нужен site_id.")
    if snapshot.site_id and site != snapshot.site_id:
        raise ValueError("site_id модели не совпадает с площадкой снимка датасета.")

    tables = target_tables(snapshot, model_type)
    algo = get_algorithm(algorithm)
    estimators: dict[str, Any] = {}
    per_target: dict[str, Any] = {}
    source_ids: list[str] = []
    feature_names: list[str] = []
    max_samples = 0

    for target in spec["targets"]:
        name = target["name"]
        table = tables[name]
        if not feature_names:
            feature_names = list(table.feature_names)
        if len(table.y) < MIN_TRAINING_SAMPLES:
            continue
        X = np.asarray(table.X, dtype=float)
        y = np.asarray(table.y, dtype=float)
        estimator = algo.fit(X, y, random_state=42)
        estimators[name] = estimator
        per_target[name] = evaluate_table(estimator, algo.name, table)
        for blast_id in table.source_blast_ids:
            if blast_id not in source_ids:
                source_ids.append(blast_id)
        max_samples = max(max_samples, len(table.y))

    if not estimators:
        available = ", ".join(
            f"{name}={len(table.y)}" for name, table in tables.items()
        )
        raise ValueError(
            f"Для обучения «{spec['class_name']}» нужно не меньше {MIN_TRAINING_SAMPLES} "
            f"образцов с замеренной целью, в снимке: {available or '0'}."
        )

    maes = [item["mae"] for item in per_target.values()]
    rmses = [item["rmse"] for item in per_target.values()]
    r2s = [item["r2"] for item in per_target.values()]
    metrics: dict[str, Any] = {
        "n_samples": max_samples,
        "mae": round(float(sum(maes) / len(maes)), 6),
        "rmse": round(float(sum(rmses) / len(rmses)), 6),
        "r2": round(float(sum(r2s) / len(r2s)), 6),
        "metrics_split": "in_sample",
        "targets": per_target,
        "trained_targets": list(estimators.keys()),
    }
    primary = spec["primary_target"]
    if primary in per_target:
        metrics["n_samples"] = per_target[primary]["n_samples"]
        metrics["mae"] = per_target[primary]["mae"]
        metrics["rmse"] = per_target[primary]["rmse"]
        metrics["r2"] = per_target[primary]["r2"]
        metrics["leave_one_out"] = per_target[primary].get("leave_one_out")

    matrix_source = tables.get(primary) if primary in estimators else None
    if matrix_source is None:
        matrix_source = next((tables[name] for name in estimators), None)
    feature_ranges = {}
    training_matrix: list[list[float]] = []
    if matrix_source is not None and matrix_source.X:
        feature_names = list(matrix_source.feature_names) or feature_names
        feature_ranges = ranges_to_dict(compute_feature_ranges(matrix_source.X, feature_names))
        training_matrix = [list(row) for row in matrix_source.X]

    return OutcomeModel(
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
        feature_names=feature_names,
        target_names=list(estimators.keys()),
        primary_target=primary,
        class_name=spec["class_name"],
        sample_count=max_samples,
        source_blast_ids=source_ids,
        feature_ranges=feature_ranges,
        training_matrix=training_matrix,
        estimators=estimators,
    )
