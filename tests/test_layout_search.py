"""Поиск раскладки по этапам: топ-3, бюджет, остановка, прогресс, отбраковка."""
import os
import unittest
from unittest import mock

from design.geometry import crest_azimuth_deg
from design.layout_search import search as search_module
from design.layout_search.evaluate import Evaluation, SearchContext, evaluate
from design.layout_search.search import search_layout
from design.layout_search.space import Candidate, is_back, stage1
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

        def counting(ctx, candidate, seen=None):
            calls["n"] += 1
            return real(ctx, candidate, seen)

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

        def counting(ctx, candidate, seen=None):
            calls["n"] += 1
            return real(ctx, candidate, seen)

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
                mock.patch.object(search_module, "stage3", lambda seeds, base, contour=None: stage3_calls.append(1) or []):
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
                mock.patch.object(search_module, "stage3", lambda seeds, base, contour=None: []):
            res = search_layout(_ctx(params), budget_s=1e9, stage2_seeds=2)
        self.assertTrue(res.all_rejected)
        self.assertEqual(len(res.best), 3)
        self.assertTrue(all(ev.rejected and ev.reject_codes for ev in res.best))
        self.assertEqual(res.rejected, res.evaluated)
        # «Все отбракованы» — флаг `all_rejected`; предупреждение ядра его не дублирует.
        self.assertFalse(any("отбраковк" in text for text in res.warnings))

    def test_floor_burden_excess_not_in_best_but_seeds_stage2(self):
        # Отступ 1,5 и 2 м — ЛСП больше W₀ + 3 % (брак), 1 м — в допуске. В итог
        # брак не идёт, а в семена этапа 2 — идёт: превышение ЛСП чинит пара.
        variants = [Candidate({**BASE, "offset_from_face_m": off}, "left") for off in (1.0, 1.5, 2.0)]
        seeds = []

        def stage2(found, base):
            seeds.extend(found)
            return list(found)

        with mock.patch.object(search_module, "stage1", lambda base, contour: variants), \
                mock.patch.object(search_module, "stage2", stage2), \
                mock.patch.object(search_module, "stage3", lambda seeds, base, contour=None: []):
            res = search_layout(_ctx(), budget_s=1e9, stage2_seeds=5)
        self.assertFalse(res.all_rejected)
        self.assertEqual(res.rejected, 2)
        self.assertEqual([ev.candidate.params["offset_from_face_m"] for ev in res.best], [1.0])
        self.assertEqual({c.params["offset_from_face_m"] for c in seeds}, {1.0, 1.5, 2.0})

    def test_all_rejected_by_floor_burden_excess_shows_best_rejected(self):
        variants = [Candidate({**BASE, "offset_from_face_m": off}, "left") for off in (1.5, 2.0)]
        with mock.patch.object(search_module, "stage1", lambda base, contour: variants), \
                mock.patch.object(search_module, "stage2", lambda seeds, base: list(seeds)), \
                mock.patch.object(search_module, "stage3", lambda seeds, base, contour=None: []):
            res = search_layout(_ctx(), budget_s=1e9)
        self.assertTrue(res.all_rejected)
        self.assertEqual(len(res.best), 2)
        self.assertTrue(all(ev.reject_codes == ["floor_burden_excess"] for ev in res.best))

    def test_no_free_face(self):
        contour = _rect_contour(40.0, 30.0, free_faces=(), face_angle_deg=75.0)
        res = search_layout(_ctx(contour=contour), budget_s=1e9, stage2_seeds=2, stage3_seeds=1)
        self.assertTrue(res.best)
        self.assertTrue(all(ev.lsp_out == 0 for ev in res.best))


def _small_stage1(base, contour):
    """Этап 1 без большей части вариантов: по 6 каждого шаблона (тесты быстрее)."""
    cands = stage1(base, contour)
    crest = [c for c in cands if not is_back(c.params)]
    back = [c for c in cands if is_back(c.params)]
    return crest[:6] + back[:6]


