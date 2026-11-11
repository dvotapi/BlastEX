"""Расход ВМ по проекту блока: `design.mass_blast_calc.explosives_consumption` (TASK-018, PR 1)."""
from __future__ import annotations

import copy

import pytest

from design.mass_blast_calc import MASS_BLAST_CALC_VERSION, explosives_consumption
from design.models import (
    BlastDesign,
    Deck,
    DownholeConnector,
    Hole,
    HoleLoad,
    InitiationNetwork,
    Point3,
    Primer,
    Starter,
    SurfaceConnector,
)
from tests.test_safety_design import FORM, MATERIALS, block66_design

MATERIAL_ROWS = [
    {"code": "MAT_PD", "name": "ПД Сферит-ДП 1000 г", "payload": {"nomenclature_role": "BOOSTER", "mass_kg": 1}},
    {"code": "MAT_NSI_S", "name": "НСИ ИСКРА-С-700-12", "payload": {"nomenclature_role": "NSI_DOWNHOLE", "delay_ms": 700}},
    {"code": "MAT_NSI_P42", "name": "НСИ ИСКРА-П-42-5", "payload": {"nomenclature_role": "NSI_SURFACE", "delay_ms": 42}},
    {"code": "MAT_START", "name": "НСИ ИСКРА-Старт-500", "payload": {"nomenclature_role": "NSI_START"}},
]


def _hole(hole_id: str, x: float, *, enabled: bool = True) -> Hole:
    return Hole(id=hole_id, row=0, col=int(x), collar=Point3(x, 0, 10), toe=Point3(x, 0, 0), diameter_mm=144, enabled=enabled)


def _load(hole_id: str, *decks: Deck, primers: list[Primer]) -> HoleLoad:
    return HoleLoad(hole_id=hole_id, decks=list(decks), primer_items=primers, primers=[p.position_m for p in primers])


def _design() -> BlastDesign:
    holes = [_hole("1", 0), _hole("2", 4), _hole("3", 8), _hole("4", 12, enabled=False)]
    loads = [
        _load(
            "1",
            Deck("stemming", 0, 2.5),
            Deck("charge", 2.5, 6, explosive_key="ЭВВ Порэмит 1А", mass_kg=60),
            Deck("air", 6, 7),
            Deck("charge", 7, 10, product="Гранулит", mass_kg=40),
            primers=[Primer(9.5, "ПД Сферит-ДП 1000 г"), Primer(5.5, "ПД Сферит-ДП 1000 г")],
        ),
        _load("2", Deck("charge", 2.5, 10, explosive_key="ЭВВ Порэмит 1А", mass_kg=130), primers=[Primer(9.5, "ПД Сферит-ДП 1000 г", mass_kg=0.9)]),
        _load("3", Deck("charge", 2.5, 10, explosive_key="ЭВВ Порэмит 1А", mass_kg=130), primers=[Primer(9.5, "ПД неизвестный")]),
        _load("4", Deck("charge", 2.5, 10, explosive_key="ЭВВ Порэмит 1А", mass_kg=999), primers=[Primer(9.5, "ПД Сферит-ДП 1000 г")]),
    ]
    network = InitiationNetwork(
        starter_items=[Starter(id="st", hole_id="1")],
        surface_connectors=[
            SurfaceConnector(id="a", from_hole="1", to_hole="2", delay_ms=25, product="НСИ ИСКРА-П-25-5"),
            SurfaceConnector(id="b", from_hole="2", to_hole="3", delay_ms=42),
            SurfaceConnector(id="c", from_hole="1", to_hole="3", delay_ms=67),
            SurfaceConnector(id="d", from_hole="3", to_hole="4", delay_ms=42),  # к выключенной — не считается
        ],
        downhole_connectors=[
            DownholeConnector(id="dh1", hole_id="1", delay_ms=700, product="НСИ ИСКРА-С-700-12"),
            DownholeConnector(id="dh2", hole_id="2", delay_ms=700),
        ],
    )
    return BlastDesign(design_id="t", holes=holes, loads=loads, network=network, explosive_key="ЭВВ Порэмит 1А")


def _by_kind(lines, kind: str):
    return [line for line in lines if line.kind == kind]


def test_version() -> None:
    assert MASS_BLAST_CALC_VERSION == "mass-blast-v2"


