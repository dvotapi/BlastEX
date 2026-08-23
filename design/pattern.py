"""Automatic blast-hole pattern generation inside a block contour."""
from __future__ import annotations

import math
from typing import Any

from design.geometry import (
    drape_collar,
    ensure_ccw,
    local_basis,
    offset_polygon,
    pattern_origin,
    point_in_polygon,
)
from design.geology import domain_at
from design.models import HOLE_KINDS, BlastDomain, BlockContour, Hole, Point3

PATTERN_TYPES = ("square", "rectangular", "staggered", "variable", "domain_dependent")
REGULAR_PATTERNS = ("square", "rectangular", "staggered")


def generate_pattern(
    contour: BlockContour,
    params: dict[str, Any],
    existing_holes: list[Hole] | None = None,
    surfaces: object | None = None,
    domains: list[BlastDomain] | None = None,
) -> list[Hole]:
    """Build a production blast pattern inside the block contour.

    params:
      pattern                 square | rectangular | staggered | variable | domain_dependent
      spacing_a_m             in-row spacing, m
      burden_b_m              inter-row burden, m (ignored for square — uses a)
      row_shift_ratio         odd-row shift as a fraction of a (staggered, default 0.5)
      row_azimuth_deg         row azimuth, deg (0 = north / +Y)
      offset_from_face_m      first-row offset from the free face when first_row_burden_m is unset
      first_row_burden_m      optional first-row burden (face → row 0); later rows use burden_b_m
      first_row_follow_face   place row 0 along an inward offset of the free faces
      edge_margin_m           inset from the contour, m
      diameter_mm / subdrill_m / angle_deg / azimuth_deg / depth_m
      default_kind            kind assigned to the main grid (default production)
      row_params              per-row overrides for variable: spacing_a_m, burden_b_m, shift_ratio, kind
      contour_row / presplit_row / trim_row / buffer_row / stab_row
      satellite_holes / infill_holes
    """
    pattern = str(params.get("pattern", "square"))
    if pattern not in PATTERN_TYPES:
        pattern = "square"

    spacing_a = float(params.get("spacing_a_m", 5.0))
    burden_b = spacing_a if pattern == "square" else float(params.get("burden_b_m", spacing_a))
    row_shift_ratio = float(params.get("row_shift_ratio", 0.5)) if pattern == "staggered" else 0.0
    row_azimuth_deg = float(params.get("row_azimuth_deg", 0.0))
    first_row_burden = params.get("first_row_burden_m")
    first_row_burden = float(first_row_burden) if first_row_burden not in (None, "") else None
    offset_from_face = (
        first_row_burden
        if first_row_burden is not None
        else float(params.get("offset_from_face_m", burden_b / 2))
    )
    follow_face = bool(params.get("first_row_follow_face", False))
    edge_margin = float(params.get("edge_margin_m", 0.0))
    diameter_mm = float(params.get("diameter_mm", 152.0))
    subdrill_m = float(params.get("subdrill_m", 1.0))
    angle_deg = float(params.get("angle_deg", 0.0))
    azimuth_deg = float(params.get("azimuth_deg", row_azimuth_deg))
    depth_override = params.get("depth_m")
    depth_override = float(depth_override) if depth_override is not None else None
    default_kind = _normalize_kind(params.get("default_kind", "production"), "production")
    domain_list = list(domains or [])

    verts = ensure_ccw(contour.points_xy)
    if len(verts) < 3 or spacing_a <= 0 or burden_b <= 0:
        return _keep_manual(existing_holes)

    boundary = offset_polygon(verts, edge_margin) if edge_margin > 0 else verts
    row_dir, advance_dir = local_basis(row_azimuth_deg)
    origin, advance_dir = pattern_origin(contour, row_dir, advance_dir)

    us = [(vx - origin[0]) * row_dir[0] + (vy - origin[1]) * row_dir[1] for vx, vy in verts]
    vs = [
        (vx - origin[0]) * advance_dir[0] + (vy - origin[1]) * advance_dir[1] for vx, vy in verts
    ]
    u_min, u_max = min(us) - spacing_a, max(us) + spacing_a
    v_max = max(vs) + burden_b
    crest_z = contour.bench.crest_z_m

    holes: list[Hole] = []
    row_index = 0
    skip_regular_first = False

    if follow_face and contour.free_faces:
        face_row = _generate_face_following_row(
            contour,
            params,
            boundary,
            origin,
            row_dir,
            advance_dir,
            offset_from_face,
            spacing_a,
            diameter_mm,
            subdrill_m,
            angle_deg,
            azimuth_deg,
            depth_override,
            default_kind,
            surfaces,
        )
        if face_row:
            holes.extend(face_row)
            row_index = 1
            skip_regular_first = True

    v = offset_from_face
    if skip_regular_first:
        v = offset_from_face + burden_b

    safety = 0
    while v <= v_max and safety < 500:
        safety += 1
        row_cfg = _row_config(params, pattern, row_index, spacing_a, burden_b, row_shift_ratio, default_kind)
        local_a, local_b, shift_ratio, row_kind = row_cfg
        if pattern == "domain_dependent" and domain_list:
            mid = _world_xy(origin, row_dir, advance_dir, 0.5 * (u_min + u_max), v)
            domain = domain_at(domain_list, Point3(x=mid[0], y=mid[1], z=crest_z))
            if domain is not None:
                if domain.spacing_a_m:
                    local_a = float(domain.spacing_a_m)
                if domain.burden_b_m:
                    local_b = float(domain.burden_b_m)
                if pattern == "square" and domain.spacing_a_m and not domain.burden_b_m:
                    local_b = local_a

        shift = shift_ratio * local_a if row_index % 2 == 1 else 0.0
        col_index = 0
        if pattern == "domain_dependent" and domain_list:
            placed = _walk_domain_row(
                contour,
                domain_list,
                boundary,
                origin,
                row_dir,
                advance_dir,
                u_min + shift,
                u_max,
                v,
                local_a,
                row_index,
                row_kind,
                diameter_mm,
                subdrill_m,
                angle_deg,
                azimuth_deg,
                depth_override,
                surfaces,
                crest_z,
            )
            holes.extend(placed)
            col_index = len(placed)
        else:
            u = u_min + shift
            while u <= u_max:
                x, y = _world_xy(origin, row_dir, advance_dir, u, v)
                if point_in_polygon((x, y), boundary):
                    collar, toe = drape_collar(
                        x, y, angle_deg, azimuth_deg, subdrill_m, contour, surfaces, depth_override
                    )
                    holes.append(
                        Hole(
                            id=_grid_id(row_kind, row_index, col_index),
                            row=row_index,
                            col=col_index,
                            collar=collar,
                            toe=toe,
                            diameter_mm=diameter_mm,
                            subdrill_m=subdrill_m,
                            kind=row_kind,
                            source="generated",
                        )
                    )
                    col_index += 1
                u += local_a

        row_index += 1
        v += local_b

    holes.extend(
        _generate_wall_row(
            contour, params, "contour", "K", "contour_row", "contour_spacing_m",
            "contour_offset_m", "contour_diameter_mm", "contour_depth_m",
            "contour_subdrill_m", "contour_angle_deg", diameter_mm, depth_override,
            subdrill_m, surfaces,
        )
    )
    holes.extend(
        _generate_wall_row(
            contour, params, "presplit", "P", "presplit_row", "presplit_spacing_m",
            "presplit_offset_m", "presplit_diameter_mm", "presplit_depth_m",
            "presplit_subdrill_m", "presplit_angle_deg", diameter_mm, depth_override,
            subdrill_m, surfaces,
        )
    )
    holes.extend(
        _generate_wall_row(
            contour, params, "trim", "T", "trim_row", "trim_spacing_m",
            "trim_offset_m", "trim_diameter_mm", "trim_depth_m",
            "trim_subdrill_m", "trim_angle_deg", diameter_mm, depth_override,
            subdrill_m, surfaces,
        )
    )
    if params.get("buffer_row"):
        holes.extend(
            _generate_buffer_row(
                contour, params, boundary, origin, row_dir, advance_dir,
                spacing_a, burden_b, diameter_mm, subdrill_m, angle_deg, azimuth_deg,
                depth_override, surfaces,
            )
        )
    if params.get("stab_row"):
        holes.extend(_generate_stab_holes(holes, contour, params, surfaces))
    if params.get("satellite_holes"):
        holes.extend(_generate_satellite_holes(holes, contour, params, surfaces))
    if params.get("infill_holes"):
        holes.extend(_generate_infill_holes(holes, contour, params, surfaces))

    return _keep_manual(existing_holes) + holes


