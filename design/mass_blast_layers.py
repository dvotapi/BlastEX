"""Слои проекта массового взрыва: документы дня взрыва (TASK-018, PR 2, §2.1).

Проект (титул, техрасчёт, таблица, распорядок, графика) — одна ревизия
проекта. Документы 6–10 — **слои**: у каждого свои данные, ревизии и
подписи; слой ссылается на ревизию проекта и её не меняет.

- Открытие: наряд-путёвка, уведомление, акт готовности — после `approved`;
  талон-допуск и акт приёмки — после `executed`. Акт готовности не
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
- «Устарел» — ревизия проекта слоя не текущая. `seed_diff` показывает, что
  изменится при повторном переносе; перенос — только с подтверждения.

Чистые функции без БД: хранение — `design/mass_blast_repository.py`.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Mapping

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

LAYER_KINDS = ("NARYAD", "NOTIFICATION", "READINESS_ACT", "TALON", "ACCEPTANCE_ACT")
LAYER_LABELS = {
    "NARYAD": "Наряд-путёвка",
    "NOTIFICATION": "Уведомление о массовом взрыве",
    "READINESS_ACT": "Акт готовности блока к заряжанию",
    "TALON": "Талон-допуск",
    "ACCEPTANCE_ACT": "Акт приёмки выполненных работ",
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
}
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


def layer_seed(kind: str, context: Mapping[str, Any], *, notification: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Данные проекта, которые переносятся в слой (без введённого вручную)."""

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
    return seed


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
