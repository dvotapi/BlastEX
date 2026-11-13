"""TASK-017, PR 3: сеть хранит полный набор параметров построения.

Пересчёт коммутации после сдвига скважин строит сеть заново тем же шаблоном
по `network.timing_params` — без формы. Здесь проверяется, что по сохранённым
параметрам каждая схема строится в точности той же, что ключи пишутся только
когда заданы, и что сдвиг в соседний столбец меняет предшественника.
"""
import math
import unittest

from api.schemas.design import TieGenerateRequest
from api.services import design_service
from design.models import Hole, InitiationNetwork
from design.pattern import generate_pattern
from design.timing import (
    ORIGIN_TEMPLATE,
    SCHEME_TYPES,
    retie_params,
)
from tests.front_rows_fixtures import _rect_contour

RECT = {
    "pattern": "rectangular",
    "spacing_a_m": 4.0,
    "burden_b_m": 4.0,
    "row_azimuth_deg": 90.0,
    "offset_from_face_m": 0.0,
    "edge_margin_m": 0.0,
}
CONTOUR = _rect_contour(20.0, 16.0)


def _holes() -> list[Hole]:
    return generate_pattern(CONTOUR, RECT)


def _generate(holes: list[Hole], scheme: str, params: dict):
    return design_service.generate_tie(
        TieGenerateRequest(
            holes=[h.to_dict() for h in holes],
            scheme=scheme,
            params=params,
            contour=CONTOUR.to_dict(),
        )
    )


# Форма страницы шлёт все поля TieParams; так же и здесь.
FORM = {
    "interval_ms": 25.0,
    "downhole_delay_ms": 500.0,
    "include_contour": False,
    "timing_mode": "",
    "timing_expression": "",
    "direction_azimuth_deg": 0.0,
    "gradient_from_ms": 0.0,
    "gradient_to_ms": 250.0,
    "base_ms": 0.0,
    "trunk_ms": 25.0,
    "chain_ms": 42.0,
    "cut_flank": "left",
    "selected_hole_ids": [],
}


def _cases():
    for scheme in SCHEME_TYPES:
        for system in ("nonel", "detcord", "electronic"):
            params = {**FORM, "system": system}
            if scheme == "trunk_chains":
                params |= {"main_kind": "production", "cut_flank": "right"}
            yield scheme, params
            if system == "electronic" and scheme != "trunk_chains":
                for mode in ("row", "direction", "selection", "expression"):
                    extra = {"timing_mode": mode}
                    if mode == "direction":
                        extra["direction_azimuth_deg"] = 30.0
                    if mode == "selection":
                        extra["selected_hole_ids"] = ["2-01", "1-01"]
                    if mode == "expression":
                        extra["timing_expression"] = "base + interval * row + abs(col - 2)"
                    yield scheme, params | extra


