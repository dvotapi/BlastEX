import unittest

from design.charging import hole_geology_for_charging, rock_properties_for_charging
from design.geology import (
    apply_domains_to_hole,
    apply_domains_to_holes,
    assign_domain_polygon,
    intercept_hole,
    properties_at,
)
from design.models import (
    BlastDomain,
    DataProvenance,
    Hole,
    HoleInterval,
    Point3,
    RockPropertySet,
    WaterInterval,
)


def _vertical(depth_m: float = 11.0, x: float = 5.0, y: float = 5.0) -> Hole:
    return Hole(
        id="1-01",
        row=0,
        col=0,
        collar=Point3(x=x, y=y, z=0.0),
        toe=Point3(x=x, y=y, z=-depth_m),
        diameter_mm=152.0,
        subdrill_m=1.0,
    )


def _layer(domain_id: str, name: str, z_top: float, z_bottom: float, **props) -> BlastDomain:
    return BlastDomain(
        id=domain_id,
        name=name,
        properties=RockPropertySet(**props),
        z_top_m=z_top,
        z_bottom_m=z_bottom,
    )


class LayeredInterceptTests(unittest.TestCase):
    def test_example_weathered_granite_stack(self):
        hole = _vertical(11.0)
        domains = [
            _layer("D-w", "weathered", 0.0, -3.0, fracturing="weathered", blastability="high"),
            _layer("D-g", "competent granite", -3.0, -8.0, ucs_mpa=140.0, blastability="medium"),
            _layer("D-f", "fractured granite", -8.0, -11.0, fracturing="intense", blastability="high"),
        ]
        rock, water = intercept_hole(hole, domains)
        self.assertEqual([(round(iv.from_m, 6), round(iv.to_m, 6), iv.domain_name) for iv in rock], [
            (0.0, 3.0, "weathered"),
            (3.0, 8.0, "competent granite"),
            (8.0, 11.0, "fractured granite"),
        ])
        self.assertEqual(water, [])
        self.assertEqual(rock[1].properties.ucs_mpa, 140.0)
        self.assertEqual(rock[0].role, "designed")
        self.assertEqual(rock[0].provenance.method, "domain_intercept")

    def test_properties_at_uses_designed_intervals(self):
        hole = apply_domains_to_hole(
            _vertical(11.0),
            [_layer("D-w", "weathered", 0.0, -3.0, density_kg_m3=2200.0)],
        )
        props = properties_at(hole, 1.5)
        self.assertIsNotNone(props)
        self.assertEqual(props.density_kg_m3, 2200.0)
        self.assertIsNone(properties_at(hole, 6.0))


class PolygonInterceptTests(unittest.TestCase):
    def test_hole_outside_polygon_has_no_interval(self):
        hole = _vertical(11.0, x=20.0, y=20.0)
        domain = BlastDomain(
            id="D-a",
            name="west",
            polygon=[Point3(0, 0, 0), Point3(10, 0, 0), Point3(10, 10, 0), Point3(0, 10, 0)],
        )
        rock, _ = intercept_hole(hole, [domain])
        self.assertEqual(rock, [])

    def test_inclined_hole_clips_to_polygon(self):
        hole = Hole(
            id="inc",
            row=0,
            col=0,
            collar=Point3(x=-2.0, y=5.0, z=0.0),
            toe=Point3(x=12.0, y=5.0, z=-14.0),
            diameter_mm=152.0,
        )
        domain = BlastDomain(
            id="D-box",
            name="box",
            polygon=[Point3(0, 0, 0), Point3(10, 0, 0), Point3(10, 10, 0), Point3(0, 10, 0)],
        )
        rock, _ = intercept_hole(hole, [domain])
        self.assertEqual(len(rock), 1)
        start = hole.length_m * (2.0 / 14.0)
        end = hole.length_m * (12.0 / 14.0)
        self.assertAlmostEqual(rock[0].from_m, start, places=5)
        self.assertAlmostEqual(rock[0].to_m, end, places=5)


