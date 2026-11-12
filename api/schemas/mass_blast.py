"""HTTP contracts for the mass-blast project module."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class MassBlastBlockDetailsSchema(BaseModel):
    """Поля блока проекта МВ v2 (TASK-018, PR 2): геология, назначение, площадь, примечания к скважинам."""

    model_config = ConfigDict(extra="forbid")

    rock_text: str = Field("", max_length=300)
    hydro_text: str = Field("", max_length=200)
    purpose: Literal["", "MINING", "STRIPPING"] = ""
    area_m2: float | None = Field(None, gt=0, le=1_000_000)
    # Ручное примечание к скважине в таблице параметров — только действие.
    hole_notes: dict[str, str] = Field(default_factory=dict, max_length=2000)


class MassBlastBlockInputSchema(BaseModel):
    design_id: str = Field(..., min_length=1, max_length=120)
    technical_passport_id: str | None = Field(None, max_length=36)
    code: str = Field("", max_length=120)
    horizon: str = Field("", max_length=120)
    details: MassBlastBlockDetailsSchema | None = None


class ResponsibilitySchema(BaseModel):
    role_code: str = Field(..., min_length=1, max_length=80)
    employee_code: str = Field(..., min_length=1, max_length=80)
    employee_name: str = Field("", max_length=300)
    position_name: str = Field("", max_length=300)
    # Учётка, которой одной разрешено согласовать эту роль в ревизии.
    account_email: str = Field("", max_length=320)


class MassBlastAccountSchema(BaseModel):
    email: str
    display_name: str


class GuardPostSchema(BaseModel):
    code: str = Field(..., min_length=1, max_length=80)
    location: str = Field(..., min_length=1, max_length=500)
    responsible_employee_code: str = Field("", max_length=80)
    notes: str = Field("", max_length=1000)


class LayoutPointSchema(BaseModel):
    """Точка на ситуационном плане Г.5 в СК объекта: пост (по коду), взрывная станция, укрытие, место сбора."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["guard_post", "blast_station", "shelter", "gather"]
    ref: str = Field("", max_length=80)
    x: float = Field(..., allow_inf_nan=False)
    y: float = Field(..., allow_inf_nan=False)
    label: str = Field("", max_length=300)


class NotificationSchema(BaseModel):
    recipient: str = Field(..., min_length=1, max_length=300)
    channel: str = Field("", max_length=80)
    sent_at: str = Field("", max_length=60)


class PersonSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    position: str = Field("", max_length=200)
    name: str = Field("", max_length=200)


class SignerSchema(PersonSchema):
    # Основание полномочий (приказ № и дата), если подписывает не технический руководитель (п. 414).
    authority: str = Field("", max_length=200)
    is_head: bool | None = None


class RequisitesSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_no: str = Field("", max_length=40)
    project_date: str = Field("", max_length=10)
    tp_basis: str = Field("", max_length=300)
    made_by: PersonSchema = Field(default_factory=PersonSchema)
    checked_by: PersonSchema = Field(default_factory=PersonSchema)
    customer_name: str = Field("", max_length=300)
    contractor_name: str = Field("", max_length=300)
    customer_approver: SignerSchema = Field(default_factory=SignerSchema)
    contractor_approver: SignerSchema = Field(default_factory=SignerSchema)
    # «Согласовано:» маркшейдер и геолог (рудные месторождения); пусто — строка не печатается.
    agreements: list[PersonSchema] = Field(default_factory=list, max_length=2)
    surveyor_name: str = Field("", max_length=200)
    drilled_by: Literal["", "CUSTOMER", "CONTRACTOR"] = ""


class ExplosivesTextSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    bit_mm: float | None = Field(None, gt=0, le=1000)
    reaming_k: float | None = Field(None, gt=0, le=2)
    initiation: str = Field("", max_length=300)
    scheme: str = Field("", max_length=300)
    charge_design: str = Field("", max_length=300)
    stemming_material: str = Field("", max_length=120)
    starter_product: str = Field("", max_length=200)
    q_tp_kg_m3: float | None = Field(None, gt=0, le=10)
    q_just: str = Field("", max_length=600)


class ScheduleInputSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    charging_from: str = Field("", max_length=10)
    charging_shift_from: str = Field("", max_length=5)
    charging_shift_to: str = Field("", max_length=5)
    charging_order: str = Field("", max_length=300)
    network_order: str = Field("", max_length=300)
    station: str = Field("", max_length=300)
    shelter: str = Field("", max_length=300)
    gather: str = Field("", max_length=300)
    exit_route: str = Field("", max_length=300)
    siren: str = Field("", max_length=200)
    measures: str = Field("", max_length=600)
    other_conditions: str = Field("", max_length=600)
    airblast_buildings: str = Field("", max_length=300)
    transport: str = Field("", max_length=200)
    cleaning: str = Field("", max_length=200)
    briefing_date: str = Field("", max_length=10)
    # С какого фланга нумеровать заходки СЗМ на Г.3, если смотреть с откоса вглубь.
    szm_start_flank: Literal["", "left", "right"] = ""


PersonnelRole = Literal[
    "senior_blaster", "escort", "mining_master", "energy", "notify", "talon_receiver",
    "blaster", "storekeeper", "site_manager", "charging_crew",
]


class PersonnelSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role_code: PersonnelRole
    position: str = Field("", max_length=200)
    name: str = Field("", max_length=300)


class ProtectedObjectSchema(BaseModel):
    """Ручной охраняемый объект или пометка к объекту ситуации (`key` = «SITUATION:<слой>»)."""

    model_config = ConfigDict(extra="forbid")

    source: Literal["MANUAL", "SITUATION"] = "MANUAL"
    key: str = Field("", max_length=320)
    name: str = Field("", max_length=300)
    kind: Literal["", "people", "buildings", "structures", "mechanisms"] = ""
    distance_m: float | None = Field(None, ge=0, le=100_000)
    sensitive: bool = False
    measures: str = Field("", max_length=600)
    k_ground: float | None = Field(None, gt=0, le=50)
    k_structure: float | None = Field(None, gt=0, le=10)


class MassBlastProjectInputSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., min_length=1, max_length=300)
    site_code: str = Field(..., min_length=1, max_length=80)
    object_name: str = Field(..., min_length=1, max_length=300)
    customer_code: str = Field("", max_length=80)
    blast_date: str = Field(..., min_length=1, max_length=10)
    blast_time: str = Field("", max_length=20)
    document_profile_code: str = Field("STANDARD", min_length=1, max_length=80)
    reference_revision_id: str | None = Field(None, max_length=36)
    blocks: list[MassBlastBlockInputSchema] = Field(min_length=1, max_length=100)
    responsibilities: list[ResponsibilitySchema] = Field(default_factory=list)
    safety_plan: dict[str, Any] = Field(default_factory=dict)
    charging_schedule: list[dict[str, Any]] = Field(default_factory=list)
    signal_plan: dict[str, Any] = Field(default_factory=dict)
    guard_posts: list[GuardPostSchema] = Field(default_factory=list)
    notifications: list[NotificationSchema] = Field(default_factory=list)
    # Документный контекст v2 (форма ВМ.09.03, TASK-018): новый проект — только при
    # включённом флаге `mass_blast_v2`; черновик v1 переводится явно и только вперёд.
    context_version: Literal[1, 2] = 1
    requisites: RequisitesSchema | None = None
    explosives: ExplosivesTextSchema | None = None
    schedule: ScheduleInputSchema | None = None
    personnel: list[PersonnelSchema] = Field(default_factory=list, max_length=40)
    protected_objects: list[ProtectedObjectSchema] = Field(default_factory=list, max_length=200)
    safety_overrides: dict[str, float | bool | None] = Field(default_factory=dict, max_length=40)
    layout_points: list[LayoutPointSchema] = Field(default_factory=list, max_length=100)
    expected_version: int | None = Field(None, ge=1)


