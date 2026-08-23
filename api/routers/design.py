"""REST-роутер проектирования БВР: раскладка сетки и паспорта блока."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Response, status

from api.schemas.cost import AggregatedCostResultSchema
from api.schemas.design import (
    AnalyzeRequest,
    AnalyzeResponse,
    BlastDesignSchema,
    ChargeGenerateRequest,
    ChargeGenerateResponse,
    DesignCostRequest,
    DesignListResponse,
    EngineeringMapsRequest,
    EngineeringMapsSchema,
    FragmentationModelsResponse,
    FragmentationPredictRequest,
    FragmentationPredictResponse,
    HoleGeometryEditRequest,
    HoleGeometryEditResponse,
    HoleInsertRequest,
    HoleInsertResponse,
    PatternGenerateRequest,
    PatternGenerateResponse,
    SurfaceImportRequest,
    SurfaceImportResponse,
    SurfaceSampleRequest,
    SurfaceSampleResponse,
    TieGenerateRequest,
    TieGenerateResponse,
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
)
from api.security import require_internal_access
from api.services import design_service

router = APIRouter(prefix="/design", tags=["design"])


@router.post("/pattern", response_model=PatternGenerateResponse)
def post_pattern(request: PatternGenerateRequest) -> PatternGenerateResponse:
    return design_service.generate_pattern(request)


@router.post("/maps", response_model=EngineeringMapsSchema)
def post_maps(request: EngineeringMapsRequest) -> EngineeringMapsSchema:
    return design_service.design_maps(request)


@router.get("/fragmentation/models", response_model=FragmentationModelsResponse)
def get_fragmentation_models() -> FragmentationModelsResponse:
    return design_service.list_fragmentation_models()


@router.post("/fragmentation", response_model=FragmentationPredictResponse)
def post_fragmentation(request: FragmentationPredictRequest) -> FragmentationPredictResponse:
    return design_service.predict_fragmentation(request)


@router.post("/holes/geometry", response_model=HoleGeometryEditResponse)
def post_hole_geometry(request: HoleGeometryEditRequest) -> HoleGeometryEditResponse:
    return design_service.edit_hole_geometry(request)


@router.post("/holes/insert", response_model=HoleInsertResponse)
def post_hole_insert(request: HoleInsertRequest) -> HoleInsertResponse:
    return design_service.insert_hole(request)


@router.post("/surfaces/import", response_model=SurfaceImportResponse)
def post_surface_import(request: SurfaceImportRequest) -> SurfaceImportResponse:
    return design_service.import_surface(request)


@router.post("/surfaces/sample", response_model=SurfaceSampleResponse)
def post_surface_sample(request: SurfaceSampleRequest) -> SurfaceSampleResponse:
    return design_service.sample_surface(request)


@router.post("/geology/assign", response_model=GeologyAssignResponse)
def post_geology_assign(request: GeologyAssignRequest) -> GeologyAssignResponse:
    return design_service.assign_domain(request)


@router.post("/geology/intercept", response_model=GeologyInterceptResponse)
def post_geology_intercept(request: GeologyInterceptRequest) -> GeologyInterceptResponse:
    return design_service.intercept_geology(request)


@router.post("/charge", response_model=ChargeGenerateResponse)
def post_charge(request: ChargeGenerateRequest) -> ChargeGenerateResponse:
    return design_service.generate_charge(request)


@router.post("/tie/generate", response_model=TieGenerateResponse)
def post_tie_generate(request: TieGenerateRequest) -> TieGenerateResponse:
    return design_service.generate_tie(request)


@router.post("/analyze", response_model=AnalyzeResponse)
def post_analyze(request: AnalyzeRequest) -> AnalyzeResponse:
    return design_service.analyze_design(request)


@router.post("/receptors", response_model=ReceptorAttachResponse)
def post_receptor(request: ReceptorAttachRequest) -> ReceptorAttachResponse:
    return design_service.attach_receptor(request)


@router.get("/vibration/conventions", response_model=VibrationConventionsResponse)
def get_vibration_conventions() -> VibrationConventionsResponse:
    return design_service.list_vibration_conventions()


@router.post("/vibration", response_model=VibrationPredictResponse)
def post_vibration(request: VibrationPredictRequest) -> VibrationPredictResponse:
    return design_service.predict_vibration(request)


@router.get("/as-drilled/mwd-schema", response_model=MwdSchemaResponse)
def get_mwd_schema() -> MwdSchemaResponse:
    return design_service.list_mwd_schema()


@router.post("/as-drilled", response_model=AsDrilledRecordResponse)
def post_as_drilled(request: AsDrilledRecordRequest) -> AsDrilledRecordResponse:
    return design_service.record_as_drilled(request)


@router.post("/as-drilled/compare", response_model=AsDrilledCompareResponse)
def post_as_drilled_compare(request: AsDrilledCompareRequest) -> AsDrilledCompareResponse:
    return design_service.compare_as_drilled(request)


@router.post("/as-drilled/mwd", response_model=AsDrilledRecordResponse)
def post_as_drilled_mwd(request: MwdImportRequest) -> AsDrilledRecordResponse:
    return design_service.import_mwd(request)


@router.post("/as-charged", response_model=AsChargedRecordResponse)
def post_as_charged(request: AsChargedRecordRequest) -> AsChargedRecordResponse:
    return design_service.record_as_charged(request)


@router.post("/as-charged/compare", response_model=AsChargedCompareResponse)
def post_as_charged_compare(request: AsChargedCompareRequest) -> AsChargedCompareResponse:
    return design_service.compare_as_charged(request)


@router.post("/as-fired", response_model=AsFiredRecordResponse)
def post_as_fired(request: AsFiredRecordRequest) -> AsFiredRecordResponse:
    return design_service.record_as_fired(request)


@router.post("/as-fired/compare", response_model=AsFiredCompareResponse)
def post_as_fired_compare(request: AsFiredCompareRequest) -> AsFiredCompareResponse:
    return design_service.compare_as_fired(request)


@router.post("/execution/compare", response_model=ExecutionCompareResponse)
def post_execution_compare(request: ExecutionCompareRequest) -> ExecutionCompareResponse:
    return design_service.compare_execution(request)


@router.post("/cost", response_model=AggregatedCostResultSchema)
def post_design_cost(request: DesignCostRequest) -> AggregatedCostResultSchema:
    return design_service.estimate_design_cost(request)


@router.get("/plans", response_model=DesignListResponse)
def list_plans(session: dict = Depends(require_internal_access)) -> DesignListResponse:
    return design_service.list_plans(session["org"])


@router.post("/plans", response_model=BlastDesignSchema, status_code=status.HTTP_201_CREATED)
def create_plan(
    body: BlastDesignSchema, session: dict = Depends(require_internal_access)
) -> BlastDesignSchema:
    return design_service.create_plan(session["org"], body)


@router.get("/plans/{design_id}", response_model=BlastDesignSchema)
def get_plan(design_id: str, session: dict = Depends(require_internal_access)) -> BlastDesignSchema:
    return design_service.get_plan(session["org"], design_id)


@router.put("/plans/{design_id}", response_model=BlastDesignSchema)
def save_plan(
    design_id: str,
    body: BlastDesignSchema,
    session: dict = Depends(require_internal_access),
) -> BlastDesignSchema:
    return design_service.save_plan(session["org"], design_id, body)


@router.delete("/plans/{design_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_plan(design_id: str, session: dict = Depends(require_internal_access)) -> None:
    design_service.delete_plan(session["org"], design_id)


@router.get("/plans/{design_id}/export.csv")
def export_plan_csv(
    design_id: str, session: dict = Depends(require_internal_access)
) -> Response:
    csv_text = design_service.export_plan_csv(session["org"], design_id)
    return Response(
        content=csv_text,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{design_id}.csv"'},
    )


@router.get("/plans/{design_id}/passport.html")
def export_plan_passport(
    design_id: str, session: dict = Depends(require_internal_access)
) -> Response:
    html_text = design_service.export_plan_passport(session["org"], design_id)
    return Response(content=html_text, media_type="text/html")
