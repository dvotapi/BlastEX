"""Ситуация карьера: виды объектов, название и дата источника, серии (TASK-013, PR 4)."""
from __future__ import annotations

import unittest
from dataclasses import dataclass
from datetime import date, datetime, timezone

from design.spatial.cad.model import SITUATION_KIND_CODES
from design.spatial.cad.situation import (
    order_versions,
    series_key,
    situation_kind_for_layer,
    title_and_date_from_file_name,
)


class SituationKindTests(unittest.TestCase):
    def test_kinds_by_layer_name(self) -> None:
        cases = {
            "Автодорога": "road",
            "Карьерная автодорога": "road",
            "Съезд на гор. +410": "road",
            "ВЛ-6кВ": "power_line",
            "ЛЭП 10 кВ": "power_line",
            "Склад негабарита": "stockpile",
            "Отвал вскрышных пород": "stockpile",
            "Здания и сооружения": "building",
            "Граница карьера": "pit",
            "Контур карьера": "pit",
            "Слой 1": "other",
            "": "other",
        }
        for name, kind in cases.items():
            with self.subTest(name=name):
                self.assertEqual(situation_kind_for_layer(name), kind)

    def test_kind_codes_cover_every_rule(self) -> None:
        self.assertEqual(
            SITUATION_KIND_CODES, {"pit", "road", "power_line", "stockpile", "building", "other"}
        )

    def test_abbreviation_inside_word_is_not_power_line(self) -> None:
        # «вл» внутри слова (управление, влажность) — не ЛЭП.
        self.assertEqual(situation_kind_for_layer("Управление"), "other")
        self.assertEqual(situation_kind_for_layer("Влажные участки"), "other")


class TitleAndDateTests(unittest.TestCase):
    def test_block_file_name(self) -> None:
        self.assertEqual(
            title_and_date_from_file_name("28.09.2026г граница блока 66 для проектирования.dwg"),
            ("граница блока 66 для проектирования", date(2026, 9, 28)),
        )

    def test_trailing_preposition_before_date_is_dropped(self) -> None:
        self.assertEqual(
            title_and_date_from_file_name("Положение горных работ на 01.09.2026.dxf"),
            ("Положение горных работ", date(2026, 9, 1)),
        )
        self.assertEqual(
            title_and_date_from_file_name("Положение горных работ по состоянию на 01.10.2026 г.dwg"),
            ("Положение горных работ", date(2026, 10, 1)),
        )

    def test_same_series_from_differently_named_files(self) -> None:
        first, first_date = title_and_date_from_file_name("Положение горных работ на 01.09.2026.dxf")
        second, second_date = title_and_date_from_file_name("01.10.2026 положение горных работ.dwg")
        self.assertEqual(first_date, date(2026, 9, 1))
        self.assertEqual(second, "положение горных работ")
        self.assertEqual(second_date, date(2026, 10, 1))
        self.assertEqual(series_key(first), series_key(second))

    def test_iso_date(self) -> None:
        self.assertEqual(
            title_and_date_from_file_name("situation_2026-09-15.dxf"),
            ("situation", date(2026, 9, 15)),
        )

    def test_name_without_date(self) -> None:
        self.assertEqual(title_and_date_from_file_name("Блок 66.dxf"), ("Блок 66", None))

    def test_impossible_date_keeps_name(self) -> None:
        self.assertEqual(
            title_and_date_from_file_name("31.02.2026 ситуация.dxf"), ("31.02.2026 ситуация", None)
        )

    def test_name_that_is_only_a_date(self) -> None:
        self.assertEqual(title_and_date_from_file_name("01.09.2026.dxf"), ("01.09.2026", date(2026, 9, 1)))


@dataclass
class _Version:
    name: str
    survey_date: date | None
    uploaded_at: datetime


def _at(day: int) -> datetime:
    return datetime(2026, 9, day, 12, tzinfo=timezone.utc)


class OrderVersionsTests(unittest.TestCase):
    def test_freshest_survey_first_undated_by_upload(self) -> None:
        versions = [
            _Version("сентябрь", date(2026, 9, 1), _at(3)),
            _Version("без даты", None, _at(20)),
            _Version("октябрь", date(2026, 10, 1), _at(2)),
            _Version("август", date(2026, 8, 1), _at(25)),
        ]
        self.assertEqual(
            [item.name for item in order_versions(versions)], ["октябрь", "без даты", "сентябрь", "август"]
        )

    def test_same_date_newer_upload_first(self) -> None:
        versions = [_Version("раньше", date(2026, 9, 1), _at(2)), _Version("позже", date(2026, 9, 1), _at(5))]
        self.assertEqual([item.name for item in order_versions(versions)], ["позже", "раньше"])


if __name__ == "__main__":
    unittest.main()
