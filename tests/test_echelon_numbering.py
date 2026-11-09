"""Нумерация сетки по эшелонам на построенном паспорте (решение владельца 09.11.2026).

Эшелон — линия скважин от бровки вглубь блока. Эшелоны — с левого фланга, если
смотреть с откоса вглубь; внутри эшелона — от бровки к тылу.
"""
import unittest
from collections import defaultdict

from design.models import BenchSurface, BlockContour, Point3, row_family
from design.pattern import generate_pattern


def _rect(free: list[list[int]], width: float = 20.0, height: float = 15.0) -> BlockContour:
    verts = [(0.0, 0.0), (width, 0.0), (width, height), (0.0, height)]
    return BlockContour(
        vertices=[Point3(x=x, y=y, z=0.0) for x, y in verts],
        free_faces=free,
        bench=BenchSurface(crest_z_m=0.0, toe_z_m=-10.0, face_angle_deg=75.0),
    )


BASE = {
    "pattern": "square",
    "spacing_a_m": 4.0,
    "burden_b_m": 4.0,
    "row_azimuth_deg": 90.0,
    "edge_margin_m": 1.0,
    "offset_from_face_m": 2.0,
}


def _echelons(holes):
    """{номер эшелона: [(номер в эшелоне, x, y)]} по основной сетке."""
    out: dict[int, list[tuple[int, float, float]]] = defaultdict(list)
    for h in holes:
        if row_family(h.kind) != "grid" or h.kind == "face_toe":
            continue
        echelon, place = h.id.split("-")
        out[int(echelon)].append((int(place), h.collar.x, h.collar.y))
    return out


class EchelonNumberingTest(unittest.TestCase):
    def assert_echelons(self, holes, left_to_right_sign: float, crest_to_back_sign: float):
        echelons = _echelons(holes)
        self.assertGreater(len(echelons), 2)
        xs = []
        for number in sorted(echelons):
            members = sorted(echelons[number])
            # Номера в эшелоне — 01, 02, … без пропусков.
            self.assertEqual([p for p, _, _ in members], list(range(1, len(members) + 1)))
            # Эшелон — одна линия вглубь (x одинаковый), номера растут от бровки.
            self.assertLess(max(x for _, x, _ in members) - min(x for _, x, _ in members), 1e-6)
            ys = [crest_to_back_sign * y for _, _, y in members]
            self.assertEqual(ys, sorted(ys))
            xs.append(left_to_right_sign * members[0][1])
        self.assertEqual(xs, sorted(xs))

    def test_crest_south_numbers_from_west_and_from_south(self):
        # Смотрим с откоса (юг) на север: левый фланг — запад.
        holes = generate_pattern(_rect([[0, 1]]), dict(BASE))
        self.assert_echelons(holes, left_to_right_sign=1.0, crest_to_back_sign=1.0)
        first = next(h for h in holes if h.id == "1-01")
        grid = [h for h in holes if row_family(h.kind) == "grid"]
        self.assertAlmostEqual(first.collar.x, min(h.collar.x for h in grid))
        self.assertAlmostEqual(first.collar.y, min(h.collar.y for h in grid))

    def test_crest_north_numbers_from_east_and_from_north(self):
        # Смотрим с откоса (север) на юг: левый фланг — восток.
        holes = generate_pattern(_rect([[2, 3]]), dict(BASE))
        self.assert_echelons(holes, left_to_right_sign=-1.0, crest_to_back_sign=-1.0)

    def test_back_template_numbers_from_crest(self):
        params = {**BASE, "layout_anchor": "back", "back_offset_m": 2.0}
        holes = generate_pattern(_rect([[0, 1]]), params)
        self.assert_echelons(holes, left_to_right_sign=1.0, crest_to_back_sign=1.0)


if __name__ == "__main__":
    unittest.main()
