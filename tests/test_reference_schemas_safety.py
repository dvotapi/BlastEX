"""Раздел «Безопасные расстояния и выписка ВМ» (`blast_safety`, TASK-018, PR 1)."""
from __future__ import annotations

from decimal import Decimal

import pytest
from pydantic import ValidationError

from cost.v2.models import ReferenceItem
from cost.v2.references import (
    REFERENCE_SECTION_DEFINITIONS,
    default_reference_sections,
    section_catalog,
    section_visible,
    validate_reference_sections,
)
from cost.v2.schemas import SECTION_SCHEMAS, section_fieldsets, section_json_schema
from cost.v2.schemas.misc import RockPayload
from cost.v2.schemas.safety import BlastSafetyPayload
from design.safety.params import KN_EXTERNAL, KZ_BY_FREE, KZ_BY_STEMMING, safety_params


def _sections(*items: ReferenceItem) -> dict:
    sections = dict(default_reference_sections())
    sections["sites"] = (
        ReferenceItem(code="SITE_A", name="Жуков Камень", payload={}),
        ReferenceItem(code="SITE_B", name="Гусевогорское", payload={}),
    )
    sections["blast_safety"] = items
    return sections


def _errors(sections: dict) -> list:
    return [issue for issue in validate_reference_sections(sections) if issue.level == "error" and issue.section == "blast_safety"]


def test_section_is_registered_behind_the_flag() -> None:
    assert SECTION_SCHEMAS["blast_safety"] is BlastSafetyPayload
    meta = REFERENCE_SECTION_DEFINITIONS["blast_safety"]
    assert meta["group"] == "blast_design"
    assert meta["label"] == "Безопасные расстояния и выписка ВМ"
    assert meta["feature"] == "mass_blast_v2"


def test_catalog_hides_the_section_while_the_flag_is_off() -> None:
    assert not section_visible("blast_safety", {"mass_blast_v2": False})
    assert section_visible("blast_safety", {"mass_blast_v2": True})
    assert section_visible("blast_safety", None)
    assert section_visible("rocks", {})
    codes = {item["code"] for item in section_catalog({"mass_blast_v2": False})}
    assert "blast_safety" not in codes and "rocks" in codes
    assert "blast_safety" in {item["code"] for item in section_catalog({"mass_blast_v2": True})}


def test_hidden_section_is_still_validated_and_published() -> None:
    """При выключенном флаге раздел читается и публикуется: валидация его видит."""

    record = ReferenceItem(code="SAFE_A", name="Жуков Камень", payload={"site_code": "SITE_A"})
    assert _errors(_sections(record)) == []


def test_titles_units_and_fieldsets() -> None:
    properties = section_json_schema("blast_safety")["properties"]
    assert properties["site_code"]["x-ref"] == "sites"
    assert properties["k_ground"]["title"] == "K_г — грунт в основании охраняемых объектов"
    assert properties["k_ground"]["x-unit"] == ""
    assert properties["people_min_m"]["x-unit"] == "м"
    assert properties["k_mech"]["x-unit"] == "доля"
    assert properties["delay_group_ms"]["x-unit"] == "мс"
    assert properties["reserve_primers_pcs"]["x-unit"] == "шт"
    assert "п. 792" in properties["k_ground"]["description"]
    assert "п. 804" in properties["rock_group_ix"]["description"]
    titles = [group["title"] for group in section_fieldsets("blast_safety")]
    assert titles == ["Объект", "Сейсмика", "Разлёт кусков", "Воздушная волна", "Запас для наряда-путёвки"]


def test_defaults_match_the_fnp_tables_used_by_the_calculation() -> None:
    payload = BlastSafetyPayload(site_code="SITE_A")
    assert payload.k_ground == 5 and payload.k_structure == 2 and payload.alpha_blast == 1
    assert payload.people_min_m == 200 and payload.k_mech == Decimal("0.667")
    assert payload.delay_group_ms == 20
    assert not (payload.rock_group_ix or payload.frost or payload.buildings_damaged or payload.rock_group_v_reduce)
    assert payload.reserve_primers_pcs == payload.reserve_nsi_pcs == payload.reserve_starters_pcs == 0
    for rows, table in (
        (payload.kz_by_stemming, KZ_BY_STEMMING),
        (payload.kz_by_free, KZ_BY_FREE),
        (payload.kn_external, KN_EXTERNAL),
    ):
        assert tuple((float(row.ratio), float(row.k)) for row in rows) == table


