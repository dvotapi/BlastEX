"""Сервис проекта БВР: раскладка сетки и хранение паспортов команды."""
from __future__ import annotations

from Blast import ExplosiveProperties
from api.exceptions import (
    DesignNotFoundError,
    FrozenDesignError,
    InvalidDesignError,
    InvalidGeometryError,
    InvalidLifecycleError,
    InvalidSurveyError,
)
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
    DesignForkRequest,
    DesignListResponse,
    DesignSummarySchema,
    LifecycleMetaResponse,
    LifecycleStateSchema,
    LifecycleStatusSchema,
    LifecycleTransitionRequest,
    WorkstationMetaResponse,
    EngineeringMapsRequest,
    EngineeringMapsSchema,
    FragmentationModelsResponse,
    FragmentationPredictRequest,
    FragmentationPredictResponse,
    HoleGeometryEditRequest,
    HoleGeometryEditResponse,
    HoleInsertRequest,
    HoleInsertResponse,
    MicSchema,
    PatternGenerateRequest,
    PatternGenerateResponse,
    SummarySchema,
    SurfaceImportRequest,
    SurfaceImportResponse,
    BenchDxfImportRequest,
    BenchDxfImportResponse,
    BenchFromPolylinesRequest,
    DrawingPolylineSchema,
    DrawingScanResponse,
    Point3Schema,
    SurfaceSampleRequest,
    SurfaceSampleResponse,
    SurfaceStatsSchema,
    TieGenerateRequest,
    TieGenerateResponse,
    ValidationWarningSchema,
    GeologyAssignRequest,
    GeologyAssignResponse,
    GeologyInterceptRequest,
    GeologyInterceptResponse,
    ReceptorAttachRequest,
    ReceptorAttachResponse,
    VibrationConventionsResponse,
    VibrationPredictRequest,
    VibrationPredictResponse,
    AsDrilledRecordRequest,
    AsDrilledRecordResponse,
    AsDrilledCompareRequest,
    AsDrilledCompareResponse,
    MwdImportRequest,
    MwdSchemaResponse,
    AsChargedRecordRequest,
    AsChargedRecordResponse,
    AsChargedCompareRequest,
    AsChargedCompareResponse,
    AsFiredRecordRequest,
    AsFiredRecordResponse,
    AsFiredCompareRequest,
    AsFiredCompareResponse,
    ExecutionCompareRequest,
    ExecutionCompareResponse,
    BlastResultRecordRequest,
    BlastResultRecordResponse,
    BlastResultCompareRequest,
    BlastResultCompareResponse,
)
from api.services.cost_service import calculate_cost
from design import lifecycle as design_lifecycle
from design import persistence as design_persistence
from design import workstation as design_workstation
from design.analysis import charge_per_delay, estimate_ppv, summary as run_summary, timing_isolines, validate as run_validate
from design.charging import apply_charge_rules
from design.editing import apply_hole_geometry, insert_manual_hole
from design.export import holes_csv
from design.reporting.html import passport_html
from design.geometry import block_volume
from design.geology import apply_domains_to_holes, assign_domain_polygon
from design.maps import engineering_maps
from design.models import (
    AsChargedHole,
    AsDrilledHole,
    AsFiredHole,
    BlastDesign,
    BlastDomain,
    BlockContour,
    BenchSurface,
    Hole,
    Point3,
    Receptor,
    VibrationMeasurement,
)
from design.pattern import generate_pattern as run_generate_pattern
from design.spatial.coordinates import CoordinateSystem
from design.spatial.drawing import DrawingError, read_drawing
from design.spatial.io import (
    SurveyImportError,
    build_bench_from_polylines,
    import_bench_dxf as import_bench_dxf_source,
    import_survey,
)
from design.spatial.surfaces import SURFACE_KINDS, SurfaceModel, SurfaceSet, build_surface
from design.timing import TimingExprError, build_template_network, resolve_network


def _surfaces_from_request(payload) -> SurfaceSet | None:
    if payload is None:
        return None
    return SurfaceSet.from_dict(payload.model_dump())


