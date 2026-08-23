import unittest

from Blast import ExplosiveProperties
from design.charging import apply_charge_rules
from design.export import holes_csv, passport_html
from design.models import BenchSurface, BlastDesign, BlockContour, Point3
from design.pattern import generate_pattern
from design.timing import build_template_network

EXPLOSIVE = ExplosiveProperties("Гранулит-РП", 0.85, 3.76)


def _design() -> BlastDesign:
    contour = BlockContour(
        vertices=[Point3(x=x, y=y, z=0.0) for x, y in [(0, 0), (20, 0), (20, 16), (0, 16)]],
        bench=BenchSurface(crest_z_m=0.0, toe_z_m=-10.0),
    )
    params = {"pattern": "rectangular", "spacing_a_m": 4.0, "burden_b_m": 4.0, "offset_from_face_m": 0.0, "edge_margin_m": 0.0}
    holes = generate_pattern(contour, params)
    loads = apply_charge_rules(
        holes, {"stemming_m": 3.0, "decking": "continuous", "grid_a_m": 4.0, "grid_b_m": 4.0}, EXPLOSIVE
    )
    network = build_template_network(holes, "row", {"system": "nonel"})
    return BlastDesign(
        design_id="test",
        name="Тестовый паспорт",
        contour=contour,
        holes=holes,
        loads=loads,
        network=network,
        pattern_params=params,
        explosive_key="Гранулит-РП",
    )


class HolesCsvTests(unittest.TestCase):
    def test_csv_has_one_row_per_hole_plus_header(self):
        design = _design()
        text = holes_csv(design)
        lines = [line for line in text.splitlines() if line]
        self.assertEqual(len(lines), len(design.holes) + 1)

    def test_csv_has_utf8_bom_for_excel(self):
        design = _design()
        text = holes_csv(design)
        self.assertTrue(text.startswith("﻿"))


class PassportHtmlTests(unittest.TestCase):
    def test_passport_contains_design_name_and_hole_rows(self):
        design = _design()
        html_text = passport_html(design)
        self.assertIn("Тестовый паспорт", html_text)
        holes_body = html_text.split('class="holes-table"', 1)[1]
        self.assertEqual(holes_body.count("<tr>"), len(design.holes) + 1)

    def test_passport_keeps_role_columns_visible(self):
        design = _design()
        html_text = passport_html(design)
        self.assertIn("DESIGNED", html_text)
        self.assertIn("EXECUTED", html_text)
        self.assertIn("PREDICTED", html_text)
        self.assertIn("MEASURED", html_text)
        self.assertIn("col-predicted", html_text)
        self.assertIn("не утверждён автоматически", html_text.lower())

    def test_passport_escapes_html_in_name(self):
        design = _design()
        design.name = "<script>alert(1)</script>"
        html_text = passport_html(design)
        self.assertNotIn("<script>alert(1)</script>", html_text)
        self.assertIn("&lt;script&gt;", html_text)

    def test_passport_handles_empty_design(self):
        empty = BlastDesign(design_id="empty")
        html_text = passport_html(empty)
        self.assertIn("<html", html_text)


if __name__ == "__main__":
    unittest.main()
