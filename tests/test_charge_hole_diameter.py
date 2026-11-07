"""Диаметр заряда в «Проектировании» — диаметр скважины `Hole.diameter_mm`.

Владелец 07.11.2026: в поле «Диаметр скважины» вкладки «Сетка» вводится
фактическая скважина (145 мм уже с учётом разбуривания), поэтому заряд не
умножает его на коэффициент разбуривания — иначе разбуривание учтено дважды.
"""
import math
import unittest

from Blast import ExplosiveProperties
from design.charge_templates import example_wet_dry_bottom_templates
from design.charging import apply_charge_rules
from design.models import Hole, Point3

ANFO = ExplosiveProperties("АНФО", 0.82, 3.80)
DIAMETER_MM = 145.0


def _hole() -> Hole:
    return Hole(
        id="1-01", row=0, col=0,
        collar=Point3(x=0.0, y=0.0, z=0.0), toe=Point3(x=0.0, y=0.0, z=-11.0),
        diameter_mm=DIAMETER_MM, subdrill_m=1.0,
    )


def _capacity_kg_per_m(density_t_m3: float) -> float:
    return math.pi * (DIAMETER_MM / 1000.0) ** 2 / 4.0 * density_t_m3 * 1000.0


class ChargeDiameterIsHoleDiameterTests(unittest.TestCase):
    def test_continuous_charge_ignores_oversize_coeff(self):
        for k in (None, 1.05, 1.2):
            rules = {"stemming_m": 3.0, "decking": "continuous"}
            if k is not None:
                rules["hole_oversize_coeff"] = k
            load = apply_charge_rules([_hole()], rules, ANFO)[0]
            charge_length = sum(d.to_m - d.from_m for d in load.decks if d.kind == "charge")
            self.assertAlmostEqual(load.total_charge_kg, charge_length * _capacity_kg_per_m(0.82), places=6, msg=k)

    def test_template_charge_ignores_oversize_coeff(self):
        rules = {
            "stemming_m": 3.0, "bottom_length_m": 2.0, "primer_offset_m": 0.3, "grid_a_m": 5.0, "grid_b_m": 4.0,
            "templates": [item.to_dict() for item in example_wet_dry_bottom_templates()],
        }
        masses = []
        for k in (1.0, 1.2):
            load = apply_charge_rules([_hole()], {**rules, "hole_oversize_coeff": k}, ANFO, explosives=[ANFO])[0]
            masses.append(load.total_charge_kg)
        self.assertGreater(masses[0], 0.0)
        self.assertAlmostEqual(masses[0], masses[1], places=6)
