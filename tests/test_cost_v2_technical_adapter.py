from decimal import Decimal

from cost.v2.technical_adapter import adapt_blast_block


def test_blast_geometry_maps_to_cost_v2_physical_drivers_with_lineage() -> None:
    snapshot = adapt_blast_block(
        {
            "block_volume_m3": "120000.5",
            "drilling_footage_m": "2400.25",
            "total_charge_mass_kg": "63000.75",
            "total_holes": 180,
            "total_intermediate_detonators": 360,
            "total_downhole_nsi": 180,
            "total_nsi_length_m": 2160,
            "total_boosters": 180,
            "total_surface_nsi": 24,
            "total_start_nsi": 1,
        },
        existing_physical={"szm_hours": "42.5", "distance_km": 35},
        source_id="BLOCK-17",
    )

    assert snapshot.source_id == "BLOCK-17"
    assert snapshot.physical["rock_volume_m3"] == Decimal("120000.5")
    assert snapshot.physical["drilling_m"] == Decimal("2400.25")
    assert snapshot.physical["explosive_kg"] == Decimal("63000.75")
    assert snapshot.physical["holes"] == Decimal("180")
    assert snapshot.physical["blasts"] == Decimal("1")
    assert snapshot.physical["szm_hours"] == Decimal("42.5")
    assert snapshot.lineage["explosive_kg"] == "BlastGeometry.block.total_charge_mass_kg"
    assert snapshot.lineage["szm_hours"] == "manual"


def test_empty_block_does_not_create_a_blast_event() -> None:
    snapshot = adapt_blast_block({})
    assert snapshot.physical["blasts"] == Decimal("0")


def test_negative_manual_driver_is_rejected() -> None:
    try:
        adapt_blast_block({}, existing_physical={"szm_hours": -1})
    except ValueError as exc:
        assert "szm_hours" in str(exc)
    else:
        raise AssertionError("negative driver must be rejected")
