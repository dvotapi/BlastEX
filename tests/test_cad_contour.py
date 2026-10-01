"""Способы контура блока: готовый, сборка, щелчок внутри (TASK-013, PR 2)."""
from __future__ import annotations

import math

import pytest

from design.spatial.cad import contour as contour_module
from design.spatial.cad.contour import (
    ContourInputError,
    ContourItem,
    assemble,
    click_contour,
    ready_contour,
    split_lines,
)
from design.spatial.cad.model import CadEntity
from design.spatial.cad.rings import ring_area


def line(handle: str, points, *, closed: bool = False, layer: str = "Проект") -> CadEntity:
    return CadEntity(handle=handle, layer=layer, kind="LWPOLYLINE", points=[(x, y, 0.0) for x, y in points], closed=closed)


def part(handle: str, start_m: float, end_m: float, *, flip: bool = False) -> ContourItem:
    return ContourItem(kind="part", handle=handle, start_m=start_m, end_m=end_m, flip=flip)


def codes(draft):
    return [issue.code for issue in draft.issues]


# --- готовый контур ------------------------------------------------------


def test_ready_closed_line_is_the_contour():
    draft = ready_contour(line("C", [(0, 0), (10, 0), (10, 10), (0, 10)], closed=True), 0.5)
    assert draft.ok
    assert ring_area(draft.ring) == pytest.approx(100.0)
    assert [item.kind for item in draft.items] == ["part"]


def test_ready_line_with_small_gap_closes_itself_without_a_tiny_edge():
    draft = ready_contour(line("C", [(0, 0), (10, 0), (10, 10), (0, 10), (0, 0.4)]), 0.5)
    assert draft.ok, draft.issues
    assert len(draft.ring) == 4


def test_ready_line_with_big_gap_is_not_closed():
    draft = ready_contour(line("C", [(0, 0), (10, 0), (10, 10), (0, 10), (0, 0.8)]), 0.5)
    assert codes(draft) == ["not_closed"]
    assert "0,80" in draft.issues[0].message
    assert draft.ring is None


# --- сборка --------------------------------------------------------------

L_SHAPE = {
    "A": line("A", [(0, 0), (10, 0), (10, 10)]),
    "B": line("B", [(0, 10.03), (0, 0.5)]),
}


def test_assembly_orients_parts_by_the_nearest_end():
    # Начало A (0, 0) ближе к B (0,5 м до его нижнего конца), чем конец A (10 м):
    # первый участок разворачивается к второму, второй — ближним концом к цепочке.
    draft = assemble([part("A", 0, 20), part("B", 0, 9.53)], L_SHAPE, 0.5)
    assert draft.ok, draft.issues
    # Стыки ≤ допуска сведены в средние точки: (0; 0,25) вместо (0; 0) и (0; 0,5).
    assert ring_area(draft.ring) == pytest.approx(98.9, abs=0.01)
    assert [info.reversed for info in draft.item_info] == [True, True]


def test_flip_reverses_the_automatic_direction():
    draft = assemble([part("A", 0, 20), part("B", 0, 9.53, flip=True)], L_SHAPE, 0.5)
    # Без «развернуть» B идёт развёрнутым (см. тест выше), с ним — как начерчен.
    assert draft.item_info[1].reversed is False
    assert "self_intersection" in codes(draft)


def test_joints_within_tolerance_merge_ends_and_bigger_gaps_get_closing_segments():
    draft = assemble([part("A", 0, 20), part("B", 0, 9.53)], L_SHAPE, 0.5)
    # Стык A → B — 0,5 м: концы сводятся; B → A (0, 10.03) → (10, 10) — 10 м: замыкающий отрезок.
    assert [info.link for info in draft.item_info] == ["joined", "closing"]
    assert draft.item_info[0].gap_to_next_m == pytest.approx(0.5)
    assert draft.item_info[1].gap_to_next_m == pytest.approx(10.0, abs=0.01)
    assert len(draft.closings) == 1
    # Стык 3 см не оставил ребра 3 см: ошибки «ребро короче 0,05 м» нет.
    tiny = assemble(
        [part("A", 0, 20), part("C", 0, 10)],
        {"A": L_SHAPE["A"], "C": line("C", [(9.97, 10), (0.0, 10), (0.0, 0.03)])},
        0.5,
    )
    assert tiny.ok, tiny.issues


def test_single_open_part_closes_with_a_closing_segment():
    draft = assemble([part("A", 0, 20)], L_SHAPE, 0.5)
    assert draft.ok
    assert ring_area(draft.ring) == pytest.approx(50.0)
    assert [info.link for info in draft.item_info] == ["closing"]


def test_segment_and_polyline_items():
    items = [
        ContourItem(kind="polyline", points=[(0, 0), (10, 0), (10, 10)]),
        ContourItem(kind="segment", points=[(10, 10), (0, 10)]),
    ]
    draft = assemble(items, {}, 0.5)
    assert draft.ok
    assert ring_area(draft.ring) == pytest.approx(100.0)


