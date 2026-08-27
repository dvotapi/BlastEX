import unittest

from design.as_charged import normalize_as_charged, record_as_charged
from design.models import (
    DESIGN_VERSION,
    ROLE_EXECUTED,
    AsChargedHole,
    BlastDesign,
    Deck,
    Hole,
    HoleLoad,
    Point3,
    Primer,
)


def _hole(hole_id: str = "1-01") -> Hole:
    return Hole(
        id=hole_id,
        row=1,
        col=1,
        collar=Point3(x=0.0, y=0.0, z=0.0),
        toe=Point3(x=0.0, y=0.0, z=-10.0),
        diameter_mm=152.0,
        subdrill_m=1.0,
    )


def _load(hole_id: str = "1-01") -> HoleLoad:
    return HoleLoad(
        hole_id=hole_id,
        decks=[
            Deck(kind="stemming", from_m=0.0, to_m=3.0),
            Deck(kind="bulk_explosive", from_m=3.0, to_m=10.0, mass_kg=70.0, product="ANFO"),
        ],
        total_charge_kg=70.0,
        primers=[9.5],
        primer_items=[Primer(position_m=9.5, product="T-500", mass_kg=0.4)],
    )


class AsChargedModelTests(unittest.TestCase):
    def test_round_trip_forces_executed_role(self):
        item = AsChargedHole(
            design_hole_id="1-01",
            decks=[Deck(kind="bulk_explosive", from_m=3.0, to_m=10.2, mass_kg=72.0, product="Emulsion")],
            explosive_product="Emulsion",
            charge_mass_kg=72.0,
            stemming_length_m=2.9,
            primer_items=[Primer(position_m=9.8, product="T-500")],
            loading_timestamp="2026-08-23T10:00:00+00:00",
        )
        restored = AsChargedHole.from_dict(item.to_dict())
        self.assertEqual(restored.role, ROLE_EXECUTED)
        self.assertEqual(restored.provenance.role, ROLE_EXECUTED)
        self.assertEqual(restored.explosive_product, "Emulsion")
        self.assertAlmostEqual(restored.charge_mass_kg, 72.0)
        self.assertAlmostEqual(restored.primer_items[0].position_m, 9.8)

    def test_normalize_fills_mass_stemming_and_product_from_decks(self):
        item = AsChargedHole(
            design_hole_id="1-01",
            decks=[
                Deck(kind="stemming", from_m=0.0, to_m=2.5),
                Deck(kind="bulk_explosive", from_m=2.5, to_m=10.0, mass_kg=65.0, product="ANFO"),
            ],
        )
        normalized = normalize_as_charged(item)
        self.assertAlmostEqual(normalized.charge_mass_kg, 65.0)
        self.assertAlmostEqual(normalized.stemming_length_m, 2.5)
        self.assertEqual(normalized.explosive_product, "ANFO")
        self.assertEqual(normalized.role, ROLE_EXECUTED)

    def test_design_version_includes_as_charged(self):
        design = BlastDesign(design_id="ac")
        payload = design.to_dict()
        self.assertEqual(payload["version"], DESIGN_VERSION)
        self.assertEqual(payload["as_charged_holes"], [])
        self.assertEqual(DESIGN_VERSION, 9)

    def test_record_does_not_overwrite_designed_load(self):
        design = BlastDesign(design_id="ac", holes=[_hole()], loads=[_load()])
        designed_before = design.loads[0].to_dict()
        hole_before = design.holes[0].to_dict()
        recorded = record_as_charged(
            design,
            AsChargedHole(
                design_hole_id="1-01",
                decks=[
                    Deck(kind="stemming", from_m=0.0, to_m=2.7),
                    Deck(kind="bulk_explosive", from_m=2.7, to_m=10.1, mass_kg=74.0, product="Emulsion"),
                ],
                primer_items=[Primer(position_m=9.9, product="T-500")],
            ),
        )
        self.assertEqual(recorded.role, ROLE_EXECUTED)
        self.assertEqual(design.loads[0].to_dict(), designed_before)
        self.assertEqual(design.holes[0].to_dict(), hole_before)
        self.assertAlmostEqual(design.loads[0].total_charge_kg, 70.0)
        self.assertAlmostEqual(design.as_charged_holes[0].charge_mass_kg, 74.0)
        self.assertTrue(design.as_charged_holes[0].loading_timestamp)

    def test_record_unknown_hole_is_rejected(self):
        design = BlastDesign(design_id="ac", holes=[_hole()], loads=[_load()])
        with self.assertRaises(ValueError):
            record_as_charged(
                design,
                AsChargedHole(design_hole_id="missing", charge_mass_kg=10.0),
            )
        self.assertEqual(design.as_charged_holes, [])
        self.assertAlmostEqual(design.loads[0].total_charge_kg, 70.0)


if __name__ == "__main__":
    unittest.main()
