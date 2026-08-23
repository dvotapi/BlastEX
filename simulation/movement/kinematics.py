"""Empirical kinematic estimate of blast movement and heave.

This is not a validated continuum or discrete-element physics engine.
Coefficients are transparent and documented so the UI can call the result
an estimate. Lengths stay in metres; powder factor stays in kg/m³.
"""
from __future__ import annotations

import math
from design.geometry import collar_burden, point_to_segment_distance, polygon_centroid
from design.models import BlockContour, Hole
from simulation.movement.models import MovementInputs, PredictedHoleMovement, ModelProvenance
from simulation.movement.units import angle_deg_from_rad, length_m_from_mm

# Reference powder factor for a typical quarry production blast, kg/m³.
Q_REF_KG_M3 = 0.60
# Horizontal throw scale: at q=q_ref and B=4 m the front row is ~4.8 m.
K_THROW = 1.20
# Vertical heave scale: at q=q_ref a 10 m bench heaves ~1.1 m.
K_HEAVE = 0.11
# Blend of free-face direction vs timing-relief direction.
FACE_WEIGHT = 0.75
TIMING_WEIGHT = 0.25
SWELL_BASE = 1.20
SWELL_GAIN = 0.25

KINEMATIC_PARAMETERS = {
    "q_ref_kg_m3": Q_REF_KG_M3,
    "k_throw": K_THROW,
    "k_heave": K_HEAVE,
    "face_weight": FACE_WEIGHT,
    "timing_weight": TIMING_WEIGHT,
    "swell_base": SWELL_BASE,
    "swell_gain": SWELL_GAIN,
    "kind": "empirical_kinematic_estimate",
    "is_physics_simulation": False,
}


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _unit(dx: float, dy: float) -> tuple[float, float]:
    length = math.hypot(dx, dy)
    if length <= 1e-12:
        return (0.0, 0.0)
    return (dx / length, dy / length)


def outward_face_normals(contour: BlockContour) -> list[tuple[tuple[float, float], tuple[float, float], tuple[float, float]]]:
    """Each free-face segment as (start, end, outward unit normal)."""
    verts = contour.points_xy
    if len(verts) < 2:
        return []
    centroid = polygon_centroid(verts) if len(verts) >= 3 else (verts[0][0], verts[0][1])
    faces: list[tuple[tuple[float, float], tuple[float, float], tuple[float, float]]] = []
    edges = list(contour.free_faces) if contour.free_faces else []
    if not edges and len(verts) >= 2:
        edges = [[0, 1]]
    for edge in edges:
        for index in range(len(edge) - 1):
            ia, ib = edge[index], edge[index + 1]
            if not (0 <= ia < len(verts) and 0 <= ib < len(verts)):
                continue
            start, end = verts[ia], verts[ib]
            dx, dy = end[0] - start[0], end[1] - start[1]
            if math.hypot(dx, dy) <= 1e-12:
                continue
            mid = ((start[0] + end[0]) / 2.0, (start[1] + end[1]) / 2.0)
            n1 = _unit(-dy, dx)
            n2 = _unit(dy, -dx)
            to_centroid = (centroid[0] - mid[0], centroid[1] - mid[1])
            if n1[0] * to_centroid[0] + n1[1] * to_centroid[1] < 0:
                normal = n1
            else:
                normal = n2
            faces.append((start, end, normal))
    return faces


def mean_outward_normal(contour: BlockContour) -> tuple[float, float]:
    faces = outward_face_normals(contour)
    if not faces:
        return (1.0, 0.0)
    sx = sum(item[2][0] for item in faces)
    sy = sum(item[2][1] for item in faces)
    unit = _unit(sx, sy)
    if unit == (0.0, 0.0):
        return faces[0][2]
    return unit


