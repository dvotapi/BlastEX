"""Схемы справочников методики ФОТ (TASK-010 PR 1): поля, умолчания, правила записи."""
from __future__ import annotations

from decimal import Decimal

import pytest
from pydantic import ValidationError

from cost.v2.schemas import section_json_schema
from cost.v2.schemas.labor import LaborRatePayload, PositionPayload
from cost.v2.schemas.misc import RockPayload
from cost.v2.schemas.organization import OrganizationRatesPayload, SitePayload
from cost.v2.schemas.payroll import DowntimeReasonPayload, DrillingDifficultyPayload, PayrollParamsPayload


def _error(exc: pytest.ExceptionInfo[ValidationError]) -> tuple[str, str]:
    error = exc.value.errors()[0]
    return ".".join(str(part) for part in error["loc"]), error["msg"]


CURVE = {
    "position_code": "POSITION_LABOR_DRILLER",
    "scale_type": "CURVE_POWER",
    "norm_per_shift": "115.3846",
    "rate_norm": "45",
    "ceiling_per_shift": "184.6154",
    "rate_ceiling": "168.66",
}
STEP = {
    "position_code": "POSITION_LABOR_DRIVER",
    "scale_type": "STEP",
    "tiers": [
        {"upto_per_shift": "115.3846", "rate": "45"},
        {"upto_per_shift": "138.4615", "rate": "75"},
        {"upto_per_shift": "184.6154", "rate": "110"},
        {"upto_per_shift": None, "rate": "140"},
    ],
}


class TestPositionNorms:
    def test_old_position_reads_with_neutral_defaults(self):
        position = PositionPayload.model_validate({"category": "INDIRECT"})
        assert position.pay_system == "TIME_BONUS"
        assert position.work_conditions_class is None
        assert position.week_hours_override is None
        assert position.hazard_pct == Decimal("0")
        assert position.difficulty == "PLAIN"
        assert position.output_source == "OWN_OUTPUT"

    def test_machinist_norms_from_the_owner_file(self):
        position = PositionPayload.model_validate({
            "category": "DIRECT",
            "operation_code": "PRODUCTION_DRILLING",
            "department": "DRILLING_BLASTING",
            "pay_system": "PIECE_PROGRESSIVE",
            "work_conditions_class": "3.2",
            "hazard_pct": "0.04",
            "extra_vacation_days": "7",
            "night_hours_per_shift": "8",
            "output_unit": "M",
            "difficulty": "NORMALIZED_METERS",
        })
        assert position.work_conditions_class == "3.2"
        assert position.night_hours_per_shift == Decimal("8")

    def test_week_override_is_36_or_40_only(self):
        with pytest.raises(ValidationError):
            PositionPayload.model_validate({"category": "INDIRECT", "week_hours_override": "35"})

    def test_labels_and_units_reach_the_form(self):
        properties = section_json_schema("positions")["properties"]
        assert properties["work_conditions_class"]["title"] == "Класс условий труда"
        assert properties["extra_vacation_days"]["x-unit"] == "дн"
        assert properties["output_unit"]["x-ref"] == "units"


