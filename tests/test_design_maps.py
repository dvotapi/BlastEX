import unittest

from design.editing import local_burden, local_spacing
from design.maps import MAP_METRICS, engineering_maps
from design.models import BenchSurface, BlastDesign, BlockContour, Hole, Point3
from design.pattern import generate_pattern


def _rect() -> BlockContour:
    return BlockContour(
        vertices=[Point3(x=x, y=y, z=0.0) for x, y in [(0, 0), (20, 0), (20, 20), (0, 20)]],
        free_faces=[[0, 1]],
        bench=BenchSurface(crest_z_m=0.0, toe_z_m=-10.0),
    )


class EngineeringMapsTests(unittest.TestCase):
    def test_maps_cover_required_metrics(self):
        contour = _rect()
        holes = generate_pattern(
            contour,
            {
                "pattern": "rectangular",
                "spacing_a_m": 5.0,
                "burden_b_m": 5.0,
                "offset_from_face_m": 0.0,
                "edge_margin_m": 0.0,
            },
        )
        design = BlastDesign(design_id="m", contour=contour, holes=holes)
        maps = engineering_maps(design)
        self.assertEqual(list(maps["metrics"]), list(MAP_METRICS))
        self.assertEqual(len(maps["holes"]), len(holes))
        sample = maps["holes"][0]
        for metric in MAP_METRICS:
            self.assertIn(metric, sample)
            self.assertIn(metric, maps["stats"])
            self.assertIn("avg", maps["stats"][metric])
        self.assertIn("true_face_burden", sample)

    def test_local_spacing_and_burden(self):
        holes = [
            Hole(id="1-01", row=0, col=0, collar=Point3(0, 0, 0), toe=Point3(0, 0, -11), diameter_mm=152),
            Hole(id="1-02", row=0, col=1, collar=Point3(5, 0, 0), toe=Point3(5, 0, -11), diameter_mm=152),
            Hole(id="2-01", row=1, col=0, collar=Point3(0, 4, 0), toe=Point3(0, 4, -11), diameter_mm=152),
        ]
        self.assertAlmostEqual(local_spacing(holes, holes[0]), 5.0)
        self.assertAlmostEqual(local_burden(holes, holes[2], _rect()), 4.0)


if __name__ == "__main__":
    unittest.main()
