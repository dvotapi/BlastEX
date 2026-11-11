"""Слои дня взрыва (TASK-018, PR 2, §9 плана): перенос, запас, «устарел», выпуск.

Хранилище — в памяти, с той же проверкой версий, что у PostgreSQL
(`design/mass_blast_repository.py`); PG-тест репозитория — под
`BLASTEX_TEST_DATABASE_URL`.
"""
from __future__ import annotations

import copy
from types import SimpleNamespace
from uuid import uuid4

import pytest

from api.services import mass_blast_layers_service as service
from design.mass_blast import content_sha256
from design.mass_blast_layers import layer_open_issue, layer_seed, naryad_lines, seed_diff
from design.mass_blast_repository import MassBlastConflictError
from tests.mass_blast_block66 import context66, payload66

ORG = "org-a"


@pytest.fixture(scope="module")
def context66_v2():
    return context66()


class _Repository:
    def __init__(self, context, status: str = "approved") -> None:
        self.project = {"id": "p1", "lifecycle_status": status, "current_revision_id": "r1"}
        self.revisions = {"r1": {"id": "r1", "project_id": "p1", "context": copy.deepcopy(context)}}
        self.layers: dict[str, dict] = {}
        self.layer_revisions: list[dict] = []

    def _view(self, layer):
        return {**copy.deepcopy(layer), "stale": layer["project_revision_id"] != self.project["current_revision_id"]}

    def get_project(self, organization_id, project_id):
        return dict(self.project)

    def get_revision(self, organization_id, revision_id):
        return copy.deepcopy(self.revisions[revision_id])

    def list_layers(self, organization_id, project_id):
        return [self._view(layer) for layer in self.layers.values()]

    def get_layer(self, organization_id, layer_id):
        return self._view(self.layers[layer_id])

    def create_layer(self, organization_id, actor, project_id, *, kind, project_revision_id, allowed_statuses, single, seed, payload):
        if self.project["lifecycle_status"] not in allowed_statuses:
            raise MassBlastConflictError("статус")
        if single and any(layer["kind"] == kind for layer in self.layers.values()):
            raise MassBlastConflictError("Такой слой у проекта уже есть.")
        layer_id = str(uuid4())
        self.layers[layer_id] = {
            "id": layer_id, "project_id": project_id, "kind": kind, "project_revision_id": project_revision_id,
            "status": "draft", "version": 1, "current_revision_id": None, "seed": seed, "payload": payload,
            "created_at": "", "created_by": actor, "updated_at": "", "updated_by": actor,
        }
        return self._view(self.layers[layer_id])

    def update_layer(self, organization_id, actor, layer_id, *, expected_version, payload=None, seed=None, project_revision_id=None):
        layer = self.layers[layer_id]
        if layer["version"] != expected_version:
            raise MassBlastConflictError("версия")
        if payload is not None:
            layer["payload"] = payload
        if seed is not None:
            layer["seed"] = seed
        if project_revision_id is not None:
            layer["project_revision_id"] = project_revision_id
        layer["version"] += 1
        return self._view(layer)

    def create_layer_revision(self, organization_id, actor, layer_id, *, expected_version, context, content_sha256):
        layer = self.layers[layer_id]
        if layer["version"] != expected_version:
            raise MassBlastConflictError("версия")
        revision = {"id": str(uuid4()), "layer_id": layer_id, "revision_no": len(self.layer_revisions) + 1,
                    "project_revision_id": layer["project_revision_id"], "context": context,
                    "content_sha256": content_sha256, "created_at": "", "created_by": actor}
        self.layer_revisions.append(revision)
        layer.update(status="issued", current_revision_id=revision["id"], version=layer["version"] + 1)
        return revision

    def reissue_project(self, context):
        self.revisions["r2"] = {"id": "r2", "project_id": "p1", "context": copy.deepcopy(context)}
        self.project["current_revision_id"] = "r2"


def _economics(*, reserve=None, notifications=()):
    sections = {
        "blast_safety": [SimpleNamespace(code="BS", name="ЖК", payload={"site_code": "ZHK", **(reserve or {})})],
        "blast_notifications": [SimpleNamespace(code=code, name=code, payload={"site_code": "ZHK", **data}) for code, data in notifications],
    }
    snapshot = SimpleNamespace(revision_id="ref-1", active_items=lambda section: tuple(sections.get(section, ())))
    return SimpleNamespace(get_reference_snapshot=lambda organization_id, revision_id=None: snapshot)


def _line(lines, kind):
    return next(line for line in lines if line["kind"] == kind)


