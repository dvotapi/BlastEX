"""Экипаж бурения блока для ФОТ по методике (TASK-010 PR 3a, находки 1, 2)."""
from __future__ import annotations

from decimal import Decimal

from cost.model import block_payroll, labor
from cost.model.block_payroll import CrewSlot, block_crew, crew_roster
from cost.model.inputs import CrewMember, ModelContext
from tests import model_fixtures as fx

D = Decimal

_PIECE_ON_METERS = {"category": "DIRECT", "pay_system": "PIECE_BONUS", "difficulty": "NORMALIZED_METERS"}


def _context(references=None, **params) -> ModelContext:
    return ModelContext(references or fx.references(), fx.parameters(**params), fx.physical())


def test_explicit_crew_without_main_adds_main_with_warning() -> None:
    """Без основной должности её премия молча выпала бы из доли: она добавляется, запрос не отклоняется."""

    members, warnings = crew_roster((("P_ASSISTANT", D("2")),), "P_DRILLER")
    assert members == (("P_DRILLER", D("1")), ("P_ASSISTANT", D("2")))
    assert len(warnings) == 1
    assert "один человек в смене" in warnings[0]


def test_crew_roster_keeps_a_crew_that_has_the_main_position() -> None:
    members, warnings = crew_roster((("P_ASSISTANT", D("1")), ("P_DRILLER", D("2"))), "P_DRILLER")
    assert members == (("P_ASSISTANT", D("1")), ("P_DRILLER", D("2")))
    assert warnings == ()


def test_crew_from_package_template_not_all_organization_piece_positions() -> None:
    """Сдельщик на метрах чужой операции и сдельщик бурения вне шаблона в экипаж не попадают."""

    positions = (
        *fx.POSITIONS,
        # Сдельщик бурения на приведённых метрах, но его нет в шаблоне пакета.
        fx.item("POS_ASSISTANT", "Помощник бурильщика", {**_PIECE_ON_METERS, "operation_code": "PRODUCTION_DRILLING"}),
        # Сдельщик на приведённых метрах чужой операции — в шаблоне есть.
        fx.item("POS_OTHER_PIECE", "Сдельщик заряжания", {**_PIECE_ON_METERS, "operation_code": "BULK_CHARGING_SZM"}),
    )
    template = fx.item(
        "CREW_DRILL_AND_BLAST",
        "Бригада полного комплекса",
        {
            "package_code": "DRILL_AND_BLAST",
            "members": [
                {"position_code": "POS_DRILLER", "headcount": "1"},
                {"position_code": "POS_BLASTER", "headcount": "2"},
                {"position_code": "POS_OTHER_PIECE", "headcount": "1"},
            ],
        },
    )
    context = _context(fx.references(positions=positions, crew_templates=(template,)), crew=())

    assert block_crew(context) == (CrewSlot("POS_DRILLER", D("1"), None),)


def test_crew_from_tab_keeps_manual_shifts_and_skips_indirect() -> None:
    positions = (
        *fx.POSITIONS,
        fx.item("POS_RIG_MASTER", "Мастер буровых", {"category": "INDIRECT", "operation_code": "PRODUCTION_DRILLING"}),
    )
    crew = (
        CrewMember("POS_DRILLER", D("2"), D("5.5")),
        CrewMember("POS_RIG_MASTER", D("1")),
        CrewMember("POS_BLASTER", D("2")),
    )
    context = _context(fx.references(positions=positions), crew=crew)

    assert block_crew(context) == (CrewSlot("POS_DRILLER", D("2"), D("5.5")),)


def test_crew_skips_drilling_position_when_operation_not_in_package() -> None:
    """Бурильщик на вкладке, но пакет без бурения — экипажа бурения у блока нет."""

    context = _context(package_code="BLASTING_NO_DRILLING")
    assert context.has_operation("PRODUCTION_DRILLING") is False
    assert block_crew(context) == ()


def test_zero_headcount_means_one_per_shift() -> None:
    """Ноль в составе — один человек в смене, как у `labor`; штат на ротацию выводится отдельно."""

    context = _context()  # вкладка: бурильщик с численностью 0
    assert block_crew(context) == (CrewSlot("POS_DRILLER", D("1"), None),)


def test_crew_rotation_is_public() -> None:
    assert callable(labor.crew_rotation)
    assert not hasattr(labor, "_crew_rotation")
    assert block_payroll.__doc__
