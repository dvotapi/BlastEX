"""api.routers.cost: калькуляторы бурения и ФОТ дают те же цифры, что и
прежние Streamlit-калькуляторы (cost/drilling_ui.py, cost/labor_ui.py)."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import cost.persistence as persistence
from api.schemas.cost import (
    DrillingUnitCalculateRequest,
    DrillingUnitCostInputSchema,
    JobPositionSchema,
    LaborAssignmentSchema,
    LaborCalculateRequest,
)
from api.services.cost_service import calculate_drilling_unit, calculate_labor
from cost.drilling import DEFAULT_DRILLING_PRICE_PER_M
from cost.labor import LaborFOTSettings, calculate_labor_fot, labor_assignments_from_records, labor_catalog_from_records


class DrillingUnitCalculatorTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        patcher = patch.object(persistence, "data_root", return_value=Path(self._tmp.name))
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_default_input_matches_excel_reference_price(self):
        request = DrillingUnitCalculateRequest(input=DrillingUnitCostInputSchema())
        response = calculate_drilling_unit(request, team_id="default")
        self.assertAlmostEqual(response.result.price_per_m, DEFAULT_DRILLING_PRICE_PER_M)
        self.assertTrue(response.summary_rows)


class LaborCalculatorTests(unittest.TestCase):
    def test_matches_direct_engine_call(self):
        catalog_records = [
            {"id": "p1", "name": "Мастер", "fixed_salary_monthly": 80_000.0, "piece_rate_per_m3": 0.25}
        ]
        assignment_records = [
            {"id": "a1", "position_id": "p1", "headcount": 1.0, "volume_m3": 30_000.0, "employee_shifts": 5.0}
        ]
        request = LaborCalculateRequest(
            labor_catalog=[JobPositionSchema(**catalog_records[0])],
            labor_assignments=[LaborAssignmentSchema(**assignment_records[0])],
        )
        response = calculate_labor(request)

        expected = calculate_labor_fot(
            catalog=labor_catalog_from_records(catalog_records),
            assignments=labor_assignments_from_records(assignment_records),
            settings=LaborFOTSettings(),
        )
        self.assertAlmostEqual(response.result.total_fot, expected.total_fot)
        self.assertEqual(len(response.table_rows), 1)


if __name__ == "__main__":
    unittest.main()
