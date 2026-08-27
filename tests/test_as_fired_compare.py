import unittest

from design.as_fired import compare_design, record_as_fired
from design.models import AsFiredHole, BlastDesign, Detonator, Hole, Point3, Starter


def _hole(hole_id: str, row: int = 1, col: int = 1, x: float = 0.0) -> Hole:
    return Hole(
        id=hole_id,
        row=row,
        col=col,
        collar=Point3(x=x, y=0.0, z=0.0),
        toe=Point3(x=x, y=0.0, z=-10.0),
        diameter_mm=152.0,
    )


class AsFiredCompareTests(unittest.TestCase):
    def test_zero_deviation_when_programmed_matches_design(self):
        design = BlastDesign(design_id="cmp", holes=[_hole("1-01")])
        design.network.system = "electronic"
        design.network.detonators = [Detonator(id="det-1", hole_id="1-01", product="i-kon", kind="electronic")]
        design.network.electronic_times_ms = {"1-01": 25.0}
        record_as_fired(
            design,
            AsFiredHole(
                design_hole_id="1-01",
                detonator=Detonator(id="det-1", hole_id="1-01", product="i-kon", kind="electronic"),
                programmed_time_ms=25.0,
                verified_time_ms=25.0,
            ),
        )
        row = compare_design(design)["deviations"][0]
        self.assertAlmostEqual(row["programmed_time_delta_ms"], 0.0)
        self.assertAlmostEqual(row["verified_time_delta_ms"], 0.0)
        self.assertAlmostEqual(row["timing_error_ms"], 0.0)
        self.assertFalse(row["detonator_product_mismatch"])
        self.assertFalse(row["detonator_kind_mismatch"])

    def test_programmed_verified_and_detonator_mismatch(self):
        design = BlastDesign(design_id="cmp", holes=[_hole("1-01")])
        design.network.system = "electronic"
        design.network.detonators = [Detonator(id="det-1", hole_id="1-01", product="i-kon", kind="electronic")]
        design.network.electronic_times_ms = {"1-01": 40.0}
        record_as_fired(
            design,
            AsFiredHole(
                design_hole_id="1-01",
                detonator=Detonator(id="det-a", hole_id="1-01", product="NPED", kind="nonel"),
                programmed_time_ms=47.0,
                verified_time_ms=49.0,
            ),
        )
        row = compare_design(design)["deviations"][0]
        self.assertAlmostEqual(row["programmed_time_delta_ms"], 7.0)
        self.assertAlmostEqual(row["verified_time_delta_ms"], 9.0)
        self.assertAlmostEqual(row["timing_error_ms"], 2.0)
        self.assertTrue(row["detonator_product_mismatch"])
        self.assertTrue(row["detonator_kind_mismatch"])

    def test_nonel_uses_resolved_network_time(self):
        holes = [_hole("1-01", 1, 1, 0.0), _hole("1-02", 1, 2, 5.0)]
        design = BlastDesign(design_id="cmp", holes=holes)
        design.network.system = "nonel"
        design.network.starter_items = [Starter(id="st-1", hole_id="1-01")]
        design.network.starters = ["1-01"]
        design.network.downhole_delay_ms = {"1-01": 0.0, "1-02": 17.0}
        design.network.connectors = []
        from design.models import SurfaceConnector

        design.network.surface_connectors = [
            SurfaceConnector(id="sc-1", from_hole="1-01", to_hole="1-02", delay_ms=25.0)
        ]
        record_as_fired(
            design,
            AsFiredHole(design_hole_id="1-02", programmed_time_ms=50.0, verified_time_ms=51.0),
        )
        row = compare_design(design)["deviations"][0]
        self.assertGreater(row["designed_time_ms"], 0.0)
        self.assertAlmostEqual(row["programmed_time_delta_ms"], 50.0 - row["designed_time_ms"], places=3)

    def test_compare_does_not_mutate_designed_network(self):
        design = BlastDesign(design_id="cmp", holes=[_hole("1-01")])
        design.network.electronic_times_ms = {"1-01": 10.0}
        design.network.detonators = [Detonator(id="det-1", hole_id="1-01", product="i-kon")]
        record_as_fired(
            design,
            AsFiredHole(design_hole_id="1-01", programmed_time_ms=12.0, verified_time_ms=12.5),
        )
        before_net = (
            [item.to_dict() for item in design.network.detonators],
            dict(design.network.electronic_times_ms),
            [item.to_dict() for item in design.network.firing_events],
        )
        compare_design(design)
        after_net = (
            [item.to_dict() for item in design.network.detonators],
            dict(design.network.electronic_times_ms),
            [item.to_dict() for item in design.network.firing_events],
        )
        self.assertEqual(after_net, before_net)


if __name__ == "__main__":
    unittest.main()
