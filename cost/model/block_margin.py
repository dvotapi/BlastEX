"""Цена метра бурения и доля экипажа в марже блока (TASK-010, решения §2.1–§2.2).

`margin` зовётся движком, когда все строки на месте (после правил затрат,
услуг и юнита), до надбавок, и только при ФОТ экипажа по методике
(`block_payroll.compute` вернул `BlockPayroll`):

- price_m = Σ строк операции бурения / drilling_m × (1 + ОХР) ×
  (1 + рентабельность) — та же себестоимость метра, что у цены листа «Расчёт»
  (`drilling_price`): станок, ФОТ методики, персонал участка по ставкам с
  взносами и резервом, суточные, проживание, правила затрат и услуги; ставки —
  `markup.rates`, как у цены блока. Цена по себестоимости, а не договорная:
  ФОТ экипажа входит и в цену, и в долю, поэтому доля растёт с ФОТ медленнее,
  чем при договорной цене;
- var_m = Σ строк слоя VARIABLE операции бурения / drilling_m — без
  амортизации, страхования и ТО станка;
- доля — `payroll.margin_check` по сдельщикам экипажа на приведённых метрах,
  при плановом темпе и на потолке, приведённых метров на п.м. = M_блока /
  drilling_m (с договорным k), порог — `margin_share_warn` года.

`to_dict` собирает блок `payroll` результата экономики.
"""
from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
from typing import Any, Sequence

from cost.model import markup
from cost.model.block_payroll import BlockPayroll
from cost.model.drilling import DRILLING_OPERATION, DrillingNorms, operation_cost_rub
from cost.model.inputs import ModelContext
from cost.model.payroll import ONE, ZERO, MarginCheck, Scale, SharePoint, fn, margin_check, scale_series
from cost.v2.models import CostLayer, CostLine



def margin(
    context: ModelContext,
    norms: DrillingNorms | None,
    payroll: BlockPayroll | None,
    lines: Sequence[CostLine],
) -> MarginCheck | None:
    """Доля экипажа в марже метра бурения; None — блок на ставках или субподряд.

    Зовётся, когда все строки уже на месте (после правил затрат, услуг и
    юнита), и до надбавок: цена — все строки операции бурения, переменные
    метра — её строки слоя VARIABLE, без амортизации, страхования и ТО станка
    (они не переменные). Каждая строка входит в цену ровно один раз: строка,
    которая снижала бы маржу, не поднимая цены, завышала бы долю.
    Предупреждения проверки уходят в контекст.
    """

    # Без нормы бурения смен станка нет: в цене метра остался бы один ФОТ.
    if payroll is None or norms is None:
        return None
    drilling_m = context.value("drilling_m")
    price: Decimal | None = None
    variable: Decimal | None = None
    lineage: dict[str, str] = {}
    if drilling_m > 0:
        overhead_rate, margin_rate, _ = markup.rates(context)
        total_rub = operation_cost_rub(lines)
        variable_rub = sum(
            (
                line.amount_rub
                for line in lines
                if line.operation_code == DRILLING_OPERATION and line.layer is CostLayer.VARIABLE
            ),
            ZERO,
        )
        price = total_rub / drilling_m * (ONE + overhead_rate) * (ONE + margin_rate)
        variable = variable_rub / drilling_m
        lineage = {
            "price_rub_per_m": (
                f"{fn(total_rub)} ₽ строк бурения / {fn(drilling_m)} м × (1 + {fn(overhead_rate)}) × "
                f"(1 + {fn(margin_rate)}) — по себестоимости с надбавками, как цена метра листа «Расчёт»"
            ),
            "variable_rub_per_m": f"Σ переменных строк бурения {fn(variable_rub)} ₽ / {fn(drilling_m)} м",
        }
    meters_factor = payroll.normalized_meters / drilling_m if drilling_m > 0 else ONE
    check = margin_check(
        main_scale=payroll.main_scale,
        crew=payroll.crew,
        pace=payroll.pace.pace,
        meters_factor=meters_factor,
        price=price,
        variable=variable,
        threshold=payroll.threshold,
    )
    for message in check.warnings:
        context.warn(message)
    # Флаг доли — и в блоке ФОТ, и в предупреждениях модели (Т13): его должен
    # видеть сметчик и там, где блока ФОТ ещё не показывают.
    for flag in check.flags:
        context.warn(flag.message)
    if check.status == "NOT_APPLICABLE":
        context.warn("Доля в марже не проверена: в экипаже нет сдельщика со шкалой на приведённых метрах.")
    if price is None:
        context.warn("Метров бурения нет: доля экипажа в марже метра не считается.")
    return replace(check, lineage={**lineage, **check.lineage})


def _num(value: Decimal | None) -> float | None:
    return float(value) if value is not None else None


def _point(point: SharePoint | None) -> dict[str, float] | None:
    if point is None:
        return None
    return {"pace": float(point.pace), "crew_share": float(point.crew_share), "main_share": float(point.main_share)}


def _scale_dict(scale: Scale | None) -> dict[str, float | str | None] | None:
    """Шкала основной должности — те же поля и единицы, что `premium` превью ФОТ."""

    if scale is None:
        return None
    return {
        "scale_type": scale.scale_type,
        "gamma": _num(scale.gamma),
        "norm_per_shift": _num(scale.norm_per_shift),
        "rate_norm": _num(scale.rate_norm),
        "ceiling_per_shift": _num(scale.ceiling_per_shift),
        "rate_ceiling": _num(scale.rate_ceiling),
    }


def _series(scale: Scale | None, pace: Decimal) -> list[dict[str, float]]:
    """Ряды графика r(m) и p(m) от плановой точки блока; нет шкалы — пусто."""

    if scale is None:
        return []
    return [
        {"pace": float(point.pace), "rate": float(point.rate), "per_shift": float(point.per_shift)}
        for point in scale_series(scale, pace)
    ]


def to_dict(payroll: BlockPayroll, check: MarginCheck) -> dict[str, Any]:
    """Блок «ФОТ по методике» результата экономики: числа — float, как остальной `to_dict`."""

    pace = payroll.pace
    return {
        "pace": {
            "m_plan": float(pace.pace),
            "k_hardness": float(pace.k_hardness),
            "k_diameter": float(pace.k_diameter),
            "diameter_mm": _num(pace.diameter_mm),
            "condition_code": pace.condition_code,
            "condition_name": pace.condition_name,
        },
        "normalized_meters": float(payroll.normalized_meters),
        "effective_shifts": float(payroll.effective_shifts),
        "positions": [
            {
                "position_code": position.position_code,
                "position_name": position.position_name,
                "headcount": float(position.headcount),
                "c_var": float(position.c_var_rub_per_reduced_m),
                "fixed_rub": float(position.fixed_rub),
                "variable_rub": float(position.variable_rub),
                "amount_rub": float(position.amount_rub),
            }
            for position in payroll.positions
        ],
        "main_position_code": payroll.main_position_code,
        "scale": _scale_dict(payroll.main_scale),
        "series": _series(payroll.main_scale, pace.pace),
        "price_rub_per_m": _num(check.price),
        "variable_rub_per_m": _num(check.variable),
        "margin": {
            "status": check.status,
            "margin_rub_per_m": _num(check.margin),
            "plan": _point(check.plan),
            "ceiling": _point(check.ceiling),
            "threshold": float(check.threshold),
            "flags": [{"code": flag.code, "message": flag.message} for flag in check.flags],
            "lineage": dict(check.lineage),
        },
        "lineage": dict(payroll.lineage),
    }
