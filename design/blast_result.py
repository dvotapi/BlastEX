"""Post-blast measurements (phase BDX-010).

Measured outcomes live on ``BlastDesign.blast_result``. Predicted
fragmentation, predicted PPV and designed geometry/cost are never overwritten
by recording or comparing results. This closes the engineering feedback loop
before any ML calibration (BDX-011+).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from design.models import (
    ROLE_DESIGNED,
    ROLE_MEASURED,
    ROLE_PREDICTED,
    BlastDesign,
    DataProvenance,
    VibrationMeasurement,
)
from simulation.fragmentation.models import (
    DesignedFragmentationTarget,
    MeasuredFragmentation,
    PredictedFragmentation,
)

TOE_CONDITIONS = ("clean", "minor", "heavy", "unbroken")
DEFAULT_TOE_CONDITION = "clean"
TOE_CONDITION_LABELS = {
    "clean": "Чистый забой",
    "minor": "Небольшой недобур",
    "heavy": "Сильный недобур",
    "unbroken": "Не взорвано",
}


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _opt_float(data: dict[str, Any], key: str) -> float | None:
    raw = data.get(key)
    if raw is None or raw == "":
        return None
    return float(raw)


def _opt_int(data: dict[str, Any], key: str) -> int | None:
    raw = data.get(key)
    if raw is None or raw == "":
        return None
    return int(raw)


def _normalize_toe(value: Any, default: str = "") -> str:
    text = str(value or default).strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "чистый": "clean",
        "чисто": "clean",
        "небольшой": "minor",
        "слабый": "minor",
        "сильный": "heavy",
        "недобур": "heavy",
        "не_взорвано": "unbroken",
        "целики": "unbroken",
        "intact": "unbroken",
    }
    if text in TOE_CONDITIONS:
        return text
    return aliases.get(text, default if default in TOE_CONDITIONS else "")


def _round_opt(value: float | None, places: int = 3) -> float | None:
    if value is None:
        return None
    return round(float(value), places)


def _delta(left: float | None, right: float | None, places: int = 3) -> float | None:
    if left is None or right is None:
        return None
    return round(float(left) - float(right), places)


def _relative_error_pct(measured: float | None, predicted: float | None, places: int = 2) -> float | None:
    if measured is None or predicted is None or predicted == 0:
        return None
    return round(100.0 * (float(measured) - float(predicted)) / float(predicted), places)


def _designed_guard(design: BlastDesign) -> tuple:
    return (
        [hole.to_dict() for hole in design.holes],
        [load.to_dict() for load in design.loads],
        [item.to_dict() for item in design.network.detonators],
        dict(design.network.electronic_times_ms),
        [item.to_dict() for item in design.network.firing_events],
    )


def _assert_design_untouched(design: BlastDesign, before: tuple, action: str) -> None:
    after = _designed_guard(design)
    if after != before:
        raise RuntimeError(f"{action} не должна менять проектные скважины, заряд или сеть.")


@dataclass
class PredictedVibrationSnapshot:
    """Predicted PPV at a receptor. Frequency is not produced by the site law."""

    receptor_id: str
    ppv_mm_s: float
    frequency_hz: float | None = None
    receptor_name: str = ""
    role: str = ROLE_PREDICTED

    def __post_init__(self) -> None:
        self.role = ROLE_PREDICTED

    def to_dict(self) -> dict[str, Any]:
        return {
            "receptor_id": self.receptor_id,
            "ppv_mm_s": self.ppv_mm_s,
            "frequency_hz": self.frequency_hz,
            "receptor_name": self.receptor_name,
            "role": ROLE_PREDICTED,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> PredictedVibrationSnapshot:
        data = data or {}
        return cls(
            receptor_id=str(data.get("receptor_id", "") or ""),
            ppv_mm_s=float(data.get("ppv_mm_s", 0.0) or 0.0),
            frequency_hz=_opt_float(data, "frequency_hz"),
            receptor_name=str(data.get("receptor_name", "") or ""),
            role=ROLE_PREDICTED,
        )


@dataclass
class MeasuredVibration:
    """Measured PPV and frequency. Separate from predicted site-law output."""

    ppv_mm_s: float | None = None
    frequency_hz: float | None = None
    receptor_id: str = ""
    measurements: list[VibrationMeasurement] = field(default_factory=list)
    source: str = ""
    method: str = ""
    timestamp: str = ""
    notes: str = ""
    role: str = ROLE_MEASURED

    def __post_init__(self) -> None:
        self.role = ROLE_MEASURED
        for item in self.measurements:
            item.role = ROLE_MEASURED

    def to_dict(self) -> dict[str, Any]:
        return {
            "role": ROLE_MEASURED,
            "ppv_mm_s": self.ppv_mm_s,
            "frequency_hz": self.frequency_hz,
            "receptor_id": self.receptor_id,
            "measurements": [item.to_dict() for item in self.measurements],
            "source": self.source,
            "method": self.method,
            "timestamp": self.timestamp,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> MeasuredVibration:
        data = data or {}
        measurements = [VibrationMeasurement.from_dict(item) for item in data.get("measurements", [])]
        ppv = _opt_float(data, "ppv_mm_s")
        frequency = _opt_float(data, "frequency_hz")
        if ppv is None and measurements:
            ppv = max((item.ppv_mm_s for item in measurements), default=None)
        if frequency is None and measurements:
            freqs = [item.frequency_hz for item in measurements if item.frequency_hz is not None]
            frequency = max(freqs) if freqs else None
        return cls(
            ppv_mm_s=ppv,
            frequency_hz=frequency,
            receptor_id=str(data.get("receptor_id", "") or ""),
            measurements=measurements,
            source=str(data.get("source", "") or ""),
            method=str(data.get("method", "") or ""),
            timestamp=str(data.get("timestamp", "") or ""),
            notes=str(data.get("notes", "") or ""),
            role=ROLE_MEASURED,
        )


@dataclass
class MeasuredMuckpile:
    """Measured muckpile dimensions. Designed geometry is a separate object."""

    length_m: float | None = None
    width_m: float | None = None
    height_m: float | None = None
    volume_m3: float | None = None
    throw_m: float | None = None
    notes: str = ""
    role: str = ROLE_MEASURED

    def __post_init__(self) -> None:
        self.role = ROLE_MEASURED

    def to_dict(self) -> dict[str, Any]:
        return {
            "role": ROLE_MEASURED,
            "length_m": self.length_m,
            "width_m": self.width_m,
            "height_m": self.height_m,
            "volume_m3": self.volume_m3,
            "throw_m": self.throw_m,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> MeasuredMuckpile:
        data = data or {}
        return cls(
            length_m=_opt_float(data, "length_m"),
            width_m=_opt_float(data, "width_m"),
            height_m=_opt_float(data, "height_m"),
            volume_m3=_opt_float(data, "volume_m3"),
            throw_m=_opt_float(data, "throw_m"),
            notes=str(data.get("notes", "") or ""),
            role=ROLE_MEASURED,
        )


@dataclass
class DesignedMuckpile:
    """Design intent for the muckpile. Never stored as a measurement."""

    length_m: float | None = None
    width_m: float | None = None
    height_m: float | None = None
    volume_m3: float | None = None
    throw_m: float | None = None
    notes: str = ""
    role: str = ROLE_DESIGNED

    def __post_init__(self) -> None:
        self.role = ROLE_DESIGNED

    def to_dict(self) -> dict[str, Any]:
        return {
            "role": ROLE_DESIGNED,
            "length_m": self.length_m,
            "width_m": self.width_m,
            "height_m": self.height_m,
            "volume_m3": self.volume_m3,
            "throw_m": self.throw_m,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> DesignedMuckpile:
        data = data or {}
        return cls(
            length_m=_opt_float(data, "length_m"),
            width_m=_opt_float(data, "width_m"),
            height_m=_opt_float(data, "height_m"),
            volume_m3=_opt_float(data, "volume_m3"),
            throw_m=_opt_float(data, "throw_m"),
            notes=str(data.get("notes", "") or ""),
            role=ROLE_DESIGNED,
        )


@dataclass
class MeasuredBackbreak:
    max_m: float | None = None
    mean_m: float | None = None
    crest_loss_m: float | None = None
    notes: str = ""
    role: str = ROLE_MEASURED

    def __post_init__(self) -> None:
        self.role = ROLE_MEASURED

    def to_dict(self) -> dict[str, Any]:
        return {
            "role": ROLE_MEASURED,
            "max_m": self.max_m,
            "mean_m": self.mean_m,
            "crest_loss_m": self.crest_loss_m,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> MeasuredBackbreak:
        data = data or {}
        return cls(
            max_m=_opt_float(data, "max_m"),
            mean_m=_opt_float(data, "mean_m"),
            crest_loss_m=_opt_float(data, "crest_loss_m"),
            notes=str(data.get("notes", "") or ""),
            role=ROLE_MEASURED,
        )


@dataclass
class DesignedBackbreak:
    max_m: float | None = None
    mean_m: float | None = None
    crest_loss_m: float | None = None
    notes: str = ""
    role: str = ROLE_DESIGNED

    def __post_init__(self) -> None:
        self.role = ROLE_DESIGNED

    def to_dict(self) -> dict[str, Any]:
        return {
            "role": ROLE_DESIGNED,
            "max_m": self.max_m,
            "mean_m": self.mean_m,
            "crest_loss_m": self.crest_loss_m,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> DesignedBackbreak:
        data = data or {}
        return cls(
            max_m=_opt_float(data, "max_m"),
            mean_m=_opt_float(data, "mean_m"),
            crest_loss_m=_opt_float(data, "crest_loss_m"),
            notes=str(data.get("notes", "") or ""),
            role=ROLE_DESIGNED,
        )


@dataclass
class MeasuredToeCondition:
    condition: str = ""
    leftover_height_m: float | None = None
    notes: str = ""
    role: str = ROLE_MEASURED

    def __post_init__(self) -> None:
        self.role = ROLE_MEASURED
        self.condition = _normalize_toe(self.condition)

    def to_dict(self) -> dict[str, Any]:
        return {
            "role": ROLE_MEASURED,
            "condition": self.condition,
            "leftover_height_m": self.leftover_height_m,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> MeasuredToeCondition:
        data = data or {}
        return cls(
            condition=_normalize_toe(data.get("condition")),
            leftover_height_m=_opt_float(data, "leftover_height_m"),
            notes=str(data.get("notes", "") or ""),
            role=ROLE_MEASURED,
        )


@dataclass
class FlyrockObservation:
    max_range_m: float | None = None
    count: int | None = None
    notes: str = ""
    role: str = ROLE_MEASURED

    def __post_init__(self) -> None:
        self.role = ROLE_MEASURED

    def to_dict(self) -> dict[str, Any]:
        return {
            "role": ROLE_MEASURED,
            "max_range_m": self.max_range_m,
            "count": self.count,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> FlyrockObservation:
        data = data or {}
        return cls(
            max_range_m=_opt_float(data, "max_range_m"),
            count=_opt_int(data, "count"),
            notes=str(data.get("notes", "") or ""),
            role=ROLE_MEASURED,
        )


@dataclass
class SecondaryBreaking:
    volume_m3: float | None = None
    hours: float | None = None
    cost_rub: float | None = None
    method: str = ""
    notes: str = ""
    role: str = ROLE_MEASURED

    def __post_init__(self) -> None:
        self.role = ROLE_MEASURED

    def to_dict(self) -> dict[str, Any]:
        return {
            "role": ROLE_MEASURED,
            "volume_m3": self.volume_m3,
            "hours": self.hours,
            "cost_rub": self.cost_rub,
            "method": self.method,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> SecondaryBreaking:
        data = data or {}
        return cls(
            volume_m3=_opt_float(data, "volume_m3"),
            hours=_opt_float(data, "hours"),
            cost_rub=_opt_float(data, "cost_rub"),
            method=str(data.get("method", "") or ""),
            notes=str(data.get("notes", "") or ""),
            role=ROLE_MEASURED,
        )


@dataclass
class ActualCost:
    """Actual (as-spent) cost. Planned cost is a separate PlannedCost object."""

    total_amount_rub: float | None = None
    cost_per_m3: float | None = None
    variable_total_rub: float | None = None
    labor_total_rub: float | None = None
    fixed_total_rub: float | None = None
    secondary_breaking_rub: float | None = None
    notes: str = ""
    role: str = ROLE_MEASURED

    def __post_init__(self) -> None:
        self.role = ROLE_MEASURED

    def to_dict(self) -> dict[str, Any]:
        return {
            "role": ROLE_MEASURED,
            "total_amount_rub": self.total_amount_rub,
            "cost_per_m3": self.cost_per_m3,
            "variable_total_rub": self.variable_total_rub,
            "labor_total_rub": self.labor_total_rub,
            "fixed_total_rub": self.fixed_total_rub,
            "secondary_breaking_rub": self.secondary_breaking_rub,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> ActualCost:
        data = data or {}
        return cls(
            total_amount_rub=_opt_float(data, "total_amount_rub"),
            cost_per_m3=_opt_float(data, "cost_per_m3"),
            variable_total_rub=_opt_float(data, "variable_total_rub"),
            labor_total_rub=_opt_float(data, "labor_total_rub"),
            fixed_total_rub=_opt_float(data, "fixed_total_rub"),
            secondary_breaking_rub=_opt_float(data, "secondary_breaking_rub"),
            notes=str(data.get("notes", "") or ""),
            role=ROLE_MEASURED,
        )


@dataclass
class PlannedCost:
    """Planned / designed cost. Never mixed into ActualCost."""

    total_amount_rub: float | None = None
    cost_per_m3: float | None = None
    variable_total_rub: float | None = None
    labor_total_rub: float | None = None
    fixed_total_rub: float | None = None
    secondary_breaking_rub: float | None = None
    notes: str = ""
    role: str = ROLE_DESIGNED

    def __post_init__(self) -> None:
        self.role = ROLE_DESIGNED

    def to_dict(self) -> dict[str, Any]:
        return {
            "role": ROLE_DESIGNED,
            "total_amount_rub": self.total_amount_rub,
            "cost_per_m3": self.cost_per_m3,
            "variable_total_rub": self.variable_total_rub,
            "labor_total_rub": self.labor_total_rub,
            "fixed_total_rub": self.fixed_total_rub,
            "secondary_breaking_rub": self.secondary_breaking_rub,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> PlannedCost:
        data = data or {}
        return cls(
            total_amount_rub=_opt_float(data, "total_amount_rub"),
            cost_per_m3=_opt_float(data, "cost_per_m3"),
            variable_total_rub=_opt_float(data, "variable_total_rub"),
            labor_total_rub=_opt_float(data, "labor_total_rub"),
            fixed_total_rub=_opt_float(data, "fixed_total_rub"),
            secondary_breaking_rub=_opt_float(data, "secondary_breaking_rub"),
            notes=str(data.get("notes", "") or ""),
            role=ROLE_DESIGNED,
        )


def _optional_from_dict(cls: Any, data: Any) -> Any:
    if not data:
        return None
    return cls.from_dict(data)


@dataclass
class ComparisonBasis:
    """Predicted / designed / planned values used for deltas.

    Stored next to measurements so a saved passport can replay the table.
    Roles stay predicted or designed — recording measured fields never copies
    into these objects.
    """

    predicted_fragmentation: PredictedFragmentation | None = None
    predicted_vibration: list[PredictedVibrationSnapshot] = field(default_factory=list)
    planned_cost: PlannedCost | None = None
    designed_fragmentation: DesignedFragmentationTarget | None = None
    designed_muckpile: DesignedMuckpile | None = None
    designed_backbreak: DesignedBackbreak | None = None
    designed_toe_condition: str = DEFAULT_TOE_CONDITION

    def to_dict(self) -> dict[str, Any]:
        return {
            "predicted_fragmentation": (
                self.predicted_fragmentation.to_dict() if self.predicted_fragmentation else None
            ),
            "predicted_vibration": [item.to_dict() for item in self.predicted_vibration],
            "planned_cost": self.planned_cost.to_dict() if self.planned_cost else None,
            "designed_fragmentation": (
                self.designed_fragmentation.to_dict() if self.designed_fragmentation else None
            ),
            "designed_muckpile": self.designed_muckpile.to_dict() if self.designed_muckpile else None,
            "designed_backbreak": self.designed_backbreak.to_dict() if self.designed_backbreak else None,
            "designed_toe_condition": _normalize_toe(self.designed_toe_condition, DEFAULT_TOE_CONDITION)
            or DEFAULT_TOE_CONDITION,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> ComparisonBasis:
        data = data or {}
        return cls(
            predicted_fragmentation=_optional_from_dict(PredictedFragmentation, data.get("predicted_fragmentation")),
            predicted_vibration=[
                PredictedVibrationSnapshot.from_dict(item) for item in data.get("predicted_vibration", [])
            ],
            planned_cost=_optional_from_dict(PlannedCost, data.get("planned_cost")),
            designed_fragmentation=_optional_from_dict(
                DesignedFragmentationTarget, data.get("designed_fragmentation")
            ),
            designed_muckpile=_optional_from_dict(DesignedMuckpile, data.get("designed_muckpile")),
            designed_backbreak=_optional_from_dict(DesignedBackbreak, data.get("designed_backbreak")),
            designed_toe_condition=_normalize_toe(data.get("designed_toe_condition"), DEFAULT_TOE_CONDITION)
            or DEFAULT_TOE_CONDITION,
        )

    def has_any(self) -> bool:
        return bool(
            self.predicted_fragmentation
            or self.predicted_vibration
            or self.planned_cost
            or self.designed_fragmentation
            or self.designed_muckpile
            or self.designed_backbreak
            or self.designed_toe_condition
        )


@dataclass
class BlastResult:
    """Post-blast measured outcomes for one design. Predicted records stay aside."""

    design_id: str
    fragmentation: MeasuredFragmentation | None = None
    vibration: MeasuredVibration | None = None
    muckpile: MeasuredMuckpile | None = None
    backbreak: MeasuredBackbreak | None = None
    toe_condition: MeasuredToeCondition | None = None
    flyrock_observations: list[FlyrockObservation] = field(default_factory=list)
    secondary_breaking: SecondaryBreaking | None = None
    cost_actual: ActualCost | None = None
    basis: ComparisonBasis | None = None
    recorded_at: str = ""
    provenance: DataProvenance = field(default_factory=lambda: DataProvenance(role=ROLE_MEASURED))
    role: str = ROLE_MEASURED

    def __post_init__(self) -> None:
        self.role = ROLE_MEASURED
        self.provenance.role = ROLE_MEASURED

    def to_dict(self) -> dict[str, Any]:
        return {
            "design_id": self.design_id,
            "role": ROLE_MEASURED,
            "fragmentation": self.fragmentation.to_dict() if self.fragmentation else None,
            "vibration": self.vibration.to_dict() if self.vibration else None,
            "muckpile": self.muckpile.to_dict() if self.muckpile else None,
            "backbreak": self.backbreak.to_dict() if self.backbreak else None,
            "toe_condition": self.toe_condition.to_dict() if self.toe_condition else None,
            "flyrock_observations": [item.to_dict() for item in self.flyrock_observations],
            "secondary_breaking": self.secondary_breaking.to_dict() if self.secondary_breaking else None,
            "cost_actual": self.cost_actual.to_dict() if self.cost_actual else None,
            "basis": self.basis.to_dict() if self.basis else None,
            "recorded_at": self.recorded_at,
            "provenance": self.provenance.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> BlastResult:
        data = data or {}
        provenance = DataProvenance.from_dict(data.get("provenance"))
        provenance.role = ROLE_MEASURED
        flyrock_raw = data.get("flyrock_observations")
        if flyrock_raw is None and data.get("flyrock"):
            flyrock_raw = data.get("flyrock") if isinstance(data.get("flyrock"), list) else [data.get("flyrock")]
        return cls(
            design_id=str(data.get("design_id", "") or ""),
            fragmentation=_optional_from_dict(MeasuredFragmentation, data.get("fragmentation")),
            vibration=_optional_from_dict(MeasuredVibration, data.get("vibration")),
            muckpile=_optional_from_dict(MeasuredMuckpile, data.get("muckpile")),
            backbreak=_optional_from_dict(MeasuredBackbreak, data.get("backbreak")),
            toe_condition=_optional_from_dict(MeasuredToeCondition, data.get("toe_condition")),
            flyrock_observations=[FlyrockObservation.from_dict(item) for item in (flyrock_raw or [])],
            secondary_breaking=_optional_from_dict(SecondaryBreaking, data.get("secondary_breaking")),
            cost_actual=_optional_from_dict(ActualCost, data.get("cost_actual")),
            basis=_optional_from_dict(ComparisonBasis, data.get("basis")),
            recorded_at=str(data.get("recorded_at", "") or ""),
            provenance=provenance,
            role=ROLE_MEASURED,
        )


def normalize_result(item: BlastResult, *, design_id: str = "") -> BlastResult:
    """Force measured roles. Predicted snapshots stay in ``basis`` only."""
    recorded = BlastResult.from_dict(item.to_dict())
    if design_id:
        recorded.design_id = design_id
    recorded.role = ROLE_MEASURED
    recorded.provenance.role = ROLE_MEASURED
    if recorded.fragmentation is not None:
        recorded.fragmentation.role = ROLE_MEASURED
    if recorded.vibration is not None:
        recorded.vibration.role = ROLE_MEASURED
        for measurement in recorded.vibration.measurements:
            measurement.role = ROLE_MEASURED
    if recorded.muckpile is not None:
        recorded.muckpile.role = ROLE_MEASURED
    if recorded.backbreak is not None:
        recorded.backbreak.role = ROLE_MEASURED
    if recorded.toe_condition is not None:
        recorded.toe_condition.role = ROLE_MEASURED
    if recorded.secondary_breaking is not None:
        recorded.secondary_breaking.role = ROLE_MEASURED
    if recorded.cost_actual is not None:
        recorded.cost_actual.role = ROLE_MEASURED
    for observation in recorded.flyrock_observations:
        observation.role = ROLE_MEASURED
    if recorded.basis is not None:
        if recorded.basis.predicted_fragmentation is not None:
            recorded.basis.predicted_fragmentation.role = ROLE_PREDICTED
        for snapshot in recorded.basis.predicted_vibration:
            snapshot.role = ROLE_PREDICTED
        if recorded.basis.planned_cost is not None:
            recorded.basis.planned_cost.role = ROLE_DESIGNED
        if recorded.basis.designed_fragmentation is not None:
            recorded.basis.designed_fragmentation.role = ROLE_DESIGNED
        if recorded.basis.designed_muckpile is not None:
            recorded.basis.designed_muckpile.role = ROLE_DESIGNED
        if recorded.basis.designed_backbreak is not None:
            recorded.basis.designed_backbreak.role = ROLE_DESIGNED
    return recorded


def merge_basis(existing: ComparisonBasis | None, incoming: ComparisonBasis | None) -> ComparisonBasis | None:
    """Keep prior predicted/designed snapshots unless the caller sends new ones."""
    if incoming is None:
        return existing
    if existing is None:
        return incoming
    return ComparisonBasis(
        predicted_fragmentation=incoming.predicted_fragmentation or existing.predicted_fragmentation,
        predicted_vibration=incoming.predicted_vibration or existing.predicted_vibration,
        planned_cost=incoming.planned_cost or existing.planned_cost,
        designed_fragmentation=incoming.designed_fragmentation or existing.designed_fragmentation,
        designed_muckpile=incoming.designed_muckpile or existing.designed_muckpile,
        designed_backbreak=incoming.designed_backbreak or existing.designed_backbreak,
        designed_toe_condition=incoming.designed_toe_condition or existing.designed_toe_condition,
    )


def record_blast_result(
    design: BlastDesign,
    item: BlastResult,
    *,
    basis: ComparisonBasis | None = None,
) -> BlastResult:
    """Persist measured outcomes. Designed holes/loads/network stay untouched."""
    if not design.design_id and not item.design_id:
        raise ValueError("У результата взрыва нет связи с проектом (design_id).")
    before = _designed_guard(design)
    existing = design.blast_result
    predicted_before = None
    if existing is not None and existing.basis is not None and existing.basis.predicted_fragmentation is not None:
        predicted_before = existing.basis.predicted_fragmentation.to_dict()
    recorded = normalize_result(item, design_id=design.design_id or item.design_id)
    if not recorded.recorded_at:
        recorded.recorded_at = _utc_now_iso()
    if not recorded.provenance.timestamp:
        recorded.provenance.timestamp = recorded.recorded_at
    recorded.basis = merge_basis(existing.basis if existing else None, basis or recorded.basis)
    if recorded.basis and recorded.basis.predicted_fragmentation is not None:
        if recorded.basis.predicted_fragmentation.role != ROLE_PREDICTED:
            raise RuntimeError("Прогноз дробления нельзя сохранить как измерение.")
    if recorded.fragmentation is not None and recorded.fragmentation.role != ROLE_MEASURED:
        raise RuntimeError("Измеренная кусковатость должна иметь role=measured.")
    if predicted_before is not None and recorded.basis and recorded.basis.predicted_fragmentation:
        incoming_pred = None
        if basis and basis.predicted_fragmentation is not None:
            incoming_pred = basis.predicted_fragmentation.to_dict()
        elif item.basis and item.basis.predicted_fragmentation is not None:
            incoming_pred = item.basis.predicted_fragmentation.to_dict()
        if incoming_pred is None and recorded.basis.predicted_fragmentation.to_dict() != predicted_before:
            raise RuntimeError("Запись результатов не должна менять сохранённый прогноз.")
    design.blast_result = recorded
    _assert_design_untouched(design, before, "Запись результатов взрыва")
    return recorded


def _row(
    metric: str,
    label: str,
    unit: str,
    *,
    predicted: float | None = None,
    measured: float | None = None,
    designed: float | None = None,
    actual: float | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = {
        "metric": metric,
        "label": label,
        "unit": unit,
        "predicted": _round_opt(predicted),
        "measured": _round_opt(measured),
        "designed": _round_opt(designed),
        "actual": _round_opt(actual if actual is not None else measured),
        "predicted_minus_measured": _delta(predicted, measured),
        "measured_minus_predicted": _delta(measured, predicted),
        "relative_error_pct": _relative_error_pct(measured, predicted),
        "designed_minus_actual": _delta(designed, actual if actual is not None else measured),
        "actual_minus_designed": _delta(actual if actual is not None else measured, designed),
    }
    if extra:
        payload.update(extra)
    return payload


def compare_fragmentation(
    measured: MeasuredFragmentation | None,
    predicted: PredictedFragmentation | None,
    designed: DesignedFragmentationTarget | None,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not measured and not predicted and not designed:
        return rows
    x20 = measured.x20_mm if measured else None
    x50 = measured.x50_mm if measured else None
    x80 = measured.x80_mm if measured else None
    oversize = measured.oversize_pct if measured else None
    rows.append(
        _row(
            "p20_mm",
            "P20",
            "мм",
            predicted=predicted.x20_mm if predicted else None,
            measured=x20,
        )
    )
    rows.append(
        _row(
            "p50_mm",
            "P50",
            "мм",
            predicted=predicted.x50_mm if predicted else None,
            measured=x50,
        )
    )
    rows.append(
        _row(
            "p80_mm",
            "P80",
            "мм",
            predicted=predicted.x80_mm if predicted else None,
            measured=x80,
            designed=designed.lump_size_mm if designed else None,
            actual=x80,
        )
    )
    rows.append(
        _row(
            "oversize_pct",
            "Негабарит",
            "%",
            predicted=predicted.oversize_pct if predicted else None,
            measured=oversize,
            designed=designed.max_oversize_pct if designed else None,
            actual=oversize,
        )
    )
    return rows


def compare_vibration(
    measured: MeasuredVibration | None,
    predicted: list[PredictedVibrationSnapshot],
    stored: list[VibrationMeasurement] | None = None,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    by_receptor: dict[str, PredictedVibrationSnapshot] = {item.receptor_id: item for item in predicted if item.receptor_id}
    used_receptors: set[str] = set()

    def add_ppv(receptor_id: str, ppv: float | None, frequency: float | None, name: str = "") -> None:
        snapshot = by_receptor.get(receptor_id)
        predicted_ppv = snapshot.ppv_mm_s if snapshot else (predicted[0].ppv_mm_s if len(predicted) == 1 else None)
        predicted_freq = snapshot.frequency_hz if snapshot else None
        suffix = f" ({name})" if name else (f" ({receptor_id})" if receptor_id else "")
        rows.append(
            _row(
                "ppv_mm_s",
                f"PPV{suffix}",
                "мм/с",
                predicted=predicted_ppv,
                measured=ppv,
                extra={"receptor_id": receptor_id},
            )
        )
        rows.append(
            _row(
                "frequency_hz",
                f"Частота{suffix}",
                "Гц",
                predicted=predicted_freq,
                measured=frequency,
                extra={"receptor_id": receptor_id},
            )
        )
        if receptor_id:
            used_receptors.add(receptor_id)

    if measured:
        if measured.measurements:
            for item in measured.measurements:
                add_ppv(item.receptor_id, item.ppv_mm_s, item.frequency_hz, item.event_label)
        else:
            add_ppv(measured.receptor_id, measured.ppv_mm_s, measured.frequency_hz)
    elif stored:
        for item in stored:
            add_ppv(item.receptor_id, item.ppv_mm_s, item.frequency_hz, item.event_label)

    for snapshot in predicted:
        if snapshot.receptor_id and snapshot.receptor_id not in used_receptors:
            add_ppv(snapshot.receptor_id, None, None, snapshot.receptor_name)
    return rows


def compare_muckpile(measured: MeasuredMuckpile | None, designed: DesignedMuckpile | None) -> list[dict[str, Any]]:
    if not measured and not designed:
        return []
    pairs = (
        ("length_m", "Длина развала", "м"),
        ("width_m", "Ширина развала", "м"),
        ("height_m", "Высота развала", "м"),
        ("volume_m3", "Объём развала", "м³"),
        ("throw_m", "Отброс", "м"),
    )
    rows = []
    for key, label, unit in pairs:
        rows.append(
            _row(
                key,
                label,
                unit,
                designed=getattr(designed, key, None) if designed else None,
                actual=getattr(measured, key, None) if measured else None,
                measured=getattr(measured, key, None) if measured else None,
            )
        )
    return rows


def compare_backbreak(measured: MeasuredBackbreak | None, designed: DesignedBackbreak | None) -> list[dict[str, Any]]:
    if not measured and not designed:
        return []
    pairs = (
        ("max_m", "Вывал, макс.", "м"),
        ("mean_m", "Вывал, среднее", "м"),
        ("crest_loss_m", "Потеря бровки", "м"),
    )
    return [
        _row(
            key,
            label,
            unit,
            designed=getattr(designed, key, None) if designed else None,
            actual=getattr(measured, key, None) if measured else None,
            measured=getattr(measured, key, None) if measured else None,
        )
        for key, label, unit in pairs
    ]


def compare_toe(measured: MeasuredToeCondition | None, designed_condition: str) -> list[dict[str, Any]]:
    if not measured and not designed_condition:
        return []
    designed = _normalize_toe(designed_condition, DEFAULT_TOE_CONDITION) or DEFAULT_TOE_CONDITION
    actual = measured.condition if measured else ""
    leftover = measured.leftover_height_m if measured else None
    mismatch = bool(actual) and actual != designed
    return [
        {
            "metric": "toe_condition",
            "label": "Состояние забоя",
            "unit": "",
            "predicted": None,
            "measured": actual,
            "designed": designed,
            "actual": actual,
            "designed_label": TOE_CONDITION_LABELS.get(designed, designed),
            "actual_label": TOE_CONDITION_LABELS.get(actual, actual),
            "mismatch": mismatch,
            "predicted_minus_measured": None,
            "measured_minus_predicted": None,
            "relative_error_pct": None,
            "designed_minus_actual": None,
            "actual_minus_designed": None,
        },
        _row(
            "leftover_height_m",
            "Остаток на почве",
            "м",
            designed=0.0 if designed == "clean" else None,
            actual=leftover,
            measured=leftover,
        ),
    ]


def compare_cost(actual: ActualCost | None, planned: PlannedCost | None) -> list[dict[str, Any]]:
    if not actual and not planned:
        return []
    pairs = (
        ("total_amount_rub", "Итого", "₽"),
        ("cost_per_m3", "Цена за м³", "₽/м³"),
        ("variable_total_rub", "Переменные", "₽"),
        ("labor_total_rub", "ФОТ", "₽"),
        ("fixed_total_rub", "Постоянные", "₽"),
        ("secondary_breaking_rub", "Вторичное дробление", "₽"),
    )
    return [
        _row(
            key,
            label,
            unit,
            designed=getattr(planned, key, None) if planned else None,
            actual=getattr(actual, key, None) if actual else None,
            measured=getattr(actual, key, None) if actual else None,
        )
        for key, label, unit in pairs
    ]


def compare_result(design: BlastDesign, *, basis: ComparisonBasis | None = None) -> dict[str, Any]:
    """Predicted vs measured, designed vs actual, planned vs actual cost."""
    before = _designed_guard(design)
    result = design.blast_result
    warnings: list[str] = []
    if result is None:
        warnings.append("Результатов взрыва ещё нет — сравнивать нечего.")
        _assert_design_untouched(design, before, "Сравнение результатов взрыва")
        return {
            "role": ROLE_MEASURED,
            "comparison": "post_blast",
            "has_result": False,
            "predicted_vs_measured": [],
            "designed_vs_actual": [],
            "planned_vs_actual_cost": [],
            "warnings": warnings,
            "result": None,
        }

    merged = merge_basis(result.basis, basis) or ComparisonBasis()
    predicted_frag = merged.predicted_fragmentation
    designed_frag = merged.designed_fragmentation
    predicted_vs_measured = compare_fragmentation(result.fragmentation, predicted_frag, designed_frag)
    predicted_vs_measured.extend(
        compare_vibration(result.vibration, merged.predicted_vibration, design.vibration_measurements)
    )

    designed_vs_actual = [
        row
        for row in compare_fragmentation(result.fragmentation, None, designed_frag)
        if row["designed"] is not None
    ]
    designed_vs_actual.extend(compare_muckpile(result.muckpile, merged.designed_muckpile))
    designed_vs_actual.extend(compare_backbreak(result.backbreak, merged.designed_backbreak))
    designed_vs_actual.extend(compare_toe(result.toe_condition, merged.designed_toe_condition))

    cost_rows = compare_cost(result.cost_actual, merged.planned_cost)
    if result.cost_actual is None and merged.planned_cost is not None:
        warnings.append("Есть плановая смета, но фактическая стоимость не записана.")
    if result.fragmentation is None and predicted_frag is not None:
        warnings.append("Есть прогноз дробления, но измеренная кусковатость не записана.")
    if result.vibration is None and merged.predicted_vibration:
        warnings.append("Есть прогноз PPV, но измеренная сейсмика в результате не записана.")

    _assert_design_untouched(design, before, "Сравнение результатов взрыва")
    if predicted_frag is not None and result.fragmentation is not None:
        if predicted_frag.role != ROLE_PREDICTED or result.fragmentation.role != ROLE_MEASURED:
            raise RuntimeError("Прогноз и измерение дробления должны оставаться разными ролями.")

    return {
        "role": ROLE_MEASURED,
        "comparison": "post_blast",
        "has_result": True,
        "predicted_vs_measured": predicted_vs_measured,
        "designed_vs_actual": designed_vs_actual,
        "planned_vs_actual_cost": cost_rows,
        "warnings": warnings,
        "result": result.to_dict(),
    }
