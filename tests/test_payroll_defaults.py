"""Сид справочников методики ФОТ поверх опубликованного снимка (TASK-010 PR 1, Т10)."""
from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

from cost.model.engine import compute_block_economics
from cost.model.inputs import CrewMember
from cost.v2.crew_defaults import DEFAULT_CREW_CODE, reclassify_positions
from cost.v2.models import ReferenceItem, ReferenceSnapshot
from cost.v2.payroll_defaults import DRILLER_SCALE, EXTRA_TARIFFS, MAPPED_POSITIONS, _fill, seed_payroll_references
from cost.v2.references import has_validation_errors, validate_reference_sections
from cost.v2.repository import InMemoryEconomicsRepository
from scripts.seed_payroll_references import run
from tests import model_fixtures as fx
from tests.test_crew_defaults import imported_snapshot


def _as_snapshot(base: ReferenceSnapshot, sections: dict[str, list[ReferenceItem]]) -> ReferenceSnapshot:
    return replace(base, sections={name: tuple(items) for name, items in sections.items()})


def _by_code(sections: dict[str, list[ReferenceItem]], section: str) -> dict[str, ReferenceItem]:
    return {item.code: item for item in sections[section]}


def test_seed_over_imported_positions_is_valid_and_complete():
    sections, report = seed_payroll_references(imported_snapshot())

    positions = _by_code(sections, "positions")
    assert len([code for code in positions if code.startswith("POSITION_LABOR_")]) == 14
    driller = positions["POSITION_LABOR_DRILLER"]
    # Наименование и заданная категория существующей записи не меняются.
    assert driller.name == "Бурильщик"
    assert driller.payload["category"] == "INDIRECT"
    assert driller.payload["pay_system"] == "PIECE_PROGRESSIVE"
    assert driller.payload["work_conditions_class"] == "3.2"
    assert driller.payload["difficulty"] == "NORMALIZED_METERS"
    assert positions["POSITION_LABOR_MINER"].payload["output_source"] == "SECTION_OUTPUT"
    storekeeper = positions["POSITION_LABOR_STOREKEEPER"]
    assert (storekeeper.source, storekeeper.payload["category"], storekeeper.payload["pay_system"]) == (
        "payroll_seed", "INDIRECT", "TIME_BONUS",
    )

    rate = _by_code(sections, "labor_rates")["RATE_POSITION_LABOR_DRILLER"]
    assert rate.payload["fixed_monthly_rub"] == "60000"
    assert {key: rate.payload[key] for key in ("scale_type", "norm_per_shift", "rate_norm", "ceiling_per_shift", "rate_ceiling")} == {
        "scale_type": "CURVE_POWER",
        "norm_per_shift": "115.3846",
        "rate_norm": "45",
        "ceiling_per_shift": "184.6154",
        "rate_ceiling": "168.66",
    }
    # У помощника в этом снимке нет ставки — новую не заводим.
    assert "labor_rates:POSITION_LABOR_ASSISTANT: нет ставки без условия бурения, шкала не заведена" in report.skipped

    params = _by_code(sections, "payroll_params")["PAYROLL_PARAMS_2026"].payload
    assert (params["mrot"], params["annual_hours_36"], params["work_days_year"]) == ("27093", "1774.4", "247")
    difficulty = _by_code(sections, "drilling_difficulty")["DRILLING_DIFFICULTY_BASE"].payload
    assert [row["k"] for row in difficulty["hardness"]] == ["0.9", "1.0", "1.1", "1.2", "1.3"]
    assert difficulty["diameter"] == [
        {"diameter_mm": diameter, "k": k}
        for diameter, k in (
            ("110", "0.72"), ("127", "0.84"), ("140", "0.92"), ("152", "1.00"),
            ("165", "1.09"), ("190", "1.25"), ("215", "1.41"), ("250", "1.64"),
        )
    ]
    reasons = _by_code(sections, "downtime_reasons")
    assert len(reasons) == 10
    assert reasons["DT_PLANNED_MAINTENANCE"].payload == {"excusable": True, "planned_maintenance": True}
    assert reasons["DT_LATE"].payload == {"excusable": False, "planned_maintenance": False}
    rates = sections["organization_rates"][0].payload
    assert rates["extra_tariffs"][1] == {"work_conditions_class": "3.2", "rate": "0.04"}
    assert rates["social_contribution_rate"] == "0.30"
    assert "units:KM" in report.added

    assert not has_validation_errors(validate_reference_sections(sections))