def _normalize_kind(value: Any, default: str) -> str:
    kind = str(value or default).strip().lower()
    return kind if kind in HOLE_KINDS else default


def _grid_id(kind: str, row_index: int, col_index: int) -> str:
    prefixes = {
        "buffer": "B",
        "stab": "S",
        "infill": "I",
        "satellite": "SAT",
    }
    prefix = prefixes.get(kind)
    if prefix:
        return f"{prefix}{row_index + 1}-{col_index + 1:02d}"
    return f"{row_index + 1}-{col_index + 1:02d}"


def _world_xy(
    origin: tuple[float, float],
    row_dir: tuple[float, float],
    advance_dir: tuple[float, float],
    u: float,
    v: float,
) -> tuple[float, float]:
    return (
        origin[0] + row_dir[0] * u + advance_dir[0] * v,
        origin[1] + row_dir[1] * u + advance_dir[1] * v,
    )


def _row_config(
    params: dict[str, Any],
    pattern: str,
    row_index: int,
    spacing_a: float,
    burden_b: float,
    row_shift_ratio: float,
    default_kind: str,
) -> tuple[float, float, float, str]:
    row_params = params.get("row_params") or []
    override: dict[str, Any] = {}
    if pattern == "variable" and isinstance(row_params, list) and row_params:
        if row_index < len(row_params) and isinstance(row_params[row_index], dict):
            override = row_params[row_index]
        elif isinstance(row_params[-1], dict):
            override = row_params[-1]
    local_a = float(override.get("spacing_a_m", spacing_a))
    local_b = float(override.get("burden_b_m", burden_b))
    shift_ratio = float(override.get("shift_ratio", row_shift_ratio))
    kind = _normalize_kind(override.get("kind", default_kind), default_kind)
    if local_a <= 0:
        local_a = spacing_a
    if local_b <= 0:
        local_b = burden_b
    return local_a, local_b, shift_ratio, kind


