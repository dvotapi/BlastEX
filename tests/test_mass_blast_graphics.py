"""Данные графической части Г.1–Г.5 проекта МВ (TASK-018, PR 4) на блоке 66.

Рендер ничего не считает: разрезы, времена сети, колонки и заходки СЗМ,
кольца опасных зон и точки постов — данные контекста v2 (`design/mass_blast_graphics.py`).
"""
from __future__ import annotations

import copy
import math

import pytest
from shapely.geometry import MultiPoint, Point, Polygon

from design.mass_blast_graphics import block_graphics, project_graphics
from design.models import BlockContour
from design.timing import resolve_network
from design.trunk_network import build_trunk_chains_network
from tests.mass_blast_block66 import context66, design66, payload66


def _trunk66():
    design = design66()
    design.network, _warnings = build_trunk_chains_network(design.holes, {"system": "nonel", "downhole_delay_ms": 700})
    return design


@pytest.fixture(scope="module")
def context():
    return context66(_trunk66())


@pytest.fixture(scope="module")
def graphics(context):
    return context["blocks_v2"][0]["graphics"]


def test_context_keeps_graphics_of_block_and_project(context, graphics):
    assert graphics["version"] == "graphics-v1"
    assert graphics["contour_source"] == "design"
    assert len(graphics["holes"]) == 196
    assert context["graphics"]["version"] == "graphics-v1"
    assert context["layout_points"] == []


def test_sections_match_form(graphics):
    # Эталон v0.11, Г.2: А–А — 18, 147, 149, 150, 151; Б–Б — 32, 92, 98, 97, 96.
    sections = {section["name"]: section for section in graphics["sections"]}
    assert [hole["hole_id"] for hole in sections["А"]["holes"]] == ["18", "147", "149", "150", "151"]
    assert [hole["hole_id"] for hole in sections["Б"]["holes"]] == ["32", "92", "98", "97", "96"]
    for section in sections.values():
        stations = [hole["station_m"] for hole in section["holes"]]
        assert stations == sorted(stations)                     # от бровки вглубь
        assert section["holes"][0]["first_row"]
        assert section["toe_station_m"] < section["crest_station_m"] < stations[0]
        assert section["slope_source"] == "contour"
        assert section["floor_z"] == pytest.approx(410.0, abs=0.1)


def test_section_decks_follow_charge(context, graphics):
    rows = {row["hole_id"]: row for row in context["blocks_v2"][0]["parameter_table"]["rows"]}
    for section in graphics["sections"]:
        for hole in section["holes"]:
            explosive = sum(d["to_m"] - d["from_m"] for d in hole["decks"] if d["kind"] == "explosive")
            assert explosive == pytest.approx(rows[hole["hole_id"]]["charge_length_m"], abs=0.02)
            assert hole["charge_kg"] == rows[hole["hole_id"]]["charge_kg"]
            assert hole["primers_m"] and all(0 < p <= hole["length_m"] for p in hole["primers_m"])


def test_network_times_are_resolved_on_copy():
    design = _trunk66()
    before = copy.deepcopy(design.network.to_dict())
    graphics, issues = block_graphics(design, [])
    assert design.network.to_dict() == before                  # проект блока не меняется
    expected = resolve_network(copy.deepcopy(design.network), [h for h in design.holes if h.enabled], design.loads).times_ms
    times = {hole["hole_id"]: hole["time_ms"] for hole in graphics["holes"]}
    assert times == {key: round(value, 1) for key, value in expected.items()}
    network = graphics["network"]
    # Замедление в скважине у «магистрали + цепочек» с СИНВ — наименьшее из 500/700/1000 сверх горящего фронта.
    assert network["label_mode"] == "surface" and network["downhole_ms"] == 500.0
    assert network["block_ms"] == max(times.values())
    assert sum(group["count"] for group in network["groups"]) == len(network["links"]) == len(design.network.surface_connectors)
    assert network["starters"] and not network["unconnected"] and not issues


