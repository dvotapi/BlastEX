"""
Расчёт стоимости бурения.

Лист Excel «Расчет стоимости бурения»:
  D37 — прямые расходы на 1 п.м.
  D40 — себестоимость на 1 п.м.
  D41 — цена на 1 п.м. (себестоимость × 1.2)

Блок 1.2 главной сметы: сумма = погonaж × D41.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from cost.drilling_data import (
    DEFAULT_DIESEL_PRICE_TON_RUB,
    DEFAULT_OBJECT_NAME,
    DEFAULT_RIG_NAME,
    SHIFT_HOURS,
    DrillRig,
    WorkObject,
    find_object,
    find_rig,
)
from cost.models import BlockGeometry

# Эталон Excel: JK 830-3, объект Теплогорский карьер, объём ≈ 2343.7 п.м.
DEFAULT_DRILLING_VOLUME_M = 2343.688167787891
DEFAULT_DRILLING_PRICE_PER_M = 1008.6731471622842


@dataclass
class DrillingUnitCostInput:
    """Входные данные калькулятора «Расчет стоимости бурения»."""

    volume_m: float = DEFAULT_DRILLING_VOLUME_M
    crown_mm: float = 152.0
    rig_name: str = DEFAULT_RIG_NAME
    tech_speed_m_h: float = 12.0
    nonproductive_h_per_shift: float = 1.0

    crown_m_per_piece: float = 700.0
    crown_price_rub: float = 25_000.0
    ppu_m_per_piece: float = 7_000.0
    ppu_price_rub: float = 100_000.0
    rig_tools_m_per_set: float = 15_000.0
    rig_tools_set_price_rub: float = 155_000.0  # 60000 + 70000 + 25000
    casing_m_per_drill_m: float = 0.03
    casing_price_rub_per_m: float = 450.0

    shifts_toir: float = 2.0
    shifts_cleaning: float = 1.0

    spares_rub_per_m: float = 30.0
    consumables_rub_per_m: float = 10.0
    fot_rub_per_m: float = 150.0  # до НДФЛ, как в Excel C25/C3*0.85

    object_name: str = DEFAULT_OBJECT_NAME
    mobilization_km: float | None = None
    diesel_price_ton_rub: float | None = None
    mobilization_rub_per_km: float = 450.0
    mobilization_divisor: float = 6.0

    line_release_rub_per_shift: float = 200.0  # 2 × 100
    include_med_exams: bool = True

    overhead_production_rub: float = 100_000.0
    overhead_admin_rub: float = 100_000.0
    profit_factor: float = 1.2


@dataclass
class DrillingCostLine:
    section: str
    name: str
    quantity: float | None
    unit: str
    total_rub: float | None
    price_per_m: float
    note: str = ""


@dataclass
class DrillingUnitCostResult:
    input: DrillingUnitCostInput
    commercial_speed_m_per_shift: float
    fuel_l_per_h: float
    fuel_l_per_m: float
    depreciation_per_shift_rub: float
    shifts_drilling: float
    shifts_total: float
    lines: list[DrillingCostLine] = field(default_factory=list)
    direct_cost_per_m: float = 0.0
    overhead_production_per_m: float = 0.0
    overhead_admin_per_m: float = 0.0
    cost_per_m: float = 0.0
    price_per_m: float = 0.0
    diesel_share: float = 0.0


@dataclass
class DrillingCostResult:
    total_holes: float
    hole_depth_m: float
    drilling_footage_m: float
    yield_per_meter_m3: float
    price_per_m: float
    amount: float


def _resolve_object_params(
    params: DrillingUnitCostInput,
    *,
    work_objects: Iterable[WorkObject] | None = None,
) -> tuple[float, float]:
    obj = find_object(params.object_name, work_objects)
    km = params.mobilization_km
    if km is None:
        km = obj.mobilization_km if obj else 300.0
    diesel = params.diesel_price_ton_rub
    if diesel is None:
        diesel = obj.diesel_price_ton_rub if obj and obj.diesel_price_ton_rub else DEFAULT_DIESEL_PRICE_TON_RUB
    return km, diesel


def calculate_drilling_unit_cost(
    params: DrillingUnitCostInput,
    *,
    work_objects: Iterable[WorkObject] | None = None,
    drill_rigs: Iterable[DrillRig] | None = None,
) -> DrillingUnitCostResult:
    """Калькулятор цены бурения за 1 п.м. по логике Excel."""
    volume = max(params.volume_m, 1e-9)
    rig = find_rig(params.rig_name, drill_rigs)
    mobilization_km, diesel_price_ton = _resolve_object_params(params, work_objects=work_objects)

    commercial_speed = params.tech_speed_m_h * (SHIFT_HOURS - params.nonproductive_h_per_shift)
    fuel_l_h = rig.fuel_l_per_h
    fuel_l_m = fuel_l_h / params.tech_speed_m_h if params.tech_speed_m_h > 0 else 0.0
    depreciation_shift = rig.depreciation_per_shift_rub

    shifts_drilling = volume / commercial_speed if commercial_speed > 0 else 0.0
    shifts_total = shifts_drilling + params.shifts_toir + params.shifts_cleaning

    crown_pm = (1.0 / params.crown_m_per_piece) * params.crown_price_rub if params.crown_m_per_piece > 0 else 0.0
    ppu_pm = (1.0 / params.ppu_m_per_piece) * params.ppu_price_rub if params.ppu_m_per_piece > 0 else 0.0
    rig_tools_pm = (
        (1.0 / params.rig_tools_m_per_set) * params.rig_tools_set_price_rub
        if params.rig_tools_m_per_set > 0
        else 0.0
    )
    casing_pm = params.casing_m_per_drill_m * params.casing_price_rub_per_m

    depreciation_pm = depreciation_shift * shifts_total / volume
    spares_pm = params.spares_rub_per_m
    consumables_pm = params.consumables_rub_per_m
    fot_contrib_pm = (params.fot_rub_per_m / 0.85) * 1.42

    diesel_total = volume * fuel_l_m * 0.85 * diesel_price_ton / 1000.0
    diesel_pm = diesel_total / volume

    mobilization_total = mobilization_km * params.mobilization_rub_per_km
    mobilization_pm = mobilization_total / (volume * params.mobilization_divisor)

    line_release_total = shifts_total * params.line_release_rub_per_shift
    line_release_pm = line_release_total / volume
    med_pm = line_release_pm if params.include_med_exams else 0.0

    overhead_prod_pm = params.overhead_production_rub / volume
    overhead_admin_pm = params.overhead_admin_rub / volume

    # Excel D37 = D14+D16+D19+D12+D23+D24+D26+D29+D32+D33 (без D18 и D31)
    direct_pm = (
        crown_pm
        + ppu_pm
        + casing_pm
        + depreciation_pm
        + spares_pm
        + consumables_pm
        + fot_contrib_pm
        + diesel_pm
        + line_release_pm
        + med_pm
    )
    cost_pm = direct_pm + overhead_prod_pm + overhead_admin_pm
    price_pm = cost_pm * params.profit_factor
    diesel_share = diesel_pm / price_pm if price_pm > 0 else 0.0

    lines = [
        DrillingCostLine("Инструмент", "Коронка", 1 / params.crown_m_per_piece, "шт/п.м.", None, crown_pm),
        DrillingCostLine("Инструмент", "ППУ", 1 / params.ppu_m_per_piece, "шт/п.м.", None, ppu_pm),
        DrillingCostLine(
            "Инструмент",
            "Оснастка (штанги, переводники, РК)",
            1 / params.rig_tools_m_per_set,
            "компл./п.м.",
            None,
            rig_tools_pm,
            "не входит в D37 Excel",
        ),
        DrillingCostLine(
            "Инструмент",
            "Обсадная труба",
            params.casing_m_per_drill_m,
            "м/п.м.",
            None,
            casing_pm,
        ),
        DrillingCostLine(
            "Амортизация",
            f"БУ {rig.name}",
            shifts_total,
            "смен",
            depreciation_shift * shifts_total,
            depreciation_pm,
            f"{depreciation_shift:,.0f} руб/смену",
        ),
        DrillingCostLine("Прямые", "Запасные части", volume, "п.м.", volume * spares_pm, spares_pm),
        DrillingCostLine(
            "Прямые",
            "Расходные материалы (ГСМ, фильтры)",
            volume,
            "п.м.",
            volume * consumables_pm,
            consumables_pm,
        ),
        DrillingCostLine(
            "ФОТ",
            "Основной персонал + отчисления",
            volume,
            "п.м.",
            volume * fot_contrib_pm,
            fot_contrib_pm,
            f"ставка {params.fot_rub_per_m:.0f} руб/п.м. до НДФЛ",
        ),
        DrillingCostLine(
            "ГСМ",
            "Дизельное топливо",
            volume * fuel_l_m,
            "л",
            diesel_total,
            diesel_pm,
            f"{fuel_l_h:.0f} л/ч, {diesel_price_ton:,.0f} руб/т",
        ),
        DrillingCostLine(
            "Мобилизация",
            "Перевозка БУ",
            mobilization_km,
            "км",
            mobilization_total,
            mobilization_pm,
            f"{params.mobilization_rub_per_km:.0f} руб/км; не входит в D37 Excel",
        ),
        DrillingCostLine(
            "Прочие",
            "Выпуск на линию (техосмотр)",
            shifts_total,
            "смен",
            line_release_total,
            line_release_pm,
        ),
    ]
    if params.include_med_exams:
        lines.append(
            DrillingCostLine(
                "Прочие",
                "Медосмотры",
                shifts_total,
                "смен",
                line_release_total,
                med_pm,
            )
        )
    lines.append(
        DrillingCostLine(
            "Прямые",
            "Итого прямые расходы (D37)",
            None,
            "руб/п.м.",
            volume * direct_pm,
            direct_pm,
        )
    )
    lines.extend(
        [
            DrillingCostLine(
                "Накладные",
                "Общепроизводственные",
                volume,
                "п.м.",
                params.overhead_production_rub,
                overhead_prod_pm,
            ),
            DrillingCostLine(
                "Накладные",
                "Административные",
                volume,
                "п.м.",
                params.overhead_admin_rub,
                overhead_admin_pm,
            ),
            DrillingCostLine("Итог", "Себестоимость", None, "руб/п.м.", volume * cost_pm, cost_pm),
            DrillingCostLine(
                "Итог",
                f"Цена (× {params.profit_factor:g})",
                None,
                "руб/п.м.",
                volume * price_pm,
                price_pm,
            ),
        ]
    )

    return DrillingUnitCostResult(
        input=params,
        commercial_speed_m_per_shift=commercial_speed,
        fuel_l_per_h=fuel_l_h,
        fuel_l_per_m=fuel_l_m,
        depreciation_per_shift_rub=depreciation_shift,
        shifts_drilling=shifts_drilling,
        shifts_total=shifts_total,
        lines=lines,
        direct_cost_per_m=direct_pm,
        overhead_production_per_m=overhead_prod_pm,
        overhead_admin_per_m=overhead_admin_pm,
        cost_per_m=cost_pm,
        price_per_m=price_pm,
        diesel_share=diesel_share,
    )


def default_drilling_unit_cost() -> DrillingUnitCostResult:
    return calculate_drilling_unit_cost(DrillingUnitCostInput())


def calculate_drilling_cost(
    *,
    block: BlockGeometry,
    hole_depth_m: float,
    price_per_m: float = DEFAULT_DRILLING_PRICE_PER_M,
) -> DrillingCostResult:
    """Стоимость бурения по потребности в п.м. из технического расчёта."""
    footage = block.drilling_footage_m
    yield_per_meter = block.block_volume_m3 / footage if footage > 0 else 0.0
    amount = footage * price_per_m

    return DrillingCostResult(
        total_holes=block.total_holes,
        hole_depth_m=hole_depth_m,
        drilling_footage_m=footage,
        yield_per_meter_m3=yield_per_meter,
        price_per_m=price_per_m,
        amount=amount,
    )


def drilling_table_rows(result: DrillingCostResult) -> list[tuple[str, str]]:
    return [
        ("Скважин, шт.", f"{result.total_holes:.1f}"),
        ("Глубина скважины, м", f"{result.hole_depth_m:.1f}"),
        ("Погonaж бурения, п.м.", f"{result.drilling_footage_m:.0f}"),
        ("Выход на 1 п.м., м³/п.м.", f"{result.yield_per_meter_m3:.3f}"),
        ("Цена бурения, руб/п.м.", f"{result.price_per_m:.2f}"),
        ("Сумма 1.2, руб", f"{result.amount:,.0f}"),
    ]


def unit_cost_summary_rows(result: DrillingUnitCostResult) -> list[tuple[str, str]]:
    p = result.input
    return [
        ("Объём бурения, п.м.", f"{p.volume_m:.1f}"),
        ("Диаметр коронки, мм", f"{p.crown_mm:.0f}"),
        ("Буровая установка", p.rig_name),
        ("Коммерческая скорость, м/смену", f"{result.commercial_speed_m_per_shift:.0f}"),
        ("Смен бурения", f"{result.shifts_drilling:.2f}"),
        ("Смен всего (с ТОиР и прочисткой)", f"{result.shifts_total:.2f}"),
        ("Расход ДТ, л/метр", f"{result.fuel_l_per_m:.3f}"),
        ("Прямые расходы, руб/п.м.", f"{result.direct_cost_per_m:.2f}"),
        ("Себестоимость, руб/п.м.", f"{result.cost_per_m:.2f}"),
        ("Цена, руб/п.м.", f"{result.price_per_m:.2f}"),
        ("Доля ДТ в цене, %", f"{result.diesel_share * 100:.1f}"),
    ]
