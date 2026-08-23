"""Read existing BDX-012 / 013 / 019 artifacts as registry cards.

Does not copy estimators. Checksum and dataset lineage come from the
write-once metadata of the original store.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from intelligence.calibration import persistence as calibration_store
from intelligence.learning import persistence as learning_store
from intelligence.learning.isolation import CrossTenantError, IsolationError, require_team_id
from intelligence.outcomes import persistence as outcome_store
from intelligence.registry.types import (
    DATA_ROLES,
    FAMILY_CALIBRATION,
    FAMILY_LEARNING,
    FAMILY_OUTCOMES,
    DatasetLineage,
    PromotionEvent,
    RegistryRecord,
    allowed_transitions,
    effective_status,
    normalize_family,
    normalize_source_status,
)


class RegistryNotFoundError(Exception):
    """No artifact with this family/id exists in the tenant store."""


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _metadata_path(team_id: str, family: str, model_id: str) -> Path:
    family = normalize_family(family)
    try:
        if family == FAMILY_CALIBRATION:
            return calibration_store.metadata_path(team_id, model_id)
        if family == FAMILY_OUTCOMES:
            return outcome_store.metadata_path(team_id, model_id)
        return learning_store.metadata_path(team_id, model_id)
    except (calibration_store.CalibrationNotFoundError, outcome_store.OutcomeNotFoundError, learning_store.LearningNotFoundError) as exc:
        raise RegistryNotFoundError(str(exc)) from exc


def _load_source_metadata(team_id: str, family: str, model_id: str) -> dict[str, Any]:
    path = _metadata_path(team_id, family, model_id)
    if not path.exists():
        raise RegistryNotFoundError(
            f"Модель «{family}/{model_id}» не найдена в хранилище команды."
        )
    try:
        data = _read_json(path)
    except (OSError, json.JSONDecodeError) as exc:
        raise RegistryNotFoundError(
            f"Модель «{family}/{model_id}» не найдена в хранилище команды."
        ) from exc
    stored_team = str(data.get("team_id", "") or "")
    if stored_team and stored_team != team_id:
        raise CrossTenantError(
            f"Модель «{family}/{model_id}» принадлежит команде «{stored_team}», "
            f"доступ команды «{team_id}» запрещён."
        )
    return data


def _list_source_ids(team_id: str, family: str) -> list[str]:
    family = normalize_family(family)
    if family == FAMILY_CALIBRATION:
        return [item.model_id for item in calibration_store.list_models(team_id)]
    if family == FAMILY_OUTCOMES:
        return [item.model_id for item in outcome_store.list_models(team_id)]
    return [item.model_id for item in learning_store.list_models(team_id)]


def _lineage_from_metadata(data: dict[str, Any]) -> DatasetLineage:
    return DatasetLineage.from_dict(data)


def record_from_source(
    team_id: str,
    family: str,
    model_id: str,
    *,
    overlay: dict[str, Any] | None = None,
) -> RegistryRecord:
    team = require_team_id(team_id)
    family = normalize_family(family)
    data = _load_source_metadata(team, family, model_id)
    source_status = normalize_source_status(str(data.get("status", "") or "candidate"))
    overlay_status = str((overlay or {}).get("status", "") or "")
    status = effective_status(source_status, overlay_status)
    transitions = list((overlay or {}).get("transitions") or [])
    promoted_by = str((overlay or {}).get("promoted_by", "") or "")
    promoted_at = str((overlay or {}).get("promoted_at", "") or "")
    if not promoted_by and transitions:
        last = transitions[-1]
        promoted_by = str(last.get("actor", "") or "")
        promoted_at = str(last.get("at", "") or "")
    scope = str(data.get("scope", "") or "")
    if not scope:
        scope = "site" if family != FAMILY_LEARNING else "global"
    return RegistryRecord(
        family=family,
        model_id=str(data.get("model_id", model_id) or model_id),
        team_id=str(data.get("team_id", team) or team),
        site_id=str(data.get("site_id", "") or ""),
        scope=scope,
        model_type=str(data.get("model_type", "") or ""),
        class_name=str(data.get("class_name", "") or ""),
        model_version=int(data.get("model_version", 0) or 0),
        status=status,
        source_status=source_status,
        checksum=str(data.get("artifact_sha256", "") or ""),
        lineage=_lineage_from_metadata(data),
        training_date=str(data.get("training_date", "") or ""),
        algorithm=str(data.get("algorithm", "") or ""),
        sample_count=int(data.get("sample_count", 0) or 0),
        promoted_by=promoted_by,
        promoted_at=promoted_at,
        transitions=[PromotionEvent.from_dict(item) for item in transitions],
        allowed_transitions=allowed_transitions(status),
        auto_deployed=False,
        data_roles=dict(DATA_ROLES),
    )


def list_source_records(team_id: str, *, family: str = "") -> list[tuple[str, str]]:
    team = require_team_id(team_id)
    families = [normalize_family(family)] if family.strip() else list(
        (FAMILY_CALIBRATION, FAMILY_OUTCOMES, FAMILY_LEARNING)
    )
    pairs: list[tuple[str, str]] = []
    for item_family in families:
        for model_id in _list_source_ids(team, item_family):
            pairs.append((item_family, model_id))
    return pairs


def apply_source_status(team_id: str, family: str, model_id: str, registry_status: str) -> str:
    """Write the mapped candidate/production/retired status back to the source."""
    from intelligence.registry.types import source_status_for

    team = require_team_id(team_id)
    family = normalize_family(family)
    mapped = source_status_for(registry_status)
    try:
        if family == FAMILY_CALIBRATION:
            calibration_store.set_status(team, model_id, mapped)
        elif family == FAMILY_OUTCOMES:
            outcome_store.set_status(team, model_id, mapped)
        else:
            learning_store.set_status(team, model_id, mapped)
    except (
        calibration_store.CalibrationNotFoundError,
        outcome_store.OutcomeNotFoundError,
        learning_store.LearningNotFoundError,
    ) as exc:
        raise RegistryNotFoundError(str(exc)) from exc
    except IsolationError:
        raise
    return mapped
