"""Живой тест против локального Compose MagEX (TASK-018 PR 7, §10, решение В11).

Только локально, в CI его нет. Стенд MagEX — `docker compose up --build backend`
в репозитории MagEX (тестовый ключ: `VM_BLASTEX_JWKS`, `VM_BLASTEX_ALLOW_TEST_KEY`),
сид — `python -m backend.scripts.seed_dev --scenario`. Переменные:

- `MAGEX_LIVE_URL` — адрес до `/api/v1` (например `http://127.0.0.1:8030/api/v1`);
- `MAGEX_LIVE_WAREHOUSE` — UUID «Склада ВМ №1» сида (`seed_dev.warehouse_id`).

Без них тест пропускается. Наряд-путёвка — на сегодня, № и UUID — новые на запуск.
"""
from __future__ import annotations

import os
import uuid
from datetime import date, datetime, timezone

import pytest

from api.services import magex_naryad_service as magex
from tests.magex_fakes import ORG, MemoryRepository, configure, naryad_seed

LIVE_URL = os.getenv("MAGEX_LIVE_URL", "").strip()
LIVE_WAREHOUSE = os.getenv("MAGEX_LIVE_WAREHOUSE", "").strip()

pytestmark = pytest.mark.skipif(not (LIVE_URL and LIVE_WAREHOUSE), reason="MAGEX_LIVE_URL и MAGEX_LIVE_WAREHOUSE не заданы")

# Позиции сида MagEX с партиями на «Складе ВМ №1» (как в `scripts/dev_naryad.py`).
LIVE_MATERIALS = {"primer": "Сферит-ДП 60П, патрон 1000 г", "nsi_downhole": "ИСКРА-С-700-12"}


def _economics(catalog: list[dict]) -> object:
    from types import SimpleNamespace

    from tests.magex_fakes import snapshot

    base = snapshot(warehouse=LIVE_WAREHOUSE)
    by_name = {item["short_name"]: item["id"] for item in catalog}
    materials = tuple(
        SimpleNamespace(code=f"LIVE_{kind.upper()}", name=name, payload={"magex_material_id": by_name[name]}, is_active=True)
        for kind, name in LIVE_MATERIALS.items()
    )

    def items(section):
        return materials if section == "materials" else base.active_items(section)

    data = SimpleNamespace(revision_id="ref-1", active_items=items, item=base.item)
    return SimpleNamespace(get_reference_snapshot=lambda organization_id, requested=None: data)


def _repository(qty: float) -> MemoryRepository:
    today = date.today().isoformat()
    repository = MemoryRepository(payload={
        "number": f"PR7-{uuid.uuid4().hex[:8]}", "issue_date": today, "admissions_confirmed": True,
        "magex_warehouse_id": LIVE_WAREHOUSE,
    })
    seed = naryad_seed()
    seed["project"]["blast_date"] = today
    seed["materials"] = [
        {**line, "material_code": f"LIVE_{line['kind'].upper()}", "project_qty": qty}
        for line in seed["materials"] if line["kind"] in LIVE_MATERIALS
    ]
    repository.layer.update(id=str(uuid.uuid4()), seed=seed)
    return repository


@pytest.fixture()
def live(monkeypatch):
    configure(monkeypatch, url=LIVE_URL)
    monkeypatch.setattr(magex, "TRANSPORT", None)
    magex._catalog_cache.clear()
    catalog = magex.catalog(ORG, fresh=True)
    yield _economics(catalog)
    magex._catalog_cache.clear()


def _approve(repository, economics):
    return magex.approve(repository, economics, ORG, "live@example.ru", repository.layer["id"], repository.layer["version"],
                         now=datetime.now(timezone.utc).replace(microsecond=0))


def test_put_200_reserve_repeat_unchanged_and_cancel(live):
    repository = _repository(2)
    result = _approve(repository, live)
    assert result["outcome"] == "ACCEPTED", result
    execution = result["execution"]
    assert execution["status"] == "approved"
    # Резерв в MagEX = «Выписано».
    assert sorted(line["ordered"] for line in execution["lines"]) == ["2.000", "2.000"]
    available = magex.availability(repository, live, ORG, repository.layer["id"])
    assert available["error"] == "" and available["items"]
    # Повтор той же выписки — «без изменений», новой версии нет.
    assert _approve(repository, live)["outcome"] == "UNCHANGED"
    assert [item["ver"] for item in repository.versions] == [1]
    state = magex.cancel(repository, ORG, "live@example.ru", repository.layer["id"], "Живой тест BlastEX PR 7")
    assert state["execution"]["status"] == "cancelled"


def test_insufficient_available_is_shown(live):
    repository = _repository(10_000_000)
    result = _approve(repository, live)
    assert result["outcome"] == "REJECTED"
    assert result["rejection"]["code"] == "INSUFFICIENT_AVAILABLE"
    assert result["rejection"]["details"]["lines"]
    assert repository.revisions == {}
