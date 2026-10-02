"""Проверка системы координат по экстенту чертежа (TASK-013, PR 4)."""
from __future__ import annotations

import unittest

import numpy as np

from design.spatial.cad.crs import CRS_FAR_M, extent_distance_m, far_from_site, robust_extent, robust_extent_of
from design.spatial.cad.model import CadEntity

# Синтетический сдвиг «как МСК»: реальные координаты заказчика в тесты не идут.
X0, Y0 = 7_000_000.0, 500_000.0


def _grid(x0: float, y0: float, size: float = 300.0, n: int = 10) -> np.ndarray:
    xs, ys = np.meshgrid(np.linspace(x0, x0 + size, n), np.linspace(y0, y0 + size, n))
    return np.column_stack([xs.ravel(), ys.ravel()])


class RobustExtentTests(unittest.TestCase):
    def test_outlier_at_origin_is_ignored(self) -> None:
        points = np.vstack([_grid(X0, Y0), [[0.0, 0.0]]])
        xmin, ymin, xmax, ymax = robust_extent(points)
        self.assertGreater(xmin, X0 - 1)
        self.assertGreater(ymin, Y0 - 1)
        self.assertLess(xmax, X0 + 301)
        self.assertLess(ymax, Y0 + 301)

    def test_few_points_plain_bounds(self) -> None:
        points = np.array([[0.0, 0.0], [10.0, 5.0], [3.0, 8.0]])
        self.assertEqual(robust_extent(points), (0.0, 0.0, 10.0, 8.0))

    def test_no_points(self) -> None:
        self.assertIsNone(robust_extent(np.empty((0, 2))))

    def test_of_entities_uses_all_vertices(self) -> None:
        line = CadEntity(handle="1", layer="0", kind="LWPOLYLINE", points=[(X0, Y0, 0.0), (X0 + 100, Y0 + 50, 0.0)])
        point = CadEntity(handle="2", layer="0", kind="POINT", points=[(X0 + 20, Y0 + 80, 410.0)])
        self.assertEqual(robust_extent_of([line, point]), (X0, Y0, X0 + 100, Y0 + 80))


class DistanceTests(unittest.TestCase):
    def test_overlap_is_zero(self) -> None:
        self.assertEqual(extent_distance_m((0, 0, 10, 10), (5, 5, 20, 20)), 0.0)

    def test_gap_along_x(self) -> None:
        self.assertEqual(extent_distance_m((0, 0, 10, 10), (40, 0, 50, 10)), 30.0)

    def test_diagonal_gap(self) -> None:
        self.assertAlmostEqual(extent_distance_m((0, 0, 10, 10), (13, 14, 20, 20)), 5.0)


class FarFromSiteTests(unittest.TestCase):
    def setUp(self) -> None:
        self.first = robust_extent(_grid(X0, Y0))

    def test_second_file_nearby_is_fine(self) -> None:
        second = robust_extent(_grid(X0 + 600, Y0 + 300))
        self.assertIsNone(far_from_site(second, [self.first]))

    def test_shift_by_50_km_is_reported(self) -> None:
        shifted = robust_extent(_grid(X0 + 50_000, Y0))
        distance = far_from_site(shifted, [self.first])
        self.assertIsNotNone(distance)
        self.assertGreater(distance, CRS_FAR_M)
        self.assertAlmostEqual(distance, 50_000 - 300, delta=1)

    def test_outlier_at_origin_does_not_alarm(self) -> None:
        with_outlier = robust_extent(np.vstack([_grid(X0 + 100, Y0 + 100), [[0.0, 0.0]]]))
        self.assertIsNone(far_from_site(with_outlier, [self.first]))

    def test_first_file_of_site_is_not_checked(self) -> None:
        self.assertIsNone(far_from_site(self.first, []))

    def test_close_to_any_previous_file_is_fine(self) -> None:
        other = robust_extent(_grid(X0 + 50_000, Y0))
        second = robust_extent(_grid(X0 + 49_000, Y0))
        self.assertIsNone(far_from_site(second, [self.first, other]))

    def test_unknown_extent_is_not_checked(self) -> None:
        self.assertIsNone(far_from_site(None, [self.first]))


if __name__ == "__main__":
    unittest.main()
