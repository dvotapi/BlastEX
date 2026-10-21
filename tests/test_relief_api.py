"""Темп отбойки в ответе анализа тайминга."""
import unittest

from api.schemas.design import AnalyzeRequest, PatternGenerateRequest, TieGenerateRequest
from api.services import design_service


def _contour_payload(width: float = 20.0, height: float = 16.0) -> dict:
    verts = [(0.0, 0.0), (width, 0.0), (width, height), (0.0, height)]
    return {
        "vertices": [{"x": x, "y": y, "z": 0.0} for x, y in verts],
        "free_faces": [[0, 1]],
        "bench": {"crest_z_m": 0.0, "toe_z_m": -10.0, "face_angle_deg": 90.0},
        "name": "Блок",
    }


def _analyze(height: float, rock_name: str = "", **kwargs):
    holes = design_service.generate_pattern(
        PatternGenerateRequest(
            contour=_contour_payload(height=height),
            params={
                "pattern": "rectangular",
                "spacing_a_m": 4.0,
                "burden_b_m": 4.0,
                "offset_from_face_m": 0.0,
                "edge_margin_m": 0.0,
            },
        )
    ).holes
    tie = design_service.generate_tie(
        TieGenerateRequest(
            holes=[h.model_dump() for h in holes],
            scheme="row",
            params={"system": "nonel", "surface_delay_ms": 25.0, "row_delay_ms": 42.0},
        )
    )
    return design_service.analyze_design(
        AnalyzeRequest(
            design={
                "design_id": "relief",
                "holes": [h.model_dump() for h in holes],
                "contour": _contour_payload(height=height),
                "network": tie.network.model_dump(),
                "loads": [],
                "rock_name": rock_name,
            }
        ),
        **kwargs,
    )


class ReliefApiTests(unittest.TestCase):
    def test_analyze_returns_burden_relief(self):
        relief = _analyze(16.0).relief
        self.assertIsNotNone(relief)
        self.assertGreater(relief.stats.triangles, 0)
        self.assertGreater(relief.stats.median_ms_m, 0)
        self.assertEqual(len(relief.triangles[0].points), 3)
        # округление: мс/м — 2 знака, координаты — 3
        value = relief.triangles[0].relief_ms_m
        self.assertEqual(value, round(value, 2))
        for x, y in relief.triangles[0].points:
            self.assertEqual(x, round(x, 3))
            self.assertEqual(y, round(y, 3))

    def test_analyze_without_triangles_returns_null_relief(self):
        # узкий блок — один ряд скважин на одной прямой
        self.assertIsNone(_analyze(3.0).relief)


def _repository_with_rock(**payload):
    from cost.v2.models import ReferenceItem
    from cost.v2.repository import InMemoryEconomicsRepository

    repository = InMemoryEconomicsRepository()
    repository.publish_references(
        "org",
        "tester",
        repository.list_reference_revisions("org")[0].id,
        {"rocks": [ReferenceItem(code="GR", name="Гранит", payload=payload)]},
        "тест",
    )
    return repository


class ReliefBoundsFromRockTests(unittest.TestCase):
    def test_relief_bounds_from_rock_by_name(self):
        repository = _repository_with_rock(relief_min_ms_m="4", relief_max_ms_m="12")
        snapshot = repository.get_reference_snapshot("org")
        bounds = design_service.relief_bounds_for_rock
        self.assertEqual(bounds(snapshot, "Гранит"), (4.0, 12.0))
        self.assertEqual(bounds(snapshot, "  гранит "), (4.0, 12.0))
        self.assertEqual(bounds(snapshot, "Нет такой"), (3.0, None))
        self.assertEqual(bounds(snapshot, ""), (3.0, None))

    def test_rock_without_range_gives_defaults(self):
        snapshot = _repository_with_rock().get_reference_snapshot("org")
        self.assertEqual(design_service.relief_bounds_for_rock(snapshot, "Гранит"), (3.0, None))

    def test_analyze_uses_rock_bounds(self):
        # блок 4 x 4 м, 25/42 мс: темп ниже 16 мс/м → весь блок быстрее нижней границы
        repository = _repository_with_rock(relief_min_ms_m="16")
        stats = _analyze(
            16.0, rock_name="Гранит", organization_id="org", repository=repository
        ).relief.stats
        self.assertEqual(stats.min_bound_ms_m, 16.0)
        self.assertEqual(stats.fast_share, 1.0)
        self.assertIsNone(stats.max_bound_ms_m)

    def test_analyze_without_repository_uses_default(self):
        stats = _analyze(16.0, rock_name="Гранит").relief.stats
        self.assertEqual(stats.min_bound_ms_m, 3.0)

    def test_response_has_converging_field(self):
        relief = _analyze(16.0).relief
        self.assertIsInstance(relief.converging, list)

    def test_rock_with_only_max_bound(self):
        snapshot = _repository_with_rock(relief_max_ms_m="12").get_reference_snapshot("org")
        self.assertEqual(design_service.relief_bounds_for_rock(snapshot, "Гранит"), (3.0, 12.0))

    def test_corrupt_stored_value_gives_default(self):
        snapshot = _repository_with_rock(relief_min_ms_m="abc", relief_max_ms_m="12").get_reference_snapshot("org")
        self.assertEqual(design_service.relief_bounds_for_rock(snapshot, "Гранит"), (3.0, 12.0))

    def test_repository_failure_does_not_break_analyze(self):
        from cost.v2.repository import EconomicsRepositoryError

        class Broken:
            def get_reference_snapshot(self, organization_id):
                raise EconomicsRepositoryError("нет связи")

        response = _analyze(16.0, rock_name="Гранит", organization_id="org", repository=Broken())
        self.assertEqual(response.relief.stats.min_bound_ms_m, 3.0)
        self.assertTrue(any("не прочитан" in w for w in response.timing_warnings))
