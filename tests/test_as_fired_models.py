import unittest

from design.as_fired import as_fired_from_design_hole, normalize_as_fired, record_as_fired
from design.models import (
    DESIGN_VERSION,
    ROLE_EXECUTED,
    AsFiredHole,
    BlastDesign,
    Detonator,
    Hole,
    Point3,
)


def _hole(hole_id: str = "1-01") -> Hole:
    return Hole(
        id=hole_id,
        row=1,
        col=1,
        collar=Point3(x=0.0, y=0.0, z=0.0),
        toe=Point3(x=0.0, y=0.0, z=-10.0),
        diameter_mm=152.0,
    )


def _design() -> BlastDesign:
    design = BlastDesign(design_id="af", holes=[_hole()])
    design.network.system = "electronic"
    design.network.detonators = [Detonator(id="det-1", hole_id="1-01", product="i-kon", kind="electronic")]
    design.network.electronic_times_ms = {"1-01": 42.0}
    design.network.electronic_channels = []
    return design


class AsFiredModelTests(unittest.TestCase):
    def test_round_trip_forces_executed_role(self):
        item = AsFiredHole(
            design_hole_id="1-01",
            detonator=Detonator(id="det-a", hole_id="1-01", product="DaveyTronic", kind="electronic"),
            programmed_time_ms=45.0,
            verified_time_ms=45.2,
            firing_timestamp="2026-08-23T14:00:00+00:00",
        )
        restored = AsFiredHole.from_dict(item.to_dict())
        self.assertEqual(restored.role, ROLE_EXECUTED)
        self.assertEqual(restored.provenance.role, ROLE_EXECUTED)
        self.assertEqual(restored.detonator.product, "DaveyTronic")
        self.assertAlmostEqual(restored.programmed_time_ms, 45.0)
        self.assertAlmostEqual(restored.verified_time_ms or 0.0, 45.2)

    def test_from_dict_accepts_flat_detonator_fields(self):
        item = AsFiredHole.from_dict(
            {
                "design_hole_id": "1-01",
                "detonator_id": "det-flat",
                "detonator_product": "NPED",
                "detonator_kind": "nonel",
                "programmed_time_ms": 17,
            }
        )
        normalized = normalize_as_fired(item)
        self.assertEqual(normalized.detonator.id, "det-flat")
        self.assertEqual(normalized.detonator.product, "NPED")
        self.assertEqual(normalized.detonator.kind, "nonel")
        self.assertEqual(normalized.detonator.hole_id, "1-01")

    def test_design_version_includes_as_fired(self):
        design = BlastDesign(design_id="af")
        payload = design.to_dict()
        self.assertEqual(payload["as_fired_holes"], [])
        self.assertEqual(DESIGN_VERSION, 9)

    def test_record_does_not_overwrite_designed_network(self):
        design = _design()
        network_before = design.network.to_dict()
        hole_before = design.holes[0].to_dict()
        recorded = record_as_fired(
            design,
            AsFiredHole(
                design_hole_id="1-01",
                detonator=Detonator(id="det-a", hole_id="1-01", product="DaveyTronic"),
                programmed_time_ms=50.0,
                verified_time_ms=50.5,
            ),
        )
        self.assertEqual(recorded.role, ROLE_EXECUTED)
        self.assertEqual(design.network.detonators[0].product, "i-kon")
        self.assertAlmostEqual(design.network.electronic_times_ms["1-01"], 42.0)
        self.assertEqual(design.holes[0].to_dict(), hole_before)
        self.assertEqual(design.network.detonators[0].to_dict(), Detonator.from_dict(network_before["detonators"][0]).to_dict())
        self.assertAlmostEqual(design.as_fired_holes[0].programmed_time_ms, 50.0)
        self.assertTrue(design.as_fired_holes[0].firing_timestamp)

    def test_stub_from_design_does_not_mutate_network(self):
        design = _design()
        before = design.network.to_dict()
        stub = as_fired_from_design_hole(design, design.holes[0])
        self.assertAlmostEqual(stub.programmed_time_ms, 42.0)
        self.assertEqual(stub.detonator.product, "i-kon")
        self.assertEqual(design.network.to_dict(), before)

    def test_record_unknown_hole_is_rejected(self):
        design = _design()
        with self.assertRaises(ValueError):
            record_as_fired(design, AsFiredHole(design_hole_id="missing", programmed_time_ms=1.0))
        self.assertEqual(design.as_fired_holes, [])
        self.assertEqual(design.network.detonators[0].product, "i-kon")


if __name__ == "__main__":
    unittest.main()
