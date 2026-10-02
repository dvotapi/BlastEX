"""Сшивка фрагментов бровок в непрерывные линии (TASK-013, PR 2)."""
from __future__ import annotations

import math
import random
from pathlib import Path

import pytest

from design.spatial.cad.model import CadEntity
from design.spatial.cad.stitch import stitch_lines

FIXTURE = Path(__file__).parent / "fixtures" / "cad" / "block66.dxf"


def line(handle: str, points) -> CadEntity:
    return CadEntity(handle=handle, layer="Бровка", kind="POLYLINE3D", points=[(x, y, 420.0 + 0.01 * x) for x, y in points])


def fragments(gaps: list[float]) -> list[CadEntity]:
    """Прямая бровка вдоль X: 5 фрагментов по 20 м, между ними разрывы `gaps`."""

    parts = []
    x = 0.0
    for index in range(len(gaps) + 1):
        parts.append(line(f"F{index}", [(x, 0.0), (x + 10.0, 0.0), (x + 20.0, 0.0)]))
        x += 20.0 + (gaps[index] if index < len(gaps) else 0.0)
    return parts


def test_five_fragments_with_gaps_up_to_a_metre_become_one_line():
    parts = fragments([0.2, 0.5, 0.9, 1.0])
    # Два фрагмента развёрнуты, порядок перемешан: сшивка не зависит от них.
    parts[1].points.reverse()
    parts[3].points.reverse()
    random.Random(7).shuffle(parts)

    lines, gaps = stitch_lines(parts)

    assert len(lines) == 1
    stitched = lines[0]
    assert sorted(part.handle for part in stitched.parts) == ["F0", "F1", "F2", "F3", "F4"]
    assert {part.handle for part in stitched.parts if part.reversed} in ({"F1", "F3"}, {"F0", "F2", "F4"})
    xs = [point[0] for point in stitched.points]
    assert xs == sorted(xs) or xs == sorted(xs, reverse=True)
    assert stitched.length_m == pytest.approx(100.0 + 0.2 + 0.5 + 0.9 + 1.0)
    assert gaps == []


def test_three_metre_gap_stays_a_gap():
    lines, gaps = stitch_lines(fragments([0.2, 3.0, 0.5, 0.5]))

    assert sorted(len(item.parts) for item in lines) == [2, 3]
    assert len(gaps) == 1
    assert gaps[0].reason == "gap"
    assert gaps[0].distance_m == pytest.approx(3.0)
    assert sorted(point[0] for point in (gaps[0].a, gaps[0].b)) == pytest.approx([40.2, 43.2])


def test_sharp_turn_across_a_gap_is_not_stitched():
    a = line("A", [(0, 0), (10, 0)])
    b = line("B", [(10.5, 0), (10.5, 10)])

    lines, gaps = stitch_lines([a, b])

    assert len(lines) == 2
    assert [gap.reason for gap in gaps] == ["turn"]


def test_coincident_ends_of_exactly_two_lines_are_stitched_at_any_angle():
    # Угол одной бровки (как 733 → 73B у блока 66): концы совпадают, поворот 95°.
    a = line("A", [(0, 0), (0, 10)])
    turn = math.radians(95)
    b = line("B", [(0, 10), (10 * math.sin(turn), 10 + 10 * math.cos(turn))])

    lines, gaps = stitch_lines([a, b])

    assert len(lines) == 1
    assert [part.handle for part in lines[0].parts] in (["A", "B"], ["B", "A"])
    assert gaps == []


def test_three_ends_at_one_point_join_the_straightest_pair():
    a = line("A", [(-10, 0), (0, 0)])
    b = line("B", [(0, 0), (10, 0)])
    c = line("C", [(0, 0), (0, 10)])

    lines, _ = stitch_lines([c, a, b])

    handles = sorted(sorted(part.handle for part in item.parts) for item in lines)
    assert handles == [["A", "B"], ["C"]]


