"""Сервис проекта БВР: раскладка сетки и хранение паспортов команды."""
from __future__ import annotations

from Blast import ExplosiveProperties
from api.exceptions import DesignNotFoundError, InvalidDesignError, InvalidGeometryError
from api.schemas.cost import (
    AggregatedCostResultSchema,
    BlockGeometrySchema,
    CostCalculateRequest,
    HoleGeometrySchema,
    InitiationConfigSchema,
)
from api.schemas.design import (
    AnalyzeRequest,
    AnalyzeResponse,
    BlastDesignSchema,
    ChargeGenerateRequest,
    ChargeGenerateResponse,
    DesignCostRequest,
    DesignListResponse,
    DesignSummarySchema,
    MicSchema,
    PatternGenerateRequest,
    PatternGenerateResponse,
    SummarySchema,
    TieGenerateRequest,
    TieGenerateResponse,
    ValidationWarningSchema,
)
from api.services.cost_service import calculate_cost
from design import persistence as design_persistence
from design.analysis import charge_per_delay, estimate_ppv, summary as run_summary, timing_isolines, validate as run_validate
from design.charging import apply_charge_rules
from design.export import holes_csv, passport_html
from design.geometry import block_volume
from design.models import BlastDesign, BlockContour, Hole
from design.pattern import generate_pattern as run_generate_pattern
from design.timing import build_template_network, resolve_times


def generate_pattern(request: PatternGenerateRequest) -> PatternGenerateResponse:
    contour = BlockContour.from_dict(request.contour.model_dump())
    if len(contour.vertices) < 3:
        raise InvalidGeometryError("Контур блока должен содержать не менее трёх точек.")

    existing_holes = [Hole.from_dict(h.model_dump()) for h in request.existing_holes]
    holes = run_generate_pattern(contour, request.params, existing_holes)

    return PatternGenerateResponse(
        holes=[h.to_dict() for h in holes],
        hole_count=len(holes),
        block_volume_m3=round(block_volume(contour), 2),
    )


def generate_charge(request: ChargeGenerateRequest) -> ChargeGenerateResponse:
    holes = [Hole.from_dict(h.model_dump()) for h in request.holes]
    if not holes:
        raise InvalidDesignError("Список скважин пуст — нечего заряжать.")

    explosive = ExplosiveProperties(
        name=request.explosive.name,
        density_t_m3=request.explosive.density_t_m3,
        power_mj_kg=request.explosive.power_mj_kg,
    )
    loads = apply_charge_rules(holes, request.rules, explosive)

    return ChargeGenerateResponse(
        loads=[ld.to_dict() for ld in loads],
        total_charge_kg=round(sum(ld.total_charge_kg for ld in loads), 2),
        total_holes_charged=sum(1 for ld in loads if ld.total_charge_kg > 0),
    )


def generate_tie(request: TieGenerateRequest) -> TieGenerateResponse:
    holes = [Hole.from_dict(h.model_dump()) for h in request.holes]
    if not holes:
        raise InvalidDesignError("Список скважин пуст — нечего коммутировать.")
    network = build_template_network(holes, request.scheme, request.params)
    return TieGenerateResponse(
        network=network.to_dict(),
        starters_count=len(network.starters),
        connectors_count=len(network.connectors),
    )


def analyze_design(request: AnalyzeRequest) -> AnalyzeResponse:
    design = BlastDesign.from_dict(request.design.model_dump())
    enabled_holes = [h for h in design.holes if h.enabled]

    times, timing_warnings = resolve_times(design.network, enabled_holes)
    validation_warnings = run_validate(design)
    summary_data = run_summary(design)
    mic_data = charge_per_delay(times, design.loads, window_ms=request.mic_window_ms)
    isolines_data = timing_isolines(times, enabled_holes, step_ms=request.isoline_step_ms)

    ppv_mm_s = None
    if request.ppv is not None:
        ppv_mm_s = estimate_ppv(mic_data["mic_kg"], request.ppv.distance_m, request.ppv.k, request.ppv.n)

    return AnalyzeResponse(
        times_ms=times,
        timing_warnings=timing_warnings,
        validation_warnings=[ValidationWarningSchema(**w) for w in validation_warnings],
        summary=SummarySchema(**summary_data),
        mic=MicSchema(**mic_data),
        isolines=isolines_data,
        ppv_mm_s=ppv_mm_s,
    )