def nearest_face_normal(x: float, y: float, contour: BlockContour) -> tuple[float, float, float]:
    """Return (nx, ny, distance_m) for the nearest free face."""
    faces = outward_face_normals(contour)
    if not faces:
        nx, ny = mean_outward_normal(contour)
        return nx, ny, 0.0
    best: tuple[float, float, float] | None = None
    for start, end, normal in faces:
        dist = point_to_segment_distance((x, y), start, end)
        if best is None or dist < best[2]:
            best = (normal[0], normal[1], dist)
    assert best is not None
    return best


def timing_relief_direction(
    hole: Hole,
    holes: list[Hole],
    times_ms: dict[str, float],
    neighbours: int = 5,
) -> tuple[float, float]:
    """Unit vector toward earlier-firing neighbours (created free face)."""
    own = times_ms.get(hole.id)
    if own is None:
        return (0.0, 0.0)
    scored: list[tuple[float, Hole]] = []
    for other in holes:
        if other.id == hole.id or not other.enabled:
            continue
        scored.append((math.hypot(other.collar.x - hole.collar.x, other.collar.y - hole.collar.y), other))
    scored.sort(key=lambda item: item[0])
    sx = 0.0
    sy = 0.0
    for distance_m, other in scored[:neighbours]:
        other_time = times_ms.get(other.id)
        if other_time is None or other_time >= own or distance_m <= 1e-9:
            continue
        weight = (own - other_time) / max(1.0, distance_m)
        sx += weight * (other.collar.x - hole.collar.x) / distance_m
        sy += weight * (other.collar.y - hole.collar.y) / distance_m
    return _unit(sx, sy)


def blend_direction(face: tuple[float, float], timing: tuple[float, float]) -> tuple[float, float]:
    dx = FACE_WEIGHT * face[0] + TIMING_WEIGHT * timing[0]
    dy = FACE_WEIGHT * face[1] + TIMING_WEIGHT * timing[1]
    unit = _unit(dx, dy)
    if unit == (0.0, 0.0):
        return face if face != (0.0, 0.0) else (1.0, 0.0)
    return unit


def powder_ratio(powder_factor_kg_m3: float) -> float:
    q = max(0.0, float(powder_factor_kg_m3))
    return _clamp(q / Q_REF_KG_M3 if Q_REF_KG_M3 else 0.0, 0.25, 2.50)


def face_confinement_factor(row: int, face_distance_m: float, burden_m: float) -> float:
    """Front-row holes throw more; back rows are more confined."""
    row_factor = 1.0 / (1.0 + 0.22 * max(0, int(row)))
    if burden_m <= 1e-9:
        return row_factor
    distance_factor = 1.0 / (1.0 + 0.08 * max(0.0, face_distance_m / burden_m - 1.0))
    return _clamp(row_factor * distance_factor, 0.35, 1.15)


def timing_relief_factor(fire_time_ms: float | None, times_ms: dict[str, float]) -> float:
    if fire_time_ms is None or not times_ms:
        return 1.0
    values = list(times_ms.values())
    lo, hi = min(values), max(values)
    if hi <= lo:
        return 1.0
    normalized = (float(fire_time_ms) - lo) / (hi - lo)
    return 1.0 + 0.18 * _clamp(normalized, 0.0, 1.0)


def stemming_factors(stemming_m: float, burden_m: float) -> tuple[float, float]:
    """(throw_factor, heave_factor). Longer stemming confines the column."""
    ratio = stemming_m / burden_m if burden_m > 1e-9 else 0.8
    throw_factor = 1.0 - 0.15 * _clamp(ratio - 0.70, -0.30, 0.60)
    heave_factor = 1.10 - 0.30 * _clamp(ratio, 0.40, 1.20)
    return throw_factor, heave_factor