def test_explosives_by_product_without_rounding() -> None:
    lines = _by_kind(explosives_consumption(_design(), MATERIAL_ROWS), "explosive")
    assert {(line.name, line.quantity, line.unit) for line in lines} == {
        ("ЭВВ Порэмит 1А", 320.0, "кг"),  # 60 + 130 + 130; выключенная скважина не входит
        ("Гранулит", 40.0, "кг"),
    }


def test_primers_pieces_and_mass() -> None:
    lines = _by_kind(explosives_consumption(_design(), MATERIAL_ROWS), "primer")
    known = next(line for line in lines if line.name == "ПД Сферит-ДП 1000 г")
    assert known.quantity == 3 and known.unit == "шт"
    assert known.mass_kg == pytest.approx(2.9)  # 1 + 1 из справочника + 0,9 у самого ПД
    assert known.material_code == "MAT_PD"
    unknown = next(line for line in lines if line.name == "ПД неизвестный")
    assert unknown.warning == "primer_mass_unknown" and unknown.mass_kg == 0


def test_downhole_nsi_by_primer_count() -> None:
    lines = _by_kind(explosives_consumption(_design(), MATERIAL_ROWS), "nsi_downhole")
    by_name = {line.name: line.quantity for line in lines}
    # Скв. 1: 2 ПД с маркой коннектора; скв. 2: замедление 700 без марки — материал NSI_DOWNHOLE 700 мс;
    # скв. 3: коннектора нет — подпись и предупреждение.
    assert by_name["НСИ ИСКРА-С-700-12"] == 3
    unmapped = [line for line in lines if line.warning]
    assert [(line.name, line.quantity, line.warning) for line in unmapped] == [("НСИ скважинное", 1.0, "nsi_downhole_unmapped")]
    assert sum(line.quantity for line in lines) == 4  # = числу ПД


def test_surface_by_product_and_delay() -> None:
    lines = _by_kind(explosives_consumption(_design(), MATERIAL_ROWS), "nsi_surface")
    rows = {(line.name, line.delay_ms): (line.quantity, line.source, line.warning) for line in lines}
    assert rows == {
        ("НСИ ИСКРА-П-25-5", 25.0): (1.0, "DESIGN", ""),
        ("НСИ ИСКРА-П-42-5", 42.0): (1.0, "REFERENCE", ""),
        ("НСИ поверхностное 67 мс", 67.0): (1.0, "REFERENCE", "nsi_surface_unmapped"),
    }


def test_starters() -> None:
    design = _design()
    by_reference = _by_kind(explosives_consumption(design, MATERIAL_ROWS), "starter")
    assert [(line.name, line.quantity, line.material_code) for line in by_reference] == [("НСИ ИСКРА-Старт-500", 1.0, "MAT_START")]
    chosen = _by_kind(explosives_consumption(design, MATERIAL_ROWS, starter_product="Старт-200"), "starter")
    assert chosen[0].name == "Старт-200"
    two = MATERIAL_ROWS + [{"code": "MAT_START2", "name": "Старт-200", "payload": {"nomenclature_role": "NSI_START"}}]
    unknown = _by_kind(explosives_consumption(design, two), "starter")
    assert unknown[0].name == "Стартовое устройство" and unknown[0].warning == "starter_unmapped"


def test_design_is_not_changed() -> None:
    design = _design()
    before = copy.deepcopy(design.to_dict())
    explosives_consumption(design, MATERIAL_ROWS)
    assert design.to_dict() == before


def test_block66_consumption_against_form(record_property) -> None:
    """Блок 66: ПД и НСИ по проекту, без запаса — запас добавит наряд-путёвка."""

    design = block66_design()
    lines = explosives_consumption(design, MATERIALS + MATERIAL_ROWS[1:], starter_product="НСИ ИСКРА-Старт-500 / Старт-200")
    explosive = _by_kind(lines, "explosive")[0]
    primers = _by_kind(lines, "primer")[0]
    downhole = _by_kind(lines, "nsi_downhole")[0]
    surface = _by_kind(lines, "nsi_surface")
    starters = _by_kind(lines, "starter")[0]
    holes_196 = FORM["holes"][:196]
    assert primers.quantity == primers.mass_kg == sum(row["primers_pcs"] for row in holes_196)
    assert downhole.quantity == primers.quantity  # В6: по числу ПД
    assert sum(line.quantity for line in surface) == 195  # цепочка теста: 196 скважин — 195 связей
    assert starters.quantity == 1
    form = {row["name"]: row["qty"] for row in FORM["technical_calculation"]["consumption"]}
    line = (
        f"BlastEX: ВВ {explosive.quantity:.1f} кг, ПД {primers.quantity:.0f} шт / {primers.mass_kg:.0f} кг, "
        f"НСИ скв. {downhole.quantity:.0f}, поверхн. {sum(item.quantity for item in surface):.0f} (сеть теста), "
        f"стартер {starters.quantity:.0f} / форма: {form}"
    )
    print(f"consumption_block66: {line}")
    record_property("consumption_block66", line)


