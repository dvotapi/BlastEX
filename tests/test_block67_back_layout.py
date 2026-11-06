"""Блок 67 (чертёж 04.11.2026): шаблон «от тыла» против раскладки от бровки.

Фикстура `fixtures/cad/block67_lines.json` — контур по линии «граница блока»,
верхняя и нижняя бровки; координаты сдвинуты (начало — минимум x, y контура,
отметки как есть; разрешение владельца 06.11.2026). Нижний контур —
`two_contours` с замыканием фланга (PR #149).
"""
from __future__ import annotations

import itertools
import json
import math
import statistics
from functools import lru_cache
from pathlib import Path

import pytest
import shapely

from design.analysis import validate
from design.back_layout import back_azimuth_deg
from design.models import BlastDesign, BlockContour
from design.pattern import generate_pattern
from design.spatial.cad.stitch import StitchedLine
from design.spatial.cad.two_contours import two_contours
from design.toe_line import crest_geometry, floor_burdens

FIXTURE = Path(__file__).parent / "fixtures" / "cad" / "block67_lines.json"
REJECT = {"floor_beyond_toe", "floor_row_gap_excess", "collar_too_close_to_crest"}
W = 3.8


@lru_cache(maxsize=1)
def _contour() -> BlockContour:
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    ring = [tuple(p) for p in data["ring"]]
    two = two_contours(
        ring,
        [StitchedLine(points=[tuple(p) for p in line]) for line in data["tops"]],
        [StitchedLine(points=[tuple(p) for p in line]) for line in data["bottoms"]],
    )
    return BlockContour.from_dict(
        {
            "vertices": [{"x": x, "y": y, "z": 0.0} for x, y in ring],
            "free_faces": [list(edge) for edge in two.free_faces],
            "bench": {"crest_z_m": 410.015, "toe_z_m": 401.184, "face_angle_deg": 75.0},
            "cad": {"bottom": [list(p) for p in two.bottom], "edited": False},
        }
    )


def _base() -> dict:
    return {
        "pattern": "rectangular",
        "spacing_a_m": 3.811,
        "burden_b_m": W,
        "row_azimuth_deg": back_azimuth_deg(_contour()),
        "subdrill_m": 1.0,
        # Явно: умолчание бэкенда меняется отдельным PR (решение владельца 06.11.2026).
        "min_crest_offset_m": 0.5,
    }


def _tilt(hole) -> float:
    return math.degrees(
        math.atan2(math.hypot(hole.toe.x - hole.collar.x, hole.toe.y - hole.collar.y), hole.collar.z - hole.toe.z)
    )


def _report(params: dict):
    contour = _contour()
    holes = generate_pattern(contour, params)
    design = BlastDesign(design_id="b67", contour=contour, holes=holes, pattern_params=params)
    burdens = floor_burdens(design)
    crest = crest_geometry(contour)
    front = [h for h in holes if h.id in burdens]
    distances = [float(shapely.distance(shapely.Point(h.collar.x, h.collar.y), crest)) for h in front]
    return {
        "median_m": statistics.median(distances),
        "tilted": sum(_tilt(h) > 0.5 for h in holes),
        "codes": {w["code"] for w in validate(design)},
        "in_corridor": sum(1 for v in burdens.values() if not v.excess and not v.short) / len(burdens),
    }


def test_fixture_is_local_and_has_the_face():
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    coords = [abs(v) for p in data["ring"] for v in p]
    coords += [abs(v) for line in data["tops"] + data["bottoms"] for p in line for v in p[:2]]
    assert max(coords) < 1000.0
    assert min(p[0] for p in data["ring"]) == 0.0 and min(p[1] for p in data["ring"]) == 0.0
    assert _contour().free_faces == [[k, k + 1] for k in range(3, 16)]
    assert back_azimuth_deg(_contour()) == pytest.approx(179.81, abs=0.01)


