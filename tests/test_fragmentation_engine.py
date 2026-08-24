"""Spatial fragmentation engine: regions, roles, heatmaps, Blast.py facade."""
import unittest

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
from simulation.fragmentation.engine import predict_design, predict_region
from simulation.fragmentation.maps import FRAGMENTATION_MAP_METRICS
from simulation.fragmentation.models import (
    ROLE_DESIGNED,
    ROLE_MEASURED,
    ROLE_PREDICTED,
    Calibration,
    DesignedFragmentationTarget,
    MeasuredFragmentation,
)
from simulation.fragmentation.regions import ExplosiveSpec, RockSpec


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

    def test_three_models_differ_in_distribution(self):
        design = _design_with_charges()
        kwargs = dict(
            lump_size_mm=400.0,
            default_rock=RockSpec("Гранит", 2.65, 150.0, 2.0),
            default_explosive=ExplosiveSpec("АНФО", 0.82, 3.8),
        )
        kuz = predict_design(design, model="kuznetsov", **kwargs)
        ram = predict_design(design, model="kuzram", **kwargs)
        sweb = predict_design(design, model="swebrec", **kwargs)
        self.assertEqual(kuz["holes"][0]["prediction"]["x50_mm"], ram["holes"][0]["prediction"]["x50_mm"])
        self.assertNotEqual(kuz["holes"][0]["prediction"]["x80_mm"], ram["holes"][0]["prediction"]["x80_mm"])
        self.assertEqual(sweb["holes"][0]["prediction"]["provenance"]["parameters"]["distribution"], "swebrec")

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


class BlastEngineRegressionTests(unittest.TestCase):
    def test_optimize_still_returns_x50_and_oversize(self):
        engine = BlastEngine(
            RockProperties("Габбро-диабаз", 2.9, 168, 2.2),
            ExplosiveProperties("ЭВЕРСИН Э-100", 1.12, 2.99),
            TargetParams(lump_size_mm=400, hole_diameter_mm=0, bench_height_m=10.0),
        )
        result = engine.optimize_blast(152, max_oversize_threshold=5.0)
        self.assertIn("x50_mm", result)
        self.assertIn("oversize_pct", result)
        self.assertGreater(result["x50_mm"], 0)
        self.assertGreaterEqual(result["oversize_pct"], 0)


if __name__ == "__main__":
    unittest.main()
