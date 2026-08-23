"""Fragmentation data types. Designed / predicted / measured stay separate."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

ROLE_DESIGNED = "designed"
ROLE_PREDICTED = "predicted"
ROLE_MEASURED = "measured"

FRAGMENTATION_ROLES = (ROLE_DESIGNED, ROLE_PREDICTED, ROLE_MEASURED)

MODEL_KUZNETSOV = "kuznetsov"
MODEL_KUZRAM = "kuzram"
MODEL_SWEBREC = "swebrec"
FRAGMENTATION_MODEL_IDS = (MODEL_KUZNETSOV, MODEL_KUZRAM, MODEL_SWEBREC)


def _opt_float(data: dict[str, Any], key: str) -> float | None:
    raw = data.get(key)
    if raw is None or raw == "":
        return None
    return float(raw)


@dataclass
class Calibration:
    """Optional site overrides. None means “use the model default”."""

    rock_factor_A: float | None = None
    uniformity_n: float | None = None
    swebrec_b: float | None = None
    xmax_mm: float | None = None
    drill_deviation_m: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "rock_factor_A": self.rock_factor_A,
            "uniformity_n": self.uniformity_n,
            "swebrec_b": self.swebrec_b,
            "xmax_mm": self.xmax_mm,
            "drill_deviation_m": self.drill_deviation_m,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> Calibration:
        data = data or {}
        return cls(
            rock_factor_A=_opt_float(data, "rock_factor_A"),
            uniformity_n=_opt_float(data, "uniformity_n"),
            swebrec_b=_opt_float(data, "swebrec_b"),
            xmax_mm=_opt_float(data, "xmax_mm"),
            drill_deviation_m=_opt_float(data, "drill_deviation_m"),
        )


@dataclass
class FragmentationInputs:
    """Engineering inputs for one influence region. Units are in the names."""

    burden_m: float
    spacing_m: float
    bench_height_m: float
    diameter_mm: float
    charge_mass_kg: float
    powder_factor_kg_m3: float
    stemming_m: float
    explosive_name: str
    explosive_density_t_m3: float
    explosive_energy_mj_kg: float
    rock_name: str
    rock_density_t_m3: float
    rock_ucs_mpa: float
    rock_fissuring: float
    lump_size_mm: float
    hole_oversize_coeff: float = 1.05
    influence_volume_m3: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> FragmentationInputs:
        data = data or {}
        return cls(
            burden_m=float(data.get("burden_m", 0.0) or 0.0),
            spacing_m=float(data.get("spacing_m", 0.0) or 0.0),
            bench_height_m=float(data.get("bench_height_m", 0.0) or 0.0),
            diameter_mm=float(data.get("diameter_mm", 0.0) or 0.0),
            charge_mass_kg=float(data.get("charge_mass_kg", 0.0) or 0.0),
            powder_factor_kg_m3=float(data.get("powder_factor_kg_m3", 0.0) or 0.0),
            stemming_m=float(data.get("stemming_m", 0.0) or 0.0),
            explosive_name=str(data.get("explosive_name", "")),
            explosive_density_t_m3=float(data.get("explosive_density_t_m3", 0.0) or 0.0),
            explosive_energy_mj_kg=float(data.get("explosive_energy_mj_kg", 0.0) or 0.0),
            rock_name=str(data.get("rock_name", "")),
            rock_density_t_m3=float(data.get("rock_density_t_m3", 0.0) or 0.0),
            rock_ucs_mpa=float(data.get("rock_ucs_mpa", 0.0) or 0.0),
            rock_fissuring=float(data.get("rock_fissuring", 0.0) or 0.0),
            lump_size_mm=float(data.get("lump_size_mm", 0.0) or 0.0),
            hole_oversize_coeff=float(data.get("hole_oversize_coeff", 1.05) or 1.05),
            influence_volume_m3=float(data.get("influence_volume_m3", 0.0) or 0.0),
        )


@dataclass
class ModelProvenance:
    """What produced a prediction. Role is always predicted for this object."""

    model: str
    model_version: str
    inputs: dict[str, Any] = field(default_factory=dict)
    parameters: dict[str, Any] = field(default_factory=dict)
    calibration: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "model": self.model,
            "model_version": self.model_version,
            "inputs": dict(self.inputs),
            "parameters": dict(self.parameters),
            "calibration": dict(self.calibration),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> ModelProvenance:
        data = data or {}
        return cls(
            model=str(data.get("model", "")),
            model_version=str(data.get("model_version", "")),
            inputs=dict(data.get("inputs", {}) or {}),
            parameters=dict(data.get("parameters", {}) or {}),
            calibration=dict(data.get("calibration", {}) or {}),
        )


@dataclass
class DistributionPoint:
    size_mm: float
    passing_pct: float

    def to_dict(self) -> dict[str, Any]:
        return {"size_mm": self.size_mm, "passing_pct": self.passing_pct}

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> DistributionPoint:
        data = data or {}
        return cls(
            size_mm=float(data.get("size_mm", 0.0) or 0.0),
            passing_pct=float(data.get("passing_pct", 0.0) or 0.0),
        )


@dataclass
class DesignedFragmentationTarget:
    """Design intent (role=designed). Not a prediction and not a measurement."""

    lump_size_mm: float
    max_oversize_pct: float = 5.0
    role: str = ROLE_DESIGNED

    def __post_init__(self) -> None:
        self.role = ROLE_DESIGNED

    def to_dict(self) -> dict[str, Any]:
        return {
            "lump_size_mm": self.lump_size_mm,
            "max_oversize_pct": self.max_oversize_pct,
            "role": ROLE_DESIGNED,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> DesignedFragmentationTarget:
        data = data or {}
        return cls(
            lump_size_mm=float(data.get("lump_size_mm", 0.0) or 0.0),
            max_oversize_pct=float(data.get("max_oversize_pct", 5.0) or 5.0),
            role=ROLE_DESIGNED,
        )


@dataclass
class PredictedFragmentation:
    """Model output. Role is always predicted and cannot be set to measured."""

    x20_mm: float
    x50_mm: float
    x80_mm: float
    oversize_pct: float
    powder_factor_kg_m3: float
    curve: list[DistributionPoint] = field(default_factory=list)
    provenance: ModelProvenance = field(default_factory=ModelProvenance)
    role: str = ROLE_PREDICTED

    def __post_init__(self) -> None:
        self.role = ROLE_PREDICTED

    def to_dict(self) -> dict[str, Any]:
        return {
            "role": ROLE_PREDICTED,
            "x20_mm": self.x20_mm,
            "x50_mm": self.x50_mm,
            "x80_mm": self.x80_mm,
            "oversize_pct": self.oversize_pct,
            "powder_factor_kg_m3": self.powder_factor_kg_m3,
            "curve": [point.to_dict() for point in self.curve],
            "provenance": self.provenance.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> PredictedFragmentation:
        data = data or {}
        return cls(
            x20_mm=float(data.get("x20_mm", 0.0) or 0.0),
            x50_mm=float(data.get("x50_mm", 0.0) or 0.0),
            x80_mm=float(data.get("x80_mm", 0.0) or 0.0),
            oversize_pct=float(data.get("oversize_pct", 0.0) or 0.0),
            powder_factor_kg_m3=float(data.get("powder_factor_kg_m3", 0.0) or 0.0),
            curve=[DistributionPoint.from_dict(item) for item in data.get("curve", [])],
            provenance=ModelProvenance.from_dict(data.get("provenance")),
            role=ROLE_PREDICTED,
        )


def _first_opt_float(data: dict[str, Any], *keys: str) -> float | None:
    for key in keys:
        if key in data and data.get(key) is not None and data.get(key) != "":
            return _opt_float(data, key)
    return None


@dataclass
class MeasuredFragmentation:
    """Sieve or image measurement. The predictor never writes this type.

    P20/P50/P80 are stored as x20_mm / x50_mm / x80_mm. Role is always measured.
    """

    x20_mm: float | None = None
    x50_mm: float | None = None
    x80_mm: float | None = None
    oversize_pct: float | None = None
    curve: list[DistributionPoint] = field(default_factory=list)
    source: str = ""
    method: str = ""
    timestamp: str = ""
    notes: str = ""
    role: str = ROLE_MEASURED

    def __post_init__(self) -> None:
        self.role = ROLE_MEASURED

    def to_dict(self) -> dict[str, Any]:
        return {
            "role": ROLE_MEASURED,
            "x20_mm": self.x20_mm,
            "x50_mm": self.x50_mm,
            "x80_mm": self.x80_mm,
            "p20_mm": self.x20_mm,
            "p50_mm": self.x50_mm,
            "p80_mm": self.x80_mm,
            "oversize_pct": self.oversize_pct,
            "curve": [point.to_dict() for point in self.curve],
            "source": self.source,
            "method": self.method,
            "timestamp": self.timestamp,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> MeasuredFragmentation:
        data = data or {}
        return cls(
            x20_mm=_first_opt_float(data, "x20_mm", "p20_mm", "P20"),
            x50_mm=_first_opt_float(data, "x50_mm", "p50_mm", "P50"),
            x80_mm=_first_opt_float(data, "x80_mm", "p80_mm", "P80"),
            oversize_pct=_first_opt_float(data, "oversize_pct", "oversize"),
            curve=[DistributionPoint.from_dict(item) for item in data.get("curve", [])],
            source=str(data.get("source", "") or ""),
            method=str(data.get("method", "") or ""),
            timestamp=str(data.get("timestamp", "") or ""),
            notes=str(data.get("notes", "") or ""),
            role=ROLE_MEASURED,
        )