def generate_pattern(request: PatternGenerateRequest) -> PatternGenerateResponse:
    contour = BlockContour.from_dict(request.contour.model_dump())
    if len(contour.vertices) < 3:
        raise InvalidGeometryError("Контур блока должен содержать не менее трёх точек.")

    existing_holes = [Hole.from_dict(h.model_dump()) for h in request.existing_holes]
    surfaces = _surfaces_from_request(request.surfaces)
    domains = [BlastDomain.from_dict(d.model_dump()) for d in request.domains]
    holes = run_generate_pattern(contour, request.params, existing_holes, surfaces, domains)

    return PatternGenerateResponse(
        holes=[h.to_dict() for h in holes],
        hole_count=len(holes),
        block_volume_m3=round(block_volume(contour, surfaces), 2),
    )


def import_surface(request: SurfaceImportRequest) -> SurfaceImportResponse:
    kind = request.kind if request.kind in SURFACE_KINDS else "top"
    try:
        survey = import_survey(request.content, filename=request.filename, format=request.format)
    except SurveyImportError as exc:
        raise InvalidSurveyError(str(exc)) from exc
    surface = build_surface(
        kind,
        survey.points,
        polylines=survey.polylines,
        name=request.name,
        source_format=survey.source_format,
        source_name=survey.source_name or request.filename,
        coordinate_system=CoordinateSystem.from_dict(request.coordinate_system.model_dump()),
    )
    if not surface.has_tin and not surface.points:
        raise InvalidSurveyError("Не удалось построить поверхность: слишком мало точек.")
    return SurfaceImportResponse(
        surface=SurfaceModel.from_dict(surface.to_dict()).to_dict(),
        stats=SurfaceStatsSchema(**surface.stats()),
    )


def scan_drawing(content: bytes, filename: str) -> DrawingScanResponse:
    """Разбирает загруженный чертёж на полилинии для ручного выбора бровок."""

    try:
        scan = read_drawing(content, filename)
    except DrawingError as exc:
        raise InvalidSurveyError(str(exc)) from exc
    return DrawingScanResponse(
        polylines=[
            DrawingPolylineSchema(
                id=item.id,
                layer=item.layer,
                entity=item.entity,
                closed=item.closed,
                points=[Point3Schema(x=p.x, y=p.y, z=p.z) for p in item.points],
                length_m=item.length_m,
                area_m2=item.area_m2,
                z_min=item.z_min,
                z_max=item.z_max,
            )
            for item in scan.polylines
        ],
        source_name=scan.source_name,
        converted_from=scan.converted_from,
        truncated=scan.truncated,
    )


def bench_from_polylines(request: BenchFromPolylinesRequest) -> BenchDxfImportResponse:
    """Собирает уступ из двух выбранных вручную полилиний."""

    crest = [Point3.from_dict(p.model_dump()) for p in request.crest]
    toe = [Point3.from_dict(p.model_dump()) for p in request.toe]
    try:
        imported = build_bench_from_polylines(crest, toe, request.crest_layer, request.toe_layer)
    except SurveyImportError as exc:
        raise InvalidSurveyError(str(exc)) from exc
    return _bench_response(imported, request.filename or "block.dxf", request.coordinate_system)


def import_bench_dxf(request: BenchDxfImportRequest) -> BenchDxfImportResponse:
    try:
        imported = import_bench_dxf_source(request.content)
    except SurveyImportError as exc:
        raise InvalidSurveyError(str(exc)) from exc
    return _bench_response(imported, request.filename or "block.dxf", request.coordinate_system)


def _bench_response(imported, source_name: str, coordinate_system_schema) -> BenchDxfImportResponse:
    coordinate_system = CoordinateSystem.from_dict(coordinate_system_schema.model_dump())
    top = build_surface(
        "top", imported.crest, polylines=[imported.crest], name="Верхняя бровка",
        source_format="dxf", source_name=source_name, coordinate_system=coordinate_system,
    )
    floor = build_surface(
        "floor", imported.toe, polylines=[imported.toe], name="Нижняя бровка",
        source_format="dxf", source_name=source_name, coordinate_system=coordinate_system,
    )
    face = build_surface(
        "face", [*imported.crest, *imported.toe], polylines=[imported.crest, imported.toe], name="Откос блока",
        source_format="dxf", source_name=source_name, coordinate_system=coordinate_system,
    )
    contour = BlockContour(
        name=source_name.rsplit(".", 1)[0], vertices=imported.contour,
        bench=BenchSurface(crest_z_m=imported.crest_z_m, toe_z_m=imported.toe_z_m),
    )
    return BenchDxfImportResponse(
        contour=contour.to_dict(), surfaces=SurfaceSet(top=top, floor=floor, face=face).to_dict(),
        crest_layer=imported.crest_layer, toe_layer=imported.toe_layer,
        crest_z_m=imported.crest_z_m, toe_z_m=imported.toe_z_m, vertex_count=len(imported.contour),
    )


