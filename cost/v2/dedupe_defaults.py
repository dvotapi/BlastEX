"""Известные дубли номенклатуры ВМ из импорта Cost V1 — деактивация, не удаление.

Импорт V1 иногда заводил одну и ту же позицию под двумя кодами (журнал
техники и прайс поставщика — разные источники). PR #61 починил угадывание
роли по названию, но сами дубли в данных этим не устраняются: код остаётся
дублем, только правильно классифицированным. Здесь — явный список таких
дублей и функция, которая гасит дублирующий код (is_active=False) в пользу
канонического, не трогая ничего, что на дублирующий код не ссылается.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any

from cost.v2.models import ReferenceItem, ReferenceSnapshot
from cost.v2.references import normalize_sections


@dataclass(frozen=True)
class DuplicateMaterial:
    duplicate_code: str
    canonical_code: str
    comment: str


# «Устройство Искра-П-*-5» (MAT_SURFACE_NSI_5) и «НСИ Искра-П-*-5»
# (MAT_NSI_ISKRA_P_50) — одна и та же позиция (поверхностное замедляющее
# устройство «*-5») под двумя кодами: журнал техники завёл её как
# MAT_SURFACE_NSI_5, прайс поставщика — как MAT_NSI_ISKRA_P_50 (префикс
# MAT_NSI_* до PR #61 уводил её в скважинные НСИ). Ни в одном другом
# разделе справочников (cost_rules, drilling_conditions) и ни в одном
# сохранённом паспорте/прогоне код MAT_NSI_ISKRA_P_50 не используется —
# деактивация безопасна.
DUPLICATE_MATERIALS: tuple[DuplicateMaterial, ...] = (
    DuplicateMaterial(
        duplicate_code="MAT_NSI_ISKRA_P_50",
        canonical_code="MAT_SURFACE_NSI_5",
        comment=(
            "Дубль «Устройство Искра-П-*-5» (MAT_SURFACE_NSI_5) под кодом "
            "прайса поставщика — используйте канонический код."
        ),
    ),
)


@dataclass
class DedupeReport:
    deactivated: list[str]
    already_inactive: list[str]
    missing: list[str]
    canonical_missing: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "deactivated": list(self.deactivated),
            "already_inactive": list(self.already_inactive),
            "missing": list(self.missing),
            "canonical_missing": list(self.canonical_missing),
        }


def deactivate_duplicate_materials(
    snapshot: ReferenceSnapshot,
) -> tuple[dict[str, list[ReferenceItem]], DedupeReport]:
    """Гасит известные дубли материалов и их цены. Идемпотентно."""

    sections = {name: list(items) for name, items in normalize_sections(snapshot.sections).items()}
    report = DedupeReport([], [], [], [])
    materials = {item.code: item for item in sections["materials"]}

    for dup in DUPLICATE_MATERIALS:
        item = materials.get(dup.duplicate_code)
        if item is None:
            report.missing.append(dup.duplicate_code)
            continue
        if not item.is_active:
            report.already_inactive.append(dup.duplicate_code)
            continue
        canonical = materials.get(dup.canonical_code)
        if canonical is None or not canonical.is_active:
            # Гасить дубль в пользу несуществующей/неактивной канонической
            # записи — оставить позицию вообще без активной замены.
            report.canonical_missing.append(dup.duplicate_code)
            continue
        materials[dup.duplicate_code] = replace(item, is_active=False, comment=dup.comment)
        sections["material_prices"] = [
            replace(price, is_active=False) if price.payload.get("material_code") == dup.duplicate_code and price.is_active
            else price
            for price in sections["material_prices"]
        ]
        report.deactivated.append(dup.duplicate_code)

    sections["materials"] = [materials.get(item.code, item) for item in sections["materials"]]
    return sections, report
