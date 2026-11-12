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
from tests.mass_blast_block66 import context66, design66, payload66
from tests.test_safety_design import MATERIALS

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

    def create_layer(self, organization_id, actor, project_id, *, kind, project_revision_id, allowed_statuses, single, seed, payload, unique_payload_key=None):
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

    def latest_layer_revision(self, organization_id, layer_id, project_revision_id):
        found = [item for item in self.layer_revisions
                 if item["layer_id"] == layer_id and item["project_revision_id"] == project_revision_id]
        return copy.deepcopy(found[-1]) if found else None

    def reissue_project(self, context):
        self.revisions["r2"] = {"id": "r2", "project_id": "p1", "context": copy.deepcopy(context)}
        self.project["current_revision_id"] = "r2"


def _economics(*, reserve=None, notifications=()):
    sections = {
        "blast_safety": [SimpleNamespace(code="BS", name="ЖК", payload={"site_code": "ZHK", **(reserve or {})})],
        "blast_notifications": [SimpleNamespace(code=code, name=code, payload={"site_code": "ZHK", **data}) for code, data in notifications],
        "materials": list(MATERIALS),
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
    assert layer["seed"]["intervals"] == context66_v2["network_intervals"] == ["поверхностные 25 мс", "в скважине 700 мс"]
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


# --- данные печати слоёв (TASK-018, PR 3) ------------------------------------


def test_print_data_in_seeds():
    from design.mass_blast_layers import DEFAULT_ACCEPTANCE_TEXT, READINESS_CONDITIONS, naryad_totals

    data = context66(payload=payload66(requisites={"customer_name": "ООО «Заказчик»", "contractor_name": "ООО «Подрядчик»"}))
    data["document_texts"] = {"letterhead": "ООО «КОМПЛЕКСНЫЕ РЕШЕНИЯ»\nИНН 1", "acceptance_text": ""}
    readiness = layer_seed("READINESS_ACT", data)
    assert readiness["parties"] == {"customer_name": "ООО «Заказчик»", "contractor_name": "ООО «Подрядчик»"}
    assert readiness["conditions"] == list(READINESS_CONDITIONS) and len(READINESS_CONDITIONS) == 7
    assert layer_seed("NOTIFICATION", data)["letterhead"].startswith("ООО «КОМПЛЕКСНЫЕ РЕШЕНИЯ»")
    acceptance = layer_seed("ACCEPTANCE_ACT", data)
    assert acceptance["acceptance_text"] == DEFAULT_ACCEPTANCE_TEXT
    assert set(acceptance["contract"]) == {"contract_no", "contract_date", "acceptance_appendix_no", "customer_responsible"}
    data["document_texts"]["acceptance_text"] = "Свой текст блока {блок}"
    assert layer_seed("ACCEPTANCE_ACT", data)["acceptance_text"] == "Свой текст блока {блок}"

    seed = layer_seed("NARYAD", data)
    lines = naryad_lines(seed, {"reserve": {}}, {"primers": 2, "nsi": 3, "starters": 2})
    explosive = next(line for line in lines if line["kind"] == "explosive")
    assert explosive["unit_mass_kg"] == 1.0 and explosive["issue_kg"] == explosive["issue_qty"]
    primer = next(line for line in lines if line["kind"] == "primer")
    assert primer["unit_mass_kg"] == pytest.approx(1.0) and primer["issue_kg"] == pytest.approx(primer["issue_qty"])
    totals = naryad_totals(seed, lines)
    assert totals["blocks_holes"] == 196
    assert totals["explosive_issue_kg"] == pytest.approx(explosive["issue_qty"])
    assert totals["initiation_issue_pcs"] == pytest.approx(sum(line["issue_qty"] for line in lines if line["kind"] != "explosive"))
    assert {item["label"]: item["qty"] for item in totals["reserve"]}["ПД"] == 2


def test_unknown_primer_mass_is_not_printed_as_zero():
    """ПД без массы (`primer_mass_unknown`, в расходе — 0 кг): в наряде масса неизвестна, а не 0."""

    from design.mass_blast_layers import naryad_lines

    context = {
        "document_context_version": 2,
        "blocks_v2": [
            {"consumption": [
                {"kind": "primer", "name": "ПД X", "quantity": 4.0, "unit": "шт", "mass_kg": 0.0, "warning": "primer_mass_unknown"},
                {"kind": "primer", "name": "ПД Y", "quantity": 2.0, "unit": "шт", "mass_kg": 1.8, "warning": ""},
            ]},
            {"consumption": [
                {"kind": "primer", "name": "ПД Y", "quantity": 2.0, "unit": "шт", "mass_kg": 0.0, "warning": "primer_mass_unknown"},
            ]},
        ],
    }
    lines = {line["name"]: line for line in naryad_lines(layer_seed("NARYAD", context), {}, {})}
    assert lines["ПД X"]["unit_mass_kg"] is None and lines["ПД X"]["issue_kg"] is None
    # Масса известна только у части скважин — строка тоже без массы, а не занижена.
    assert lines["ПД Y"]["unit_mass_kg"] is None and lines["ПД Y"]["issue_kg"] is None


# --- слой «Факт», наряд после взрыва, талон и акт приёмки по факту (PR 5) ------

from design.as_charged import as_charged_from_design_load  # noqa: E402
from design.as_drilled import as_drilled_from_design_hole  # noqa: E402


@pytest.fixture()
def executed(monkeypatch):
    """Проект блока 66 с фактом бурения и заряжания (заряд +2 кг) и его ревизия проекта МВ."""

    design = design66()
    context = context66(design)
    design.as_drilled_holes = [as_drilled_from_design_hole(hole) for hole in design.holes if hole.enabled]
    design.as_charged_holes = [as_charged_from_design_load(load) for load in design.loads]
    for item in design.as_charged_holes:
        item.charge_mass_kg += 2.0
    monkeypatch.setattr(service, "_load_design", lambda organization_id, design_id: design)
    return design, context


def _codes(layer):
    return {issue["code"] for issue in layer["issues"]}


def test_execution_layer_seeds_fact_and_needs_approval(executed):
    _design, context = executed
    assert layer_open_issue("EXECUTION", "in_review", context) is not None
    assert layer_open_issue("EXECUTION", "approved", context) is None
    repository = _Repository(context)
    layer = service.create_layer(repository, _economics(), ORG, "user", "p1", "EXECUTION",
                                 {"blast_date": "2026-10-14", "blast_time": "13:05", "misfired_holes": ["17"]})
    block = layer["seed"]["blocks_fact"][0]
    assert block["parameter_table"]["totals"]["drilled_count"] == 196
    assert block["graphics"]["holes"] and block["consumption"]
    rows = {row["hole_id"]: row for row in layer["view"]["blocks"][0]["parameter_table"]["rows"]}
    assert "отказ" in rows["17"]["note"]
    assert layer["view"]["blocks"][0]["parameter_table"]["totals"]["misfired_count"] == 1
    assert "fact_copied_from_design" in _codes(layer) and "fact_changed" not in _codes(layer)
    with pytest.raises(MassBlastConflictError):
        service.create_layer(repository, _economics(), ORG, "user", "p1", "EXECUTION", {})


def test_fact_recorded_after_transfer_blocks_issue(executed):
    design, context = executed
    repository = _Repository(context)
    layer = service.create_layer(repository, _economics(), ORG, "user", "p1", "EXECUTION", {})
    design.as_charged_holes[0].charge_mass_kg += 10.0
    layer = service.get_layer(repository, _economics(), ORG, layer["id"])
    assert "fact_changed" in _codes(layer)
    with pytest.raises(ValueError, match="Факт в проекте блока изменился"):
        service.issue_layer(repository, _economics(), ORG, "user", layer["id"], layer["version"])
    refreshed = service.refresh_layer(repository, _economics(), ORG, "user", layer["id"], layer["version"], confirm=True)
    assert refreshed["applied"] and "fact_changed" not in _codes(refreshed["layer"])
    revision = service.issue_layer(repository, _economics(), ORG, "user", layer["id"], refreshed["layer"]["version"])
    assert revision["context"]["kind"] == "EXECUTION"


def test_fact_of_another_grid_is_refused(executed, monkeypatch):
    design, context = executed
    other = copy.deepcopy(design)
    other.holes[0].subdrill_m += 1.0
    other.designed_sha256 = ""
    monkeypatch.setattr(service, "_load_design", lambda organization_id, design_id: other)
    with pytest.raises(ValueError, match="изменён после выпуска ревизии"):
        service.create_layer(_Repository(context), _economics(), ORG, "user", "p1", "EXECUTION", {})


def test_unknown_misfire_hole_is_an_error(executed):
    _design, context = executed
    repository = _Repository(context)
    layer = service.create_layer(repository, _economics(), ORG, "user", "p1", "EXECUTION", {"misfired_holes": ["999"]})
    assert "fact_misfire_unknown_hole" in _codes(layer)
    with pytest.raises(ValueError, match="нет в проекте"):
        service.issue_layer(repository, _economics(), ORG, "user", layer["id"], layer["version"])


def _issued_execution(repository, payload=None):
    layer = service.create_layer(repository, _economics(), ORG, "user", "p1", "EXECUTION", payload or {})
    return layer, service.issue_layer(repository, _economics(), ORG, "user", layer["id"], layer["version"])


def test_acceptance_takes_the_latest_issued_fact(executed):
    _design, context = executed
    repository = _Repository(context, status="executed")
    acceptance = service.create_layer(repository, _economics(), ORG, "user", "p1", "ACCEPTANCE_ACT", {})
    assert acceptance["view"]["fact"]["basis"] == "PROJECT" and "execution_missing" in _codes(acceptance)

    layer, first = _issued_execution(repository, {"blast_date": "2026-10-15"})
    refreshed = service.refresh_layer(repository, _economics(), ORG, "user", acceptance["id"], acceptance["version"], confirm=True)
    acceptance = refreshed["layer"]
    fact = acceptance["view"]["fact"]
    assert acceptance["seed"]["fact"]["execution_revision_id"] == first["id"]
    assert fact["basis"] == "FACT" and fact["blast_date"] == "2026-10-15"
    assert fact["explosive_kg"] == pytest.approx(32659.3 + 196 * 2.0, abs=1.0)
    assert fact["volume_basis"] == "CONTOUR"
    accepted = service.update_layer(repository, _economics(), ORG, "user", acceptance["id"],
                                    {"accepted_volume_m3": 30000}, acceptance["version"])
    assert accepted["view"]["fact"]["volume_basis"] == "ACCEPTED"
    assert accepted["view"]["fact"]["q_kg_m3"] == pytest.approx(fact["explosive_kg"] / 30000, abs=0.01)

    # Новая ревизия «Факта» — акт предлагает перенести заново.
    layer = service.get_layer(repository, _economics(), ORG, layer["id"])
    service.issue_layer(repository, _economics(), ORG, "user", layer["id"], layer["version"])
    assert "fact_layer_stale" in _codes(service.get_layer(repository, _economics(), ORG, acceptance["id"]))


def test_naryad_after_blast(executed):
    _design, context = executed
    repository = _Repository(context)
    naryad = service.create_layer(repository, _economics(), ORG, "user", "p1", "NARYAD", {"number": "15"})
    explosive = _line(naryad["view"]["lines"], "explosive")
    key = explosive["key"]
    # До взрыва графы «после взрыва» не правятся и в наряде их нет.
    assert "after_blast" not in naryad["view"]
    with pytest.raises(ValueError, match="после взрыва"):
        service.update_layer(repository, _economics(), ORG, "user", naryad["id"], {"issued": {key: 33000}}, naryad["version"])

    _issued_execution(repository, {"misfired_holes": ["17"]})
    repository.project["lifecycle_status"] = "executed"
    assert "fact_layer_stale" in _codes(service.get_layer(repository, _economics(), ORG, naryad["id"]))
    naryad = service.refresh_layer(repository, _economics(), ORG, "user", naryad["id"], naryad["version"], confirm=True)["layer"]
    surface = _line(naryad["view"]["lines"], "nsi_surface")["key"]
    naryad = service.update_layer(repository, _economics(), ORG, "user", naryad["id"],
                                  {"number": "15", "issued": {key: 33100, surface: 200}, "consumed": {surface: 195}},
                                  naryad["version"])
    lines = {line["key"]: line for line in naryad["view"]["lines"]}
    assert lines[key]["consumed_source"] == "FACT"
    assert lines[key]["consumed_qty"] == pytest.approx(32659.3 + 392, abs=1.0)
    assert lines[key]["returned_qty"] == pytest.approx(33100 - lines[key]["consumed_qty"], abs=0.01)
    assert lines[surface]["consumed_source"] == "MANUAL_OVERRIDE" and lines[surface]["returned_qty"] == 5
    assert _line(naryad["view"]["lines"], "starter")["consumed_qty"] is None  # факта стартеров нет — вручную
    block = naryad["view"]["blocks_fact"][0]
    assert block["charged_holes"] == 196 and block["misfired"] == 1 and block["fired_holes"] == 195

    # ВВ, изготавливаемые на месте: возврата нет, расход ≠ выдано — предупреждение.
    site = service.update_layer(repository, _economics(), ORG, "user", naryad["id"],
                                {**naryad["payload"], "vv_site": True}, naryad["version"])
    explosive = {line["key"]: line for line in site["view"]["lines"]}[key]
    assert explosive["returned_qty"] is None and explosive["returned_source"] == "VV_SITE"
    assert "naryad_vv_site_balance" in _codes(site)

    # Ручной возврат, который не сходится с выдано − израсходовано, — предупреждение.
    manual = service.update_layer(repository, _economics(), ORG, "user", site["id"],
                                  {**site["payload"], "vv_site": False, "returned": {key: 1.0}}, site["version"])
    assert "naryad_balance_mismatch" in _codes(manual)


def test_talon_admittance_from_fact_time(context66_v2):
    repository = _Repository(context66_v2, status="executed")
    talon = service.create_layer(repository, _economics(), ORG, "user", "p1", "TALON", {})
    assert talon["view"]["admittance_not_before"] == "13:30" and talon["view"]["admittance_source"] == "PROJECT"
    talon = service.update_layer(repository, _economics(), ORG, "user", talon["id"],
                                 {"fired_date": "2026-10-14", "fired_time": "23:45"}, talon["version"])
    assert talon["view"] == {**talon["view"], "admittance_not_before": "00:15", "admittance_date": "2026-10-15",
                             "admittance_source": "FACT"}
    with pytest.raises(ValueError):
        service.update_layer(repository, _economics(), ORG, "user", talon["id"], {"fired_time": "25:00"}, talon["version"])


def test_fact_refresh_diff_is_per_hole_and_source_errors_are_named(executed, monkeypatch):
    design, context = executed
    repository = _Repository(context)
    layer = service.create_layer(repository, _economics(), ORG, "user", "p1", "EXECUTION", {})
    target = design.as_charged_holes[0]
    target.charge_mass_kg += 10.0
    preview = service.refresh_layer(repository, _economics(), ORG, "user", layer["id"], layer["version"], confirm=False)
    paths = [change["path"] for change in preview["changes"]]
    assert f"blocks_fact[0].{target.design_hole_id}.charge_fact_kg" in paths
    assert all(not isinstance(change["after"], list) or change["path"].endswith("consumption") for change in preview["changes"])

    monkeypatch.setattr(service, "_load_design", lambda organization_id, design_id: (_ for _ in ()).throw(
        service.design_persistence.DesignNotFoundError(design_id)))
    broken = service.get_layer(repository, _economics(), ORG, layer["id"])
    assert "fact_source_invalid" in _codes(broken) and "fact_changed" not in _codes(broken)


def test_fact_line_found_by_material_code():
    from design.mass_blast_layers import naryad_after_blast

    seed = {"blocks": [], "fact": {"blocks": [], "consumption": [
        {"key": "primer:ПД-1000:", "kind": "primer", "name": "ПД-1000", "material_code": "MAT_PD", "delay_ms": None, "quantity": 7.0},
    ]}}
    lines = [{"key": "primer:ПД Сферит 1000 г:", "kind": "primer", "name": "ПД Сферит 1000 г", "material_code": "MAT_PD",
              "delay_ms": None, "unit": "шт", "unit_mass_kg": 1.0, "project_qty": 8.0, "issue_qty": 8.0}]
    after, _blocks, issues = naryad_after_blast(seed, {}, lines)
    assert len(after) == 1 and after[0]["consumed_qty"] == 7.0 and not issues


def test_misfire_in_multi_block_project_needs_the_block():
    from design.mass_blast_layers import execution_view

    def block(code):
        rows = [{"hole_id": "1", "charged": True, "charge_fact_exact_kg": 100.0, "note": ""},
                {"hole_id": "2", "charged": True, "charge_fact_exact_kg": 90.0, "note": ""}]
        return {"code": code, "parameter_table": {"rows": rows, "totals": {}}}

    seed = {"blocks_fact": [block("66"), block("67")]}
    view, issues = execution_view(seed, {"misfired_holes": ["1"]})
    assert "fact_hole_ambiguous" in {issue["code"] for issue in issues}
    view, issues = execution_view(seed, {"misfired_holes": ["67:1"], "hole_notes": {"66:2": "вода"}})
    assert not [issue for issue in issues if issue["level"] == "error"]
    totals = [b["parameter_table"]["totals"]["misfired_count"] for b in view["blocks"]]
    assert totals == [0, 1]
    assert view["blocks"][0]["parameter_table"]["rows"][1]["note"] == "вода"


def test_talon_prints_the_admittance_date_when_the_blast_moved(context66_v2):
    from design.mass_blast_layers import talon_view

    seed = layer_seed("TALON", context66_v2)
    moved = talon_view(seed, {"fired_date": "2026-10-15", "fired_time": "13:05"})
    assert moved["admittance_not_before"] == "13:35" and moved["admittance_date"] == "2026-10-15"
    issued_that_day = talon_view(seed, {"fired_date": "2026-10-15", "fired_time": "13:05", "issued_date": "2026-10-15"})
    assert issued_that_day["admittance_date"] == ""


def test_outside_project_primer_keeps_its_fact_mass():
    from design.mass_blast_layers import execution_summary, naryad_after_blast

    revision = {"seed": {"blocks_fact": [{"code": "66", "consumption": [
        {"kind": "primer", "name": "ПД-900", "unit": "шт", "delay_ms": None, "material_code": "", "quantity": 2.0, "mass_kg": 1.8},
    ]}]}, "view": {}}
    summary = execution_summary(revision, "lr-1")
    assert summary["consumption"][0]["mass_kg"] == 1.8
    after, _blocks, issues = naryad_after_blast({"blocks": [], "fact": summary}, {"issued": {"primer:ПД-900:": 3}}, [])
    line = after[0]
    assert line["outside_project"] and line["unit_mass_kg"] == 0.9
    assert line["consumed_kg"] == 1.8 and line["issued_kg"] == 2.7 and line["returned_kg"] == pytest.approx(0.9)
    assert "fact_material_not_in_project" in {issue["code"] for issue in issues}