def sample_surface(request: SurfaceSampleRequest) -> SurfaceSampleResponse:
    surface = SurfaceModel.from_dict(request.surface.model_dump())
    if surface is None:
        raise InvalidSurveyError("Поверхность не задана.")
    elevations: list[float | None] = []
    for raw in request.points:
        if len(raw) < 2:
            elevations.append(None)
            continue
        elevations.append(surface.elevation_at(float(raw[0]), float(raw[1])))
    return SurfaceSampleResponse(elevations=elevations)


def assign_domain(request: GeologyAssignRequest) -> GeologyAssignResponse:
    domain = BlastDomain.from_dict(request.domain.model_dump())
    polygon = [Point3.from_dict(p.model_dump()) for p in request.polygon]
    try:
        assigned = assign_domain_polygon(domain, polygon)
    except ValueError as exc:
        raise InvalidGeometryError(str(exc)) from exc
    return GeologyAssignResponse(domain=assigned.to_dict())


def intercept_geology(request: GeologyInterceptRequest) -> GeologyInterceptResponse:
    holes = [Hole.from_dict(h.model_dump()) for h in request.holes]
    domains = [BlastDomain.from_dict(d.model_dump()) for d in request.domains]
    updated = apply_domains_to_holes(holes, domains, water_table_z_m=request.water_table_z_m)
    return GeologyInterceptResponse(
        holes=[h.to_dict() for h in updated],
        interval_count=sum(len(h.intervals) for h in updated),
        water_interval_count=sum(len(h.water_intervals) for h in updated),
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
    catalog = [
        ExplosiveProperties(
            name=item.name,
            density_t_m3=item.density_t_m3,
            power_mj_kg=item.power_mj_kg,
        )
        for item in request.explosives
    ]
    contour = BlockContour.from_dict(request.contour.model_dump()) if request.contour is not None else None
    loads = apply_charge_rules(holes, request.rules, explosive, contour=contour, explosives=catalog)

    return ChargeGenerateResponse(
        loads=[ld.to_dict() for ld in loads],
        total_charge_kg=round(sum(ld.total_charge_kg for ld in loads), 2),
        total_holes_charged=sum(1 for ld in loads if ld.total_charge_kg > 0),
    )


def generate_tie(request: TieGenerateRequest) -> TieGenerateResponse:
    holes = [Hole.from_dict(h.model_dump()) for h in request.holes]
    if not holes:
        raise InvalidDesignError("Список скважин пуст — нечего коммутировать.")
    try:
        network = build_template_network(holes, request.scheme, request.params)
    except TimingExprError as exc:
        raise InvalidDesignError(str(exc)) from exc
    return TieGenerateResponse(
        network=network.to_dict(),
        starters_count=len(network.starters),
        connectors_count=len(network.connectors),
    )


def analyze_design(request: AnalyzeRequest) -> AnalyzeResponse:
    design = BlastDesign.from_dict(request.design.model_dump())
    enabled_holes = [h for h in design.holes if h.enabled]

    result = resolve_network(design.network, enabled_holes, design.loads)
    times, timing_warnings = result.times_ms, result.warnings
    validation_warnings = run_validate(design)
    summary_data = run_summary(design)
    mic_data = charge_per_delay(times, design.loads, window_ms=request.mic_window_ms, events=result.events)
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
        maps=EngineeringMapsSchema(**engineering_maps(design)),
        firing_events=[event.to_dict() for event in result.events],
    )


def design_maps(request: EngineeringMapsRequest) -> EngineeringMapsSchema:
    design = BlastDesign.from_dict(request.design.model_dump())
    return EngineeringMapsSchema(**engineering_maps(design))


