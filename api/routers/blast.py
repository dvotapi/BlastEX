"""REST-роутер технологического расчёта: оптимизация сетки, геометрия, схема заряда."""
from __future__ import annotations

import io

from fastapi import APIRouter, Depends, Response

from api.schemas.blast import (
    BlastConstantsSchema,
    BlastGeometryRequest,
    BlastGeometryResponse,
    BlastOptimizeRequest,
    BlastOptimizeResponse,
)
from api.services.blast_service import compute_geometry, optimize_blast
from api.services.legacy_references import current_legacy_references
from Blast import CROWNS_MM
from cost.geometry import (
    DETONATOR_DELAY_MS_OPTIONS,
    NSI_LENGTH_OPTIONS_M,
    block_geometry_table_rows,
    contour_hole_table_rows,
    drilling_block_table_rows,
    drilling_hole_table_rows,
    hole_geometry_table_rows,
)
from cost.v2.legacy_adapter import LegacyReferences

router = APIRouter(prefix="/blast", tags=["blast"])


@router.get("/options", response_model=BlastConstantsSchema)
def blast_options() -> BlastConstantsSchema:
    return BlastConstantsSchema(
        crown_diameters_mm=list(CROWNS_MM),
        nsi_length_options_m=list(NSI_LENGTH_OPTIONS_M),
        detonator_delay_ms_options=list(DETONATOR_DELAY_MS_OPTIONS),
    )


@router.post("/optimize", response_model=BlastOptimizeResponse)
def post_blast_optimize(request: BlastOptimizeRequest) -> BlastOptimizeResponse:
    return optimize_blast(request)


@router.post("/geometry", response_model=BlastGeometryResponse)
def post_blast_geometry(
    payload: BlastGeometryRequest,
    legacy: LegacyReferences = Depends(current_legacy_references),
) -> BlastGeometryResponse:
    hole, block, initiation, label = compute_geometry(payload, legacy)

    if payload.view == "contour":
        hole_rows = contour_hole_table_rows(hole, initiation=initiation)
        block_rows = block_geometry_table_rows(block)
    elif payload.view == "drilling":
        hole_rows = drilling_hole_table_rows(hole)
        block_rows = drilling_block_table_rows(block)
    else:
        hole_rows = hole_geometry_table_rows(hole, initiation=initiation)
        block_rows = block_geometry_table_rows(block)

    return BlastGeometryResponse(
        hole=hole,
        block=block,
        initiation=initiation,
        label=label,
        hole_rows=hole_rows,
        block_rows=block_rows,
    )


@router.post("/hole-scheme")
def post_hole_scheme(
    payload: BlastGeometryRequest,
    legacy: LegacyReferences = Depends(current_legacy_references),
) -> Response:
    import matplotlib.pyplot as plt

    from blast_hole_viz import draw_hole_section

    hole, _block, initiation, label = compute_geometry(payload, legacy)
    fig = draw_hole_section(hole, title=label, initiation=initiation)
    buf = io.BytesIO()
    try:
        fig.savefig(buf, format="svg", bbox_inches="tight")
    finally:
        plt.close(fig)
    return Response(content=buf.getvalue(), media_type="image/svg+xml")
