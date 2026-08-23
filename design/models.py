"""Доменная модель проекта БВР (паспорт буровзрывных работ).

Геометрия — полная 3D: скважина хранит устье и забой как две точки, что делает
наклон, азимут и разрез по ряду частными случаями общей модели, а не отдельным
режимом.
"""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from typing import Any

DESIGN_VERSION = 6

DATA_ROLES = ("designed", "executed", "predicted", "measured")
ROLE_PREDICTED = "predicted"
ROLE_MEASURED = "measured"
RECEPTOR_KINDS = (
    "building",
    "pipeline",
    "crusher",
    "highwall",
    "power_line",
    "monitoring_station",
)
SCALED_DISTANCE_CONVENTIONS = (
    "q_cube_over_r",
    "r_over_q_cube",
    "q_sqrt_over_r",
    "r_over_q_sqrt",
)
DEFAULT_VIBRATION_CONVENTION = "q_cube_over_r"
WATER_CONDITIONS = ("dry", "moist", "wet", "flowing")
DECK_KINDS = (
    "stemming",
    "charge",  # legacy alias of bulk_explosive
    "bulk_explosive",
    "packaged_explosive",
    "air",  # legacy alias of air_deck
    "air_deck",
    "inert_deck",
    "water_deck",
    "primer",
    "booster",
    "detonator",
)
EXPLOSIVE_DECK_KINDS = frozenset({"charge", "bulk_explosive", "packaged_explosive"})
AIR_DECK_KINDS = frozenset({"air", "air_deck"})
PRIMER_KINDS = ("primer", "booster", "detonator")
GEOLOGICAL_INTERVALS = ("", "any", "bottom", "column", "collar")
CHARGE_ACTION_REGIONS = ("interval", "bottom", "column", "collar", "remaining")
HOLE_KINDS = (
    "production",
    "buffer",
    "trim",
    "presplit",
    "contour",
    "stab",
    "satellite",
    "infill",
)
# Wall / auxiliary kinds keep their own ids when the production grid is renumbered.
PRESERVED_HOLE_KINDS = ("contour", "presplit", "trim", "satellite")
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
    spacing_a_m: float | None = None
    burden_b_m: float | None = None

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
            "spacing_a_m": self.spacing_a_m,
            "burden_b_m": self.burden_b_m,
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
            spacing_a_m=_opt_float(data, "spacing_a_m"),
            burden_b_m=_opt_float(data, "burden_b_m"),
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
    kind: str = "production"  # see HOLE_KINDS; unknown values are kept for old designs
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


def is_explosive_deck_kind(kind: str) -> bool:
    """True for decks that carry explosive mass (legacy charge included)."""
    return str(kind) in EXPLOSIVE_DECK_KINDS


def is_air_deck_kind(kind: str) -> bool:
    return str(kind) in AIR_DECK_KINDS


@dataclass
class Primer:
    """In-hole initiator: position from collar plus product and mass.

    Old designs stored only depths in ``HoleLoad.primers``. New loads keep both
    the float list (backward compatible) and these explicit objects.
    """

    position_m: float
    product: str = ""
    mass_kg: float = 0.0
    kind: str = "primer"

    def to_dict(self) -> dict[str, Any]:
        return {
            "position_m": self.position_m,
            "product": self.product,
            "mass_kg": self.mass_kg,
            "kind": self.kind if self.kind in PRIMER_KINDS else "primer",
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | float | int) -> Primer:
        if isinstance(data, (int, float)):
            return cls(position_m=float(data))
        raw_kind = str(data.get("kind", "primer") or "primer")
        return cls(
            position_m=float(data.get("position_m", data.get("depth_m", 0.0)) or 0.0),
            product=str(data.get("product", data.get("explosive_key", "")) or ""),
            mass_kg=float(data.get("mass_kg", 0.0) or 0.0),
            kind=raw_kind if raw_kind in PRIMER_KINDS else "primer",
        )


def _parse_primers(data: dict[str, Any]) -> tuple[list[float], list[Primer]]:
    """Accept old ``primers: [float]`` and new ``primer_items`` side by side."""
    raw_items = data.get("primer_items")
    raw_primers = data.get("primers", [])
    items: list[Primer] = []
    if raw_items:
        items = [Primer.from_dict(item) for item in raw_items]
    elif raw_primers:
        items = [Primer.from_dict(item) for item in raw_primers]
    depths = [item.position_m for item in items]
    if not depths and raw_primers:
        depths = [float(item) for item in raw_primers if isinstance(item, (int, float))]
    return depths, items