class TemplateSearchTests(unittest.TestCase):
    """Перебор пробует оба шаблона: от бровки и «от тыла» (PR 3)."""

    def _recorded(self, **kwargs):
        """Поиск с записью оценённых вариантов по этапам: [(этап, вариант)]."""
        stage = {"name": ""}
        seen = []
        real = search_module.evaluate

        def recording(ctx, candidate, cache=None):
            seen.append((stage["name"], candidate))
            return real(ctx, candidate, cache)

        def progress(name, done, total):
            stage["name"] = name

        with mock.patch.object(search_module, "evaluate", recording), \
                mock.patch.object(search_module, "stage1", _small_stage1):
            res = search_layout(_ctx(), progress=progress, **kwargs)
        return res, seen

    def test_both_templates_searched(self):
        res, seen = self._recorded(budget_s=1e9, stage2_seeds=2, stage3_seeds=1)
        self.assertFalse(res.stopped_early)
        by_stage = {}
        for name, candidate in seen:
            by_stage.setdefault(name, set()).add(is_back(candidate.params))
        # Геометрия и уточнение — оба шаблона; первый ряд у откоса — только от бровки.
        self.assertEqual(by_stage["geometry"], {False, True})
        self.assertEqual(by_stage["front_rows"], {False})
        self.assertEqual(by_stage["refine"], {False, True})
        for _, candidate in seen:
            if is_back(candidate.params):
                self.assertNotIn("front_rows_mode", candidate.params)
                self.assertNotIn("offset_from_face_m", candidate.params)

    def test_stage1_budget_shared(self):
        # Бюджет кончился на 20-й оценке этапа 1: шаблоны чередуются, каждому — половина.
        calls = {"n": 0}
        real = search_module.evaluate
        seen = []

        def counting(ctx, candidate, cache=None):
            calls["n"] += 1
            seen.append(candidate)
            return real(ctx, candidate, cache)

        with mock.patch.object(search_module, "evaluate", counting):
            res = search_layout(_ctx(), budget_s=100.0, clock=lambda: 0.0 if calls["n"] < 20 else 1000.0)
        self.assertTrue(res.stopped_early)
        self.assertEqual(sum(is_back(c.params) for c in seen), 10)
        self.assertEqual(sum(not is_back(c.params) for c in seen), 10)

    def test_refine_seeds_per_template(self):
        # Семена уточнения — лучшие каждого шаблона, а не только общий лидер.
        seeds_seen = []
        real_stage3 = search_module.stage3

        def spy(seeds, base, contour=None):
            seeds_seen.extend(seeds)
            return real_stage3(seeds, base, contour)

        with mock.patch.object(search_module, "stage3", spy), \
                mock.patch.object(search_module, "stage1", _small_stage1):
            search_layout(_ctx(), budget_s=1e9, stage2_seeds=2, stage3_seeds=2)
        self.assertEqual(sum(is_back(c.params) for c in seeds_seen), 2)
        self.assertEqual(sum(not is_back(c.params) for c in seeds_seen), 2)

    def test_crest_only_base_unchanged(self):
        # Шахматка — без шаблона «от тыла»: перебор как раньше.
        params = {**BASE, "pattern": "staggered"}
        evaluated = []
        real = search_module.evaluate

        def recording(ctx, candidate, cache=None):
            evaluated.append(candidate)
            return real(ctx, candidate, cache)

        flag = {"stop": False}

        def progress(stage, done, total):
            if stage == "geometry" and done == total:
                flag["stop"] = True

        with mock.patch.object(search_module, "evaluate", recording):
            search_layout(_ctx(params), budget_s=1e9, progress=progress, should_stop=lambda: flag["stop"])
        self.assertTrue(evaluated)
        self.assertFalse(any(is_back(c.params) for c in evaluated))

    def test_pattern_generated_once_for_both_flanks(self):
        # Фланг сетку не меняет: два фланга одного варианта строят сетку один раз.
        from design.layout_search import evaluate as evaluate_module

        ctx = _ctx()
        back = [c for c in stage1(BASE, CONTOUR) if is_back(c.params)][:1]
        pair = [Candidate(back[0].params, flank) for flank in ("left", "right")]
        calls = []
        real = evaluate_module.generate_pattern

        def counted(*args, **kwargs):
            calls.append(1)
            return real(*args, **kwargs)

        cache: dict = {}
        with mock.patch.object(evaluate_module, "generate_pattern", counted):
            left, right = (evaluate(ctx, c, cache) for c in pair)
        self.assertEqual(len(calls), 1)
        self.assertEqual(left.hole_count, right.hole_count)
        self.assertEqual(right.candidate.cut_flank, "right")
        self.assertIsNot(left.holes, right.holes)


@unittest.skipUnless(os.environ.get("BLASTEX_SLOW"), "медленный тест (≈1 мин): BLASTEX_SLOW=1")
class Block66SearchTests(unittest.TestCase):
    """Блок №66 с полным бюджетом: три лучших варианта не хуже базы без перебора.

    С 09.11.2026 превышение ЛСП — брак: на 66 оно есть у всех вариантов, в том
    числе у базы, поэтому и база, и итог отбракованы только им; итог — лучшие
    из отбракованных (`all_rejected`)."""

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
        # База без брака по геометрии (иначе сравнение с ней ничего не значит).
        self.assertTrue(all(set(ev.reject_codes) <= {"floor_burden_excess"} for ev in base_evals),
                        [ev.reject_codes for ev in base_evals])
        base_key = min(ev.rank_key() for ev in base_evals)

        res = search_layout(ctx, budget_s=150.0)
        self.assertEqual(len(res.best), 3)
        self.assertTrue(res.all_rejected)
        self.assertTrue(all(ev.reject_codes == ["floor_burden_excess"] for ev in res.best))
        self.assertLessEqual(res.best[0].rank_key(), base_key)


if __name__ == "__main__":
    unittest.main()