def attach_receptor(request: ReceptorAttachRequest) -> ReceptorAttachResponse:
    from design.vibration import attach_receptor as attach

    design = BlastDesign.from_dict(request.design.model_dump())
    receptor = attach(design, Receptor.from_dict(request.receptor.model_dump()))
    return ReceptorAttachResponse(
        receptor=receptor.to_dict(),
        receptors=[item.to_dict() for item in design.receptors],
    )


def list_vibration_conventions() -> VibrationConventionsResponse:
    from design.vibration import list_conventions

    return VibrationConventionsResponse(conventions=list_conventions())


def predict_vibration(request: VibrationPredictRequest) -> VibrationPredictResponse:
    from design.vibration import ScaledDistanceMismatchError, predict_design

    design = BlastDesign.from_dict(request.design.model_dump())
    measured = [VibrationMeasurement.from_dict(item.model_dump()) for item in request.measured]
    try:
        payload = predict_design(
            design,
            model_id=request.model_id,
            mic_window_ms=request.mic_window_ms,
            measurements=measured,
        )
    except (ValueError, ScaledDistanceMismatchError) as exc:
        raise InvalidDesignError(str(exc)) from exc
    return VibrationPredictResponse(**payload)


def list_mwd_schema() -> MwdSchemaResponse:
    from design.as_drilled import mwd_import_schema

    return MwdSchemaResponse(**mwd_import_schema())


def record_as_drilled(request: AsDrilledRecordRequest) -> AsDrilledRecordResponse:
    from design.as_drilled import compare_design, record_as_drilled_many

    design = BlastDesign.from_dict(request.design.model_dump())
    designed_before = [hole.to_dict() for hole in design.holes]
    try:
        record_as_drilled_many(
            design,
            [AsDrilledHole.from_dict(item.model_dump()) for item in request.holes],
            replace=request.replace,
        )
        payload = compare_design(design)
    except ValueError as exc:
        raise InvalidDesignError(str(exc)) from exc
    designed_after = [hole.to_dict() for hole in design.holes]
    if designed_after != designed_before:
        raise InvalidDesignError("Запись факта бурения не должна менять проектные скважины.")
    return AsDrilledRecordResponse(
        **payload,
        holes=designed_after,
    )


def compare_as_drilled(request: AsDrilledCompareRequest) -> AsDrilledCompareResponse:
    from design.as_drilled import compare_design

    design = BlastDesign.from_dict(request.design.model_dump())
    designed_before = [hole.to_dict() for hole in design.holes]
    try:
        payload = compare_design(design)
    except ValueError as exc:
        raise InvalidDesignError(str(exc)) from exc
    if [hole.to_dict() for hole in design.holes] != designed_before:
        raise InvalidDesignError("Сравнение факта с проектом не должно менять проектные скважины.")
    return AsDrilledCompareResponse(**payload)


def import_mwd(request: MwdImportRequest) -> AsDrilledRecordResponse:
    from design.as_drilled import attach_mwd, compare_design, parse_mwd_samples

    design = BlastDesign.from_dict(request.design.model_dump())
    designed_before = [hole.to_dict() for hole in design.holes]
    try:
        attach_mwd(
            design,
            request.design_hole_id,
            parse_mwd_samples(request.samples),
            source=request.source,
        )
        payload = compare_design(design)
    except ValueError as exc:
        raise InvalidDesignError(str(exc)) from exc
    designed_after = [hole.to_dict() for hole in design.holes]
    if designed_after != designed_before:
        raise InvalidDesignError("Импорт MWD не должен менять проектные скважины.")
    return AsDrilledRecordResponse(**payload, holes=designed_after)


def _guard_designed(design: BlastDesign) -> tuple:
    return (
        [hole.to_dict() for hole in design.holes],
        [load.to_dict() for load in design.loads],
        [item.to_dict() for item in design.network.detonators],
        dict(design.network.electronic_times_ms),
    )


def record_as_charged(request: AsChargedRecordRequest) -> AsChargedRecordResponse:
    from design.as_charged import compare_design, record_as_charged_many

    design = BlastDesign.from_dict(request.design.model_dump())
    designed_before = _guard_designed(design)
    try:
        record_as_charged_many(
            design,
            [AsChargedHole.from_dict(item.model_dump()) for item in request.holes],
            replace=request.replace,
        )
        payload = compare_design(design)
    except ValueError as exc:
        raise InvalidDesignError(str(exc)) from exc
    if _guard_designed(design) != designed_before:
        raise InvalidDesignError("Запись факта заряжания не должна менять проектные скважины, заряд или сеть.")
    return AsChargedRecordResponse(
        **payload,
        holes=[hole.to_dict() for hole in design.holes],
        loads=[load.to_dict() for load in design.loads],
    )


