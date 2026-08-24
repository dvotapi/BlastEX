"""Доменная модель проекта БВР (паспорт буровзрывных работ).

Геометрия — полная 3D: скважина хранит устье и забой как две точки, что делает
наклон, азимут и разрез по ряду частными случаями общей модели, а не отдельным
режимом.
"""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from typing import Any

DESIGN_VERSION = 3

DATA_ROLES = ("designed", "executed", "predicted", "measured")
WATER_CONDITIONS = ("dry", "moist", "wet", "flowing")
MPA_TO_PA = 1_000_000.0
GPA_TO_PA = 1_000_000_000.0


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


def _opt_float(data: dict[str, Any], key: str) -> float | None:
    raw = data.get(key)
    if raw is None or raw == "":
        return None
    return float(raw)


def _normalize_role(value: Any, default: str = "designed") -> str:
    role = str(value or default).strip().lower()
    return role if role in DATA_ROLES else default


def _normalize_water(value: Any, default: str = "") -> str:
    condition = str(value or default).strip().lower()
    if not condition:
        return ""
    return condition if condition in WATER_CONDITIONS else default


@dataclass
class DataProvenance:
    """Who/how/when a geological record was created. Role is never inferred by ML."""

    source: str = ""
    method: str = ""
    timestamp: str = ""
    role: str = "designed"

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "method": self.method,
            "timestamp": self.timestamp,
            "role": _normalize_role(self.role),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> DataProvenance:
        data = data or {}
        return cls(
            source=str(data.get("source", "")),
            method=str(data.get("method", "")),
            timestamp=str(data.get("timestamp", "")),
            role=_normalize_role(data.get("role")),
        )


@dataclass
class RockPropertySet:
    """Optional rock properties. Units are explicit; conversions are opt-in.

    density_kg_m3          SI density, kg/m³
    ucs_mpa                unconfined compressive strength, MPa
    fracturing             qualitative description or index text
    rqd_pct                rock quality designation, 0–100
    youngs_modulus_gpa     Young's modulus, GPa
    poisson_ratio          dimensionless
    p_wave_velocity_m_s    P-wave velocity, m/s
    joint_spacing_m        mean joint spacing, m
    joint_dip_deg          joint dip, degrees
    joint_dip_direction_deg  joint dip direction, degrees
    blastability           qualitative description or index text
    water_condition        dry | moist | wet | flowing
    """

    density_kg_m3: float | None = None
    ucs_mpa: float | None = None
    fracturing: str = ""
    rqd_pct: float | None = None
    youngs_modulus_gpa: float | None = None
    poisson_ratio: float | None = None
    p_wave_velocity_m_s: float | None = None
    joint_spacing_m: float | None = None
    joint_dip_deg: float | None = None
    joint_dip_direction_deg: float | None = None
    blastability: str = ""
    water_condition: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "density_kg_m3": self.density_kg_m3,
            "ucs_mpa": self.ucs_mpa,
            "fracturing": self.fracturing,
            "rqd_pct": self.rqd_pct,
            "youngs_modulus_gpa": self.youngs_modulus_gpa,
            "poisson_ratio": self.poisson_ratio,
            "p_wave_velocity_m_s": self.p_wave_velocity_m_s,
            "joint_spacing_m": self.joint_spacing_m,
            "joint_dip_deg": self.joint_dip_deg,
            "joint_dip_direction_deg": self.joint_dip_direction_deg,
            "blastability": self.blastability,
            "water_condition": _normalize_water(self.water_condition),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> RockPropertySet:
        data = data or {}
        return cls(
            density_kg_m3=_opt_float(data, "density_kg_m3"),
            ucs_mpa=_opt_float(data, "ucs_mpa"),
            fracturing=str(data.get("fracturing", "")),
            rqd_pct=_opt_float(data, "rqd_pct"),
            youngs_modulus_gpa=_opt_float(data, "youngs_modulus_gpa"),
            poisson_ratio=_opt_float(data, "poisson_ratio"),
            p_wave_velocity_m_s=_opt_float(data, "p_wave_velocity_m_s"),
            joint_spacing_m=_opt_float(data, "joint_spacing_m"),
            joint_dip_deg=_opt_float(data, "joint_dip_deg"),
            joint_dip_direction_deg=_opt_float(data, "joint_dip_direction_deg"),
            blastability=str(data.get("blastability", "")),
            water_condition=_normalize_water(data.get("water_condition")),
        )

    def ucs_pa(self) -> float | None:
        """Explicit MPa → Pa (1 MPa = 1e6 Pa). Never applied implicitly."""
        if self.ucs_mpa is None:
            return None
        return self.ucs_mpa * MPA_TO_PA

    def youngs_modulus_pa(self) -> float | None:
        """Explicit GPa → Pa (1 GPa = 1e9 Pa). Never applied implicitly."""
        if self.youngs_modulus_gpa is None:
            return None
        return self.youngs_modulus_gpa * GPA_TO_PA

    @staticmethod
    def ucs_mpa_from_pa(ucs_pa: float) -> float:
        """Explicit Pa → MPa. Callers must opt in."""
        return float(ucs_pa) / MPA_TO_PA

    @staticmethod
    def youngs_modulus_gpa_from_pa(youngs_modulus_pa: float) -> float:
        """Explicit Pa → GPa. Callers must opt in."""
        return float(youngs_modulus_pa) / GPA_TO_PA


