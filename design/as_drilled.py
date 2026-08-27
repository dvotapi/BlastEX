"""As-drilled execution records (phase BDX-008).

Designed holes stay on ``BlastDesign.holes``. Executed geometry lives only on
``BlastDesign.as_drilled_holes``. Recording, comparing, or importing MWD never
mutates ``Hole`` fields.

MWD import is manufacturer-neutral: samples are physical quantities
(depth, penetration rate, pressures, torque). Vendor file formats are out of
scope — this module only stores the common schema.
"""
from __future__ import annotations

import math
from typing import Any

from design.editing import local_burden, local_spacing
from design.models import (
    ROLE_EXECUTED,
    AsDrilledHole,
    BlastDesign,
    DataProvenance,
    Hole,
    MwdSample,
    Point3,
    SurveyPoint,
)

MWD_FIELD_SCHEMA: tuple[dict[str, Any], ...] = (
    {
        "id": "depth_m",
        "aliases": ("depth", "depth_m", "hole_depth", "along_hole"),
        "unit": "m",
        "required": True,
        "description": "Along-hole depth from the actual collar",
    },
    {
        "id": "penetration_rate",
        "aliases": ("penetration_rate", "penetration_rate_m_min", "rop", "pr"),
        "unit": "m/min",
        "required": False,
        "description": "Instantaneous penetration rate",
    },
    {
        "id": "rotation_pressure",
        "aliases": ("rotation_pressure", "rotation_pressure_bar", "rotary_pressure"),
        "unit": "bar",
        "required": False,
        "description": "Rotation / rotary pressure",
    },
    {
        "id": "feed_pressure",
        "aliases": ("feed_pressure", "feed_pressure_bar", "pulldown"),
        "unit": "bar",
        "required": False,
        "description": "Feed / pulldown pressure",
    },
    {
        "id": "torque",
        "aliases": ("torque", "torque_n_m", "torque_nm"),
        "unit": "N·m",
        "required": False,
        "description": "Rotary torque",
    },
    {
        "id": "air_pressure",
        "aliases": ("air_pressure", "air_pressure_bar", "flushing_pressure"),
        "unit": "bar",
        "required": False,
        "description": "Flushing / air pressure",
    },
)

_MWD_ALIAS_TO_ID = {
    alias: field["id"]
    for field in MWD_FIELD_SCHEMA
    for alias in field["aliases"]
}

PATTERN_BASIS_EXECUTED = "executed"
PATTERN_BASIS_MIXED = "mixed"
PATTERN_BASIS_NONE = "none"


def _distance3(a: Point3, b: Point3) -> float:
    dx = a.x - b.x
    dy = a.y - b.y
    dz = a.z - b.z
    return math.sqrt(dx * dx + dy * dy + dz * dz)


def _signed_azimuth_delta(actual_deg: float, designed_deg: float) -> float:
    """Shortest signed difference in (-180, 180]."""
    return (actual_deg - designed_deg + 180.0) % 360.0 - 180.0


def _round_opt(value: float | None, places: int = 3) -> float | None:
    if value is None:
        return None
    return round(float(value), places)


def mwd_import_schema() -> dict[str, Any]:
    """Public, manufacturer-neutral MWD import contract."""
    return {
        "kind": "mwd",
        "role": ROLE_EXECUTED,
        "manufacturer": None,
        "vendor_format": None,
        "note": (
            "Physical quantities only. Map any drill-rig export onto these fields; "
            "do not store manufacturer-specific column names in the core."
        ),
        "fields": [
            {
                "id": field["id"],
                "aliases": list(field["aliases"]),
                "unit": field["unit"],
                "required": field["required"],
                "description": field["description"],
            }
            for field in MWD_FIELD_SCHEMA
        ],
    }