class TestLaborRateScale:
    def test_rate_without_a_scale_stays_valid(self):
        rate = LaborRatePayload.model_validate({"position_code": "P", "fixed_monthly_rub": "60000", "piece_rate_rub": "150"})
        assert rate.scale_type is None
        assert rate.tiers == []
        assert rate.kpi_bonus_pct == Decimal("0")

    def test_power_curve_of_the_machinist(self):
        rate = LaborRatePayload.model_validate(CURVE)
        assert rate.ceiling_per_shift == Decimal("184.6154")

    def test_curve_fields_without_a_scale_type_are_rejected(self):
        with pytest.raises(ValidationError) as exc:
            LaborRatePayload.model_validate({**CURVE, "scale_type": None})
        assert _error(exc) == ("norm_per_shift", "Поле заполняется только вместе с типом шкалы сдельной премии")

    def test_scale_with_a_drilling_condition_is_rejected(self):
        with pytest.raises(ValidationError) as exc:
            LaborRatePayload.model_validate({**CURVE, "condition_code": "COND_GRANITE"})
        assert _error(exc) == (
            "condition_code",
            "Шкала сдельной премии задаётся ставкой без условия бурения: породу учитывают приведённые метры",
        )

    @pytest.mark.parametrize(
        ("patch", "expected"),
        [
            ({"rate_ceiling": None}, ("rate_ceiling", "Для кривой нужны норма, потолок и обе расценки")),
            ({"ceiling_per_shift": "115.3846"}, ("ceiling_per_shift", "Потолок должен быть выше нормы")),
            ({"rate_ceiling": "40"}, ("rate_ceiling", "Расценка на потолке не может быть ниже расценки на норме")),
            ({"rate_norm": "0"}, ("rate_norm", "Расценка на норме должна быть больше нуля")),
            ({"tiers": [{"rate": "45"}]}, ("tiers", "У кривой ступени не заполняются")),
        ],
    )
    def test_broken_curve_is_reported_under_its_field(self, patch, expected):
        with pytest.raises(ValidationError) as exc:
            LaborRatePayload.model_validate({**CURVE, **patch})
        assert _error(exc) == expected

    def test_equal_rates_make_a_flat_curve(self):
        assert LaborRatePayload.model_validate({**CURVE, "rate_ceiling": "45"}).rate_ceiling == Decimal("45")

    def test_step_scale_with_the_owner_tiers(self):
        rate = LaborRatePayload.model_validate(STEP)
        assert [tier.rate for tier in rate.tiers] == [Decimal("45"), Decimal("75"), Decimal("110"), Decimal("140")]
        assert LaborRatePayload.model_validate({**STEP, "tiers": [{"rate": "45"}]}).tiers[0].upto_per_shift is None

    @pytest.mark.parametrize(
        ("tiers", "expected"),
        [
            ([], ("tiers", "Для шкалы «Ступени» нужна хотя бы одна ступень")),
            (
                [{"upto_per_shift": "0", "rate": "45"}, {"rate": "75"}],
                ("tiers.0.upto_per_shift", "Граница первой ступени должна быть больше нуля"),
            ),
            (
                [{"upto_per_shift": None, "rate": "45"}, {"rate": "75"}],
                ("tiers.0.upto_per_shift", "Верхняя граница не задаётся только у последней ступени"),
            ),
            (
                [{"upto_per_shift": "115", "rate": "45"}, {"upto_per_shift": "200", "rate": "75"}],
                ("tiers.1.upto_per_shift", "У последней ступени верхней границы нет: выше неё действует её расценка"),
            ),
            (
                [{"upto_per_shift": "115", "rate": "45"}, {"upto_per_shift": "100", "rate": "75"}, {"rate": "140"}],
                ("tiers.1.upto_per_shift", "Границы ступеней должны возрастать"),
            ),
            (
                [{"upto_per_shift": "115", "rate": "45"}, {"upto_per_shift": "138", "rate": "40"}, {"rate": "140"}],
                ("tiers.1.rate", "Расценка ступени не может быть ниже предыдущей"),
            ),
        ],
    )
    def test_broken_tiers_are_reported_under_the_row(self, tiers, expected):
        with pytest.raises(ValidationError) as exc:
            LaborRatePayload.model_validate({**STEP, "tiers": tiers})
        assert _error(exc) == expected

    def test_step_scale_rejects_curve_fields(self):
        with pytest.raises(ValidationError) as exc:
            LaborRatePayload.model_validate({**STEP, "norm_per_shift": "115"})
        assert _error(exc) == ("norm_per_shift", "У шкалы «Ступени» поля кривой не заполняются")


