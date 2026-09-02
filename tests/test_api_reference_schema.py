"""Эндпоинт `GET /economics/references/schema` (TASK-006, этап C)."""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routers import economics
from cost.v2.references import REFERENCE_SECTION_DEFINITIONS
from cost.v2.schemas import SECTION_SCHEMAS


def _client(monkeypatch) -> TestClient:
    monkeypatch.setenv("BLASTEX_API_KEY", "test-api-key")
    monkeypatch.setenv("BLASTEX_SESSION_SECRET", "test-session-secret")
    app = FastAPI()
    app.include_router(economics.router, prefix="/api/v1")
    return TestClient(app, headers={"X-API-Key": "test-api-key"})


def _schema(monkeypatch) -> dict:
    response = _client(monkeypatch).get("/api/v1/economics/references/schema")
    assert response.status_code == 200, response.text
    return response.json()


def test_every_section_with_a_schema_is_published(monkeypatch) -> None:
    payload = _schema(monkeypatch)
    assert set(payload["sections"]) == set(SECTION_SCHEMAS)
    for code, section in payload["sections"].items():
        assert section["json_schema"], code
        assert section["label"] == REFERENCE_SECTION_DEFINITIONS[code]["label"]


def test_groups_cover_every_section(monkeypatch) -> None:
    payload = _schema(monkeypatch)
    groups = {group["code"] for group in payload["groups"]}
    assert {section["group"] for section in payload["sections"].values()} <= groups


def test_numeric_fields_carry_a_unit(monkeypatch) -> None:
    payload = _schema(monkeypatch)
    for code, section in payload["sections"].items():
        for name, field in section["json_schema"]["properties"].items():
            variants = field.get("anyOf") or [field]
            numeric = any(v.get("type") in {"number", "integer"} for v in variants if isinstance(v, dict))
            if not numeric:
                continue
            has_unit = "x-unit" in field or any(
                isinstance(v, dict) and "x-unit" in v for v in variants
            )
            assert has_unit, f"{code}.{name} без единицы измерения"


def test_reference_fields_declare_their_target_section(monkeypatch) -> None:
    positions = _schema(monkeypatch)["sections"]["positions"]["json_schema"]["properties"]
    operation = positions["operation_code"]
    targets = [v.get("x-ref") for v in operation.get("anyOf", []) if isinstance(v, dict)]
    assert "operations" in targets or operation.get("x-ref") == "operations"


def test_fieldsets_cover_all_visible_fields(monkeypatch) -> None:
    """Поле, не попавшее ни в одну группу, не появится в форме — это баг."""

    payload = _schema(monkeypatch)
    for code, section in payload["sections"].items():
        visible = {
            name for name, field in section["json_schema"]["properties"].items()
            if not field.get("x-internal")
        }
        grouped = {name for fieldset in section["fieldsets"] for name in fieldset["fields"]}
        assert grouped == visible, code


def test_drilling_conditions_use_the_matrix_view(monkeypatch) -> None:
    sections = _schema(monkeypatch)["sections"]
    assert sections["drilling_conditions"]["view"] == "matrix"
    assert sections["positions"]["view"] == "table"


def test_list_columns_exist_in_the_schema(monkeypatch) -> None:
    payload = _schema(monkeypatch)
    for code, section in payload["sections"].items():
        for column in section["list_columns"]:
            # `name` — поле самой записи, а не payload, и в схеме его нет.
            if column in {"name", "code", "valid_from", "valid_to"}:
                continue
            assert column in section["json_schema"]["properties"], f"{code}.{column}"


def test_deprecated_section_is_not_published(monkeypatch) -> None:
    assert "drilling_productivity" not in _schema(monkeypatch)["sections"]