def parse_mwd_sample(row: dict[str, Any]) -> MwdSample:
    """Accept canonical ids or generic aliases. Extra vendor keys are ignored."""
    mapped: dict[str, Any] = {}
    for key, raw in (row or {}).items():
        field_id = _MWD_ALIAS_TO_ID.get(str(key).strip().lower())
        if field_id and field_id not in mapped:
            mapped[field_id] = raw
    return MwdSample.from_dict(mapped)


def parse_mwd_samples(rows: list[dict[str, Any]] | None) -> list[MwdSample]:
    samples = [parse_mwd_sample(row) for row in (rows or [])]
    return [item for item in samples if item.depth_m >= 0]


def normalize_as_drilled(item: AsDrilledHole) -> AsDrilledHole:
    """Fill derived executed geometry. Role is forced to executed."""
    collar = item.actual_collar
    toe = item.actual_toe
    depth = float(item.actual_depth or 0.0)
    points = sorted(item.survey_points, key=lambda point: point.depth_m)
    if points:
        last = points[-1]
        if last.has_xyz:
            toe = Point3(x=float(last.x), y=float(last.y), z=float(last.z))
        if depth <= 0 and last.depth_m > 0:
            depth = last.depth_m
    if depth <= 0:
        depth = _distance3(collar, toe)
    provenance = item.provenance
    provenance.role = ROLE_EXECUTED
    return AsDrilledHole(
        design_hole_id=item.design_hole_id,
        actual_collar=collar,
        actual_toe=toe,
        actual_depth=depth,
        actual_diameter=max(0.0, float(item.actual_diameter or 0.0)),
        survey_points=points,
        mwd_samples=list(item.mwd_samples),
        role=ROLE_EXECUTED,
        provenance=provenance,
    )


def as_drilled_from_design_hole(hole: Hole, *, source: str = "copied_from_design") -> AsDrilledHole:
    """Build an executed stub from designed geometry. The designed Hole is not changed."""
    return normalize_as_drilled(
        AsDrilledHole(
            design_hole_id=hole.id,
            actual_collar=Point3(x=hole.collar.x, y=hole.collar.y, z=hole.collar.z),
            actual_toe=Point3(x=hole.toe.x, y=hole.toe.y, z=hole.toe.z),
            actual_depth=hole.length_m,
            actual_diameter=hole.diameter_mm,
            provenance=DataProvenance(source=source, method="copy", role=ROLE_EXECUTED),
        )
    )


def _designed_snapshot(hole: Hole) -> dict[str, Any]:
    return {
        "id": hole.id,
        "collar": hole.collar.to_dict(),
        "toe": hole.toe.to_dict(),
        "diameter_mm": hole.diameter_mm,
        "subdrill_m": hole.subdrill_m,
        "kind": hole.kind,
        "row": hole.row,
        "col": hole.col,
        "enabled": hole.enabled,
    }


def record_as_drilled(design: BlastDesign, item: AsDrilledHole) -> AsDrilledHole:
    """Upsert one executed hole. Designed ``Hole`` fields stay untouched."""
    designed = next((hole for hole in design.holes if hole.id == item.design_hole_id), None)
    if designed is None:
        raise ValueError(f"Проектная скважина «{item.design_hole_id}» не найдена.")
    before = _designed_snapshot(designed)
    recorded = normalize_as_drilled(item)
    if not recorded.design_hole_id:
        raise ValueError("У фактической скважины нет связи с проектом (design_hole_id).")
    for index, existing in enumerate(design.as_drilled_holes):
        if existing.design_hole_id == recorded.design_hole_id:
            recorded.mwd_samples = recorded.mwd_samples or existing.mwd_samples
            if not recorded.survey_points:
                recorded.survey_points = existing.survey_points
            design.as_drilled_holes[index] = recorded
            after = _designed_snapshot(designed)
            if after != before:
                raise RuntimeError("Запись факта бурения не должна менять проектную скважину.")
            return recorded
    design.as_drilled_holes.append(recorded)
    after = _designed_snapshot(designed)
    if after != before:
        raise RuntimeError("Запись факта бурения не должна менять проектную скважину.")
    return recorded