def compare_as_charged(request: AsChargedCompareRequest) -> AsChargedCompareResponse:
    from design.as_charged import compare_design

    design = BlastDesign.from_dict(request.design.model_dump())
    designed_before = _guard_designed(design)
    try:
        payload = compare_design(design)
    except ValueError as exc:
        raise InvalidDesignError(str(exc)) from exc
    if _guard_designed(design) != designed_before:
        raise InvalidDesignError("Сравнение факта заряжания не должно менять проектные скважины, заряд или сеть.")
    return AsChargedCompareResponse(**payload)


def record_as_fired(request: AsFiredRecordRequest) -> AsFiredRecordResponse:
    from design.as_fired import compare_design, record_as_fired_many

    design = BlastDesign.from_dict(request.design.model_dump())
    designed_before = _guard_designed(design)
    try:
        record_as_fired_many(
            design,
            [AsFiredHole.from_dict(item.model_dump()) for item in request.holes],
            replace=request.replace,
        )
        payload = compare_design(design)
    except ValueError as exc:
        raise InvalidDesignError(str(exc)) from exc
    if _guard_designed(design) != designed_before:
        raise InvalidDesignError("Запись факта взрыва не должна менять проектные скважины, заряд или сеть.")
    return AsFiredRecordResponse(
        **payload,
        holes=[hole.to_dict() for hole in design.holes],
        network=design.network.to_dict(),
    )


def compare_as_fired(request: AsFiredCompareRequest) -> AsFiredCompareResponse:
    from design.as_fired import compare_design

    design = BlastDesign.from_dict(request.design.model_dump())
    designed_before = _guard_designed(design)
    try:
        payload = compare_design(design)
    except ValueError as exc:
        raise InvalidDesignError(str(exc)) from exc
    if _guard_designed(design) != designed_before:
        raise InvalidDesignError("Сравнение факта взрыва не должно менять проектные скважины, заряд или сеть.")
    return AsFiredCompareResponse(**payload)


def compare_execution(request: ExecutionCompareRequest) -> ExecutionCompareResponse:
    from design.execution import compare_execution as run_compare_execution

    design = BlastDesign.from_dict(request.design.model_dump())
    designed_before = _guard_designed(design)
    try:
        payload = run_compare_execution(design)
    except ValueError as exc:
        raise InvalidDesignError(str(exc)) from exc
    if _guard_designed(design) != designed_before:
        raise InvalidDesignError("Сводка исполнения не должна менять проектные скважины, заряд или сеть.")
    return ExecutionCompareResponse(**payload)


def _basis_from_request(request):
    from design.blast_result import (
        ComparisonBasis,
        DesignedBackbreak,
        DesignedMuckpile,
        PlannedCost,
        PredictedVibrationSnapshot,
    )
    from simulation.fragmentation.models import DesignedFragmentationTarget, PredictedFragmentation

    predicted_frag = None
    if request.predicted_fragmentation is not None:
        predicted_frag = PredictedFragmentation.from_dict(request.predicted_fragmentation.model_dump())
    planned = None
    if request.planned_cost is not None:
        planned = PlannedCost.from_dict(request.planned_cost.model_dump())
    designed_frag = None
    if request.designed_fragmentation is not None:
        designed_frag = DesignedFragmentationTarget.from_dict(request.designed_fragmentation.model_dump())
    designed_muck = None
    if request.designed_muckpile is not None:
        designed_muck = DesignedMuckpile.from_dict(request.designed_muckpile.model_dump())
    designed_bb = None
    if request.designed_backbreak is not None:
        designed_bb = DesignedBackbreak.from_dict(request.designed_backbreak.model_dump())
    return ComparisonBasis(
        predicted_fragmentation=predicted_frag,
        predicted_vibration=[
            PredictedVibrationSnapshot.from_dict(item.model_dump()) for item in request.predicted_vibration
        ],
        planned_cost=planned,
        designed_fragmentation=designed_frag,
        designed_muckpile=designed_muck,
        designed_backbreak=designed_bb,
        designed_toe_condition=request.designed_toe_condition,
    )


