import unittest

from api.schemas.design import (
    EngineeringMapsRequest,
    HoleGeometryEditRequest,
    HoleInsertRequest,
    PatternGenerateRequest,
)
from api.services import design_service
from design.models import BlastDesign, BlockContour, Hole


def _contour_payload(width: float = 20.0, height: float = 20.0) -> dict:
    verts = [(0.0, 0.0), (width, 0.0), (width, height), (0.0, height)]
    return {
        "vertices": [{"x": x, "y": y, "z": 0.0} for x, y in verts],
        "free_faces": [[0, 1]],
        "bench": {"crest_z_m": 0.0, "toe_z_m": -10.0, "face_angle_deg": 90.0},
        "name": "Блок",
    }


class PatternApiTests(unittest.TestCase):
    def test_domain_dependent_pattern_uses_domain_spacing(self):
        contour = _contour_payload(40.0, 20.0)
        contour["free_faces"] = []
        response = design_service.generate_pattern(
            PatternGenerateRequest(
                contour=contour,
                params={
                    "pattern": "domain_dependent",
                    "spacing_a_m": 8.0,
                    "burden_b_m": 8.0,
                    "offset_from_face_m": 0.0,
                    "edge_margin_m": 0.0,
                },
                domains=[
                    {
                        "id": "D-hard",
                        "name": "hard",
                        "polygon": [
                            {"x": 0, "y": 0, "z": 0},
                            {"x": 20, "y": 0, "z": 0},
                            {"x": 20, "y": 20, "z": 0},
                            {"x": 0, "y": 20, "z": 0},
                        ],
                        "spacing_a_m": 4.0,
                        "burden_b_m": 4.0,
                        "priority": 2,
                    },
                    {
                        "id": "D-soft",
                        "name": "soft",
                        "polygon": [
                            {"x": 20, "y": 0, "z": 0},
                            {"x": 40, "y": 0, "z": 0},
                            {"x": 40, "y": 20, "z": 0},
                            {"x": 20, "y": 20, "z": 0},
                        ],
                        "spacing_a_m": 10.0,
                        "burden_b_m": 10.0,
                        "priority": 1,
                    },
                ],
            )
        )
        left = [h for h in response.holes if h.collar.x < 20]
        right = [h for h in response.holes if h.collar.x > 20]
        self.assertGreater(len(left), len(right))

    def test_maps_and_hole_edits(self):
        generated = design_service.generate_pattern(
            PatternGenerateRequest(
                contour=_contour_payload(),
                params={
                    "pattern": "rectangular",
                    "spacing_a_m": 5.0,
                    "burden_b_m": 5.0,
                    "offset_from_face_m": 0.0,
                    "edge_margin_m": 0.0,
                    "first_row_burden_m": 3.0,
                },
            )
        )
        self.assertGreater(generated.hole_count, 0)
        design = BlastDesign(
            design_id="api-maps",
            contour=BlockContour.from_dict(_contour_payload()),
            holes=[Hole.from_dict(h.model_dump()) for h in generated.holes],
        )
        maps = design_service.design_maps(EngineeringMapsRequest(design=design.to_dict()))
        self.assertEqual(len(maps.holes), generated.hole_count)
        self.assertIn("burden", maps.metrics)

        first = generated.holes[0]
        edited = design_service.edit_hole_geometry(
            HoleGeometryEditRequest(
                hole=first.model_dump(),
                patch={"depth_m": 14.0, "angle_deg": 12.0, "azimuth_deg": 45.0, "kind": "buffer"},
                contour=_contour_payload(),
            )
        )
        self.assertEqual(edited.hole.kind, "buffer")
        inserted = design_service.insert_hole(
            HoleInsertRequest(
                contour=_contour_payload(),
                x=7.0,
                y=8.0,
                params={"kind": "infill", "subdrill_m": 1.0},
                existing_holes=[h.model_dump() for h in generated.holes],
            )
        )
        self.assertEqual(inserted.hole.source, "manual")
        self.assertEqual(inserted.hole.kind, "infill")


if __name__ == "__main__":
    unittest.main()
