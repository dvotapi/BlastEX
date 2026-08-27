"""Unit conversions stay explicit: mm vs m, kg vs t, ms vs s."""
import unittest

from simulation.movement.units import (
    angle_deg_from_rad,
    angle_rad_from_deg,
    length_m_from_mm,
    length_mm_from_m,
    mass_kg_from_t,
    mass_t_from_kg,
    time_ms_from_s,
    time_s_from_ms,
)


class MovementUnitTests(unittest.TestCase):
    def test_length_round_trip(self):
        self.assertEqual(length_m_from_mm(152.0), 0.152)
        self.assertEqual(length_mm_from_m(4.0), 4000.0)

    def test_mass_round_trip(self):
        self.assertEqual(mass_kg_from_t(2.5), 2500.0)
        self.assertEqual(mass_t_from_kg(820.0), 0.82)

    def test_time_round_trip(self):
        self.assertEqual(time_s_from_ms(25.0), 0.025)
        self.assertEqual(time_ms_from_s(0.008), 8.0)

    def test_angle_round_trip(self):
        self.assertAlmostEqual(angle_deg_from_rad(angle_rad_from_deg(90.0)), 90.0)

    def test_diameter_mm_is_never_used_as_metres(self):
        diameter_mm = 152.0
        self.assertNotAlmostEqual(length_m_from_mm(diameter_mm), diameter_mm)
        self.assertLess(length_m_from_mm(diameter_mm), 1.0)


if __name__ == "__main__":
    unittest.main()
