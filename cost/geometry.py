"""
Этап 1 — геометрия скважин и заряда (левый блок Excel «Расчет стоимости БВР»).

Формулы:
  Выход на скважину     = a × b × (глубина − перебур)
  Длина заряда          = глубина − недозаряд
  Диаметр заряда        = коронка × коэфф. разбуривания
  Вместимость           = π×d²/4 × ρ_ВВ × 1000  (кг/п.м.)
  Масса заряда          = длина × вместимость
  Удельный расход       = масса / выход

  Скважин на блок       = объём блока / выход на скважину
  Доп. скважины         = основные × % добавочных
  Погonaж бурения       = (основные + доп.) × глубина
  Масса ВВ на блок      = (основные + доп.) × масса заряда
  Пром. детонаторы      = всего скважин × шт/скв (1 или 2)
  НСИ скважинное        = всего скважин × (1 или 2 при дублировании)
  НСИ поверхностное     = всего скважин × 1
  НСИ стартовое         = 1 на блок
  Боевики на НСИ        = кол-во скважинного НСИ
"""
from __future__ import annotations

import math

from Blast import ExplosiveProperties

from cost.models import BlockCalculationInput, BlockGeometry, HoleGeometry, InitiationConfig

NSI_LENGTH_OPTIONS_M = [3.6, 4.2, 4.8, 6.0, 7.2, 8.5, 9.0, 10.0, 12.0, 15.0, 18.0]
DETONATOR_DELAY_MS_OPTIONS = list(range(450, 1001, 50))


def normalize_initiation_config(
    *,
    intermediate_detonators_per_hole: int,
    nsi_per_hole: int,
    nsi_length_1_m: float,
    nsi_length_2_m: float,
    detonator_delay_ms: int,
) -> InitiationConfig:
    """Нормализует параметры инициирования (1–2 шт/скв, допустимые длины и задержка)."""
    intermediate_detonators_per_hole = 1 if intermediate_detonators_per_hole < 2 else 2
    nsi_per_hole = 1 if nsi_per_hole < 2 else 2

    if nsi_length_1_m not in NSI_LENGTH_OPTIONS_M:
        nsi_length_1_m = min(NSI_LENGTH_OPTIONS_M, key=lambda x: abs(x - nsi_length_1_m))
    if nsi_length_2_m not in NSI_LENGTH_OPTIONS_M:
        nsi_length_2_m = min(NSI_LENGTH_OPTIONS_M, key=lambda x: abs(x - nsi_length_2_m))

    if detonator_delay_ms not in DETONATOR_DELAY_MS_OPTIONS:
        detonator_delay_ms = min(
            DETONATOR_DELAY_MS_OPTIONS,
            key=lambda x: abs(x - detonator_delay_ms),
        )

    return InitiationConfig(
        intermediate_detonators_per_hole=intermediate_detonators_per_hole,
        nsi_per_hole=nsi_per_hole,
        nsi_length_1_m=nsi_length_1_m,
        nsi_length_2_m=nsi_length_2_m if nsi_per_hole == 2 else 0.0,
        detonator_delay_ms=detonator_delay_ms,
    )


def nsi_length_per_hole(initiation: InitiationConfig) -> float:
    if initiation.nsi_per_hole == 2:
        return initiation.nsi_length_1_m + initiation.nsi_length_2_m
    return initiation.nsi_length_1_m


def charge_diameter_m(crown_mm: float, hole_oversize_coeff: float) -> float:
    return (crown_mm / 1000) * hole_oversize_coeff


def linear_capacity_kg_per_m(diameter_m: float, density_t_m3: float) -> float:
    """Масса ВВ на 1 п.м. скважины, кг."""
    return (math.pi * diameter_m**2 / 4) * density_t_m3 * 1000


