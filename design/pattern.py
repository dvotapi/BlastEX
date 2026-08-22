"""Автоматическая раскладка сетки скважин по контуру блока."""
from __future__ import annotations

import math
from typing import Any

from design.geometry import (
    ensure_ccw,
    hole_from_collar,
    local_basis,
    offset_polygon,
    pattern_origin,
    point_in_polygon,
)
from design.models import BlockContour, Hole, Point3

PATTERN_TYPES = ("square", "rectangular", "staggered")


def generate_pattern(
    contour: BlockContour,
    params: dict[str, Any],
    existing_holes: list[Hole] | None = None,
) -> list[Hole]:
    """Строит регулярную сетку скважин внутри контура блока.

    params:
      pattern            "square" | "rectangular" | "staggered"
      spacing_a_m        шаг вдоль ряда, м
      burden_b_m         шаг между рядами, м (игнорируется для "square" — берётся = a)
      row_shift_ratio     доля a смещения чётных рядов (только "staggered", по умолч. 0.5)
      row_azimuth_deg    азимут рядов, град (0 = север/+Y)
      offset_from_face_m отступ первого ряда от открытого откоса, м
      edge_margin_m      отступ раскладки от границы контура, м
      diameter_mm        диаметр скважины, мм
      subdrill_m         перебур, м
      angle_deg          угол скважины от вертикали, град
      azimuth_deg        азимут наклона скважины, град
      depth_m            глубина скважины по оси, м (по умолчанию — высота уступа + перебур)
    """
    pattern = str(params.get("pattern", "square"))
    if pattern not in PATTERN_TYPES:
        pattern = "square"

    spacing_a = float(params.get("spacing_a_m", 5.0))
    burden_b = spacing_a if pattern == "square" else float(params.get("burden_b_m", spacing_a))
    row_shift_ratio = float(params.get("row_shift_ratio", 0.5)) if pattern == "staggered" else 0.0
    row_azimuth_deg = float(params.get("row_azimuth_deg", 0.0))
    offset_from_face = float(params.get("offset_from_face_m", burden_b / 2))
    edge_margin = float(params.get("edge_margin_m", 0.0))
    diameter_mm = float(params.get("diameter_mm", 152.0))
    subdrill_m = float(params.get("subdrill_m", 1.0))
    angle_deg = float(params.get("angle_deg", 0.0))
    azimuth_deg = float(params.get("azimuth_deg", row_azimuth_deg))
    depth_m = params.get("depth_m")
    depth_m = float(depth_m) if depth_m is not None else contour.bench.height_m + subdrill_m

    verts = ensure_ccw(contour.points_xy)
    if len(verts) < 3 or spacing_a <= 0 or burden_b <= 0:
        return _keep_manual(existing_holes)

    boundary = offset_polygon(verts, edge_margin) if edge_margin > 0 else verts

    row_dir, advance_dir = local_basis(row_azimuth_deg)
    origin, advance_dir = pattern_origin(contour, row_dir, advance_dir)

    us = [
        (vx - origin[0]) * row_dir[0] + (vy - origin[1]) * row_dir[1] for vx, vy in verts
    ]
    vs = [
        (vx - origin[0]) * advance_dir[0] + (vy - origin[1]) * advance_dir[1]
        for vx, vy in verts
    ]
    u_min, u_max = min(us) - spacing_a, max(us) + spacing_a
    v_max = max(vs) + burden_b

    collar_z = contour.bench.crest_z_m

    holes: list[Hole] = []
    row_index = 0
    v = offset_from_face
    while v <= v_max:
        shift = row_shift_ratio * spacing_a if row_index % 2 == 1 else 0.0
        col_index = 0
        u = u_min + shift
        while u <= u_max:
            x = origin[0] + row_dir[0] * u + advance_dir[0] * v
            y = origin[1] + row_dir[1] * u + advance_dir[1] * v
            if point_in_polygon((x, y), boundary):
                collar = Point3(x=x, y=y, z=collar_z)
                toe = hole_from_collar(collar, depth_m, angle_deg, azimuth_deg)
                holes.append(
                    Hole(
                        id=f"{row_index + 1}-{col_index + 1:02d}",
                        row=row_index,
                        col=col_index,
                        collar=collar,
                        toe=toe,
                        diameter_mm=diameter_mm,
                        subdrill_m=subdrill_m,
                        kind="production",
                        source="generated",
                    )
                )
                col_index += 1
            u += spacing_a
        row_index += 1
        v += burden_b

    contour_holes = _generate_contour_row(contour, params, collar_z, diameter_mm, depth_m, subdrill_m)
    holes.extend(contour_holes)

    manual = _keep_manual(existing_holes)
    return manual + holes


def _keep_manual(existing_holes: list[Hole] | None) -> list[Hole]:
    if not existing_holes:
        return []
    return [h for h in existing_holes if h.source == "manual"]


def _generate_contour_row(
    contour: BlockContour,
    params: dict[str, Any],
    collar_z: float,
    default_diameter_mm: float,
    default_depth_m: float,
    default_subdrill_m: float,
) -> list[Hole]:
    if not params.get("contour_row"):
        return []
    spacing = float(params.get("contour_spacing_m", 2.0))
    start_offset = float(params.get("contour_offset_m", 1.0))
    if spacing <= 0:
        return []
    diameter_mm = float(params.get("contour_diameter_mm", default_diameter_mm))
    depth_m = float(params.get("contour_depth_m", default_depth_m))
    subdrill_m = float(params.get("contour_subdrill_m", default_subdrill_m))
    angle_deg = float(params.get("contour_angle_deg", 0.0))

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
                collar = Point3(x=x, y=y, z=collar_z)
                toe = hole_from_collar(collar, depth_m, angle_deg, azimuth_deg)
                holes.append(
                    Hole(
                        id=f"K{edge_idx + 1}-{col_index + 1:02d}",
                        row=-(edge_idx + 1),
                        col=col_index,
                        collar=collar,
                        toe=toe,
                        diameter_mm=diameter_mm,
                        subdrill_m=subdrill_m,
                        kind="contour",
                        source="generated",
                    )
                )
                col_index += 1
                distance += spacing
    return holes
