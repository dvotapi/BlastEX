"""Паспорт на бурение: скважины, сводка и проверка первого ряда (`drill-v1`, TASK-015).

Чистые функции без базы и HTTP. Единственное место, где складываются формулы
расстояния станка от бровки: H₁ — наибольшая высота уступа по скважинам
первого ряда, Hs — проектная высота уступа (нет — H₁), ширина призмы
обрушения Bпр = Hs·(ctg γ − ctg α), расстояние s = roundup(max(2,0; Bпр),
0,1 м). Для инженера (не печатается): c_min = max(s − e, 0) и ЛСПП у подошвы
W = H·ctg α + c − d по каждой скважине первого ряда, где d — смещение оси на
уровне подошвы к откосу (у наклона к откосу d = H·ctg β, в массив — со
знаком минус).
"""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from typing import Any, Iterable, Literal, Mapping, Sequence

import shapely
from shapely.geometry import LineString, Point
from shapely.ops import nearest_points

from design.geometry import polygon_area
from design.lifecycle import designed_sha256
from design.mass_blast import ValidationIssue
from design.models import BlastDesign, Point3, in_main_grid
from design.pattern import front_row_ranks
from design.toe_line import crest_geometry, crest_polylines, floor_point, grid_steps_m, toe_line

DRILL_FORMULA_VERSION = "drill-v1"

# Минимум от бровки до опоры станка по ФНП 505 и форме паспорта, м.
MIN_CREST_DISTANCE_M = 2.0
# Скважина круче этого угла от горизонта — вертикальная: угол и азимут не печатаются.
VERTICAL_DIP_DEG = 89.95
# Сколько номеров скважин перечислять в предупреждении.
MAX_LISTED_HOLES = 10
# Первый ряд выше проектной высоты уступа Hs больше чем на столько — предупреждение, м.
BENCH_ABOVE_DESIGN_TOLERANCE_M = 0.5
# Сколько скважин с наибольшей высотой называть в предупреждении `bench_above_design`.
MAX_LISTED_TALL_HOLES = 5
_EPS = 1e-9

PASSPORT_STATUSES = ("draft", "approved", "drilled", "accepted")
DEFAULT_ACCEPTANCE = "исполнительная съёмка маркшейдерской службой заказчика"
DEFAULT_SITE_PREPARATION = "бульдозером под руководством горного мастера заказчика; приём площадки по акту"
# Должности без «ведущий» и без «(заказчик)»: на карьерах они называются по-разному.
DEFAULT_EXTRA_APPROVALS = ("маркшейдер", "геолог")
# Допуски по глубине скважины и положению устья по умолчанию, ± м.
DEFAULT_TOLERANCE_M = 0.3

# Профиль паспорта по умолчанию — тексты формы v0.7 (§2.1 спеки). Профиль
# справочника («Профиль паспорта на бурение») их переопределяет; в ревизию
# тексты попадают копией, PDF справочник не читает.
DEFAULT_SAFETY_ITEMS = (
    "Работать только по утверждённому паспорту; паспорт на бурение находится в кабине буровой установки.",
    "Перед началом работ осмотреть блок и бровку уступа: козырьки, навесы, заколы. При их наличии работу "
    "не начинать, сообщить мастеру.",
    "Устанавливать станок не ближе безопасного расстояния от верхней бровки до ближайшей точки опоры, "
    "указанного в паспорте (см. схему); на первом ряду продольная ось станка перпендикулярна бровке; "
    "под домкраты породу не подкладывать.",
    "Работа на первом ряду в тёмное время суток запрещена. Находиться в призме возможного обрушения запрещено.",
    "Движение буровой установки с поднятой мачтой разрешено только по спланированным участкам блока; при "
    "движении на неровных участках, при перегоне и под ЛЭП — только в транспортном положении, буровой "
    "инструмент снят или закреплён.",
    "Работа вблизи ЛЭП под напряжением — только по наряду-допуску с разрешением владельца ЛЭП.",
    "Запрещается забуриваться в старые стаканы.",
    "Не бурить при неисправной системе пылеподавления. Посторонним находиться в кабине и на площадках "
    "станка во время работы запрещено.",
    "Зону пробуренных скважин ограждать знаками (ГР.05.02). При заряжании вслед за бурением отводить станок "
    "от заряжаемых скважин не менее чем на 10 м.",
    "К работе допускаются машинисты, прошедшие инструктаж и ознакомленные с паспортом под подпись.",
)
DEFAULT_SAFETY_BASIS = "Основание: ФНП 505 пп. 989–991, 993; ФНП 494 п. 187."
DEFAULT_DRILLING_TECHNOLOGY = (
    "В раздробленных и обводнённых породах продувать скважину от устья до забоя многократно; штыб на "
    "забое — не более 20 см. Буровой снаряд поднимать с вращением и малым расходом воздуха."
)


