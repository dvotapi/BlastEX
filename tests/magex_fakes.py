"""Наряд блока 66 в памяти и заглушка MagEX для тестов интеграции (TASK-018 PR 7).

`MemoryRepository` повторяет методы `PostgresMassBlastRepository`, которые
зовут слои и сервис MagEX (слой, ревизии слоя, версии выписки, исполнение);
`FakeMagex` — транспорт клиента: проверяет строку и токен так, как проверяет
MagEX (`tests.magex_contract`), держит резерв и остаток, отвечает по контракту.
"""
from __future__ import annotations

import copy
import json
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from typing import Any

from design.mass_blast_layers import layer_seed
from design.mass_blast_repository import MassBlastConflictError, MassBlastNotFoundError
from tests.magex_contract import FIXTURES, ContractError, fixture_keys, verify, verify_service_token
from tests.mass_blast_block66 import context66, payload66

ORG = "org-a"
MAGEX_ORG = "00000000-0000-4000-8000-00000000d0e1"
WAREHOUSE = "40713246-b06d-5fbf-8a28-0bae4482f87d"
LAYER_ID = "5aeb0ed8-a0f9-5002-a9e0-556b29a5ede8"
# Позиции MagEX блока 66: ВВ на месте (кг), ПД (шт), НСИ скважинные и поверхностные, стартер.
MATERIAL_IDS = {
    "MAT_EVV": "b3f2c83a-9a54-5f99-96da-96d9d6fae70f",
    "MAT_PD_1000": "1245e861-01f5-52d7-9c66-88a950bbc1be",
    "MAT_NSI_700": "4722aad7-a1b3-5312-9534-51192221b0e0",
    "MAT_NSI_25": "7155437b-5255-5739-82ae-e14d9cd4f761",
    "MAT_START": "4dd16123-2957-561c-9296-652536c9a220",
}
CATALOG = [
    {"id": MATERIAL_IDS["MAT_EVV"], "short_name": "Порэмит 1А", "pvm_code": "1", "pvm_name": "ЭВВ Порэмит 1А",
     "kind": "vv_onsite", "accounting_unit": "kg", "unit_mass_kg": None},
    {"id": MATERIAL_IDS["MAT_PD_1000"], "short_name": "Сферит-ДП 1000", "pvm_code": "2", "pvm_name": "ПД",
     "kind": "vv_factory", "accounting_unit": "pcs", "unit_mass_kg": "1.000"},
    {"id": MATERIAL_IDS["MAT_NSI_700"], "short_name": "ИСКРА-С-700-12", "pvm_code": "3", "pvm_name": "НСИ",
     "kind": "si", "accounting_unit": "pcs", "unit_mass_kg": None},
    {"id": MATERIAL_IDS["MAT_NSI_25"], "short_name": "ИСКРА-П-25-5", "pvm_code": "4", "pvm_name": "НСИ",
     "kind": "si", "accounting_unit": "pcs", "unit_mass_kg": None},
    {"id": MATERIAL_IDS["MAT_START"], "short_name": "ИСКРА-СТАРТ", "pvm_code": "5", "pvm_name": "Стартер",
     "kind": "si", "accounting_unit": "pcs", "unit_mass_kg": None},
]
CODES = {"explosive": "MAT_EVV", "primer": "MAT_PD_1000", "nsi_downhole": "MAT_NSI_700", "nsi_surface": "MAT_NSI_25",
         "starter": "MAT_START"}


def _item(code: str, name: str, payload: dict) -> SimpleNamespace:
    return SimpleNamespace(code=code, name=name, payload=payload, is_active=True)


