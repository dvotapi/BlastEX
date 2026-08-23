import unittest

from api.exceptions import InvalidDesignError
from api.schemas.design import BlastResultCompareRequest, BlastResultRecordRequest, PatternGenerateRequest
from api.services import design_service


def _contour_payload(width: float = 24.0, height: float = 16.0) -> dict:
    verts = [(0.0, 0.0), (width, 0.0), (width, height), (0.0, height)]
    return {
        "vertices": [{"x": x, "y": y, "z": 0.0} for x, y in verts],
        "free_faces": [[0, 1]],
        "bench": {"crest_z_m": 0.0, "toe_z_m": -10.0, "face_angle_deg": 90.0},
        "name": "Блок",
    }


class BlastResultApiTests(unittest.TestCase):
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
        return {
            "design_id": "br-api",
            "contour": _contour_payload(),
            "holes": [h.model_dump() for h in holes],
            "loads": [
                {
                    "hole_id": first.id,
                    "decks": [],
                    "total_charge_kg": 70.0,
                    "influence_volume_m3": 0.0,
                    "specific_q_kg_m3": 0.0,
                    "primers": [],
                    "primer_items": [],
                }
            ],
            "blast_result": None,
        }

    def test_record_returns_comparisons_and_keeps_design(self):
        design = self._design()
        first = design["holes"][0]
        designed_collar = first["collar"]
        designed_mass = design["loads"][0]["total_charge_kg"]
        response = design_service.record_blast_result(
            BlastResultRecordRequest(
                design=design,
                result={
                    "design_id": "br-api",
                    "fragmentation": {"x20_mm": 95, "x50_mm": 185, "x80_mm": 340, "oversize_pct": 6.2, "source": "image"},
                    "vibration": {"ppv_mm_s": 5.1, "frequency_hz": 14.0, "receptor_id": "R-1"},
                    "muckpile": {"length_m": 46, "width_m": 19, "height_m": 6.5, "volume_m3": 2400, "throw_m": 13},
                    "backbreak": {"max_m": 1.1, "mean_m": 0.6},
                    "toe_condition": {"condition": "heavy", "leftover_height_m": 0.5},
                    "cost_actual": {"total_amount_rub": 2_000_000, "cost_per_m3": 100},
                },
                predicted_fragmentation={
                    "x20_mm": 80,
                    "x50_mm": 150,
                    "x80_mm": 280,
                    "oversize_pct": 4.0,
                    "powder_factor_kg_m3": 0.7,
                    "curve": [],
                    "provenance": {"model": "kuzram", "model_version": "1", "inputs": {}, "parameters": {}, "calibration": {}},
                    "role": "predicted",
                },
                predicted_vibration=[{"receptor_id": "R-1", "ppv_mm_s": 3.8, "receptor_name": "Офис", "role": "predicted"}],
                planned_cost={"total_amount_rub": 1_700_000, "cost_per_m3": 85, "role": "designed"},
                designed_fragmentation={"lump_size_mm": 400, "max_oversize_pct": 5.0, "role": "designed"},
                designed_muckpile={"length_m": 40, "width_m": 16, "height_m": 6, "volume_m3": 2100, "throw_m": 10, "role": "designed"},
                designed_backbreak={"max_m": 0.5, "mean_m": 0.2, "role": "designed"},
                designed_toe_condition="clean",
            )
        )
        self.assertTrue(response.has_result)
        self.assertEqual(response.result.role, "measured")
        self.assertEqual(response.result.fragmentation.role, "measured")
        self.assertEqual(response.result.basis.predicted_fragmentation.role, "predicted")
        self.assertAlmostEqual(response.result.basis.predicted_fragmentation.x50_mm, 150.0)
        self.assertAlmostEqual(response.result.fragmentation.x50_mm, 185.0)
        p50 = next(row for row in response.predicted_vs_measured if row.metric == "p50_mm")
        self.assertAlmostEqual(p50.measured_minus_predicted, 35.0)
        total = next(row for row in response.planned_vs_actual_cost if row.metric == "total_amount_rub")
        self.assertAlmostEqual(total.actual_minus_designed, 300_000.0)
        echoed_hole = next(hole for hole in response.holes if hole.id == first["id"])
        self.assertEqual(echoed_hole.collar.model_dump(), designed_collar)
        echoed_load = next(load for load in response.loads if load.hole_id == first["id"])
        self.assertAlmostEqual(echoed_load.total_charge_kg, designed_mass)

    def test_compare_reads_stored_result(self):
        design = self._design()
        recorded = design_service.record_blast_result(
            BlastResultRecordRequest(
                design=design,
                result={"design_id": "br-api", "fragmentation": {"p50_mm": 170, "p80_mm": 300, "oversize_pct": 5}},
                predicted_fragmentation={
                    "x20_mm": 80,
                    "x50_mm": 150,
                    "x80_mm": 280,
                    "oversize_pct": 4.0,
                    "powder_factor_kg_m3": 0.7,
                    "curve": [],
                    "provenance": {"model": "kuzram", "model_version": "1", "inputs": {}, "parameters": {}, "calibration": {}},
                },
            )
        )
        design["blast_result"] = recorded.result.model_dump()
        compared = design_service.compare_blast_result(BlastResultCompareRequest(design=design))
        self.assertTrue(compared.has_result)
        p50 = next(row for row in compared.predicted_vs_measured if row.metric == "p50_mm")
        self.assertAlmostEqual(p50.measured, 170.0)
        self.assertEqual(compared.result.fragmentation.role, "measured")
        self.assertEqual(compared.result.basis.predicted_fragmentation.role, "predicted")

    def test_missing_design_id_is_invalid(self):
        with self.assertRaises(InvalidDesignError):
            design_service.record_blast_result(
                BlastResultRecordRequest(
                    design={"design_id": "", "holes": [], "contour": _contour_payload()},
                    result={"design_id": "", "fragmentation": {"x50_mm": 100}},
                )
            )


if __name__ == "__main__":
    unittest.main()
