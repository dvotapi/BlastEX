"""Пространственная основа проекта БВР (фаза BDX-001).

Пакет держит систему координат, треугольную сеть (TIN), типизированные
поверхности уступа и импорт съёмки. Плоский `BenchSurface` остаётся
совместимым запасным вариантом: если TIN нет, отметки берутся с плоскости.
"""
from design.spatial.coordinates import CoordinateSystem
from design.spatial.io import SurveyImport, detect_format, import_survey
from design.spatial.surfaces import (
    SURFACE_KINDS,
    SurfaceModel,
    SurfaceSet,
    build_surface,
    face_surface,
    floor_surface,
    post_blast_surface,
    top_surface,
)
from design.spatial.tin import TIN, build_tin, loft_polylines

__all__ = [
    "SURFACE_KINDS",
    "TIN",
    "CoordinateSystem",
    "SurfaceModel",
    "SurfaceSet",
    "SurveyImport",
    "build_surface",
    "build_tin",
    "detect_format",
    "face_surface",
    "floor_surface",
    "import_survey",
    "loft_polylines",
    "post_blast_surface",
    "top_surface",
]
