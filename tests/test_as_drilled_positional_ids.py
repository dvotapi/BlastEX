"""Фактическая съёмка находит проектные скважины по id с нумерацией по позиции.

Id назначается после размещения и не совпадает с row. Связь as_drilled — по id,
поэтому проверяем: каждая сгенерированная скважина (сетка, передние ряды, стенки)
принимает факт, сравнение не даёт предупреждений о потере связи.
"""
import unittest

from design.as_drilled import as_drilled_from_design_hole, compare_design, record_as_drilled
from design.models import BlastDesign
from design.pattern import generate_pattern
from tests.test_design_pattern_full_contour import BOOT, PARAMS, _contour


class PositionalIdsAsDrilledTest(unittest.TestCase):
    def test_every_generated_hole_is_linked_by_its_id(self):
        contour = _contour(BOOT)
        holes = generate_pattern(
            contour, {**PARAMS, "contour_row": True, "buffer_row": True, "presplit_row": True}
        )
        design = BlastDesign(design_id="pos", contour=contour, holes=holes)
        self.assertEqual(len({h.id for h in holes}), len(holes))
        for hole in holes:
            record_as_drilled(design, as_drilled_from_design_hole(hole, source="test"))
        self.assertEqual(len(design.as_drilled_holes), len(holes))
        report = compare_design(design)
        self.assertEqual(report["compared_count"], len(holes))
        self.assertFalse([w for w in report["warnings"] if "отсутствующий" in w or "Нет факта" in w])


if __name__ == "__main__":
    unittest.main()
