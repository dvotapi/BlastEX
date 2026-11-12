"""Слои проекта МВ — документы дня взрыва (TASK-018, PR 2, §2.1).

Слой открывается по статусу проекта и переносит данные текущей ревизии
проекта (`design/mass_blast_layers.layer_seed`); введённое вручную хранится
отдельно. Повторный перенос (проект перевыпущен) показывает расхождение и
применяется только с подтверждения. Ревизия слоя — неизменяемый снимок с
`content_sha256`. Печать — PR 3, MagEX — PR 7.

Слой «Факт» (PR 5) переносит факт из проектов блоков ревизии
(`design/mass_blast_fact.py`); акт приёмки и наряд после взрыва — из последней
выпущенной ревизии «Факта» на той же ревизии проекта.
"""
from __future__ import annotations

from typing import Any, Mapping

from api.schemas.mass_blast import LAYER_PAYLOAD_SCHEMAS
from cost.v2.repository import EconomicsRepository
from design import persistence as design_persistence
from design.lifecycle import designed_sha256
from design.mass_blast import content_sha256
from design.mass_blast_fact import block_fact, execution_sha256
from design.mass_blast_layer_diff import describe_changes
from design.mass_blast_layers import (
    AFTER_BLAST_STATUSES,
    LAYER_KINDS,
    LAYER_LABELS,
    LAYER_OPEN_AFTER,
    MULTI_LAYER_KINDS,
    acceptance_view,
    execution_seed_diff,
    execution_summary,
    execution_view,
    layer_open_issue,
    layer_seed,
    naryad_after_blast,
    naryad_lines,
    naryad_totals,
    seed_diff,
    talon_view,
)
from design.mass_blast_repository import PostgresMassBlastRepository

__all__ = [
    "available_layers",
    "create_layer",
    "get_layer",
    "issue_layer",
    "list_layers",
    "notification_addressees",
    "refresh_layer",
    "update_layer",
]

LAYER_CONTEXT_VERSION = 1


def _payload(kind: str, payload: Mapping[str, Any]) -> dict[str, Any]:
    """Введённое вручную по схеме вида слоя: лишнее поле или неверное значение — ошибка."""

    schema = LAYER_PAYLOAD_SCHEMAS[kind]
    data = schema.model_validate(dict(payload)).model_dump()
    if kind == "NOTIFICATION" and data["notification_code"] and any(
        str(data[key]).strip() for key in _MANUAL_RECIPIENT
    ):
        raise ValueError("Адресат из справочника карьера вручную не правится: заведите уведомление без кода адресата.")
    return data


# Адресат уведомления вручную — только когда справочника уведомлений у карьера нет.
_MANUAL_RECIPIENT = ("recipient_position", "recipient_name", "salutation")


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


AFTER_BLAST_KEYS = ("issued", "consumed", "returned")


def _after_blast(payload: Mapping[str, Any]) -> bool:
    return any(payload.get(key) for key in AFTER_BLAST_KEYS)


