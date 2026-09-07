"""Стоимость ВМ и средств инициирования по выбранной номенклатуре.

Количества уже посчитал технический паспорт: масса заряда, скважины, НСИ,
боевики. Вкладка выбирает только наименование, а цену модель берёт из
справочника «Стоимость материалов». Норм расхода здесь нет и быть не должно —
дублировать технический расчёт в справочнике значит завести второй источник
истины.

Правила затрат с теми же драйверами — прежний путь начисления ВМ; он остаётся
запасным: пока номенклатура не выбрана или у неё нет цены, статью считает
правило, и модель об этом говорит, а не молчит.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from cost.model.inputs import ModelContext, payload_number, payload_text
from cost.model.prices import price_lookup
from cost.v2.models import CostLayer, ReferenceItem
from cost.v2.prices import effective_price


@dataclass(frozen=True)
class Role:
    """Роль номенклатуры в смете и её место в расчёте.

    Связь роли с драйвером и операциями — способ считать смету, а не
    настройка: боевики всегда идут в монтаж боевиков, поверхностные НСИ —
    в сеть инициирования. Операций несколько, потому что пакеты различаются:
    в контурном взрывании боевики и НСИ ставят при монтаже гирлянд.
    """

    code: str
    # Подпись для предупреждений: «основное ВВ», «скважинное НСИ».
    label: str
    driver: str
    # Драйверы правил затрат, которые роль замещает: правило по любому из них
    # посчитало бы ту же позицию второй раз.
    covered_drivers: frozenset[str]
    # Операции пакета, принимающие строку; берётся первая, что есть в пакете.
    operations: tuple[str, ...]
    cost_item_code: str
    unit: str
    # Паспорт считает позицию штуками, а справочник хранит цену килограмма.
    priced_per_kg: bool = False


ROLES: tuple[Role, ...] = (
    Role(
        "EXPLOSIVE",
        "основное ВВ",
        "explosive_kg",
        frozenset({"explosive_kg", "bulk_kg", "cartridge_kg"}),
        ("EVV_MANUFACTURE_ON_SITE", "GARLAND_CHARGING", "MANUAL_CHARGING", "BULK_CHARGING_SZM"),
        "MATERIAL_EXPLOSIVE",
        "кг",
    ),
    Role(
        "BOOSTER",
        "промежуточный детонатор",
        "intermediate_detonators",
        frozenset({"intermediate_detonators", "boosters"}),
        ("PRIMER_ASSEMBLY", "GARLAND_CHARGING"),
        "MATERIAL_BOOSTER",
        "кг",
        priced_per_kg=True,
    ),
    Role(
        "NSI_DOWNHOLE",
        "скважинное НСИ",
        "downhole_nsi",
        frozenset({"downhole_nsi"}),
        ("PRIMER_ASSEMBLY", "GARLAND_CHARGING"),
        "MATERIAL_NSI_DOWNHOLE",
        "шт",
    ),
    Role(
        "NSI_SURFACE",
        "поверхностное НСИ",
        "surface_nsi",
        frozenset({"surface_nsi"}),
        ("INITIATION_NETWORK", "GARLAND_CHARGING"),
        "MATERIAL_NSI_SURFACE",
        "шт",
    ),
    Role(
        "NSI_START",
        "стартовое устройство",
        "start_nsi",
        frozenset({"start_nsi"}),
        ("INITIATION_NETWORK", "GARLAND_CHARGING"),
        "MATERIAL_NSI_START",
        "шт",
    ),
    Role(
        "DETONATOR_ELECTRIC",
        "электродетонатор",
        "electric_detonators",
        frozenset({"electric_detonators"}),
        ("BLAST_EXECUTION",),
        "MATERIAL_DETONATOR",
        "шт",
    ),
)

ROLE_BY_CODE: dict[str, Role] = {role.code: role for role in ROLES}

# Подписи для сообщения о чужой роли: сметчик читает «скважинное НСИ», а не
# NSI_DOWNHOLE. `OTHER` и буровой инструмент ролями выбора не являются.
_ROLE_LABELS: dict[str, str] = {
    **{role.code: role.label for role in ROLES},
    "DRILL_TOOL": "буровой инструмент",
    "OTHER": "роль не задана",
}


@dataclass(frozen=True)
class Gap:
    """Роль, которую не удалось начислить, и что сказать сметчику.

    Текст зависит от того, начислило ли статью правило затрат: «не оценено в
    деньгах» — когда статьи нет вовсе, «посчитано по правилу» — когда её
    закрыл прежний механизм. Пустой текст означает «молчать».
    """

    role: Role
    when_uncharged: str
    when_rule_charged: str = ""


@dataclass
class MaterialsOutcome:
    # Драйвер, замещённый начисленной ролью хоть на какой-то операции: нужен
    # только для текста предупреждения («посчитано по правилу» вместо «не
    # оценено»), а не для блокировки — один и тот же драйвер (масса ВВ)
    # может относиться к разным статьям на разных операциях (сама стоимость
    # ВВ и, например, комплектация склада), и блокировать нужно только ту
    # статью, что действительно совпадает.
    charged_drivers: set[str] = field(default_factory=set)
    # (операция, драйвер) начисленной роли: правило затрат с той же парой
    # пропускается — это и есть повторный счёт той же статьи. Правило с тем
    # же драйвером, но другой операцией — отдельная статья, его блокировать
    # нельзя.
    charged_operation_drivers: set[tuple[str, str]] = field(default_factory=set)
    # Статьи начисленных ролей: правило, считающее ту же статью на другой
    # операции пакета, — это та же позиция, посчитанная второй раз.
    charged_cost_items: set[str] = field(default_factory=set)
    gaps: list[Gap] = field(default_factory=list)


def compute(context: ModelContext) -> MaterialsOutcome:
    # Электродетонаторов технический расчёт не считает: их число задаёт сметчик,
    # поэтому драйвер появляется здесь, а не в адаптере паспорта.
    context.set_value(
        "electric_detonators",
        context.params.electric_detonators_qty,
        "количество задано на вкладке",
    )
    outcome = MaterialsOutcome()
    for role in ROLES:
        _role_line(context, role, outcome)
    return outcome


def report_gaps(
    context: ModelContext, outcome: MaterialsOutcome, rule_drivers: set[str]
) -> None:
    """Предупреждения о неначисленных ролях — после прохода правил затрат."""

    for gap in outcome.gaps:
        charged_by_rule = bool(gap.role.covered_drivers & rule_drivers)
        message = gap.when_rule_charged if charged_by_rule else gap.when_uncharged
        if message:
            context.warn(message)


def operation_for(context: ModelContext, role: Role) -> str | None:
    """Операция пакета, принимающая строку роли; None — заряжания в пакете нет."""

    return next((code for code in role.operations if context.has_operation(code)), None)


def _role_line(context: ModelContext, role: Role, outcome: MaterialsOutcome) -> None:
    operation_code = operation_for(context, role)
    if operation_code is None:
        # Пакет без заряжания (бурение, продажа со склада): ВВ не наше.
        return
    driver_value = context.value(role.driver)
    if driver_value <= 0:
        # Позиции в блоке нет — нет ни строки, ни предупреждения: пустое место
        # в смете не повод пугать сметчика.
        return

    code = context.params.nomenclature.get(role.code, "")
    if not code:
        outcome.gaps.append(
            Gap(role, f"Не выбрано: {role.label} — позиция не оценена в деньгах.")
        )
        return
    material = context.item("materials", code)
    if material is None:
        outcome.gaps.append(
            Gap(
                role,
                f"Номенклатура {code} не найдена в справочнике материалов: "
                f"{role.label} не оценено в деньгах.",
                f"Номенклатура {code} не найдена в справочнике материалов: "
                f"{role.label} посчитано по правилу затрат.",
            )
        )
        return
    # Роль позиции в справочнике задаёт единицу цены: НСИ, выбранное как
    # основное ВВ, умножило бы массу заряда на цену за штуку. Выбор мог
    # устареть после правки справочника или прийти запросом мимо вкладки.
    material_role = payload_text(material, "nomenclature_role", "OTHER")
    if material_role != role.code:
        outcome.gaps.append(
            Gap(
                role,
                f"У номенклатуры «{material.name}» роль в смете — "
                f"{_ROLE_LABELS.get(material_role, material_role)}, а выбрана она как "
                f"{role.label}: строка не начислена.",
                f"У номенклатуры «{material.name}» роль в смете — "
                f"{_ROLE_LABELS.get(material_role, material_role)}, а выбрана она как "
                f"{role.label}: {role.label} посчитано по правилу затрат.",
            )
        )
        return

    quantity, quantity_formula = _quantity(role, material, driver_value)
    if quantity is None:
        outcome.gaps.append(
            Gap(
                role,
                f"У номенклатуры «{material.name}» не задана масса единицы: "
                f"{role.label} не оценено в деньгах.",
                f"У номенклатуры «{material.name}» не задана масса единицы: "
                f"{role.label} посчитано по правилу затрат.",
            )
        )
        return

    lookup = price_lookup(context, code)
    if lookup.chosen is None:
        reason = (
            "срок действия всех цен истёк или ещё не наступил"
            if lookup.found
            else "нет цены в разделе «Стоимость материалов»"
        )
        outcome.gaps.append(
            Gap(
                role,
                f"Для номенклатуры «{material.name}» {reason}: "
                f"{role.label} не оценено в деньгах.",
                f"Для номенклатуры «{material.name}» {reason}: "
                f"{role.label} посчитано по правилу затрат.",
            )
        )
        return
    if len(lookup.duplicates) > 1:
        context.warn(
            f"Для номенклатуры «{material.name}» на одну дату задано несколько цен "
            f"({', '.join(item.code for item in lookup.duplicates)}): взята {lookup.chosen.code}."
        )

    price = effective_price(lookup)
    outcome.charged_drivers |= role.covered_drivers
    outcome.charged_operation_drivers |= {
        (operation_code, driver) for driver in role.covered_drivers
    }
    outcome.charged_cost_items.add(role.cost_item_code)
    context.add_line(
        operation_code=operation_code,
        cost_item_code=role.cost_item_code,
        cost_item_name=material.name,
        layer=CostLayer.VARIABLE,
        amount_rub=quantity * price,
        formula=f"{quantity_formula} × {price} ₽/{role.unit} ({lookup.source})",
        resource_code=code,
    )


def quantity_in_price_units(
    role: Role, material: ReferenceItem, driver_value: Decimal
) -> tuple[Decimal | None, str]:
    """Количество в единицах цены и его происхождение.

    None — штуки нельзя перевести в килограммы: у позиции нет массы единицы.
    Функция общая для модели и подсказки на вкладке, чтобы подпись под
    выбором и строка сметы называли одно и то же число.
    """

    if not role.priced_per_kg:
        return driver_value, f"{driver_value} {role.unit}"
    mass_kg = payload_number(material, "mass_kg")
    if mass_kg <= 0:
        return None, ""
    return driver_value * mass_kg, f"{driver_value} шт × {mass_kg} кг"


_quantity = quantity_in_price_units


__all__ = [
    "Gap",
    "MaterialsOutcome",
    "ROLES",
    "ROLE_BY_CODE",
    "Role",
    "compute",
    "operation_for",
    "quantity_in_price_units",
    "report_gaps",
]
