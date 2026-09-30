"""Spatial fragmentation engine: regions, roles, heatmaps, Blast.py facade."""
import unittest
from dataclasses import asdict

from Blast import BlastEngine, ExplosiveProperties, RockProperties, TargetParams
from design.charging import apply_charge_rules
from design.geology import apply_domains_to_holes
from design.models import (
    BenchSurface,
    BlastDesign,
    BlastDomain,
    BlockContour,
    Point3,
    RockPropertySet,
)
from design.pattern import generate_pattern
from simulation.fragmentation.base import settings_from_snapshot, settings_snapshot
from simulation.fragmentation.cunningham import KuzRamSettings
from simulation.fragmentation.engine import is_legacy_model, list_models, predict_design, predict_region, resolve_model
from simulation.fragmentation.maps import FRAGMENTATION_MAP_METRICS
from simulation.fragmentation.models import (
    ROLE_DESIGNED,
    ROLE_MEASURED,
    ROLE_PREDICTED,
    Calibration,
    DesignedFragmentationTarget,
    MeasuredFragmentation,
)
from simulation.fragmentation.regions import ExplosiveSpec, RockSpec, collect_regions


def _contour() -> BlockContour:
    return BlockContour(
        vertices=[Point3(x=x, y=y, z=0.0) for x, y in [(0, 0), (24, 0), (24, 16), (0, 16)]],
        free_faces=[[0, 1]],
        bench=BenchSurface(crest_z_m=0.0, toe_z_m=-10.0),
    )


def _design_with_charges() -> BlastDesign:
    contour = _contour()
    holes = generate_pattern(
        contour,
        {
            "pattern": "rectangular",
            "spacing_a_m": 5.0,
            "burden_b_m": 4.0,
            "offset_from_face_m": 0.0,
            "edge_margin_m": 0.0,
            "diameter_mm": 152.0,
            "subdrill_m": 1.0,
        },
    )
    explosive = ExplosiveProperties("АНФО", 0.82, 3.8)
    loads = apply_charge_rules(
        holes,
        {"stemming_m": 3.0, "decking": "continuous", "grid_a_m": 5.0, "grid_b_m": 4.0},
        explosive,
        contour=contour,
    )
    return BlastDesign(
        design_id="frag",
        contour=contour,
        holes=holes,
        loads=loads,
        pattern_params={"spacing_a_m": 5.0, "burden_b_m": 4.0},
        charge_rules={"stemming_m": 3.0, "hole_oversize_coeff": 1.05, "grid_a_m": 5.0, "grid_b_m": 4.0},
        rock_name="Гранит",
        explosive_key="АНФО",
    )


