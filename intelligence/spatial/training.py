"""Train hole-level residual models from immutable snapshots only (BDX-022)."""
from __future__ import annotations

import uuid
from typing import Any

import numpy as np

from intelligence.calibration.algorithms import DEFAULT_ALGORITHM, get_algorithm
from intelligence.datasets.builder import DatasetSnapshot, TrainingSample
from intelligence.learning.isolation import IsolationError, require_team_id
from intelligence.spatial.features import hole_rows_from_payload
from intelligence.spatial.residuals import residual_tables
from intelligence.spatial.types import (
    FEATURE_SCHEMA_VERSION,
    HOLE_FEATURE_NAMES,
    MIN_TRAINING_SAMPLES,
    RESIDUAL_METRICS,
    STATUS_CANDIDATE,
    SpatialModel,
    utc_now_iso,
)


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


def collect_hole_observations(snapshot: DatasetSnapshot) -> list:
    if not snapshot.immutable:
        raise ValueError("Обучение разрешено только по неизменяемому снимку датасета.")
    rows = []
    for sample in snapshot.samples:
        rows.extend(_holes_from_sample(sample, site_id=snapshot.site_id))
    if len(rows) < MIN_TRAINING_SAMPLES:
        raise ValueError(
            f"Для пространственной модели нужно не меньше {MIN_TRAINING_SAMPLES} скважинных строк "
            f"в неизменяемом снимке, получено {len(rows)}."
        )
    return rows


def _holes_from_sample(sample: TrainingSample, *, site_id: str) -> list:
    payload = getattr(sample, "holes", None)
    if payload is None and isinstance(sample, TrainingSample):
        payload = (sample.to_dict().get("holes") if hasattr(sample, "to_dict") else None)
    if payload is None:
        raw = sample.__dict__.get("holes") if hasattr(sample, "__dict__") else None
        payload = raw
    if not payload:
        # Backward compatible: some snapshots store holes on provenance.
        payload = (sample.provenance or {}).get("holes") if sample.provenance else None
    return hole_rows_from_payload(list(payload or []), site_id=site_id or sample.site_id)


def train_from_snapshot(
    snapshot: DatasetSnapshot,
    *,
    team_id: str,
    algorithm: str = DEFAULT_ALGORITHM,
    model_id: str = "",
    model_version: int = 1,
    site_id: str = "",
    training_date: str = "",
    neighbor_k: int = 4,
) -> SpatialModel:
    """Fit local residual trees on a frozen snapshot. Never reads live designs."""
    team = require_team_id(team_id)
    if not snapshot.immutable:
        raise ValueError("Обучение разрешено только по неизменяемому снимку датасета.")
    observations = collect_hole_observations(snapshot)
    feature_names = list(HOLE_FEATURE_NAMES)
    tables = residual_tables(observations, feature_names=feature_names)
    algo = get_algorithm(algorithm)
    estimators: dict[str, Any] = {}
    metrics: dict[str, Any] = {"targets": {}}
    trained = 0
    for name in RESIDUAL_METRICS:
        table = tables[name]
        if len(table["y"]) < MIN_TRAINING_SAMPLES:
            continue
        X = np.asarray(table["X"], dtype=float)
        y = np.asarray(table["y"], dtype=float)
        estimator = algo.fit(X, y, random_state=42)
        estimators[name] = estimator
        predicted = np.asarray(algo.predict(estimator, X), dtype=float)
        metrics["targets"][name] = {
            **_metrics(y, predicted),
            "n_samples": int(len(y)),
            "unit": table["unit"],
            "role": table["role"],
        }
        trained += 1
    if not estimators:
        raise ValueError(
            "В снимке нет скважинных остатков для обучения. "
            "Нужны hole-level predicted или measured значения в неизменяемом снимке."
        )
    primary = next(iter(estimators))
    metrics.update(metrics["targets"].get(primary) or {})
    return SpatialModel(
        model_id=model_id or uuid.uuid4().hex[:12],
        team_id=team,
        site_id=str(site_id or snapshot.site_id or ""),
        model_version=int(model_version),
        training_dataset_id=snapshot.dataset_id,
        training_dataset_version=int(snapshot.dataset_version),
        feature_schema_version=FEATURE_SCHEMA_VERSION,
        training_date=training_date or utc_now_iso(),
        metrics=metrics,
        status=STATUS_CANDIDATE,
        algorithm=algorithm,
        feature_names=feature_names,
        target_names=list(estimators.keys()),
        sample_count=int(snapshot.sample_count),
        hole_count=len(observations),
        source_blast_ids=list(snapshot.source_blast_ids),
        neighbor_k=int(neighbor_k),
        estimators=estimators,
    )


def assert_snapshot_only(snapshot: Any) -> DatasetSnapshot:
    if isinstance(snapshot, DatasetSnapshot):
        if not snapshot.immutable:
            raise ValueError("Обучение разрешено только по неизменяемому снимку датасета.")
        return snapshot
    raise ValueError(
        "Обучение пространственной модели разрешено только по неизменяемому снимку "
        "датасета (BDX-011), никогда по живому паспорту БВР."
    )


# IsolationError is re-exported for callers that train without persistence.
_ = IsolationError