def record_blast_result(request: BlastResultRecordRequest) -> BlastResultRecordResponse:
    from design.blast_result import BlastResult, compare_result, record_blast_result as persist_result

    design = BlastDesign.from_dict(request.design.model_dump())
    designed_before = _guard_designed(design)
    try:
        persist_result(
            design,
            BlastResult.from_dict(request.result.model_dump()),
            basis=_basis_from_request(request),
        )
        payload = compare_result(design)
    except ValueError as exc:
        raise InvalidDesignError(str(exc)) from exc
    if _guard_designed(design) != designed_before:
        raise InvalidDesignError("Запись результатов взрыва не должна менять проектные скважины, заряд или сеть.")
    return BlastResultRecordResponse(
        **payload,
        holes=[hole.to_dict() for hole in design.holes],
        loads=[load.to_dict() for load in design.loads],
        network=design.network.to_dict(),
    )


def compare_blast_result(request: BlastResultCompareRequest) -> BlastResultCompareResponse:
    from design.blast_result import compare_result

    design = BlastDesign.from_dict(request.design.model_dump())
    designed_before = _guard_designed(design)
    try:
        payload = compare_result(design, basis=_basis_from_request(request))
    except ValueError as exc:
        raise InvalidDesignError(str(exc)) from exc
    if _guard_designed(design) != designed_before:
        raise InvalidDesignError("Сравнение результатов взрыва не должно менять проектные скважины, заряд или сеть.")
    return BlastResultCompareResponse(**payload)


def list_fragmentation_models() -> FragmentationModelsResponse:
    from simulation.fragmentation.engine import list_models

    return FragmentationModelsResponse(models=list_models())


def predict_fragmentation(request: FragmentationPredictRequest) -> FragmentationPredictResponse:
    from simulation.fragmentation.engine import predict_design
    from simulation.fragmentation.models import Calibration, DistributionPoint, MeasuredFragmentation
    from simulation.fragmentation.regions import ExplosiveSpec, RockSpec

    design = BlastDesign.from_dict(request.design.model_dump())
    rock = None
    if request.rock is not None:
        rock = RockSpec(
            name=request.rock.name,
            density_t_m3=request.rock.density_t_m3,
            ucs_mpa=request.rock.ucs_mpa,
            fissuring_ff=request.rock.fissuring_ff,
        )
    explosive = None
    if request.explosive is not None:
        explosive = ExplosiveSpec(
            name=request.explosive.name,
            density_t_m3=request.explosive.density_t_m3,
            power_mj_kg=request.explosive.power_mj_kg,
        )
    catalog = {
        item.name: ExplosiveSpec(name=item.name, density_t_m3=item.density_t_m3, power_mj_kg=item.power_mj_kg)
        for item in request.explosives
    }
    measured = [
        MeasuredFragmentation(
            x20_mm=item.x20_mm,
            x50_mm=item.x50_mm,
            x80_mm=item.x80_mm,
            oversize_pct=item.oversize_pct,
            curve=[DistributionPoint.from_dict(point.model_dump()) for point in item.curve],
            source=item.source,
            method=item.method,
        )
        for item in request.measured
    ]
    try:
        payload = predict_design(
            design,
            model=request.model,
            lump_size_mm=request.lump_size_mm,
            max_oversize_pct=request.max_oversize_pct,
            calibration=Calibration.from_dict(request.calibration),
            default_rock=rock,
            default_explosive=explosive,
            explosives=catalog or None,
            hole_oversize_coeff=request.hole_oversize_coeff,
            measured=measured,
        )
    except ValueError as exc:
        raise InvalidDesignError(str(exc)) from exc
    return FragmentationPredictResponse(**payload)


def list_movement_models():
    from api.schemas.movement import MovementModelsResponse
    from simulation.movement.engine import list_models
    from simulation.movement.models import estimate_kind_payload

    payload = estimate_kind_payload()
    return MovementModelsResponse(models=list_models(), **payload)