def test_second_run_changes_nothing():
    first, _ = seed_payroll_references(imported_snapshot())
    again, report = seed_payroll_references(_as_snapshot(imported_snapshot(), first))
    assert again == first
    assert report.added == [] and report.filled == []


def test_filled_values_are_never_overwritten():
    base = imported_snapshot()
    positions = tuple(
        replace(item, payload={**item.payload, "pay_system": "TIME_BONUS", "work_conditions_class": "3.3"})
        if item.code == "POSITION_LABOR_DRILLER"
        else item
        for item in base.sections["positions"]
    )
    rates = tuple(
        replace(item, payload={**item.payload, "scale_type": "STEP", "tiers": [{"rate": "100"}]})
        if item.code == "RATE_POSITION_LABOR_DRILLER"
        else item
        for item in base.sections["labor_rates"]
    )
    sections, report = seed_payroll_references(
        replace(base, sections={**base.sections, "positions": positions, "labor_rates": rates})
    )

    driller = _by_code(sections, "positions")["POSITION_LABOR_DRILLER"].payload
    assert (driller["pay_system"], driller["work_conditions_class"]) == ("TIME_BONUS", "3.3")
    assert driller["hazard_pct"] == "0.04"
    rate = _by_code(sections, "labor_rates")["RATE_POSITION_LABOR_DRILLER"].payload
    assert rate["scale_type"] == "STEP" and "norm_per_shift" not in rate
    # Ставка со своей шкалой пропускается целиком, но расхождение с файлом названо.
    assert report.kept == [
        "positions:POSITION_LABOR_DRILLER: pay_system=TIME_BONUS (файл: PIECE_PROGRESSIVE)",
        "positions:POSITION_LABOR_DRILLER: work_conditions_class=3.3 (файл: 3.2)",
        "labor_rates:RATE_POSITION_LABOR_DRILLER: scale_type=STEP (файл: CURVE_POWER)",
    ]


def test_fill_keeps_zero_false_and_zero_string():
    item = ReferenceItem(code="X", name="Запись", payload={"hazard_pct": 0, "flag": False, "x": "0"})
    updated, filled = _fill(item, {"hazard_pct": "0.04", "flag": True, "x": "1"})
    assert updated.payload == {"hazard_pct": 0, "flag": False, "x": "0"}
    assert filled == []


def test_values_that_differ_from_the_file_are_kept_and_reported():
    """Форма пишет в payload умолчания схемы: сид их не трогает, но называет."""

    base = imported_snapshot()
    positions = tuple(
        replace(item, payload={**item.payload, "pay_system": "TIME_BONUS"})
        if item.code == "POSITION_LABOR_DRILLER"
        else item
        for item in base.sections["positions"]
    )
    # Число и строка с лишним нулём равны значению файла — это не расхождение.
    assistant = ReferenceItem(
        code="POSITION_LABOR_ASSISTANT",
        name="Помощник бурильщика",
        payload={"category": "INDIRECT", "hazard_pct": 0.04, "night_hours_per_shift": "8.0"},
    )
    sections, report = seed_payroll_references(
        replace(base, sections={**base.sections, "positions": (*positions, assistant)})
    )

    assert _by_code(sections, "positions")["POSITION_LABOR_DRILLER"].payload["pay_system"] == "TIME_BONUS"
    assert _by_code(sections, "positions")["POSITION_LABOR_ASSISTANT"].payload["hazard_pct"] == 0.04
    assert report.kept == ["positions:POSITION_LABOR_DRILLER: pay_system=TIME_BONUS (файл: PIECE_PROGRESSIVE)"]
    assert report.to_dict()["kept"] == report.kept


