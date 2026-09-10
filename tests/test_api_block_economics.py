"""API вкладки «Экономика» на in-memory репозитории."""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest

from tests import model_fixtures as fx
from tests.conftest import parameters_payload as _parameters
from api.routers.block_economics import _explosive_from_variant, _positions


def test_block_economics_returns_the_price_ladder(client) -> None:
    test_client, _, passport_id = client
    response = test_client.post("/api/v1/economics/block-economics", json=_parameters(passport_id))

    assert response.status_code == 200
    body = response.json()
    assert set(body["price_per_m3"]) == {
        "marginal",
        "full",
        "with_overhead",
        "with_margin",
        "with_vat",
    }
    assert body["price_per_m3"]["full"] > body["price_per_m3"]["marginal"]
    assert body["natural"]["values"]["rig_shifts"]
    assert any(line["cost_item_code"] == "DRILL_TOOLING" for line in body["lines"])


def test_unknown_passport_gives_404(client) -> None:
    test_client, _, _ = client
    response = test_client.post(
        "/api/v1/economics/block-economics", json=_parameters("no-such-passport")
    )
    assert response.status_code == 404


def test_run_is_saved_listed_and_read_back(client) -> None:
    test_client, _, passport_id = client
    created = test_client.post(
        "/api/v1/economics/runs", json={**_parameters(passport_id), "name": "Базовый"}
    )
    assert created.status_code == 201
    run = created.json()
    assert run["name"] == "Базовый"
    assert run["reference_revision_id"]

    listed = test_client.get(
        "/api/v1/economics/runs", params={"technical_passport_id": passport_id}
    )
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()] == [run["id"]]
    assert listed.json()[0]["price_per_m3"]["full"] > 0

    single = test_client.get(f"/api/v1/economics/runs/{run['id']}")
    assert single.status_code == 200
    assert single.json()["result"]["price_per_m3"] == run["result"]["price_per_m3"]


def test_compare_shows_delta_per_item_and_price(client) -> None:
    test_client, _, passport_id = client
    first = test_client.post(
        "/api/v1/economics/runs", json={**_parameters(passport_id), "name": "План 600 000"}
    ).json()
    second = test_client.post(
        "/api/v1/economics/runs",
        json={
            **_parameters(passport_id, unit_plan_volume_m3="400000"),
            "name": "План 400 000",
        },
    ).json()

    response = test_client.post(
        "/api/v1/economics/runs/compare", json={"run_ids": [first["id"], second["id"]]}
    )
    assert response.status_code == 200
    body = response.json()
    assert [run["name"] for run in body["runs"]] == ["План 600 000", "План 400 000"]
    assert body["delta_price_per_m3"]["full"] > 0
    assert body["delta_price_per_m3"]["marginal"] == 0
    unit_row = next(row for row in body["rows"] if row["cost_item_code"].startswith("UNIT_"))
    assert unit_row["delta_rub"] > 0
    assert len(unit_row["amounts"]) == 2


def test_sensitivity_is_sorted_by_effect(client) -> None:
    test_client, _, passport_id = client
    response = test_client.post(
        "/api/v1/economics/block-economics/sensitivity", json=_parameters(passport_id)
    )

    assert response.status_code == 200
    rows = response.json()["rows"]
    deltas = [abs(row["delta_rub_m3"]) for row in rows]
    assert deltas == sorted(deltas, reverse=True)
    assert {row["code"] for row in rows} >= {"EXPLOSIVE_PRICE", "UNIT_PLAN_VOLUME"}


