"""Predicted muckpile movement / heave. Explicitly an estimate, not physics.

All objects produced here carry ``role=predicted``. Designed pattern geometry
and measured post-blast muckpile stay on other types (BDX-010).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from design.models import ROLE_DESIGNED, ROLE_MEASURED, ROLE_PREDICTED

MODEL_ID = "kinematic_heave"
MODEL_VERSION = "1.0.0"
KIND_ESTIMATE = "empirical_kinematic_estimate"
LABEL_RU = "оценка"
LABEL_EN = "estimate"
DISCLAIMER = (
    "оценка / estimate — эмпирическая кинематическая модель развала и вывала. "
    "Это не физическая симуляция."
)
IS_PHYSICS_SIMULATION = False

MOVEMENT_ROLES = (ROLE_DESIGNED, ROLE_PREDICTED, ROLE_MEASURED)


def _opt_float(data: dict[str, Any], key: str) -> float | None:
    raw = data.get(key)
    if raw is None or raw == "":
        return None
    return float(raw)


def estimate_kind_payload() -> dict[str, Any]:
    """UI/API must label the output as an estimate, never as physics."""
    return {
        "kind": KIND_ESTIMATE,
        "label_ru": LABEL_RU,
        "label_en": LABEL_EN,
        "disclaimer": DISCLAIMER,
        "is_physics_simulation": IS_PHYSICS_SIMULATION,
    }


@dataclass
class ModelProvenance:
    model: str = MODEL_ID
    model_version: str = MODEL_VERSION
    inputs: dict[str, Any] = field(default_factory=dict)
    parameters: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "model": self.model,
            "model_version": self.model_version,
            "inputs": dict(self.inputs),
            "parameters": dict(self.parameters),
        }
        payload.update(estimate_kind_payload())
        return payload

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> ModelProvenance:
        data = data or {}
        return cls(
            model=str(data.get("model", MODEL_ID) or MODEL_ID),
            model_version=str(data.get("model_version", MODEL_VERSION) or MODEL_VERSION),
            inputs=dict(data.get("inputs") or {}),
            parameters=dict(data.get("parameters") or {}),
        )


@dataclass
class MovementInputs:
    """Designed inputs used by the estimate. Lengths in metres, mass in kg."""

    burden_m: float
    spacing_m: float
    bench_height_m: float
    diameter_mm: float
    diameter_m: float
    charge_mass_kg: float
    powder_factor_kg_m3: float
    stemming_m: float
    influence_volume_m3: float
    face_distance_m: float
    fire_time_ms: float | None = None
    row: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "burden_m": self.burden_m,
            "spacing_m": self.spacing_m,
            "bench_height_m": self.bench_height_m,
            "diameter_mm": self.diameter_mm,
            "diameter_m": self.diameter_m,
            "charge_mass_kg": self.charge_mass_kg,
            "powder_factor_kg_m3": self.powder_factor_kg_m3,
            "stemming_m": self.stemming_m,
            "influence_volume_m3": self.influence_volume_m3,
            "face_distance_m": self.face_distance_m,
            "fire_time_ms": self.fire_time_ms,
            "row": self.row,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> MovementInputs:
        data = data or {}
        return cls(
            burden_m=float(data.get("burden_m", 0.0) or 0.0),
            spacing_m=float(data.get("spacing_m", 0.0) or 0.0),
            bench_height_m=float(data.get("bench_height_m", 0.0) or 0.0),
            diameter_mm=float(data.get("diameter_mm", 0.0) or 0.0),
            diameter_m=float(data.get("diameter_m", 0.0) or 0.0),
            charge_mass_kg=float(data.get("charge_mass_kg", 0.0) or 0.0),
            powder_factor_kg_m3=float(data.get("powder_factor_kg_m3", 0.0) or 0.0),
            stemming_m=float(data.get("stemming_m", 0.0) or 0.0),
            influence_volume_m3=float(data.get("influence_volume_m3", 0.0) or 0.0),
            face_distance_m=float(data.get("face_distance_m", 0.0) or 0.0),
            fire_time_ms=_opt_float(data, "fire_time_ms"),
            row=int(data.get("row", 0) or 0),
        )


@dataclass
class PredictedHoleMovement:
    """Per-hole throw / heave vector. Role is always predicted."""

    hole_id: str
    x: float
    y: float
    dx_m: float
    dy_m: float
    dz_m: float
    throw_m: float
    heave_m: float
    direction_deg: float
    swell_factor: float
    predicted_x: float
    predicted_y: float
    predicted_z: float
    inputs: MovementInputs
    provenance: ModelProvenance = field(default_factory=ModelProvenance)
    role: str = ROLE_PREDICTED

    def __post_init__(self) -> None:
        self.role = ROLE_PREDICTED

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "hole_id": self.hole_id,
            "x": self.x,
            "y": self.y,
            "dx_m": self.dx_m,
            "dy_m": self.dy_m,
            "dz_m": self.dz_m,
            "throw_m": self.throw_m,
            "heave_m": self.heave_m,
            "direction_deg": self.direction_deg,
            "swell_factor": self.swell_factor,
            "predicted_x": self.predicted_x,
            "predicted_y": self.predicted_y,
            "predicted_z": self.predicted_z,
            "inputs": self.inputs.to_dict(),
            "provenance": self.provenance.to_dict(),
            "role": ROLE_PREDICTED,
        }
        payload.update(estimate_kind_payload())
        return payload

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> PredictedHoleMovement:
        data = data or {}
        return cls(
            hole_id=str(data.get("hole_id", "") or ""),
            x=float(data.get("x", 0.0) or 0.0),
            y=float(data.get("y", 0.0) or 0.0),
            dx_m=float(data.get("dx_m", 0.0) or 0.0),
            dy_m=float(data.get("dy_m", 0.0) or 0.0),
            dz_m=float(data.get("dz_m", 0.0) or 0.0),
            throw_m=float(data.get("throw_m", 0.0) or 0.0),
            heave_m=float(data.get("heave_m", 0.0) or 0.0),
            direction_deg=float(data.get("direction_deg", 0.0) or 0.0),
            swell_factor=float(data.get("swell_factor", 1.0) or 1.0),
            predicted_x=float(data.get("predicted_x", 0.0) or 0.0),
            predicted_y=float(data.get("predicted_y", 0.0) or 0.0),
            predicted_z=float(data.get("predicted_z", 0.0) or 0.0),
            inputs=MovementInputs.from_dict(data.get("inputs")),
            provenance=ModelProvenance.from_dict(data.get("provenance")),
            role=ROLE_PREDICTED,
        )


@dataclass
class PredictedMuckpile:
    """Estimated muckpile envelope. Never stored as designed or measured."""

    length_m: float
    width_m: float
    height_m: float
    volume_m3: float
    throw_m: float
    heave_m: float
    swell_factor: float
    in_situ_volume_m3: float
    centroid_x: float
    centroid_y: float
    envelope: list[dict[str, float]] = field(default_factory=list)
    notes: str = DISCLAIMER
    provenance: ModelProvenance = field(default_factory=ModelProvenance)
    role: str = ROLE_PREDICTED

    def __post_init__(self) -> None:
        self.role = ROLE_PREDICTED
        if not self.notes:
            self.notes = DISCLAIMER

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "role": ROLE_PREDICTED,
            "length_m": self.length_m,
            "width_m": self.width_m,
            "height_m": self.height_m,
            "volume_m3": self.volume_m3,
            "throw_m": self.throw_m,
            "heave_m": self.heave_m,
            "swell_factor": self.swell_factor,
            "in_situ_volume_m3": self.in_situ_volume_m3,
            "centroid_x": self.centroid_x,
            "centroid_y": self.centroid_y,
            "envelope": [dict(point) for point in self.envelope],
            "notes": self.notes or DISCLAIMER,
            "provenance": self.provenance.to_dict(),
        }
        payload.update(estimate_kind_payload())
        return payload

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> PredictedMuckpile:
        data = data or {}
        return cls(
            length_m=float(data.get("length_m", 0.0) or 0.0),
            width_m=float(data.get("width_m", 0.0) or 0.0),
            height_m=float(data.get("height_m", 0.0) or 0.0),
            volume_m3=float(data.get("volume_m3", 0.0) or 0.0),
            throw_m=float(data.get("throw_m", 0.0) or 0.0),
            heave_m=float(data.get("heave_m", 0.0) or 0.0),
            swell_factor=float(data.get("swell_factor", 1.0) or 1.0),
            in_situ_volume_m3=float(data.get("in_situ_volume_m3", 0.0) or 0.0),
            centroid_x=float(data.get("centroid_x", 0.0) or 0.0),
            centroid_y=float(data.get("centroid_y", 0.0) or 0.0),
            envelope=[dict(point) for point in data.get("envelope", [])],
            notes=str(data.get("notes", "") or DISCLAIMER),
            provenance=ModelProvenance.from_dict(data.get("provenance")),
            role=ROLE_PREDICTED,
        )


@dataclass
class MeasuredMuckpileEcho:
    """Echo of a measured muckpile. The estimate never overwrites these values."""

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
    def from_dict(cls, data: dict[str, Any] | None) -> MeasuredMuckpileEcho:
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
