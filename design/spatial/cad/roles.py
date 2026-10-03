"""Авторазметка ролей слоёв и сущностей чертежа маркшейдера.

Роль назначается слою, у отдельной сущности её можно переопределить. Порядок
для слоя: ручная роль → шаблон объекта (имя слоя → роль, сохраняется на
объекте) → правила по имени слоя и типу сущностей («авто»). Сущность берёт
роль слоя, приведённую к своей геометрии: точка на слое бровок — отметка,
а не бровка. Бровки обоих уровней на одном слое («Горизонт +410») делятся
по Z относительно проектной подошвы: в пределах половины высоты уступа от
подошвы — нижняя, выше — верхняя.
"""
from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field

from design.spatial.cad.labels import parse_elevation
from design.spatial.cad.model import (
    LAYER_ROLE_CODES,
    ORIGIN_AUTO,
    ORIGIN_MANUAL,
    ORIGIN_TEMPLATE,
    ORIGIN_Z,
    ROLE_BLOCK_CONTOUR,
    ROLE_CODES,
    ROLE_CONTOUR_LINE,
    ROLE_CREST_BOTTOM,
    ROLE_CREST_TOP,
    ROLE_CRESTS_BY_Z,
    ROLE_DESIGN_LINE,
    ROLE_FEATURE_LINE,
    ROLE_IGNORE,
    ROLE_SITUATION,
    ROLE_SPOT_HEIGHTS,
    CadEntity,
    CadWarning,
    ru_number,
)

# Наименьший разрыв отметок, по которому бровки делятся без подошвы, м.
MIN_CREST_GAP_M = 2.0
DEFAULT_BENCH_HEIGHT_M = 10.0

_BLOCK = re.compile(r"блок")
_BLOCK_MARK = re.compile(r"\d|границ")
_CREST = re.compile(r"бровк")
_TOP = re.compile(r"верх")
_BOTTOM = re.compile(r"ниж")
# «Горизонт +410» — уступ; «Горизонтали» — изолинии рельефа.
_BENCH = re.compile(r"горизонт(?!ал)|бровк")
_CONTOUR_LINES = re.compile(r"горизонтал|изолин")
_RELIEF = re.compile(r"рельеф|съ[её]мк|отметк|пикет|высот|тахеом|survey|topo")
_FLOOR_IN_NAME = re.compile(r"(?:горизонт|гор\.?)\s*([+\-−]?)\s*(\d{2,4}(?:[.,]\d+)?)")

_LINE_ROLES_FOR_POINTS = frozenset({ROLE_SITUATION, ROLE_IGNORE})


@dataclass(frozen=True)
class TemplateEntry:
    """Роль слоя в шаблоне объекта. `manual` — роль подтверждена человеком.

    Загрузка пополняет шаблон догадками «авто»; такая роль из шаблона ведёт
    себя как «авто» (точки с отметкой на «Ситуации» остаются отметками), а
    подтверждённая — как ручная.
    """

    role: str
    manual: bool = False
    # Вид объекта ситуации, заданный человеком (PR 4); None — по имени слоя.
    kind: str | None = None


@dataclass(frozen=True)
class RoleParams:
    floor_z_m: float | None = None
    bench_height_m: float = DEFAULT_BENCH_HEIGHT_M


@dataclass
class LayerRole:
    name: str
    role: str
    origin: str
    # Роль выбрана человеком: вручную в этом файле или подтверждена в шаблоне.
    confirmed: bool = False


@dataclass
class RoleAssignment:
    layers: list[LayerRole] = field(default_factory=list)
    warnings: list[CadWarning] = field(default_factory=list)
    # Подошва, по которой делились бровки: из параметра или из имени слоя.
    floor_z_m: float | None = None


def layer_key(name: str) -> str:
    """Ключ слоя в шаблоне: без учёта регистра и лишних пробелов."""

    return " ".join((name or "").casefold().split())


def floor_from_layer_name(name: str) -> float | None:
    match = _FLOOR_IN_NAME.search(layer_key(name))
    if not match:
        return None
    sign, number = match.groups()
    value = float(number.replace(",", "."))
    return -value if sign in ("-", "−") else value


def assign_roles(
    entities: list[CadEntity],
    template: Mapping[str, TemplateEntry | str],
    params: RoleParams,
    manual_layers: dict[str, str] | None = None,
    manual_entities: dict[str, str] | None = None,
) -> RoleAssignment:
    """Проставляет `role` и `role_origin` сущностям и возвращает роли слоёв."""

    manual_layers = manual_layers or {}
    manual_entities = manual_entities or {}
    by_layer: dict[str, list[CadEntity]] = {}
    for item in entities:
        by_layer.setdefault(item.layer, []).append(item)

    result = RoleAssignment(floor_z_m=params.floor_z_m)
    for name in sorted(by_layer, key=layer_key):
        members = by_layer[name]
        manual_role = manual_layers.get(name) or ""
        entry = template.get(layer_key(name))
        if isinstance(entry, str):
            entry = TemplateEntry(entry)
        if manual_role in LAYER_ROLE_CODES:
            role, origin, confirmed = manual_role, ORIGIN_MANUAL, True
        elif entry is not None and entry.role in LAYER_ROLE_CODES:
            role, origin, confirmed = entry.role, ORIGIN_TEMPLATE, entry.manual
        else:
            role, origin, confirmed = _auto_layer_role(name, members), ORIGIN_AUTO, False
        result.layers.append(LayerRole(name=name, role=role, origin=origin, confirmed=confirmed))

        for item in members:
            item.role, item.role_origin = _entity_role(item, role, origin, confirmed)
        if role == ROLE_CRESTS_BY_Z:
            _split_crests(name, members, params, result)

    for item in entities:
        manual = manual_entities.get(item.handle)
        if manual in ROLE_CODES:
            item.role, item.role_origin = manual, ORIGIN_MANUAL
    return result