def record_as_drilled_many(
    design: BlastDesign,
    items: list[AsDrilledHole],
    *,
    replace: bool = False,
) -> list[AsDrilledHole]:
    snapshots = {hole.id: _designed_snapshot(hole) for hole in design.holes}
    if replace:
        design.as_drilled_holes = []
    recorded: list[AsDrilledHole] = []
    for item in items:
        recorded.append(record_as_drilled(design, item))
    for hole in design.holes:
        if _designed_snapshot(hole) != snapshots[hole.id]:
            raise RuntimeError("Пакетная запись факта бурения не должна менять проектные скважины.")
    return recorded


def attach_mwd(
    design: BlastDesign,
    design_hole_id: str,
    samples: list[MwdSample],
    *,
    source: str = "",
) -> AsDrilledHole:
    """Attach MWD samples to an executed hole. Designed geometry is never used as MWD."""
    designed = next((hole for hole in design.holes if hole.id == design_hole_id), None)
    if designed is None:
        raise ValueError(f"Проектная скважина «{design_hole_id}» не найдена.")
    existing = next((item for item in design.as_drilled_holes if item.design_hole_id == design_hole_id), None)
    if existing is None:
        existing = as_drilled_from_design_hole(designed, source=source or "mwd_import")
    existing.mwd_samples = sorted(samples, key=lambda item: item.depth_m)
    if source:
        existing.provenance.source = source
        existing.provenance.method = "mwd"
    return record_as_drilled(design, existing)


def _proxy_hole(designed: Hole, collar: Point3, toe: Point3, diameter_mm: float) -> Hole:
    """Temporary hole used only to reuse burden/spacing helpers. Not stored."""
    return Hole(
        id=designed.id,
        row=designed.row,
        col=designed.col,
        collar=collar,
        toe=toe,
        diameter_mm=diameter_mm,
        subdrill_m=designed.subdrill_m,
        kind=designed.kind,
        source=designed.source,
        enabled=designed.enabled,
    )


def _pattern_positions(design: BlastDesign, *, executed: bool) -> list[Hole]:
    as_drilled = {item.design_hole_id: item for item in design.as_drilled_holes}
    proxies: list[Hole] = []
    for hole in design.holes:
        if not hole.enabled:
            continue
        if executed:
            item = as_drilled.get(hole.id)
            if item is None:
                continue
            proxies.append(_proxy_hole(hole, item.actual_collar, item.actual_toe, item.actual_diameter))
        else:
            proxies.append(hole)
    return proxies


def _mixed_pattern_holes(design: BlastDesign) -> tuple[list[Hole], str]:
    """Actual collar when recorded, otherwise designed collar. Basis is reported."""
    as_drilled = {item.design_hole_id: item for item in design.as_drilled_holes}
    proxies: list[Hole] = []
    used_executed = 0
    used_designed = 0
    for hole in design.holes:
        if not hole.enabled:
            continue
        item = as_drilled.get(hole.id)
        if item is not None:
            proxies.append(_proxy_hole(hole, item.actual_collar, item.actual_toe, item.actual_diameter))
            used_executed += 1
        else:
            proxies.append(hole)
            used_designed += 1
    if used_executed == 0:
        basis = PATTERN_BASIS_NONE
    elif used_designed == 0:
        basis = PATTERN_BASIS_EXECUTED
    else:
        basis = PATTERN_BASIS_MIXED
    return proxies, basis


