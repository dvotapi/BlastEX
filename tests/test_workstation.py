"""BDX-026: workstation contract keeps roles, units and lifecycle gates distinct."""
import unittest

from design.lifecycle import (
    MUTATION_DESIGNED,
    MUTATION_EXECUTION,
    MUTATION_MEASURED,
    ROLE_DESIGNED,
    ROLE_EXECUTED,
    ROLE_MEASURED,
    ROLE_PREDICTED,
    STATUS_APPROVED,
    STATUS_CLOSED,
    STATUS_DRAFT,
    STATUS_EXECUTED,
    STATUS_IN_REVIEW,
)
from design.workstation import (
    DISPLAY_UNITS,
    ROLE_CODES,
    SILENT_UNIT_CONVERSION,
    WORKFLOW_STAGES,
    freeze_message,
    listed_stages,
    listed_transitions,
    ui_can_delete,
    ui_can_edit_designed,
    ui_can_edit_execution,
    ui_can_edit_measured,
    ui_can_save,
    workstation_meta,
)


class WorkstationContractTests(unittest.TestCase):
    def test_workflow_follows_engineering_order(self):
        self.assertEqual(
            [stage["id"] for stage in WORKFLOW_STAGES],
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
        orders = [item["order"] for item in listed_stages()]
        self.assertEqual(orders, list(range(1, 11)))

    def test_role_codes_stay_uppercase_and_apart(self):
        self.assertEqual(ROLE_CODES[ROLE_DESIGNED], "DESIGNED")
        self.assertEqual(ROLE_CODES[ROLE_EXECUTED], "EXECUTED")
        self.assertEqual(ROLE_CODES[ROLE_PREDICTED], "PREDICTED")
        self.assertEqual(ROLE_CODES[ROLE_MEASURED], "MEASURED")
        self.assertEqual(len(set(ROLE_CODES.values())), 4)

    def test_stage_roles_do_not_mix_predicted_into_designed(self):
        by_id = {stage["id"]: stage for stage in listed_stages()}
        self.assertEqual(by_id["survey"]["role_code"], "DESIGNED")
        self.assertEqual(by_id["pattern"]["role_code"], "DESIGNED")
        self.assertEqual(by_id["charge"]["role_code"], "DESIGNED")
        self.assertEqual(by_id["simulation"]["role_code"], "PREDICTED")
        self.assertEqual(by_id["execution"]["role_code"], "EXECUTED")
        self.assertEqual(by_id["intelligence"]["role_code"], "PREDICTED")
        self.assertEqual(by_id["scenarios"]["role_code"], "PREDICTED")

    def test_approved_and_closed_are_not_silently_editable(self):
        self.assertTrue(ui_can_edit_designed(STATUS_DRAFT))
        self.assertFalse(ui_can_edit_designed(STATUS_IN_REVIEW))
        self.assertFalse(ui_can_edit_designed(STATUS_APPROVED))
        self.assertFalse(ui_can_edit_designed(STATUS_EXECUTED))
        self.assertFalse(ui_can_edit_designed(STATUS_CLOSED))

        self.assertTrue(ui_can_edit_execution(STATUS_APPROVED))
        self.assertTrue(ui_can_edit_measured(STATUS_APPROVED))
        self.assertTrue(ui_can_edit_execution(STATUS_EXECUTED))
        self.assertFalse(ui_can_edit_execution(STATUS_IN_REVIEW))
        self.assertFalse(ui_can_edit_execution(STATUS_CLOSED))
        self.assertFalse(ui_can_edit_measured(STATUS_CLOSED))

        self.assertFalse(ui_can_save(STATUS_CLOSED))
        self.assertFalse(ui_can_delete(STATUS_APPROVED))
        self.assertFalse(ui_can_delete(STATUS_CLOSED))
        self.assertTrue(ui_can_delete(STATUS_DRAFT))

    def test_freeze_message_names_the_role(self):
        approved = freeze_message(STATUS_APPROVED, MUTATION_DESIGNED)
        self.assertIn("DESIGNED", approved)
        self.assertIn("утверждён", approved)
        closed = freeze_message(STATUS_CLOSED, MUTATION_EXECUTION)
        self.assertIn("закрыт", closed)
        review = freeze_message(STATUS_IN_REVIEW, MUTATION_MEASURED)
        self.assertIn("MEASURED", review)

    def test_no_silent_unit_conversion(self):
        self.assertFalse(SILENT_UNIT_CONVERSION)
        self.assertEqual(DISPLAY_UNITS["mass"], "кг")
        self.assertEqual(DISPLAY_UNITS["diameter"], "мм")
        self.assertEqual(DISPLAY_UNITS["powder_factor"], "кг/м³")
        self.assertEqual(DISPLAY_UNITS["ppv"], "мм/с")
        self.assertNotIn("т", DISPLAY_UNITS.values())
        self.assertNotIn("t", DISPLAY_UNITS.values())

    def test_meta_exposes_human_gates_and_overlay_roles(self):
        meta = workstation_meta()
        self.assertFalse(meta["auto_transition"])
        self.assertFalse(meta["silent_unit_conversion"])
        self.assertEqual(meta["overlay_roles"]["fragmentation"], ROLE_PREDICTED)
        self.assertEqual(meta["overlay_roles"]["as_drilled"], ROLE_EXECUTED)
        self.assertEqual(meta["overlay_roles"]["post_blast"], ROLE_MEASURED)
        self.assertEqual(
            meta["overlay_roles"]["passport"],
            [ROLE_DESIGNED, ROLE_EXECUTED, ROLE_PREDICTED, ROLE_MEASURED],
        )
        labels = {(item["from_status"], item["to_status"]): item["label"] for item in listed_transitions()}
        self.assertEqual(labels[("draft", "in_review")], "На проверку")
        self.assertEqual(labels[("in_review", "approved")], "Утвердить")
        self.assertEqual(labels[("executed", "closed")], "Закрыть паспорт")


if __name__ == "__main__":
    unittest.main()
