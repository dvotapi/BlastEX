"""Схемы API паспорта на бурение (TASK-015, PR 1)."""
from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from design.drilling_passport import (
    DEFAULT_ACCEPTANCE,
    DEFAULT_EXTRA_APPROVALS,
    DEFAULT_SITE_PREPARATION,
    DEFAULT_TOLERANCE_M,
)

ApprovalLine = Annotated[str, Field(max_length=120)]

# Длины печатаемых полей ограничены: титул и порядок работ должны помещаться
# на свою страницу без заметного ужатия (PDF, PR 2). Проверяются только при
# записи (`DrillingPassportPayloadInput`): черновики, сохранённые раньше,
# читаются как есть.
MAX_PERSONNEL = 20
TEXT_LIMITS = {
    "basis": 300, "object_name": 200, "customer": 200, "block": 40, "horizon": 40,
    "rig_name": 80, "rig_number": 40, "drilling_start": 40, "drilling_end": 40,
    "site_preparation": 300, "stakeout": 300, "drilling_order": 300, "access_route": 300,
    "power_lines": 300, "adjacent_works": 300, "acceptance": 300, "profile_code": 80,
}
SIGNER_LIMITS = {"position": 120, "organization": 200, "name": 120}
PERSON_LIMITS = {"name": 120, "position": 120}


class SignerSchema(BaseModel):
    position: str = Field(default="", description="Должность")
    organization: str = Field(default="", description="Организация")
    name: str = Field(default="", description="ФИО")


class PersonSchema(BaseModel):
    name: str = Field(default="", description="ФИО")
    position: str = Field(default="", description="Должность")


class DrillingPassportPayload(BaseModel):
    """Поля листа «Реквизиты» формы v0.7 и ручные переопределения расчёта."""

    # Бесконечность в JSONB не записать: 422, а не 503.
    model_config = ConfigDict(allow_inf_nan=False)

    agreed_by: SignerSchema = Field(default_factory=SignerSchema, description="СОГЛАСОВАНО")
    approved_by: SignerSchema = Field(default_factory=SignerSchema, description="УТВЕРЖДАЮ")
    compiled_by: SignerSchema = Field(default_factory=SignerSchema, description="Паспорт составил")
    basis: str = Field(default="", description="Составлен на основании")
    site_code: str = Field(default="", description="Код объекта в справочнике")
    object_name: str = Field(default="", description="Объект")
    customer: str = Field(default="", description="Заказчик")
    block: str = Field(default="", description="Блок")
    horizon: str = Field(default="", description="Горизонт")
    block_area_m2: float | None = Field(default=None, gt=0, description="Площадь блока, м²")
    rig_type_code: str = Field(default="", description="Тип бурового станка в справочнике")
    profile_code: str = Field(
        default="", description="Профиль паспорта в справочнике: тексты мер безопасности и технологии"
    )
    rig_name: str = Field(default="", description="Буровая установка")
    rig_number: str = Field(default="", description="Номер станка")
    bit_diameter_mm: float | None = Field(default=None, gt=0, description="Диаметр инструмента, мм")
    drilling_start: str = Field(default="", description="Начало бурения")
    drilling_end: str = Field(default="", description="Окончание бурения")
    site_preparation: str = Field(default=DEFAULT_SITE_PREPARATION, description="Подготовка площадки")
    stakeout: str = Field(default="", description="Вынос точек")
    drilling_order: str = Field(default="", description="Порядок обуривания")
    access_route: str = Field(default="", description="Въезд и перегон")
    power_lines: str = Field(default="", description="ЛЭП и кабели")
    adjacent_works: str = Field(default="", description="Соседние работы")
    acceptance: str = Field(default=DEFAULT_ACCEPTANCE, description="Приёмка блока")
    extra_approvals: list[ApprovalLine] = Field(
        default_factory=lambda: list(DEFAULT_EXTRA_APPROVALS),
        max_length=2,
        description="Дополнительные согласования: до двух строк «должность ФИО»",
    )
    tol_depth_m: float = Field(default=DEFAULT_TOLERANCE_M, gt=0, le=2, description="Допуск по глубине скважины, ± м")
    tol_collar_m: float = Field(default=DEFAULT_TOLERANCE_M, gt=0, le=2, description="Допуск по положению устья, ± м")
    personnel: list[PersonSchema] = Field(default_factory=list, description="Персонал для ознакомления")
    alpha_deg: float | None = Field(default=None, ge=30, le=90, description="Угол откоса α, если не из справочника")
    gamma_deg: float | None = Field(default=None, ge=20, le=90, description="Угол устойчивого борта γ")
    axis_offset_m: float | None = Field(default=None, ge=0, le=5, description="Вылет оси e, м")
    first_row_offset_m: float | None = Field(default=None, ge=0, description="От бровки до оси первого ряда c, м")
    w_max_m: float | None = Field(default=None, gt=0, description="Допустимая ЛСПП Wпред, м")
    bench_height_for_s_m: float | None = Field(
        default=None, gt=0, le=30, description="Высота уступа для безопасного расстояния, м"
    )


