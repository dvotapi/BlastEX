"""Поле паспорта `contour.cad`: происхождение контура из чертежа (TASK-013, PR 2).

Хэш утверждённого паспорта (`designed_sha256`) считается по контуру. Ключ
`cad` пишется, только когда поле есть, — иначе у всех старых паспортов хэш
сменился бы при первой же записи и сломалась бы сверка массового взрыва.
"""
from __future__ import annotations

from api.schemas.design import BlastDesignSchema
from design.lifecycle import classify_mutations, designed_sha256
from design.models import BenchSurface, BlastDesign, BlockContour, Point3

CAD = {
    "source_id": "src-1",
    "file_name": "блок 66.dwg",
    "method": "ready",
    "items": [{"kind": "part", "handle": "769", "start_m": 0.0, "end_m": 341.08, "points": [], "flip": False, "label": ""}],
    "top": [[0.0, 0.0], [40.0, 0.0], [40.0, 20.0]],
    "bottom": [[0.0, 0.0], [44.0, 0.0], [44.0, 20.0]],
    "area_top_m2": 800.0,
    "area_bottom_m2": 880.0,
    "area_mean_m2": 840.0,
    "map_area_m2": 2772.49,
    "built_at": "2026-10-01T10:00:00+00:00",
    "edited": False,
}


def _design(cad=None) -> BlastDesign:
    contour = BlockContour(
        vertices=[Point3(0.0, 0.0, 420.0), Point3(40.0, 0.0, 420.0), Point3(40.0, 20.0, 420.0)],
        free_faces=[[1, 2]],
        bench=BenchSurface(crest_z_m=420.0, toe_z_m=410.0),
        cad=cad,
    )
    return BlastDesign(design_id="d-1", contour=contour)


def _through_api(design: BlastDesign) -> BlastDesign:
    return BlastDesign.from_dict(BlastDesignSchema(**design.to_dict()).model_dump())


def test_old_passport_has_no_cad_key_and_keeps_its_hash():
    design = _design()
    assert "cad" not in design.to_dict()["contour"]

    again = _through_api(design)

    assert again.contour.cad is None
    assert designed_sha256(again) == designed_sha256(design)
    assert classify_mutations(design, again) == []


def test_cad_survives_the_api_round_trip():
    design = _design(CAD)

    again = _through_api(design)

    assert again.contour.cad == CAD
    assert again.to_dict()["contour"]["cad"]["map_area_m2"] == 2772.49
    assert designed_sha256(again) == designed_sha256(design)


def test_building_from_a_drawing_is_a_design_change():
    assert designed_sha256(_design(CAD)) != designed_sha256(_design())


def test_revision_of_a_passport_keeps_the_drawing_contour(tmp_path):
    from unittest.mock import patch

    from design.persistence import fork_design, load_design, save_design

    with patch("cost.persistence.data_root", return_value=tmp_path):
        saved = save_design("cad-team", _design(CAD))
        forked = fork_design("cad-team", saved.design_id, name="Новая версия", actor="lead@mine")

        assert forked.contour.cad == CAD
        assert load_design("cad-team", saved.design_id).contour.cad == CAD
