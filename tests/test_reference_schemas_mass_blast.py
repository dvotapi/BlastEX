"""Разделы проекта МВ по форме ВМ.09.03 (TASK-018, PR 2): реквизиты объекта, профиль, уведомления."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from cost.v2.models import ReferenceItem
from cost.v2.references import REFERENCE_SECTION_DEFINITIONS, validate_reference_sections
from cost.v2.schemas import SECTION_SCHEMAS, section_json_schema
from cost.v2.schemas.mass_blast import BlastNotificationPayload, MassBlastProfilePayload, MassBlastSitePayload

SECTIONS = ("mass_blast_sites", "mass_blast_profiles", "blast_notifications")


def _item(section: str, code: str, payload: dict, name: str = "Запись") -> ReferenceItem:
    return ReferenceItem(code=code, name=name, payload=payload)


@pytest.mark.parametrize("section", SECTIONS)
def test_sections_are_registered_behind_the_flag(section):
    assert section in SECTION_SCHEMAS
    assert REFERENCE_SECTION_DEFINITIONS[section]["feature"] == "mass_blast_v2"
    assert REFERENCE_SECTION_DEFINITIONS[section]["group"] == "blast_design"


def test_site_fields_have_units_and_refs():
    schema = section_json_schema("mass_blast_sites")["properties"]
    assert schema["q_tp_kg_m3"]["x-unit"] == "кг/м³"
    assert schema["site_code"]["x-ref"] == "sites"
    refs = schema["profile_code"].get("x-ref") or [o.get("x-ref") for o in schema["profile_code"].get("anyOf", [])]
    assert "mass_blast_profiles" in (refs if isinstance(refs, list) else [refs])
    assert all(prop.get("title") for prop in schema.values() if not prop.get("x-internal"))


def test_q_tp_bounds():
    with pytest.raises(ValidationError):
        MassBlastSitePayload.model_validate({"site_code": "ZHK", "q_tp_kg_m3": 0})
    assert MassBlastSitePayload.model_validate({"site_code": "ZHK", "q_tp_kg_m3": 1.1}).customer_approver_is_head is True


def test_profile_points_are_unique_and_well_formed():
    MassBlastProfilePayload.model_validate({"schedule_texts": [{"point": "29.1", "title": "Посты"}]})
    with pytest.raises(ValidationError):
        MassBlastProfilePayload.model_validate({"schedule_texts": [{"point": "16"}, {"point": "16"}]})
    with pytest.raises(ValidationError):
        MassBlastProfilePayload.model_validate({"schedule_texts": [{"point": "п. 16"}]})
    with pytest.raises(ValidationError):
        MassBlastProfilePayload.model_validate({"charge_round_kg": 0})


def test_notification_requires_addressee():
    with pytest.raises(ValidationError):
        BlastNotificationPayload.model_validate({"site_code": "ZHK", "recipient_position": " "})
    item = BlastNotificationPayload.model_validate({"site_code": "ZHK", "recipient_position": "Ростехнадзор"})
    assert item.channel == "LETTER" and item.lead_days == 1


def test_one_site_record_per_site():
    sections = {
        "sites": [_item("sites", "ZHK", {}, "Жуков Камень")],
        "mass_blast_sites": [
            _item("mass_blast_sites", "A", {"site_code": "ZHK"}),
            _item("mass_blast_sites", "B", {"site_code": "ZHK"}),
        ],
    }
    issues = [issue for issue in validate_reference_sections(sections) if issue.section == "mass_blast_sites"]
    assert [issue.code for issue in issues if issue.level == "error"] == ["B"]
