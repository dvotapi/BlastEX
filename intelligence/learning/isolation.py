"""Tenant / site isolation for two-level learning.

Cross-tenant reads and writes fail closed. A site snapshot or model never
becomes training input for another tenant. Live passports are not a training
source.
"""
from __future__ import annotations

from typing import Any, Iterable

from intelligence.datasets.builder import DatasetSnapshot, TrainingSample
from intelligence.learning.types import (
    GLOBAL_SITE_ID,
    SCOPE_GLOBAL,
    SCOPE_SITE,
    IsolationKeys,
    LearnedModel,
    normalize_scope,
    normalize_site_id,
)


class IsolationError(ValueError):
    """Requested learning data crossed a tenant or site boundary."""


class CrossTenantError(IsolationError):
    """A team tried to read or write another team's snapshots or models."""


def require_team_id(team_id: str) -> str:
    text = str(team_id or "").strip()
    if not text:
        raise IsolationError("Для обучения и хранения модели нужен team_id.")
    return text


def require_site_id(site_id: str, *, scope: str = SCOPE_SITE) -> str:
    scope = normalize_scope(scope)
    text = normalize_site_id(site_id, scope=scope)
    if scope == SCOPE_SITE and not text:
        raise IsolationError("Для модели площадки нужен site_id.")
    if scope == SCOPE_GLOBAL:
        return GLOBAL_SITE_ID
    return text


def isolation_keys(team_id: str, site_id: str = "", *, scope: str = SCOPE_SITE) -> IsolationKeys:
    team = require_team_id(team_id)
    resolved_scope = normalize_scope(scope)
    site = require_site_id(site_id, scope=resolved_scope)
    return IsolationKeys(team_id=team, site_id=site, scope=resolved_scope)


def assert_same_tenant(expected_team: str, actual_team: str, *, resource: str = "ресурс") -> None:
    expected = require_team_id(expected_team)
    actual = str(actual_team or "").strip()
    if actual and actual != expected:
        raise CrossTenantError(
            f"Изоляция данных: {resource} принадлежит команде «{actual}», "
            f"а не «{expected}». Чтение и запись между арендаторами запрещены."
        )


def assert_model_tenant(model: LearnedModel, team_id: str) -> None:
    require_team_id(team_id)
    if not str(model.team_id or "").strip():
        raise IsolationError("У модели нет ключа изоляции team_id.")
    assert_same_tenant(team_id, model.team_id, resource=f"модель «{model.model_id}»")
    if model.prior_team_id:
        assert_same_tenant(team_id, model.prior_team_id, resource=f"prior «{model.prior_model_id}»")


def assert_prior_usable(prior: LearnedModel, *, team_id: str) -> None:
    assert_model_tenant(prior, team_id)
    if normalize_scope(prior.scope) != SCOPE_GLOBAL:
        raise IsolationError(
            f"Адаптация площадки стартует только от глобального prior, не от «{prior.scope}»."
        )


def sample_site_id(sample: TrainingSample) -> str:
    site = str(sample.site_id or "").strip()
    if site:
        return site
    provenance = sample.provenance or {}
    features = sample.features or {}
    return str(
        provenance.get("site_id")
        or (features.get("SITE") or {}).get("site_id")
        or ""
    ).strip()


def snapshot_site_ids(snapshot: DatasetSnapshot) -> list[str]:
    seen: list[str] = []
    header = str(snapshot.site_id or "").strip()
    if header and header not in seen:
        seen.append(header)
    for sample in snapshot.samples:
        site = sample_site_id(sample)
        if site and site not in seen:
            seen.append(site)
    return seen


def assert_training_snapshot(snapshot: Any) -> DatasetSnapshot:
    if isinstance(snapshot, DatasetSnapshot):
        if not snapshot.immutable:
            raise ValueError("Обучение разрешено только по неизменяемому снимку датасета.")
        return snapshot
    raise ValueError(
        "Обучение разрешено только по неизменяемому снимку датасета (BDX-011), "
        "никогда по живому паспорту БВР."
    )


def assert_snapshots_for_scope(
    snapshots: Iterable[DatasetSnapshot],
    *,
    team_id: str,
    scope: str,
    site_id: str = "",
) -> list[DatasetSnapshot]:
    require_team_id(team_id)
    scope = normalize_scope(scope)
    wanted_site = require_site_id(site_id, scope=scope) if scope == SCOPE_SITE else ""
    frozen: list[DatasetSnapshot] = []
    for item in snapshots:
        snapshot = assert_training_snapshot(item)
        sites = snapshot_site_ids(snapshot)
        if scope == SCOPE_SITE:
            foreign = [site for site in sites if site and site != wanted_site]
            if foreign:
                raise IsolationError(
                    f"Снимок «{snapshot.dataset_id}» содержит площадки {', '.join(foreign)} "
                    f"и не может обучать модель площадки «{wanted_site}»."
                )
            if snapshot.site_id and snapshot.site_id != wanted_site:
                raise IsolationError(
                    f"site_id снимка «{snapshot.dataset_id}» не совпадает с площадкой «{wanted_site}»."
                )
        frozen.append(snapshot)
    if not frozen:
        raise ValueError("Для обучения нужен хотя бы один неизменяемый снимок датасета.")
    return frozen
