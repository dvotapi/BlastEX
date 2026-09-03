"""Идемпотентное сопоставление JSON-справочников Cost V1 с разделами Cost V2."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from cost.v2.models import ReferenceItem, ReferenceSnapshot


# Cost V1 хранил единицу измерения свободным текстом. Схемы Cost V2 требуют
# ссылку на раздел «Единицы измерения», поэтому текст переводится в код.
#
# Сокращения, у которых есть второе прочтение, сюда не входят: «см» в
# номенклатуре — это сантиметр, а не смена, и молча превратить длину во время
# опаснее, чем оставить единицу незаполненной.
_UNIT_CODES: dict[str, str] = {
    "шт": "PIECE", "шт.": "PIECE", "штука": "PIECE",
    "кг": "KG", "т": "T", "тонна": "T",
    "м": "M", "п.м": "M", "пм": "M", "м2": "M2", "м²": "M2", "м3": "M3", "м³": "M3",
    "ч": "HOUR", "час": "HOUR", "смена": "SHIFT",
    "рейс": "TRIP", "взрыв": "BLAST",
}


def _unit_code(raw: Any, unknown: set[str]) -> str | None:
    """Код единицы измерения; нераспознанный текст копится в `unknown`."""

    text = str(raw or "").strip().lower()
    if not text:
        return None
    code = _UNIT_CODES.get(text)
    if code is None:
        unknown.add(text)
    return code


@dataclass
class ImportReport:
    team_id: str
    source_files: list[str] = field(default_factory=list)
    imported_counts: dict[str, int] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "team_id": self.team_id,
            "source_files": self.source_files,
            "imported_counts": self.imported_counts,
            "warnings": self.warnings,
        }


def build_import_sections(
    project_root: Path,
    team_id: str,
    current: ReferenceSnapshot,
) -> tuple[dict[str, tuple[ReferenceItem, ...]], ImportReport]:
    """Прочитать V1 без изменения файлов и вернуть полный кандидатный снимок."""

    team_dir = project_root / "data" / "teams" / team_id
    report = ImportReport(team_id=team_id)
    sections = {key: tuple(values) for key, values in current.sections.items()}
    references = _read_json(team_dir / "references.json", report)
    settings = _read_json(team_dir / "settings.json", report)
    scenario_id = str(settings.get("active_scenario_id", "drill_blast"))
    snapshot = _read_json(team_dir / "scenarios" / f"{scenario_id}.json", report)

    if not references and not snapshot:
        report.warnings.append(f"В {team_dir} не найдены данные Cost V1.")
        return sections, report

    production_unit_code = f"UNIT_{_code(team_id)}"
    _merge_section(
        sections,
        "production_units",
        [
            ReferenceItem(
                code=production_unit_code,
                name=str(settings.get("team_name") or team_id),
                source="Cost V1 JSON import",
                payload={"legacy_ref": team_id},
            )
        ],
        report,
    )

    sites: list[ReferenceItem] = []
    for row in references.get("work_object_records", []):
        name = str(row.get("name", "Объект"))
        sites.append(
            ReferenceItem(
                code=f"SITE_{_code(name)}",
                name=name,
                source="Cost V1 references.json",
                payload={
                    "production_unit_code": production_unit_code,
                    "mobilization_km": row.get("mobilization_km", 0),
                    "diesel_price_ton_rub": row.get("diesel_price_ton_rub"),
                },
            )
        )
    _merge_section(sections, "sites", sites, report)

    rocks: list[ReferenceItem] = []
    for row in references.get("rock_records", []):
        name = str(row.get("name", "Порода"))
        rocks.append(
            ReferenceItem(
                code=f"ROCK_{_code(name)}",
                name=name,
                source="Cost V1 references.json",
                payload={
                    "density_t_m3": row.get("density_t_m3"),
                    "ucs_mpa": row.get("ucs_mpa"),
                    "fissuring_ff": row.get("fissuring_ff"),
                },
            )
        )
    _merge_section(sections, "rocks", rocks, report)

    # Cost V1 не разделял тип техники и единицу: буровой станок был одной
    # записью. Cost V2 требует тип (нормы, ТОиР, расход) отдельно от основного
    # средства (стоимость, срок), поэтому на каждый станок заводится пара.
    equipment_types: list[ReferenceItem] = []
    equipment: list[ReferenceItem] = []
    default_type_code = "TYPE_V1_LEGACY"
    for row in references.get("drill_rig_records", []):
        name = str(row.get("name", "Буровой станок"))
        type_code = f"TYPE_{_code(name)}"
        equipment_types.append(
            ReferenceItem(
                code=type_code,
                name=name,
                source="Cost V1 references.json",
                payload={"kind": "DRILL_RIG", "fuel_l_per_h": row.get("fuel_l_per_h", 0)},
            )
        )
        equipment.append(
            ReferenceItem(
                code=f"RIG_{_code(name)}",
                name=name,
                source="Cost V1 references.json",
                payload={
                    "equipment_type_code": type_code,
                    "production_unit_code": production_unit_code,
                    "depreciation_per_shift_rub": row.get("depreciation_per_shift_rub", 0),
                    "legacy_ref": row.get("id"),
                },
            )
        )

    legacy_assets = list(references.get("depreciation_asset_records", []))
    if legacy_assets:
        # У амортизируемых ОС V1 вида техники не было вовсе — вешаем их на
        # служебный тип, чтобы ссылка была валидной, и просим разобрать вручную.
        equipment_types.append(
            ReferenceItem(
                code=default_type_code,
                name="Техника из Cost V1 (требует классификации)",
                source="Cost V1 references.json",
                payload={"kind": "LIGHT_VEHICLE"},
            )
        )
        report.warnings.append(
            "Основные средства Cost V1 привязаны к служебному типу техники "
            f"«{default_type_code}»: укажите настоящий вид и нормы смен."
        )
    for row in legacy_assets:
        name = str(row.get("name", "Основное средство"))
        equipment.append(
            ReferenceItem(
                code=f"ASSET_{_code(name)}",
                name=name,
                source="Cost V1 references.json",
                payload={
                    "equipment_type_code": default_type_code,
                    "production_unit_code": production_unit_code,
                    "initial_cost_rub": row.get("initial_cost_rub", 0),
                    "useful_life_months": row.get("useful_life_months", 0),
                    "productive_shifts_per_month": row.get("productive_shifts_per_month", 0),
                    "depreciation_per_shift_rub": row.get("depreciation_per_shift_rub", 0),
                },
            )
        )
    # Дополняем раздел, а не заменяем: у организации уже могут быть типы,
    # заведённые руками, с нормами смен, ТОиР и расходом топлива — импорт
    # сценария V1 не должен их стирать. При совпадении кода побеждает
    # существующая запись как более полная.
    _merge_section(sections, "equipment_types", equipment_types, report)
    _merge_section(sections, "equipment_assets", equipment, report)

    materials: list[ReferenceItem] = []
    material_prices: list[ReferenceItem] = []
    unknown_units: set[str] = set()
    for row in references.get("explosive_records", []):
        code = f"EXP_{_code(str(row.get('key') or row.get('name') or 'VM'))}"
        materials.append(
            ReferenceItem(
                code=code,
                name=str(row.get("name", code)),
                source="Cost V1 references.json",
                payload={
                    "category": "EXPLOSIVE",
                    "density_t_m3": row.get("density_t_m3"),
                    "power_mj_kg": row.get("power_mj_kg"),
                    "legacy_ref": row.get("key"),
                    "chart_label": row.get("chart_label") or None,
                    "material_kind": "ВВ",
                },
            )
        )
    for row in snapshot.get("cost_catalog_records", []):
        code = f"MAT_{_code(str(row.get('id') or row.get('name') or 'ITEM'))}"
        materials.append(
            ReferenceItem(
                code=code,
                name=str(row.get("name", code)),
                source="Cost V1 scenario JSON",
                payload={
                    "category": row.get("category", "OTHER"),
                    "unit": _unit_code(row.get("unit"), unknown_units),
                    "mass_kg": row.get("mass_kg"),
                    "length_m": row.get("length_m"),
                    "legacy_ref": row.get("id"),
                },
            )
        )
        material_prices.append(
            ReferenceItem(
                code=f"PRICE_{code}",
                name=f"Стоимость: {row.get('name', code)}",
                source="Cost V1 scenario JSON",
                payload={
                    "material_code": code,
                    "price_rub": row.get("price", 0),
                    "unit": _unit_code(row.get("unit"), unknown_units),
                },
            )
        )
    if unknown_units:
        report.warnings.append(
            "Единицы измерения Cost V1 не распознаны и оставлены пустыми: "
            + ", ".join(sorted(unknown_units))
            + ". Проставьте их вручную."
        )
    _merge_section(sections, "materials", materials, report)
    _merge_section(sections, "material_prices", material_prices, report)

    positions: list[ReferenceItem] = []
    labor_rates: list[ReferenceItem] = []
    for row in snapshot.get("labor_catalog_records", []):
        code = f"POSITION_{_code(str(row.get('id') or row.get('name') or 'ROLE'))}"
        positions.append(
            ReferenceItem(
                code=code,
                name=str(row.get("name", code)),
                source="Cost V1 scenario JSON",
                payload={"legacy_ref": row.get("id"), "category": "INDIRECT"},
            )
        )
        labor_rates.append(
            ReferenceItem(
                code=f"RATE_{code}",
                name=f"Ставка: {row.get('name', code)}",
                source="Cost V1 scenario JSON",
                payload={
                    "position_code": code,
                    "fixed_monthly_rub": row.get("fixed_salary_monthly", 0),
                    "piece_rate_rub": row.get("piece_rate_per_m3", 0),
                },
            )
        )
    _merge_section(sections, "positions", positions, report)
    _merge_section(sections, "labor_rates", labor_rates, report)

    fixed_items: list[ReferenceItem] = []
    for row in snapshot.get("fixed_cost_records", []):
        code = f"V1_FIXED_{_code(str(row.get('id') or row.get('name') or 'COST'))}"
        fixed_items.append(
            ReferenceItem(
                code=code,
                name=str(row.get("name", code)),
                is_active=bool(row.get("enabled", True)),
                source="Cost V1 scenario JSON",
                comment=str(row.get("note", "")),
                payload={
                    "legacy_section": row.get("section", ""),
                    "amount_rub": row.get("amount_rub", 0),
                    "requires_cost_v2_classification": True,
                    "legacy_ref": row.get("id"),
                },
            )
        )
    if fixed_items:
        _merge_section(sections, "cost_items", fixed_items, report)
        report.warnings.append(
            "Постоянные затраты V1 импортированы как статьи без правил: "
            "перед публикацией задайте слой, поведение и драйвер Cost V2."
        )

    for section, items in sections.items():
        report.imported_counts[section] = len(items)
    return sections, report


def _read_json(path: Path, report: ImportReport) -> dict[str, Any]:
    if not path.exists():
        return {}
    report.source_files.append(str(path))
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        report.warnings.append(f"Не удалось прочитать {path}: {exc}")
        return {}
    return value if isinstance(value, dict) else {}


_TRANSLIT = str.maketrans(
    "абвгдеёжзийклмнопрстуфхцчшщъыьэюя",
    "abvgdeejziyklmnoprstufhccss_y_eua",
)


def _code(value: str) -> str:
    latin = value.lower().translate(_TRANSLIT).upper()
    normalized = re.sub(r"[^A-Z0-9]+", "_", latin).strip("_")
    return (normalized or "ITEM")[:64]


def _dedupe_items(items: list[ReferenceItem]) -> tuple[tuple[ReferenceItem, ...], list[str]]:
    """Развести записи V1, у которых совпал код, и назвать такие пары.

    Совпадение кода у одинаковых записей — обычное дублирование строк V1, о нём
    говорить нечего. Совпадение у разных записей означает, что транслитерация
    названий склеила две сущности: код меняется, а пара попадает в отчёт.
    """

    result: dict[str, ReferenceItem] = {}
    renamed: list[str] = []
    for item in items:
        candidate = item.code
        suffix = 2
        while candidate in result and result[candidate].to_dict() != item.to_dict():
            candidate = f"{item.code}_{suffix}"
            suffix += 1
        if candidate != item.code:
            renamed.append(f"{item.code} → {candidate}")
        result[candidate] = item if candidate == item.code else ReferenceItem(
            code=candidate,
            name=item.name,
            payload=item.payload,
            is_active=item.is_active,
            valid_from=item.valid_from,
            valid_to=item.valid_to,
            source=item.source,
            comment=item.comment,
            revision=item.revision,
        )
    return tuple(result.values()), renamed


def _merge_section(
    sections: dict[str, tuple[ReferenceItem, ...]],
    section: str,
    imported: list[ReferenceItem],
    report: ImportReport | None = None,
) -> None:
    """Дополнить раздел, не стирая записи организации: при совпадении кода
    побеждает существующая запись как более полная."""

    existing = sections.get(section, ())
    existing_codes = {item.code for item in existing}
    deduped, renamed = _dedupe_items(imported)
    if renamed and report is not None:
        report.warnings.append(
            f"В разделе «{section}» разные записи Cost V1 дали один код, "
            f"переименованы: {', '.join(renamed)}. Проверьте, что это разные сущности."
        )
    sections[section] = tuple(existing) + tuple(
        item for item in deduped if item.code not in existing_codes
    )
