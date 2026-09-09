"""Дубль номенклатуры «Искра-П-*-5»: деактивация, а не удаление, и идемпотентно."""
from __future__ import annotations

from cost.v2.dedupe_defaults import deactivate_duplicate_materials
from cost.v2.models import ReferenceItem, ReferenceSnapshot
from cost.v2.references import default_reference_snapshot


def _snapshot_with_duplicate() -> ReferenceSnapshot:
    base = default_reference_snapshot()
    sections = dict(base.sections)
    sections["materials"] = (
        *sections["materials"],
        ReferenceItem(
            code="MAT_SURFACE_NSI_5",
            name="Устройство Искра-П-*-5",
            payload={"unit": "PIECE", "nomenclature_role": "NSI_SURFACE"},
        ),
        ReferenceItem(
            code="MAT_NSI_ISKRA_P_50",
            name="НСИ Искра-П-*-5",
            payload={"unit": "PIECE", "nomenclature_role": "NSI_SURFACE"},
        ),
    )
    sections["material_prices"] = (
        *sections["material_prices"],
        ReferenceItem(
            code="PRICE_MAT_NSI_ISKRA_P_50",
            name="Цена",
            payload={"material_code": "MAT_NSI_ISKRA_P_50", "price_rub": "239.55"},
        ),
    )
    return ReferenceSnapshot(revision_id="TEST", sections=sections)


def test_duplicate_material_and_its_price_are_deactivated_not_deleted() -> None:
    sections, report = deactivate_duplicate_materials(_snapshot_with_duplicate())

    assert report.deactivated == ["MAT_NSI_ISKRA_P_50"]
    assert report.missing == []

    dup = next(item for item in sections["materials"] if item.code == "MAT_NSI_ISKRA_P_50")
    assert dup.is_active is False
    assert "MAT_SURFACE_NSI_5" in dup.comment

    canonical = next(item for item in sections["materials"] if item.code == "MAT_SURFACE_NSI_5")
    assert canonical.is_active is True

    price = next(item for item in sections["material_prices"] if item.code == "PRICE_MAT_NSI_ISKRA_P_50")
    assert price.is_active is False


def test_running_twice_does_not_double_deactivate() -> None:
    first_sections, _ = deactivate_duplicate_materials(_snapshot_with_duplicate())
    again = ReferenceSnapshot(
        revision_id="TEST-2",
        sections={name: tuple(items) for name, items in first_sections.items()},
    )

    sections, report = deactivate_duplicate_materials(again)

    assert report.deactivated == []
    assert report.already_inactive == ["MAT_NSI_ISKRA_P_50"]
    dup = next(item for item in sections["materials"] if item.code == "MAT_NSI_ISKRA_P_50")
    assert dup.is_active is False


def test_missing_duplicate_is_reported_not_an_error() -> None:
    _, report = deactivate_duplicate_materials(default_reference_snapshot())

    assert report.missing == ["MAT_NSI_ISKRA_P_50"]
    assert report.deactivated == []