def test_people_minimum_cannot_be_below_appendix_21() -> None:
    with pytest.raises(ValidationError):
        BlastSafetyPayload(site_code="SITE_A", people_min_m=150)


def test_ix_group_and_v_group_reduction_exclude_each_other() -> None:
    with pytest.raises(ValidationError) as error:
        BlastSafetyPayload(site_code="SITE_A", rock_group_ix=True, rock_group_v_reduce=True)
    assert error.value.errors()[0]["loc"] == ("rock_group_v_reduce",)


def test_kz_table_must_start_at_zero() -> None:
    with pytest.raises(ValidationError):
        BlastSafetyPayload(site_code="SITE_A", kz_by_stemming=[{"ratio": 5, "k": 0.15}])


def test_one_record_per_site() -> None:
    first = ReferenceItem(code="SAFE_A", name="Жуков Камень", payload={"site_code": "SITE_A"})
    second = ReferenceItem(code="SAFE_A2", name="Жуков Камень, копия", payload={"site_code": "SITE_A"})
    issues = _errors(_sections(first, second))
    assert [(issue.code, issue.field) for issue in issues] == [("SAFE_A2", "site_code")]
    assert "одна запись" in issues[0].message
    retired = ReferenceItem(code="SAFE_A2", name="Старая", payload={"site_code": "SITE_A"}, is_active=False)
    other = ReferenceItem(code="SAFE_B", name="Гусевогорское", payload={"site_code": "SITE_B"})
    assert _errors(_sections(first, retired, other)) == []


def test_unknown_site_is_a_dangling_reference() -> None:
    record = ReferenceItem(code="SAFE_X", name="Нет такого", payload={"site_code": "SITE_GHOST"})
    issues = _errors(_sections(record))
    assert [issue.field for issue in issues] == ["site_code"]


def test_record_with_empty_fields_takes_schema_defaults() -> None:
    """Запись заведена — пустые поля по схеме (IX группа, мороз — «нет»), не по форме v0.11."""

    params = safety_params({"site_code": "SITE_A"}, {"hardness_f": 12})
    assert not params.rock_group_ix and not params.frost
    assert params.hardness_f == 12 and params.source("hardness_f") == "REFERENCE"
    assert not params.issues


def test_rock_group_wins_over_site_flags() -> None:
    assert RockPayload(blast_rock_group="IX_PLUS").blast_rock_group == "IX_PLUS"
    with pytest.raises(ValidationError):
        RockPayload(blast_rock_group="X")
    site = {"site_code": "SITE_A", "rock_group_ix": False}
    assert safety_params(site, {"blast_rock_group": "IX_PLUS", "hardness_f": 14}).rock_group_ix
    assert not safety_params({"site_code": "SITE_A", "rock_group_ix": True}, {"blast_rock_group": "VI_VIII"}).rock_group_ix
    reduce = {"site_code": "SITE_A", "rock_group_v_reduce": True}
    assert safety_params(reduce, {"blast_rock_group": "V_MINUS"}).rock_group_v_reduce
    assert not safety_params(reduce, {"blast_rock_group": "VI_VIII"}).rock_group_v_reduce


def test_project_values_override_the_reference() -> None:
    params = safety_params({"site_code": "SITE_A"}, {"hardness_f": 12}, overrides={"hardness_f": 16, "k_ground": 8})
    assert params.hardness_f == 16 and params.source("hardness_f") == "MANUAL_OVERRIDE"
    assert params.k_ground == 8 and params.source("k_ground") == "MANUAL_OVERRIDE"
    assert params.source("k_structure") == "REFERENCE"