def snapshot(*, mapped: bool = True, warehouse: str = WAREHOUSE) -> SimpleNamespace:
    sections = {
        "materials": tuple(
            _item(code, code, {"magex_material_id": material_id} if mapped else {}) for code, material_id in MATERIAL_IDS.items()
        ),
        "blasters": (_item("BL-01", "Трегубов Александр Иванович", {"blaster_index": "ЮФ60АВ", "book_number": "",
                                                                     "employee_ref": None}),),
        "mass_blast_sites": (_item("ZHK-MB", "Жуков Камень", {
            "site_code": "ZHK", "warehouse": "Склад ВМ № 1", "magex_warehouse_id": warehouse,
            "blasting_permit_number": "РВ-66", "blasting_permit_date": "2026-01-15",
            "vehicle_model": "КамАЗ 43118", "vehicle_plate": "А123ВС96", "driver": "Петров П. П.",
        }),),
        "blast_safety": (),
        "blast_notifications": (),
    }
    return SimpleNamespace(
        revision_id="ref-1", active_items=lambda section: sections.get(section, ()),
        item=lambda section, code: next((entry for entry in sections.get(section, ()) if entry.code == code), None),
    )


def economics(**options) -> SimpleNamespace:
    data = snapshot(**options)
    return SimpleNamespace(get_reference_snapshot=lambda organization_id, requested=None: data)


def naryad_seed() -> dict:
    context = context66(payload=payload66(requisites={"project_no": "66-26"}))
    seed = layer_seed("NARYAD", context)
    for line in seed["materials"]:
        line["material_code"] = CODES[line["kind"]]
    seed["people"]["blaster"] = {"position": "взрывник", "name": "Трегубов Александр Иванович"}
    seed["people"]["site_manager"] = {"position": "начальник участка", "name": "Гизатуллин Р. Р."}
    return seed


