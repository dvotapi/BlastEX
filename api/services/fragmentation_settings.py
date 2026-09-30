"""Настройки модели Kuz-Ram для прогнозов «Проектирования»: откуда их взять.

Расчётный слой в базу не ходит — настройки достаёт API. Порядок: явные
настройки из запроса → блок kuzram черновика листа «Расчёт» (таблица
calc_object_inputs) для объекта из запроса, а без него — для активного
объекта организации → умолчания. Третьего набора настроек нет: C(A) и
остальное «Проектирование» берёт ровно оттуда, откуда их берёт лист «Расчёт».
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any

from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError

from api.schemas.blast import KuzRamSettingsSchema
from cost.v2.repository import EconomicsRepository, EconomicsRepositoryError
from design.scenarios.types import ScenarioParams
from simulation.fragmentation.base import (
    SETTINGS_SOURCE_DEFAULTS,
    SETTINGS_SOURCE_REQUEST,
    SETTINGS_SOURCE_WORK_OBJECT,
    settings_snapshot,
)
from simulation.fragmentation.cunningham import KuzRamSettings


@dataclass(frozen=True)
class ResolvedSettings:
    settings: KuzRamSettings
    source: str
    work_object_name: str = ""
    warnings: tuple[str, ...] = ()

    def source_payload(self) -> dict[str, Any]:
        """Источник для settings_snapshot движка."""
        return {"source": self.source, "work_object_name": self.work_object_name, "warnings": list(self.warnings)}


def _defaults(work_object_name: str = "", warning: str = "") -> ResolvedSettings:
    return ResolvedSettings(
        KuzRamSettings(), SETTINGS_SOURCE_DEFAULTS, work_object_name, (warning,) if warning else ()
    )


def _settings_from_block(block: dict[str, Any]) -> KuzRamSettings:
    """Блок kuzram листа → настройки. Факты взрывов и прочие ключи отбрасываются."""
    values = {key: block[key] for key in KuzRamSettingsSchema.model_fields if key in block}
    return KuzRamSettingsSchema(**values).to_settings()


def resolve_kuzram_settings(
    *,
    explicit: KuzRamSettings | None,
    work_object_name: str,
    organization_id: str | None,
    repository: EconomicsRepository | None,
) -> ResolvedSettings:
    """Настройки для прогноза и их источник; ошибки хранилища — предупреждение, не отказ."""
    if explicit is not None:
        return ResolvedSettings(explicit, SETTINGS_SOURCE_REQUEST)
    if not organization_id or repository is None:
        return _defaults()
    name = (work_object_name or "").strip()
    try:
        if not name:
            workspace = repository.get_legacy_workspace(organization_id)
            name = (workspace.active_work_object_name if workspace else "").strip()
        if not name:
            return _defaults()
        stored = repository.get_calc_inputs(organization_id, name)
    except (EconomicsRepositoryError, SQLAlchemyError) as exc:
        label = f"объекта работ «{name}»" if name else "активного объекта работ"
        return _defaults(name, f"Настройки модели {label} недоступны: {exc}. Взяты умолчания.")
    block = (stored.inputs or {}).get("kuzram") if stored is not None else None
    if not isinstance(block, dict):
        # У объекта нет сохранённых настроек модели: лист «Расчёт» в этом
        # случае тоже считает по умолчаниям.
        return _defaults(name)
    try:
        settings = _settings_from_block(block)
    except ValidationError as exc:
        reason = "; ".join(str(error["msg"]) for error in exc.errors())
        return _defaults(name, f"Настройки модели объекта работ «{name}» не прочитаны ({reason}). Взяты умолчания.")
    return ResolvedSettings(settings, SETTINGS_SOURCE_WORK_OBJECT, name)


def with_scenario_settings(
    params: ScenarioParams,
    *,
    organization_id: str | None,
    repository: EconomicsRepository | None,
) -> ScenarioParams:
    """Параметры сценария со снимком применённых настроек Kuz-Ram.

    Снимок всегда пересчитывается: присланному клиентом сервер не доверяет,
    явные настройки клиент передаёт полем kuzram.
    """
    explicit = KuzRamSettingsSchema(**params.kuzram).to_settings() if params.kuzram else None
    resolved = resolve_kuzram_settings(
        explicit=explicit,
        work_object_name=params.work_object_name,
        organization_id=organization_id,
        repository=repository,
    )
    return replace(params, kuzram_settings=settings_snapshot(resolved.settings, resolved.source_payload()))