class RetieParamsTest(unittest.TestCase):
    def test_every_scheme_rebuilds_same_network(self):
        holes = _holes()
        for scheme, params in _cases():
            with self.subTest(scheme=scheme, system=params["system"], mode=params.get("timing_mode")):
                first = _generate(holes, scheme, params)
                network = InitiationNetwork.from_dict(first.network.model_dump())
                self.assertEqual(network.timing_params.get("origin"), ORIGIN_TEMPLATE)
                again = retie_params(network)
                self.assertIsNotNone(again)
                rebuilt = _generate(holes, again[0], again[1])
                self.assertEqual(rebuilt.network.model_dump(), first.network.model_dump())
                self.assertEqual(rebuilt.warnings, first.warnings)

    def test_keys_only_when_given(self):
        holes = _holes()
        response = _generate(holes, "trunk_chains", {"system": "nonel"})
        timing = response.network.timing_params
        self.assertNotIn("main_kind", timing)
        self.assertNotIn("burning_front_m", timing)
        self.assertNotIn("include_contour", timing)
        self.assertNotIn("crest_azimuth_deg", timing)
        given = _generate(holes, "trunk_chains", {"system": "nonel", "main_kind": "production", "burning_front_m": 40})
        self.assertEqual(given.network.timing_params["main_kind"], "production")
        self.assertEqual(given.network.timing_params["burning_front_m"], 40)
        self.assertNotIn("crest_azimuth_deg", given.network.timing_params)
        row = _generate(holes, "row", {"system": "nonel"}).network.timing_params
        self.assertNotIn("trunk_ms", row)
        self.assertNotIn("timing_mode", row)

    def test_trunk_keeps_ignored_electronic_mode_warning(self):
        holes = _holes()
        first = _generate(holes, "trunk_chains", {**FORM, "system": "electronic", "timing_mode": "row"})
        network = InitiationNetwork.from_dict(first.network.model_dump())
        again = _generate(holes, *retie_params(network))
        self.assertEqual(again.warnings, first.warnings)
        self.assertTrue(first.warnings)

    def test_network_without_origin_has_no_retie_params(self):
        old = InitiationNetwork(system="nonel", timing_params={"scheme": "trunk_chains", "trunk_ms": 25.0})
        self.assertIsNone(retie_params(old))
        unknown = InitiationNetwork(system="nonel", timing_params={"scheme": "spiral", "origin": "template"})
        self.assertIsNone(retie_params(unknown))

    def test_selection_order_comes_from_network_field(self):
        # Перенумерация переименовывает `network.selected_hole_ids`; копии в
        # `timing_params` нет, пересчёт берёт поле сети.
        holes = _holes()
        params = {**FORM, "system": "electronic", "timing_mode": "selection", "selected_hole_ids": ["2-01", "1-01"]}
        network = InitiationNetwork.from_dict(_generate(holes, "row", params).network.model_dump())
        self.assertNotIn("selected_hole_ids", network.timing_params)
        network.selected_hole_ids = ["1-01", "2-01"]
        self.assertEqual(retie_params(network)[1]["selected_hole_ids"], ["1-01", "2-01"])

    def test_retie_params_drop_service_keys(self):
        network = InitiationNetwork(
            system="detcord",
            timing_params={"scheme": "row", "origin": "edited", "geometry_stale": True, "interval_ms": 20.0},
        )
        self.assertEqual(retie_params(network), ("row", {"interval_ms": 20.0, "system": "detcord"}))

    def test_move_to_next_column_changes_predecessor(self):
        holes = _holes()
        first = _generate(holes, "trunk_chains", {"system": "nonel"})
        network = InitiationNetwork.from_dict(first.network.model_dump())
        incoming = {c.to_hole: c.from_hole for c in network.connectors}
        by_id = {h.id: h for h in holes}
        # Скважина в глубине блока, у которой есть сосед справа в ряду впереди.
        target = next(
            h
            for h in holes
            if h.id in incoming
            and by_id[incoming[h.id]].collar.y < h.collar.y - 1.0
            and any(
                abs(o.collar.y - by_id[incoming[h.id]].collar.y) < 0.1 and abs(o.collar.x - (h.collar.x + 4.0)) < 0.1
                for o in holes
            )
        )
        before = by_id[incoming[target.id]]
        self.assertLess(abs(before.collar.x - target.collar.x), 0.1)
        moved = [
            Hole.from_dict({**h.to_dict(), "collar": {**h.collar.to_dict(), "x": h.collar.x + 2.4}, "toe": {**h.toe.to_dict(), "x": h.toe.x + 2.4}})
            if h.id == target.id
            else h
            for h in holes
        ]
        scheme, params = retie_params(network)
        after_network = _generate(moved, scheme, params).network
        after = {c.to_hole: c.from_hole for c in after_network.connectors}[target.id]
        self.assertNotEqual(after, before.id)
        self.assertTrue(math.isclose(by_id[after].collar.x, target.collar.x + 4.0, abs_tol=0.1))


if __name__ == "__main__":
    unittest.main()
