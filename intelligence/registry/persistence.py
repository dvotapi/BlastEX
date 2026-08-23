"""Lifecycle overlay on top of existing model stores.

Overlay files live in ``data/teams/{team_id}/registry/`` and only store
promotion history plus staging/archived. Estimators stay in the original
calibration / outcomes / learning folders. This is not a second artifact tree.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from cost.persistence import team_dir
from intelligence.learning.isolation import CrossTenantError, require_team_id
from intelligence.registry.catalog import (
    RegistryNotFoundError,
    apply_source_status,
    list_source_records,
    record_from_source,
)
from intelligence.registry.lifecycle import plan_promotion
from intelligence.registry.types import (
    RegistryRecord,
    normalize_family,
    normalize_status,
)


class ImmutableRegistryError(Exception):
    """Registry overlay was tampered with or cannot be rewritten as an artifact."""


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def registry_dir(team_id: str) -> Path:
    return team_dir(require_team_id(team_id)) / "registry"


def _validate_model_id(model_id: str) -> None:
    if not model_id or model_id != Path(model_id).name or model_id in {".", ".."}:
        raise RegistryNotFoundError(f"Карточка реестра «{model_id}» не найдена.")


def overlay_path(team_id: str, family: str, model_id: str) -> Path:
    _validate_model_id(model_id)
    family = normalize_family(family)
    base = registry_dir(team_id).resolve()
    path = (base / f"{family}__{model_id}.json").resolve()
    if not path.is_relative_to(base):
        raise RegistryNotFoundError(f"Карточка реестра «{family}/{model_id}» не найдена.")
    return path


def load_overlay(team_id: str, family: str, model_id: str) -> dict[str, Any]:
    team = require_team_id(team_id)
    path = overlay_path(team, family, model_id)
    if not path.exists():
        return {}
    data = _read_json(path)
    stored_team = str(data.get("team_id", "") or "")
    if stored_team and stored_team != team:
        raise CrossTenantError(
            f"Карточка реестра «{family}/{model_id}» принадлежит команде «{stored_team}», "
            f"доступ команды «{team}» запрещён."
        )
    return data


def get_record(team_id: str, family: str, model_id: str) -> RegistryRecord:
    team = require_team_id(team_id)
    overlay = load_overlay(team, family, model_id)
    return record_from_source(team, family, model_id, overlay=overlay)


def list_records(
    team_id: str,
    *,
    family: str = "",
    status: str = "",
    site_id: str = "",
) -> list[RegistryRecord]:
    team = require_team_id(team_id)
    wanted_status = normalize_status(status) if status.strip() else ""
    wanted_site = site_id.strip()
    items: list[RegistryRecord] = []
    for item_family, model_id in list_source_records(team, family=family):
        try:
            record = get_record(team, item_family, model_id)
        except (RegistryNotFoundError, CrossTenantError):
            continue
        if wanted_status and record.status != wanted_status:
            continue
        if wanted_site and record.site_id != wanted_site:
            continue
        items.append(record)
    items.sort(key=lambda item: (item.training_date, item.model_version, item.model_id), reverse=True)
    return items


def promote(
    team_id: str,
    family: str,
    model_id: str,
    *,
    to_status: str,
    actor: str,
    confirm: bool,
    note: str = "",
) -> RegistryRecord:
    """Explicit human-gated promotion. Does not train. Never auto-deploys."""
    team = require_team_id(team_id)
    family = normalize_family(family)
    current = get_record(team, family, model_id)
    event = plan_promotion(
        from_status=current.status,
        to_status=to_status,
        actor=actor,
        confirm=confirm,
        note=note,
    )
    apply_source_status(team, family, model_id, event.to_status)
    overlay = load_overlay(team, family, model_id)
    history = list(overlay.get("transitions") or [])
    history.append(event.to_dict())
    payload = {
        "team_id": team,
        "family": family,
        "model_id": model_id,
        "status": event.to_status,
        "promoted_by": event.actor,
        "promoted_at": event.at,
        "checksum": current.checksum,
        "lineage": current.lineage.to_dict(),
        "transitions": history,
        "auto_deployed": False,
    }
    _write_json(overlay_path(team, family, model_id), payload)
    return get_record(team, family, model_id)
