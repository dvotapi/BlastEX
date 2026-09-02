"""Схемы payload разделов справочников Cost V2 (TASK-006, этап A)."""
from __future__ import annotations

from decimal import Decimal

import pytest
from pydantic import ValidationError

from cost.v2.models import ReferenceItem
from cost.v2.references import (
    REFERENCE_SECTION_DEFINITIONS,
    ValidationIssue,
    default_reference_sections,
    validate_reference_sections,
)
from cost.v2.schemas import SECTION_SCHEMAS, referenced_sections, section_json_schema
from cost.v2.schemas.labor import PositionPayload
from cost.v2.schemas.costs import UnitFixedCostPayload
from cost.v2.schemas.equipment import EquipmentTypePayload
from cost.v2.schemas.organization import OrganizationRatesPayload


def _item(code: str, payload: dict, name: str = "Запись") -> ReferenceItem:
    return ReferenceItem(code=code, name=name, payload=payload)


class TestRegistry:
    def test_every_section_except_the_deprecated_one_has_a_schema(self):
        without_schema = {
            code for code in REFERENCE_SECTION_DEFINITIONS if code not in SECTION_SCHEMAS
        }
        assert without_schema == {"drilling_productivity"}

    def test_no_schema_without_a_section(self):
        assert not set(SECTION_SCHEMAS) - set(REFERENCE_SECTION_DEFINITIONS)

    def test_every_numeric_field_declares_a_unit(self):
        """Без единицы сметчик не понимает, руб/смену перед ним или руб/месяц."""

        missing: list[str] = []
        for section in SECTION_SCHEMAS:
            for name, field in (section_json_schema(section).get("properties") or {}).items():
                if not _is_numeric(field):
                    continue
                if "x-unit" not in field and not any(
                    "x-unit" in variant for variant in field.get("anyOf", []) if isinstance(variant, dict)
                ):
                    missing.append(f"{section}.{name}")
        assert missing == []

    def test_reference_fields_point_at_existing_sections(self):
        for section in SECTION_SCHEMAS:
            for field, target in referenced_sections(section).items():
                assert target in REFERENCE_SECTION_DEFINITIONS, f"{section}.{field} → {target}"


def _is_numeric(field: dict) -> bool:
    if field.get("x-internal"):
        return False
    variants = field.get("anyOf") or [field]
    return any(isinstance(v, dict) and v.get("type") in {"number", "integer"} for v in variants)


class TestPositionSchema:
    def test_accepts_the_example_from_the_reference_model(self):
        payload = PositionPayload.model_validate({
            "category": "DIRECT",
            "operation_code": "BLAST_EXECUTION",
            "norm_shifts_per_month": 21,
            "norm_operations_per_month": 10,
            "piece_driver": "rock_volume_m3",
            "piece_unit": 1000,
            "per_diem_applies": True,
        })
        assert payload.norm_operations_per_month == Decimal("10")

    def test_direct_position_without_an_operation_is_rejected(self):
        with pytest.raises(ValidationError) as exc:
            PositionPayload.model_validate({"category": "DIRECT"})
        assert "операция" in str(exc.value).lower()

    def test_indirect_position_must_not_carry_an_operation(self):
        with pytest.raises(ValidationError):
            PositionPayload.model_validate({"category": "INDIRECT", "operation_code": "BLAST_EXECUTION"})

    def test_extra_field_is_rejected(self):
        with pytest.raises(ValidationError) as exc:
            PositionPayload.model_validate({"category": "INDIRECT", "salary": 100})
        assert "salary" in str(exc.value)

    def test_negative_norm_is_rejected(self):
        with pytest.raises(ValidationError):
            PositionPayload.model_validate({"category": "INDIRECT", "norm_shifts_per_month": -1})


