import unittest

from api.schemas.design import ChargeGenerateRequest
from api.services import design_service
from design.charge_templates import example_wet_dry_bottom_templates


def _hole_payload(water=None):
    return {
        "id": "1-01",
        "row": 0,
        "col": 0,
        "collar": {"x": 0.0, "y": 0.0, "z": 0.0},
        "toe": {"x": 0.0, "y": 0.0, "z": -11.0},
        "diameter_mm": 152.0,
        "subdrill_m": 1.0,
        "kind": "production",
        "source": "generated",
        "enabled": True,
        "intervals": [],
        "water_intervals": water or [],
        "measured_intervals": [],
        "measured_water_intervals": [],
    }


class ChargeApiTests(unittest.TestCase):
    def test_generate_without_templates_keeps_simple_charge(self):
        response = design_service.generate_charge(
            ChargeGenerateRequest(
                holes=[_hole_payload()],
                rules={"stemming_m": 3.0, "decking": "continuous"},
                explosive={"name": "АНФО", "density_t_m3": 0.82, "power_mj_kg": 3.8},
            )
        )
        self.assertEqual(response.total_holes_charged, 1)
        self.assertEqual([d.kind for d in response.loads[0].decks], ["stemming", "charge"])
        self.assertEqual(len(response.loads[0].primers), 1)
        self.assertEqual(len(response.loads[0].primer_items), 1)

    def test_generate_from_templates_splits_wet_dry_bottom(self):
        water = [{"from_m": 6.0, "to_m": 9.0, "condition": "wet", "role": "designed", "notes": "", "provenance": {}}]
        response = design_service.generate_charge(
            ChargeGenerateRequest(
                holes=[_hole_payload(water=water)],
                rules={
                    "stemming_m": 3.0,
                    "bottom_length_m": 2.0,
                    "templates": [t.to_dict() for t in example_wet_dry_bottom_templates()],
                },
                explosive={"name": "АНФО", "density_t_m3": 0.82, "power_mj_kg": 3.8},
                explosives=[
                    {"name": "АНФО", "density_t_m3": 0.82, "power_mj_kg": 3.8},
                    {"name": "Эмульсия плотная", "density_t_m3": 1.25, "power_mj_kg": 3.2},
                    {"name": "Эмульсия водоустойчивая", "density_t_m3": 1.15, "power_mj_kg": 3.1},
                ],
            )
        )
        keys = [d.explosive_key for d in response.loads[0].decks if d.mass_kg > 0]
        self.assertEqual(keys, ["АНФО", "Эмульсия водоустойчивая", "Эмульсия плотная"])
        self.assertGreater(response.total_charge_kg, 0)


if __name__ == "__main__":
    unittest.main()
