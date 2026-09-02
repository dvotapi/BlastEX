"""Входы и общий контекст модели себестоимости блока.

Слой норм превращает драйверы технического паспорта в натуральные величины
(смены станка, человеко-смены, литры, тонно-километры). Цены сюда не
попадают: они живут в справочниках Cost V2, а умножение на них выполняют
модули домена и правила затрат.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Iterable, Literal, Mapping

from cost.v2.models import (
    CostLayer,
    CostLine,
    ReferenceItem,
    ReferenceSnapshot,
    decimal_value,
)
from cost.v2.packages import PackageDefinition, package_map


MODEL_VERSION = "cost-model-v1"

# Литров дизельного топлива в тонне при плотности 0,85 т/м³: справочник хранит
# цену тонны, а нормы расхода техники заданы в литрах.
DIESEL_LITRES_PER_TON = Decimal("1176.47")

BLOCK_SERVICE_LINE_ID = "BLOCK"


@dataclass(frozen=True)
class CrewMember:
    """Строка состава бригады на вкладке.

    ``shifts_per_block`` — ручная поправка: пусто означает «взять норматив
    должности либо вывести из производительности техники».
    """

    position_code: str
    headcount: Decimal = Decimal("1")
    shifts_per_block: Decimal | None = None

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "CrewMember":
        raw_shifts = data.get("shifts_per_block")
        return cls(
            position_code=str(data.get("position_code", "")),
            headcount=decimal_value(data.get("headcount"), Decimal("1")),
            shifts_per_block=None if raw_shifts in (None, "") else decimal_value(raw_shifts),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "position_code": self.position_code,
            "headcount": str(self.headcount),
            "shifts_per_block": (
                str(self.shifts_per_block) if self.shifts_per_block is not None else None
            ),
        }


DrillingExecutor = Literal["OWN", "SUBCONTRACTOR"]


@dataclass(frozen=True)
class ModelParameters:
    """Всё, чего нет в техническом паспорте, и что пользователь двигает руками."""

    package_code: str
    site_code: str
    reference_revision_id: str
    unit_plan_volume_m3: Decimal
    rig_code: str | None = None
    rig_plan_shifts: Decimal | None = None
    szm_code: str | None = None
    delivery_truck_code: str | None = None
    crew: tuple[CrewMember, ...] = ()
    drilling_executor: DrillingExecutor = "OWN"
    overhead_rate: Decimal | None = None
    target_margin_rate: Decimal | None = None
    vat_rate: Decimal | None = None

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ModelParameters":
        return cls(
            package_code=str(data.get("package_code", "")),
            site_code=str(data.get("site_code", "")),
            reference_revision_id=str(data.get("reference_revision_id", "")),
            unit_plan_volume_m3=decimal_value(data.get("unit_plan_volume_m3")),
            rig_code=_optional_code(data.get("rig_code")),
            rig_plan_shifts=_optional_number(data.get("rig_plan_shifts")),
            szm_code=_optional_code(data.get("szm_code")),
            delivery_truck_code=_optional_code(data.get("delivery_truck_code")),
            crew=tuple(CrewMember.from_dict(item) for item in data.get("crew", ())),
            drilling_executor=(
                "SUBCONTRACTOR"
                if str(data.get("drilling_executor", "OWN")).upper() == "SUBCONTRACTOR"
                else "OWN"
            ),
            overhead_rate=_optional_number(data.get("overhead_rate")),
            target_margin_rate=_optional_number(data.get("target_margin_rate")),
            vat_rate=_optional_number(data.get("vat_rate")),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "package_code": self.package_code,
            "site_code": self.site_code,
            "reference_revision_id": self.reference_revision_id,
            "unit_plan_volume_m3": str(self.unit_plan_volume_m3),
            "rig_code": self.rig_code,
            "rig_plan_shifts": str(self.rig_plan_shifts) if self.rig_plan_shifts is not None else None,
            "szm_code": self.szm_code,
            "delivery_truck_code": self.delivery_truck_code,
            "crew": [member.to_dict() for member in self.crew],
            "drilling_executor": self.drilling_executor,
            "overhead_rate": str(self.overhead_rate) if self.overhead_rate is not None else None,
            "target_margin_rate": (
                str(self.target_margin_rate) if self.target_margin_rate is not None else None
            ),
            "vat_rate": str(self.vat_rate) if self.vat_rate is not None else None,
        }


@dataclass(frozen=True)
class NaturalDrivers:
    """Натуральные величины блока с происхождением каждой из них."""

    values: dict[str, Decimal]
    lineage: dict[str, str]
    warnings: tuple[str, ...] = ()

    def get(self, key: str, default: Decimal = Decimal("0")) -> Decimal:
        return self.values.get(key, default)

    def to_dict(self) -> dict[str, Any]:
        return {
            "values": {key: str(value) for key, value in self.values.items()},
            "lineage": dict(self.lineage),
            "warnings": list(self.warnings),
        }


@dataclass(frozen=True)
class CapacityWarning:
    """Узкое место мощности: склад, станок или СЗМ."""

    resource_code: str
    resource_name: str
    required: Decimal
    available: Decimal | None
    unit: str
    message: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "resource_code": self.resource_code,
            "resource_name": self.resource_name,
            "required": float(self.required),
            "available": float(self.available) if self.available is not None else None,
            "unit": self.unit,
            "message": self.message,
        }


@dataclass(frozen=True)
class BlockEconomics:
    lines: tuple[CostLine, ...]
    layer_totals: dict[CostLayer, Decimal]
    price_per_m3: dict[str, Decimal]
    natural: NaturalDrivers
    capacity: tuple[CapacityWarning, ...] = ()
    warnings: tuple[str, ...] = ()
    markup: dict[str, Decimal] = field(default_factory=dict)
    block_volume_m3: Decimal = Decimal("0")
    model_version: str = MODEL_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "model_version": self.model_version,
            "block_volume_m3": float(self.block_volume_m3),
            "lines": [line.to_dict() for line in self.lines],
            "layer_totals": {layer.value: float(value) for layer, value in self.layer_totals.items()},
            "price_per_m3": {key: float(value) for key, value in self.price_per_m3.items()},
            "markup": {key: float(value) for key, value in self.markup.items()},
            "natural": self.natural.to_dict(),
            "capacity": [item.to_dict() for item in self.capacity],
            "warnings": list(self.warnings),
        }


@dataclass(frozen=True)
class OrganizationRates:
    """Ставки и надбавки организации: параметры, а не затраты."""

    income_tax_rate: Decimal = Decimal("0.13")
    social_contribution_rate: Decimal = Decimal("0.30")
    injury_insurance_rate: Decimal = Decimal("0.0042")
    vacation_reserve_rate: Decimal = Decimal("0.20")
    salary_basis: str = "GROSS"
    overhead_rate: Decimal = Decimal("0.10")
    target_margin_rate: Decimal = Decimal("0.10")
    vat_rate: Decimal = Decimal("0.20")
    per_diem_rub: Decimal = Decimal("0")
    lodging_rub: Decimal = Decimal("0")
    shift_hours: Decimal = Decimal("11")

    @classmethod
    def from_item(cls, item: ReferenceItem | None) -> "OrganizationRates":
        if item is None:
            return cls()
        payload = item.payload
        defaults = cls()
        return cls(
            income_tax_rate=decimal_value(payload.get("income_tax_rate"), defaults.income_tax_rate),
            social_contribution_rate=decimal_value(
                payload.get("social_contribution_rate"), defaults.social_contribution_rate
            ),
            injury_insurance_rate=decimal_value(
                payload.get("injury_insurance_rate"), defaults.injury_insurance_rate
            ),
            vacation_reserve_rate=decimal_value(
                payload.get("vacation_reserve_rate"), defaults.vacation_reserve_rate
            ),
            salary_basis=str(payload.get("salary_basis", defaults.salary_basis)).upper(),
            overhead_rate=decimal_value(payload.get("overhead_rate"), defaults.overhead_rate),
            target_margin_rate=decimal_value(
                payload.get("target_margin_rate"), defaults.target_margin_rate
            ),
            vat_rate=decimal_value(payload.get("vat_rate"), defaults.vat_rate),
            per_diem_rub=decimal_value(payload.get("per_diem_rub"), defaults.per_diem_rub),
            lodging_rub=decimal_value(payload.get("lodging_rub"), defaults.lodging_rub),
            shift_hours=decimal_value(payload.get("shift_hours"), defaults.shift_hours),
        )


class ModelContext:
    """Общее состояние прогона: справочники, параметры, драйверы, предупреждения.

    Контекст намеренно изменяем: модули домена дописывают в него натуральные
    величины и происхождение норм, а движок собирает из него результат.
    """

    def __init__(
        self,
        references: ReferenceSnapshot,
        params: ModelParameters,
        physical: Mapping[str, Any],
        *,
        passport_lineage: Mapping[str, str] | None = None,
        passport_name: str = "Блок",
    ) -> None:
        self.references = references
        self.params = params
        self.passport_name = passport_name
        self.values: dict[str, Decimal] = {
            str(key): decimal_value(value) for key, value in physical.items()
        }
        self.lineage: dict[str, str] = {
            str(key): str(value) for key, value in (passport_lineage or {}).items()
        }
        self.warnings: list[str] = []
        self.capacity: list[CapacityWarning] = []
        self.lines: list[CostLine] = []
        self.rates = OrganizationRates.from_item(self._first("organization_rates"))
        if self._first("organization_rates") is None:
            self.warn(
                "Не заполнен раздел «Ставки и надбавки организации»: "
                "взносы, ОХР, рентабельность и НДС взяты по умолчанию."
            )
        self.package = package_map(references).get(params.package_code)
        if self.package is None:
            self.warn(f"Пакет работ {params.package_code} не найден: операции не ограничены.")
        self.site = self.item("sites", params.site_code) if params.site_code else None
        if params.site_code and self.site is None:
            self.warn(f"Объект работ {params.site_code} не найден в справочнике карьеров.")

    # --- справочники -------------------------------------------------

    def items(self, section: str) -> tuple[ReferenceItem, ...]:
        return self.references.active_items(section)

    def item(self, section: str, code: str | None) -> ReferenceItem | None:
        if not code:
            return None
        return self.references.item(section, code)

    def _first(self, section: str) -> ReferenceItem | None:
        items = self.items(section)
        return items[0] if items else None

    # --- натуральные величины ---------------------------------------

    def value(self, key: str, default: Decimal = Decimal("0")) -> Decimal:
        return self.values.get(key, default)

    def set_value(self, key: str, value: Decimal, source: str) -> Decimal:
        self.values[key] = value
        self.lineage[key] = source
        return value

    def warn(self, message: str) -> None:
        if message not in self.warnings:
            self.warnings.append(message)

    def add_capacity(self, warning: CapacityWarning) -> None:
        self.capacity.append(warning)
        self.warn(warning.message)

    # --- строки затрат ----------------------------------------------

    def add_line(
        self,
        *,
        operation_code: str,
        cost_item_code: str,
        cost_item_name: str,
        layer: CostLayer,
        amount_rub: Decimal,
        formula: str,
        resource_code: str = "",
    ) -> None:
        self.lines.append(
            CostLine(
                month="",
                service_line_id=BLOCK_SERVICE_LINE_ID,
                service_line_name=self.passport_name,
                operation_code=operation_code,
                cost_item_code=cost_item_code,
                cost_item_name=cost_item_name,
                layer=layer,
                amount_rub=amount_rub,
                formula=formula,
                resource_code=resource_code,
            )
        )

    # --- пакет работ -------------------------------------------------

    def package_operations(self) -> tuple[str, ...]:
        if self.package is None:
            return ()
        return tuple(item.operation_code for item in self.package.operations)

    def has_operation(self, operation_code: str) -> bool:
        # Пакет не найден — считаем всё: иначе один неверный код пакета
        # обнулил бы весь расчёт молча.
        if self.package is None:
            return True
        return operation_code in self.package_operations()

    def natural(self) -> NaturalDrivers:
        return NaturalDrivers(
            values=dict(self.values),
            lineage=dict(self.lineage),
            warnings=tuple(self.warnings),
        )

    # --- разное ------------------------------------------------------

    @property
    def block_volume_m3(self) -> Decimal:
        return self.value("rock_volume_m3")

    def site_number(self, key: str, default: Decimal = Decimal("0")) -> Decimal:
        if self.site is None:
            return default
        return payload_number(self.site, key, default)

    def diesel_price_l(self) -> Decimal:
        """Цена литра ДТ: справочник объекта хранит цену тонны."""

        price_ton = self.site_number("diesel_price_ton_rub")
        if price_ton <= 0:
            return Decimal("0")
        # Плотность ДТ 0,85 т/м³ → 1 т ≈ 1176,5 л. Коэффициент — техническая
        # константа перевода, а не цена, поэтому живёт в коде.
        return price_ton / DIESEL_LITRES_PER_TON


def payload_number(
    item: ReferenceItem | None, key: str, default: Decimal = Decimal("0")
) -> Decimal:
    if item is None:
        return default
    value = item.payload.get(key)
    if value in (None, ""):
        return default
    return decimal_value(value, default)


def payload_text(item: ReferenceItem | None, key: str, default: str = "") -> str:
    if item is None:
        return default
    value = item.payload.get(key)
    return default if value in (None, "") else str(value)


def find_items(items: Iterable[ReferenceItem], key: str, value: str) -> list[ReferenceItem]:
    return [item for item in items if str(item.payload.get(key, "")) == value]


def _optional_code(value: Any) -> str | None:
    if value in (None, ""):
        return None
    return str(value)


def _optional_number(value: Any) -> Decimal | None:
    if value in (None, ""):
        return None
    return decimal_value(value)


__all__ = [
    "BLOCK_SERVICE_LINE_ID",
    "BlockEconomics",
    "CapacityWarning",
    "CrewMember",
    "MODEL_VERSION",
    "ModelContext",
    "ModelParameters",
    "NaturalDrivers",
    "OrganizationRates",
    "PackageDefinition",
    "find_items",
    "payload_number",
    "payload_text",
]
