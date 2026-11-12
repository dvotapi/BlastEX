"""Значения по умолчанию полей проекта МВ v2 и слоёв (TASK-018, PR 6, §14, В1–В7).

Владелец 12.11.2026: «очень много ручного ввода». Каждое поле формы, которое
можно взять из данных, берётся само; в поле окна — значение, которое пойдёт в
документ, и откуда оно. Порядок источников для поля проекта:

    справочник объекта → проект блока → паспорт на бурение блока →
    прошлый проект МВ объекта → правило (дата взрыва, шаблон №, Общество).

Здесь — только чистые функции: справочник, проекты блоков, паспорта на
бурение и прошлый проект читает сервис (`api/services/mass_blast_v2.py`).
Заданное в проекте главнее: `fill_empty` подставляет значение только в
пустое поле. Чистый `build_document_context_v2` эти значения не знает —
эталоны PDF тестов прежние; заполняет пустые поля сервис перед сборкой
контекста (проверка, предпросмотр, выпуск ревизии).
"""
from __future__ import annotations

import copy
import re
import statistics
from collections import Counter
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Mapping, Sequence

from design.models import BlastDesign, is_explosive_deck_kind

__all__ = [
    "SITE_FIELDS",
    "DefaultsInputs",
    "fill_empty",
    "get_path",
    "layer_defaults",
    "project_defaults",
    "project_number",
    "remember_values",
]

# Источник значения — подпись в окне.
REFERENCE = "REFERENCE"  # справочник объекта
DESIGN = "DESIGN"  # проект блока
DRILL_PASSPORT = "DRILL_PASSPORT"  # паспорт на бурение блока
PREVIOUS = "PREVIOUS"  # прошлый проект МВ объекта (у слоёв — прошлый наряд)
RULE = "RULE"  # правило: дата взрыва, шаблон №, Общество
PROJECT = "PROJECT"  # данные проекта МВ (у слоёв: роли распорядка, подписанты)

# Поле проекта (или слоя «вид:поле») → поле записи «Проект МВ: реквизиты объекта».
# Только поля объекта (В8): то, что не меняется от взрыва к взрыву.
SITE_FIELDS: dict[str, str] = {
    "requisites.tp_basis": "tp_basis",
    "explosives.q_tp_kg_m3": "q_tp_kg_m3",
    "explosives.q_just": "q_just",
    "requisites.customer_approver.position": "customer_approver_position",
    "requisites.customer_approver.name": "customer_approver_name",
    "requisites.customer_approver.authority": "customer_approver_authority",
    "requisites.contractor_approver.position": "contractor_approver_position",
    "requisites.contractor_approver.name": "contractor_approver_name",
    "requisites.contractor_approver.authority": "contractor_approver_authority",
    "schedule.station": "station",
    "schedule.shelter": "shelter",
    "schedule.gather": "gather",
    "schedule.exit_route": "exit_route",
    "schedule.siren": "siren",
    "schedule.transport": "transport",
    "schedule.cleaning": "cleaning",
    "NARYAD:warehouse": "warehouse",
    "NARYAD:permit": "blasting_permit",
    "NARYAD:vehicle": "vehicle",
    "NARYAD:driver": "driver",
    "ACCEPTANCE_ACT:contract_no": "contract_no",
    "ACCEPTANCE_ACT:contract_date": "contract_date",
    "ACCEPTANCE_ACT:appendix_no": "acceptance_appendix_no",
    "ACCEPTANCE_ACT:customer_person": "customer_responsible",
}

# Поля прошлого проекта, которые не зависят от места и дня взрыва (решение В3, В4 и В5).
# Люди — целиком, человеком (`_PEOPLE`); q по ТП и его обоснование — только справочник
# объекта: у них в документе печатается источник (п. 411), чужой проект им не источник.
_FROM_PREVIOUS = (
    "requisites.tp_basis",
    "requisites.customer_name", "requisites.contractor_name",
    "requisites.surveyor_name", "requisites.drilled_by",
    "explosives.initiation", "explosives.scheme", "explosives.charge_design",
    "explosives.stemming_material", "explosives.starter_product",
    "explosives.bit_mm", "explosives.reaming_k",
    "schedule.charging_shift_from", "schedule.charging_shift_to",
    "schedule.charging_order", "schedule.network_order",
    "schedule.station", "schedule.shelter", "schedule.gather", "schedule.exit_route",
    "schedule.siren", "schedule.measures", "schedule.transport", "schedule.cleaning",
)

