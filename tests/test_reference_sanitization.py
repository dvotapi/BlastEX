import math
import unittest

from cost.rock_data import rocks_from_records


class ReferenceSanitizationTests(unittest.TestCase):
    def test_non_finite_rock_values_are_normalized(self):
        rock = rocks_from_records(
            [{"name": "Тест", "density_t_m3": 2.5, "ucs_mpa": math.nan, "fissuring_ff": math.inf}]
        )[0]
        self.assertEqual(rock.ucs_mpa, 0.0)
        self.assertEqual(rock.fissuring_ff, 0.0)


if __name__ == "__main__":
    unittest.main()
