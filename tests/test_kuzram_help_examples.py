"""Цифры примеров справки «Модель Kuz-Ram» совпадают с моделью.

Вкладка «Как пользоваться» (frontend/src/pages/calc/kuzram/KuzRamHelp.tsx)
показывает примеры из helpExamples.json; тест пересчитывает каждый пример
сервисом подбора и калибровки. Изменилась модель — тест падает, и справка
не расходится с расчётом.
"""
from __future__ import annotations

import json
import unittest
from pathlib import Path

from api.schemas.blast import BlastOptimizeRequest, BlastOptimizeVariant, KuzRamCalibrateRequest
from api.services.blast_service import calibrate_kuzram, optimize_blast
from api.services.converters import blast_request_to_engine_inputs
from Blast import BlastEngine
from simulation.fragmentation.cunningham import KuzRamSettings

EXAMPLES = (
    Path(__file__).resolve().parents[1] / "frontend" / "src" / "pages" / "calc" / "kuzram" / "helpExamples.json"
)


class KuzRamHelpExamplesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.examples = json.loads(EXAMPLES.read_text(encoding="utf-8"))
        cls.source = cls.examples["source"]

    def _request(self, crown_mm: float, kuzram: dict | None = None, rock: dict | None = None) -> BlastOptimizeRequest:
        return BlastOptimizeRequest(
            rock=rock or self.source["rock"],
            explosive=self.source["explosive"],
            target=self.source["target"],
            crown_diameters_mm=[crown_mm],
            max_oversize_threshold_pct=self.source["max_oversize_threshold_pct"],
            kuzram=kuzram,
        )

    def _variant(self, crown_mm: float, kuzram: dict | None = None, rock: dict | None = None) -> BlastOptimizeVariant:
        return optimize_blast(self._request(crown_mm, kuzram, rock)).variants[0]

    def test_basic_example(self) -> None:
        example = self.examples["basic"]
        variant = self._variant(example["crown_mm"])
        legacy = variant.legacy
        self.assertEqual(
            {
                "q_kg_m3": variant.specific_q_kg_m3,
                "grid_a_m": variant.grid_a_m,
                "grid_b_m": variant.grid_b_m,
                "oversize_pct": variant.oversize_pct,
                "reached": variant.reached,
            },
            example["kuzram"],
        )
        self.assertEqual(
            {
                "q_kg_m3": legacy.specific_q_kg_m3,
                "grid_a_m": legacy.grid_a_m,
                "grid_b_m": legacy.grid_b_m,
                "oversize_pct": legacy.oversize_pct,
                "reached": legacy.reached,
            },
            example["legacy"],
        )

    def test_calibration_example(self) -> None:
        example = self.examples["calibration"]
        # Справка показывает «до подбора» по базовому примеру — коронка должна совпадать.
        self.assertEqual(example["crown_mm"], self.examples["basic"]["crown_mm"])
        response = calibrate_kuzram(
            KuzRamCalibrateRequest(
                rock=self.source["rock"],
                explosive=self.source["explosive"],
                target=self.source["target"],
                facts=example["facts"],
            )
        )
        self.assertEqual(
            [
                {"model_oversize_pct": row.model_oversize_pct, "rock_factor_correction": row.rock_factor_correction}
                for row in response.rows
            ],
            example["rows"],
        )
        self.assertEqual(response.rock_factor_correction, example["rock_factor_correction"])
        self.assertEqual(response.skipped, 0)
        after = self._variant(example["crown_mm"], {"rock_factor_correction": response.rock_factor_correction})
        self.assertEqual(
            {"q_kg_m3": after.specific_q_kg_m3, "grid_a_m": after.grid_a_m, "grid_b_m": after.grid_b_m},
            example["after"],
        )

    def test_rock_factor_methods_example(self) -> None:
        example = self.examples["methods"]
        for row in example["rows"]:
            with self.subTest(method=row["rock_factor_method"]):
                variant = self._variant(example["crown_mm"], {"rock_factor_method": row["rock_factor_method"]})
                self.assertEqual(
                    {
                        "rock_factor_method": row["rock_factor_method"],
                        "rmd": variant.details.rock_factor.rmd,
                        "rock_factor_a": round(variant.details.rock_factor_a, 2),
                        "q_kg_m3": variant.specific_q_kg_m3,
                        "grid_a_m": variant.grid_a_m,
                        "grid_b_m": variant.grid_b_m,
                    },
                    row,
                )

    def test_not_reached_example(self) -> None:
        example = self.examples["not_reached"]
        for key in ("low", "raised"):
            expected = example[key]
            with self.subTest(case=key):
                variant = self._variant(example["crown_mm"], {"q_max_kg_m3": expected["q_max_kg_m3"]})
                self.assertEqual(
                    {
                        "q_max_kg_m3": expected["q_max_kg_m3"],
                        "q_kg_m3": variant.specific_q_kg_m3,
                        "oversize_pct": variant.oversize_pct,
                        "reached": variant.reached,
                    },
                    expected,
                )

    def test_joint_switch_example(self) -> None:
        example = self.examples["joint_switch"]
        rock = {**self.source["rock"], "fissuring_ff": example["fissuring_ff"]}
        settings = {"rock_factor_method": "joint_factor"}
        after = self._variant(example["crown_mm"], settings, rock)
        breakdown = after.details.rock_factor
        self.assertEqual(round(breakdown.joint_spacing_m, 2), example["joint_spacing_m"])
        self.assertEqual(
            {
                "q_kg_m3": after.specific_q_kg_m3,
                "reduced_pattern_m": round(breakdown.reduced_pattern_m, 2),
                "jps": breakdown.jps,
                "rock_factor_a": round(after.details.rock_factor_a, 2),
                "oversize_pct": after.oversize_pct,
            },
            example["after"],
        )
        # Шаг перебора назад: та же коронка при q на 0,01 меньше — до переключения JPS.
        engine = BlastEngine(*blast_request_to_engine_inputs(self._request(example["crown_mm"], settings, rock)))
        before_q = round(after.specific_q_kg_m3 - 0.01, 2)
        point = engine.kuzram_point(example["crown_mm"], before_q, KuzRamSettings(**settings))
        self.assertEqual(
            {
                "q_kg_m3": before_q,
                "reduced_pattern_m": round(point.rock_factor.reduced_pattern_m, 2),
                "jps": point.rock_factor.jps,
                "rock_factor_a": round(point.rock_factor_a, 2),
                "oversize_pct": round(point.oversize_pct, 2),
            },
            example["before"],
        )
