"""BDX-024: passport API stays a document, never an approval or rewrite."""
import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from api.schemas.design import BlastDesignSchema
from api.schemas.reporting import PassportBuildRequest
from api.services import reporting_service
from design.models import ROLE_DESIGNED, ROLE_PREDICTED
from design.persistence import save_design
from tests.scenario_fixtures import charged_design

TEAM_ID = "passport-api-team"


class PassportApiTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        patcher = patch("cost.persistence.data_root", return_value=Path(self._tmp.name))
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_lists_roles_without_approval(self):
        response = reporting_service.list_roles()
        self.assertEqual(response.roles, ["designed", "executed", "predicted", "measured"])
        self.assertFalse(response.approved)
        self.assertFalse(response.auto_approved)
        self.assertFalse(response.evaluates_code)
        self.assertFalse(response.silent_unit_conversion)

    def test_build_from_request_keeps_roles_and_design(self):
        design = charged_design("api-passport")
        payload = BlastDesignSchema(**design.to_dict())
        original = copy.deepcopy(payload.model_dump())
        document = reporting_service.build_from_request(
            PassportBuildRequest(
                design=payload,
                lump_size_mm=400.0,
                planned_cost={"total_amount_rub": 900000.0, "cost_per_m3": 60.0},
            )
        )
        self.assertFalse(document.approved)
        self.assertFalse(document.auto_approved)
        self.assertFalse(document.design_rewritten)
        self.assertEqual(document.designed["role"], ROLE_DESIGNED)
        self.assertEqual(document.predicted["role"], ROLE_PREDICTED)
        self.assertGreater(document.designed["hole_count"], 0)
        self.assertIsNotNone(document.predicted["x50_mm"])
        self.assertIsNotNone(document.predicted["ppv_mm_s"])
        cost_row = next(row for row in document.comparison if row["key"] == "total_amount_rub")
        self.assertEqual(cost_row["designed"], 900000.0)
        self.assertEqual(cost_row["roles"]["designed"], ROLE_DESIGNED)
        self.assertEqual(cost_row["roles"]["predicted"], ROLE_PREDICTED)
        self.assertEqual(payload.model_dump()["holes"], original["holes"])
        self.assertEqual(payload.model_dump()["loads"], original["loads"])

    def test_saved_plan_json_and_html(self):
        design = save_design(TEAM_ID, charged_design("saved-passport"))
        document = reporting_service.get_plan_passport(TEAM_ID, design.design_id)
        self.assertEqual(document.design_id, design.design_id)
        self.assertFalse(document.approved)
        html_text = reporting_service.export_plan_passport_html(TEAM_ID, design.design_id)
        self.assertIn(design.name, html_text)
        self.assertIn("DESIGNED", html_text)
        self.assertIn("PREDICTED", html_text)
        self.assertIn("MEASURED", html_text)
        self.assertIn("не утверждён автоматически", html_text.lower())


if __name__ == "__main__":
    unittest.main()
