"""Pydantic-схемы технологического расчёта BlastEngine."""
from __future__ import annotations

import math
from dataclasses import asdict
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, WithJsonSchema, model_validator
from pydantic_core import PydanticCustomError

from api.schemas.cost import BlockGeometrySchema, HoleGeometrySchema, InitiationConfigSchema
from simulation.fragmentation.cunningham import MIN_HOLE_DIAMETER_MM, KuzRamSettings


class RockPropertiesSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: str = Field(..., examples=["Габбро-диабаз"])
    density_t_m3: float = Field(..., gt=0, examples=[2.9])
    ucs_mpa: float = Field(..., gt=0, examples=[168])
    fissuring_ff: float = Field(..., ge=0, examples=[2.2])


class ExplosivePropertiesSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: str = Field(..., examples=["ЭВЕРСИН Э-100"])
    density_t_m3: float = Field(..., gt=0, examples=[1.12])
    power_mj_kg: float = Field(..., gt=0, examples=[2.99])


class TargetParamsSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    # Верхние границы — не технологический предел, а защита от переполнения:
    # без клэмпа n = math.pow(lump/xc, n) в rosin_rammler_oversize_pct кидает
    # OverflowError на абсурдных значениях (интерфейс не даёт их ввести:
    # lump_size_mm — 100–1200 мм, spacing_coeff_m — 1–2).
    lump_size_mm: float = Field(..., gt=0, le=10000, examples=[400])
    hole_diameter_mm: float = Field(0, ge=0)
    overdrill_m: float = Field(1.0, ge=0)
    hole_oversize_coeff: float = Field(1.05, ge=1.0, le=1.5)
    spacing_coeff_m: float = Field(1.25, gt=0, le=10)
    bench_height_m: float = Field(10.0, gt=0)


# Коронка не меньше нижней границы диаметра скважины в формуле n (коэффициент
# разбуривания не меньше 1); сверху — прежний предел фактов калибровки. Что
# и при коэффициенте до 1,5 скважина остаётся в границах формулы, проверяет тест.
CROWN_MM_MIN = MIN_HOLE_DIAMETER_MM
CROWN_MM_MAX = 1000.0


def _crown_within_bounds(value: float) -> float:
    if not (math.isfinite(value) and CROWN_MM_MIN <= value <= CROWN_MM_MAX):
        raise PydanticCustomError("crown_mm", f"Диаметр коронки — от {CROWN_MM_MIN:g} до {CROWN_MM_MAX:g} мм.")
    return value


# Границы проверяет AfterValidator (ради русского текста ошибки), поэтому в
# JSON-схему OpenAPI они вписаны явно — иначе клиент видит просто число.
CrownMm = Annotated[
    float,
    AfterValidator(_crown_within_bounds),
    WithJsonSchema({"type": "number", "minimum": CROWN_MM_MIN, "maximum": CROWN_MM_MAX}),
]

_KUZRAM_DEFAULTS = KuzRamSettings()


class KuzRamSettingsSchema(BaseModel):
    """Настройки модели Kuz-Ram. Границы и тексты ошибок — в KuzRamSettings.

    Умолчания читаются из ``_KUZRAM_DEFAULTS`` (сам датакласс), а не
    повторяются литералами — иначе схема и датакласс расходятся молча.
    """

    model_config = ConfigDict(extra="forbid")

    rock_factor_method: Literal["rmd50", "rmd10", "joint_factor", "manual"] = _KUZRAM_DEFAULTS.rock_factor_method
    rock_factor_manual: float = _KUZRAM_DEFAULTS.rock_factor_manual
    joint_condition: float = _KUZRAM_DEFAULTS.joint_condition
    joint_angle: int = _KUZRAM_DEFAULTS.joint_angle
    rock_factor_correction: float = _KUZRAM_DEFAULTS.rock_factor_correction
    strength_exponent: Literal["19/20", "19/30"] = _KUZRAM_DEFAULTS.strength_exponent
    drill_deviation_m: float = _KUZRAM_DEFAULTS.drill_deviation_m
    uniformity_correction: float = _KUZRAM_DEFAULTS.uniformity_correction
    q_max_kg_m3: float = _KUZRAM_DEFAULTS.q_max_kg_m3

    @model_validator(mode="after")
    def _within_bounds(self) -> "KuzRamSettingsSchema":
        try:
            self.to_settings()
        except ValueError as exc:
            # Простой ValueError pydantic заворачивает в ctx с самим объектом
            # исключения (не JSON-сериализуемо) и добавляет префикс «Value
            # error, » — PydanticCustomError отдаёт ровно текст сообщения.
            raise PydanticCustomError("kuzram_settings", str(exc)) from exc
        return self

    def to_settings(self) -> KuzRamSettings:
        return KuzRamSettings(**self.model_dump())

    @classmethod
    def from_settings(cls, settings: KuzRamSettings) -> "KuzRamSettingsSchema":
        return cls(**asdict(settings))


