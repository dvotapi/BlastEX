"""Roles on the movement overlay cannot be rewritten to designed or measured."""
import unittest

from design.models import ROLE_DESIGNED, ROLE_MEASURED, ROLE_PREDICTED
from simulation.movement.models import (
    DISCLAIMER,
    IS_PHYSICS_SIMULATION,
    KIND_ESTIMATE,
    LABEL_EN,
    LABEL_RU,
    MeasuredMuckpileEcho,
    MovementInputs,
    PredictedHoleMovement,
    PredictedMuckpile,
    estimate_kind_payload,
)


def _inputs() -> MovementInputs:
    return MovementInputs(
        burden_m=4.0,
        spacing_m=5.0,
        bench_height_m=10.0,
        diameter_mm=152.0,
        diameter_m=0.152,
        charge_mass_kg=80.0,
        powder_factor_kg_m3=0.6,
        stemming_m=3.0,
        influence_volume_m3=200.0,
        face_distance_m=4.0,
        fire_time_ms=25.0,
        row=0,
    )


class MovementModelTests(unittest.TestCase):
    def test_predicted_muckpile_role_stays_predicted(self):
        pile = PredictedMuckpile.from_dict(
            {
                "length_m": 40,
                "width_m": 18,
                "height_m": 8,
                "volume_m3": 2500,
                "throw_m": 6,
                "role": "measured",
            }
        )
        self.assertEqual(pile.role, ROLE_PREDICTED)
        self.assertEqual(pile.to_dict()["role"], ROLE_PREDICTED)
        self.assertNotEqual(pile.role, ROLE_DESIGNED)
        self.assertNotEqual(pile.role, ROLE_MEASURED)

    def test_hole_movement_role_stays_predicted(self):
        item = PredictedHoleMovement.from_dict(
            {
                "hole_id": "H-1",
                "throw_m": 5.0,
                "heave_m": 1.2,
                "inputs": _inputs().to_dict(),
                "role": "designed",
            }
        )
        self.assertEqual(item.role, ROLE_PREDICTED)
        self.assertEqual(item.to_dict()["role"], ROLE_PREDICTED)

    def test_measured_echo_role_stays_measured(self):
        echo = MeasuredMuckpileEcho.from_dict({"length_m": 44, "throw_m": 9, "role": "predicted"})
        self.assertEqual(echo.role, ROLE_MEASURED)
        self.assertEqual(echo.to_dict()["role"], ROLE_MEASURED)

    def test_payload_is_labelled_estimate_not_physics(self):
        payload = estimate_kind_payload()
        self.assertEqual(payload["kind"], KIND_ESTIMATE)
        self.assertEqual(payload["label_ru"], LABEL_RU)
        self.assertEqual(payload["label_en"], LABEL_EN)
        self.assertFalse(payload["is_physics_simulation"])
        self.assertFalse(IS_PHYSICS_SIMULATION)
        self.assertIn("оценка", payload["disclaimer"].lower())
        self.assertIn("estimate", payload["disclaimer"].lower())
        self.assertNotIn("simulation of physics", payload["disclaimer"].lower())
        self.assertIn("оценка", DISCLAIMER.lower())
        pile = PredictedMuckpile(
            length_m=30,
            width_m=16,
            height_m=7,
            volume_m3=2000,
            throw_m=5,
            heave_m=1.1,
            swell_factor=1.35,
            in_situ_volume_m3=1500,
            centroid_x=10,
            centroid_y=8,
        )
        dumped = pile.to_dict()
        self.assertEqual(dumped["kind"], KIND_ESTIMATE)
        self.assertFalse(dumped["is_physics_simulation"])
        self.assertIn("оценка", dumped["disclaimer"])


if __name__ == "__main__":
    unittest.main()
