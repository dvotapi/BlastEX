"""Поиск раскладки по этапам: топ-3, бюджет, остановка, прогресс, отбраковка."""
import unittest
from unittest import mock

from design.geometry import crest_azimuth_deg
from design.layout_search import search as search_module
from design.layout_search.evaluate import SearchContext
from design.layout_search.search import search_layout
from design.layout_search.space import stage1
from design.models import BlastDesign
from tests.front_rows_fixtures import _rect_contour

CONTOUR = _rect_contour(40.0, 30.0, face_angle_deg=75.0)
BASE = {
    "pattern": "rectangular",
    "spacing_a_m": 4.0,
    "burden_b_m": 4.0,
    "row_azimuth_deg": crest_azimuth_deg(CONTOUR),
    "offset_from_face_m": 1.0,
    "edge_margin_m": 1.0,
    "subdrill_m": 1.0,
}


def _ctx(params=None, contour=CONTOUR) -> SearchContext:
    design = BlastDesign(design_id="t", contour=contour, pattern_params=dict(BASE if params is None else params))
    return SearchContext.from_design(design)


class SearchTests(unittest.TestCase):
    def test_returns_top3_sorted(self):
        res = search_layout(_ctx(), budget_s=1e9)
        self.assertFalse(res.stopped_early)
        self.assertEqual(len(res.best), 3)
        keys = [ev.rank_key() for ev in res.best]
        self.assertEqual(keys, sorted(keys))
        grids = {tuple(sorted((round(h.collar.x, 2), round(h.collar.y, 2)) for h in ev.holes)) + (ev.candidate.cut_flank,)
                 for ev in res.best}
        self.assertEqual(len(grids), 3)
        self.assertGreater(res.evaluated, len(stage1(BASE, CONTOUR)))

    def test_budget_stops_early(self):
        calls = {"n": 0}
        real = search_module.evaluate

        def counting(ctx, candidate):
            calls["n"] += 1
            return real(ctx, candidate)

        # Часы показывают превышение бюджета после 10 оценок.
        clock = lambda: 0.0 if calls["n"] < 10 else 1000.0  # noqa: E731
        progress_stages = []
        with mock.patch.object(search_module, "evaluate", counting):
            res = search_layout(_ctx(), budget_s=100.0, clock=clock,
                                progress=lambda s, d, t: progress_stages.append(s))
        self.assertTrue(res.stopped_early)
        self.assertEqual(res.evaluated, 10)
        self.assertTrue(res.best)
        self.assertEqual(set(progress_stages), {"geometry"})

    def test_should_stop(self):
        flag = {"stop": False}

        def progress(stage, done, total):
            if stage == "geometry" and done == total:
                flag["stop"] = True

        res = search_layout(_ctx(), budget_s=1e9, progress=progress, should_stop=lambda: flag["stop"])
        self.assertTrue(res.stopped_early)
        self.assertEqual(res.evaluated, len(stage1(BASE, CONTOUR)))
        self.assertTrue(res.best)

    def test_progress_reports_stages(self):
        events = []
        search_layout(_ctx(), budget_s=1e9, stage2_seeds=2, stage3_seeds=1,
                      progress=lambda s, d, t: events.append((s, d, t)))
        order = []
        for stage, done, total in events:
            self.assertLessEqual(done, total)
            if not order or order[-1] != stage:
                order.append(stage)
        self.assertEqual(order, ["geometry", "front_rows", "refine"])

    def test_all_rejected_returns_best_rejected(self):
        # Отступ от кромки 3 м больше любого offset_from_face_m кандидатов
        # (этапы в штатном виде отступ не занижают или чинят схемой первого ряда,
        # поэтому этапы 1–3 подменены).
        from design.layout_search.space import Candidate

        params = {**BASE, "min_crest_offset_m": 3.0}
        tight = [Candidate({**params, "offset_from_face_m": off}, flank)
                 for off in (1.0, 1.25, 1.5, 2.0) for flank in ("left", "right")]
        with mock.patch.object(search_module, "stage1", lambda base, contour: tight), \
                mock.patch.object(search_module, "stage2", lambda seeds, base: list(seeds)), \
                mock.patch.object(search_module, "stage3", lambda seeds, base: []):
            res = search_layout(_ctx(params), budget_s=1e9, stage2_seeds=2)
        self.assertTrue(res.all_rejected)
        self.assertEqual(len(res.best), 3)
        self.assertTrue(all(ev.rejected and ev.reject_codes for ev in res.best))
        self.assertEqual(res.rejected, res.evaluated)

    def test_no_free_face(self):
        contour = _rect_contour(40.0, 30.0, free_faces=(), face_angle_deg=75.0)
        res = search_layout(_ctx(contour=contour), budget_s=1e9, stage2_seeds=2, stage3_seeds=1)
        self.assertTrue(res.best)
        self.assertTrue(all(ev.lsp_out == 0 for ev in res.best))


if __name__ == "__main__":
    unittest.main()