def calculate_hole_geometry(
    *,
    grid_a_m: float,
    grid_b_m: float,
    depth_m: float,
    overdrill_m: float,
    undercharge_m: float,
    crown_mm: float,
    hole_oversize_coeff: float,
    explosive: ExplosiveProperties,
    explosive_label: str | None = None,
) -> HoleGeometry:
    """Расчёт заряда одной скважины."""
    undercharge_m = max(0.0, min(undercharge_m, depth_m))
    charge_length_m = depth_m - undercharge_m
    effective_bench_m = max(0.0, depth_m - overdrill_m)
    yield_m3 = grid_a_m * grid_b_m * effective_bench_m

    d_m = charge_diameter_m(crown_mm, hole_oversize_coeff)
    capacity = linear_capacity_kg_per_m(d_m, explosive.density_t_m3)
    charge_mass_kg = charge_length_m * capacity
    specific_q = charge_mass_kg / yield_m3 if yield_m3 > 0 else 0.0

    return HoleGeometry(
        grid_a_m=grid_a_m,
        grid_b_m=grid_b_m,
        depth_m=depth_m,
        overdrill_m=overdrill_m,
        undercharge_m=undercharge_m,
        charge_length_m=charge_length_m,
        charge_diameter_m=d_m,
        capacity_kg_per_m=capacity,
        charge_mass_kg=charge_mass_kg,
        yield_m3=yield_m3,
        specific_q_kg_m3=specific_q,
        explosive_name=explosive.name,
        explosive_label=explosive_label or explosive.name,
    )


def calculate_block_geometry(
    *,
    block_volume_m3: float,
    hole: HoleGeometry,
    additional_holes_pct: float = 0.03,
    initiation: InitiationConfig | None = None,
    intermediate_detonators_per_hole: int = 1,
    nsi_per_hole: int = 1,
    nsi_length_1_m: float = 12.0,
    nsi_length_2_m: float = 6.0,
    detonator_delay_ms: int = 500,
) -> BlockGeometry:
    """Показатели блока для выбранного варианта заряжания."""
    if initiation is None:
        initiation = normalize_initiation_config(
            intermediate_detonators_per_hole=intermediate_detonators_per_hole,
            nsi_per_hole=nsi_per_hole,
            nsi_length_1_m=nsi_length_1_m,
            nsi_length_2_m=nsi_length_2_m,
            detonator_delay_ms=detonator_delay_ms,
        )

    yield_per_hole = hole.yield_m3
    hole_count = (
        math.ceil(block_volume_m3 / yield_per_hole) if yield_per_hole > 0 else 0
    )
    additional_holes = math.ceil(hole_count * additional_holes_pct)
    total_holes = hole_count + additional_holes
    drilling_footage_m = total_holes * hole.depth_m
    total_charge_mass_kg = total_holes * hole.charge_mass_kg
    specific_q = total_charge_mass_kg / block_volume_m3 if block_volume_m3 > 0 else 0.0
    total_intermediate_detonators = (
        total_holes * initiation.intermediate_detonators_per_hole
    )
    total_downhole_nsi = total_holes * initiation.nsi_per_hole
    total_nsi_length_m = total_holes * nsi_length_per_hole(initiation)
    total_boosters = total_downhole_nsi
    total_surface_nsi = total_holes
    total_start_nsi = 1

    return BlockGeometry(
        block_volume_m3=block_volume_m3,
        yield_per_hole_m3=yield_per_hole,
        hole_count=hole_count,
        additional_holes_pct=additional_holes_pct,
        additional_holes=additional_holes,
        total_holes=total_holes,
        drilling_footage_m=drilling_footage_m,
        total_charge_mass_kg=total_charge_mass_kg,
        specific_q_kg_m3=specific_q,
        intermediate_detonators_per_hole=initiation.intermediate_detonators_per_hole,
        nsi_per_hole=initiation.nsi_per_hole,
        nsi_length_1_m=initiation.nsi_length_1_m,
        nsi_length_2_m=initiation.nsi_length_2_m,
        detonator_delay_ms=initiation.detonator_delay_ms,
        total_intermediate_detonators=total_intermediate_detonators,
        total_downhole_nsi=total_downhole_nsi,
        total_nsi_length_m=total_nsi_length_m,
        total_boosters=total_boosters,
        total_surface_nsi=total_surface_nsi,
        total_start_nsi=total_start_nsi,
    )


