import unittest

from design.models import (
    DESIGN_VERSION,
    BlastDesign,
    BlastDomain,
    DataProvenance,
    Hole,
    HoleInterval,
    Point3,
    RockPropertySet,
    WaterInterval,
)


class RockPropertySetTests(unittest.TestCase):
    def test_round_trip_keeps_optional_fields(self):
        props = RockPropertySet(
            density_kg_m3=2700.0,
            ucs_mpa=120.0,
            fracturing="moderate",
            rqd_pct=72.0,
            youngs_modulus_gpa=45.0,
            poisson_ratio=0.25,
            p_wave_velocity_m_s=4500.0,
            joint_spacing_m=0.8,
            joint_dip_deg=65.0,
            joint_dip_direction_deg=210.0,
            blastability="medium",
            water_condition="moist",
        )
        restored = RockPropertySet.from_dict(props.to_dict())
        self.assertEqual(restored, props)

    def test_missing_fields_stay_empty(self):
        restored = RockPropertySet.from_dict({})
        self.assertIsNone(restored.density_kg_m3)
        self.assertIsNone(restored.ucs_mpa)
        self.assertEqual(restored.water_condition, "")

    def test_ucs_pa_is_explicit_conversion(self):
        props = RockPropertySet(ucs_mpa=2.5)
        self.assertAlmostEqual(props.ucs_pa(), 2_500_000.0)
        self.assertAlmostEqual(RockPropertySet.ucs_mpa_from_pa(2_500_000.0), 2.5)

    def test_youngs_modulus_pa_is_explicit_conversion(self):
        props = RockPropertySet(youngs_modulus_gpa=40.0)
        self.assertAlmostEqual(props.youngs_modulus_pa(), 40_000_000_000.0)
        self.assertAlmostEqual(RockPropertySet.youngs_modulus_gpa_from_pa(40_000_000_000.0), 40.0)


class GeologySerializationTests(unittest.TestCase):
    def test_old_design_loads_without_geology(self):
        data = {
            "design_id": "legacy",
            "name": "Старый паспорт",
            "contour": {
                "vertices": [{"x": 0, "y": 0, "z": 0}, {"x": 10, "y": 0, "z": 0}, {"x": 10, "y": 10, "z": 0}],
                "free_faces": [],
                "bench": {"crest_z_m": 0.0, "toe_z_m": -10.0, "face_angle_deg": 90.0},
                "name": "Блок",
            },
            "holes": [
                {
                    "id": "1-01",
                    "row": 0,
                    "col": 0,
                    "collar": {"x": 5, "y": 5, "z": 0},
                    "toe": {"x": 5, "y": 5, "z": -11},
                    "diameter_mm": 152,
                }
            ],
        }
        design = BlastDesign.from_dict(data)
        self.assertEqual(design.domains, [])
        self.assertIsNone(design.water_table_z_m)
        hole = design.holes[0]
        self.assertEqual(hole.intervals, [])
        self.assertEqual(hole.water_intervals, [])
        self.assertEqual(hole.measured_intervals, [])
        self.assertEqual(hole.measured_water_intervals, [])

    def test_domain_and_intervals_round_trip(self):
        domain = BlastDomain(
            id="D-w",
            name="weathered",
            polygon=[Point3(0, 0, 0), Point3(10, 0, 0), Point3(10, 10, 0), Point3(0, 10, 0)],
            properties=RockPropertySet(density_kg_m3=2200.0, blastability="high"),
            provenance=DataProvenance(source="engineer", method="manual", role="designed"),
            z_top_m=0.0,
            z_bottom_m=-3.0,
            priority=1,
            color="#c4a574",
            spacing_a_m=4.5,
            burden_b_m=3.5,
        )
        hole = Hole(
            id="1-01",
            row=0,
            col=0,
            collar=Point3(5, 5, 0),
            toe=Point3(5, 5, -11),
            diameter_mm=152,
            intervals=[
                HoleInterval(from_m=0.0, to_m=3.0, domain_id="D-w", domain_name="weathered"),
            ],
            water_intervals=[WaterInterval(from_m=8.0, to_m=11.0, condition="wet")],
            measured_intervals=[
                HoleInterval(from_m=0.0, to_m=2.5, domain_name="core log", role="measured"),
            ],
        )
        design = BlastDesign(design_id="g1", name="Геология", holes=[hole], domains=[domain])
        restored = BlastDesign.from_dict(design.to_dict())
        self.assertEqual(len(restored.domains), 1)
        self.assertEqual(restored.domains[0].name, "weathered")
        self.assertEqual(restored.domains[0].properties.density_kg_m3, 2200.0)
        self.assertAlmostEqual(restored.domains[0].spacing_a_m, 4.5)
        self.assertAlmostEqual(restored.domains[0].burden_b_m, 3.5)
        self.assertEqual(restored.holes[0].intervals[0].domain_id, "D-w")
        self.assertEqual(restored.holes[0].water_intervals[0].condition, "wet")
        self.assertEqual(restored.holes[0].measured_intervals[0].role, "measured")
        self.assertEqual(restored.version, DESIGN_VERSION)

    def test_swapped_interval_bounds_are_normalized(self):
        interval = HoleInterval.from_dict({"from_m": 8, "to_m": 3, "domain_name": "x"})
        self.assertEqual(interval.from_m, 3.0)
        self.assertEqual(interval.to_m, 8.0)


if __name__ == "__main__":
    unittest.main()