def test_empty_assembly_has_too_few_points():
    assert codes(assemble([], {}, 0.5)) == ["too_few_points"]


def test_unknown_handle_is_an_input_error():
    with pytest.raises(ContourInputError):
        assemble([part("X", 0, 1)], L_SHAPE, 0.5)


# --- щелчок внутри -------------------------------------------------------

SQUARE_WITH_GAP = [
    line("S1", [(0, 0), (10, 0)]),
    line("S2", [(10, 0), (10, 10)]),
    line("S3", [(10, 10), (0, 10)]),
    line("S4", [(0, 10), (0, 2)]),  # разрыв 2 м до (0, 0)
]


def test_click_inside_bridges_a_two_metre_gap():
    draft = click_contour(SQUARE_WITH_GAP, (5, 5), 0.5, 5.0)
    assert draft.ok, draft.issues
    assert ring_area(draft.ring) == pytest.approx(100.0)
    assert len(draft.closings) == 1
    assert draft.closings[0] in (((0.0, 2.0), (0.0, 0.0)), ((0.0, 0.0), (0.0, 2.0)))


def test_click_inside_without_a_long_enough_bridge_is_outside():
    draft = click_contour(SQUARE_WITH_GAP, (5, 5), 0.5, 1.0)
    assert codes(draft) == ["outside"]


def test_click_outside_every_area():
    draft = click_contour(SQUARE_WITH_GAP, (50, 50), 0.5, 5.0)
    assert codes(draft) == ["outside"]


def test_click_items_reassemble_into_the_same_polygon():
    lines = {item.handle: item for item in SQUARE_WITH_GAP}
    draft = click_contour(SQUARE_WITH_GAP, (5, 5), 0.5, 5.0)
    again = assemble(draft.items, lines, 0.5)
    assert again.ok
    assert ring_area(again.ring) == pytest.approx(ring_area(draft.ring))


def test_crossing_lines_split_the_area_and_the_click_picks_its_face():
    lines = [line("R", [(0, 0), (10, 0), (10, 10), (0, 10)], closed=True), line("X", [(5, -2), (5, 12)])]
    draft = click_contour(lines, (2, 5), 0.5, 5.0)
    assert draft.ok
    assert ring_area(draft.ring) == pytest.approx(50.0)


# --- разрезы линий -------------------------------------------------------


def test_split_lines_cut_both_lines_at_the_crossing():
    splits, crossings = split_lines([line("H", [(0, 0), (10, 0)]), line("V", [(4, -5), (4, 5)])])
    assert splits == {"H": [pytest.approx(4.0)], "V": [pytest.approx(5.0)]}
    assert crossings == [pytest.approx((4.0, 0.0))]


def test_too_many_segments_is_an_input_error(monkeypatch):
    monkeypatch.setattr(contour_module, "MAX_CONTOUR_SEGMENTS", 3)
    with pytest.raises(ContourInputError, match="3"):
        split_lines([line("H", [(0, 0), (1, 0), (2, 0), (3, 0), (4, 0)])])


# --- правки ревью ---------------------------------------------------------


def _read_lwpolyline(points, *, closed: bool = False):
    import io

    import ezdxf

    from design.spatial.cad.reader import read_cad

    doc = ezdxf.new("R2010")
    doc.modelspace().add_lwpolyline(points, close=closed, dxfattribs={"layer": "блок 1"})
    buffer = io.StringIO()
    doc.write(buffer)
    return read_cad(buffer.getvalue().encode("utf-8"), "t.dxf").entities[0]


@pytest.mark.parametrize("last", [(0.02, 0.02), (0.03, 0.0), (0.0, 0.4)])
def test_nearly_closed_line_from_the_reader_closes_without_a_tiny_edge(last):
    # Reader сам ставит closed_by_gap при разрыве до 0,5 м и точки не трогает.
    entity = _read_lwpolyline([(0, 0), (10, 0), (10, 10), (0, 10), last])
    assert entity.closed and entity.closed_by_gap

    ready = ready_contour(entity, 0.5)
    clicked = click_contour([entity], (5, 5), 0.5, 5.0)

    assert ready.ok, ready.issues
    assert clicked.ok, clicked.issues
    assert len(ready.ring) == 4
    again = assemble(ready.items, {entity.handle: entity}, 0.5)
    assert again.ok, again.issues


