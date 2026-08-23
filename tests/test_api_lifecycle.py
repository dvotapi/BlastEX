"""BDX-025: lifecycle API is human-gated and does not auto-transition."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from api.exceptions import FrozenDesignError, InvalidLifecycleError
from api.schemas.design import BlastDesignSchema, DesignForkRequest, LifecycleTransitionRequest
from api.schemas.recommendation import RecommendationRequest
from api.schemas.scenarios import ScenarioCreateRequest, ScenarioParamsSchema
from api.services import design_service, recommendation_service, scenario_service
from design.lifecycle import STATUS_APPROVED, STATUS_CLOSED, STATUS_DRAFT, STATUS_EXECUTED, STATUS_IN_REVIEW
from design.models import BlastDesign
from design.persistence import load_design
from tests.scenario_fixtures import charged_design

TEAM_ID = "api-lifecycle-team"


class LifecycleApiTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        patcher = patch("cost.persistence.data_root", return_value=Path(self._tmp.name))
        patcher.start()
        self.addCleanup(patcher.stop)

    def _create(self) -> BlastDesignSchema:
        payload = BlastDesignSchema(**charged_design("api-life").to_dict())
        payload.lifecycle_status = STATUS_APPROVED
        return design_service.create_plan(TEAM_ID, payload, actor="engineer@mine")

    def _transition(self, design_id: str, to_status: str) -> None:
        design_service.transition_plan(
            TEAM_ID,
            design_id,
            LifecycleTransitionRequest(to_status=to_status, confirm=True, note="ok"),
            actor="lead@mine",
        )

    def test_meta_lists_statuses_and_keeps_data_roles_apart(self):
        meta = design_service.lifecycle_meta()
        self.assertFalse(meta.auto_transition)
        names = [item.name for item in meta.statuses]
        self.assertEqual(names, ["draft", "in_review", "approved", "executed", "closed"])
        self.assertEqual(meta.data_roles["designed"], "designed")
        self.assertEqual(meta.data_roles["executed"], "executed")
        self.assertEqual(meta.data_roles["predicted"], "predicted")
        self.assertEqual(meta.data_roles["measured"], "measured")
        approved = next(item for item in meta.statuses if item.name == "approved")
        self.assertTrue(approved.frozen_designed)
        self.assertFalse(approved.frozen_record)
        closed = next(item for item in meta.statuses if item.name == "closed")
        self.assertTrue(closed.frozen_record)

    def test_create_ignores_client_status_and_starts_as_draft(self):
        created = self._create()
        self.assertEqual(created.lifecycle_status, STATUS_DRAFT)
        self.assertEqual(created.revision, 1)
        self.assertTrue(created.designed_sha256)
        self.assertEqual(created.lifecycle_events[0].kind, "created")
        listed = design_service.list_plans(TEAM_ID)
        self.assertEqual(listed.items[0].lifecycle_status, STATUS_DRAFT)

    def test_transition_requires_confirm_and_actor(self):
        created = self._create()
        with self.assertRaises(InvalidLifecycleError):
            design_service.transition_plan(
                TEAM_ID,
                created.design_id,
                LifecycleTransitionRequest(to_status=STATUS_IN_REVIEW, confirm=False),
                actor="lead@mine",
            )
        with self.assertRaises(InvalidLifecycleError):
            design_service.transition_plan(
                TEAM_ID,
                created.design_id,
                LifecycleTransitionRequest(to_status=STATUS_IN_REVIEW, confirm=True),
                actor="system",
            )
        state = design_service.transition_plan(
            TEAM_ID,
            created.design_id,
            LifecycleTransitionRequest(to_status=STATUS_IN_REVIEW, confirm=True),
            actor="lead@mine",
        )
        self.assertEqual(state.lifecycle_status, STATUS_IN_REVIEW)
        self.assertEqual(state.allowed_transitions, [STATUS_DRAFT, STATUS_APPROVED])
        self.assertTrue(state.frozen_designed)

    def test_save_after_approve_rejects_designed_rewrite(self):
        created = self._create()
        self._transition(created.design_id, STATUS_IN_REVIEW)
        self._transition(created.design_id, STATUS_APPROVED)
        mutated = BlastDesign.from_dict(created.model_dump())
        mutated.design_id = created.design_id
        mutated.holes[0].diameter_mm = 250.0
        with self.assertRaises(FrozenDesignError):
            design_service.save_plan(
                TEAM_ID, created.design_id, BlastDesignSchema(**mutated.to_dict()), actor="overlay"
            )
        loaded = design_service.get_plan(TEAM_ID, created.design_id)
        self.assertAlmostEqual(loaded.holes[0].diameter_mm, created.holes[0].diameter_mm)
        self.assertEqual(loaded.lifecycle_status, STATUS_APPROVED)

    def test_scenario_and_recommendation_leave_approved_passport_untouched(self):
        created = self._create()
        self._transition(created.design_id, STATUS_IN_REVIEW)
        self._transition(created.design_id, STATUS_APPROVED)
        before = load_design(TEAM_ID, created.design_id)
        holes_before = [hole.to_dict() for hole in before.holes]
        status_before = before.lifecycle_status
        sha_before = before.designed_sha256

        scenario = scenario_service.create_scenario(
            TEAM_ID,
            ScenarioCreateRequest(
                design=BlastDesignSchema(**before.to_dict()),
                name="Оверлей",
                params=ScenarioParamsSchema(diameter_mm=165, spacing_a_m=6.0, burden_b_m=5.0),
            ),
        )
        self.assertTrue(scenario.approved_unchanged)
        self.assertFalse(scenario.modifies_design)

        recommendation_service.run_recommendation(
            TEAM_ID,
            RecommendationRequest(
                design=BlastDesignSchema(**before.to_dict()),
                profile="balanced",
                target_x50_mm=180.0,
                max_candidates=4,
            ),
        )

        after = load_design(TEAM_ID, created.design_id)
        self.assertEqual(after.lifecycle_status, status_before)
        self.assertEqual(after.designed_sha256, sha_before)
        self.assertEqual([hole.to_dict() for hole in after.holes], holes_before)

    def test_fork_and_close(self):
        created = self._create()
        self._transition(created.design_id, STATUS_IN_REVIEW)
        self._transition(created.design_id, STATUS_APPROVED)
        self._transition(created.design_id, STATUS_EXECUTED)
        closed = design_service.transition_plan(
            TEAM_ID,
            created.design_id,
            LifecycleTransitionRequest(to_status=STATUS_CLOSED, confirm=True, note="архив"),
            actor="lead@mine",
        )
        self.assertEqual(closed.lifecycle_status, STATUS_CLOSED)
        self.assertTrue(closed.frozen_record)
        with self.assertRaises(FrozenDesignError):
            design_service.delete_plan(TEAM_ID, created.design_id)

        forked = design_service.fork_plan(
            TEAM_ID, created.design_id, DesignForkRequest(name="Ревизия"), actor="lead@mine"
        )
        self.assertEqual(forked.lifecycle_status, STATUS_DRAFT)
        self.assertEqual(forked.parent_design_id, created.design_id)
        self.assertNotEqual(forked.design_id, created.design_id)
        state = design_service.get_plan_lifecycle(TEAM_ID, created.design_id)
        self.assertEqual(state.lifecycle_status, STATUS_CLOSED)


if __name__ == "__main__":
    unittest.main()
