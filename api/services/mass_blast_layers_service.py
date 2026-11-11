"""Слои проекта МВ — документы дня взрыва (TASK-018, PR 2, §2.1).

Слой открывается по статусу проекта и переносит данные текущей ревизии
проекта (`design/mass_blast_layers.layer_seed`); введённое вручную хранится
отдельно. Повторный перенос (проект перевыпущен) показывает расхождение и
применяется только с подтверждения. Ревизия слоя — неизменяемый снимок с
`content_sha256`. Печать — PR 3, MagEX — PR 7.
"""
from __future__ import annotations

from typing import Any, Mapping

from api.schemas.mass_blast import LAYER_PAYLOAD_SCHEMAS
from cost.v2.repository import EconomicsRepository
from design.mass_blast import content_sha256
from design.mass_blast_layers import (
    LAYER_LABELS,
    LAYER_OPEN_AFTER,
    MULTI_LAYER_KINDS,
    layer_open_issue,
    layer_seed,
    naryad_lines,
    seed_diff,
)
from design.mass_blast_repository import PostgresMassBlastRepository

__all__ = ["create_layer", "get_layer", "issue_layer", "list_layers", "refresh_layer", "update_layer"]

LAYER_CONTEXT_VERSION = 1


def _payload(kind: str, payload: Mapping[str, Any]) -> dict[str, Any]:
    """Введённое вручную по схеме вида слоя: лишнее поле или неверное значение — ошибка."""

    schema = LAYER_PAYLOAD_SCHEMAS[kind]
    return schema.model_validate(dict(payload)).model_dump()


def _current_revision(repository: PostgresMassBlastRepository, organization_id: str, project: Mapping[str, Any]) -> dict[str, Any]:
    revision_id = project.get("current_revision_id")
    if not revision_id:
        raise ValueError("У проекта нет выпущенной ревизии: слою не из чего брать данные.")
    return repository.get_revision(organization_id, str(revision_id))


def _snapshot(economics_repository: EconomicsRepository | None, organization_id: str, context: Mapping[str, Any]):
    if economics_repository is None:
        return None
    revision_id = str((context.get("project") or {}).get("reference_revision_id") or "") or None
    try:
        return economics_repository.get_reference_snapshot(organization_id, revision_id)
    except Exception:  # noqa: BLE001 — справочник даёт только умолчания: без него слой открывается
        return None


def _site_record(snapshot: Any, section: str, site_code: str) -> Mapping[str, Any] | None:
    if snapshot is None:
        return None
    for item in snapshot.active_items(section):
        if str(item.payload.get("site_code") or "") == site_code:
            return dict(item.payload)
    return None


def _notification(
    snapshot: Any, context: Mapping[str, Any], payload: Mapping[str, Any]
) -> tuple[dict[str, Any] | None, list[dict[str, str]]]:
    """Адресат уведомления из справочника карьера (одно уведомление — один адресат)."""

    site_code = str((context.get("project") or {}).get("site_code") or "")
    code = str(payload.get("notification_code") or "")
    records = [] if snapshot is None else [
        item for item in snapshot.active_items("blast_notifications") if str(item.payload.get("site_code") or "") == site_code
    ]
    if not records:
        return None, [
            {
                "level": "warning",
                "code": "notify_registry_missing",
                "message": "У объекта нет справочника уведомлений: адресата уведомления заполните вручную.",
                "path": "payload.notification_code",
            }
        ]
    if not code:
        return None, [
            {
                "level": "error",
                "code": "notification_addressee_missing",
                "message": "Выберите адресата уведомления из справочника карьера.",
                "path": "payload.notification_code",
            }
        ]
    for item in records:
        if item.code == code:
            return {"code": item.code, "name": item.name, **dict(item.payload)}, []
    raise ValueError(f"Адресат уведомления {code} не найден в справочнике карьера {site_code}.")


def _reserve_defaults(snapshot: Any, context: Mapping[str, Any]) -> dict[str, int]:
    site = _site_record(snapshot, "blast_safety", str((context.get("project") or {}).get("site_code") or "")) or {}
    return {
        "primers": int(site.get("reserve_primers_pcs") or 0),
        "nsi": int(site.get("reserve_nsi_pcs") or 0),
        "starters": int(site.get("reserve_starters_pcs") or 0),
    }


def _with_view(layer: dict[str, Any], snapshot: Any, context: Mapping[str, Any]) -> dict[str, Any]:
    """Что слой показывает и печатает: у наряда — строки ВМ «по проекту / запас / к выдаче»."""

    view: dict[str, Any] = {"label": LAYER_LABELS.get(layer["kind"], layer["kind"])}
    issues: list[dict[str, str]] = []
    if layer["kind"] == "NARYAD":
        view["lines"] = naryad_lines(layer["seed"], layer["payload"], _reserve_defaults(snapshot, context))
        view["vv_site"] = bool(layer["payload"].get("vv_site"))
    if layer["kind"] == "NOTIFICATION" and not (layer["seed"].get("addressee") or {}):
        issues.append(
            {
                "level": "warning",
                "code": "notify_registry_missing",
                "message": "Адресат уведомления не из справочника карьера: проверьте реквизиты.",
                "path": "seed.addressee",
            }
        )
    if layer["stale"]:
        issues.append(
            {
                "level": "warning",
                "code": "layer_stale",
                "message": "Проект перевыпущен новой ревизией: перенесите данные проекта заново.",
                "path": "project_revision_id",
            }
        )
    return {**layer, "view": view, "issues": issues}