@dataclass
class BlastDomain:
    """Designed geological domain: a plan polygon plus optional elevation bounds.

    An empty polygon means the domain applies everywhere in plan (a layer).
    Measured geology must not be stored here — use hole.measured_intervals.
    """

    id: str
    name: str
    polygon: list[Point3] = field(default_factory=list)
    properties: RockPropertySet = field(default_factory=RockPropertySet)
    provenance: DataProvenance = field(default_factory=DataProvenance)
    z_top_m: float | None = None
    z_bottom_m: float | None = None
    priority: int = 0
    color: str = ""
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "polygon": [p.to_dict() for p in self.polygon],
            "properties": self.properties.to_dict(),
            "provenance": self.provenance.to_dict(),
            "z_top_m": self.z_top_m,
            "z_bottom_m": self.z_bottom_m,
            "priority": self.priority,
            "color": self.color,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> BlastDomain:
        data = data or {}
        return cls(
            id=str(data.get("id", "")),
            name=str(data.get("name", "")),
            polygon=[Point3.from_dict(p) for p in data.get("polygon", [])],
            properties=RockPropertySet.from_dict(data.get("properties")),
            provenance=DataProvenance.from_dict(data.get("provenance")),
            z_top_m=_opt_float(data, "z_top_m"),
            z_bottom_m=_opt_float(data, "z_bottom_m"),
            priority=int(data.get("priority", 0) or 0),
            color=str(data.get("color", "")),
            notes=str(data.get("notes", "")),
        )

    @property
    def points_xy(self) -> list[tuple[float, float]]:
        return [(p.x, p.y) for p in self.polygon]

    def elevation_bounds(self) -> tuple[float | None, float | None]:
        """Return (z_top, z_bottom) with top ≥ bottom when both are set."""
        top, bottom = self.z_top_m, self.z_bottom_m
        if top is not None and bottom is not None and top < bottom:
            return bottom, top
        return top, bottom


@dataclass
class HoleInterval:
    """Designed or measured rock interval along a hole, metres from collar."""

    from_m: float
    to_m: float
    domain_id: str = ""
    domain_name: str = ""
    properties: RockPropertySet = field(default_factory=RockPropertySet)
    provenance: DataProvenance = field(default_factory=DataProvenance)
    role: str = "designed"

    def to_dict(self) -> dict[str, Any]:
        return {
            "from_m": self.from_m,
            "to_m": self.to_m,
            "domain_id": self.domain_id,
            "domain_name": self.domain_name,
            "properties": self.properties.to_dict(),
            "provenance": self.provenance.to_dict(),
            "role": _normalize_role(self.role),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> HoleInterval:
        data = data or {}
        start = float(data.get("from_m", 0.0))
        end = float(data.get("to_m", 0.0))
        if end < start:
            start, end = end, start
        return cls(
            from_m=start,
            to_m=end,
            domain_id=str(data.get("domain_id", "")),
            domain_name=str(data.get("domain_name", "")),
            properties=RockPropertySet.from_dict(data.get("properties")),
            provenance=DataProvenance.from_dict(data.get("provenance")),
            role=_normalize_role(data.get("role")),
        )


@dataclass
class WaterInterval:
    """Designed or measured water along a hole, metres from collar."""

    from_m: float
    to_m: float
    condition: str = "wet"
    provenance: DataProvenance = field(default_factory=DataProvenance)
    role: str = "designed"
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "from_m": self.from_m,
            "to_m": self.to_m,
            "condition": _normalize_water(self.condition, default="wet") or "wet",
            "provenance": self.provenance.to_dict(),
            "role": _normalize_role(self.role),
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> WaterInterval:
        data = data or {}
        start = float(data.get("from_m", 0.0))
        end = float(data.get("to_m", 0.0))
        if end < start:
            start, end = end, start
        return cls(
            from_m=start,
            to_m=end,
            condition=_normalize_water(data.get("condition"), default="wet") or "wet",
            provenance=DataProvenance.from_dict(data.get("provenance")),
            role=_normalize_role(data.get("role")),
            notes=str(data.get("notes", "")),
        )


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
    intervals: list[HoleInterval] = field(default_factory=list)
    water_intervals: list[WaterInterval] = field(default_factory=list)
    measured_intervals: list[HoleInterval] = field(default_factory=list)
    measured_water_intervals: list[WaterInterval] = field(default_factory=list)

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
            "intervals": [iv.to_dict() for iv in self.intervals],
            "water_intervals": [iv.to_dict() for iv in self.water_intervals],
            "measured_intervals": [iv.to_dict() for iv in self.measured_intervals],
            "measured_water_intervals": [iv.to_dict() for iv in self.measured_water_intervals],
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
            intervals=[HoleInterval.from_dict(iv) for iv in data.get("intervals", [])],
            water_intervals=[WaterInterval.from_dict(iv) for iv in data.get("water_intervals", [])],
            measured_intervals=[HoleInterval.from_dict(iv) for iv in data.get("measured_intervals", [])],
            measured_water_intervals=[
                WaterInterval.from_dict(iv) for iv in data.get("measured_water_intervals", [])
            ],
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
    domains: list[BlastDomain] = field(default_factory=list)
    water_table_z_m: float | None = None

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
            "domains": [domain.to_dict() for domain in self.domains],
            "water_table_z_m": self.water_table_z_m,
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
            domains=[BlastDomain.from_dict(d) for d in data.get("domains", [])],
            water_table_z_m=_opt_float(data, "water_table_z_m"),
        )