class RockFactorBreakdownSchema(BaseModel):
    """Состав фактора породы A (только новая модель)."""

    model_config = ConfigDict(from_attributes=True)

    method: str
    rmd: float | None
    rdi: float | None
    hf: float | None
    joint_spacing_m: float | None
    reduced_pattern_m: float | None
    jps: float | None
    base: float
    correction: float
    value: float


class FragmentationDetailsSchema(BaseModel):
    """Промежуточные величины расчёта коронки при подобранном q — для разбора."""

    model_config = ConfigDict(from_attributes=True)

    q_kg_m3: float
    hole_diameter_mm: float
    charge_length_m: float
    charge_mass_kg: float
    volume_per_hole_m3: float
    burden_m: float
    spacing_m: float
    burden_to_diameter: float
    rock_factor_a: float
    rock_factor: RockFactorBreakdownSchema | None
    re_weight: float
    strength_exponent: str
    x50_mm: float
    uniformity_n_raw: float
    uniformity_n: float
    charge_to_bench: float | None
    characteristic_size_mm: float
    oversize_pct: float


class LegacyVariantSchema(BaseModel):
    """Результат расчёта «до исправления» — для сравнения на переходный период."""

    specific_q_kg_m3: float
    line_of_least_resistance_m: float
    grid_a_m: float
    grid_b_m: float
    grid_label: str
    x50_mm: float
    oversize_pct: float
    reached: bool
    details: FragmentationDetailsSchema


class BlastOptimizeRequest(BaseModel):
    rock: RockPropertiesSchema
    explosive: ExplosivePropertiesSchema
    target: TargetParamsSchema
    crown_diameters_mm: list[CrownMm] = Field(
        default_factory=lambda: [110, 115, 122, 125, 130, 140, 152, 165, 171, 220, 250],
        min_length=1,
        max_length=50,
    )
    max_oversize_threshold_pct: float = Field(5.0, gt=0, le=30)
    kuzram: KuzRamSettingsSchema | None = None


class BlastOptimizeVariant(BaseModel):
    crown_mm: float
    specific_q_kg_m3: float
    line_of_least_resistance_m: float
    grid_a_m: float
    grid_b_m: float
    grid_label: str
    x50_mm: float
    oversize_pct: float
    target_q_kg_m3: float | None = None
    reached: bool
    details: FragmentationDetailsSchema
    legacy: LegacyVariantSchema


class BlastOptimizeResponse(BaseModel):
    variants: list[BlastOptimizeVariant]
    max_oversize_threshold_pct: float
    rock_name: str
    explosive_name: str
    model_version: str
    kuzram: KuzRamSettingsSchema


class KuzRamFactSchema(BaseModel):
    crown_mm: CrownMm
    q_kg_m3: float = Field(..., gt=0, le=10)
    oversize_pct: float = Field(..., gt=0, lt=100)


class KuzRamCalibrateRequest(BaseModel):
    rock: RockPropertiesSchema
    explosive: ExplosivePropertiesSchema
    target: TargetParamsSchema
    kuzram: KuzRamSettingsSchema | None = None
    facts: list[KuzRamFactSchema] = Field(..., min_length=1, max_length=50)


class KuzRamCalibrationRow(BaseModel):
    crown_mm: float
    q_kg_m3: float
    oversize_pct: float
    legacy_oversize_pct: float
    model_oversize_pct: float
    rock_factor_correction: float | None
    note: str | None = None


class KuzRamCalibrateResponse(BaseModel):
    rows: list[KuzRamCalibrationRow]
    rock_factor_correction: float | None
    used: int
    skipped: int
    model_version: str


class BlastConstantsSchema(BaseModel):
    crown_diameters_mm: list[float]
    nsi_length_options_m: list[float]
    detonator_delay_ms_options: list[int]


class BlastGeometryRequest(BaseModel):
    grid_a_m: float = Field(..., gt=0)
    grid_b_m: float = Field(..., gt=0)
    depth_m: float = Field(..., gt=0)
    overdrill_m: float = Field(0, ge=0)
    undercharge_m: float = Field(0, ge=0)
    crown_mm: float = Field(..., gt=0)
    hole_oversize_coeff: float = Field(1.05, ge=1.0, le=1.5)
    explosive_key: str
    block_volume_m3: float = Field(0, ge=0)
    additional_holes_pct: float = Field(0.03, ge=0, le=1)
    intermediate_detonators_per_hole: int = Field(1, ge=1, le=2)
    nsi_per_hole: int = Field(1, ge=1, le=2)
    nsi_length_1_m: float = Field(12.0, gt=0)
    nsi_length_2_m: float = Field(6.0, ge=0)
    detonator_delay_ms: int = Field(500, ge=0)
    view: str = Field("charge", pattern="^(charge|contour|drilling)$")


class BlastGeometryResponse(BaseModel):
    hole: HoleGeometrySchema
    block: BlockGeometrySchema
    initiation: InitiationConfigSchema
    label: str
    hole_rows: list[tuple[str, str]]
    block_rows: list[tuple[str, str]]