@dataclass
class ChargeCondition:
    """When a charge template applies. Empty / None fields mean “any”."""

    hole_kinds: list[str] = field(default_factory=list)
    rows: list[int] = field(default_factory=list)
    depth_min_m: float | None = None
    depth_max_m: float | None = None
    diameter_min_mm: float | None = None
    diameter_max_mm: float | None = None
    burden_min_m: float | None = None
    burden_max_m: float | None = None
    spacing_min_m: float | None = None
    spacing_max_m: float | None = None
    rock_domain_ids: list[str] = field(default_factory=list)
    geological_interval: str = ""
    water: str = ""
    distance_to_face_min_m: float | None = None
    distance_to_face_max_m: float | None = None
    target_pf_min: float | None = None
    target_pf_max: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "hole_kinds": list(self.hole_kinds),
            "rows": list(self.rows),
            "depth_min_m": self.depth_min_m,
            "depth_max_m": self.depth_max_m,
            "diameter_min_mm": self.diameter_min_mm,
            "diameter_max_mm": self.diameter_max_mm,
            "burden_min_m": self.burden_min_m,
            "burden_max_m": self.burden_max_m,
            "spacing_min_m": self.spacing_min_m,
            "spacing_max_m": self.spacing_max_m,
            "rock_domain_ids": list(self.rock_domain_ids),
            "geological_interval": self.geological_interval,
            "water": self.water,
            "distance_to_face_min_m": self.distance_to_face_min_m,
            "distance_to_face_max_m": self.distance_to_face_max_m,
            "target_pf_min": self.target_pf_min,
            "target_pf_max": self.target_pf_max,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> ChargeCondition:
        data = data or {}
        rows_raw = data.get("rows") or []
        return cls(
            hole_kinds=[str(v) for v in data.get("hole_kinds", []) if str(v)],
            rows=[int(v) for v in rows_raw],
            depth_min_m=_opt_float(data, "depth_min_m"),
            depth_max_m=_opt_float(data, "depth_max_m"),
            diameter_min_mm=_opt_float(data, "diameter_min_mm"),
            diameter_max_mm=_opt_float(data, "diameter_max_mm"),
            burden_min_m=_opt_float(data, "burden_min_m"),
            burden_max_m=_opt_float(data, "burden_max_m"),
            spacing_min_m=_opt_float(data, "spacing_min_m"),
            spacing_max_m=_opt_float(data, "spacing_max_m"),
            rock_domain_ids=[str(v) for v in data.get("rock_domain_ids", []) if str(v)],
            geological_interval=str(data.get("geological_interval", "") or ""),
            water=str(data.get("water", "") or ""),
            distance_to_face_min_m=_opt_float(data, "distance_to_face_min_m"),
            distance_to_face_max_m=_opt_float(data, "distance_to_face_max_m"),
            target_pf_min=_opt_float(data, "target_pf_min"),
            target_pf_max=_opt_float(data, "target_pf_max"),
        )


