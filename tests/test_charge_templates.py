import unittest

from Blast import ExplosiveProperties
from design.charge_templates import example_wet_dry_bottom_templates
from design.charging import apply_charge_rules, hole_geology_for_charging
from design.models import (
    ChargeAction,
    ChargeCondition,
    ChargeTemplate,
    Hole,
    HoleInterval,
    Point3,
    RockPropertySet,
    WaterInterval,
    templates_from_rules,
)

ANFO = ExplosiveProperties("АНФО", 0.82, 3.80)
DENSE = ExplosiveProperties("Эмульсия плотная", 1.25, 3.20)
WET_EM = ExplosiveProperties("Эмульсия водоустойчивая", 1.15, 3.10)
CATALOG = [ANFO, DENSE, WET_EM]


def _hole(
    *,
    hole_id: str = "1-01",
    depth_m: float = 11.0,
    kind: str = "production",
    row: int = 0,
    water: list[tuple[float, float, str]] | None = None,
    domains: list[tuple[float, float, str]] | None = None,
) -> Hole:
    hole = Hole(
        id=hole_id,
        row=row,
        col=0,
        collar=Point3(x=0.0, y=0.0, z=0.0),
        toe=Point3(x=0.0, y=0.0, z=-depth_m),
        diameter_mm=152.0,
        subdrill_m=1.0,
        kind=kind,
    )
    if domains:
        hole.intervals = [
            HoleInterval(
                from_m=start,
                to_m=end,
                domain_id=name,
                domain_name=name,
                properties=RockPropertySet(),
                role="designed",
            )
            for start, end, name in domains
        ]
    if water:
        hole.water_intervals = [
            WaterInterval(from_m=start, to_m=end, condition=condition, role="designed")
            for start, end, condition in water
        ]
    return hole


def _rules(**extra):
    payload = {
        "stemming_m": 3.0,
        "bottom_length_m": 2.0,
        "primer_offset_m": 0.3,
        "grid_a_m": 5.0,
        "grid_b_m": 4.0,
        "templates": [item.to_dict() for item in example_wet_dry_bottom_templates()],
    }
    payload.update(extra)
    return payload


class WetDryBottomSplitTests(unittest.TestCase):
    def test_example_assigns_three_explosives(self):
        hole = _hole(water=[(6.0, 9.0, "wet")])
        load = apply_charge_rules([hole], _rules(), ANFO, explosives=CATALOG)[0]
        explosive_decks = [d for d in load.decks if d.kind in {"bulk_explosive", "charge"}]
        kinds = [d.kind for d in load.decks]
        self.assertEqual(kinds[0], "stemming")
        self.assertEqual(load.decks[0].to_m, 3.0)

        by_product = {d.explosive_key: d for d in explosive_decks}
        self.assertIn("АНФО", by_product)
        self.assertIn("Эмульсия водоустойчивая", by_product)
        self.assertIn("Эмульсия плотная", by_product)

        self.assertAlmostEqual(by_product["АНФО"].from_m, 3.0)
        self.assertAlmostEqual(by_product["АНФО"].to_m, 6.0)
        self.assertAlmostEqual(by_product["Эмульсия водоустойчивая"].from_m, 6.0)
        self.assertAlmostEqual(by_product["Эмульсия водоустойчивая"].to_m, 9.0)
        self.assertAlmostEqual(by_product["Эмульсия плотная"].from_m, 9.0)
        self.assertAlmostEqual(by_product["Эмульсия плотная"].to_m, 11.0)

        self.assertGreater(by_product["Эмульсия плотная"].mass_kg, by_product["АНФО"].mass_kg / 3)
        self.assertEqual(len(load.primer_items), 2)
        self.assertTrue(all(item.product for item in load.primer_items))

    def test_wet_overlapping_bottom_loses_to_higher_priority(self):
        hole = _hole(water=[(6.0, 11.0, "wet")])
        load = apply_charge_rules([hole], _rules(), ANFO, explosives=CATALOG)[0]
        bottom = next(d for d in load.decks if d.explosive_key == "Эмульсия плотная")
        wet = next(d for d in load.decks if d.explosive_key == "Эмульсия водоустойчивая")
        self.assertAlmostEqual(bottom.from_m, 9.0)
        self.assertAlmostEqual(wet.to_m, 9.0)
        self.assertAlmostEqual(wet.from_m, 6.0)


class PriorityTests(unittest.TestCase):
    def test_higher_priority_wins_on_same_slice(self):
        hole = _hole()
        templates = [
            ChargeTemplate(
                id="T-low",
                name="low",
                priority=5,
                conditions=ChargeCondition(water="dry"),
                actions=[ChargeAction(kind="bulk_explosive", explosive_key="АНФО", region="interval")],
            ),
            ChargeTemplate(
                id="T-high",
                name="high",
                priority=40,
                conditions=ChargeCondition(water="dry"),
                actions=[ChargeAction(kind="bulk_explosive", explosive_key="Эмульсия плотная", region="interval")],
            ),
        ]
        rules = {"stemming_m": 3.0, "bottom_length_m": 0.0, "templates": [t.to_dict() for t in templates]}
        load = apply_charge_rules([hole], rules, ANFO, explosives=CATALOG)[0]
        products = {d.explosive_key for d in load.decks if d.mass_kg > 0}
        self.assertEqual(products, {"Эмульсия плотная"})

    def test_disabled_template_is_skipped(self):
        hole = _hole()
        templates = [
            ChargeTemplate(
                id="T-off",
                name="off",
                priority=50,
                enabled=False,
                conditions=ChargeCondition(),
                actions=[ChargeAction(kind="bulk_explosive", explosive_key="Эмульсия плотная", region="interval")],
            ),
            ChargeTemplate(
                id="T-on",
                name="on",
                priority=1,
                conditions=ChargeCondition(),
                actions=[ChargeAction(kind="bulk_explosive", explosive_key="АНФО", region="interval")],
            ),
        ]
        rules = {"stemming_m": 3.0, "templates": [t.to_dict() for t in templates]}
        load = apply_charge_rules([hole], rules, ANFO, explosives=CATALOG)[0]
        products = {d.explosive_key for d in load.decks if d.mass_kg > 0}
        self.assertEqual(products, {"АНФО"})

    def test_equal_priority_is_stable_by_id(self):
        hole = _hole()
        templates = [
            ChargeTemplate(
                id="T-b",
                priority=10,
                conditions=ChargeCondition(),
                actions=[ChargeAction(kind="bulk_explosive", explosive_key="АНФО", region="interval")],
            ),
            ChargeTemplate(
                id="T-a",
                priority=10,
                conditions=ChargeCondition(),
                actions=[ChargeAction(kind="bulk_explosive", explosive_key="Эмульсия плотная", region="interval")],
            ),
        ]
        rules = {"stemming_m": 3.0, "templates": [t.to_dict() for t in templates]}
        load = apply_charge_rules([hole], rules, ANFO, explosives=CATALOG)[0]
        products = {d.explosive_key for d in load.decks if d.mass_kg > 0}
        self.assertEqual(products, {"Эмульсия плотная"})