def list_plans(team_id: str) -> DesignListResponse:
    summaries = design_persistence.list_designs(team_id)
    return DesignListResponse(
        items=[DesignSummarySchema(**s.__dict__) for s in summaries]
    )


def create_plan(team_id: str, schema: BlastDesignSchema) -> BlastDesignSchema:
    design = BlastDesign.from_dict(schema.model_dump())
    design.design_id = ""  # новый паспорт всегда получает свежий id
    saved = design_persistence.save_design(team_id, design)
    return BlastDesignSchema(**saved.to_dict())


def get_plan(team_id: str, design_id: str) -> BlastDesignSchema:
    try:
        design = design_persistence.load_design(team_id, design_id)
    except design_persistence.DesignNotFoundError as exc:
        raise DesignNotFoundError(design_id) from exc
    return BlastDesignSchema(**design.to_dict())


def save_plan(team_id: str, design_id: str, schema: BlastDesignSchema) -> BlastDesignSchema:
    if schema.design_id and schema.design_id != design_id:
        raise InvalidDesignError("Идентификатор паспорта в теле запроса не совпадает с адресом.")
    design = BlastDesign.from_dict(schema.model_dump())
    design.design_id = design_id
    saved = design_persistence.save_design(team_id, design)
    return BlastDesignSchema(**saved.to_dict())


def delete_plan(team_id: str, design_id: str) -> None:
    try:
        design_persistence.delete_design(team_id, design_id)
    except design_persistence.DesignNotFoundError as exc:
        raise DesignNotFoundError(design_id) from exc


def rename_plan(team_id: str, design_id: str, name: str) -> BlastDesignSchema:
    try:
        design = design_persistence.rename_design(team_id, design_id, name)
    except design_persistence.DesignNotFoundError as exc:
        raise DesignNotFoundError(design_id) from exc
    return BlastDesignSchema(**design.to_dict())


def export_plan_csv(team_id: str, design_id: str) -> str:
    try:
        design = design_persistence.load_design(team_id, design_id)
    except design_persistence.DesignNotFoundError as exc:
        raise DesignNotFoundError(design_id) from exc
    return holes_csv(design)


