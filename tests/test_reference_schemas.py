"""Схемы payload разделов справочников Cost V2 (TASK-006, этап A)."""
from __future__ import annotations

from decimal import Decimal

import pytest
from pydantic import ValidationError, model_validator

from cost.v2.schemas.base import ReferencePayload, field_error

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
            for container, properties in _field_containers(section):
                for name, field in properties.items():
                    if not _is_numeric(field):
                        continue
                    if "x-unit" not in field and not any(
                        "x-unit" in variant for variant in field.get("anyOf", []) if isinstance(variant, dict)
                    ):
                        missing.append(f"{container}.{name}")
        assert missing == []

    def test_reference_fields_point_at_existing_sections(self):
        for section in SECTION_SCHEMAS:
            for field, target in referenced_sections(section).items():
                assert target in REFERENCE_SECTION_DEFINITIONS, f"{section}.{field} → {target}"

    def test_forms_get_only_flat_fields_and_lists_of_flat_rows(self):
        """Форма справочника рисует плоские поля и списки плоских строк.

        Вложенный объект она превратила бы в строку «[object Object]», а флаг
        или дату в строке списка — в текстовое поле (открытые вопросы после
        TASK-010 PR 0). Новая схема с такими полями сначала учит форму.
        """

        problems: list[str] = []
        for section in SECTION_SCHEMAS:
            schema = section_json_schema(section)
            for name, node in (schema.get("properties") or {}).items():
                if any("$ref" in variant for variant in _variants(node)):
                    problems.append(f"{section}.{name}: вложенный объект")
            for model_name, model in (schema.get("$defs") or {}).items():
                for name, node in (model.get("properties") or {}).items():
                    if node.get("x-internal"):
                        continue
                    if any(
                        variant.get("type") in {"array", "object", "boolean"}
                        or "$ref" in variant
                        or variant.get("format") == "date"
                        for variant in _variants(node)
                    ):
                        problems.append(f"{section}.{model_name}.{name}: подполе строки списка")
        assert problems == []


def _is_numeric(field: dict) -> bool:
    if field.get("x-internal"):
        return False
    variants = field.get("anyOf") or [field]
    return any(isinstance(v, dict) and v.get("type") in {"number", "integer"} for v in variants)


def _field_containers(section: str):
    """Свойства раздела и вложенных моделей: подполе списка — такое же поле формы."""

    schema = section_json_schema(section)
    yield section, schema.get("properties") or {}
    for name, model in (schema.get("$defs") or {}).items():
        yield f"{section}.{name}", model.get("properties") or {}


class _ProbeRow(ReferencePayload):
    rate: int = 0


class _Probe(ReferencePayload):
    rows: list[_ProbeRow] = []

    @model_validator(mode="after")
    def _second_row_is_wrong(self) -> "_Probe":
        if len(self.rows) > 1:
            field_error(type(self), ("rows", 1, "rate"), "Ошибка во второй строке", self.rows[1].rate)
        return self


class TestFieldErrorPath:
    def test_error_inside_a_list_row_keeps_the_row_path(self):
        with pytest.raises(ValidationError) as exc:
            _Probe.model_validate({"rows": [{}, {"rate": 5}]})
        error = exc.value.errors()[0]
        assert (error["loc"], error["msg"]) == (("rows", 1, "rate"), "Ошибка во второй строке")

    def test_plain_field_name_still_works(self):
        with pytest.raises(ValidationError) as exc:
            field_error(_Probe, "rows", "Ошибка поля")
        assert exc.value.errors()[0]["loc"] == ("rows",)


