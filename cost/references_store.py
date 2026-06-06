"""Активные справочники команды из session_state."""
from __future__ import annotations

from typing import Any

from Blast import RockProperties

from cost.drilling_data import (
    DEFAULT_DRILL_RIGS,
    DEFAULT_WORK_OBJECTS,
    DrillRig,
    WorkObject,
    drill_rigs_from_records,
    drill_rigs_to_records,
    work_objects_from_records,
    work_objects_to_records,
)
from cost.depreciation_data import (
    DEFAULT_DEPRECIATION_ASSETS,
    FixedAssetDepreciation,
    depreciation_assets_from_records,
    depreciation_assets_to_records,
    find_depreciation_asset,
)
from cost.explosive_data import (
    DEFAULT_EXPLOSIVES,
    ExplosiveCatalogItem,
    explosives_from_records,
    explosives_to_records,
    find_explosive,
)
from cost.rock_data import DEFAULT_ROCKS, find_rock, rocks_from_records, rocks_to_records


def init_references_state(session_state: Any) -> None:
    if "work_object_records" not in session_state:
        session_state["work_object_records"] = work_objects_to_records(DEFAULT_WORK_OBJECTS)
    if "drill_rig_records" not in session_state:
        session_state["drill_rig_records"] = drill_rigs_to_records(DEFAULT_DRILL_RIGS)
    if "rock_records" not in session_state:
        session_state["rock_records"] = rocks_to_records(DEFAULT_ROCKS)
    if "explosive_records" not in session_state:
        session_state["explosive_records"] = explosives_to_records(DEFAULT_EXPLOSIVES)
    if "depreciation_asset_records" not in session_state:
        session_state["depreciation_asset_records"] = depreciation_assets_to_records(
            DEFAULT_DEPRECIATION_ASSETS
        )


def get_depreciation_assets(session_state: Any) -> list[FixedAssetDepreciation]:
    init_references_state(session_state)
    assets = depreciation_assets_from_records(list(session_state["depreciation_asset_records"]))
    return assets or list(DEFAULT_DEPRECIATION_ASSETS)


def find_depreciation_asset_by_name(
    session_state: Any,
    name: str,
) -> FixedAssetDepreciation | None:
    return find_depreciation_asset(name, get_depreciation_assets(session_state))


def get_explosives(session_state: Any) -> list[ExplosiveCatalogItem]:
    init_references_state(session_state)
    items = explosives_from_records(list(session_state["explosive_records"]))
    return items or list(DEFAULT_EXPLOSIVES)


def get_explosives_dict(session_state: Any) -> dict[str, ExplosiveCatalogItem]:
    return {item.key: item for item in get_explosives(session_state)}


def find_explosive_by_key(session_state: Any, key: str) -> ExplosiveCatalogItem | None:
    return find_explosive(key, get_explosives(session_state))


def get_rocks(session_state: Any) -> list[RockProperties]:
    init_references_state(session_state)
    rocks = rocks_from_records(list(session_state["rock_records"]))
    return rocks or list(DEFAULT_ROCKS)


def get_rocks_dict(session_state: Any) -> dict[str, RockProperties]:
    return {rock.name: rock for rock in get_rocks(session_state)}


def find_rock_by_name(session_state: Any, name: str) -> RockProperties | None:
    return find_rock(name, get_rocks(session_state))


def get_work_objects(session_state: Any) -> list[WorkObject]:
    init_references_state(session_state)
    objects = work_objects_from_records(list(session_state["work_object_records"]))
    return objects or list(DEFAULT_WORK_OBJECTS)


def get_drill_rigs(session_state: Any) -> list[DrillRig]:
    init_references_state(session_state)
    rigs = drill_rigs_from_records(list(session_state["drill_rig_records"]))
    return rigs or list(DEFAULT_DRILL_RIGS)


def find_work_object(session_state: Any, name: str) -> WorkObject | None:
    from cost.drilling_data import find_object

    return find_object(name, get_work_objects(session_state))


def find_drill_rig(session_state: Any, name: str) -> DrillRig:
    from cost.drilling_data import find_rig

    return find_rig(name, get_drill_rigs(session_state))
