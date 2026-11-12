"""Содержимое выписки наряд-путёвки для MagEX (`NaryadPayloadV1`, контракт разд. 2; TASK-018 PR 7, §4).

Чистые функции: на вход — слой «Наряд-путёвка» (перенесённое `seed`, введённое
`payload` с умолчаниями, строки ВМ `view.lines`) и то, что знает сервис
(организация MagEX, сопоставление ВМ и номенклатура MagEX, взрывник,
начальник участка); на выход — содержимое и замечания с `path` к полю окна.

- `lines` — «Выписано» = по проекту + запас в единице учёта позиции MagEX,
  строкой с тремя знаками; несколько строк наряда одной позиции складываются;
  патронированные ВВ (кг → шт) — вверх до целого патрона (решение В6).
- Необязательное, которого нет, — опущено (запись одна у всех переподписаний).
- `site.id` и `blaster.ref` без сотрудника SafetyMAIN — UUID v5, постоянные.
"""
from __future__ import annotations

import math
import re
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Mapping, Sequence

__all__ = [
    "MAX_BLOCKS",
    "MAX_LINES",
    "MagexContext",
    "blaster_ref",
    "build_naryad_payload",
    "magex_lines",
    "qty_text",
    "site_uuid",
]

MAX_LINES = 40
MAX_BLOCKS = 50
MAX_DELIVERY = 10
_TEXT = 200
_PROJECT_TEXT = 100
_NUM_TEXT = 50
_EPS = 1e-6
# Единица строки наряда BlastEX → единица учёта MagEX без пересчёта.
_SAME_UNIT = {("кг", "kg"), ("шт", "pcs"), ("м", "m")}


def _uuid5(name: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, name))


def site_uuid(organization_id: str, site_code: str) -> str:
    """Постоянный UUID объекта BlastEX для `site.id` (нового поля в справочнике нет)."""

    return _uuid5(f"blastex:site:{organization_id}:{site_code}")


def blaster_ref(organization_id: str, index: str, employee_ref: str | None = None) -> str:
    """`blaster.ref`: сотрудник SafetyMAIN, иначе постоянный UUID по организации и индексу (решение В2)."""

    if employee_ref:
        return str(uuid.UUID(str(employee_ref)))
    return _uuid5(f"blastex:blaster:{organization_id}:{str(index).strip().casefold()}")


def qty_text(value: Decimal | float) -> str:
    """Количество по контракту: ровно три знака после точки, без ведущих нулей."""

    amount = Decimal(str(value)).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)
    text = f"{amount:.3f}"
    return "0.000" if amount == 0 else text


def _issue(level: str, code: str, message: str, path: str) -> dict[str, str]:
    return {"level": level, "code": code, "message": message, "path": path}


def _text(value: Any, limit: int = _TEXT) -> str:
    # Пробелы по краям сервис обрезает до хэша — пишем без них; NUL Postgres не хранит.
    return str(value or "").replace("\x00", "").strip()[:limit].strip()


@dataclass(frozen=True)
class MagexContext:
    """Что знает сервис, а не слой: организация MagEX, объект, ВМ, люди, склад."""

    organization: str
    organization_id: str
    site_code: str
    site_name: str
    warehouse_id: str
    # Код материала BlastEX → позиция MagEX (справочник ВМ, `magex_material_id`).
    materials: Mapping[str, str] = field(default_factory=dict)
    # Позиция MagEX → номенклатура (`GET /materials`): единица учёта, масса единицы, вид.
    catalog: Mapping[str, Mapping[str, Any]] = field(default_factory=dict)
    blaster: Mapping[str, Any] | None = None
    approver: Mapping[str, Any] | None = None
    admissions_confirmed: bool = False


