"""HTTP-маршруты подбора раскладки: старт, ход, остановка, чужая организация."""
from __future__ import annotations

import json
import logging
import time
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routers import design
from api.security import current_team_id, require_internal_access
from api.services.economics_service import get_economics_repository
from cost.v2.repository import InMemoryEconomicsRepository
from design.layout_search.jobs import LayoutSearchJobs, get_layout_search_jobs
from design.layout_search.evaluate import network_params
from design.models import BlastDesign, Hole, InitiationNetwork
from design.pattern import generate_pattern
from design.timing import resolve_times
from design.trunk_network import build_trunk_chains_network
from design.persistence import design_path, save_design
from tests.test_layout_search_jobs import _inputs

BASE = "/api/v1/design"
WAIT_S = 120.0


@pytest.fixture()
def jobs(tmp_path: Path):
    with patch("cost.persistence.data_root", return_value=tmp_path):
        instance = LayoutSearchJobs(runner="thread", budget_s=20.0)
        yield instance
        for design_id in ("d1", "d2"):
            instance.stop("org-a", design_id)
        _wait(instance, "org-a", "d1")


def _client(jobs: LayoutSearchJobs, org: str = "org-a", repository=None) -> TestClient:
    repository = repository if repository is not None else InMemoryEconomicsRepository()
    app = FastAPI()
    app.include_router(design.router, prefix="/api/v1")
    app.dependency_overrides[require_internal_access] = lambda: {"sub": "a@example.ru", "role": "admin", "org": org}
    app.dependency_overrides[current_team_id] = lambda: org
    app.dependency_overrides[get_economics_repository] = lambda: repository
    app.dependency_overrides[get_layout_search_jobs] = lambda: jobs
    return TestClient(app)


def _wait(jobs: LayoutSearchJobs, org: str, design_id: str) -> dict:
    deadline = time.monotonic() + WAIT_S
    while time.monotonic() < deadline:
        status = jobs.status(org, design_id)
        if status["state"] != "running":
            return status
        time.sleep(0.05)
    raise AssertionError("подбор не закончился вовремя")


def _body(
    design_id: str = "d1", name: str = "Блок 1", rock: str = "", fingerprint: str = "fp1", save: bool = True
) -> dict:
    payload = _inputs(name=name, design_id=design_id)
    if save and design_id not in ("", ".", "..") and not design_path("org-a", design_id).exists():
        save_design("org-a", BlastDesign.from_dict(payload))
    payload["rock_name"] = rock
    return {"design_id": design_id, "design": payload, "fingerprint": fingerprint}


def _poll(client: TestClient, design_id: str = "d1") -> dict:
    deadline = time.monotonic() + WAIT_S
    while time.monotonic() < deadline:
        data = client.get(f"{BASE}/layout-search/{design_id}").json()
        if data["state"] != "running":
            return data
        time.sleep(0.05)
    raise AssertionError("подбор не закончился вовремя")


def test_start_poll_result(jobs):
    client = _client(jobs)
    response = client.post(f"{BASE}/layout-search", json=_body())
    assert response.status_code == 202
    assert response.json()["state"] == "running"
    assert response.json()["fingerprint"] == "fp1"

    data = _poll(client)
    assert data["state"] == "done"
    assert data["fingerprint"] == "fp1"
    variants = data["result"]["best"]
    assert 1 <= len(variants) <= 3
    for variant in variants:
        assert variant["holes"]
        assert "connectors" in variant["network"]
        assert variant["cut_flank"] in ("left", "right")
        assert "row_azimuth_deg" in variant["params"]


def test_second_start_conflict(jobs):
    client = _client(jobs)
    assert client.post(f"{BASE}/layout-search", json=_body()).status_code == 202
    again = client.post(f"{BASE}/layout-search", json=_body())
    assert again.status_code == 409
    assert again.json()["detail"] == (
        "Подбор раскладки уже идёт: блок «Блок 1». Дождитесь окончания или остановите его."
    )
    other = client.post(f"{BASE}/layout-search", json=_body("d2", "Блок 2"))
    assert other.status_code == 409


def test_stop(jobs):
    client = _client(jobs)
    assert client.post(f"{BASE}/layout-search", json=_body()).status_code == 202
    stopped = client.post(f"{BASE}/layout-search/d1/stop")
    assert stopped.status_code == 200
    data = _poll(client)
    assert data["state"] in ("stopped", "done")


def test_other_organization_sees_idle(jobs):
    client = _client(jobs)
    assert client.post(f"{BASE}/layout-search", json=_body()).status_code == 202
    assert _poll(client)["state"] == "done"
    foreign = _client(jobs, org="org-b").get(f"{BASE}/layout-search/d1").json()
    assert foreign["state"] == "idle"
    assert foreign["result"] is None