def compare_hole(designed: Hole, executed: AsDrilledHole, mixed: list[Hole], designed_set: list[Hole], contour) -> dict[str, Any]:
    actual = normalize_as_drilled(executed)
    designed_burden = local_burden(designed_set, designed, contour)
    designed_spacing = local_spacing(designed_set, designed)
    proxy = next((item for item in mixed if item.id == designed.id), None)
    actual_burden = local_burden(mixed, proxy, contour) if proxy is not None else None
    actual_spacing = local_spacing(mixed, proxy) if proxy is not None else None
    horizontal_actual = math.hypot(
        actual.actual_toe.x - actual.actual_collar.x,
        actual.actual_toe.y - actual.actual_collar.y,
    )
    horizontal_designed = math.hypot(designed.toe.x - designed.collar.x, designed.toe.y - designed.collar.y)
    azimuth_dev = 0.0
    if horizontal_actual > 1e-9 and horizontal_designed > 1e-9:
        azimuth_dev = _signed_azimuth_delta(actual.azimuth_deg, designed.azimuth_deg)
    return {
        "design_hole_id": designed.id,
        "role": ROLE_EXECUTED,
        "collar_offset_m": round(_distance3(actual.actual_collar, designed.collar), 3),
        "toe_offset_m": round(_distance3(actual.actual_toe, designed.toe), 3),
        "depth_deviation_m": round(actual.length_m - designed.length_m, 3),
        "angle_deviation_deg": round(actual.angle_deg - designed.angle_deg, 3),
        "azimuth_deviation_deg": round(azimuth_dev, 3),
        "actual_burden_m": _round_opt(actual_burden),
        "actual_spacing_m": _round_opt(actual_spacing),
        "designed_burden_m": _round_opt(designed_burden),
        "designed_spacing_m": _round_opt(designed_spacing),
        "actual_depth_m": round(actual.length_m, 3),
        "designed_depth_m": round(designed.length_m, 3),
        "actual_diameter_mm": round(actual.actual_diameter, 2),
        "designed_diameter_mm": round(designed.diameter_mm, 2),
    }


def compare_design(design: BlastDesign) -> dict[str, Any]:
    """Compare executed records with designed holes. Designed holes are read-only."""
    designed_by_id = {hole.id: hole for hole in design.holes}
    designed_set = [hole for hole in design.holes if hole.enabled]
    mixed, basis = _mixed_pattern_holes(design)
    deviations: list[dict[str, Any]] = []
    warnings: list[str] = []
    snapshots = {hole.id: _designed_snapshot(hole) for hole in design.holes}

    for item in design.as_drilled_holes:
        designed = designed_by_id.get(item.design_hole_id)
        if designed is None:
            warnings.append(f"Фактическая скважина ссылается на отсутствующий проект «{item.design_hole_id}».")
            continue
        deviations.append(compare_hole(designed, item, mixed, designed_set, design.contour))

    missing = [
        hole.id
        for hole in designed_set
        if hole.id not in {item.design_hole_id for item in design.as_drilled_holes}
    ]
    if missing:
        preview = ", ".join(missing[:8])
        extra = f" и ещё {len(missing) - 8}" if len(missing) > 8 else ""
        warnings.append(f"Нет факта бурения для скважин: {preview}{extra}.")
    if basis == PATTERN_BASIS_MIXED:
        warnings.append(
            "Фактические ЛНС и шаг считаются по смешанной сетке: "
            "есть факт — берём его устье, нет факта — проектное."
        )
    if basis == PATTERN_BASIS_NONE and design.as_drilled_holes:
        warnings.append("Фактическая сетка пуста — ЛНС и шаг по факту не посчитаны.")

    for hole in design.holes:
        if _designed_snapshot(hole) != snapshots[hole.id]:
            raise RuntimeError("Сравнение факта с проектом не должно менять проектные скважины.")

    return {
        "role": ROLE_EXECUTED,
        "compared_count": len(deviations),
        "designed_count": len(designed_set),
        "as_drilled_count": len(design.as_drilled_holes),
        "pattern_basis": basis,
        "deviations": deviations,
        "warnings": warnings,
        "as_drilled_holes": [item.to_dict() for item in design.as_drilled_holes],
    }