class TestSitePayroll:
    def test_old_site_reads_with_the_company_schedule(self):
        site = SitePayload.model_validate({})
        assert (site.shift_days_on, site.shift_days_off, site.travel_days) == (Decimal("15"), Decimal("15"), Decimal("2"))
        assert site.maintenance_shifts == Decimal("2")
        assert site.night_shift_share == Decimal("0.5")
        assert site.regional_coefficient == Decimal("0.15")
        assert site.northern_pct == Decimal("0")
        assert site.contract_k == Decimal("1")
        assert site.geology == []
        # Длительность смены объекта заводится в PR 3a вместе с резолвером.
        assert "shift_hours" not in SitePayload.model_fields

    def test_geology_shares_sum_to_one_within_a_thousandth(self):
        thirds = [{"rock_code": code, "share": "0.333"} for code in ("R1", "R2", "R3")]
        assert len(SitePayload.model_validate({"geology": thirds}).geology) == 3
        with pytest.raises(ValidationError) as exc:
            SitePayload.model_validate({"geology": [{"rock_code": "R1", "share": "0.5"}, {"rock_code": "R2", "share": "0.4"}]})
        assert _error(exc) == ("geology", "Сумма долей пород — 0.9, а должна быть 1")

    def test_rock_is_listed_once(self):
        with pytest.raises(ValidationError) as exc:
            SitePayload.model_validate({"geology": [{"rock_code": "R1", "share": "0.5"}, {"rock_code": "R1", "share": "0.5"}]})
        assert _error(exc) == ("geology.1.rock_code", "Порода уже есть в плановой геологии")

    def test_maintenance_cannot_take_the_whole_rotation(self):
        with pytest.raises(ValidationError) as exc:
            SitePayload.model_validate({"shift_days_on": "2", "maintenance_shifts": "2"})
        assert _error(exc) == (
            "maintenance_shifts", "Плановое ТОиР не может занимать всю вахту: эффективных смен не останется"
        )

    def test_contract_factor_is_positive(self):
        with pytest.raises(ValidationError) as exc:
            SitePayload.model_validate({"contract_k": "0"})
        assert _error(exc) == ("contract_k", "Договорной коэффициент должен быть больше нуля")


class TestOrganizationTariffs:
    def test_extra_tariffs_default_to_empty_and_accept_the_law_table(self):
        assert OrganizationRatesPayload().extra_tariffs == []
        rates = OrganizationRatesPayload.model_validate(
            {"extra_tariffs": [{"work_conditions_class": "3.2", "rate": "0.04"}, {"work_conditions_class": "4", "rate": "0.08"}]}
        )
        assert rates.extra_tariffs[1].rate == Decimal("0.08")

    def test_class_is_listed_once(self):
        with pytest.raises(ValidationError) as exc:
            OrganizationRatesPayload.model_validate(
                {"extra_tariffs": [{"work_conditions_class": "3.2", "rate": "0.04"}, {"work_conditions_class": "3.2", "rate": "0.05"}]}
            )
        assert _error(exc) == ("extra_tariffs.1.work_conditions_class", "Класс условий труда уже есть в таблице")


class TestRockHardness:
    def test_empty_hardness_is_allowed(self):
        assert RockPayload.model_validate({}).hardness_f is None

    def test_zero_hardness_is_rejected(self):
        # Отрицательное значение отсекает ещё `ge=0` поля; нуль — только эта проверка.
        with pytest.raises(ValidationError) as exc:
            RockPayload.model_validate({"hardness_f": "0"})
        assert _error(exc) == (
            "hardness_f", "Крепость по Протодьяконову должна быть больше нуля; не знаете — оставьте поле пустым"
        )


PARAMS = {
    "year": "2026",
    "mrot": "27093",
    "annual_hours_40": "1972",
    "annual_hours_36": "1774.4",
    "work_days_year": "247",
    "holidays_year": "14",
}


