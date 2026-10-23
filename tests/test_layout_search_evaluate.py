"""Оценка одного варианта раскладки: отбраковка, ЛСП по W₀, темп, окно 8 мс."""
import math
import unittest
from dataclasses import replace

import shapely

from design.analysis import collar_crest_warnings, validate
from design.geometry import crest_azimuth_deg
from design.layout_search.evaluate import (
    REJECT_CODES,
    Evaluation,
    SearchContext,
    evaluate,
    reject_codes_and_lsp,
)
from design.layout_search.space import Candidate, stage1
from design.models import BlastDesign, InitiationNetwork
from design.toe_line import crest_geometry, floor_report, min_crest_offset_m
from tests.front_rows_fixtures import (
    GAP_PATTERN,
    _contour_of,
    _rect_contour,
    design_with,
    grid_rows,
)
from tests.test_trunk_network import BLOCK66_PARAMS, _block66_contour

# Прямоугольник 40×30, грань — нижнее ребро y = 0, уступ 10 м, откос 75°:
# подошва в 10 / tg 75° ≈ 2,68 м от кромки, ЛСП первого ряда = отступ + 2,68 м.
CONTOUR = _rect_contour(40.0, 30.0, face_angle_deg=75.0)
BASE = {
    "pattern": "rectangular",
    "spacing_a_m": 4.0,
    "burden_b_m": 4.0,
    "row_azimuth_deg": crest_azimuth_deg(CONTOUR),
    "offset_from_face_m": 1.0,  # ЛСП ≈ 3,68 м — в коридоре [3,2; 4,12] при W₀ = 4
    "edge_margin_m": 1.0,
    "subdrill_m": 1.0,
}


def _ctx(params=None, **kwargs) -> SearchContext:
    design = BlastDesign(design_id="t", contour=CONTOUR, pattern_params=dict(BASE if params is None else params))
    return SearchContext.from_design(design, **kwargs)


def _evaluation(**overrides) -> Evaluation:
    values = dict(
        candidate=Candidate({}, "left"), holes=[], network=InitiationNetwork(), rejected=False,
        reject_codes=[], lsp_out=0, fast_share=0.0, converging_length_m=0.0, outside_share=0.0,
        robust_spread=0.1, hole_count=50, window8_max_holes=1, downhole_ms=500.0, warnings=[],
    )
    values.update(overrides)
    return Evaluation(**values)


