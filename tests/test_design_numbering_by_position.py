"""Нумерация по позиции: север→юг по рядам, запад→восток внутри ряда.

Пресплит, контур и буфер — отдельные группы с буквами P, K, B. Ручные скважины
номер не меняют.
"""
import unittest

from design.models import Hole, Point3
from design.numbering import number_by_position


def _hole(hid: str, x: float, y: float, kind: str = "production", source: str = "generated") -> Hole:
    point = Point3(x=x, y=y, z=0.0)
    return Hole(id=hid, row=0, col=0, collar=point, toe=point, diameter_mm=152.0, kind=kind, source=source)


class NumberByPositionTest(unittest.TestCase):
    def test_rows_go_north_to_south_and_columns_west_to_east(self):
        holes = [
            _hole("a", x=10.0, y=0.0),
            _hole("b", x=0.0, y=0.0),
            _hole("c", x=5.0, y=10.0),
            _hole("d", x=0.0, y=10.0),
        ]
        a, b, c, d = number_by_position(holes)
        self.assertEqual(c.id, "1-02")
        self.assertEqual(d.id, "1-01")
        self.assertEqual((d.row, d.col), (0, 0))  # fixture: row/col одинаковые — не переназначены
        self.assertEqual(b.id, "2-01")
        self.assertEqual(a.id, "2-02")

    def test_walls_use_own_letters_and_own_counting(self):
        holes = [
            _hole("g", x=0.0, y=0.0),
            _hole("k", x=0.0, y=-20.0, kind="contour"),
            _hole("p", x=0.0, y=10.0, kind="presplit"),
            _hole("b", x=0.0, y=-10.0, kind="buffer"),
        ]
        ids = {h.id: h.kind for h in number_by_position(holes)}
        self.assertEqual(sorted(ids.values()), sorted(["production", "contour", "presplit", "buffer"]))
        numbered = {h.kind: h.id for h in number_by_position(holes)}
        self.assertEqual(numbered["presplit"], "P1-01")
        self.assertEqual(numbered["buffer"], "B1-01")
        self.assertEqual(numbered["contour"], "K1-01")
        self.assertEqual(numbered["production"], "1-01")

    def test_row_and_col_stay_technical(self):
        holes = [
            Hole(id="x", row=3, col=7, collar=Point3(x=0.0, y=0.0, z=0.0), toe=Point3(x=0.0, y=0.0, z=0.0),
                 diameter_mm=152.0),
        ]
        only = number_by_position(holes)[0]
        self.assertEqual((only.row, only.col), (3, 7))
        self.assertEqual(only.id, "1-01")

    def test_manual_holes_keep_their_id_and_do_not_shift_others(self):
        holes = [
            _hole("M-1", x=0.0, y=50.0, source="manual"),
            _hole("g", x=0.0, y=0.0),
        ]
        numbered = number_by_position(holes)
        self.assertEqual(numbered[0].id, "M-1")
        self.assertEqual(numbered[1].id, "1-01")


if __name__ == "__main__":
    unittest.main()