def _walk_domain_row(
    contour: BlockContour,
    domains: list[BlastDomain],
    boundary: list[tuple[float, float]],
    origin: tuple[float, float],
    row_dir: tuple[float, float],
    advance_dir: tuple[float, float],
    u_start: float,
    u_max: float,
    v: float,
    fallback_a: float,
    row_index: int,
    row_kind: str,
    diameter_mm: float,
    subdrill_m: float,
    angle_deg: float,
    azimuth_deg: float,
    depth_override: float | None,
    surfaces: object | None,
    crest_z: float,
) -> list[Hole]:
    holes: list[Hole] = []
    u = u_start
    col_index = 0
    probe = max(0.25, fallback_a * 0.25)
    safety = 0
    while u <= u_max and safety < 2000:
        safety += 1
        x, y = _world_xy(origin, row_dir, advance_dir, u, v)
        if not point_in_polygon((x, y), boundary):
            u += probe
            continue
        domain = domain_at(domains, Point3(x=x, y=y, z=crest_z))
        local_a = fallback_a
        if domain is not None and domain.spacing_a_m:
            local_a = float(domain.spacing_a_m)
        if local_a <= 0:
            local_a = fallback_a
        collar, toe = drape_collar(
            x, y, angle_deg, azimuth_deg, subdrill_m, contour, surfaces, depth_override
        )
        holes.append(
            Hole(
                id=_grid_id(row_kind, row_index, col_index),
                row=row_index,
                col=col_index,
                collar=collar,
                toe=toe,
                diameter_mm=diameter_mm,
                subdrill_m=subdrill_m,
                kind=row_kind,
                source="generated",
            )
        )
        col_index += 1
        u += local_a
    return holes


def _keep_manual(existing_holes: list[Hole] | None) -> list[Hole]:
    if not existing_holes:
        return []
    return [h for h in existing_holes if h.source == "manual"]


def _inward_normal(a: tuple[float, float], b: tuple[float, float]) -> tuple[float, float]:
    dx, dy = b[0] - a[0], b[1] - a[1]
    length = math.hypot(dx, dy)
    if length < 1e-9:
        return (0.0, 0.0)
    ux, uy = dx / length, dy / length
    return (-uy, ux)


