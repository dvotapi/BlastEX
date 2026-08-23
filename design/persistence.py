"""Сохранение и загрузка паспортов БВР по командам.

Зеркалит устройство `cost/persistence.py`: файлы лежат в
`data/teams/{team_id}/designs/{design_id}.json`, тот же `data/teams/` уже
исключён из git (`.gitignore`), сериализация — обычный JSON без сжатия.

BDX-025: запись уважает lifecycle. Утверждённый и закрытый паспорт нельзя
тихо переписать сценарием, оптимизацией или ML-оверлеем.
"""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from cost.persistence import team_dir
from design.lifecycle import (
    FrozenDesignError,
    KIND_CREATED,
    KIND_FORK,
    KIND_RECORD_EXECUTION,
    KIND_RECORD_MEASURED,
    KIND_RENAME,
    KIND_REVISE,
    MUTATION_DESIGNED,
    MUTATION_EXECUTION,
    MUTATION_MEASURED,
    MUTATION_METADATA,
    STATUS_DRAFT,
    assert_mutations_allowed,
    can_delete,
    classify_mutations,
    designed_sha256,
    make_event,
    normalize_status,
    plan_transition,
    utc_now_iso,
)
from design.models import DESIGN_VERSION, BlastDesign

__all__ = [
    "DesignNotFoundError",
    "DesignSummary",
    "designs_dir",
    "design_path",
    "ensure_designs_layout",
    "new_design_id",
    "list_designs",
    "load_design",
    "save_design",
    "delete_design",
    "rename_design",
    "transition_design",
    "fork_design",
]


class DesignNotFoundError(Exception):
    """Паспорт БВР с указанным id не найден в хранилище команды."""


@dataclass
class DesignSummary:
    design_id: str
    name: str
    updated_at: str
    hole_count: int
    lifecycle_status: str = STATUS_DRAFT
    revision: int = 0
    designed_sha256: str = ""
    parent_design_id: str = ""


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def designs_dir(team_id: str) -> Path:
    return team_dir(team_id) / "designs"


def _validate_design_id(design_id: str) -> None:
    if not design_id or design_id != Path(design_id).name or design_id in {".", ".."}:
        raise DesignNotFoundError(f"Паспорт БВР «{design_id}» не найден.")


def design_path(team_id: str, design_id: str) -> Path:
    _validate_design_id(design_id)
    base = designs_dir(team_id).resolve()
    path = (base / f"{design_id}.json").resolve()
    if not path.is_relative_to(base):
        raise DesignNotFoundError(f"Паспорт БВР «{design_id}» не найден.")
    return path


def ensure_designs_layout(team_id: str) -> None:
    designs_dir(team_id).mkdir(parents=True, exist_ok=True)


def new_design_id() -> str:
    return uuid.uuid4().hex[:12]


def list_designs(team_id: str) -> list[DesignSummary]:
    ensure_designs_layout(team_id)
    summaries: list[DesignSummary] = []
    for path in sorted(designs_dir(team_id).glob("*.json")):
        try:
            data = _read_json(path)
        except (OSError, json.JSONDecodeError):
            continue
        summaries.append(
            DesignSummary(
                design_id=str(data.get("design_id", path.stem)),
                name=str(data.get("name", path.stem)),
                updated_at=str(data.get("updated_at", "")),
                hole_count=len(data.get("holes", [])),
                lifecycle_status=normalize_status(data.get("lifecycle_status", STATUS_DRAFT)),
                revision=int(data.get("revision", 0) or 0),
                designed_sha256=str(data.get("designed_sha256", "") or ""),
                parent_design_id=str(data.get("parent_design_id", "") or ""),
            )
        )
    summaries.sort(key=lambda s: s.updated_at, reverse=True)
    return summaries


def load_design(team_id: str, design_id: str) -> BlastDesign:
    path = design_path(team_id, design_id)
    if not path.exists():
        raise DesignNotFoundError(f"Паспорт БВР «{design_id}» не найден.")
    return BlastDesign.from_dict(_read_json(path))


def _persist(team_id: str, design: BlastDesign) -> BlastDesign:
    ensure_designs_layout(team_id)
    design.version = DESIGN_VERSION
    design.updated_at = utc_now_iso()
    design.designed_sha256 = designed_sha256(design)
    _write_json(design_path(team_id, design.design_id), design.to_dict())
    return design


def _prepare_new(design: BlastDesign, actor: str) -> BlastDesign:
    if not design.design_id:
        design.design_id = new_design_id()
    design.lifecycle_status = STATUS_DRAFT
    design.revision = 1
    design.designed_sha256 = designed_sha256(design)
    design.lifecycle_events = [
        make_event(
            kind=KIND_CREATED,
            actor=actor,
            from_status="",
            to_status=STATUS_DRAFT,
            revision=1,
            content_sha256=design.designed_sha256,
            mutations=[MUTATION_DESIGNED],
        )
    ]
    return design


