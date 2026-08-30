"""Явный адаптер технического расчёта BlastEX в драйверы Cost V2.

Модуль не знает о React, Streamlit или хранилищах. Он принимает
сериализованный ``BlockGeometry`` существующего REST API и возвращает
воспроизводимый снимок физических величин с происхождением.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Mapping

from cost.v2.models import decimal_value


BLOCK_DRIVER_MAP: dict[str, str] = {
    "rock_volume_m3": "block_volume_m3",
    "drilling_m": "drilling_footage_m",
    "explosive_kg": "total_charge_mass_kg",
    "holes": "total_holes",
    "intermediate_detonators": "total_intermediate_detonators",
    "downhole_nsi": "total_downhole_nsi",
    "nsi_length_m": "total_nsi_length_m",
    "boosters": "total_boosters",
    "surface_nsi": "total_surface_nsi",
    "start_nsi": "total_start_nsi",
}


@dataclass(frozen=True)
class TechnicalDriverSnapshot:
    source_type: str
    source_id: str | None
    physical: dict[str, Decimal]
    lineage: dict[str, str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_type": self.source_type,
            "source_id": self.source_id,
            "physical": dict(self.physical),
            "lineage": dict(self.lineage),
        }


def adapt_blast_block(
    block: Mapping[str, Any],
    *,
    existing_physical: Mapping[str, Any] | None = None,
    source_id: str | None = None,
) -> TechnicalDriverSnapshot:
    """Наложить технические итоги блока на ручные драйверы строки.

    Технические величины имеют приоритет для полей, которые рассчитал
    BlastEX. Операционные поля (часы СЗМ, рейсы, условия объекта)
    сохраняются из ``existing_physical``.
    """

    physical: dict[str, Decimal] = {}
    lineage: dict[str, str] = {}
    for key, raw_value in (existing_physical or {}).items():
        value = decimal_value(raw_value)
        if value < 0:
            raise ValueError(f"Физический драйвер {key} не может быть отрицательным.")
        physical[str(key)] = value
        lineage[str(key)] = "manual"

    for driver, source_field in BLOCK_DRIVER_MAP.items():
        value = decimal_value(block.get(source_field))
        if value < 0:
            raise ValueError(f"Поле BlockGeometry.{source_field} не может быть отрицательным.")
        physical[driver] = value
        lineage[driver] = f"BlastGeometry.block.{source_field}"

    # One BlockGeometry response represents one blastable block. Do not infer
    # blasts for an empty technical draft.
    has_block = any(
        physical.get(key, Decimal("0")) > 0
        for key in ("rock_volume_m3", "drilling_m", "explosive_kg", "holes")
    )
    physical["blasts"] = Decimal("1") if has_block else Decimal("0")
    lineage["blasts"] = "BlastGeometry.block (one calculated block)"

    return TechnicalDriverSnapshot(
        source_type="BLAST_GEOMETRY",
        source_id=source_id,
        physical=physical,
        lineage=lineage,
    )
