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

from api import config
from api.schemas.mass_blast import LAYER_PAYLOAD_SCHEMAS, NARYAD_MAGEX_KEYS
from api.services.magex_settings import magex_mode, offline_reason
from cost.v2.repository import EconomicsRepository
from design import persistence as design_persistence
from design.lifecycle import designed_sha256
from design.mass_blast import content_sha256
from design.mass_blast_fact import block_fact, execution_sha256
from design.mass_blast_defaults import created_on, fill_layer_empty, layer_defaults
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
from design.magex.execution import block_results, explosive_consumed_kg, values_by_line
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
# Ключи вида слоя, которые показывает окно, но не хранит ревизия: умолчания, «запомнить»,
# состояние MagEX (меняется со временем, в снимок не идёт).
VIEW_STATE_KEYS = ("defaults", "rememberable", "magex")


def _payload(kind: str, payload: Mapping[str, Any]) -> dict[str, Any]:
    """Введённое вручную по схеме вида слоя: лишнее поле или неверное значение — ошибка."""

    schema = LAYER_PAYLOAD_SCHEMAS[kind]
    data = schema.model_validate(dict(payload)).model_dump()
    if kind == "NARYAD":
        # Поля MagEX (PR 7) — только заданные: содержимое прежних нарядов не меняется.
        for key in NARYAD_MAGEX_KEYS:
            if data.get(key) in ("", False, None):
                data.pop(key, None)
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
        # Исполнение MagEX — в графах после взрыва только у проекта со взрывом (решения В9 PR 5, В7 PR 7).
        execution = state.get("magex_execution") if state.get("after_blast") else None
        magex_values, magex_issues = (
            values_by_line(execution, state.get("magex_lines") or [], view["lines"]) if execution else ({}, [])
        )
        if seed.get("fact") or _after_blast(payload) or magex_values:
            view["lines"], view["blocks_fact"], after_issues = naryad_after_blast(
                seed, payload, view["lines"], magex=magex_values,
                magex_blocks=block_results(execution) if execution else None,
            )
            view["after_blast"] = True
            issues += after_issues + magex_issues
        if "magex" in state:
            view["magex"] = state["magex"]
    if layer["kind"] == "TALON":
        view.update(talon_view(seed, payload))
    if layer["kind"] == "ACCEPTANCE_ACT":
        view["fact"], fact_issues = acceptance_view(seed, payload)
        issues += fact_issues
        magex_kg = state.get("magex_explosive_kg")
        if magex_kg is not None and view["fact"].get("basis") == "FACT":
            # Фактический расход ВВ — по MagEX, когда расход по нарядам внесён (решение В7 PR 7).
            if abs(float(view["fact"].get("explosive_kg") or 0.0) - magex_kg) > 1e-6:
                issues.append({
                    "level": "warning", "code": "magex_fact_mismatch",
                    "message": f"Расход ВВ по MagEX {magex_kg:g} кг, по факту заряжания "
                               f"{float(view['fact'].get('explosive_kg') or 0.0):g} кг: в акте — по MagEX.",
                    "path": "seed.fact",
                })
            volume = float(payload.get("accepted_volume_m3") or seed.get("volume_contour_m3") or 0.0)
            view["fact"] = {
                **view["fact"], "explosive_kg": magex_kg, "explosive_source": "MAGEX",
                "q_kg_m3": round(magex_kg / volume, 2) if volume > 0 else None,
            }
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
    # Значения по умолчанию ручного ввода (PR 6, §14, В3 и В7): окно показывает их
    # в полях, выпуск и предпросмотр подставляют в пустые поля.
    site_code = str((context.get("project") or {}).get("site_code") or "")
    view["defaults"] = layer_defaults(
        layer["kind"], seed, payload, site=_site_record(snapshot, "mass_blast_sites", site_code),
        previous_naryad=state.get("previous_naryad"), view=view, created_on=created_on(layer.get("created_at")),
    )
    return {**layer, "view": view, "issues": issues}


def _with_remember(
    layers: list[dict[str, Any]], economics_repository: EconomicsRepository | None, organization_id: str,
) -> list[dict[str, Any]]:
    """«Запомнить для объекта» у полей слоя — по текущему справочнику, а не по ревизии,
    на которой выпущен проект: пишется запомненное именно в текущий (ревью Codex)."""

    from api.services.mass_blast_remember import rememberable

    if not layers:
        return layers
    try:
        current = economics_repository.get_reference_snapshot(organization_id) if economics_repository is not None else None
    except Exception:  # noqa: BLE001 — без справочника запоминать некуда
        current = None
    for layer in layers:
        magex = layer["view"].get("magex")
        if layer["kind"] == "NARYAD" and magex and magex.get("mode"):
            # Взрывник наряда для MagEX — по текущему справочнику «Взрывники» (решение В2).
            from api.services.magex_naryad_service import resolved_blaster

            magex["blaster"] = resolved_blaster(current, organization_id, layer, effective_payload(layer))
        site_code = str(((layer.get("seed") or {}).get("project") or {}).get("site_code") or "")
        layer["view"]["rememberable"] = (
            {} if current is None
            else rememberable(_site_record(current, "mass_blast_sites", site_code), layer_kind=layer["kind"])
        )
    return layers