def _design_to_hole_and_block(design: BlastDesign) -> tuple[HoleGeometrySchema, BlockGeometrySchema, InitiationConfigSchema]:
    """Строит входные данные сметы из фактической геометрии проекта.

    В отличие от формульной оценки в `cost.geometry` (объём блока делится на
    выход одной скважины), здесь `total_holes`, `drilling_footage_m`,
    `total_charge_mass_kg` и `block_volume_m3` — фактические суммы по
    построенной сетке и заряжанию, а не оценка.
    """
    enabled = [h for h in design.holes if h.enabled]
    total_holes = len(enabled)
    if total_holes == 0:
        raise InvalidDesignError("В паспорте нет активных скважин — нечего передавать в смету.")

    drilling_footage_m = sum(h.length_m for h in enabled)
    avg_depth_m = drilling_footage_m / total_holes
    avg_subdrill_m = sum(h.subdrill_m for h in enabled) / total_holes
    avg_diameter_mm = sum(h.diameter_mm for h in enabled) / total_holes
    hole_oversize_coeff = float(design.charge_rules.get("hole_oversize_coeff") or 1.05) if design.charge_rules else 1.05

    loads_by_hole = {ld.hole_id: ld for ld in design.loads}
    charged = [loads_by_hole[h.id] for h in enabled if h.id in loads_by_hole and loads_by_hole[h.id].total_charge_kg > 0]
    total_charge_mass_kg = sum(ld.total_charge_kg for ld in charged)
    avg_charge_mass_kg = total_charge_mass_kg / len(charged) if charged else 0.0
    total_primers = sum(len(ld.primers) for ld in design.loads)

    stemming_lengths = [
        deck.to_m - deck.from_m for ld in charged for deck in ld.decks if deck.kind == "stemming"
    ]
    avg_undercharge_m = sum(stemming_lengths) / len(stemming_lengths) if stemming_lengths else 0.0

    block_volume_m3 = block_volume(design.contour)
    specific_q = total_charge_mass_kg / block_volume_m3 if block_volume_m3 > 0 else 0.0
    yield_per_hole_m3 = block_volume_m3 / total_holes if total_holes else 0.0

    network = design.network
    is_nonel = network.system == "nonel"
    total_surface_nsi = len([c for c in network.connectors if c.kind == "surface_nsi"]) if is_nonel else 0
    # downhole_delay_ms содержит запись только для скважин, реально включённых
    # в схему (build_template_network по умолчанию не берёт контурные скважины) —
    # total_holes здесь был бы завышением, если в проекте есть контурные скважины.
    total_downhole_nsi = len(network.downhole_delay_ms) if is_nonel else 0
    total_start_nsi = len(network.starters) if is_nonel else 0
    downhole_delay_ms = int(next(iter(network.downhole_delay_ms.values()), 500)) if network.downhole_delay_ms else 500

    intermediate_per_hole = max(1, round(total_primers / total_holes)) if total_holes else 1

    hole = HoleGeometrySchema(
        grid_a_m=float(design.pattern_params.get("spacing_a_m") or 1.0),
        grid_b_m=float(design.pattern_params.get("burden_b_m") or 1.0),
        depth_m=avg_depth_m,
        overdrill_m=avg_subdrill_m,
        undercharge_m=avg_undercharge_m,
        charge_length_m=max(0.0, avg_depth_m - avg_undercharge_m),
        charge_diameter_m=(avg_diameter_mm / 1000.0) * hole_oversize_coeff,
        capacity_kg_per_m=(total_charge_mass_kg / drilling_footage_m) if drilling_footage_m > 0 else 0.0,
        charge_mass_kg=avg_charge_mass_kg,
        yield_m3=yield_per_hole_m3,
        specific_q_kg_m3=specific_q,
        explosive_name=design.explosive_key,
        explosive_label=design.explosive_key,
    )

    initiation = InitiationConfigSchema(
        intermediate_detonators_per_hole=intermediate_per_hole,
        nsi_per_hole=1,
        nsi_length_1_m=12.0,
        nsi_length_2_m=0.0,
        detonator_delay_ms=downhole_delay_ms,
    )

    block = BlockGeometrySchema(
        block_volume_m3=block_volume_m3,
        yield_per_hole_m3=yield_per_hole_m3,
        hole_count=total_holes,
        additional_holes_pct=0.0,
        additional_holes=0,
        total_holes=total_holes,
        drilling_footage_m=drilling_footage_m,
        total_charge_mass_kg=total_charge_mass_kg,
        specific_q_kg_m3=specific_q,
        intermediate_detonators_per_hole=intermediate_per_hole,
        nsi_per_hole=1,
        nsi_length_1_m=12.0,
        nsi_length_2_m=0.0,
        detonator_delay_ms=downhole_delay_ms,
        total_intermediate_detonators=total_primers,
        total_downhole_nsi=total_downhole_nsi,
        total_nsi_length_m=total_downhole_nsi * 12.0,
        total_boosters=total_primers,
        total_surface_nsi=total_surface_nsi,
        total_start_nsi=total_start_nsi,
    )

    return hole, block, initiation


def estimate_design_cost(request: DesignCostRequest) -> AggregatedCostResultSchema:
    from api.schemas.cost import BlockCalculationInputSchema

    design = BlastDesign.from_dict(request.design.model_dump())
    hole, block, initiation = _design_to_hole_and_block(design)

    block_input = BlockCalculationInputSchema(
        hole=hole,
        block=block,
        initiation=initiation,
        explosive_key=design.explosive_key,
        hole_depth_m=hole.depth_m,
        materials_selection=request.materials_selection,
        production_volume_tons=0.0,
        rock_density_t_m3=2.65,
    )

    cost_request = CostCalculateRequest(
        scenario_id=request.scenario_id,
        work_object_name=request.work_object_name,
        context=request.context,
        block=block_input,
        materials_selection=request.materials_selection,
        production_volume_tons=0.0,
    )
    return calculate_cost(cost_request)


def export_plan_passport(team_id: str, design_id: str) -> str:
    try:
        design = design_persistence.load_design(team_id, design_id)
    except design_persistence.DesignNotFoundError as exc:
        raise DesignNotFoundError(design_id) from exc
    return passport_html(design)
