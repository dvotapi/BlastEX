"""BDX-026: workstation meta API lists workflow, roles and freeze flags."""
import unittest

from api.services import design_service
from design.lifecycle import STATUS_APPROVED, STATUS_CLOSED


class WorkstationApiTests(unittest.TestCase):
    def test_workstation_meta_keeps_roles_and_workflow_apart(self):
        meta = design_service.workstation_meta()
        self.assertEqual(
            list(meta.workflow),
            [
                "survey",
                "geology",
                "pattern",
                "charge",
                "timing",
                "simulation",
                "execution",
                "intelligence",
                "scenarios",
                "report",
            ],
        )
        self.assertEqual(meta.role_codes["designed"], "DESIGNED")
        self.assertEqual(meta.role_codes["executed"], "EXECUTED")
        self.assertEqual(meta.role_codes["predicted"], "PREDICTED")
        self.assertEqual(meta.role_codes["measured"], "MEASURED")
        self.assertFalse(meta.auto_transition)
        self.assertFalse(meta.silent_unit_conversion)
        self.assertEqual(meta.display_units["mass"], "кг")
        self.assertEqual(meta.overlay_roles["movement"], "predicted")
        approved = next(item for item in meta.statuses if item.name == STATUS_APPROVED)
        self.assertTrue(approved.frozen_designed)
        self.assertFalse(approved.frozen_record)
        closed = next(item for item in meta.statuses if item.name == STATUS_CLOSED)
        self.assertTrue(closed.frozen_record)
        self.assertNotIn("designed", meta.mutations[STATUS_APPROVED])
        self.assertEqual(meta.mutations[STATUS_CLOSED], [])


if __name__ == "__main__":
    unittest.main()