@dataclass(frozen=True)
class DrillHoleRow:
    """Одна строка таблицы глубин паспорта."""

    number: str
    first_row: bool
    length_m: float
    dip_deg: float
    azimuth_deg: float | None
    subdrill_m: float
    bench_height_m: float
    collar: Point3
    # Смещение оси на уровне подошвы в сторону откоса, м: у вертикальной 0,
    # у наклона в массив — отрицательное; None — направление к откосу не
    # известно (нет бровки).
    face_shift_m: float | None = 0.0
    # Для плана на стр. 4 (PR 3): забой (отрезок наклонной в плане) и диаметр
    # скважины (кружок). None — строка из ревизии до PR 3.
    toe: Point3 | None = None
    diameter_mm: float | None = None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["collar"] = self.collar.to_dict()
        data["toe"] = self.toe.to_dict() if self.toe is not None else None
        return data


@dataclass(frozen=True)
class FirstRowCheck:
    h1_m: float | None
    prism_m: float | None
    s_m: float | None
    c_min_m: float | None
    c_m: float | None
    w_m: float | None
    w_max_m: float | None
    issues: list[ValidationIssue] = field(default_factory=list)
    # Высота уступа, по которой посчитан s (Hs), и её происхождение.
    hs_m: float | None = None
    hs_source: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "h1_m": self.h1_m,
            "prism_m": self.prism_m,
            "s_m": self.s_m,
            "c_min_m": self.c_min_m,
            "c_m": self.c_m,
            "w_m": self.w_m,
            "w_max_m": self.w_max_m,
            "hs_m": self.hs_m,
            "hs_source": self.hs_source,
            "issues": [issue.to_dict() for issue in self.issues],
        }


def _issue(level: Literal["error", "warning"], code: str, message: str, path: str = "") -> ValidationIssue:
    return ValidationIssue(level=level, code=code, message=message, path=path)


def _ctg(angle_deg: float) -> float:
    return math.cos(math.radians(angle_deg)) / math.sin(math.radians(angle_deg))


def round_up_tenth(value: float) -> float:
    """Округление вверх до 0,1 м: расстояние до бровки не занижается."""

    return math.ceil(value * 10 - 1e-9) / 10


def _listed(numbers: list[str]) -> str:
    shown = ", ".join(numbers[:MAX_LISTED_HOLES])
    rest = len(numbers) - MAX_LISTED_HOLES
    return f"{shown} и ещё {rest}" if rest > 0 else shown


# --- профиль паспорта -----------------------------------------------------


def _text(value: Any) -> str:
    return str(value).strip() if value is not None else ""


def drill_profile(record: Mapping[str, Any] | None, code: str = "") -> dict[str, Any]:
    """Тексты паспорта из записи профиля; пустое поле — текст по умолчанию."""

    record = record or {}
    items = [
        _text(item.get("text") if isinstance(item, Mapping) else item)
        for item in record.get("safety_items") or ()
    ]
    items = [item for item in items if item]
    return {
        "code": code,
        "safety_items": items or list(DEFAULT_SAFETY_ITEMS),
        "safety_basis": _text(record.get("safety_basis")) or DEFAULT_SAFETY_BASIS,
        "drilling_technology": _text(record.get("drilling_technology")) or DEFAULT_DRILLING_TECHNOLOGY,
    }


