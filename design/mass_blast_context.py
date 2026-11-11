"""Документный контекст проекта массового взрыва v2 (TASK-018, PR 2).

Контекст v2 — надмножество v1 (`design.mass_blast.build_document_context`,
он не меняется): те же ключи той же формы плюс реквизиты, роли распорядка,
расчёты по каждому блоку (безопасные расстояния, расход ВМ, техрасчёт,
таблица параметров), опасные зоны проекта, охраняемые объекты, распорядок и
замечания. Нынешняя заглушка рендера печатает и ревизию v2, пока PR 3 не
сделает свой рендер. `safety_plan.danger_zone_radius_m` в v2 — расчётная
зона для людей, а не ручной ввод.

Чистые функции: проекты блоков, записи справочника и слои ситуации
передаёт сервис (`api/services/mass_blast_service.py`). Проекты блоков
только читаются.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Sequence

from design.mass_blast import (
    ProjectBlock,
    ValidationIssue,
    build_document_context,
    validate_project_context,
)
from design.mass_blast_calc import MASS_BLAST_CALC_VERSION, explosives_consumption
from design.mass_blast_objects import ObjectZones, assess_project_objects, situation_candidates
from design.mass_blast_schedule import PERSONNEL_ROLES, build_schedule
from design.mass_blast_table import DEFAULT_CHARGE_ROUND_KG, parameter_table
from design.mass_blast_techcalc import technical_calculation
from design.models import BlastDesign
from design.safety import SAFETY_FORMULA_VERSION, num
from design.safety.design import SafetyResult, safety_for_design
from design.safety.holes import material_index
from design.safety.params import safety_params

__all__ = [
    "CONTEXT_VERSION_V2",
    "BlockSource",
    "ContextReferences",
    "build_document_context_v2",
    "validate_project_context_v2",
]

CONTEXT_VERSION_V2 = 2
MANUAL_ZONE_KINDS = ("people", "mechanisms", "buildings")


@dataclass(frozen=True)
class BlockSource:
    """Что нужно расчёту по одному блоку, кроме payload проекта МВ."""

    design: BlastDesign
    site_safety: Mapping[str, Any] | None = None     # payload записи `blast_safety` объекта; None — записи нет
    rock: Mapping[str, Any] | None = None            # payload породы блока
    materials: Sequence[Any] = ()


@dataclass(frozen=True)
class ContextReferences:
    """Справочник ревизии проекта: реквизиты объекта и профиль документов."""

    site: Mapping[str, Any] | None = None            # payload `mass_blast_sites` объекта
    profile: Mapping[str, Any] | None = None         # payload `mass_blast_profiles`
    situation_layers: Sequence[Mapping[str, Any]] = ()
    situation_issues: Sequence[Mapping[str, str]] = ()
    has_situation_refs: bool = False
    issues: Sequence[Mapping[str, str]] = field(default_factory=tuple)


def _issue(level: str, code: str, message: str, path: str = "") -> dict[str, str]:
    return {"level": level, "code": code, "message": message, "path": path}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _manual_zones(payload: Mapping[str, Any]) -> tuple[dict[str, tuple[float, str]], list[dict[str, str]]]:
    zones: dict[str, tuple[float, str]] = {}
    issues: list[dict[str, str]] = []
    raw = (payload.get("safety_plan") or {}).get("manual_zones") or {}
    for kind in MANUAL_ZONE_KINDS:
        entry = raw.get(kind) if isinstance(raw, Mapping) else None
        if not entry:
            continue
        try:
            if not isinstance(entry, Mapping):
                raise TypeError(entry)
            value = float(entry.get("value"))
        except (TypeError, ValueError):
            issues.append(
                _issue(
                    "error",
                    "manual_value_invalid",
                    f"Ручная опасная зона «{kind}» задаётся значением и причиной ({{value, reason}}), значение — число.",
                    f"safety_plan.manual_zones.{kind}",
                )
            )
            continue
        zones[kind] = (value, _text(entry.get("reason")))
    return zones, issues


def _signer(
    own: Mapping[str, Any] | None,
    site: Mapping[str, Any] | None,
    prefix: str,
) -> dict[str, Any]:
    """Подписант: заданное в проекте главнее справочника объекта."""

    own = own or {}
    site = site or {}
    position = _text(own.get("position")) or _text(site.get(f"{prefix}_approver_position"))
    name = _text(own.get("name")) or _text(site.get(f"{prefix}_approver_name"))
    authority = _text(own.get("authority")) or _text(site.get(f"{prefix}_approver_authority"))
    is_head = own.get("is_head")
    if is_head is None:
        is_head = bool(site.get(f"{prefix}_approver_is_head", True))
    return {"position": position, "name": name, "authority": authority, "is_head": bool(is_head)}


def _requisites(payload: Mapping[str, Any], site: Mapping[str, Any] | None) -> tuple[dict[str, Any], list[dict[str, str]]]:
    own = dict(payload.get("requisites") or {})
    site = site or {}
    issues: list[dict[str, str]] = []
    customer = _signer(own.get("customer_approver"), site, "customer")
    contractor = _signer(own.get("contractor_approver"), site, "contractor")
    for label, signer, path in (
        ("заказчика", customer, "requisites.customer_approver"),
        ("подрядчика", contractor, "requisites.contractor_approver"),
    ):
        if signer["name"] and not signer["is_head"] and not signer["authority"]:
            issues.append(
                _issue(
                    "warning",
                    "signer_no_authority",
                    f"Подписант {label} {signer['name']} — не технический руководитель, а основание полномочий "
                    "(приказ № и дата) не указано (п. 414).",
                    path,
                )
            )
    requisites = {
        "project_no": _text(own.get("project_no")),
        "project_date": _text(own.get("project_date")),
        "tp_basis": _text(own.get("tp_basis")) or _text(site.get("tp_basis")),
        "made_by": dict(own.get("made_by") or {}),
        "checked_by": dict(own.get("checked_by") or {}),
        "customer_name": _text(own.get("customer_name")),
        "contractor_name": _text(own.get("contractor_name")),
        "customer_approver": customer,
        "contractor_approver": contractor,
        "agreements": [dict(item) for item in own.get("agreements") or [] if _text(item.get("name")) or _text(item.get("position"))],
        "surveyor_name": _text(own.get("surveyor_name")),
        "drilled_by": _text(own.get("drilled_by")),
        "customer_tech_contact": _text(site.get("customer_tech_contact")),
    }
    return requisites, issues


def _people(payload: Mapping[str, Any]) -> dict[str, dict[str, str]]:
    """Роль → {position, name}: роли распорядка и две роли согласования (#113)."""

    people: dict[str, dict[str, str]] = {}
    for item in payload.get("responsibilities") or []:
        role = _text(item.get("role_code"))
        if role:
            people[role] = {"position": _text(item.get("position_name")), "name": _text(item.get("employee_name"))}
    for item in payload.get("personnel") or []:
        role = _text(item.get("role_code"))
        if role:
            people[role] = {"position": _text(item.get("position")), "name": _text(item.get("name"))}
    # Раздатчик ВМ по умолчанию — ответственный за выдачу ВМ (роль согласования).
    if "storekeeper" not in people and "explosives_supervisor" in people:
        people["storekeeper"] = dict(people["explosives_supervisor"])
    return people


def _block_detail(payload_block: Mapping[str, Any]) -> dict[str, Any]:
    return dict(payload_block.get("details") or {})


def _scaled_issues(items: Iterable[Any], path: str) -> list[dict[str, str]]:
    result = []
    for item in items:
        data = item.to_dict() if hasattr(item, "to_dict") else dict(item)
        result.append(_issue(data["level"], data["code"], data["message"], data.get("path") or path))
    return result


def build_document_context_v2(
    payload: Mapping[str, Any],
    blocks: Sequence[ProjectBlock],
    sources: Sequence[BlockSource],
    references: ContextReferences | None = None,
) -> dict[str, Any]:
    """Контекст v2 по сохранённому проекту МВ; `sources[i]` — проект блока `blocks[i]`."""

    if len(sources) != len(blocks):
        raise ValueError("Каждому блоку проекта МВ нужен свой проект блока.")
    references = references or ContextReferences()
    context = build_document_context(dict(payload), blocks)
    context["document_context_version"] = CONTEXT_VERSION_V2
    context["formula_version"] = MASS_BLAST_CALC_VERSION
    context["safety_formula_version"] = SAFETY_FORMULA_VERSION
    issues: list[dict[str, str]] = [dict(item) for item in references.issues]

    site = references.site or {}
    profile = references.profile or {}
    explosives = dict(payload.get("explosives") or {})
    schedule_payload = dict(payload.get("schedule") or {})
    overrides = dict(payload.get("safety_overrides") or {})
    manual_zones, zone_issues = _manual_zones(payload)
    issues += zone_issues
    try:
        charge_round = float(profile.get("charge_round_kg") or DEFAULT_CHARGE_ROUND_KG)
    except (TypeError, ValueError):
        charge_round = DEFAULT_CHARGE_ROUND_KG
    payload_blocks = list(payload.get("blocks") or [])

    computed: list[dict[str, Any]] = []
    for index, (block, source) in enumerate(zip(blocks, sources)):
        path = f"blocks[{index}]"
        design = source.design
        materials = list(source.materials)
        params = safety_params(source.site_safety, source.rock, overrides=overrides, manual_zones=manual_zones)
        safety = safety_for_design(design, params, materials=materials)
        consumption = explosives_consumption(design, materials, starter_product=_text(explosives.get("starter_product")))
        detail = _block_detail(payload_blocks[index] if index < len(payload_blocks) else {})
        table = parameter_table(
            design,
            material_index(materials),
            charge_round_kg=charge_round,
            hole_notes=detail.get("hole_notes") or {},
            flyrock_by_hole={key: round(value) for key, value in safety.flyrock.per_hole.items()},
            stemming_by_hole={hole.hole_id: hole.stemming_m for hole in safety.holes},
        )
        issues += _scaled_issues(safety.issues, f"{path}.safety")
        issues += [{**issue, "path": issue.get("path") or f"{path}.parameter_table"} for issue in table.issues]
        for line in consumption:
            if line.warning:
                issues.append(_issue("warning", line.warning, line.message, f"{path}.consumption"))
        computed.append(
            {
                "block": block,
                "design": design,
                "detail": detail,
                "safety": safety,
                "consumption": consumption,
                "table": table,
                "volume": float(block.snapshot.get("totals", {}).get("block_volume_m3") or 0.0),
            }
        )

    if len(computed) > 1:
        issues.append(
            _issue(
                "warning",
                "multi_block_timing",
                "В проекте несколько блоков: сейсмика и воздушная волна посчитаны по каждому блоку отдельно — "
                "сети блоков независимы, время между блоками не задано.",
                "blocks",
            )
        )

    zones = _project_zones([item["safety"] for item in computed])
    object_zones = _object_zones([item["safety"] for item in computed], zones)
    geometry = [
        (
            item["design"].contour.points_xy if len(item["design"].contour.vertices) >= 3 else [],
            [(hole.collar.x, hole.collar.y) for hole in item["design"].holes if hole.enabled],
        )
        for item in computed
    ]
    candidates = situation_candidates(references.situation_layers, geometry)
    rows, object_issues = assess_project_objects(candidates, list(payload.get("protected_objects") or []), object_zones)
    issues += _scaled_issues(object_issues, "protected_objects")
    objects = [row.to_dict() for row in rows]
    for row in rows:
        if row.inside and not row.measures:
            issues.append(
                _issue(
                    "error",
                    "object_in_zone_no_measures",
                    f"«{row.name}» в опасной зоне ({num(row.distance_m)} м < {num(row.required_m)} м): "
                    "укажите мероприятия по защите (п. 14 распорядка, п. 138).",
                    "protected_objects",
                )
            )
    if not references.has_situation_refs:
        issues.append(
            _issue(
                "warning",
                "situation_missing",
                "У блоков нет ситуации карьера: охраняемые объекты — только из ручного списка проекта.",
                "protected_objects",
            )
        )
    issues += [dict(item) for item in references.situation_issues]

    q_tp = _q_tp(explosives, site)
    texts = {
        "tp_basis": _text((payload.get("requisites") or {}).get("tp_basis")) or _text(site.get("tp_basis")),
        "initiation": _text(explosives.get("initiation")),
        "scheme": _text(explosives.get("scheme")),
        "charge_design": _text(explosives.get("charge_design")),
        "stemming_material": _text(explosives.get("stemming_material")),
        "bit_mm": explosives.get("bit_mm"),
        "reaming_k": explosives.get("reaming_k"),
        "other": _text(schedule_payload.get("other_conditions")),
        "airblast_buildings": _text(schedule_payload.get("airblast_buildings")),
    }
    blocks_v2: list[dict[str, Any]] = []
    for index, item in enumerate(computed):
        block: ProjectBlock = item["block"]
        detail = item["detail"]
        block_fields = {
            "code": block.code,
            "horizon": block.horizon,
            "rock_text": detail.get("rock_text"),
            "hydro_text": detail.get("hydro_text"),
            "purpose": detail.get("purpose"),
            "area_m2": detail.get("area_m2"),
        }
        sections, calc_issues = technical_calculation(
            item["design"],
            block=block_fields,
            safety=item["safety"],
            table=item["table"],
            consumption=item["consumption"],
            texts=texts,
            q_tp=q_tp,
            objects=objects,
            volume_m3=item["volume"],
        )
        issues += [{**issue, "path": issue.get("path") or f"blocks[{index}].technical_calculation"} for issue in calc_issues]
        blocks_v2.append(
            {
                "design_id": block.design_id,
                "code": block.code,
                "horizon": block.horizon,
                "details": block_fields,
                "safety": item["safety"].to_dict(),
                "consumption": [line.to_dict() for line in item["consumption"]],
                "technical_calculation": sections,
                "parameter_table": item["table"].to_dict(),
            }
        )

    requisites, requisite_issues = _requisites(payload, site)
    issues += requisite_issues
    people = _people(payload)
    totals = {
        "explosive_kg": sum(line.quantity for item in computed for line in item["consumption"] if line.kind == "explosive"),
        "primer_kg": sum(float(line.mass_kg or 0.0) for item in computed for line in item["consumption"] if line.kind == "primer"),
        "hole_count": sum(item["table"].totals["hole_count"] for item in computed),
    }
    explosive_names = sorted({line.name for item in computed for line in item["consumption"] if line.kind == "explosive"})
    surface = sorted({float(c.delay_ms) for item in computed for c in item["design"].network.surface_connectors})
    downhole = sorted({float(c.delay_ms) for item in computed for c in item["design"].network.downhole_connectors})
    intervals = " / ".join(num(value, 0 if value.is_integer() else 1) for value in surface)
    if downhole:
        intervals += ("; " if intervals else "") + "в скважине " + " / ".join(num(value, 0 if value.is_integer() else 1) for value in downhole)
    schedule, schedule_issues = build_schedule(
        project=context["project"],
        schedule=schedule_payload,
        people=people,
        zones={key: zones[key]["value"] for key in MANUAL_ZONE_KINDS},
        objects=objects,
        blocks=[{"code": item["block"].code, "horizon": item["block"].horizon} for item in computed],
        totals=totals,
        guard_posts=list(payload.get("guard_posts") or []),
        texts={"explosives": ", ".join(explosive_names), "initiation": _text(explosives.get("initiation")), "intervals": f"{intervals} мс" if intervals else ""},
        signals={
            "warning": _text(profile.get("signal_warning")),
            "combat": _text(profile.get("signal_combat")),
            "clear": _text(profile.get("signal_clear")),
        },
        profile_texts={_text(row.get("point")): row for row in profile.get("schedule_texts") or []},
    )
    issues += schedule_issues

    context["safety_plan"] = {
        **dict(context.get("safety_plan") or {}),
        "danger_zone_radius_m": zones["people"]["value"],
    }
    context["requisites"] = requisites
    context["personnel"] = [
        {"role_code": role, "role_label": PERSONNEL_ROLES.get(role, role), **person}
        for role, person in people.items()
        if role in PERSONNEL_ROLES
    ]
    context["explosives"] = {key: explosives.get(key) for key in sorted(explosives)}
    context["schedule_input"] = schedule_payload
    context["blocks_v2"] = blocks_v2
    context["zones"] = zones
    context["protected_objects"] = objects
    context["schedule"] = schedule
    context["q_tp"] = q_tp
    context["issues"] = issues
    return context


def _q_tp(explosives: Mapping[str, Any], site: Mapping[str, Any]) -> dict[str, Any]:
    own = explosives.get("q_tp_kg_m3")
    if own not in (None, ""):
        return {
            "value": float(own),
            "source": "MANUAL_OVERRIDE",
            "basis": "задано в проекте МВ",
            "justification": _text(explosives.get("q_just")) or _text(site.get("q_just")),
        }
    value = site.get("q_tp_kg_m3")
    return {
        "value": float(value) if value not in (None, "") else None,
        "source": "REFERENCE",
        "basis": _text(site.get("q_tp_source")),
        "justification": _text(explosives.get("q_just")) or _text(site.get("q_just")),
    }


def _project_zones(results: Sequence[SafetyResult]) -> dict[str, dict[str, Any]]:
    """Зоны проекта — наибольшие по блокам; с номером определяющего блока."""

    zones: dict[str, dict[str, Any]] = {}
    for kind in MANUAL_ZONE_KINDS:
        best: tuple[float, int, Any] | None = None
        for index, result in enumerate(results):
            value = getattr(result.zones, kind)
            if value.value is not None and (best is None or value.value > best[0]):
                best = (float(value.value), index, value)
        if best is None:
            zones[kind] = {"value": None, "block_index": None}
            continue
        zones[kind] = {"value": best[0], "block_index": best[1], **best[2].to_dict()}
        if kind == "people":
            zones[kind]["factor"] = results[best[1]].zones.people_factor
        if kind == "buildings":
            zones[kind]["factor"] = results[best[1]].zones.buildings_factor
    return zones


def _object_zones(results: Sequence[SafetyResult], zones: Mapping[str, Mapping[str, Any]]) -> ObjectZones:
    def biggest(values: Iterable[float | None]) -> float:
        known = [float(value) for value in values if value is not None]
        return max(known) if known else 0.0

    params = results[0].params if results else None
    return ObjectZones(
        people_m=float(zones["people"]["value"] or 0.0),
        mechanisms_m=float(zones["mechanisms"]["value"] or 0.0),
        seismic_m=biggest(result.seismic.accepted.value for result in results),
        seismic_raw_m=biggest(result.seismic.calculated.value for result in results),
        airblast_m=biggest(result.airblast.accepted.value for result in results),
        buildings_m=float(zones["buildings"]["value"] or 0.0),
        k_ground=params.k_ground if params else 0.0,
        k_structure=params.k_structure if params else 0.0,
        buildings_manual=zones["buildings"].get("source") == "MANUAL_OVERRIDE",
    )


def validate_project_context_v2(context: Mapping[str, Any], *, require_attachments: bool = False) -> list[ValidationIssue]:
    """Проверки v1 (кроме ручного радиуса опасной зоны — в v2 он расчётный) и замечания расчёта v2."""

    issues = [
        issue
        for issue in validate_project_context(dict(context), require_attachments=require_attachments)
        if issue.code != "danger_zone"
    ]
    if not (context.get("zones") or {}).get("people", {}).get("value"):
        issues.append(
            ValidationIssue("error", "danger_zone", "Опасная зона для людей не рассчитана: проверьте заряжание блоков.", "zones.people")
        )
    seen: set[tuple[str, str, str]] = set()
    for item in context.get("issues") or []:
        key = (str(item.get("code")), str(item.get("message")), str(item.get("path") or ""))
        if key in seen:
            continue
        seen.add(key)
        level = "error" if item.get("level") == "error" else "warning"
        issues.append(ValidationIssue(level, key[0], key[1], key[2]))
    return issues