def test_block67_back_layout_beats_crest_layout():
    """Устья первого ряда не дальше от бровки, чем у пары, отбраковки нет, ЛСП
    в коридоре — у половины первого ряда.

    Пара у откоса сама сдвигает устье к кромке (PR #153), поэтому медиана
    расстояния устья до бровки у обоих шаблонов — отступ 0,5 м; у пары после
    сдвига наклонных 15, ЛСП в коридоре — 41 %.

    Доля ЛСП в коридоре на блоке 67 у шаблона «от тыла» ниже, чем у пары от
    бровки: подошва здесь в 3,2–4,8 м от бровки (≈ W), и там, где последний
    узел эшелона в 0,7–1,5 м от бровки, ни остатку (станок — не ближе 1 м к
    последней, устье — не ближе 0,5 м к бровке), ни наклону последней (разрыв
    у подошвы ≤ b + 3 %) места нет. Вертикальный остаток с ЛСП > W + 3 %
    уступает наклонному в допуске (Codex, PR #154): ЛСП в коридоре 24 → 48 %,
    наклонных 15 → 21 (у пары — 18). Шаблоны сравнивает перебор (PR 3).
    """
    back = _report({**_base(), "layout_anchor": "back"})
    crest = _report({**_base(), "front_rows_mode": "pair"})
    assert back["median_m"] <= crest["median_m"] + 1e-3
    assert not back["codes"] & REJECT, back["codes"]
    assert back["in_corridor"] > 0.4


@pytest.mark.parametrize(
    "offset, shift, turn",
    list(itertools.product([1.9, 2.28, 2.66, 3.04], [0.0, 0.95, 1.9, 2.86], [-5.0, 0.0, 5.0])),
)
def test_block67_back_variants_are_not_rejected(offset, shift, turn):
    """Подстройка перебора (отступ от тыла, сдвиг, поворот ±5°): генератор не
    даёт разрыва у подошвы, выхода за подошву и устья у кромки."""
    params = {
        **_base(),
        "layout_anchor": "back",
        "back_offset_m": offset,
        "grid_shift_along_m": shift,
        "row_azimuth_deg": _base()["row_azimuth_deg"] + turn,
    }
    report = _report(params)
    assert not report["codes"] & REJECT, report["codes"]


def test_block66_back_layout_compared_with_crest_layout():
    """Блок 66 (`fixtures/cad/block66.dxf`): сравнение шаблонов. Тыл — западная
    сторона; «от тыла» не хуже по доле ЛСП в коридоре, без отбраковки."""
    from tests.test_trunk_network import BLOCK66_PARAMS, _block66_contour

    contour = _block66_contour()
    azimuth = back_azimuth_deg(contour)
    assert azimuth == pytest.approx(167.3, abs=0.1)

    def share(params):
        holes = generate_pattern(contour, params)
        design = BlastDesign(design_id="b66", contour=contour, holes=holes, pattern_params=params)
        burdens = floor_burdens(design)
        codes = {w["code"] for w in validate(design)}
        return sum(1 for v in burdens.values() if not v.excess and not v.short) / len(burdens), codes

    back, back_codes = share({**BLOCK66_PARAMS, "row_azimuth_deg": azimuth, "layout_anchor": "back"})
    crest, _ = share({**BLOCK66_PARAMS, "front_rows_mode": "pair"})
    assert not back_codes & REJECT, back_codes
    assert back >= crest


def test_block67_back_layout_fires_from_the_crest():
    """Монтаж «магистраль + цепочки» и стабилизация на шаблоне «от тыла» — от
    бровки, как у раскладки от бровки: ряд 0 — у откоса (финальное ревью PR 2)."""
    from design.timing import resolve_times
    from design.trunk_network import build_trunk_chains_network

    contour = _contour()
    crest = crest_geometry(contour)
    params = {**_base(), "layout_anchor": "back", "stab_row": True}
    holes = generate_pattern(contour, params)
    network, _ = build_trunk_chains_network(holes, {"main_kind": "production"})
    times, _ = resolve_times(network, holes)
    by_id = {h.id: h for h in holes}

    def to_crest(hole_id):
        hole = by_id[hole_id]
        return float(shapely.distance(shapely.Point(hole.collar.x, hole.collar.y), crest))

    order = sorted(times, key=times.get)
    early = statistics.mean(to_crest(k) for k in order[:8])
    late = statistics.mean(to_crest(k) for k in order[-8:])
    assert early < late
    stab = [h for h in holes if h.kind == "stab"]
    assert stab and statistics.mean(to_crest(h.id) for h in stab) < 6.0


def test_block67_back_layout_toe_queries_are_bounded(monkeypatch):
    """Перебор (PR 3) зовёт генератор сотни раз: ЛСП считается пакетами, а
    деления пополам останавливаются по точности — не больше 300 запросов к
    линии подошвы на генерацию блока 67 (0,12 с; наклонный остаток вместо
    вертикального с ЛСП > W + 3 % — около 290, без него было около 150)."""
    import design.back_layout as back_layout
    import design.pattern as pattern
    import design.toe_line as toe_line

    calls = []
    original = toe_line.toe_positions

    def counted(*args, **kwargs):
        calls.append(1)
        return original(*args, **kwargs)

    for module in (toe_line, back_layout, pattern):
        monkeypatch.setattr(module, "toe_positions", counted)
    generate_pattern(_contour(), {**_base(), "layout_anchor": "back"})
    assert len(calls) <= 300, len(calls)


