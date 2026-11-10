"""Раскладка паспорта на бурение (форма v0.7) из снимка ревизии.

Чистые данные: каждая строка, которую печатает PDF, уже отформатирована
здесь, поэтому состав и значения страниц проверяются без PDF. Источник —
только `drilling_passport_revisions.context`; ничего не пересчитывается.
Печатается s; c_min, W, Wпред и проверки первого ряда — нет (решения
владельца, §2 спеки).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from design.drilling_passport import DEFAULT_TOLERANCE_M, drill_profile
from design.reporting.drill import fmt
from design.reporting.drill.plan import PlanSheet, build_plan

ROWS_PER_COLUMN = 50
COLUMNS = 4
ACQUAINTANCE_ROWS = 9
MAX_EXTRA_APPROVALS = 2

WORK_ORDER_FIELDS = (
    ("Подготовка площадки", "site_preparation"),
    ("Вынос точек", "stakeout"),
    ("Порядок обуривания", "drilling_order"),
    ("Въезд и перегон", "access_route"),
    ("ЛЭП и кабели", "power_lines"),
    ("Соседние работы", "adjacent_works"),
    ("Приёмка блока", "acceptance"),
)


@dataclass(frozen=True)
class TitlePage:
    agreed: tuple[str, str, str]
    approved: tuple[str, str, str]
    passport_no: str
    object_name: str
    customer: str
    summary: tuple[tuple[str, str], ...]
    approvals: tuple[str, ...]
    acquaintance: tuple[tuple[str, str], ...]
    basis: str
    org_year: str


@dataclass(frozen=True)
class SafetyPage:
    items: tuple[str, ...]
    basis: str
    work_order: tuple[tuple[str, str], ...]
    s_text: str


@dataclass(frozen=True)
class DepthCell:
    number: str
    depth: str
    angle: str
    azimuth: str
    first_row: bool


@dataclass(frozen=True)
class DepthPage:
    params: tuple[tuple[str, str], ...] | None
    tolerances: str | None
    technology: str | None
    columns: tuple[tuple[DepthCell, ...], ...]
    total: str | None
    compiled_by: str | None


@dataclass(frozen=True)
class PassportLayout:
    header: str
    title: TitlePage
    safety: SafetyPage
    depth_pages: tuple[DepthPage, ...]
    blank_before_plan: bool
    page_count: int
    plan: PlanSheet


def _text(value: Any) -> str:
    return str(value).strip() if value is not None else ""


def _signer(payload: Mapping[str, Any], key: str) -> tuple[str, str, str]:
    signer = payload.get(key) or {}
    return (_text(signer.get("position")), _text(signer.get("organization")), _text(signer.get("name")))


def _joined(*parts: str) -> str:
    return " ".join(part for part in parts if part)


def _number(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def block_and_horizon(payload: Mapping[str, Any]) -> tuple[str, str]:
    """Блок и горизонт для печати (PDF и `BLX_INFO` чертежа): без пробелов по
    краям, горизонт — с «м»; вводят его и с единицей («+410,0 м») — вторую
    «м» не добавлять."""

    block, horizon = _text(payload.get("block")), _text(payload.get("horizon"))
    if horizon and not horizon.rstrip(" .").endswith("м"):
        horizon = f"{horizon} м"
    return block, horizon


def _title(passport: Mapping[str, Any], payload: Mapping[str, Any], summary: Mapping[str, Any]) -> TitlePage:
    block, horizon = block_and_horizon(payload)
    block_line = " / ".join(part for part in (block, horizon) if part) or fmt.DASH
    rig_number = _text(payload.get("rig_number"))
    rig = _joined(_text(payload.get("rig_name")), f"№ {rig_number}" if rig_number else "") or fmt.DASH
    grid_a, grid_b = summary.get("grid_a_m"), summary.get("grid_b_m")
    grid = f"{fmt.short(grid_a)} × {fmt.short(grid_b)}" if grid_a and grid_b else fmt.DASH
    diameter = _number(summary.get("bit_diameter_mm")) or _number(payload.get("bit_diameter_mm"))
    approvals = tuple(
        text for text in (_text(line) for line in (payload.get("extra_approvals") or ())[:MAX_EXTRA_APPROVALS]) if text
    )
    people = [
        (_text(person.get("name")), _text(person.get("position")))
        for person in payload.get("personnel") or ()
        if _text(person.get("name")) or _text(person.get("position"))
    ]
    # Строки согласования занимают место одной строки ознакомления.
    rows = max(ACQUAINTANCE_ROWS - (1 if approvals else 0), len(people))
    people += [("", "")] * (rows - len(people))
    approved = _signer(payload, "approved_by")
    year = _text(passport.get("passport_date"))[:4]
    basis = _text(payload.get("basis"))
    return TitlePage(
        agreed=_signer(payload, "agreed_by"),
        approved=approved,
        passport_no=_text(passport.get("passport_no")),
        object_name=_text(payload.get("object_name")),
        customer=_text(payload.get("customer")),
        summary=(
            ("Блок / горизонт", block_line),
            ("Начало бурения", fmt.date(payload.get("drilling_start"))),
            ("Окончание бурения (план)", fmt.date(payload.get("drilling_end"))),
            ("Буровая установка", rig),
            ("Диаметр инструмента, мм", fmt.short(diameter, 1)),
            ("Сетка скважин, м", grid),
            ("Скважин, шт", str(int(summary.get("hole_count") or 0))),
            ("Объём бурения, п. м", fmt.num(summary.get("total_length_m"), 1)),
        ),
        approvals=approvals,
        acquaintance=tuple(people),
        basis=f"Составлен на основании: {basis or fmt.DASH}",
        org_year=", ".join(part for part in (approved[1], f"{year} г." if year else "") if part),
    )


def _safety(payload: Mapping[str, Any], profile: Mapping[str, Any], check: Mapping[str, Any]) -> SafetyPage:
    return SafetyPage(
        items=tuple(profile["safety_items"]),
        basis=profile["safety_basis"],
        work_order=tuple((label, _text(payload.get(key)) or fmt.DASH) for label, key in WORK_ORDER_FIELDS),
        s_text=f"s = {fmt.num(check.get('s_m'), 1)} м",
    )


def _params(summary: Mapping[str, Any]) -> tuple[tuple[str, str], ...]:
    if summary.get("vertical_only", True):
        angle = "90° (вертикальные)"
    else:
        angle = f"{fmt.num_range(summary.get('dip_min_deg'), summary.get('dip_max_deg'), 0)}°"
    first, other = summary.get("subdrill_first_row_m"), summary.get("subdrill_other_m")
    # Пропущенная группа — «—», иначе одно число не понять, к какому ряду оно.
    subdrill = fmt.DASH if first is None and other is None else f"{fmt.short(first)} / {fmt.short(other)}"
    return (
        ("Угол наклона скважин", angle),
        ("Глубина скважин, м", fmt.num_range(summary.get("length_min_m"), summary.get("length_max_m"))),
        ("Перебур: 1-й ряд / остальные, м", subdrill),
        ("Средняя высота уступа, м", fmt.num(summary.get("bench_height_avg_m"), 1)),
        ("Площадь блока, м²", fmt.num(summary.get("block_area_m2"), 0)),
        ("Объём блока, м³", fmt.num(summary.get("block_volume_m3"), 0)),
        ("Выход горной массы, м³/п. м", fmt.num(summary.get("yield_m3_per_m"), 2)),
    )


def _cell(hole: Mapping[str, Any]) -> DepthCell:
    inclined = hole.get("azimuth_deg") is not None
    return DepthCell(
        number=_text(hole.get("number")),
        depth=fmt.num(hole.get("length_m"), 1),
        angle=fmt.num(hole.get("dip_deg"), 0) if inclined else "",
        azimuth=fmt.num(hole.get("azimuth_deg"), 0) if inclined else "",
        first_row=bool(hole.get("first_row")),
    )


def _depth_pages(
    context: Mapping[str, Any], payload: Mapping[str, Any], profile: Mapping[str, Any],
    rows_per_column: int, columns: int,
) -> tuple[DepthPage, ...]:
    summary = context.get("summary") or {}
    cells = [_cell(hole) for hole in context.get("holes") or ()]
    per_page = rows_per_column * columns
    chunks = [cells[start:start + per_page] for start in range(0, len(cells), per_page)] or [[]]
    tolerances = (
        f"глубина ±{fmt.short(_number(payload.get('tol_depth_m')) or DEFAULT_TOLERANCE_M)} м; "
        f"положение устья ±{fmt.short(_number(payload.get('tol_collar_m')) or DEFAULT_TOLERANCE_M)} м"
    )
    total = f"Всего: {len(cells)} скв., {fmt.num(summary.get('total_length_m'), 1)} п. м"
    pages = []
    for index, chunk in enumerate(chunks):
        first, last = index == 0, index == len(chunks) - 1
        pages.append(
            DepthPage(
                params=_params(summary) if first else None,
                tolerances=tolerances if first else None,
                technology=profile["drilling_technology"] if first else None,
                columns=tuple(
                    tuple(chunk[start:start + rows_per_column]) for start in range(0, per_page, rows_per_column)
                    if chunk[start:start + rows_per_column]
                ),
                total=total if last else None,
                compiled_by=_joined(*_signer(payload, "compiled_by")[::2]) if last else None,
            )
        )
    return tuple(pages)


def build_layout(
    context: Mapping[str, Any], *, rows_per_column: int = ROWS_PER_COLUMN, columns: int = COLUMNS
) -> PassportLayout:
    """Страницы паспорта: титул, меры безопасности, таблица глубин, место плана.

    План — всегда на чётной странице (оборот последнего листа): при нечётном
    числе страниц перед ним — пустая.
    """

    passport = context.get("passport") or {}
    payload = passport.get("payload") or {}
    summary = context.get("summary") or {}
    profile = context.get("profile") or drill_profile(None)
    depth_pages = _depth_pages(context, payload, profile, rows_per_column, columns)
    before_plan = 2 + len(depth_pages)
    blank = (before_plan + 1) % 2 == 1
    block, horizon = _text(payload.get("block")), _text(payload.get("horizon"))
    header = " · ".join(
        part for part in (
            f"Паспорт на бурение № {_text(passport.get('passport_no'))}",
            f"блок № {block}" if block else "",
            f"гор. {horizon}" if horizon else "",
        ) if part
    )
    return PassportLayout(
        header=header,
        title=_title(passport, payload, summary),
        safety=_safety(payload, profile, context.get("first_row_check") or {}),
        depth_pages=depth_pages,
        blank_before_plan=blank,
        page_count=before_plan + (1 if blank else 0) + 1,
        plan=build_plan(context),
    )
