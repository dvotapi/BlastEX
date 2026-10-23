"""Нумерация по позиции: север→юг по рядам, запад→восток внутри ряда.

Пресплит, контур и буфер — отдельные группы с буквами P, K, B. Ручные скважины
номер не меняют.
"""
import unittest

from design.geometry import local_basis
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
        # Ряды — линии вдоль оси (север–юг), идут с запада на восток; внутри ряда — с севера на юг.
        self.assertEqual(d.id, "1-01")  # x=0, север
        self.assertEqual(b.id, "1-02")  # x=0, юг
        self.assertEqual(c.id, "2-01")  # x=5
        self.assertEqual(a.id, "3-01")  # x=10
        self.assertEqual((d.row, d.col), (0, 0))  # fixture: row/col одинаковые — не переназначены

    def test_face_pair_takes_vertical_number_with_t(self):
        # Пара на 1 м ближе к откосу не образует свой ряд и не сбивает нумерацию.
        holes = [
            _hole("v1", x=0.0, y=0.0),
            _hole("v2", x=0.0, y=4.0),
            _hole("v1T", x=1.0, y=0.0, kind="face_toe"),
            _hole("x", x=1.0, y=4.0, kind="face_toe"),  # без вертикальной — номер не меняется
        ]
        v1, v2, pair, orphan = number_by_position(holes)
        self.assertEqual((v1.id, v2.id), ("1-02", "1-01"))
        self.assertEqual(pair.id, "1-02T")
        self.assertEqual(orphan.id, "x")
        # Явная связь: индекс вертикальной.
        _, _, pair, _ = number_by_position(holes, partners=[None, None, 1, None])
        self.assertEqual(pair.id, "1-01T")

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

    def test_rotated_block_groups_rows_along_its_axis(self):
        # Азимут 30°: ряды идут вдоль оси 30°, а не по полосам Y. Каждый ряд — одна строка id.
        row_dir, advance = local_basis(30.0)
        holes = []
        for j in range(3):  # полосы поперёк оси
            for i in range(4):  # скважины вдоль оси
                x = i * 5.0 * row_dir[0] + j * 5.0 * advance[0]
                y = i * 5.0 * row_dir[1] + j * 5.0 * advance[1]
                holes.append(_hole(f"h{j}-{i}", x=x, y=y))
        numbered = number_by_position(holes, row_azimuth_deg=30.0)
        for j in range(3):
            band = numbered[j * 4 : (j + 1) * 4]
            self.assertEqual({h.id.split("-")[0] for h in band}, {str(j + 1)})
            self.assertEqual(len({h.id for h in band}), 4)

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


class AuxiliaryPrefixTest(unittest.TestCase):
    def test_satellite_stab_and_infill_keep_their_prefix_and_stay_unique(self):
        holes = [
            _hole("g", x=0.0, y=0.0),
            _hole("s", x=0.0, y=0.0, kind="satellite"),
            _hole("t", x=0.0, y=0.0, kind="stab"),
            _hole("i", x=0.0, y=0.0, kind="infill"),
        ]
        ids = [h.id for h in number_by_position(holes)]
        self.assertEqual(ids, ["1-01", "SAT1-01", "S1-01", "I1-01"])
        self.assertEqual(len(set(ids)), len(ids))


class MinimumSpacingBandsTest(unittest.TestCase):
    def test_one_metre_spaced_rows_stay_separate(self):
        # Ряды через 1 м поперёк оси: раньше допуск 1.0 м склеивал все в одну полосу.
        holes = [
            Hole(id=f"x{i}{j}", row=i, col=j, collar=Point3(x=float(i), y=float(j) * 5.0, z=0.0),
                 toe=Point3(x=0.0, y=0.0, z=0.0), diameter_mm=152.0)
            for i in range(10) for j in range(2)
        ]
        numbered = number_by_position(holes, row_azimuth_deg=0.0)
        self.assertEqual(len({h.id.split("-")[0] for h in numbered}), 10)
