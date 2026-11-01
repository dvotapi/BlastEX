"""Цена метра бурения для листа «Расчёт» (TASK-010, PR 3).

Лист «Расчёт» работает с живой геометрией блока, а не с сохранённым паспортом,
поэтому модель блока запускается на синтетическом снимке из одного драйвера —
погонажа бурения; всё остальное (станок, порода, объект, экипаж, режим ФОТ,
надбавки) берётся из параметров активного черновика сметы. Цена метра —
одна и та же в режимах «Ставки» и «Методика ФОТ»:

    price_m = Σ строк операции бурения / drilling_m × (1 + ОХР) × (1 + рентабельность)

В сумму входят строки самой модели бурения (оснастка, ДТ, запчасти,
амортизация и страховка станка, ТО), ФОТ экипажа бурения и строки правил
затрат и услуг этой операции. Взносы и суточные экипажа лежат отдельными
строками без операции и в цену метра не входят — как и в цене метра для доли
в марже (`block_margin.margin`).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from cost.model.drilling import DRILLING_OPERATION
from cost.model.engine import compute_block_economics
from cost.model.inputs import ModelParameters, payload_number, payload_text
from cost.v2.models import ReferenceSnapshot

ZERO = Decimal("0")
ONE = Decimal("1")


# Снимок листа несёт один драйвер, поэтому модель жалуется на отсутствие
# остальных (ВВ, НСИ, объём): для цены метра это шум, а не предупреждение.
_SYNTHETIC_NOISE = ("в натуральных величинах блока", "Объём блока равен нулю")


@dataclass(frozen=True)
class DrillingPriceSource:
    """Откуда лист берёт цену метра: параметры черновика и справочники ревизии."""

    params: ModelParameters
    references: ReferenceSnapshot


@dataclass(frozen=True)
class DrillingPrice:
    price_rub_per_m: Decimal
    cost_rub_per_m: Decimal
    overhead_rate: Decimal
    margin_rate: Decimal
    drilling_m: Decimal
    payroll_source: str
    warnings: tuple[str, ...] = ()


def compute(
    params: ModelParameters,
    references: ReferenceSnapshot,
    *,
    drilling_m: Decimal,
    as_of: date | None = None,
) -> DrillingPrice:
    """Цена метра бурения по параметрам черновика; нет метров — нулевая цена с предупреждением."""

    if drilling_m <= 0:
        return DrillingPrice(
            ZERO,
            ZERO,
            ZERO,
            ZERO,
            drilling_m,
            params.payroll_source,
            ("Метров бурения нет: цена метра не считается.",),
        )
    economics = compute_block_economics(
        {
            "physical": {"drilling_m": drilling_m},
            "lineage": {"drilling_m": "лист «Расчёт»: погонаж бурения блока"},
        },
        params,
        references,
        passport_name="Лист «Расчёт»",
        as_of=as_of,
    )
    warnings = tuple(
        message for message in economics.warnings if not any(part in message for part in _SYNTHETIC_NOISE)
    )
    # Нет нормы бурения (нет условия или скорости) — смен станка нет, и от цены
    # остался бы один ФОТ экипажа: это не цена метра, а обманчивая часть.
    if params.drilling_executor == "OWN" and economics.natural.values.get("rig_shifts", ZERO) <= 0:
        return DrillingPrice(ZERO, ZERO, ZERO, ZERO, drilling_m, params.payroll_source, warnings)
    total = sum(
        (line.amount_rub for line in economics.lines if line.operation_code == DRILLING_OPERATION),
        ZERO,
    )
    overhead_rate = economics.markup.get("overhead_rate", ZERO)
    margin_rate = economics.markup.get("target_margin_rate", ZERO)
    cost_per_m = total / drilling_m
    return DrillingPrice(
        price_rub_per_m=cost_per_m * (ONE + overhead_rate) * (ONE + margin_rate),
        cost_rub_per_m=cost_per_m,
        overhead_rate=overhead_rate,
        margin_rate=margin_rate,
        drilling_m=drilling_m,
        payroll_source=params.payroll_source,
        warnings=warnings,
    )


def default_source(
    references: ReferenceSnapshot,
    *,
    site_name: str | None = None,
    package_code: str = "DRILL_AND_BLAST",
) -> DrillingPriceSource | None:
    """Параметры «как у нового черновика сметы» для расчётов без черновика.

    «Проектирование» (смета проекта, сценарии, рекомендации, оптимизация) считает
    смету по геометрии без вкладки «Экономика». Цена метра там — по первому
    буровому станку справочника, шаблону экипажа пакета, ставкам организации
    и объекту `site_name` (иначе первому по списку), как в `/model-defaults`.
    Нет бурового станка в справочнике — None: цены нет, и это видно в `notes`.
    """

    rigs = [
        item
        for item in references.active_items("equipment_types")
        if payload_text(item, "kind") == "DRILL_RIG"
    ]
    if not rigs:
        return None
    rig = rigs[0]
    sites = references.active_items("sites")
    site = next((item for item in sites if item.name == site_name), None) if site_name else None
    site = site or (sites[0] if sites else None)
    rates = references.active_items("organization_rates")
    rate = rates[0] if rates else None
    crew = [
        {
            "position_code": str(member.get("position_code", "")),
            "headcount": str(member.get("headcount", "1")),
            "shifts_per_block": None,
        }
        for template in references.active_items("crew_templates")
        if payload_text(template, "package_code") == package_code
        for member in template.payload.get("members", [])
    ]
    params = ModelParameters.from_dict(
        {
            "package_code": package_code,
            "site_code": site.code if site is not None else "",
            "reference_revision_id": "",
            "unit_plan_volume_m3": "0",
            "rig_code": rig.code,
            "rig_plan_shifts": payload_number(rig, "norm_shifts_per_month", ZERO) or None,
            "crew": crew,
            "overhead_rate": payload_number(rate, "overhead_rate", Decimal("0.1")),
            "target_margin_rate": payload_number(rate, "target_margin_rate", Decimal("0.1")),
            "vat_rate": payload_number(rate, "vat_rate", Decimal("0.2")),
        }
    )
    return DrillingPriceSource(params=params, references=references)
