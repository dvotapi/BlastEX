"""Unit conversions stay explicit: kg/m³ vs t/m³, cm vs mm."""
import unittest

from simulation.fragmentation.units import (
    TNT_ENERGY_MJ_KG,
    density_kg_m3_from_t_m3,
    density_t_m3_from_kg_m3,
    fragment_mm_from_cm,
    length_m_from_mm,
    length_mm_from_m,
    relative_weight_strength,
)


class UnitConversionTests(unittest.TestCase):
    def test_density_round_trip(self):
        self.assertAlmostEqual(density_t_m3_from_kg_m3(2700.0), 2.7)
        self.assertAlmostEqual(density_kg_m3_from_t_m3(2.7), 2700.0)

    def test_fragment_cm_to_mm(self):
        self.assertEqual(fragment_mm_from_cm(12.3), 123.0)

    def test_length_mm_m(self):
        self.assertEqual(length_mm_from_m(4.0), 4000.0)
        self.assertEqual(length_m_from_mm(152.0), 0.152)

    def test_tnt_reference_is_explicit(self):
        self.assertEqual(TNT_ENERGY_MJ_KG, 4.184)
        self.assertAlmostEqual(relative_weight_strength(4.184), 1.0)


if __name__ == "__main__":
    unittest.main()
