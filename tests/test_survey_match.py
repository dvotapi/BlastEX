import unittest

from api.schemas.design import PatternGenerateRequest
from api.services import design_service
from design.models import Hole, Point3
from design.survey.match import match_survey, swap_detect
from design.survey.read import SurveyedPoint


def _hole(hid: str, x: float, y: float, enabled: bool = True) -> Hole:
    return Hole(
        id=hid, row=1, col=1, collar=Point3(x, y, 0.0), toe=Point3(x, y, -10.0),
        diameter_mm=152.0, enabled=enabled,
    )


def _grid() -> list[Hole]:
    return [_hole(f"{c}-0{r}", c * 5.0, r * 4.0) for c in (1, 2, 3) for r in (1, 2, 3)]


def _pt(name: str, x: float, y: float, line: int = 0) -> SurveyedPoint:
    return SurveyedPoint(name=name, x=x, y=y, line=line)


def _match(points, **kw):
    kw.setdefault("block", "66")
    kw.setdefault("tol_collar_m", 0.3)
    return match_survey(_grid(), points, **kw)


def _by_hole(result, hid):
    return [m for m in result if m.hole_id == hid]


class MatchTests(unittest.TestCase):
    def test_by_name_with_block_prefix_and_case(self):
        pts = [_pt("66-1-01", 5, 4), _pt("1-02", 5, 8), _pt("66-1-03".lower(), 5, 12)]
        res = _match(pts)
        for hid in ("1-01", "1-02", "1-03"):
            (m,) = _by_hole(res, hid)
            self.assertEqual((m.by, m.issue), ("name", ""))
            self.assertIsNotNone(m.point)

    def test_numeric_name_three_digits(self):
        holes = [_hole("7", 0, 0)]
        res = match_survey(holes, [_pt("66-007", 50, 50)], block="66", tol_collar_m=0.3)
        self.assertEqual((res[0].hole_id, res[0].by), ("7", "name"))

    def test_nearest_within_two_tolerances(self):
        res = _match([_pt("zzz", 5.5, 4.0)])
        (m,) = _by_hole(res, "1-01")
        self.assertEqual((m.by, m.issue), ("nearest", ""))

    def test_far_point_not_matched(self):
        res = _match([_pt("RP1", 5.7, 4.0)])
        (m,) = _by_hole(res, "1-01")
        self.assertEqual(m.issue, "missing_point")
        self.assertIsNone(m.point)
        extra = [x for x in res if x.hole_id is None]
        self.assertEqual([x.issue for x in extra], ["unmatched_point"])

    def test_toe_point_suffix_T_ignored(self):
        res = _match([_pt("66-1-01_T", 5.0, 4.0)])
        (m,) = _by_hole(res, "1-01")
        self.assertEqual(m.issue, "missing_point")
        extra = [x for x in res if x.hole_id is None]
        self.assertEqual([(x.point.name, x.issue) for x in extra], [("66-1-01_T", "unmatched_point")])

    def test_two_points_one_hole(self):
        res = _match([_pt("66-1-01", 5, 4), _pt("1-01", 5.1, 4)])
        recs = _by_hole(res, "1-01")
        self.assertEqual(sorted(m.issue for m in recs), ["duplicate_point", "duplicate_point", "missing_point"])
        self.assertTrue(all(m.point is None for m in recs if m.issue == "missing_point"))

    def test_manual_overrides_and_skip(self):
        pts = [_pt("A", 40, 40, 1), _pt("66-1-02", 5, 8, 2), _pt("RP", 5, 4, 3)]
        res = _match(pts, manual={1: "1-02"}, skip={3})
        (m,) = _by_hole(res, "1-02")
        self.assertEqual((m.by, m.point.name, m.issue), ("manual", "A", ""))
        self.assertFalse(any(x.point is not None and x.point.name == "RP" for x in res))
        (m1,) = _by_hole(res, "1-01")
        self.assertEqual(m1.issue, "missing_point")

    def test_manual_resolves_duplicate(self):
        res = _match([_pt("66-1-01", 5, 4, 1), _pt("X", 5.1, 4, 2)], manual={2: "1-01"})
        (m,) = _by_hole(res, "1-01")
        self.assertEqual((m.by, m.point.name), ("manual", "X"))

    def test_name_of_manually_taken_hole_not_nearest(self):
        pts = [_pt("X", 40, 40, 1), _pt("1-01", 5, 7.9, 2)]
        res = _match(pts, manual={1: "1-01"})
        (m1,) = _by_hole(res, "1-01")
        self.assertEqual((m1.by, m1.point.name), ("manual", "X"))
        (m2,) = _by_hole(res, "1-02")
        self.assertEqual((m2.issue, m2.point), ("missing_point", None))
        extra = [x for x in res if x.hole_id is None]
        self.assertEqual([(x.point.name, x.issue, x.by) for x in extra], [("1-01", "unmatched_point", "")])

    def test_decisions_by_line_separate_points_with_same_name(self):
        """Две точки «1-03»: пропуск одной (по строке файла) другую не трогает."""

        pts = [_pt("1-03", 5, 12, 4), _pt("1-03", 5.1, 12, 9)]
        res = _match(pts, skip={9})
        (m,) = _by_hole(res, "1-03")
        self.assertEqual((m.by, m.issue, m.point.line), ("name", "", 4))
        res = _match(pts, manual={9: "1-02"})
        (m2,) = _by_hole(res, "1-02")
        self.assertEqual((m2.by, m2.point.line), ("manual", 9))
        (m3,) = _by_hole(res, "1-03")
        self.assertEqual((m3.by, m3.point.line, m3.issue), ("name", 4, ""))

    def test_name_match_can_be_detached(self):
        """«Без скважины» (пустой id в manual) снимает привязку по имени: точка — без скважины."""

        res = _match([_pt("1-01", 45, 4, 1)], manual={1: ""})
        (m,) = _by_hole(res, "1-01")
        self.assertEqual(m.issue, "missing_point")
        extra = [x for x in res if x.hole_id is None]
        self.assertEqual([(x.point.line, x.by, x.issue) for x in extra], [(1, "manual", "unmatched_point")])

    def test_disabled_hole_matched(self):
        holes = [_hole("1", 0, 0, enabled=False)]
        res = match_survey(holes, [_pt("p", 0.1, 0)], block="", tol_collar_m=0.3)
        self.assertEqual(res[0].by, "nearest")

    def test_swap_detect_true_for_mirrored_points(self):
        holes = _grid()
        mirrored = [_pt(f"p{i}", h.collar.y, h.collar.x) for i, h in enumerate(holes)]
        self.assertTrue(swap_detect(holes, mirrored, 0.3))

    def test_swap_detect_false_for_normal_points(self):
        holes = _grid()
        pts = [_pt(f"p{i}", h.collar.x, h.collar.y) for i, h in enumerate(holes)]
        self.assertFalse(swap_detect(holes, pts, 0.3))

    def test_generated_grid(self):
        holes = design_service.generate_pattern(
            PatternGenerateRequest(
                contour={
                    "vertices": [{"x": x, "y": y, "z": 0.0} for x, y in [(0, 0), (24, 0), (24, 16), (0, 16)]],
                    "free_faces": [[0, 1]],
                    "bench": {"crest_z_m": 0.0, "toe_z_m": -10.0, "face_angle_deg": 90.0},
                    "name": "Блок",
                },
                params={"pattern": "rectangular", "spacing_a_m": 5.0, "burden_b_m": 4.0,
                        "offset_from_face_m": 0.0, "edge_margin_m": 0.0, "diameter_mm": 152.0,
                        "subdrill_m": 1.0},
            )
        ).holes
        real = [Hole(id=h.id, row=h.row, col=h.col, collar=Point3(h.collar.x, h.collar.y, h.collar.z),
                     toe=Point3(h.toe.x, h.toe.y, h.toe.z), diameter_mm=h.diameter_mm) for h in holes]
        pts = [_pt(f"p{i}", h.collar.x + 0.05, h.collar.y) for i, h in enumerate(real)]
        res = match_survey(real, pts, block="", tol_collar_m=0.3)
        self.assertTrue(all(m.issue == "" and m.by == "nearest" for m in res))
        self.assertEqual(len(res), len(real))


if __name__ == "__main__":
    unittest.main()
