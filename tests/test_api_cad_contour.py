"""HTTP-маршруты контура блока: линии для контура и предпросмотр (TASK-013, PR 2)."""
from __future__ import annotations

from pathlib import Path

import pytest

from tests.test_api_cad import BASE, SESSION_B, _client, _upload
from design.spatial.cad.repository import InMemoryCadRepository

FIXTURE = Path(__file__).parent / "fixtures" / "cad" / "block66.dxf"


@pytest.fixture(scope="module")
def loaded():
    repository = InMemoryCadRepository()
    client = _client(repository)
    source = _upload(client, ("block66.dxf", FIXTURE.read_bytes()))["sources"][0]
    return repository, client, source


def _contour(client, source_id: str, **payload):
    return client.post(f"{BASE}/sources/{source_id}/contour", json=payload)


def _entity(source: dict, handle: str) -> dict:
    return next(item for item in source["entities"] if item["handle"] == handle)


def test_lines_for_the_contour_of_block_66(loaded):
    _, client, source = loaded

    response = client.post(f"{BASE}/sources/{source['id']}/contour/lines", json={})

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["splits"]["769"], "контур пересекают фрагменты бровок"
    assert body["intersections"]
    top_sets = [{part["handle"] for part in line["parts"]} for line in body["crests_top"]]
    assert any({"6C3", "6BE", "72E"} <= handles for handles in top_sets)
    assert len(body["crests_bottom"]) == 1
    assert all(gap["reason"] in {"gap", "turn"} for gap in body["gaps"])


def test_ready_contour_preview_of_block_66(loaded):
    _, client, source = loaded

    response = _contour(client, source["id"], method="ready", handle="769")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["ok"] is True and body["issues"] == []
    assert len(body["top"]["points"]) == 33
    assert body["top"]["area_m2"] == pytest.approx(2789.93, abs=0.05)
    assert body["bottom"]["area_m2"] > body["top"]["area_m2"]
    assert body["mean_area_m2"] == pytest.approx((body["top"]["area_m2"] + body["bottom"]["area_m2"]) / 2)
    assert len(body["free_faces"]) == 27
    assert len(body["flanks"]) == 2
    assert body["bench"]["crest_z_m"] == pytest.approx(420.0, abs=0.7)
    assert body["bench"]["toe_z_m"] == pytest.approx(410.0)
    assert body["bench"]["toe_source"] == "floor"
    assert [item["kind"] for item in body["items"]] == ["part"]


def test_assembly_of_crest_and_fragment_shows_the_self_intersection(loaded):
    _, client, source = loaded
    items = [
        {"kind": "part", "handle": handle, "start_m": 0, "end_m": _entity(source, handle)["length_m"]}
        for handle in ("6C3", "733")
    ]

    body = _contour(client, source["id"], method="assembly", items=items).json()

    assert body["ok"] is False
    assert [issue["code"] for issue in body["issues"]] == ["self_intersection"]
    assert len(body["issues"][0]["point"]) == 2
    assert [info["link"] for info in body["item_info"]] == ["closing", "closing"]


def test_crest_block_preview_has_both_flanks(loaded):
    _, client, source = loaded
    lines = client.post(f"{BASE}/sources/{source['id']}/contour/lines", json={}).json()
    main = next(line for line in lines["crests_top"] if {"6C3", "6BE", "72E"} <= {p["handle"] for p in line["parts"]})
    start, end = main["points"][5][:2], main["points"][20][:2]

    body = _contour(
        client, source["id"], method="crest", crest={"start": start, "end": end, "width_m": 20, "side": "auto"}
    ).json()

    assert body["ok"] is True, body["issues"]
    assert len(body["flanks"]) == 2 and all(flank["end"] for flank in body["flanks"])
    assert body["crest_line"]


def test_click_outside_is_a_visible_issue_not_an_http_error(loaded):
    _, client, source = loaded
    x0, y0, x1, y1 = source["extent"]

    response = _contour(client, source["id"], method="click", point=[x1 + 500, y1 + 500])

    assert response.status_code == 200
    assert [issue["code"] for issue in response.json()["issues"]] == ["outside"]


def test_unknown_handle_and_role_are_rejected(loaded):
    _, client, source = loaded
    unknown = _contour(client, source["id"], method="assembly", items=[{"kind": "part", "handle": "nope", "end_m": 1}])
    assert unknown.status_code == 422
    assert "nope" in unknown.json()["detail"]

    role = client.post(f"{BASE}/sources/{source['id']}/contour/lines", json={"roles": ["bogus"]})
    assert role.status_code == 422


def test_other_organization_gets_404(loaded):
    repository, _, source = loaded
    stranger = _client(repository, session=SESSION_B)

    assert stranger.post(f"{BASE}/sources/{source['id']}/contour/lines", json={}).status_code == 404
    assert _contour(stranger, source["id"], method="ready", handle="769").status_code == 404


@pytest.mark.parametrize("roles", [[], ["contour_line"]])
def test_lines_for_roles_without_lines_still_return_crests(loaded, roles):
    _, client, source = loaded

    response = client.post(f"{BASE}/sources/{source['id']}/contour/lines", json={"roles": roles})

    assert response.status_code == 200, response.text
    assert response.json()["splits"] == {}
    assert response.json()["crests_top"]


def test_too_many_contour_lines_still_return_crests_for_the_crest_method(loaded, monkeypatch):
    from design.spatial.cad import contour as contour_module

    _, client, source = loaded
    monkeypatch.setattr(contour_module, "MAX_CONTOUR_SEGMENTS", 5)

    response = client.post(f"{BASE}/sources/{source['id']}/contour/lines", json={})

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["splits"] == {}
    assert "предел 5" in body["splits_error"]
    assert body["crests_top"] and body["crests_bottom"]
