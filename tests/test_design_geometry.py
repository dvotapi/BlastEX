import math
import unittest

from design.geometry import (
    angle_azimuth,
    block_volume,
    collar_burden,
    face_azimuth_deg,
    hole_from_collar,
    offset_polygon,
    point_in_polygon,
    polygon_area,
    toe_burden,
    true_burden,
)
from design.models import BenchSurface, BlockContour, Hole, Point3

SQUARE = [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0)]


class PointInPolygonTests(unittest.TestCase):
    def test_center_is_inside(self):
        self.assertTrue(point_in_polygon((5.0, 5.0), SQUARE))

    def test_outside_point(self):
        self.assertFalse(point_in_polygon((15.0, 5.0), SQUARE))

    def test_vertex_counts_as_inside(self):
        self.assertTrue(point_in_polygon((0.0, 0.0), SQUARE))

    def test_edge_point_counts_as_inside(self):
        self.assertTrue(point_in_polygon((0.0, 5.0), SQUARE))


class PolygonAreaTests(unittest.TestCase):
    def test_square_area(self):
        self.assertAlmostEqual(polygon_area(SQUARE), 100.0)

    def test_area_independent_of_winding(self):
        reversed_square = list(reversed(SQUARE))
        self.assertAlmostEqual(polygon_area(reversed_square), 100.0)


class OffsetPolygonTests(unittest.TestCase):
    def test_shrinks_inward(self):
        offset = offset_polygon(SQUARE, 2.0)
        expected = [(2.0, 2.0), (8.0, 2.0), (8.0, 8.0), (2.0, 8.0)]
        for (x, y), (ex, ey) in zip(offset, expected):
            self.assertAlmostEqual(x, ex)
            self.assertAlmostEqual(y, ey)

    def test_zero_distance_is_noop(self):
        offset = offset_polygon(SQUARE, 0.0)
        self.assertEqual(offset, SQUARE)


class HoleGeometryTests(unittest.TestCase):
    def test_vertical_hole_round_trip(self):
        collar = Point3(x=10.0, y=20.0, z=100.0)
        toe = hole_from_collar(collar, depth_m=15.0, angle_deg=0.0, azimuth_deg=0.0)
        self.assertAlmostEqual(toe.x, 10.0)
        self.assertAlmostEqual(toe.y, 20.0)
        self.assertAlmostEqual(toe.z, 85.0)

    def test_inclined_hole_round_trip(self):
        collar = Point3(x=0.0, y=0.0, z=0.0)
        toe = hole_from_collar(collar, depth_m=20.0, angle_deg=15.0, azimuth_deg=45.0)
        angle_deg, azimuth_deg = angle_azimuth(collar, toe)
        self.assertAlmostEqual(angle_deg, 15.0, places=6)
        self.assertAlmostEqual(azimuth_deg, 45.0, places=6)

    def test_hole_length_matches_depth(self):
        collar = Point3(x=0.0, y=0.0, z=0.0)
        toe = hole_from_collar(collar, depth_m=18.0, angle_deg=20.0, azimuth_deg=200.0)
        length = math.dist((collar.x, collar.y, collar.z), (toe.x, toe.y, toe.z))
        self.assertAlmostEqual(length, 18.0, places=6)


class BurdenGeometryTests(unittest.TestCase):
    def test_collar_and_toe_burden_use_free_face(self):
        contour = BlockContour(
            vertices=[Point3(x=x, y=y, z=0.0) for x, y in SQUARE],
            free_faces=[[0, 1]],
            bench=BenchSurface(crest_z_m=0.0, toe_z_m=-10.0),
        )
        hole = Hole(
            id="1-01",
            row=0,
            col=0,
            collar=Point3(x=5.0, y=3.0, z=0.0),
            toe=Point3(x=5.0, y=4.0, z=-11.0),
            diameter_mm=152.0,
        )
        self.assertAlmostEqual(collar_burden(hole, contour), 3.0)
        self.assertAlmostEqual(toe_burden(hole, contour), 4.0)
        self.assertAlmostEqual(true_burden(hole, contour), 4.0)


class FaceAzimuthTests(unittest.TestCase):
    @staticmethod
    def _contour(points, free_faces):
        return BlockContour(
            vertices=[Point3(x=x, y=y, z=0.0) for x, y in points],
            free_faces=free_faces,
            bench=BenchSurface(crest_z_m=0.0, toe_z_m=-10.0),
        )

    def _rect(self, free_faces):
        return self._contour([(0, 0), (40, 0), (40, 22), (0, 22)], free_faces)

    def test_points_out_of_block_to_south_face(self):
        self.assertAlmostEqual(face_azimuth_deg((10.0, 5.0), self._rect([[0, 1]])), 180.0)

    def test_east_face(self):
        self.assertAlmostEqual(face_azimuth_deg((30.0, 10.0), self._rect([[1, 2]])), 90.0)

    def test_follows_nearest_segment_of_bent_crest(self):
        contour = self._contour(
            [(0, 0), (20, 0), (40, 10), (40, 30), (0, 30)], [[0, 1, 2]]
        )
        a1 = face_azimuth_deg((5.0, 5.0), contour)
        a2 = face_azimuth_deg((33.0, 14.0), contour)
        self.assertAlmostEqual(a1, 180.0)
        # Перпендикуляр к отрезку (20,0)-(40,10): направление (10,-20).
        self.assertAlmostEqual(a2, math.degrees(math.atan2(10.0, -20.0)), places=6)
        self.assertAlmostEqual(a2, 153.4349, places=3)

    def test_point_outside_block_still_points_out(self):
        self.assertAlmostEqual(face_azimuth_deg((10.0, -3.0), self._rect([[0, 1]])), 180.0)

    def test_point_beyond_segment_end_points_to_vertex(self):
        # Вогнутый для блока стык (20,0): проекция точки за концами обоих отрезков.
        contour = self._contour([(0, 0), (20, 0), (40, -10), (40, 30), (0, 30)], [[0, 1, 2]])
        az = face_azimuth_deg((22.0, 8.0), contour)
        self.assertAlmostEqual(az, math.degrees(math.atan2(-2.0, -8.0)) % 360.0)

    def test_clockwise_contour(self):
        contour = self._contour([(0, 0), (0, 22), (40, 22), (40, 0)], [[3, 0]])
        self.assertAlmostEqual(face_azimuth_deg((10.0, 5.0), contour), 180.0)
        self.assertAlmostEqual(face_azimuth_deg((10.0, 0.0), contour), 180.0)

    def test_point_on_segment_uses_outward_normal(self):
        self.assertAlmostEqual(face_azimuth_deg((10.0, 0.0), self._rect([[0, 1]])), 180.0)
        # Грань задана против порядка обхода — наружу всё равно.
        self.assertAlmostEqual(face_azimuth_deg((10.0, 0.0), self._rect([[1, 0]])), 180.0)

    def test_none_without_free_faces(self):
        self.assertIsNone(face_azimuth_deg((10.0, 5.0), self._rect([])))


class BlockVolumeTests(unittest.TestCase):
    def test_volume_is_area_times_height(self):
        contour = BlockContour(
            vertices=[Point3(x=x, y=y, z=0.0) for x, y in SQUARE],
            bench=BenchSurface(crest_z_m=100.0, toe_z_m=90.0),
        )
        self.assertAlmostEqual(block_volume(contour), 1000.0)


if __name__ == "__main__":
    unittest.main()
