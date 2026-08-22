import unittest

from Blast import ExplosiveProperties
from cost.geometry import calculate_hole_geometry
from design.charging import apply_charge_rules
from design.models import Hole, Point3

EXPLOSIVE = ExplosiveProperties("Гранулит-РП", 0.85, 3.76)


def _vertical_hole(depth_m: float = 11.0, subdrill_m: float = 1.0, diameter_mm: float = 152.0) -> Hole:
    return Hole(
        id="1-01",
        row=0,
        col=0,
        collar=Point3(x=0.0, y=0.0, z=0.0),
        toe=Point3(x=0.0, y=0.0, z=-depth_m),
        diameter_mm=diameter_mm,
        subdrill_m=subdrill_m,
    )


class ContinuousChargeMatchesCostGeometryTests(unittest.TestCase):
    def test_mass_and_specific_q_match_cost_geometry(self):
        hole = _vertical_hole()
        loads = apply_charge_rules(
            [hole],
            {
                "hole_oversize_coeff": 1.05,
                "stemming_m": 3.0,
                "decking": "continuous",
                "grid_a_m": 5.0,
                "grid_b_m": 5.0,
            },
            EXPLOSIVE,
        )
        load = loads[0]

        reference = calculate_hole_geometry(
            grid_a_m=5.0,
            grid_b_m=5.0,
            depth_m=11.0,
            overdrill_m=1.0,
            undercharge_m=3.0,
            crown_mm=152.0,
            hole_oversize_coeff=1.05,
            explosive=EXPLOSIVE,
        )

        self.assertAlmostEqual(load.total_charge_kg, reference.charge_mass_kg, places=6)
        self.assertAlmostEqual(load.influence_volume_m3, reference.yield_m3, places=6)
        self.assertAlmostEqual(load.specific_q_kg_m3, reference.specific_q_kg_m3, places=6)

    def test_single_charge_deck_spans_from_stemming_to_toe(self):
        hole = _vertical_hole()
        loads = apply_charge_rules(
            [hole],
            {"stemming_m": 3.0, "decking": "continuous"},
            EXPLOSIVE,
        )
        decks = loads[0].decks
        self.assertEqual([d.kind for d in decks], ["stemming", "charge"])
        self.assertEqual(decks[0].from_m, 0.0)
        self.assertEqual(decks[0].to_m, 3.0)
        self.assertEqual(decks[1].from_m, 3.0)
        self.assertAlmostEqual(decks[1].to_m, hole.length_m)


class SpacedChargeTests(unittest.TestCase):
    def test_two_decks_with_air_gap_sum_to_hole_length(self):
        hole = _vertical_hole()
        loads = apply_charge_rules(
            [hole],
            {
                "stemming_m": 3.0,
                "decking": "spaced",
                "deck_count": 2,
                "air_gap_m": 1.5,
            },
            EXPLOSIVE,
        )
        decks = loads[0].decks
        kinds = [d.kind for d in decks]
        self.assertEqual(kinds, ["stemming", "charge", "air", "charge"])
        self.assertAlmostEqual(decks[-1].to_m, hole.length_m)
        # Обе деки заряда должны быть равной длины.
        charge_decks = [d for d in decks if d.kind == "charge"]
        lengths = [d.to_m - d.from_m for d in charge_decks]
        self.assertAlmostEqual(lengths[0], lengths[1])
        # Масса — сумма масс обеих дек, воздух и забойка массы не несут.
        self.assertAlmostEqual(
            loads[0].total_charge_kg, sum(d.mass_kg for d in charge_decks)
        )

    def test_primers_placed_near_bottom_of_each_charge_deck(self):
        hole = _vertical_hole()
        loads = apply_charge_rules(
            [hole],
            {
                "stemming_m": 3.0,
                "decking": "spaced",
                "deck_count": 2,
                "air_gap_m": 1.5,
                "primer_offset_m": 0.3,
            },
            EXPLOSIVE,
        )
        load = loads[0]
        charge_decks = [d for d in load.decks if d.kind == "charge"]
        self.assertEqual(len(load.primers), 2)
        for primer_depth, deck in zip(load.primers, charge_decks):
            self.assertAlmostEqual(primer_depth, deck.to_m - 0.3)
            self.assertGreaterEqual(primer_depth, deck.from_m)

    def test_gap_too_large_falls_back_to_continuous(self):
        hole = _vertical_hole(depth_m=6.0, subdrill_m=0.0)
        loads = apply_charge_rules(
            [hole],
            {
                "stemming_m": 1.0,
                "decking": "spaced",
                "deck_count": 3,
                "air_gap_m": 5.0,  # промежутки заведомо не помещаются в оставшуюся длину
            },
            EXPLOSIVE,
        )
        decks = loads[0].decks
        self.assertEqual([d.kind for d in decks], ["stemming", "charge"])
        self.assertAlmostEqual(decks[1].to_m, hole.length_m)


class StemmingFromCoefficientTests(unittest.TestCase):
    def test_stemming_derived_from_diameter_when_not_fixed(self):
        hole = _vertical_hole(diameter_mm=200.0)
        loads = apply_charge_rules(
            [hole],
            {"stemming_k": 15.0, "decking": "continuous"},
            EXPLOSIVE,
        )
        stemming = loads[0].decks[0]
        self.assertEqual(stemming.kind, "stemming")
        self.assertAlmostEqual(stemming.to_m, 15.0 * 0.2)


if __name__ == "__main__":
    unittest.main()