def _too_long(label: str, value: str, limit: int) -> str | None:
    return f"{label}: не длиннее {limit} символов" if len(value) > limit else None


class DrillingPassportPayloadInput(DrillingPassportPayload):
    """Payload при создании и сохранении: с пределами длины печатаемых полей."""

    @model_validator(mode="after")
    def _printable_lengths(self) -> "DrillingPassportPayloadInput":
        problems = [_too_long(key, getattr(self, key), limit) for key, limit in TEXT_LIMITS.items()]
        for key in ("agreed_by", "approved_by", "compiled_by"):
            signer = getattr(self, key)
            problems += [_too_long(f"{key}.{field}", getattr(signer, field), limit) for field, limit in SIGNER_LIMITS.items()]
        for index, person in enumerate(self.personnel):
            problems += [
                _too_long(f"personnel[{index}].{field}", getattr(person, field), limit)
                for field, limit in PERSON_LIMITS.items()
            ]
        if len(self.personnel) > MAX_PERSONNEL:
            problems.append(f"personnel: не больше {MAX_PERSONNEL} человек")
        problems = [problem for problem in problems if problem]
        if problems:
            raise ValueError("; ".join(problems))
        return self


class DrillingPassportCreateSchema(BaseModel):
    design_id: str = Field(min_length=1)
    passport_no: str | None = Field(default=None, min_length=1, max_length=120)
    passport_date: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    payload: DrillingPassportPayloadInput | None = None


class DrillingPassportUpdateSchema(BaseModel):
    passport_no: str = Field(min_length=1, max_length=120)
    passport_date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    payload: DrillingPassportPayloadInput
    expected_version: int = Field(ge=1)


class DrillingPassportSchema(BaseModel):
    id: str
    design_id: str
    passport_no: str
    passport_date: str
    status: Literal["draft", "approved", "drilled", "accepted"]
    version: int
    current_revision_id: str | None = None
    payload: DrillingPassportPayload
    created_at: str
    created_by: str
    updated_at: str
    updated_by: str


class DrillingPassportValidationSchema(BaseModel):
    valid: bool
    issues: list[dict[str, str]]
    summary: dict[str, Any]
    first_row_check: dict[str, Any]
    inputs: dict[str, float | None]
    provenance: dict[str, str | None]


class DrillingPassportRevisionCreateSchema(BaseModel):
    expected_version: int = Field(ge=1)
    acknowledged_warnings: list[str] = Field(default_factory=list, description="Коды просмотренных предупреждений")


class DrillingPassportRevisionSchema(BaseModel):
    id: str
    passport_id: str
    revision_no: int
    previous_revision_id: str | None = None
    reference_revision_id: str | None = None
    formula_version: str
    design_id: str
    design_revision: int
    design_sha256: str
    content_sha256: str
    context: dict[str, Any]
    created_at: str
    created_by: str
