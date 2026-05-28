"""Активные справочники команды из session_state."""
from __future__ import annotations

from typing import Any

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


def init_references_state(session_state: Any) -> None:
    if "work_object_records" not in session_state:
        session_state["work_object_records"] = work_objects_to_records(DEFAULT_WORK_OBJECTS)
    if "drill_rig_records" not in session_state:
        session_state["drill_rig_records"] = drill_rigs_to_records(DEFAULT_DRILL_RIGS)


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
