"""BDX-024: assembling the passport must not rewrite or approve the design."""
import unittest

from design.models import ROLE_DESIGNED, ROLE_MEASURED, ROLE_PREDICTED
from design.reporting.engine import build_passport
from tests.scenario_fixtures import charged_design


class ReportingIsolationTests(unittest.TestCase):
    def test_build_does_not_rewrite_holes_loads_or_network(self):
        design = charged_design("passport-isolation")
        holes_before = [hole.to_dict() for hole in design.holes]
        loads_before = [load.to_dict() for load in design.loads]
        pattern_before = dict(design.pattern_params)
        detonators_before = [item.to_dict() for item in design.network.detonators]
        times_before = dict(design.network.electronic_times_ms)
        document = build_passport(design)
        self.assertEqual([hole.to_dict() for hole in design.holes], holes_before)
        self.assertEqual([load.to_dict() for load in design.loads], loads_before)
        self.assertEqual(dict(design.pattern_params), pattern_before)
        self.assertEqual([item.to_dict() for item in design.network.detonators], detonators_before)
        self.assertEqual(dict(design.network.electronic_times_ms), times_before)
        self.assertFalse(document.approved)
        self.assertFalse(document.auto_approved)
        self.assertFalse(document.design_rewritten)

    def test_predicted_column_is_never_copied_into_designed(self):
        design = charged_design("passport-roles")
        document = build_passport(design)
        x50_row = next(row for row in document.comparison if row.key == "x50_mm")
        self.assertIsNone(x50_row.designed)
        self.assertIsNotNone(x50_row.predicted)
        self.assertEqual(document.designed.role, ROLE_DESIGNED)
        self.assertEqual(document.predicted.role, ROLE_PREDICTED)
        self.assertEqual(document.measured.role, ROLE_MEASURED)
        self.assertNotEqual(document.predicted.role, document.designed.role)
        self.assertNotEqual(document.predicted.role, document.measured.role)

    def test_module_does_not_use_eval(self):
        import inspect

        from design.reporting import engine, html, types, units

        for module in (engine, html, types, units):
            source = inspect.getsource(module)
            self.assertNotIn(" eval(", source)
            self.assertNotIn("eval(", source.replace("evaluate", ""))


if __name__ == "__main__":
    unittest.main()
