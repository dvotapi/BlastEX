"""Предзаполнение проекта МВ и «Запомнить для объекта» (TASK-018, PR 6, §14, В1–В8)."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from api.services.mass_blast_remember import remember_for_site, rememberable
from cost.v2.models import ReferenceItem
from design.mass_blast_defaults import (
    DefaultsInputs,
    fill_empty,
    hydro_text,
    layer_defaults,
    project_defaults,
    project_number,
    remember_values,
)
from design.mass_blast_posts import suggest_layout
from tests.mass_blast_block66 import design66


@pytest.fixture(scope="module")
def design():
    return design66()


def _payload(**changes):
    payload = {"blast_date": "2026-11-20", "site_code": "ZHK", "blocks": [{"design_id": "d66", "code": "66"}]}
    payload.update(changes)
    return payload


def test_project_number_template():
    assert project_number(["66"], "2026-11-20") == "66-26/МВ"
    assert project_number(["66", "67"], "2026-11-20") == "66+67-26/МВ"
    assert project_number([""], "2026-11-20") == "" and project_number(["66"], "") == ""


def test_design_texts_and_rules(design):
    defaults = project_defaults(_payload(), DefaultsInputs(designs=[design], organization="ООО «Комплексные решения»", created_on="2026-11-12"))
    value = lambda path: defaults[path]["value"]  # noqa: E731
    assert defaults["explosives.initiation"]["source"] == "DESIGN"
    assert value("explosives.initiation") == "Неэлектрическая система инициирования (НСИ)"
    assert value("explosives.charge_design").startswith("Сплошная колонка ВВ")
    # Воды в проекте блока не вводили — «сухие» в документ не пишется.
    assert "blocks[0].details.hydro_text" not in defaults and hydro_text(design) == ""
    assert value("requisites.project_no") == "66-26/МВ" and defaults["requisites.project_no"]["source"] == "RULE"
    assert value("requisites.project_date") == "2026-11-12"
    assert value("requisites.contractor_name") == "ООО «Комплексные решения»"
    assert value("schedule.charging_from") == "2026-11-20" and value("schedule.briefing_date") == "2026-11-20"


def test_source_order_reference_then_passport_then_previous(design):
    previous = {
        "requisites": {"tp_basis": "ТП прошлого проекта", "made_by": {"position": "инженер", "name": "Прошлов П. П."}},
        "explosives": {"initiation": "Текст прошлого проекта"},
        "schedule": {"station": "станция прошлого проекта", "shelter": "укрытие прошлого проекта"},
        "blocks": [{"details": {"purpose": "MINING"}}],
    }
    passport = {"bit_diameter_mm": 140, "compiled_by": {"position": "инженер БВР", "name": "Паспортов П. П."},
                "approved_by": {"position": "тех. директор", "name": "Утвердов У. У."}}
    defaults = project_defaults(_payload(), DefaultsInputs(
        designs=[design], site={"tp_basis": "ТП объекта", "station": "станция объекта"},
        drill_passports=[passport], previous=previous,
    ))
    value = lambda path: (defaults[path]["value"], defaults[path]["source"])  # noqa: E731
    assert value("requisites.tp_basis") == ("ТП объекта", "REFERENCE")
    assert value("schedule.station") == ("станция объекта", "REFERENCE")
    assert value("schedule.shelter") == ("укрытие прошлого проекта", "PREVIOUS")
    # Проект блока главнее прошлого проекта.
    assert value("explosives.initiation")[1] == "DESIGN"
    assert value("explosives.bit_mm") == (140.0, "DRILL_PASSPORT")
    assert value("explosives.reaming_k")[0] == round(144 / 140, 2)
    # Люди: прошлый проект главнее паспорта (В4), но и паспорт подставляется, где прошлого нет.
    assert value("requisites.made_by.name") == ("Прошлов П. П.", "PREVIOUS")
    assert value("requisites.contractor_approver.name") == ("Утвердов У. У.", "DRILL_PASSPORT")
    assert value("blocks[0].details.purpose") == ("MINING", "PREVIOUS")


def test_fill_empty_keeps_own_values():
    payload = {"requisites": {"tp_basis": "своё", "made_by": {"name": ""}}, "blocks": [{"code": "66"}]}
    defaults = {
        "requisites.tp_basis": {"value": "справочник", "source": "REFERENCE"},
        "requisites.made_by.name": {"value": "Иванов", "source": "PREVIOUS"},
        "blocks[0].details.rock_text": {"value": "гранит", "source": "DESIGN"},
        "NARYAD:warehouse": {"value": "склад", "source": "REFERENCE"},
    }
    filled = fill_empty(payload, defaults)
    assert filled["requisites"] == {"tp_basis": "своё", "made_by": {"name": "Иванов"}}
    assert filled["blocks"][0]["details"] == {"rock_text": "гранит"}
    assert payload["requisites"]["made_by"]["name"] == ""  # исходный payload не меняется


def test_layer_defaults():
    seed = {"project": {"blast_date": "2026-11-20"}, "blast_manager": {"position": "рук.", "name": "Руководов"},
            "talon_receiver": {"position": "мастер", "name": "Мастеров"}, "contract": {"contract_no": "Д-1", "contract_date": "01.02.2026"}}
    naryad = layer_defaults("NARYAD", seed, {}, site={"warehouse": "Склад 1", "vehicle": ""}, previous_naryad={"vehicle": "КамАЗ", "blaster_index": "17"})
    assert naryad["warehouse"] == {"value": "Склад 1", "source": "REFERENCE"}
    assert naryad["vehicle"] == {"value": "КамАЗ", "source": "PREVIOUS"}
    assert naryad["issue_date"]["value"] == "2026-11-20" and naryad["blaster_index"]["value"] == "17"
    talon = layer_defaults("TALON", seed, {"fired_date": "2026-11-21"}, view={"admittance_not_before": "13:30"})
    assert talon["issued_date"]["value"] == "2026-11-21" and talon["issued_time"]["value"] == "13:30"
    assert talon["received_by"]["value"] == "мастер Мастеров"
    act = layer_defaults("ACCEPTANCE_ACT", seed, {})
    assert act["contract_date"]["value"] == "2026-02-01" and act["contract_no"]["value"] == "Д-1"
    assert layer_defaults("NOTIFICATION", seed, {}, created_on="2026-11-12")["out_date"]["value"] == "2026-11-12"


def test_remember_values_only_site_fields():
    project = {"requisites": {"tp_basis": "ТП 1"}, "schedule": {"station": "Будка"}}
    assert remember_values(project, ["requisites.tp_basis", "schedule.station"]) == {"tp_basis": "ТП 1", "station": "Будка"}
    with pytest.raises(ValueError, match="не относится"):
        remember_values(project, ["requisites.project_no"])
    with pytest.raises(ValueError, match="пустое"):
        remember_values(project, ["schedule.shelter"])
    assert remember_values({}, ["permit"], layer_kind="NARYAD", layer_payload={"permit": "Разрешение № 5"}) == {
        "blasting_permit": "Разрешение № 5"
    }
    assert remember_values({}, ["contract_date"], layer_kind="ACCEPTANCE_ACT", layer_payload={"contract_date": "2026-02-01"}) == {
        "contract_date": "01.02.2026"
    }


class _Economics:
    def __init__(self, sections):
        self.snapshot = SimpleNamespace(
            revision_id="r1", sections=sections,
            item=lambda section, code: next((i for i in sections.get(section, ()) if i.code == code), None),
        )
        self.published = []

    def get_reference_snapshot(self, organization_id, requested=None):
        return self.snapshot

    def publish_references(self, organization_id, user_id, base_revision, sections, comment=""):
        self.published.append((base_revision, sections, comment))
        return SimpleNamespace(revision_id="r2")


def test_remember_creates_or_updates_the_site_record():
    economics = _Economics({"sites": (ReferenceItem("ZHK", "Жуков Камень", {}),), "mass_blast_sites": ()})
    project = {"site_code": "ZHK", "name": "МВ 66", "schedule": {"station": "Будка у въезда"}}
    result = remember_for_site(economics, "org", "editor", project, ["schedule.station"])
    assert result == {"revision_id": "r2", "fields": ["station"]}
    base, sections, comment = economics.published[-1]
    record = sections["mass_blast_sites"][0]
    assert base == "r1" and record.code == "MBS_ZHK" and record.name == "Жуков Камень"
    assert record.payload == {"site_code": "ZHK", "station": "Будка у въезда"}
    assert "МВ 66" in comment
    # Запись уже есть — обновляется только запомненное поле.
    existing = ReferenceItem("MBS_ZHK", "Жуков Камень", {"site_code": "ZHK", "tp_basis": "ТП"})
    economics = _Economics({"mass_blast_sites": (existing,)})
    remember_for_site(economics, "org", "editor", {**project, "requisites": {"tp_basis": "ТП 2"}}, ["requisites.tp_basis"])
    record = economics.published[-1][1]["mass_blast_sites"][0]
    assert record.payload == {"site_code": "ZHK", "tp_basis": "ТП 2"} and record.revision == 2


def test_remember_stops_on_validation_errors():
    economics = _Economics({"mass_blast_sites": ()})
    errors = [SimpleNamespace(level="error", message="Поле слишком длинное")]
    with pytest.raises(ValueError, match="слишком длинное"):
        remember_for_site(economics, "org", "editor", {"site_code": "ZHK", "schedule": {"station": "x"}}, ["schedule.station"],
                          issues_of=lambda sections: errors)
    assert not economics.published


def test_rememberable_reports_reference_values():
    fields = rememberable({"station": "Будка", "tp_basis": ""})
    assert fields["schedule.station"] == "Будка" and fields["requisites.tp_basis"] is None
    assert "NARYAD:warehouse" not in fields and "warehouse" not in fields
    assert rememberable({"warehouse": "Склад"}, layer_kind="NARYAD") == {
        "warehouse": "Склад", "permit": None, "vehicle": None, "driver": None,
    }


def _square(cx, cy, half):
    return [[cx - half, cy - half], [cx + half, cy - half], [cx + half, cy + half], [cx - half, cy + half]]


def test_suggest_posts_on_road_crossings():
    graphics = {
        "has_situation": True,
        "outlines": [_square(0, 0, 20)],
        "zones": [{"kind": "people", "value_m": 500, "rings": [_square(0, 0, 500)]}],
        "situation": [
            {"name": "Карьерная дорога", "kind": "road", "lines": [[[-800, 10], [800, 10]]]},
            {"name": "ЛЭП", "kind": "power_line", "lines": [[[10, -800], [10, 800]]]},
        ],
    }
    result = suggest_layout(graphics)
    assert [post["code"] for post in result["posts"]] == ["1", "2"]
    posts = [point for point in result["points"] if point["kind"] == "guard_post"]
    assert sorted(abs(point["x"]) for point in posts) == [500.0, 500.0]  # дорога пересекает границу зоны дважды
    station = next(point for point in result["points"] if point["kind"] == "blast_station")
    assert max(abs(station["x"]), abs(station["y"])) > 500  # станция — за зоной
    assert suggest_layout({**graphics, "has_situation": False})["posts"] == []


def test_hydro_text_counts_wet_holes():
    from design.models import WaterInterval

    design = design66()
    design.holes[0].water_intervals = [WaterInterval(from_m=8.0, to_m=10.0, condition="wet")]
    design.holes[1].water_intervals = [WaterInterval(from_m=0.0, to_m=10.0, condition="dry")]
    assert hydro_text(design) == f"Обводнённых скважин 1 из {len([h for h in design.holes if h.enabled])}"


def test_person_comes_whole_from_one_source(design):
    """Должность из справочника и фамилия из прошлого проекта не склеиваются (ревью PR 6)."""

    previous = {"requisites": {"contractor_approver": {"position": "Главный инженер", "name": "Иванов И. И.",
                                                       "authority": "приказ № 5", "is_head": False}}}
    defaults = project_defaults(_payload(), DefaultsInputs(
        designs=[design], site={"contractor_approver_position": "Технический директор"}, previous=previous,
    ))
    person = {part: defaults[f"requisites.contractor_approver.{part}"] for part in ("position", "name", "authority", "is_head")}
    assert {part: entry["value"] for part, entry in person.items()} == {
        "position": "Главный инженер", "name": "Иванов И. И.", "authority": "приказ № 5", "is_head": False,
    }
    assert {entry["source"] for entry in person.values()} == {"PREVIOUS"}


def test_reference_values_resolved_by_context_are_not_filled():
    """q по ТП, ТП и подписанты из справочника контекст берёт сам — с источником (ревью PR 6)."""

    defaults = {
        "explosives.q_tp_kg_m3": {"value": 1.1, "source": "REFERENCE"},
        "requisites.customer_approver.name": {"value": "Заказчиков", "source": "REFERENCE"},
        "schedule.station": {"value": "Будка", "source": "REFERENCE"},
        "requisites.contractor_approver.name": {"value": "Иванов", "source": "PREVIOUS"},
    }
    filled = fill_empty({"explosives": {}, "requisites": {}, "schedule": {}}, defaults)
    assert filled["explosives"] == {} and "customer_approver" not in filled["requisites"]
    assert filled["schedule"]["station"] == "Будка" and filled["requisites"]["contractor_approver"]["name"] == "Иванов"


def test_talon_issue_date_follows_midnight_rollover():
    seed = {"project": {"blast_date": "2026-11-20"}}
    talon = layer_defaults("TALON", seed, {"fired_date": "2026-11-20", "fired_time": "23:50"},
                           view={"admittance_not_before": "00:20", "admittance_date": "2026-11-21"})
    assert (talon["issued_date"]["value"], talon["issued_time"]["value"]) == ("2026-11-21", "00:20")


def test_station_leaves_every_zone_of_a_multi_block_project():
    """Несвязные зоны двух блоков: станция и укрытие — вне обеих (замечание Codex)."""

    graphics = {
        "has_situation": True,
        "outlines": [_square(-5000, 0, 50), _square(5000, 0, 50)],
        "zones": [{"kind": "people", "value_m": 1000, "rings": [_square(-5000, 0, 1050), _square(5000, 0, 1050)]}],
        "situation": [{"name": "Дорога", "kind": "road", "lines": [[[0, 10], [4500, 10]]]}],
    }
    result = suggest_layout(graphics)
    from shapely.geometry import Point, Polygon
    from shapely.ops import unary_union

    zone = unary_union([Polygon(_square(-5000, 0, 1050)), Polygon(_square(5000, 0, 1050))])
    for point in result["points"]:
        if point["kind"] in ("blast_station", "shelter"):
            assert not zone.covers(Point(point["x"], point["y"])), point


def test_inherited_values_come_from_earlier_projects(design):
    """A задал порядок заряжания, B взял его по умолчанию (в payload B пусто) — C получает его от A (Codex)."""

    project_a = {"schedule": {"charging_order": "от бровки к тылу"}, "requisites": {"made_by": {"position": "инженер", "name": "Аов А. А."}}}
    project_b = {"schedule": {"charging_order": ""}, "requisites": {"made_by": {"position": "", "name": ""}}}
    defaults = project_defaults(_payload(), DefaultsInputs(designs=[design], previous=[project_b, project_a]))
    assert defaults["schedule.charging_order"] == {"value": "от бровки к тылу", "source": "PREVIOUS"}
    assert defaults["requisites.made_by.name"]["value"] == "Аов А. А."
    naryad = layer_defaults("NARYAD", {"project": {}}, {}, previous_naryad=[{"vehicle": ""}, {"vehicle": "КамАЗ"}])
    assert naryad["vehicle"]["value"] == "КамАЗ"


def test_reaming_k_uses_the_bit_entered_in_the_project(design):
    defaults = project_defaults(_payload(explosives={"bit_mm": 120}), DefaultsInputs(designs=[design], drill_passports=[{"bit_diameter_mm": 140}]))
    assert defaults["explosives.reaming_k"]["value"] == round(144 / 120, 2)