def effective_payload(viewed: Mapping[str, Any]) -> dict[str, Any]:
    """Ручной ввод слоя для выпуска и предпросмотра: пустые поля — значениями по умолчанию."""

    return fill_layer_empty(viewed["payload"], (viewed.get("view") or {}).get("defaults") or {})


def _previous_naryad(
    repository: PostgresMassBlastRepository, organization_id: str, project: Mapping[str, Any]
) -> list[dict[str, Any]]:
    """Ручной ввод нарядов прошлых проектов того же объекта, от последнего (склад, разрешение,
    транспорт): поле, взятое прошлым нарядом по умолчанию, ищется у нарядов раньше."""

    from api.services.mass_blast_prefill import previous_v2_projects

    payloads: list[dict[str, Any]] = []
    try:
        for previous in previous_v2_projects(
            repository, organization_id, str(project.get("site_code") or ""), exclude=str(project.get("id") or ""),
            before=str(project.get("created_at") or ""),
        ):
            naryads = [layer for layer in repository.list_layers(organization_id, previous["id"]) if layer["kind"] == "NARYAD"]
            naryads.sort(key=lambda layer: str(layer.get("updated_at") or ""), reverse=True)
            payloads += [dict(layer["payload"]) for layer in naryads]
    except Exception:  # noqa: BLE001 — прошлые наряды дают только умолчания
        return payloads
    return payloads


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


def _accepted_magex_lines(repository: PostgresMassBlastRepository, organization_id: str, layer_id: str) -> list[dict[str, Any]]:
    """Строки выписки последней принятой MagEX версии наряда (позиция MagEX → ключи строк наряда)."""

    accepted = [item for item in repository.list_magex_versions(organization_id, layer_id) if item["status"] == "ACCEPTED"]
    if not accepted or not accepted[-1].get("layer_revision_id"):
        return []
    revision = repository.get_layer_revision(organization_id, accepted[-1]["layer_revision_id"])
    return list(((revision.get("context") or {}).get("magex") or {}).get("lines") or [])


def _magex_state(repository: PostgresMassBlastRepository, organization_id: str, layer: Mapping[str, Any]) -> dict[str, Any]:
    """Что слой берёт из MagEX (TASK-018 PR 7): состояние наряда, исполнение для граф после взрыва,
    у акта приёмки — израсходованное ВВ по нарядам проекта, когда расход внесён (решение В7)."""

    from api.services import magex_naryad_service as magex

    if layer["kind"] == "NARYAD":
        state: dict[str, Any] = {"magex": magex.layer_state(repository, organization_id, layer["id"])}
        accepted_lines = state["magex"].pop("accepted_lines", [])
        execution = state["magex"].get("execution")
        if execution:
            state["magex_execution"] = execution
            state["magex_lines"] = accepted_lines
        return state
    total = 0.0
    found = False
    for naryad in repository.list_layers(organization_id, layer["project_id"]):
        if naryad["kind"] != "NARYAD":
            continue
        stored = repository.magex_execution(organization_id, naryad["id"])
        if not stored:
            continue
        lines = _accepted_magex_lines(repository, organization_id, naryad["id"])
        explosive_keys = {
            str(line.get("key")) for line in naryad["seed"].get("materials") or [] if line.get("kind") == "explosive"
        }
        value = explosive_consumed_kg(stored["execution"], lines, explosive_keys)
        if value is not None:
            total += value
            found = True
    return {"magex_explosive_kg": round(total, 3)} if found else {}


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
    if layer["kind"] == "NARYAD":
        project = project or repository.get_project(organization_id, layer["project_id"])
        if latest is not None and "previous_naryad" in latest:
            state["previous_naryad"] = latest["previous_naryad"]  # type: ignore[assignment]
        else:
            state["previous_naryad"] = _previous_naryad(repository, organization_id, project)
            if latest is not None:
                latest["previous_naryad"] = state["previous_naryad"]  # type: ignore[assignment]
    if config.magex_integration_enabled() and layer["kind"] in ("NARYAD", "ACCEPTANCE_ACT"):
        state.update(_magex_state(repository, organization_id, layer))
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
    return _with_remember(result, economics_repository, organization_id)