def test_incompatible_stored_result_is_idle(jobs, caplog):
    # Файл итога прежней версии, который схема ответа не принимает: панель
    # блока открывается как «нет подбора», а не 500.
    from design.persistence import layout_search_path

    path = layout_search_path("org-a", "d1")
    path.parent.mkdir(parents=True, exist_ok=True)
    stale = {"fingerprint": "fp", "state": "done", "result": {"best": [{"params": "не словарь"}]}}
    path.write_text(json.dumps(stale), encoding="utf-8")
    client = _client(jobs)
    with caplog.at_level(logging.WARNING):
        for response in (client.get(f"{BASE}/layout-search/d1"), client.post(f"{BASE}/layout-search/d1/stop")):
            assert response.status_code == 200
            data = response.json()
            assert data["state"] == "idle"
            assert data["result"] is None
            assert data["fingerprint"] is None
    assert any("итог" in record.getMessage() for record in caplog.records)

    path.write_text("{не json", encoding="utf-8")
    assert client.get(f"{BASE}/layout-search/d1").json()["state"] == "idle"


def test_bad_design_id_is_404(jobs):
    client = _client(jobs)
    assert client.get(f"{BASE}/layout-search/..").status_code == 404
    assert client.post(f"{BASE}/layout-search/../stop").status_code in (404, 405)
    assert client.post(f"{BASE}/layout-search/%2E%2E/stop").status_code == 404
    assert client.post(f"{BASE}/layout-search", json=_body("..")).status_code == 404


def test_unsaved_design_is_404(jobs):
    client = _client(jobs)
    response = client.post(f"{BASE}/layout-search", json=_body(save=False))
    assert response.status_code == 404
    assert response.json()["detail"] == "Паспорт не найден — сохраните его перед подбором."
    assert jobs.status("org-a", "d1")["state"] == "idle"


def _walled_body(wired: bool) -> dict:
    """Паспорт с контурным рядом; `wired` — базовая сеть монтирует стенки."""
    body = _body()
    design = BlastDesign.from_dict(body["design"])
    params = {**design.pattern_params, "contour_row": True, "contour_spacing_m": 3.0}
    holes = generate_pattern(design.contour, params)
    network, _ = build_trunk_chains_network(holes, {"include_contour": True} if wired else {})
    design = replace(design, pattern_params=params, holes=holes, network=network)
    body["design"] = design.to_dict()
    return body


def test_child_gets_only_search_inputs(jobs):
    # В дочерний процесс уходит лишь то, что нужно перебору, а не весь паспорт:
    # из скважин — только стенки, которые монтирует базовая сеть.
    client = _client(jobs)
    for wired in (True, False):
        body = _walled_body(wired)
        body["design"]["rock_name"] = "Гранит"
        body["design"]["water_table_z_m"] = 410.0
        with patch.object(jobs, "start") as start:
            assert client.post(f"{BASE}/layout-search", json=body).status_code == 202
        inputs = start.call_args.args[3]
        assert set(inputs) == {
            "contour", "surfaces", "domains", "pattern_params", "rock_name", "name", "network", "holes"
        }
        assert inputs["rock_name"] == "Гранит"
        assert inputs["pattern_params"] == body["design"]["pattern_params"]
        walls = [h for h in body["design"]["holes"] if h["kind"] == "contour"]
        assert walls and len(walls) < len(body["design"]["holes"])
        assert inputs["holes"] == (walls if wired else [])
        # Монтаж стенок у урезанного паспорта — тот же, что у полного.
        full = network_params(BlastDesign.from_dict(body["design"]))
        assert network_params(BlastDesign.from_dict(inputs)) == full
        assert full["include_contour"] is wired


def test_background_search_wires_walls(jobs):
    # Базовая сеть монтирует контурный ряд — и у варианта из фонового подбора
    # стенки в сети и получают время (п. 5 ревью #124).
    client = _client(jobs)
    assert client.post(f"{BASE}/layout-search", json=_walled_body(True)).status_code == 202
    data = _poll(client)
    assert data["state"] == "done", data.get("error")
    variant = data["result"]["best"][0]
    holes = [Hole.from_dict(h) for h in variant["holes"]]
    walls = {h.id for h in holes if h.kind == "contour"}
    assert walls
    times, _ = resolve_times(InitiationNetwork.from_dict(variant["network"]), [h for h in holes if h.enabled])
    assert walls <= set(times)


def test_unknown_rock_warning_in_result(jobs):
    client = _client(jobs)
    assert client.post(f"{BASE}/layout-search", json=_body(rock="Нет такой")).status_code == 202
    data = _poll(client)
    assert any("Нет такой" in w for w in data["result"]["warnings"])


