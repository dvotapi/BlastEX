import math
import unittest

from design.models import Point3
from design.spatial.tin import TIN, build_tin, loft_polylines


def _plane_points(z_at):
    pts = []
    for x in (0.0, 10.0, 20.0):
        for y in (0.0, 10.0, 20.0):
            pts.append(Point3(x=x, y=y, z=z_at(x, y)))
    return pts


class TinElevationTests(unittest.TestCase):
    def test_flat_plane_elevation(self):
        tin = build_tin(_plane_points(lambda x, y: 100.0))
        self.assertAlmostEqual(tin.elevation_at(7.0, 13.0), 100.0, places=6)

    def test_sloped_plane_interpolates_z(self):
        tin = build_tin(_plane_points(lambda x, y: 50.0 + 0.2 * x))
        z = tin.elevation_at(10.0, 5.0)
        self.assertIsNotNone(z)
        self.assertAlmostEqual(z, 52.0, places=5)

    def test_outside_hull_returns_none(self):
        tin = build_tin(_plane_points(lambda x, y: 0.0))
        self.assertIsNone(tin.elevation_at(-20.0, -20.0))

    def test_vertical_intersection(self):
        tin = build_tin(_plane_points(lambda x, y: 12.5))
        hit = tin.vertical_intersection(4.0, 6.0)
        self.assertIsNotNone(hit)
        self.assertAlmostEqual(hit.z, 12.5)

    def test_line_intersection_hits_plane(self):
        tin = build_tin(_plane_points(lambda x, y: 0.0))
        hit = tin.line_intersection(Point3(x=5.0, y=5.0, z=10.0), Point3(x=5.0, y=5.0, z=-10.0))
        self.assertIsNotNone(hit)
        self.assertAlmostEqual(hit.z, 0.0, places=5)

    def test_distance_above_surface_is_positive(self):
        tin = build_tin(_plane_points(lambda x, y: 10.0))
        dist = tin.distance_to_surface(Point3(x=5.0, y=5.0, z=13.0))
        self.assertAlmostEqual(dist, 3.0, places=6)

    def test_empty_tin(self):
        tin = TIN()
        self.assertTrue(tin.is_empty)
        self.assertIsNone(tin.elevation_at(0.0, 0.0))
        self.assertIsNone(tin.distance_to_surface(Point3(0, 0, 0)))


class LoftPolylineTests(unittest.TestCase):
    def test_face_loft_has_triangles(self):
        crest = [Point3(x=0.0, y=i * 5.0, z=100.0) for i in range(4)]
        toe = [Point3(x=8.0, y=i * 5.0, z=90.0) for i in range(4)]
        tin = loft_polylines(crest, toe)
        self.assertGreaterEqual(len(tin.triangles), 4)
        hit = tin.line_intersection(
            Point3(x=-1.0, y=7.5, z=95.0),
            Point3(x=10.0, y=7.5, z=95.0),
        )
        self.assertIsNotNone(hit)


class SampleLineTests(unittest.TestCase):
    def test_sample_follows_slope(self):
        tin = build_tin(_plane_points(lambda x, y: x))
        profile = tin.sample_line(0.0, 10.0, 20.0, 10.0, count=5)
        self.assertGreaterEqual(len(profile), 3)
        self.assertAlmostEqual(profile[0].z, 0.0, places=4)
        self.assertAlmostEqual(profile[-1].z, 20.0, places=4)


class RoundTripTests(unittest.TestCase):
    def test_to_dict_from_dict(self):
        tin = build_tin(_plane_points(lambda x, y: 1.0))
        restored = TIN.from_dict(tin.to_dict())
        self.assertEqual(len(restored.triangles), len(tin.triangles))
        self.assertAlmostEqual(restored.elevation_at(3.0, 3.0), 1.0)


if __name__ == "__main__":
    unittest.main()