def _organization_rates(extra_tariffs: list[dict]) -> ReferenceSnapshot:
    base = imported_snapshot()
    rates = tuple(
        replace(item, payload={**item.payload, "extra_tariffs": extra_tariffs})
        for item in base.sections["organization_rates"]
    )
    return replace(base, sections={**base.sections, "organization_rates": rates})


def test_extra_tariffs_that_differ_from_the_file_are_kept_and_reported():
    own = [{"work_conditions_class": "3.2", "rate": "0.05"}]
    sections, report = seed_payroll_references(_organization_rates(own))
    assert sections["organization_rates"][0].payload["extra_tariffs"] == own
    assert report.kept == ["organization_rates:ORG_RATES_DEFAULT: extra_tariffs задан, отличается от файла"]

    _, same = seed_payroll_references(_organization_rates([dict(row) for row in EXTRA_TARIFFS]))
    assert same.kept == []


def test_extra_tariffs_with_numbers_instead_of_strings_are_not_a_mismatch():
    # Ставки файла как числа (не строки) — то же значение, не расхождение.
    numeric = [{**row, "rate": float(row["rate"])} for row in EXTRA_TARIFFS]
    _, report = seed_payroll_references(_organization_rates(numeric))
    assert report.kept == []

    differs = [
        {**row, "rate": "0.05"} if row["work_conditions_class"] == "3.2" else row for row in EXTRA_TARIFFS
    ]
    _, report_differs = seed_payroll_references(_organization_rates(differs))
    assert report_differs.kept == ["organization_rates:ORG_RATES_DEFAULT: extra_tariffs задан, отличается от файла"]


def test_assistant_rate_without_a_drilling_condition_gets_the_curve():
    base = imported_snapshot()
    rate = ReferenceItem(
        code="RATE_POSITION_LABOR_ASSISTANT",
        name="Ставка: помощник машиниста",
        payload={"position_code": "POSITION_LABOR_ASSISTANT", "fixed_monthly_rub": "50000"},
    )
    sections, report = seed_payroll_references(
        replace(base, sections={**base.sections, "labor_rates": (*base.sections["labor_rates"], rate)})
    )

    payload = _by_code(sections, "labor_rates")["RATE_POSITION_LABOR_ASSISTANT"].payload
    assert {key: payload[key] for key in DRILLER_SCALE} == DRILLER_SCALE
    assert (
        "labor_rates:RATE_POSITION_LABOR_ASSISTANT: scale_type, norm_per_shift, rate_norm, ceiling_per_shift, rate_ceiling"
        in report.filled
    )


def test_driller_rates_by_drilling_condition_only_get_no_new_rate():
    base = imported_snapshot()
    rates = tuple(
        replace(item, payload={**item.payload, "condition_code": "COND_GRANITE"})
        if item.code == "RATE_POSITION_LABOR_DRILLER"
        else item
        for item in base.sections["labor_rates"]
    )
    sections, report = seed_payroll_references(replace(base, sections={**base.sections, "labor_rates": rates}))

    assert len(sections["labor_rates"]) == len(rates)
    assert "scale_type" not in _by_code(sections, "labor_rates")["RATE_POSITION_LABOR_DRILLER"].payload
    assert "labor_rates:POSITION_LABOR_DRILLER: нет ставки без условия бурения, шкала не заведена" in report.skipped


def test_matched_positions_are_the_mapped_codes_found_in_the_snapshot():
    # Сопоставление владельца 14.09.2026: семь должностей файла — существующие коды.
    assert MAPPED_POSITIONS == (
        "POSITION_LABOR_DRILLER",
        "POSITION_LABOR_ASSISTANT",
        "POSITION_LABOR_DRIVER_SZM",
        "POSITION_LABOR_BLASTERS",
        "POSITION_LABOR_MASTER",
        "POSITION_LABOR_MINER",
        "POSITION_LABOR_DRIVER_DEL",
    )
    # Кладовщик — новая должность файла: сопоставленной она не считается.
    present = ("POSITION_LABOR_MINER", "POSITION_LABOR_STOREKEEPER", "POSITION_LABOR_DRILLER", "POSITION_LABOR_MASTER")
    positions = tuple(ReferenceItem(code=code, name=code, payload={"category": "INDIRECT"}) for code in present)

    _, report = seed_payroll_references(fx.references(positions=(*fx.POSITIONS, *positions)))

    assert report.matched_positions == ["POSITION_LABOR_DRILLER", "POSITION_LABOR_MASTER", "POSITION_LABOR_MINER"]
    assert report.to_dict()["matched_positions"] == report.matched_positions