def test_analyze_rock_warning_unchanged():
    from tests.test_relief_api import _analyze

    from cost.v2.repository import InMemoryEconomicsRepository

    response = _analyze(
        16.0, rock_name="Нет такой", organization_id="org-a", repository=InMemoryEconomicsRepository()
    )
    assert response.relief_rock_used is False
    assert len(response.relief_warnings) == 1
    assert "Нет такой" in response.relief_warnings[0]


def test_design_id_mismatch_is_400(jobs):
    # Номер паспорта запроса и номер в данных подбора — один и тот же паспорт.
    client = _client(jobs)
    body = _body()
    body["design"]["design_id"] = "d2"
    response = client.post(f"{BASE}/layout-search", json=body)
    assert response.status_code == 400
    assert response.json()["detail"] == "Номер паспорта не совпадает с данными подбора."
    assert jobs.status("org-a", "d1")["state"] == "idle"
    # Номер в данных не задан — сверять не с чем.
    body["design"]["design_id"] = ""
    assert client.post(f"{BASE}/layout-search", json=body).status_code == 202


def _publish_rock(repository, **payload) -> None:
    from cost.v2.models import ReferenceItem

    repository.publish_references(
        "org-a",
        "tester",
        repository.list_reference_revisions("org-a")[0].id,
        {"rocks": [ReferenceItem(code="GR", name="Гранит", payload=payload)]},
        "тест",
    )


def test_relief_bounds_stored_and_change_marks_result(jobs):
    # Итог помнит границы темпа запуска; справочник пород поменялся — итог устарел.
    repository = InMemoryEconomicsRepository()
    _publish_rock(repository, relief_min_ms_m="4", relief_max_ms_m="12")
    client = _client(jobs, repository=repository)
    assert client.post(f"{BASE}/layout-search", json=_body(rock="Гранит")).status_code == 202
    data = _poll(client)
    assert data["state"] == "done", data.get("error")
    assert data["result"]["relief_min_ms_m"] == 4.0
    assert data["result"]["relief_max_ms_m"] == 12.0
    assert data["bounds_changed"] is False
    from design.persistence import layout_search_path

    stored = json.loads(layout_search_path("org-a", "d1").read_text(encoding="utf-8"))
    assert stored["rock_name"] == "Гранит"

    _publish_rock(repository, relief_min_ms_m="5", relief_max_ms_m="12")
    assert client.get(f"{BASE}/layout-search/d1").json()["bounds_changed"] is True
    _publish_rock(repository, relief_min_ms_m="4")
    assert client.get(f"{BASE}/layout-search/d1").json()["bounds_changed"] is True
    _publish_rock(repository, relief_min_ms_m="4", relief_max_ms_m="12")
    assert client.get(f"{BASE}/layout-search/d1").json()["bounds_changed"] is False


def test_relief_bounds_without_rock_and_old_file(jobs):
    # Без породы — нижняя граница по умолчанию; файл итога без границ — не «устарел».
    client = _client(jobs)
    assert client.post(f"{BASE}/layout-search", json=_body()).status_code == 202
    data = _poll(client)
    assert data["result"]["relief_min_ms_m"] == 3.0
    assert data["result"]["relief_max_ms_m"] is None
    assert data["bounds_changed"] is False

    from design.persistence import layout_search_path

    path = layout_search_path("org-a", "d1")
    stored = json.loads(path.read_text(encoding="utf-8"))
    stored.pop("rock_name")
    stored["result"].pop("relief_min_ms_m")
    stored["result"].pop("relief_max_ms_m")
    path.write_text(json.dumps(stored), encoding="utf-8")
    data = client.get(f"{BASE}/layout-search/d1").json()
    assert data["state"] == "done"
    assert data["bounds_changed"] is False
    assert data["result"]["relief_min_ms_m"] is None


def test_relief_bounds_repository_failure_is_not_change(jobs):
    # Справочник не прочитан — «устарел» не ставится: сравнивать не с чем.
    from cost.v2.repository import EconomicsRepositoryError

    repository = InMemoryEconomicsRepository()
    _publish_rock(repository, relief_min_ms_m="4")
    client = _client(jobs, repository=repository)
    assert client.post(f"{BASE}/layout-search", json=_body(rock="Гранит")).status_code == 202
    assert _poll(client)["result"]["relief_min_ms_m"] == 4.0
    with patch.object(repository, "get_reference_snapshot", side_effect=EconomicsRepositoryError("нет связи")):
        data = client.get(f"{BASE}/layout-search/d1").json()
    assert data["bounds_changed"] is False