# Люди проекта: значение по умолчанию — один человек из одного источника, а не
# должность из одного места и фамилия из другого. Порядок: справочник объекта
# (подписанты), прошлый проект объекта, паспорт на бурение блока (В4).
_PEOPLE = {
    "requisites.customer_approver": ("customer_approver", "agreed_by"),
    "requisites.contractor_approver": ("contractor_approver", "approved_by"),
    "requisites.made_by": ("", "compiled_by"),
    "requisites.checked_by": ("", ""),
}
# Поля, которые контекст v2 и так берёт из справочника объекта, когда поле
# проекта пустое (`mass_blast_context._signer`, `_q_tp`, `_requisites`): их
# значение из справочника в проект не подставляется — у q по ТП источник
# печатается в техрасчёте («по справочнику объекта», документ-источник).
CONTEXT_RESOLVED = frozenset({
    "requisites.tp_basis", "explosives.q_tp_kg_m3", "explosives.q_just",
    *(f"{prefix}.{part}" for prefix in ("requisites.customer_approver", "requisites.contractor_approver")
      for part in ("position", "name", "authority", "is_head")),
})

_SYSTEM_TEXT = {
    "nonel": "Неэлектрическая система инициирования (НСИ)",
    "detcord": "Детонирующий шнур (ДШ)",
    "electronic": "Электронная система инициирования",
}
_SCHEME_TEXT = {
    "row": "Порядная короткозамедленная",
    "echelon": "Поэшелонная короткозамедленная",
    "diagonal_v": "Диагональная (V-образная) короткозамедленная",
    "trapezoid": "Трапециевидная короткозамедленная",
    "trunk_chains": "Поочерёдная короткозамедленная: магистраль + цепочки",
}
_PATH = re.compile(r"([a-z_]+)(?:\[(\d+)\])?")
_ISO = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")
_RU = re.compile(r"^(\d{2})\.(\d{2})\.(\d{4})$")


@dataclass(frozen=True)
class DefaultsInputs:
    """Всё, что сервис прочитал для значений по умолчанию проекта."""

    designs: Sequence[BlastDesign] = ()
    site: Mapping[str, Any] = field(default_factory=dict)  # запись «Проект МВ: реквизиты объекта»
    customer_name: str = ""  # заказчик объекта (контрагент справочника)
    drill_passports: Sequence[Mapping[str, Any] | None] = ()  # payload паспорта на бурение по блоку
    previous: Mapping[str, Any] | None = None  # прошлый проект МВ v2 объекта
    organization: str = ""  # Общество — подрядчик
    created_on: str = ""  # дата создания проекта (ISO)


def _empty(value: Any) -> bool:
    return value is None or (isinstance(value, str) and not value.strip()) or value == [] or value == {}


def _steps(path: str) -> list[tuple[str, int | None]]:
    return [(name, int(index) if index else None) for name, index in _PATH.findall(path)]


def get_path(data: Mapping[str, Any] | None, path: str) -> Any:
    current: Any = data or {}
    for name, index in _steps(path):
        if not isinstance(current, Mapping):
            return None
        current = current.get(name)
        if index is not None:
            if not isinstance(current, list) or index >= len(current):
                return None
            current = current[index]
    return current


def _set_path(data: dict[str, Any], path: str, value: Any) -> None:
    steps = _steps(path)
    current: Any = data
    for position, (name, index) in enumerate(steps):
        last = position == len(steps) - 1
        if index is None:
            if last:
                current[name] = value
                return
            if not isinstance(current.get(name), dict):
                current[name] = {}
            current = current[name]
        else:
            items = current.get(name)
            if not isinstance(items, list) or index >= len(items):
                return
            if last:
                items[index] = value
                return
            if not isinstance(items[index], dict):
                items[index] = {}
            current = items[index]