# --- скважины -------------------------------------------------------------


def _passport_holes(design: BlastDesign):
    # Бурятся все включённые скважины проекта, в том числе контурные.
    return [hole for hole in design.holes if hole.enabled]


def first_row_selection(design: BlastDesign) -> tuple[set[str], list[ValidationIssue]]:
    """Скважины первого ряда — у свободной поверхности — и предупреждения.

    Первый ряд — скважины основной сетки (`in_main_grid`) ранга 1 по
    `pattern.front_row_ranks`: в коридоре к верхней бровке перед ними нет
    другой скважины сетки. Так на изогнутой бровке, где ряды впереди первого
    стоят лишь у выступа, и в шаблоне «от тыла» с остатком эшелона у части
    столбцов первым рядом остаётся вся линия у откоса, а не только самый
    передний номер ряда. Шаги a, b — как у генератора (`grid_steps_m`).
    Отдельные стеночные ряды в отбор не входят. Без бровки или без рядов
    основной сетки первый ряд не определить — берутся скважины с наибольшим
    перебуром и предупреждение `first_row_guessed`.
    """

    holes = _passport_holes(design)
    grid = [hole for hole in holes if in_main_grid(hole)]
    crest = crest_geometry(design.contour)
    if crest is not None and grid:
        spacing_a, burden_b = grid_steps_m(design.pattern_params)
        ranks = front_row_ranks(
            [(hole.collar.x, hole.collar.y) for hole in grid], design.contour, spacing_a, burden_b
        )
        ids = {hole.id for hole, rank in zip(grid, ranks) if rank == 1}
        if ids:
            return ids, []
    if not holes:
        return set(), []
    deepest = max(hole.subdrill_m for hole in holes)
    ids = {hole.id for hole in holes if math.isclose(hole.subdrill_m, deepest, abs_tol=1e-6)}
    reason = "нет свободной поверхности" if crest is None else "нет скважин основной сетки у бровки"
    return ids, [
        _issue(
            "warning",
            "first_row_guessed",
            f"Первый ряд не определён по бровке ({reason}): взяты скважины с наибольшим перебуром "
            f"{deepest:.1f} м — {len(ids)} шт. Проверьте свободную поверхность блока.",
            "holes",
        )
    ]


def first_row_ids(design: BlastDesign) -> set[str]:
    return first_row_selection(design)[0]


def holes_for_passport(design: BlastDesign, first_row: set[str] | None = None) -> list[DrillHoleRow]:
    """Строки таблицы глубин в порядке таблицы скважин паспорта БВР."""

    first = first_row_ids(design) if first_row is None else first_row
    crest = crest_geometry(design.contour)
    rows: list[DrillHoleRow] = []
    for hole in _passport_holes(design):
        dip = 90.0 - hole.angle_deg
        rows.append(
            DrillHoleRow(
                number=hole.id,
                first_row=hole.id in first,
                length_m=hole.length_m,
                dip_deg=dip,
                azimuth_deg=None if dip >= VERTICAL_DIP_DEG else hole.azimuth_deg,
                subdrill_m=hole.subdrill_m,
                bench_height_m=hole.bench_height_m,
                collar=Point3(hole.collar.x, hole.collar.y, hole.collar.z),
                face_shift_m=_face_shift(hole, crest),
                toe=Point3(hole.toe.x, hole.toe.y, hole.toe.z),
                diameter_mm=hole.diameter_mm,
            )
        )
    return rows


