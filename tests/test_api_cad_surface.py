"""HTTP-маршрут предпросмотра кровли блока (TASK-013, PR 3, задача 6)."""
from __future__ import annotations

from pathlib import Path

import pytest

from design.spatial.cad.repository import InMemoryCadRepository
from tests.test_api_cad import BASE, SESSION_B, _client, _upload

FIXTURE = Path(__file__).parent / "fixtures" / "cad" / "block66.dxf"


@pytest.fixture(scope="module")
def loaded():
    repository = InMemoryCadRepository()
    client = _client(repository)
    source = _upload(client, ("block66.dxf", FIXTURE.read_bytes()))["sources"][0]
    contour = client.post(f"{BASE}/sources/{source['id']}/contour", json={"method": "ready", "handle": "769"}).json()
    return repository, client, source, contour


def _surface(client, source_id: str, contour: dict, **payload):
    body = {"top": contour["top"]["points"], "bottom": contour["bottom"]["points"], **payload}
    return client.post(f"{BASE}/sources/{source_id}/surface", json=body)


def test_roof_preview_of_block_66(loaded):
    _, client, source, contour = loaded

    response = _surface(client, source["id"], contour, floor_z_m=410.0, crest_z_m=contour["bench"]["crest_z_m"])

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["ok"] is True and body["issues"] == []
    assert body["builder"] in {"cdt", "scipy"}
    assert body["plane"] is False
    assert len(body["tin"]["vertices"]) > 500
    assert all(len(vertex) == 3 for vertex in body["tin"]["vertices"])
    assert all(len(triangle) == 3 for triangle in body["tin"]["triangles"])
    assert body["quality"]["spot_count"] == 206
    assert body["quality"]["coverage_pct"] > 99.9
    assert body["quality"]["max_gap_m"] > 0
    assert len(body["quality"]["max_gap_point"]) == 2
    assert body["outliers"] == []
    assert body["thresholds"] and body["thresholds"][0]["segments"]
    assert body["bench"]["floor_z_m"] == 410.0
    assert body["bench"]["mean_height_m"] == pytest.approx(10.5, abs=0.1)
    assert body["bench"]["needs_confirmation"] is False
    volume = body["volume"]
    assert volume["basis"] == "bottom"
    assert volume["area_top_m2"] == pytest.approx(contour["top"]["area_m2"])
    assert volume["area_bottom_m2"] == pytest.approx(contour["bottom"]["area_m2"])
    assert volume["mean_area_volume_m3"] == pytest.approx(volume["area_mean_m2"] * body["bench"]["mean_height_m"])
    assert volume["volume_m3"] == pytest.approx(36_939, rel=0.01)


def test_floor_defaults_to_the_layer_name(loaded):
    _, client, source, contour = loaded

    body = _surface(client, source["id"], contour).json()

    assert body["bench"]["floor_z_m"] == 410.0


def test_excluded_point_is_listed_and_left_out(loaded):
    _, client, source, contour = loaded
    first = _surface(client, source["id"], contour, floor_z_m=410.0).json()
    # Отметка, вошедшая в кровлю: её точка — вершина TIN.
    vertices = {tuple(round(c, 6) for c in vertex[:2]) for vertex in first["tin"]["vertices"]}
    spot = next(
        item
        for item in source["entities"]
        if item["role"] == "spot_heights"
        and item["geometry_type"] == "point"
        and tuple(round(c, 6) for c in item["points"][0][:2]) in vertices
    )

    body = _surface(client, source["id"], contour, floor_z_m=410.0, excluded=[spot["handle"]]).json()

    assert body["quality"]["spot_count"] == first["quality"]["spot_count"] - 1
    assert [item["id"] for item in body["excluded_points"]] == [spot["handle"]]
    assert body["excluded_points"][0]["point"] == pytest.approx(spot["points"][0])


def test_no_roles_gives_a_plane_at_the_crest(loaded):
    _, client, source, contour = loaded

    body = _surface(client, source["id"], contour, roles=[], floor_z_m=410.0, crest_z_m=420.5).json()

    assert body["ok"] is True
    assert body["plane"] is True
    assert "no_marks" in [warning["code"] for warning in body["warnings"]]
    assert {vertex[2] for vertex in body["tin"]["vertices"]} == {420.5}


def test_no_data_and_no_crest_is_a_visible_issue(loaded):
    _, client, source, contour = loaded

    response = _surface(client, source["id"], contour, roles=[], floor_z_m=410.0)

    assert response.status_code == 200
    assert response.json()["ok"] is False
    assert [issue["code"] for issue in response.json()["issues"]] == ["no_marks"]


def test_unknown_point_and_role_are_rejected(loaded):
    _, client, source, contour = loaded

    unknown = _surface(client, source["id"], contour, excluded=["nope"])
    assert unknown.status_code == 422
    assert "nope" in unknown.json()["detail"]

    role = _surface(client, source["id"], contour, roles=["block_contour"])
    assert role.status_code == 422


def test_other_organization_gets_404(loaded):
    repository, _, source, contour = loaded
    stranger = _client(repository, session=SESSION_B)

    assert _surface(stranger, source["id"], contour).status_code == 404


def test_too_much_data_is_an_input_error(loaded, monkeypatch):
    _, client, source, contour = loaded
    monkeypatch.setattr("design.spatial.cad.surface_data.MAX_SURFACE_POINTS", 10)

    response = _surface(client, source["id"], contour, floor_z_m=410.0)

    assert response.status_code == 422
    assert "предел" in response.json()["detail"]
