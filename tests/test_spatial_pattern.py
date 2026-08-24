import unittest

from design.geometry import block_volume, collar_elevation, drape_collar
from design.models import BenchSurface, BlockContour, Point3
from design.pattern import generate_pattern
from design.spatial.surfaces import SurfaceSet, floor_surface, top_surface


def _rect(width: float, height: float, crest: float = 0.0, toe: float = -10.0) -> BlockContour:
    verts = [(0.0, 0.0), (width, 0.0), (width, height), (0.0, height)]
    return BlockContour(
        vertices=[Point3(x=x, y=y, z=crest) for x, y in verts],
        bench=BenchSurface(crest_z_m=crest, toe_z_m=toe),
    )


def _sloped_top() -> SurfaceSet:
    points = []
    for x in (0.0, 10.0, 20.0):
        for y in (0.0, 10.0, 20.0):
            points.append(Point3(x=x, y=y, z=100.0 + 0.5 * x))
    floor_pts = [Point3(x=p.x, y=p.y, z=90.0) for p in points]
    return SurfaceSet(top=top_surface(points), floor=floor_surface(floor_pts))


class PlanarFallbackTests(unittest.TestCase):
    def test_no_surfaces_uses_bench_crest(self):
        contour = _rect(20.0, 20.0, crest=12.0, toe=0.0)
        holes = generate_pattern(
            contour,
            {"pattern": "rectangular", "spacing_a_m": 10.0, "burden_b_m": 10.0, "offset_from_face_m": 0.0, "edge_margin_m": 0.0},
        )
        self.assertTrue(holes)
        for hole in holes:
            self.assertAlmostEqual(hole.collar.z, 12.0)
            self.assertAlmostEqual(hole.toe.z, 12.0 - (12.0 + 1.0), places=5)


class TerrainDrapeTests(unittest.TestCase):
    def test_collars_follow_sloped_top(self):
        contour = _rect(20.0, 20.0, crest=100.0, toe=90.0)
        surfaces = _sloped_top()
        holes = generate_pattern(
            contour,
            {
                "pattern": "rectangular",
                "spacing_a_m": 10.0,
                "burden_b_m": 10.0,
                "offset_from_face_m": 0.0,
                "edge_margin_m": 0.0,
                "subdrill_m": 1.0,
            },
            surfaces=surfaces,
        )
        self.assertGreater(len(holes), 2)
        zs = {round(h.collar.x, 3): h.collar.z for h in holes if h.kind == "production"}
        self.assertAlmostEqual(zs[0.0], 100.0, places=4)
        self.assertAlmostEqual(zs[10.0], 105.0, places=4)
        self.assertAlmostEqual(zs[20.0], 110.0, places=4)

    def test_depth_uses_floor_surface(self):
        contour = _rect(20.0, 20.0, crest=100.0, toe=80.0)
        surfaces = _sloped_top()
        collar, toe = drape_collar(10.0, 10.0, 0.0, 0.0, 1.0, contour, surfaces)
        self.assertAlmostEqual(collar.z, 105.0, places=4)
        self.assertAlmostEqual(toe.z, 89.0, places=4)

    def test_collar_elevation_fallback(self):
        contour = _rect(20.0, 20.0, crest=7.0)
        self.assertAlmostEqual(collar_elevation(3.0, 3.0, contour, None), 7.0)


class VolumeTests(unittest.TestCase):
    def test_planar_volume_unchanged(self):
        contour = _rect(10.0, 10.0, crest=10.0, toe=0.0)
        self.assertAlmostEqual(block_volume(contour), 1000.0)

    def test_surface_volume_near_expected(self):
        contour = _rect(20.0, 20.0, crest=100.0, toe=90.0)
        surfaces = _sloped_top()
        volume = block_volume(contour, surfaces)
        # Средняя высота кровли 105, подошва 90 → ~15 × 400 = 6000 м³
        self.assertGreater(volume, 5000.0)
        self.assertLess(volume, 7000.0)


if __name__ == "__main__":
    unittest.main()
