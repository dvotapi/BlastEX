import unittest

from design.as_charged import compare_design, record_as_charged
from design.as_drilled import record_as_drilled
from design.models import (
    AsChargedHole,
    AsDrilledHole,
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
        primer_items=[Primer(position_m=9.5, product="T-500")],
    )


class AsChargedCompareTests(unittest.TestCase):
    def test_zero_deviation_when_fact_matches_design(self):
        design = BlastDesign(design_id="cmp", holes=[_hole()], loads=[_load()])
        record_as_charged(
            design,
            AsChargedHole(
                design_hole_id="1-01",
                decks=[deck for deck in _load().decks],
                charge_mass_kg=70.0,
                stemming_length_m=3.0,
                explosive_product="ANFO",
                primer_items=[Primer(position_m=9.5, product="T-500")],
            ),
        )
        row = compare_design(design)["deviations"][0]
        self.assertAlmostEqual(row["charge_mass_delta_kg"], 0.0)
        self.assertAlmostEqual(row["stemming_delta_m"], 0.0)
        self.assertAlmostEqual(row["primer_position_delta_m"], 0.0)
        self.assertFalse(row["product_mismatch"])

    def test_mass_stemming_primer_product_and_deck_depths(self):
        design = BlastDesign(design_id="cmp", holes=[_hole()], loads=[_load()])
        record_as_charged(
            design,
            AsChargedHole(
                design_hole_id="1-01",
                decks=[
                    Deck(kind="stemming", from_m=0.0, to_m=2.4),
                    Deck(kind="bulk_explosive", from_m=2.4, to_m=10.5, mass_kg=78.0, product="Emulsion"),
                ],
                primer_items=[Primer(position_m=10.0, product="T-500")],
            ),
        )
        row = compare_design(design)["deviations"][0]
        self.assertAlmostEqual(row["charge_mass_delta_kg"], 8.0)
        self.assertAlmostEqual(row["stemming_delta_m"], -0.6)
        self.assertAlmostEqual(row["primer_position_delta_m"], 0.5)
        self.assertTrue(row["product_mismatch"])
        self.assertAlmostEqual(row["deck_from_delta_m"], -0.6)
        self.assertAlmostEqual(row["deck_to_delta_m"], 0.5)

    def test_drilled_depth_used_for_leftover_and_overcharge(self):
        design = BlastDesign(design_id="cmp", holes=[_hole()], loads=[_load()])
        record_as_drilled(
            design,
            AsDrilledHole(
                design_hole_id="1-01",
                actual_collar=Point3(x=0, y=0, z=0),
                actual_toe=Point3(x=0, y=0, z=-12.0),
                actual_depth=12.0,
                actual_diameter=152.0,
            ),
        )
        record_as_charged(
            design,
            AsChargedHole(
                design_hole_id="1-01",
                decks=[
                    Deck(kind="stemming", from_m=0.0, to_m=3.0),
                    Deck(kind="bulk_explosive", from_m=3.0, to_m=10.0, mass_kg=70.0, product="ANFO"),
                ],
            ),
        )
        row = compare_design(design)["deviations"][0]
        self.assertEqual(row["depth_basis"], "drilled")
        self.assertAlmostEqual(row["leftover_unloaded_m"], 2.0)
        self.assertAlmostEqual(row["overcharge_m"], 0.0)

    def test_compare_does_not_mutate_designed_load(self):
        design = BlastDesign(design_id="cmp", holes=[_hole()], loads=[_load()])
        record_as_charged(
            design,
            AsChargedHole(design_hole_id="1-01", charge_mass_kg=80.0, explosive_product="Emulsion"),
        )
        before_load = design.loads[0].to_dict()
        before_hole = design.holes[0].to_dict()
        compare_design(design)
        self.assertEqual(design.loads[0].to_dict(), before_load)
        self.assertEqual(design.holes[0].to_dict(), before_hole)


if __name__ == "__main__":
    unittest.main()
