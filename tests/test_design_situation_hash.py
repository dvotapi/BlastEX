"""Новые поля паспорта TASK-013 PR 4 и хэш утверждённого паспорта.

`contour.cad.situation` (версии ситуации, показанные при «Построить блок») и
`coordinate_system.height_system` (система высот объекта) пишутся, только
когда заданы: иначе у старых утверждённых паспортов сменился бы
`designed_sha256`.
"""
from __future__ import annotations

from api.schemas.design import BlastDesignSchema
from design.lifecycle import classify_mutations, designed_sha256
from design.models import BenchSurface, BlastDesign, BlockContour, Point3
from design.spatial.coordinates import CoordinateSystem

CONTOUR_CAD = {
    "source_id": "src-1",
    "file_name": "блок.dxf",
    "method": "ready",
    "items": [],
    "top": [[0.0, 0.0], [40.0, 0.0], [40.0, 20.0]],
    "bottom": None,
    "area_top_m2": 800.0,
    "area_bottom_m2": 800.0,
    "area_mean_m2": 800.0,
    "map_area_m2": None,
    "area_basis": "mean",
    "area_m2": 800.0,
    "built_at": "2026-10-01T10:00:00+00:00",
    "edited": False,
}
SITUATION = [
    {"source_id": "src-1", "title": "граница блока 70", "survey_date": "2026-09-28"},
    {"source_id": "src-2", "title": "Положение горных работ", "survey_date": None},
]
MSK66 = CoordinateSystem(name="МСК-66 зона 1", height_system="Балтийская 1977", confirmed=True)


def _design(*, contour_cad=None, crs: CoordinateSystem | None = None) -> BlastDesign:
    contour = BlockContour(
        vertices=[Point3(0.0, 0.0, 420.0), Point3(40.0, 0.0, 420.0), Point3(40.0, 20.0, 420.0)],
        bench=BenchSurface(crest_z_m=420.0, toe_z_m=410.0),
        cad=contour_cad,
    )
    return BlastDesign(design_id="d-1", contour=contour, coordinate_system=crs)


def _through_api(design: BlastDesign) -> BlastDesign:
    return BlastDesign.from_dict(BlastDesignSchema(**design.to_dict()).model_dump())


def test_old_passport_keeps_its_hash_and_has_no_new_keys():
    design = _design(contour_cad=dict(CONTOUR_CAD), crs=CoordinateSystem(name="Карьерная сетка", confirmed=True))

    again = _through_api(design)

    assert "situation" not in again.to_dict()["contour"]["cad"]
    assert "height_system" not in again.to_dict()["coordinate_system"]
    assert designed_sha256(again) == designed_sha256(design)
    assert classify_mutations(design, again) == []


def test_empty_situation_reference_is_not_written():
    design = _design(contour_cad={**CONTOUR_CAD, "situation": []})

    assert "situation" not in design.to_dict()["contour"]["cad"]
    assert designed_sha256(design) == designed_sha256(_design(contour_cad=dict(CONTOUR_CAD)))


def test_situation_reference_and_height_system_survive_the_api():
    design = _design(contour_cad={**CONTOUR_CAD, "situation": SITUATION}, crs=MSK66)

    again = _through_api(design)

    assert again.contour.cad["situation"] == SITUATION
    assert again.coordinate_system.height_system == "Балтийская 1977"
    assert again.coordinate_system.name == "МСК-66 зона 1"
    assert designed_sha256(again) == designed_sha256(design)


def test_situation_reference_and_height_system_are_design_changes():
    plain = designed_sha256(_design(contour_cad=dict(CONTOUR_CAD)))

    assert designed_sha256(_design(contour_cad={**CONTOUR_CAD, "situation": SITUATION})) != plain
    assert designed_sha256(_design(contour_cad=dict(CONTOUR_CAD), crs=MSK66)) != plain


def test_coordinate_system_without_height_system_keeps_the_old_shape():
    assert CoordinateSystem(name="МСК-66 зона 1").to_dict() == {
        "name": "МСК-66 зона 1",
        "epsg": None,
        "origin_x": 0.0,
        "origin_y": 0.0,
        "origin_z": 0.0,
        "units": "m",
        "confirmed": False,
    }
    assert CoordinateSystem.from_dict({"name": "x", "height_system": " БСВ "}).height_system == "БСВ"