def test_open_rules_by_status_and_version(context66_v2):
    assert layer_open_issue("NARYAD", "in_review", context66_v2).startswith("«Наряд-путёвка» открывается после утверждения")
    assert layer_open_issue("NARYAD", "approved", context66_v2) is None
    assert layer_open_issue("TALON", "approved", context66_v2).endswith("после отметки взрыва.")
    assert layer_open_issue("TALON", "executed", context66_v2) is None
    assert "контекст v2" in layer_open_issue("NARYAD", "approved", {"document_context_version": 1})
    contractor = {**context66_v2, "requisites": {**context66_v2["requisites"], "drilled_by": "CONTRACTOR"}}
    assert "п. 413" in layer_open_issue("READINESS_ACT", "approved", contractor)


def test_naryad_seed_carries_project_materials(context66_v2):
    seed = layer_seed("NARYAD", context66_v2)
    explosive = _line(seed["materials"], "explosive")
    assert explosive["project_qty"] == pytest.approx(32659.3, abs=0.5)
    assert _line(seed["materials"], "primer")["project_qty"] == 198
    assert seed["blocks"] == [
        {"code": "66", "horizon": "410", "holes": 196, "charge_kg": 32675.0, "depth_mean_m": 11.64,
         "spacing_mean_m": seed["blocks"][0]["spacing_mean_m"], "burden_mean_m": seed["blocks"][0]["burden_mean_m"]}
    ]
    assert seed["project"]["blast_time"] == "13:00"


def test_block66_reserve_is_added_only_to_issue(context66_v2):
    """§7 TASK-018: запас 50 кг ВВ и 5 ПД → к выдаче = проект + запас; зоны и Q_э не меняются."""

    seed = layer_seed("NARYAD", context66_v2)
    explosive_key = _line(seed["materials"], "explosive")["key"]
    primer_key = _line(seed["materials"], "primer")["key"]
    lines = naryad_lines(seed, {"reserve": {explosive_key: 50, primer_key: 5}})
    assert _line(lines, "explosive")["issue_qty"] == pytest.approx(_line(lines, "explosive")["project_qty"] + 50)
    assert _line(lines, "primer")["issue_qty"] == 203
    assert _line(lines, "nsi_downhole")["reserve_qty"] == 0
    # Проект запас не видит: контекст ревизии тот же.
    assert context66_v2["zones"] == context66()["zones"]


def test_reserve_defaults_from_reference(context66_v2):
    seed = layer_seed("NARYAD", context66_v2)
    lines = naryad_lines(seed, {}, {"primers": 2, "nsi": 3, "starters": 1})
    assert _line(lines, "primer")["reserve_qty"] == 2 and _line(lines, "primer")["reserve_source"] == "REFERENCE"
    # Запас НСИ — один раз на группу: на самую большую строку (скважинные 198 шт).
    assert _line(lines, "nsi_downhole")["reserve_qty"] == 3
    assert sum(line["reserve_qty"] for line in lines if line["kind"] in ("nsi_downhole", "nsi_surface")) == 3
    assert _line(lines, "explosive")["reserve_qty"] == 0


def test_seed_diff_lists_changed_paths():
    assert seed_diff({"a": 1, "b": {"c": 2}}, {"a": 1, "b": {"c": 3}, "d": [1]}) == [
        {"path": "b.c", "before": 2, "after": 3},
        {"path": "d", "before": None, "after": [1]},
    ]


def test_layer_lifecycle_stale_refresh_keeps_reserve(context66_v2):
    repository = _Repository(context66_v2)
    economics = _economics()
    layer = service.create_layer(repository, economics, ORG, "user", "p1", "NARYAD", {"number": "15"})
    assert layer["stale"] is False and layer["view"]["lines"]
    key = _line(layer["seed"]["materials"], "primer")["key"]
    layer = service.update_layer(repository, economics, ORG, "user", layer["id"], {"number": "15", "reserve": {key: 5}}, layer["version"])

    # Проект перевыпущен с другим временем взрыва: наряд «устарел».
    changed = context66(payload=payload66(blast_time="14:00"))
    repository.reissue_project(changed)
    layer = service.get_layer(repository, economics, ORG, layer["id"])
    assert layer["stale"] is True and "layer_stale" in {issue["code"] for issue in layer["issues"]}
    with pytest.raises(ValueError, match="перенесите данные"):
        service.issue_layer(repository, economics, ORG, "user", layer["id"], layer["version"])

    preview = service.refresh_layer(repository, economics, ORG, "user", layer["id"], layer["version"], confirm=False)
    assert preview["applied"] is False
    assert {"path": "project.blast_time", "before": "13:00", "after": "14:00"} in preview["changes"]
    assert preview["layer"]["stale"] is True

    applied = service.refresh_layer(repository, economics, ORG, "user", layer["id"], layer["version"], confirm=True)
    layer = applied["layer"]
    assert applied["applied"] is True and layer["stale"] is False
    assert layer["payload"]["reserve"] == {key: 5}  # введённое вручную сохранилось
    assert _line(layer["view"]["lines"], "primer")["issue_qty"] == 203

    revision = service.issue_layer(repository, economics, ORG, "user", layer["id"], layer["version"])
    assert revision["context"]["kind"] == "NARYAD"
    assert revision["content_sha256"] == content_sha256(revision["context"])
    assert repository.layers[layer["id"]]["status"] == "issued"


