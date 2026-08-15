"""Справочник горных пород для технологического расчёта БВР."""
from __future__ import annotations

from dataclasses import asdict
import math
from typing import Iterable

from Blast import RockProperties

DEFAULT_ROCKS: tuple[RockProperties, ...] = (
    RockProperties("Габбро-диабаз", 2.9, 168, 2.2),
    RockProperties("Гранит", 2.65, 150, 2.0),
    RockProperties("Известняк", 2.5, 80, 1.5),
    RockProperties("Песчаник", 2.4, 100, 1.8),
)

DEFAULT_ROCK_NAME = "Габбро-диабаз"


def _finite_float(value: object, default: float = 0.0) -> float:
    try:
        parsed = float(value or default)
    except (TypeError, ValueError):
        return default
    return parsed if math.isfinite(parsed) else default


def rocks_to_records(rocks: Iterable[RockProperties]) -> list[dict]:
    return [asdict(rock) for rock in rocks]


def rocks_from_records(records: list[dict]) -> list[RockProperties]:
    rocks: list[RockProperties] = []
    for row in records:
        name = str(row.get("name", "")).strip()
        if not name:
            continue
        rocks.append(
            RockProperties(
                name=name,
                density_t_m3=_finite_float(row.get("density_t_m3")),
                ucs_mpa=_finite_float(row.get("ucs_mpa")),
                fissuring_ff=_finite_float(row.get("fissuring_ff")),
            )
        )
    return rocks


def find_rock(name: str, rocks: Iterable[RockProperties] | None = None) -> RockProperties | None:
    source = rocks if rocks is not None else DEFAULT_ROCKS
    for rock in source:
        if rock.name == name:
            return rock
    return None
