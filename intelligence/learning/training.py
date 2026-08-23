"""Train global priors and site adapters from immutable snapshots only."""
from __future__ import annotations

import copy
import uuid
from typing import Any, Iterable

import numpy as np

from intelligence.calibration.algorithms import DEFAULT_ALGORITHM, get_algorithm
from intelligence.datasets.builder import DatasetSnapshot
from intelligence.datasets.features import FEATURE_SCHEMA_VERSION
from intelligence.learning.isolation import (
    assert_prior_usable,
    assert_snapshots_for_scope,
    isolation_keys,
    require_team_id,
    sample_site_id,
)
from intelligence.learning.pooling import pool_snapshots
from intelligence.learning.types import (
    ADAPTATION_DIRECT,
    ADAPTATION_RESIDUAL,
    GLOBAL_SITE_ID,
    MIN_TRAINING_SAMPLES,
    SCOPE_GLOBAL,
    SCOPE_SITE,
    STATUS_CANDIDATE,
    LearnedModel,
    normalize_model_type,
    spec_for,
    utc_now_iso,
)
from intelligence.outcomes.features import target_tables
from intelligence.outcomes.training import evaluate_table, train_from_snapshot
from intelligence.outcomes.types import TargetTable
from intelligence.uncertainty.domain import compute_feature_ranges
from intelligence.uncertainty.types import ranges_to_dict


def next_model_version(existing_versions: Iterable[int]) -> int:
    versions = [int(item) for item in existing_versions]
    return (max(versions) + 1) if versions else 1


def _source_site_ids(snapshot: DatasetSnapshot) -> list[str]:
    seen: list[str] = []
    for sample in snapshot.samples:
        site = sample_site_id(sample)
        if site and site not in seen:
            seen.append(site)
    if snapshot.site_id and snapshot.site_id not in seen:
        seen.append(snapshot.site_id)
    return seen


def _from_outcome(
    outcome,
    *,
    team_id: str,
    scope: str,
    site_id: str,
    dataset_ids: list[str],
    source_site_ids: list[str],
    prior_model_id: str = "",
    prior_team_id: str = "",
    prior_scope: str = "",
    adaptation: str = ADAPTATION_DIRECT,
    prior_estimators: dict[str, Any] | None = None,
    estimators: dict[str, Any] | None = None,
    metrics: dict[str, Any] | None = None,
) -> LearnedModel:
    keys = isolation_keys(team_id, site_id, scope=scope)
    return LearnedModel(
        model_id=outcome.model_id,
        team_id=keys.team_id,
        site_id=keys.site_id,
        scope=keys.scope,
        model_type=outcome.model_type,
        model_version=int(outcome.model_version),
        training_dataset_id=outcome.training_dataset_id,
        training_dataset_version=int(outcome.training_dataset_version),
        feature_schema_version=outcome.feature_schema_version or FEATURE_SCHEMA_VERSION,
        training_date=outcome.training_date,
        metrics=metrics if metrics is not None else dict(outcome.metrics),
        status=STATUS_CANDIDATE,
        algorithm=outcome.algorithm,
        feature_names=list(outcome.feature_names),
        target_names=list(outcome.target_names),
        primary_target=outcome.primary_target,
        class_name=outcome.class_name,
        sample_count=int(outcome.sample_count),
        source_blast_ids=list(outcome.source_blast_ids),
        source_site_ids=list(source_site_ids),
        training_dataset_ids=list(dataset_ids),
        feature_ranges=dict(outcome.feature_ranges),
        training_matrix=[list(row) for row in outcome.training_matrix],
        prior_model_id=prior_model_id,
        prior_team_id=prior_team_id,
        prior_scope=prior_scope,
        adaptation=adaptation,
        estimators=dict(estimators if estimators is not None else outcome.estimators),
        prior_estimators=dict(prior_estimators or {}),
    )