def _variants(node: dict) -> list[dict]:
    return [variant for variant in (node.get("anyOf") or [node]) if isinstance(variant, dict)]


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

    def test_wrong_number_is_reported_in_russian_with_the_field_title(self):
        # Сметчик набирает «2,7» с запятой: сообщение обязано назвать поле так,
        # как оно подписано в форме, и объяснить ошибку по-русски.
        sections = dict(default_reference_sections())
        sections["rocks"] = (_item("ROCK_X", {"density_t_m3": "2,7"}),)
        issues = _errors(validate_reference_sections(sections))
        message = next(issue.message for issue in issues if issue.field == "density_t_m3")
        assert "Плотность" in message
        assert "ожидается число" in message

    def test_nested_field_error_names_the_whole_path(self):
        sections = dict(default_reference_sections())
        sections["crew_templates"] = (
            _item("CREW_X", {"package_code": "VM_IN_HOLE", "members": [{"position_code": "P", "headcount": "нет"}]}),
        )
        issues = _errors(validate_reference_sections(sections))
        message = next(issue.message for issue in issues if issue.field == "members.0.headcount")
        assert "Состав бригады → строка 1 → Человек в смене" in message

    def test_every_field_has_a_russian_title(self):
        latin = set("abcdefghijklmnopqrstuvwxyz")
        for section in SECTION_SCHEMAS:
            for container, properties in _field_containers(section):
                for name, node in properties.items():
                    if node.get("x-internal"):
                        continue
                    title = node.get("title", "")
                    assert title, f"{container}.{name}: нет подписи поля"
                    # Английский заголовок pydantic («Rock Code») в интерфейс не попадает.
                    assert not set(title.lower()) <= latin | set(" -/()0123456789"), f"{container}.{name}: подпись {title!r}"

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

    def test_reference_inside_a_list_is_checked(self):
        """Ссылка в составе бригады лежит в элементе списка, а не на верхнем уровне."""

        sections = dict(default_reference_sections())
        sections["crew_templates"] = (
            _item("CREW_X", {
                "package_code": "DRILL_AND_BLAST",
                "members": [
                    {"position_code": "POSITION_GHOST", "headcount": 2},
                    {"position_code": "POSITION_ALSO_MISSING", "headcount": 1},
                ],
            }),
        )
        issues = _errors(validate_reference_sections(sections))
        fields = {issue.field for issue in issues if issue.section == "crew_templates"}
        # Индекс в адресе нужен, чтобы форма подсветила нужную строку состава.
        assert fields == {"members.0.position_code", "members.1.position_code"}

    def test_valid_reference_inside_a_list_passes(self):
        sections = dict(default_reference_sections())
        sections["positions"] = (_item("POSITION_HEAD", {"category": "INDIRECT"}),)
        sections["crew_templates"] = (
            _item("CREW_OK", {
                "package_code": "DRILL_AND_BLAST",
                "members": [{"position_code": "POSITION_HEAD", "headcount": 1}],
            }),
        )
        issues = _errors(validate_reference_sections(sections))
        assert [issue for issue in issues if issue.section == "crew_templates"] == []

    def test_a_negative_rate_is_reported_once(self):
        """Схема и старая проверка не должны показывать одну ошибку дважды."""

        sections = dict(default_reference_sections())
        sections["cost_rules"] = (_item("RULE_X", {"rate_rub": -5}),)
        issues = [
            issue for issue in _errors(validate_reference_sections(sections))
            if issue.section == "cost_rules" and issue.code == "RULE_X"
        ]
        assert len(issues) == 1
        assert issues[0].field == "rate_rub"

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


class TestLegacyEngineFields:
    """Поля, которые движок Cost V1 читает через адаптер (спецификация §4.2, §6)."""

    def test_rock_keeps_strength_and_fissuring(self):
        from cost.v2.schemas.misc import RockPayload

        payload = RockPayload(density_t_m3=Decimal("2.9"), ucs_mpa=Decimal("168"), fissuring_ff=Decimal("2.2"))
        assert payload.ucs_mpa == Decimal("168")
        assert payload.fissuring_ff == Decimal("2.2")
        schema = section_json_schema("rocks")
        assert schema["properties"]["ucs_mpa"]["x-unit"] == "МПа"
        assert schema["properties"]["fissuring_ff"]["x-unit"] == "трещин/м"

    def test_material_keeps_explosive_density_and_chart_label(self):
        from cost.v2.schemas.materials import MaterialPayload

        payload = MaterialPayload(density_t_m3=Decimal("0.85"), chart_label="ГРАНУЛИТ-РП")
        assert payload.density_t_m3 == Decimal("0.85")
        assert payload.chart_label == "ГРАНУЛИТ-РП"
        schema = section_json_schema("materials")
        assert schema["properties"]["density_t_m3"]["x-unit"] == "т/м³"


