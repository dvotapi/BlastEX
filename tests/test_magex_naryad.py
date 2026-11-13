"""Наряд-путёвка ↔ MagEX: выписка блока 66, разрешение, очередь, блокировки (TASK-018 PR 7, §4–§7)."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from api.services import magex_naryad_service as magex
from api.services import mass_blast_documents_v2 as documents
from api.services import mass_blast_layers_service as layers
from design.magex.jws import content_sha256
from design.magex.naryad_payload import MagexContext, blaster_ref, build_naryad_payload, magex_lines, qty_text, site_uuid
from design.mass_blast_repository import MassBlastConflictError
from tests.magex_contract import verify
from tests.magex_fakes import (
    CATALOG,
    LAYER_ID,
    MAGEX_ORG,
    MATERIAL_IDS,
    ORG,
    WAREHOUSE,
    FakeMagex,
    MemoryRepository,
    configure,
    economics,
    naryad_seed,
)

NOW = datetime(2026, 10, 14, 5, 0, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def _magex(monkeypatch):
    configure(monkeypatch)
    magex._catalog_cache.clear()
    yield
    magex._catalog_cache.clear()


def _approve(repository, fake, **options):
    return magex.approve(
        repository, economics(**options), ORG, "manager@example.ru", LAYER_ID, repository.layer["version"],
        transport=fake, now=NOW,
    )


# --- содержимое выписки ----------------------------------------------------

def _ctx(**changes) -> MagexContext:
    base = dict(
        organization=MAGEX_ORG, organization_id=ORG, site_code="ZHK", site_name="Жуков Камень", warehouse_id=WAREHOUSE,
        materials={code: material_id for code, material_id in MATERIAL_IDS.items()},
        catalog={item["id"]: item for item in CATALOG},
        blaster={"ref": blaster_ref(ORG, "ЮФ60АВ"), "name": "Трегубов Александр Иванович", "index": "ЮФ60АВ"},
        approver={"name": "Гизатуллин Р. Р.", "position": "начальник участка"}, admissions_confirmed=True,
    )
    base.update(changes)
    return MagexContext(**base)


def _lines(reserve=None):
    from design.mass_blast_layers import naryad_lines

    return naryad_lines(naryad_seed(), {"reserve": reserve or {}}, {})


def test_block66_naryad_with_five_blocks_fits_and_passes_contract():
    """§7 задачи: 5 блоков-строк, «по проекту + запас», строка ≤ 2 000 и проходит проверку MagEX."""

    from design.magex import jws as jws_module
    from tests.magex_fakes import FIXTURES

    seed = naryad_seed()
    seed["blocks"] = [{**seed["blocks"][0], "code": f"6{index}", "horizon": "410"} for index in range(5)]
    payload = {"number": "66-26", "issue_date": "2026-10-14", "permit_number": "РВ-66", "permit_date": "2026-01-15",
               "vehicle_model": "КамАЗ 43118", "vehicle_plate": "А123ВС96", "driver": "Петров П. П.",
               "delivery": "Иванов И. И.; Сидоров С. С."}
    content, issues = build_naryad_payload(LAYER_ID, seed, payload, _lines(), _ctx(), ver=1, iat=1_789_448_400, approved_at=NOW)
    assert [item for item in issues if item["level"] == "error"] == []
    key = jws_module.load_signing_key((FIXTURES / "keys" / "TEST-ONLY-private.pem").read_text(), "TEST-ONLY-magex-fixture")
    token = jws_module.sign_naryad(content, key)
    assert len(token) <= 2000
    assert verify(token) == content
    assert len(content["blocks"]) == 5 and content["blocks"][0] == {
        "code": "60", "name": "Блок 60", "horizon": "410", "holes": 196, "charge_kg": "32675.000",
    }
    assert content["site"]["id"] == site_uuid(ORG, "ZHK")
    assert content["permit_vr"] == {"number": "РВ-66", "date": "2026-01-15"}
    assert content["vehicle"] == {"model": "КамАЗ 43118", "plate": "А123ВС96"}
    assert content["delivery"] == [{"name": "Иванов И. И."}, {"name": "Сидоров С. С."}]
    assert content["approved"] == {"name": "Гизатуллин Р. Р.", "position": "начальник участка", "at": "2026-10-14T05:00:00+00:00"}
    assert content["blast_on"] == "2026-10-14" and content["project"] == "Проект МВ № 66-26 блок № 60, 61, 62, 63, 64"


def test_reserve_changes_qty_but_not_project():
    """Запас 50 кг ВВ и 5 ПД: «Выписано» = по проекту + запас; проект запасом не меняется."""

    plain, _ = magex_lines(_lines(), _ctx().materials, _ctx().catalog)
    lines = _lines({"explosive:ЭВВ Порэмит 1А:": 50, "primer:ПД Сферит-ДП 1000 г:": 5})
    reserved, _ = magex_lines(lines, _ctx().materials, _ctx().catalog)
    by_id = lambda rows: {row["material_id"]: row["qty"] for row in rows}  # noqa: E731
    assert by_id(reserved)[MATERIAL_IDS["MAT_EVV"]] - by_id(plain)[MATERIAL_IDS["MAT_EVV"]] == Decimal("50")
    assert by_id(reserved)[MATERIAL_IDS["MAT_PD_1000"]] == Decimal("203")
    assert qty_text(Decimal("32709.326")) == "32709.326" and qty_text(0) == "0.000"


def test_unmapped_material_forbids_approval():
    rows, issues = magex_lines(_lines(), {}, _ctx().catalog)
    assert rows == []
    assert [item["code"] for item in issues] == ["magex_material_unmapped"]


def test_cartridges_round_up_to_whole_pieces():
    lines = [{"key": "explosive:Патрон:", "name": "Патрон", "unit": "кг", "issue_qty": 101.0, "material_code": "C"}]
    catalog = {"m": {"id": "m", "accounting_unit": "pcs", "unit_mass_kg": "25.000"}}
    rows, issues = magex_lines(lines, {"C": "m"}, catalog)
    assert rows[0]["qty"] == Decimal(5)
    assert issues[0]["code"] == "magex_qty_rounded"


def test_pieces_must_be_whole():
    lines = [{"key": "primer:ПД:", "name": "ПД", "unit": "шт", "issue_qty": 2.5, "material_code": "P"}]
    rows, issues = magex_lines(lines, {"P": "m"}, {"m": {"id": "m", "accounting_unit": "pcs"}})
    assert rows == [] and issues[0]["code"] == "magex_qty_not_integer"


def test_same_material_lines_are_summed():
    lines = [
        {"key": "a", "name": "НСИ 25", "unit": "шт", "issue_qty": 3.0, "material_code": "N"},
        {"key": "b", "name": "НСИ 25 (2)", "unit": "шт", "issue_qty": 4.0, "material_code": "N"},
    ]
    rows, _ = magex_lines(lines, {"N": "m"}, {"m": {"id": "m", "accounting_unit": "pcs"}})
    assert rows == [{"material_id": "m", "qty": Decimal(7), "keys": ["a", "b"], "unit": "pcs"}]


def test_missing_people_and_admissions_are_errors():
    seed = naryad_seed()
    content, issues = build_naryad_payload(
        LAYER_ID, seed, {}, _lines(), _ctx(blaster=None, approver={}, admissions_confirmed=False, warehouse_id=""),
        ver=1, iat=0, approved_at=NOW,
    )
    codes = {item["code"] for item in issues if item["level"] == "error"}
    assert {"magex_number_missing", "magex_issue_date_missing", "magex_warehouse_missing", "magex_blaster_missing",
            "magex_approver_missing", "magex_admissions_unconfirmed"} <= codes


def test_blaster_ref_is_stable_and_safetymain_wins():
    assert blaster_ref(ORG, " ЮФ60АВ ") == blaster_ref(ORG, "юф60ав")
    assert blaster_ref(ORG, "x", "32DB5D1C-F05B-5E1E-AB77-3F0B5C0D2909") == "32db5d1c-f05b-5e1e-ab77-3f0b5c0d2909"


# --- разрешение -----------------------------------------------------------

def test_approve_accepted_makes_revision_printable_with_qr():
    repository, fake = MemoryRepository(), FakeMagex()
    result = _approve(repository, fake)
    assert result["outcome"] == "ACCEPTED" and result["accepted_ver"] == 1
    version = repository.versions[0]
    assert version["status"] == "ACCEPTED"
    revision = repository.revisions[version["layer_revision_id"]]
    assert revision["context"]["magex"]["jws"] == version["jws"] == fake.naryads[LAYER_ID]["jws"]
    # Резерв в MagEX = «Выписано».
    lines = {line["material_id"]: line["qty"] for line in fake.naryads[LAYER_ID]["payload"]["lines"]}
    assert lines[MATERIAL_IDS["MAT_PD_1000"]] == "198.000"
    assert fake._reserved(MATERIAL_IDS["MAT_PD_1000"]) == Decimal(198)
    pdf, _ = documents.layer_document(repository, ORG, revision["id"])
    assert pdf.startswith(b"%PDF")


def test_insufficient_available_leaves_nothing_and_no_print():
    repository = MemoryRepository()
    fake = FakeMagex(stock={**{key: Decimal(100000) for key in MATERIAL_IDS.values()}, MATERIAL_IDS["MAT_PD_1000"]: Decimal(10)})
    result = _approve(repository, fake)
    assert result["outcome"] == "REJECTED"
    assert result["rejection"]["code"] == "INSUFFICIENT_AVAILABLE"
    assert [line["material_id"] for line in result["rejection"]["details"]["lines"]] == [MATERIAL_IDS["MAT_PD_1000"]]
    assert repository.revisions == {} and repository.layer["status"] == "draft"
    assert repository.versions[0]["status"] == "REJECTED"


def test_unavailable_magex_queues_the_same_string_then_accepts():
    repository, fake = MemoryRepository(), FakeMagex()
    magex.availability(repository, economics(), ORG, LAYER_ID, transport=fake)  # окно открыто — номенклатура прочитана
    fake.down = True
    result = _approve(repository, fake)
    assert result["outcome"] == "PENDING"
    version = repository.versions[0]
    assert version["status"] == "PENDING" and version["attempts"] == 1
    revision_id = version["layer_revision_id"]
    with pytest.raises(MassBlastConflictError, match="ожидает MagEX"):
        documents.layer_document(repository, ORG, revision_id)
    # Очередь: срок ещё не пришёл — ничего.
    assert magex.process_due(repository, transport=fake, now=NOW) == 0
    fake.down = False
    assert magex.process_due(repository, transport=fake, now=NOW + timedelta(seconds=31)) == 1
    assert repository.versions[0]["status"] == "ACCEPTED"
    assert fake.naryads[LAYER_ID]["jws"] == version["jws"]
    documents.layer_document(repository, ORG, revision_id)


def test_repeat_without_changes_is_unchanged_not_a_new_version():
    repository, fake = MemoryRepository(), FakeMagex()
    _approve(repository, fake)
    result = _approve(repository, fake)
    assert result["outcome"] == "UNCHANGED"
    assert [item["ver"] for item in repository.versions] == [1]


def test_new_content_is_new_version_and_supersedes_pending():
    repository, fake = MemoryRepository(), FakeMagex()
    magex.catalog(ORG, magex.client_for(ORG, fake))
    fake.down = True
    _approve(repository, fake)
    fake.down = False
    repository.layer["payload"] = {**repository.layer["payload"], "reserve": {"primer:ПД Сферит-ДП 1000 г:": 5}}
    result = _approve(repository, fake)
    assert result["outcome"] == "ACCEPTED"
    assert [(item["ver"], item["status"]) for item in repository.versions] == [(1, "SUPERSEDED"), (2, "ACCEPTED")]
    assert fake.naryads[LAYER_ID]["payload"]["ver"] == 2


def test_only_newest_accepted_version_prints():
    repository, fake = MemoryRepository(), FakeMagex()
    _approve(repository, fake)
    first = repository.versions[0]["layer_revision_id"]
    repository.layer["payload"] = {**repository.layer["payload"], "reserve": {"primer:ПД Сферит-ДП 1000 г:": 5}}
    _approve(repository, fake)
    with pytest.raises(MassBlastConflictError, match="более новую версию"):
        documents.layer_document(repository, ORG, first)
    documents.layer_document(repository, ORG, repository.versions[1]["layer_revision_id"])


def test_never_read_catalog_and_no_network_is_an_error():
    repository, fake = MemoryRepository(), FakeMagex()
    fake.down = True
    with pytest.raises(ValueError, match="Номенклатура MagEX недоступна"):
        _approve(repository, fake)
    assert repository.versions == []


def test_rejection_on_validation_lists_fields():
    repository = MemoryRepository(payload={"number": "", "issue_date": "2026-10-14"})
    with pytest.raises(magex.MagexValidationError) as caught:
        _approve(repository, FakeMagex())
    codes = {item["code"] for item in caught.value.issues}
    assert {"magex_number_missing", "magex_admissions_unconfirmed"} <= codes
    assert repository.versions == []


def test_after_issue_locked_fields_and_new_naryad_needed():
    repository, fake = MemoryRepository(), FakeMagex()
    _approve(repository, fake)
    fake.naryads[LAYER_ID]["status"] = "issued"
    magex.refresh_execution(repository, ORG, LAYER_ID, transport=fake)
    state = magex.layer_state(repository, ORG, LAYER_ID)
    assert state["issued"] is True and "magex_warehouse_id" in state["locked_fields"]
    # Правка запаса после выдачи — отказ сервера.
    with pytest.raises(ValueError, match="уже выданы"):
        layers.update_layer(repository, economics(), ORG, "a", LAYER_ID,
                            {**repository.layer["payload"], "reserve": {"primer:ПД Сферит-ДП 1000 г:": 5}},
                            repository.layer["version"])
    # Изменённые количества (например, после переноса проекта) — «Разрешить» не отправит.
    repository.layer["payload"]["reserve"] = {"primer:ПД Сферит-ДП 1000 г:": 7}
    with pytest.raises(magex.MagexValidationError) as caught:
        _approve(repository, fake)
    assert {item["code"] for item in caught.value.issues} == {"magex_field_locked"}


def test_cancel_before_issue_and_refused_after():
    repository, fake = MemoryRepository(), FakeMagex()
    _approve(repository, fake)
    state = magex.cancel(repository, ORG, "a", LAYER_ID, "Взрыв перенесён", transport=fake)
    assert state["execution"]["status"] == "cancelled" and state["execution"]["status_label"] == "отменена"
    # Отменённую наряд-путёвку не печатают (QR склад уже не примет).
    with pytest.raises(MassBlastConflictError, match="отменена"):
        documents.layer_document(repository, ORG, repository.versions[0]["layer_revision_id"])
    repository2, fake2 = MemoryRepository(), FakeMagex()
    _approve(repository2, fake2)
    fake2.naryads[LAYER_ID]["status"] = "issued"
    with pytest.raises(ValueError, match="уже выданы"):
        magex.cancel(repository2, ORG, "a", LAYER_ID, "отмена", transport=fake2)


def test_issue_without_approve_is_refused_online_and_marked_offline(monkeypatch):
    repository = MemoryRepository()
    with pytest.raises(ValueError, match="Разрешить"):
        layers.issue_layer(repository, economics(), ORG, "a", LAYER_ID, repository.layer["version"])
    configure(monkeypatch, url="")
    revision = layers.issue_layer(repository, economics(), ORG, "a", LAYER_ID, repository.layer["version"])
    assert revision["context"]["magex"]["mode"] == "OFFLINE"
    assert "MAGEX_API_URL" in revision["context"]["magex"]["reason"]


def test_flag_off_keeps_revision_without_magex(monkeypatch):
    from api import config
    from api.services import magex_settings

    monkeypatch.setenv(config.MAGEX_INTEGRATION_ENABLED_ENV, "0")
    magex_settings.reset_magex_settings()
    repository = MemoryRepository()
    revision = layers.issue_layer(repository, economics(), ORG, "a", LAYER_ID, repository.layer["version"])
    assert "magex" not in revision["context"]
    viewed = layers.get_layer(repository, economics(), ORG, LAYER_ID)
    assert "magex" not in viewed["view"]


def test_availability_column_and_shortage():
    repository = MemoryRepository()
    fake = FakeMagex(stock={**{key: Decimal(100000) for key in MATERIAL_IDS.values()}, MATERIAL_IDS["MAT_PD_1000"]: Decimal(100)})
    answer = magex.availability(repository, economics(), ORG, LAYER_ID, transport=fake)
    assert answer["items"]["primer:ПД Сферит-ДП 1000 г:"] == {
        "available": 100.0, "short": True, "shared": False, "material_id": MATERIAL_IDS["MAT_PD_1000"],
        "available_magex": 100.0, "factor": 1.0, "whole": True,
    }
    assert answer["shortages"][0]["required"] == 198.0
    assert answer["calculated_at"] == "2026-10-14T02:11:00Z"


def test_view_shows_magex_state_and_blaster_from_reference():
    repository, fake = MemoryRepository(), FakeMagex()
    _approve(repository, fake)
    viewed = layers.get_layer(repository, economics(), ORG, LAYER_ID)
    state = viewed["view"]["magex"]
    assert state["mode"] == "ONLINE" and state["accepted_ver"] == 1
    assert state["blaster"]["code"] == "BL-01" and state["blaster"]["source"] == "PROJECT"
    assert viewed["view"]["defaults"]["magex_warehouse_id"]["value"] == WAREHOUSE


def test_after_blast_columns_come_from_magex():
    repository, fake = MemoryRepository(status="executed"), FakeMagex()
    _approve(repository, fake)
    pd = MATERIAL_IDS["MAT_PD_1000"]
    naryad = fake.naryads[LAYER_ID]
    naryad.update(status="closed", issued={pd: "198.000"}, consumed={pd: "196.000"},
                  block_results=[{"code": "66", "holes_charged": 196, "charged_kg": "32600.000", "charges_blasted": 196,
                                  "blasted_kg": "32600.000", "misfires": 0, "deviation_kg": "-75.000"}])
    magex.refresh_execution(repository, ORG, LAYER_ID, transport=fake)
    viewed = layers.get_layer(repository, economics(), ORG, LAYER_ID)
    line = next(item for item in viewed["view"]["lines"] if item["kind"] == "primer")
    assert line["issued_qty"] == 198.0 and line["consumed_qty"] == 196.0 and line["consumed_source"] == "MAGEX"
    assert line["returned_qty"] == 0.0 and line["returned_source"] == "MAGEX"
    block = viewed["view"]["blocks_fact"][0]
    assert block["charged_kg"] == 32600.0 and block["source"] == "MAGEX"


def test_semantic_hash_ignores_signing_moment():
    content, _ = build_naryad_payload(LAYER_ID, naryad_seed(), {"number": "1", "issue_date": "2026-10-14"}, _lines(), _ctx(),
                                      ver=1, iat=1, approved_at=NOW)
    later, _ = build_naryad_payload(LAYER_ID, naryad_seed(), {"number": "1", "issue_date": "2026-10-14"}, _lines(), _ctx(),
                                    ver=2, iat=99, approved_at=NOW + timedelta(hours=1))
    assert magex._semantic_sha(content) == magex._semantic_sha(later)
    assert content_sha256(content) != content_sha256(later)
    assert json.dumps(content, ensure_ascii=False).count("\\u") == 0


def test_back_to_accepted_while_newer_is_queued_is_a_new_version():
    repository, fake = MemoryRepository(), FakeMagex()
    _approve(repository, fake)
    original = dict(repository.layer["payload"])
    fake.down = True
    repository.layer["payload"] = {**original, "reserve": {"primer:ПД Сферит-ДП 1000 г:": 5}}
    assert _approve(repository, fake)["outcome"] == "PENDING"
    fake.down = False
    repository.layer["payload"] = original
    result = _approve(repository, fake)
    # Не «без изменений»: ожидающая v2 заменена, в MagEX — v3 с исходной выпиской.
    assert result["outcome"] == "ACCEPTED"
    assert [(item["ver"], item["status"]) for item in repository.versions] == [(1, "ACCEPTED"), (2, "SUPERSEDED"), (3, "ACCEPTED")]
    assert magex.process_due(repository, transport=fake, now=NOW + timedelta(hours=2)) == 0


def test_new_version_is_queued_before_sending():
    """Процесс упал между созданием версии и ответом MagEX — версию отправит очередь."""

    repository, fake = MemoryRepository(), FakeMagex()
    seen = []
    original_put = magex.MagexClient.put_naryad

    def crash(self, naryad_id, token):
        seen.append(repository.versions[-1]["status"])
        raise RuntimeError("процесс упал")

    magex.MagexClient.put_naryad = crash
    try:
        with pytest.raises(RuntimeError):
            _approve(repository, fake)
    finally:
        magex.MagexClient.put_naryad = original_put
    assert seen == ["PENDING"]
    assert magex.process_due(repository, transport=fake, now=NOW + timedelta(seconds=magex.LEASE_S + 1)) == 1
    assert repository.versions[0]["status"] == "ACCEPTED"


def test_after_blast_reprint_keeps_the_accepted_string():
    """После взрыва — ревизия для печати с графами исполнения и той же строкой (замечание Codex)."""

    repository, fake = MemoryRepository(status="executed"), FakeMagex()
    _approve(repository, fake)
    first = repository.layer["current_revision_id"]
    pd = MATERIAL_IDS["MAT_PD_1000"]
    fake.naryads[LAYER_ID].update(status="closed", issued={pd: "198.000"}, consumed={pd: "196.000"})
    magex.refresh_execution(repository, ORG, LAYER_ID, transport=fake)
    result = _approve(repository, fake)
    assert result["outcome"] == "UNCHANGED" and result["reprinted"] is True
    second = repository.layer["current_revision_id"]
    assert second != first and [item["ver"] for item in repository.versions] == [1]
    context = repository.revisions[second]["context"]
    assert context["magex"]["jws"] == repository.versions[0]["jws"]
    primer = next(line for line in context["view"]["lines"] if line["kind"] == "primer")
    assert primer["consumed_qty"] == 196.0
    documents.layer_document(repository, ORG, second)
    # Ничего нового — та же ревизия.
    assert _approve(repository, fake)["reprinted"] is False


def test_acceptance_uses_magex_only_when_every_naryad_has_consumption():
    repository, fake = MemoryRepository(status="executed"), FakeMagex()
    act = {"kind": "ACCEPTANCE_ACT", "project_id": "p1", "id": "act"}
    assert layers._magex_state(repository, ORG, act) == {}
    _approve(repository, fake)
    magex.refresh_execution(repository, ORG, LAYER_ID, transport=fake)
    # Расход не внесён — итог по MagEX не подменяет «Факт».
    assert layers._magex_state(repository, ORG, act) == {}
    evv = MATERIAL_IDS["MAT_EVV"]
    fake.naryads[LAYER_ID].update(status="closed", consumed_kg={evv: "32600.000"})
    magex.refresh_execution(repository, ORG, LAYER_ID, transport=fake)
    assert layers._magex_state(repository, ORG, act) == {"magex_explosive_kg": 32600.0}


def test_more_than_50_blocks_is_an_error():
    seed = naryad_seed()
    seed["blocks"] = [{**seed["blocks"][0], "code": f"B{index}"} for index in range(51)]
    _, issues = build_naryad_payload(LAYER_ID, seed, {"number": "1", "issue_date": "2026-10-14"}, _lines(), _ctx(),
                                     ver=1, iat=0, approved_at=NOW)
    assert "magex_too_many_blocks" in {item["code"] for item in issues if item["level"] == "error"}


def test_cartridge_rounding_is_printed_and_reported():
    """кг → целые патроны: печать «Выписано» как в выписке, округление — предупреждением (замечание Codex)."""

    class Cartridges(FakeMagex):
        def _catalog(self):
            return [dict(item, accounting_unit="pcs", unit_mass_kg="25.000") if item["id"] == MATERIAL_IDS["MAT_EVV"] else item
                    for item in CATALOG]

    repository, fake = MemoryRepository(), Cartridges()
    result = _approve(repository, fake)
    assert result["outcome"] == "ACCEPTED"
    assert "magex_qty_rounded" in {item["code"] for item in result["warnings"]}
    signed = {line["material_id"]: line["qty"] for line in fake.naryads[LAYER_ID]["payload"]["lines"]}
    assert signed[MATERIAL_IDS["MAT_EVV"]] == "1307.000"
    context = repository.revisions[repository.layer["current_revision_id"]]["context"]
    line = next(item for item in context["view"]["lines"] if item["kind"] == "explosive")
    assert line["issue_qty"] == 32675.0 and line["issue_kg"] == 32675.0
    assert line["reserve_qty"] == pytest.approx(32675.0 - 32659.326)
    assert context["view"]["totals"]["explosive_issue_kg"] == 32675.0


def test_same_block_code_on_two_horizons_gets_distinct_codes():
    from design.magex.naryad_payload import block_codes

    seed = naryad_seed()
    seed["blocks"] = [{**seed["blocks"][0], "horizon": "410"}, {**seed["blocks"][0], "horizon": "420"}]
    assert block_codes(seed["blocks"]) == ["66/410", "66/420"]
    content, issues = build_naryad_payload(LAYER_ID, seed, {"number": "1", "issue_date": "2026-10-14"}, _lines(), _ctx(),
                                           ver=1, iat=0, approved_at=NOW)
    assert [block["code"] for block in content["blocks"]] == ["66/410", "66/420"]
    assert "magex_block_codes_repeat" not in {item["code"] for item in issues}


def test_mixed_kg_and_pieces_rows_round_only_the_surplus():
    from api.services.magex_naryad_service import _rounded_issue

    lines = [{"key": "a", "unit": "кг", "issue_qty": 100.0}, {"key": "b", "unit": "шт", "issue_qty": 5.0}]
    merged = [{"material_id": "m", "qty": Decimal(105), "keys": ["a", "b"], "unit": "pcs"}]
    assert _rounded_issue(lines, merged, {"m": {"unit_mass_kg": "1.000"}}) == {}
    lines[0]["issue_qty"] = 100.5
    merged[0]["qty"] = Decimal(106)
    assert _rounded_issue(lines, merged, {"m": {"unit_mass_kg": "1.000"}}) == {"a": 101.0}


def test_rejected_replacement_restores_the_accepted_revision():
    repository, fake = MemoryRepository(), FakeMagex()
    _approve(repository, fake)
    accepted_revision = repository.layer["current_revision_id"]
    fake.down = True
    repository.layer["payload"] = {**repository.layer["payload"], "reserve": {"primer:ПД Сферит-ДП 1000 г:": 5}}
    _approve(repository, fake)  # v2 в очереди
    fake.down = False
    fake.stock = {**fake.stock, MATERIAL_IDS["MAT_PD_1000"]: Decimal(1)}
    repository.layer["payload"] = {**repository.layer["payload"], "reserve": {"primer:ПД Сферит-ДП 1000 г:": 9}}
    assert _approve(repository, fake)["outcome"] == "REJECTED"  # v3 отклонена, v2 заменена
    assert repository.layer["current_revision_id"] == accepted_revision
    documents.layer_document(repository, ORG, accepted_revision)


def test_retry_with_nothing_queued_returns_state():
    repository, fake = MemoryRepository(), FakeMagex()
    _approve(repository, fake)
    assert magex.retry_now(repository, ORG, "a", LAYER_ID, transport=fake)["outcome"] == "NOTHING_PENDING"


def test_magex_kilograms_kept_for_pieces_with_unknown_mass():
    from design.magex.execution import values_by_line
    from design.mass_blast_layers import naryad_after_blast

    execution = {"lines": [{"material_id": "m", "issued": "5.000", "issued_kg": "5.000", "consumed": "4.000",
                            "consumed_kg": "4.000", "returned": "1.000", "returned_kg": "1.000"}]}
    lines = [{"key": "nsi:x:", "kind": "nsi_surface", "name": "НСИ", "unit": "шт", "delay_ms": None, "project_qty": 5.0,
              "issue_qty": 5.0, "unit_mass_kg": None, "material_code": "N"}]
    values, _ = values_by_line(execution, [{"material_id": "m", "keys": ["nsi:x:"], "unit": "pcs"}], lines)
    result, _, _ = naryad_after_blast({"blocks": []}, {}, lines, magex=values)
    assert (result[0]["issued_kg"], result[0]["consumed_kg"], result[0]["returned_kg"]) == (5.0, 4.0, 1.0)


def test_acceptance_without_fact_layer_uses_magex_total():
    repository, fake = MemoryRepository(status="executed"), FakeMagex()
    _approve(repository, fake)
    evv = MATERIAL_IDS["MAT_EVV"]
    fake.naryads[LAYER_ID].update(status="closed", consumed_kg={evv: "32600.000"})
    magex.refresh_execution(repository, ORG, LAYER_ID, transport=fake)
    act = {"id": "act", "project_id": "p1", "kind": "ACCEPTANCE_ACT", "stale": False,
           "seed": {"volume_contour_m3": 26000.0, "blocks": []}, "payload": {}}
    viewed = layers._with_view(act, None, {}, layers._magex_state(repository, ORG, act))
    assert viewed["view"]["fact"]["explosive_kg"] == 32600.0 and viewed["view"]["fact"]["explosive_source"] == "MAGEX"
    assert viewed["view"]["fact"]["q_kg_m3"] == round(32600 / 26000, 2)


def test_failed_issue_leaves_no_queued_version_and_previous_stays_queued():
    repository, fake = MemoryRepository(), FakeMagex()
    magex.catalog(ORG, magex.client_for(ORG, fake))
    fake.down = True
    _approve(repository, fake)  # v1 в очереди
    repository.layer["payload"] = {**repository.layer["payload"], "reserve": {"primer:ПД Сферит-ДП 1000 г:": 5}}
    repository.fail_next_revision = True
    with pytest.raises(RuntimeError):
        _approve(repository, fake)
    assert [(item["ver"], item["status"]) for item in repository.versions] == [(1, "PENDING"), (2, "SUPERSEDED")]


def test_send_result_does_not_resurrect_a_superseded_version():
    repository, fake = MemoryRepository(), FakeMagex()
    magex.catalog(ORG, magex.client_for(ORG, fake))
    fake.down = True
    _approve(repository, fake)
    version = repository.versions[0]
    repository.update_magex_version(version["id"], status="SUPERSEDED")
    # Отправка, начатая до замены, кончилась сбоем сети — версия остаётся заменённой.
    magex._send(repository, ORG, "a", LAYER_ID, version, magex.client_for(ORG, fake), NOW)
    assert repository.versions[0]["status"] == "SUPERSEDED"


def test_naryad_options_fill_fields_from_references():
    options = layers.naryad_options(economics(), ORG)
    assert options["vehicles"][0]["fill"] == {
        "vehicle_model": "КамАЗ 43118", "vehicle_plate": "А123ВС96", "driver": "Петров П. П.", "driver_code": "D-01",
    }
    assert options["warehouses"] == [{"value": "W-01", "label": "Склад ВМ № 1",
                                      "fill": {"warehouse": "Склад ВМ № 1", "magex_warehouse_id": WAREHOUSE}}]
    assert [item["value"] for item in options["drivers"]] == ["D-01"]
    assert options["escorts"] == [{"value": "E-01", "label": "Сидоров С. С. — взрывник", "fill": {"delivery": "Сидоров С. С."}}]
    assert options["blasters"][0]["fill"] == {"blaster_name": "Трегубов Александр Иванович", "blaster_index": "ЮФ60АВ"}
    assert layers.naryad_options(None, ORG) == {key: [] for key in ("warehouses", "blasters", "vehicles", "drivers", "escorts")}


def test_choice_keys_are_written_only_when_set():
    assert "vehicle_code" not in layers._payload("NARYAD", {"vehicle_code": "", "blaster_name": ""})
    assert layers._payload("NARYAD", {"vehicle_code": "V-01"})["vehicle_code"] == "V-01"


def test_signed_warehouse_name_is_snapshotted_for_print():
    repository, fake = MemoryRepository(), FakeMagex()
    _approve(repository, fake)
    context = repository.revisions[repository.layer["current_revision_id"]]["context"]
    assert context["magex"]["print"]["warehouse"] == "Склад ВМ № 1"