def _block(name: str):
    """Контур и базовые параметры блока для перебора; отступ от кромки — явно."""
    if name == "67":
        return _contour(), _base()
    from tests.test_trunk_network import BLOCK66_PARAMS, _block66_contour

    return _block66_contour(), {**BLOCK66_PARAMS, "min_crest_offset_m": 0.5}


def _search_ctx(contour, params):
    from design.layout_search.evaluate import SearchContext

    return SearchContext.from_design(BlastDesign(design_id="search", contour=contour, pattern_params=dict(params)))


@pytest.mark.parametrize("block", ["67", "66"])
def test_search_back_variants_pass(block):
    """Перебор (PR 3): варианты «от тыла» этапа 1 на блоках 67 и 66 — у тыла,
    без отбраковки; у варианта от бровки того же блока — свой ключ опоры нет."""
    from design.layout_search.evaluate import evaluate
    from design.layout_search.space import is_back, stage1

    contour, base = _block(block)
    ref = back_azimuth_deg(contour)
    cands = stage1(base, contour)
    back = [
        c for c in cands
        if is_back(c.params) and c.cut_flank == "left" and "grid_shift_along_m" not in c.params
        and abs((c.params["row_azimuth_deg"] - ref + 180.0) % 360.0 - 180.0) < 1e-3
    ]
    assert len(back) == 4
    assert any(not is_back(c.params) for c in cands)
    ctx = _search_ctx(contour, base)
    cache: dict = {}
    for candidate in back:
        ev = evaluate(ctx, candidate, cache)
        assert not ev.rejected, (candidate.params["back_offset_m"], ev.reject_codes)
        assert ev.hole_count > 0
        assert ev.candidate.params["layout_anchor"] == "back"


@pytest.mark.skipif(not __import__("os").environ.get("BLASTEX_SLOW"), reason="медленный тест (≈2 мин): BLASTEX_SLOW=1")
@pytest.mark.parametrize("block", ["67", "66"])
def test_full_search_tries_both_templates(block):
    """Полный перебор блока с бюджетом 150 с: оба шаблона оценены и проходят
    отбраковку, итог — лучшие из обоих, бюджет хватает на все этапы."""
    from unittest import mock

    from design.layout_search import search as search_module
    from design.layout_search.space import is_back

    contour, base = _block(block)
    evaluations = []
    real = search_module.evaluate

    def recording(ctx, candidate, cache=None):
        ev = real(ctx, candidate, cache)
        evaluations.append(ev)
        return ev

    with mock.patch.object(search_module, "evaluate", recording):
        res = search_module.search_layout(_search_ctx(contour, base), budget_s=150.0)
    assert not res.stopped_early, res.elapsed_s
    assert len(res.best) == 3
    assert all(not ev.rejected for ev in res.best)
    best_by_template = {}
    for ev in evaluations:
        if ev.rejected:
            continue
        key = is_back(ev.candidate.params)
        if key not in best_by_template or ev.rank_key() < best_by_template[key].rank_key():
            best_by_template[key] = ev
    assert set(best_by_template) == {False, True}
    assert res.best[0].rank_key() <= min(ev.rank_key() for ev in best_by_template.values())


@pytest.mark.parametrize("block", ["67", "66"])
def test_search_refines_around_edge_turn_seed(block):
    """Семя на краю поворота (±5°): азимут округлён до 0,0001°, но подстройка
    отступа и сдвига при азимуте самого семени не теряется (ревью PR 3)."""
    from design.layout_search.space import is_back, stage1, stage3

    contour, base = _block(block)
    ref = back_azimuth_deg(contour)

    def turn(c):
        return (c.params["row_azimuth_deg"] - ref + 180.0) % 360.0 - 180.0

    for sign in (1.0, -1.0):
        edge = next(c for c in stage1(base, contour) if is_back(c.params) and abs(turn(c) - 5.0 * sign) < 1e-3)
        out = stage3([edge], base, contour)
        same_azimuth = [c for c in out if c.params["row_azimuth_deg"] == edge.params["row_azimuth_deg"]]
        offsets = {c.params["back_offset_m"] for c in same_azimuth}
        assert len(offsets) >= 2, (sign, offsets)
        assert all(abs(turn(c)) <= 5.0 + 1e-3 for c in out)