class EvaluateTests(unittest.TestCase):
    def test_evaluate_basic(self):
        ev = evaluate(_ctx(), Candidate(dict(BASE), "left"))
        self.assertFalse(ev.rejected, ev.reject_codes)
        self.assertGreater(ev.hole_count, 0)
        self.assertEqual(ev.hole_count, len(ev.holes))
        self.assertIn(ev.downhole_ms, (500.0, 700.0, 1000.0))
        self.assertEqual(ev.fast_share, 0.0)
        self.assertGreaterEqual(ev.window8_max_holes, 1)
        self.assertEqual(ev.lsp_out, 0)

    def test_w0_fixed(self):
        # Отступ 1,5 м: ЛСП всех 9 скважин первого ряда ≈ 4,18 м. Это вне коридора
        # по W₀ = 4 (сверху 4,12), но внутри коридора по b варианта 4,12 (сверху
        # 4,2436): счёт по b дал бы 0.
        ctx = _ctx()
        self.assertEqual(ctx.w0_m, 4.0)
        params = {**BASE, "burden_b_m": 4.12, "offset_from_face_m": 1.5}
        ev = evaluate(ctx, Candidate(params, "left"))
        design = replace(ctx.design, holes=ev.holes, network=ev.network, pattern_params=params)
        burdens, _ = floor_report(design)
        self.assertEqual(len(burdens), 9)
        for item in burdens.values():
            self.assertAlmostEqual(item.value_m, 4.179, places=2)
        self.assertEqual(ev.lsp_out, 9)
        # Тот же вариант с W₀ = b варианта — ни одной скважины вне коридора.
        own_b = SearchContext.from_design(replace(ctx.design, pattern_params=params))
        self.assertEqual(evaluate(own_b, Candidate(params, "left")).lsp_out, 0)

    def test_w0_none_counts_nothing(self):
        params = {k: v for k, v in BASE.items() if k != "burden_b_m"}
        ctx = _ctx(params)
        self.assertIsNone(ctx.w0_m)
        self.assertEqual(evaluate(ctx, Candidate(params, "left")).lsp_out, 0)

    def test_reject_collar_too_close(self):
        ctx = _ctx({**BASE, "min_crest_offset_m": 3.0})
        params = {**BASE, "min_crest_offset_m": 3.0, "offset_from_face_m": 1.0}
        ev = evaluate(ctx, Candidate(params, "left"))
        self.assertTrue(ev.rejected)
        self.assertIn("collar_too_close_to_crest", ev.reject_codes)

    def test_collar_checked_without_keys_on_convex_crest(self):
        # Выпуклая бровка (мыс): откос — два первых ребра, без ключей отступа и
        # схемы. Отступ первого ряда меряется от средней точки бровки, концы
        # бровки позади — обычные ряды встают к ней вплотную. Перебор отступ
        # проверяет всегда (1 м), `validate` без ключей — нет.
        contour = _contour_of([(0, 4), (20, 0), (40, 4), (40, 30), (0, 30)], ((0, 1), (1, 2)), 75.0)
        base = {"pattern": "rectangular", "spacing_a_m": 4.0, "burden_b_m": 4.0,
                "row_azimuth_deg": 90.0, "edge_margin_m": 0.0, "subdrill_m": 1.0}
        ctx = SearchContext.from_design(BlastDesign(design_id="c", contour=contour, pattern_params=base))
        crest = crest_geometry(contour)
        close = 0
        for cand in stage1(base, contour):
            ev = evaluate(ctx, cand)
            grid = [h for h in ev.holes if h.enabled]
            nearest = float(shapely.distance(shapely.points([(h.collar.x, h.collar.y) for h in grid]), crest).min())
            too_close = nearest < 1.0 - 1e-6
            self.assertEqual("collar_too_close_to_crest" in ev.reject_codes, too_close, cand.params)
            if not too_close:
                continue
            close += 1
            self.assertTrue(ev.rejected)
            design = replace(ctx.design, holes=ev.holes, network=ev.network, pattern_params=cand.params)
            self.assertNotIn("collar_too_close_to_crest", {w["code"] for w in validate(design)})
            self.assertEqual(collar_crest_warnings(design), [])
        self.assertGreater(close, 0)

    def test_relief_none_ranks_worst(self):
        # Один ряд скважин — треугольников темпа нет: доли и стыки — inf.
        params = {**BASE, "offset_from_face_m": 1.0}
        contour = _rect_contour(20.0, 3.0, face_angle_deg=75.0)
        ctx = SearchContext.from_design(BlastDesign(design_id="t", contour=contour, pattern_params=params))
        ev = evaluate(ctx, Candidate(params, "left"))
        self.assertFalse(ev.rejected, ev.reject_codes)
        self.assertGreater(ev.hole_count, 0)
        self.assertEqual(ev.fast_share, math.inf)
        self.assertEqual(ev.converging_length_m, math.inf)
        self.assertEqual(ev.outside_share, math.inf)
        self.assertIsNone(ev.robust_spread)
        self.assertEqual(ev.rank_key()[2:6], (math.inf,) * 4)
        # Вариант с темпом, но хуже по всем его показателям, всё равно впереди.
        with_relief = _evaluation(fast_share=0.9, converging_length_m=500.0, outside_share=0.9,
                                  robust_spread=5.0, hole_count=ev.hole_count + 100)
        self.assertLess(with_relief.rank_key(), ev.rank_key())

    def test_empty_pattern_rejected(self):
        params = {**BASE, "spacing_a_m": 80.0, "burden_b_m": 80.0, "offset_from_face_m": 40.0}
        ev = evaluate(_ctx(), Candidate(params, "left"))
        self.assertTrue(ev.rejected)
        self.assertEqual(ev.reject_codes, ["empty"])
        self.assertEqual(ev.hole_count, 0)
        self.assertIsNone(ev.robust_spread)

    def test_rank_key_order(self):
        good = _evaluation()
        rejected = _evaluation(rejected=True, reject_codes=["floor_beyond_toe"], lsp_out=0, hole_count=1)
        worse_lsp = _evaluation(lsp_out=9, hole_count=999)
        self.assertLess(good.rank_key(), rejected.rank_key())
        self.assertLess(worse_lsp.rank_key(), rejected.rank_key())
        self.assertLess(_evaluation(hole_count=40).rank_key(), _evaluation(hole_count=41).rank_key())
        self.assertLess(_evaluation(robust_spread=0.5).rank_key(), _evaluation(robust_spread=None).rank_key())
        # Шум меньше шага округления порядок не решает.
        self.assertEqual(
            _evaluation(outside_share=0.1201).rank_key()[:5], _evaluation(outside_share=0.1199).rank_key()[:5]
        )
        self.assertEqual(
            _evaluation(converging_length_m=10.1).rank_key(), _evaluation(converging_length_m=9.9).rank_key()
        )
        # Окно 8 мс и внутрискважинное замедление в сравнении не участвуют.
        self.assertEqual(
            _evaluation(window8_max_holes=1, downhole_ms=500.0).rank_key(),
            _evaluation(window8_max_holes=7, downhole_ms=1000.0).rank_key(),
        )

    def test_relief_bounds_passed_through(self):
        cand = Candidate(dict(BASE), "left")
        base = evaluate(_ctx(), cand)
        strict = evaluate(_ctx(relief_min_ms_m=20.0), cand)
        self.assertEqual(base.fast_share, 0.0)
        self.assertGreater(strict.fast_share, 0.0)
        self.assertEqual(strict.hole_count, base.hole_count)

    def test_window8(self):
        params = {**BASE, "offset_from_face_m": 2.0, "edge_margin_m": 2.0}
        contour = _rect_contour(20.0, 16.0)
        design = BlastDesign(design_id="t", contour=contour, pattern_params=dict(params))
        ev = evaluate(SearchContext.from_design(design), Candidate(params, "left"))
        self.assertEqual(ev.hole_count, 16)
        self.assertEqual(ev.window8_max_holes, 1)
        self.assertTrue(math.isfinite(ev.downhole_ms))


