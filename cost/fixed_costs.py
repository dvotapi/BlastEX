"""
Постоянные расходы блока 2 сметы БВР (сценарий «БВР сухие», Excel S-колонка).

Суммы задаются на блок; удельная стоимость = сумма / объём блока.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

FixedCostSection = str  # "2.1" … "2.6"

SECTION_TITLES: dict[FixedCostSection, str] = {
    "2.1": "Хранение, производство и доставка ВМ и СИ",
    "2.2": "Суточные, вахтовые, проживание",
    "2.3": "Фонд оплаты труда",
    "2.4": "ГСМ на бурение",
    "2.5": "Амортизация",
    "2.6": "Общепроизводственные затраты",
}

SECTION_ORDER: tuple[FixedCostSection, ...] = ("2.1", "2.2", "2.3", "2.4", "2.5", "2.6")


@dataclass
class FixedCostItem:
    id: str
    section: FixedCostSection
    name: str
    amount_rub: float
    note: str = ""
    enabled: bool = True


@dataclass
class FixedCostLine:
    section: FixedCostSection
    section_title: str
    name: str
    amount: float


@dataclass
class FixedCostsResult:
    lines: list[FixedCostLine]
    section_totals: dict[FixedCostSection, float]
    total_amount: float
    block_volume_m3: float

    @property
    def total_per_m3(self) -> float:
        if self.block_volume_m3 <= 0:
            return 0.0
        return self.total_amount / self.block_volume_m3


DEFAULT_FIXED_COSTS: list[FixedCostItem] = [
    FixedCostItem("fc_21_storage", "2.1", "Стоимость хранения", 45_000.0),
    FixedCostItem("fc_21_delivery", "2.1", "Доставка, разгрузка ВМ", 6_000.0),
    FixedCostItem("fc_22_daily", "2.2", "Суточные (чел. × 1000 руб × дней)", 5_000.0),
    FixedCostItem(
        "fc_22_shift",
        "2.2",
        "Вахтовые (чел. × 1500 руб × дней)",
        0.0,
        note="не применяется для АСП",
        enabled=False,
    ),
    FixedCostItem(
        "fc_22_lodging",
        "2.2",
        "Проживание (чел. × 1000 руб × дней)",
        0.0,
        note="не применяется для АСП",
        enabled=False,
    ),
    FixedCostItem("fc_23_master", "2.3", "Руководитель взрывных работ (мастер БВР)", 27_647.06),
    FixedCostItem("fc_23_blasters", "2.3", "Взрывники", 43_529.41),
    FixedCostItem(
        "fc_23_miner",
        "2.3",
        "Горнорабочий",
        0.0,
        note="не применяется для БВР сухие",
        enabled=False,
    ),
    FixedCostItem("fc_23_driver_szm", "2.3", "Водитель СЗМ", 23_724.46),
    FixedCostItem("fc_23_driver_del", "2.3", "Водитель доставщика", 28_430.34),
    FixedCostItem("fc_23_accident", "2.3", "Отчисления от несчастного случая (0,42%)", 517.99),
    FixedCostItem("fc_23_social", "2.3", "Отчисления в фонды социального страхования (30%)", 36_999.38),
    FixedCostItem("fc_23_vacation", "2.3", "Резерв отпусков", 32_169.73),
    FixedCostItem("fc_24_szm", "2.4", "ДТ СЗМ: пробег до карьера + моточасы", 9_180.0),
    FixedCostItem("fc_24_tractor", "2.4", "ДТ тягач: пробег до карьера + моточасы", 9_180.0),
    FixedCostItem("fc_24_luidor", "2.4", "ДТ Луидор: пробег + моточасы", 3_060.0),
    FixedCostItem("fc_24_car", "2.4", "ДТ для проезда на карьер на легковом а/м", 3_060.0),
    FixedCostItem(
        "fc_25_gaz",
        "2.5",
        "А/м перевозки опасных грузов ГАЗ 5796М1",
        9_968.64,
    ),
    FixedCostItem("fc_25_szm", "2.5", "СЗМ TDR.PR-12 на базе КАМАЗ", 18_852.14),
    FixedCostItem("fc_25_base", "2.5", "База и вспомогательное", 15_539.98),
    FixedCostItem("fc_25_kmu", "2.5", "Седельный тягач с КМУ УСТ 54531U", 15_428.20),
    FixedCostItem("fc_26_toir", "2.6", "ТОиР СЗМ, доставщика", 15_000.0),
    FixedCostItem("fc_26_osago", "2.6", "ОСАГО (СВМ, СЗМ)", 500.0),
    FixedCostItem("fc_26_base", "2.6", "Содержание базы", 4_000.0),
    FixedCostItem("fc_26_spares", "2.6", "Запасные части и расходные материалы", 55_000.0),
    FixedCostItem("fc_26_ppe", "2.6", "Спецодежда и СИЗ", 3_000.0),
    FixedCostItem("fc_26_inspection", "2.6", "Проверка СЗМ и медосмотр водителей", 200.0),
]


def fixed_costs_to_records(items: list[FixedCostItem]) -> list[dict]:
    return [asdict(item) for item in items]


def fixed_costs_from_records(records: list[dict]) -> list[FixedCostItem]:
    out: list[FixedCostItem] = []
    for row in records:
        section = str(row.get("section", "2.1"))
        if section not in SECTION_TITLES:
            continue
        out.append(
            FixedCostItem(
                id=str(row.get("id", "")),
                section=section,
                name=str(row.get("name", "")),
                amount_rub=float(row.get("amount_rub", 0) or 0),
                note=str(row.get("note", "")),
                enabled=bool(row.get("enabled", True)),
            )
        )
    return out


def calculate_fixed_costs(
    *,
    block_volume_m3: float,
    items: list[FixedCostItem],
) -> FixedCostsResult:
    lines: list[FixedCostLine] = []
    section_totals: dict[FixedCostSection, float] = {s: 0.0 for s in SECTION_ORDER}

    for item in items:
        if not item.enabled or item.amount_rub <= 0:
            continue
        amount = item.amount_rub
        lines.append(
            FixedCostLine(
                section=item.section,
                section_title=SECTION_TITLES[item.section],
                name=item.name,
                amount=amount,
            )
        )
        section_totals[item.section] += amount

    total = sum(line.amount for line in lines)
    return FixedCostsResult(
        lines=lines,
        section_totals=section_totals,
        total_amount=total,
        block_volume_m3=block_volume_m3,
    )


def section_summary_rows(result: FixedCostsResult) -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    for section in SECTION_ORDER:
        amount = result.section_totals.get(section, 0.0)
        if amount <= 0:
            continue
        per_m3 = amount / result.block_volume_m3 if result.block_volume_m3 > 0 else 0.0
        title = SECTION_TITLES[section]
        rows.append((f"{section} — {title}", f"{amount:,.0f} руб ({per_m3:.2f} руб/м³)"))
    rows.append(("Итого постоянные, руб", f"{result.total_amount:,.0f}"))
    return rows