def predict_movement(request):
    from api.schemas.movement import MovementPredictRequest, MovementPredictResponse
    from design.models import BlastDesign
    from simulation.movement.engine import predict_design
    from simulation.movement.models import MeasuredMuckpileEcho

    if not isinstance(request, MovementPredictRequest):
        request = MovementPredictRequest.model_validate(request)

    design = BlastDesign.from_dict(request.design.model_dump())
    before_holes = [hole.to_dict() for hole in design.holes]
    before_loads = [load.to_dict() for load in design.loads]
    before_pattern = dict(design.pattern_params or {})
    measured = [MeasuredMuckpileEcho.from_dict(item.model_dump()) for item in request.measured]
    try:
        payload = predict_design(design, measured=measured)
    except ValueError as exc:
        raise InvalidDesignError(str(exc)) from exc
    if [hole.to_dict() for hole in design.holes] != before_holes:
        raise InvalidDesignError("Оценка развала не должна переписывать проектные скважины.")
    if [load.to_dict() for load in design.loads] != before_loads:
        raise InvalidDesignError("Оценка развала не должна переписывать заряжание.")
    if dict(design.pattern_params or {}) != before_pattern:
        raise InvalidDesignError("Оценка развала не должна переписывать сетку.")
    if payload.get("is_physics_simulation"):
        raise InvalidDesignError("Оценка развала не является физической симуляцией.")
    return MovementPredictResponse(**payload)


def edit_hole_geometry(request: HoleGeometryEditRequest) -> HoleGeometryEditResponse:
    hole = Hole.from_dict(request.hole.model_dump())
    contour = BlockContour.from_dict(request.contour.model_dump()) if request.contour is not None else None
    surfaces = _surfaces_from_request(request.surfaces)
    updated = apply_hole_geometry(hole, request.patch, contour, surfaces)
    return HoleGeometryEditResponse(hole=updated.to_dict())


def insert_hole(request: HoleInsertRequest) -> HoleInsertResponse:
    contour = BlockContour.from_dict(request.contour.model_dump())
    if len(contour.vertices) < 3:
        raise InvalidGeometryError("Контур блока должен содержать не менее трёх точек.")
    existing = [Hole.from_dict(h.model_dump()) for h in request.existing_holes]
    surfaces = _surfaces_from_request(request.surfaces)
    hole = insert_manual_hole(existing, request.x, request.y, contour, request.params, surfaces)
    return HoleInsertResponse(hole=hole.to_dict())


def list_plans(team_id: str) -> DesignListResponse:
    summaries = design_persistence.list_designs(team_id)
    return DesignListResponse(
        items=[DesignSummarySchema(**s.__dict__) for s in summaries]
    )


def _map_lifecycle_error(exc: Exception) -> None:
    if isinstance(exc, design_lifecycle.FrozenDesignError):
        raise FrozenDesignError(str(exc)) from exc
    if isinstance(exc, design_lifecycle.InvalidLifecycleError):
        raise InvalidLifecycleError(str(exc)) from exc


def create_plan(team_id: str, schema: BlastDesignSchema, *, actor: str = "") -> BlastDesignSchema:
    design = BlastDesign.from_dict(schema.model_dump())
    design.design_id = ""  # новый паспорт всегда получает свежий id
    design.lifecycle_status = design_lifecycle.STATUS_DRAFT
    saved = design_persistence.save_design(team_id, design, actor=actor)
    return BlastDesignSchema(**saved.to_dict())


def get_plan(team_id: str, design_id: str) -> BlastDesignSchema:
    try:
        design = design_persistence.load_design(team_id, design_id)
    except design_persistence.DesignNotFoundError as exc:
        raise DesignNotFoundError(design_id) from exc
    return BlastDesignSchema(**design.to_dict())


def save_plan(
    team_id: str, design_id: str, schema: BlastDesignSchema, *, actor: str = ""
) -> BlastDesignSchema:
    if schema.design_id and schema.design_id != design_id:
        raise InvalidDesignError("Идентификатор паспорта в теле запроса не совпадает с адресом.")
    design = BlastDesign.from_dict(schema.model_dump())
    design.design_id = design_id
    try:
        saved = design_persistence.save_design(team_id, design, actor=actor)
    except (design_lifecycle.FrozenDesignError, design_lifecycle.InvalidLifecycleError) as exc:
        _map_lifecycle_error(exc)
        raise
    return BlastDesignSchema(**saved.to_dict())