class FragmentationEngineTests(unittest.TestCase):
    def test_predicts_site_holes_and_maps(self):
        design = _design_with_charges()
        result = predict_design(
            design,
            model="kuzram",
            lump_size_mm=400.0,
            default_rock=RockSpec("Гранит", 2.65, 150.0, 2.0),
            default_explosive=ExplosiveSpec("АНФО", 0.82, 3.8),
        )
        self.assertEqual(result["model"], "kuzram")
        self.assertTrue(result["model_version"])
        self.assertEqual(result["site"]["prediction"]["role"], ROLE_PREDICTED)
        self.assertEqual(result["target"]["role"], ROLE_DESIGNED)
        self.assertEqual(result["measured"], [])
        self.assertGreater(len(result["holes"]), 0)
        self.assertEqual(len(result["holes"]), len([h for h in design.holes if h.enabled]))
        site = result["site"]["prediction"]
        self.assertLess(site["x20_mm"], site["x50_mm"])
        self.assertLess(site["x50_mm"], site["x80_mm"])
        hole_x50 = result["holes"][0]["prediction"]["x50_mm"]
        self.assertAlmostEqual(site["x50_mm"], hole_x50, delta=1.0)
        self.assertIn("curve", site)
        self.assertGreater(len(site["curve"]), 5)
        provenance = site["provenance"]
        for key in ("model", "model_version", "inputs", "parameters", "calibration"):
            self.assertIn(key, provenance)
        self.assertEqual(list(result["maps"]["metrics"]), list(FRAGMENTATION_MAP_METRICS))
        sample = result["maps"]["holes"][0]
        for metric in FRAGMENTATION_MAP_METRICS:
            self.assertIn(metric, sample)
            self.assertIn(metric, result["maps"]["stats"])

    def _kwargs(self):
        return dict(
            lump_size_mm=400.0,
            default_rock=RockSpec("Гранит", 2.65, 150.0, 2.0),
            default_explosive=ExplosiveSpec("АНФО", 0.82, 3.8),
        )

    def test_new_models_share_cunningham_base(self):
        design = _design_with_charges()
        rows = {
            model: predict_design(design, model=model, **self._kwargs())["holes"][0]["prediction"]
            for model in ("kuznetsov", "kuzram", "swebrec")
        }
        self.assertEqual(len({row["x50_mm"] for row in rows.values()}), 1)
        self.assertEqual(len({row["provenance"]["parameters"]["rock_factor_A"] for row in rows.values()}), 1)
        self.assertNotEqual(rows["kuznetsov"]["x80_mm"], rows["kuzram"]["x80_mm"])
        self.assertEqual(rows["swebrec"]["provenance"]["parameters"]["distribution"], "swebrec")
        self.assertEqual({row["provenance"]["model_version"] for row in rows.values()}, {"2.0.0"})

    def test_legacy_models_keep_old_base(self):
        design = _design_with_charges()
        legacy = {
            model: predict_design(design, model=model, **self._kwargs())["holes"][0]["prediction"]
            for model in ("kuznetsov_legacy", "kuzram_legacy", "swebrec_legacy")
        }
        new = predict_design(design, model="kuzram", **self._kwargs())["holes"][0]["prediction"]
        self.assertEqual(len({row["x50_mm"] for row in legacy.values()}), 1)
        self.assertEqual({row["provenance"]["model_version"] for row in legacy.values()}, {"1.0.0"})
        self.assertNotEqual(legacy["kuzram_legacy"]["x50_mm"], new["x50_mm"])

    def test_model_version_has_one_source(self):
        design = _design_with_charges()
        for info in list_models():
            with self.subTest(model=info["id"]):
                result = predict_design(design, model=info["id"], **self._kwargs())
                self.assertEqual(result["model"], info["id"])
                self.assertEqual(result["model_version"], info["version"])
                self.assertEqual(result["site"]["prediction"]["provenance"]["model_version"], info["version"])

    def test_resolve_model_aliases(self):
        self.assertEqual(resolve_model("Kuz-Ram"), "kuzram")
        self.assertEqual(resolve_model(""), "kuzram")
        self.assertEqual(resolve_model("kuz-ram_legacy"), "kuzram_legacy")
        self.assertEqual(resolve_model("swebeck_legacy"), "swebrec_legacy")
        self.assertTrue(is_legacy_model("kuznetsov_legacy"))
        self.assertFalse(is_legacy_model("kuzram"))
        with self.assertRaises(ValueError) as ctx:
            resolve_model("ml-magic")
        self.assertIn("kuzram_legacy", str(ctx.exception))

    def test_measured_is_echoed_never_overwritten(self):
        design = _design_with_charges()
        measured = MeasuredFragmentation(x50_mm=90.0, x80_mm=180.0, source="sieve", method="lab")
        result = predict_design(
            design,
            model="kuzram",
            lump_size_mm=400.0,
            default_rock=RockSpec("Гранит", 2.65, 150.0, 2.0),
            default_explosive=ExplosiveSpec("АНФО", 0.82, 3.8),
            measured=[measured],
        )
        self.assertEqual(result["measured"][0]["role"], ROLE_MEASURED)
        self.assertEqual(result["measured"][0]["x50_mm"], 90.0)
        self.assertNotEqual(result["site"]["prediction"]["x50_mm"], 90.0)
        self.assertEqual(result["site"]["prediction"]["role"], ROLE_PREDICTED)
        self.assertNotEqual(result["holes"][0]["prediction"]["role"], ROLE_MEASURED)

    def test_geology_density_is_converted_from_kg_m3(self):
        design = _design_with_charges()
        domain = BlastDomain(
            id="D-hard",
            name="hard",
            properties=RockPropertySet(density_kg_m3=2700.0, ucs_mpa=140.0, fracturing="2.0"),
        )
        design.domains = [domain]
        design.holes = apply_domains_to_holes(design.holes, [domain])
        result = predict_design(
            design,
            model="kuznetsov",
            lump_size_mm=400.0,
            default_rock=RockSpec("fallback", 1.8, 40.0, 1.0),
            default_explosive=ExplosiveSpec("АНФО", 0.82, 3.8),
        )
        rock_density = result["holes"][0]["inputs"]["rock_density_t_m3"]
        self.assertAlmostEqual(rock_density, 2.7, places=3)
        self.assertNotAlmostEqual(rock_density, 2700.0)

    def test_domain_regions_are_grouped(self):
        design = _design_with_charges()
        left = BlastDomain(
            id="D-left",
            name="left",
            polygon=[Point3(x=x, y=y, z=0) for x, y in [(0, 0), (12, 0), (12, 16), (0, 16)]],
            properties=RockPropertySet(density_kg_m3=2200.0, ucs_mpa=80.0),
            priority=2,
        )
        right = BlastDomain(
            id="D-right",
            name="right",
            polygon=[Point3(x=x, y=y, z=0) for x, y in [(12, 0), (24, 0), (24, 16), (12, 16)]],
            properties=RockPropertySet(density_kg_m3=2800.0, ucs_mpa=160.0),
            priority=1,
        )
        design.holes = apply_domains_to_holes(design.holes, [left, right])
        result = predict_design(
            design,
            model="kuzram",
            lump_size_mm=400.0,
            default_rock=RockSpec("Гранит", 2.65, 150.0, 2.0),
            default_explosive=ExplosiveSpec("АНФО", 0.82, 3.8),
        )
        domain_ids = {row["id"] for row in result["regions"]}
        self.assertIn("domain:D-left", domain_ids)
        self.assertIn("domain:D-right", domain_ids)

    def test_designed_target_is_not_a_prediction(self):
        target = DesignedFragmentationTarget(lump_size_mm=400, max_oversize_pct=5)
        self.assertEqual(target.to_dict()["role"], ROLE_DESIGNED)

    def test_unknown_model_rejected(self):
        from tests.test_fragmentation_kuzram import _inputs

        with self.assertRaises(ValueError):
            predict_region(_inputs(), model="ml-magic")


