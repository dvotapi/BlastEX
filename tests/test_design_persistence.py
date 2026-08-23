import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from design.models import BenchSurface, BlockContour, BlastDesign, Point3
from design.persistence import (
    DesignNotFoundError,
    delete_design,
    list_designs,
    load_design,
    rename_design,
    save_design,
)

TEAM_ID = "test-team"


class DesignPersistenceRoundTripTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        patcher = patch("cost.persistence.data_root", return_value=Path(self._tmp.name))
        patcher.start()
        self.addCleanup(patcher.stop)

    def _sample_design(self) -> BlastDesign:
        return BlastDesign(
            design_id="",
            name="Тестовый блок",
            contour=BlockContour(
                vertices=[Point3(x=x, y=y, z=0.0) for x, y in [(0, 0), (10, 0), (10, 10), (0, 10)]],
                bench=BenchSurface(crest_z_m=0.0, toe_z_m=-10.0),
            ),
        )

    def test_save_assigns_id_and_round_trips(self):
        design = self._sample_design()
        saved = save_design(TEAM_ID, design)
        self.assertTrue(saved.design_id)
        self.assertTrue(saved.updated_at)

        loaded = load_design(TEAM_ID, saved.design_id)
        self.assertEqual(loaded.name, "Тестовый блок")
        self.assertEqual(len(loaded.contour.vertices), 4)
        self.assertEqual(loaded.version, saved.version)

    def test_list_designs_returns_summary(self):
        saved = save_design(TEAM_ID, self._sample_design())
        summaries = list_designs(TEAM_ID)
        self.assertEqual(len(summaries), 1)
        self.assertEqual(summaries[0].design_id, saved.design_id)
        self.assertEqual(summaries[0].name, "Тестовый блок")

    def test_rename_updates_name(self):
        saved = save_design(TEAM_ID, self._sample_design())
        renamed = rename_design(TEAM_ID, saved.design_id, "Новое имя")
        self.assertEqual(renamed.name, "Новое имя")
        self.assertEqual(load_design(TEAM_ID, saved.design_id).name, "Новое имя")

    def test_delete_removes_design(self):
        saved = save_design(TEAM_ID, self._sample_design())
        delete_design(TEAM_ID, saved.design_id)
        with self.assertRaises(DesignNotFoundError):
            load_design(TEAM_ID, saved.design_id)

    def test_load_missing_raises(self):
        with self.assertRaises(DesignNotFoundError):
            load_design(TEAM_ID, "no-such-id")

    def test_path_traversal_id_rejected(self):
        with self.assertRaises(DesignNotFoundError):
            load_design(TEAM_ID, "../secret")
        with self.assertRaises(DesignNotFoundError):
            delete_design(TEAM_ID, "../../outside")

    def test_designs_are_isolated_per_team(self):
        save_design(TEAM_ID, self._sample_design())
        self.assertEqual(list_designs("another-team"), [])

    def test_legacy_json_without_geology_loads(self):
        from design.persistence import design_path, ensure_designs_layout
        import json

        ensure_designs_layout(TEAM_ID)
        payload = {
            "design_id": "legacy01",
            "name": "Без геологии",
            "holes": [],
            "contour": {"vertices": [], "free_faces": [], "bench": {}, "name": "Блок"},
        }
        path = design_path(TEAM_ID, "legacy01")
        path.write_text(json.dumps(payload), encoding="utf-8")
        loaded = load_design(TEAM_ID, "legacy01")
        self.assertEqual(loaded.domains, [])
        self.assertIsNone(loaded.water_table_z_m)

    def test_charge_templates_round_trip_in_charge_rules(self):
        from design.charge_templates import example_wet_dry_bottom_templates
        from design.models import HoleLoad, Primer

        design = self._sample_design()
        design.charge_rules = {
            "stemming_m": 3.0,
            "bottom_length_m": 2.0,
            "templates": [item.to_dict() for item in example_wet_dry_bottom_templates()],
        }
        design.loads = [
            HoleLoad(
                hole_id="1-01",
                primers=[10.7],
                primer_items=[Primer(position_m=10.7, product="T-500", mass_kg=0.4, kind="booster")],
            )
        ]
        saved = save_design(TEAM_ID, design)
        loaded = load_design(TEAM_ID, saved.design_id)
        self.assertEqual(len(loaded.charge_rules["templates"]), 3)
        self.assertEqual(loaded.charge_rules["templates"][0]["id"], "T-bottom")
        self.assertEqual(loaded.loads[0].primer_items[0].kind, "booster")
        self.assertAlmostEqual(loaded.loads[0].primer_items[0].mass_kg, 0.4)

    def test_legacy_network_hydrates_v2_objects(self):
        import json
        from design.persistence import design_path, ensure_designs_layout

        ensure_designs_layout(TEAM_ID)
        payload = {
            "design_id": "legacy-net",
            "name": "Старая схема",
            "holes": [],
            "contour": {"vertices": [], "free_faces": [], "bench": {}, "name": "Блок"},
            "network": {
                "system": "nonel",
                "starters": ["1-01"],
                "connectors": [{"from_hole": "1-01", "to_hole": "1-02", "delay_ms": 25.0, "kind": "surface_nsi"}],
                "downhole_delay_ms": {"1-01": 500.0},
                "electronic_times_ms": {},
            },
        }
        path = design_path(TEAM_ID, "legacy-net")
        path.write_text(json.dumps(payload), encoding="utf-8")
        loaded = load_design(TEAM_ID, "legacy-net")
        self.assertEqual(loaded.network.starters, ["1-01"])
        self.assertEqual(len(loaded.network.starter_items), 1)
        self.assertEqual(loaded.network.starter_items[0].hole_id, "1-01")
        self.assertEqual(len(loaded.network.surface_connectors), 1)
        self.assertEqual(loaded.network.surface_connectors[0].to_hole, "1-02")
        self.assertEqual(loaded.network.downhole_connectors[0].delay_ms, 500.0)

    def test_initiation_v2_round_trip(self):
        from design.models import (
            Detonator,
            ElectronicChannel,
            FiringEvent,
            InitiationNetwork,
            Starter,
            SurfaceConnector,
        )

        design = self._sample_design()
        design.network = InitiationNetwork(
            system="electronic",
            timing_mode="expression",
            timing_expression="interval * row",
            starters=["1-01"],
            starter_items=[Starter(id="st-1", hole_id="1-01")],
            surface_connectors=[
                SurfaceConnector(id="sc-1", from_hole="1-01", to_hole="1-02", delay_ms=17.0, kind="electronic")
            ],
            detonators=[Detonator(id="det-1", hole_id="1-01", kind="electronic", channel_id="ch-1")],
            electronic_channels=[ElectronicChannel(id="ch-1", hole_id="1-01", time_ms=0.0)],
            firing_events=[FiringEvent(id="fire-1", hole_id="1-01", time_ms=0.0, level="hole")],
        )
        saved = save_design(TEAM_ID, design)
        loaded = load_design(TEAM_ID, saved.design_id)
        self.assertEqual(loaded.version, 5)
        self.assertEqual(loaded.network.timing_mode, "expression")
        self.assertEqual(loaded.network.timing_expression, "interval * row")
        self.assertEqual(loaded.network.detonators[0].channel_id, "ch-1")
        self.assertEqual(loaded.network.firing_events[0].level, "hole")
        self.assertEqual(loaded.network.connectors[0].to_hole, "1-02")


if __name__ == "__main__":
    unittest.main()
