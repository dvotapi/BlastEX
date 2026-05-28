"""Сервис технологического расчёта."""
from __future__ import annotations

from Blast import BlastEngine
from api.exceptions import InvalidGeometryError
from api.schemas.blast import (
    BlastOptimizeRequest,
    BlastOptimizeResponse,
    BlastOptimizeVariant,
)
from api.services.converters import blast_request_to_engine_inputs


def optimize_blast(request: BlastOptimizeRequest) -> BlastOptimizeResponse:
    rock, explosive, target = blast_request_to_engine_inputs(request)

    if target.bench_height_m <= 0:
        raise InvalidGeometryError("Высота уступа должна быть больше нуля.")
    if not request.crown_diameters_mm:
        raise InvalidGeometryError("Укажите хотя бы один диаметр коронки.")

    engine = BlastEngine(rock, explosive, target)
    variants: list[BlastOptimizeVariant] = []

    for diameter_mm in sorted(request.crown_diameters_mm):
        if diameter_mm <= 0:
            raise InvalidGeometryError(f"Некорректный диаметр коронки: {diameter_mm} мм.")

        result = engine.optimize_blast(
            diameter_mm,
            max_oversize_threshold=request.max_oversize_threshold_pct,
        )
        w_val = float(result["W_m"])
        a_m = round(target.spacing_coeff_m * w_val, 2)
        b_m = w_val

        variants.append(
            BlastOptimizeVariant(
                crown_mm=diameter_mm,
                specific_q_kg_m3=float(result["q"]),
                line_of_least_resistance_m=w_val,
                grid_a_m=a_m,
                grid_b_m=b_m,
                grid_label=f"{a_m} × {b_m}",
                x50_mm=float(result["x50_mm"]),
                oversize_pct=float(result["oversize_pct"]),
                target_q_kg_m3=result.get("target_q"),
            )
        )

    return BlastOptimizeResponse(
        variants=variants,
        max_oversize_threshold_pct=request.max_oversize_threshold_pct,
        rock_name=rock.name,
        explosive_name=explosive.name,
    )
