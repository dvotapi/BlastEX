"""Compare an observation window with a production model's training snapshot.

Alerts only. The function never trains, never calls registry promotion and
never swaps the live model.
"""
from __future__ import annotations

import uuid
from typing import Any, Iterable

from intelligence.datasets.builder import DatasetSnapshot
from intelligence.datasets.persistence import DatasetNotFoundError, load_snapshot
from intelligence.drift.extract import feature_series, prediction_series, stored_prediction_series, target_series
from intelligence.drift.scoring import score_snapshots
from intelligence.drift.statistics import compare_series
from intelligence.drift.types import (
    ACTION_ALERT_ONLY,
    ACTION_HUMAN_PROMOTE,
    DATA_ROLES,
    KIND_FEATURE,
    KIND_PREDICTION,
    KIND_TARGET,
    SEVERITY_ALERT,
    SEVERITY_OK,
    DriftAlert,
    DriftMetric,
    DriftReport,
    worse_severity,
    utc_now_iso,
)
from intelligence.learning.isolation import require_team_id
from intelligence.registry.persistence import get_record
from intelligence.registry.types import STATUS_PRODUCTION


class DriftCheckError(ValueError):
    """A drift check could not run without violating product rules."""


def new_report_id() -> str:
    return uuid.uuid4().hex[:12]


def new_alert_id() -> str:
    return uuid.uuid4().hex[:12]


def _require_immutable(snapshot: DatasetSnapshot) -> DatasetSnapshot:
    if not getattr(snapshot, "immutable", True):
        raise DriftCheckError("Дрифт считается только по неизменяемому снимку датасета, не по живому паспорту.")
    return snapshot