class PriorityAndWaterTests(unittest.TestCase):
    def test_higher_priority_wins_on_overlap(self):
        hole = _vertical(10.0)
        low = _layer("D-low", "background", 0.0, -10.0, blastability="low")
        low.priority = 0
        high = _layer("D-high", "lens", 0.0, -4.0, blastability="high")
        high.priority = 5
        rock, _ = intercept_hole(hole, [low, high])
        self.assertEqual(rock[0].domain_id, "D-high")
        self.assertAlmostEqual(rock[0].to_m, 4.0)
        self.assertEqual(rock[1].domain_id, "D-low")

    def test_later_equal_priority_overrides(self):
        hole = _vertical(6.0)
        first = _layer("D-a", "A", 0.0, -6.0)
        second = _layer("D-b", "B", 0.0, -6.0)
        rock, _ = intercept_hole(hole, [first, second])
        self.assertEqual(rock[0].domain_id, "D-b")

    def test_domain_water_and_water_table(self):
        hole = _vertical(11.0)
        wet_layer = _layer("D-w", "weathered", 0.0, -3.0, water_condition="moist")
        dry_layer = _layer("D-g", "granite", -3.0, -11.0)
        rock, water = intercept_hole(hole, [wet_layer, dry_layer], water_table_z_m=-8.0)
        self.assertEqual(len(rock), 2)
        by_cond = [(round(iv.from_m, 6), round(iv.to_m, 6), iv.condition) for iv in water]
        self.assertEqual(by_cond, [(0.0, 3.0, "moist"), (8.0, 11.0, "wet")])


class MeasuredIsolationTests(unittest.TestCase):
    def test_apply_does_not_touch_measured_intervals(self):
        measured = HoleInterval(from_m=0.0, to_m=2.0, domain_name="core", role="measured")
        measured_water = WaterInterval(from_m=9.0, to_m=11.0, condition="flowing", role="measured")
        hole = _vertical(11.0)
        hole.measured_intervals = [measured]
        hole.measured_water_intervals = [measured_water]
        hole.intervals = [HoleInterval(from_m=0.0, to_m=11.0, domain_name="stale")]
        updated = apply_domains_to_hole(hole, [_layer("D-w", "weathered", 0.0, -3.0)])
        self.assertEqual(updated.measured_intervals, [measured])
        self.assertEqual(updated.measured_water_intervals, [measured_water])
        self.assertEqual(updated.intervals[0].domain_name, "weathered")
        self.assertNotEqual(updated.intervals[0].domain_name, "stale")

    def test_charging_hook_ignores_measured(self):
        hole = _vertical(11.0)
        hole.intervals = [HoleInterval(from_m=0.0, to_m=3.0, domain_name="designed", role="designed")]
        hole.measured_intervals = [
            HoleInterval(from_m=0.0, to_m=11.0, domain_name="measured", role="measured")
        ]
        designed = hole_geology_for_charging(hole)
        self.assertEqual([iv.domain_name for iv in designed], ["designed"])
        props = rock_properties_for_charging(hole, 1.0)
        self.assertIsNotNone(props)


class AssignPolygonTests(unittest.TestCase):
    def test_assign_copies_polygon(self):
        domain = BlastDomain(id="D-1", name="unit")
        polygon = [Point3(0, 0, 0), Point3(4, 0, 0), Point3(4, 4, 0), Point3(0, 4, 0)]
        assigned = assign_domain_polygon(domain, polygon)
        self.assertEqual(len(assigned.polygon), 4)
        self.assertEqual(domain.polygon, [])

    def test_two_points_rejected(self):
        domain = BlastDomain(id="D-1", name="unit")
        with self.assertRaises(ValueError):
            assign_domain_polygon(domain, [Point3(0, 0, 0), Point3(1, 0, 0)])

    def test_empty_polygon_means_whole_plan(self):
        assigned = assign_domain_polygon(BlastDomain(id="D-1", name="layer"), [])
        hole = _vertical(5.0, x=100.0, y=100.0)
        rock, _ = intercept_hole(hole, [assigned])
        self.assertEqual(len(rock), 1)
        self.assertAlmostEqual(rock[0].to_m, 5.0)

    def test_batch_apply_keeps_hole_ids(self):
        holes = [_vertical(11.0, x=1.0), _vertical(11.0, x=2.0)]
        holes[1].id = "1-02"
        updated = apply_domains_to_holes(holes, [_layer("D-w", "weathered", 0.0, -3.0)])
        self.assertEqual([h.id for h in updated], ["1-01", "1-02"])
        self.assertTrue(all(h.intervals for h in updated))


if __name__ == "__main__":
    unittest.main()