def test_single_layer_kinds_and_status(context66_v2):
    repository = _Repository(context66_v2)
    service.create_layer(repository, None, ORG, "user", "p1", "READINESS_ACT", {})
    with pytest.raises(MassBlastConflictError):
        service.create_layer(repository, None, ORG, "user", "p1", "READINESS_ACT", {})
    with pytest.raises(ValueError, match="отметки взрыва"):
        service.create_layer(repository, None, ORG, "user", "p1", "TALON", {})
    service.create_layer(repository, None, ORG, "user", "p1", "NARYAD", {})
    service.create_layer(repository, None, ORG, "user", "p1", "NARYAD", {})  # второй наряд — можно


def test_layer_payload_is_validated_by_kind(context66_v2):
    repository = _Repository(context66_v2)
    with pytest.raises(ValueError):
        service.create_layer(repository, None, ORG, "user", "p1", "NARYAD", {"unknown": 1})
    with pytest.raises(ValueError):
        service.create_layer(repository, None, ORG, "user", "p1", "NARYAD", {"reserve": {"x": -1}})


def test_notification_per_addressee(context66_v2):
    repository = _Repository(context66_v2)
    economics = _economics(notifications=[("RTN", {"recipient_position": "Ростехнадзор", "lead_days": 1})])
    with pytest.raises(ValueError, match="адресата"):
        service.create_layer(repository, economics, ORG, "user", "p1", "NOTIFICATION", {})
    layer = service.create_layer(repository, economics, ORG, "user", "p1", "NOTIFICATION", {"notification_code": "RTN"})
    assert layer["seed"]["addressee"]["recipient_position"] == "Ростехнадзор"
    assert layer["seed"]["explosive_kg"] == pytest.approx(32659.3, abs=0.5)
    with pytest.raises(ValueError, match="уже есть"):
        service.create_layer(repository, economics, ORG, "user", "p1", "NOTIFICATION", {"notification_code": "RTN"})
    with pytest.raises(ValueError, match="Адресат уведомления не меняется"):
        service.update_layer(repository, economics, ORG, "user", layer["id"], {"notification_code": "OTHER"}, layer["version"])
    with pytest.raises(ValueError, match="вручную не правится"):
        service.create_layer(repository, economics, ORG, "user", "p1", "NOTIFICATION", {"notification_code": "RTN", "recipient_name": "Иванову"})
    # Справочника уведомлений нет — адресат вручную, без него слой не выпускается.
    bare = _Repository(context66_v2)
    layer = service.create_layer(bare, _economics(), ORG, "user", "p1", "NOTIFICATION", {})
    assert {"notify_registry_missing", "notification_addressee_missing"} <= {issue["code"] for issue in layer["issues"]}
    with pytest.raises(ValueError, match="Укажите адресата"):
        service.issue_layer(bare, _economics(), ORG, "user", layer["id"], layer["version"])
    layer = service.update_layer(bare, _economics(), ORG, "user", layer["id"], {"recipient_position": "Глава района"}, layer["version"])
    assert layer["view"]["addressee"]["recipient_position"] == "Глава района"
    revision = service.issue_layer(bare, _economics(), ORG, "user", layer["id"], layer["version"])
    assert revision["context"]["view"]["addressee"]["recipient_position"] == "Глава района"


def test_talon_admittance_time(context66_v2):
    seed = layer_seed("TALON", context66_v2)
    assert seed["admittance_not_before"] == "13:30"


def test_list_shows_each_layer_by_its_own_revision(context66_v2):
    repository = _Repository(context66_v2)
    economics = _economics()
    layer = service.create_layer(repository, economics, ORG, "user", "p1", "NARYAD", {})
    repository.reissue_project(context66(payload=payload66(blast_time="14:00")))
    listed = service.list_layers(repository, economics, ORG, "p1")[0]
    single = service.get_layer(repository, economics, ORG, layer["id"])
    assert listed["view"] == single["view"] and listed["stale"] is True


def test_refresh_keeps_the_addressee_when_the_registry_is_gone(context66_v2):
    repository = _Repository(context66_v2)
    economics = _economics(notifications=[("RTN", {"recipient_position": "Ростехнадзор"})])
    layer = service.create_layer(repository, economics, ORG, "user", "p1", "NOTIFICATION", {"notification_code": "RTN"})
    repository.reissue_project(context66(payload=payload66(blast_time="14:00")))
    applied = service.refresh_layer(repository, _economics(), ORG, "user", layer["id"], layer["version"], confirm=True)
    assert applied["layer"]["seed"]["addressee"]["recipient_position"] == "Ростехнадзор"
    assert "notification_addressee_missing" not in {issue["code"] for issue in applied["layer"]["issues"]}