class MemoryRepository:
    def __init__(self, *, status: str = "approved", payload: dict | None = None) -> None:
        self.project = {"id": "p1", "lifecycle_status": status, "site_code": "ZHK", "current_revision_id": "rev-1",
                        "created_at": "2026-10-10T00:00:00+00:00", "context_version": 2}
        self.context = {"document_context_version": 2, "project": {"site_code": "ZHK", "reference_revision_id": "ref-1"}}
        now = "2026-10-12T00:00:00+00:00"
        self.layer = {
            "id": LAYER_ID, "project_id": "p1", "kind": "NARYAD", "project_revision_id": "rev-1", "status": "draft",
            "version": 1, "current_revision_id": None, "seed": naryad_seed(),
            "payload": payload if payload is not None else {
                "number": "66-26", "issue_date": "2026-10-14", "admissions_confirmed": True,
            },
            "stale": False, "created_at": now, "created_by": "a", "updated_at": now, "updated_by": "a",
        }
        self.revisions: dict[str, dict] = {}
        self.versions: list[dict] = []
        self.execution: dict | None = None

    # --- проект и слой
    def get_project(self, organization_id, project_id):
        return copy.deepcopy(self.project)

    def list_projects(self, organization_id):
        return [copy.deepcopy(self.project)]

    def get_revision(self, organization_id, revision_id):
        return {"id": revision_id, "context": copy.deepcopy(self.context)}

    def get_layer(self, organization_id, layer_id):
        if layer_id != self.layer["id"] or organization_id != ORG:
            raise MassBlastNotFoundError("нет слоя")
        return copy.deepcopy(self.layer)

    def list_layers(self, organization_id, project_id):
        return [copy.deepcopy(self.layer)]

    def update_layer(self, organization_id, actor, layer_id, *, expected_version, payload=None, seed=None, project_revision_id=None):
        if self.layer["version"] != expected_version:
            raise MassBlastConflictError("версия")
        if payload is not None:
            self.layer["payload"] = payload
        self.layer["version"] += 1
        return self.get_layer(organization_id, layer_id)

    def create_layer_revision(self, organization_id, actor, layer_id, *, expected_version, context, content_sha256):
        if self.layer["version"] != expected_version:
            raise MassBlastConflictError("версия")
        number = max((item["revision_no"] for item in self.revisions.values()), default=0) + 1
        revision = {"id": str(uuid.uuid4()), "layer_id": layer_id, "revision_no": number, "project_revision_id": "rev-1",
                    "content_sha256": content_sha256, "context": copy.deepcopy(context), "kind": "NARYAD", "project_id": "p1"}
        self.revisions[revision["id"]] = revision
        self.layer.update(status="issued", current_revision_id=revision["id"], version=self.layer["version"] + 1)
        return copy.deepcopy(revision)

    def get_layer_revision(self, organization_id, revision_id):
        if revision_id not in self.revisions:
            raise MassBlastNotFoundError("нет ревизии")
        return copy.deepcopy(self.revisions[revision_id])

    def latest_layer_revision(self, organization_id, layer_id, project_revision_id):
        found = sorted(self.revisions.values(), key=lambda item: item["revision_no"])
        return copy.deepcopy(found[-1]) if found else None

    def discard_layer_revision(self, organization_id, actor, layer_id, revision_id):
        self.revisions.pop(revision_id)
        for version in self.versions:
            if version["layer_revision_id"] == revision_id:
                version["layer_revision_id"] = None
        statuses = {item["ver"]: item["status"] for item in self.versions}
        latest = [
            item for item in sorted(self.revisions.values(), key=lambda item: item["revision_no"])
            if (item["context"].get("magex") or {}).get("mode") != "ONLINE"
            or statuses.get((item["context"].get("magex") or {}).get("ver")) == "ACCEPTED"
        ]
        if self.layer["current_revision_id"] == revision_id:
            self.layer["current_revision_id"] = latest[-1]["id"] if latest else None
            self.layer["status"] = "issued" if latest else "draft"
        self.layer["version"] += 1
        return self.get_layer(organization_id, layer_id)

    # --- MagEX
    def create_magex_version(self, organization_id, actor, layer_id, build, *, expected_version=None):
        if expected_version is not None and self.layer["version"] != expected_version:
            raise MassBlastConflictError("версия")
        if any(item["status"] == "SENDING" for item in self.versions):
            raise MassBlastConflictError("уже отправляется")
        ver = max((item["ver"] for item in self.versions), default=0) + 1
        jws, kid, sha = build(ver)
        now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        version = {"id": str(uuid.uuid4()), "organization_id": organization_id, "layer_id": layer_id, "ver": ver,
                   "layer_revision_id": None, "jws": jws, "kid": kid, "payload_sha256": sha, "status": "SENDING",
                   "response_code": None, "response": {}, "attempts": 0, "next_attempt_at": None, "created_at": now,
                   "created_by": actor, "updated_at": now, "accepted_at": None}
        self.versions.append(version)
        return copy.deepcopy(version)

    def activate_magex_version(self, version_id, layer_revision_id, next_attempt_at):
        for item in self.versions:
            if item["id"] != version_id and item["status"] in ("PENDING", "SENDING"):
                item.update(status="SUPERSEDED", next_attempt_at=None)
        return self.update_magex_version(version_id, layer_revision_id=layer_revision_id, status="PENDING",
                                         next_attempt_at=next_attempt_at)

    def update_magex_version(self, version_id, **changes):
        version = next(item for item in self.versions if item["id"] == version_id)
        for key, value in changes.items():
            version[key] = value.isoformat() if isinstance(value, datetime) else value
        return copy.deepcopy(version)

    def list_magex_versions(self, organization_id, layer_id):
        return [copy.deepcopy(item) for item in sorted(self.versions, key=lambda item: item["ver"])]

    def claim_due_magex_versions(self, now, lease_s, limit=20):
        due = [item for item in self.versions if item["status"] == "PENDING" and item["next_attempt_at"]
               and datetime.fromisoformat(item["next_attempt_at"]) <= now]
        for item in due:
            item["next_attempt_at"] = (now + timedelta(seconds=lease_s)).isoformat()
        return [copy.deepcopy(item) for item in due]

    def save_magex_execution(self, organization_id, layer_id, execution):
        self.execution = {"status": str(execution.get("status") or ""), "execution": copy.deepcopy(execution),
                          "fetched_at": "2026-10-14T05:00:00+00:00"}
        return copy.deepcopy(self.execution)

    def magex_execution(self, organization_id, layer_id):
        return copy.deepcopy(self.execution)