@pytest.mark.parametrize("overlap", [0.03, 0.3])
def test_click_and_assembly_agree_when_lines_overlap_at_corners(overlap):
    # Маркшейдер часто чертит углы с перехлёстом: линии пересекаются, концы торчат.
    o = overlap
    lines = [
        line("B", [(-o, 0), (40 + o, 0)]),
        line("R", [(40, -o), (40, 20 + o)]),
        line("T", [(40 + o, 20), (-o, 20)]),
        line("L", [(0, 20 + o), (0, -o)]),
    ]
    by_handle = {item.handle: item for item in lines}
    splits, _ = split_lines(lines)
    pieces = [part(handle, splits[handle][0], splits[handle][-1]) for handle in ("B", "R", "T", "L")]

    assembled = assemble(pieces, by_handle, 0.5)
    clicked = click_contour(lines, (20, 10), 0.5, 5.0)

    assert assembled.ok and clicked.ok, (assembled.issues, clicked.issues)
    assert ring_area(assembled.ring) == pytest.approx(800.0, abs=0.01)
    assert ring_area(clicked.ring) == pytest.approx(800.0, abs=0.01)


def test_click_closes_micro_gaps_without_short_edges():
    lines = [
        line("B", [(0, 0), (40, 0)]),
        line("R", [(40.02, 0.01), (40, 20)]),
        line("T", [(40, 20.03), (0, 20)]),
        line("L", [(0, 20), (0.0, 0.02)]),
    ]
    draft = click_contour(lines, (20, 10), 0.5, 5.0)
    assert draft.ok, draft.issues
    assert ring_area(draft.ring) == pytest.approx(800.0, abs=1.0)


def test_click_pulls_an_undershooting_end_onto_the_line_without_a_bridge():
    lines = [
        line("B", [(-5, 0), (45, 0)]),
        line("R", [(40, -5), (40, 20)]),
        line("T", [(40, 20), (0, 20)]),
        line("L", [(0, 20), (0, 0.3)]),  # не дотянута до B на 0,3 м
    ]
    draft = click_contour(lines, (20, 10), 0.5, 0.0)
    assert draft.ok, draft.issues
    assert ring_area(draft.ring) == pytest.approx(800.0, abs=0.01)
    assert draft.closings == []


def test_bridges_still_work_with_thousands_of_dangling_ends_far_away():
    # Раньше при > 2000 висячих концов мосты молча не строились («увеличьте мост»).
    block = [
        line("B", [(0, 0), (40, 0)]),
        line("R", [(41, 0), (41, 20)]),
        line("T", [(41, 21), (0, 21)]),
        line("L", [(0, 20), (0, 1)]),
    ]
    # Отрезки 2 м — длиннее допуска: их концы не сводятся друг с другом и
    # остаются висячими (5000 концов).
    noise = [line(f"N{k}", [(1000 + (k % 50) * 4, (k // 50) * 4), (1002 + (k % 50) * 4, (k // 50) * 4)]) for k in range(2500)]

    draft = click_contour([*block, *noise], (20, 10), 0.5, 5.0)

    assert draft.ok, draft.issues
    assert len(draft.closings) == 4


def test_split_lines_without_lines_is_empty():
    assert split_lines([]) == ({}, [])



def _rotated(points, degrees, origin=(0.0, 0.0)):
    angle = math.radians(degrees)
    c, s_ = math.cos(angle), math.sin(angle)
    return [(origin[0] + x * c - y * s_, origin[1] + x * s_ + y * c) for x, y in points]


@pytest.mark.parametrize("degrees", [7.37, 31.7, 58.0])
@pytest.mark.parametrize("short", [0.05, 0.1, 0.3, 0.45])
def test_undershooting_end_joins_a_slanted_line(degrees, short):
    lines = [
        line("B", _rotated([(-5, 0), (45, 0)], degrees)),
        line("R", _rotated([(40, -5), (40, 20)], degrees)),
        line("T", _rotated([(40, 20), (0, 20)], degrees)),
        line("L", _rotated([(0, 20), (0, short)], degrees)),
    ]
    inside = _rotated([(20, 10)], degrees)[0]

    draft = click_contour(lines, inside, 0.5, 0.0)

    assert draft.ok, draft.issues
    assert ring_area(draft.ring) == pytest.approx(800.0, abs=0.05)


@pytest.mark.parametrize("overlap", [0.41, 0.45, 0.49])
def test_slanted_overlap_gives_no_zero_length_bridges(overlap):
    o = overlap
    lines = [
        line("B", _rotated([(-o, 0), (40 + o, 0)], 31.7)),
        line("R", _rotated([(40, -o), (40, 20 + o)], 31.7)),
        line("T", _rotated([(40 + o, 20), (-o, 20)], 31.7)),
        line("L", _rotated([(0, 20 + o), (0, -o)], 31.7)),
    ]
    by_handle = {item.handle: item for item in lines}

    draft = click_contour(lines, _rotated([(20, 10)], 31.7)[0], 0.5, 5.0)

    assert draft.ok, draft.issues
    assert ring_area(draft.ring) == pytest.approx(800.0, abs=0.05)
    assert all(math.dist(a, b) >= 0.05 for a, b in draft.closings)
    again = assemble(draft.items, by_handle, 0.5)
    assert again.ok, again.issues
