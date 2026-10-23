"""Поиск раскладки по этапам: топ-3, бюджет, остановка, прогресс, отбраковка."""
import os
import unittest
from unittest import mock

from design.geometry import crest_azimuth_deg
from design.layout_search import search as search_module
from design.layout_search.evaluate import Evaluation, SearchContext, evaluate
from design.layout_search.search import search_layout
from design.layout_search.space import Candidate, stage1
from design.models import BlastDesign, InitiationNetwork
from design.toe_line import min_crest_offset_m
from tests.front_rows_fixtures import _rect_contour, vertical_hole
from tests.test_trunk_network import BLOCK66_PARAMS, _block66_contour

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

    def test_budget_in_stage1_warns_big_block(self):
        # Бюджет кончился в этапе 1 — блок большой; остановка по запросу или
        # бюджет, кончившийся позже, такого пояснения не дают.
        calls = {"n": 0}
        real = search_module.evaluate

        def counting(ctx, candidate):
            calls["n"] += 1
            return real(ctx, candidate)

        stage1_total = len(stage1(BASE, CONTOUR))
        cases = (
            ({"budget_s": 100.0, "clock": lambda: 0.0 if calls["n"] < 10 else 1000.0}, True),
            ({"budget_s": 100.0, "clock": lambda: 0.0 if calls["n"] < stage1_total + 5 else 1000.0}, False),
            ({"budget_s": 1e9, "should_stop": lambda: calls["n"] >= 10}, False),
        )
        for kwargs, big in cases:
            calls["n"] = 0
            with self.subTest(big=big, n=len(kwargs)), mock.patch.object(search_module, "evaluate", counting):
                res = search_layout(_ctx(), **kwargs)
                self.assertTrue(res.stopped_early)
                self.assertTrue(res.best)
                self.assertEqual(search_module.BIG_BLOCK in res.warnings, big, res.warnings)

    def test_seeds_distinct_grids(self):
        # Два варианта с одной сеткой (те же устья и фланг) — одно семя.
        holes = [vertical_hole("1", 1.0, 2.0, 0), vertical_hole("2", 5.0, 2.0, 0)]
        shifted = [vertical_hole("1", 1.0, 3.0, 0), vertical_hole("2", 5.0, 3.0, 0)]

        def ev(params, grid, flank="left", count=10):
            return Evaluation(
                candidate=Candidate(params, flank), holes=grid, network=InitiationNetwork(), rejected=False,
                reject_codes=[], lsp_out=0, fast_share=0.0, converging_length_m=0.0, outside_share=0.0,
                robust_spread=0.1, hole_count=count, window8_max_holes=1, downhole_ms=500.0,
            )

        evaluations = [ev({"k": 1}, holes, count=1), ev({"k": 2}, holes, count=2),
                       ev({"k": 3}, shifted, count=3), ev({"k": 4}, holes, "right", count=4)]
        seeds = search_module._seeds(evaluations, 3)
        self.assertEqual([s.params["k"] for s in seeds], [1, 3, 4])

    def test_should_stop(self):
        flag = {"stop": False}

        def progress(stage, done, total):
            if stage == "geometry" and done == total:
                flag["stop"] = True

        res = search_layout(_ctx(), budget_s=1e9, progress=progress, should_stop=lambda: flag["stop"])
        self.assertTrue(res.stopped_early)
        self.assertEqual(res.evaluated, len(stage1(BASE, CONTOUR)))
        self.assertTrue(res.best)
        # Об остановке говорит флаг `stopped_early` (интерфейс даёт одну пометку),
        # а не предупреждение ядра.
        self.assertFalse(any("остановлен" in text for text in res.warnings))

    def test_zero_budget_nothing_evaluated(self):
        for kwargs in ({"budget_s": 0.0}, {"budget_s": -1.0}, {"budget_s": 1e9, "should_stop": lambda: True}):
            with self.subTest(kwargs=kwargs):
                res = search_layout(_ctx(), **kwargs)
                self.assertTrue(res.stopped_early)
                self.assertEqual(res.evaluated, 0)
                self.assertEqual(res.best, [])
                self.assertFalse(res.all_rejected)
                self.assertEqual(res.warnings, [search_module.NOTHING_EVALUATED])

    def test_stop_checked_at_stage_start(self):
        # Этап 2 без новых вариантов: остановка, запрошенная после этапа 1,
        # срабатывает в начале этапа, и этап 3 не строится.
        stage3_calls = []
        flag = {"stop": False}

        def progress(stage, done, total):
            if stage == "geometry" and done == total:
                flag["stop"] = True

        with mock.patch.object(search_module, "stage2", lambda seeds, base: []), \
                mock.patch.object(search_module, "stage3", lambda seeds, base: stage3_calls.append(1) or []):
            res = search_layout(_ctx(), budget_s=1e9, progress=progress, should_stop=lambda: flag["stop"])
        self.assertTrue(res.stopped_early)
        self.assertEqual(stage3_calls, [])
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
        # «Все отбракованы» — флаг `all_rejected`; предупреждение ядра его не дублирует.
        self.assertFalse(any("отбраковк" in text for text in res.warnings))

    def test_no_free_face(self):
        contour = _rect_contour(40.0, 30.0, free_faces=(), face_angle_deg=75.0)
        res = search_layout(_ctx(contour=contour), budget_s=1e9, stage2_seeds=2, stage3_seeds=1)
        self.assertTrue(res.best)
        self.assertTrue(all(ev.lsp_out == 0 for ev in res.best))


@unittest.skipUnless(os.environ.get("BLASTEX_SLOW"), "медленный тест (≈1 мин): BLASTEX_SLOW=1")
class Block66SearchTests(unittest.TestCase):
    """Блок №66 с полным бюджетом: три прошедших варианта не хуже базы без перебора."""

    def test_best_not_worse_than_base(self):
        contour = _block66_contour()
        ctx = SearchContext.from_design(
            BlastDesign(design_id="66", contour=contour, pattern_params=dict(BLOCK66_PARAMS))
        )
        # База без перебора — вариант этапа 1 при k = 0: азимут бровки, без
        # сдвига, отступ o₀; фланг — лучший из двух.
        azimuth = round(crest_azimuth_deg(contour) % 360.0, 4)
        o0 = min_crest_offset_m(BLOCK66_PARAMS)
        bases = [
            c for c in stage1(BLOCK66_PARAMS, contour)
            if c.params["row_azimuth_deg"] == azimuth
            and "grid_shift_along_m" not in c.params
            and abs(c.params["offset_from_face_m"] - o0) < 1e-9
        ]
        self.assertEqual({c.cut_flank for c in bases}, {"left", "right"})
        self.assertEqual(len(bases), 2)
        base_evals = [evaluate(ctx, c) for c in bases]
        # Сама база отбраковку проходит (иначе сравнение с ней ничего не значит).
        self.assertTrue(all(not ev.rejected for ev in base_evals), [ev.reject_codes for ev in base_evals])
        base_key = min(ev.rank_key() for ev in base_evals)

        res = search_layout(ctx, budget_s=150.0)
        self.assertEqual(len(res.best), 3)
        self.assertTrue(all(not ev.rejected for ev in res.best))
        self.assertLessEqual(res.best[0].rank_key(), base_key)


if __name__ == "__main__":
    unittest.main()
