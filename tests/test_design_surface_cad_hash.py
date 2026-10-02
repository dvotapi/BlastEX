"""Новые поля паспорта TASK-013 PR 3 и хэш утверждённого паспорта.

`surfaces.top.cad` (кровля из чертежа), `Hole.manual` (ручная правка длины и
отметки устья) и `contour.cad.map_volume_m3` (объём с блоковой карты)
пишутся, только когда заданы: иначе у старых утверждённых паспортов сменился
бы `designed_sha256` и сломалась бы сверка массового взрыва.
"""
from __future__ import annotations

import pytest

from api.schemas.design import BlastDesignSchema
from design.lifecycle import classify_mutations, designed_sha256
from design.models import BenchSurface, BlastDesign, BlockContour, Hole, Point3
from design.spatial.surfaces import SurfaceModel, SurfaceSet
from design.spatial.tin import TIN

CONTOUR_CAD = {
    "source_id": "src-1",
    "file_name": "блок.dxf",
    "method": "ready",
    "items": [],
    "top": [[0.0, 0.0], [40.0, 0.0], [40.0, 20.0]],
    "bottom": [[0.0, 0.0], [44.0, 0.0], [44.0, 20.0]],
    "area_top_m2": 800.0,
    "area_bottom_m2": 880.0,
    "area_mean_m2": 840.0,
    "map_area_m2": None,
    "area_basis": "mean",
    "area_m2": 840.0,
    "built_at": "2026-10-01T10:00:00+00:00",
    "edited": False,
}
SURFACE_CAD = {
    "source_id": "src-1",
    "file_name": "блок.dxf",
    "roles": ["crest_top", "spot_heights"],
    "excluded": ["P7"],
    "builder": "cdt",
    "plane": False,
    "floor_z_m": 410.0,
    "quality": {"spot_count": 206, "coverage_pct": 99.93, "max_gap_m": 10.9, "outlier_count": 0, "conflict_count": 0},
    "built_at": "2026-10-02T10:00:00+00:00",
}


def _hole(manual=None) -> Hole:
    hole = Hole(
        id="1-1",
        row=0,
        col=0,
        collar=Point3(10.0, 10.0, 420.0),
        toe=Point3(10.0, 10.0, 409.0),
        diameter_mm=152.0,
        subdrill_m=1.0,
    )
    if manual is not None:
        hole.manual = manual
    return hole


def _roof(cad=None) -> SurfaceModel:
    tin = TIN(
        vertices=[Point3(0.0, 0.0, 420.0), Point3(40.0, 0.0, 420.0), Point3(40.0, 20.0, 420.0), Point3(0.0, 20.0, 420.0)],
        triangles=[(0, 1, 2), (0, 2, 3)],
    )
    return SurfaceModel(kind="top", name="Кровля", source_format="cad", created_at="2026-10-02T10:00:00+00:00", tin=tin, cad=cad)


def _design(*, contour_cad=None, roof=None, manual=None) -> BlastDesign:
    contour = BlockContour(
        vertices=[Point3(0.0, 0.0, 420.0), Point3(40.0, 0.0, 420.0), Point3(40.0, 20.0, 420.0)],
        bench=BenchSurface(crest_z_m=420.0, toe_z_m=410.0),
        cad=contour_cad,
    )
    return BlastDesign(design_id="d-1", contour=contour, holes=[_hole(manual)], surfaces=SurfaceSet(top=roof))


def _through_api(design: BlastDesign) -> BlastDesign:
    return BlastDesign.from_dict(BlastDesignSchema(**design.to_dict()).model_dump())


def test_old_passport_keeps_its_hash_and_has_no_new_keys():
    design = _design(roof=_roof())
    data = design.to_dict()
    assert "cad" not in data["surfaces"]["top"]
    assert "manual" not in data["holes"][0]

    again = _through_api(design)

    assert designed_sha256(again) == designed_sha256(design)
    assert classify_mutations(design, again) == []
    assert "manual" not in again.to_dict()["holes"][0]
    assert "cad" not in again.to_dict()["surfaces"]["top"]


def test_drawing_contour_of_pr2_keeps_its_hash_without_a_map_volume():
    design = _design(contour_cad=dict(CONTOUR_CAD))

    again = _through_api(design)

    assert "map_volume_m3" not in again.to_dict()["contour"]["cad"]
    assert designed_sha256(again) == designed_sha256(design)


def test_roof_from_a_drawing_manual_flags_and_map_volume_survive_the_api():
    design = _design(
        contour_cad={**CONTOUR_CAD, "map_volume_m3": 28279.39},
        roof=_roof(dict(SURFACE_CAD)),
        manual=["collar_z", "length"],
    )

    again = _through_api(design)

    assert again.surfaces.top.cad == SURFACE_CAD
    assert again.holes[0].manual == ["collar_z", "length"]
    assert again.contour.cad["map_volume_m3"] == pytest.approx(28279.39)
    assert designed_sha256(again) == designed_sha256(design)


def test_roof_from_a_drawing_and_manual_edit_are_design_changes():
    plain = designed_sha256(_design(roof=_roof()))

    assert designed_sha256(_design(roof=_roof(dict(SURFACE_CAD)))) != plain
    assert designed_sha256(_design(roof=_roof(), manual=["length"])) != plain


def test_unknown_manual_flag_is_rejected_by_the_api():
    data = _design(manual=["collar_z"]).to_dict()
    data["holes"][0]["manual"] = ["depth"]

    with pytest.raises(ValueError):
        BlastDesignSchema(**data)
