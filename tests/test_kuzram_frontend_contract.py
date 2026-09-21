"""Умолчания и границы модели Kuz-Ram во фронте совпадают с сервером.

Фронт держит их в frontend/src/pages/calc/kuzram/kuzramContract.json, чтобы
читать сохранённые настройки листа и проверять ввод без запроса к API. Тест
не даёт этой копии разойтись с cunningham.py и схемами api/schemas/blast.py.
"""
from __future__ import annotations

import json
import unittest
from dataclasses import asdict
from pathlib import Path

from api.schemas.blast import CROWN_MM_MAX, CROWN_MM_MIN, KuzRamCalibrateRequest, KuzRamFactSchema
from simulation.fragmentation.cunningham import (
    JOINT_ANGLES,
    JOINT_CONDITIONS,
    NUMERIC_BOUNDS,
    Q_MIN_KG_M3,
    ROCK_FACTOR_METHODS,
    STRENGTH_EXPONENTS,
    KuzRamSettings,
)

CONTRACT = (
    Path(__file__).resolve().parents[1] / "frontend" / "src" / "pages" / "calc" / "kuzram" / "kuzramContract.json"
)


def _constraints(field) -> dict[str, float]:
    """Ограничения поля pydantic (gt, ge, lt, le, max_length) из его metadata."""
    found: dict[str, float] = {}
    for item in field.metadata:
        for key in ("gt", "ge", "lt", "le", "max_length"):
            value = getattr(item, key, None)
            if value is not None:
                found[key] = value
    return found


class KuzRamFrontendContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.contract = json.loads(CONTRACT.read_text(encoding="utf-8"))

    def test_defaults_match_settings_dataclass(self) -> None:
        self.assertEqual(self.contract["defaults"], asdict(KuzRamSettings()))

    def test_numeric_bounds_match(self) -> None:
        expected = {name: [low, high] for name, (low, high, _label) in NUMERIC_BOUNDS.items()}
        self.assertEqual(self.contract["bounds"], expected)

    def test_options_match(self) -> None:
        self.assertEqual(self.contract["rock_factor_methods"], list(ROCK_FACTOR_METHODS))
        self.assertEqual(self.contract["joint_conditions"], list(JOINT_CONDITIONS))
        self.assertEqual(self.contract["joint_angles"], list(JOINT_ANGLES))
        self.assertEqual(self.contract["strength_exponents"], list(STRENGTH_EXPONENTS))
        self.assertEqual(self.contract["q_min_kg_m3"], Q_MIN_KG_M3)

    def test_fact_bounds_match_api_schema(self) -> None:
        # Коронку проверяет валидатор CrownMm (границы — константы схемы), q и
        # негабарит — ограничения Field.
        expected = {name: _constraints(field) for name, field in KuzRamFactSchema.model_fields.items()}
        expected["crown_mm"] = {"ge": CROWN_MM_MIN, "le": CROWN_MM_MAX}
        self.assertEqual(self.contract["fact_bounds"], expected)
        facts_field = KuzRamCalibrateRequest.model_fields["facts"]
        self.assertEqual(self.contract["max_facts"], _constraints(facts_field)["max_length"])
