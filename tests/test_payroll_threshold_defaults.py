"""Умолчания порогов ФОТ совпадают в схеме, модели и сиде справочников."""

from __future__ import annotations

from decimal import Decimal

from cost.model.payroll import PACE_FLAG_RATIO, PROTODYAKONOV_MAX, WRITE_OFF_FLAG_SHARE
from cost.v2.payroll_defaults import HARDNESS_SCALE_MAX, PAYROLL_PARAMS
from cost.v2.schemas.payroll import DrillingDifficultyPayload, PayrollParamsPayload


def test_threshold_defaults_agree_across_schema_model_and_seed() -> None:
    params = PayrollParamsPayload.model_fields
    schema = (
        params["write_off_flag_share"].default,
        params["pace_flag_ratio"].default,
        DrillingDifficultyPayload.model_fields["hardness_scale_max"].default,
    )
    model = (WRITE_OFF_FLAG_SHARE, PACE_FLAG_RATIO, PROTODYAKONOV_MAX)
    seed = (
        Decimal(PAYROLL_PARAMS["write_off_flag_share"]),
        Decimal(PAYROLL_PARAMS["pace_flag_ratio"]),
        Decimal(HARDNESS_SCALE_MAX),
    )
    assert schema == model == seed == (Decimal("0.25"), Decimal("1.2"), Decimal("20"))
