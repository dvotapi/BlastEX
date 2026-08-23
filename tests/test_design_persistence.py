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
        self.assertEqual(loaded.version, 8)
        self.assertEqual(loaded.network.timing_mode, "expression")
        self.assertEqual(loaded.network.timing_expression, "interval * row")
        self.assertEqual(loaded.network.detonators[0].channel_id, "ch-1")
        self.assertEqual(loaded.network.firing_events[0].level, "hole")
        self.assertEqual(loaded.network.connectors[0].to_hole, "1-02")

    def test_receptors_and_vibration_round_trip(self):
        from design.models import Receptor, VibrationMeasurement, VibrationModel

        design = self._sample_design()
        design.receptors = [
            Receptor(id="R-1", name="Офис", kind="building", location=Point3(x=80.0, y=10.0, z=0.0), ppv_limit_mm_s=5.0)
        ]
        design.vibration_models = [
            VibrationModel(
                id="vm-site",
                k=180.0,
                n=1.5,
                scaled_distance="r_over_q_sqrt",
                calibration_source="кампания 2024",
                confidence=0.7,
            )
        ]
        design.vibration_measurements = [
            VibrationMeasurement(id="VM-1", receptor_id="R-1", ppv_mm_s=3.2, source="сейсмопост", scaled_distance="r_over_q_sqrt")
        ]
        saved = save_design(TEAM_ID, design)
        loaded = load_design(TEAM_ID, saved.design_id)
        self.assertEqual(loaded.receptors[0].kind, "building")
        self.assertAlmostEqual(loaded.receptors[0].ppv_limit_mm_s or 0.0, 5.0)
        self.assertEqual(loaded.vibration_models[0].scaled_distance, "r_over_q_sqrt")
        self.assertEqual(loaded.vibration_measurements[0].role, "measured")
        self.assertAlmostEqual(loaded.vibration_measurements[0].ppv_mm_s, 3.2)

    def test_legacy_json_without_vibration_loads(self):
        import json
        from design.persistence import design_path, ensure_designs_layout

        ensure_designs_layout(TEAM_ID)
        payload = {
            "design_id": "legacy-vib",
            "name": "Без сейсмики",
            "holes": [],
            "contour": {"vertices": [], "free_faces": [], "bench": {}, "name": "Блок"},
        }
        path = design_path(TEAM_ID, "legacy-vib")
        path.write_text(json.dumps(payload), encoding="utf-8")
        loaded = load_design(TEAM_ID, "legacy-vib")
        self.assertEqual(loaded.receptors, [])
        self.assertEqual(loaded.vibration_models, [])
        self.assertEqual(loaded.vibration_measurements, [])
        self.assertEqual(loaded.as_drilled_holes, [])
        self.assertEqual(loaded.as_charged_holes, [])
        self.assertEqual(loaded.as_fired_holes, [])
        self.assertIsNone(loaded.blast_result)

    def test_as_drilled_round_trip_keeps_designed_holes(self):
        from design.models import AsDrilledHole, Hole

        design = self._sample_design()
        designed = Hole(
            id="1-01",
            row=1,
            col=1,
            collar=Point3(x=2.0, y=3.0, z=0.0),
            toe=Point3(x=2.0, y=3.0, z=-11.0),
            diameter_mm=152.0,
        )
        design.holes = [designed]
        design.as_drilled_holes = [
            AsDrilledHole(
                design_hole_id="1-01",
                actual_collar=Point3(x=2.4, y=3.1, z=0.0),
                actual_toe=Point3(x=2.6, y=3.3, z=-11.2),
                actual_depth=11.25,
                actual_diameter=165.0,
            )
        ]
        saved = save_design(TEAM_ID, design)
        loaded = load_design(TEAM_ID, saved.design_id)
        self.assertEqual(loaded.holes[0].collar.to_dict(), {"x": 2.0, "y": 3.0, "z": 0.0})
        self.assertEqual(loaded.holes[0].toe.to_dict(), {"x": 2.0, "y": 3.0, "z": -11.0})
        self.assertAlmostEqual(loaded.holes[0].diameter_mm, 152.0)
        self.assertEqual(loaded.as_drilled_holes[0].role, "executed")
        self.assertAlmostEqual(loaded.as_drilled_holes[0].actual_collar.x, 2.4)
        self.assertEqual(loaded.as_drilled_holes[0].actual_diameter, 165.0)

    def test_as_charged_and_as_fired_round_trip_keeps_designed_load_and_network(self):
        from design.models import (
            AsChargedHole,
            AsFiredHole,
            Deck,
            Detonator,
            Hole,
            HoleLoad,
            Primer,
        )

        design = self._sample_design()
        designed = Hole(
            id="1-01",
            row=1,
            col=1,
            collar=Point3(x=2.0, y=3.0, z=0.0),
            toe=Point3(x=2.0, y=3.0, z=-11.0),
            diameter_mm=152.0,
        )
        design.holes = [designed]
        design.loads = [
            HoleLoad(
                hole_id="1-01",
                decks=[
                    Deck(kind="stemming", from_m=0, to_m=3.0),
                    Deck(kind="bulk_explosive", from_m=3.0, to_m=11.0, mass_kg=80.0, product="ANFO"),
                ],
                total_charge_kg=80.0,
                primer_items=[Primer(position_m=10.5, product="T-500", mass_kg=0.4)],
            )
        ]
        design.network.detonators = [Detonator(id="det-1", hole_id="1-01", product="i-kon", kind="electronic")]
        design.network.electronic_times_ms = {"1-01": 25.0}
        design.as_charged_holes = [
            AsChargedHole(
                design_hole_id="1-01",
                decks=[
                    Deck(kind="stemming", from_m=0, to_m=2.8),
                    Deck(kind="bulk_explosive", from_m=2.8, to_m=11.1, mass_kg=84.0, product="Emulsion"),
                ],
                explosive_product="Emulsion",
                charge_mass_kg=84.0,
                stemming_length_m=2.8,
                primer_items=[Primer(position_m=10.8, product="T-500", mass_kg=0.45)],
                loading_timestamp="2026-08-23T10:00:00+00:00",
            )
        ]
        design.as_fired_holes = [
            AsFiredHole(
                design_hole_id="1-01",
                detonator=Detonator(id="det-actual", hole_id="1-01", product="DaveyTronic", kind="electronic"),
                programmed_time_ms=27.0,
                verified_time_ms=27.4,
                firing_timestamp="2026-08-23T14:00:00+00:00",
            )
        ]
        saved = save_design(TEAM_ID, design)
        loaded = load_design(TEAM_ID, saved.design_id)
        self.assertAlmostEqual(loaded.loads[0].total_charge_kg, 80.0)
        self.assertEqual(loaded.loads[0].decks[1].product, "ANFO")
        self.assertEqual(loaded.network.detonators[0].product, "i-kon")
        self.assertAlmostEqual(loaded.network.electronic_times_ms["1-01"], 25.0)
        self.assertEqual(loaded.as_charged_holes[0].role, "executed")
        self.assertAlmostEqual(loaded.as_charged_holes[0].charge_mass_kg, 84.0)
        self.assertEqual(loaded.as_charged_holes[0].explosive_product, "Emulsion")
        self.assertEqual(loaded.as_fired_holes[0].role, "executed")
        self.assertAlmostEqual(loaded.as_fired_holes[0].programmed_time_ms, 27.0)
        self.assertAlmostEqual(loaded.as_fired_holes[0].verified_time_ms or 0.0, 27.4)
        self.assertEqual(loaded.as_fired_holes[0].detonator.product, "DaveyTronic")

    def test_blast_result_round_trip_keeps_predicted_separate(self):
        from design.blast_result import (
            ActualCost,
            BlastResult,
            ComparisonBasis,
            MeasuredMuckpile,
            MeasuredVibration,
            PlannedCost,
        )
        from design.models import Hole
        from simulation.fragmentation.models import (
            MeasuredFragmentation,
            ModelProvenance,
            PredictedFragmentation,
        )

        design = self._sample_design()
        design.holes = [
            Hole(
                id="1-01",
                row=1,
                col=1,
                collar=Point3(x=2.0, y=3.0, z=0.0),
                toe=Point3(x=2.0, y=3.0, z=-11.0),
                diameter_mm=152.0,
            )
        ]
        design.blast_result = BlastResult(
            design_id=design.design_id or "saved",
            fragmentation=MeasuredFragmentation(x20_mm=90.0, x50_mm=175.0, x80_mm=320.0, oversize_pct=6.0, source="sieve"),
            vibration=MeasuredVibration(ppv_mm_s=3.5, frequency_hz=15.0, receptor_id="R-1"),
            muckpile=MeasuredMuckpile(length_m=41.0, width_m=17.0, height_m=6.2),
            cost_actual=ActualCost(total_amount_rub=1_900_000.0, cost_per_m3=95.0),
            basis=ComparisonBasis(
                predicted_fragmentation=PredictedFragmentation(
                    x20_mm=80.0,
                    x50_mm=150.0,
                    x80_mm=280.0,
                    oversize_pct=4.0,
                    powder_factor_kg_m3=0.7,
                    provenance=ModelProvenance(model="kuzram", model_version="1"),
                ),
                planned_cost=PlannedCost(total_amount_rub=1_600_000.0, cost_per_m3=80.0),
            ),
        )
        saved = save_design(TEAM_ID, design)
        loaded = load_design(TEAM_ID, saved.design_id)
        self.assertEqual(loaded.holes[0].collar.to_dict(), {"x": 2.0, "y": 3.0, "z": 0.0})
        self.assertEqual(loaded.blast_result.role, "measured")
        self.assertEqual(loaded.blast_result.fragmentation.role, "measured")
        self.assertAlmostEqual(loaded.blast_result.fragmentation.x50_mm, 175.0)
        self.assertEqual(loaded.blast_result.basis.predicted_fragmentation.role, "predicted")
        self.assertAlmostEqual(loaded.blast_result.basis.predicted_fragmentation.x50_mm, 150.0)
        self.assertEqual(loaded.blast_result.basis.planned_cost.role, "designed")
        self.assertAlmostEqual(loaded.blast_result.vibration.frequency_hz, 15.0)

    def test_legacy_json_without_blast_result_loads(self):
        import json
        from design.persistence import design_path, ensure_designs_layout

        ensure_designs_layout(TEAM_ID)
        payload = {
            "design_id": "legacy-br",
            "name": "Без результатов",
            "holes": [],
            "contour": {"vertices": [], "free_faces": [], "bench": {}, "name": "Блок"},
        }
        path = design_path(TEAM_ID, "legacy-br")
        path.write_text(json.dumps(payload), encoding="utf-8")
        loaded = load_design(TEAM_ID, "legacy-br")
        self.assertIsNone(loaded.blast_result)


if __name__ == "__main__":
    unittest.main()
