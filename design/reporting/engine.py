"""Assemble an official blast passport without rewriting or approving the design.

Predicted overlays (fragmentation, vibration, movement) stay on the predicted
column. Executed as-drilled / as-charged / as-fired stay on executed.
Measured blast results stay on measured. Planned cost stays designed.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from design.analysis import summary as run_summary
from design.models import (
    ROLE_DESIGNED,
    ROLE_EXECUTED,
    ROLE_MEASURED,
    ROLE_PREDICTED,
    BlastDesign,
)
from design.reporting.types import (
    DISCLAIMER,
    BlastPassport,
    DesignedParameters,
    ExecutedSnapshot,
    HolePassportRow,
    MeasuredOutcomes,
    MetricRow,
    PlannedCostSnapshot,
    PredictedOutcomes,
)

DEFAULT_LUMP_SIZE_MM = 400.0
DEFAULT_MAX_OVERSIZE_PCT = 5.0
DEFAULT_FRAG_MODEL = "kuzram"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _opt_float(raw: Any) -> float | None:
    if raw is None or raw == "":
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def _pattern_float(design: BlastDesign, key: str) -> float | None:
    raw = (design.pattern_params or {}).get(key)
    return _opt_float(raw)


def _mean(values: list[float]) -> float | None:
    if not values:
        return None
    return sum(values) / len(values)


def _designed_guard(design: BlastDesign) -> tuple:
    return (
        [hole.to_dict() for hole in design.holes],
        [load.to_dict() for load in design.loads],
        dict(design.pattern_params or {}),
        dict(design.charge_rules or {}),
        [item.to_dict() for item in design.network.detonators],
        dict(design.network.electronic_times_ms),
        [item.to_dict() for item in design.network.firing_events],
    )


def _assert_design_untouched(design: BlastDesign, before: tuple, action: str) -> None:
    after = _designed_guard(design)
    if after != before:
        raise RuntimeError(f"{action} must not rewrite the designed pattern, charges or network.")


def _planned_cost_from_payload(raw: Any) -> PlannedCostSnapshot | None:
    if raw is None:
        return None
    if isinstance(raw, PlannedCostSnapshot):
        snapshot = PlannedCostSnapshot.from_dict(raw.to_dict())
    elif hasattr(raw, "to_dict"):
        snapshot = PlannedCostSnapshot.from_dict(raw.to_dict())
    elif isinstance(raw, dict):
        snapshot = PlannedCostSnapshot.from_dict(raw)
    else:
        return None
    snapshot.role = ROLE_DESIGNED
    if (
        snapshot.total_amount_rub is None
        and snapshot.cost_per_m3 is None
        and snapshot.variable_total_rub is None
    ):
        return None
    return snapshot


def _collect_designed(design: BlastDesign, *, lump_size_mm: float, max_oversize_pct: float) -> DesignedParameters:
    stats = run_summary(design)
    enabled = [hole for hole in design.holes if hole.enabled]
    diameter = _pattern_float(design, "diameter_mm")
    if diameter is None:
        diameter = _mean([hole.diameter_mm for hole in enabled])
    subdrill = _pattern_float(design, "subdrill_m")
    if subdrill is None:
        subdrill = _mean([hole.subdrill_m for hole in enabled])
    basis = None
    if design.blast_result is not None:
        basis = getattr(design.blast_result, "basis", None)
    designed_frag = getattr(basis, "designed_fragmentation", None) if basis else None
    lump = lump_size_mm
    oversize = max_oversize_pct
    if designed_frag is not None:
        lump = float(designed_frag.lump_size_mm or lump)
        oversize = float(designed_frag.max_oversize_pct if designed_frag.max_oversize_pct is not None else oversize)
    return DesignedParameters(
        name=design.name,
        rock_name=design.rock_name,
        explosive_key=design.explosive_key,
        initiation_system=design.network.system or "",
        spacing_a_m=_pattern_float(design, "spacing_a_m"),
        burden_b_m=_pattern_float(design, "burden_b_m"),
        diameter_mm=diameter,
        subdrill_m=subdrill,
        hole_count=int(stats.get("hole_count") or 0),
        production_hole_count=int(stats.get("production_hole_count") or 0),
        contour_hole_count=int(stats.get("contour_hole_count") or 0),
        charged_hole_count=int(stats.get("charged_hole_count") or 0),
        drilling_metres=float(stats.get("drilling_footage_m") or 0.0),
        block_volume_m3=float(stats.get("block_volume_m3") or 0.0),
        explosive_mass_kg=float(stats.get("total_charge_kg") or 0.0),
        powder_factor_kg_m3=float(stats.get("avg_specific_q_kg_m3") or 0.0),
        lump_size_mm=lump,
        max_oversize_pct=oversize,
    )


def _collect_executed(design: BlastDesign) -> ExecutedSnapshot:
    drilled = list(design.as_drilled_holes)
    charged = list(design.as_charged_holes)
    fired = list(design.as_fired_holes)
    depths = [float(item.actual_depth) for item in drilled if item.actual_depth]
    diameters = [float(item.actual_diameter) for item in drilled if item.actual_diameter]
    masses = [float(item.charge_mass_kg) for item in charged if item.charge_mass_kg]
    return ExecutedSnapshot(
        as_drilled_count=len(drilled),
        as_charged_count=len(charged),
        as_fired_count=len(fired),
        drilling_metres=sum(depths) if depths else None,
        explosive_mass_kg=sum(masses) if masses else None,
        mean_diameter_mm=_mean(diameters),
    )


def _collect_measured(design: BlastDesign) -> MeasuredOutcomes:
    result = design.blast_result
    if result is None:
        return MeasuredOutcomes()
    frag = result.fragmentation
    vib = result.vibration
    pile = result.muckpile
    cost = result.cost_actual
    return MeasuredOutcomes(
        x20_mm=frag.x20_mm if frag else None,
        x50_mm=frag.x50_mm if frag else None,
        x80_mm=frag.x80_mm if frag else None,
        oversize_pct=frag.oversize_pct if frag else None,
        ppv_mm_s=vib.ppv_mm_s if vib else None,
        throw_m=pile.throw_m if pile else None,
        heave_m=None,
        muckpile_volume_m3=pile.volume_m3 if pile else None,
        cost_rub=cost.total_amount_rub if cost else None,
        cost_per_m3=cost.cost_per_m3 if cost else None,
        recorded_at=result.recorded_at or "",
    )


def _clone_design(design: BlastDesign) -> BlastDesign:
    """Independent copy so prediction engines cannot alias the original."""
    return BlastDesign.from_dict(design.to_dict())


def _collect_predicted(
    design: BlastDesign,
    *,
    lump_size_mm: float,
    max_oversize_pct: float,
    fragmentation_model: str,
    predicted_cost: PlannedCostSnapshot | None,
    warnings: list[str],
) -> PredictedOutcomes:
    predicted = PredictedOutcomes()
    if predicted_cost is not None:
        # Explicit predicted-cost overlay only. Planned estimate stays designed.
        predicted.cost_rub = predicted_cost.total_amount_rub
        predicted.cost_per_m3 = predicted_cost.cost_per_m3

    basis = None
    if design.blast_result is not None:
        basis = getattr(design.blast_result, "basis", None)
    stored_frag = getattr(basis, "predicted_fragmentation", None) if basis else None
    stored_vib = list(getattr(basis, "predicted_vibration", []) or []) if basis else []

    if stored_frag is not None:
        predicted.x20_mm = stored_frag.x20_mm
        predicted.x50_mm = stored_frag.x50_mm
        predicted.x80_mm = stored_frag.x80_mm
        predicted.oversize_pct = stored_frag.oversize_pct
        predicted.fragmentation_model = getattr(stored_frag.provenance, "model", "") or ""
        predicted.fragmentation_model_version = getattr(stored_frag.provenance, "model_version", "") or ""
    elif design.loads:
        try:
            from simulation.fragmentation.engine import predict_design as predict_fragmentation

            payload = predict_fragmentation(
                design,
                model=fragmentation_model or DEFAULT_FRAG_MODEL,
                lump_size_mm=lump_size_mm,
                max_oversize_pct=max_oversize_pct,
                hole_oversize_coeff=(design.charge_rules or {}).get("hole_oversize_coeff"),
            )
            site = (payload.get("site") or {}).get("prediction") or {}
            predicted.x20_mm = _opt_float(site.get("x20_mm"))
            predicted.x50_mm = _opt_float(site.get("x50_mm"))
            predicted.x80_mm = _opt_float(site.get("x80_mm"))
            predicted.oversize_pct = _opt_float(site.get("oversize_pct"))
            predicted.fragmentation_model = str(payload.get("model") or "")
            predicted.fragmentation_model_version = str(payload.get("model_version") or "")
            for warning in payload.get("warnings") or []:
                warnings.append(str(warning))
        except (ValueError, Exception) as exc:
            warnings.append(f"Прогноз дробления недоступен: {exc}")
    else:
        warnings.append("Нет зарядов — прогноз кусковатости пропущен.")

    if stored_vib:
        peak = max(stored_vib, key=lambda item: float(getattr(item, "ppv_mm_s", 0.0) or 0.0))
        predicted.ppv_mm_s = float(peak.ppv_mm_s)
    try:
        from design.vibration import predict_design as predict_vibration

        payload = predict_vibration(design)
        predictions = list(payload.get("predictions") or [])
        if predictions and predicted.ppv_mm_s is None:
            peak_row = max(predictions, key=lambda row: float(row.get("ppv_mm_s") or 0.0))
            predicted.ppv_mm_s = _opt_float(peak_row.get("ppv_mm_s"))
        mic = payload.get("mic") or {}
        predicted.mic_kg = _opt_float(mic.get("mic_kg"))
        model = payload.get("model") or {}
        predicted.vibration_convention = str(model.get("scaled_distance") or "")
        for warning in payload.get("warnings") or []:
            text = str(warning)
            if text not in warnings:
                warnings.append(text)
    except (ValueError, Exception) as exc:
        if predicted.ppv_mm_s is None:
            warnings.append(f"Прогноз сейсмики недоступен: {exc}")

    if design.holes:
        try:
            from simulation.movement.engine import predict_design as predict_movement

            payload = predict_movement(design)
            pile = payload.get("muckpile") or {}
            predicted.throw_m = _opt_float(pile.get("throw_m"))
            predicted.heave_m = _opt_float(pile.get("heave_m"))
            predicted.swell_factor = _opt_float(pile.get("swell_factor"))
            predicted.muckpile_volume_m3 = _opt_float(pile.get("volume_m3"))
            predicted.movement_kind = str(payload.get("kind") or "")
            predicted.movement_label = str(payload.get("label_ru") or "оценка")
            for warning in payload.get("warnings") or []:
                text = str(warning)
                if text not in warnings:
                    warnings.append(text)
        except (ValueError, Exception) as exc:
            warnings.append(f"Оценка развала недоступна: {exc}")

    predicted.role = ROLE_PREDICTED
    return predicted


def _collect_holes(design: BlastDesign) -> list[HolePassportRow]:
    loads = {load.hole_id: load for load in design.loads}
    drilled = {item.design_hole_id: item for item in design.as_drilled_holes}
    charged = {item.design_hole_id: item for item in design.as_charged_holes}
    rows: list[HolePassportRow] = []
    for hole in design.holes:
        load = loads.get(hole.id)
        actual = drilled.get(hole.id)
        charged_hole = charged.get(hole.id)
        rows.append(
            HolePassportRow(
                hole_id=hole.id,
                kind=hole.kind,
                enabled=hole.enabled,
                collar_x_m=hole.collar.x,
                collar_y_m=hole.collar.y,
                collar_z_m=hole.collar.z,
                designed_length_m=hole.length_m,
                designed_angle_deg=hole.angle_deg,
                designed_azimuth_deg=hole.azimuth_deg,
                designed_diameter_mm=hole.diameter_mm,
                designed_charge_kg=load.total_charge_kg if load else None,
                designed_q_kg_m3=load.specific_q_kg_m3 if load else None,
                executed_length_m=actual.actual_depth if actual and actual.actual_depth else None,
                executed_diameter_mm=actual.actual_diameter if actual and actual.actual_diameter else None,
                executed_charge_kg=charged_hole.charge_mass_kg if charged_hole and charged_hole.charge_mass_kg else None,
            )
        )
    return rows


def _row(
    key: str,
    label: str,
    unit: str,
    section: str,
    *,
    designed: float | None = None,
    executed: float | None = None,
    predicted: float | None = None,
    measured: float | None = None,
) -> MetricRow:
    return MetricRow(
        key=key,
        label=label,
        unit=unit,
        section=section,
        designed=designed,
        executed=executed,
        predicted=predicted,
        measured=measured,
    )


def _build_comparison(
    designed: DesignedParameters,
    executed: ExecutedSnapshot,
    predicted: PredictedOutcomes,
    measured: MeasuredOutcomes,
    planned_cost: PlannedCostSnapshot | None,
    design: BlastDesign,
) -> list[MetricRow]:
    designed_pile = None
    if design.blast_result is not None and design.blast_result.basis is not None:
        designed_pile = design.blast_result.basis.designed_muckpile
    planned_total = planned_cost.total_amount_rub if planned_cost else None
    planned_unit = planned_cost.cost_per_m3 if planned_cost else None
    return [
        _row(
            "hole_count",
            "Скважин",
            "шт.",
            "parameters",
            designed=float(designed.hole_count),
            executed=float(executed.as_drilled_count) if executed.as_drilled_count else None,
        ),
        _row(
            "drilling_metres",
            "Погонаж бурения",
            "м",
            "parameters",
            designed=designed.drilling_metres,
            executed=executed.drilling_metres,
        ),
        _row(
            "diameter_mm",
            "Диаметр",
            "мм",
            "parameters",
            designed=designed.diameter_mm,
            executed=executed.mean_diameter_mm,
        ),
        _row(
            "explosive_mass_kg",
            "Масса ВВ",
            "кг",
            "parameters",
            designed=designed.explosive_mass_kg,
            executed=executed.explosive_mass_kg,
        ),
        _row(
            "powder_factor_kg_m3",
            "Удельный расход",
            "кг/м³",
            "parameters",
            designed=designed.powder_factor_kg_m3,
        ),
        _row(
            "x50_mm",
            "X50",
            "мм",
            "fragmentation",
            predicted=predicted.x50_mm,
            measured=measured.x50_mm,
        ),
        _row(
            "x80_mm",
            "X80",
            "мм",
            "fragmentation",
            designed=designed.lump_size_mm,
            predicted=predicted.x80_mm,
            measured=measured.x80_mm,
        ),
        _row(
            "oversize_pct",
            "Негабарит",
            "%",
            "fragmentation",
            designed=designed.max_oversize_pct,
            predicted=predicted.oversize_pct,
            measured=measured.oversize_pct,
        ),
        _row(
            "mic_kg",
            "MIC",
            "кг",
            "vibration",
            predicted=predicted.mic_kg,
        ),
        _row(
            "ppv_mm_s",
            "PPV",
            "мм/с",
            "vibration",
            predicted=predicted.ppv_mm_s,
            measured=measured.ppv_mm_s,
        ),
        _row(
            "throw_m",
            "Отброс",
            "м",
            "movement",
            designed=designed_pile.throw_m if designed_pile else None,
            predicted=predicted.throw_m,
            measured=measured.throw_m,
        ),
        _row(
            "heave_m",
            "Вывал",
            "м",
            "movement",
            predicted=predicted.heave_m,
            measured=measured.heave_m,
        ),
        _row(
            "muckpile_volume_m3",
            "Объём развала",
            "м³",
            "movement",
            designed=designed_pile.volume_m3 if designed_pile else None,
            predicted=predicted.muckpile_volume_m3,
            measured=measured.muckpile_volume_m3,
        ),
        _row(
            "total_amount_rub",
            "Смета, итого",
            "₽",
            "cost",
            designed=planned_total,
            predicted=predicted.cost_rub,
            measured=measured.cost_rub,
        ),
        _row(
            "cost_per_m3",
            "Цена за м³",
            "₽/м³",
            "cost",
            designed=planned_unit,
            predicted=predicted.cost_per_m3,
            measured=measured.cost_per_m3,
        ),
    ]


def build_passport(
    design: BlastDesign,
    *,
    lump_size_mm: float = DEFAULT_LUMP_SIZE_MM,
    max_oversize_pct: float = DEFAULT_MAX_OVERSIZE_PCT,
    fragmentation_model: str = DEFAULT_FRAG_MODEL,
    include_predictions: bool = True,
    planned_cost: Any = None,
    predicted_cost: Any = None,
) -> BlastPassport:
    """Build the official document. Never writes the design and never approves it."""
    if lump_size_mm <= 0:
        raise ValueError("Кондиционный размер куска должен быть больше нуля, мм.")
    if max_oversize_pct < 0:
        raise ValueError("Доля негабарита не может быть отрицательной, %.")
    before = _designed_guard(design)
    warnings: list[str] = []
    designed = _collect_designed(design, lump_size_mm=lump_size_mm, max_oversize_pct=max_oversize_pct)
    executed = _collect_executed(design)
    measured = _collect_measured(design)
    planned = _planned_cost_from_payload(planned_cost)
    if planned is None and design.blast_result is not None:
        basis = getattr(design.blast_result, "basis", None)
        if basis is not None and basis.planned_cost is not None:
            planned = _planned_cost_from_payload(basis.planned_cost.to_dict())
    predicted_cost_snapshot = _planned_cost_from_payload(predicted_cost)
    if include_predictions:
        predicted = _collect_predicted(
            _clone_design(design),
            lump_size_mm=lump_size_mm,
            max_oversize_pct=max_oversize_pct,
            fragmentation_model=fragmentation_model,
            predicted_cost=predicted_cost_snapshot,
            warnings=warnings,
        )
    else:
        predicted = PredictedOutcomes(
            cost_rub=predicted_cost_snapshot.total_amount_rub if predicted_cost_snapshot else None,
            cost_per_m3=predicted_cost_snapshot.cost_per_m3 if predicted_cost_snapshot else None,
        )
        warnings.append("Прогнозные слои не считались — в документе только проект / исполнение / замер.")
    holes = _collect_holes(design)
    comparison = _build_comparison(designed, executed, predicted, measured, planned, design)
    _assert_design_untouched(design, before, "Building the blast passport")
    document = BlastPassport(
        design_id=design.design_id,
        name=design.name,
        generated_at=_utc_now_iso(),
        updated_at=design.updated_at or "",
        approved=False,
        auto_approved=False,
        design_rewritten=False,
        disclaimer=DISCLAIMER,
        designed=designed,
        executed=executed,
        predicted=predicted,
        measured=measured,
        planned_cost=planned,
        comparison=comparison,
        holes=holes,
        warnings=warnings,
    )
    if document.approved or document.auto_approved:
        raise RuntimeError("Blast passport must not auto-approve the design.")
    if document.designed.role != ROLE_DESIGNED:
        raise RuntimeError("Designed parameters must stay role=designed.")
    if document.executed.role != ROLE_EXECUTED:
        raise RuntimeError("Executed snapshot must stay role=executed.")
    if document.predicted.role != ROLE_PREDICTED:
        raise RuntimeError("Predicted outcomes must stay role=predicted.")
    if document.measured.role != ROLE_MEASURED:
        raise RuntimeError("Measured outcomes must stay role=measured.")
    return document