def _apply_incoming(stored: BlastDesign, incoming: BlastDesign, actor: str) -> BlastDesign:
    incoming.design_id = stored.design_id
    incoming.lifecycle_status = stored.lifecycle_status
    incoming.parent_design_id = stored.parent_design_id
    incoming.lifecycle_events = list(stored.lifecycle_events)
    incoming.revision = stored.revision
    incoming.designed_sha256 = stored.designed_sha256

    mutations = classify_mutations(stored, incoming)
    if not mutations:
        incoming.version = DESIGN_VERSION
        incoming.updated_at = stored.updated_at
        incoming.designed_sha256 = stored.designed_sha256
        return incoming

    assert_mutations_allowed(stored.lifecycle_status, mutations)

    if MUTATION_DESIGNED in mutations:
        incoming.revision = stored.revision + 1
        incoming.designed_sha256 = designed_sha256(incoming)
        event_kind = KIND_REVISE
    elif MUTATION_METADATA in mutations and len(mutations) == 1:
        incoming.revision = stored.revision
        incoming.designed_sha256 = stored.designed_sha256
        event_kind = KIND_RENAME
    elif MUTATION_MEASURED in mutations:
        incoming.revision = stored.revision
        incoming.designed_sha256 = stored.designed_sha256
        event_kind = KIND_RECORD_MEASURED
    else:
        incoming.revision = stored.revision
        incoming.designed_sha256 = stored.designed_sha256
        event_kind = KIND_RECORD_EXECUTION

    incoming.lifecycle_events.append(
        make_event(
            kind=event_kind,
            actor=actor,
            from_status=stored.lifecycle_status,
            to_status=stored.lifecycle_status,
            revision=incoming.revision,
            content_sha256=incoming.designed_sha256,
            mutations=mutations,
        )
    )
    return incoming


def save_design(team_id: str, design: BlastDesign, *, actor: str = "") -> BlastDesign:
    ensure_designs_layout(team_id)
    if not design.design_id:
        return _persist(team_id, _prepare_new(design, actor))
    path = design_path(team_id, design.design_id)
    if not path.exists():
        return _persist(team_id, _prepare_new(design, actor))
    stored = BlastDesign.from_dict(_read_json(path))
    prepared = _apply_incoming(stored, design, actor)
    if not classify_mutations(stored, prepared) and prepared.lifecycle_events == stored.lifecycle_events:
        return stored
    return _persist(team_id, prepared)


def delete_design(team_id: str, design_id: str) -> None:
    path = design_path(team_id, design_id)
    if not path.exists():
        raise DesignNotFoundError(f"Паспорт БВР «{design_id}» не найден.")
    stored = BlastDesign.from_dict(_read_json(path))
    if not can_delete(stored.lifecycle_status):
        raise FrozenDesignError(
            f"Паспорт в статусе «{stored.lifecycle_status}» нельзя удалить. "
            "Удаляются только черновик и паспорт на проверке."
        )
    path.unlink()


def rename_design(team_id: str, design_id: str, new_name: str, *, actor: str = "") -> BlastDesign:
    design = load_design(team_id, design_id)
    design.name = new_name
    return save_design(team_id, design, actor=actor)


def transition_design(
    team_id: str,
    design_id: str,
    *,
    to_status: str,
    actor: str,
    confirm: bool,
    note: str = "",
) -> BlastDesign:
    design = load_design(team_id, design_id)
    event = plan_transition(
        from_status=design.lifecycle_status,
        to_status=to_status,
        actor=actor,
        confirm=confirm,
        note=note,
        revision=design.revision,
        content_sha256=design.designed_sha256 or designed_sha256(design),
    )
    design.lifecycle_status = event.to_status
    design.lifecycle_events.append(event)
    return _persist(team_id, design)


def fork_design(
    team_id: str,
    design_id: str,
    *,
    name: str = "",
    actor: str = "",
) -> BlastDesign:
    source = load_design(team_id, design_id)
    clone = BlastDesign.from_dict(source.to_dict())
    clone.design_id = ""
    clone.name = name.strip() or f"{source.name} (v{source.revision + 1})"
    clone.parent_design_id = source.design_id
    clone.lifecycle_status = STATUS_DRAFT
    clone.revision = 0
    clone.lifecycle_events = []
    clone.designed_sha256 = ""
    clone.as_drilled_holes = []
    clone.as_charged_holes = []
    clone.as_fired_holes = []
    clone.blast_result = None
    clone.vibration_measurements = []
    clone.updated_at = ""
    prepared = _prepare_new(clone, actor)
    if prepared.lifecycle_events:
        prepared.lifecycle_events[0] = make_event(
            kind=KIND_FORK,
            actor=actor,
            from_status=source.lifecycle_status,
            to_status=STATUS_DRAFT,
            note=f"fork of {source.design_id}",
            revision=1,
            content_sha256=prepared.designed_sha256,
            mutations=[MUTATION_DESIGNED],
        )
    return _persist(team_id, prepared)