def _face_shift(hole, crest) -> float | None:
    """Смещение оси на уровне подошвы к ближайшей точке верхней бровки, м.

    Проекция смещения «устье → точка оси на подошве» (`toe_line.floor_point`)
    на направление от устья к бровке: наклон к откосу уменьшает ЛСПП, вдоль
    бровки — не меняет, в массив — увеличивает.
    """

    floor_x, floor_y = floor_point(hole)
    dx, dy = floor_x - hole.collar.x, floor_y - hole.collar.y
    if math.hypot(dx, dy) < 1e-6:
        return 0.0
    if crest is None:
        return None
    _, nearest = nearest_points(Point(hole.collar.x, hole.collar.y), crest)
    to_x, to_y = nearest.x - hole.collar.x, nearest.y - hole.collar.y
    norm = math.hypot(to_x, to_y)
    if norm < 1e-6:
        return None  # устье на бровке: направление к откосу не определить
    return (dx * to_x + dy * to_y) / norm


# --- сводка ---------------------------------------------------------------


def _max_or_none(values: Iterable[float]) -> float | None:
    items = list(values)
    return max(items) if items else None


def summary(rows: list[DrillHoleRow], area_m2: float | None) -> dict[str, Any]:
    """Значения раздела «Параметры бурения» (страница 3 паспорта)."""

    count = len(rows)
    total = sum(row.length_m for row in rows)
    lengths = [row.length_m for row in rows]
    dips = [row.dip_deg for row in rows]
    bench_avg = sum(row.bench_height_m for row in rows) / count if count else None
    area = float(area_m2) if area_m2 else None
    volume = area * bench_avg if area is not None and bench_avg is not None else None
    return {
        "hole_count": count,
        "total_length_m": total,
        "length_min_m": min(lengths) if lengths else None,
        "length_max_m": max(lengths) if lengths else None,
        "dip_min_deg": min(dips) if dips else None,
        "dip_max_deg": max(dips) if dips else None,
        "vertical_only": all(row.azimuth_deg is None for row in rows),
        "bench_height_avg_m": bench_avg,
        "subdrill_first_row_m": _max_or_none(row.subdrill_m for row in rows if row.first_row),
        "subdrill_other_m": _max_or_none(row.subdrill_m for row in rows if not row.first_row),
        "block_area_m2": area,
        "block_volume_m3": volume,
        "yield_m3_per_m": volume / total if volume is not None and total > 0 else None,
    }


# --- первый ряд -----------------------------------------------------------