def magex_lines(
    lines: Sequence[Mapping[str, Any]],
    materials: Mapping[str, str],
    catalog: Mapping[str, Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    """Строки выписки: позиция MagEX и «Выписано» в её единице учёта; несопоставленное — ошибки."""

    merged: dict[str, dict[str, Any]] = {}
    issues: list[dict[str, str]] = []
    unmapped: list[str] = []
    for line in lines:
        issue_qty = float(line.get("issue_qty") or 0.0)
        if issue_qty <= _EPS:
            continue
        key = str(line.get("key") or "")
        name = str(line.get("name") or "")
        material_id = materials.get(str(line.get("material_code") or ""))
        if not material_id:
            unmapped.append(name)
            continue
        item = catalog.get(material_id)
        if item is None:
            issues.append(_issue(
                "error", "magex_material_unknown",
                f"Позиции MagEX для «{name}» нет в номенклатуре MagEX (или она неактивна): сопоставьте заново.",
                f"lines.{key}",
            ))
            continue
        unit = str(line.get("unit") or "")
        accounting = str(item.get("accounting_unit") or "")
        unit_mass = item.get("unit_mass_kg")
        amount: Decimal
        if (unit, accounting) in _SAME_UNIT:
            amount = Decimal(str(issue_qty))
        elif unit == "шт" and accounting == "kg" and line.get("issue_kg") is not None:
            amount = Decimal(str(line["issue_kg"]))
        elif unit == "кг" and accounting == "pcs" and unit_mass and float(unit_mass) > 0:
            pieces = issue_qty / float(unit_mass)
            whole = math.ceil(pieces - _EPS)
            if abs(pieces - whole) > _EPS:
                issues.append(_issue(
                    "warning", "magex_qty_rounded",
                    f"«{name}»: {issue_qty:g} кг — {whole} шт по {float(unit_mass):g} кг (вверх до целого).",
                    f"lines.{key}",
                ))
            amount = Decimal(whole)
        else:
            issues.append(_issue(
                "error", "magex_unit_mismatch",
                f"«{name}»: в наряде — {unit}, в MagEX — {accounting or 'не задана'}; пересчёт невозможен.",
                f"lines.{key}",
            ))
            continue
        if accounting == "pcs" and amount != amount.to_integral_value():
            issues.append(_issue(
                "error", "magex_qty_not_integer",
                f"«{name}»: штучная позиция MagEX, а к выдаче {amount.normalize():f} — нужно целое (поправьте запас).",
                f"payload.reserve.{key}",
            ))
            continue
        row = merged.setdefault(material_id, {"material_id": material_id, "qty": Decimal(0), "keys": [], "unit": accounting})
        row["qty"] += amount
        row["keys"].append(key)
    if unmapped:
        issues.append(_issue(
            "error", "magex_material_unmapped",
            "Не сопоставлены с позициями MagEX: " + ", ".join(sorted(set(unmapped)))
            + " — укажите «Позиция MagEX» в справочнике материалов.",
            "lines",
        ))
    if len(merged) > MAX_LINES:
        issues.append(_issue("error", "magex_too_many_lines", f"Позиций больше {MAX_LINES}: разделите наряд-путёвку.", "lines"))
    if not merged and not unmapped and not any(item["level"] == "error" for item in issues):
        issues.append(_issue("error", "magex_no_lines", "В наряде нет ВМ к выдаче.", "lines"))
    return list(merged.values()), issues


def _iso(value: Any) -> str:
    text = str(value or "").strip()
    try:
        return date.fromisoformat(text[:10]).isoformat() if text else ""
    except ValueError:
        return ""


def _delivery(text: str) -> list[dict[str, str]]:
    names = [_text(part) for part in re.split(r"[;,\n]", str(text or ""))]
    return [{"name": name} for name in names if name][:MAX_DELIVERY]


def _project_text(seed: Mapping[str, Any]) -> str:
    project = seed.get("project") or {}
    codes = [str(block.get("code") or "").strip() for block in seed.get("blocks") or []]
    codes = [code for code in codes if code]
    number = str(project.get("project_no") or "").strip()
    head = f"Проект МВ № {number}" if number else "Проект МВ"
    text = f"{head} блок № {', '.join(codes)}" if codes else head
    if len(text) > _PROJECT_TEXT:
        text = f"{head}, блоков: {len(codes)}"
    return text[:_PROJECT_TEXT].strip()


def _blocks(seed: Mapping[str, Any], short_names: bool) -> list[dict[str, Any]]:
    blocks = []
    for block in (seed.get("blocks") or [])[:MAX_BLOCKS]:
        code = _text(block.get("code"))
        if not code:
            continue
        item: dict[str, Any] = {"code": code, "name": code if short_names else _text(f"Блок {code}")}
        horizon = _text(block.get("horizon"))
        if horizon:
            item["horizon"] = horizon
        holes = block.get("holes")
        if holes is not None:
            item["holes"] = int(holes)
        if block.get("charge_kg") is not None:
            item["charge_kg"] = qty_text(block["charge_kg"])
        blocks.append(item)
    return blocks


def build_naryad_payload(
    layer_id: str,
    seed: Mapping[str, Any],
    payload: Mapping[str, Any],
    lines: Sequence[Mapping[str, Any]],
    ctx: MagexContext,
    *,
    ver: int,
    iat: int,
    approved_at: datetime,
    short_block_names: bool = False,
) -> tuple[dict[str, Any], list[dict[str, str]]]:
    """Содержимое `NaryadPayloadV1` и замечания (ошибка — разрешить нельзя)."""

    issues: list[dict[str, str]] = []
    number = _text(payload.get("number"), _NUM_TEXT)
    if not number:
        issues.append(_issue("error", "magex_number_missing", "Укажите № наряда-путёвки.", "payload.number"))
    issued_on = _iso(payload.get("issue_date"))
    if not issued_on:
        issues.append(_issue("error", "magex_issue_date_missing", "Укажите дату выписки.", "payload.issue_date"))
    blast_on = _iso((seed.get("project") or {}).get("blast_date"))
    if issued_on and blast_on and blast_on < issued_on:
        issues.append(_issue(
            "error", "magex_blast_before_issue", "Дата взрыва раньше даты выписки наряда-путёвки.", "payload.issue_date",
        ))
    try:
        warehouse = str(uuid.UUID(str(ctx.warehouse_id))) if ctx.warehouse_id else ""
    except ValueError:
        warehouse = ""
    if not warehouse:
        issues.append(_issue(
            "error", "magex_warehouse_missing",
            "Не выбран склад MagEX: укажите «Склад MagEX» в реквизитах объекта или выберите склад в наряде.",
            "payload.magex_warehouse_id",
        ))
    blaster = dict(ctx.blaster or {})
    if not blaster.get("ref") or not _text(blaster.get("name")) or not _text(blaster.get("index")):
        issues.append(_issue(
            "error", "magex_blaster_missing",
            "Выберите взрывника из справочника «Взрывники» (ФИО и индивидуальный индекс).", "payload.blaster_code",
        ))
    approver = dict(ctx.approver or {})
    if not _text(approver.get("name")):
        issues.append(_issue(
            "error", "magex_approver_missing",
            "В персонале проекта не указан начальник участка — он разрешает перевозку ВМ и взрывные работы.",
            "seed.people.site_manager",
        ))
    if approved_at.tzinfo is None:
        raise ValueError("Момент разрешения — только с часовым поясом")
    if not ctx.admissions_confirmed:
        issues.append(_issue(
            "error", "magex_admissions_unconfirmed",
            "Подтвердите, что допуски взрывника, водителя и спецавтомобиля проверены.", "payload.admissions_confirmed",
        ))
    magex, line_issues = magex_lines(lines, ctx.materials, ctx.catalog)
    issues += line_issues

    content: dict[str, Any] = {
        "iss": "blastex",
        "sub": str(uuid.UUID(str(layer_id))),
        "ver": int(ver),
        "iat": int(iat),
        "org": ctx.organization,
        "wh": warehouse,
        "num": number,
        "on": issued_on,
        "site": {"id": site_uuid(ctx.organization_id, ctx.site_code), "name": _text(ctx.site_name) or _text(ctx.site_code)},
        "blaster": {"ref": str(blaster.get("ref") or ""), "name": _text(blaster.get("name")), "index": _text(blaster.get("index"))},
        "approved": {"name": _text(approver.get("name")), "at": approved_at.isoformat(timespec="seconds")},
        "blocks": _blocks(seed, short_block_names),
        "lines": [{"material_id": row["material_id"], "qty": qty_text(row["qty"])} for row in magex],
    }
    if blast_on:
        content["blast_on"] = blast_on
    project = _project_text(seed)
    if project:
        content["project"] = project
    position = _text(approver.get("position"))
    if position:
        content["approved"]["position"] = position
    permit_number = _text(payload.get("permit_number"))
    permit_date = _iso(payload.get("permit_date"))
    if permit_number and permit_date:
        content["permit_vr"] = {"number": permit_number, "date": permit_date}
    else:
        issues.append(_issue(
            "warning", "magex_permit_missing",
            "Разрешение на ВР (№ и дата) не указано: MagEX нужно оно для отчёта 2-ВМ.", "payload.permit_number",
        ))
    vehicle = {
        key: value
        for key, value in (
            ("model", _text(payload.get("vehicle_model")) or _text(payload.get("vehicle"))),
            ("plate", _text(payload.get("vehicle_plate"))),
        )
        if value
    }
    if vehicle:
        content["vehicle"] = vehicle
    driver = _text(payload.get("driver"))
    if driver:
        content["driver"] = {"name": driver}
    delivery = _delivery(str(payload.get("delivery") or ""))
    if delivery:
        content["delivery"] = delivery
    return content, issues
