"""Movement / heave estimate: predicted overlay, no design rewrite."""
import copy
import unittest

from design.charging import apply_charge_rules
from design.models import (
    ROLE_MEASURED,
    ROLE_PREDICTED,
    BenchSurface,
    BlastDesign,
    BlockContour,
    InitiationNetwork,
    Point3,
)
from design.pattern import generate_pattern
from design.timing import build_template_network
from Blast import ExplosiveProperties
from simulation.movement.engine import predict_design
from simulation.movement.kinematics import estimate_heave_m, estimate_throw_m
from simulation.movement.maps import MOVEMENT_MAP_METRICS
from simulation.movement.models import (
    DISCLAIMER,
    KIND_ESTIMATE,
    MeasuredMuckpileEcho,
    MovementInputs,
)


def _contour() -> BlockContour:
    return BlockContour(
        vertices=[Point3(x=x, y=y, z=0.0) for x, y in [(0, 0), (24, 0), (24, 16), (0, 16)]],
        free_faces=[[0, 1]],
        bench=BenchSurface(crest_z_m=0.0, toe_z_m=-10.0),
    )


def _design_with_charges(*, q_scale: float = 1.0) -> BlastDesign:
    contour = _contour()
    holes = generate_pattern(
        contour,
        {
            "pattern": "rectangular",
            "spacing_a_m": 5.0,
            "burden_b_m": 4.0,
            "offset_from_face_m": 0.0,
            "edge_margin_m": 0.0,
            "diameter_mm": 152.0,
            "subdrill_m": 1.0,
        },
    )
    explosive = ExplosiveProperties("АНФО", 0.82, 3.8)
    loads = apply_charge_rules(
        holes,
        {"stemming_m": 3.0, "decking": "continuous", "grid_a_m": 5.0, "grid_b_m": 4.0},
        explosive,
        contour=contour,
    )
    if q_scale != 1.0:
        for load in loads:
            load.total_charge_kg *= q_scale
            load.specific_q_kg_m3 *= q_scale
    network = build_template_network(
        holes,
        "row",
        {"system": "nonel", "interval_ms": 25.0, "downhole_delay_ms": 500.0},
    )
    return BlastDesign(
        design_id="heave",
        contour=contour,
        holes=holes,
        loads=loads,
        network=network,
        pattern_params={"spacing_a_m": 5.0, "burden_b_m": 4.0},
        charge_rules={"stemming_m": 3.0, "grid_a_m": 5.0, "grid_b_m": 4.0},
        explosive_key="АНФО",
    )


def _snapshot(design: BlastDesign) -> dict:
    return {
        "holes": [hole.to_dict() for hole in design.holes],
        "loads": [load.to_dict() for load in design.loads],
        "pattern": copy.deepcopy(design.pattern_params),
        "network": design.network.to_dict(),
        "events": [item.to_dict() for item in design.network.firing_events],
    }