def train_global(
    snapshots: Iterable[DatasetSnapshot],
    *,
    team_id: str,
    model_type: str,
    algorithm: str = DEFAULT_ALGORITHM,
    model_id: str = "",
    model_version: int = 1,
    training_date: str = "",
) -> LearnedModel:
    """Fit a tenant-scoped prior. Snapshots may cover several sites of this team."""
    team = require_team_id(team_id)
    frozen = assert_snapshots_for_scope(snapshots, team_id=team, scope=SCOPE_GLOBAL)
    pooled = pool_snapshots(frozen, team_id=team, scope=SCOPE_GLOBAL, name="global-prior")
    outcome = train_from_snapshot(
        pooled,
        model_type=model_type,
        algorithm=algorithm,
        model_id=str(model_id or "").strip() or uuid.uuid4().hex[:12],
        model_version=int(model_version),
        site_id=GLOBAL_SITE_ID,
        training_date=training_date or utc_now_iso(),
    )
    return _from_outcome(
        outcome,
        team_id=team,
        scope=SCOPE_GLOBAL,
        site_id=GLOBAL_SITE_ID,
        dataset_ids=[item.dataset_id for item in frozen],
        source_site_ids=_source_site_ids(pooled),
        adaptation=ADAPTATION_DIRECT,
    )


def _residual_metrics(y_true: np.ndarray, y_pred: np.ndarray) -> dict[str, float]:
    residual = y_true - y_pred
    mae = float(np.mean(np.abs(residual)))
    rmse = float(np.sqrt(np.mean(residual**2)))
    denom = float(np.sum((y_true - np.mean(y_true)) ** 2))
    r2 = 1.0 - float(np.sum(residual**2) / denom) if denom > 1e-12 else 0.0
    return {"mae": round(mae, 6), "rmse": round(rmse, 6), "r2": round(r2, 6)}


def _adapt_target(
    *,
    table: TargetTable,
    prior_estimator: Any | None,
    algorithm_name: str,
) -> tuple[Any, dict[str, Any], np.ndarray]:
    algo = get_algorithm(algorithm_name)
    X = np.asarray(table.X, dtype=float)
    y = np.asarray(table.y, dtype=float)
    if prior_estimator is None:
        estimator = algo.fit(X, y, random_state=42)
        return estimator, evaluate_table(estimator, algo.name, table), y

    prior_pred = np.asarray(algo.predict(prior_estimator, X), dtype=float)
    residual = y - prior_pred
    estimator = algo.fit(X, residual, random_state=42)
    adapted = prior_pred + np.asarray(algo.predict(estimator, X), dtype=float)
    metrics = {
        "n_samples": int(len(y)),
        **_residual_metrics(y, adapted),
        "prior_mae": _residual_metrics(y, prior_pred)["mae"],
        "metrics_split": "in_sample",
        "adaptation": ADAPTATION_RESIDUAL,
    }
    return estimator, metrics, adapted


def train_site(
    snapshots: Iterable[DatasetSnapshot],
    *,
    team_id: str,
    site_id: str,
    model_type: str,
    algorithm: str = DEFAULT_ALGORITHM,
    model_id: str = "",
    model_version: int = 1,
    training_date: str = "",
    prior: LearnedModel | None = None,
) -> LearnedModel:
    """Fit a site model. Optional global prior stays in the same tenant."""
    team = require_team_id(team_id)
    keys = isolation_keys(team, site_id, scope=SCOPE_SITE)
    frozen = assert_snapshots_for_scope(
        snapshots, team_id=team, scope=SCOPE_SITE, site_id=keys.site_id
    )
    pooled = pool_snapshots(
        frozen, team_id=team, scope=SCOPE_SITE, site_id=keys.site_id, name=f"site-{keys.site_id}"
    )
    model_type = normalize_model_type(model_type)
    if prior is not None:
        assert_prior_usable(prior, team_id=team)
        if prior.model_type != model_type:
            raise ValueError("Тип глобального prior не совпадает с типом модели площадки.")
        return _adapt_site(
            pooled,
            prior=prior,
            team_id=team,
            site_id=keys.site_id,
            model_type=model_type,
            algorithm=algorithm,
            model_id=model_id,
            model_version=model_version,
            training_date=training_date,
            dataset_ids=[item.dataset_id for item in frozen],
        )

    outcome = train_from_snapshot(
        pooled,
        model_type=model_type,
        algorithm=algorithm,
        model_id=str(model_id or "").strip() or uuid.uuid4().hex[:12],
        model_version=int(model_version),
        site_id=keys.site_id,
        training_date=training_date or utc_now_iso(),
    )
    return _from_outcome(
        outcome,
        team_id=team,
        scope=SCOPE_SITE,
        site_id=keys.site_id,
        dataset_ids=[item.dataset_id for item in frozen],
        source_site_ids=[keys.site_id],
        adaptation=ADAPTATION_DIRECT,
    )