def fill_empty(payload: Mapping[str, Any], defaults: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    """Копия payload: пустые поля — значениями по умолчанию; заданное не меняется.

    Значения справочника по `CONTEXT_RESOLVED` не подставляются: контекст сам
    берёт их из справочника и помнит источник."""

    result = copy.deepcopy(dict(payload))
    for path, entry in defaults.items():
        if ":" in path or _empty(entry.get("value")):
            continue
        if entry.get("source") == REFERENCE and path in CONTEXT_RESOLVED:
            continue
        if _empty(get_path(result, path)):
            _set_path(result, path, entry["value"])
    return result


def _put(target: dict[str, dict[str, Any]], path: str, value: Any, source: str) -> None:
    """Первое непустое значение по пути — по порядку источников."""

    if path not in target and not _empty(value):
        target[path] = {"value": value, "source": source}


def iso_date(value: Any) -> str:
    text = str(value or "").strip()
    match = _RU.match(text)
    return f"{match.group(3)}-{match.group(2)}-{match.group(1)}" if match else text


def ru_date(value: Any) -> str:
    text = str(value or "").strip()
    match = _ISO.match(text)
    return f"{match.group(3)}.{match.group(2)}.{match.group(1)}" if match else text


def project_number(codes: Sequence[str], blast_date: str) -> str:
    """№ проекта по шаблону «{блок}-{гг}/МВ» (В2); несколько блоков — через «+»."""

    blocks = "+".join(code.strip() for code in codes if code and code.strip())
    year = blast_date[2:4] if _ISO.match(blast_date or "") else ""
    if not blocks or not year:
        return ""
    return f"{blocks}-{year}/МВ"[:40]


# --- Проект блока --------------------------------------------------------------


def _enabled_holes(design: BlastDesign) -> list[Any]:
    return [hole for hole in design.holes if getattr(hole, "enabled", True)]


def rock_text(design: BlastDesign) -> str:
    if design.rock_name.strip():
        return design.rock_name.strip()
    names = list(dict.fromkeys(domain.name.strip() for domain in design.domains if getattr(domain, "name", "").strip()))
    return ", ".join(names)


def hydro_text(design: BlastDesign) -> str:
    """«Обводнённых скважин N из M» или «Скважины сухие» — по интервалам воды проекта."""

    holes = _enabled_holes(design)
    # Нет ни интервалов воды, ни уровня подземных вод — обводнённость не проверяли:
    # «сухие» в документ не пишем.
    if not holes or (design.water_table_z_m is None and not any(getattr(hole, "water_intervals", None) for hole in holes)):
        return ""
    wet = sum(
        1 for hole in holes
        if any(str(getattr(interval, "condition", "")) in ("wet", "flowing") for interval in getattr(hole, "water_intervals", []) or [])
    )
    return f"Обводнённых скважин {wet} из {len(holes)}" if wet else "Скважины сухие"


def initiation_text(design: BlastDesign) -> str:
    network = design.network
    if network is None or not (network.surface_connectors or network.connectors or network.detonating_cords
                               or network.electronic_channels or network.starter_items):
        return ""
    return _SYSTEM_TEXT.get(str(network.system or ""), "")


def scheme_text(design: BlastDesign) -> str:
    network = design.network
    scheme = str(((network.timing_params or {}) if network is not None else {}).get("scheme") or "")
    return _SCHEME_TEXT.get(scheme, "")


def charge_design_text(design: BlastDesign) -> str:
    """Сплошной или рассредоточенный заряд и число боевиков — по декам проекта."""

    parts: list[int] = []
    primers: list[int] = []
    for load in design.loads:
        decks = [deck for deck in load.decks if is_explosive_deck_kind(deck.kind)]
        if not decks:
            continue
        parts.append(len(decks))
        primers.append(len(load.primer_items))
    if not parts:
        return ""
    most = max(parts)
    text = "Сплошная колонка ВВ" if most == 1 else f"Рассредоточенный заряд (до {most} частей)"
    if primers:
        usual = Counter(primers).most_common(1)[0][0]
        if usual:
            text += f", {usual} боевик{'а' if 2 <= usual <= 4 else 'ов' if usual >= 5 else ''} в скважине"
    return text


def stemming_text(design: BlastDesign) -> str:
    products = Counter(
        str(deck.product).strip()
        for load in design.loads for deck in load.decks
        if deck.kind == "stemming" and str(deck.product or "").strip()
    )
    return products.most_common(1)[0][0] if products else ""


def reaming_k(design: BlastDesign, bit_mm: float | None) -> float | None:
    """k разбуривания = диаметр скважины (медиана) / диаметр долота."""

    diameters = [float(hole.diameter_mm) for hole in _enabled_holes(design) if getattr(hole, "diameter_mm", 0)]
    if not bit_mm or not diameters:
        return None
    k = round(statistics.median(diameters) / float(bit_mm), 2)
    return k if 0 < k <= 2 else None


def _joined(values: Sequence[str]) -> str:
    return "; ".join(dict.fromkeys(value for value in values if value))


def _number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def project_defaults(payload: Mapping[str, Any], inputs: DefaultsInputs) -> dict[str, dict[str, Any]]:
    """Значения по умолчанию полей проекта: путь payload → {value, source}."""

    result: dict[str, dict[str, Any]] = {}
    site = dict(inputs.site or {})
    previous = inputs.previous or {}
    designs = list(inputs.designs)
    passports = [dict(item or {}) for item in inputs.drill_passports]
    blast_date = str(payload.get("blast_date") or "")

    # 0. Люди — человеком из одного источника.
    for prefix, (site_key, passport_key) in _PEOPLE.items():
        candidates: list[tuple[Mapping[str, Any], str]] = []
        if site_key:
            candidates.append(({
                "position": site.get(f"{site_key}_position"), "name": site.get(f"{site_key}_name"),
                "authority": site.get(f"{site_key}_authority"), "is_head": site.get(f"{site_key}_is_head"),
            }, REFERENCE))
        candidates.append((get_path(previous, prefix) or {}, PREVIOUS))
        if passport_key:
            candidates += [(passport.get(passport_key) or {}, DRILL_PASSPORT) for passport in passports]
        for person, source in candidates:
            if isinstance(person, Mapping) and not _empty(person.get("name")):
                for part in ("position", "name", "authority"):
                    _put(result, f"{prefix}.{part}", person.get(part), source)
                if site_key and isinstance(person.get("is_head"), bool):
                    _put(result, f"{prefix}.is_head", person["is_head"], source)
                break

    # 1. Справочник объекта.
    for path, key in SITE_FIELDS.items():
        if ":" not in path and not any(path.startswith(prefix + ".") for prefix in _PEOPLE):
            _put(result, path, site.get(key), REFERENCE)
    _put(result, "requisites.customer_name", inputs.customer_name, REFERENCE)

    # 2. Проект блока.
    if designs:
        _put(result, "explosives.initiation", _joined([initiation_text(d) for d in designs]), DESIGN)
        _put(result, "explosives.scheme", _joined([scheme_text(d) for d in designs]), DESIGN)
        _put(result, "explosives.charge_design", _joined([charge_design_text(d) for d in designs]), DESIGN)
        _put(result, "explosives.stemming_material", _joined([stemming_text(d) for d in designs]), DESIGN)
    for index, design in enumerate(designs):
        _put(result, f"blocks[{index}].details.rock_text", rock_text(design), DESIGN)
        _put(result, f"blocks[{index}].details.hydro_text", hydro_text(design), DESIGN)

    # 3. Паспорт на бурение блока: долото, люди.
    bits = [_number(passport.get("bit_diameter_mm")) for passport in passports]
    bit = next((value for value in bits if value), None)
    if bit:
        _put(result, "explosives.bit_mm", bit, DRILL_PASSPORT)
        k = next((reaming_k(design, bits[i] or bit) for i, design in enumerate(designs) if reaming_k(design, bits[i] or bit)), None)
        _put(result, "explosives.reaming_k", k, DRILL_PASSPORT)

    # 4. Прошлый проект МВ объекта.
    for path in _FROM_PREVIOUS:
        _put(result, path, get_path(previous, path), PREVIOUS)
    first_block = (previous.get("blocks") or [{}])[0] if previous else {}
    for index, _ in enumerate(designs):
        _put(result, f"blocks[{index}].details.purpose", get_path(first_block, "details.purpose"), PREVIOUS)

    # 5. Правила.
    codes = [str(block.get("code") or "") for block in payload.get("blocks") or []]
    _put(result, "requisites.project_no", project_number(codes, blast_date), RULE)
    _put(result, "requisites.project_date", inputs.created_on, RULE)
    _put(result, "requisites.contractor_name", inputs.organization, RULE)
    _put(result, "schedule.charging_from", blast_date, RULE)
    _put(result, "schedule.briefing_date", blast_date, RULE)
    return result


# --- Слои дня взрыва --------------------------------------------------------------


def _person_line(item: Any) -> str:
    if not isinstance(item, Mapping):
        return ""
    return " ".join(str(item.get(key) or "").strip() for key in ("position", "name")).strip()


def layer_defaults(
    kind: str,
    seed: Mapping[str, Any],
    payload: Mapping[str, Any],
    *,
    site: Mapping[str, Any] | None = None,
    previous_naryad: Mapping[str, Any] | None = None,
    view: Mapping[str, Any] | None = None,
    created_on: str = "",
) -> dict[str, dict[str, Any]]:
    """Значения по умолчанию ручного ввода слоя: поле payload → {value, source} (В3, В7)."""

    result: dict[str, dict[str, Any]] = {}
    site = dict(site or {})
    view = view or {}
    project = seed.get("project") or {}
    blast_date = str(project.get("blast_date") or "")
    if kind == "NARYAD":
        for name in ("warehouse", "permit", "vehicle", "driver"):
            _put(result, name, site.get(SITE_FIELDS[f"NARYAD:{name}"]), REFERENCE)
        for name in ("warehouse", "permit", "vehicle", "driver", "blaster_index"):
            _put(result, name, (previous_naryad or {}).get(name), PREVIOUS)
        _put(result, "issue_date", blast_date, RULE)
    elif kind == "NOTIFICATION":
        _put(result, "out_date", created_on, RULE)
        _put(result, "signer", (seed.get("addressee") or {}).get("signer"), REFERENCE)
    elif kind == "READINESS_ACT":
        _put(result, "act_date", blast_date, RULE)
        _put(result, "handed_by", _person_line(seed.get("customer_approver")), PROJECT)
        _put(result, "accepted_by", _person_line(seed.get("blast_manager")), PROJECT)
    elif kind == "TALON":
        # Допуск после полуночи — дата допуска (`talon_view`), иначе дата взрыва по факту или проектная.
        _put(result, "issued_date", view.get("admittance_date") or payload.get("fired_date") or blast_date, RULE)
        _put(result, "issued_time", view.get("admittance_not_before"), RULE)
        _put(result, "issued_by", _person_line(seed.get("blast_manager")), PROJECT)
        _put(result, "received_by", _person_line(seed.get("talon_receiver")), PROJECT)
    elif kind == "ACCEPTANCE_ACT":
        fact = seed.get("fact") or {}
        _put(result, "act_date", fact.get("blast_date") or blast_date, RULE)
        contract = seed.get("contract") or {}
        _put(result, "contract_no", contract.get("contract_no"), REFERENCE)
        _put(result, "contract_date", iso_date(contract.get("contract_date")), REFERENCE)
        _put(result, "appendix_no", contract.get("acceptance_appendix_no"), REFERENCE)
        _put(result, "customer_person", contract.get("customer_responsible"), REFERENCE)
    return result


def fill_layer_empty(payload: Mapping[str, Any], defaults: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    """Ручной ввод слоя для выпуска и предпросмотра: пустые поля — значениями по умолчанию."""

    result = dict(payload)
    for name, entry in defaults.items():
        if _empty(result.get(name)) and not _empty(entry.get("value")):
            result[name] = entry["value"]
    return result


def remember_values(
    project: Mapping[str, Any],
    paths: Sequence[str],
    *,
    layer_kind: str = "",
    layer_payload: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Поля записи справочника объекта из сохранённого проекта или слоя (В8).

    Неизвестный путь или пустое значение — ошибка: в справочник пишется
    только поле объекта и только заданное значение.
    """

    values: dict[str, Any] = {}
    for path in paths:
        key = f"{layer_kind}:{path}" if layer_kind else path
        if key not in SITE_FIELDS:
            raise ValueError(f"Поле «{path}» не относится к реквизитам объекта: в справочник его не записать.")
        value = (layer_payload or {}).get(path) if layer_kind else get_path(project, path)
        if _empty(value):
            raise ValueError(f"Поле «{path}» пустое: записывать в справочник нечего.")
        field_name = SITE_FIELDS[key]
        values[field_name] = ru_date(value) if field_name == "contract_date" else value
    return values


def created_on(value: Any) -> str:
    """Дата создания из момента ISO с часовым поясом («2026-11-12T09:29:40+00:00»)."""

    text = str(value or "")
    return text[:10] if _ISO.match(text[:10]) else date.today().isoformat()
