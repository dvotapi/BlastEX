"""Сущности чертежа маркшейдера, роли слоёв и их происхождение (TASK-013).

Сущность хранит мировые координаты в метрах (после масштаба импорта). Роль
отвечает на вопрос «что это для блока»: контур, бровка, отметки, ситуация.
Код роли — стабильный ключ хранения, подпись видит пользователь.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

Point = tuple[float, float, float]

LINE_KINDS = frozenset(
    {"LWPOLYLINE", "POLYLINE2D", "POLYLINE3D", "LINE", "ARC", "CIRCLE", "ELLIPSE", "SPLINE"}
)
POINT_KINDS = frozenset({"POINT", "INSERT"})
TEXT_KINDS = frozenset({"TEXT", "MTEXT"})

# Допуски вида Z: «ноль» — отметки нет, «постоянная» — одна отметка на линию
# (горизонталь или отметка вычерчивания), иначе — 3D-линия съёмки.
ZERO_Z_TOLERANCE_M = 0.001
CONST_Z_TOLERANCE_M = 0.005


@dataclass(frozen=True)
class RoleInfo:
    code: str
    label: str
    applies_to: tuple[str, ...]


ROLE_BLOCK_CONTOUR = "block_contour"
ROLE_DESIGN_LINE = "design_line"
ROLE_CREST_TOP = "crest_top"
ROLE_CREST_BOTTOM = "crest_bottom"
ROLE_FEATURE_LINE = "feature_line"
ROLE_CONTOUR_LINE = "contour_line"
ROLE_SPOT_HEIGHTS = "spot_heights"
ROLE_SITUATION = "situation"
ROLE_IGNORE = "ignore"
# Только для слоя: бровки обоих уровней на одном слое, сущности делятся по Z.
ROLE_CRESTS_BY_Z = "crests_by_z"

ROLES: tuple[RoleInfo, ...] = (
    RoleInfo(ROLE_BLOCK_CONTOUR, "Контур блока", ("line",)),
    RoleInfo(ROLE_DESIGN_LINE, "Проектная линия", ("line",)),
    RoleInfo(ROLE_CREST_TOP, "Бровка верхняя", ("line",)),
    RoleInfo(ROLE_CREST_BOTTOM, "Бровка нижняя", ("line",)),
    RoleInfo(ROLE_FEATURE_LINE, "Характерная линия", ("line",)),
    RoleInfo(ROLE_CONTOUR_LINE, "Горизонталь", ("line",)),
    RoleInfo(ROLE_SPOT_HEIGHTS, "Отметки поверхности", ("line", "point", "text")),
    RoleInfo(ROLE_SITUATION, "Ситуация", ("line", "point", "text")),
    RoleInfo(ROLE_IGNORE, "Не использовать", ("line", "point", "text")),
)
LAYER_ONLY_ROLES: tuple[RoleInfo, ...] = (
    RoleInfo(ROLE_CRESTS_BY_Z, "Бровки (по Z)", ("line",)),
)
ROLE_CODES = frozenset(item.code for item in ROLES)
LAYER_ROLE_CODES = ROLE_CODES | {item.code for item in LAYER_ONLY_ROLES}

# Какую площадь маркшейдер называет площадью блока — у каждого по-своему.
# Выбор хранится на объекте работ (cad_site_settings), по умолчанию S ср (§2).
AREA_BASIS_TOP = "top"
AREA_BASIS_BOTTOM = "bottom"
AREA_BASIS_MEAN = "mean"
AREA_BASES: tuple[tuple[str, str, str], ...] = (
    (AREA_BASIS_TOP, "S верх", "площадь контура по верхней бровке"),
    (AREA_BASIS_BOTTOM, "S низ", "площадь контура по нижней бровке"),
    (AREA_BASIS_MEAN, "S ср", "(S верх + S низ) / 2 — способ горизонтальных сечений"),
)
AREA_BASIS_CODES = frozenset(code for code, _, _ in AREA_BASES)
DEFAULT_AREA_BASIS = AREA_BASIS_MEAN

# Вид объекта ситуации (§2 «Ситуация карьера»): хранится сразу, чтобы позже
# повесить на объекты охранные зоны. Назначается слою роли «Ситуация».
SITUATION_KIND_PIT = "pit"
SITUATION_KIND_ROAD = "road"
SITUATION_KIND_POWER_LINE = "power_line"
SITUATION_KIND_STOCKPILE = "stockpile"
SITUATION_KIND_BUILDING = "building"
SITUATION_KIND_OTHER = "other"
SITUATION_KINDS: tuple[tuple[str, str], ...] = (
    (SITUATION_KIND_PIT, "Контур карьера"),
    (SITUATION_KIND_ROAD, "Дорога"),
    (SITUATION_KIND_POWER_LINE, "ЛЭП"),
    (SITUATION_KIND_STOCKPILE, "Склад"),
    (SITUATION_KIND_BUILDING, "Здание"),
    (SITUATION_KIND_OTHER, "Прочее"),
)
SITUATION_KIND_CODES = frozenset(code for code, _ in SITUATION_KINDS)

ORIGIN_TEMPLATE = "template"
ORIGIN_AUTO = "auto"
ORIGIN_Z = "z"
ORIGIN_MANUAL = "manual"
ORIGINS: dict[str, str] = {
    ORIGIN_TEMPLATE: "шаблон",
    ORIGIN_AUTO: "авто",
    ORIGIN_Z: "по Z",
    ORIGIN_MANUAL: "вручную",
}


@dataclass
class CadWarning:
    """Предупреждение импорта. `info` — заметка, `warning` — требует внимания."""

    code: str
    message: str
    level: str = "warning"

    def to_dict(self) -> dict[str, str]:
        return {"code": self.code, "message": self.message, "level": self.level}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CadWarning:
        return cls(code=str(data.get("code", "")), message=str(data.get("message", "")), level=str(data.get("level", "warning")))


@dataclass
class CadEntity:
    """Одна сущность чертежа в мировых координатах."""

    handle: str
    layer: str
    kind: str
    points: list[Point]
    closed: bool = False
    closed_by_gap: bool = False
    text: str = ""
    text_height: float = 0.0
    z_from_label: bool = False
    label_handle: str = ""
    color: str | None = None
    role: str = ""
    role_origin: str = ""

    @property
    def geometry_type(self) -> str:
        if self.kind in TEXT_KINDS:
            return "text"
        if self.kind in POINT_KINDS:
            return "point"
        return "line"

    @property
    def vertex_count(self) -> int:
        return len(self.points)

    @property
    def length_m(self) -> float:
        """Длина в плане; у замкнутой линии — с замыкающим отрезком."""

        if self.geometry_type != "line":
            return 0.0
        total = sum(math.dist(a[:2], b[:2]) for a, b in zip(self.points, self.points[1:]))
        if self.closed and len(self.points) > 2:
            total += math.dist(self.points[-1][:2], self.points[0][:2])
        return total

    @property
    def area_m2(self) -> float:
        """Площадь в плане для замкнутой линии, иначе 0."""

        if not self.closed or len(self.points) < 3:
            return 0.0
        ring = [*self.points, self.points[0]]
        return abs(sum(a[0] * b[1] - b[0] * a[1] for a, b in zip(ring, ring[1:]))) / 2

    @property
    def z_min(self) -> float:
        return min(point[2] for point in self.points)

    @property
    def z_max(self) -> float:
        return max(point[2] for point in self.points)

    @property
    def z_kind(self) -> str:
        if self.geometry_type == "text":
            return "zero"
        if all(abs(point[2]) <= ZERO_Z_TOLERANCE_M for point in self.points):
            return "zero"
        if self.z_max - self.z_min <= CONST_Z_TOLERANCE_M:
            return "const"
        return "variable"

    @property
    def z_median(self) -> float:
        values = sorted(point[2] for point in self.points)
        middle = len(values) // 2
        return values[middle] if len(values) % 2 else (values[middle - 1] + values[middle]) / 2

    def geometry(self) -> dict[str, Any]:
        """Геометрия для хранения (JSONB) и для холста."""

        if self.geometry_type == "line":
            return {"points": [list(point) for point in self.points]}
        data: dict[str, Any] = {"point": list(self.points[0])}
        if self.text:
            data["text"] = self.text
        if self.text_height:
            data["height"] = self.text_height
        return data

    def attributes(self) -> dict[str, Any]:
        return {
            "color": self.color,
            "closed_by_gap": self.closed_by_gap,
            "z_from_label": self.z_from_label,
            "label_handle": self.label_handle,
        }

    @classmethod
    def restore(
        cls,
        *,
        handle: str,
        layer: str,
        kind: str,
        geometry: dict[str, Any],
        closed: bool,
        attributes: dict[str, Any],
        role: str,
        role_origin: str,
    ) -> CadEntity:
        if "points" in geometry:
            points = [(float(x), float(y), float(z)) for x, y, z in geometry["points"]]
        else:
            x, y, z = geometry["point"]
            points = [(float(x), float(y), float(z))]
        return cls(
            handle=handle,
            layer=layer,
            kind=kind,
            points=points,
            closed=closed,
            closed_by_gap=bool(attributes.get("closed_by_gap")),
            text=str(geometry.get("text", "")),
            text_height=float(geometry.get("height", 0.0)),
            z_from_label=bool(attributes.get("z_from_label")),
            label_handle=str(attributes.get("label_handle") or ""),
            color=attributes.get("color"),
            role=role,
            role_origin=role_origin,
        )


@dataclass
class CadDrawing:
    """Результат чтения одного файла."""

    entities: list[CadEntity] = field(default_factory=list)
    layers: dict[str, str | None] = field(default_factory=dict)
    insunits: int | None = None
    extent: tuple[float, float, float, float] | None = None
    source_format: str = "dxf"
    minimal_dxf: bool = False
    warnings: list[CadWarning] = field(default_factory=list)
    suggested_scale: float | None = None


def ru_number(value: float, digits: int = 1) -> str:
    """Число с десятичной запятой и пробелами в разрядах — для текстов пользователю."""

    text = f"{value:,.{digits}f}".replace(",", " ").replace(".", ",")
    return text
