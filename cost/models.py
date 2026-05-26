"""Dataclass'ы для сметных расчётов (этап 0)."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class HoleGeometry:
    """Геометрия и заряд одной скважины (левый блок Excel)."""

    grid_a_m: float
    grid_b_m: float
    depth_m: float
    overdrill_m: float
    undercharge_m: float
    charge_length_m: float
    charge_diameter_m: float
    capacity_kg_per_m: float
    charge_mass_kg: float
    yield_m3: float
    specific_q_kg_m3: float
    explosive_name: str
    explosive_label: str

    @property
    def charge_diameter_mm(self) -> float:
        return self.charge_diameter_m * 1000


@dataclass
class InitiationConfig:
    """Схема инициирования одной скважины."""

    intermediate_detonators_per_hole: int
    nsi_per_hole: int  # скважинное НСИ: 1 или 2 при дублировании внутрискв. сети
    nsi_length_1_m: float
    nsi_length_2_m: float
    detonator_delay_ms: int

    @property
    def downhole_nsi_per_hole(self) -> int:
        return self.nsi_per_hole

    @property
    def surface_nsi_per_hole(self) -> int:
        return 1


@dataclass
class BlockGeometry:
    """Показатели блока по одному варианту заряжания."""

    block_volume_m3: float
    yield_per_hole_m3: float
    hole_count: int
    additional_holes_pct: float
    additional_holes: int
    total_holes: int
    drilling_footage_m: float
    total_charge_mass_kg: float
    specific_q_kg_m3: float
    intermediate_detonators_per_hole: int
    nsi_per_hole: int
    nsi_length_1_m: float
    nsi_length_2_m: float
    detonator_delay_ms: int
    total_intermediate_detonators: int
    total_downhole_nsi: int
    total_nsi_length_m: float
    total_boosters: int
    total_surface_nsi: int
    total_start_nsi: int
