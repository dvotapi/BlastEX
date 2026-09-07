"""Стоимость ВМ и средств инициирования по выбранной номенклатуре.

Количества уже посчитал технический паспорт: масса заряда, скважины, НСИ,
боевики. Вкладка выбирает только наименование, а цену модель берёт из
справочника «Стоимость материалов». Норм расхода здесь нет и быть не должно —
дублировать технический расчёт в справочнике значит завести второй источник
истины.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from cost.model.inputs import ModelContext, payload_number
from cost.model.prices import material_price, price_source
from cost.v2.models import CostLayer


@dataclass(frozen=True)
class Role:
    """Роль номенклатуры в смете и её место в расчёте.

    Связь роли с драйвером и операцией — способ считать смету, а не
    настройка: боевики всегда идут в монтаж боевиков, поверхностные НСИ —
    в сеть инициирования.
    """

    code: str
    driver: str
    operation_code: str
    cost_item_code: str
    unit: str
    missing_message: str
    # Паспорт считает позицию штуками, а справочник хранит цену килограмма.
    priced_per_kg: bool = False


ROLES: tuple[Role, ...] = (
    Role(
        "EXPLOSIVE",
        "explosive_kg",
        "EVV_MANUFACTURE_ON_SITE",
        "MATERIAL_EXPLOSIVE",
        "кг",
        "Не выбрано основное ВВ: масса заряда не оценена в деньгах.",
    ),
    Role(
        "BOOSTER",
        "intermediate_detonators",
        "PRIMER_ASSEMBLY",
        "MATERIAL_BOOSTER",
        "кг",
        "Не выбран промежуточный детонатор: боевики не оценены в деньгах.",
        priced_per_kg=True,
    ),
    Role(
        "NSI_DOWNHOLE",
        "downhole_nsi",
        "PRIMER_ASSEMBLY",
        "MATERIAL_NSI_DOWNHOLE",
        "шт",
        "Не выбрано скважинное НСИ: внутрискважинная сеть не оценена в деньгах.",
    ),
    Role(
        "NSI_SURFACE",
        "surface_nsi",
        "INITIATION_NETWORK",
        "MATERIAL_NSI_SURFACE",
        "шт",
        "Не выбрано поверхностное НСИ: поверхностная сеть не оценена в деньгах.",
    ),
    Role(
        "NSI_START",
        "start_nsi",
        "INITIATION_NETWORK",
        "MATERIAL_NSI_START",
        "шт",
        "Не выбрано стартовое устройство: запуск сети не оценён в деньгах.",
    ),
    Role(
        "DETONATOR_ELECTRIC",
        "electric_detonators",
        "BLAST_EXECUTION",
        "MATERIAL_DETONATOR",
        "шт",
        "Не выбран электродетонатор: количество задано, но наименования нет.",
    ),
)


def compute(context: ModelContext) -> None:
    # Электродетонаторов технический расчёт не считает: их число задаёт сметчик,
    # поэтому драйвер появляется здесь, а не в адаптере паспорта.
    context.set_value(
        "electric_detonators",
        context.params.electric_detonators_qty,
        "количество задано на вкладке",
    )
    for role in ROLES:
        _role_line(context, role)


def _role_line(context: ModelContext, role: Role) -> None:
    if not context.has_operation(role.operation_code):
        return
    driver_value = context.value(role.driver)
    if driver_value <= 0:
        # Позиции в блоке нет — нет ни строки, ни предупреждения: пустое место
        # в смете не повод пугать сметчика.
        return

    code = context.params.nomenclature.get(role.code, "")
    if not code:
        context.warn(role.missing_message)
        return
    material = context.item("materials", code)
    if material is None:
        context.warn(f"Номенклатура {code} не найдена в справочнике материалов.")
        return

    quantity, quantity_formula = _quantity(context, role, material, driver_value)
    if quantity is None:
        return

    price = material_price(context, code)
    if price <= 0:
        context.warn(
            f"Для номенклатуры «{material.name}» нет цены "
            "в разделе «Стоимость материалов»: строка не начислена."
        )
        return

    context.set_value(f"nomenclature.{role.code}", quantity, quantity_formula)
    context.add_line(
        operation_code=role.operation_code,
        cost_item_code=role.cost_item_code,
        cost_item_name=material.name,
        layer=CostLayer.VARIABLE,
        amount_rub=quantity * price,
        formula=(
            f"{quantity_formula} × {price} ₽/{role.unit} ({price_source(context, code)})"
        ),
        resource_code=code,
    )


def _quantity(
    context: ModelContext, role: Role, material, driver_value: Decimal
) -> tuple[Decimal | None, str]:
    """Количество в единицах цены и его происхождение для колонки «формула»."""

    if not role.priced_per_kg:
        return driver_value, f"{driver_value} {role.unit}"
    mass_kg = payload_number(material, "mass_kg")
    if mass_kg <= 0:
        context.warn(
            f"У номенклатуры «{material.name}» не задана масса единицы: "
            "штуки не переведены в килограммы, строка не начислена."
        )
        return None, ""
    return driver_value * mass_kg, f"{driver_value} шт × {mass_kg} кг"


__all__ = ["ROLES", "Role", "compute"]
