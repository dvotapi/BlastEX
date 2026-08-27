import unittest

from design.as_charged import record_as_charged
from design.as_drilled import record_as_drilled
from design.as_fired import record_as_fired
from design.execution import compare_execution
from design.models import (
    AsChargedHole,
    AsDrilledHole,
    AsFiredHole,
    BlastDesign,
    Deck,
    Detonator,
    Hole,
    HoleLoad,
    Point3,
)


class ExecutionCompareTests(unittest.TestCase):
    def test_combined_report_keeps_designed_data(self):
        hole = Hole(
            id="1-01",
            row=1,
            col=1,
            collar=Point3(x=0, y=0, z=0),
            toe=Point3(x=0, y=0, z=-10),
            diameter_mm=152.0,
        )
        design = BlastDesign(
            design_id="ex",
            holes=[hole],
            loads=[
                HoleLoad(
                    hole_id="1-01",
                    decks=[
                        Deck(kind="stemming", from_m=0, to_m=3),
                        Deck(kind="bulk_explosive", from_m=3, to_m=10, mass_kg=70, product="ANFO"),
                    ],
                    total_charge_kg=70.0,
                )
            ],
        )
        design.network.electronic_times_ms = {"1-01": 20.0}
        design.network.detonators = [Detonator(id="det-1", hole_id="1-01", product="i-kon")]
        record_as_drilled(
            design,
            AsDrilledHole(
                design_hole_id="1-01",
                actual_collar=Point3(x=0.4, y=0.0, z=0.0),
                actual_toe=Point3(x=0.4, y=0.0, z=-10.0),
                actual_depth=10.0,
                actual_diameter=152.0,
            ),
        )
        record_as_charged(
            design,
            AsChargedHole(design_hole_id="1-01", charge_mass_kg=72.0, explosive_product="ANFO", stemming_length_m=3.0),
        )
        record_as_fired(
            design,
            AsFiredHole(design_hole_id="1-01", programmed_time_ms=22.0, verified_time_ms=22.5),
        )
        holes_before = [item.to_dict() for item in design.holes]
        loads_before = [item.to_dict() for item in design.loads]
        detonators_before = [item.to_dict() for item in design.network.detonators]
        payload = compare_execution(design)
        self.assertEqual(payload["design_vs_drilled"]["compared_count"], 1)
        self.assertEqual(payload["design_vs_charged"]["compared_count"], 1)
        self.assertEqual(payload["design_vs_fired"]["compared_count"], 1)
        self.assertEqual(payload["as_drilled_count"], 1)
        self.assertEqual(payload["as_charged_count"], 1)
        self.assertEqual(payload["as_fired_count"], 1)
        self.assertGreater(payload["design_vs_drilled"]["deviations"][0]["collar_offset_m"], 0.0)
        self.assertAlmostEqual(payload["design_vs_charged"]["deviations"][0]["charge_mass_delta_kg"], 2.0)
        self.assertAlmostEqual(payload["design_vs_fired"]["deviations"][0]["programmed_time_delta_ms"], 2.0)
        self.assertEqual([item.to_dict() for item in design.holes], holes_before)
        self.assertEqual([item.to_dict() for item in design.loads], loads_before)
        self.assertEqual([item.to_dict() for item in design.network.detonators], detonators_before)


if __name__ == "__main__":
    unittest.main()