def _adapt_site(
    snapshot: DatasetSnapshot,
    *,
    prior: LearnedModel,
    team_id: str,
    site_id: str,
    model_type: str,
    algorithm: str,
    model_id: str,
    model_version: int,
    training_date: str,
    dataset_ids: list[str],
) -> LearnedModel:
    spec = spec_for(model_type)
    tables = target_tables(snapshot, model_type)
    algo = get_algorithm(algorithm or prior.algorithm or DEFAULT_ALGORITHM)
    estimators: dict[str, Any] = {}
    per_target: dict[str, Any] = {}
    source_ids: list[str] = []
    feature_names: list[str] = list(prior.feature_names)
    max_samples = 0
    prior_estimators = copy.deepcopy(prior.estimators)

    for target in spec["targets"]:
        name = target["name"]
        table = tables[name]
        if not feature_names:
            feature_names = list(table.feature_names)
        if len(table.y) < MIN_TRAINING_SAMPLES:
            continue
        estimator, metrics, _adapted = _adapt_target(
            table=table,
            prior_estimator=prior_estimators.get(name),
            algorithm_name=algo.name,
        )
        estimators[name] = estimator
        per_target[name] = metrics
        for blast_id in table.source_blast_ids:
            if blast_id not in source_ids:
                source_ids.append(blast_id)
        max_samples = max(max_samples, len(table.y))

    if not estimators:
        available = ", ".join(f"{name}={len(table.y)}" for name, table in tables.items())
        raise ValueError(
            f"Для адаптации «{spec['class_name']}» на площадке «{site_id}» нужно не меньше "
            f"{MIN_TRAINING_SAMPLES} образцов, в снимке: {available or '0'}."
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
        "adaptation": ADAPTATION_RESIDUAL,
        "prior_model_id": prior.model_id,
    }
    primary = spec["primary_target"]
    if primary in per_target:
        metrics["n_samples"] = per_target[primary]["n_samples"]
        metrics["mae"] = per_target[primary]["mae"]
        metrics["rmse"] = per_target[primary]["rmse"]
        metrics["r2"] = per_target[primary]["r2"]

    matrix_source = tables.get(primary) if primary in estimators else None
    if matrix_source is None:
        matrix_source = next((tables[name] for name in estimators), None)
    feature_ranges = {}
    training_matrix: list[list[float]] = []
    if matrix_source is not None and matrix_source.X:
        feature_names = list(matrix_source.feature_names) or feature_names
        feature_ranges = ranges_to_dict(compute_feature_ranges(matrix_source.X, feature_names))
        training_matrix = [list(row) for row in matrix_source.X]

    return LearnedModel(
        model_id=str(model_id or "").strip() or uuid.uuid4().hex[:12],
        team_id=team_id,
        site_id=site_id,
        scope=SCOPE_SITE,
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
        source_site_ids=[site_id],
        training_dataset_ids=list(dataset_ids),
        feature_ranges=feature_ranges,
        training_matrix=training_matrix,
        prior_model_id=prior.model_id,
        prior_team_id=prior.team_id,
        prior_scope=prior.scope,
        adaptation=ADAPTATION_RESIDUAL,
        estimators=estimators,
        prior_estimators=prior_estimators,
    )
