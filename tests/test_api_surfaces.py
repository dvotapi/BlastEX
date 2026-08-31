import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from api.exceptions import InvalidSurveyError
from api.schemas.design import BenchDxfImportRequest, PatternGenerateRequest, SurfaceImportRequest
from api.services import design_service
from design.models import BenchSurface, BlockContour, Point3


class SurfaceImportApiTests(unittest.TestCase):
    def test_import_xyz_builds_top_tin(self):
        content = "\n".join(
            f"{x} {y} {100 + 0.2 * x}"
            for x in (0, 10, 20)
            for y in (0, 10, 20)
        )
        result = design_service.import_surface(
            SurfaceImportRequest(content=content, filename="bench.xyz", kind="top")
        )
        self.assertEqual(result.surface.kind, "top")
        self.assertGreaterEqual(result.stats.triangle_count, 1)
        self.assertGreaterEqual(result.stats.point_count, 9)

    def test_empty_file_rejected(self):
        with self.assertRaises(InvalidSurveyError):
            design_service.import_surface(SurfaceImportRequest(content="  ", filename="empty.xyz"))

    def test_bench_dxf_creates_contour_and_three_surfaces(self):
        from tests.test_spatial_import import BENCH_DXF

        result = design_service.import_bench_dxf(BenchDxfImportRequest(content=BENCH_DXF, filename="block.dxf"))
        self.assertEqual(len(result.contour.vertices), 6)
        self.assertIsNotNone(result.surfaces.top)
        self.assertIsNotNone(result.surfaces.floor)
        self.assertIsNotNone(result.surfaces.face)
        self.assertGreater(result.crest_z_m, result.toe_z_m)


class PatternWithSurfacesApiTests(unittest.TestCase):
    def test_generated_collars_use_imported_top(self):
        content = "\n".join(
            f"{x} {y} {50 + x}"
            for x in (0, 10, 20)
            for y in (0, 10, 20)
        )
        imported = design_service.import_surface(
            SurfaceImportRequest(content=content, filename="top.xyz", kind="top")
        )
        contour = BlockContour(
            vertices=[Point3(x=x, y=y, z=50.0) for x, y in [(0, 0), (20, 0), (20, 20), (0, 20)]],
            bench=BenchSurface(crest_z_m=50.0, toe_z_m=40.0),
        )
        response = design_service.generate_pattern(
            PatternGenerateRequest(
                contour=contour.to_dict(),
                params={
                    "pattern": "rectangular",
                    "spacing_a_m": 10.0,
                    "burden_b_m": 10.0,
                    "offset_from_face_m": 0.0,
                    "edge_margin_m": 0.0,
                    "subdrill_m": 1.0,
                },
                surfaces={"top": imported.surface.model_dump(), "floor": None, "face": None, "post_blast": None},
            )
        )
        self.assertGreater(response.hole_count, 0)
        by_x = {round(h.collar.x, 3): h.collar.z for h in response.holes}
        self.assertAlmostEqual(by_x[0.0], 50.0, places=3)
        self.assertAlmostEqual(by_x[10.0], 60.0, places=3)


class SurfacePersistenceTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        patcher = patch("cost.persistence.data_root", return_value=Path(self._tmp.name))
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_design_round_trip_keeps_surface(self):
        from api.schemas.design import BlastDesignSchema
        from design.models import BlastDesign
        from design.persistence import load_design, save_design

        imported = design_service.import_surface(
            SurfaceImportRequest(content="0 0 1\n10 0 1\n0 10 1\n10 10 2\n", filename="t.xyz", kind="top")
        )
        schema = BlastDesignSchema(
            name="Съёмка",
            surfaces={"top": imported.surface.model_dump()},
        )
        saved = save_design("team-a", BlastDesign.from_dict(schema.model_dump()))
        loaded = load_design("team-a", saved.design_id)
        self.assertIsNotNone(loaded.surfaces.top)
        self.assertTrue(loaded.surfaces.top.has_tin)
        self.assertEqual(loaded.coordinate_system.units, "m")


if __name__ == "__main__":
    unittest.main()