class RegionLengthTests(unittest.TestCase):
    """Длина заряда нужна множителю L/H: без неё n новой модели берёт 1."""

    def _regions(self, design):
        return collect_regions(
            design,
            lump_size_mm=400.0,
            default_rock=RockSpec("Гранит", 2.65, 150.0, 2.0),
            default_explosive=ExplosiveSpec("АНФО", 0.82, 3.8),
        )

    def _hole_region(self, holes, hole_id):
        return next(region for region in holes if region.hole_ids == [hole_id])

    def test_charge_length_is_sum_of_explosive_decks(self):
        design = _design_with_charges()
        holes, _domains, site, _warnings = self._regions(design)

        region = self._hole_region(holes, design.loads[0].hole_id)

        # Скважина 11 м (уступ 10 + перебур 1), забойка 3 м, заряд 3–11 м.
        self.assertAlmostEqual(region.inputs.charge_length_m, 8.0)
        self.assertAlmostEqual(region.inputs.hole_length_m, 11.0)
        self.assertAlmostEqual(site.inputs.charge_length_m, 8.0)
        self.assertAlmostEqual(site.inputs.hole_length_m, 11.0)

    def test_air_gap_is_not_charge(self):
        design = _design_with_charges()
        charge = next(deck for deck in design.loads[0].decks if deck.kind == "charge")
        charge.to_m = 9.0  # заряд 3–9 м, ниже — пустота

        holes, *_ = self._regions(design)

        self.assertAlmostEqual(self._hole_region(holes, design.loads[0].hole_id).inputs.charge_length_m, 6.0)

    def test_without_decks_charge_is_hole_minus_stemming(self):
        design = _design_with_charges()
        hole_id = design.holes[0].id
        design.loads = []
        design.charge_rules = dict(design.charge_rules, stemming_m=2.5)

        holes, *_ = self._regions(design)

        self.assertAlmostEqual(self._hole_region(holes, hole_id).inputs.charge_length_m, 8.5)


KW = dict(
    lump_size_mm=400.0,
    default_rock=RockSpec("Гранит", 2.65, 150.0, 2.0),
    default_explosive=ExplosiveSpec("АНФО", 0.82, 3.8),
)