def test_window_counts_holes_within_8_ms():
    design = _trunk66()
    graphics, _ = block_graphics(design, [])
    times = sorted(hole["time_ms"] for hole in graphics["holes"])
    best = max(sum(1 for t in times if start <= t <= start + 8.0) for start in times)
    assert graphics["network"]["window_8ms_max"] == best


def test_unconnected_hole_is_reported():
    design = _trunk66()
    lost = design.holes[50].id
    design.network.surface_connectors = [c for c in design.network.surface_connectors if lost not in (c.from_hole, c.to_hole)]
    graphics, issues = block_graphics(design, [])
    assert lost in graphics["network"]["unconnected"]
    assert [issue["code"] for issue in issues] == ["graphics_unconnected_holes"]


def test_no_network_is_a_warning():
    design = _trunk66()
    design.network.surface_connectors = []
    design.network.connectors = []
    _graphics, issues = block_graphics(design, [])
    assert "graphics_network_missing" in [issue["code"] for issue in issues]


def test_szm_passes_from_rear_to_crest(graphics):
    szm = graphics["szm"]
    columns = szm["columns"]
    holes = [hole_id for column in columns for hole_id in column]
    assert sorted(holes) == sorted(hole["hole_id"] for hole in graphics["holes"])   # каждая скважина — в одной колонке
    assert len(szm["passes"]) == math.ceil(len(columns) / 2)
    assert [item["number"] for item in szm["passes"]] == list(range(1, len(szm["passes"]) + 1))
    # Эталон v0.11 — 21 заходка по колонкам «по геометрии»; у BlastEX — 23 (отчёт в плане PR 4).
    assert 18 <= len(szm["passes"]) <= 26
    assert szm["rear_label"] and szm["front_label"] and szm["forbidden_zone_m"] == 20.0


def test_szm_start_flank_reverses_numbering():
    design = _trunk66()
    left, _ = block_graphics(design, [], szm_start_flank="left")
    right, _ = block_graphics(design, [], szm_start_flank="right")
    assert right["szm"]["start_flank"] == "right"
    assert left["szm"]["columns"][0] != right["szm"]["columns"][0]
    assert left["szm"]["columns"][0] == right["szm"]["columns"][-1]


def test_szm_start_flank_from_schedule():
    data = context66(_trunk66(), payload=payload66(schedule={"station": "у дороги", "szm_start_flank": "right"}))
    assert data["blocks_v2"][0]["graphics"]["szm"]["start_flank"] == "right"


def test_contour_by_holes_without_design_contour():
    design = _trunk66()
    design.contour = BlockContour()
    graphics, _ = block_graphics(design, [])
    assert graphics["contour_source"] == "holes"
    polygon = Polygon(graphics["plan"]["contour"])
    collars = MultiPoint([(h.collar.x, h.collar.y) for h in design.holes])
    assert polygon.contains(collars)
    # Отступ ≈ 1,9 м от крайних скважин, не выпуклая оболочка.
    assert polygon.area < collars.convex_hull.buffer(1.9).area
    assert polygon.exterior.distance(collars) == pytest.approx(1.9, abs=0.35)


# --- Г.5 --------------------------------------------------------------------

BLOCK = ([(0.0, 0.0), (60.0, 0.0), (60.0, 30.0), (0.0, 30.0)], [(10.0, 10.0)])
ZONES = {"people": {"value": 300.0}, "mechanisms": {"value": 200.0}, "buildings": {"value": 100.0}}
POSTS = [{"code": "1", "location": "дорога на отвал"}, {"code": "2", "location": "съезд"}]


def _g5(**changes):
    arguments = dict(zones=ZONES, objects=[], situation_layers=[], has_situation=False, layout_points=[], guard_posts=POSTS)
    arguments.update(changes)
    return project_graphics([BLOCK], **arguments)


def test_zone_rings_are_buffers_of_block():
    graphics, _ = _g5()
    block = Polygon(BLOCK[0])
    for zone in graphics["zones"]:
        distances = [block.distance(Point(x, y)) for x, y in zone["rings"][0]]
        assert min(distances) == pytest.approx(zone["value_m"], abs=1.5)
        assert max(distances) == pytest.approx(zone["value_m"], abs=1.5)
    assert [zone["kind"] for zone in graphics["zones"]] == ["people", "mechanisms", "buildings"]
    assert graphics["outlines"] == [[[0.0, 0.0], [60.0, 0.0], [60.0, 30.0], [0.0, 30.0]]]


