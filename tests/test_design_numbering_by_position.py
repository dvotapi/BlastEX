"""Нумерация по позиции.

Основная сетка — по эшелонам: эшелон — линия скважин от бровки вглубь блока,
эшелоны считаются с левого фланга (если смотреть с откоса вглубь), внутри
эшелона — от бровки. Пресплит, контур и буфер — отдельные группы с буквами
P, K, B и прежней нумерацией по рядам. Ручные скважины номер не меняют.
"""
import unittest

from design.geometry import local_basis
from design.models import Hole, Point3
from design.numbering import number_by_position


def _hole(hid: str, x: float, y: float, kind: str = "production", source: str = "generated") -> Hole:
    point = Point3(x=x, y=y, z=0.0)
    return Hole(id=hid, row=0, col=0, collar=point, toe=point, diameter_mm=152.0, kind=kind, source=source)


class NumberByPositionTest(unittest.TestCase):
    def test_echelons_start_at_left_flank_and_count_from_crest(self):
        # Бровка на юге, блок к северу: вглубь — +Y, левый фланг — запад.
        holes = [
            _hole("a", x=5.0, y=5.0),
            _hole("b", x=0.0, y=0.0),
            _hole("c", x=5.0, y=0.0),
            _hole("d", x=0.0, y=5.0),
        ]
        a, b, c, d = number_by_position(holes, deep_dir=(0.0, 1.0))
        self.assertEqual(b.id, "1-01")  # левый фланг, у бровки
        self.assertEqual(d.id, "1-02")  # левый фланг, к тылу
        self.assertEqual(c.id, "2-01")
        self.assertEqual(a.id, "2-02")
        self.assertEqual((b.row, b.col), (0, 0))  # fixture: row/col одинаковые — не переназначены

    def test_reversed_block_flips_left_flank_and_crest(self):
        # Бровка на севере, вглубь — −Y: левый фланг (с откоса вглубь) — восток.
        holes = [
            _hole("a", x=5.0, y=5.0),
            _hole("b", x=0.0, y=0.0),
            _hole("c", x=5.0, y=0.0),
            _hole("d", x=0.0, y=5.0),
        ]
        a, b, c, d = number_by_position(holes, deep_dir=(0.0, -1.0))
        self.assertEqual((a.id, c.id, d.id, b.id), ("1-01", "1-02", "2-01", "2-02"))

    def test_without_deep_dir_uses_row_axis_advance(self):
        # Азимут 0: ось ряда — на север, продвижение — на восток; левый фланг — север.
        holes = [
            _hole("a", x=10.0, y=0.0),
            _hole("b", x=0.0, y=0.0),
            _hole("c", x=5.0, y=10.0),
            _hole("d", x=0.0, y=10.0),
        ]
        a, b, c, d = number_by_position(holes)
        self.assertEqual((d.id, c.id, b.id, a.id), ("1-01", "1-02", "2-01", "2-02"))

    def test_face_pair_takes_vertical_number_with_t(self):
        # Пара на 1 м ближе к откосу не образует свой эшелон и не сбивает нумерацию.
        holes = [
            _hole("v1", x=0.0, y=0.0),
            _hole("v2", x=4.0, y=0.0),
            _hole("v1T", x=0.0, y=-1.0, kind="face_toe"),
            _hole("x", x=4.0, y=-1.0, kind="face_toe"),  # без вертикальной — номер не меняется
        ]
        v1, v2, pair, orphan = number_by_position(holes, deep_dir=(0.0, 1.0))
        self.assertEqual((v1.id, v2.id), ("1-01", "2-01"))
        self.assertEqual(pair.id, "1-01T")
        self.assertEqual(orphan.id, "x")
        # Явная связь: индекс вертикальной.
        _, _, pair, _ = number_by_position(holes, deep_dir=(0.0, 1.0), partners=[None, None, 1, None])
        self.assertEqual(pair.id, "2-01T")

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

    def test_rotated_block_groups_echelons_along_deep_direction(self):
        # Азимут 30°: эшелон — линия вглубь блока, а не полоса по X. Каждый эшелон — одна строка id.
        row_dir, advance = local_basis(30.0)
        holes = []
        for i in range(4):  # эшелоны вдоль оси ряда
            for j in range(3):  # скважины эшелона вглубь
                x = i * 5.0 * row_dir[0] + j * 5.0 * advance[0]
                y = i * 5.0 * row_dir[1] + j * 5.0 * advance[1]
                holes.append(_hole(f"h{i}-{j}", x=x, y=y))
        numbered = number_by_position(holes, row_azimuth_deg=30.0, deep_dir=advance)
        for i in range(4):
            echelon = numbered[i * 3 : (i + 1) * 3]
            # Вглубь — advance, левый фланг — по оси ряда дальше всех (ось ряда смотрит вправо назад).
            self.assertEqual([h.id for h in echelon], [f"{4 - i}-0{j + 1}" for j in range(3)])

    def test_walls_keep_row_numbering(self):
        # Стенка вдоль оси ряда: по-прежнему ряд → номер внутри ряда, без эшелонов.
        holes = [_hole(f"p{i}", x=0.0, y=float(i) * 3.0, kind="presplit") for i in range(3)]
        numbered = number_by_position(holes, deep_dir=(1.0, 0.0))
        self.assertEqual([h.id for h in numbered], ["P1-03", "P1-02", "P1-01"])

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
    def test_one_metre_spaced_echelons_stay_separate(self):
        # Эшелоны через 1 м: допуск склейки — 5 см, а не шаг сетки.
        holes = [
            Hole(id=f"x{i}{j}", row=i, col=j, collar=Point3(x=float(i), y=float(j) * 5.0, z=0.0),
                 toe=Point3(x=0.0, y=0.0, z=0.0), diameter_mm=152.0)
            for i in range(10) for j in range(2)
        ]
        numbered = number_by_position(holes, deep_dir=(0.0, 1.0))
        self.assertEqual(len({h.id.split("-")[0] for h in numbered}), 10)
