"""Проектирование БВР: контур блока, поверхности уступа, геологические домены, сетка, заряжание, тайминг, сейсмика, факт бурения, факт заряжания и взрыва, результаты после взрыва, сценарии сравнения (BDX-016), детерминированная оптимизация Парето (BDX-017), ML-рекомендация оверлея (BDX-018), официальный паспорт (BDX-024)."""

from design.models import HOLE_KINDS, PRESERVED_HOLE_KINDS, RECEPTOR_KINDS
from design.pattern import PATTERN_TYPES

__all__ = ["HOLE_KINDS", "PATTERN_TYPES", "PRESERVED_HOLE_KINDS", "RECEPTOR_KINDS"]
