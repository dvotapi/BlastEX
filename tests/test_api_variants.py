"""Расчёт нескольких вариантов блока одним запросом."""
from __future__ import annotations

from tests.conftest import parameters_payload as _parameters


def test_variants_are_computed_on_one_revision(client) -> None:
    test_client, _, passport_id = client
    response = test_client.post(
        "/api/v1/economics/block-economics/variants",
        json={
            "technical_passport_id": passport_id,
            "variants": [
                {
                    "name": "БВР сухие",
                    "parameters": _parameters(passport_id, nomenclature={"EXPLOSIVE": "MAT_ANFO"})["parameters"],
                },
                {
                    "name": "БВР обводнённые",
                    "parameters": _parameters(passport_id, nomenclature={"EXPLOSIVE": "MAT_EVERSIN"})["parameters"],
                },
            ],
        },
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert [v["name"] for v in body["variants"]] == ["БВР сухие", "БВР обводнённые"]
    dry, wet = (v["economics"] for v in body["variants"])
    assert dry["price_per_m3"]["full"] < wet["price_per_m3"]["full"]
    assert body["reference_revision_id"]
    assert all(v["economics"]["reference_revision_id"] == body["reference_revision_id"] for v in body["variants"])


def test_variants_are_limited_to_four(client) -> None:
    test_client, _, passport_id = client
    one = {"name": "В", "parameters": _parameters(passport_id)["parameters"]}
    response = test_client.post(
        "/api/v1/economics/block-economics/variants",
        json={"technical_passport_id": passport_id, "variants": [one] * 5},
    )
    assert response.status_code == 422


def test_variants_need_at_least_one(client) -> None:
    test_client, _, passport_id = client
    response = test_client.post(
        "/api/v1/economics/block-economics/variants",
        json={"technical_passport_id": passport_id, "variants": []},
    )
    assert response.status_code == 422


def test_unknown_passport_gives_404(client) -> None:
    test_client, _, passport_id = client
    one = {"name": "В", "parameters": _parameters(passport_id)["parameters"]}
    response = test_client.post(
        "/api/v1/economics/block-economics/variants",
        json={"technical_passport_id": "missing", "variants": [one]},
    )
    assert response.status_code == 404


def test_reference_revision_id_is_a_request_field_not_a_per_variant_one(client) -> None:
    """Ревизия — поле запроса: разные значения внутри вариантов на выбор снимка не влияют."""

    test_client, _, passport_id = client
    one = _parameters(passport_id, reference_revision_id="")["parameters"]
    other = _parameters(passport_id, reference_revision_id="some-other-revision")["parameters"]
    response = test_client.post(
        "/api/v1/economics/block-economics/variants",
        json={
            "technical_passport_id": passport_id,
            "reference_revision_id": "",
            "variants": [{"name": "А", "parameters": one}, {"name": "Б", "parameters": other}],
        },
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["reference_revision_id"]
    assert body["variants"][0]["economics"]["reference_revision_id"] == body["reference_revision_id"]
    assert body["variants"][1]["economics"]["reference_revision_id"] == body["reference_revision_id"]
