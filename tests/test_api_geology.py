import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from api.exceptions import InvalidGeometryError
from api.schemas.design import (
    BlastDesignSchema,
    GeologyAssignRequest,
    GeologyInterceptRequest,
)
from api.services import design_service
from design.models import BlastDesign, Hole, Point3
from design.persistence import load_design, save_design


def _hole_payload(x: float = 5.0, y: float = 5.0, depth: float = 11.0) -> dict:
    return {
        "id": "1-01",
        "row": 0,
        "col": 0,
        "collar": {"x": x, "y": y, "z": 0.0},
        "toe": {"x": x, "y": y, "z": -depth},
        "diameter_mm": 152.0,
        "subdrill_m": 1.0,
    }


def _layer_payload(domain_id: str, name: str, z_top: float, z_bottom: float, **props) -> dict:
    return {
        "id": domain_id,
        "name": name,
        "polygon": [],
        "properties": props,
        "z_top_m": z_top,
        "z_bottom_m": z_bottom,
    }


class GeologyAssignApiTests(unittest.TestCase):
    def test_assign_attaches_polygon(self):
        result = design_service.assign_domain(
            GeologyAssignRequest(
                domain={"id": "D-1", "name": "гранит"},
                polygon=[{"x": 0, "y": 0, "z": 0}, {"x": 8, "y": 0, "z": 0}, {"x": 8, "y": 8, "z": 0}, {"x": 0, "y": 8, "z": 0}],
            )
        )
        self.assertEqual(result.domain.id, "D-1")
        self.assertEqual(len(result.domain.polygon), 4)

    def test_short_polygon_rejected(self):
        with self.assertRaises(InvalidGeometryError):
            design_service.assign_domain(
                GeologyAssignRequest(
                    domain={"id": "D-1", "name": "гранит"},
                    polygon=[{"x": 0, "y": 0, "z": 0}, {"x": 1, "y": 0, "z": 0}],
                )
            )


class GeologyInterceptApiTests(unittest.TestCase):
    def test_intercept_builds_example_stack(self):
        result = design_service.intercept_geology(
            GeologyInterceptRequest(
                holes=[_hole_payload()],
                domains=[
                    _layer_payload("D-w", "weathered", 0.0, -3.0, fracturing="weathered"),
                    _layer_payload("D-g", "competent granite", -3.0, -8.0, ucs_mpa=140.0),
                    _layer_payload("D-f", "fractured granite", -8.0, -11.0, fracturing="intense"),
                ],
            )
        )
        self.assertEqual(result.interval_count, 3)
        names = [iv.domain_name for iv in result.holes[0].intervals]
        self.assertEqual(names, ["weathered", "competent granite", "fractured granite"])
        self.assertAlmostEqual(result.holes[0].intervals[0].to_m, 3.0)
        self.assertAlmostEqual(result.holes[0].intervals[1].to_m, 8.0)

    def test_measured_intervals_survive_intercept(self):
        hole = _hole_payload()
        hole["measured_intervals"] = [
            {"from_m": 0.0, "to_m": 1.2, "domain_name": "core", "role": "measured"}
        ]
        result = design_service.intercept_geology(
            GeologyInterceptRequest(
                holes=[hole],
                domains=[_layer_payload("D-w", "weathered", 0.0, -3.0)],
            )
        )
        self.assertEqual(result.holes[0].measured_intervals[0].domain_name, "core")
        self.assertEqual(result.holes[0].intervals[0].domain_name, "weathered")


class GeologyPersistenceTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        patcher = patch("cost.persistence.data_root", return_value=Path(self._tmp.name))
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_design_round_trip_keeps_domains_and_intervals(self):
        intercepted = design_service.intercept_geology(
            GeologyInterceptRequest(
                holes=[_hole_payload()],
                domains=[_layer_payload("D-w", "weathered", 0.0, -3.0, density_kg_m3=2300.0)],
                water_table_z_m=-8.0,
            )
        )
        schema = BlastDesignSchema(
            name="Геология блока",
            holes=[h.model_dump() for h in intercepted.holes],
            domains=[_layer_payload("D-w", "weathered", 0.0, -3.0, density_kg_m3=2300.0)],
            water_table_z_m=-8.0,
        )
        saved = save_design("team-geo", BlastDesign.from_dict(schema.model_dump()))
        loaded = load_design("team-geo", saved.design_id)
        self.assertEqual(len(loaded.domains), 1)
        self.assertEqual(loaded.domains[0].properties.density_kg_m3, 2300.0)
        self.assertEqual(loaded.water_table_z_m, -8.0)
        self.assertEqual(loaded.holes[0].intervals[0].domain_name, "weathered")
        self.assertTrue(loaded.holes[0].water_intervals)

    def test_schema_accepts_design_without_geology(self):
        schema = BlastDesignSchema(name="Пустой")
        design = BlastDesign.from_dict(schema.model_dump())
        self.assertEqual(design.domains, [])
        self.assertEqual(design.holes, [])


class ChargingConsumesIntervalsTests(unittest.TestCase):
    def test_hole_from_api_payload_exposes_intervals(self):
        result = design_service.intercept_geology(
            GeologyInterceptRequest(
                holes=[_hole_payload()],
                domains=[_layer_payload("D-w", "weathered", 0.0, -3.0, ucs_mpa=40.0)],
            )
        )
        hole = Hole.from_dict(result.holes[0].model_dump())
        from design.charging import hole_geology_for_charging

        intervals = hole_geology_for_charging(hole)
        self.assertEqual(len(intervals), 1)
        self.assertEqual(intervals[0].properties.ucs_mpa, 40.0)
        self.assertIsInstance(hole.collar, Point3)


if __name__ == "__main__":
    unittest.main()
