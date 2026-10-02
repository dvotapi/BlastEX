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


def _grid_tin(n: int, z_at) -> TIN:
    """Сетка n × n ячеек по 1 м, по два треугольника на ячейку."""
    vertices = [Point3(x=float(x), y=float(y), z=z_at(x, y)) for y in range(n + 1) for x in range(n + 1)]
    triangles = []
    for y in range(n):
        for x in range(n):
            a = y * (n + 1) + x
            triangles += [(a, a + 1, a + n + 2), (a, a + n + 2, a + n + 1)]
    return TIN(vertices=vertices, triangles=triangles)


def _brute_force(tin: TIN, p0: Point3, p1: Point3):
    from design.spatial.tin import _segment_triangle

    direction = (p1.x - p0.x, p1.y - p0.y, p1.z - p0.z)
    hits = []
    for i, j, k in tin.triangles:
        hit = _segment_triangle(p0, direction, tin.vertices[i], tin.vertices[j], tin.vertices[k])
        if hit is not None and 0.0 <= hit[0] <= 1.0:
            hits.append(hit)
    return min(hits, key=lambda item: item[0])[1] if hits else None


class LineIntersectionIndexTests(unittest.TestCase):
    """Ревью Codex #104: пересчёт скважин зовёт line_intersection на каждую
    скважину — перебор всех треугольников давал O(скважин × треугольников)."""

    def test_line_intersection_checks_only_nearby_triangles(self):
        from unittest import mock

        import design.spatial.tin as tin_module

        tin = _grid_tin(60, lambda x, y: 400.0 + 0.05 * x + 0.02 * y)
        calls = []
        original = tin_module._segment_triangle

        def counting(*args):
            calls.append(1)
            return original(*args)

        with mock.patch.object(tin_module, "_segment_triangle", counting):
            hit = tin.line_intersection(Point3(x=30.3, y=20.7, z=420.0), Point3(x=30.3, y=20.7, z=380.0))

        self.assertIsNotNone(hit)
        self.assertAlmostEqual(hit.z, 400.0 + 0.05 * 30.3 + 0.02 * 20.7, places=6)
        self.assertLess(len(calls), len(tin.triangles) // 20)

    def test_line_intersection_matches_brute_force(self):
        tin = _grid_tin(30, lambda x, y: 400.0 + math.sin(x / 4.0) + 0.3 * math.cos(y / 3.0))
        segments = [
            (Point3(x=5.5, y=5.5, z=420.0), Point3(x=5.5, y=5.5, z=380.0)),
            # Наклонная: в плане проходит через много ячеек индекса.
            (Point3(x=2.0, y=3.0, z=420.0), Point3(x=27.0, y=21.0, z=380.0)),
            (Point3(x=29.9, y=0.1, z=402.0), Point3(x=0.2, y=29.8, z=398.0)),
            # Ровно по вершине и по границе ячейки индекса.
            (Point3(x=10.0, y=10.0, z=420.0), Point3(x=10.0, y=10.0, z=380.0)),
            # Мимо сети.
            (Point3(x=-5.0, y=-5.0, z=420.0), Point3(x=-5.0, y=-5.0, z=380.0)),
        ]
        for p0, p1 in segments:
            expected = _brute_force(tin, p0, p1)
            got = tin.line_intersection(p0, p1)
            if expected is None:
                self.assertIsNone(got)
            else:
                self.assertIsNotNone(got)
                self.assertAlmostEqual(got.x, expected.x, places=9)
                self.assertAlmostEqual(got.y, expected.y, places=9)
                self.assertAlmostEqual(got.z, expected.z, places=9)


class IndexEntriesTests(unittest.TestCase):
    def test_index_entries_match_the_built_index(self):
        import numpy as np

        from design.spatial.tin import index_entries

        for tin in (
            _grid_tin(30, lambda x, y: 400.0),
            build_tin(_plane_points(lambda x, y: 100.0)),
            TIN(
                vertices=[Point3(x=0, y=0, z=0), Point3(x=50, y=0, z=0), Point3(x=0, y=50, z=0)],
                triangles=[(0, 1, 2)] * 7,
            ),
        ):
            xy = np.array([(v.x, v.y) for v in tin.vertices])
            self.assertEqual(index_entries(xy, np.asarray(tin.triangles)), sum(len(bucket) for bucket in tin._buckets))
