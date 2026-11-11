"""HTTP проекта МВ v2 (TASK-018, PR 2): флаг, контекст v2, ревизия, слои; v1 — байт-в-байт."""
from __future__ import annotations

import copy
import json
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api import config
from api.routers import mass_blast
from api.security import require_human, require_internal_access
from api.services import mass_blast_service, mass_blast_v2
from api.services.economics_service import get_economics_repository
from api.services.mass_blast_service import get_mass_blast_repository
from design.lifecycle import designed_sha256
from design.mass_blast import block_from_design, build_document_context, content_sha256
from tests.mass_blast_block66 import design66, payload66
from tests.test_api_mass_blast import USERS, _project
from tests.test_safety_design import MATERIALS, SITE_SAFETY

BASE = "/api/v1/design/mass-blast-projects"
SESSION = {"sub": "supervisor@example.ru", "role": "admin", "org": "org-a"}
# Хэш контекста v1 проекта блока 66 до TASK-018 PR 2: v1 не меняется ни на байт.
V1_CONTEXT_SHA256 = "37b412252147eb31d7f6520b6242bea96b3d8b2bcccd2ac7db343aaaa2c86ff5"


@pytest.fixture(scope="module")
def design():
    design = design66()
    design.designed_sha256 = designed_sha256(design)
    return design


@pytest.fixture(scope="module")
def block(design):
    return block_from_design(design, code="66", horizon="410")


def test_v1_context_is_unchanged():
    block = block_from_design(design66(), code="66", horizon="410")
    payload = {**_project(), "blocks": [block.to_dict()], "blast_time": "13:00"}
    assert content_sha256(build_document_context(payload, [block])) == V1_CONTEXT_SHA256


class _Repository:
    def __init__(self, stored: dict) -> None:
        self.stored = stored
        self.created: list[dict] = []
        self.revisions: list[tuple] = []

    def get_project(self, organization_id, project_id):
        return copy.deepcopy(self.stored)

    def create_project(self, organization_id, actor, payload):
        self.created.append(payload)
        return {
            **payload, "id": "project-1", "lifecycle_status": "draft", "version": 1, "current_revision_id": None,
            "block_design_ids": [], "updated_at": "", "created_at": "", "created_by": actor, "updated_by": actor,
        }

    def update_project(self, organization_id, actor, project_id, payload, expected_version):
        return self.create_project(organization_id, actor, payload)

    def list_draft_attachments(self, organization_id, project_id):
        return []

    def create_revision(self, organization_id, actor, project_id, expected_version, reference_revision_id, context, blocks, formula, template, sha):
        self.revisions.append((reference_revision_id, context, formula, sha))
        return {
            "id": "rev-1", "project_id": project_id, "revision_no": 1, "previous_revision_id": None,
            "reference_revision_id": reference_revision_id, "technical_formula_version": formula,
            "document_template_version": template, "content_sha256": sha, "created_at": "", "created_by": actor,
            "context": context,
        }


def _snapshot():
    sections = {
        "blast_safety": (SimpleNamespace(code="BS", name="ЖК", payload=dict(SITE_SAFETY), is_active=True),),
        "materials": tuple(SimpleNamespace(code=m["code"], name=m["name"], payload=m["payload"], is_active=True) for m in MATERIALS),
        "rocks": (SimpleNamespace(code="R", name="Габбро", payload={"hardness_f": 14}, is_active=True),),
    }
    return SimpleNamespace(revision_id="ref-1", active_items=lambda section: sections.get(section, ()), item=lambda section, code: None)


def _client(monkeypatch, repository, design, *, enabled: bool = True) -> TestClient:
    monkeypatch.setenv("BLASTEX_USERS_JSON", json.dumps(USERS))
    if enabled:
        monkeypatch.setenv(config.MASS_BLAST_V2_ENABLED_ENV, "1")
    else:
        monkeypatch.delenv(config.MASS_BLAST_V2_ENABLED_ENV, raising=False)
    monkeypatch.setattr(mass_blast_service, "_blocks_from_payload", lambda organization_id, payload: [block_from_design(design, code="66", horizon="410")])
    monkeypatch.setattr(mass_blast_v2.design_persistence, "load_design", lambda organization_id, design_id: design)
    app = FastAPI()
    app.include_router(mass_blast.router, prefix="/api/v1")
    app.dependency_overrides[require_internal_access] = lambda: SESSION
    app.dependency_overrides[require_human] = lambda: SESSION
    app.dependency_overrides[get_mass_blast_repository] = lambda: repository
    snapshot = _snapshot()
    app.dependency_overrides[get_economics_repository] = lambda: SimpleNamespace(
        get_reference_snapshot=lambda organization_id, requested=None: snapshot
    )
    return TestClient(app)


def _body(**changes) -> dict:
    payload = {**_project(), **{k: v for k, v in payload66().items() if k not in ("blocks", "responsibilities")}}
    payload["blocks"] = [{"design_id": "block-66", "code": "66", "horizon": "410", "details": {"purpose": "MINING", "rock_text": "порфириты"}}]
    payload.update(changes)
    return payload