def first_row_check(
    rows: list[DrillHoleRow],
    alpha_deg: float | None,
    gamma_deg: float | None,
    e_m: float | None,
    c_m: float | None,
    w_max_m: float | None,
    *,
    hs_m: float | None = None,
    hs_source: str = "MANUAL_OVERRIDE",
) -> FirstRowCheck:
    """Расстояние s от бровки и проверка ЛСПП первого ряда.

    s считается по проектной высоте уступа Hs (`hs_m`; не задана — H₁,
    источник CALCULATED), W — по фактической высоте каждой скважины первого
    ряда. Принятое расстояние c до оси первого ряда не задано — берётся c_min.
    Ошибка только одна — нет углов α, γ: без них s не считается. Остальное —
    предупреждения: выпуск не блокируют, требуют отметки «просмотрено».
    """

    issues: list[ValidationIssue] = []
    first = [row for row in rows if row.first_row]
    if not first:
        issues.append(_issue("error", "first_row_empty", "В паспорте нет скважин первого ряда.", "holes"))
        return FirstRowCheck(None, None, None, None, c_m, None, w_max_m, issues, hs_m, hs_source if hs_m is not None else None)
    h1 = max(row.bench_height_m for row in first)
    if hs_m is None:
        hs_m, hs_source = h1, "CALCULATED"
    elif h1 > hs_m + BENCH_ABOVE_DESIGN_TOLERANCE_M + _EPS:
        tall = sorted(
            (row for row in first if row.bench_height_m > hs_m + BENCH_ABOVE_DESIGN_TOLERANCE_M + _EPS),
            key=lambda row: -row.bench_height_m,
        )
        issues.append(
            _issue(
                "warning",
                "bench_above_design",
                f"Высота уступа по первому ряду до {h1:.1f} м больше расчётной {hs_m:.1f} м "
                f"(скв. {', '.join(row.number for row in tall[:MAX_LISTED_TALL_HOLES])}) — "
                "проверить безопасное расстояние.",
                "bench_height_for_s_m",
            )
        )

    if alpha_deg is None or gamma_deg is None or gamma_deg >= alpha_deg or gamma_deg <= 0:
        issues.append(
            _issue(
                "error",
                "slope_angles_required",
                "Нужны угол откоса рабочего уступа α и угол устойчивого борта γ (γ < α): "
                "заполните их у объекта в справочнике или в паспорте.",
                "alpha_deg",
            )
        )
        return FirstRowCheck(h1, None, None, None, c_m, None, w_max_m, issues, hs_m, hs_source)

    prism = hs_m * (_ctg(gamma_deg) - _ctg(alpha_deg))
    s = round_up_tenth(max(MIN_CREST_DISTANCE_M, prism))

    if e_m is None:
        # Спека §2.2: без вылета e принимается e = 0 — c_min не занижается.
        issues.append(
            _issue(
                "warning",
                "axis_offset_missing",
                "Не задан вылет оси скважины e у станка: принято e = 0, минимум от бровки "
                "до оси первого ряда равен s. Внесите e в справочник станков.",
                "axis_offset_m",
            )
        )
    c_min = s - (e_m or 0.0)
    if c_min < 0.0:
        # Ось скважины не может стоять за бровкой: c_min < 0 занизил бы W.
        issues.append(
            _issue(
                "warning",
                "axis_offset_exceeds_s",
                f"Вылет оси e = {e_m:.1f} м больше расстояния s = {s:.1f} м: минимум от бровки "
                "до оси первого ряда принят 0. Проверьте вылет e у станка.",
                "axis_offset_m",
            )
        )
        c_min = 0.0
    accepted_c = c_m if c_m is not None else c_min
    if c_m is not None and c_min is not None and c_m < c_min - _EPS:
        issues.append(
            _issue(
                "warning",
                "first_row_too_close",
                f"Ось первого ряда в {c_m:.1f} м от бровки, а нужно не менее c_min = {c_min:.1f} м.",
                "first_row_offset_m",
            )
        )

    unknown = [row.number for row in first if row.face_shift_m is None]
    if unknown:
        issues.append(
            _issue(
                "warning",
                "first_row_tilt_direction_unknown",
                "Направление наклона к откосу не определено (нет бровки): ЛСПП посчитана как при "
                f"наклоне к откосу и может быть занижена; скважины: {_listed(unknown)}.",
                "holes",
            )
        )

    w: float | None = None
    if accepted_c is not None:  # c_min считается всегда, когда есть s
        burdens = [
            (row.bench_height_m * _ctg(alpha_deg) + accepted_c - _assumed_face_shift(row), row) for row in first
        ]
        w = max(item[0] for item in burdens)
        if w_max_m is not None and w > w_max_m + _EPS:
            over = sorted(
                (item for item in burdens if item[0] > w_max_m + _EPS),
                key=lambda item: (-item[1].bench_height_m, -item[0]),
            )
            issues.append(
                _issue(
                    "warning",
                    "first_row_burden",
                    f"ЛСПП первого ряда у подошвы W = {w:.2f} м больше допустимой {w_max_m:.2f} м; "
                    f"скважины: {_listed([item[1].number for item in over])}.",
                    "w_max_m",
                )
            )
    if w_max_m is None:
        issues.append(
            _issue(
                "warning",
                "w_max_missing",
                "Не задана допустимая ЛСПП Wпред: проверка ЛСПП первого ряда пропущена.",
                "w_max_m",
            )
        )
    return FirstRowCheck(h1, prism, s, c_min, accepted_c, w, w_max_m, issues, hs_m, hs_source)


