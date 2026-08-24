"""Geological domains and hole-axis intercepts (phase BDX-002).

Designed geology lives on `BlastDesign.domains` and `Hole.intervals`.
Measured records stay on `Hole.measured_*` and are never overwritten here.
Charging (BDX-004) consumes `designed_rock_intervals` and water intervals.
"""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from typing import Callable, TypeVar

from design.geometry import point_in_polygon
from design.models import (
    BlastDesign,
    BlastDomain,
    DataProvenance,
    Hole,
    HoleInterval,
    Point3,
    RockPropertySet,
    WaterInterval,
)

_EPS = 1e-9
_LENGTH_EPS = 1e-6

T = TypeVar("T")


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def assign_domain_polygon(domain: BlastDomain, polygon: list[Point3]) -> BlastDomain:
    """Attach a plan region to a designed domain. Empty polygon = whole plan."""
    if 0 < len(polygon) < 3:
        raise ValueError("Полигон домена должен быть пустым (весь план) или содержать не менее трёх вершин.")
    return replace(domain, polygon=list(polygon))


def point_along_hole(hole: Hole, along_m: float) -> Point3:
    """Point on the hole axis, metres from collar."""
    length = hole.length_m
    if length <= _EPS:
        return Point3(x=hole.collar.x, y=hole.collar.y, z=hole.collar.z)
    t = max(0.0, min(1.0, along_m / length))
    return Point3(
        x=hole.collar.x + t * (hole.toe.x - hole.collar.x),
        y=hole.collar.y + t * (hole.toe.y - hole.collar.y),
        z=hole.collar.z + t * (hole.toe.z - hole.collar.z),
    )


def designed_rock_intervals(hole: Hole) -> list[HoleInterval]:
    """Designed geology along the hole. Charging/simulation engines consume this later."""
    return [iv for iv in hole.intervals if iv.role == "designed"]


def designed_water_intervals(hole: Hole) -> list[WaterInterval]:
    return [iv for iv in hole.water_intervals if iv.role == "designed"]


def properties_at(hole: Hole, along_m: float) -> RockPropertySet | None:
    """Designed rock properties covering a depth along the hole. Measured data is ignored."""
    for interval in designed_rock_intervals(hole):
        if interval.from_m - _EPS <= along_m <= interval.to_m + _EPS:
            return interval.properties
    return None


def _segment_intersection_t(
    p0: tuple[float, float],
    p1: tuple[float, float],
    a: tuple[float, float],
    b: tuple[float, float],
) -> float | None:
    """Parameter t in (0, 1) along p0→p1 where it crosses segment a→b."""
    dx, dy = p1[0] - p0[0], p1[1] - p0[1]
    ex, ey = b[0] - a[0], b[1] - a[1]
    denom = dx * ey - dy * ex
    if abs(denom) < 1e-12:
        return None
    t = ((a[0] - p0[0]) * ey - (a[1] - p0[1]) * ex) / denom
    u = ((a[0] - p0[0]) * dy - (a[1] - p0[1]) * dx) / denom
    if _EPS < t < 1.0 - _EPS and -_EPS <= u <= 1.0 + _EPS:
        return t
    return None


def _xy_cut_parameters(hole: Hole, polygon: list[tuple[float, float]]) -> list[float]:
    p0 = (hole.collar.x, hole.collar.y)
    p1 = (hole.toe.x, hole.toe.y)
    cuts: list[float] = []
    for i, a in enumerate(polygon):
        b = polygon[(i + 1) % len(polygon)]
        t = _segment_intersection_t(p0, p1, a, b)
        if t is not None:
            cuts.append(t)
    return cuts


def _plane_cut_along_m(hole: Hole, z_plane: float) -> float | None:
    dz = hole.toe.z - hole.collar.z
    if abs(dz) < 1e-12:
        return None
    t = (z_plane - hole.collar.z) / dz
    if _EPS < t < 1.0 - _EPS:
        return t * hole.length_m
    return None


def _domain_contains(domain: BlastDomain, point: Point3) -> bool:
    poly = domain.points_xy
    if len(poly) >= 3:
        if not point_in_polygon((point.x, point.y), poly):
            return False
    elif poly:
        return False
    z_top, z_bottom = domain.elevation_bounds()
    if z_top is not None and point.z > z_top + _EPS:
        return False
    if z_bottom is not None and point.z < z_bottom - _EPS:
        return False
    return True


def domain_at(domains: list[BlastDomain], point: Point3) -> BlastDomain | None:
    """Highest-priority designed domain covering a point. Empty polygon = whole plan."""
    return _pick_domain(domains, point)


def _pick_domain(domains: list[BlastDomain], point: Point3) -> BlastDomain | None:
    best: BlastDomain | None = None
    best_index = -1
    for index, domain in enumerate(domains):
        if not _domain_contains(domain, point):
            continue
        if (
            best is None
            or domain.priority > best.priority
            or (domain.priority == best.priority and index > best_index)
        ):
            best = domain
            best_index = index
    return best


def _merge_adjacent(items: list[T], same: Callable[[T, T], bool], join: Callable[[T, T], T]) -> list[T]:
    if not items:
        return []
    merged = [items[0]]
    for item in items[1:]:
        prev = merged[-1]
        if same(prev, item):
            merged[-1] = join(prev, item)
        else:
            merged.append(item)
    return merged


def _interval_provenance(domain: BlastDomain, timestamp: str) -> DataProvenance:
    source = domain.provenance.source or "design"
    return DataProvenance(
        source=source,
        method="domain_intercept",
        timestamp=timestamp,
        role="designed",
    )


