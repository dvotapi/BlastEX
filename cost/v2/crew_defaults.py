"""Должности БВР из импорта Cost V1 как прямой персонал блока и бригада по умолчанию.

Импорт переносит должности косвенными (`category=INDIRECT`) и без операции:
классификация по слою — работа человека, а не переноса. Здесь она сделана
для бригады БВР: кто на блоке, к какой операции пакета относится и по какому
драйверу получает сдельную часть. Должности вне таблицы не трогаются — они
остаются постоянными затратами юнита.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from decimal import Decimal
from typing import Any, Mapping, Sequence

from cost.v2.models import ReferenceItem, ReferenceSnapshot
from cost.v2.references import normalize_sections

DEFAULT_PACKAGE = "DRILL_AND_BLAST"
DEFAULT_CREW_CODE = "CREW_DRILL_AND_BLAST"

# Норма взрывов в месяц: столько раз бригада выезжает на блок, столько смен
# на один блок приходится каждому — ADR-001 считает взрывника при десяти
# взрывах в месяц.
DEFAULT_BLASTS_PER_MONTH = Decimal("10")


@dataclass(frozen=True)
class DirectPosition:
    code: str
    operation_code: str
    piece_driver: str
    norm_shifts_per_month: Decimal = Decimal("21")
    # Норма выездов в месяц: взрывник и горнорабочий работают по числу взрывов,
    # водителям она нужна как запасной путь — пока техника не выбрана или в
    # блоке нет рейсов (нет патронов — нет доставки), смены из неё не выводятся.
    # Бурильщикам не задаётся: их смены — только из станка.
    norm_operations_per_month: Decimal | None = DEFAULT_BLASTS_PER_MONTH
    # Численность по умолчанию в бригаде полного комплекса; ноль — в бригаду
    # блока должность не входит (бурильщиков считает экипаж станка).
    default_headcount: Decimal = Decimal("0")


DIRECT_POSITIONS: tuple[DirectPosition, ...] = (
    DirectPosition("POSITION_LABOR_MASTER", "BLAST_EXECUTION", "rock_volume_m3", default_headcount=Decimal("1")),
    DirectPosition("POSITION_LABOR_BLASTERS", "BLAST_EXECUTION", "rock_volume_m3", default_headcount=Decimal("2")),
    DirectPosition("POSITION_LABOR_DRIVER_SZM", "BULK_CHARGING_SZM", "explosive_kg", default_headcount=Decimal("1")),
    DirectPosition("POSITION_LABOR_DRIVER_DEL", "VM_DELIVERY_SITE", "rock_volume_m3", default_headcount=Decimal("1")),
    DirectPosition("POSITION_LABOR_MINER", "MANUAL_CHARGING", "rock_volume_m3", default_headcount=Decimal("2")),
    DirectPosition(
        "POSITION_LABOR_DRILLER", "PRODUCTION_DRILLING", "drilling_m",
        norm_shifts_per_month=Decimal("15"), norm_operations_per_month=None,
    ),
    DirectPosition(
        "POSITION_LABOR_ASSISTANT", "PRODUCTION_DRILLING", "drilling_m",
        norm_shifts_per_month=Decimal("15"), norm_operations_per_month=None,
    ),
)


@dataclass
class ReclassifyReport:
    reclassified: list[str]
    already_direct: list[str]
    missing: list[str]
    crew_members: list[str]
    # Код шаблона, который оставлен как есть: состав уже заполнен человеком.
    crew_kept: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "reclassified": list(self.reclassified),
            "already_direct": list(self.already_direct),
            "missing": list(self.missing),
            "crew_members": list(self.crew_members),
            "crew_kept": self.crew_kept,
        }


def reclassify_positions(
    snapshot: ReferenceSnapshot,
) -> tuple[dict[str, list[ReferenceItem]], ReclassifyReport]:
    """Новые разделы с прямыми должностями БВР и шаблоном бригады.

    Идемпотентно: должность, уже переведённая в прямую с операцией, не
    меняется, а шаблон бригады пересобирается из тех должностей таблицы,
    которые есть в справочнике.
    """

    sections = {name: list(items) for name, items in normalize_sections(snapshot.sections).items()}
    report = ReclassifyReport([], [], [], [])
    by_code = {item.code: item for item in sections["positions"]}

    for spec in DIRECT_POSITIONS:
        item = by_code.get(spec.code)
        if item is None:
            report.missing.append(spec.code)
            continue
        payload = dict(item.payload)
        if payload.get("category") == "DIRECT" and payload.get("operation_code"):
            report.already_direct.append(spec.code)
            continue
        payload.update(
            {
                "category": "DIRECT",
                "operation_code": spec.operation_code,
                "norm_shifts_per_month": str(spec.norm_shifts_per_month),
                "piece_driver": spec.piece_driver,
                "piece_unit": "1",
                "per_diem_applies": True,
            }
        )
        if spec.norm_operations_per_month is not None:
            payload["norm_operations_per_month"] = str(spec.norm_operations_per_month)
        by_code[spec.code] = replace(item, payload=payload)
        report.reclassified.append(spec.code)
    sections["positions"] = [by_code.get(item.code, item) for item in sections["positions"]]

    members = [
        {"position_code": spec.code, "headcount": str(spec.default_headcount)}
        for spec in DIRECT_POSITIONS
        if spec.default_headcount > 0 and spec.code in by_code
    ]
    sections["crew_templates"], kept = _with_default_crew(sections["crew_templates"], members)
    report.crew_kept = kept
    report.crew_members = (
        [] if kept else [f"{m['position_code']} × {m['headcount']}" for m in members]
    )
    return sections, report


def _with_default_crew(
    templates: Sequence[ReferenceItem], members: list[Mapping[str, str]]
) -> tuple[list[ReferenceItem], str]:
    """Шаблон бригады по умолчанию и код шаблона, оставленного без изменений.

    Заполненный состав — данные организации: человек мог убрать должность или
    поставить трёх взрывников, и повторный прогон скрипта не вправе это
    затирать. Дозаполняется только пустой или отсутствующий шаблон.
    """

    if not members:
        return list(templates), ""
    template = next((item for item in templates if item.code == DEFAULT_CREW_CODE), None)
    if template is not None and template.payload.get("members"):
        return list(templates), template.code
    if template is None:
        template = ReferenceItem(
            code=DEFAULT_CREW_CODE,
            name="Бригада полного комплекса БВР",
            payload={"package_code": DEFAULT_PACKAGE},
            source="crew_defaults",
        )
    updated = replace(
        template,
        payload={**template.payload, "package_code": DEFAULT_PACKAGE, "members": members},
    )
    if any(item.code == DEFAULT_CREW_CODE for item in templates):
        return [updated if item.code == DEFAULT_CREW_CODE else item for item in templates], ""
    return [*templates, updated], ""


__all__ = [
    "DEFAULT_CREW_CODE",
    "DEFAULT_PACKAGE",
    "DIRECT_POSITIONS",
    "DirectPosition",
    "ReclassifyReport",
    "reclassify_positions",
]
