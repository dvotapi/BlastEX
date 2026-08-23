"""Система координат проекта. Преобразования между СК не делаются молча."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass
class CoordinateSystem:
    """Местная или именованная СК. Единицы — метры, без скрытой смены масштаба."""

    name: str = "local"
    epsg: int | None = None
    origin_x: float = 0.0
    origin_y: float = 0.0
    origin_z: float = 0.0
    units: str = "m"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> CoordinateSystem:
        data = data or {}
        epsg_raw = data.get("epsg")
        epsg = int(epsg_raw) if epsg_raw not in (None, "") else None
        return cls(
            name=str(data.get("name") or "local"),
            epsg=epsg,
            origin_x=float(data.get("origin_x", 0.0)),
            origin_y=float(data.get("origin_y", 0.0)),
            origin_z=float(data.get("origin_z", 0.0)),
            units=str(data.get("units") or "m"),
        )