def _qty(value: Decimal) -> str:
    return f"{value:.3f}"


class FakeMagex:
    """MagEX в процессе: строка проверяется по контракту, резерв — по выписанному."""

    def __init__(self, stock: dict[str, Decimal] | None = None) -> None:
        self.keys = fixture_keys()
        self.stock = {key: Decimal("100000") for key in MATERIAL_IDS.values()} if stock is None else dict(stock)
        self.naryads: dict[str, dict] = {}
        self.calls: list[tuple[str, str]] = []
        self.down = False

    def _error(self, status: int, code: str, message: str = "", details: Any = None) -> tuple[int, dict]:
        return status, {"code": code, "message": message or code, "details": details or {}}

    def _execution(self, naryad_id: str) -> dict:
        naryad = self.naryads[naryad_id]
        lines = [{"material_id": line["material_id"], "ordered": line["qty"], "issued": naryad.get("issued", {}).get(line["material_id"], "0.000"),
                  "returned": "0.000", "consumed": naryad.get("consumed", {}).get(line["material_id"], "0.000"),
                  "lost": "0.000", "on_hand": "0.000", "ordered_kg": None, "issued_kg": None, "returned_kg": None,
                  "consumed_kg": naryad.get("consumed_kg", {}).get(line["material_id"]), "lost_kg": None, "on_hand_kg": None}
                 for line in naryad["payload"]["lines"]]
        return {"id": naryad_id, "status": naryad["status"], "version": naryad["payload"]["ver"], "lines": lines,
                "issued_batches": [], "cancellation": naryad.get("cancellation"), "closing_events": naryad.get("events", []),
                "block_results": naryad.get("block_results", [])}

    def __call__(self, method, url, headers, params, body):
        path = url.split("/integrations/blastex", 1)[1]
        self.calls.append((method, path))
        if self.down:
            raise ConnectionError("нет сети")
        token = headers["Authorization"].removeprefix("Bearer ")
        claims = verify_service_token(token, self.keys, now=int(datetime.now(timezone.utc).timestamp()))
        assert claims["org"] == MAGEX_ORG
        if method == "GET" and path == "/materials":
            return 200, {"items": copy.deepcopy([dict(item, unit_mass_kg=item["unit_mass_kg"]) for item in self._catalog()])}
        if method == "GET" and path == "/availability":
            warehouse = dict(params)["warehouse_id"]
            if warehouse != WAREHOUSE:
                return self._error(404, "NOT_FOUND")
            items = []
            for key, value in params:
                if key == "material_id":
                    free = self.stock.get(value, Decimal(0)) - self._reserved(value)
                    items.append({"material_id": value, "accounting_unit": "pcs", "stock": _qty(self.stock.get(value, Decimal(0))),
                                  "reserved": _qty(self._reserved(value)), "available": _qty(max(free, Decimal(0)))})
            return 200, {"warehouse_id": warehouse, "calculated_at": "2026-10-14T02:11:00Z", "warehouse_synced_at": None, "items": items}
        if path.startswith("/blasters/"):
            return 200, {"reported": True, "pending": []}
        naryad_id = path.split("/")[2]
        if method == "PUT":
            try:
                payload = verify(body["jws"], self.keys)
            except ContractError as exc:
                return self._error(422, exc.code, details={"errors": exc.errors})
            if payload["sub"] != naryad_id:
                return self._error(422, "NARYAD_SIGNATURE_INVALID")
            current = self.naryads.get(naryad_id)
            same = lambda a, b: {k: v for k, v in a.items() if k != "iat"} == {k: v for k, v in b.items() if k != "iat"}  # noqa: E731
            if current is not None:
                ver = current["payload"]["ver"]
                if payload["ver"] == ver:
                    if same(payload, current["payload"]):
                        return 200, self._execution(naryad_id)
                    return self._error(409, "NARYAD_VERSION_CONFLICT", details={"current_version": ver})
                if payload["ver"] < ver:
                    return self._error(409, "NARYAD_VERSION_OUTDATED", details={"current_version": ver})
                if current["status"] != "approved":
                    problems = []
                    if current["payload"]["wh"] != payload["wh"]:
                        problems.append({"field": "wh", "code": "WAREHOUSE_LOCKED", "message": ""})
                    if current["payload"]["lines"] != payload["lines"]:
                        problems.append({"field": "lines", "code": "QTY_LOCKED", "message": ""})
                    if problems:
                        return self._error(409, "NARYAD_LOCKED", details={"problems": problems})
            short = []
            for line in payload["lines"]:
                free = self.stock.get(line["material_id"], Decimal(0)) - self._reserved(line["material_id"], exclude=naryad_id)
                if Decimal(line["qty"]) > free:
                    short.append({"material_id": line["material_id"], "material": "", "required": line["qty"], "available": _qty(max(free, Decimal(0)))})
            if short:
                return self._error(409, "INSUFFICIENT_AVAILABLE", details={"lines": short})
            status = current["status"] if current else "approved"
            self.naryads[naryad_id] = {**(current or {}), "payload": payload, "status": status, "jws": body["jws"]}
            return 200, self._execution(naryad_id)
        if method == "POST" and path.endswith("/cancel"):
            naryad = self.naryads[naryad_id]
            if naryad["status"] != "approved":
                return self._error(409, "NARYAD_ALREADY_ISSUED")
            naryad["status"] = "cancelled"
            naryad["cancellation"] = {"at": "2026-10-14T05:00:00Z", "reason": body["reason"]}
            return 200, self._execution(naryad_id)
        if method == "GET":
            if naryad_id not in self.naryads:
                return self._error(404, "NOT_FOUND")
            return 200, self._execution(naryad_id)
        raise AssertionError(f"Неожиданный вызов {method} {path}")

    def _catalog(self):
        return CATALOG

    def _reserved(self, material_id: str, exclude: str = "") -> Decimal:
        total = Decimal(0)
        for naryad_id, naryad in self.naryads.items():
            if naryad_id == exclude or naryad["status"] != "approved":
                continue
            for line in naryad["payload"]["lines"]:
                if line["material_id"] == material_id:
                    total += Decimal(line["qty"])
        return total


def configure(monkeypatch, *, url: str = "http://magex.test/api/v1") -> None:
    """Флаги и ключ: тестовый ключ MagEX (только тесты), организация, адрес."""

    from api import config
    from api.services import magex_settings

    monkeypatch.setenv(config.MASS_BLAST_V2_ENABLED_ENV, "1")
    monkeypatch.setenv(config.MAGEX_INTEGRATION_ENABLED_ENV, "1")
    monkeypatch.setenv(config.SIGNING_KEY_ENV, (FIXTURES / "keys" / "TEST-ONLY-private.pem").read_text())
    monkeypatch.setenv(config.SIGNING_KID_ENV, "TEST-ONLY-magex-fixture")
    monkeypatch.setenv(config.ALLOW_TEST_KEY_ENV, "true")
    monkeypatch.setenv(config.MAGEX_ORGANIZATIONS_ENV, json.dumps({ORG: MAGEX_ORG}))
    if url:
        monkeypatch.setenv(config.MAGEX_API_URL_ENV, url)
    else:
        monkeypatch.delenv(config.MAGEX_API_URL_ENV, raising=False)
    magex_settings.reset_magex_settings()