class TestOtherSchemas:
    def test_organization_rates_defaults_match_the_adr(self):
        rates = OrganizationRatesPayload()
        assert rates.income_tax_rate == Decimal("0.13")
        assert rates.social_contribution_rate == Decimal("0.30")
        assert rates.injury_insurance_rate == Decimal("0.0042")
        assert rates.vacation_reserve_rate == Decimal("0.20")
        assert rates.overhead_rate == Decimal("0.10")
        assert rates.target_margin_rate == Decimal("0.10")
        assert rates.vat_rate == Decimal("0.20")

    def test_rate_above_one_is_rejected(self):
        with pytest.raises(ValidationError):
            OrganizationRatesPayload(vat_rate=Decimal("1.2"))

    def test_monthly_budget_maintenance_needs_an_amount(self):
        with pytest.raises(ValidationError) as exc:
            EquipmentTypePayload.model_validate({"kind": "SZM", "maintenance_mode": "MONTHLY_BUDGET"})
        assert "бюджет" in str(exc.value).lower()

    def test_indirect_labour_cost_needs_a_position_and_headcount(self):
        with pytest.raises(ValidationError):
            UnitFixedCostPayload.model_validate({"category": "INDIRECT_LABOR", "monthly_rub": 1000})
        ok = UnitFixedCostPayload.model_validate({
            "category": "INDIRECT_LABOR", "position_code": "POSITION_WAREHOUSE_HEAD", "headcount": 1,
        })
        assert ok.monthly_rub is None

    def test_other_fixed_cost_needs_an_amount(self):
        with pytest.raises(ValidationError):
            UnitFixedCostPayload.model_validate({"category": "FACILITY"})


class TestValidationThroughSchemas:
    def test_default_sections_are_valid(self):
        issues = validate_reference_sections(default_reference_sections())
        assert [issue for issue in issues if issue.level == "error"] == []

    def test_extra_field_is_reported_with_the_field_name(self):
        sections = dict(default_reference_sections())
        sections["rocks"] = (_item("ROCK_X", {"density_t_m3": 2.7, "hardness": 12}),)
        issues = _errors(validate_reference_sections(sections))
        assert any(issue.field == "hardness" and "не входит" in issue.message for issue in issues)

    def test_direct_position_without_operation_blocks_publication(self):
        sections = dict(default_reference_sections())
        sections["positions"] = (_item("POSITION_DRILLER", {"category": "DIRECT"}),)
        issues = _errors(validate_reference_sections(sections))
        assert any(issue.section == "positions" and "операция" in issue.message.lower() for issue in issues)

    def test_dangling_reference_is_reported_under_its_field(self):
        sections = dict(default_reference_sections())
        sections["labor_rates"] = (_item("RATE_X", {"position_code": "POSITION_MISSING"}),)
        issues = _errors(validate_reference_sections(sections))
        assert any(
            issue.section == "labor_rates" and issue.field == "position_code" and "не найдена" in issue.message
            for issue in issues
        )

    def test_existing_reference_passes(self):
        sections = dict(default_reference_sections())
        sections["positions"] = (_item("POSITION_HEAD", {"category": "INDIRECT"}),)
        sections["labor_rates"] = (_item("RATE_HEAD", {"position_code": "POSITION_HEAD"}),)
        issues = _errors(validate_reference_sections(sections))
        assert [issue for issue in issues if issue.section == "labor_rates"] == []

    def test_drilling_condition_without_rock_is_a_valid_default(self):
        sections = dict(default_reference_sections())
        sections["equipment_types"] = (_item("TYPE_JK830", {"kind": "DRILL_RIG"}),)
        sections["drilling_conditions"] = (
            _item("COND_DEFAULT", {"equipment_type_code": "TYPE_JK830", "tech_speed_m_per_h": 12}),
        )
        issues = _errors(validate_reference_sections(sections))
        assert [issue for issue in issues if issue.section == "drilling_conditions"] == []


def _errors(issues: list[ValidationIssue]) -> list[ValidationIssue]:
    return [issue for issue in issues if issue.level == "error"]