class EngineSettingsTests(unittest.TestCase):
    def test_defaults_snapshot(self):
        result = predict_design(_design_with_charges(), model="kuzram", **KW)

        self.assertEqual(result["settings"]["source"], "defaults")
        self.assertEqual(result["settings"]["values"], asdict(KuzRamSettings()))
        self.assertEqual(result["site"]["prediction"]["provenance"]["settings"], result["settings"])

    def test_settings_change_prediction_and_are_recorded(self):
        design = _design_with_charges()
        plain = predict_design(design, model="kuzram", **KW)
        tuned = predict_design(
            design,
            model="kuzram",
            settings=KuzRamSettings(rock_factor_correction=1.5),
            settings_source={"source": "work_object", "work_object_name": "Карьер-1"},
            **KW,
        )

        self.assertGreater(tuned["site"]["prediction"]["x50_mm"], plain["site"]["prediction"]["x50_mm"])
        snapshot = tuned["holes"][0]["prediction"]["provenance"]["settings"]
        self.assertEqual(snapshot["source"], "work_object")
        self.assertEqual(snapshot["work_object_name"], "Карьер-1")
        self.assertEqual(snapshot["values"]["rock_factor_correction"], 1.5)

    def test_settings_reach_holes_domains_and_block(self):
        design = _design_with_charges()
        plain = predict_design(design, model="kuzram", **KW)
        tuned = predict_design(design, model="kuzram", settings=KuzRamSettings(rock_factor_correction=1.5), **KW)

        self.assertGreater(tuned["holes"][0]["prediction"]["x50_mm"], plain["holes"][0]["prediction"]["x50_mm"])
        self.assertGreater(tuned["site"]["prediction"]["x50_mm"], plain["site"]["prediction"]["x50_mm"])
        for tuned_row, plain_row in zip(tuned["regions"], plain["regions"]):
            self.assertGreater(tuned_row["prediction"]["x50_mm"], plain_row["prediction"]["x50_mm"])

    def test_legacy_model_ignores_settings(self):
        design = _design_with_charges()
        plain = predict_design(design, model="kuzram_legacy", **KW)
        tuned = predict_design(design, model="kuzram_legacy", settings=KuzRamSettings(rock_factor_correction=1.5), **KW)

        self.assertEqual(tuned["site"]["prediction"]["x50_mm"], plain["site"]["prediction"]["x50_mm"])
        self.assertEqual(tuned["site"]["prediction"]["provenance"]["settings"], {})

    def test_resolution_warnings_reach_payload(self):
        result = predict_design(
            _design_with_charges(),
            model="kuzram",
            settings_source={"source": "defaults", "work_object_name": "Карьер-3", "warnings": ["Настройки не прочитаны."]},
            **KW,
        )

        self.assertIn("Настройки не прочитаны.", result["warnings"])

    def test_bad_hole_is_skipped_with_warning(self):
        design = _design_with_charges()
        load = design.loads[0]
        for deck in load.decks:
            if deck.kind == "charge":
                deck.explosive_key = "Пустышка"

        result = predict_design(
            design, model="kuzram", explosives={"Пустышка": ExplosiveSpec("Пустышка", 0.82, 0.0)}, **KW
        )

        self.assertNotIn(load.hole_id, [row["hole_ids"][0] for row in result["holes"]])
        self.assertEqual(len(result["holes"]), len(design.holes) - 1)
        self.assertTrue(
            any(
                item.startswith(f"Скважина {load.hole_id}: прогноз не посчитан") and "сила ВВ" in item
                for item in result["warnings"]
            )
        )

    def test_whole_block_failure_is_russian_error(self):
        with self.assertRaises(ValueError) as ctx:
            predict_design(
                _design_with_charges(),
                model="kuzram",
                lump_size_mm=400.0,
                default_rock=RockSpec("Гранит", 2.65, 150.0, 2.0),
                default_explosive=ExplosiveSpec("АНФО", 0.82, 0.0),
                explosives={"АНФО": ExplosiveSpec("АНФО", 0.82, 0.0)},
            )

        self.assertIn("по блоку не посчитан", str(ctx.exception))

    def test_missing_bench_height_warns_once(self):
        design = _design_with_charges()
        for hole in design.holes:
            hole.subdrill_m = hole.length_m  # паспорт без высоты уступа: H = 0

        result = predict_design(design, model="kuzram", **KW)

        lh = [item for item in result["warnings"] if "L/H" in item]
        self.assertEqual(len(lh), 1)
        self.assertIn(lh[0], result["holes"][0]["warnings"])

    def test_snapshot_round_trip(self):
        snapshot = settings_snapshot(
            KuzRamSettings(rock_factor_method="rmd10"), {"source": "work_object", "work_object_name": "Карьер-1"}
        )

        settings, source = settings_from_snapshot(snapshot)

        self.assertEqual(settings, KuzRamSettings(rock_factor_method="rmd10"))
        self.assertEqual(source, {"source": "work_object", "work_object_name": "Карьер-1", "warnings": []})
        self.assertEqual(settings_from_snapshot({}), (None, {}))


class BlastEngineRegressionTests(unittest.TestCase):
    def test_optimize_still_returns_x50_and_oversize(self):
        engine = BlastEngine(
            RockProperties("Габбро-диабаз", 2.9, 168, 2.2),
            ExplosiveProperties("ЭВЕРСИН Э-100", 1.12, 2.99),
            TargetParams(lump_size_mm=400, hole_diameter_mm=0, bench_height_m=10.0),
        )
        result = engine.optimize_blast(152, max_oversize_threshold=5.0)
        self.assertTrue(result.reached)
        self.assertGreater(result.point.x50_mm, 0)
        self.assertGreaterEqual(result.point.oversize_pct, 0)


if __name__ == "__main__":
    unittest.main()