def test_layout_points_and_warnings():
    points = [
        {"kind": "guard_post", "ref": "1", "x": 400.0, "y": 15.0},
        {"kind": "guard_post", "ref": "2", "x": 100.0, "y": 15.0},      # 40 м от блока — внутри зоны 300 м
        {"kind": "blast_station", "x": 30.0, "y": 500.0, "label": "КПП"},
        {"kind": "guard_post", "ref": "9", "x": 0.0, "y": 0.0},
    ]
    graphics, issues = _g5(layout_points=points)
    codes = [issue["code"] for issue in issues]
    assert codes.count("layout_point_unknown_post") == 1
    assert [issue["level"] for issue in issues if issue["code"] == "layout_point_unknown_post"] == ["error"]
    assert codes.count("guard_post_inside_zone") == 1
    missing = next(issue for issue in issues if issue["code"] == "layout_point_missing")
    assert "укрытие" in missing["message"] and "пост" not in missing["message"]
    rows = graphics["points"]
    assert [(row["kind"], row["number"]) for row in rows] == [("guard_post", 1), ("guard_post", 2), ("blast_station", None)]
    assert rows[0]["distance_m"] == 340 and rows[0]["label"] == "дорога на отвал"
    assert rows[2]["label"] == "КПП" and rows[2]["distance_m"] == 470


def test_station_inside_zone_is_warning_only():
    points = [{"kind": "shelter", "x": 70.0, "y": 15.0}]
    _graphics, issues = _g5(layout_points=points)
    shelter = [issue for issue in issues if issue["code"] == "station_inside_zone"]
    assert len(shelter) == 1 and shelter[0]["level"] == "warning"


def test_situation_is_clipped_and_objects_linked():
    near = {"name": "ЛЭП 6 кВ", "kind": "power_line", "lines": [{"points": [[-200.0, 150.0], [300.0, 150.0]], "closed": False}]}
    far = {"name": "Дорога далеко", "kind": "road", "lines": [{"points": [[5000.0, 5000.0], [5100.0, 5000.0]], "closed": False}]}
    objects = [{"key": "SITUATION:ЛЭП 6 кВ", "name": "ЛЭП 6 кВ"}, {"key": "MANUAL:1", "name": "ручной"}]
    graphics, _ = _g5(situation_layers=[near, far], has_situation=True, objects=objects)
    assert [layer["name"] for layer in graphics["situation"]] == ["ЛЭП 6 кВ"]
    assert graphics["has_situation"]
    linked, manual = graphics["objects"]
    assert linked["number"] == 1 and manual["link"] is None
    (_bx, by), (_ox, oy) = linked["link"]
    assert oy == pytest.approx(150.0) and by == pytest.approx(30.0)


def test_layout_points_in_v2_payload_only():
    from api.services.mass_blast_v2 import V2_PAYLOAD_KEYS

    assert "layout_points" in V2_PAYLOAD_KEYS
    design = _trunk66()
    near = {"kind": "guard_post", "ref": "1", "x": design.holes[0].collar.x + 50, "y": design.holes[0].collar.y}
    data = context66(design, payload=payload66(layout_points=[near]))
    assert data["layout_points"][0]["ref"] == "1"
    assert any(issue["code"] == "guard_post_inside_zone" for issue in data["issues"])


def test_duplicate_post_codes_keep_first_number():
    posts = [{"code": "1", "location": "А"}, {"code": "1", "location": "Б"}]
    graphics, issues = _g5(guard_posts=posts, layout_points=[{"kind": "guard_post", "ref": "1", "x": 400.0, "y": 15.0}])
    assert [row["number"] for row in graphics["points"]] == [1]
    assert not any(issue["code"] == "layout_point_missing" and "пост" in issue["message"] for issue in issues)
