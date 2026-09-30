"""«Проектирование» берёт настройки Kuz-Ram из объекта работ — там же, где лист «Расчёт»."""
import os
import unittest
from dataclasses import asdict
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routers import design as design_router
from api.schemas.blast import KuzRamSettingsSchema
from api.schemas.design import FragmentationPredictRequest
from api.services import design_service
from api.services.economics_service import get_economics_repository
from api.services.fragmentation_settings import resolve_kuzram_settings
from cost.v2.repository import EconomicsRepositoryError, InMemoryEconomicsRepository
from simulation.fragmentation.cunningham import KuzRamSettings
from tests.test_api_fragmentation import FragmentationApiTests

ORG = "org-frag"
OBJECT = "Карьер-1"
TUNED = {"rock_factor_correction": 1.6, "strength_exponent": "19/30"}
ROCK = {"name": "Гранит", "density_t_m3": 2.65, "ucs_mpa": 150.0, "fissuring_ff": 2.0}
EXPLOSIVE = {"name": "АНФО", "density_t_m3": 0.82, "power_mj_kg": 3.8}


def _block(**values) -> dict:
    """Блок kuzram, как его сохраняет лист «Расчёт»: настройки и факты взрывов."""
    return {**asdict(KuzRamSettings()), **values, "facts": [{"crown_mm": 152, "q_kg_m3": 1.2, "oversize_pct": 4.0}]}


def _repository(organization: str = ORG, *, active: str = "") -> InMemoryEconomicsRepository:
    repository = InMemoryEconomicsRepository()
    repository.save_calc_inputs(organization, "tester", OBJECT, {"version": 1, "kuzram": _block(**TUNED)})
    if active:
        repository.import_legacy_workspace(
            organization,
            "tester",
            team_name="Команда",
            active_scenario_id="drill_blast",
            active_work_object_name=active,
        )
    return repository


def _design() -> dict:
    return FragmentationApiTests._charged_design(None)


class ResolveSettingsTests(unittest.TestCase):
    def test_explicit_settings_win(self):
        explicit = KuzRamSettings(rock_factor_correction=2.0)

        resolved = resolve_kuzram_settings(
            explicit=explicit, work_object_name=OBJECT, organization_id=ORG, repository=_repository()
        )

        self.assertEqual((resolved.source, resolved.settings), ("request", explicit))

    def test_named_work_object(self):
        resolved = resolve_kuzram_settings(
            explicit=None, work_object_name=OBJECT, organization_id=ORG, repository=_repository()
        )

        self.assertEqual(resolved.source, "work_object")
        self.assertEqual(resolved.work_object_name, OBJECT)
        self.assertEqual(resolved.settings, KuzRamSettings(**TUNED))
        self.assertEqual(resolved.warnings, ())

    def test_active_work_object_fallback(self):
        resolved = resolve_kuzram_settings(
            explicit=None, work_object_name="", organization_id=ORG, repository=_repository(active=OBJECT)
        )

        self.assertEqual((resolved.source, resolved.work_object_name), ("work_object", OBJECT))

    def test_no_organization_means_defaults(self):
        resolved = resolve_kuzram_settings(
            explicit=None, work_object_name=OBJECT, organization_id=None, repository=_repository()
        )

        self.assertEqual((resolved.source, resolved.settings), ("defaults", KuzRamSettings()))

    def test_object_without_block_is_defaults_with_name(self):
        repository = _repository()
        repository.save_calc_inputs(ORG, "tester", "Карьер-2", {"version": 1})

        resolved = resolve_kuzram_settings(
            explicit=None, work_object_name="Карьер-2", organization_id=ORG, repository=repository
        )

        self.assertEqual((resolved.source, resolved.work_object_name), ("defaults", "Карьер-2"))
        self.assertEqual(resolved.warnings, ())

    def test_invalid_block_is_defaults_with_warning(self):
        repository = _repository()
        repository.save_calc_inputs(ORG, "tester", "Карьер-3", {"kuzram": _block(rock_factor_correction=50.0)})

        resolved = resolve_kuzram_settings(
            explicit=None, work_object_name="Карьер-3", organization_id=ORG, repository=repository
        )

        self.assertEqual((resolved.source, resolved.settings), ("defaults", KuzRamSettings()))
        self.assertEqual(len(resolved.warnings), 1)
        self.assertIn("Карьер-3", resolved.warnings[0])
        self.assertIn("Поправка C(A)", resolved.warnings[0])

    def test_repository_error_is_warning(self):
        class Broken(InMemoryEconomicsRepository):
            def get_calc_inputs(self, organization_id, work_object_name):
                raise EconomicsRepositoryError("БД недоступна")

        resolved = resolve_kuzram_settings(
            explicit=None, work_object_name=OBJECT, organization_id=ORG, repository=Broken()
        )

        self.assertEqual(resolved.source, "defaults")
        self.assertIn("БД недоступна", resolved.warnings[0])


class PredictFragmentationSettingsTests(unittest.TestCase):
    def _request(self, **extra) -> FragmentationPredictRequest:
        return FragmentationPredictRequest(
            design=_design(), model="kuzram", lump_size_mm=400.0, rock=ROCK, explosive=EXPLOSIVE, **extra
        )

    def test_work_object_settings_equal_explicit_ones(self):
        tuned = design_service.predict_fragmentation(
            self._request(work_object_name=OBJECT), organization_id=ORG, repository=_repository()
        )
        explicit = design_service.predict_fragmentation(
            self._request(kuzram=KuzRamSettingsSchema(**{**asdict(KuzRamSettings()), **TUNED}))
        )
        plain = design_service.predict_fragmentation(self._request())

        self.assertEqual(tuned.settings.source, "work_object")
        self.assertEqual(tuned.settings.work_object_name, OBJECT)
        self.assertEqual(explicit.settings.source, "request")
        self.assertEqual(plain.settings.source, "defaults")
        self.assertEqual(tuned.site.prediction.x50_mm, explicit.site.prediction.x50_mm)
        self.assertNotEqual(tuned.site.prediction.x50_mm, plain.site.prediction.x50_mm)
        self.assertEqual(tuned.site.prediction.provenance.settings["work_object_name"], OBJECT)


class FragmentationRouteTests(unittest.TestCase):
    def test_route_reads_organization_work_object(self):
        # Сервисный API-ключ даёт организацию «default».
        repository = _repository("default")
        app = FastAPI()
        app.include_router(design_router.router, prefix="/api/v1")
        app.dependency_overrides[get_economics_repository] = lambda: repository

        with patch.dict(os.environ, {"BLASTEX_API_KEY": "test-api-key", "BLASTEX_SESSION_SECRET": "test-secret"}):
            client = TestClient(app, headers={"X-API-Key": "test-api-key"})
            response = client.post(
                "/api/v1/design/fragmentation",
                json={"design": _design(), "model": "kuzram", "work_object_name": OBJECT},
            )

        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["settings"]["source"], "work_object")
        self.assertEqual(body["settings"]["values"]["rock_factor_correction"], 1.6)


if __name__ == "__main__":
    unittest.main()
