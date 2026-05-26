"""
Справочник номенклатуры и цен (листы Excel: ВВ, СВ, СИ).
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Literal

CatalogCategory = Literal["explosive", "detonator", "downhole_nsi", "surface_nsi", "start_nsi"]

_LEGACY_CATALOG_CATEGORIES = {
    "nsi": "downhole_nsi",
}
_SKIP_CATALOG_CATEGORIES = frozenset({"surface_waveguide"})


@dataclass
class CatalogItem:
    id: str
    name: str
    category: CatalogCategory
    unit: str
    price: float
    mass_kg: float | None = None
    length_m: float | None = None
    note: str = ""


DEFAULT_CATALOG: list[CatalogItem] = [
    CatalogItem("vv_granulit", "ГВВ Гранулит РП", "explosive", "кг", 46.0),
    CatalogItem("vv_eversin", "ЭВВ Эверсин-100", "explosive", "кг", 48.9),
    CatalogItem("vv_beresit", "ЭВВ Березит Э-100", "explosive", "кг", 47.0),
    CatalogItem("vv_nitronit", "ЭВВ Нитронит Э-100", "explosive", "кг", 40.0),
    CatalogItem("vv_protolit", "ЭВВ Протолит-100", "explosive", "кг", 45.0),
    CatalogItem(
        "sv_dpu_pt600",
        'Детонатор промежуточный ДПУ-ПТ600',
        "detonator",
        "кг",
        150.0,
        mass_kg=0.65,
    ),
    CatalogItem(
        "sv_sferit_08",
        'Детонатор промежуточный "Сферит ДП" - 60 / 0,8',
        "detonator",
        "кг",
        150.0,
        mass_kg=0.8,
    ),
    CatalogItem(
        "sv_sferit_10",
        'Детонатор промежуточный "Сферит ДП" - 60 / 1,0',
        "detonator",
        "кг",
        150.0,
        mass_kg=1.0,
    ),
    CatalogItem("nsi_36", 'НСИ "Rionel" Х-*-3,6 м', "downhole_nsi", "шт", 77.09, length_m=3.6),
    CatalogItem("nsi_42", 'НСИ "Rionel" Х-*-4,2 м', "downhole_nsi", "шт", 74.06, length_m=4.2),
    CatalogItem("nsi_48", 'НСИ "Rionel" Х-*-4,8 м', "downhole_nsi", "шт", 103.16, length_m=4.8),
    CatalogItem("nsi_60", 'НСИ "Rionel" MS-20-6 м', "downhole_nsi", "шт", 99.08, length_m=6.0),
    CatalogItem("nsi_72", 'НСИ "Rionel" Х-*-7,2 м', "downhole_nsi", "шт", 109.65, length_m=7.2),
    CatalogItem("nsi_85", "Устройство Искра-С-*-8,5", "downhole_nsi", "шт", 300.0, length_m=8.5),
    CatalogItem("nsi_90", 'НСИ "Rionel" MS-20-9 м', "downhole_nsi", "шт", 99.91, length_m=9.0),
    CatalogItem("nsi_120", "Устройство Искра-С-*-12", "downhole_nsi", "шт", 335.2, length_m=12.0),
    CatalogItem("nsi_150", 'НСИ "Rionel" MS-20-15 м', "downhole_nsi", "шт", 120.0, length_m=15.0),
    CatalogItem("nsi_180", 'НСИ "Rionel" MS-20-18 м', "downhole_nsi", "шт", 146.76, length_m=18.0),
    CatalogItem("surface_nsi_4", "Устройство Искра-П-*-4", "surface_nsi", "шт", 214.0),
    CatalogItem("surface_nsi_5", "Устройство Искра-П-*-5", "surface_nsi", "шт", 240.0),
    CatalogItem("surface_nsi_6", "Устройство Искра-П-*-6", "surface_nsi", "шт", 265.0),
    CatalogItem("start_nsi_200", "Устройство ИСКРА-СТАРТ-В-200", "start_nsi", "шт", 3210.0),
    CatalogItem("start_nsi_500", "Устройство ИСКРА-СТАРТ-В-500", "start_nsi", "шт", 7400.0),
]

EXPLOSIVE_TO_CATALOG_ID = {
    "ПВВ Гранулит-РП": "vv_granulit",
    "ПЭВВ ЭВЕРСИН Э-100": "vv_eversin",
}


def catalog_to_records(items: list[CatalogItem]) -> list[dict]:
    return [asdict(item) for item in items]


def _normalize_catalog_category(category: str) -> str | None:
    if category in _SKIP_CATALOG_CATEGORIES:
        return None
    return _LEGACY_CATALOG_CATEGORIES.get(category, category)


def catalog_from_records(records: list[dict]) -> list[CatalogItem]:
    items: list[CatalogItem] = []
    for row in records:
        category = _normalize_catalog_category(str(row["category"]))
        if category is None:
            continue
        items.append(
            CatalogItem(
                id=str(row["id"]),
                name=str(row["name"]),
                category=category,  # type: ignore[arg-type]
                unit=str(row["unit"]),
                price=float(row["price"]),
                mass_kg=float(row["mass_kg"]) if row.get("mass_kg") not in (None, "") else None,
                length_m=float(row["length_m"]) if row.get("length_m") not in (None, "") else None,
                note=str(row.get("note") or ""),
            )
        )
    return items


def get_catalog_item(items: list[CatalogItem], item_id: str) -> CatalogItem | None:
    for item in items:
        if item.id == item_id:
            return item
    return None


def items_by_category(items: list[CatalogItem], category: CatalogCategory) -> list[CatalogItem]:
    return [item for item in items if item.category == category]


def find_downhole_nsi_by_length(items: list[CatalogItem], length_m: float) -> CatalogItem | None:
    candidates = [
        i for i in items if i.category == "downhole_nsi" and i.length_m is not None
    ]
    if not candidates:
        return None
    return min(candidates, key=lambda item: abs(item.length_m - length_m))


def find_nsi_by_length(items: list[CatalogItem], length_m: float) -> CatalogItem | None:
    """Обратная совместимость."""
    return find_downhole_nsi_by_length(items, length_m)


def default_surface_nsi(items: list[CatalogItem]) -> CatalogItem | None:
    surface = items_by_category(items, "surface_nsi")
    if not surface:
        return None
    for item in surface:
        if item.id == "surface_nsi_5":
            return item
    return surface[0]


def default_start_nsi(items: list[CatalogItem]) -> CatalogItem | None:
    start_items = items_by_category(items, "start_nsi")
    if not start_items:
        return None
    for item in start_items:
        if item.id == "start_nsi_500":
            return item
    return start_items[0]


def resolve_explosive_id(explosive_key: str, items: list[CatalogItem]) -> str:
    mapped = EXPLOSIVE_TO_CATALOG_ID.get(explosive_key)
    if mapped and get_catalog_item(items, mapped):
        return mapped
    explosives = items_by_category(items, "explosive")
    return explosives[0].id if explosives else ""
