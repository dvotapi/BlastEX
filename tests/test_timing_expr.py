import unittest

from design.timing_expr import TimingExprError, evaluate_timing_expression


class TimingExpressionTests(unittest.TestCase):
    def test_row_interval_formula(self):
        result = evaluate_timing_expression(
            "base + interval * row + abs(col - 3)",
            {"base": 10, "interval": 17, "row": 2, "col": 5},
        )
        self.assertAlmostEqual(result, 10 + 17 * 2 + 2)

    def test_functions_and_comparisons(self):
        result = evaluate_timing_expression(
            "min(row, col) * 10 + (x > 5) * 100",
            {"row": 3, "col": 1, "x": 8},
        )
        self.assertAlmostEqual(result, 110)

    def test_rejects_eval_and_attribute_access(self):
        with self.assertRaises(TimingExprError):
            evaluate_timing_expression("__import__('os')", {"row": 1})
        with self.assertRaises(TimingExprError):
            evaluate_timing_expression("row.__class__", {"row": 1})
        with self.assertRaises(TimingExprError):
            evaluate_timing_expression("eval(1)", {"row": 1})
        with self.assertRaises(TimingExprError):
            evaluate_timing_expression("(lambda x: x)(1)", {"row": 1})

    def test_rejects_unknown_names_and_empty(self):
        with self.assertRaises(TimingExprError):
            evaluate_timing_expression("foo + 1", {"row": 1})
        with self.assertRaises(TimingExprError):
            evaluate_timing_expression("", {"row": 1})
        with self.assertRaises(TimingExprError):
            evaluate_timing_expression("1 / 0", {"row": 1})

    def test_does_not_call_python_eval(self):
        # A name that would be resolved if the implementation used eval().
        with self.assertRaises(TimingExprError):
            evaluate_timing_expression("open", {})


if __name__ == "__main__":
    unittest.main()
