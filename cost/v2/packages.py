"""Элементарные операции и утверждённые шаблоны работ Cost V2."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from cost.v2.models import ReferenceItem, ReferenceSnapshot


@dataclass(frozen=True)
class OperationDefinition:
    code: str
    name: str
    driver: str
    resource_code: str = ""
    description: str = ""


@dataclass(frozen=True)
class PackageOperation:
    operation_code: str
    optional: bool = False


@dataclass(frozen=True)
class PackageDefinition:
    code: str
    name: str
    operations: tuple[PackageOperation, ...]
    description: str = ""


DEFAULT_OPERATIONS: tuple[OperationDefinition, ...] = (
    OperationDefinition("DRILL_DESIGN", "Проектирование бурения", "rock_volume_m3", "ENGINEERING_HOUR"),
    OperationDefinition("BLAST_DESIGN", "Проектирование взрывных работ", "rock_volume_m3", "ENGINEERING_HOUR"),
    OperationDefinition("SURVEY_STAKEOUT", "Вынос скважин в натуру", "stakeout_holes", "SURVEY_CAPACITY"),
    OperationDefinition("BLOCK_ACCEPTANCE", "Приёмка подготовленного блока", "holes", "ENGINEERING_HOUR"),
    OperationDefinition("PRODUCTION_DRILLING", "Основное бурение", "drill_hours", "DRILL_RIG_HOUR"),
    OperationDefinition("CONTOUR_DRILLING", "Контурное бурение", "contour_drill_hours", "CONTOUR_DRILL_RIG_HOUR"),
    OperationDefinition("COMPONENT_MANUFACTURE", "Изготовление компонентов ЭВВ", "explosive_kg", "COMPONENT_PLANT_KG"),
    OperationDefinition("COMPONENT_PURCHASE", "Закупка компонентов ЭВВ", "explosive_kg"),
    OperationDefinition("COMPONENT_DELIVERY", "Доставка компонентов ЭВВ", "component_tkm", "HAZMAT_TRANSPORT_TKM"),
    # The manufacturing cost is driven by kg, while the same SZM's time is
    # accounted once by BULK_CHARGING_SZM. Mapping kg directly to SZM_HOUR
    # would mix units and double-count capacity.
    OperationDefinition("EVV_MANUFACTURE_ON_SITE", "Изготовление ЭВВ на месте применения", "explosive_kg"),
    OperationDefinition("BULK_CHARGING_SZM", "Подача ВМ в скважину СЗМ", "szm_hours", "SZM_HOUR"),
    OperationDefinition("CHARGING_HOSE_ASSISTANCE", "Помощь горнорабочего с зарядным рукавом", "szm_hours", "MINER_HOUR"),
    OperationDefinition("WAREHOUSE_PICKING", "Комплектация ВМ на складе", "explosive_kg", "WAREHOUSE_KG"),
    OperationDefinition("VM_DELIVERY_SITE", "Доставка ВМ от склада до карьера", "vm_tkm", "HAZMAT_TRANSPORT_TKM"),
    OperationDefinition("VM_INTERWAREHOUSE_TRANSPORT", "Межскладская доставка ВМ", "vm_tkm", "HAZMAT_TRANSPORT_TKM"),
    OperationDefinition("PRIMER_ASSEMBLY", "Изготовление и монтаж боевиков", "holes", "BLAST_CREW_HOUR"),
    OperationDefinition("MANUAL_CHARGING", "Ручное заряжание", "explosive_kg", "BLAST_CREW_HOUR"),
    OperationDefinition("GARLAND_CHARGING", "Изготовление и монтаж гирляндовых зарядов", "contour_drilling_m", "BLAST_CREW_HOUR"),
    OperationDefinition("STEMMING", "Забойка", "holes", "BLAST_CREW_HOUR"),
    OperationDefinition("INITIATION_NETWORK", "Монтаж сети инициирования", "holes", "BLAST_CREW_HOUR"),
    OperationDefinition("BLAST_SAFETY_ZONE", "Организация опасной зоны", "blasts", "BLAST_CREW_HOUR"),
    OperationDefinition("BLAST_EXECUTION", "Производство взрыва", "blasts", "BLAST_CREW_HOUR"),
    OperationDefinition("POST_BLAST_DOCUMENTATION", "Исполнительная документация", "blasts", "ENGINEERING_HOUR"),
    OperationDefinition("MOBILIZATION", "Мобилизация", "mobilizations", "TRANSPORT_TRIP"),
    OperationDefinition("DEMOBILIZATION", "Демобилизация", "demobilizations", "TRANSPORT_TRIP"),
    OperationDefinition("OVERSIZE_BREAKING", "Разделка негабарита экскаватором с гидроклином", "excavator_hours", "OWN_EXCAVATOR_HOUR"),
)


def _ops(*codes: str, optional: Iterable[str] = ()) -> tuple[PackageOperation, ...]:
    optional_set = set(optional)
    return tuple(PackageOperation(code, code in optional_set) for code in codes)


DEFAULT_PACKAGES: tuple[PackageDefinition, ...] = (
    PackageDefinition(
        "VM_IN_HOLE",
        "Поставка ВМ франко-скважина",
        _ops(
            "COMPONENT_MANUFACTURE",
            "COMPONENT_PURCHASE",
            "COMPONENT_DELIVERY",
            "EVV_MANUFACTURE_ON_SITE",
            "BULK_CHARGING_SZM",
            "CHARGING_HOSE_ASSISTANCE",
            optional=("COMPONENT_MANUFACTURE", "COMPONENT_PURCHASE", "CHARGING_HOSE_ASSISTANCE"),
        ),
        "Граница услуги заканчивается после подачи ВМ в скважину; СИ, забойка и сеть исключены.",
    ),
    PackageDefinition(
        "BLASTING_NO_DRILLING",
        "Взрывные работы без бурения",
        _ops(
            "DRILL_DESIGN",
            "BLAST_DESIGN",
            "BLOCK_ACCEPTANCE",
            "EVV_MANUFACTURE_ON_SITE",
            "BULK_CHARGING_SZM",
            "PRIMER_ASSEMBLY",
            "MANUAL_CHARGING",
            "STEMMING",
            "INITIATION_NETWORK",
            "BLAST_SAFETY_ZONE",
            "BLAST_EXECUTION",
            "POST_BLAST_DOCUMENTATION",
            optional=("DRILL_DESIGN",),
        ),
    ),
    PackageDefinition(
        "DRILLING",
        "Буровые работы",
        _ops("DRILL_DESIGN", "SURVEY_STAKEOUT", "BLOCK_ACCEPTANCE", "MOBILIZATION", "PRODUCTION_DRILLING", "DEMOBILIZATION", optional=("DRILL_DESIGN",)),
    ),
    PackageDefinition(
        "DRILL_AND_BLAST",
        "Полный комплекс БВР",
        _ops(
            "DRILL_DESIGN",
            "BLAST_DESIGN",
            "SURVEY_STAKEOUT",
            "BLOCK_ACCEPTANCE",
            "MOBILIZATION",
            "PRODUCTION_DRILLING",
            "COMPONENT_MANUFACTURE",
            "COMPONENT_PURCHASE",
            "COMPONENT_DELIVERY",
            "EVV_MANUFACTURE_ON_SITE",
            "BULK_CHARGING_SZM",
            "WAREHOUSE_PICKING",
            "VM_DELIVERY_SITE",
            "PRIMER_ASSEMBLY",
            "MANUAL_CHARGING",
            "STEMMING",
            "INITIATION_NETWORK",
            "BLAST_SAFETY_ZONE",
            "BLAST_EXECUTION",
            "POST_BLAST_DOCUMENTATION",
            "OVERSIZE_BREAKING",
            "DEMOBILIZATION",
            optional=("COMPONENT_MANUFACTURE", "COMPONENT_PURCHASE", "OVERSIZE_BREAKING"),
        ),
    ),
    PackageDefinition(
        "VM_WAREHOUSE_SALE",
        "Продажа ВМ со склада",
        _ops("WAREHOUSE_PICKING", "VM_DELIVERY_SITE", optional=("VM_DELIVERY_SITE",)),
    ),
    PackageDefinition(
        "VM_WAREHOUSE_TRANSFER",
        "Межскладская доставка ВМ",
        _ops("WAREHOUSE_PICKING", "VM_INTERWAREHOUSE_TRANSPORT"),
    ),
    PackageDefinition(
        "CONTOUR_BLASTING",
        "Контурное взрывание",
        _ops("BLAST_DESIGN", "BLOCK_ACCEPTANCE", "GARLAND_CHARGING", "INITIATION_NETWORK", "BLAST_SAFETY_ZONE", "BLAST_EXECUTION", "POST_BLAST_DOCUMENTATION"),
    ),
    PackageDefinition(
        "CONTOUR_DRILLING",
        "Контурное бурение",
        _ops("DRILL_DESIGN", "SURVEY_STAKEOUT", "MOBILIZATION", "CONTOUR_DRILLING", "DEMOBILIZATION"),
    ),
    PackageDefinition(
        "CONTOUR_DRILL_AND_BLAST",
        "Полный комплекс контурных работ",
        _ops("DRILL_DESIGN", "BLAST_DESIGN", "SURVEY_STAKEOUT", "MOBILIZATION", "CONTOUR_DRILLING", "GARLAND_CHARGING", "INITIATION_NETWORK", "BLAST_SAFETY_ZONE", "BLAST_EXECUTION", "POST_BLAST_DOCUMENTATION", "DEMOBILIZATION"),
    ),
    PackageDefinition(
        "OVERSIZE_BREAKING",
        "Разделка негабарита",
        _ops("MOBILIZATION", "OVERSIZE_BREAKING", "DEMOBILIZATION"),
        "Экскаватор с гидроклином всегда относится к собственному ресурсному пулу.",
    ),
)


def operation_map(snapshot: ReferenceSnapshot | None = None) -> dict[str, OperationDefinition]:
    defaults = {item.code: item for item in DEFAULT_OPERATIONS}
    if snapshot is None:
        return defaults
    for item in snapshot.active_items("operations"):
        defaults[item.code] = OperationDefinition(
            code=item.code,
            name=item.name,
            driver=str(item.payload.get("driver", "billed_quantity")),
            resource_code=str(item.payload.get("resource_code", "")),
            description=str(item.payload.get("description", "")),
        )
    return defaults


def package_map(snapshot: ReferenceSnapshot | None = None) -> dict[str, PackageDefinition]:
    defaults = {item.code: item for item in DEFAULT_PACKAGES}
    if snapshot is None:
        return defaults
    for item in snapshot.active_items("work_packages"):
        operations: list[PackageOperation] = []
        for raw in item.payload.get("operations", []):
            if isinstance(raw, str):
                operations.append(PackageOperation(raw))
            else:
                operations.append(
                    PackageOperation(
                        operation_code=str(raw.get("operation_code", "")),
                        optional=bool(raw.get("optional", False)),
                    )
                )
        if operations:
            defaults[item.code] = PackageDefinition(
                code=item.code,
                name=item.name,
                operations=tuple(operations),
                description=str(item.payload.get("description", "")),
            )
    return defaults


def package_reference_items() -> tuple[ReferenceItem, ...]:
    return tuple(
        ReferenceItem(
            code=package.code,
            name=package.name,
            source="BlastEX Cost V2",
            payload={
                "description": package.description,
                "operations": [
                    {"operation_code": operation.operation_code, "optional": operation.optional}
                    for operation in package.operations
                ],
            },
        )
        for package in DEFAULT_PACKAGES
    )


def operation_reference_items() -> tuple[ReferenceItem, ...]:
    return tuple(
        ReferenceItem(
            code=operation.code,
            name=operation.name,
            source="BlastEX Cost V2",
            payload={
                "driver": operation.driver,
                "resource_code": operation.resource_code,
                "description": operation.description,
            },
        )
        for operation in DEFAULT_OPERATIONS
    )


def package_codes() -> tuple[str, ...]:
    return tuple(item.code for item in DEFAULT_PACKAGES)


def package_to_dict(package: PackageDefinition) -> dict[str, Any]:
    return {
        "code": package.code,
        "name": package.name,
        "description": package.description,
        "operations": [
            {"operation_code": item.operation_code, "optional": item.optional}
            for item in package.operations
        ],
    }