class MassBlastNewProjectSchema(BaseModel):
    """Окно «Создать проект МВ» (TASK-018, PR 6): остальное сервер заполняет сам."""

    model_config = ConfigDict(extra="forbid")

    design_ids: list[str] = Field(..., min_length=1, max_length=100)
    blast_date: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$")
    blast_time: str = Field("", pattern=r"^$|^([01]\d|2[0-3]):[0-5]\d$")
    site_code: str = Field("", max_length=80)

    @field_validator("design_ids")
    @classmethod
    def _ids(cls, value: list[str]) -> list[str]:
        if any(not item.strip() or len(item) > 120 for item in value):
            raise ValueError("Идентификатор проекта блока — от 1 до 120 знаков")
        return value


class MassBlastRoleSchema(BaseModel):
    code: str
    label: str


class MassBlastHintsSchema(BaseModel):
    previous_project_no: str = ""
    previous_project_date: str = ""
    previous_project_name: str = ""
    # Роли распорядка с подписями (`PERSONNEL_ROLES`): форма «Персонал» их не дублирует.
    personnel_roles: list[MassBlastRoleSchema] = Field(default_factory=list)


class MassBlastProjectSummarySchema(BaseModel):
    id: str
    name: str
    site_code: str
    object_name: str
    blast_date: str
    lifecycle_status: Literal["draft", "in_review", "approved", "executed", "closed"]
    version: int
    current_revision_id: str | None = None
    block_design_ids: list[str] = Field(default_factory=list)
    updated_at: str


class MassBlastProjectSchema(MassBlastProjectSummarySchema):
    customer_code: str = ""
    blast_time: str = ""
    document_profile_code: str
    reference_revision_id: str | None = None
    blocks: list[dict[str, Any]]
    responsibilities: list[ResponsibilitySchema]
    safety_plan: dict[str, Any]
    charging_schedule: list[dict[str, Any]]
    signal_plan: dict[str, Any]
    guard_posts: list[GuardPostSchema]
    notifications: list[NotificationSchema]
    context_version: int = 1
    requisites: dict[str, Any] | None = None
    explosives: dict[str, Any] | None = None
    schedule: dict[str, Any] | None = None
    personnel: list[dict[str, Any]] = Field(default_factory=list)
    protected_objects: list[dict[str, Any]] = Field(default_factory=list)
    safety_overrides: dict[str, Any] = Field(default_factory=dict)
    layout_points: list[dict[str, Any]] = Field(default_factory=list)
    created_at: str
    created_by: str
    updated_by: str


class MassBlastValidationIssueSchema(BaseModel):
    level: Literal["error", "warning"]
    code: str
    message: str
    path: str = ""


class MassBlastValidationResponse(BaseModel):
    valid: bool
    issues: list[MassBlastValidationIssueSchema]
    context: dict[str, Any]
    # Проект v2 (PR 6, §14): путь поля payload → {value, source} — что подставится в пустое поле.
    defaults: dict[str, Any] = Field(default_factory=dict)
    # «Запомнить для объекта» (В8): путь поля → значение в справочнике объекта (null — пусто).
    rememberable: dict[str, Any] = Field(default_factory=dict)


class RevisionCreateSchema(BaseModel):
    expected_version: int = Field(..., ge=1)
    require_attachments: bool = False


class MassBlastRevisionSchema(BaseModel):
    id: str
    project_id: str
    revision_no: int
    previous_revision_id: str | None = None
    reference_revision_id: str
    technical_formula_version: str
    document_template_version: str
    content_sha256: str
    created_at: str
    created_by: str
    context: dict[str, Any]


class MassBlastApprovalCreateSchema(BaseModel):
    role_code: str = Field(..., min_length=1, max_length=80)
    decision: Literal["approved", "rejected"]
    comment: str = Field("", max_length=2000)


class MassBlastApprovalSchema(BaseModel):
    id: str
    revision_id: str
    role_code: str
    actor: str
    decision: Literal["approved", "rejected"]
    comment: str
    content_sha256: str
    created_at: str


class MassBlastDocumentCreateSchema(BaseModel):
    revision_id: str = Field(..., min_length=1, max_length=36)
    kind: Literal["PROJECT", "ORDER", "SCHEDULE", "PACKAGE"] = "PROJECT"
    format: Literal["PDF", "XLSX", "ZIP"] = "PDF"


class MassBlastDocumentSchema(BaseModel):
    id: str
    revision_id: str
    kind: str
    format: str
    filename: str
    sha256: str
    created_at: str


