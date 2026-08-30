from dataclasses import replace

from cost.v2.models import ReferenceSnapshot
from cost.v2.packages import DEFAULT_OPERATIONS, DEFAULT_PACKAGES
from cost.v2.references import default_reference_snapshot, validate_reference_sections


def test_all_ten_approved_packages_exist() -> None:
    assert {item.code for item in DEFAULT_PACKAGES} == {
        "VM_IN_HOLE",
        "BLASTING_NO_DRILLING",
        "DRILLING",
        "DRILL_AND_BLAST",
        "VM_WAREHOUSE_SALE",
        "VM_WAREHOUSE_TRANSFER",
        "CONTOUR_BLASTING",
        "CONTOUR_DRILLING",
        "CONTOUR_DRILL_AND_BLAST",
        "OVERSIZE_BREAKING",
    }


def test_vm_in_hole_stops_after_explosive_delivery() -> None:
    package = next(item for item in DEFAULT_PACKAGES if item.code == "VM_IN_HOLE")
    codes = {item.operation_code for item in package.operations}
    assert "BULK_CHARGING_SZM" in codes
    assert "CHARGING_HOSE_ASSISTANCE" in codes
    assert codes.isdisjoint(
        {
            "PRIMER_ASSEMBLY",
            "STEMMING",
            "INITIATION_NETWORK",
            "BLAST_SAFETY_ZONE",
            "BLAST_EXECUTION",
        }
    )


def test_drill_and_blast_contains_unique_substage_operations() -> None:
    package = next(item for item in DEFAULT_PACKAGES if item.code == "DRILL_AND_BLAST")
    codes = [item.operation_code for item in package.operations]
    assert len(codes) == len(set(codes))
    assert "BULK_CHARGING_SZM" in codes
    assert "PRIMER_ASSEMBLY" in codes
    assert "OVERSIZE_BREAKING" in codes


def test_oversize_breaking_uses_own_excavator_pool() -> None:
    operation = next(item for item in DEFAULT_OPERATIONS if item.code == "OVERSIZE_BREAKING")
    assert operation.resource_code == "OWN_EXCAVATOR_HOUR"


def test_reference_validation_rejects_initiation_in_vm_in_hole() -> None:
    snapshot = default_reference_snapshot()
    sections = dict(snapshot.sections)
    packages = []
    for item in sections["work_packages"]:
        if item.code != "VM_IN_HOLE":
            packages.append(item)
            continue
        payload = dict(item.payload)
        payload["operations"] = [*payload["operations"], {"operation_code": "INITIATION_NETWORK"}]
        packages.append(replace(item, payload=payload))
    sections["work_packages"] = tuple(packages)
    issues = validate_reference_sections(ReferenceSnapshot("bad", sections).sections)
    assert any(
        issue.level == "error"
        and issue.section == "work_packages"
        and issue.code == "VM_IN_HOLE"
        for issue in issues
    )