def _with_view(
    layer: dict[str, Any], snapshot: Any, context: Mapping[str, Any], state: Mapping[str, Any] | None = None
) -> dict[str, Any]:
    """Что слой показывает и печатает: у наряда — строки ВМ «по проекту / запас / к выдаче».

    `state` — то, что знает только сервис (`_fact_state`): изменился ли факт
    проектов блоков после переноса в слой «Факт» и какая ревизия «Факта»
    последняя (для акта приёмки и наряда).
    """

    state = state or {}
    view: dict[str, Any] = {"label": LAYER_LABELS.get(layer["kind"], layer["kind"])}
    issues: list[dict[str, str]] = []
    seed, payload = layer["seed"], layer["payload"]
    if layer["kind"] == "NARYAD":
        view["lines"] = naryad_lines(seed, payload, _reserve_defaults(snapshot, context))
        view["totals"] = naryad_totals(seed, view["lines"])
        view["vv_site"] = bool(payload.get("vv_site"))
        if seed.get("fact") or _after_blast(payload):
            view["lines"], view["blocks_fact"], after_issues = naryad_after_blast(seed, payload, view["lines"])
            view["after_blast"] = True
            issues += after_issues
    if layer["kind"] == "TALON":
        view.update(talon_view(seed, payload))
    if layer["kind"] == "ACCEPTANCE_ACT":
        view["fact"], fact_issues = acceptance_view(seed, payload)
        issues += fact_issues
    if layer["kind"] == "EXECUTION":
        execution, fact_issues = execution_view(seed, payload)
        view.update(execution)
        issues += fact_issues
        if state.get("fact_error"):
            issues.append(
                {"level": "error", "code": "fact_source_invalid", "message": str(state["fact_error"]), "path": "seed.blocks_fact"}
            )
        if state.get("fact_changed"):
            issues.append(
                {
                    "level": "error",
                    "code": "fact_changed",
                    "message": "Факт в проекте блока изменился после переноса: перенесите факт заново, затем выпускайте.",
                    "path": "seed.blocks_fact",
                }
            )
    fact = seed.get("fact") or {}
    latest = state.get("latest_execution_id")
    # Наряд до взрыва факта не берёт: про новую ревизию «Факта» — только после взрыва.
    wants_fact = layer["kind"] == "ACCEPTANCE_ACT" or bool(fact) or state.get("after_blast")
    if layer["kind"] in ("NARYAD", "ACCEPTANCE_ACT") and wants_fact and latest and fact.get("execution_revision_id") != latest:
        issues.append(
            {
                "level": "warning",
                "code": "fact_layer_stale",
                "message": "Выпущена новая ревизия слоя «Факт»: перенесите данные заново.",
                "path": "seed.fact",
            }
        )
    if layer["kind"] == "NOTIFICATION":
        if not str(layer["seed"].get("letterhead") or "").strip():
            issues.append(
                {
                    "level": "warning",
                    "code": "letterhead_missing",
                    "message": "В профиле документов нет бланка Общества: уведомление печатается только с наименованием.",
                    "path": "seed.letterhead",
                }
            )
        registry = dict(layer["seed"].get("addressee") or {})
        if registry:
            view["addressee"] = registry
        else:
            payload = layer["payload"]
            view["addressee"] = {key: payload.get(key, "") for key in (*_MANUAL_RECIPIENT, "signer")}
            issues.append(
                {
                    "level": "warning",
                    "code": "notify_registry_missing",
                    "message": "Адресат уведомления введён вручную, не из справочника карьера: проверьте реквизиты.",
                    "path": "payload.recipient_position",
                }
            )
            if not str(payload.get("recipient_position") or "").strip():
                issues.append(
                    {
                        "level": "error",
                        "code": "notification_addressee_missing",
                        "message": "Укажите адресата уведомления: справочника уведомлений у карьера нет.",
                        "path": "payload.recipient_position",
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


def _load_design(organization_id: str, design_id: str):
    return design_persistence.load_design(organization_id, design_id)


def _block_designs(organization_id: str, context: Mapping[str, Any]) -> list[Any]:
    """Проекты блоков ревизии проекта МВ — источник факта.

    Проектная часть блока обязана быть той, что утверждена в ревизии: иначе
    факт относится к другой сетке.
    """

    designs = []
    for block in context.get("blocks") or []:
        name = str(block.get("code") or block.get("design_id") or "")
        try:
            design = _load_design(organization_id, str(block.get("design_id") or ""))
        except design_persistence.DesignNotFoundError as exc:
            raise ValueError(f"Проект блока «{name}» больше недоступен: факт взять неоткуда.") from exc
        current = design.designed_sha256 or designed_sha256(design)
        if current != str(block.get("design_sha256") or ""):
            raise ValueError(
                f"Проект блока «{name}» изменён после выпуска ревизии проекта МВ: факт относится к другой сетке."
            )
        designs.append(design)
    return designs


def _execution_facts(organization_id: str, context: Mapping[str, Any], snapshot: Any) -> list[tuple[dict, list]]:
    designs = _block_designs(organization_id, context)
    materials = list(snapshot.active_items("materials")) if snapshot is not None else []
    starter = str((context.get("explosives") or {}).get("starter_product") or "")
    blocks = list(context.get("blocks_v2") or [])
    return [
        block_fact(design, (blocks[index] if index < len(blocks) else {}).get("parameter_table") or {}, materials,
                   starter_product=starter)
        for index, design in enumerate(designs)
    ]


def _latest_execution(
    repository: PostgresMassBlastRepository, organization_id: str, project_id: str, project_revision_id: str
) -> tuple[str | None, dict[str, Any] | None]:
    """Последняя выпущенная ревизия слоя «Факт» на этой ревизии проекта."""

    for layer in repository.list_layers(organization_id, project_id):
        if layer["kind"] != "EXECUTION" or not layer.get("current_revision_id"):
            continue
        revision = repository.latest_layer_revision(organization_id, layer["id"], project_revision_id)
        if revision is not None:
            return str(revision["id"]), dict(revision.get("context") or {})
    return None, None


def _fact_state(
    repository: PostgresMassBlastRepository,
    organization_id: str,
    layer: Mapping[str, Any],
    context: Mapping[str, Any],
    project: Mapping[str, Any] | None = None,
    latest: dict[str, str | None] | None = None,
) -> dict[str, Any]:
    """Что о слое знает только сервис; `latest` — кэш последней ревизии «Факта»
    по ревизии проекта на один список слоёв."""

    state: dict[str, Any] = {}
    if layer["kind"] == "EXECUTION":
        try:
            hashes = [execution_sha256(design) for design in _block_designs(organization_id, context)]
        except ValueError as exc:
            # Проект блока удалён или изменён: причина — как есть, а не «факт изменился».
            state["fact_error"] = str(exc)
            return state
        seeded = [str(block.get("execution_sha256") or "") for block in layer["seed"].get("blocks_fact") or []]
        state["fact_changed"] = hashes != seeded
    elif layer["kind"] in ("NARYAD", "ACCEPTANCE_ACT"):
        project = project or repository.get_project(organization_id, layer["project_id"])
        state["after_blast"] = str(project.get("lifecycle_status") or "") in AFTER_BLAST_STATUSES
        key = layer["project_revision_id"]
        if latest is None or key not in latest:
            found, _ = _latest_execution(repository, organization_id, layer["project_id"], key)
            if latest is None:
                return {**state, "latest_execution_id": found}
            latest[key] = found
        state["latest_execution_id"] = latest[key]
    return state


def _seed(
    repository: PostgresMassBlastRepository,
    organization_id: str,
    kind: str,
    context: Mapping[str, Any],
    snapshot: Any,
    project: Mapping[str, Any],
    project_revision_id: str,
    notification: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Перенос в слой: у «Факта» — факт проектов блоков; у акта приёмки и наряда
    после взрыва — сводка последней выпущенной ревизии «Факта»."""

    facts = _execution_facts(organization_id, context, snapshot) if kind == "EXECUTION" else None
    execution = None
    after_blast = str(project.get("lifecycle_status") or "") in AFTER_BLAST_STATUSES
    if kind == "ACCEPTANCE_ACT" or (kind == "NARYAD" and after_blast):
        revision_id, revision_context = _latest_execution(repository, organization_id, str(project["id"]), project_revision_id)
        if revision_id is not None and revision_context is not None:
            execution = execution_summary(revision_context, revision_id)
    return layer_seed(kind, context, notification=notification, facts=facts, execution=execution)


def list_layers(
    repository: PostgresMassBlastRepository, economics_repository: EconomicsRepository | None, organization_id: str, project_id: str,
) -> list[dict[str, Any]]:
    """Слои проекта; вид каждого — по ревизии проекта, на которой он основан (как у `get_layer`)."""

    contexts: dict[str, tuple[Mapping[str, Any], Any]] = {}
    latest: dict[str, str | None] = {}
    project = repository.get_project(organization_id, project_id)
    result = []
    for layer in repository.list_layers(organization_id, project_id):
        revision_id = layer["project_revision_id"]
        if revision_id not in contexts:
            context = repository.get_revision(organization_id, revision_id)["context"]
            contexts[revision_id] = (context, _snapshot(economics_repository, organization_id, context))
        context, snapshot = contexts[revision_id]
        result.append(_with_view(layer, snapshot, context,
                                 _fact_state(repository, organization_id, layer, context, project, latest)))
    return result


def get_layer(
    repository: PostgresMassBlastRepository, economics_repository: EconomicsRepository | None, organization_id: str, layer_id: str,
) -> dict[str, Any]:
    layer = repository.get_layer(organization_id, layer_id)
    context = repository.get_revision(organization_id, layer["project_revision_id"])["context"]
    return _with_view(
        layer, _snapshot(economics_repository, organization_id, context), context,
        _fact_state(repository, organization_id, layer, context),
    )


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
    _check_after_blast(kind, project, data, {})
    snapshot = _snapshot(economics_repository, organization_id, context)
    addressee = None
    if kind == "NOTIFICATION":
        addressee, problems = _notification(snapshot, context, data)
        if any(item["level"] == "error" for item in problems):
            raise ValueError(problems[0]["message"])
        code = str(data.get("notification_code") or "")
        if code and any(
            layer["kind"] == "NOTIFICATION" and layer["payload"].get("notification_code") == code
            for layer in repository.list_layers(organization_id, project_id)
        ):
            raise ValueError("Уведомление этому адресату у проекта уже есть: на адресата — одно уведомление.")
    seed = _seed(repository, organization_id, kind, context, snapshot, project, revision["id"], addressee)
    layer = repository.create_layer(
        organization_id, actor, project_id, kind=kind, project_revision_id=revision["id"],
        allowed_statuses=set(LAYER_OPEN_AFTER[kind]), single=kind not in MULTI_LAYER_KINDS,
        seed=seed, payload=data,
        # Одно уведомление на адресата: окончательная проверка — в транзакции
        # создания под блокировкой проекта (одновременные запросы).
        unique_payload_key="notification_code" if kind == "NOTIFICATION" else None,
    )
    # Только что перенесённый факт не изменился: проекты блоков второй раз не читаются.
    state = {"fact_changed": False} if kind == "EXECUTION" else _fact_state(repository, organization_id, layer, context, project)
    return _with_view(layer, snapshot, context, state)


def _check_after_blast(kind: str, project: Mapping[str, Any], data: Mapping[str, Any], stored: Mapping[str, Any]) -> None:
    """Графы наряда «после взрыва» правятся только у проекта со взрывом (решение В9 PR 5)."""

    if kind != "NARYAD" or str(project.get("lifecycle_status") or "") in AFTER_BLAST_STATUSES:
        return
    if any((data.get(key) or {}) != (stored.get(key) or {}) for key in AFTER_BLAST_KEYS):
        raise ValueError("Графы «выдано», «израсходовано», «возвращено» заполняются после взрыва (проект «выполнен»).")


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
    project = repository.get_project(organization_id, layer["project_id"])
    _check_after_blast(layer["kind"], project, data, layer["payload"])
    updated = repository.update_layer(organization_id, actor, layer_id, expected_version=expected_version, payload=data)
    context = repository.get_revision(organization_id, updated["project_revision_id"])["context"]
    return _with_view(
        updated, _snapshot(economics_repository, organization_id, context), context,
        _fact_state(repository, organization_id, updated, context, project),
    )


def refresh_layer(
    repository: PostgresMassBlastRepository,
    economics_repository: EconomicsRepository | None,
    organization_id: str,
    actor: str,
    layer_id: str,
    expected_version: int,
    confirm: bool,
) -> dict[str, Any]:
    """Повторный перенос данных текущей ревизии проекта (у «Факта» — и факта
    проектов блоков); без `confirm` — только расхождение."""

    layer = repository.get_layer(organization_id, layer_id)
    project = repository.get_project(organization_id, layer["project_id"])
    revision = _current_revision(repository, organization_id, project)
    context = revision["context"]
    snapshot = _snapshot(economics_repository, organization_id, context)
    addressee = layer["seed"].get("addressee") or None
    if layer["kind"] == "NOTIFICATION" and layer["payload"].get("notification_code"):
        try:
            found, _ = _notification(snapshot, context, layer["payload"])
        except ValueError:
            found = None
        # Адресата убрали из справочника или справочник не прочитан — остаётся прежний.
        addressee = found or addressee
    new_seed = _seed(repository, organization_id, layer["kind"], context, snapshot, project, revision["id"], addressee)
    diff = execution_seed_diff if layer["kind"] == "EXECUTION" else seed_diff
    changes = diff(layer["seed"], new_seed)
    if revision["id"] != layer["project_revision_id"]:
        changes.insert(0, {"path": "project_revision_id", "before": layer["project_revision_id"], "after": revision["id"]})
    # Подписи и тексты значений — для окна проекта (PR 6): без служебных путей и JSON.
    changes = describe_changes(changes)
    if not confirm or not changes:
        return {
            "applied": False, "changes": changes,
            "layer": _with_view(layer, snapshot, context, _fact_state(repository, organization_id, layer, context, project)),
        }
    updated = repository.update_layer(
        organization_id, actor, layer_id, expected_version=expected_version, seed=new_seed, project_revision_id=revision["id"],
    )
    return {
        "applied": True, "changes": changes,
        "layer": _with_view(updated, snapshot, context, _fact_state(repository, organization_id, updated, context, project)),
    }


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
    viewed = _with_view(
        layer, _snapshot(economics_repository, organization_id, context), context,
        _fact_state(repository, organization_id, layer, context),
    )
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


# --- Окно проекта (TASK-018, PR 6) ------------------------------------------

# Способ направления уведомления — подписью для списка адресатов.
CHANNEL_LABELS = {"LETTER": "письмо", "EMAIL": "эл. почта", "PHONEGRAM": "телефонограмма"}


def available_layers(
    repository: PostgresMassBlastRepository, organization_id: str, project_id: str
) -> list[dict[str, Any]]:
    """Какие слои можно открыть сейчас и почему нельзя (правило — `layer_open_issue`)."""

    project = repository.get_project(organization_id, project_id)
    status = str(project.get("lifecycle_status") or "")
    context: Mapping[str, Any] = {}
    if project.get("current_revision_id"):
        context = repository.get_revision(organization_id, str(project["current_revision_id"]))["context"]
    existing: dict[str, int] = {}
    for layer in repository.list_layers(organization_id, project_id):
        existing[layer["kind"]] = existing.get(layer["kind"], 0) + 1
    result = []
    for kind in LAYER_KINDS:
        reason = (
            layer_open_issue(kind, status, context) if context
            else "У проекта нет выпущенной ревизии: слою не из чего брать данные."
        )
        multiple = kind in MULTI_LAYER_KINDS
        if reason is None and existing.get(kind) and not multiple:
            reason = "Слой уже открыт: у проекта он один."
        result.append({
            "kind": kind,
            "label": LAYER_LABELS[kind],
            "can_open": reason is None,
            "reason": reason or "",
            "multiple": multiple,
            "count": existing.get(kind, 0),
        })
    return result


def _addressee_label(name: str, payload: Mapping[str, Any]) -> str:
    who = " ".join(part for part in (str(payload.get("recipient_position") or "").strip(),
                                     str(payload.get("recipient_name") or "").strip()) if part)
    channel = CHANNEL_LABELS.get(str(payload.get("channel") or ""), "")
    days = payload.get("lead_days")
    when = f"за {days} сут." if days not in (None, "") else ""
    details = ", ".join(part for part in (channel, when) if part)
    label = who or name
    return f"{label} ({details})" if details else label


def notification_addressees(
    repository: PostgresMassBlastRepository,
    economics_repository: EconomicsRepository | None,
    organization_id: str,
    project_id: str,
) -> dict[str, Any]:
    """Адресаты уведомления из справочника карьера: код, подпись, есть ли уже уведомление.

    Подпись собирает сервер — интерфейс полей справочника не знает (CLAUDE.md).
    """

    project = repository.get_project(organization_id, project_id)
    revision = _current_revision(repository, organization_id, project)
    context = revision["context"]
    snapshot = _snapshot(economics_repository, organization_id, context)
    site_code = str((context.get("project") or {}).get("site_code") or "")
    records = [] if snapshot is None else sorted(
        (item for item in snapshot.active_items("blast_notifications")
         if str(item.payload.get("site_code") or "") == site_code),
        key=lambda item: item.code,
    )
    taken = {
        str(layer["payload"].get("notification_code") or "")
        for layer in repository.list_layers(organization_id, project_id)
        if layer["kind"] == "NOTIFICATION"
    } - {""}
    return {
        "registry": bool(records),
        "items": [
            {"code": item.code, "label": _addressee_label(item.name, item.payload), "taken": item.code in taken}
            for item in records
        ],
    }