@dataclass
class ChargeAction:
    """What to place when a template matches: product, region, optional primer."""

    kind: str = "bulk_explosive"
    explosive_key: str = ""
    product: str = ""
    region: str = "interval"
    length_m: float | None = None
    mass_kg: float | None = None
    place_primer: bool = False
    primer_offset_m: float | None = None
    primer_product: str = ""
    primer_mass_kg: float = 0.0
    primer_kind: str = "primer"

    def to_dict(self) -> dict[str, Any]:
        kind = self.kind if self.kind in DECK_KINDS else "bulk_explosive"
        region = self.region if self.region in CHARGE_ACTION_REGIONS else "interval"
        primer_kind = self.primer_kind if self.primer_kind in PRIMER_KINDS else "primer"
        return {
            "kind": kind,
            "explosive_key": self.explosive_key,
            "product": self.product,
            "region": region,
            "length_m": self.length_m,
            "mass_kg": self.mass_kg,
            "place_primer": self.place_primer,
            "primer_offset_m": self.primer_offset_m,
            "primer_product": self.primer_product,
            "primer_mass_kg": self.primer_mass_kg,
            "primer_kind": primer_kind,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> ChargeAction:
        data = data or {}
        kind = str(data.get("kind", "bulk_explosive") or "bulk_explosive")
        if kind == "charge":
            kind = "bulk_explosive"
        elif kind == "air":
            kind = "air_deck"
        elif kind not in DECK_KINDS:
            kind = "bulk_explosive"
        region = str(data.get("region", "interval") or "interval")
        if region not in CHARGE_ACTION_REGIONS:
            region = "interval"
        primer_kind = str(data.get("primer_kind", "primer") or "primer")
        if primer_kind not in PRIMER_KINDS:
            primer_kind = "primer"
        return cls(
            kind=kind,
            explosive_key=str(data.get("explosive_key", "") or ""),
            product=str(data.get("product", "") or ""),
            region=region,
            length_m=_opt_float(data, "length_m"),
            mass_kg=_opt_float(data, "mass_kg"),
            place_primer=bool(data.get("place_primer", False)),
            primer_offset_m=_opt_float(data, "primer_offset_m"),
            primer_product=str(data.get("primer_product", "") or ""),
            primer_mass_kg=float(data.get("primer_mass_kg", 0.0) or 0.0),
            primer_kind=primer_kind,
        )


@dataclass
class ChargeTemplate:
    """Spatial charging rule: conditions + actions, applied by priority."""

    id: str
    name: str = ""
    conditions: ChargeCondition = field(default_factory=ChargeCondition)
    actions: list[ChargeAction] = field(default_factory=list)
    priority: int = 0
    enabled: bool = True
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "conditions": self.conditions.to_dict(),
            "actions": [action.to_dict() for action in self.actions],
            "priority": self.priority,
            "enabled": self.enabled,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> ChargeTemplate:
        data = data or {}
        return cls(
            id=str(data.get("id", "") or ""),
            name=str(data.get("name", "") or ""),
            conditions=ChargeCondition.from_dict(data.get("conditions")),
            actions=[ChargeAction.from_dict(action) for action in data.get("actions", [])],
            priority=int(data.get("priority", 0) or 0),
            enabled=bool(data.get("enabled", True)),
            notes=str(data.get("notes", "") or ""),
        )


def templates_from_rules(rules: dict[str, Any] | None) -> list[ChargeTemplate]:
    """Read ``charge_rules.templates`` (or a top-level list) as ChargeTemplate."""
    rules = rules or {}
    raw = rules.get("templates")
    if raw is None:
        raw = rules.get("charge_templates")
    if not raw:
        return []
    templates = [ChargeTemplate.from_dict(item) for item in raw]
    return [item for item in templates if item.id or item.actions]


def sort_templates(templates: list[ChargeTemplate]) -> list[ChargeTemplate]:
    """Deterministic order: enabled first, then priority desc, then id asc."""
    return sorted(
        templates,
        key=lambda item: (not item.enabled, -item.priority, item.id),
    )


@dataclass
class Deck:
    """One interval along the hole: explosive, stemming, air, water, or inert."""

    kind: str  # see DECK_KINDS; unknown values are kept for old designs
    from_m: float
    to_m: float
    explosive_key: str = ""
    mass_kg: float = 0.0
    product: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "from_m": self.from_m,
            "to_m": self.to_m,
            "explosive_key": self.explosive_key,
            "mass_kg": self.mass_kg,
            "product": self.product,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Deck:
        return cls(
            kind=str(data.get("kind", "charge")),
            from_m=float(data.get("from_m", 0.0)),
            to_m=float(data.get("to_m", 0.0)),
            explosive_key=str(data.get("explosive_key", "")),
            mass_kg=float(data.get("mass_kg", 0.0)),
            product=str(data.get("product", "") or ""),
        )


@dataclass
class HoleLoad:
    """Заряжание одной скважины: набор дек и агрегаты."""

    hole_id: str
    decks: list[Deck] = field(default_factory=list)
    total_charge_kg: float = 0.0
    influence_volume_m3: float = 0.0
    specific_q_kg_m3: float = 0.0
    primers: list[float] = field(default_factory=list)  # depths from collar, m
    primer_items: list[Primer] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        items = list(self.primer_items)
        if not items and self.primers:
            items = [Primer(position_m=depth) for depth in self.primers]
        depths = list(self.primers) if self.primers else [item.position_m for item in items]
        return {
            "hole_id": self.hole_id,
            "decks": [d.to_dict() for d in self.decks],
            "total_charge_kg": self.total_charge_kg,
            "influence_volume_m3": self.influence_volume_m3,
            "specific_q_kg_m3": self.specific_q_kg_m3,
            "primers": depths,
            "primer_items": [item.to_dict() for item in items],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> HoleLoad:
        depths, items = _parse_primers(data)
        return cls(
            hole_id=str(data.get("hole_id", "")),
            decks=[Deck.from_dict(d) for d in data.get("decks", [])],
            total_charge_kg=float(data.get("total_charge_kg", 0.0)),
            influence_volume_m3=float(data.get("influence_volume_m3", 0.0)),
            specific_q_kg_m3=float(data.get("specific_q_kg_m3", 0.0)),
            primers=depths,
            primer_items=items,
        )


DETONATOR_KINDS = ("electronic", "nonel", "detonating_cord")
SURFACE_CONNECTOR_KINDS = ("surface_nsi", "ds_relay", "electronic", "detonating_cord")
DOWNHOLE_CONNECTOR_KINDS = ("downhole_nsi", "electronic", "detonating_cord")
FIRING_LEVELS = ("hole", "deck", "primer")
ELECTRONIC_TIMING_MODES = (
    "row",
    "selection",
    "direction",
    "gradient",
    "v_pattern",
    "diagonal",
    "expression",
)
TIMING_LEVELS = FIRING_LEVELS


def _opt_int(data: dict[str, Any], key: str) -> int | None:
    raw = data.get(key)
    if raw is None or raw == "":
        return None
    return int(raw)


def _normalize_choice(value: Any, allowed: tuple[str, ...], default: str) -> str:
    text = str(value or default).strip()
    return text if text in allowed else default


@dataclass
class Connector:
    """Legacy surface/downhole link. Kept so old passports still load."""

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
class Detonator:
    """In-hole initiator assigned to a hole, deck, or primer."""

    id: str
    hole_id: str
    delay_ms: float = 0.0
    product: str = ""
    kind: str = "electronic"
    deck_index: int | None = None
    primer_index: int | None = None
    channel_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "hole_id": self.hole_id,
            "delay_ms": self.delay_ms,
            "product": self.product,
            "kind": _normalize_choice(self.kind, DETONATOR_KINDS, "electronic"),
            "deck_index": self.deck_index,
            "primer_index": self.primer_index,
            "channel_id": self.channel_id,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> Detonator:
        data = data or {}
        return cls(
            id=str(data.get("id", "") or ""),
            hole_id=str(data.get("hole_id", "") or ""),
            delay_ms=float(data.get("delay_ms", 0.0) or 0.0),
            product=str(data.get("product", "") or ""),
            kind=_normalize_choice(data.get("kind"), DETONATOR_KINDS, "electronic"),
            deck_index=_opt_int(data, "deck_index"),
            primer_index=_opt_int(data, "primer_index"),
            channel_id=str(data.get("channel_id", "") or ""),
        )


@dataclass
class SurfaceConnector:
    """Editable surface delay between two holes."""

    id: str
    from_hole: str
    to_hole: str
    delay_ms: float = 0.0
    kind: str = "surface_nsi"
    product: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "from_hole": self.from_hole,
            "to_hole": self.to_hole,
            "delay_ms": self.delay_ms,
            "kind": _normalize_choice(self.kind, SURFACE_CONNECTOR_KINDS, "surface_nsi"),
            "product": self.product,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> SurfaceConnector:
        data = data or {}
        return cls(
            id=str(data.get("id", "") or ""),
            from_hole=str(data.get("from_hole", "") or ""),
            to_hole=str(data.get("to_hole", "") or ""),
            delay_ms=float(data.get("delay_ms", 0.0) or 0.0),
            kind=_normalize_choice(data.get("kind"), SURFACE_CONNECTOR_KINDS, "surface_nsi"),
            product=str(data.get("product", "") or ""),
        )


@dataclass
class DownholeConnector:
    """Downhole delay from surface arrival to a hole, deck, or primer."""

    id: str
    hole_id: str
    delay_ms: float = 0.0
    kind: str = "downhole_nsi"
    deck_index: int | None = None
    primer_index: int | None = None
    product: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "hole_id": self.hole_id,
            "delay_ms": self.delay_ms,
            "kind": _normalize_choice(self.kind, DOWNHOLE_CONNECTOR_KINDS, "downhole_nsi"),
            "deck_index": self.deck_index,
            "primer_index": self.primer_index,
            "product": self.product,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> DownholeConnector:
        data = data or {}
        return cls(
            id=str(data.get("id", "") or ""),
            hole_id=str(data.get("hole_id", "") or ""),
            delay_ms=float(data.get("delay_ms", 0.0) or 0.0),
            kind=_normalize_choice(data.get("kind"), DOWNHOLE_CONNECTOR_KINDS, "downhole_nsi"),
            deck_index=_opt_int(data, "deck_index"),
            primer_index=_opt_int(data, "primer_index"),
            product=str(data.get("product", "") or ""),
        )


@dataclass
class DetonatingCord:
    """Detonating-cord run along an ordered list of holes."""

    id: str
    hole_ids: list[str] = field(default_factory=list)
    velocity_m_s: float = 7000.0
    relay_delay_ms: float = 0.0
    product: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "hole_ids": list(self.hole_ids),
            "velocity_m_s": self.velocity_m_s,
            "relay_delay_ms": self.relay_delay_ms,
            "product": self.product,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> DetonatingCord:
        data = data or {}
        return cls(
            id=str(data.get("id", "") or ""),
            hole_ids=[str(item) for item in data.get("hole_ids", []) if str(item)],
            velocity_m_s=float(data.get("velocity_m_s", 7000.0) or 7000.0),
            relay_delay_ms=float(data.get("relay_delay_ms", 0.0) or 0.0),
            product=str(data.get("product", "") or ""),
        )


@dataclass
class Starter:
    """Network start point: a hole that receives the first signal."""

    id: str
    hole_id: str
    delay_ms: float = 0.0
    kind: str = "starter"

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "hole_id": self.hole_id,
            "delay_ms": self.delay_ms,
            "kind": self.kind or "starter",
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> Starter:
        data = data or {}
        return cls(
            id=str(data.get("id", "") or ""),
            hole_id=str(data.get("hole_id", data.get("id", "")) or ""),
            delay_ms=float(data.get("delay_ms", 0.0) or 0.0),
            kind=str(data.get("kind", "starter") or "starter"),
        )


@dataclass
class ElectronicChannel:
    """Programmed electronic-detonator channel (absolute time)."""

    id: str
    hole_id: str
    time_ms: float = 0.0
    deck_index: int | None = None
    primer_index: int | None = None
    label: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "hole_id": self.hole_id,
            "time_ms": self.time_ms,
            "deck_index": self.deck_index,
            "primer_index": self.primer_index,
            "label": self.label,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> ElectronicChannel:
        data = data or {}
        return cls(
            id=str(data.get("id", "") or ""),
            hole_id=str(data.get("hole_id", "") or ""),
            time_ms=float(data.get("time_ms", 0.0) or 0.0),
            deck_index=_opt_int(data, "deck_index"),
            primer_index=_opt_int(data, "primer_index"),
            label=str(data.get("label", "") or ""),
        )


@dataclass
class FiringEvent:
    """Resolved fire of a hole, deck, or primer at an absolute time."""

    id: str
    hole_id: str
    time_ms: float
    level: str = "hole"
    deck_index: int | None = None
    primer_index: int | None = None
    mass_kg: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "hole_id": self.hole_id,
            "time_ms": self.time_ms,
            "level": _normalize_choice(self.level, FIRING_LEVELS, "hole"),
            "deck_index": self.deck_index,
            "primer_index": self.primer_index,
            "mass_kg": self.mass_kg,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> FiringEvent:
        data = data or {}
        return cls(
            id=str(data.get("id", "") or ""),
            hole_id=str(data.get("hole_id", "") or ""),
            time_ms=float(data.get("time_ms", 0.0) or 0.0),
            level=_normalize_choice(data.get("level"), FIRING_LEVELS, "hole"),
            deck_index=_opt_int(data, "deck_index"),
            primer_index=_opt_int(data, "primer_index"),
            mass_kg=float(data.get("mass_kg", 0.0) or 0.0),
        )


def _legacy_surface_id(from_hole: str, to_hole: str) -> str:
    return f"sc-{from_hole}-{to_hole}"


@dataclass
class InitiationNetwork:
    """Initiation network 2.0. Legacy fields stay so old designs load."""

    system: str = "nonel"  # nonel | electronic | detcord
    starters: list[str] = field(default_factory=list)
    connectors: list[Connector] = field(default_factory=list)
    downhole_delay_ms: dict[str, float] = field(default_factory=dict)
    electronic_times_ms: dict[str, float] = field(default_factory=dict)
    detonators: list[Detonator] = field(default_factory=list)
    surface_connectors: list[SurfaceConnector] = field(default_factory=list)
    downhole_connectors: list[DownholeConnector] = field(default_factory=list)
    detonating_cords: list[DetonatingCord] = field(default_factory=list)
    starter_items: list[Starter] = field(default_factory=list)
    electronic_channels: list[ElectronicChannel] = field(default_factory=list)
    firing_events: list[FiringEvent] = field(default_factory=list)
    timing_mode: str = ""
    timing_expression: str = ""
    timing_params: dict[str, Any] = field(default_factory=dict)
    selected_hole_ids: list[str] = field(default_factory=list)

    def hydrate_from_legacy(self) -> None:
        """Fill 2.0 objects from first-generation fields when they are empty."""
        if not self.starter_items and self.starters:
            self.starter_items = [
                Starter(id=f"st-{hole_id}", hole_id=hole_id) for hole_id in self.starters
            ]
        if not self.surface_connectors and self.connectors:
            self.surface_connectors = [
                SurfaceConnector(
                    id=_legacy_surface_id(item.from_hole, item.to_hole) or f"sc-{index}",
                    from_hole=item.from_hole,
                    to_hole=item.to_hole,
                    delay_ms=item.delay_ms,
                    kind=item.kind if item.kind in SURFACE_CONNECTOR_KINDS else "surface_nsi",
                )
                for index, item in enumerate(self.connectors)
            ]
        if not self.downhole_connectors and self.downhole_delay_ms:
            self.downhole_connectors = [
                DownholeConnector(id=f"dh-{hole_id}", hole_id=hole_id, delay_ms=delay)
                for hole_id, delay in self.downhole_delay_ms.items()
            ]
        if not self.electronic_channels and self.electronic_times_ms:
            self.electronic_channels = [
                ElectronicChannel(id=f"ch-{hole_id}", hole_id=hole_id, time_ms=time_ms)
                for hole_id, time_ms in self.electronic_times_ms.items()
            ]
        if not self.detonators:
            kind = "electronic" if self.system == "electronic" else "nonel"
            if self.electronic_channels:
                self.detonators = [
                    Detonator(
                        id=f"det-{channel.hole_id}",
                        hole_id=channel.hole_id,
                        delay_ms=0.0,
                        kind="electronic",
                        deck_index=channel.deck_index,
                        primer_index=channel.primer_index,
                        channel_id=channel.id,
                    )
                    for channel in self.electronic_channels
                    if channel.hole_id
                ]
            elif self.downhole_connectors:
                self.detonators = [
                    Detonator(
                        id=f"det-{item.hole_id}",
                        hole_id=item.hole_id,
                        delay_ms=item.delay_ms,
                        kind=kind,
                        deck_index=item.deck_index,
                        primer_index=item.primer_index,
                    )
                    for item in self.downhole_connectors
                    if item.hole_id
                ]

    def sync_legacy_from_v2(self) -> None:
        """Keep first-generation fields in sync so old readers still work."""
        if self.starter_items:
            self.starters = [item.hole_id for item in self.starter_items if item.hole_id]
        if self.surface_connectors:
            self.connectors = [
                Connector(
                    from_hole=item.from_hole,
                    to_hole=item.to_hole,
                    delay_ms=item.delay_ms,
                    kind=item.kind,
                )
                for item in self.surface_connectors
            ]
        hole_downhole = {
            item.hole_id: item.delay_ms
            for item in self.downhole_connectors
            if item.hole_id and item.deck_index is None and item.primer_index is None
        }
        if hole_downhole:
            self.downhole_delay_ms = hole_downhole
        hole_channels = {
            item.hole_id: item.time_ms
            for item in self.electronic_channels
            if item.hole_id and item.deck_index is None and item.primer_index is None
        }
        if hole_channels:
            self.electronic_times_ms = hole_channels

    def to_dict(self) -> dict[str, Any]:
        self.sync_legacy_from_v2()
        return {
            "system": self.system,
            "starters": list(self.starters),
            "connectors": [c.to_dict() for c in self.connectors],
            "downhole_delay_ms": dict(self.downhole_delay_ms),
            "electronic_times_ms": dict(self.electronic_times_ms),
            "detonators": [item.to_dict() for item in self.detonators],
            "surface_connectors": [item.to_dict() for item in self.surface_connectors],
            "downhole_connectors": [item.to_dict() for item in self.downhole_connectors],
            "detonating_cords": [item.to_dict() for item in self.detonating_cords],
            "starter_items": [item.to_dict() for item in self.starter_items],
            "electronic_channels": [item.to_dict() for item in self.electronic_channels],
            "firing_events": [item.to_dict() for item in self.firing_events],
            "timing_mode": self.timing_mode,
            "timing_expression": self.timing_expression,
            "timing_params": dict(self.timing_params),
            "selected_hole_ids": list(self.selected_hole_ids),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> InitiationNetwork:
        data = data or {}
        network = cls(
            system=str(data.get("system", "nonel")),
            starters=[str(s) for s in data.get("starters", [])],
            connectors=[Connector.from_dict(c) for c in data.get("connectors", [])],
            downhole_delay_ms={
                str(k): float(v) for k, v in data.get("downhole_delay_ms", {}).items()
            },
            electronic_times_ms={
                str(k): float(v) for k, v in data.get("electronic_times_ms", {}).items()
            },
            detonators=[Detonator.from_dict(item) for item in data.get("detonators", [])],
            surface_connectors=[
                SurfaceConnector.from_dict(item) for item in data.get("surface_connectors", [])
            ],
            downhole_connectors=[
                DownholeConnector.from_dict(item) for item in data.get("downhole_connectors", [])
            ],
            detonating_cords=[
                DetonatingCord.from_dict(item) for item in data.get("detonating_cords", [])
            ],
            starter_items=[Starter.from_dict(item) for item in data.get("starter_items", [])],
            electronic_channels=[
                ElectronicChannel.from_dict(item) for item in data.get("electronic_channels", [])
            ],
            firing_events=[FiringEvent.from_dict(item) for item in data.get("firing_events", [])],
            timing_mode=str(data.get("timing_mode", "") or ""),
            timing_expression=str(data.get("timing_expression", "") or ""),
            timing_params=dict(data.get("timing_params", {}) or {}),
            selected_hole_ids=[str(item) for item in data.get("selected_hole_ids", [])],
        )
        has_v2 = any(
            [
                data.get("detonators"),
                data.get("surface_connectors"),
                data.get("downhole_connectors"),
                data.get("detonating_cords"),
                data.get("starter_items"),
                data.get("electronic_channels"),
            ]
        )
        if not has_v2:
            network.hydrate_from_legacy()
        else:
            network.sync_legacy_from_v2()
        return network


def _normalize_receptor_kind(value: Any, default: str = "building") -> str:
    kind = str(value or default).strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "здание": "building",
        "здание_жилое": "building",
        "труба": "pipeline",
        "трубопровод": "pipeline",
        "дробилка": "crusher",
        "борт": "highwall",
        "уступ": "highwall",
        "лэп": "power_line",
        "powerline": "power_line",
        "линия": "power_line",
        "сейсмопост": "monitoring_station",
        "monitor": "monitoring_station",
        "station": "monitoring_station",
    }
    if kind in RECEPTOR_KINDS:
        return kind
    return aliases.get(kind, default if default in RECEPTOR_KINDS else "building")


def _normalize_sd_convention(value: Any, default: str = DEFAULT_VIBRATION_CONVENTION) -> str:
    text = str(value or default).strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "cube": DEFAULT_VIBRATION_CONVENTION,
        "cube_root": DEFAULT_VIBRATION_CONVENTION,
        "q13_over_r": DEFAULT_VIBRATION_CONVENTION,
        "cis": DEFAULT_VIBRATION_CONVENTION,
        "r_over_q13": "r_over_q_cube",
        "square": "r_over_q_sqrt",
        "square_root": "r_over_q_sqrt",
        "usbm": "r_over_q_sqrt",
    }
    if text in SCALED_DISTANCE_CONVENTIONS:
        return text
    return aliases.get(text, default if default in SCALED_DISTANCE_CONVENTIONS else DEFAULT_VIBRATION_CONVENTION)


def _clamp_confidence(value: Any, default: float = 0.3) -> float:
    try:
        confidence = float(value)
    except (TypeError, ValueError):
        return default
    return max(0.0, min(1.0, confidence))


@dataclass
class Receptor:
    """Protected or monitored site object. Predicted PPV is not stored here."""

    id: str
    name: str = ""
    kind: str = "building"
    location: Point3 = field(default_factory=lambda: Point3(x=0.0, y=0.0, z=0.0))
    ppv_limit_mm_s: float | None = None
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "kind": _normalize_receptor_kind(self.kind),
            "location": self.location.to_dict(),
            "ppv_limit_mm_s": self.ppv_limit_mm_s,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> Receptor:
        data = data or {}
        loc = data.get("location") or {}
        if not loc and any(key in data for key in ("x", "y", "z")):
            loc = {"x": data.get("x", 0.0), "y": data.get("y", 0.0), "z": data.get("z", 0.0)}
        return cls(
            id=str(data.get("id", "") or ""),
            name=str(data.get("name", "") or ""),
            kind=_normalize_receptor_kind(data.get("kind")),
            location=Point3.from_dict(loc),
            ppv_limit_mm_s=_opt_float(data, "ppv_limit_mm_s"),
            notes=str(data.get("notes", "") or ""),
        )


@dataclass
class VibrationModel:
    """Explicit site law PPV = K × SD^n. SD convention is part of the identity."""

    id: str
    name: str = ""
    k: float = 200.0
    n: float = 1.6
    scaled_distance: str = DEFAULT_VIBRATION_CONVENTION
    calibration_source: str = ""
    confidence: float = 0.3
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "k": self.k,
            "n": self.n,
            "scaled_distance": _normalize_sd_convention(self.scaled_distance),
            "calibration_source": self.calibration_source,
            "confidence": _clamp_confidence(self.confidence),
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> VibrationModel:
        data = data or {}
        return cls(
            id=str(data.get("id", "") or ""),
            name=str(data.get("name", "") or ""),
            k=float(data.get("k", 200.0) or 200.0),
            n=float(data.get("n", 1.6) if data.get("n") is not None else 1.6),
            scaled_distance=_normalize_sd_convention(data.get("scaled_distance")),
            calibration_source=str(data.get("calibration_source", "") or ""),
            confidence=_clamp_confidence(data.get("confidence"), default=0.3),
            notes=str(data.get("notes", "") or ""),
        )


@dataclass
class VibrationMeasurement:
    """Measured PPV at a receptor. Never stored as a prediction."""

    id: str
    receptor_id: str
    ppv_mm_s: float
    role: str = ROLE_MEASURED
    distance_m: float | None = None
    mic_kg: float | None = None
    scaled_distance: str = ""
    source: str = ""
    method: str = ""
    timestamp: str = ""
    event_label: str = ""
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        convention = str(self.scaled_distance or "").strip()
        if convention:
            convention = _normalize_sd_convention(convention)
        return {
            "id": self.id,
            "receptor_id": self.receptor_id,
            "ppv_mm_s": self.ppv_mm_s,
            "role": ROLE_MEASURED,
            "distance_m": self.distance_m,
            "mic_kg": self.mic_kg,
            "scaled_distance": convention,
            "source": self.source,
            "method": self.method,
            "timestamp": self.timestamp,
            "event_label": self.event_label,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> VibrationMeasurement:
        data = data or {}
        convention = str(data.get("scaled_distance", "") or "").strip()
        if convention:
            convention = _normalize_sd_convention(convention)
        return cls(
            id=str(data.get("id", "") or ""),
            receptor_id=str(data.get("receptor_id", "") or ""),
            ppv_mm_s=float(data.get("ppv_mm_s", 0.0) or 0.0),
            role=ROLE_MEASURED,
            distance_m=_opt_float(data, "distance_m"),
            mic_kg=_opt_float(data, "mic_kg"),
            scaled_distance=convention,
            source=str(data.get("source", "") or ""),
            method=str(data.get("method", "") or ""),
            timestamp=str(data.get("timestamp", "") or ""),
            event_label=str(data.get("event_label", "") or ""),
            notes=str(data.get("notes", "") or ""),
        )


def default_vibration_model() -> VibrationModel:
    return VibrationModel(
        id="vm-site",
        name="Площадочный закон",
        k=200.0,
        n=1.6,
        scaled_distance=DEFAULT_VIBRATION_CONVENTION,
        calibration_source="ориентировочно",
        confidence=0.3,
        notes="PPV = K × SD^n. Коэффициенты ориентировочные, не норматив.",
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
    receptors: list[Receptor] = field(default_factory=list)
    vibration_models: list[VibrationModel] = field(default_factory=list)
    vibration_measurements: list[VibrationMeasurement] = field(default_factory=list)

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
            "receptors": [item.to_dict() for item in self.receptors],
            "vibration_models": [item.to_dict() for item in self.vibration_models],
            "vibration_measurements": [item.to_dict() for item in self.vibration_measurements],
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
            receptors=[Receptor.from_dict(item) for item in data.get("receptors", [])],
            vibration_models=[VibrationModel.from_dict(item) for item in data.get("vibration_models", [])],
            vibration_measurements=[
                VibrationMeasurement.from_dict(item) for item in data.get("vibration_measurements", [])
            ],
        )
