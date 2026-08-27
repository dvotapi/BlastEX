"""Tenant-isolated storage for drift reports and alerts.

Reports are write-once. Alerts may be acknowledged by a human. Nothing here
promotes a model or starts a training run.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from cost.persistence import team_dir
from intelligence.drift.types import (
    ACTION_ALERT_ONLY,
    AUTO_ACTORS,
    DriftAlert,
    DriftReport,
    utc_now_iso,
)
from intelligence.learning.isolation import CrossTenantError, IsolationError, require_team_id


class DriftNotFoundError(Exception):
    """Report or alert is not in the tenant store."""


class ImmutableDriftError(Exception):
    """A write-once drift report cannot be overwritten."""


class InvalidDriftError(ValueError):
    """Acknowledge / lookup broke a product rule."""


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def drift_dir(team_id: str) -> Path:
    return team_dir(require_team_id(team_id)) / "drift"


def reports_dir(team_id: str) -> Path:
    return drift_dir(team_id) / "reports"


def alerts_dir(team_id: str) -> Path:
    return drift_dir(team_id) / "alerts"


def _validate_id(value: str, *, kind: str) -> str:
    text = str(value or "").strip()
    if not text or text != Path(text).name or text in {".", ".."}:
        raise DriftNotFoundError(f"{kind} «{value}» не найден.")
    return text


def report_path(team_id: str, report_id: str) -> Path:
    report_id = _validate_id(report_id, kind="Отчёт дрифта")
    base = reports_dir(team_id).resolve()
    path = (base / f"{report_id}.json").resolve()
    if not path.is_relative_to(base):
        raise DriftNotFoundError(f"Отчёт дрифта «{report_id}» не найден.")
    return path


def alert_path(team_id: str, alert_id: str) -> Path:
    alert_id = _validate_id(alert_id, kind="Сигнал дрифта")
    base = alerts_dir(team_id).resolve()
    path = (base / f"{alert_id}.json").resolve()
    if not path.is_relative_to(base):
        raise DriftNotFoundError(f"Сигнал дрифта «{alert_id}» не найден.")
    return path


def _assert_team(payload: dict[str, Any], team_id: str, *, resource: str) -> None:
    stored = str(payload.get("team_id", "") or "")
    if stored and stored != team_id:
        raise CrossTenantError(
            f"{resource} принадлежит команде «{stored}», доступ команды «{team_id}» запрещён."
        )


def save_report(team_id: str, report: DriftReport) -> DriftReport:
    team = require_team_id(team_id)
    if report.team_id and report.team_id != team:
        raise CrossTenantError(
            f"Отчёт дрифта принадлежит команде «{report.team_id}», "
            f"запись от команды «{team}» запрещена."
        )
    report.team_id = team
    report.auto_deployed = False
    report.auto_retrained = False
    report.live_model_unchanged = True
    report.action = ACTION_ALERT_ONLY
    path = report_path(team, report.report_id)
    if path.exists():
        raise ImmutableDriftError(
            f"Отчёт дрифта «{report.report_id}» уже сохранён и не может быть перезаписан."
        )
    payload = report.to_dict()
    _write_json(path, payload)
    for alert in report.alerts:
        alert.team_id = team
        alert.report_id = report.report_id
        _write_json(alert_path(team, alert.alert_id), alert.to_dict())
    return DriftReport.from_dict(payload)


def get_report(team_id: str, report_id: str) -> DriftReport:
    team = require_team_id(team_id)
    path = report_path(team, report_id)
    if not path.exists():
        raise DriftNotFoundError(f"Отчёт дрифта «{report_id}» не найден.")
    data = _read_json(path)
    _assert_team(data, team, resource=f"Отчёт дрифта «{report_id}»")
    return DriftReport.from_dict(data)


def list_reports(team_id: str, *, model_id: str = "", family: str = "") -> list[DriftReport]:
    team = require_team_id(team_id)
    folder = reports_dir(team)
    folder.mkdir(parents=True, exist_ok=True)
    items: list[DriftReport] = []
    for path in sorted(folder.glob("*.json")):
        try:
            data = _read_json(path)
        except (OSError, json.JSONDecodeError):
            continue
        try:
            _assert_team(data, team, resource=f"Отчёт дрифта «{path.stem}»")
        except CrossTenantError:
            continue
        report = DriftReport.from_dict(data)
        if model_id and report.model_id != model_id:
            continue
        if family and report.family != family:
            continue
        items.append(report)
    items.sort(key=lambda item: item.created_at, reverse=True)
    return items


def get_alert(team_id: str, alert_id: str) -> DriftAlert:
    team = require_team_id(team_id)
    path = alert_path(team, alert_id)
    if not path.exists():
        raise DriftNotFoundError(f"Сигнал дрифта «{alert_id}» не найден.")
    data = _read_json(path)
    _assert_team(data, team, resource=f"Сигнал дрифта «{alert_id}»")
    return DriftAlert.from_dict(data)


def list_alerts(
    team_id: str,
    *,
    model_id: str = "",
    family: str = "",
    acknowledged: bool | None = None,
) -> list[DriftAlert]:
    team = require_team_id(team_id)
    folder = alerts_dir(team)
    folder.mkdir(parents=True, exist_ok=True)
    items: list[DriftAlert] = []
    for path in sorted(folder.glob("*.json")):
        try:
            data = _read_json(path)
        except (OSError, json.JSONDecodeError):
            continue
        try:
            _assert_team(data, team, resource=f"Сигнал дрифта «{path.stem}»")
        except CrossTenantError:
            continue
        alert = DriftAlert.from_dict(data)
        if model_id and alert.model_id != model_id:
            continue
        if family and alert.family != family:
            continue
        if acknowledged is not None and bool(alert.acknowledged) != bool(acknowledged):
            continue
        items.append(alert)
    items.sort(key=lambda item: item.created_at, reverse=True)
    return items


def acknowledge_alert(team_id: str, alert_id: str, *, actor: str) -> DriftAlert:
    """Human acknowledgement. Does not retrain or promote the live model."""
    team = require_team_id(team_id)
    who = str(actor or "").strip()
    if who.lower() in AUTO_ACTORS:
        raise InvalidDriftError(
            "Подтверждение сигнала дрифта только вручную: системные акторы запрещены."
        )
    alert = get_alert(team, alert_id)
    alert.acknowledged = True
    alert.acknowledged_by = who
    alert.acknowledged_at = utc_now_iso()
    alert.auto_deployed = False
    alert.auto_retrained = False
    alert.live_model_unchanged = True
    alert.action = ACTION_ALERT_ONLY
    _write_json(alert_path(team, alert.alert_id), alert.to_dict())
    return alert


def require_team(team_id: str) -> str:
    try:
        return require_team_id(team_id)
    except IsolationError:
        raise
