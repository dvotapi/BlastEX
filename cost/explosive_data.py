"""Справочник взрывчатых веществ для технологического расчёта БВР."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Iterable

from Blast import ExplosiveProperties


@dataclass(frozen=True)
class ExplosiveCatalogItem:
    """Позиция справочника ВВ: ключ UI, свойства для BlastEngine и подпись на схеме."""

    key: str
    name: str
    density_t_m3: float
    power_mj_kg: float
    chart_label: str = ""

    @property
    def properties(self) -> ExplosiveProperties:
        return ExplosiveProperties(self.name, self.density_t_m3, self.power_mj_kg)

    @property
    def label(self) -> str:
        return self.chart_label or self.name.upper()


DEFAULT_EXPLOSIVES: tuple[ExplosiveCatalogItem, ...] = (
    ExplosiveCatalogItem(
        key="ПВВ Гранулит-РП",
        name="Гранулит-РП",
        density_t_m3=0.85,
        power_mj_kg=3.76,
        chart_label="ГРАНУЛИТ-РП",
    ),
    ExplosiveCatalogItem(
        key="ПЭВВ ЭВЕРСИН Э-100",
        name="ЭВЕРСИН Э-100",
        density_t_m3=1.12,
        power_mj_kg=2.99,
        chart_label="ЭВЕРСИН",
    ),
)

DEFAULT_EXPLOSIVE_KEY = "ПВВ Гранулит-РП"


def explosives_to_records(items: Iterable[ExplosiveCatalogItem]) -> list[dict]:
    return [asdict(item) for item in items]


def explosives_from_records(records: list[dict]) -> list[ExplosiveCatalogItem]:
    items: list[ExplosiveCatalogItem] = []
    for row in records:
        key = str(row.get("key", "")).strip()
        name = str(row.get("name", "")).strip()
        if not key or not name:
            continue
        items.append(
            ExplosiveCatalogItem(
                key=key,
                name=name,
                density_t_m3=float(row.get("density_t_m3", 0) or 0),
                power_mj_kg=float(row.get("power_mj_kg", 0) or 0),
                chart_label=str(row.get("chart_label", "") or "").strip(),
            )
        )
    return items


def find_explosive(
    key: str,
    items: Iterable[ExplosiveCatalogItem] | None = None,
) -> ExplosiveCatalogItem | None:
    source = items if items is not None else DEFAULT_EXPLOSIVES
    for item in source:
        if item.key == key:
            return item
    return None
