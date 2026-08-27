import unittest

from api.exceptions import InvalidDesignError
from api.schemas.design import (
    AsChargedCompareRequest,
    AsChargedRecordRequest,
    PatternGenerateRequest,
)
from api.services import design_service


def _contour_payload(width: float = 24.0, height: float = 16.0) -> dict:
    verts = [(0.0, 0.0), (width, 0.0), (width, height), (0.0, height)]
    return {
        "vertices": [{"x": x, "y": y, "z": 0.0} for x, y in verts],
        "free_faces": [[0, 1]],
        "bench": {"crest_z_m": 0.0, "toe_z_m": -10.0, "face_angle_deg": 90.0},
        "name": "Блок",
    }


class AsChargedApiTests(unittest.TestCase):
    def _design(self) -> dict:
        holes = design_service.generate_pattern(
            PatternGenerateRequest(
                contour=_contour_payload(),
                params={
                    "pattern": "rectangular",
                    "spacing_a_m": 5.0,
                    "burden_b_m": 4.0,
                    "offset_from_face_m": 0.0,
                    "edge_margin_m": 0.0,
                    "diameter_mm": 152.0,
                    "subdrill_m": 1.0,
                },
            )
        ).holes
        first = holes[0]
        load = {
            "hole_id": first.id,
            "decks": [
                {"kind": "stemming", "from_m": 0.0, "to_m": 3.0, "explosive_key": "", "mass_kg": 0.0, "product": ""},
                {
                    "kind": "bulk_explosive",
                    "from_m": 3.0,
                    "to_m": 10.0,
                    "explosive_key": "ANFO",
                    "mass_kg": 70.0,
                    "product": "ANFO",
                },
            ],
            "total_charge_kg": 70.0,
            "influence_volume_m3": 0.0,
            "specific_q_kg_m3": 0.0,
            "primers": [9.5],
            "primer_items": [{"position_m": 9.5, "product": "T-500", "mass_kg": 0.4, "kind": "primer"}],
        }
        return {
            "design_id": "ac-api",
            "contour": _contour_payload(),
            "holes": [h.model_dump() for h in holes],
            "loads": [load],
            "as_charged_holes": [],
        }

    def test_record_returns_deviations_and_keeps_designed_load(self):
        design = self._design()
        first = design["holes"][0]
        designed_mass = design["loads"][0]["total_charge_kg"]
        designed_product = design["loads"][0]["decks"][1]["product"]
        response = design_service.record_as_charged(
            AsChargedRecordRequest(
                design=design,
                holes=[
                    {
                        "design_hole_id": first["id"],
                        "decks": [
                            {"kind": "stemming", "from_m": 0.0, "to_m": 2.5, "mass_kg": 0.0, "product": ""},
                            {
                                "kind": "bulk_explosive",
                                "from_m": 2.5,
                                "to_m": 10.2,
                                "mass_kg": 76.0,
                                "product": "Emulsion",
                                "explosive_key": "Emulsion",
                            },
                        ],
                        "primer_items": [{"position_m": 10.0, "product": "T-500", "mass_kg": 0.4, "kind": "primer"}],
                    }
                ],
            )
        )
        self.assertEqual(response.as_charged_count, 1)
        self.assertEqual(response.deviations[0].design_hole_id, first["id"])
        self.assertAlmostEqual(response.deviations[0].charge_mass_delta_kg, 6.0, places=3)
        self.assertTrue(response.deviations[0].product_mismatch)
        echoed_load = next(load for load in response.loads if load.hole_id == first["id"])
        self.assertAlmostEqual(echoed_load.total_charge_kg, designed_mass)
        self.assertEqual(echoed_load.decks[1].product, designed_product)
        echoed_hole = next(hole for hole in response.holes if hole.id == first["id"])
        self.assertEqual(echoed_hole.collar.model_dump(), first["collar"])

    def test_compare_reads_stored_as_charged(self):
        design = self._design()
        first = design["holes"][0]
        recorded = design_service.record_as_charged(
            AsChargedRecordRequest(
                design=design,
                holes=[
                    {
                        "design_hole_id": first["id"],
                        "charge_mass_kg": 70.0,
                        "stemming_length_m": 3.0,
                        "explosive_product": "ANFO",
                        "decks": design["loads"][0]["decks"],
                        "primer_items": design["loads"][0]["primer_items"],
                    }
                ],
            )
        )
        design["as_charged_holes"] = [item.model_dump() for item in recorded.as_charged_holes]
        compared = design_service.compare_as_charged(AsChargedCompareRequest(design=design))
        self.assertEqual(compared.compared_count, 1)
        self.assertAlmostEqual(compared.deviations[0].charge_mass_delta_kg, 0.0)

    def test_unknown_design_hole_is_invalid(self):
        design = self._design()
        with self.assertRaises(InvalidDesignError):
            design_service.record_as_charged(
                AsChargedRecordRequest(
                    design=design,
                    holes=[{"design_hole_id": "no-such-hole", "charge_mass_kg": 10.0}],
                )
            )


if __name__ == "__main__":
    unittest.main()
