"""Справочники Cost V1 для роутеров: одна зависимость вместо чтения файлов."""
from __future__ import annotations

from fastapi import Depends

from api.security import current_team_id
from api.services.economics_service import get_economics_repository
from cost.v2.legacy_adapter import LegacyReferences, legacy_references_from_snapshot
from cost.v2.repository import EconomicsRepository


def load_legacy_references(repository: EconomicsRepository, organization_id: str) -> LegacyReferences:
    """Опубликованная ревизия организации в структурах Cost V1."""

    return legacy_references_from_snapshot(repository.get_reference_snapshot(organization_id))


def current_legacy_references(
    organization_id: str = Depends(current_team_id),
    repository: EconomicsRepository = Depends(get_economics_repository),
) -> LegacyReferences:
    return load_legacy_references(repository, organization_id)
