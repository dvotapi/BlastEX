"""Охраняемые объекты проекта массового взрыва (TASK-018, PR 2, §3.6).

Два источника (решение владельца В1):

- ситуация карьера TASK-013: слой вида «здания» — охраняемые здания, «ЛЭП» и
  «дороги» — сооружения; один объект на слой (имя слоя), расстояние — от
  ближайшей точки контура блока (нет контура — от ближайшего устья) до линий
  слоя; в список идут объекты не дальше наибольшей опасной зоны («в радиусе
  максимальной опасной зоны», форма ВМ.09.03). Склады, контур карьера,
  развалы и «прочее» охраняемыми не считаются — их добавляют руками;
- ручной список проекта МВ.

Пометки к объекту ситуации (тип, мероприятия, «лечебное или детское», свои
K_г и K_с) хранятся в проекте по ключу `SITUATION:<имя слоя>` и переживают
пересчёт расстояний. Оценка «вне зоны / В ЗОНЕ» — `safety.objects`; у объекта
со своими K_г, K_с сейсмически безопасное расстояние пересчитывается
пропорционально (формула (8) линейна по K_г·K_с) и снова вверх до 50 м.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Sequence

import shapely
from shapely.geometry import LineString, MultiPoint, Point, Polygon

from design.safety import SafetyIssue, ceil_to, num
from design.safety.objects import INSIDE, OBJECT_KINDS, OBJECT_KIND_LABELS, OUTSIDE

__all__ = [
    "OBJECT_SOURCE_MANUAL",
    "OBJECT_SOURCE_SITUATION",
    "ObjectRow",
    "ObjectZones",
    "assess_project_objects",
    "situation_candidates",
]

OBJECT_SOURCE_SITUATION = "SITUATION"
OBJECT_SOURCE_MANUAL = "MANUAL"
SITUATION_PROTECTED_KINDS = {"building": "buildings", "power_line": "structures", "road": "structures"}


@dataclass(frozen=True)
class ObjectZones:
    """Принятые расстояния проекта, от которых считается «В ЗОНЕ»."""

    people_m: float
    mechanisms_m: float
    seismic_m: float            # принятое r_с (вверх до 50 м)
    seismic_raw_m: float        # r_с до округления, с ×2 п. 795
    airblast_m: float
    buildings_m: float          # принятая зона для зданий (с ручным вводом)
    k_ground: float
    k_structure: float
    buildings_manual: bool = False  # зона для зданий задана вручную (`MANUAL_OVERRIDE`)

    @property
    def largest_m(self) -> float:
        return max(self.people_m, self.mechanisms_m, self.buildings_m, self.seismic_m, self.airblast_m)


@dataclass(frozen=True)
class ObjectRow:
    key: str
    name: str
    kind: str
    source: str
    distance_m: float
    required_m: float
    factor: str
    position: str
    measures: str = ""
    sensitive: bool = False
    k_ground: float | None = None
    k_structure: float | None = None
    situation_kind: str = ""

    @property
    def inside(self) -> bool:
        return self.position == INSIDE

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "name": self.name,
            "kind": self.kind,
            "kind_label": OBJECT_KIND_LABELS.get(self.kind, self.kind),
            "source": self.source,
            "distance_m": self.distance_m,
            "required_m": self.required_m,
            "factor": self.factor,
            "position": self.position,
            "measures": self.measures,
            "sensitive": self.sensitive,
            "k_ground": self.k_ground,
            "k_structure": self.k_structure,
            "situation_kind": self.situation_kind,
        }


def _block_geometry(contours: Sequence[Sequence[tuple[float, float]]], collars: Sequence[tuple[float, float]]):
    shapes = []
    for ring in contours:
        if len(ring) >= 3:
            polygon = Polygon(ring)
            shapes.append(polygon if polygon.is_valid else polygon.buffer(0))
    if shapes:
        return shapely.union_all(shapes)
    return MultiPoint(list(collars)) if collars else None


def _layer_geometry(lines: Iterable[Mapping[str, Any]]):
    parts = []
    for line in lines:
        points = [(float(p[0]), float(p[1])) for p in line.get("points") or ()]
        if len(points) >= 3 and line.get("closed"):
            parts.append(Polygon(points))
        elif len(points) >= 2:
            parts.append(LineString(points))
        elif points:
            parts.append(Point(points[0]))
    return shapely.union_all([part if part.is_valid else part.buffer(0) for part in parts]) if parts else None


def situation_candidates(
    layers: Sequence[Mapping[str, Any]],
    contours: Sequence[Sequence[tuple[float, float]]],
    collars: Sequence[tuple[float, float]],
) -> list[dict[str, Any]]:
    """Слои ситуации охраняемых видов с расстоянием до блоков, без отбора по зоне.

    Слой с одним именем из разных версий ситуации — один объект, по ближайшей.
    """

    block = _block_geometry(contours, collars)
    if block is None or block.is_empty:
        return []
    by_name: dict[str, dict[str, Any]] = {}
    for layer in layers:
        kind = SITUATION_PROTECTED_KINDS.get(str(layer.get("kind") or ""))
        name = str(layer.get("name") or "").strip()
        if kind is None or not name:
            continue
        geometry = _layer_geometry(layer.get("lines") or ())
        if geometry is None or geometry.is_empty:
            continue
        distance = round(float(block.distance(geometry)), 1)
        current = by_name.get(name)
        if current is None or distance < current["distance_m"]:
            by_name[name] = {
                "key": f"{OBJECT_SOURCE_SITUATION}:{name}",
                "name": name,
                "kind": kind,
                "distance_m": distance,
                "situation_kind": str(layer.get("kind") or ""),
            }
    return sorted(by_name.values(), key=lambda item: (item["distance_m"], item["name"]))


def _positive(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) and number > 0 else None


def _required(kind: str, zones: ObjectZones, k_ground: float | None, k_structure: float | None) -> tuple[float, str]:
    seismic = zones.seismic_m
    if (k_ground or k_structure) and zones.k_ground > 0 and zones.k_structure > 0:
        scale = (k_ground or zones.k_ground) * (k_structure or zones.k_structure) / (zones.k_ground * zones.k_structure)
        seismic = ceil_to(zones.seismic_raw_m * scale)
    buildings = max((seismic, "сейсмика"), (zones.airblast_m, "УВВ"))
    # Расчётная зона для зданий — тот же max(r_с, r_в) без K объекта: она не
    # должна перекрывать пересчёт по K объекта. Перекрывает только ручная.
    if zones.buildings_manual and zones.buildings_m > buildings[0]:
        buildings = (zones.buildings_m, "принято проектом")
    return {
        "people": (zones.people_m, "люди"),
        "buildings": buildings,
        "structures": max((zones.mechanisms_m, "механизмы"), (seismic, "сейсмика")),
        "mechanisms": (zones.mechanisms_m, "механизмы"),
    }[kind]


def assess_project_objects(
    candidates: Sequence[Mapping[str, Any]],
    entries: Sequence[Mapping[str, Any]],
    zones: ObjectZones,
) -> tuple[list[ObjectRow], list[SafetyIssue]]:
    """Объекты ситуации в радиусе наибольшей зоны + ручной список, с оценкой.

    `entries` — `protected_objects` проекта: ручные объекты (`source` =
    MANUAL) и пометки к объектам ситуации (`key` объекта ситуации).
    """

    issues: list[SafetyIssue] = []
    notes = {
        str(entry.get("key")): entry
        for entry in entries
        if str(entry.get("source") or "") == OBJECT_SOURCE_SITUATION and entry.get("key")
    }
    rows: list[ObjectRow | None] = []
    largest = zones.largest_m
    for candidate in candidates:
        if candidate["distance_m"] > largest:
            continue
        note = notes.get(candidate["key"], {})
        kind = str(note.get("kind") or candidate["kind"])
        rows.append(_row(candidate["key"], candidate["name"], kind, OBJECT_SOURCE_SITUATION, candidate["distance_m"], note, zones, issues, candidate.get("situation_kind", "")))
    for index, entry in enumerate(entries):
        if str(entry.get("source") or OBJECT_SOURCE_MANUAL) != OBJECT_SOURCE_MANUAL:
            continue
        name = str(entry.get("name") or "").strip()
        distance = entry.get("distance_m")
        try:
            distance = float(distance)
        except (TypeError, ValueError):
            distance = float("nan")
        if not name or not math.isfinite(distance) or distance < 0:
            issues.append(
                SafetyIssue("error", "object_incomplete", f"Охраняемый объект № {index + 1}: укажите наименование и расстояние, м.")
            )
            continue
        key = str(entry.get("key") or f"{OBJECT_SOURCE_MANUAL}:{index + 1}")
        rows.append(_row(key, name, str(entry.get("kind") or ""), OBJECT_SOURCE_MANUAL, distance, entry, zones, issues))
    return [row for row in rows if row is not None], issues


def _row(
    key: str,
    name: str,
    kind: str,
    source: str,
    distance: float,
    note: Mapping[str, Any],
    zones: ObjectZones,
    issues: list[SafetyIssue],
    situation_kind: str = "",
) -> ObjectRow | None:
    if kind not in OBJECT_KINDS:
        issues.append(
            SafetyIssue("error", "object_kind_unknown", f"«{name}»: тип объекта не из списка (люди, здания, сооружения, механизмы).")
        )
        return None
    k_ground, k_structure = _positive(note.get("k_ground")), _positive(note.get("k_structure"))
    need, factor = _required(kind, zones, k_ground, k_structure)
    sensitive = bool(note.get("sensitive"))
    row = ObjectRow(
        key=key,
        name=name,
        kind=kind,
        source=source,
        distance_m=distance,
        required_m=need,
        factor=factor,
        position=INSIDE if distance < need else OUTSIDE,
        measures=str(note.get("measures") or "").strip(),
        sensitive=sensitive,
        k_ground=k_ground,
        k_structure=k_structure,
        situation_kind=situation_kind,
    )
    buildings = _required("buildings", zones, k_ground, k_structure)[0]
    if sensitive and distance < buildings:
        issues.append(
            SafetyIssue(
                "error",
                "expert_required",
                f"«{name}» ({num(distance)} м) — лечебное или детское учреждение ближе {num(buildings)} м: "
                "безопасные расстояния определяет экспертная организация (п. 808).",
            )
        )
    return row
