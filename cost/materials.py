"""
Этап 2 — переменные расходы 1.1 (ВМ и СИ).

Количества берутся из технического расчёта (geometry), цены — из справочника.
"""
from __future__ import annotations

from dataclasses import dataclass

from cost.catalog import (
    CatalogItem,
    default_start_nsi,
    default_surface_nsi,
    find_downhole_nsi_by_length,
    get_catalog_item,
    items_by_category,
    resolve_explosive_id,
)
from cost.models import BlockGeometry, InitiationConfig


@dataclass
class MaterialLine:
    section: str
    nomenclature: str
    unit: str
    quantity: float
    price: float
    amount: float
    source: str


@dataclass
class VariableMaterialsResult:
    lines: list[MaterialLine]
    total_amount: float

    @property
    def total_per_m3(self) -> float:
        if not self.lines:
            return 0.0
        return self.total_amount  # caller divides by block volume if needed


@dataclass
class MaterialsSelection:
    explosive_id: str
    detonator_id: str
    downhole_nsi1_id: str
    downhole_nsi2_id: str | None = None
    surface_nsi_id: str = ""
    start_nsi_id: str = ""


def auto_materials_selection(
    *,
    catalog: list[CatalogItem],
    explosive_key: str,
    initiation: InitiationConfig,
) -> MaterialsSelection:
    explosive_id = resolve_explosive_id(explosive_key, catalog)
    detonators = items_by_category(catalog, "detonator")
    detonator_id = detonators[0].id if detonators else ""

    downhole1 = find_downhole_nsi_by_length(catalog, initiation.nsi_length_1_m)
    downhole2 = (
        find_downhole_nsi_by_length(catalog, initiation.nsi_length_2_m)
        if initiation.nsi_per_hole == 2
        else None
    )
    surface_nsi = default_surface_nsi(catalog)
    start_nsi = default_start_nsi(catalog)
    return MaterialsSelection(
        explosive_id=explosive_id,
        detonator_id=detonator_id,
        downhole_nsi1_id=downhole1.id if downhole1 else "",
        downhole_nsi2_id=downhole2.id if downhole2 else None,
        surface_nsi_id=surface_nsi.id if surface_nsi else "",
        start_nsi_id=start_nsi.id if start_nsi else "",
    )


def calculate_variable_materials(
    *,
    block: BlockGeometry,
    initiation: InitiationConfig,
    catalog: list[CatalogItem],
    selection: MaterialsSelection,
) -> VariableMaterialsResult:
    """Расчёт переменных расходов 1.1 для одного варианта заряжания."""
    lines: list[MaterialLine] = []

    explosive = get_catalog_item(catalog, selection.explosive_id)
    if explosive and block.total_charge_mass_kg > 0:
        qty = block.total_charge_mass_kg
        lines.append(
            MaterialLine(
                section="1.1 ВМ",
                nomenclature=explosive.name,
                unit=explosive.unit,
                quantity=qty,
                price=explosive.price,
                amount=qty * explosive.price,
                source="масса ВВ на блок",
            )
        )

    detonator = get_catalog_item(catalog, selection.detonator_id)
    if detonator and block.total_intermediate_detonators > 0:
        mass_kg = detonator.mass_kg or 1.0
        qty_pieces = block.total_intermediate_detonators
        qty_kg = qty_pieces * mass_kg
        lines.append(
            MaterialLine(
                section="1.1 ВМ",
                nomenclature=detonator.name,
                unit=detonator.unit,
                quantity=qty_kg,
                price=detonator.price,
                amount=qty_kg * detonator.price,
                source=f"пром. детонаторы: {qty_pieces} шт × {mass_kg:.2f} кг",
            )
        )

    if block.total_holes > 0:
        downhole1 = get_catalog_item(catalog, selection.downhole_nsi1_id)
        if downhole1:
            qty = block.total_holes
            lines.append(
                MaterialLine(
                    section="1.1 СИ",
                    nomenclature=downhole1.name,
                    unit=downhole1.unit,
                    quantity=qty,
                    price=downhole1.price,
                    amount=qty * downhole1.price,
                    source="НСИ скважинное × скважины",
                )
            )

        if initiation.nsi_per_hole == 2 and selection.downhole_nsi2_id:
            downhole2 = get_catalog_item(catalog, selection.downhole_nsi2_id)
            if downhole2:
                qty = block.total_holes
                lines.append(
                    MaterialLine(
                        section="1.1 СИ",
                        nomenclature=downhole2.name,
                        unit=downhole2.unit,
                        quantity=qty,
                        price=downhole2.price,
                        amount=qty * downhole2.price,
                        source="НСИ скважинное (дубль) × скважины",
                    )
                )

        if selection.surface_nsi_id:
            surface_nsi = get_catalog_item(catalog, selection.surface_nsi_id)
            if surface_nsi:
                qty = block.total_surface_nsi
                lines.append(
                    MaterialLine(
                        section="1.1 СИ",
                        nomenclature=surface_nsi.name,
                        unit=surface_nsi.unit,
                        quantity=qty,
                        price=surface_nsi.price,
                        amount=qty * surface_nsi.price,
                        source="НСИ поверхностное × скважины",
                    )
                )

    if selection.start_nsi_id:
        start_nsi = get_catalog_item(catalog, selection.start_nsi_id)
        if start_nsi:
            qty = block.total_start_nsi
            lines.append(
                MaterialLine(
                    section="1.1 СИ",
                    nomenclature=start_nsi.name,
                    unit=start_nsi.unit,
                    quantity=qty,
                    price=start_nsi.price,
                    amount=qty * start_nsi.price,
                    source="НСИ стартовое на блок",
                )
            )

    total = sum(line.amount for line in lines)
    return VariableMaterialsResult(lines=lines, total_amount=total)


def materials_table_rows(result: VariableMaterialsResult) -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    for line in result.lines:
        qty_fmt = f"{line.quantity:.0f}" if line.unit == "шт" else f"{line.quantity:.1f}"
        rows.append((line.nomenclature, f"{qty_fmt} {line.unit}"))
        rows.append((f"  цена, руб/{line.unit}", f"{line.price:.2f}"))
        rows.append((f"  сумма, руб", f"{line.amount:,.0f}"))
    rows.append(("Итого 1.1, руб", f"{result.total_amount:,.0f}"))
    return rows
