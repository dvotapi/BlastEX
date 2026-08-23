"""Типизированные поверхности уступа: кровля, подошва, откос, пост-взрыв."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterable

from design.models import Point3
from design.spatial.coordinates import CoordinateSystem
from design.spatial.tin import TIN, build_tin, loft_polylines

SURFACE_KINDS = ("top", "floor", "face", "post_blast")

_KIND_NAMES = {
    "top": "Кровля уступа",
    "floor": "Подошва уступа",
    "face": "Откос",
    "post_blast": "Поверхность после взрыва",
}


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


@dataclass
class SurfaceModel:
    """Пространственная поверхность. Операции делегируются TIN, если сеть построена."""

    kind: str
    name: str = ""
    source_format: str = ""
    source_name: str = ""
    created_at: str = ""
    coordinate_system: CoordinateSystem = field(default_factory=CoordinateSystem)
    points: list[Point3] = field(default_factory=list)
    polylines: list[list[Point3]] = field(default_factory=list)
    tin: TIN = field(default_factory=TIN)

    def __post_init__(self) -> None:
        if self.kind not in SURFACE_KINDS:
            raise ValueError(f"Неизвестный тип поверхности: {self.kind}")
        if not self.name:
            self.name = _KIND_NAMES[self.kind]
        if not self.created_at:
            self.created_at = _utc_now_iso()

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "name": self.name,
            "source_format": self.source_format,
            "source_name": self.source_name,
            "created_at": self.created_at,
            "coordinate_system": self.coordinate_system.to_dict(),
            "points": [p.to_dict() for p in self.points],
            "polylines": [[p.to_dict() for p in line] for line in self.polylines],
            "tin": self.tin.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> SurfaceModel | None:
        if not data:
            return None
        kind = str(data.get("kind") or "")
        if kind not in SURFACE_KINDS:
            return None
        tin_data = data.get("tin") or {}
        points = [Point3.from_dict(p) for p in data.get("points", [])]
        if not tin_data.get("triangles") and len(points) >= 3:
            tin = build_tin(points)
        else:
            tin = TIN.from_dict(tin_data)
        return cls(
            kind=kind,
            name=str(data.get("name") or _KIND_NAMES[kind]),
            source_format=str(data.get("source_format") or ""),
            source_name=str(data.get("source_name") or ""),
            created_at=str(data.get("created_at") or ""),
            coordinate_system=CoordinateSystem.from_dict(data.get("coordinate_system")),
            points=points,
            polylines=[
                [Point3.from_dict(p) for p in line] for line in data.get("polylines", [])
            ],
            tin=tin,
        )

    @property
    def has_tin(self) -> bool:
        return not self.tin.is_empty

    def elevation_at(self, x: float, y: float) -> float | None:
        return None if self.tin.is_empty else self.tin.elevation_at(x, y)

    def vertical_intersection(self, x: float, y: float) -> Point3 | None:
        return None if self.tin.is_empty else self.tin.vertical_intersection(x, y)

    def line_intersection(self, p0: Point3, p1: Point3) -> Point3 | None:
        return None if self.tin.is_empty else self.tin.line_intersection(p0, p1)

    def distance_to_surface(self, point: Point3) -> float | None:
        return None if self.tin.is_empty else self.tin.distance_to_surface(point)

    def sample_line(self, x0: float, y0: float, x1: float, y1: float, count: int = 48) -> list[Point3]:
        return [] if self.tin.is_empty else self.tin.sample_line(x0, y0, x1, y1, count)

    def z_range(self) -> tuple[float, float] | None:
        if not self.points and self.tin.is_empty:
            return None
        zs = [p.z for p in (self.points or self.tin.vertices)]
        return (min(zs), max(zs)) if zs else None

    def stats(self) -> dict[str, Any]:
        bounds = self.tin.bounds()
        z_range = self.z_range()
        return {
            "kind": self.kind,
            "name": self.name,
            "source_format": self.source_format,
            "source_name": self.source_name,
            "point_count": len(self.points) or len(self.tin.vertices),
            "triangle_count": len(self.tin.triangles),
            "polyline_count": len(self.polylines),
            "z_min": z_range[0] if z_range else None,
            "z_max": z_range[1] if z_range else None,
            "bounds": {
                "min_x": bounds[0],
                "min_y": bounds[1],
                "min_z": bounds[2],
                "max_x": bounds[3],
                "max_y": bounds[4],
                "max_z": bounds[5],
            }
            if bounds
            else None,
        }


@dataclass
class SurfaceSet:
    """Набор поверхностей блока. Любое поле может отсутствовать — тогда плоскость уступа."""

    top: SurfaceModel | None = None
    floor: SurfaceModel | None = None
    face: SurfaceModel | None = None
    post_blast: SurfaceModel | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "top": self.top.to_dict() if self.top else None,
            "floor": self.floor.to_dict() if self.floor else None,
            "face": self.face.to_dict() if self.face else None,
            "post_blast": self.post_blast.to_dict() if self.post_blast else None,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> SurfaceSet:
        data = data or {}
        return cls(
            top=SurfaceModel.from_dict(data.get("top")),
            floor=SurfaceModel.from_dict(data.get("floor")),
            face=SurfaceModel.from_dict(data.get("face")),
            post_blast=SurfaceModel.from_dict(data.get("post_blast")),
        )

    def get(self, kind: str) -> SurfaceModel | None:
        if kind == "top":
            return self.top
        if kind == "floor":
            return self.floor
        if kind == "face":
            return self.face
        if kind == "post_blast":
            return self.post_blast
        raise ValueError(f"Неизвестный тип поверхности: {kind}")

    def with_surface(self, surface: SurfaceModel) -> SurfaceSet:
        payload = self.to_dict()
        payload[surface.kind] = surface.to_dict()
        return SurfaceSet.from_dict(payload)

    def without(self, kind: str) -> SurfaceSet:
        payload = self.to_dict()
        if kind not in payload:
            raise ValueError(f"Неизвестный тип поверхности: {kind}")
        payload[kind] = None
        return SurfaceSet.from_dict(payload)

    def has_any(self) -> bool:
        return any(s is not None for s in (self.top, self.floor, self.face, self.post_blast))


def build_surface(
    kind: str,
    points: Iterable[Point3],
    *,
    polylines: list[list[Point3]] | None = None,
    name: str = "",
    source_format: str = "",
    source_name: str = "",
    coordinate_system: CoordinateSystem | None = None,
) -> SurfaceModel:
    """Собирает поверхность нужного типа. Для откоса две полилинии лофтятся в сеть."""
    if kind not in SURFACE_KINDS:
        raise ValueError(f"Неизвестный тип поверхности: {kind}")
    point_list = [Point3(x=p.x, y=p.y, z=p.z) for p in points]
    lines = [[Point3(x=p.x, y=p.y, z=p.z) for p in line] for line in (polylines or [])]
    if not point_list:
        point_list = [p for line in lines for p in line]
    tin = _build_kind_tin(kind, point_list, lines)
    return SurfaceModel(
        kind=kind,
        name=name or _KIND_NAMES[kind],
        source_format=source_format,
        source_name=source_name,
        coordinate_system=coordinate_system or CoordinateSystem(),
        points=point_list,
        polylines=lines,
        tin=tin,
    )


def top_surface(points: Iterable[Point3], **kwargs: Any) -> SurfaceModel:
    return build_surface("top", points, **kwargs)


def floor_surface(points: Iterable[Point3], **kwargs: Any) -> SurfaceModel:
    return build_surface("floor", points, **kwargs)


def face_surface(points: Iterable[Point3], **kwargs: Any) -> SurfaceModel:
    return build_surface("face", points, **kwargs)


def post_blast_surface(points: Iterable[Point3], **kwargs: Any) -> SurfaceModel:
    return build_surface("post_blast", points, **kwargs)


def _build_kind_tin(kind: str, points: list[Point3], polylines: list[list[Point3]]) -> TIN:
    usable = [line for line in polylines if len(line) >= 2]
    if kind == "face" and len(usable) >= 2:
        ranked = sorted(usable, key=lambda line: sum(p.z for p in line) / len(line), reverse=True)
        return loft_polylines(ranked[0], ranked[1])
    return build_tin(points)