def test_matched_positions_count_only_active_records():
    # Из семи сопоставленных владельцем должностей в снимке есть только
    # одна, и та деактивирована — защита «не та организация» не должна
    # считать её найденной.
    positions = (
        ReferenceItem(
            code="POSITION_LABOR_DRILLER",
            name="Машинист буровой установки",
            payload={"category": "INDIRECT"},
            is_active=False,
        ),
    )

    _, report = seed_payroll_references(fx.references(positions=(*fx.POSITIONS, *positions)))

    assert report.matched_positions == []


def test_broken_bit_diameters_are_skipped():
    diameters = {
        "MAT_BIT_TEXT": "abc",
        "MAT_BIT_FLAG": True,
        "MAT_BIT_NAN": "NaN",
        "MAT_BIT_INF": "Infinity",
        "MAT_BIT_171": "171",
    }
    materials = tuple(
        ReferenceItem(code=code, name="Коронка", payload={"unit": "PIECE", "diameter_mm": diameter})
        for code, diameter in diameters.items()
    )
    conditions = tuple(
        ReferenceItem(
            code=f"COND_{code}",
            name="JK830",
            payload={"equipment_type_code": "RIG_JK830", "tech_speed_m_per_h": "10", "bit_material_code": code},
        )
        for code in diameters
    )

    sections, _ = seed_payroll_references(fx.references(materials=materials, drilling_conditions=conditions))

    table = _by_code(sections, "drilling_difficulty")["DRILLING_DIFFICULTY_BASE"].payload["diameter"]
    assert [row["diameter_mm"] for row in table] == ["110", "127", "140", "152", "165", "171", "190", "215", "250"]


def test_bit_diameters_from_drilling_conditions_join_the_owner_list():
    snapshot = fx.references(
        materials=tuple(
            replace(item, payload={**item.payload, "diameter_mm": "171"}) if item.code == "MAT_BIT" else item
            for item in fx.MATERIALS
        )
    )
    sections, _ = seed_payroll_references(snapshot)
    diameters = _by_code(sections, "drilling_difficulty")["DRILLING_DIFFICULTY_BASE"].payload["diameter"]
    assert {"diameter_mm": "171", "k": "1.13"} in diameters
    assert not has_validation_errors(validate_reference_sections(sections))


def test_huge_bit_diameter_is_skipped_not_crashed():
    # "1e30" / 152 не укладывается в 28 знаков Decimal при округлении до
    # сотых — коэффициент не вычисляется, коронка в таблицу не попадает.
    snapshot = fx.references(
        materials=tuple(
            replace(item, payload={**item.payload, "diameter_mm": "1e30"}) if item.code == "MAT_BIT" else item
            for item in fx.MATERIALS
        )
    )
    sections, _ = seed_payroll_references(snapshot)
    diameters = _by_code(sections, "drilling_difficulty")["DRILLING_DIFFICULTY_BASE"].payload["diameter"]
    assert [row["diameter_mm"] for row in diameters] == ["110", "127", "140", "152", "165", "190", "215", "250"]


def test_rates_based_block_economics_do_not_move():
    """Расчёт по ставкам новых ключей не читает: смета до и после сида одна."""

    reclassified, _ = reclassify_positions(imported_snapshot())
    before = _as_snapshot(imported_snapshot(), reclassified)
    crew = tuple(
        CrewMember(member["position_code"], Decimal(member["headcount"]))
        for item in reclassified["crew_templates"]
        if item.code == DEFAULT_CREW_CODE
        for member in item.payload["members"]
    ) + (CrewMember("POSITION_LABOR_DRILLER", Decimal("1")),)
    seeded, _ = seed_payroll_references(before)
    after = _as_snapshot(before, seeded)

    parameters = fx.parameters(crew=crew)
    lines_before = compute_block_economics(fx.snapshot(), parameters, before).lines
    lines_after = compute_block_economics(fx.snapshot(), parameters, after).lines

    assert [(line.cost_item_code, line.amount_rub) for line in lines_after] == [
        (line.cost_item_code, line.amount_rub) for line in lines_before
    ]
    assert any(line.cost_item_code == "LABOR_POSITION_LABOR_DRILLER" for line in lines_after)


