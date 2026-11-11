"""Расчёты проекта массового взрыва по форме ВМ.09.03 (TASK-018, версия `mass-blast-v2`).

В PR 1 — только расход ВМ по проекту (`explosives_consumption`):
технический расчёт, таблицу параметров и распорядок добавит PR 2.
Проект блока только читается. Запаса и кратности выписки нет: запас —
слой «наряд-путёвка» (PR 6), округление массы до 5 кг — печать таблицы.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable

from design.models import (
    BlastDesign,
    DownholeConnector,
    HoleLoad,
    Primer,
    SurfaceConnector,
    is_explosive_deck_kind,
)
from design.safety.holes import MaterialIndex, material_index, primer_items, primer_mass_kg

__all__ = ["MASS_BLAST_CALC_VERSION", "ConsumptionLine", "explosives_consumption"]

MASS_BLAST_CALC_VERSION = "mass-blast-v2"

# Поверхностные соединители, которые расходуются штуками. Электронные линии
# и шнур (`electronic`, `detonating_cord`) штучным расходом не считаются.
_PIECE_SURFACE_KINDS = {"surface_nsi": "НСИ поверхностное", "ds_relay": "Реле ДШ"}
STARTER_FALLBACK = "Стартовое устройство"


@dataclass(frozen=True)
class ConsumptionLine:
    """Строка расхода ВМ: что, сколько и откуда взялась марка."""

    kind: str               # explosive | primer | nsi_downhole | detonator_electronic | nsi_surface | starter
    name: str
    quantity: float
    unit: str               # «кг» | «шт»
    mass_kg: float | None = None
    material_code: str = ""
    delay_ms: float | None = None
    source: str = "DESIGN"  # DESIGN — марка из проекта, REFERENCE — подобрана по справочнику
    warning: str = ""       # код предупреждения, если марку подобрать не удалось
    message: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "name": self.name,
            "quantity": self.quantity,
            "unit": self.unit,
            "mass_kg": self.mass_kg,
            "material_code": self.material_code,
            "delay_ms": self.delay_ms,
            "source": self.source,
            "warning": self.warning,
            "message": self.message,
        }


def explosives_consumption(
    design: BlastDesign,
    materials: Iterable[Any] | None = None,
    *,
    starter_product: str = "",
) -> list[ConsumptionLine]:
    """Потребность в ВМ по проекту блока, без запаса и без округления.

    ВВ — сумма масс взрывчатых дек по марке; ПД — штуки и масса; НСИ
    скважинные — по числу ПД (решение владельца В6); поверхностные — по сети,
    группами «марка / замедление»; стартеры — по числу стартов сети, марка —
    поле проекта МВ `starter_product` (решение В7).
    """

    index = material_index(materials)
    enabled = {hole.id for hole in design.holes if hole.enabled}
    loads = [load for load in design.loads if load.hole_id in enabled]
    lines: list[ConsumptionLine] = []

    explosives: dict[str, float] = {}
    for load in loads:
        for deck in load.decks:
            if is_explosive_deck_kind(deck.kind) and deck.mass_kg > 0:
                key = deck.product or deck.explosive_key or design.explosive_key
                explosives[key] = explosives.get(key, 0.0) + float(deck.mass_kg)
    for product, mass in sorted(explosives.items()):
        material = index.find(product)
        lines.append(
            ConsumptionLine(
                "explosive", _name(material, product) or "ВВ", mass, "кг", mass,
                material_code=material["code"] if material else "",
            )
        )

    primers: dict[str, list[float | None]] = {}
    downhole: dict[tuple[str, float | None], int] = {}
    connectors: dict[str, list[DownholeConnector]] = {}
    for connector in design.network.downhole_connectors:
        connectors.setdefault(connector.hole_id, []).append(connector)
    for load in loads:
        items = primer_items(load)
        for position, primer in enumerate(items):
            primers.setdefault(primer.product, []).append(primer_mass_kg(primer, index))
            kind, product, delay = _downhole_connector(
                design, connectors.get(load.hole_id, []), load, primer, position, len(items)
            )
            downhole[(kind, product, delay)] = downhole.get((kind, product, delay), 0) + 1
    for product, masses in sorted(primers.items()):
        material = index.find(product)
        known = [mass for mass in masses if mass is not None]
        missing = len(masses) - len(known)
        lines.append(
            ConsumptionLine(
                "primer",
                _name(material, product) or "Промежуточный детонатор",
                float(len(masses)),
                "шт",
                sum(known),
                material_code=material["code"] if material else "",
                warning="primer_mass_unknown" if missing else "",
                message=f"Масса не задана у {missing} шт." if missing else "",
            )
        )
    ordered = sorted(downhole.items(), key=lambda item: (item[0][0], item[0][1], item[0][2] or 0))
    lines.extend(
        _merged(
            _nsi_line("nsi_downhole", "NSI_DOWNHOLE", "НСИ скважинное", product, delay, count, index)
            for (kind, product, delay), count in ordered
            if kind == "downhole_nsi"
        )
    )
    # Электронный детонатор — не НСИ: марку по замедлению среди скважинных НСИ
    # не подбираем, строка — с маркой из сети или подписью и предупреждением.
    lines.extend(
        _merged(
            _nsi_line("detonator_electronic", "", "Электронный детонатор", product, None, count, index)
            for (kind, product, delay), count in ordered
            if kind == "electronic"
        )
    )

    surface: dict[tuple[str, str, float], int] = {}
    # Как `timing._surface_edges`: сеть без объектов 2.0 читается по старым полям.
    surface_connectors = design.network.surface_connectors or [
        SurfaceConnector(id="", from_hole=item.from_hole, to_hole=item.to_hole, delay_ms=item.delay_ms, kind=item.kind)
        for item in design.network.connectors
    ]
    for connector in surface_connectors:
        if connector.kind not in _PIECE_SURFACE_KINDS:
            continue
        if connector.from_hole not in enabled or connector.to_hole not in enabled:
            continue
        key = (connector.kind, connector.product, float(connector.delay_ms))
        surface[key] = surface.get(key, 0) + 1
    lines.extend(
        _merged(
            _nsi_line(
                "nsi_surface", "NSI_SURFACE" if kind == "surface_nsi" else "", _PIECE_SURFACE_KINDS[kind],
                product, delay, count, index,
            )
            for (kind, product, delay), count in sorted(surface.items())
        )
    )

    # Как `timing._starter_seeds`: без объектов стартов — старый список скважин.
    # У электронной сети старты — точки отсчёта тайминга, а не стартовые
    # устройства НСИ: расходом они не считаются.
    starter_holes = [item.hole_id for item in design.network.starter_items] or list(design.network.starters)
    if design.network.system == "electronic":
        starter_holes = []
    starters = [hole_id for hole_id in starter_holes if hole_id in enabled]
    if starters:
        lines.append(_starter_line(len(starters), starter_product, index))
    return lines


def _merged(lines: Iterable[ConsumptionLine]) -> list[ConsumptionLine]:
    """Строки одной марки и замедления — одной строкой.

    Марка из сети и та же марка, подобранная по справочнику, — один материал:
    в таблице расхода он не должен стоять дважды.
    """

    merged: dict[tuple[str, str, float | None], ConsumptionLine] = {}
    for line in lines:
        key = (line.material_code or line.name, line.name, line.delay_ms)
        if key in merged:
            first = merged[key]
            merged[key] = replace(first, quantity=first.quantity + line.quantity)
        else:
            merged[key] = line
    return list(merged.values())


def _name(material: Any, product: str) -> str:
    return str(material["name"]) if material else product


def _downhole_connector(
    design: BlastDesign,
    own: list[DownholeConnector],
    load: HoleLoad,
    primer: Primer,
    primer_index: int,
    primer_count: int,
) -> tuple[str, str, float | None]:
    """Вид, марка и замедление скважинного инициатора ПД.

    Вид — у коннектора (`downhole_nsi`, `electronic`, `detonating_cord`),
    иначе у назначенного детонатора (`network.detonators`), иначе по системе
    сети. В расход НСИ идёт только `downhole_nsi`; шнур — отдельной строкой ДШ
    (следующая версия). Марка — коннектора, иначе детонатора.
    """

    deck = _deck_of(load, primer.position_m)
    connector = _assigned(own, primer_index, deck, primer_count)
    detonators = [item for item in design.network.detonators if item.hole_id == load.hole_id]
    detonator = _assigned(detonators, primer_index, deck, primer_count)
    if connector is not None:
        product = connector.product or (detonator.product if detonator else "")
        return connector.kind, product, float(connector.delay_ms)
    if detonator is not None:
        kind = detonator.kind if detonator.kind in ("electronic", "detonating_cord") else "downhole_nsi"
        return kind, detonator.product, float(detonator.delay_ms)
    delay = design.network.downhole_delay_ms.get(load.hole_id)
    system = design.network.system
    kind = "electronic" if system == "electronic" else "detonating_cord" if system == "detcord" else "downhole_nsi"
    return kind, "", None if delay is None else float(delay)


def _assigned(items: list[Any], primer_index: int, deck: int | None, primer_count: int) -> Any:
    """Назначение ПД (коннектор или детонатор): своё; деки, где ПД стоит; скважины.

    У единственного ПД годится любое назначение без номера ПД.
    """

    match = next((item for item in items if item.primer_index == primer_index), None)
    if match is None and deck is not None:
        match = next((item for item in items if item.primer_index is None and item.deck_index == deck), None)
    if match is None:
        match = next((item for item in items if item.primer_index is None and item.deck_index is None), None)
    if match is None and primer_count == 1:
        match = next((item for item in items if item.primer_index is None), None)
    return match


def _deck_of(load: HoleLoad, position_m: float) -> int | None:
    """Номер взрывчатой деки, в которой стоит ПД."""

    for number, deck in enumerate(load.decks):
        if is_explosive_deck_kind(deck.kind) and min(deck.from_m, deck.to_m) - 1e-6 <= position_m <= max(deck.from_m, deck.to_m) + 1e-6:
            return number
    return None


def _same_delay(payload: dict[str, Any], delay: float | None) -> bool:
    """Материал с тем же замедлением. Замедление сети неизвестно — марку не угадываем."""

    if delay is None:
        return False
    try:
        return Decimal(str(payload.get("delay_ms"))) == Decimal(str(delay))
    except (InvalidOperation, TypeError, ValueError):
        return False


def _nsi_line(
    kind: str,
    role: str,
    label: str,
    product: str,
    delay: float | None,
    count: int,
    index: MaterialIndex,
) -> ConsumptionLine:
    """Строка НСИ: марка из сети, иначе материал роли с тем же замедлением, иначе подпись и предупреждение."""

    material = index.find(product) if product else None
    if material is not None or product:
        return ConsumptionLine(
            kind, _name(material, product), float(count), "шт", None,
            material_code=material["code"] if material else "", delay_ms=delay,
        )
    candidates = [item for item in index.by_role(role) if _same_delay(item["payload"], delay)] if role else []
    if candidates:
        return ConsumptionLine(
            kind, str(candidates[0]["name"]), float(count), "шт", None,
            material_code=str(candidates[0]["code"]), delay_ms=delay, source="REFERENCE",
        )
    delay_text = f" {_ms(delay)} мс" if delay is not None else ""
    warning = f"{kind}_unmapped"
    return ConsumptionLine(
        kind,
        f"{label}{delay_text}",
        float(count),
        "шт",
        None,
        delay_ms=delay,
        source="REFERENCE",
        warning=warning,
        message=f"В сети нет марки и в справочнике материалов нет позиции «{label}{delay_text}».",
    )


def _starter_line(count: int, starter_product: str, index: MaterialIndex) -> ConsumptionLine:
    if starter_product:
        material = index.find(starter_product)
        return ConsumptionLine(
            "starter", _name(material, starter_product), float(count), "шт", None,
            material_code=material["code"] if material else "",
        )
    candidates = index.by_role("NSI_START")
    if len(candidates) == 1:
        return ConsumptionLine(
            "starter", str(candidates[0]["name"]), float(count), "шт", None,
            material_code=str(candidates[0]["code"]), source="REFERENCE",
        )
    return ConsumptionLine(
        "starter",
        STARTER_FALLBACK,
        float(count),
        "шт",
        None,
        source="REFERENCE",
        warning="starter_unmapped",
        message="Марка стартового устройства не выбрана в проекте МВ, а в справочнике материалов не одна позиция стартера.",
    )


def _ms(delay: float) -> str:
    return f"{delay:g}".replace(".", ",")