def test_v2_project_needs_the_flag(monkeypatch, design):
    repository = _Repository({})
    response = _client(monkeypatch, repository, design, enabled=False).post(BASE, json=_body())
    assert response.status_code == 422 and "модуль выключен" in response.json()["detail"]
    response = _client(monkeypatch, repository, design).post(BASE, json=_body())
    assert response.status_code == 201, response.text
    stored = repository.created[-1]
    assert stored["context_version"] == 2
    assert stored["blocks"][0]["details"]["purpose"] == "MINING"
    assert stored["explosives"]["initiation"].startswith("НСИ")


def test_v1_project_keeps_its_payload(monkeypatch, design):
    repository = _Repository({})
    body = _project()
    response = _client(monkeypatch, repository, design).post(BASE, json=body)
    assert response.status_code == 201
    stored = repository.created[-1]
    for key in mass_blast_v2.V2_PAYLOAD_KEYS:
        assert key not in stored
    assert "details" not in stored["blocks"][0]
    details = {**body, "blocks": [{"design_id": "d", "details": {"purpose": "MINING"}}]}
    assert _client(monkeypatch, repository, design).post(BASE, json=details).status_code == 422


def test_v2_project_does_not_go_back_to_v1(monkeypatch, design):
    stored = {**_body(), "id": "p1", "version": 3, "context_version": 2}
    repository = _Repository(stored)
    response = _client(monkeypatch, repository, design).put(f"{BASE}/p1", json={**_project(), "expected_version": 3})
    assert response.status_code == 422 and "обратно на v1" in response.json()["detail"]


def _stored_v2(block) -> dict:
    stored = {**_body(), "id": "p1", "version": 2, "lifecycle_status": "draft", "reference_revision_id": "ref-1"}
    stored["responsibilities"] = payload66()["responsibilities"]
    stored["responsibilities"][0]["account_email"] = "manager@example.ru"
    stored["responsibilities"][1]["account_email"] = "supervisor@example.ru"
    stored["blocks"] = [{**block.to_dict(), "details": {"purpose": "MINING"}}]
    return stored


def test_validate_v2_returns_context_and_issues(monkeypatch, design, block):
    repository = _Repository(_stored_v2(block))
    response = _client(monkeypatch, repository, design).post(f"{BASE}/p1/validate")
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["context"]["document_context_version"] == 2
    assert data["context"]["project"]["reference_revision_id"] == "ref-1"
    codes = {issue["code"] for issue in data["issues"]}
    assert "situation_missing" in codes and "mass_blast_site_missing" in codes
    assert data["valid"] is True, [issue for issue in data["issues"] if issue["level"] == "error"]


def test_validate_v2_reports_a_changed_source(monkeypatch, design, block):
    stored = _stored_v2(block)
    stored["blocks"][0]["design_sha256"] = "0" * 64
    response = _client(monkeypatch, _Repository(stored), design).post(f"{BASE}/p1/validate")
    assert "stale_source" in {issue["code"] for issue in response.json()["issues"]}


def test_v2_revision_is_released_with_v2_formula(monkeypatch, design, block):
    repository = _Repository(_stored_v2(block))
    response = _client(monkeypatch, repository, design).post(f"{BASE}/p1/revisions", json={"expected_version": 2})
    assert response.status_code == 201, response.text
    reference, context, formula, sha = repository.revisions[-1]
    assert reference == "ref-1" and formula == "mass-blast-v2"
    assert sha == content_sha256(context)
    assert context["blocks_v2"][0]["parameter_table"]["totals"]["hole_count"] == 196


def test_v2_revision_with_errors_is_refused(monkeypatch, design, block):
    stored = _stored_v2(block)
    stored["schedule"] = {"station": ""}
    response = _client(monkeypatch, _Repository(stored), design).post(f"{BASE}/p1/revisions", json={"expected_version": 2})
    assert response.status_code == 422 and "взрывной станции" in response.json()["detail"]


def test_layer_routes_are_hidden_without_the_flag(monkeypatch, design):
    client = _client(monkeypatch, _Repository({}), design, enabled=False)
    assert client.get(f"{BASE}/p1/layers").status_code == 404
    assert client.post(f"{BASE}/p1/layers", json={"kind": "NARYAD"}).status_code == 404
    assert client.get(f"{BASE}/layers/l1").status_code == 404


def test_layer_creation_needs_an_approved_project(monkeypatch, design, block):
    stored = {**_stored_v2(block), "lifecycle_status": "in_review", "current_revision_id": "rev-1"}
    repository = _Repository(stored)
    repository.get_revision = lambda organization_id, revision_id: {"id": "rev-1", "context": {"document_context_version": 2}}
    response = _client(monkeypatch, repository, design).post(f"{BASE}/p1/layers", json={"kind": "NARYAD"})
    assert response.status_code == 422 and "после утверждения" in response.json()["detail"]