def test_chain_distance_maps_back_to_the_fragment():
    parts = fragments([0.5])
    parts[1].points.reverse()

    stitched = stitch_lines(parts)[0][0]
    first, second = stitched.parts
    assert first.chain_start_m == 0.0
    assert second.chain_start_m == pytest.approx(20.5)
    # Точка в 5 м от начала второго фрагмента по цепочке.
    assert second.entity_m(25.5) == pytest.approx(15.0 if second.reversed else 5.0)


def test_block_66_crests_are_stitched_into_the_expected_lines():
    from design.spatial.cad.reader import read_cad
    from design.spatial.cad.roles import RoleParams, assign_roles

    drawing = read_cad(FIXTURE.read_bytes(), "block66.dxf")
    assign_roles(drawing.entities, {}, RoleParams())
    tops = [item for item in drawing.entities if item.role == "crest_top"]
    bottoms = [item for item in drawing.entities if item.role == "crest_bottom"]

    top_lines, _ = stitch_lines(tops)
    assert {"6C3", "6BE", "72E"} in [{part.handle for part in item.parts} for item in top_lines]

    bottom_lines, _ = stitch_lines(bottoms)
    assert len(bottom_lines) == 1
    assert {part.handle for part in bottom_lines[0].parts} == {"73B", "733", "753", "75A"}
    assert bottom_lines[0].length_m == pytest.approx(239.9, abs=0.1)


def test_fragments_of_different_benches_are_not_stitched():
    # Конец в конец в плане, направление продолжается, но бровки на 420 и 410 м.
    upper = CadEntity(handle="U", layer="Бровка", kind="POLYLINE3D", points=[(0.0, 0.0, 420.0), (20.0, 0.0, 420.0)])
    lower = CadEntity(handle="L", layer="Бровка", kind="POLYLINE3D", points=[(20.3, 0.0, 410.0), (40.0, 0.0, 410.0)])

    lines, _ = stitch_lines([upper, lower])

    assert sorted(line.handles for line in lines) == [["L"], ["U"]]


def test_flat_drawing_without_elevations_still_stitches():
    flat = [
        CadEntity(handle="A", layer="Бровка", kind="LWPOLYLINE", points=[(0.0, 0.0, 0.0), (20.0, 0.0, 0.0)]),
        CadEntity(handle="B", layer="Бровка", kind="POLYLINE3D", points=[(20.3, 0.0, 420.0), (40.0, 0.0, 420.0)]),
    ]
    # Линия без отметок (Z = 0) отметкой не мешает: её Z неизвестен.
    lines, _ = stitch_lines(flat)
    assert [line.handles for line in lines] == [["A", "B"]]


def test_many_ends_at_one_junction_stitch_quickly():
    import time

    # 400 лучей из одной точки — узел, где сходятся сотни концов (дубли, обрывки).
    rays = [
        line(f"R{k:03d}", [(0.0, 0.0), (30 * math.cos(2 * math.pi * k / 400), 30 * math.sin(2 * math.pi * k / 400))])
        for k in range(400)
    ]
    started = time.perf_counter()
    stitch_lines(rays)
    elapsed = time.perf_counter() - started
    assert elapsed < 2.0, f"{elapsed:.2f} с"


def test_thousands_of_unstitchable_ends_close_together_stay_fast():
    import time

    # 1500 коротких обрывков разных уступов в пятиметровом пятне: сшить нечего,
    # а пар концов ближе 5 м — миллионы (Codex P1).
    rng = random.Random(3)
    scraps = []
    for k in range(1500):
        x, y, angle = rng.uniform(0, 5), rng.uniform(0, 5), rng.uniform(0, 2 * math.pi)
        z = 2.0 * k  # у каждого обрывка своя отметка: сшить нечего
        scraps.append(
            CadEntity(handle=f"S{k:04d}", layer="Бровка", kind="POLYLINE3D",
                      points=[(x, y, z), (x + 0.3 * math.cos(angle), y + 0.3 * math.sin(angle), z)])
        )
    started = time.perf_counter()
    lines, gaps = stitch_lines(scraps)
    elapsed = time.perf_counter() - started

    assert lines and len(gaps) <= len(lines)
    assert elapsed < 3.0, f"{elapsed:.2f} с"
