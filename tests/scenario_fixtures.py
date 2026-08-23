"""Charged-block fixtures for BDX-016 scenario tests."""
from __future__ import annotations

from Blast import ExplosiveProperties
from design.charging import apply_charge_rules
from design.models import (
    BenchSurface,
    BlastDesign,
    BlockContour,
    Point3,
    Receptor,
    default_vibration_model,
)
from design.pattern import generate_pattern
from design.timing import build_template_network

EXPLOSIVE = ExplosiveProperties("Гранулит-РП", 0.85, 3.76)

CONTOUR_VERTS = ((0.0, 0.0), (24.0, 0.0), (24.0, 16.0), (0.0, 16.0))


def sample_contour() -> BlockContour:
    return BlockContour(
        vertices=[Point3(x=x, y=y, z=0.0) for x, y in CONTOUR_VERTS],
        free_faces=[[0, 1]],
        bench=BenchSurface(crest_z_m=0.0, toe_z_m=-10.0, face_angle_deg=90.0),
        name="Уступ",
    )


def charged_design(design_id: str = "blast-approved") -> BlastDesign:
    contour = sample_contour()
    params = {
        "pattern": "rectangular",
        "spacing_a_m": 5.0,
        "burden_b_m": 4.0,
        "offset_from_face_m": 0.0,
        "edge_margin_m": 0.0,
        "diameter_mm": 152.0,
        "subdrill_m": 1.0,
    }
    holes = generate_pattern(contour, params)
    rules = {
        "stemming_m": 3.0,
        "decking": "continuous",
        "grid_a_m": 5.0,
        "grid_b_m": 4.0,
        "hole_oversize_coeff": 1.05,
    }
    loads = apply_charge_rules(holes, rules, EXPLOSIVE, contour=contour)
    network = build_template_network(holes, "row", {"system": "nonel", "scheme": "row"})
    network.timing_params = {"system": "nonel", "scheme": "row"}
    return BlastDesign(
        design_id=design_id,
        name="Утверждённый паспорт",
        contour=contour,
        holes=holes,
        loads=loads,
        network=network,
        pattern_params=params,
        charge_rules=rules,
        rock_name="гранит",
        explosive_key="ПВВ Гранулит-РП",
        receptors=[
            Receptor(
                id="R-office",
                name="Офис",
                kind="building",
                location=Point3(x=80.0, y=40.0, z=0.0),
                ppv_limit_mm_s=10.0,
            )
        ],
        vibration_models=[default_vibration_model()],
    )
