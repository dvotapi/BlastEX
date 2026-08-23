"""Apply a hole-level residual model as a PREDICTED overlay.

The result never writes designed charges or the approved pattern.
"""
from __future__ import annotations

from typing import Any

import numpy as np

from design.models import BlastDesign
from intelligence.calibration.algorithms import get_algorithm
from intelligence.spatial.features import extract_hole_observations, vectorize_hole
from intelligence.spatial.maps import spatial_maps
from intelligence.spatial.residuals import apply_residuals, neighborhood_from_holes, physics_residuals
from intelligence.spatial.types import (
    APPLIED_AS_OVERLAY,
    FEATURE_SCHEMA_VERSION,
    METRIC_OVERSIZE,
    METRIC_TOE,
    METRIC_X50,
    RESIDUAL_METRICS,
    ROLE_PREDICTED,
    STATUS_CANDIDATE,
    STATUS_PRODUCTION,
    SpatialModel,
    SpatialOverlay,
)


def _warnings_for(model: SpatialModel | None) -> list[str]:
    warnings = [
        "Прогноз скважинного уровня — слой predicted. Заряды и утверждённая сетка не изменяются.",
    ]
    if model is None:
        warnings.insert(0, "Пространственная модель не выбрана: остатки распределены по локальной физике.")
        return warnings
    if model.status == STATUS_CANDIDATE:
        warnings.append("Модель в статусе candidate: рекомендация, не производственный расчёт.")
    if model.status != STATUS_PRODUCTION:
        warnings.append("Пространственная модель не утверждена как production и не подменяет проект БВР.")
    return warnings


def _block_from_request(
    block: dict[str, Any] | None,
    observations,
) -> dict[str, float | None]:
    payload = dict(block or {})
    out: dict[str, float | None] = {}
    aliases = {
        METRIC_X50: ("x50_mm", "x50", "predicted_x50_mm"),
        METRIC_OVERSIZE: ("oversize_pct", "oversize", "predicted_oversize_pct"),
        METRIC_TOE: ("toe_probability", "toe", "predicted_toe_probability"),
    }
    for metric, names in aliases.items():
        value = None
        for name in names:
            if payload.get(name) not in (None, ""):
                value = float(payload[name])
                break
        if value is None:
            nums = [
                float(item.predicted[metric])
                for item in observations
                if (item.predicted or {}).get(metric) is not None
            ]
            value = (sum(nums) / len(nums)) if nums else None
        out[metric] = value
    return out


def apply_model(
    design: BlastDesign,
    *,
    model: SpatialModel | None = None,
    site_id: str = "",
    block: dict[str, Any] | None = None,
    neighbor_k: int | None = None,
) -> SpatialOverlay:
    """Hole / neighborhood predicted overlay. Design is untouched."""
    k = int(neighbor_k or (model.neighbor_k if model is not None else 4))
    before = (
        [hole.to_dict() for hole in design.holes],
        [load.to_dict() for load in design.loads],
    )
    observations = extract_hole_observations(
        design,
        site_id=site_id or (model.site_id if model else ""),
        neighbor_k=k,
        include_physics=True,
    )
    block_pred = _block_from_request(block, observations)
    residuals: dict[str, list[float | None]]
    if model is not None and model.estimators:
        algo = get_algorithm(model.algorithm)
        residuals = {name: [] for name in RESIDUAL_METRICS}
        for item in observations:
            vector = np.asarray([vectorize_hole(item, model.feature_names)], dtype=float)
            for name in RESIDUAL_METRICS:
                estimator = model.estimators.get(name)
                if estimator is None:
                    residuals[name].append(None)
                    continue
                residuals[name].append(float(algo.predict(estimator, vector)[0]))
    else:
        residuals = physics_residuals(observations)
    holes = apply_residuals(observations, residuals, block=block_pred)
    neighborhoods = neighborhood_from_holes(holes, observations)
    after = (
        [hole.to_dict() for hole in design.holes],
        [load.to_dict() for load in design.loads],
    )
    if after != before:
        raise RuntimeError("Пространственный прогноз не должен менять проектные скважины или заряды.")
    return SpatialOverlay(
        holes=holes,
        neighborhoods=neighborhoods,
        maps=spatial_maps(holes),
        block=block_pred,
        model_id=model.model_id if model else "",
        team_id=model.team_id if model else "",
        site_id=site_id or (model.site_id if model else ""),
        model_version=model.model_version if model else 0,
        training_dataset_version=model.training_dataset_version if model else 0,
        feature_schema_version=model.feature_schema_version if model else FEATURE_SCHEMA_VERSION,
        algorithm=model.algorithm if model else "",
        status=model.status if model else "",
        hole_count=len(holes),
        applied_as=APPLIED_AS_OVERLAY,
        modifies_design=False,
        prediction_applied=True,
        warnings=_warnings_for(model),
        role=ROLE_PREDICTED,
    )


def empty_overlay(*, site_id: str = "", reason: str = "") -> SpatialOverlay:
    warnings = ["Пространственный прогноз не применён: нет скважин или модели."]
    if reason:
        warnings.insert(0, reason)
    warnings.append("Прогноз скважинного уровня — слой predicted. Заряды и утверждённая сетка не изменяются.")
    return SpatialOverlay(
        holes=[],
        neighborhoods=[],
        maps=spatial_maps([]),
        block={METRIC_X50: None, METRIC_OVERSIZE: None, METRIC_TOE: None},
        site_id=site_id,
        prediction_applied=False,
        warnings=warnings,
        role=ROLE_PREDICTED,
    )