def _generate_face_following_row(
    contour: BlockContour,
    params: dict[str, Any],
    boundary: list[tuple[float, float]],
    origin: tuple[float, float],
    row_dir: tuple[float, float],
    advance_dir: tuple[float, float],
    burden_m: float,
    spacing_a: float,
    diameter_mm: float,
    subdrill_m: float,
    angle_deg: float,
    azimuth_deg: float,
    depth_m: float | None,
    kind: str,
    surfaces: object | None,
) -> list[Hole]:
    """Place row 0 at a constant burden from the actual free-face polyline."""
    verts = ensure_ccw(contour.points_xy)
    start_offset = float(params.get("first_row_start_offset_m", 0.0))
    holes: list[Hole] = []
    col_index = 0
    for edge in contour.free_faces:
        for i in range(len(edge) - 1):
            if not (0 <= edge[i] < len(verts) and 0 <= edge[i + 1] < len(verts)):
                continue
            a, b = verts[edge[i]], verts[edge[i + 1]]
            nx, ny = _inward_normal(a, b)
            dx, dy = b[0] - a[0], b[1] - a[1]
            length = math.hypot(dx, dy)
            if length < 1e-9 or spacing_a <= 0:
                continue
            ux, uy = dx / length, dy / length
            distance = start_offset
            while distance <= length:
                x = a[0] + ux * distance + nx * burden_m
                y = a[1] + uy * distance + ny * burden_m
                if point_in_polygon((x, y), boundary):
                    collar, toe = drape_collar(
                        x, y, angle_deg, azimuth_deg, subdrill_m, contour, surfaces, depth_m
                    )
                    holes.append(
                        Hole(
                            id=_grid_id(kind, 0, col_index),
                            row=0,
                            col=col_index,
                            collar=collar,
                            toe=toe,
                            diameter_mm=diameter_mm,
                            subdrill_m=subdrill_m,
                            kind=kind,
                            source="generated",
                        )
                    )
                    col_index += 1
                distance += spacing_a
    return holes


def _generate_wall_row(
    contour: BlockContour,
    params: dict[str, Any],
    kind: str,
    prefix: str,
    flag_key: str,
    spacing_key: str,
    offset_key: str,
    diameter_key: str,
    depth_key: str,
    subdrill_key: str,
    angle_key: str,
    default_diameter_mm: float,
    default_depth_m: float | None,
    default_subdrill_m: float,
    surfaces: object | None = None,
) -> list[Hole]:
    if not params.get(flag_key):
        return []
    spacing = float(params.get(spacing_key, 2.0))
    start_offset = float(params.get(offset_key, 1.0))
    if spacing <= 0:
        return []
    diameter_mm = float(params.get(diameter_key, default_diameter_mm))
    raw_depth = params.get(depth_key, default_depth_m)
    depth_m = float(raw_depth) if raw_depth is not None else None
    subdrill_m = float(params.get(subdrill_key, default_subdrill_m))
    angle_deg = float(params.get(angle_key, 0.0))

    verts = contour.points_xy
    holes: list[Hole] = []
    for edge_idx, edge in enumerate(contour.free_faces):
        col_index = 0
        for i in range(len(edge) - 1):
            a = verts[edge[i]]
            b = verts[edge[i + 1]]
            dx, dy = b[0] - a[0], b[1] - a[1]
            length = math.hypot(dx, dy)
            if length < 1e-9:
                continue
            ux, uy = dx / length, dy / length
            azimuth_deg = math.degrees(math.atan2(ux, uy)) % 360.0
            distance = start_offset
            while distance <= length:
                x = a[0] + ux * distance
                y = a[1] + uy * distance
                collar, toe = drape_collar(
                    x, y, angle_deg, azimuth_deg, subdrill_m, contour, surfaces, depth_m
                )
                holes.append(
                    Hole(
                        id=f"{prefix}{edge_idx + 1}-{col_index + 1:02d}",
                        row=-(edge_idx + 1),
                        col=col_index,
                        collar=collar,
                        toe=toe,
                        diameter_mm=diameter_mm,
                        subdrill_m=subdrill_m,
                        kind=kind,
                        source="generated",
                    )
                )
                col_index += 1
                distance += spacing
    return holes


