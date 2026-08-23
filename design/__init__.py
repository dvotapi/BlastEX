"""Проектирование БВР: контур блока, поверхности уступа, геологические домены, сетка, заряжание, тайминг, сейсмика, факт бурения."""

from design.models import HOLE_KINDS, PRESERVED_HOLE_KINDS, RECEPTOR_KINDS
from design.pattern import PATTERN_TYPES

__all__ = ["HOLE_KINDS", "PATTERN_TYPES", "PRESERVED_HOLE_KINDS", "RECEPTOR_KINDS"]
