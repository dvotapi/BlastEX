"""Drift checks emit alerts only. Never train. Never auto-deploy."""
from __future__ import annotations

from api.exceptions import (
    DriftIsolationError,
    DriftNotFoundError,
    ImmutableDriftError,
    InvalidDriftError,
)
from api.schemas.drift import (
    DriftAcknowledgeRequest,
    DriftAlertListResponse,
    DriftAlertSchema,
    DriftCheckRequest,
    DriftKindSchema,
    DriftMetaResponse,
    DriftMetricSchema,
    DriftReportListResponse,
    DriftReportSchema,
    DriftSeveritySchema,
)
from intelligence.drift.monitor import DriftCheckError, check_production_model
from intelligence.drift.persistence import (
    DriftNotFoundError as StoreNotFound,
    ImmutableDriftError as StoreImmutable,
    InvalidDriftError as StoreInvalid,
    acknowledge_alert,
    get_alert,
    get_report,
    list_alerts,
    list_reports,
)
from intelligence.drift.types import ACTION_ALERT_ONLY, ACTION_HUMAN_PROMOTE, DATA_ROLES, listed_kinds, listed_severities
from intelligence.learning.isolation import CrossTenantError, IsolationError
from intelligence.registry.catalog import RegistryNotFoundError as StoreRegistryMissing


def _metric_schema(item) -> DriftMetricSchema:
    return DriftMetricSchema(**item.to_dict())


def _alert_schema(item) -> DriftAlertSchema:
    payload = item.to_dict()
    payload["auto_deployed"] = False
    payload["auto_retrained"] = False
    payload["live_model_unchanged"] = True
    payload["action"] = ACTION_ALERT_ONLY
    return DriftAlertSchema(**payload)


def _report_schema(item) -> DriftReportSchema:
    payload = item.to_dict()
    payload["metrics"] = [_metric_schema(metric) for metric in item.metrics]
    payload["alerts"] = [_alert_schema(alert) for alert in item.alerts]
    payload["auto_deployed"] = False
    payload["auto_retrained"] = False
    payload["live_model_unchanged"] = True
    payload["action"] = ACTION_ALERT_ONLY
    payload["next_step"] = ACTION_HUMAN_PROMOTE
    payload["data_roles"] = dict(payload.get("data_roles") or DATA_ROLES)
    return DriftReportSchema(**payload)


def _translate_store(exc: Exception) -> Exception:
    if isinstance(exc, StoreNotFound):
        return DriftNotFoundError(str(exc))
    if isinstance(exc, StoreRegistryMissing):
        return DriftNotFoundError(str(exc))
    if isinstance(exc, StoreImmutable):
        return ImmutableDriftError(str(exc))
    if isinstance(exc, StoreInvalid):
        return InvalidDriftError(str(exc))
    if isinstance(exc, DriftCheckError):
        return InvalidDriftError(str(exc))
    if isinstance(exc, CrossTenantError):
        return DriftIsolationError(str(exc))
    if isinstance(exc, IsolationError):
        return DriftIsolationError(str(exc))
    if isinstance(exc, ValueError):
        return InvalidDriftError(str(exc))
    return exc


def catalog_meta() -> DriftMetaResponse:
    return DriftMetaResponse(
        kinds=[DriftKindSchema(**item) for item in listed_kinds()],
        severities=[DriftSeveritySchema(**item) for item in listed_severities()],
        data_roles=dict(DATA_ROLES),
        auto_deployed=False,
        auto_retrained=False,
        action=ACTION_ALERT_ONLY,
        next_step=ACTION_HUMAN_PROMOTE,
    )


def run_check(team_id: str, request: DriftCheckRequest) -> DriftReportSchema:
    try:
        report = check_production_model(
            team_id,
            request.family,
            request.model_id,
            current_dataset_id=request.current_dataset_id,
        )
    except Exception as exc:
        raise _translate_store(exc) from exc
    if report.auto_deployed or report.auto_retrained:
        raise InvalidDriftError("Мониторинг дрифта не деплоит и не переобучает live-модель.")
    if not report.live_model_unchanged:
        raise InvalidDriftError("Проверка дрифта не может менять live-модель.")
    return _report_schema(report)


def list_drift_reports(team_id: str, *, model_id: str = "", family: str = "") -> DriftReportListResponse:
    try:
        items = list_reports(team_id, model_id=model_id.strip(), family=family.strip())
    except Exception as exc:
        raise _translate_store(exc) from exc
    return DriftReportListResponse(
        items=[_report_schema(item) for item in items],
        auto_deployed=False,
        auto_retrained=False,
    )


def get_drift_report(team_id: str, report_id: str) -> DriftReportSchema:
    try:
        report = get_report(team_id, report_id)
    except Exception as exc:
        raise _translate_store(exc) from exc
    return _report_schema(report)


def list_drift_alerts(
    team_id: str,
    *,
    model_id: str = "",
    family: str = "",
    acknowledged: bool | None = None,
) -> DriftAlertListResponse:
    try:
        items = list_alerts(
            team_id,
            model_id=model_id.strip(),
            family=family.strip(),
            acknowledged=acknowledged,
        )
    except Exception as exc:
        raise _translate_store(exc) from exc
    return DriftAlertListResponse(
        items=[_alert_schema(item) for item in items],
        auto_deployed=False,
        auto_retrained=False,
    )


def get_drift_alert(team_id: str, alert_id: str) -> DriftAlertSchema:
    try:
        alert = get_alert(team_id, alert_id)
    except Exception as exc:
        raise _translate_store(exc) from exc
    return _alert_schema(alert)


def acknowledge_drift_alert(
    team_id: str,
    alert_id: str,
    request: DriftAcknowledgeRequest,
    *,
    actor: str,
) -> DriftAlertSchema:
    if request.confirm is not True:
        raise InvalidDriftError("Подтверждение сигнала требует явного confirm=true. Автодеплоя нет.")
    try:
        alert = acknowledge_alert(team_id, alert_id, actor=actor)
    except Exception as exc:
        raise _translate_store(exc) from exc
    return _alert_schema(alert)