def intercept_hole(
    hole: Hole,
    domains: list[BlastDomain],
    *,
    water_table_z_m: float | None = None,
    timestamp: str | None = None,
) -> tuple[list[HoleInterval], list[WaterInterval]]:
    """Intersect the hole axis with designed domains.

    Returns designed rock and water intervals. Measured lists on `hole` are ignored.
    """
    length = hole.length_m
    if length <= _LENGTH_EPS:
        return [], []

    stamp = timestamp or _utc_now_iso()
    cuts: set[float] = {0.0, length}
    for domain in domains:
        poly = domain.points_xy
        if len(poly) >= 3:
            for t in _xy_cut_parameters(hole, poly):
                cuts.add(t * length)
        z_top, z_bottom = domain.elevation_bounds()
        for z_plane in (z_top, z_bottom):
            if z_plane is None:
                continue
            along = _plane_cut_along_m(hole, z_plane)
            if along is not None:
                cuts.add(along)
    if water_table_z_m is not None:
        along = _plane_cut_along_m(hole, water_table_z_m)
        if along is not None:
            cuts.add(along)

    ordered = sorted(max(0.0, min(length, value)) for value in cuts)
    unique: list[float] = []
    for value in ordered:
        if not unique or abs(value - unique[-1]) > _LENGTH_EPS:
            unique.append(value)

    rock: list[HoleInterval] = []
    domain_water: list[WaterInterval] = []
    for start, end in zip(unique, unique[1:]):
        if end - start <= _LENGTH_EPS:
            continue
        mid = point_along_hole(hole, 0.5 * (start + end))
        domain = _pick_domain(domains, mid)
        if domain is None:
            continue
        props = RockPropertySet.from_dict(domain.properties.to_dict())
        rock.append(
            HoleInterval(
                from_m=start,
                to_m=end,
                domain_id=domain.id,
                domain_name=domain.name,
                properties=props,
                provenance=_interval_provenance(domain, stamp),
                role="designed",
            )
        )
        if props.water_condition:
            domain_water.append(
                WaterInterval(
                    from_m=start,
                    to_m=end,
                    condition=props.water_condition,
                    provenance=_interval_provenance(domain, stamp),
                    role="designed",
                    notes=f"from domain {domain.id}",
                )
            )

    rock = _merge_adjacent(
        rock,
        same=lambda a, b: a.domain_id == b.domain_id and abs(a.to_m - b.from_m) <= _LENGTH_EPS,
        join=lambda a, b: replace(a, to_m=b.to_m),
    )

    table_water: list[WaterInterval] = []
    if water_table_z_m is not None:
        for start, end in zip(unique, unique[1:]):
            if end - start <= _LENGTH_EPS:
                continue
            mid = point_along_hole(hole, 0.5 * (start + end))
            if mid.z <= water_table_z_m + _EPS:
                table_water.append(
                    WaterInterval(
                        from_m=start,
                        to_m=end,
                        condition="wet",
                        provenance=DataProvenance(
                            source="design",
                            method="water_table",
                            timestamp=stamp,
                            role="designed",
                        ),
                        role="designed",
                        notes="water table",
                    )
                )

    water = _overlay_water(domain_water, table_water)
    return rock, water


def _overlay_water(primary: list[WaterInterval], fallback: list[WaterInterval]) -> list[WaterInterval]:
    """Domain water wins where it overlaps; water-table fills the rest."""
    if not fallback:
        return _merge_water(primary)
    if not primary:
        return _merge_water(fallback)

    cuts = sorted({iv.from_m for iv in primary + fallback} | {iv.to_m for iv in primary + fallback})
    pieces: list[WaterInterval] = []
    for start, end in zip(cuts, cuts[1:]):
        if end - start <= _LENGTH_EPS:
            continue
        mid = 0.5 * (start + end)
        chosen = _covering_water(primary, mid) or _covering_water(fallback, mid)
        if chosen is None:
            continue
        pieces.append(replace(chosen, from_m=start, to_m=end))
    return _merge_water(pieces)


def _covering_water(intervals: list[WaterInterval], along_m: float) -> WaterInterval | None:
    for interval in intervals:
        if interval.from_m - _EPS <= along_m <= interval.to_m + _EPS:
            return interval
    return None


def _merge_water(intervals: list[WaterInterval]) -> list[WaterInterval]:
    ordered = sorted(intervals, key=lambda iv: iv.from_m)
    return _merge_adjacent(
        ordered,
        same=lambda a, b: a.condition == b.condition and abs(a.to_m - b.from_m) <= _LENGTH_EPS,
        join=lambda a, b: replace(a, to_m=b.to_m),
    )


def apply_domains_to_hole(
    hole: Hole,
    domains: list[BlastDomain],
    *,
    water_table_z_m: float | None = None,
    timestamp: str | None = None,
) -> Hole:
    """Replace designed intervals only. Measured geology is copied unchanged."""
    rock, water = intercept_hole(
        hole, domains, water_table_z_m=water_table_z_m, timestamp=timestamp
    )
    return replace(hole, intervals=rock, water_intervals=water)


def apply_domains_to_holes(
    holes: list[Hole],
    domains: list[BlastDomain],
    *,
    water_table_z_m: float | None = None,
    timestamp: str | None = None,
) -> list[Hole]:
    stamp = timestamp or _utc_now_iso()
    return [
        apply_domains_to_hole(hole, domains, water_table_z_m=water_table_z_m, timestamp=stamp)
        for hole in holes
    ]


def apply_domains_to_design(design: BlastDesign, *, timestamp: str | None = None) -> BlastDesign:
    """Recompute designed hole intercepts from design domains. Measured data stays."""
    stamp = timestamp or _utc_now_iso()
    holes = apply_domains_to_holes(
        design.holes,
        design.domains,
        water_table_z_m=design.water_table_z_m,
        timestamp=stamp,
    )
    return replace(design, holes=holes)