def _assumed_face_shift(row: DrillHoleRow) -> float:
    """Смещение к откосу; не известно — как у наклона к откосу (формула §2.2)."""

    if row.face_shift_m is not None:
        return row.face_shift_m
    if row.dip_deg <= _EPS or row.dip_deg >= VERTICAL_DIP_DEG:
        return 0.0
    return row.bench_height_m * _ctg(row.dip_deg)


# --- исходные величины ----------------------------------------------------


def _number(source: Mapping[str, Any] | None, key: str) -> float | None:
    if not source:
        return None
    raw = source.get(key)
    if raw is None or raw == "":
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def _first_source(*candidates: tuple[float | None, str]) -> tuple[float | None, str | None]:
    for value, source in candidates:
        if value is not None:
            return value, source
    return None, None


def _design_alpha(design: BlastDesign) -> float | None:
    """Угол откоса уступа из проекта; 90° — значение модели по умолчанию, не угол."""

    face = design.contour.bench.face_angle_deg
    return face if face and not math.isclose(face, 90.0) else None


def resolve_inputs(
    design: BlastDesign,
    site: Mapping[str, Any] | None,
    rig: Mapping[str, Any] | None,
    payload: Mapping[str, Any] | None,
) -> tuple[dict[str, float | None], dict[str, str | None]]:
    """Величины расчёта и их происхождение (`FIELD_SOURCES`); None — нет нигде."""

    manual = "MANUAL_OVERRIDE"
    design_alpha = _design_alpha(design)
    vertices = design.contour.points_xy
    contour_area = polygon_area(vertices) if len(vertices) >= 3 else 0.0
    resolved = {
        # Объект раньше проекта: в интерфейсе у нового блока угол откоса по
        # умолчанию 75°, и он перекрыл бы техпроект объекта.
        "alpha_deg": _first_source(
            (_number(payload, "alpha_deg"), manual),
            (_number(site, "bench_face_angle_deg"), "REFERENCE"),
            (design_alpha, "DESIGN"),
        ),
        "gamma_deg": _first_source(
            (_number(payload, "gamma_deg"), manual),
            (_number(site, "stable_slope_angle_deg"), "REFERENCE"),
        ),
        "axis_offset_m": _first_source(
            (_number(payload, "axis_offset_m"), manual),
            (_number(rig, "axis_offset_m"), "REFERENCE"),
        ),
        "bench_height_for_s_m": _first_source(
            (_number(payload, "bench_height_for_s_m"), manual),
            (_number(site, "design_bench_height_m"), "REFERENCE"),
        ),
        "first_row_offset_m": _first_source((_number(payload, "first_row_offset_m"), manual)),
        "w_max_m": _first_source((_number(payload, "w_max_m"), manual)),
        "block_area_m2": _first_source(
            (_number(payload, "block_area_m2"), manual),
            (contour_area if contour_area > 0 else None, "DESIGN"),
        ),
    }
    values = {key: value for key, (value, _) in resolved.items()}
    provenance = {key: source for key, (_, source) in resolved.items()}
    return values, provenance


# --- снимок паспорта ------------------------------------------------------