class MovementEngineTests(unittest.TestCase):
    def test_predicts_site_holes_and_maps(self):
        design = _design_with_charges()
        result = predict_design(design)
        self.assertEqual(result["model"], "kinematic_heave")
        self.assertTrue(result["model_version"])
        self.assertEqual(result["role"], ROLE_PREDICTED)
        self.assertEqual(result["kind"], KIND_ESTIMATE)
        self.assertFalse(result["is_physics_simulation"])
        self.assertFalse(result["design_rewritten"])
        self.assertIn("оценка", result["disclaimer"].lower())
        self.assertIn("estimate", result["disclaimer"].lower())
        self.assertNotIn("simulation of physics", result["disclaimer"].lower())
        self.assertEqual(result["muckpile"]["role"], ROLE_PREDICTED)
        self.assertGreater(result["muckpile"]["throw_m"], 0.0)
        self.assertGreater(result["muckpile"]["heave_m"], 0.0)
        self.assertGreater(result["muckpile"]["swell_factor"], 1.0)
        self.assertGreater(result["muckpile"]["volume_m3"], result["muckpile"]["in_situ_volume_m3"])
        bench = result["holes"][0]["inputs"]["bench_height_m"]
        self.assertLess(result["muckpile"]["height_m"], bench * result["muckpile"]["swell_factor"] + 2.0)
        self.assertGreater(result["muckpile"]["height_m"], bench)
        self.assertEqual(len(result["holes"]), len([h for h in design.holes if h.enabled]))
        self.assertTrue(all(row["role"] == ROLE_PREDICTED for row in result["holes"]))
        self.assertEqual(list(result["maps"]["metrics"]), list(MOVEMENT_MAP_METRICS))
        self.assertEqual(result["maps"]["role"], ROLE_PREDICTED)
        sample = next(row for row in result["holes"] if row["inputs"]["charge_mass_kg"] > 0)
        self.assertAlmostEqual(sample["inputs"]["diameter_m"], 0.152)
        self.assertEqual(sample["inputs"]["diameter_mm"], 152.0)
        self.assertNotAlmostEqual(sample["inputs"]["diameter_m"], sample["inputs"]["diameter_mm"])
        self.assertGreater(sample["throw_m"], 0.0)
        self.assertGreater(sample["heave_m"], 0.0)
        charged = [row for row in result["holes"] if row["inputs"]["charge_mass_kg"] > 0]
        self.assertGreater(len(charged), 0)
        self.assertTrue(all(row["throw_m"] > 0 for row in charged))

    def test_does_not_rewrite_designed_pattern(self):
        design = _design_with_charges()
        before = _snapshot(design)
        firing_before = list(design.network.firing_events)
        predict_design(design)
        after = _snapshot(design)
        self.assertEqual(before["holes"], after["holes"])
        self.assertEqual(before["loads"], after["loads"])
        self.assertEqual(before["pattern"], after["pattern"])
        self.assertEqual(before["network"], after["network"])
        self.assertEqual(firing_before, design.network.firing_events)
        self.assertEqual(before["events"], after["events"])

    def test_higher_powder_factor_increases_throw_and_heave(self):
        low = predict_design(_design_with_charges(q_scale=0.7))
        high = predict_design(_design_with_charges(q_scale=1.6))
        self.assertGreater(high["muckpile"]["throw_m"], low["muckpile"]["throw_m"])
        self.assertGreater(high["muckpile"]["heave_m"], low["muckpile"]["heave_m"])
        self.assertGreater(high["muckpile"]["swell_factor"], low["muckpile"]["swell_factor"])

    def test_front_row_throws_farther_than_back_row(self):
        result = predict_design(_design_with_charges())
        by_row: dict[int, list[float]] = {}
        for row in result["holes"]:
            by_row.setdefault(int(row["inputs"]["row"]), []).append(row["throw_m"])
        self.assertIn(0, by_row)
        self.assertGreater(len(by_row), 1)
        front = sum(by_row[0]) / len(by_row[0])
        back_row = max(by_row)
        back = sum(by_row[back_row]) / len(by_row[back_row])
        self.assertGreater(front, back)

    def test_measured_is_echoed_never_overwritten(self):
        design = _design_with_charges()
        measured = MeasuredMuckpileEcho(length_m=90.0, throw_m=40.0, notes="survey")
        result = predict_design(design, measured=[measured])
        self.assertEqual(result["measured"][0]["role"], ROLE_MEASURED)
        self.assertEqual(result["measured"][0]["throw_m"], 40.0)
        self.assertNotAlmostEqual(result["muckpile"]["throw_m"], 40.0)
        self.assertEqual(result["muckpile"]["role"], ROLE_PREDICTED)

    def test_heave_decreases_with_longer_stemming(self):
        short = MovementInputs(
            burden_m=4.0,
            spacing_m=5.0,
            bench_height_m=10.0,
            diameter_mm=152.0,
            diameter_m=0.152,
            charge_mass_kg=80.0,
            powder_factor_kg_m3=0.6,
            stemming_m=2.0,
            influence_volume_m3=200.0,
            face_distance_m=4.0,
            row=0,
        )
        long = MovementInputs(**{**short.to_dict(), "stemming_m": 5.0})
        self.assertGreater(estimate_heave_m(short), estimate_heave_m(long))
        self.assertGreater(estimate_throw_m(short), estimate_throw_m(long))

    def test_disclaimer_is_on_every_layer(self):
        result = predict_design(_design_with_charges())
        self.assertEqual(result["muckpile"]["kind"], KIND_ESTIMATE)
        self.assertEqual(result["holes"][0]["kind"], KIND_ESTIMATE)
        self.assertIn("оценка", result["muckpile"]["disclaimer"])
        self.assertIn(DISCLAIMER[:20], result["muckpile"]["notes"])

    def test_empty_network_still_estimates_from_face(self):
        design = _design_with_charges()
        design.network = InitiationNetwork()
        result = predict_design(design)
        self.assertEqual(result["role"], ROLE_PREDICTED)
        self.assertGreater(result["muckpile"]["throw_m"], 0.0)
        self.assertGreater(len(result["holes"]), 0)


if __name__ == "__main__":
    unittest.main()