def _generate_buffer_row(
    contour: BlockContour,
    params: dict[str, Any],
    boundary: list[tuple[float, float]],
    origin: tuple[float, float],
    row_dir: tuple[float, float],
    advance_dir: tuple[float, float],
    spacing_a: float,
    burden_b: float,
    diameter_mm: float,
    subdrill_m: float,
    angle_deg: float,
    azimuth_deg: float,
    depth_m: float | None,
    surfaces: object | None,
) -> list[Hole]:
    spacing = float(params.get("buffer_spacing_m", spacing_a))
    offset = float(params.get("buffer_offset_m", max(0.5, burden_b * 0.5)))
    if spacing <= 0:
        return []
    verts = ensure_ccw(contour.points_xy)
    holes: list[Hole] = []
    col_index = 0
    if contour.free_faces:
        for edge in contour.free_faces:
            for i in range(len(edge) - 1):
                if not (0 <= edge[i] < len(verts) and 0 <= edge[i + 1] < len(verts)):
                    continue
                a, b = verts[edge[i]], verts[edge[i + 1]]
                nx, ny = _inward_normal(a, b)
                dx, dy = b[0] - a[0], b[1] - a[1]
                length = math.hypot(dx, dy)
                if length < 1e-9:
                    continue
                ux, uy = dx / length, dy / length
                distance = 0.0
                while distance <= length:
                    x = a[0] + ux * distance + nx * offset
                    y = a[1] + uy * distance + ny * offset
                    if point_in_polygon((x, y), boundary):
                        collar, toe = drape_collar(
                            x, y, angle_deg, azimuth_deg, subdrill_m, contour, surfaces, depth_m
                        )
                        holes.append(
                            Hole(
                                id=_grid_id("buffer", 0, col_index),
                                row=-10,
                                col=col_index,
                                collar=collar,
                                toe=toe,
                                diameter_mm=float(params.get("buffer_diameter_mm", diameter_mm)),
                                subdrill_m=subdrill_m,
                                kind="buffer",
                                source="generated",
                            )
                        )
                        col_index += 1
                    distance += spacing
        return holes

    us = [(vx - origin[0]) * row_dir[0] + (vy - origin[1]) * row_dir[1] for vx, vy in verts]
    u = min(us)
    while u <= max(us):
        x, y = _world_xy(origin, row_dir, advance_dir, u, offset)
        if point_in_polygon((x, y), boundary):
            collar, toe = drape_collar(
                x, y, angle_deg, azimuth_deg, subdrill_m, contour, surfaces, depth_m
            )
            holes.append(
                Hole(
                    id=_grid_id("buffer", 0, col_index),
                    row=-10,
                    col=col_index,
                    collar=collar,
                    toe=toe,
                    diameter_mm=float(params.get("buffer_diameter_mm", diameter_mm)),
                    subdrill_m=subdrill_m,
                    kind="buffer",
                    source="generated",
                )
            )
            col_index += 1
        u += spacing
    return holes


def _generate_stab_holes(
    holes: list[Hole],
    contour: BlockContour,
    params: dict[str, Any],
    surfaces: object | None,
) -> list[Hole]:
    """Short holes midway between first-row production holes (or in front if a single hole)."""
    first_row = [h for h in holes if h.enabled and h.kind == "production" and h.row == 0]
    if not first_row:
        first_row = [h for h in holes if h.enabled and h.kind == "production"]
        if not first_row:
            return []
        min_row = min(h.row for h in first_row)
        first_row = [h for h in first_row if h.row == min_row]
    ordered = sorted(first_row, key=lambda h: h.col)
    depth_m = float(params.get("stab_depth_m", 3.0))
    angle_deg = float(params.get("stab_angle_deg", params.get("angle_deg", 0.0)))
    azimuth_deg = float(params.get("stab_azimuth_deg", params.get("azimuth_deg", 0.0)))
    subdrill_m = float(params.get("stab_subdrill_m", 0.0))
    diameter_mm = float(params.get("stab_diameter_mm", params.get("diameter_mm", 152.0)))
    created: list[Hole] = []
    if len(ordered) == 1:
        hole = ordered[0]
        x = hole.collar.x
        y = hole.collar.y
        collar, toe = drape_collar(x, y, angle_deg, azimuth_deg, subdrill_m, contour, surfaces, depth_m)
        created.append(
            Hole(
                id="S1-01",
                row=hole.row,
                col=0,
                collar=collar,
                toe=toe,
                diameter_mm=diameter_mm,
                subdrill_m=subdrill_m,
                kind="stab",
                source="generated",
            )
        )
        return created
    for index, (left, right) in enumerate(zip(ordered, ordered[1:])):
        x = 0.5 * (left.collar.x + right.collar.x)
        y = 0.5 * (left.collar.y + right.collar.y)
        collar, toe = drape_collar(x, y, angle_deg, azimuth_deg, subdrill_m, contour, surfaces, depth_m)
        created.append(
            Hole(
                id=f"S1-{index + 1:02d}",
                row=left.row,
                col=index,
                collar=collar,
                toe=toe,
                diameter_mm=diameter_mm,
                subdrill_m=subdrill_m,
                kind="stab",
                source="generated",
            )
        )
    return created