def passport_context(
    design: BlastDesign,
    payload: Mapping[str, Any] | None,
    site: Mapping[str, Any] | None,
    rig: Mapping[str, Any] | None,
    profile: Mapping[str, Any] | None = None,
    profile_code: str = "",
    situation: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Снимок для проверки и ревизии: строки, сводка, проверка первого ряда, источники.

    Всё, что печатает PDF, — в снимке: сетка и диаметр в `summary`, тексты
    мер безопасности и технологии — в `profile`.
    """

    values, provenance = resolve_inputs(design, site, rig, payload)
    first_ids, issues = first_row_selection(design)
    design_alpha = _design_alpha(design)
    if (
        design_alpha is not None
        and values["alpha_deg"] is not None
        and provenance["alpha_deg"] != "DESIGN"
        and not math.isclose(design_alpha, values["alpha_deg"], abs_tol=0.05)
    ):
        issues.append(
            _issue(
                "warning",
                "alpha_mismatch",
                f"Угол откоса в проекте блока {design_alpha:g}° не совпадает с принятым "
                f"{values['alpha_deg']:g}° ({'паспорт' if provenance['alpha_deg'] == 'MANUAL_OVERRIDE' else 'справочник объекта'}): "
                "расстояние s посчитано по принятому.",
                "alpha_deg",
            )
        )
    rows = holes_for_passport(design, first_ids)
    if not rows:
        issues.append(_issue("error", "no_holes", "В проекте нет включённых скважин.", "holes"))
    upward = [row.number for row in rows if row.dip_deg <= _EPS]
    if upward:
        # Горизонтальную или восходящую скважину станок паспорта не бурит, и
        # высоты уступа у неё нет.
        issues.append(
            _issue(
                "error",
                "hole_not_downward",
                f"Скважины не направлены вниз (забой не ниже устья): {_listed(upward)}. Исправьте их в проекте.",
                "holes",
            )
        )
    data = summary(rows, values["block_area_m2"])
    data.update(_print_summary(design, payload))
    if data["bit_diameter_mm"] is None:
        issues.append(
            _issue(
                "warning",
                "bit_diameter_missing",
                "Не задан диаметр бурового инструмента: в паспорте будет «—».",
                "bit_diameter_mm",
            )
        )
    if data["block_area_m2"] is None:
        issues.append(
            _issue("warning", "block_area_missing", "Не задана площадь блока: объём и выход не посчитаны.", "block_area_m2")
        )
    check = first_row_check(
        rows,
        values["alpha_deg"],
        values["gamma_deg"],
        values["axis_offset_m"],
        values["first_row_offset_m"],
        values["w_max_m"],
        hs_m=values["bench_height_for_s_m"],
        hs_source=provenance["bench_height_for_s_m"] or "CALCULATED",
    )
    if provenance["bench_height_for_s_m"] is None and check.hs_m is not None:
        # Проектная высота не задана — s посчитан по H₁.
        values["bench_height_for_s_m"] = check.hs_m
        provenance["bench_height_for_s_m"] = "CALCULATED"
    if provenance["first_row_offset_m"] is None and check.c_m is not None:
        provenance["first_row_offset_m"] = "CALCULATED"
    for key in ("s_m", "c_min_m", "w_m"):
        provenance[key] = "CALCULATED" if getattr(check, key) is not None else None
    return {
        "formula_version": DRILL_FORMULA_VERSION,
        "design_id": design.design_id,
        "design_revision": design.revision,
        "design_sha256": design.designed_sha256 or designed_sha256(design),
        "inputs": values,
        "provenance": provenance,
        "holes": [row.to_dict() for row in rows],
        "summary": data,
        "first_row_check": check.to_dict(),
        "issues": [issue.to_dict() for issue in [*issues, *check.issues]],
        "profile": drill_profile(profile, profile_code),
        "plan": plan_geometry(design, situation),
        # СК объекта для `BLX_INFO` чертежа скважин (PR 4): координаты в
        # снимке уже в ней, без пересчёта.
        "crs": {
            "name": design.coordinate_system.name,
            "epsg": design.coordinate_system.epsg,
            "height_system": design.coordinate_system.height_system,
        },
    }


# Ситуация вокруг блока в снимке: габарит контура и устьев плюс запас — не
# меньше 60 м и не меньше 1,4 наибольшей стороны габарита. Поле листа (масштаб
# по наибольшей стороне) выходит за габарит не дальше чем на 0,7 этой стороны,
# поэтому ситуация не обрывается внутри поля; PDF обрезает её по полю сам.
PLAN_SITUATION_MARGIN_M = 60.0
PLAN_SITUATION_MARGIN_SHARE = 1.4


def _xy(points: Iterable[Sequence[float]]) -> list[list[float]]:
    return [[round(float(p[0]), 3), round(float(p[1]), 3)] for p in points]


def _finite_xy(point: Any) -> tuple[float, float] | None:
    try:
        x, y = float(point[0]), float(point[1])
    except (TypeError, ValueError, IndexError):
        return None
    return (x, y) if math.isfinite(x) and math.isfinite(y) else None


def _clipped_lines(points: Sequence[Sequence[float]], closed: bool, box: tuple[float, float, float, float]):
    # Точка без чисел или с NaN — линия ситуации не печатается (это фон плана).
    coords = [_finite_xy(p) for p in points]
    if any(p is None for p in coords):
        return []
    if closed and len(coords) > 2 and coords[0] != coords[-1]:
        coords.append(coords[0])
    if len(coords) < 2:
        return []
    clipped = shapely.clip_by_rect(LineString(coords), *box)
    if clipped.is_empty:
        return []
    parts = getattr(clipped, "geoms", [clipped])
    return [_xy(part.coords) for part in parts if part.geom_type == "LineString" and len(part.coords) >= 2]


def plan_geometry(design: BlastDesign, situation: Sequence[Mapping[str, Any]] | None = None) -> dict[str, Any]:
    """Геометрия плана на стр. 4 для снимка ревизии (TASK-015, PR 3).

    Контур блока, верхняя бровка (свободные поверхности), линия подошвы
    (`toe_line`: по углу или по съёмке) и ситуация TASK-013 в
    `PLAN_SITUATION_MARGIN_M` вокруг блока — плоские, до миллиметра.
    `situation` — слои `{"kind", "lines": [{"points", "closed"}]}`.
    """

    contour = design.contour
    ring = contour.points_xy if len(contour.vertices) >= 3 else []
    top = crest_polylines(contour) if ring else []
    toe = toe_line(contour) if top else None
    xs = [p[0] for p in ring] + [h.collar.x for h in _passport_holes(design)]
    ys = [p[1] for p in ring] + [h.collar.y for h in _passport_holes(design)]
    layers: list[dict[str, Any]] = []
    if xs and situation:
        m = max(PLAN_SITUATION_MARGIN_M, PLAN_SITUATION_MARGIN_SHARE * max(max(xs) - min(xs), max(ys) - min(ys)))
        box = (min(xs) - m, min(ys) - m, max(xs) + m, max(ys) + m)
        for layer in situation:
            lines = [
                {"points": part, "closed": False}
                for line in layer.get("lines") or ()
                for part in _clipped_lines(line.get("points") or (), bool(line.get("closed")), box)
            ]
            if lines:
                layers.append({"kind": str(layer.get("kind") or ""), "lines": lines})
    return {
        "contour": _xy(ring),
        "crest_top": [_xy(line) for line in top],
        "crest_toe": [_xy(line) for line in toe.polylines] if toe is not None else [],
        "toe_source": toe.source if toe is not None else None,
        "situation": layers,
    }


def _print_summary(design: BlastDesign, payload: Mapping[str, Any] | None) -> dict[str, float | None]:
    """Сетка a × b и диаметр инструмента для титула паспорта."""

    params = design.pattern_params or {}
    # Без введённого шага a (скважины из SHOTPlus) сетку не выдумывать: без
    # него `grid_steps_m` подставил бы шаг по умолчанию.
    grid_a, grid_b = grid_steps_m(params) if _number(params, "spacing_a_m") else (None, None)
    # Диаметр инструмента — только из паспорта: `Hole.diameter_mm` — диаметр
    # скважины с разбуриванием (или умолчание генератора), а не долота.
    return {"grid_a_m": grid_a, "grid_b_m": grid_b, "bit_diameter_mm": _number(payload, "bit_diameter_mm")}


def has_errors(issues: Iterable[Mapping[str, Any]]) -> bool:
    return any(issue.get("level") == "error" for issue in issues)


def warning_codes(issues: Iterable[Mapping[str, Any]]) -> list[str]:
    """Коды предупреждений без повторов, в порядке появления."""

    codes: list[str] = []
    for issue in issues:
        code = str(issue.get("code", ""))
        if issue.get("level") == "warning" and code not in codes:
            codes.append(code)
    return codes
