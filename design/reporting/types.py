"""Official blast passport types (BDX-024).

Roles stay distinct: DESIGNED / EXECUTED / PREDICTED / MEASURED.
The document never auto-approves a design. Predicted values are labelled
as predictions, not as design intent and not as measurements.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from design.models import (
    DATA_ROLES,
    ROLE_DESIGNED,
    ROLE_EXECUTED,
    ROLE_MEASURED,
    ROLE_PREDICTED,
)

PASSPORT_KIND = "blast_passport"
PASSPORT_VERSION = "1"

ROLE_LABELS_RU = {
    ROLE_DESIGNED: "проект",
    ROLE_EXECUTED: "исполнение",
    ROLE_PREDICTED: "прогноз",
    ROLE_MEASURED: "замер",
}
ROLE_LABELS_EN = {
    ROLE_DESIGNED: "designed",
    ROLE_EXECUTED: "executed",
    ROLE_PREDICTED: "predicted",
    ROLE_MEASURED: "measured",
}

DISCLAIMER = (
    "Официальный паспорт БВР для инженера. Колонки DESIGNED / EXECUTED / "
    "PREDICTED / MEASURED не смешиваются. Прогноз (predicted) — инженерная "
    "оценка, не замер и не утверждение проекта. Документ не утверждает "
    "паспорт автоматически."
)

AUTO_APPROVED = False


def _opt_float(data: dict[str, Any], key: str) -> float | None:
    raw = data.get(key)
    if raw is None or raw == "":
        return None
    return float(raw)


def _round_opt(value: float | None, places: int = 3) -> float | None:
    if value is None:
        return None
    return round(float(value), places)


@dataclass
class MetricRow:
    """One engineer-facing metric with four independent role columns."""

    key: str
    label: str
    unit: str
    section: str
    designed: float | None = None
    executed: float | None = None
    predicted: float | None = None
    measured: float | None = None
    designed_text: str = ""
    executed_text: str = ""
    predicted_text: str = ""
    measured_text: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "label": self.label,
            "unit": self.unit,
            "section": self.section,
            "designed": _round_opt(self.designed),
            "executed": _round_opt(self.executed),
            "predicted": _round_opt(self.predicted),
            "measured": _round_opt(self.measured),
            "designed_text": self.designed_text,
            "executed_text": self.executed_text,
            "predicted_text": self.predicted_text,
            "measured_text": self.measured_text,
            "roles": {
                "designed": ROLE_DESIGNED,
                "executed": ROLE_EXECUTED,
                "predicted": ROLE_PREDICTED,
                "measured": ROLE_MEASURED,
            },
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> MetricRow:
        data = data or {}
        return cls(
            key=str(data.get("key", "") or ""),
            label=str(data.get("label", "") or ""),
            unit=str(data.get("unit", "") or ""),
            section=str(data.get("section", "") or ""),
            designed=_opt_float(data, "designed"),
            executed=_opt_float(data, "executed"),
            predicted=_opt_float(data, "predicted"),
            measured=_opt_float(data, "measured"),
            designed_text=str(data.get("designed_text", "") or ""),
            executed_text=str(data.get("executed_text", "") or ""),
            predicted_text=str(data.get("predicted_text", "") or ""),
            measured_text=str(data.get("measured_text", "") or ""),
        )


@dataclass
class DesignedParameters:
    """Project geometry and charge. Role is always designed."""

    name: str = ""
    rock_name: str = ""
    explosive_key: str = ""
    initiation_system: str = ""
    spacing_a_m: float | None = None
    burden_b_m: float | None = None
    diameter_mm: float | None = None
    subdrill_m: float | None = None
    hole_count: int = 0
    production_hole_count: int = 0
    contour_hole_count: int = 0
    charged_hole_count: int = 0
    drilling_metres: float = 0.0
    block_volume_m3: float = 0.0
    explosive_mass_kg: float = 0.0
    powder_factor_kg_m3: float = 0.0
    lump_size_mm: float | None = None
    max_oversize_pct: float | None = None
    role: str = ROLE_DESIGNED

    def __post_init__(self) -> None:
        self.role = ROLE_DESIGNED

    def to_dict(self) -> dict[str, Any]:
        return {
            "role": ROLE_DESIGNED,
            "name": self.name,
            "rock_name": self.rock_name,
            "explosive_key": self.explosive_key,
            "initiation_system": self.initiation_system,
            "spacing_a_m": _round_opt(self.spacing_a_m),
            "burden_b_m": _round_opt(self.burden_b_m),
            "diameter_mm": _round_opt(self.diameter_mm),
            "subdrill_m": _round_opt(self.subdrill_m),
            "hole_count": self.hole_count,
            "production_hole_count": self.production_hole_count,
            "contour_hole_count": self.contour_hole_count,
            "charged_hole_count": self.charged_hole_count,
            "drilling_metres": _round_opt(self.drilling_metres, 2),
            "block_volume_m3": _round_opt(self.block_volume_m3, 2),
            "explosive_mass_kg": _round_opt(self.explosive_mass_kg, 2),
            "powder_factor_kg_m3": _round_opt(self.powder_factor_kg_m3, 4),
            "lump_size_mm": _round_opt(self.lump_size_mm),
            "max_oversize_pct": _round_opt(self.max_oversize_pct),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> DesignedParameters:
        data = data or {}
        return cls(
            name=str(data.get("name", "") or ""),
            rock_name=str(data.get("rock_name", "") or ""),
            explosive_key=str(data.get("explosive_key", "") or ""),
            initiation_system=str(data.get("initiation_system", "") or ""),
            spacing_a_m=_opt_float(data, "spacing_a_m"),
            burden_b_m=_opt_float(data, "burden_b_m"),
            diameter_mm=_opt_float(data, "diameter_mm"),
            subdrill_m=_opt_float(data, "subdrill_m"),
            hole_count=int(data.get("hole_count") or 0),
            production_hole_count=int(data.get("production_hole_count") or 0),
            contour_hole_count=int(data.get("contour_hole_count") or 0),
            charged_hole_count=int(data.get("charged_hole_count") or 0),
            drilling_metres=float(data.get("drilling_metres") or 0.0),
            block_volume_m3=float(data.get("block_volume_m3") or 0.0),
            explosive_mass_kg=float(data.get("explosive_mass_kg") or 0.0),
            powder_factor_kg_m3=float(data.get("powder_factor_kg_m3") or 0.0),
            lump_size_mm=_opt_float(data, "lump_size_mm"),
            max_oversize_pct=_opt_float(data, "max_oversize_pct"),
            role=ROLE_DESIGNED,
        )


@dataclass
class ExecutedSnapshot:
    """As-drilled / as-charged / as-fired totals. Role is always executed."""

    as_drilled_count: int = 0
    as_charged_count: int = 0
    as_fired_count: int = 0
    drilling_metres: float | None = None
    explosive_mass_kg: float | None = None
    mean_diameter_mm: float | None = None
    role: str = ROLE_EXECUTED

    def __post_init__(self) -> None:
        self.role = ROLE_EXECUTED

    def to_dict(self) -> dict[str, Any]:
        return {
            "role": ROLE_EXECUTED,
            "as_drilled_count": self.as_drilled_count,
            "as_charged_count": self.as_charged_count,
            "as_fired_count": self.as_fired_count,
            "drilling_metres": _round_opt(self.drilling_metres, 2),
            "explosive_mass_kg": _round_opt(self.explosive_mass_kg, 2),
            "mean_diameter_mm": _round_opt(self.mean_diameter_mm),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> ExecutedSnapshot:
        data = data or {}
        return cls(
            as_drilled_count=int(data.get("as_drilled_count") or 0),
            as_charged_count=int(data.get("as_charged_count") or 0),
            as_fired_count=int(data.get("as_fired_count") or 0),
            drilling_metres=_opt_float(data, "drilling_metres"),
            explosive_mass_kg=_opt_float(data, "explosive_mass_kg"),
            mean_diameter_mm=_opt_float(data, "mean_diameter_mm"),
            role=ROLE_EXECUTED,
        )


@dataclass
class PredictedOutcomes:
    """Engineering overlays. Role is always predicted — never a measurement."""

    x20_mm: float | None = None
    x50_mm: float | None = None
    x80_mm: float | None = None
    oversize_pct: float | None = None
    fragmentation_model: str = ""
    fragmentation_model_version: str = ""
    mic_kg: float | None = None
    ppv_mm_s: float | None = None
    vibration_convention: str = ""
    throw_m: float | None = None
    heave_m: float | None = None
    swell_factor: float | None = None
    muckpile_volume_m3: float | None = None
    movement_kind: str = ""
    movement_label: str = ""
    cost_rub: float | None = None
    cost_per_m3: float | None = None
    role: str = ROLE_PREDICTED

    def __post_init__(self) -> None:
        self.role = ROLE_PREDICTED

    def to_dict(self) -> dict[str, Any]:
        return {
            "role": ROLE_PREDICTED,
            "x20_mm": _round_opt(self.x20_mm),
            "x50_mm": _round_opt(self.x50_mm),
            "x80_mm": _round_opt(self.x80_mm),
            "oversize_pct": _round_opt(self.oversize_pct),
            "fragmentation_model": self.fragmentation_model,
            "fragmentation_model_version": self.fragmentation_model_version,
            "mic_kg": _round_opt(self.mic_kg, 2),
            "ppv_mm_s": _round_opt(self.ppv_mm_s, 4),
            "vibration_convention": self.vibration_convention,
            "throw_m": _round_opt(self.throw_m),
            "heave_m": _round_opt(self.heave_m),
            "swell_factor": _round_opt(self.swell_factor),
            "muckpile_volume_m3": _round_opt(self.muckpile_volume_m3, 2),
            "movement_kind": self.movement_kind,
            "movement_label": self.movement_label,
            "cost_rub": _round_opt(self.cost_rub, 2),
            "cost_per_m3": _round_opt(self.cost_per_m3, 2),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> PredictedOutcomes:
        data = data or {}
        return cls(
            x20_mm=_opt_float(data, "x20_mm"),
            x50_mm=_opt_float(data, "x50_mm"),
            x80_mm=_opt_float(data, "x80_mm"),
            oversize_pct=_opt_float(data, "oversize_pct"),
            fragmentation_model=str(data.get("fragmentation_model", "") or ""),
            fragmentation_model_version=str(data.get("fragmentation_model_version", "") or ""),
            mic_kg=_opt_float(data, "mic_kg"),
            ppv_mm_s=_opt_float(data, "ppv_mm_s"),
            vibration_convention=str(data.get("vibration_convention", "") or ""),
            throw_m=_opt_float(data, "throw_m"),
            heave_m=_opt_float(data, "heave_m"),
            swell_factor=_opt_float(data, "swell_factor"),
            muckpile_volume_m3=_opt_float(data, "muckpile_volume_m3"),
            movement_kind=str(data.get("movement_kind", "") or ""),
            movement_label=str(data.get("movement_label", "") or ""),
            cost_rub=_opt_float(data, "cost_rub"),
            cost_per_m3=_opt_float(data, "cost_per_m3"),
            role=ROLE_PREDICTED,
        )


@dataclass
class MeasuredOutcomes:
    """Post-blast measurements. Role is always measured."""

    x20_mm: float | None = None
    x50_mm: float | None = None
    x80_mm: float | None = None
    oversize_pct: float | None = None
    ppv_mm_s: float | None = None
    throw_m: float | None = None
    heave_m: float | None = None
    muckpile_volume_m3: float | None = None
    cost_rub: float | None = None
    cost_per_m3: float | None = None
    recorded_at: str = ""
    role: str = ROLE_MEASURED

    def __post_init__(self) -> None:
        self.role = ROLE_MEASURED

    def to_dict(self) -> dict[str, Any]:
        return {
            "role": ROLE_MEASURED,
            "x20_mm": _round_opt(self.x20_mm),
            "x50_mm": _round_opt(self.x50_mm),
            "x80_mm": _round_opt(self.x80_mm),
            "oversize_pct": _round_opt(self.oversize_pct),
            "ppv_mm_s": _round_opt(self.ppv_mm_s, 4),
            "throw_m": _round_opt(self.throw_m),
            "heave_m": _round_opt(self.heave_m),
            "muckpile_volume_m3": _round_opt(self.muckpile_volume_m3, 2),
            "cost_rub": _round_opt(self.cost_rub, 2),
            "cost_per_m3": _round_opt(self.cost_per_m3, 2),
            "recorded_at": self.recorded_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> MeasuredOutcomes:
        data = data or {}
        return cls(
            x20_mm=_opt_float(data, "x20_mm"),
            x50_mm=_opt_float(data, "x50_mm"),
            x80_mm=_opt_float(data, "x80_mm"),
            oversize_pct=_opt_float(data, "oversize_pct"),
            ppv_mm_s=_opt_float(data, "ppv_mm_s"),
            throw_m=_opt_float(data, "throw_m"),
            heave_m=_opt_float(data, "heave_m"),
            muckpile_volume_m3=_opt_float(data, "muckpile_volume_m3"),
            cost_rub=_opt_float(data, "cost_rub"),
            cost_per_m3=_opt_float(data, "cost_per_m3"),
            recorded_at=str(data.get("recorded_at", "") or ""),
            role=ROLE_MEASURED,
        )


@dataclass
class PlannedCostSnapshot:
    """Planned / designed estimate. Not a prediction and not an actual."""

    total_amount_rub: float | None = None
    cost_per_m3: float | None = None
    variable_total_rub: float | None = None
    labor_total_rub: float | None = None
    fixed_total_rub: float | None = None
    notes: str = ""
    role: str = ROLE_DESIGNED

    def __post_init__(self) -> None:
        self.role = ROLE_DESIGNED

    def to_dict(self) -> dict[str, Any]:
        return {
            "role": ROLE_DESIGNED,
            "total_amount_rub": _round_opt(self.total_amount_rub, 2),
            "cost_per_m3": _round_opt(self.cost_per_m3, 2),
            "variable_total_rub": _round_opt(self.variable_total_rub, 2),
            "labor_total_rub": _round_opt(self.labor_total_rub, 2),
            "fixed_total_rub": _round_opt(self.fixed_total_rub, 2),
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> PlannedCostSnapshot:
        data = data or {}
        return cls(
            total_amount_rub=_opt_float(data, "total_amount_rub"),
            cost_per_m3=_opt_float(data, "cost_per_m3"),
            variable_total_rub=_opt_float(data, "variable_total_rub"),
            labor_total_rub=_opt_float(data, "labor_total_rub"),
            fixed_total_rub=_opt_float(data, "fixed_total_rub"),
            notes=str(data.get("notes", "") or ""),
            role=ROLE_DESIGNED,
        )


@dataclass
class HolePassportRow:
    """Per-hole designed values, plus executed facts when they exist."""

    hole_id: str
    kind: str
    enabled: bool
    collar_x_m: float
    collar_y_m: float
    collar_z_m: float
    designed_length_m: float
    designed_angle_deg: float
    designed_azimuth_deg: float
    designed_diameter_mm: float
    designed_charge_kg: float | None = None
    designed_q_kg_m3: float | None = None
    executed_length_m: float | None = None
    executed_diameter_mm: float | None = None
    executed_charge_kg: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "hole_id": self.hole_id,
            "kind": self.kind,
            "enabled": self.enabled,
            "collar_x_m": round(self.collar_x_m, 3),
            "collar_y_m": round(self.collar_y_m, 3),
            "collar_z_m": round(self.collar_z_m, 3),
            "designed": {
                "role": ROLE_DESIGNED,
                "length_m": round(self.designed_length_m, 2),
                "angle_deg": round(self.designed_angle_deg, 1),
                "azimuth_deg": round(self.designed_azimuth_deg, 1),
                "diameter_mm": round(self.designed_diameter_mm, 1),
                "charge_mass_kg": _round_opt(self.designed_charge_kg, 1),
                "specific_q_kg_m3": _round_opt(self.designed_q_kg_m3, 3),
            },
            "executed": {
                "role": ROLE_EXECUTED,
                "length_m": _round_opt(self.executed_length_m, 2),
                "diameter_mm": _round_opt(self.executed_diameter_mm, 1),
                "charge_mass_kg": _round_opt(self.executed_charge_kg, 1),
            },
        }


@dataclass
class BlastPassport:
    """Official engineer-facing blast passport. Never auto-approved."""

    design_id: str
    name: str
    generated_at: str = ""
    updated_at: str = ""
    kind: str = PASSPORT_KIND
    version: str = PASSPORT_VERSION
    approved: bool = False
    auto_approved: bool = False
    design_rewritten: bool = False
    disclaimer: str = DISCLAIMER
    designed: DesignedParameters = field(default_factory=DesignedParameters)
    executed: ExecutedSnapshot = field(default_factory=ExecutedSnapshot)
    predicted: PredictedOutcomes = field(default_factory=PredictedOutcomes)
    measured: MeasuredOutcomes = field(default_factory=MeasuredOutcomes)
    planned_cost: PlannedCostSnapshot | None = None
    comparison: list[MetricRow] = field(default_factory=list)
    holes: list[HolePassportRow] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    roles: tuple[str, ...] = DATA_ROLES

    def __post_init__(self) -> None:
        self.approved = False
        self.auto_approved = False
        self.design_rewritten = False
        self.kind = PASSPORT_KIND
        self.roles = DATA_ROLES
        self.designed.role = ROLE_DESIGNED
        self.executed.role = ROLE_EXECUTED
        self.predicted.role = ROLE_PREDICTED
        self.measured.role = ROLE_MEASURED
        if self.planned_cost is not None:
            self.planned_cost.role = ROLE_DESIGNED

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": PASSPORT_KIND,
            "version": self.version,
            "design_id": self.design_id,
            "name": self.name,
            "generated_at": self.generated_at,
            "updated_at": self.updated_at,
            "approved": False,
            "auto_approved": False,
            "design_rewritten": False,
            "disclaimer": self.disclaimer,
            "roles": list(DATA_ROLES),
            "role_labels_ru": dict(ROLE_LABELS_RU),
            "role_labels_en": dict(ROLE_LABELS_EN),
            "designed": self.designed.to_dict(),
            "executed": self.executed.to_dict(),
            "predicted": self.predicted.to_dict(),
            "measured": self.measured.to_dict(),
            "planned_cost": self.planned_cost.to_dict() if self.planned_cost else None,
            "comparison": [row.to_dict() for row in self.comparison],
            "holes": [row.to_dict() for row in self.holes],
            "warnings": list(self.warnings),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> BlastPassport:
        data = data or {}
        planned = data.get("planned_cost")
        return cls(
            design_id=str(data.get("design_id", "") or ""),
            name=str(data.get("name", "") or ""),
            generated_at=str(data.get("generated_at", "") or ""),
            updated_at=str(data.get("updated_at", "") or ""),
            version=str(data.get("version", PASSPORT_VERSION) or PASSPORT_VERSION),
            approved=False,
            auto_approved=False,
            design_rewritten=False,
            disclaimer=str(data.get("disclaimer", DISCLAIMER) or DISCLAIMER),
            designed=DesignedParameters.from_dict(data.get("designed")),
            executed=ExecutedSnapshot.from_dict(data.get("executed")),
            predicted=PredictedOutcomes.from_dict(data.get("predicted")),
            measured=MeasuredOutcomes.from_dict(data.get("measured")),
            planned_cost=PlannedCostSnapshot.from_dict(planned) if planned else None,
            comparison=[MetricRow.from_dict(item) for item in data.get("comparison", [])],
            warnings=[str(item) for item in data.get("warnings", [])],
        )


def roles_payload() -> dict[str, Any]:
    """Conventions for the official document. No lifecycle, no auto-approve."""
    return {
        "roles": list(DATA_ROLES),
        "labels_ru": dict(ROLE_LABELS_RU),
        "labels_en": dict(ROLE_LABELS_EN),
        "kind": PASSPORT_KIND,
        "approved": False,
        "auto_approved": False,
        "evaluates_code": False,
        "silent_unit_conversion": False,
        "disclaimer": DISCLAIMER,
    }