def _load_training_snapshots(team_id: str, dataset_ids: Iterable[str]) -> list[DatasetSnapshot]:
    snapshots: list[DatasetSnapshot] = []
    seen: set[str] = set()
    for dataset_id in dataset_ids:
        text = str(dataset_id or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        try:
            snapshots.append(_require_immutable(load_snapshot(team_id, text)))
        except DatasetNotFoundError as exc:
            raise DriftCheckError(str(exc)) from exc
    if not snapshots:
        raise DriftCheckError(
            "У производственной модели нет снимка обучения — дрифт сравнивать не с чем."
        )
    return snapshots


def compare_windows(
    baseline_snapshots: list[DatasetSnapshot],
    current_snapshots: list[DatasetSnapshot],
    *,
    baseline_scores: dict[str, list[float]] | None = None,
    current_scores: dict[str, list[float]] | None = None,
) -> list[DriftMetric]:
    """Compare feature / measured-target / prediction series. No unit conversion."""
    metrics: list[DriftMetric] = []
    channels = (
        (feature_series(baseline_snapshots), feature_series(current_snapshots)),
        (target_series(baseline_snapshots), target_series(current_snapshots)),
    )
    for baseline_map, current_map in channels:
        names = sorted(set(baseline_map) | set(current_map))
        for name in names:
            left = baseline_map.get(name)
            right = current_map.get(name)
            if not left or not right:
                continue
            if left["unit"] != right["unit"]:
                # Same semantic path but a different unit suffix — refuse to convert.
                continue
            item = compare_series(
                name,
                left["values"],
                right["values"],
                kind=left["kind"],
                role=left["role"],
                unit=left["unit"],
            )
            if item is not None:
                metrics.append(item)

    pred_left = prediction_series(baseline_scores or {})
    pred_right = prediction_series(current_scores or {})
    if not pred_left or not pred_right:
        pred_left = stored_prediction_series(baseline_snapshots)
        pred_right = stored_prediction_series(current_snapshots)
    for name in sorted(set(pred_left) | set(pred_right)):
        left = pred_left.get(name)
        right = pred_right.get(name)
        if not left or not right:
            continue
        if left["unit"] != right["unit"]:
            continue
        item = compare_series(
            name,
            left["values"],
            right["values"],
            kind=KIND_PREDICTION,
            role=left["role"],
            unit=left["unit"],
        )
        if item is not None:
            metrics.append(item)
    metrics.sort(key=lambda item: (item.kind, item.name))
    return metrics


def _alert_message(metric: DriftMetric) -> str:
    kind_ru = {
        KIND_FEATURE: "признаков",
        KIND_TARGET: "измеренных целей",
        KIND_PREDICTION: "прогнозов модели",
    }[metric.kind]
    detail = "; ".join(metric.reasons) if metric.reasons else "распределение сместилось"
    return (
        f"Дрифт {kind_ru} «{metric.name}» ({metric.role}): {detail}. "
        "Автодеплоя нет — продвижение только вручную в реестре моделей."
    )


def build_alerts(
    report: DriftReport,
    metrics: list[DriftMetric],
) -> list[DriftAlert]:
    alerts: list[DriftAlert] = []
    for metric in metrics:
        if metric.severity != SEVERITY_ALERT:
            continue
        alerts.append(
            DriftAlert(
                alert_id=new_alert_id(),
                team_id=report.team_id,
                family=report.family,
                model_id=report.model_id,
                kind=metric.kind,
                role=metric.role,
                metric_name=metric.name,
                severity=metric.severity,
                message=_alert_message(metric),
                report_id=report.report_id,
                site_id=report.site_id,
                created_at=report.created_at,
                auto_deployed=False,
                auto_retrained=False,
                live_model_unchanged=True,
                action=ACTION_ALERT_ONLY,
            )
        )
    return alerts


def check_production_model(
    team_id: str,
    family: str,
    model_id: str,
    *,
    current_dataset_id: str,
    persist: bool = True,
) -> DriftReport:
    """Compare current snapshot vs the training snapshot of a production model.

    Does not train. Does not promote. Does not swap the live artifact.
    """
    team = require_team_id(team_id)
    record = get_record(team, family, model_id)
    if record.status != STATUS_PRODUCTION:
        raise DriftCheckError(
            f"Дрифт считается относительно производственной модели, "
            f"статус «{record.status}» не подходит. Автодеплоя нет."
        )
    if record.team_id and record.team_id != team:
        raise DriftCheckError(
            f"Модель «{family}/{model_id}» принадлежит другой команде."
        )
    lineage_ids = list(record.lineage.training_dataset_ids or [])
    if record.lineage.training_dataset_id and record.lineage.training_dataset_id not in lineage_ids:
        lineage_ids.insert(0, record.lineage.training_dataset_id)
    baseline = _load_training_snapshots(team, lineage_ids)
    try:
        current = _require_immutable(load_snapshot(team, current_dataset_id))
    except DatasetNotFoundError as exc:
        raise DriftCheckError(str(exc)) from exc

    warnings: list[str] = []
    if current.dataset_id in {item.dataset_id for item in baseline}:
        warnings.append("Текущий снимок совпадает со снимком обучения — это контроль, не новый поток.")
    if (
        current.feature_schema_version
        and record.lineage.feature_schema_version
        and current.feature_schema_version != record.lineage.feature_schema_version
    ):
        warnings.append(
            f"Версия схемы признаков снимка ({current.feature_schema_version}) "
            f"отличается от обучения ({record.lineage.feature_schema_version})."
        )

    baseline_scores: dict[str, list[float]] = {}
    current_scores: dict[str, list[float]] = {}
    try:
        baseline_scores = score_snapshots(team, family, model_id, baseline)
        current_scores = score_snapshots(team, family, model_id, [current])
    except Exception as exc:  # scoring is optional; feature/target still run
        warnings.append(f"Прогнозный канал пропущен: {exc}")

    metrics = compare_windows(
        baseline,
        [current],
        baseline_scores=baseline_scores,
        current_scores=current_scores,
    )
    overall = SEVERITY_OK
    for metric in metrics:
        overall = worse_severity(overall, metric.severity)

    created = utc_now_iso()
    report = DriftReport(
        report_id=new_report_id(),
        team_id=team,
        family=record.family,
        model_id=record.model_id,
        model_checksum=record.checksum,
        model_status=record.status,
        training_dataset_ids=[item.dataset_id for item in baseline],
        training_dataset_version=record.lineage.training_dataset_version,
        current_dataset_id=current.dataset_id,
        current_dataset_version=current.dataset_version,
        feature_schema_version=record.lineage.feature_schema_version or current.feature_schema_version,
        site_id=record.site_id or current.site_id,
        created_at=created,
        overall_severity=overall,
        metrics=metrics,
        warnings=warnings,
        data_roles=dict(DATA_ROLES),
        auto_deployed=False,
        auto_retrained=False,
        live_model_unchanged=True,
        action=ACTION_ALERT_ONLY,
        next_step=ACTION_HUMAN_PROMOTE,
    )
    report.alerts = build_alerts(report, metrics)

    after = get_record(team, family, model_id)
    if after.status != STATUS_PRODUCTION or after.checksum != record.checksum:
        raise DriftCheckError(
            "Проверка дрифта изменила live-модель — это запрещено. Автодеплоя нет."
        )
    report.live_model_unchanged = True
    report.auto_deployed = False
    report.auto_retrained = False

    if persist:
        from intelligence.drift.persistence import save_report

        return save_report(team, report)
    return report