def estimate_throw_m(inputs: MovementInputs, *, times_ms: dict[str, float] | None = None) -> float:
    ratio = powder_ratio(inputs.powder_factor_kg_m3)
    face = face_confinement_factor(inputs.row, inputs.face_distance_m, inputs.burden_m)
    timing = timing_relief_factor(inputs.fire_time_ms, times_ms or {})
    throw_stem, _ = stemming_factors(inputs.stemming_m, inputs.burden_m)
    burden = max(0.0, inputs.burden_m)
    throw_m = K_THROW * (ratio ** 0.75) * burden * face * timing * throw_stem
    return max(0.0, throw_m)


def estimate_heave_m(inputs: MovementInputs) -> float:
    ratio = powder_ratio(inputs.powder_factor_kg_m3)
    _, heave_stem = stemming_factors(inputs.stemming_m, inputs.burden_m)
    bench = max(0.0, inputs.bench_height_m)
    return max(0.0, K_HEAVE * (ratio ** 0.55) * bench * heave_stem)


def estimate_swell_factor(powder_factor_kg_m3: float) -> float:
    return SWELL_BASE + SWELL_GAIN * _clamp(powder_ratio(powder_factor_kg_m3), 0.50, 1.80)


def estimate_hole_movement(
    hole: Hole,
    inputs: MovementInputs,
    contour: BlockContour,
    holes: list[Hole],
    times_ms: dict[str, float],
) -> PredictedHoleMovement:
    nx, ny, _dist = nearest_face_normal(hole.collar.x, hole.collar.y, contour)
    timing = timing_relief_direction(hole, holes, times_ms)
    direction = blend_direction((nx, ny), timing)
    throw_m = estimate_throw_m(inputs, times_ms=times_ms)
    heave_m = estimate_heave_m(inputs)
    swell = estimate_swell_factor(inputs.powder_factor_kg_m3)
    dx = throw_m * direction[0]
    dy = throw_m * direction[1]
    dz = heave_m
    provenance = ModelProvenance(
        inputs=inputs.to_dict(),
        parameters=dict(KINEMATIC_PARAMETERS),
    )
    return PredictedHoleMovement(
        hole_id=hole.id,
        x=hole.collar.x,
        y=hole.collar.y,
        dx_m=round(dx, 3),
        dy_m=round(dy, 3),
        dz_m=round(dz, 3),
        throw_m=round(throw_m, 3),
        heave_m=round(heave_m, 3),
        direction_deg=round(angle_deg_from_rad(math.atan2(direction[0], direction[1])) % 360.0, 2),
        swell_factor=round(swell, 3),
        predicted_x=round(hole.collar.x + dx, 3),
        predicted_y=round(hole.collar.y + dy, 3),
        predicted_z=round(hole.collar.z + dz, 3),
        inputs=inputs,
        provenance=provenance,
    )


def designed_diameter_m(diameter_mm: float) -> float:
    """Hole diameter is stored in millimetres; kinematics use metres."""
    return length_m_from_mm(diameter_mm)


def designed_face_distance_m(hole: Hole, contour: BlockContour) -> float:
    measured = collar_burden(hole, contour)
    if measured is None:
        return 0.0
    return float(measured)


def envelope_from_points(points: list[tuple[float, float]]) -> list[dict[str, float]]:
    if not points:
        return []
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    return [
        {"x": min_x, "y": min_y},
        {"x": max_x, "y": min_y},
        {"x": max_x, "y": max_y},
        {"x": min_x, "y": max_y},
    ]


def along_across_extents(
    points: list[tuple[float, float]],
    face_normal: tuple[float, float],
) -> tuple[float, float]:
    """Return (length along face, width along throw) of a point set."""
    if not points:
        return 0.0, 0.0
    nx, ny = face_normal
    along = (-ny, nx)
    proj_along = [p[0] * along[0] + p[1] * along[1] for p in points]
    proj_across = [p[0] * nx + p[1] * ny for p in points]
    length_m = max(proj_along) - min(proj_along)
    width_m = max(proj_across) - min(proj_across)
    return max(0.0, length_m), max(0.0, width_m)