def _auto_layer_role(name: str, members: list[CadEntity]) -> str:
    key = layer_key(name)
    lines = [item for item in members if item.geometry_type == "line"]
    points = [item for item in members if item.geometry_type == "point"]

    if _BLOCK.search(key) and _BLOCK_MARK.search(key) and lines:
        # Замкнутая линия — готовый контур; одни открытые — его участки.
        return ROLE_BLOCK_CONTOUR if any(item.closed for item in lines) else ROLE_DESIGN_LINE
    if _CREST.search(key) and _TOP.search(key):
        return ROLE_CREST_TOP
    if _CREST.search(key) and _BOTTOM.search(key):
        return ROLE_CREST_BOTTOM
    if _BENCH.search(key) and any(item.z_kind == "variable" for item in lines):
        return ROLE_CRESTS_BY_Z
    if _CONTOUR_LINES.search(key):
        return ROLE_CONTOUR_LINE
    if _RELIEF.search(key):
        return ROLE_SPOT_HEIGHTS
    if points and not lines and any(item.z_kind != "zero" for item in points):
        return ROLE_SPOT_HEIGHTS
    return ROLE_SITUATION


def _entity_role(item: CadEntity, layer_role: str, origin: str, confirmed: bool) -> tuple[str, str]:
    """Роль слоя, приведённая к геометрии сущности."""

    kind = item.geometry_type
    if kind == "text":
        if layer_role == ROLE_IGNORE:
            return ROLE_IGNORE, origin
        if parse_elevation(item.text) is not None and layer_role not in _LINE_ROLES_FOR_POINTS:
            return ROLE_SPOT_HEIGHTS, origin
        return (layer_role if layer_role in _LINE_ROLES_FOR_POINTS else ROLE_SITUATION), origin

    if kind == "point":
        has_z = item.z_kind != "zero"
        # «Ситуация», выбранная человеком, забирает и точки слоя; догадка — нет.
        if layer_role == ROLE_IGNORE or (layer_role == ROLE_SITUATION and confirmed):
            return layer_role, origin
        # Точки и знаки с отметкой — поверхность (§2); без отметки им там не место.
        return (ROLE_SPOT_HEIGHTS if has_z else ROLE_SITUATION), origin

    if layer_role == ROLE_BLOCK_CONTOUR and not item.closed:
        return ROLE_DESIGN_LINE, origin
    if layer_role == ROLE_CONTOUR_LINE and item.z_kind != "const":
        return ROLE_FEATURE_LINE, origin
    if layer_role == ROLE_SPOT_HEIGHTS and item.z_kind != "variable":
        return ROLE_FEATURE_LINE, origin
    if layer_role == ROLE_CRESTS_BY_Z:
        # Линия без отметки бровкой быть не может: по Z её не разделить, а
        # нижней бровкой на нуле она «построила» бы уступ в сотни метров.
        if item.z_kind == "zero":
            return ROLE_FEATURE_LINE, origin
        # Верх/низ проставит _split_crests; до него — верхняя.
        return ROLE_CREST_TOP, ORIGIN_Z
    return layer_role, origin


def _split_crests(name: str, members: list[CadEntity], params: RoleParams, result: RoleAssignment) -> None:
    crests = [item for item in members if item.geometry_type == "line" and item.z_kind != "zero"]
    flat = sum(1 for item in members if item.geometry_type == "line" and item.z_kind == "zero")
    if flat:
        result.warnings.append(
            CadWarning(
                code="crest_without_z",
                message=(
                    f"На слое «{name}» линий без отметки: {flat}. Бровками они не считаются — "
                    "отнесены к характерным линиям."
                ),
            )
        )
    if not crests:
        return

    floor = params.floor_z_m
    if floor is None:
        floor = floor_from_layer_name(name)
        if floor is not None:
            result.floor_z_m = result.floor_z_m if result.floor_z_m is not None else floor
            result.warnings.append(
                CadWarning(
                    code="floor_from_name",
                    message=f"Подошва {ru_number(floor, 1)} м взята из имени слоя «{name}».",
                    level="info",
                )
            )

    if floor is not None:
        threshold = floor + max(params.bench_height_m, 0.0) / 2
        for item in crests:
            item.role = ROLE_CREST_BOTTOM if item.z_median <= threshold else ROLE_CREST_TOP
            item.role_origin = ORIGIN_Z
        return

    levels = sorted(item.z_median for item in crests)
    gaps = [(b - a, (a + b) / 2) for a, b in zip(levels, levels[1:])]
    widest = max(gaps, default=(0.0, 0.0))
    if widest[0] < MIN_CREST_GAP_M:
        for item in crests:
            item.role, item.role_origin = ROLE_CREST_TOP, ORIGIN_Z
        result.warnings.append(
            CadWarning(
                code="crest_split",
                message=(
                    f"Бровки слоя «{name}» не удалось разделить на верхние и нижние: "
                    "задайте отметку подошвы."
                ),
            )
        )
        return
    for item in crests:
        item.role = ROLE_CREST_BOTTOM if item.z_median <= widest[1] else ROLE_CREST_TOP
        item.role_origin = ORIGIN_Z
