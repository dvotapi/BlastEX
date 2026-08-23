"""BDX-017: discrete search space is deterministic and unit-explicit."""
import unittest

from design.optimization.space import (
    InvalidSearchSpaceError,
    build_space,
    discrete_range,
    enumerate_vectors,
)
from design.optimization.types import DecisionVector, VariableBound


class OptimizationSpaceTests(unittest.TestCase):
    def test_discrete_range_keeps_declared_millimetres(self):
        values = discrete_range(152.0, 178.0, 13.0)
        self.assertEqual(values, [152.0, 165.0, 178.0])

    def test_expand_rejects_unknown_axis(self):
        with self.assertRaises(InvalidSearchSpaceError):
            build_space([VariableBound(name="q_mystery", values=[1.0])])

    def test_categorical_explosive_requires_explicit_values(self):
        with self.assertRaises(InvalidSearchSpaceError):
            build_space([VariableBound(name="explosive_key", minimum=0, maximum=1, step=1)])

    def test_enumerate_is_lexicographic_and_repeatable(self):
        space = build_space(
            [
                VariableBound(name="diameter_mm", values=[152, 165]),
                VariableBound(name="burden_b_m", values=[4.0, 4.5]),
            ]
        )
        first = [item.values for item in enumerate_vectors(space, max_candidates=10)]
        second = [item.values for item in enumerate_vectors(space, max_candidates=10)]
        self.assertEqual(first, second)
        self.assertEqual(first[0], {"diameter_mm": 152.0, "burden_b_m": 4.0})
        self.assertEqual(first[-1], {"diameter_mm": 165.0, "burden_b_m": 4.5})
        self.assertEqual(len(first), 4)

    def test_thinning_is_regular_and_keeps_last(self):
        space = build_space([VariableBound(name="diameter_mm", values=[100, 120, 140, 160, 180, 200])])
        vectors = enumerate_vectors(space, max_candidates=3)
        self.assertEqual(len(vectors), 3)
        self.assertEqual(vectors[0].values["diameter_mm"], 100.0)
        self.assertEqual(vectors[-1].values["diameter_mm"], 200.0)

    def test_include_baseline_vector_once(self):
        space = build_space([VariableBound(name="spacing_a_m", values=[5.0, 5.5])])
        extra = DecisionVector(values={"spacing_a_m": 4.5})
        vectors = enumerate_vectors(space, max_candidates=10, include=extra)
        fingerprints = [item.fingerprint() for item in vectors]
        self.assertEqual(fingerprints[0], extra.fingerprint())
        self.assertEqual(fingerprints.count(extra.fingerprint()), 1)


if __name__ == "__main__":
    unittest.main()
