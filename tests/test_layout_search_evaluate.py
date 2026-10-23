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
    network_params,
    reject_codes_and_lsp,
    window_max_holes,
    wired_wall_holes,
    with_base_steps,
)
from design.layout_search.space import Candidate, stage1
from design.models import BlastDesign, DetonatingCord, Detonator, ElectronicChannel, InitiationNetwork
from design.pattern import generate_pattern
from design.timing import resolve_times
from design.toe_line import crest_geometry, floor_report, min_crest_offset_m
from design.trunk_network import build_trunk_chains_network
from tests.front_rows_fixtures import (
    GAP_PATTERN,
    _contour_of,
    _rect_contour,
    design_with,
    grid_rows,
    vertical_hole,
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
        # Окно — как у МИС (`analysis.charge_per_delay`): разница ≤ 8 мс — одно
        # окно. Скважины через ровно 8 мс (2·25 против 42 мс) в него попадают.
        params = {**BASE, "offset_from_face_m": 2.0, "edge_margin_m": 2.0}
        contour = _rect_contour(20.0, 16.0)
        design = BlastDesign(design_id="t", contour=contour, pattern_params=dict(params))
        ev = evaluate(SearchContext.from_design(design), Candidate(params, "left"))
        self.assertEqual(ev.hole_count, 16)
        self.assertEqual(ev.window8_max_holes, 2)
        self.assertTrue(math.isfinite(ev.downhole_ms))

    def test_window8_closed_like_charge_per_delay(self):
        self.assertEqual(window_max_holes({"a": 0.0, "b": 8.0}), 2)
        self.assertEqual(window_max_holes({"a": 0.0, "b": 8.01}), 1)
        self.assertEqual(window_max_holes({"a": 0.0, "b": 4.0, "c": 8.0, "d": 12.0}), 3)

    def test_network_system_from_base(self):
        # Система монтажа варианта — как у базовой сети; неизвестная — СИНВ.
        for system, expected in (("electronic", "electronic"), ("detcord", "detcord"), ("nonel", "nonel"),
                                 ("plasma", "nonel")):
            with self.subTest(system=system):
                design = BlastDesign(design_id="t", contour=CONTOUR, pattern_params=dict(BASE),
                                     network=InitiationNetwork(system=system))
                ev = evaluate(SearchContext.from_design(design), Candidate(dict(BASE), "left"))
                self.assertEqual(ev.network.system, expected)

    def test_walls_timed_when_base_network_wires_them(self):
        # Контурный ряд: в базовой сети связи к стенкам есть — у варианта стенки
        # получают время; базовая сеть без стенок — контурные времени не получают.
        params = {**BASE, "contour_row": True, "contour_spacing_m": 3.0}
        holes = generate_pattern(CONTOUR, params)
        walls_base = {h.id for h in holes if h.kind == "contour"}
        self.assertTrue(walls_base)
        wired, _ = build_trunk_chains_network(holes, {"include_contour": True})
        plain, _ = build_trunk_chains_network(holes, {})
        for network, timed in ((wired, True), (plain, False)):
            with self.subTest(timed=timed):
                design = BlastDesign(design_id="t", contour=CONTOUR, pattern_params=dict(params),
                                     holes=holes, network=network)
                ev = evaluate(SearchContext.from_design(design), Candidate(dict(params), "left"))
                walls = {h.id for h in ev.holes if h.kind == "contour"}
                self.assertTrue(walls)
                times, _ = resolve_times(ev.network, [h for h in ev.holes if h.enabled])
                self.assertEqual(walls <= set(times), timed)
                if not timed:
                    self.assertFalse(walls & set(times))


class MountingFromBaseTests(unittest.TestCase):
    """Стенки и замедление в скважине монтажа варианта — по базовой сети."""

    @staticmethod
    def _timed(ev, kind: str) -> tuple[set[str], set[str]]:
        walls = {h.id for h in ev.holes if h.kind == kind}
        times, _ = resolve_times(ev.network, [h for h in ev.holes if h.enabled])
        return walls, walls & set(times)

    def test_wired_presplit_does_not_wire_contour(self):
        # `include_contour` управляет только видом contour: пресплит в сеть входит
        # всегда, и его связи в базе не должны включать контурный ряд варианта.
        params = {**BASE, "contour_row": True, "contour_spacing_m": 3.0,
                  "presplit_row": True, "presplit_spacing_m": 3.0}
        holes = generate_pattern(CONTOUR, params)
        self.assertTrue({h.kind for h in holes} >= {"contour", "presplit"})
        network, _ = build_trunk_chains_network(holes, {})
        design = BlastDesign(design_id="t", contour=CONTOUR, pattern_params=dict(params),
                             holes=holes, network=network)
        self.assertFalse(network_params(design)["include_contour"])
        self.assertEqual(wired_wall_holes(design), [])
        ev = evaluate(SearchContext.from_design(design), Candidate(dict(params), "left"))
        contour, timed = self._timed(ev, "contour")
        self.assertTrue(contour)
        self.assertFalse(timed)
        presplit, timed = self._timed(ev, "presplit")
        self.assertTrue(presplit)
        self.assertEqual(timed, presplit)

    def test_wired_wall_holes_only_contour(self):
        params = {**BASE, "contour_row": True, "contour_spacing_m": 3.0,
                  "presplit_row": True, "presplit_spacing_m": 3.0}
        holes = generate_pattern(CONTOUR, params)
        network, _ = build_trunk_chains_network(holes, {"include_contour": True})
        design = BlastDesign(design_id="t", contour=CONTOUR, pattern_params=dict(params),
                             holes=holes, network=network)
        self.assertTrue(network_params(design)["include_contour"])
        wired = wired_wall_holes(design)
        self.assertTrue(wired)
        self.assertEqual({h.kind for h in wired}, {"contour"})

    def test_contour_default_kind_without_base_network(self):
        # Основная сетка строится видом contour: сеть варианта не пуста и без
        # флага `include_contour` — сетку берёт `main_kind`.
        params = {**BASE, "default_kind": "contour"}
        design = BlastDesign(design_id="t", contour=CONTOUR, pattern_params=dict(params))
        self.assertFalse(network_params(design)["include_contour"])
        ev = evaluate(SearchContext.from_design(design), Candidate(dict(params), "left"))
        self.assertTrue(ev.holes)
        self.assertTrue(ev.network.starters)
        self.assertTrue(ev.network.connectors)

    def test_contour_main_grid_base_network_does_not_wire_walls(self):
        # Базовая сеть монтирует основную сетку вида contour, но не отдельный
        # контурный ряд: это не «контурные скважины в сети», ряд в сеть
        # варианта не входит.
        params = {**BASE, "default_kind": "contour", "contour_row": True, "contour_spacing_m": 3.0}
        holes = generate_pattern(CONTOUR, params)
        walls = {h.id for h in holes if h.kind == "contour" and h.row < 0}
        self.assertTrue(walls)
        network, _ = build_trunk_chains_network(holes, {"main_kind": "contour"})
        design = BlastDesign(design_id="t", contour=CONTOUR, pattern_params=dict(params), holes=holes,
                             network=network)
        self.assertEqual(wired_wall_holes(design), [])
        self.assertFalse(network_params(design)["include_contour"])
        ev = evaluate(SearchContext.from_design(design), Candidate(dict(params), "left"))
        times, _ = resolve_times(ev.network, ev.holes)
        self.assertFalse({h.id for h in ev.holes if h.kind == "contour" and h.row < 0} & set(times))
        self.assertTrue(any(c.delay_ms == 25.0 for c in ev.network.surface_connectors))

    def test_contour_main_grid_gets_trunk(self):
        # Основная сетка вида contour — члены столбцов: магистраль 25 мс по
        # головам, а не дерево «прочих» по 42 мс.
        params = {**BASE, "default_kind": "contour"}
        design = BlastDesign(design_id="t", contour=CONTOUR, pattern_params=dict(params))
        self.assertEqual(network_params(design)["main_kind"], "contour")
        ev = evaluate(SearchContext.from_design(design), Candidate(dict(params), "left"))
        self.assertTrue(all(h.kind == "contour" for h in ev.holes))
        self.assertTrue(any(c.delay_ms == 25.0 for c in ev.network.surface_connectors))
        self.assertEqual(len(ev.network.starters), 1)
        production = evaluate(_ctx(), Candidate(dict(BASE), "left"))
        times, _ = resolve_times(ev.network, ev.holes)
        base_times, _ = resolve_times(production.network, production.holes)
        xy = lambda holes, t: sorted((round(h.collar.x, 6), round(h.collar.y, 6), t[h.id]) for h in holes)
        self.assertEqual(xy(ev.holes, times), xy(production.holes, base_times))

    def test_stab_main_grid_gets_trunk(self):
        # Основная сетка вида stab — члены столбцов: магистраль 25 мс.
        params = {**BASE, "default_kind": "stab"}
        design = BlastDesign(design_id="t", contour=CONTOUR, pattern_params=dict(params))
        self.assertEqual(network_params(design)["main_kind"], "stab")
        ev = evaluate(SearchContext.from_design(design), Candidate(dict(params), "left"))
        self.assertTrue(ev.holes and all(h.kind == "stab" for h in ev.holes))
        self.assertTrue(any(c.delay_ms == 25.0 for c in ev.network.surface_connectors))
        self.assertEqual(len(ev.network.starters), 1)

    def test_contour_wired_by_cord_or_electronic(self):
        # Контурный ряд, смонтированный шнуром ДШ или электронными временами,
        # — тоже «контурные скважины в сети».
        params = {**BASE, "contour_row": True, "contour_spacing_m": 3.0}
        holes = generate_pattern(CONTOUR, params)
        walls = [h.id for h in holes if h.kind == "contour"]
        self.assertTrue(walls)
        networks = {
            "cord": InitiationNetwork(system="detcord", detonating_cords=[DetonatingCord(id="c1", hole_ids=walls)]),
            "times": InitiationNetwork(system="electronic", electronic_times_ms={walls[0]: 10.0}),
            "channels": InitiationNetwork(
                system="electronic", electronic_channels=[ElectronicChannel(id="e1", hole_id=walls[-1], time_ms=5.0)]
            ),
        }
        for name, network in networks.items():
            design = BlastDesign(design_id="t", contour=CONTOUR, pattern_params=dict(params), holes=holes,
                                 network=network)
            self.assertTrue(network_params(design)["include_contour"], msg=name)
            self.assertTrue(wired_wall_holes(design), msg=name)

    def test_contour_main_grid_checked(self):
        # Основная сетка вида contour проверяется как рядовая: отступ устья и ЛСП.
        params = {**BASE, "default_kind": "contour", "min_crest_offset_m": 3.0}
        ev = evaluate(_ctx(params), Candidate(dict(params), "left"))
        self.assertIn("collar_too_close_to_crest", ev.reject_codes)
        params = {**BASE, "default_kind": "contour", "offset_from_face_m": 1.5}
        self.assertEqual(evaluate(_ctx(params), Candidate(params, "left")).lsp_out, 9)

    def test_downhole_delay_from_base_network(self):
        # У ДШ и электронной замедление в скважине — из базовой сети, а не умолчание системы.
        cases = (
            ("timing_params", InitiationNetwork(system="detcord", timing_params={"downhole_delay_ms": 42.0}), 42.0),
            ("downhole_delay_ms", InitiationNetwork(system="electronic", downhole_delay_ms={"1-01": 17.0}), 17.0),
            ("detonators", InitiationNetwork(
                system="electronic", detonators=[Detonator(id="d1", hole_id="1-01", delay_ms=9.0)]), 9.0),
            ("none", InitiationNetwork(system="detcord"), 0.0),
        )
        for name, network, expected in cases:
            with self.subTest(source=name):
                design = BlastDesign(design_id="t", contour=CONTOUR, pattern_params=dict(BASE), network=network)
                ev = evaluate(SearchContext.from_design(design), Candidate(dict(BASE), "left"))
                self.assertEqual(ev.downhole_ms, expected)

    def test_nonel_ignores_base_downhole(self):
        # У СИНВ замедление выбирает построитель (500/700/1000 мс), поле базы не передаётся.
        network = InitiationNetwork(system="nonel", timing_params={"downhole_delay_ms": 42.0})
        design = BlastDesign(design_id="t", contour=CONTOUR, pattern_params=dict(BASE), network=network)
        self.assertNotIn("downhole_delay_ms", network_params(design))
        ev = evaluate(SearchContext.from_design(design), Candidate(dict(BASE), "left"))
        self.assertIn(ev.downhole_ms, (500.0, 700.0, 1000.0))


class BaseStepsTests(unittest.TestCase):
    """Разрыв у подошвы — от шагов базы, как W₀ для ЛСП: «шаг + 3 %» не растёт с b варианта."""

    @staticmethod
    def _rows(gap: float) -> list:
        return [vertical_hole(f"{r + 1}-{c + 1:02d}", x, 4.0 + gap * r, r)
                for r in range(4) for c, x in enumerate((8.0, 12.0, 16.0, 20.0, 24.0))]

    def test_with_base_steps(self):
        variant = {**GAP_PATTERN, "spacing_a_m": 4.12, "burden_b_m": 3.605, "offset_from_face_m": 2.0}
        self.assertEqual(with_base_steps(variant, GAP_PATTERN), {**variant, "spacing_a_m": 4.0, "burden_b_m": 3.5})
        # Шага нет в базе — нет и в паспорте проверки (умолчание генератора).
        square = with_base_steps({"pattern": "square", "spacing_a_m": 5.15}, {"pattern": "square"})
        self.assertEqual(square, {"pattern": "square"})

    def test_row_gap_from_base_b(self):
        b0 = GAP_PATTERN["burden_b_m"]
        variant = {**GAP_PATTERN, "burden_b_m": round(b0 * 1.03, 4)}
        for gap, codes in ((1.05 * b0, ["floor_row_gap_excess"]), (1.02 * b0, [])):
            with self.subTest(gap=gap):
                design = replace(design_with(self._rows(gap)), pattern_params=variant)
                # По b варианта (допуск 1,03·1,03·b₀) разрыв 1,05·b₀ в допуске.
                self.assertEqual(reject_codes_and_lsp(design, b0)[0], [])
                checked = replace(design, pattern_params=with_base_steps(variant, GAP_PATTERN))
                self.assertEqual(reject_codes_and_lsp(checked, b0)[0], codes)


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
        # Паспорт проверки — шаги базы, скважины варианта (как в `evaluate`).
        self.assertEqual(ev.reject_codes, self._assert_same(
            replace(ctx.design, holes=ev.holes, network=ev.network, pattern_params=with_base_steps(params, base))
        ))
        return ev

    def test_generated_variants(self):
        cases = [
            ({}, []),
            ({"min_crest_offset_m": 3.0}, ["collar_too_close_to_crest"]),
            ({"angle_deg": 30, "azimuth_deg": 180}, ["floor_beyond_toe"]),
            ({"burden_b_m": 4.12, "offset_from_face_m": 1.5}, []),
            # b на 5 % больше базы: разрыв у подошвы больше b₀ + 3 %.
            ({"burden_b_m": 4.2}, ["floor_row_gap_excess"]),
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