# Скрипт `scripts/seed_payroll_references.py`: публикация и коды выхода.

ORGANIZATION = "team-payroll"
COMMENT = "Справочники методики ФОТ"


def _repository(snapshot: ReferenceSnapshot) -> InMemoryEconomicsRepository:
    repository = InMemoryEconomicsRepository()
    repository.publish_references(
        ORGANIZATION,
        "tester",
        _latest(repository),
        {name: list(items) for name, items in snapshot.sections.items()},
        "фикстура тестов",
    )
    return repository


def _latest(repository: InMemoryEconomicsRepository) -> str:
    return repository.list_reference_revisions(ORGANIZATION)[0].id


def test_dry_run_reports_and_publishes_nothing():
    repository = _repository(imported_snapshot())
    base = _latest(repository)

    output, code = run(repository, ORGANIZATION, publish=False, comment=COMMENT)

    assert code == 0
    assert _latest(repository) == base
    assert "published_revision" not in output
    assert (output["organization"], output["base_revision"], output["valid"]) == (ORGANIZATION, base, True)
    # У помощника в этом снимке нет должности: сопоставлены шесть из семи.
    assert output["matched_positions"] == {
        "found": 6,
        "of": len(MAPPED_POSITIONS),
        "codes": [
            "POSITION_LABOR_DRILLER",
            "POSITION_LABOR_DRIVER_SZM",
            "POSITION_LABOR_BLASTERS",
            "POSITION_LABOR_MASTER",
            "POSITION_LABOR_MINER",
            "POSITION_LABOR_DRIVER_DEL",
        ],
    }
    assert "positions:POSITION_LABOR_ASSISTANT" in output["report"]["added"]


def test_publish_again_after_a_successful_one_creates_no_revision():
    repository = _repository(imported_snapshot())

    first, code = run(repository, ORGANIZATION, publish=True, comment=COMMENT)
    assert code == 0
    seeded = repository.list_reference_revisions(ORGANIZATION)[0]
    assert (first["published_revision"], seeded.comment) == (seeded.id, COMMENT)

    again, code = run(repository, ORGANIZATION, publish=True, comment=COMMENT)

    assert code == 0
    assert "published_revision" not in again
    assert again["message"] == "Изменений нет: ревизия не опубликована."
    assert _latest(repository) == seeded.id


def test_publish_with_validation_errors_exits_with_one():
    base = imported_snapshot()
    broken = ReferenceItem(code="ROCK_ZERO", name="Порода без крепости", payload={"hardness_f": 0})
    repository = _repository(replace(base, sections={**base.sections, "rocks": (*base.sections["rocks"], broken)}))
    before = _latest(repository)

    output, code = run(repository, ORGANIZATION, publish=True, comment=COMMENT)

    assert code == 1
    assert _latest(repository) == before
    assert output["valid"] is False
    assert ("rocks", "ROCK_ZERO", "hardness_f") in {
        (issue["section"], issue["code"], issue["field"]) for issue in output["issues"]
    }
    assert "published_revision" not in output


def test_publish_into_an_organization_without_mapped_positions_exits_with_one():
    repository = _repository(fx.references())
    before = _latest(repository)

    output, code = run(repository, ORGANIZATION, publish=True, comment=COMMENT)

    assert code == 1
    assert _latest(repository) == before
    assert output["valid"] is True
    assert output["matched_positions"] == {"found": 0, "of": len(MAPPED_POSITIONS), "codes": []}
    assert output["message"] == (
        "Ни одной из должностей, сопоставленных владельцем, нет в справочнике организации: "
        "вероятно, не та организация. Ревизия не опубликована."
    )
    assert "published_revision" not in output