def get_layer(
    repository: PostgresMassBlastRepository, economics_repository: EconomicsRepository | None, organization_id: str, layer_id: str,
) -> dict[str, Any]:
    layer = repository.get_layer(organization_id, layer_id)
    context = repository.get_revision(organization_id, layer["project_revision_id"])["context"]
    return _with_remember([_with_view(
        layer, _snapshot(economics_repository, organization_id, context), context,
        _fact_state(repository, organization_id, layer, context),
    )], economics_repository, organization_id)[0]


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
    return _with_remember([_with_view(layer, snapshot, context, state)], economics_repository, organization_id)[0]


def _check_after_blast(kind: str, project: Mapping[str, Any], data: Mapping[str, Any], stored: Mapping[str, Any]) -> None:
    """Графы наряда «после взрыва» правятся только у проекта со взрывом (решение В9 PR 5)."""

    if kind != "NARYAD" or str(project.get("lifecycle_status") or "") in AFTER_BLAST_STATUSES:
        return
    if any((data.get(key) or {}) != (stored.get(key) or {}) for key in AFTER_BLAST_KEYS):
        raise ValueError("Графы «выдано», «израсходовано», «возвращено» заполняются после взрыва (проект «выполнен»).")


def _check_magex_lock(
    repository: PostgresMassBlastRepository, organization_id: str, layer: Mapping[str, Any], data: Mapping[str, Any],
) -> None:
    """После выдачи ВМ по наряду (MagEX) склад, взрывник, дата выписки, запас, № и допуски не меняются (§7)."""

    if layer["kind"] != "NARYAD" or not config.magex_integration_enabled():
        return
    from api.services.magex_naryad_service import ISSUED_STATUSES, LOCKED_PAYLOAD_KEYS

    stored = repository.magex_execution(organization_id, layer["id"])
    if not stored or stored["status"] not in ISSUED_STATUSES:
        return
    changed = [key for key in LOCKED_PAYLOAD_KEYS if (data.get(key) or None) != (layer["payload"].get(key) or None)]
    if changed:
        raise ValueError(
            "ВМ по наряду-путёвке уже выданы: склад, взрывник, дата выписки, запас, № и допуски не меняются. "
            "Если нужно больше ВМ — заведите новую наряд-путёвку."
        )


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
    _check_magex_lock(repository, organization_id, layer, data)
    updated = repository.update_layer(organization_id, actor, layer_id, expected_version=expected_version, payload=data)
    context = repository.get_revision(organization_id, updated["project_revision_id"])["context"]
    return _with_remember([_with_view(
        updated, _snapshot(economics_repository, organization_id, context), context,
        _fact_state(repository, organization_id, updated, context, project),
    )], economics_repository, organization_id)[0]


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
            "layer": _with_remember([_with_view(layer, snapshot, context, _fact_state(repository, organization_id, layer, context, project))],
                                    economics_repository, organization_id)[0],
        }
    updated = repository.update_layer(
        organization_id, actor, layer_id, expected_version=expected_version, seed=new_seed, project_revision_id=revision["id"],
    )
    return {
        "applied": True, "changes": changes,
        "layer": _with_remember([_with_view(updated, snapshot, context, _fact_state(repository, organization_id, updated, context, project))],
                                economics_repository, organization_id)[0],
    }


def issue_layer(
    repository: PostgresMassBlastRepository,
    economics_repository: EconomicsRepository | None,
    organization_id: str,
    actor: str,
    layer_id: str,
    expected_version: int,
    *,
    magex: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Неизменяемая ревизия слоя: перенесённое, введённое и вычисленное (строки наряда).

    Наряд при включённой интеграции с MagEX (TASK-018 PR 7): настроена — выпуск
    только «Разрешить» (`magex` — версия выписки и строка JWS для QR); не
    настроена — снимок помечается «вне учёта MagEX». Флаг выключен — ключа нет.
    """

    layer = repository.get_layer(organization_id, layer_id)
    mode = magex_mode(organization_id) if layer["kind"] == "NARYAD" else None
    if mode == "ONLINE" and magex is None:
        raise ValueError("Наряд-путёвка выпускается кнопкой «Разрешить»: печать — после того, как её примет MagEX.")
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
        # Пустые поля — значениями по умолчанию: ревизия печатает то, что окно показывало.
        "payload": effective_payload(viewed),
        "view": {key: value for key, value in viewed["view"].items() if key not in VIEW_STATE_KEYS},
    }
    if magex is not None:
        snapshot["magex"] = dict(magex)
    elif mode == "OFFLINE":
        snapshot["magex"] = {"mode": "OFFLINE", "reason": offline_reason(organization_id)}
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
