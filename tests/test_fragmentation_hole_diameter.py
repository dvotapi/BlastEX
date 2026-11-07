"""Прогноз кусковатости «Проектирования» — по диаметру скважины без коэффициента разбуривания.

Владелец 07.11.2026: «Диаметр скважины» вкладки «Сетка» — фактическая
скважина (уже с разбуриванием), поэтому регион влияния не умножает его на
`hole_oversize_coeff` правил заряда.
"""
import unittest

from simulation.fragmentation.base import charged_diameter_mm
from simulation.fragmentation.regions import ExplosiveSpec, RockSpec, collect_hole_regions
from tests.test_fragmentation_engine import _design_with_charges

ROCK = RockSpec(name="Гранит", density_t_m3=2.7, ucs_mpa=120.0, fissuring_ff=2.0)
ANFO = ExplosiveSpec(name="АНФО", density_t_m3=0.82, power_mj_kg=3.8)


class RegionDiameterTests(unittest.TestCase):
    def test_region_diameter_is_hole_diameter(self):
        for k in (1.05, 1.3):
            design = _design_with_charges()
            design.charge_rules = {**design.charge_rules, "hole_oversize_coeff": k}
            regions = collect_hole_regions(design, lump_size_mm=400.0, default_rock=ROCK, default_explosive=ANFO)
            self.assertTrue(regions)
            for region in regions:
                self.assertAlmostEqual(charged_diameter_mm(region.inputs), region.inputs.diameter_mm, places=9)
