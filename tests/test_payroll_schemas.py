"""Схемы справочников методики ФОТ (TASK-010 PR 1): поля, умолчания, правила записи."""
from __future__ import annotations

from decimal import Decimal

import pytest
from pydantic import ValidationError

from cost.v2.schemas import section_json_schema
from cost.v2.schemas.labor import LaborRatePayload, PositionPayload


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
