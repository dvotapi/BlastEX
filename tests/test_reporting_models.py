"""BDX-024: passport types keep DESIGNED / EXECUTED / PREDICTED / MEASURED apart."""
import unittest

from design.models import ROLE_DESIGNED, ROLE_EXECUTED, ROLE_MEASURED, ROLE_PREDICTED
from design.reporting.types import (
    AUTO_APPROVED,
    DISCLAIMER,
    BlastPassport,
    DesignedParameters,
    ExecutedSnapshot,
    MeasuredOutcomes,
    MetricRow,
    PlannedCostSnapshot,
    PredictedOutcomes,
    roles_payload,
)


class ReportingModelTests(unittest.TestCase):
    def test_roles_payload_never_approves(self):
        payload = roles_payload()
        self.assertEqual(payload["roles"], ["designed", "executed", "predicted", "measured"])
        self.assertFalse(payload["approved"])
        self.assertFalse(payload["auto_approved"])
        self.assertFalse(AUTO_APPROVED)
        self.assertFalse(payload["evaluates_code"])
        self.assertFalse(payload["silent_unit_conversion"])
        self.assertIn("predicted", DISCLAIMER.lower())

    def test_metric_row_carries_four_independent_columns(self):
        row = MetricRow(
            key="x50_mm",
            label="X50",
            unit="мм",
            section="fragmentation",
            designed=None,
            executed=None,
            predicted=180.0,
            measured=210.0,
        )
        payload = row.to_dict()
        self.assertIsNone(payload["designed"])
        self.assertIsNone(payload["executed"])
        self.assertEqual(payload["predicted"], 180.0)
        self.assertEqual(payload["measured"], 210.0)
        self.assertEqual(payload["roles"]["predicted"], ROLE_PREDICTED)
        self.assertEqual(payload["roles"]["measured"], ROLE_MEASURED)
        self.assertNotEqual(payload["predicted"], payload["measured"])

    def test_section_roles_cannot_be_overridden(self):
        designed = DesignedParameters(role=ROLE_PREDICTED)
        executed = ExecutedSnapshot(role=ROLE_DESIGNED)
        predicted = PredictedOutcomes(role=ROLE_MEASURED)
        measured = MeasuredOutcomes(role=ROLE_DESIGNED)
        planned = PlannedCostSnapshot(total_amount_rub=100.0, role=ROLE_PREDICTED)
        document = BlastPassport(
            design_id="p1",
            name="Тест",
            approved=True,
            auto_approved=True,
            designed=designed,
            executed=executed,
            predicted=predicted,
            measured=measured,
            planned_cost=planned,
        )
        self.assertFalse(document.approved)
        self.assertFalse(document.auto_approved)
        self.assertEqual(document.designed.role, ROLE_DESIGNED)
        self.assertEqual(document.executed.role, ROLE_EXECUTED)
        self.assertEqual(document.predicted.role, ROLE_PREDICTED)
        self.assertEqual(document.measured.role, ROLE_MEASURED)
        self.assertEqual(document.planned_cost.role, ROLE_DESIGNED)
        dumped = document.to_dict()
        self.assertFalse(dumped["approved"])
        self.assertEqual(dumped["designed"]["role"], ROLE_DESIGNED)
        self.assertEqual(dumped["predicted"]["role"], ROLE_PREDICTED)


if __name__ == "__main__":
    unittest.main()
