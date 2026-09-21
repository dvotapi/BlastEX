"""Сервис технологического расчёта."""
from __future__ import annotations

import math

from Blast import BlastEngine, BlastPoint
from api.exceptions import InvalidGeometryError
from api.schemas.blast import (
    BlastOptimizeRequest,
    BlastOptimizeResponse,
    BlastOptimizeVariant,
    FragmentationDetailsSchema,
    KuzRamCalibrateRequest,
    KuzRamCalibrateResponse,
    KuzRamCalibrationRow,
    KuzRamSettingsSchema,
    LegacyVariantSchema,
)
from api.services.converters import blast_request_to_engine_inputs
from cost.v2.legacy_adapter import LegacyReferences
from simulation.fragmentation.cunningham import MODEL_VERSION


def _grid(point: BlastPoint, spacing_coeff_m: float) -> tuple[float, float, str]:
    """Сетка a × b с округлением, как в прежнем ответе: a считается от округлённого W."""
    b_m = round(point.burden_m, 2)
    a_m = round(spacing_coeff_m * b_m, 2)
    return a_m, b_m, f"{a_m} × {b_m}"


def optimize_blast(request: BlastOptimizeRequest) -> BlastOptimizeResponse:
    rock, explosive, target = blast_request_to_engine_inputs(request)

    if target.bench_height_m <= 0:
        raise InvalidGeometryError("Высота уступа должна быть больше нуля.")
    if not request.crown_diameters_mm:
        raise InvalidGeometryError("Укажите хотя бы один диаметр коронки.")

    settings_schema = request.kuzram or KuzRamSettingsSchema()
    settings = settings_schema.to_settings()
    engine = BlastEngine(rock, explosive, target)
    threshold = request.max_oversize_threshold_pct
    variants: list[BlastOptimizeVariant] = []

    for diameter_mm in sorted(request.crown_diameters_mm):
        if diameter_mm <= 0:
            raise InvalidGeometryError(f"Некорректный диаметр коронки: {diameter_mm} мм.")

        current = engine.optimize_blast(diameter_mm, threshold, settings)
        legacy = engine.optimize_blast_legacy(diameter_mm, threshold)
        a_m, b_m, label = _grid(current.point, target.spacing_coeff_m)
        legacy_a, legacy_b, legacy_label = _grid(legacy.point, target.spacing_coeff_m)
        q = round(current.point.q_kg_m3, 2)

        variants.append(
            BlastOptimizeVariant(
                crown_mm=diameter_mm,
                specific_q_kg_m3=q,
                line_of_least_resistance_m=b_m,
                grid_a_m=a_m,
                grid_b_m=b_m,
                grid_label=label,
                x50_mm=round(current.point.x50_mm, 1),
                oversize_pct=round(current.point.oversize_pct, 2),
                target_q_kg_m3=q if current.reached else None,
                reached=current.reached,
                details=FragmentationDetailsSchema.model_validate(current.point),
                legacy=LegacyVariantSchema(
                    specific_q_kg_m3=round(legacy.point.q_kg_m3, 2),
                    line_of_least_resistance_m=legacy_b,
                    grid_a_m=legacy_a,
                    grid_b_m=legacy_b,
                    grid_label=legacy_label,
                    x50_mm=round(legacy.point.x50_mm, 1),
                    oversize_pct=round(legacy.point.oversize_pct, 2),
                    reached=legacy.reached,
                    details=FragmentationDetailsSchema.model_validate(legacy.point),
                ),
            )
        )

    return BlastOptimizeResponse(
        variants=variants,
        max_oversize_threshold_pct=threshold,
        rock_name=rock.name,
        explosive_name=explosive.name,
        model_version=MODEL_VERSION,
        kuzram=KuzRamSettingsSchema.from_settings(settings),
    )


def calibrate_kuzram(request: KuzRamCalibrateRequest) -> KuzRamCalibrateResponse:
    """C(A) по фактическим взрывам: для каждой строки и среднее геометрическое по решённым."""
    rock, explosive, target = blast_request_to_engine_inputs(request)
    settings = (request.kuzram or KuzRamSettingsSchema()).to_settings()
    engine = BlastEngine(rock, explosive, target)
    rows: list[KuzRamCalibrationRow] = []
    solved: list[float] = []

    for fact in request.facts:
        correction = engine.calibrate_rock_factor(fact.crown_mm, fact.q_kg_m3, fact.oversize_pct, settings)
        if correction is not None:
            solved.append(correction)
        rows.append(
            KuzRamCalibrationRow(
                crown_mm=fact.crown_mm,
                q_kg_m3=fact.q_kg_m3,
                oversize_pct=fact.oversize_pct,
                legacy_oversize_pct=round(engine.legacy_point(fact.crown_mm, fact.q_kg_m3).oversize_pct, 2),
                model_oversize_pct=round(
                    engine.kuzram_point(fact.crown_mm, fact.q_kg_m3, settings).oversize_pct, 2
                ),
                rock_factor_correction=None if correction is None else round(correction, 3),
                note=None
                if correction is not None
                else "Фактический негабарит не получается ни при каком C(A) от 0,1 до 10.",
            )
        )

    mean = math.exp(sum(math.log(value) for value in solved) / len(solved)) if solved else None
    return KuzRamCalibrateResponse(
        rows=rows,
        rock_factor_correction=None if mean is None else round(mean, 3),
        used=len(solved),
        skipped=len(rows) - len(solved),
        model_version=MODEL_VERSION,
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
