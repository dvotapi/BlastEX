import unittest

from design.models import (
    DESIGN_VERSION,
    ROLE_MEASURED,
    ROLE_PREDICTED,
    BlastDesign,
    Point3,
    Receptor,
    VibrationMeasurement,
    VibrationModel,
    default_vibration_model,
)
from design.vibration import (
    CONVENTION_Q_CUBE_OVER_R,
    CONVENTION_R_OVER_Q_SQRT,
    SCALED_DISTANCE_CONVENTIONS,
    ScaledDistanceMismatchError,
    attach_measurement,
    attach_receptor,
    normalize_convention,
    predict_ppv,
    require_same_convention,
    scaled_distance,
)


class ReceptorModelTests(unittest.TestCase):
    def test_round_trip_and_kind_aliases(self):
        receptor = Receptor(
            id="R-1",
            name="Насосная",
            kind="pipeline",
            location=Point3(x=40.0, y=-8.0, z=2.0),
            ppv_limit_mm_s=15.0,
            notes="магистраль",
        )
        restored = Receptor.from_dict(receptor.to_dict())
        self.assertEqual(restored.kind, "pipeline")
        self.assertAlmostEqual(restored.location.x, 40.0)
        self.assertAlmostEqual(restored.ppv_limit_mm_s or 0.0, 15.0)
        self.assertEqual(Receptor.from_dict({"id": "R-2", "kind": "ЛЭП"}).kind, "power_line")
        self.assertEqual(Receptor.from_dict({"id": "R-3", "kind": "сейсмопост"}).kind, "monitoring_station")

    def test_attach_upserts_and_assigns_id(self):
        design = BlastDesign(design_id="d")
        first = attach_receptor(design, Receptor(id="", name="Офис", kind="building", location=Point3(x=1, y=2, z=0)))
        self.assertEqual(first.id, "R-1")
        self.assertEqual(len(design.receptors), 1)
        first.name = "Офис блока"
        attach_receptor(design, first)
        self.assertEqual(len(design.receptors), 1)
        self.assertEqual(design.receptors[0].name, "Офис блока")


class VibrationModelTests(unittest.TestCase):
    def test_stores_law_and_convention(self):
        model = VibrationModel(
            id="vm-1",
            k=1140.0,
            n=-1.6,
            scaled_distance="usbm",
            calibration_source="USBM RI 8507",
            confidence=1.4,
        )
        payload = model.to_dict()
        self.assertEqual(payload["scaled_distance"], CONVENTION_R_OVER_Q_SQRT)
        self.assertEqual(payload["confidence"], 1.0)
        restored = VibrationModel.from_dict(payload)
        self.assertAlmostEqual(restored.k, 1140.0)
        self.assertEqual(restored.calibration_source, "USBM RI 8507")

    def test_default_model_is_explicit_cube_root_q_over_r(self):
        model = default_vibration_model()
        self.assertEqual(model.scaled_distance, CONVENTION_Q_CUBE_OVER_R)
        self.assertIn(model.scaled_distance, SCALED_DISTANCE_CONVENTIONS)

    def test_design_version_includes_vibration(self):
        design = BlastDesign(design_id="v")
        payload = design.to_dict()
        self.assertEqual(payload["version"], DESIGN_VERSION)
        self.assertEqual(payload["receptors"], [])
        self.assertEqual(payload["vibration_measurements"], [])


class ScaledDistanceConventionTests(unittest.TestCase):
    def test_four_conventions_are_not_equal(self):
        values = [scaled_distance(125.0, 50.0, key) for key in SCALED_DISTANCE_CONVENTIONS]
        self.assertEqual(len(set(round(v, 8) for v in values)), 4)

    def test_unknown_convention_is_rejected(self):
        with self.assertRaises(ValueError):
            normalize_convention("mix_them")

    def test_mismatch_is_not_silent(self):
        with self.assertRaises(ScaledDistanceMismatchError) as ctx:
            require_same_convention(CONVENTION_Q_CUBE_OVER_R, CONVENTION_R_OVER_Q_SQRT, context="калибровка")
        self.assertIn("Нельзя смешивать", str(ctx.exception))
        self.assertEqual(
            require_same_convention("cube_root", CONVENTION_Q_CUBE_OVER_R, context="ok"),
            CONVENTION_Q_CUBE_OVER_R,
        )


class SiteLawTests(unittest.TestCase):
    def test_ppv_is_k_times_sd_n(self):
        model = VibrationModel(id="m", k=200.0, n=1.6, scaled_distance=CONVENTION_Q_CUBE_OVER_R)
        mic, distance = 100.0, 50.0
        sd = scaled_distance(mic, distance, model.scaled_distance)
        self.assertAlmostEqual(predict_ppv(mic, distance, model), 200.0 * sd**1.6, places=6)

    def test_same_k_n_differ_across_conventions(self):
        cube = VibrationModel(id="c", k=200.0, n=1.6, scaled_distance=CONVENTION_Q_CUBE_OVER_R)
        square = VibrationModel(id="s", k=200.0, n=1.6, scaled_distance=CONVENTION_R_OVER_Q_SQRT)
        self.assertNotAlmostEqual(predict_ppv(100.0, 50.0, cube), predict_ppv(100.0, 50.0, square))

    def test_zero_inputs_are_zero(self):
        model = default_vibration_model()
        self.assertEqual(predict_ppv(0.0, 50.0, model), 0.0)
        self.assertEqual(predict_ppv(100.0, 0.0, model), 0.0)


class VibrationMeasurementTests(unittest.TestCase):
    def test_role_is_always_measured(self):
        item = VibrationMeasurement.from_dict(
            {"id": "VM-1", "receptor_id": "R-1", "ppv_mm_s": 4.5, "role": ROLE_PREDICTED}
        )
        self.assertEqual(item.role, ROLE_MEASURED)
        self.assertEqual(item.to_dict()["role"], ROLE_MEASURED)

    def test_attach_requires_existing_receptor(self):
        design = BlastDesign(design_id="d")
        with self.assertRaises(ValueError):
            attach_measurement(design, VibrationMeasurement(id="VM-1", receptor_id="R-9", ppv_mm_s=2.0))
        attach_receptor(design, Receptor(id="R-9", name="пост", kind="monitoring_station"))
        stored = attach_measurement(
            design,
            VibrationMeasurement(id="", receptor_id="R-9", ppv_mm_s=2.0, scaled_distance="usbm"),
        )
        self.assertEqual(stored.id, "VM-1")
        self.assertEqual(stored.scaled_distance, CONVENTION_R_OVER_Q_SQRT)


if __name__ == "__main__":
    unittest.main()
