"""BDX-025: Draft → In Review → Approved → Executed → Closed, with freeze and audit."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from design.lifecycle import (
    FrozenDesignError,
    InvalidLifecycleError,
    STATUS_APPROVED,
    STATUS_CLOSED,
    STATUS_DRAFT,
    STATUS_EXECUTED,
    STATUS_IN_REVIEW,
    allowed_transitions,
    designed_sha256,
    plan_transition,
)
from design.models import (
    ROLE_DESIGNED,
    ROLE_EXECUTED,
    ROLE_MEASURED,
    AsDrilledHole,
    BenchSurface,
    BlastDesign,
    BlockContour,
    Hole,
    Point3,
)
from design.persistence import (
    delete_design,
    fork_design,
    list_designs,
    load_design,
    rename_design,
    save_design,
    transition_design,
)
from design.blast_result import BlastResult

TEAM_ID = "lifecycle-team"


class DesignLifecycleTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        patcher = patch("cost.persistence.data_root", return_value=Path(self._tmp.name))
        patcher.start()
        self.addCleanup(patcher.stop)

    def _design(self, name: str = "Блок") -> BlastDesign:
        return BlastDesign(
            design_id="",
            name=name,
            contour=BlockContour(
                vertices=[Point3(x=x, y=y, z=0.0) for x, y in [(0, 0), (10, 0), (10, 10), (0, 10)]],
                bench=BenchSurface(crest_z_m=0.0, toe_z_m=-10.0),
            ),
            holes=[
                Hole(
                    id="1-01",
                    row=1,
                    col=1,
                    collar=Point3(x=2.0, y=3.0, z=0.0),
                    toe=Point3(x=2.0, y=3.0, z=-11.0),
                    diameter_mm=152.0,
                )
            ],
        )

    def _walk(self, design: BlastDesign, *statuses: str) -> BlastDesign:
        current = design
        for status in statuses:
            current = transition_design(
                TEAM_ID,
                current.design_id,
                to_status=status,
                actor="lead@mine",
                confirm=True,
            )
        return current

    def test_allowed_graph_is_sequential_with_review_withdraw(self):
        self.assertEqual(allowed_transitions(STATUS_DRAFT), [STATUS_IN_REVIEW])
        self.assertEqual(allowed_transitions(STATUS_IN_REVIEW), [STATUS_DRAFT, STATUS_APPROVED])
        self.assertEqual(allowed_transitions(STATUS_APPROVED), [STATUS_EXECUTED])
        self.assertEqual(allowed_transitions(STATUS_EXECUTED), [STATUS_CLOSED])
        self.assertEqual(allowed_transitions(STATUS_CLOSED), [])

    def test_new_design_is_draft_with_revision_and_audit(self):
        saved = save_design(TEAM_ID, self._design())
        self.assertEqual(saved.lifecycle_status, STATUS_DRAFT)
        self.assertEqual(saved.revision, 1)
        self.assertTrue(saved.designed_sha256)
        self.assertEqual(saved.designed_sha256, designed_sha256(saved))
        self.assertEqual(saved.lifecycle_events[0].kind, "created")
        self.assertEqual(saved.lifecycle_events[0].to_status, STATUS_DRAFT)
        summaries = list_designs(TEAM_ID)
        self.assertEqual(summaries[0].lifecycle_status, STATUS_DRAFT)
        self.assertEqual(summaries[0].revision, 1)

    def test_human_gate_rejects_auto_actor_and_missing_confirm(self):
        with self.assertRaises(InvalidLifecycleError):
            plan_transition(
                from_status=STATUS_DRAFT,
                to_status=STATUS_IN_REVIEW,
                actor="auto",
                confirm=True,
            )
        with self.assertRaises(InvalidLifecycleError):
            plan_transition(
                from_status=STATUS_DRAFT,
                to_status=STATUS_IN_REVIEW,
                actor="lead@mine",
                confirm=False,
            )

    def test_skip_and_reverse_transitions_are_rejected(self):
        saved = save_design(TEAM_ID, self._design())
        with self.assertRaises(InvalidLifecycleError):
            transition_design(
                TEAM_ID, saved.design_id, to_status=STATUS_APPROVED, actor="lead@mine", confirm=True
            )
        reviewed = self._walk(saved, STATUS_IN_REVIEW)
        approved = self._walk(reviewed, STATUS_APPROVED)
        with self.assertRaises(InvalidLifecycleError):
            transition_design(
                TEAM_ID, approved.design_id, to_status=STATUS_DRAFT, actor="lead@mine", confirm=True
            )
        with self.assertRaises(InvalidLifecycleError):
            transition_design(
                TEAM_ID, approved.design_id, to_status=STATUS_CLOSED, actor="lead@mine", confirm=True
            )

    def test_full_chain_writes_audit_trail(self):
        saved = save_design(TEAM_ID, self._design())
        closed = self._walk(
            saved, STATUS_IN_REVIEW, STATUS_APPROVED, STATUS_EXECUTED, STATUS_CLOSED
        )
        self.assertEqual(closed.lifecycle_status, STATUS_CLOSED)
        kinds = [item.kind for item in closed.lifecycle_events]
        self.assertEqual(kinds.count("transition"), 4)
        self.assertEqual(closed.lifecycle_events[-1].actor, "lead@mine")
        self.assertTrue(closed.lifecycle_events[-1].confirm)
        self.assertEqual(closed.lifecycle_events[-1].to_status, STATUS_CLOSED)
        self.assertNotEqual(closed.lifecycle_status, ROLE_DESIGNED)
        self.assertNotEqual(closed.lifecycle_status, ROLE_EXECUTED)
        self.assertNotEqual(closed.lifecycle_status, ROLE_MEASURED)

    def test_in_review_can_withdraw_to_edit_designed(self):
        saved = save_design(TEAM_ID, self._design())
        reviewed = self._walk(saved, STATUS_IN_REVIEW)
        reviewed.holes[0].diameter_mm = 165.0
        with self.assertRaises(FrozenDesignError):
            save_design(TEAM_ID, reviewed)
        withdrawn = transition_design(
            TEAM_ID, reviewed.design_id, to_status=STATUS_DRAFT, actor="lead@mine", confirm=True
        )
        withdrawn.holes[0].diameter_mm = 165.0
        updated = save_design(TEAM_ID, withdrawn)
        self.assertEqual(updated.revision, 2)
        self.assertAlmostEqual(updated.holes[0].diameter_mm, 165.0)
        self.assertEqual(updated.lifecycle_events[-1].kind, "revise")

    def test_approved_rejects_silent_designed_mutation(self):
        saved = save_design(TEAM_ID, self._design())
        approved = self._walk(saved, STATUS_IN_REVIEW, STATUS_APPROVED)
        before = designed_sha256(approved)
        approved.holes[0].diameter_mm = 200.0
        approved.holes[0].collar.x = 9.9
        with self.assertRaises(FrozenDesignError):
            save_design(TEAM_ID, approved)
        reloaded = load_design(TEAM_ID, approved.design_id)
        self.assertEqual(designed_sha256(reloaded), before)
        self.assertAlmostEqual(reloaded.holes[0].diameter_mm, 152.0)
        self.assertAlmostEqual(reloaded.holes[0].collar.x, 2.0)

    def test_approved_allows_execution_record_without_rewriting_designed(self):
        saved = save_design(TEAM_ID, self._design())
        approved = self._walk(saved, STATUS_IN_REVIEW, STATUS_APPROVED)
        before = designed_sha256(approved)
        approved.as_drilled_holes = [
            AsDrilledHole(
                design_hole_id="1-01",
                actual_collar=Point3(x=2.2, y=3.1, z=0.0),
                actual_toe=Point3(x=2.3, y=3.2, z=-11.1),
            )
        ]
        updated = save_design(TEAM_ID, approved)
        self.assertEqual(updated.lifecycle_status, STATUS_APPROVED)
        self.assertEqual(updated.designed_sha256, before)
        self.assertEqual(updated.revision, 1)
        self.assertEqual(updated.as_drilled_holes[0].role, ROLE_EXECUTED)
        self.assertAlmostEqual(updated.holes[0].collar.x, 2.0)
        self.assertEqual(updated.lifecycle_events[-1].kind, "record_execution")

    def test_closed_freezes_the_record(self):
        saved = save_design(TEAM_ID, self._design())
        closed = self._walk(saved, STATUS_IN_REVIEW, STATUS_APPROVED, STATUS_EXECUTED, STATUS_CLOSED)
        closed.name = "Нельзя"
        with self.assertRaises(FrozenDesignError):
            save_design(TEAM_ID, closed)
        closed = load_design(TEAM_ID, closed.design_id)
        closed.as_drilled_holes = [
            AsDrilledHole(
                design_hole_id="1-01",
                actual_collar=Point3(x=2.0, y=3.0, z=0.0),
                actual_toe=Point3(x=2.0, y=3.0, z=-11.0),
            )
        ]
        with self.assertRaises(FrozenDesignError):
            save_design(TEAM_ID, closed)
        closed = load_design(TEAM_ID, closed.design_id)
        closed.blast_result = BlastResult(design_id=closed.design_id)
        with self.assertRaises(FrozenDesignError):
            save_design(TEAM_ID, closed)
        with self.assertRaises(FrozenDesignError):
            rename_design(TEAM_ID, closed.design_id, "Ещё нет")
        with self.assertRaises(FrozenDesignError):
            delete_design(TEAM_ID, closed.design_id)
        with self.assertRaises(InvalidLifecycleError):
            transition_design(
                TEAM_ID, closed.design_id, to_status=STATUS_DRAFT, actor="lead@mine", confirm=True
            )
        self.assertEqual(load_design(TEAM_ID, closed.design_id).lifecycle_status, STATUS_CLOSED)

    def test_save_cannot_smuggle_a_status_change(self):
        saved = save_design(TEAM_ID, self._design())
        saved.lifecycle_status = STATUS_APPROVED
        stored = save_design(TEAM_ID, saved)
        self.assertEqual(stored.lifecycle_status, STATUS_DRAFT)

    def test_fork_opens_a_new_draft_with_parent_and_clean_execution(self):
        saved = save_design(TEAM_ID, self._design())
        approved = self._walk(saved, STATUS_IN_REVIEW, STATUS_APPROVED)
        approved.as_drilled_holes = [
            AsDrilledHole(
                design_hole_id="1-01",
                actual_collar=Point3(x=2.1, y=3.0, z=0.0),
                actual_toe=Point3(x=2.1, y=3.0, z=-11.0),
            )
        ]
        save_design(TEAM_ID, approved)
        forked = fork_design(TEAM_ID, approved.design_id, name="Новая версия", actor="lead@mine")
        self.assertNotEqual(forked.design_id, approved.design_id)
        self.assertEqual(forked.lifecycle_status, STATUS_DRAFT)
        self.assertEqual(forked.parent_design_id, approved.design_id)
        self.assertEqual(forked.revision, 1)
        self.assertEqual(forked.as_drilled_holes, [])
        self.assertEqual(forked.lifecycle_events[0].kind, "fork")
        self.assertAlmostEqual(forked.holes[0].diameter_mm, 152.0)
        original = load_design(TEAM_ID, approved.design_id)
        self.assertEqual(original.lifecycle_status, STATUS_APPROVED)
        self.assertEqual(len(original.as_drilled_holes), 1)

    def test_draft_can_be_deleted_approved_cannot(self):
        draft = save_design(TEAM_ID, self._design("Черновик"))
        approved = self._walk(save_design(TEAM_ID, self._design("Утверждённый")), STATUS_IN_REVIEW, STATUS_APPROVED)
        delete_design(TEAM_ID, draft.design_id)
        with self.assertRaises(FrozenDesignError):
            delete_design(TEAM_ID, approved.design_id)


if __name__ == "__main__":
    unittest.main()