def test_downhole_nsi_by_deck_connector() -> None:
    """Коннекторы по декам: ПД берёт марку коннектора своей деки."""

    design = _design()
    design.network.downhole_connectors = [
        DownholeConnector(id="d1", hole_id="1", delay_ms=500, deck_index=1, product="НСИ ИСКРА-С-500-12"),
        DownholeConnector(id="d3", hole_id="1", delay_ms=700, deck_index=3, product="НСИ ИСКРА-С-700-12"),
    ]
    lines = _by_kind(explosives_consumption(design, MATERIAL_ROWS), "nsi_downhole")
    by_name = {line.name: line.quantity for line in lines}
    # ПД на 9,5 м — в деке 3 (7–10 м), на 5,5 м — в деке 1 (2,5–6 м).
    assert by_name["НСИ ИСКРА-С-500-12"] == 1 and by_name["НСИ ИСКРА-С-700-12"] == 1


def test_network_without_v2_objects_is_read_by_legacy_fields() -> None:
    from design.models import Connector

    design = _design()
    design.network.starter_items = []
    design.network.starters = ["1"]
    design.network.surface_connectors = []
    design.network.connectors = [Connector("1", "2", 42), Connector("2", "3", 42)]
    lines = explosives_consumption(design, MATERIAL_ROWS)
    assert _by_kind(lines, "starter")[0].quantity == 1
    assert sum(line.quantity for line in _by_kind(lines, "nsi_surface")) == 2


def test_electronic_downhole_is_not_nonel() -> None:
    """Электронная сеть: на ПД — электронный детонатор, а не НСИ 700 мс из справочника."""

    design = _design()
    design.network.system = "electronic"
    design.network.downhole_connectors = [
        DownholeConnector(id=f"e{h}", hole_id=h, delay_ms=700, kind="electronic") for h in ("1", "2", "3")
    ]
    lines = explosives_consumption(design, MATERIAL_ROWS)
    assert _by_kind(lines, "nsi_downhole") == []
    electronic = _by_kind(lines, "detonator_electronic")
    assert [(line.name, line.quantity, line.material_code) for line in electronic] == [("Электронный детонатор", 4.0, "")]
    assert electronic[0].warning == "detonator_electronic_unmapped"
    # Без коннекторов вид берётся по системе сети.
    design.network.downhole_connectors = []
    assert _by_kind(explosives_consumption(design, MATERIAL_ROWS), "nsi_downhole") == []


def test_electronic_detonator_product_is_kept() -> None:
    """Марка электронного детонатора задана назначением `network.detonators`, а не коннектором."""

    from design.models import Detonator

    design = _design()
    design.network.system = "electronic"
    design.network.downhole_connectors = []
    design.network.detonators = [
        Detonator(id=f"d{h}", hole_id=h, product="DaveyTronic", kind="electronic") for h in ("1", "2", "3")
    ]
    materials = MATERIAL_ROWS + [{"code": "MAT_EDET", "name": "DaveyTronic", "payload": {"nomenclature_role": "DETONATOR_ELECTRIC"}}]
    electronic = _by_kind(explosives_consumption(design, materials), "detonator_electronic")
    assert [(line.name, line.quantity, line.material_code, line.warning) for line in electronic] == [
        ("DaveyTronic", 4.0, "MAT_EDET", "")
    ]


def test_electronic_timing_seeds_are_not_starters() -> None:
    design = _design()
    design.network.system = "electronic"
    assert _by_kind(explosives_consumption(design, MATERIAL_ROWS), "starter") == []