class MassBlastAttachmentSchema(BaseModel):
    id: str
    project_id: str
    revision_id: str | None = None
    kind: str
    filename: str
    mime_type: str
    byte_size: int
    sha256: str
    created_at: str
    created_by: str


class MassBlastLifecycleSchema(BaseModel):
    to_status: Literal["draft", "in_review", "approved", "executed", "closed"]
    expected_version: int = Field(..., ge=1)
    confirm: bool = False
    note: str = Field("", max_length=2000)


# --- Слои дня взрыва (TASK-018, PR 2) ---------------------------------------

LayerKind = Literal["NARYAD", "NOTIFICATION", "READINESS_ACT", "TALON", "ACCEPTANCE_ACT", "EXECUTION"]

_TIME_PATTERN = r"^$|^([01]\d|2[0-3]):[0-5]\d$"
_DATE_PATTERN = r"^$|^\d{4}-\d{2}-\d{2}$"


def _not_negative(name: str, value: dict[str, float]) -> dict[str, float]:
    for key, amount in value.items():
        if amount < 0:
            raise ValueError(f"{name} «{key}» не может быть отрицательным")
    return value


class NaryadPayloadSchema(BaseModel):
    """Наряд-путёвка: введённое вручную. Запас — по ключу строки ВМ («вид:марка:замедление»)."""

    model_config = ConfigDict(extra="forbid")

    number: str = Field("", max_length=40)
    issue_date: str = Field("", max_length=10)
    warehouse: str = Field("", max_length=200)
    permit: str = Field("", max_length=300)
    blaster_index: str = Field("", max_length=40)
    vehicle: str = Field("", max_length=200)
    driver: str = Field("", max_length=200)
    delivery: str = Field("", max_length=300)
    vv_site: bool = False
    reserve: dict[str, float] = Field(default_factory=dict, max_length=60)
    # После взрыва (TASK-018, PR 5): выдано, израсходовано (главнее факта),
    # возвращено (главнее «выдано − израсходовано») — по ключу строки ВМ.
    issued: dict[str, float] = Field(default_factory=dict, max_length=60)
    consumed: dict[str, float] = Field(default_factory=dict, max_length=60)
    returned: dict[str, float] = Field(default_factory=dict, max_length=60)

    @field_validator("reserve")
    @classmethod
    def _reserve_not_negative(cls, value: dict[str, float]) -> dict[str, float]:
        return _not_negative("Запас", value)

    @field_validator("issued", "consumed", "returned")
    @classmethod
    def _after_blast_not_negative(cls, value: dict[str, float]) -> dict[str, float]:
        return _not_negative("Количество", value)


class NotificationPayloadSchema(BaseModel):
    """Уведомление: адресат — из справочника карьера (`notification_code`) или, без справочника, вручную."""

    model_config = ConfigDict(extra="forbid")

    notification_code: str = Field("", max_length=120)
    recipient_position: str = Field("", max_length=300)
    recipient_name: str = Field("", max_length=120)
    salutation: str = Field("", max_length=200)
    signer: str = Field("", max_length=200)
    out_no: str = Field("", max_length=40)
    out_date: str = Field("", max_length=10)


class ReadinessActPayloadSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    act_date: str = Field("", max_length=10)
    conditions: dict[str, bool | None] = Field(default_factory=dict, max_length=10)
    remarks: str = Field("", max_length=1000)
    conclusion: Literal["", "READY", "NOT_READY"] = ""
    handed_by: str = Field("", max_length=200)
    accepted_by: str = Field("", max_length=200)
    survey_handed_over: bool = False


class TalonPayloadSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    issued_date: str = Field("", max_length=10)
    issued_time: str = Field("", max_length=5)
    issued_by: str = Field("", max_length=200)
    received_by: str = Field("", max_length=200)
    # Фактические дата и время взрыва: «не ранее» = факт + 30 мин (п. 422, PR 5).
    fired_date: str = Field("", pattern=_DATE_PATTERN)
    fired_time: str = Field("", pattern=_TIME_PATTERN)


class AcceptanceActPayloadSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    act_date: str = Field("", max_length=10)
    contract_no: str = Field("", max_length=80)
    contract_date: str = Field("", max_length=10)
    appendix_no: str = Field("", max_length=20)
    customer_person: str = Field("", max_length=300)
    accepted_volume_m3: float | None = Field(None, ge=0, le=10_000_000)
    remarks: str = Field("", max_length=1000)


class ExecutionPayloadSchema(BaseModel):
    """Слой «Факт» (PR 5): время взрыва по факту, отказы, примечания по факту к скважинам."""

    model_config = ConfigDict(extra="forbid")

    blast_date: str = Field("", pattern=_DATE_PATTERN)
    blast_time: str = Field("", pattern=_TIME_PATTERN)
    misfired_holes: list[str] = Field(default_factory=list, max_length=2000)
    hole_notes: dict[str, str] = Field(default_factory=dict, max_length=2000)

    @field_validator("misfired_holes")
    @classmethod
    def _short_ids(cls, value: list[str]) -> list[str]:
        if any(len(item) > 40 for item in value):
            raise ValueError("Номер скважины длиннее 40 знаков")
        return value

    @field_validator("hole_notes")
    @classmethod
    def _short_notes(cls, value: dict[str, str]) -> dict[str, str]:
        if any(len(key) > 40 or len(note) > 200 for key, note in value.items()):
            raise ValueError("Примечание по факту — до 200 знаков, номер скважины — до 40")
        return value


LAYER_PAYLOAD_SCHEMAS: dict[str, type[BaseModel]] = {
    "NARYAD": NaryadPayloadSchema,
    "NOTIFICATION": NotificationPayloadSchema,
    "READINESS_ACT": ReadinessActPayloadSchema,
    "TALON": TalonPayloadSchema,
    "ACCEPTANCE_ACT": AcceptanceActPayloadSchema,
    "EXECUTION": ExecutionPayloadSchema,
}


class MassBlastLayerCreateSchema(BaseModel):
    kind: LayerKind
    payload: dict[str, Any] = Field(default_factory=dict)


class MassBlastLayerUpdateSchema(BaseModel):
    payload: dict[str, Any] = Field(default_factory=dict)
    expected_version: int = Field(..., ge=1)


class MassBlastLayerRefreshSchema(BaseModel):
    expected_version: int = Field(..., ge=1)
    confirm: bool = False


class MassBlastLayerIssueSchema(BaseModel):
    expected_version: int = Field(..., ge=1)


class MassBlastLayerSchema(BaseModel):
    id: str
    project_id: str
    kind: LayerKind
    project_revision_id: str
    status: Literal["draft", "issued"]
    version: int
    current_revision_id: str | None = None
    stale: bool
    seed: dict[str, Any]
    payload: dict[str, Any]
    view: dict[str, Any] = Field(default_factory=dict)
    issues: list[MassBlastValidationIssueSchema] = Field(default_factory=list)
    created_at: str
    created_by: str
    updated_at: str
    updated_by: str


class MassBlastLayerRefreshResponse(BaseModel):
    applied: bool
    changes: list[dict[str, Any]]
    layer: MassBlastLayerSchema


class MassBlastLayerRevisionSchema(BaseModel):
    id: str
    layer_id: str
    revision_no: int
    project_revision_id: str
    content_sha256: str
    created_at: str
    created_by: str
    context: dict[str, Any]


class MassBlastLayerAvailabilitySchema(BaseModel):
    kind: LayerKind
    label: str
    can_open: bool
    reason: str = ""
    multiple: bool = False
    count: int = 0


class NotificationAddresseeSchema(BaseModel):
    code: str
    label: str
    taken: bool = False


class NotificationAddresseesSchema(BaseModel):
    registry: bool
    items: list[NotificationAddresseeSchema] = Field(default_factory=list)


class MassBlastRememberSchema(BaseModel):
    """«Запомнить для объекта» (В8): поля проекта (или слоя, если задан `layer_id`)."""

    model_config = ConfigDict(extra="forbid")

    paths: list[str] = Field(..., min_length=1, max_length=40)
    layer_id: str | None = Field(None, max_length=36)


class MassBlastRememberResponse(BaseModel):
    revision_id: str
    fields: list[str]