class TestPayrollParams:
    def test_year_2026_from_the_owner_file(self):
        params = PayrollParamsPayload.model_validate(PARAMS)
        assert params.year == 2026
        assert params.night_pct == Decimal("0.20")
        assert params.vacation_days_base == Decimal("28")
        assert params.margin_share_warn == Decimal("0.70")

    def test_calendar_fields_are_required(self):
        with pytest.raises(ValidationError) as exc:
            PayrollParamsPayload.model_validate({"year": "2026"})
        assert {error["loc"][0] for error in exc.value.errors()} == {
            "mrot", "annual_hours_40", "annual_hours_36", "work_days_year", "holidays_year",
        }

    def test_36_hour_norm_is_not_above_40_hour_norm(self):
        with pytest.raises(ValidationError) as exc:
            PayrollParamsPayload.model_validate({**PARAMS, "annual_hours_36": "2000"})
        assert _error(exc) == (
            "annual_hours_36", "Норма при 36-часовой неделе больше нуля и не больше нормы при 40-часовой"
        )


HARDNESS = [
    {"f_from": None, "f_to": "8", "k": "0.9"},
    {"f_from": "8", "f_to": "12", "k": "1.0"},
    {"f_from": "12", "f_to": "16", "k": "1.1"},
    {"f_from": "16", "f_to": "18", "k": "1.2"},
    {"f_from": "18", "f_to": None, "k": "1.3"},
]


class TestDrillingDifficulty:
    def test_owner_tables_are_valid(self):
        difficulty = DrillingDifficultyPayload.model_validate(
            {"hardness": HARDNESS, "diameter": [{"diameter_mm": "152", "k": "1.00"}, {"diameter_mm": "250", "k": "1.64"}]}
        )
        assert difficulty.hardness[3].k == Decimal("1.2")

    @pytest.mark.parametrize(
        ("rows", "expected"),
        [
            (
                [{"f_from": "0", "f_to": "8", "k": "0.9"}, {"f_from": "8", "f_to": None, "k": "1"}],
                ("hardness.0.f_from", "У первой строки нижней границы нет: она охватывает всю крепость до верхней границы"),
            ),
            (
                [{"f_from": None, "f_to": "8", "k": "0.9"}, {"f_from": "8", "f_to": "20", "k": "1"}],
                ("hardness.1.f_to", "У последней строки верхней границы нет: крепость выше шкалы берёт её коэффициент"),
            ),
            (
                [{"f_from": None, "f_to": "8", "k": "0.9"}, {"f_from": "9", "f_to": None, "k": "1"}],
                (
                    "hardness.1.f_from",
                    "Интервалы крепости идут без разрыва: нижняя граница равна верхней границе предыдущей строки (8)",
                ),
            ),
            (
                [{"f_from": None, "f_to": "8", "k": "0"}],
                ("hardness.0.k", "Коэффициент должен быть больше нуля"),
            ),
        ],
    )
    def test_broken_hardness_table_is_reported_under_the_row(self, rows, expected):
        with pytest.raises(ValidationError) as exc:
            DrillingDifficultyPayload.model_validate({"hardness": rows})
        assert _error(exc) == expected

    def test_diameter_is_listed_once(self):
        with pytest.raises(ValidationError) as exc:
            DrillingDifficultyPayload.model_validate(
                {"diameter": [{"diameter_mm": "152", "k": "1"}, {"diameter_mm": "152.0", "k": "1"}]}
            )
        assert _error(exc) == ("diameter.1.diameter_mm", "Диаметр уже есть в таблице")


class TestDowntimeReasons:
    def test_planned_maintenance_is_excusable(self):
        assert DowntimeReasonPayload.model_validate({"excusable": True, "planned_maintenance": True}).planned_maintenance
        with pytest.raises(ValidationError) as exc:
            DowntimeReasonPayload.model_validate({"planned_maintenance": True})
        assert _error(exc) == (
            "planned_maintenance", "Плановое ТОиР — простой не по вине машиниста: отметьте оба признака"
        )
