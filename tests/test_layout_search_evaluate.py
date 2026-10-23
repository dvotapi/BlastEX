"""Оценка одного варианта раскладки: отбраковка, ЛСП по W₀, темп, окно 8 мс."""
import math
import unittest
from dataclasses import replace

from design.geometry import crest_azimuth_deg
from design.layout_search.evaluate import Evaluation, SearchContext, evaluate
from design.layout_search.space import Candidate
from design.models import BlastDesign, InitiationNetwork
from design.toe_line import floor_report
from tests.front_rows_fixtures import _rect_contour

# Прямоугольник 40×30, грань — нижнее ребро y = 0, уступ 10 м.
CONTOUR = _rect_contour(40.0, 30.0)
BASE = {
    "pattern": "rectangular",
    "spacing_a_m": 4.0,
    "burden_b_m": 4.0,
    "row_azimuth_deg": crest_azimuth_deg(CONTOUR),
    "offset_from_face_m": 2.0,
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

    def test_w0_fixed(self):
        ctx = _ctx()
        self.assertEqual(ctx.w0_m, 4.0)
        params = {**BASE, "burden_b_m": round(4.0 * 1.03, 4)}
        ev = evaluate(ctx, Candidate(params, "left"))
        design = replace(ctx.design, holes=ev.holes, network=ev.network, pattern_params=params)
        burdens, _ = floor_report(design)
        expected = sum(
            1 for item in burdens.values()
            if item.beyond_toe or not (0.8 * 4.0 - 1e-6 <= item.value_m <= 1.03 * 4.0 + 1e-6)
        )
        self.assertGreater(len(burdens), 0)
        self.assertEqual(ev.lsp_out, expected)

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


if __name__ == "__main__":
    unittest.main()
