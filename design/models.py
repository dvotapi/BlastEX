"""Доменная модель проекта БВР (паспорт буровзрывных работ).

Геометрия — полная 3D: скважина хранит устье и забой как две точки, что делает
наклон, азимут и разрез по ряду частными случаями общей модели, а не отдельным
режимом.
"""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from typing import Any

DESIGN_VERSION = 2


@dataclass
class Point3:
    """Точка в проектных координатах блока, м."""

    x: float
    y: float
    z: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Point3:
        return cls(
            x=float(data.get("x", 0.0)),
            y=float(data.get("y", 0.0)),
            z=float(data.get("z", 0.0)),
        )


@dataclass
class BenchSurface:
    """Плоскость уступа: отметки бровки и подошвы, угол откоса."""

    crest_z_m: float = 0.0
    toe_z_m: float = -10.0
    face_angle_deg: float = 90.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BenchSurface:
        return cls(
            crest_z_m=float(data.get("crest_z_m", 0.0)),
            toe_z_m=float(data.get("toe_z_m", -10.0)),
            face_angle_deg=float(data.get("face_angle_deg", 90.0)),
        )

    @property
    def height_m(self) -> float:
        return max(0.0, self.crest_z_m - self.toe_z_m)


@dataclass
class BlockContour:
    """Контур блока в плане: замкнутый полигон + помеченные открытые откосы."""

    vertices: list[Point3] = field(default_factory=list)
    free_faces: list[list[int]] = field(default_factory=list)
    bench: BenchSurface = field(default_factory=BenchSurface)
    name: str = "Блок"

    def to_dict(self) -> dict[str, Any]:
        return {
            "vertices": [v.to_dict() for v in self.vertices],
            "free_faces": [list(edge) for edge in self.free_faces],
            "bench": self.bench.to_dict(),
            "name": self.name,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BlockContour:
        return cls(
            vertices=[Point3.from_dict(v) for v in data.get("vertices", [])],
            free_faces=[list(edge) for edge in data.get("free_faces", [])],
            bench=BenchSurface.from_dict(data.get("bench", {})),
            name=str(data.get("name", "Блок")),
        )

    @property
    def points_xy(self) -> list[tuple[float, float]]:
        return [(v.x, v.y) for v in self.vertices]


@dataclass
class Hole:
    """Одна скважина: устье и забой как явные 3D-точки."""

    id: str
    row: int
    col: int
    collar: Point3
    toe: Point3
    diameter_mm: float
    subdrill_m: float = 0.0
    kind: str = "production"  # production | contour | presplit | trim
    source: str = "generated"  # generated | manual
    enabled: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "row": self.row,
            "col": self.col,
            "collar": self.collar.to_dict(),
            "toe": self.toe.to_dict(),
            "diameter_mm": self.diameter_mm,
            "subdrill_m": self.subdrill_m,
            "kind": self.kind,
            "source": self.source,
            "enabled": self.enabled,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Hole:
        return cls(
            id=str(data.get("id", "")),
            row=int(data.get("row", 0)),
            col=int(data.get("col", 0)),
            collar=Point3.from_dict(data.get("collar", {})),
            toe=Point3.from_dict(data.get("toe", {})),
            diameter_mm=float(data.get("diameter_mm", 0.0)),
            subdrill_m=float(data.get("subdrill_m", 0.0)),
            kind=str(data.get("kind", "production")),
            source=str(data.get("source", "generated")),
            enabled=bool(data.get("enabled", True)),
        )

    @property
    def length_m(self) -> float:
        dx = self.toe.x - self.collar.x
        dy = self.toe.y - self.collar.y
        dz = self.toe.z - self.collar.z
        return math.sqrt(dx * dx + dy * dy + dz * dz)

    @property
    def angle_deg(self) -> float:
        """Угол оси скважины от вертикали, 0 — строго вниз."""
        horizontal = math.hypot(self.toe.x - self.collar.x, self.toe.y - self.collar.y)
        vertical = self.collar.z - self.toe.z
        if horizontal == 0.0 and vertical == 0.0:
            return 0.0
        return math.degrees(math.atan2(horizontal, vertical))

    @property
    def azimuth_deg(self) -> float:
        """Азимут проекции скважины на план, 0° = север (+Y), по часовой стрелке."""
        dx = self.toe.x - self.collar.x
        dy = self.toe.y - self.collar.y
        if dx == 0.0 and dy == 0.0:
            return 0.0
        return math.degrees(math.atan2(dx, dy)) % 360.0

    @property
    def bench_height_m(self) -> float:
        """Высота уступа по оси скважины без учёта перебура (для выхода породы)."""
        subdrill_vertical = self.subdrill_m * math.cos(math.radians(self.angle_deg))
        return max(0.0, (self.collar.z - self.toe.z) - subdrill_vertical)


@dataclass
class Deck:
    """Одна деко (заряд/забойка/воздушный промежуток) вдоль скважины от устья."""

    kind: str  # charge | stemming | air
    from_m: float
    to_m: float
    explosive_key: str = ""
    mass_kg: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Deck:
        return cls(
            kind=str(data.get("kind", "charge")),
            from_m=float(data.get("from_m", 0.0)),
            to_m=float(data.get("to_m", 0.0)),
            explosive_key=str(data.get("explosive_key", "")),
            mass_kg=float(data.get("mass_kg", 0.0)),
        )


@dataclass
class HoleLoad:
    """Заряжание одной скважины: набор дек и агрегаты."""

    hole_id: str
    decks: list[Deck] = field(default_factory=list)
    total_charge_kg: float = 0.0
    influence_volume_m3: float = 0.0
    specific_q_kg_m3: float = 0.0
    primers: list[float] = field(default_factory=list)  # глубины боевиков, м от устья

    def to_dict(self) -> dict[str, Any]:
        return {
            "hole_id": self.hole_id,
            "decks": [d.to_dict() for d in self.decks],
            "total_charge_kg": self.total_charge_kg,
            "influence_volume_m3": self.influence_volume_m3,
            "specific_q_kg_m3": self.specific_q_kg_m3,
            "primers": list(self.primers),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> HoleLoad:
        return cls(
            hole_id=str(data.get("hole_id", "")),
            decks=[Deck.from_dict(d) for d in data.get("decks", [])],
            total_charge_kg=float(data.get("total_charge_kg", 0.0)),
            influence_volume_m3=float(data.get("influence_volume_m3", 0.0)),
            specific_q_kg_m3=float(data.get("specific_q_kg_m3", 0.0)),
            primers=[float(p) for p in data.get("primers", [])],
        )


@dataclass
class Connector:
    """Связь в схеме инициирования (поверхностная или внутрискважинная)."""

    from_hole: str
    to_hole: str
    delay_ms: float
    kind: str = "surface_nsi"  # surface_nsi | ds_relay | electronic

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Connector:
        return cls(
            from_hole=str(data.get("from_hole", "")),
            to_hole=str(data.get("to_hole", "")),
            delay_ms=float(data.get("delay_ms", 0.0)),
            kind=str(data.get("kind", "surface_nsi")),
        )


@dataclass
class InitiationNetwork:
    """Схема инициирования блока."""

    system: str = "nonel"  # nonel | electronic | detcord
    starters: list[str] = field(default_factory=list)
    connectors: list[Connector] = field(default_factory=list)
    downhole_delay_ms: dict[str, float] = field(default_factory=dict)
    electronic_times_ms: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "system": self.system,
            "starters": list(self.starters),
            "connectors": [c.to_dict() for c in self.connectors],
            "downhole_delay_ms": dict(self.downhole_delay_ms),
            "electronic_times_ms": dict(self.electronic_times_ms),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> InitiationNetwork:
        return cls(
            system=str(data.get("system", "nonel")),
            starters=[str(s) for s in data.get("starters", [])],
            connectors=[Connector.from_dict(c) for c in data.get("connectors", [])],
            downhole_delay_ms={
                str(k): float(v) for k, v in data.get("downhole_delay_ms", {}).items()
            },
            electronic_times_ms={
                str(k): float(v) for k, v in data.get("electronic_times_ms", {}).items()
            },
        )


@dataclass
class BlastDesign:
    """Паспорт БВР — агрегат всего проекта блока."""

    design_id: str
    name: str = "Новый паспорт"
    version: int = DESIGN_VERSION
    updated_at: str = ""
    contour: BlockContour = field(default_factory=BlockContour)
    holes: list[Hole] = field(default_factory=list)
    loads: list[HoleLoad] = field(default_factory=list)
    network: InitiationNetwork = field(default_factory=InitiationNetwork)
    pattern_params: dict[str, Any] = field(default_factory=dict)
    charge_rules: dict[str, Any] = field(default_factory=dict)
    rock_name: str = ""
    explosive_key: str = ""
    coordinate_system: Any = None
    surfaces: Any = None

    def __post_init__(self) -> None:
        from design.spatial.coordinates import CoordinateSystem
        from design.spatial.surfaces import SurfaceSet

        if self.coordinate_system is None:
            self.coordinate_system = CoordinateSystem()
        if self.surfaces is None:
            self.surfaces = SurfaceSet()

    def to_dict(self) -> dict[str, Any]:
        return {
            "design_id": self.design_id,
            "name": self.name,
            "version": self.version,
            "updated_at": self.updated_at,
            "contour": self.contour.to_dict(),
            "holes": [h.to_dict() for h in self.holes],
            "loads": [ld.to_dict() for ld in self.loads],
            "network": self.network.to_dict(),
            "pattern_params": dict(self.pattern_params),
            "charge_rules": dict(self.charge_rules),
            "rock_name": self.rock_name,
            "explosive_key": self.explosive_key,
            "coordinate_system": self.coordinate_system.to_dict(),
            "surfaces": self.surfaces.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BlastDesign:
        from design.spatial.coordinates import CoordinateSystem
        from design.spatial.surfaces import SurfaceSet

        return cls(
            design_id=str(data.get("design_id", "")),
            name=str(data.get("name", "Новый паспорт")),
            version=int(data.get("version", DESIGN_VERSION)),
            updated_at=str(data.get("updated_at", "")),
            contour=BlockContour.from_dict(data.get("contour", {})),
            holes=[Hole.from_dict(h) for h in data.get("holes", [])],
            loads=[HoleLoad.from_dict(ld) for ld in data.get("loads", [])],
            network=InitiationNetwork.from_dict(data.get("network", {})),
            pattern_params=dict(data.get("pattern_params", {})),
            charge_rules=dict(data.get("charge_rules", {})),
            rock_name=str(data.get("rock_name", "")),
            explosive_key=str(data.get("explosive_key", "")),
            coordinate_system=CoordinateSystem.from_dict(data.get("coordinate_system")),
            surfaces=SurfaceSet.from_dict(data.get("surfaces")),
        )
