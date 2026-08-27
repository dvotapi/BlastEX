import unittest

from design.as_drilled import attach_mwd, mwd_import_schema, parse_mwd_sample, parse_mwd_samples
from design.models import BlastDesign, Hole, MwdSample, Point3


def _hole() -> Hole:
    return Hole(
        id="1-01",
        row=1,
        col=1,
        collar=Point3(x=1.0, y=2.0, z=0.0),
        toe=Point3(x=1.0, y=2.0, z=-10.0),
        diameter_mm=152.0,
    )


class MwdSchemaTests(unittest.TestCase):
    def test_schema_is_manufacturer_neutral(self):
        schema = mwd_import_schema()
        self.assertIsNone(schema["manufacturer"])
        self.assertIsNone(schema["vendor_format"])
        ids = [field["id"] for field in schema["fields"]]
        self.assertEqual(
            ids,
            [
                "depth_m",
                "penetration_rate",
                "rotation_pressure",
                "feed_pressure",
                "torque",
                "air_pressure",
            ],
        )
        blob = str(schema).lower()
        for vendor in ("atlas", "sandvik", "epiroc", "smartroc", "flexiroc", "leopard"):
            self.assertNotIn(vendor, blob)

    def test_aliases_map_to_physical_fields(self):
        sample = parse_mwd_sample(
            {
                "depth": 4.5,
                "rop": 1.1,
                "rotary_pressure": 130,
                "pulldown": 80,
                "torque_nm": 2000,
                "flushing_pressure": 16,
                "vendor_channel": 99,
                "smartroc_bit_id": "ignore-me",
            }
        )
        self.assertAlmostEqual(sample.depth_m, 4.5)
        self.assertAlmostEqual(sample.penetration_rate or 0.0, 1.1)
        self.assertAlmostEqual(sample.rotation_pressure or 0.0, 130)
        self.assertAlmostEqual(sample.feed_pressure or 0.0, 80)
        self.assertAlmostEqual(sample.torque or 0.0, 2000)
        self.assertAlmostEqual(sample.air_pressure or 0.0, 16)
        self.assertEqual(set(sample.to_dict()), {
            "depth_m",
            "penetration_rate",
            "rotation_pressure",
            "feed_pressure",
            "torque",
            "air_pressure",
        })

    def test_attach_mwd_does_not_rewrite_designed_geometry(self):
        design = BlastDesign(design_id="mwd", holes=[_hole()])
        before = design.holes[0].to_dict()
        samples = parse_mwd_samples(
            [
                {"depth_m": 0.0, "penetration_rate": 0.8},
                {"depth_m": 5.0, "penetration_rate": 1.3, "torque": 1900},
            ]
        )
        attached = attach_mwd(design, "1-01", samples, source="json")
        self.assertEqual(design.holes[0].to_dict(), before)
        self.assertEqual(attached.role, "executed")
        self.assertEqual(len(attached.mwd_samples), 2)
        self.assertAlmostEqual(design.holes[0].collar.x, 1.0)
        self.assertAlmostEqual(design.holes[0].diameter_mm, 152.0)

    def test_canonical_sample_round_trip(self):
        sample = MwdSample(
            depth_m=7.0,
            penetration_rate=1.0,
            rotation_pressure=120.0,
            feed_pressure=70.0,
            torque=1500.0,
            air_pressure=15.0,
        )
        restored = MwdSample.from_dict(sample.to_dict())
        self.assertEqual(restored.to_dict(), sample.to_dict())


if __name__ == "__main__":
    unittest.main()
