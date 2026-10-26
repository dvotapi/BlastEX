"""Плановый темп по строке матрицы условий бурения (TASK-010, Т9).

m_план = v_commercial × k_f(крепость породы строки) × k_d(Ø коронки строки):
коэффициенты блока входят только в M_блока, темп от них не зависит.
"""
from decimal import Decimal

from cost.model import drilling
from cost.model.inputs import ModelContext
from cost.model.pace import planned_pace
from tests import model_fixtures as fx
from tests import payroll_fixtures as pfx

ROCKS = (*fx.ROCKS, *pfx.PAYROLL_SECTIONS["rocks"])
BIT_250 = fx.item(
    "MAT_BIT_250",
    "Коронка 250",
    {"unit": "PIECE", "material_kind": "ТМЦ", "storage_class": "NONE", "nomenclature_role": "DRILL_TOOL", "diameter_mm": "250"},
)
BIT_171 = fx.item(
    "MAT_BIT_171",
    "Коронка 171",
    {"unit": "PIECE", "material_kind": "ТМЦ", "storage_class": "NONE", "nomenclature_role": "DRILL_TOOL", "diameter_mm": "171"},
)
MATERIALS = (*fx.MATERIALS, BIT_250, BIT_171)


def _condition(code: str, **payload: str) -> object:
    base = {
        "equipment_type_code": "RIG_JK830",
        "tech_speed_m_per_h": "12",
        "unproductive_h_per_shift": "1",
        "bit_life_m": "700",
    }
    return fx.item(code, f"JK830 {code}", {**base, **payload})


def _sites(rock_code: str) -> tuple:
    site = fx.SITES[0]
    return (fx.item(site.code, site.name, {**site.payload, "rock_code": rock_code}),)


def _context(conditions: tuple, *, site_rock: str = "ROCK_GRANITE") -> ModelContext:
    references = fx.references(
        rocks=ROCKS,
        sites=_sites(site_rock),
        materials=MATERIALS,
        drilling_conditions=conditions,
        drilling_difficulty=pfx.PAYROLL_SECTIONS["drilling_difficulty"],
    )
    return ModelContext(references, fx.parameters(), fx.physical())


def _pace(conditions: tuple, *, site_rock: str = "ROCK_GRANITE"):
    context = _context(conditions, site_rock=site_rock)
    norms = drilling.compute(context)
    assert norms is not None
    return planned_pace(context, norms), norms


def test_base_row_gives_pace_120() -> None:
    """Строка без породы и коронки — базовая: 12 м/ч × (11 − 1) ч = 120, k = 1."""

    pace, norms = _pace((_condition("COND_BASE"),))

    assert norms.v_commercial_m_per_shift == Decimal("120")
    assert pace.pace == Decimal("120")
    assert pace.k_hardness == Decimal("1")
    assert pace.k_diameter == Decimal("1")
    assert pace.diameter_mm is None
    assert pace.condition_code == "COND_BASE"
    assert any("COND_BASE" in w and "не задана порода" in w for w in pace.warnings)
    assert any("COND_BASE" in w and "не задана коронка" in w for w in pace.warnings)


def test_f17_d250_row_gives_pace_120_times_k() -> None:
    pace, _ = _pace(
        (_condition("COND_F17", rock_code="ROCK_F17", bit_material_code="MAT_BIT_250"),),
        site_rock="ROCK_F17",
    )

    assert pace.k_hardness == Decimal("1.2")
    assert pace.k_diameter == Decimal("1.64")
    assert pace.diameter_mm == Decimal("250")
    assert pace.pace == Decimal("120") * Decimal("1.968")
    assert pace.warnings == ()
    assert "COND_F17" in pace.lineage["planned_pace"]
    assert pace.lineage["condition"] == "drilling_conditions.COND_F17"


def test_rock_without_hardness_warns_with_rock_name() -> None:
    pace, _ = _pace(
        (_condition("COND_NO_F", rock_code="ROCK_NO_F", bit_material_code="MAT_BIT_250"),),
        site_rock="ROCK_NO_F",
    )

    assert pace.k_hardness == Decimal("1")
    assert pace.pace == Decimal("120") * Decimal("1.64")
    assert any("Порода без крепости" in w and "ROCK_NO_F" in w for w in pace.warnings)


def test_unknown_rock_is_warning_not_error() -> None:
    """Порода строки не найдена: `PayrollInputError` становится предупреждением."""

    pace, _ = _pace(
        (_condition("COND_GHOST", rock_code="ROCK_GHOST", bit_material_code="MAT_BIT_250"),),
        site_rock="ROCK_GHOST",
    )

    assert pace.k_hardness == Decimal("1")
    assert any("ROCK_GHOST" in w for w in pace.warnings)


def test_diameter_missing_in_table_falls_back_to_one_with_warning() -> None:
    pace, _ = _pace(
        (_condition("COND_171", rock_code="ROCK_F10", bit_material_code="MAT_BIT_171"),),
        site_rock="ROCK_F10",
    )

    assert pace.k_diameter == Decimal("1")
    assert pace.diameter_mm == Decimal("171")
    assert pace.pace == Decimal("120")
    assert any("MAT_BIT_171" in w and "171" in w for w in pace.warnings)


def test_bit_without_diameter_warns_with_bit_code() -> None:
    pace, _ = _pace((_condition("COND_BIT", bit_material_code="MAT_BIT"),))

    assert pace.k_diameter == Decimal("1")
    assert pace.diameter_mm is None
    assert any("MAT_BIT" in w and "диаметр" in w for w in pace.warnings)


def test_block_k_does_not_change_pace() -> None:
    """Порода блока (объект работ) другая — темп считается по строке матрицы."""

    conditions = (_condition("COND_F17", rock_code="ROCK_F17", bit_material_code="MAT_BIT_250"),)
    pace, norms = _pace(conditions, site_rock="ROCK_F17")
    other_block = _context(conditions, site_rock="ROCK_F10")

    assert planned_pace(other_block, norms).pace == pace.pace


def _pace_f25(scale_max: str | None):
    """Строка f 25 / Ø 152; верх шкалы крепости — из записи «Сложности бурения»."""

    record = pfx.PAYROLL_SECTIONS["drilling_difficulty"][0]
    payload = dict(record.payload) if scale_max is None else {**record.payload, "hardness_scale_max": scale_max}
    references = fx.references(
        rocks=(*ROCKS, fx.item("ROCK_F25", "Порода f25", {"hardness_f": "25"})),
        sites=_sites("ROCK_F25"),
        materials=MATERIALS,
        drilling_conditions=(_condition("COND_F25", rock_code="ROCK_F25"),),
        drilling_difficulty=(fx.item(record.code, record.name, payload),),
    )
    context = ModelContext(references, fx.parameters(), fx.physical())
    norms = drilling.compute(context)
    assert norms is not None
    return planned_pace(context, norms)


def test_hardness_scale_max_comes_from_the_difficulty_record() -> None:
    narrow = _pace_f25(None)
    assert any("выше шкалы" in w and "до 20" in w for w in narrow.warnings)
    wide = _pace_f25("30")
    assert not any("выше шкалы" in w for w in wide.warnings)
    # Коэффициент последней строки таблицы крепости.
    assert wide.k_hardness == Decimal("1.3")
