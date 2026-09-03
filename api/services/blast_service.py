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
from cost.v2.legacy_adapter import LegacyReferences


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


def resolve_explosive_item(legacy: LegacyReferences, explosive_key: str):
    """ВВ по ключу UI, с откатом на первый элемент справочника."""
    items = list(legacy.explosives)
    return next((item for item in items if item.key == explosive_key), items[0])


def compute_geometry(payload, legacy: LegacyReferences):
    """Геометрия скважины и блока для панели схемы заряда (api/schemas/blast.BlastGeometryRequest)."""
    from cost.geometry import (
        calculate_block_geometry,
        calculate_hole_geometry,
        normalize_initiation_config,
    )

    explosive_item = resolve_explosive_item(legacy, payload.explosive_key)
    initiation = normalize_initiation_config(
        intermediate_detonators_per_hole=payload.intermediate_detonators_per_hole,
        nsi_per_hole=payload.nsi_per_hole,
        nsi_length_1_m=payload.nsi_length_1_m,
        nsi_length_2_m=payload.nsi_length_2_m,
        detonator_delay_ms=payload.detonator_delay_ms,
    )
    hole = calculate_hole_geometry(
        grid_a_m=payload.grid_a_m,
        grid_b_m=payload.grid_b_m,
        depth_m=payload.depth_m,
        overdrill_m=payload.overdrill_m,
        undercharge_m=payload.undercharge_m,
        crown_mm=payload.crown_mm,
        hole_oversize_coeff=payload.hole_oversize_coeff,
        explosive=explosive_item.properties,
        explosive_label=explosive_item.label,
    )
    block = calculate_block_geometry(
        block_volume_m3=payload.block_volume_m3,
        hole=hole,
        additional_holes_pct=payload.additional_holes_pct,
        initiation=initiation,
    )
    return hole, block, initiation, explosive_item.label
