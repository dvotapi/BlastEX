"""Слои проекта массового взрыва: документы дня взрыва (TASK-018, PR 2, §2.1).

Проект (титул, техрасчёт, таблица, распорядок, графика) — одна ревизия
проекта. Документы 6–10 — **слои**: у каждого свои данные, ревизии и
подписи; слой ссылается на ревизию проекта и её не меняет.

- Открытие: наряд-путёвка, уведомление, акт готовности и слой «Факт» — после
  `approved`; талон-допуск и акт приёмки — после `executed`. Акт готовности не
  заводится, если бурит и взрывает Общество («бурение выполнил: Общество»,
  п. 413) — готовность тогда отмечается в распорядке.
- Перенос (`layer_seed`): из контекста ревизии проекта — блоки, ВМ по видам
  и маркам, ответственные, зоны, дата и время. Введённое вручную (запас,
  номера, время, подписанты) хранится отдельно (`payload`) и переносом не
  трогается.
- Наряд-путёвка: строки ВМ «по проекту / запас / к выдаче»; к выдаче = по
  проекту + запас. Запас по умолчанию — из раздела `blast_safety` объекта
  (ПД, НСИ, стартеры) один раз на группу — на самую большую её строку,
  иначе 0. Расчёты проекта запас не меняет.
- Слой «Факт» (`EXECUTION`, TASK-018 PR 5): снимок факта бурения и заряжания
  проектов блоков (`design/mass_blast_fact.py`) — графы «Ф» таблицы параметров,
  фактический расход ВМ, Г.1 по съёмке. Отказы и время взрыва по факту —
  ручной ввод слоя. Акт приёмки и наряд после взрыва берут факт из последней
  выпущенной ревизии «Факта» (`execution_summary`); талон — своё фактическое
  время взрыва.
- «Устарел» — ревизия проекта слоя не текущая. `seed_diff` показывает, что
  изменится при повторном переносе; перенос — только с подтверждения.

Чистые функции без БД: хранение — `design/mass_blast_repository.py`.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Any, Mapping, Sequence

__all__ = [
    "LAYER_KINDS",
    "LAYER_OPEN_AFTER",
    "LAYER_LABELS",
    "MULTI_LAYER_KINDS",
    "layer_open_issue",
    "layer_seed",
    "naryad_lines",
    "naryad_totals",
    "seed_diff",
    "acceptance_view",
    "execution_summary",
    "execution_seed_diff",
    "execution_view",
    "naryad_after_blast",
    "talon_view",
]

# Условия готовности блока к заряжанию (акт, п. 413) — тексты формы ВМ.09.03 v0.11.
READINESS_CONDITIONS = (
    "Скважины пробурены по проекту (схеме расположения) и очищены; маркшейдерская съёмка блока передана, "
    "фактические глубины внесены в таблицу параметров (п. 412)",
    "Отклонения скважин от проекта (глубина, ЛСПП, расстояния) — в пределах ±0,5 м; отклонения указаны "
    "в примечании таблицы",
    "Блок очищен от посторонних предметов, конструкций и оборудования; подъездные пути и площадка подготовлены для СЗМ",
    "Забоечный материал завезён на блок в требуемом объёме",
    "Обводнённость скважин проверена; обводнённые скважины отмечены в таблице параметров",
    "Электроэнергия на блоке отключена; запретная зона (≥ 20 м) обозначена знаками",
    "Охраняемые объекты в опасной зоне уведомлены; условия владельцев выполнены (при наличии)",
)
# Акт приёмки выполненных работ: текст формы ВМ.09.03 v0.11 (своя форма — в
# профиле документов, `acceptance_text`). Подстановки — {блок}, {горизонт}, {дата взрыва}.
DEFAULT_ACCEPTANCE_TEXT = (
    "{дата взрыва} был произведён массовый взрыв блока № {блок}, горизонт {горизонт} м.\n"
    "По результатам первичного осмотра отказавших зарядов ВВ обнаружено не было. Мероприятия по безопасности "
    "при взрывных работах выполнены в полном объёме."
)
# Группы запаса для красной строки под итогом наряда (форма 4).
RESERVE_GROUPS = (
    ("explosive", "ВВ", "кг"),
    ("primer", "ПД", "шт"),
    ("nsi_downhole", "НСИ скважинные", "шт"),
    ("nsi_surface", "поверхностные", "шт"),
    ("starter", "стартовые", "шт"),
)

LAYER_KINDS = ("NARYAD", "NOTIFICATION", "READINESS_ACT", "TALON", "ACCEPTANCE_ACT", "EXECUTION")
LAYER_LABELS = {
    "NARYAD": "Наряд-путёвка",
    "NOTIFICATION": "Уведомление о массовом взрыве",
    "READINESS_ACT": "Акт готовности блока к заряжанию",
    "TALON": "Талон-допуск",
    "ACCEPTANCE_ACT": "Акт приёмки выполненных работ",
    "EXECUTION": "Таблица параметров (исполнительная) и Г.1 по съёмке",
}
# Нарядов бывает несколько (больше ВМ после выдачи — новый наряд), уведомлений —
# по одному на адресата; остальных слоёв у проекта по одному.
MULTI_LAYER_KINDS = frozenset({"NARYAD", "NOTIFICATION"})
LAYER_OPEN_AFTER = {
    "NARYAD": {"approved", "executed", "closed"},
    "NOTIFICATION": {"approved", "executed", "closed"},
    "READINESS_ACT": {"approved", "executed", "closed"},
    "TALON": {"executed", "closed"},
    "ACCEPTANCE_ACT": {"executed", "closed"},
    # Факт бурения нужен до заряжания (п. 412): слой «Факт» — после утверждения,
    # перевыпуск — после заряжания и взрыва (решение владельца В2 PR 5).
    "EXECUTION": {"approved", "executed", "closed"},
}
# Графы наряда «после взрыва» (выдано, израсходовано, возвращено) — только у
# проекта со взрывом (решение В9 PR 5).
AFTER_BLAST_STATUSES = frozenset({"executed", "closed"})
TALON_AFTER_MIN = 30
# Строки ВМ, запас которых по умолчанию берётся из справочника объекта.
_RESERVE_DEFAULTS = {"primer": "primers", "nsi_downhole": "nsi", "nsi_surface": "nsi", "starter": "starters"}


def layer_open_issue(kind: str, project_status: str, context: Mapping[str, Any]) -> str | None:
    """Почему слой нельзя открыть; None — можно."""

    if kind not in LAYER_KINDS:
        return f"Неизвестный вид слоя: {kind}."
    if project_status not in LAYER_OPEN_AFTER[kind]:
        stage = "утверждения проекта" if "approved" in LAYER_OPEN_AFTER[kind] else "отметки взрыва"
        return f"«{LAYER_LABELS[kind]}» открывается после {stage}."
    if int(context.get("document_context_version") or 1) < 2:
        return "Слои дня взрыва есть только у проекта по форме ВМ.09.03 (контекст v2)."
    if kind == "READINESS_ACT" and str((context.get("requisites") or {}).get("drilled_by") or "") == "CONTRACTOR":
        return "Бурит и взрывает Общество: акт готовности не составляется, готовность отмечается в распорядке (п. 413)."
    return None


def _line_key(line: Mapping[str, Any]) -> str:
    delay = line.get("delay_ms")
    delay_text = "" if delay is None else f"{float(delay):g}"
    return f"{line.get('kind', '')}:{line.get('name', '')}:{delay_text}"


def _consumption(context: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Расход ВМ проекта по всем блокам, сложенный по виду, марке и замедлению."""

    merged: dict[str, dict[str, Any]] = {}
    for block in context.get("blocks_v2") or []:
        for line in block.get("consumption") or []:
            key = _line_key(line)
            row = merged.setdefault(
                key,
                {
                    "key": key,
                    "kind": line.get("kind", ""),
                    "name": line.get("name", ""),
                    "unit": line.get("unit", ""),
                    "delay_ms": line.get("delay_ms"),
                    "project_qty": 0.0,
                    "mass_kg": None,
                    "mass_known": True,
                },
            )
            row["project_qty"] = round(row["project_qty"] + float(line.get("quantity") or 0.0), 3)
            # Масса ПД неизвестна (`primer_mass_unknown`: расход пишет 0) — масса строки
            # неизвестна целиком, а не занижена: в наряд не идут нулевые килограммы.
            if line.get("warning") == "primer_mass_unknown":
                row["mass_known"] = False
            if line.get("mass_kg") is not None:
                row["mass_kg"] = round(float(row["mass_kg"] or 0.0) + float(line["mass_kg"]), 3)
    return list(merged.values())