def test_model_defaults_come_from_references(client) -> None:
    test_client, _, passport_id = client
    response = test_client.get(
        "/api/v1/economics/model-defaults",
        params={"technical_passport_id": passport_id, "package_code": "DRILL_AND_BLAST"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["parameters"]["site_code"] == "SITE_MAIN"
    assert Decimal(body["parameters"]["unit_plan_volume_m3"]) == Decimal("600000")
    assert body["parameters"]["rig_code"] == "RIG_JK830"
    assert [member["position_code"] for member in body["parameters"]["crew"]] == [
        "POS_DRILLER",
        "POS_BLASTER",
        "POS_SZM_DRIVER",
    ]
    assert "PRODUCTION_DRILLING" in body["package_operations"]


def test_defaults_offer_subcontract_rates_with_counterparties(client) -> None:
    test_client, _, passport_id = client
    response = test_client.get(
        "/api/v1/economics/model-defaults",
        params={"technical_passport_id": passport_id, "package_code": "DRILL_AND_BLAST"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["subcontract_rates"], "в фикстуре должна быть ставка бурения"
    rate = body["subcontract_rates"][0]
    assert set(rate) >= {
        "code",
        "name",
        "counterparty_code",
        "counterparty_name",
        "operation_code",
        "unit",
        "rate_rub",
    }
    assert rate["code"] == "SUB_DRILLING"
    assert rate["counterparty_code"] == "CP_DRILLING"
    assert rate["counterparty_name"] == "БурСервис ООО"
    assert rate["rate_rub"] == pytest.approx(900.0)
    assert body["counterparties"] == [{"code": "CP_DRILLING", "name": "БурСервис ООО"}]

    position = body["positions"][0]
    assert set(position) >= {
        "code",
        "name",
        "fixed_monthly_rub",
        "norm_shifts_per_month",
        "category",
    }
    driller = next(row for row in body["positions"] if row["code"] == "POS_DRILLER")
    assert driller["fixed_monthly_rub"] == pytest.approx(60000.0)
    assert driller["norm_shifts_per_month"] == pytest.approx(15.0)
    assert driller["category"] == "DIRECT"

    assert body["parameters"]["subcontract_rate_code"] is None


def test_positions_default_rate_ignores_condition_specific_rows() -> None:
    """Несколько ставок на должность — отдаём безусловную, а не какую попало по порядку словаря."""

    references = fx.references(
        labor_rates=(
            fx.item(
                "LR_DRILLER_HARD", "Бурильщик (крепкая порода)",
                {
                    "position_code": "POS_DRILLER",
                    "fixed_monthly_rub": "90000",
                    "condition_code": "HARD_ROCK",
                },
            ),
            fx.item(
                "LR_DRILLER", "Бурильщик",
                {"position_code": "POS_DRILLER", "fixed_monthly_rub": "60000"},
            ),
        )
    )

    driller = next(row for row in _positions(references) if row["code"] == "POS_DRILLER")
    assert driller["fixed_monthly_rub"] == pytest.approx(60000.0)


def test_subcontract_rate_selection_reaches_the_computed_line(client) -> None:
    test_client, _, passport_id = client
    response = test_client.post(
        "/api/v1/economics/block-economics",
        json=_parameters(
            passport_id,
            drilling_executor="SUBCONTRACTOR",
            subcontract_rate_code="SUB_DRILLING",
        ),
    )

    line = next(
        row for row in response.json()["lines"] if row["cost_item_code"] == "DRILL_SUBCONTRACT"
    )
    assert line["unit_price_rub"] == pytest.approx(900.0)
    assert line["price_origin"] == "REFERENCE"


def test_manual_subcontract_rate_reaches_the_computed_line(client) -> None:
    test_client, _, passport_id = client
    response = test_client.post(
        "/api/v1/economics/block-economics",
        json=_parameters(
            passport_id,
            drilling_executor="SUBCONTRACTOR",
            subcontract_rate_rub="199.5",
        ),
    )

    line = next(
        row for row in response.json()["lines"] if row["cost_item_code"] == "DRILL_SUBCONTRACT"
    )
    assert line["unit_price_rub"] == pytest.approx(199.5)
    assert line["price_origin"] == "MANUAL"


def test_export_returns_xlsx_workbook(client) -> None:
    test_client, _, passport_id = client
    run = test_client.post(
        "/api/v1/economics/runs", json={**_parameters(passport_id), "name": "Экспорт"}
    ).json()

    response = test_client.get(f"/api/v1/economics/runs/{run['id']}/export.xlsx")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument"
    )
    assert response.content[:2] == b"PK"


def test_another_organization_does_not_see_runs(client) -> None:
    test_client, repository, passport_id = client
    test_client.post(
        "/api/v1/economics/runs", json={**_parameters(passport_id), "name": "Свой"}
    )

    assert repository.list_economics_runs("other-org") == ()


def test_defaults_offer_nomenclature_with_prices(client) -> None:
    test_client, _, passport_id = client
    response = test_client.get(
        "/api/v1/economics/model-defaults",
        params={"technical_passport_id": passport_id, "package_code": "DRILL_AND_BLAST"},
    )

    body = response.json()
    explosives = body["nomenclature"]["EXPLOSIVE"]
    assert {"code", "name", "unit", "price_rub"} <= set(explosives[0])
    # Буровой инструмент и прочее в выбор номенклатуры блока не попадают.
    assert "DRILL_TOOL" not in body["nomenclature"]
    assert "OTHER" not in body["nomenclature"]
    eversin = next(row for row in explosives if row["code"] == "MAT_EVERSIN")
    assert eversin["price_rub"] == pytest.approx(48.9)


def test_defaults_preselect_nomenclature_with_a_price(client) -> None:
    """Позиция без цены не годится в умолчание: сметчик получил бы нулевую строку."""

    test_client, _, passport_id = client
    response = test_client.get(
        "/api/v1/economics/model-defaults",
        params={"technical_passport_id": passport_id, "package_code": "DRILL_AND_BLAST"},
    )

    chosen = response.json()["parameters"]["nomenclature"]
    assert chosen["EXPLOSIVE"] != "MAT_PROTOLIT"
    assert chosen["NSI_SURFACE"] == "MAT_NSI_SURFACE"
    assert chosen["BOOSTER"] == "MAT_BOOSTER"


def test_downhole_nsi_default_is_closest_by_length(client) -> None:
    """В паспорте 1224 скважины и 14 688 м НСИ — 12 м на скважину."""

    test_client, _, passport_id = client
    response = test_client.get(
        "/api/v1/economics/model-defaults",
        params={"technical_passport_id": passport_id, "package_code": "DRILL_AND_BLAST"},
    )

    assert response.json()["parameters"]["nomenclature"]["NSI_DOWNHOLE"] == "MAT_NSI_12"


def test_selected_nomenclature_reaches_the_cost_lines(client) -> None:
    test_client, _, passport_id = client
    response = test_client.post(
        "/api/v1/economics/block-economics",
        json=_parameters(
            passport_id,
            nomenclature={"EXPLOSIVE": "MAT_EVERSIN", "NSI_DOWNHOLE": "MAT_NSI"},
        ),
    )

    lines = {line["cost_item_code"]: line for line in response.json()["lines"]}
    assert lines["MATERIAL_EXPLOSIVE"]["cost_item_name"] == "ЭВВ Эверсин-100"
    assert lines["MATERIAL_EXPLOSIVE"]["amount_rub"] == pytest.approx(42000 * 48.9)


def test_defaults_compute_on_the_current_revision(client) -> None:
    """Цена берётся на сегодня: паспорт фиксирует геометрию, а не прайс-лист."""

    test_client, repository, passport_id = client
    head = repository.list_reference_revisions("default")[0]
    sections = {
        section: [item.to_dict() for item in items]
        for section, items in repository.get_reference_snapshot("default", head.id).sections.items()
    }
    for row in sections["material_prices"]:
        if row["payload"].get("material_code") == "MAT_EVERSIN":
            row["payload"]["price_rub"] = "60"
    published = repository.publish_references(
        "default", "tester", head.id, sections, "подорожание ВВ"
    )

    defaults = test_client.get(
        "/api/v1/economics/model-defaults",
        params={"technical_passport_id": passport_id, "package_code": "DRILL_AND_BLAST"},
    ).json()

    assert defaults["reference_revision_id"] == published.revision_id
    # Параметры не прибивают ревизию: расчёт идёт на актуальной, пока сметчик
    # сам не выберет другую.
    assert defaults["parameters"]["reference_revision_id"] == ""
    eversin = next(
        row for row in defaults["nomenclature"]["EXPLOSIVE"] if row["code"] == "MAT_EVERSIN"
    )
    assert eversin["price_rub"] == pytest.approx(60.0)

    computed = test_client.post(
        "/api/v1/economics/block-economics",
        json=_parameters(
            passport_id, reference_revision_id="", nomenclature={"EXPLOSIVE": "MAT_EVERSIN"}
        ),
    ).json()
    explosive = next(
        line for line in computed["lines"] if line["cost_item_code"] == "MATERIAL_EXPLOSIVE"
    )
    assert explosive["amount_rub"] == pytest.approx(42000 * 60)


def test_explicit_revision_still_wins(client) -> None:
    """Старый прогон воспроизводим: явная ревизия считает по ценам своего времени."""

    test_client, repository, passport_id = client
    old_revision = repository.list_reference_revisions("default")[0].id
    sections = {
        section: [item.to_dict() for item in items]
        for section, items in repository.get_reference_snapshot("default", old_revision).sections.items()
    }
    for row in sections["material_prices"]:
        if row["payload"].get("material_code") == "MAT_EVERSIN":
            row["payload"]["price_rub"] = "60"
    repository.publish_references("default", "tester", old_revision, sections, "подорожание ВВ")

    computed = test_client.post(
        "/api/v1/economics/block-economics",
        json=_parameters(
            passport_id,
            reference_revision_id=old_revision,
            nomenclature={"EXPLOSIVE": "MAT_EVERSIN"},
        ),
    ).json()
    explosive = next(
        line for line in computed["lines"] if line["cost_item_code"] == "MATERIAL_EXPLOSIVE"
    )
    assert explosive["amount_rub"] == pytest.approx(42000 * 48.9)


def test_options_carry_the_quantity_in_price_units(client) -> None:
    """Подпись под выбором должна называть то же число, что и строка сметы."""

    test_client, _, passport_id = client
    body = test_client.get(
        "/api/v1/economics/model-defaults",
        params={"technical_passport_id": passport_id, "package_code": "DRILL_AND_BLAST"},
    ).json()

    booster = next(row for row in body["nomenclature"]["BOOSTER"] if row["code"] == "MAT_BOOSTER")
    # 1224 боевика × 0,8 кг — справочник хранит цену килограмма.
    assert booster["quantity"] == pytest.approx(1224 * 0.8)
    assert booster["quantity_label"] == "1224 шт × 0.8 кг"
    assert booster["unit"] == "кг"

    eversin = next(row for row in body["nomenclature"]["EXPLOSIVE"] if row["code"] == "MAT_EVERSIN")
    assert eversin["quantity"] == pytest.approx(42000)
    assert eversin["unit"] == "кг"

    # Электродетонаторы паспорт не считает — количество задаёт сметчик.
    detonator = body["nomenclature"]["DETONATOR_ELECTRIC"][0]
    assert detonator["quantity"] is None


def test_block_economics_reports_the_revision_it_computed_on(client) -> None:
    test_client, repository, passport_id = client
    head = repository.list_reference_revisions("default")[0].id

    computed = test_client.post(
        "/api/v1/economics/block-economics", json=_parameters(passport_id, reference_revision_id="")
    ).json()
    sensitivity = test_client.post(
        "/api/v1/economics/block-economics/sensitivity",
        json=_parameters(passport_id, reference_revision_id=""),
    ).json()

    assert computed["reference_revision_id"] == head
    assert sensitivity["reference_revision_id"] == head


def test_defaults_offer_an_emulsion_truck_and_manual_plan_shifts_reach_the_model(client) -> None:
    test_client, _, passport_id = client
    defaults = test_client.get(
        "/api/v1/economics/model-defaults",
        params={"technical_passport_id": passport_id, "package_code": "DRILL_AND_BLAST"},
    ).json()

    assert [row["code"] for row in defaults["emulsion_trucks"]] == ["TRUCK_EMULSION_20T"]
    assert defaults["parameters"]["emulsion_truck_code"] == "TRUCK_EMULSION_20T"

    computed = test_client.post(
        "/api/v1/economics/block-economics",
        json=_parameters(
            passport_id,
            emulsion_truck_code="TRUCK_EMULSION_20T",
            machine_plan_shifts={"TRUCK_EMULSION_20T": "12"},
        ),
    ).json()
    depreciation = next(
        line for line in computed["lines"] if line["cost_item_code"] == "EMULSION_TRUCK_DEPRECIATION"
    )
    assert depreciation["amount_rub"] == pytest.approx(9_000_000 / 60 / 12 * 3)


def test_service_is_moved_to_cost_rules_and_then_yields_to_the_rule(client) -> None:
    test_client, repository, passport_id = client
    service = {
        "name": "Проживание и питание",
        "amount_rub": "120000",
        "layer": "project_direct",
        "operation_code": "BLAST_EXECUTION",
        "per_shift": False,
    }

    first = test_client.post("/api/v1/economics/services/to-reference", json={"service": service})
    assert first.status_code == 201, first.text
    body = first.json()
    assert body["section"] == "cost_rules"
    assert body["code"] == "SERVICE_PROZHIVANIE_I_PITANIE"
    assert body["created"] is True
    head = repository.list_reference_revisions("default")[0].id
    assert body["reference_revision_id"] == head

    rule = repository.get_reference_snapshot("default", head).item("cost_rules", body["code"])
    assert rule is not None
    assert rule.payload["fixed_rub"] == "120000"
    assert rule.payload["operation_code"] == "BLAST_EXECUTION"
    assert rule.payload["cost_layer"] == "project_direct"

    # Повторный перенос обновляет ту же запись, а не плодит дубли.
    again = test_client.post(
        "/api/v1/economics/services/to-reference", json={"service": {**service, "amount_rub": "130000"}}
    ).json()
    assert again["created"] is False
    latest = repository.get_reference_snapshot("default")
    assert [item.code for item in latest.active_items("cost_rules")].count(body["code"]) == 1
    assert latest.item("cost_rules", body["code"]).payload["fixed_rub"] == "130000"

    # Услуга, оставшаяся в параметрах, уступает правилу.
    computed = test_client.post(
        "/api/v1/economics/block-economics", json=_parameters(passport_id, services=[service])
    ).json()
    lodging = [line for line in computed["lines"] if line["cost_item_name"] == "Проживание и питание"]
    assert len(lodging) == 1
    assert lodging[0]["amount_rub"] == pytest.approx(130000)
    assert any("уже есть в правилах затрат" in text for text in computed["warnings"])


def test_per_shift_service_is_moved_as_a_rate_per_operation_shift(client) -> None:
    test_client, repository, _ = client
    body = test_client.post(
        "/api/v1/economics/services/to-reference",
        json={
            "service": {
                "name": "Предрейсовый медосмотр",
                "amount_rub": "350",
                "layer": "project_direct",
                "operation_code": "BULK_CHARGING_SZM",
                "per_shift": True,
            }
        },
    ).json()

    rule = repository.get_reference_snapshot("default").item("cost_rules", body["code"])
    assert rule.payload["driver"] == "szm_shifts"
    assert rule.payload["rate_rub"] == "350"
    assert "fixed_rub" not in rule.payload


def test_defaults_name_the_package_operations(client) -> None:
    test_client, _, passport_id = client
    body = test_client.get(
        "/api/v1/economics/model-defaults",
        params={"technical_passport_id": passport_id, "package_code": "DRILL_AND_BLAST"},
    ).json()

    operations = {row["code"]: row["name"] for row in body["operations"]}
    assert operations["BLAST_EXECUTION"] == "Производство взрыва"
    assert set(operations) == set(body["package_operations"])


def test_service_transfer_refuses_a_code_taken_by_another_name(client) -> None:
    """Короткие названия могут дать один код после транслита: молча перезаписать чужое правило нельзя."""

    test_client, repository, _ = client
    first = test_client.post(
        "/api/v1/economics/services/to-reference",
        json={
            "service": {
                "name": "Проживание и питание",
                "amount_rub": "120000",
                "layer": "project_direct",
                "operation_code": "BLAST_EXECUTION",
                "per_shift": False,
            }
        },
    ).json()

    clash = test_client.post(
        "/api/v1/economics/services/to-reference",
        json={
            "service": {
                "name": "проживание и питание!",
                "amount_rub": "9000",
                "layer": "project_direct",
                "operation_code": "BLAST_EXECUTION",
                "per_shift": False,
            }
        },
    )

    assert clash.status_code == 409, clash.text
    assert first["code"] in clash.json()["detail"]["message"]
    rule = repository.get_reference_snapshot("default").item("cost_rules", first["code"])
    assert rule.name == "Проживание и питание"
    assert rule.payload["fixed_rub"] == "120000"
def test_downhole_nsi_default_accounts_for_two_devices_per_hole(client) -> None:
    """Длина одного устройства — общая длина на число устройств, а не на число скважин."""

    test_client, repository, _ = client
    passport = repository.save_technical_passport(
        "default",
        "tester",
        site_code="SITE_MAIN",
        object_name="Блок с двумя НСИ в скважине",
        previous_passport_id=None,
        reference_revision_id=repository.list_reference_revisions("default")[0].id,
        formula_version="blast-geometry-v1",
        input_snapshot={},
        selected_variant={},
        block_snapshot={},
        # 1224 скважины × 2 устройства по 9 м: суммарная длина вдвое больше.
        physical={
            **{key: str(value) for key, value in fx.physical().items()},
            "downhole_nsi": "2448",
            "nsi_length_m": "22032",
        },
        lineage={},
    )

    body = test_client.get(
        "/api/v1/economics/model-defaults",
        params={"technical_passport_id": passport.id, "package_code": "DRILL_AND_BLAST"},
    ).json()

    # 22032 / 2448 = 9 м на устройство — берём девятиметровое, а не 18-метровое.
    assert body["parameters"]["nomenclature"]["NSI_DOWNHOLE"] == "MAT_NSI"


def test_downhole_nsi_default_is_never_shorter_than_required(client) -> None:
    """Короче скважины сеть не смонтировать: ближайшее по модулю разности не годится."""

    test_client, repository, _ = client
    passport = repository.save_technical_passport(
        "default",
        "tester",
        site_code="SITE_MAIN",
        object_name="Блок под 10 м НСИ",
        previous_passport_id=None,
        reference_revision_id=repository.list_reference_revisions("default")[0].id,
        formula_version="blast-geometry-v1",
        input_snapshot={},
        selected_variant={},
        block_snapshot={},
        # 10 м на устройство: 9 м ближе по модулю, но короче требуемого.
        physical={
            **{key: str(value) for key, value in fx.physical().items()},
            "downhole_nsi": "1224",
            "nsi_length_m": "12240",
        },
        lineage={},
    )

    body = test_client.get(
        "/api/v1/economics/model-defaults",
        params={"technical_passport_id": passport.id, "package_code": "DRILL_AND_BLAST"},
    ).json()

    assert body["parameters"]["nomenclature"]["NSI_DOWNHOLE"] == "MAT_NSI_12"


def _passport_with_variant(repository, label: str) -> str:
    passport = repository.save_technical_passport(
        "default",
        "tester",
        site_code="SITE_MAIN",
        object_name=f"Блок на {label}",
        previous_passport_id=None,
        reference_revision_id=repository.list_reference_revisions("default")[0].id,
        formula_version="blast-geometry-v1",
        input_snapshot={},
        selected_variant={"label": label},
        block_snapshot={},
        physical={key: str(value) for key, value in fx.physical().items()},
        lineage={},
    )
    return passport.id


def _explosive_default(test_client, passport_id: str) -> str:
    body = test_client.get(
        "/api/v1/economics/model-defaults",
        params={"technical_passport_id": passport_id, "package_code": "DRILL_AND_BLAST"},
    ).json()
    return body["parameters"]["nomenclature"]["EXPLOSIVE"]


def test_explosive_default_follows_the_passport_variant(client) -> None:
    """Смета считается на том ВВ, на котором посчитан блок, а не на первом в каталоге."""

    test_client, repository, _ = client

    # Подпись паспорта — подпись диаграммы: без префикса типа ВВ, без марки,
    # в другом регистре и с дефисами.
    eversin = _passport_with_variant(repository, "ЭВЕРСИН")
    granulit = _passport_with_variant(repository, "ГРАНУЛИТ-РП")
    # Подпись бывает и с маркой — вещество то же.
    marked = _passport_with_variant(repository, "ЭВЕРСИН Э-100")

    assert _explosive_default(test_client, eversin) == "MAT_EVERSIN"
    assert _explosive_default(test_client, granulit) == "MAT_ANFO"
    assert _explosive_default(test_client, marked) == "MAT_EVERSIN"


def test_explosive_default_skips_the_priceless_twin(client) -> None:
    """Дубль из справочника расчётной части совпадает по имени, но цены не имеет."""

    test_client, repository, _ = client

    chosen = _explosive_default(test_client, _passport_with_variant(repository, "ЭВЕРСИН"))

    assert chosen == "MAT_EVERSIN"
    assert chosen != "EXP_PEVV_EVERSIN_E_100"


def test_explosive_partial_match_takes_the_name_closest_to_the_label(client) -> None:
    """Из похожих имён выигрывает ближайшее к подписи, а не самое короткое."""

    _, repository, _ = client
    passport = repository.get_technical_passport(
        "default", _passport_with_variant(repository, "Гранулит РП новый")
    )
    options = [
        {"code": "MAT_GRANULIT", "name": "ГВВ Гранулит", "price_rub": 45.0},
        {"code": "MAT_GRANULIT_RP", "name": "ГВВ Гранулит РП", "price_rub": 46.0},
    ]

    assert _explosive_from_variant(options, passport) == "MAT_GRANULIT_RP"


def test_explosive_default_falls_back_when_the_variant_is_unknown(client) -> None:
    """Подписи нет в каталоге — прежнее правило, а не пустая строка сметы."""

    test_client, repository, passport_id = client

    unknown = _passport_with_variant(repository, "ПОРЭМИТ 1А")

    assert _explosive_default(test_client, unknown) == "MAT_ANFO"
    # Старый паспорт без выбранного варианта ведёт себя как прежде.
    assert _explosive_default(test_client, passport_id) == "MAT_ANFO"


def test_export_prices_the_run_on_its_own_date(client) -> None:
    """Экспорт повторяет сохранённый прогон, а не пересчитывает его по ценам на сегодня."""

    test_client, repository, passport_id = client
    run = test_client.post(
        "/api/v1/economics/runs",
        json={
            **_parameters(passport_id, nomenclature={"EXPLOSIVE": "MAT_EVERSIN"}),
            "name": "Экспорт по дате прогона",
        },
    ).json()
    saved = next(
        line for line in run["result"]["lines"] if line["cost_item_code"] == "MATERIAL_EXPLOSIVE"
    )

    # Цена ВВ истекла вчера: сегодняшний расчёт на той же ревизии дал бы ноль.
    head = repository.list_reference_revisions("default")[0].id
    sections = {
        section: [item.to_dict() for item in items]
        for section, items in repository.get_reference_snapshot("default", head).sections.items()
    }
    for row in sections["material_prices"]:
        if row["payload"].get("material_code") == "MAT_EVERSIN":
            row["payload"]["valid_to"] = (date.today() - timedelta(days=1)).isoformat()
            row["valid_to"] = (date.today() - timedelta(days=1)).isoformat()
    repository.publish_references("default", "tester", head, sections, "цена истекла")

    response = test_client.get(f"/api/v1/economics/runs/{run['id']}/export.xlsx")

    assert response.status_code == 200
    assert saved["amount_rub"] == pytest.approx(42000 * 48.9)


def test_a_new_service_rule_names_its_section(client) -> None:
    """Правило заводит вкладка, а не старая ревизия: модель не должна о нём предупреждать."""

    test_client, repository, _ = client
    body = test_client.post(
        "/api/v1/economics/services/to-reference",
        json={
            "service": {
                "name": "Услуга сторонней организации",
                "amount_rub": "12000",
                "layer": "production",
                "operation_code": "BLAST_EXECUTION",
                "per_shift": False,
            }
        },
    ).json()

    rule = repository.get_reference_snapshot("default").item("cost_rules", body["code"])
    assert rule.payload["estimate_section"] == "OVERHEAD"


def test_service_transfer_keeps_every_field_edited_in_the_reference(client) -> None:
    """Вкладка владеет суммой и операцией; ресурсный пул и ступени правят в справочнике."""

    test_client, repository, _ = client
    service = {
        "name": "Медосмотр и выпуск на линию",
        "amount_rub": "40000",
        "layer": "production",
        "operation_code": "BLAST_EXECUTION",
        "per_shift": False,
    }
    code = test_client.post(
        "/api/v1/economics/services/to-reference", json={"service": service}
    ).json()["code"]

    head = repository.list_reference_revisions("default")[0].id
    sections = {
        section: [item.to_dict() for item in items]
        for section, items in repository.get_reference_snapshot("default", head).sections.items()
    }
    for row in sections["cost_rules"]:
        if row["code"] == code:
            row["payload"]["step_capacity"] = "50"
            row["payload"]["step_cost_rub"] = "1000"
    for row in sections["cost_items"]:
        if row["code"] == code:
            row["payload"]["cost_center_code"] = None
            row["payload"]["legacy_section"] = "2.6"
    repository.publish_references("default", "tester", head, sections, "правки справочника")

    test_client.post(
        "/api/v1/economics/services/to-reference",
        json={"service": {**service, "amount_rub": "45000"}},
    )

    snapshot = repository.get_reference_snapshot("default")
    rule = snapshot.item("cost_rules", code)
    assert rule.payload["fixed_rub"] == "45000"
    assert rule.payload["step_capacity"] == "50"
    assert snapshot.item("cost_items", code).payload["legacy_section"] == "2.6"


def test_service_transfer_clears_a_rate_when_the_service_stops_being_per_shift(client) -> None:
    """Ставка за смену снята — драйвер и ставка должны уйти, иначе сумма удвоится."""

    test_client, repository, _ = client
    service = {
        "name": "Сопровождение взрывов",
        "amount_rub": "5000",
        "layer": "variable",
        "operation_code": "BULK_CHARGING_SZM",
        "per_shift": True,
    }
    code = test_client.post(
        "/api/v1/economics/services/to-reference", json={"service": service}
    ).json()["code"]
    assert repository.get_reference_snapshot("default").item("cost_rules", code).payload["driver"]

    test_client.post(
        "/api/v1/economics/services/to-reference",
        json={"service": {**service, "per_shift": False, "amount_rub": "60000"}},
    )

    payload = repository.get_reference_snapshot("default").item("cost_rules", code).payload
    assert payload["fixed_rub"] == "60000"
    assert "driver" not in payload
    assert "rate_rub" not in payload


def test_service_transfer_keeps_the_section_set_in_the_reference(client) -> None:
    """Раздел правят в справочнике; повторный перенос суммы не должен его сбрасывать."""

    test_client, repository, _ = client
    service = {
        "name": "Проживание бригады",
        "amount_rub": "120000",
        "layer": "project_direct",
        "operation_code": "BLAST_EXECUTION",
        "per_shift": False,
    }
    code = test_client.post("/api/v1/economics/services/to-reference", json={"service": service}).json()["code"]

    head = repository.list_reference_revisions("default")[0].id
    sections = {
        section: [item.to_dict() for item in items]
        for section, items in repository.get_reference_snapshot("default", head).sections.items()
    }
    for row in sections["cost_rules"]:
        if row["code"] == code:
            row["payload"]["estimate_section"] = "PER_DIEM"
    repository.publish_references("default", "tester", head, sections, "раздел поправлен вручную")

    test_client.post(
        "/api/v1/economics/services/to-reference",
        json={"service": {**service, "amount_rub": "130000"}},
    )

    rule = repository.get_reference_snapshot("default").item("cost_rules", code)
    assert rule.payload["fixed_rub"] == "130000"
    assert rule.payload["estimate_section"] == "PER_DIEM"


def test_subcontract_rate_is_published_only_by_explicit_request(client) -> None:
    """Расчёт с ручной ставкой справочник не трогает — тариф попадает туда только по кнопке."""

    test_client, repository, passport_id = client
    before = test_client.get(
        "/api/v1/economics/model-defaults", params={"technical_passport_id": passport_id}
    ).json()

    computed = test_client.post(
        "/api/v1/economics/block-economics",
        json=_parameters(
            passport_id,
            drilling_executor="SUBCONTRACTOR",
            subcontract_rate_rub="185",
        ),
    )
    assert computed.status_code == 200, computed.text
    unchanged = test_client.get(
        "/api/v1/economics/model-defaults", params={"technical_passport_id": passport_id}
    ).json()
    assert unchanged["reference_revision_id"] == before["reference_revision_id"]

    saved = test_client.post(
        "/api/v1/economics/subcontract-rates/to-reference",
        json={
            "counterparty_code": before["counterparties"][0]["code"],
            "name": "Бурение Ø140 мм",
            "rate_rub": "185",
        },
    )
    assert saved.status_code == 201, saved.text
    body = saved.json()
    assert body["section"] == "subcontract_rates"
    assert body["created"] is True
    assert body["reference_revision_id"] != before["reference_revision_id"]
    head = repository.list_reference_revisions("default")[0].id
    assert body["reference_revision_id"] == head

    rate = repository.get_reference_snapshot("default", head).item("subcontract_rates", body["code"])
    assert rate is not None
    assert rate.payload["counterparty_code"] == before["counterparties"][0]["code"]
    assert rate.payload["operation_code"] == "PRODUCTION_DRILLING"
    assert rate.payload["unit"] == "M"
    assert rate.payload["rate_rub"] == "185"

    after = test_client.get(
        "/api/v1/economics/model-defaults", params={"technical_passport_id": passport_id}
    ).json()
    assert after["reference_revision_id"] != before["reference_revision_id"]
    assert any(
        row["code"] == body["code"] and row["rate_rub"] == 185.0
        for row in after["subcontract_rates"]
    )

    # Повторная публикация с тем же кодом обновляет запись, а не плодит дубли.
    again = test_client.post(
        "/api/v1/economics/subcontract-rates/to-reference",
        json={
            "counterparty_code": before["counterparties"][0]["code"],
            "name": "Бурение Ø140 мм",
            "rate_rub": "190",
        },
    )
    assert again.status_code == 201, again.text
    assert again.json()["created"] is False
    latest = repository.get_reference_snapshot("default")
    assert [item.code for item in latest.active_items("subcontract_rates")].count(body["code"]) == 1
    assert latest.item("subcontract_rates", body["code"]).payload["rate_rub"] == "190"


def test_subcontract_rate_transfer_refuses_a_code_taken_by_another_name(client) -> None:
    """Разные названия могут дать один код после транслита — молча перезаписать чужой тариф нельзя."""

    test_client, repository, passport_id = client
    before = test_client.get(
        "/api/v1/economics/model-defaults", params={"technical_passport_id": passport_id}
    ).json()
    counterparty_code = before["counterparties"][0]["code"]

    first = test_client.post(
        "/api/v1/economics/subcontract-rates/to-reference",
        json={"counterparty_code": counterparty_code, "name": "Бурение Ø140 мм", "rate_rub": "185"},
    ).json()

    clash = test_client.post(
        "/api/v1/economics/subcontract-rates/to-reference",
        json={"counterparty_code": counterparty_code, "name": "бурение ø140 мм!", "rate_rub": "9"},
    )

    assert clash.status_code == 409, clash.text
    assert first["code"] in clash.json()["detail"]["message"]
    rate = repository.get_reference_snapshot("default").item("subcontract_rates", first["code"])
    assert rate.name == "Бурение Ø140 мм"
    assert rate.payload["rate_rub"] == "185"


def test_saved_run_survives_passport_deletion(client) -> None:
    """Удаление паспорта не трогает уже сохранённые прогоны, но закрывает новые."""

    test_client, repository, passport_id = client
    run = test_client.post(
        "/api/v1/economics/runs", json={**_parameters(passport_id), "name": "Базовый"}
    ).json()
    repository.delete_technical_passport("default", "tester", passport_id)

    single = test_client.get(f"/api/v1/economics/runs/{run['id']}")
    assert single.status_code == 200, single.text
    assert single.json()["result"]["price_per_m3"]

    repeated = test_client.post(
        "/api/v1/economics/runs", json={**_parameters(passport_id), "name": "Ещё один"}
    )
    assert repeated.status_code == 409, repeated.text
