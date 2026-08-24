import unittest

from design.models import BlastDomain, BenchSurface, BlockContour, Hole, Point3
from design.pattern import PATTERN_TYPES, generate_pattern


def _rect(width: float, height: float, free_south: bool = False) -> BlockContour:
    verts = [(0.0, 0.0), (width, 0.0), (width, height), (0.0, height)]
    return BlockContour(
        vertices=[Point3(x=x, y=y, z=0.0) for x, y in verts],
        free_faces=[[0, 1]] if free_south else [],
        bench=BenchSurface(crest_z_m=0.0, toe_z_m=-10.0),
    )


BASE = {
    "spacing_a_m": 5.0,
    "burden_b_m": 5.0,
    "offset_from_face_m": 0.0,
    "edge_margin_m": 0.0,
}


class PatternTypeRegistryTests(unittest.TestCase):
    def test_supported_pattern_types(self):
        self.assertEqual(
            PATTERN_TYPES,
            ("square", "rectangular", "staggered", "variable", "domain_dependent"),
        )


class FirstRowBurdenTests(unittest.TestCase):
    def test_first_row_uses_dedicated_burden_then_production_step(self):
        # row_azimuth=0 → rows along +Y, advance along +X. Face origin is min X.
        holes = generate_pattern(
            _rect(20.0, 20.0),
            {**BASE, "pattern": "rectangular", "first_row_burden_m": 6.0, "burden_b_m": 4.0},
        )
        production = [h for h in holes if h.kind == "production"]
        xs = sorted({round(h.collar.x, 6) for h in production})
        self.assertIn(6.0, xs)
        self.assertIn(10.0, xs)
        self.assertNotIn(0.0, xs)

    def test_follow_face_places_first_row_at_constant_burden(self):
        contour = _rect(20.0, 20.0, free_south=True)
        holes = generate_pattern(
            contour,
            {
                **BASE,
                "pattern": "rectangular",
                "first_row_burden_m": 3.0,
                "first_row_follow_face": True,
                "row_azimuth_deg": 90.0,
            },
        )
        first = [h for h in holes if h.kind == "production" and h.row == 0]
        self.assertGreaterEqual(len(first), 3)
        for hole in first:
            self.assertAlmostEqual(hole.collar.y, 3.0, places=5)


class VariablePatternTests(unittest.TestCase):
    def test_per_row_spacing_and_kind(self):
        holes = generate_pattern(
            _rect(20.0, 20.0),
            {
                **BASE,
                "pattern": "variable",
                "row_params": [
                    {"spacing_a_m": 10.0, "burden_b_m": 5.0, "kind": "buffer"},
                    {"spacing_a_m": 5.0, "burden_b_m": 5.0, "kind": "production"},
                ],
            },
        )
        row0 = [h for h in holes if h.row == 0]
        row1 = [h for h in holes if h.row == 1]
        self.assertTrue(row0)
        self.assertTrue(all(h.kind == "buffer" for h in row0))
        self.assertTrue(all(h.kind == "production" for h in row1))
        self.assertLess(len(row0), len(row1))


class DomainDependentPatternTests(unittest.TestCase):
    def test_denser_domain_gets_tighter_spacing(self):
        contour = _rect(40.0, 20.0)
        hard = BlastDomain(
            id="D-hard",
            name="hard",
            polygon=[
                Point3(0, 0, 0),
                Point3(20, 0, 0),
                Point3(20, 20, 0),
                Point3(0, 20, 0),
            ],
            spacing_a_m=4.0,
            burden_b_m=4.0,
            priority=2,
        )
        soft = BlastDomain(
            id="D-soft",
            name="soft",
            polygon=[
                Point3(20, 0, 0),
                Point3(40, 0, 0),
                Point3(40, 20, 0),
                Point3(20, 20, 0),
            ],
            spacing_a_m=10.0,
            burden_b_m=10.0,
            priority=1,
        )
        holes = generate_pattern(
            contour,
            {**BASE, "pattern": "domain_dependent", "spacing_a_m": 8.0, "burden_b_m": 8.0},
            domains=[hard, soft],
        )
        left = [h for h in holes if h.collar.x < 20]
        right = [h for h in holes if h.collar.x > 20]
        self.assertGreater(len(left), len(right))
        self.assertTrue(holes)
        self.assertTrue(all(h.source == "generated" for h in holes))


class HoleKindGenerationTests(unittest.TestCase):
    def test_all_special_kinds_can_be_generated(self):
        contour = _rect(20.0, 20.0, free_south=True)
        holes = generate_pattern(
            contour,
            {
                **BASE,
                "pattern": "rectangular",
                "row_azimuth_deg": 90.0,
                "contour_row": True,
                "presplit_row": True,
                "trim_row": True,
                "buffer_row": True,
                "stab_row": True,
                "satellite_holes": True,
                "infill_holes": True,
                "contour_spacing_m": 4.0,
                "presplit_spacing_m": 2.0,
                "trim_spacing_m": 3.0,
                "buffer_offset_m": 1.5,
                "buffer_spacing_m": 5.0,
                "satellite_radius_m": 1.0,
                "satellite_count": 1,
                "infill_gap_factor": 1.01,
            },
        )
        kinds = {h.kind for h in holes}
        self.assertTrue({"production", "contour", "presplit", "trim", "buffer"}.issubset(kinds))
        self.assertTrue({"stab", "satellite"} & kinds)
        self.assertTrue(all(h.source == "generated" for h in holes))

    def test_default_kind_assigns_production_grid(self):
        holes = generate_pattern(_rect(20.0, 20.0), {**BASE, "pattern": "square", "default_kind": "infill"})
        self.assertTrue(holes)
        self.assertTrue(all(h.kind == "infill" for h in holes))

    def test_unknown_kind_falls_back_to_production(self):
        holes = generate_pattern(_rect(20.0, 20.0), {**BASE, "pattern": "square", "default_kind": "mystery"})
        self.assertTrue(all(h.kind == "production" for h in holes))

    def test_manual_holes_survive_professional_regeneration(self):
        contour = _rect(20.0, 20.0)
        manual = Hole(
            id="M-1",
            row=99,
            col=1,
            collar=Point3(x=3.0, y=3.0, z=0.0),
            toe=Point3(x=3.0, y=3.0, z=-10.0),
            diameter_mm=152.0,
            kind="satellite",
            source="manual",
        )
        regenerated = generate_pattern(contour, {**BASE, "pattern": "staggered"}, existing_holes=[manual])
        self.assertTrue(any(h.id == "M-1" and h.kind == "satellite" for h in regenerated))


if __name__ == "__main__":
    unittest.main()
