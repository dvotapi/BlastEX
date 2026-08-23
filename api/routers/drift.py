"""REST routes for drift monitoring. Alerts only — no auto-deploy."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from api.schemas.drift import (
    DriftAcknowledgeRequest,
    DriftAlertListResponse,
    DriftAlertSchema,
    DriftCheckRequest,
    DriftMetaResponse,
    DriftReportListResponse,
    DriftReportSchema,
)
from api.security import require_internal_access
from api.services import drift_service

router = APIRouter(prefix="/drift", tags=["drift"])


@router.get("/meta", response_model=DriftMetaResponse)
def drift_meta() -> DriftMetaResponse:
    return drift_service.catalog_meta()


@router.post("/check", response_model=DriftReportSchema)
def check_drift(
    request: DriftCheckRequest,
    session: dict = Depends(require_internal_access),
) -> DriftReportSchema:
    return drift_service.run_check(str(session["org"]), request)


@router.get("/reports", response_model=DriftReportListResponse)
def list_reports(
    family: str = "",
    model_id: str = "",
    session: dict = Depends(require_internal_access),
) -> DriftReportListResponse:
    return drift_service.list_drift_reports(str(session["org"]), family=family, model_id=model_id)


@router.get("/reports/{report_id}", response_model=DriftReportSchema)
def get_report(
    report_id: str,
    session: dict = Depends(require_internal_access),
) -> DriftReportSchema:
    return drift_service.get_drift_report(str(session["org"]), report_id)


@router.get("/alerts", response_model=DriftAlertListResponse)
def list_alerts(
    family: str = "",
    model_id: str = "",
    acknowledged: bool | None = None,
    session: dict = Depends(require_internal_access),
) -> DriftAlertListResponse:
    return drift_service.list_drift_alerts(
        str(session["org"]),
        family=family,
        model_id=model_id,
        acknowledged=acknowledged,
    )


@router.get("/alerts/{alert_id}", response_model=DriftAlertSchema)
def get_alert(
    alert_id: str,
    session: dict = Depends(require_internal_access),
) -> DriftAlertSchema:
    return drift_service.get_drift_alert(str(session["org"]), alert_id)


@router.post("/alerts/{alert_id}/acknowledge", response_model=DriftAlertSchema)
def acknowledge_alert(
    alert_id: str,
    request: DriftAcknowledgeRequest,
    session: dict = Depends(require_internal_access),
) -> DriftAlertSchema:
    return drift_service.acknowledge_drift_alert(
        str(session["org"]),
        alert_id,
        request,
        actor=str(session.get("sub") or ""),
    )