def hole_geometry_table_rows(
    hole: HoleGeometry,
    *,
    initiation: InitiationConfig | None = None,
    intermediate_detonators_per_hole: int = 1,
    nsi_per_hole: int = 1,
) -> list[tuple[str, str]]:
    """Строки таблицы параметров одной скважины."""
    if initiation is None:
        initiation = normalize_initiation_config(
            intermediate_detonators_per_hole=intermediate_detonators_per_hole,
            nsi_per_hole=nsi_per_hole,
            nsi_length_1_m=12.0,
            nsi_length_2_m=6.0,
            detonator_delay_ms=500,
        )

    rows = [
        ("Сетка a×b, м", f"{hole.grid_a_m:g} × {hole.grid_b_m:g}"),
        ("Глубина, м", f"{hole.depth_m:.1f}"),
        ("Перебур, м", f"{hole.overdrill_m:.1f}"),
        ("Недозаряд, м", f"{hole.undercharge_m:.1f}"),
        ("Длина заряда, м", f"{hole.charge_length_m:.1f}"),
        ("Диаметр заряда, мм", f"{hole.charge_diameter_mm:.0f}"),
        ("Вместимость, кг/п.м.", f"{hole.capacity_kg_per_m:.2f}"),
        ("Выход, м³", f"{hole.yield_m3:.2f}"),
        ("Заряд, кг", f"{hole.charge_mass_kg:.0f}"),
        ("Удельный, кг/м³", f"{hole.specific_q_kg_m3:.3f}"),
        ("Пром. детонаторы, шт/скв", f"{initiation.intermediate_detonators_per_hole}"),
        (
            "Скважинное НСИ, шт/скв",
            f"{initiation.nsi_per_hole}"
            + (" (дублирование)" if initiation.nsi_per_hole == 2 else ""),
        ),
        ("Поверхностное НСИ, шт/скв", "1"),
        ("Длина скважинного НСИ-1, м", f"{initiation.nsi_length_1_m:g}"),
    ]
    if initiation.nsi_per_hole == 2:
        rows.append(("Длина скважинного НСИ-2, м", f"{initiation.nsi_length_2_m:g}"))
    rows.append(("Замедление, мс", f"{initiation.detonator_delay_ms}"))
    return rows


def block_geometry_table_rows(block: BlockGeometry) -> list[tuple[str, str]]:
    """Строки таблицы параметров блока."""
    return [
        ("Объём блока, м³", f"{block.block_volume_m3:.0f}"),
        ("Скважин, шт.", f"{block.hole_count}"),
        ("Доп. скважины, %", f"{block.additional_holes_pct * 100:.1f}"),
        ("Доп. скважины, шт.", f"{block.additional_holes}"),
        ("Всего скважин, шт.", f"{block.total_holes}"),
        ("Кол-во п.м., п.м.", f"{block.drilling_footage_m:.0f}"),
        ("Масса ВВ на блок, кг", f"{block.total_charge_mass_kg:.0f}"),
        ("Удельный с доп., кг/м³", f"{block.specific_q_kg_m3:.3f}"),
        ("Пром. детонаторы, шт", f"{block.total_intermediate_detonators}"),
        ("НСИ скважинное, шт", f"{block.total_downhole_nsi}"),
        ("Боевики на НСИ, шт", f"{block.total_boosters}"),
        ("НСИ поверхностное, шт", f"{block.total_surface_nsi}"),
        ("НСИ стартовое, шт", f"{block.total_start_nsi}"),
        ("Длина скважинного НСИ на блок, м", f"{block.total_nsi_length_m:.0f}"),
    ]


def drilling_hole_table_rows(hole: HoleGeometry) -> list[tuple[str, str]]:
    """Таблица скважины для сценария «только бурение» (без ВВ)."""
    return [
        ("Сетка a×b, м", f"{hole.grid_a_m:g} × {hole.grid_b_m:g}"),
        ("Глубина, м", f"{hole.depth_m:.1f}"),
        ("Перебур, м", f"{hole.overdrill_m:.1f}"),
        ("Выход, м³", f"{hole.yield_m3:.2f}"),
        ("Диаметр коронки, мм", f"{hole.charge_diameter_mm:.0f}"),
    ]