def list_layers(
    repository: PostgresMassBlastRepository, economics_repository: EconomicsRepository | None, organization_id: str, project_id: str,
) -> list[dict[str, Any]]:
    layers = list(repository.list_layers(organization_id, project_id))
    if not layers:
        return []
    project = repository.get_project(organization_id, project_id)
    context = _current_revision(repository, organization_id, project)["context"]
    snapshot = _snapshot(economics_repository, organization_id, context)
    return [_with_view(layer, snapshot, context) for layer in layers]


def get_layer(
    repository: PostgresMassBlastRepository, economics_repository: EconomicsRepository | None, organization_id: str, layer_id: str,
) -> dict[str, Any]:
    layer = repository.get_layer(organization_id, layer_id)
    context = repository.get_revision(organization_id, layer["project_revision_id"])["context"]
    return _with_view(layer, _snapshot(economics_repository, organization_id, context), context)


def create_layer(
    repository: PostgresMassBlastRepository,
    economics_repository: EconomicsRepository | None,
    organization_id: str,
    actor: str,
    project_id: str,
    kind: str,
    payload: Mapping[str, Any],
) -> dict[str, Any]:
    project = repository.get_project(organization_id, project_id)
    revision = _current_revision(repository, organization_id, project)
    context = revision["context"]
    reason = layer_open_issue(kind, str(project.get("lifecycle_status") or ""), context)
    if reason:
        raise ValueError(reason)
    data = _payload(kind, payload)
    snapshot = _snapshot(economics_repository, organization_id, context)
    addressee = None
    if kind == "NOTIFICATION":
        addressee, problems = _notification(snapshot, context, data)
        if any(item["level"] == "error" for item in problems):
            raise ValueError(problems[0]["message"])
    layer = repository.create_layer(
        organization_id, actor, project_id, kind=kind, project_revision_id=revision["id"],
        allowed_statuses=set(LAYER_OPEN_AFTER[kind]), single=kind not in MULTI_LAYER_KINDS,
        seed=layer_seed(kind, context, notification=addressee), payload=data,
    )
    return _with_view(layer, snapshot, context)


def update_layer(
    repository: PostgresMassBlastRepository,
    economics_repository: EconomicsRepository | None,
    organization_id: str,
    actor: str,
    layer_id: str,
    payload: Mapping[str, Any],
    expected_version: int,
) -> dict[str, Any]:
    layer = repository.get_layer(organization_id, layer_id)
    data = _payload(layer["kind"], payload)
    if layer["kind"] == "NOTIFICATION" and data.get("notification_code") != layer["payload"].get("notification_code"):
        raise ValueError("Адресат уведомления не меняется: заведите отдельное уведомление на другого адресата.")
    updated = repository.update_layer(organization_id, actor, layer_id, expected_version=expected_version, payload=data)
    context = repository.get_revision(organization_id, updated["project_revision_id"])["context"]
    return _with_view(updated, _snapshot(economics_repository, organization_id, context), context)


def refresh_layer(
    repository: PostgresMassBlastRepository,
    economics_repository: EconomicsRepository | None,
    organization_id: str,
    actor: str,
    layer_id: str,
    expected_version: int,
    confirm: bool,
) -> dict[str, Any]:
    """Повторный перенос данных текущей ревизии проекта; без `confirm` — только расхождение."""

    layer = repository.get_layer(organization_id, layer_id)
    project = repository.get_project(organization_id, layer["project_id"])
    revision = _current_revision(repository, organization_id, project)
    context = revision["context"]
    snapshot = _snapshot(economics_repository, organization_id, context)
    addressee = layer["seed"].get("addressee") or None
    if layer["kind"] == "NOTIFICATION" and layer["payload"].get("notification_code"):
        try:
            addressee, _ = _notification(snapshot, context, layer["payload"])
        except ValueError:
            pass  # адресата убрали из справочника — остаётся прежний
    new_seed = layer_seed(layer["kind"], context, notification=addressee)
    changes = seed_diff(layer["seed"], new_seed)
    if revision["id"] != layer["project_revision_id"]:
        changes.insert(0, {"path": "project_revision_id", "before": layer["project_revision_id"], "after": revision["id"]})
    if not confirm or not changes:
        return {"applied": False, "changes": changes, "layer": _with_view(layer, snapshot, context)}
    updated = repository.update_layer(
        organization_id, actor, layer_id, expected_version=expected_version, seed=new_seed, project_revision_id=revision["id"],
    )
    return {"applied": True, "changes": changes, "layer": _with_view(updated, snapshot, context)}


def issue_layer(
    repository: PostgresMassBlastRepository,
    economics_repository: EconomicsRepository | None,
    organization_id: str,
    actor: str,
    layer_id: str,
    expected_version: int,
) -> dict[str, Any]:
    """Неизменяемая ревизия слоя: перенесённое, введённое и вычисленное (строки наряда)."""

    layer = repository.get_layer(organization_id, layer_id)
    if layer["stale"]:
        raise ValueError("Проект перевыпущен: перенесите данные проекта в слой заново, затем выпускайте.")
    context = repository.get_revision(organization_id, layer["project_revision_id"])["context"]
    viewed = _with_view(layer, _snapshot(economics_repository, organization_id, context), context)
    errors = [item for item in viewed["issues"] if item["level"] == "error"]
    if errors:
        raise ValueError("Слой нельзя выпустить: " + "; ".join(item["message"] for item in errors))
    snapshot = {
        "layer_context_version": LAYER_CONTEXT_VERSION,
        "kind": layer["kind"],
        "project_revision_id": layer["project_revision_id"],
        "seed": layer["seed"],
        "payload": layer["payload"],
        "view": viewed["view"],
    }
    return repository.create_layer_revision(
        organization_id, actor, layer_id, expected_version=expected_version, context=snapshot,
        content_sha256=content_sha256(snapshot),
    )