class ConditionFilterTests(unittest.TestCase):
    def test_hole_kind_and_row_filters(self):
        production = _hole(hole_id="P-1", kind="production", row=0)
        contour = _hole(hole_id="C-1", kind="contour", row=0)
        other_row = _hole(hole_id="P-2", kind="production", row=2)
        template = ChargeTemplate(
            id="T-prod",
            priority=10,
            conditions=ChargeCondition(hole_kinds=["production"], rows=[0]),
            actions=[ChargeAction(kind="packaged_explosive", explosive_key="АНФО", region="interval")],
        )
        rules = {"stemming_m": 3.0, "templates": [template.to_dict()]}
        loads = apply_charge_rules([production, contour, other_row], rules, ANFO, explosives=CATALOG)
        by_id = {ld.hole_id: ld for ld in loads}
        prod_keys = {d.explosive_key for d in by_id["P-1"].decks if d.mass_kg > 0}
        self.assertEqual(prod_keys, {"АНФО"})
        # contour and other row fall back to the default explosive leftover
        self.assertTrue(any(d.kind == "bulk_explosive" for d in loads[1].decks))

    def test_rock_domain_condition(self):
        hole = _hole(domains=[(0.0, 6.0, "weathered"), (6.0, 11.0, "fresh")])
        self.assertEqual([iv.domain_id for iv in hole_geology_for_charging(hole)], ["weathered", "fresh"])
        template = ChargeTemplate(
            id="T-fresh",
            priority=10,
            conditions=ChargeCondition(rock_domain_ids=["fresh"]),
            actions=[ChargeAction(kind="bulk_explosive", explosive_key="Эмульсия плотная", region="interval")],
        )
        rules = {"stemming_m": 3.0, "bottom_length_m": 0.0, "templates": [template.to_dict()]}
        load = apply_charge_rules([hole], rules, ANFO, explosives=CATALOG)[0]
        dense = next(d for d in load.decks if d.explosive_key == "Эмульсия плотная")
        self.assertAlmostEqual(dense.from_m, 6.0)
        leftover = next(d for d in load.decks if d.explosive_key == "АНФО")
        self.assertAlmostEqual(leftover.from_m, 3.0)
        self.assertAlmostEqual(leftover.to_m, 6.0)


class FallbackAndComponentsTests(unittest.TestCase):
    def test_no_templates_keeps_simple_charge_kind(self):
        hole = _hole()
        load = apply_charge_rules([hole], {"stemming_m": 3.0, "decking": "continuous"}, ANFO)[0]
        self.assertEqual([d.kind for d in load.decks], ["stemming", "charge"])

    def test_empty_templates_list_is_simple_rules(self):
        hole = _hole()
        load = apply_charge_rules([hole], {"stemming_m": 3.0, "templates": []}, ANFO)[0]
        self.assertEqual([d.kind for d in load.decks], ["stemming", "charge"])

    def test_air_inert_water_decks(self):
        hole = _hole()
        templates = [
            ChargeTemplate(
                id="T-air",
                priority=30,
                conditions=ChargeCondition(geological_interval="bottom"),
                actions=[ChargeAction(kind="air_deck", region="bottom", length_m=1.0)],
            ),
            ChargeTemplate(
                id="T-water",
                priority=20,
                conditions=ChargeCondition(),
                actions=[ChargeAction(kind="water_deck", region="interval")],
            ),
        ]
        rules = {"stemming_m": 3.0, "bottom_length_m": 1.0, "templates": [t.to_dict() for t in templates]}
        load = apply_charge_rules([hole], rules, ANFO)[0]
        kinds = [d.kind for d in load.decks]
        self.assertIn("air_deck", kinds)
        self.assertIn("water_deck", kinds)
        self.assertTrue(all(d.mass_kg == 0 for d in load.decks if d.kind in {"air_deck", "water_deck", "stemming"}))

    def test_templates_from_rules_parses_round_trip(self):
        rules = _rules()
        parsed = templates_from_rules(rules)
        self.assertEqual([t.id for t in parsed], ["T-bottom", "T-wet", "T-dry"])
        self.assertEqual(parsed[0].priority, 30)
        again = ChargeTemplate.from_dict(parsed[0].to_dict())
        self.assertEqual(again.actions[0].kind, "bulk_explosive")
        self.assertTrue(again.actions[0].place_primer)


if __name__ == "__main__":
    unittest.main()