def _generate_satellite_holes(
    holes: list[Hole],
    contour: BlockContour,
    params: dict[str, Any],
    surfaces: object | None,
) -> list[Hole]:
    production = [h for h in holes if h.enabled and h.kind == "production"]
    if not production:
        return []
    radius = float(params.get("satellite_radius_m", 1.5))
    count = max(1, int(params.get("satellite_count", 1)))
    depth_override = params.get("satellite_depth_m", params.get("depth_m"))
    depth_m = float(depth_override) if depth_override is not None else None
    angle_deg = float(params.get("angle_deg", 0.0))
    azimuth_deg = float(params.get("azimuth_deg", 0.0))
    subdrill_m = float(params.get("subdrill_m", 1.0))
    diameter_mm = float(params.get("satellite_diameter_mm", params.get("diameter_mm", 152.0)))
    created: list[Hole] = []
    for hole in production:
        for index in range(count):
            bearing = math.radians((azimuth_deg + index * (360.0 / count)) % 360.0)
            x = hole.collar.x + radius * math.sin(bearing)
            y = hole.collar.y + radius * math.cos(bearing)
            if not point_in_polygon((x, y), contour.points_xy):
                continue
            collar, toe = drape_collar(
                x, y, angle_deg, azimuth_deg, subdrill_m, contour, surfaces, depth_m
            )
            created.append(
                Hole(
                    id=f"SAT-{hole.id}-{index + 1}",
                    row=hole.row,
                    col=index,
                    collar=collar,
                    toe=toe,
                    diameter_mm=diameter_mm,
                    subdrill_m=subdrill_m,
                    kind="satellite",
                    source="generated",
                )
            )
    return created


def _generate_infill_holes(
    holes: list[Hole],
    contour: BlockContour,
    params: dict[str, Any],
    surfaces: object | None,
) -> list[Hole]:
    factor = float(params.get("infill_gap_factor", 1.6))
    production = [h for h in holes if h.enabled and h.kind == "production"]
    by_row: dict[int, list[Hole]] = {}
    for hole in production:
        by_row.setdefault(hole.row, []).append(hole)
    expected_a = float(params.get("spacing_a_m", 5.0))
    threshold = expected_a * factor
    angle_deg = float(params.get("angle_deg", 0.0))
    azimuth_deg = float(params.get("azimuth_deg", 0.0))
    subdrill_m = float(params.get("subdrill_m", 1.0))
    depth_override = params.get("depth_m")
    depth_m = float(depth_override) if depth_override is not None else None
    diameter_mm = float(params.get("diameter_mm", 152.0))
    created: list[Hole] = []
    index = 0
    for row, group in by_row.items():
        ordered = sorted(group, key=lambda h: h.col)
        for left, right in zip(ordered, ordered[1:]):
            gap = math.hypot(right.collar.x - left.collar.x, right.collar.y - left.collar.y)
            if gap < threshold:
                continue
            x = 0.5 * (left.collar.x + right.collar.x)
            y = 0.5 * (left.collar.y + right.collar.y)
            if not point_in_polygon((x, y), contour.points_xy):
                continue
            collar, toe = drape_collar(
                x, y, angle_deg, azimuth_deg, subdrill_m, contour, surfaces, depth_m
            )
            created.append(
                Hole(
                    id=f"I-{index + 1:02d}",
                    row=row,
                    col=index,
                    collar=collar,
                    toe=toe,
                    diameter_mm=diameter_mm,
                    subdrill_m=subdrill_m,
                    kind="infill",
                    source="generated",
                )
            )
            index += 1
    return created