def _shift(time_text: str, minutes: int) -> str:
    try:
        moment = datetime.strptime(str(time_text or "")[:5], "%H:%M")
    except ValueError:
        return ""
    return (moment + timedelta(minutes=minutes)).strftime("%H:%M")


def layer_seed(
    kind: str,
    context: Mapping[str, Any],
    *,
    notification: Mapping[str, Any] | None = None,
    facts: Sequence[tuple[Mapping[str, Any], Sequence[Mapping[str, str]]]] | None = None,
    execution: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Данные проекта, которые переносятся в слой (без введённого вручную).

    `facts` — факт блоков для слоя «Факт» (`mass_blast_fact.block_fact` по
    каждому блоку ревизии, с предупреждениями); `execution` — сводка последней
    выпущенной ревизии «Факта» (`execution_summary`) для акта приёмки и наряда
    после взрыва. Без них — данные проекта, как до PR 5 (ключа `fact` нет).
    """

    project = dict(context.get("project") or {})
    requisites = dict(context.get("requisites") or {})
    people = {item.get("role_code"): item for item in context.get("personnel") or []}
    for item in context.get("responsibilities") or []:
        people.setdefault(item.get("role_code"), {"position": item.get("position_name", ""), "name": item.get("employee_name", "")})
    blocks = []
    for block in context.get("blocks_v2") or []:
        table = (block.get("parameter_table") or {}).get("totals") or {}
        blocks.append(
            {
                "code": block.get("code", ""),
                "horizon": block.get("horizon", ""),
                "holes": int(table.get("hole_count") or 0),
                "charge_kg": float(table.get("charge_kg") or 0.0),
                "depth_mean_m": table.get("depth_mean_m"),
                "spacing_mean_m": table.get("spacing_mean_m"),
                "burden_mean_m": table.get("burden_mean_m"),
            }
        )
    zones = {key: (value or {}).get("value") for key, value in (context.get("zones") or {}).items()}
    seed: dict[str, Any] = {
        "kind": kind,
        "project": {
            "name": project.get("name", ""),
            "project_no": requisites.get("project_no", ""),
            "project_date": requisites.get("project_date", ""),
            "object_name": project.get("object_name", ""),
            "site_code": project.get("site_code", ""),
            "blast_date": project.get("blast_date", ""),
            "blast_time": project.get("blast_time", ""),
        },
        "blocks": blocks,
        "zones": zones,
        "parties": {
            "customer_name": requisites.get("customer_name", ""),
            "contractor_name": requisites.get("contractor_name", ""),
        },
    }
    if kind == "NARYAD":
        seed["materials"] = _consumption(context)
        seed["people"] = {role: _person(people.get(role)) for role in ("blast_manager", "blaster", "site_manager", "storekeeper", "escort")}
    elif kind == "NOTIFICATION":
        explosive = sum(line["project_qty"] for line in _consumption(context) if line["kind"] == "explosive")
        diameters = [row.get("diameter_mm") for block in context.get("blocks_v2") or [] for row in (block.get("parameter_table") or {}).get("rows") or []]
        seed["explosive_kg"] = round(explosive, 3)
        seed["diameter_mm"] = sorted({d for d in diameters if d})
        seed["intervals"] = list(context.get("network_intervals") or [])
        seed["customer_tech_contact"] = requisites.get("customer_tech_contact", "")
        seed["blast_manager"] = _person(people.get("blast_manager"))
        seed["addressee"] = dict(notification or {})
        seed["explosive_names"] = sorted({line["name"] for line in _consumption(context) if line["kind"] == "explosive"})
        seed["letterhead"] = str((context.get("document_texts") or {}).get("letterhead") or "")
    elif kind == "READINESS_ACT":
        seed["drilled_by"] = requisites.get("drilled_by", "")
        seed["surveyor_name"] = requisites.get("surveyor_name", "")
        seed["customer_approver"] = _person(requisites.get("customer_approver"))
        seed["blast_manager"] = _person(people.get("blast_manager"))
        seed["conditions"] = list(READINESS_CONDITIONS)
    elif kind == "TALON":
        seed["admittance_not_before"] = _shift(project.get("blast_time", ""), TALON_AFTER_MIN)
        seed["talon_receiver"] = _person(people.get("talon_receiver"))
        seed["blast_manager"] = _person(people.get("blast_manager"))
    elif kind == "ACCEPTANCE_ACT":
        seed["volume_contour_m3"] = (context.get("totals") or {}).get("block_volume_m3")
        seed["specific_q_kg_m3"] = (context.get("totals") or {}).get("specific_q_kg_m3")
        seed["contract"] = {
            key: requisites.get(key, "")
            for key in ("contract_no", "contract_date", "acceptance_appendix_no", "customer_responsible")
        }
        seed["blast_manager"] = _person(people.get("blast_manager"))
        seed["acceptance_text"] = (
            str((context.get("document_texts") or {}).get("acceptance_text") or "") or DEFAULT_ACCEPTANCE_TEXT
        )
    elif kind == "EXECUTION":
        seed["requisites"] = {key: requisites.get(key) for key in ("surveyor_name", "made_by", "checked_by")}
        seed["blocks_fact"], seed["fact_issues"] = _blocks_fact(context, facts or [])
    if execution is not None and kind in ("NARYAD", "ACCEPTANCE_ACT"):
        seed["fact"] = dict(execution)
    return seed


def _blocks_fact(
    context: Mapping[str, Any], facts: Sequence[tuple[Mapping[str, Any], Sequence[Mapping[str, str]]]]
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    """Слой «Факт» по блокам: строки Р ревизии с графами Ф, расход по факту и Г.1 по съёмке.

    Из ревизии проекта копируется то, что печатается рядом с фактом (строки Р,
    подписи шапки таблицы, геометрия плана Г.1): документ слоя печатается
    только из ревизии слоя.
    """

    blocks: list[dict[str, Any]] = []
    issues: list[dict[str, str]] = []
    project_blocks = list(context.get("blocks") or [])
    for index, block in enumerate(context.get("blocks_v2") or []):
        fact, fact_issues = facts[index] if index < len(facts) else ({}, [])
        table = dict(block.get("parameter_table") or {})
        consumption = list(block.get("consumption") or [])
        p_kg_m = next(
            (item.get("p_kg_m") for item in block.get("technical_calculation") or [] if item.get("number") == "4"), None
        )
        graphics = dict(block.get("graphics") or {})
        source = project_blocks[index] if index < len(project_blocks) else {}
        blocks.append(
            {
                "code": block.get("code", ""),
                "horizon": block.get("horizon", ""),
                "design_id": str(source.get("design_id") or block.get("design_id") or ""),
                "execution_sha256": fact.get("execution_sha256", ""),
                "parameter_table": {
                    "rows": list(fact.get("rows") or table.get("rows") or []),
                    "totals": dict(fact.get("totals") or table.get("totals") or {}),
                    "common_note": table.get("common_note", ""),
                    "charge_round_kg": table.get("charge_round_kg"),
                },
                "summary": {
                    "explosives": list(dict.fromkeys(str(l.get("name")) for l in consumption if l.get("kind") == "explosive")),
                    "primers": list(dict.fromkeys(str(l.get("name")) for l in consumption if l.get("kind") == "primer")),
                    "p_kg_m": p_kg_m,
                    "hardness_f": ((block.get("safety") or {}).get("params") or {}).get("hardness_f"),
                },
                "consumption": list(fact.get("consumption") or []),
                # Г.1 по съёмке: геометрия плана — из ревизии проекта, скважины — по факту.
                "graphics": {
                    **{key: graphics.get(key) for key in ("plan", "contours", "contour_source", "sections", "crs")},
                    "holes": list(fact.get("holes") or []),
                } if graphics else None,
            }
        )
        prefix = f"Блок {block.get('code')}: " if len(context.get("blocks_v2") or []) > 1 else ""
        issues += [{**item, "message": prefix + str(item.get("message", "")), "path": f"blocks_fact[{index}]"}
                   for item in fact_issues]
    return blocks, issues


# --- слой «Факт»: отказы, время взрыва и сводка для других слоёв (PR 5) --------

NOTE_MISFIRE = "отказ"


def execution_view(seed: Mapping[str, Any], payload: Mapping[str, Any]) -> tuple[dict[str, Any], list[dict[str, str]]]:
    """Что печатает слой «Факт»: строки с отказами и примечаниями по факту, итоги отказов."""

    misfired = [str(item).strip() for item in payload.get("misfired_holes") or [] if str(item).strip()]
    notes = {str(key): str(value).strip() for key, value in (payload.get("hole_notes") or {}).items() if str(value or "").strip()}
    known: set[str] = set()
    blocks: list[dict[str, Any]] = []
    issues: list[dict[str, str]] = list(seed.get("fact_issues") or [])
    for block in seed.get("blocks_fact") or []:
        table = dict(block.get("parameter_table") or {})
        rows = []
        misfired_kg = 0.0
        count = 0
        for source in table.get("rows") or []:
            row = dict(source)
            hole_id = str(row.get("hole_id"))
            known.add(hole_id)
            extra = []
            if hole_id in misfired:
                extra.append(NOTE_MISFIRE)
                count += 1
                misfired_kg += float(row.get("charge_fact_exact_kg") or 0.0)
                if not row.get("charged"):
                    issues.append(_issue(
                        "warning", "fact_misfire_not_charged",
                        f"Скважина {hole_id} отмечена отказом, но факта её заряжания нет.", "payload.misfired_holes",
                    ))
            if notes.get(hole_id):
                extra.append(notes[hole_id])
            if extra:
                row["note"] = "; ".join(item for item in (str(row.get("note") or ""), *extra) if item)
            rows.append(row)
        totals = dict(table.get("totals") or {})
        totals["misfired_count"] = count
        totals["misfired_kg"] = round(misfired_kg, 3)
        # В `view` — только то, что меняет ручной ввод (строки с отказами и итоги):
        # геометрия Г.1 и расход остаются в `seed`, ревизия их не дублирует.
        blocks.append({"code": block.get("code", ""), "horizon": block.get("horizon", ""),
                       "parameter_table": {**table, "rows": rows, "totals": totals}})
    unknown = [hole for hole in dict.fromkeys(misfired) if hole not in known]
    if unknown:
        issues.append(_issue(
            "error", "fact_misfire_unknown_hole",
            f"Отказ отмечен у скважин, которых нет в проекте: {', '.join(unknown)}.", "payload.misfired_holes",
        ))
    unknown_notes = [hole for hole in notes if hole not in known]
    if unknown_notes:
        issues.append(_issue(
            "error", "fact_note_unknown_hole",
            f"Примечание по факту у скважин, которых нет в проекте: {', '.join(unknown_notes)}.", "payload.hole_notes",
        ))
    view = {
        "blocks": blocks,
        "blast_date": str(payload.get("blast_date") or ""),
        "blast_time": str(payload.get("blast_time") or ""),
        "misfired_holes": list(dict.fromkeys(misfired)),
    }
    return view, issues


def execution_summary(revision_context: Mapping[str, Any], revision_id: str) -> dict[str, Any]:
    """Сводка выпущенной ревизии «Факта» для акта приёмки и наряда после взрыва."""

    seed = revision_context.get("seed") or {}
    view = revision_context.get("view") or {}
    blocks = []
    for block in view.get("blocks") or seed.get("blocks_fact") or []:
        totals = (block.get("parameter_table") or {}).get("totals") or {}
        charged_kg = float(totals.get("charge_fact_partial_kg") or 0.0)
        misfired_kg = float(totals.get("misfired_kg") or 0.0)
        blocks.append(
            {
                "code": block.get("code", ""),
                "horizon": block.get("horizon", ""),
                "holes": int(totals.get("hole_count") or 0),
                "drilled": int(totals.get("drilled_count") or 0),
                "charged": int(totals.get("charged_count") or 0),
                "charged_kg": round(charged_kg, 3),
                "misfired": int(totals.get("misfired_count") or 0),
                "misfired_kg": round(misfired_kg, 3),
                "spacing_fact_mean_m": totals.get("spacing_fact_mean_m"),
                "burden_fact_mean_m": totals.get("burden_fact_mean_m"),
            }
        )
    merged: dict[str, dict[str, Any]] = {}
    for block in seed.get("blocks_fact") or []:
        for line in block.get("consumption") or []:
            key = _line_key(line)
            row = merged.setdefault(key, {"key": key, "kind": line.get("kind", ""), "name": line.get("name", ""),
                                          "unit": line.get("unit", ""), "delay_ms": line.get("delay_ms"),
                                          "material_code": line.get("material_code", ""), "quantity": 0.0})
            row["quantity"] = round(row["quantity"] + float(line.get("quantity") or 0.0), 3)
    return {
        "execution_revision_id": revision_id,
        "blast_date": str(view.get("blast_date") or ""),
        "blast_time": str(view.get("blast_time") or ""),
        "blocks": blocks,
        "consumption": list(merged.values()),
    }


def _issue(level: str, code: str, message: str, path: str) -> dict[str, str]:
    return {"level": level, "code": code, "message": message, "path": path}


def _shift_moment(day: str, time_text: str, minutes: int) -> tuple[str, str]:
    """Дата и время + `minutes`; время не разобрано — пусто."""

    try:
        moment = datetime.strptime(f"{(day or '2000-01-01')[:10]} {str(time_text or '')[:5]}", "%Y-%m-%d %H:%M")
    except ValueError:
        return "", ""
    shifted = moment + timedelta(minutes=minutes)
    return (shifted.strftime("%Y-%m-%d") if day else ""), shifted.strftime("%H:%M")


def talon_view(seed: Mapping[str, Any], payload: Mapping[str, Any]) -> dict[str, Any]:
    """«Не ранее» талона: фактическое время взрыва + 30 мин, без него — проектное (решение В8)."""

    fired_time = str(payload.get("fired_time") or "")
    if fired_time:
        fired_date = str(payload.get("fired_date") or (seed.get("project") or {}).get("blast_date") or "")
        day, time_text = _shift_moment(fired_date, fired_time, TALON_AFTER_MIN)
        if time_text:
            next_day = bool(fired_date) and day != fired_date[:10]
            return {"admittance_not_before": time_text, "admittance_date": day if next_day else "",
                    "admittance_source": "FACT"}
    return {"admittance_not_before": str(seed.get("admittance_not_before") or ""), "admittance_date": "",
            "admittance_source": "PROJECT"}


def acceptance_view(seed: Mapping[str, Any], payload: Mapping[str, Any]) -> tuple[dict[str, Any], list[dict[str, str]]]:
    """Параметры акта приёмки по факту (решение В10): расход ВВ, сетка и удельный расход."""

    fact = seed.get("fact")
    if not fact:
        return {"basis": "PROJECT"}, [_issue(
            "warning", "execution_missing",
            "Слой «Факт» не выпущен: параметры взрывных работ в акте — по проекту.", "seed.fact",
        )]
    explosive = sum(float(line.get("quantity") or 0.0) for line in fact.get("consumption") or [] if line.get("kind") == "explosive")
    accepted = payload.get("accepted_volume_m3")
    volume = float(accepted) if accepted else float(seed.get("volume_contour_m3") or 0.0)
    grids = [
        {"code": block.get("code", ""), "spacing_m": block.get("spacing_fact_mean_m"), "burden_m": block.get("burden_fact_mean_m")}
        for block in fact.get("blocks") or []
    ]
    issues = []
    short = [block["code"] for block in fact.get("blocks") or [] if int(block.get("charged") or 0) < int(block.get("holes") or 0)]
    if short:
        issues.append(_issue(
            "warning", "fact_charging_missing",
            f"Факт заряжания записан не у всех скважин (блок {', '.join(short)}): расход ВВ в акте — по записанным.",
            "seed.fact",
        ))
    return {
        "basis": "FACT",
        "blast_date": str(fact.get("blast_date") or ""),
        "explosive_kg": round(explosive, 3),
        "grids": grids,
        "q_kg_m3": round(explosive / volume, 2) if volume > 0 else None,
        "volume_basis": "ACCEPTED" if accepted else "CONTOUR",
    }, issues


def naryad_after_blast(
    seed: Mapping[str, Any], payload: Mapping[str, Any], lines: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, str]]]:
    """Графы наряда после взрыва (решение В9): строки ВМ и разд. 1 по блокам.

    Израсходовано — из факта (ВВ, ПД, НСИ скважинные), ручное главнее;
    выдано — вручную (MagEX — PR 7); возвращено — выдано − израсходовано,
    иначе вручную; у ВВ, изготавливаемых на месте, возврата нет.
    """

    fact = seed.get("fact") or {}
    vv_site = bool(payload.get("vv_site"))
    issued = {str(k): v for k, v in (payload.get("issued") or {}).items() if v is not None}
    consumed = {str(k): v for k, v in (payload.get("consumed") or {}).items() if v is not None}
    returned = {str(k): v for k, v in (payload.get("returned") or {}).items() if v is not None}
    facts = {line["key"]: line for line in fact.get("consumption") or []}
    # Строка факта ищется по ключу «вид:марка:замедление», а не нашлась — по коду
    # материала справочника с тем же видом и замедлением (марка подписана иначе).
    by_code = {
        (line.get("kind"), line.get("material_code"), line.get("delay_ms")): line
        for line in fact.get("consumption") or [] if line.get("material_code")
    }
    for line in lines:
        code = (line.get("kind"), line.get("material_code"), line.get("delay_ms"))
        if line["key"] not in facts and line.get("material_code") and code in by_code:
            found = by_code[code]
            facts.pop(found["key"], None)
            facts[line["key"]] = {**found, "key": line["key"]}
    issues: list[dict[str, str]] = []
    result: list[dict[str, Any]] = []
    known = {line["key"] for line in lines}
    extra = [
        {"key": key, "kind": line.get("kind", ""), "name": line.get("name", ""), "unit": line.get("unit", ""),
         "delay_ms": line.get("delay_ms"), "project_qty": 0.0, "mass_kg": None, "mass_known": True,
         "reserve_qty": 0.0, "reserve_source": "REFERENCE", "issue_qty": 0.0, "unit_mass_kg": 1.0 if line.get("unit") == "кг" else None,
         "issue_kg": 0.0 if line.get("unit") == "кг" else None, "outside_project": True}
        for key, line in facts.items() if key not in known
    ]
    for line in extra:
        issues.append(_issue(
            "warning", "fact_material_not_in_project",
            f"По факту израсходовано «{line['name']}», которого нет в проекте: строка добавлена в наряд.", "seed.fact",
        ))
    for line in [*lines, *extra]:
        key = line["key"]
        unit_mass = line.get("unit_mass_kg")
        fact_line = facts.get(key)
        if key in consumed:
            spent, source = float(consumed[key]), "MANUAL_OVERRIDE"
        elif fact_line is not None:
            spent, source = float(fact_line.get("quantity") or 0.0), "FACT"
        elif fact and line.get("kind") in ("explosive", "primer", "nsi_downhole", "detonator_electronic"):
            # Факт заряжания есть, а этой марки в нём нет — не израсходована.
            spent, source = 0.0, "FACT"
        else:
            spent, source = None, ""
        given = float(issued[key]) if key in issued else None
        explosive = line.get("kind") == "explosive"
        if explosive and vv_site:
            back, back_source = None, "VV_SITE"
            if given is not None and spent is not None and abs(given - spent) > 1e-6:
                issues.append(_issue(
                    "warning", "naryad_vv_site_balance",
                    f"«{line['name']}» изготавливается на месте: израсходовано {spent:g} ≠ выдано {given:g} "
                    "(остаток заряжается в крайние скважины).", f"payload.consumed.{key}",
                ))
        elif key in returned:
            back, back_source = float(returned[key]), "MANUAL_OVERRIDE"
            if given is not None and spent is not None and abs(given - spent - back) > 1e-6:
                issues.append(_issue(
                    "warning", "naryad_balance_mismatch",
                    f"«{line['name']}»: выдано {given:g} ≠ израсходовано {spent:g} + возвращено {back:g}.",
                    f"payload.returned.{key}",
                ))
        elif given is not None and spent is not None:
            back, back_source = round(given - spent, 3), "COMPUTED"
            if back < -1e-6:
                # Отрицательного остатка не бывает: в графу — ничего, расхождение — в слой.
                back, back_source = None, ""
                issues.append(_issue(
                    "warning", "naryad_balance_mismatch",
                    f"«{line['name']}»: израсходовано {spent:g} больше выданного {given:g}.", f"payload.issued.{key}",
                ))
        else:
            back, back_source = None, ""

        def kg(value: float | None) -> float | None:
            return None if value is None or unit_mass is None else round(value * float(unit_mass), 3)

        result.append({
            **line,
            "issued_qty": given, "issued_kg": kg(given),
            "consumed_qty": None if spent is None else round(spent, 3), "consumed_kg": kg(spent), "consumed_source": source,
            "returned_qty": back, "returned_kg": kg(back), "returned_source": back_source,
        })

    blocks: list[dict[str, Any]] = []
    by_code = {str(block.get("code")): block for block in fact.get("blocks") or []}
    for block in seed.get("blocks") or []:
        done = by_code.get(str(block.get("code")))
        if done is None:
            blocks.append({"code": block.get("code", "")})
            continue
        charged_kg = float(done.get("charged_kg") or 0.0)
        misfired_kg = float(done.get("misfired_kg") or 0.0)
        blocks.append({
            "code": block.get("code", ""),
            "charged_holes": int(done.get("charged") or 0),
            "charged_kg": round(charged_kg, 3),
            "fired_holes": int(done.get("charged") or 0) - int(done.get("misfired") or 0),
            "fired_kg": round(charged_kg - misfired_kg, 3),
            "misfired": int(done.get("misfired") or 0),
            "deviation_kg": round(charged_kg - float(block.get("charge_kg") or 0.0), 3),
        })
    return result, blocks, issues


def _person(item: Mapping[str, Any] | None) -> dict[str, str]:
    item = item or {}
    return {"position": str(item.get("position") or ""), "name": str(item.get("name") or "")}


def naryad_lines(
    seed: Mapping[str, Any],
    payload: Mapping[str, Any],
    reserve_defaults: Mapping[str, int] | None = None,
) -> list[dict[str, Any]]:
    """Строки ВМ наряда: по проекту, запас, к выдаче (= по проекту + запас)."""

    reserve = dict(payload.get("reserve") or {})
    defaults = dict(reserve_defaults or {})
    materials = list(seed.get("materials") or [])
    # Запас справочника — на группу (ПД, НСИ, стартеры), а не на каждую строку:
    # он ложится на самую большую строку группы, остальные — 0.
    target: dict[str, str] = {}
    for line in sorted(materials, key=lambda item: -float(item["project_qty"])):
        group = _RESERVE_DEFAULTS.get(line["kind"])
        if group:
            target.setdefault(group, line["key"])
    lines: list[dict[str, Any]] = []
    for line in materials:
        key = line["key"]
        group = _RESERVE_DEFAULTS.get(line["kind"], "")
        if key in reserve and reserve[key] is not None:
            extra, source = float(reserve[key]), "MANUAL_OVERRIDE"
        else:
            extra = float(defaults.get(group, 0) or 0) if group and target.get(group) == key else 0.0
            source = "REFERENCE"
        issue = round(float(line["project_qty"]) + extra, 3)
        # Масса единицы: у ВВ (кг) — 1; у штучных — по массе в расходе проекта (ПД), иначе неизвестна.
        unit_mass = None
        if line.get("unit") == "кг":
            unit_mass = 1.0
        elif (
            line.get("mass_known", True)
            and line.get("mass_kg") is not None
            and float(line["mass_kg"]) > 0
            and float(line["project_qty"] or 0) > 0
        ):
            unit_mass = round(float(line["mass_kg"]) / float(line["project_qty"]), 6)
        lines.append(
            {
                **line,
                "reserve_qty": extra,
                "reserve_source": source,
                "issue_qty": issue,
                "unit_mass_kg": unit_mass,
                "issue_kg": None if unit_mass is None else round(issue * unit_mass, 3),
            }
        )
    return lines


def naryad_totals(seed: Mapping[str, Any], lines: list[Mapping[str, Any]]) -> dict[str, Any]:
    """Итоги наряда для печати (форма 4): блоки разд. 1, ВВ и средства инициирования
    разд. 2, запас по группам — красной строкой под итогом."""

    blocks = list(seed.get("blocks") or [])
    explosives = [line for line in lines if line.get("kind") == "explosive"]
    pieces = [line for line in lines if line.get("kind") != "explosive"]
    reserve = []
    for kind, label, unit in RESERVE_GROUPS:
        group = [line for line in lines if line.get("kind") == kind]
        if group:
            reserve.append({"label": label, "qty": round(sum(float(line["reserve_qty"]) for line in group), 3), "unit": unit})
    return {
        "blocks_holes": sum(int(block.get("holes") or 0) for block in blocks),
        "blocks_charge_kg": round(sum(float(block.get("charge_kg") or 0.0) for block in blocks), 3),
        "explosive_issue_kg": round(sum(float(line.get("issue_kg") or line["issue_qty"]) for line in explosives), 3),
        "initiation_issue_pcs": round(sum(float(line["issue_qty"]) for line in pieces), 3),
        "reserve": reserve,
    }


FACT_DIFF_KEYS = ("depth_fact_m", "subdrill_fact_m", "lspp_fact_m", "spacing_fact_m", "burden_fact_m",
                  "charge_fact_kg", "stemming_fact_m")


def execution_seed_diff(old: Mapping[str, Any], new: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Расхождение переноса слоя «Факт»: по скважинам и графам Ф, а не списками целиком."""

    def rest(seed: Mapping[str, Any]) -> dict[str, Any]:
        return {key: value for key, value in seed.items() if key != "blocks_fact"}

    changes = seed_diff(rest(old), rest(new))
    before_blocks, after_blocks = list(old.get("blocks_fact") or []), list(new.get("blocks_fact") or [])
    if len(before_blocks) != len(after_blocks):
        return changes + [{"path": "blocks_fact", "before": len(before_blocks), "after": len(after_blocks)}]
    for index, (before, after) in enumerate(zip(before_blocks, after_blocks)):
        path = f"blocks_fact[{index}]"
        found = len(changes)
        rows_before = {str(r.get("hole_id")): r for r in (before.get("parameter_table") or {}).get("rows") or []}
        rows_after = {str(r.get("hole_id")): r for r in (after.get("parameter_table") or {}).get("rows") or []}
        for hole_id in sorted(set(rows_before) | set(rows_after), key=_natural_key):
            a, b = rows_before.get(hole_id) or {}, rows_after.get(hole_id) or {}
            changes += [{"path": f"{path}.{hole_id}.{key}", "before": a.get(key), "after": b.get(key)}
                        for key in FACT_DIFF_KEYS if a.get(key) != b.get(key)]
        if before.get("consumption") != after.get("consumption"):
            changes.append({"path": f"{path}.consumption", "before": before.get("consumption"), "after": after.get("consumption")})
        # Остальное (устья Г.1 без смены граф, отпечаток факта) — одной строкой.
        if len(changes) == found and before != after:
            changes.append({"path": path, "before": before.get("execution_sha256"), "after": after.get("execution_sha256")})
    return changes


def _natural_key(hole_id: str) -> tuple:
    return tuple(int(part) if part.isdigit() else part for part in re.split(r"(\d+)", hole_id))


def seed_diff(old: Mapping[str, Any], new: Mapping[str, Any], prefix: str = "") -> list[dict[str, Any]]:
    """Что изменится при повторном переносе: путь, было, станет."""

    changes: list[dict[str, Any]] = []
    for key in sorted(set(old) | set(new)):
        path = f"{prefix}.{key}" if prefix else str(key)
        before, after = old.get(key), new.get(key)
        if isinstance(before, Mapping) and isinstance(after, Mapping):
            changes += seed_diff(before, after, path)
        elif before != after:
            changes.append({"path": path, "before": before, "after": after})
    return changes