class RejectEquivalenceTests(unittest.TestCase):
    """Отбраковка за один проход подошвы совпадает с кодами полного `validate`
    при заданном отступе от кромки: перебор проверяет устье всегда (без ключа —
    1 м), `validate` — только по ключам, поэтому ему отступ передаётся явно."""

    def _assert_same(self, design):
        codes, _ = reject_codes_and_lsp(design, 4.0)
        params = design.pattern_params or {}
        keyed = replace(design, pattern_params={**params, "min_crest_offset_m": min_crest_offset_m(params)})
        expected = sorted({w["code"] for w in validate(keyed)} & set(REJECT_CODES))
        self.assertEqual(codes, expected)
        return codes

    def _variant(self, contour, base, params, flank="left"):
        ctx = SearchContext.from_design(BlastDesign(design_id="t", contour=contour, pattern_params=dict(base)))
        ev = evaluate(ctx, Candidate(params, flank))
        self.assertEqual(ev.reject_codes, self._assert_same(
            replace(ctx.design, holes=ev.holes, network=ev.network, pattern_params=params)
        ))
        return ev

    def test_generated_variants(self):
        cases = [
            ({}, []),
            ({"min_crest_offset_m": 3.0}, ["collar_too_close_to_crest"]),
            ({"angle_deg": 30, "azimuth_deg": 180}, ["floor_beyond_toe"]),
            ({"burden_b_m": 4.12, "offset_from_face_m": 1.5}, []),
            ({"front_rows_mode": "taper", "front_rows_tilt_count": 2, "front_rows_tilt_deg": 30,
              "offset_from_face_m": 3.5}, []),
        ]
        for extra, codes in cases:
            with self.subTest(extra=extra):
                self.assertEqual(self._variant(CONTOUR, BASE, {**BASE, **extra}).reject_codes, codes)

    def test_row_gap_and_crest_on_hand_built_rows(self):
        # Первый ряд наклонён на 15° к откосу, устья второго не сдвинуты — разрыв у подошвы.
        design = design_with(grid_rows(15.0), pattern_params={**GAP_PATTERN, "min_crest_offset_m": 3.0})
        self.assertEqual(self._assert_same(design), ["collar_too_close_to_crest", "floor_row_gap_excess"])

    def test_block66(self):
        contour = _block66_contour()
        for extra in ({}, {"min_crest_offset_m": 3.0}):
            params = {**BLOCK66_PARAMS, **extra}
            for flank in ("left", "right"):
                with self.subTest(extra=extra, flank=flank):
                    ev = self._variant(contour, BLOCK66_PARAMS, params, flank)
                    self.assertGreater(ev.hole_count, 100)


if __name__ == "__main__":
    unittest.main()
