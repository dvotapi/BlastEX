"""Публикация справочников методики ФОТ через API (TASK-010 PR 1)."""
from __future__ import annotations

from tests.test_api_economics import _client


def _record(code: str, name: str, payload: dict) -> dict:
    return {
        "code": code,
        "name": name,
        "payload": payload,
        "is_active": True,
        "valid_from": None,
        "valid_to": None,
        "source": "test",
        "comment": "",
        "revision": 1,
    }


CURVE = {
    "position_code": "POSITION_LABOR_DRILLER",
    "fixed_monthly_rub": "27093",
    "scale_type": "CURVE_POWER",
    "norm_per_shift": "115.3846",
    "rate_norm": "45",
    "ceiling_per_shift": "184.6154",
    "rate_ceiling": "168.66",
}


def _sections(snapshot: dict, rate: dict) -> dict:
    sections = snapshot["sections"]
    sections["production_units"] = [_record("UNIT_1", "Юнит 1", {})]
    sections["positions"] = [
        _record(
            "POSITION_LABOR_DRILLER",
            "Машинист буровой установки",
            {"category": "INDIRECT", "pay_system": "PIECE_PROGRESSIVE", "difficulty": "NORMALIZED_METERS"},
        )
    ]
    sections["labor_rates"] = [_record("RATE_DRILLER", "Машинист", rate)]
    sections["payroll_params"] = [
        _record(
            "PAYROLL_PARAMS_2026",
            "Параметры ФОТ 2026",
            {
                "year": "2026",
                "mrot": "27093",
                "annual_hours_40": "1972",
                "annual_hours_36": "1774.4",
                "work_days_year": "247",
                "holidays_year": "14",
            },
        )
    ]
    sections["downtime_reasons"] = [
        _record("DT_PLANNED_MAINTENANCE", "Плановое ТОиР", {"excusable": True, "planned_maintenance": True})
    ]
    sections["drilling_difficulty"] = [
        _record(
            "DRILLING_DIFFICULTY_BASE",
            "Сложность бурения",
            {
                "hardness": [{"f_from": None, "f_to": "12", "k": "1"}, {"f_from": "12", "f_to": None, "k": "1.2"}],
                "diameter": [{"diameter_mm": "152", "k": "1.00"}],
            },
        )
    ]
    return sections


def test_payroll_sections_are_published_and_read_back(monkeypatch) -> None:
    client, _ = _client(monkeypatch)
    snapshot = client.get("/api/v1/economics/references/snapshot").json()
    sections = _sections(snapshot, CURVE)

    published = client.post(
        "/api/v1/economics/references/publish",
        json={"base_revision": snapshot["revision_id"], "sections": sections, "comment": "ФОТ"},
    )

    assert published.status_code == 200, published.text
    stored = client.get("/api/v1/economics/references/snapshot").json()["sections"]
    assert stored["labor_rates"][0]["payload"]["ceiling_per_shift"] == "184.6154"
    assert stored["drilling_difficulty"][0]["payload"]["hardness"][1] == {"f_from": "12", "f_to": None, "k": "1.2"}
    assert [item["code"] for item in stored["payroll_params"]] == ["PAYROLL_PARAMS_2026"]


def test_broken_scale_blocks_publication_under_its_field(monkeypatch) -> None:
    client, _ = _client(monkeypatch)
    snapshot = client.get("/api/v1/economics/references/snapshot").json()
    sections = _sections(snapshot, {**CURVE, "rate_ceiling": "40"})

    response = client.post(
        "/api/v1/economics/references/publish",
        json={"base_revision": snapshot["revision_id"], "sections": sections, "comment": "ФОТ"},
    )

    assert response.status_code == 422
    issues = response.json()["detail"]["issues"]
    assert {
        "level": "error",
        "section": "labor_rates",
        "code": "RATE_DRILLER",
        "message": "Расценка на потолке не может быть ниже расценки на норме",
        "field": "rate_ceiling",
    } in issues