def drilling_block_table_rows(block: BlockGeometry) -> list[tuple[str, str]]:
    """Таблица блока для сценария «только бурение»."""
    return [
        ("Объём блока, м³", f"{block.block_volume_m3:.0f}"),
        ("Скважин, шт.", f"{block.hole_count}"),
        ("Доп. скважины, %", f"{block.additional_holes_pct * 100:.1f}"),
        ("Всего скважин, шт.", f"{block.total_holes}"),
        ("Погонаж бурения, п.м.", f"{block.drilling_footage_m:.0f}"),
    ]


def contour_hole_table_rows(hole: HoleGeometry, *, initiation: InitiationConfig) -> list[tuple[str, str]]:
    """Скважина контура: удельный расход на п.м."""
    q_per_m = hole.charge_mass_kg / hole.charge_length_m if hole.charge_length_m > 0 else 0.0
    rows = hole_geometry_table_rows(hole, initiation=initiation)
    rows.append(("Удельный расход, кг/п.м.", f"{q_per_m:.2f}"))
    return rows


def build_manual_block_input(
    *,
    block_volume_m3: float = 0.0,
    total_holes: int = 0,
    drilling_footage_m: float = 0.0,
    total_charge_mass_kg: float = 0.0,
    production_volume_tons: float = 0.0,
    explosive_key: str = "",
) -> BlockCalculationInput:
    """Синтетический блок для сценариев без геометрии БВР (ПВВ, ЭВВ, RC)."""
    hole = HoleGeometry(
        grid_a_m=0.0,
        grid_b_m=0.0,
        depth_m=0.0,
        overdrill_m=0.0,
        undercharge_m=0.0,
        charge_length_m=0.0,
        charge_diameter_m=0.0,
        capacity_kg_per_m=0.0,
        charge_mass_kg=0.0,
        yield_m3=0.0,
        specific_q_kg_m3=0.0,
        explosive_name="",
        explosive_label="",
    )
    block = BlockGeometry(
        block_volume_m3=block_volume_m3,
        yield_per_hole_m3=0.0,
        hole_count=total_holes,
        additional_holes_pct=0.0,
        additional_holes=0,
        total_holes=total_holes,
        drilling_footage_m=drilling_footage_m,
        total_charge_mass_kg=total_charge_mass_kg,
        specific_q_kg_m3=(
            total_charge_mass_kg / block_volume_m3 if block_volume_m3 > 0 else 0.0
        ),
        intermediate_detonators_per_hole=0,
        nsi_per_hole=0,
        nsi_length_1_m=0.0,
        nsi_length_2_m=0.0,
        detonator_delay_ms=0,
        total_intermediate_detonators=0,
        total_downhole_nsi=0,
        total_nsi_length_m=0.0,
        total_boosters=0,
        total_surface_nsi=0,
        total_start_nsi=0,
    )
    initiation = InitiationConfig(0, 0, 0.0, 0.0, 0)
    return BlockCalculationInput(
        hole=hole,
        block=block,
        initiation=initiation,
        explosive_key=explosive_key,
        hole_depth_m=0.0,
        production_volume_tons=production_volume_tons,
    )


def geometry_table_rows(
    hole: HoleGeometry,
    block: BlockGeometry | None = None,
    *,
    initiation: InitiationConfig | None = None,
    intermediate_detonators_per_hole: int = 1,
    nsi_per_hole: int = 1,
) -> list[tuple[str, str]]:
    """Полная таблица: скважина + опционально блок."""
    rows = hole_geometry_table_rows(
        hole,
        initiation=initiation,
        intermediate_detonators_per_hole=intermediate_detonators_per_hole,
        nsi_per_hole=nsi_per_hole,
    )
    if block is not None:
        rows.append(("", ""))
        rows.extend(block_geometry_table_rows(block))
    return rows