class TestPublicExchangeFields:
    """Поля, без которых обмен со схемой public теряет данные (спецификация §4.2)."""

    def test_site_fields(self):
        from cost.v2.schemas.organization import SitePayload

        payload = SitePayload(short_name="ЛОМ", mineral_type="нерудные материалы", customer_legal_name='АО "ТК"')
        assert payload.short_name == "ЛОМ"
        with pytest.raises(ValidationError):
            SitePayload(short_name="СЛИШКОМ")
        schema = section_json_schema("sites")
        assert schema["properties"]["short_name"]["title"] == "Краткое имя"
        assert schema["properties"]["customer_legal_name"]["title"] == "Заказчик текстом"

    def test_counterparty_short_name(self):
        from cost.v2.schemas.organization import CounterpartyPayload

        assert CounterpartyPayload(short_name='ООО "ПОМБУР"').short_name == 'ООО "ПОМБУР"'

    def test_equipment_fields_and_other_kind(self):
        from cost.v2.schemas.equipment import EquipmentAssetPayload, EquipmentTypePayload

        item = EquipmentTypePayload(kind="OTHER", brand="INTEO", machine_type_name="Самосвал")
        assert item.kind == "OTHER" and item.brand == "INTEO"
        asset = EquipmentAssetPayload(equipment_type_code="T", serial_number="JK2526063L")
        assert asset.serial_number == "JK2526063L"
        assert "OTHER" in section_json_schema("equipment_types")["properties"]["kind"]["enum"]

    def test_material_tool_and_delay_fields(self):
        from cost.v2.schemas.materials import MaterialPayload

        tool = MaterialPayload(lifetime_m=Decimal("600"), diameter_mm=Decimal("152"), thread_type="DHD350")
        assert tool.lifetime_m == Decimal("600")
        schema = section_json_schema("materials")["properties"]
        assert schema["lifetime_m"]["x-unit"] == "м"
        assert schema["diameter_mm"]["x-unit"] == "мм"
        assert schema["delay_ms"]["x-unit"] == "мс"
        assert MaterialPayload(delay_ms=Decimal("42")).delay_ms == Decimal("42")


class TestNomenclatureRole:
    """Роль номенклатуры в смете: по ней вкладка «Экономика» наполняет списки."""

    def test_role_is_machine_readable(self):
        from cost.v2.schemas.materials import MaterialPayload

        payload = MaterialPayload.model_validate({"nomenclature_role": "EXPLOSIVE"})
        assert payload.nomenclature_role == "EXPLOSIVE"
        assert section_json_schema("materials")["properties"]["nomenclature_role"]["title"] == (
            "Роль в смете"
        )

    def test_role_defaults_to_other(self):
        from cost.v2.schemas.materials import MaterialPayload

        assert MaterialPayload.model_validate({}).nomenclature_role == "OTHER"

    def test_unknown_role_is_rejected(self):
        from cost.v2.schemas.materials import MaterialPayload

        with pytest.raises(ValidationError):
            MaterialPayload.model_validate({"nomenclature_role": "DYNAMITE"})


class TestNumericBoundMessages:
    """Границы `UnitField` (`gt`/`ge`/`le`) — из схемы, а не отдельного правила.

    Крепость породы больше не проверяется валидатором: нижняя граница —
    строгая (`gt=0`) прямо в поле, и `_humanize` называет её числом из
    `ctx`, а не общей фразой «вне допустимого диапазона» (решение владельца
    21.09.2026, TASK-010 PR 1).
    """

    def test_hardness_schema_declares_a_strict_lower_bound(self):
        variants = _variants(section_json_schema("rocks")["properties"]["hardness_f"])
        numeric = next(v for v in variants if v.get("type") == "number")
        assert numeric.get("exclusiveMinimum") == 0
        assert "minimum" not in numeric

    @pytest.mark.parametrize("value", ["0", "-1"])
    def test_non_positive_hardness_is_rejected_with_the_bound_in_the_message(self, value):
        sections = dict(default_reference_sections())
        sections["rocks"] = (_item("ROCK_X", {"hardness_f": value}),)
        issues = _errors(validate_reference_sections(sections))
        message = next(issue.message for issue in issues if issue.field == "hardness_f")
        assert message == "Поле «Крепость по Протодьяконову»: должно быть больше 0."

    def test_upper_bound_message_names_the_limit(self):
        sections = dict(default_reference_sections())
        sections["sites"] = (_item("SITE_X", {"shift_days_on": "400"}),)
        issues = _errors(validate_reference_sections(sections))
        message = next(issue.message for issue in issues if issue.field == "shift_days_on")
        assert message == "Поле «Дней вахты»: должно быть не больше 366."
