"""Сдвиг скважины от узла сетки (TASK-017, PR 2).

Сдвинутая на плане скважина сетки помнит узел (мировые координаты места,
куда её поставил генератор) и смещение от него в осях раскладки:
`manual: ["xy"]` и `manual_offset`. Ключи пишутся только у сдвинутой —
иначе у утверждённых паспортов сменился бы `designed_sha256`.
"""
from __future__ import annotations

from api.schemas.design import BlastDesignSchema
from design.lifecycle import designed_sha256
from design.models import BenchSurface, BlastDesign, BlockContour, Hole, ManualOffset, Point3

# `designed_sha256` паспорта `_design()` до TASK-017 PR 2: новые поля его не меняют.
UNMOVED_SHA256 = "1e5e5e1c0a7d8d81464854229b7ec1961395416e40dec4c08eddb7d29ee1c126"


def _hole(**changes) -> Hole:
    hole = Hole(
        id="1-1",
        row=0,
        col=0,
        collar=Point3(10.0, 10.0, 420.0),
        toe=Point3(10.0, 10.0, 409.0),
        diameter_mm=152.0,
        subdrill_m=1.0,
    )
    for key, value in changes.items():
        setattr(hole, key, value)
    return hole


def _design(hole: Hole | None = None) -> BlastDesign:
    contour = BlockContour(
        vertices=[Point3(0.0, 0.0, 420.0), Point3(40.0, 0.0, 420.0), Point3(40.0, 20.0, 420.0)],
        bench=BenchSurface(crest_z_m=420.0, toe_z_m=410.0),
    )
    return BlastDesign(design_id="d-1", contour=contour, holes=[hole or _hole()])


def _through_api(design: BlastDesign) -> BlastDesign:
    return BlastDesign.from_dict(BlastDesignSchema(**design.to_dict()).model_dump())


def test_unmoved_hole_has_no_new_keys_and_keeps_its_hash():
    design = _design()
    again = _through_api(design)

    hole = again.to_dict()["holes"][0]
    assert "manual" not in hole
    assert "manual_offset" not in hole
    assert designed_sha256(design) == UNMOVED_SHA256
    assert designed_sha256(again) == UNMOVED_SHA256


def test_moved_hole_round_trips_through_the_api():
    offset = ManualOffset(node_x=10.0, node_y=10.0, along=0.75, across=-0.5)
    design = _design(_hole(manual=["xy"], manual_offset=offset))

    again = _through_api(design)

    data = again.to_dict()["holes"][0]
    assert data["manual"] == ["xy"]
    assert data["manual_offset"] == {"node_x": 10.0, "node_y": 10.0, "along": 0.75, "across": -0.5}
    assert again.holes[0].manual_offset == offset
    assert designed_sha256(again) == designed_sha256(design) != UNMOVED_SHA256