def delete_plan(team_id: str, design_id: str) -> None:
    try:
        design_persistence.delete_design(team_id, design_id)
    except design_persistence.DesignNotFoundError as exc:
        raise DesignNotFoundError(design_id) from exc
    except design_lifecycle.FrozenDesignError as exc:
        raise FrozenDesignError(str(exc)) from exc


def rename_plan(team_id: str, design_id: str, name: str, *, actor: str = "") -> BlastDesignSchema:
    try:
        design = design_persistence.rename_design(team_id, design_id, name, actor=actor)
    except design_persistence.DesignNotFoundError as exc:
        raise DesignNotFoundError(design_id) from exc
    except (design_lifecycle.FrozenDesignError, design_lifecycle.InvalidLifecycleError) as exc:
        _map_lifecycle_error(exc)
        raise
    return BlastDesignSchema(**design.to_dict())


def lifecycle_meta() -> LifecycleMetaResponse:
    return LifecycleMetaResponse(
        statuses=[LifecycleStatusSchema(**item) for item in design_lifecycle.listed_statuses()],
        data_roles=dict(design_lifecycle.DATA_ROLES),
        auto_transition=False,
    )


def workstation_meta() -> WorkstationMetaResponse:
    return WorkstationMetaResponse(**design_workstation.workstation_meta())


def _lifecycle_state(design: BlastDesign) -> LifecycleStateSchema:
    status = design.lifecycle_status
    return LifecycleStateSchema(
        design_id=design.design_id,
        name=design.name,
        lifecycle_status=status,
        revision=design.revision,
        parent_design_id=design.parent_design_id,
        designed_sha256=design.designed_sha256,
        allowed_transitions=design_lifecycle.allowed_transitions(status),
        allowed_mutations=sorted(design_lifecycle.ALLOWED_MUTATIONS[status]),
        frozen_designed=not design_lifecycle.designed_mutable(status),
        frozen_record=design_lifecycle.is_record_frozen(status),
        events=[item.to_dict() for item in design.lifecycle_events],
    )


def get_plan_lifecycle(team_id: str, design_id: str) -> LifecycleStateSchema:
    try:
        design = design_persistence.load_design(team_id, design_id)
    except design_persistence.DesignNotFoundError as exc:
        raise DesignNotFoundError(design_id) from exc
    return _lifecycle_state(design)


def transition_plan(
    team_id: str,
    design_id: str,
    request: LifecycleTransitionRequest,
    *,
    actor: str,
) -> LifecycleStateSchema:
    try:
        design = design_persistence.transition_design(
            team_id,
            design_id,
            to_status=request.to_status,
            actor=actor,
            confirm=request.confirm,
            note=request.note,
        )
    except design_persistence.DesignNotFoundError as exc:
        raise DesignNotFoundError(design_id) from exc
    except (design_lifecycle.FrozenDesignError, design_lifecycle.InvalidLifecycleError) as exc:
        _map_lifecycle_error(exc)
        raise
    return _lifecycle_state(design)


def fork_plan(
    team_id: str,
    design_id: str,
    request: DesignForkRequest,
    *,
    actor: str = "",
) -> BlastDesignSchema:
    try:
        design = design_persistence.fork_design(team_id, design_id, name=request.name, actor=actor)
    except design_persistence.DesignNotFoundError as exc:
        raise DesignNotFoundError(design_id) from exc
    except (design_lifecycle.FrozenDesignError, design_lifecycle.InvalidLifecycleError) as exc:
        _map_lifecycle_error(exc)
        raise
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

    block_volume_m3 = block_volume(design.contour, design.surfaces)
    specific_q = total_charge_mass_kg / block_volume_m3 if block_volume_m3 > 0 else 0.0
    yield_per_hole_m3 = block_volume_m3 / total_holes if total_holes else 0.0

    network = design.network
    is_nonel = network.system == "nonel"
    total_surface_nsi = len([c for c in network.connectors if c.kind == "surface_nsi"]) if is_nonel else 0
    total_downhole_nsi = total_holes if is_nonel and network.downhole_delay_ms else 0
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
        total_nsi_length_m=total_holes * 12.0,
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
