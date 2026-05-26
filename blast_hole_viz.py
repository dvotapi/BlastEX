"""
Визуализация сечения скважины (столбик: недозаряд + заряд), как в Excel-смете.
"""
from __future__ import annotations

import matplotlib.pyplot as plt
from matplotlib.figure import Figure

from blast_hole import HoleChargeResult
from cost.geometry import geometry_table_rows
from cost.models import InitiationConfig

# Цвета в духе Excel-сметы
CHARGE_COLORS = {
    "Гранулит": "#FAF3E0",   # ПВВ Гранулит-РП — молочно-сливочный
    "ЭВЕРСИН": "#E85555",   # ПЭВВ ЭВЕРСИН Э-100 — насыщенный светло-красный
    "Э-100": "#E85555",
}
DEFAULT_CHARGE_COLOR = "#4472C4"
STEMMING_COLOR = "#595959"
HOLE_BG_COLOR = "#9E9E9E"  # фон скважины вокруг заряда
CHARGE_MASS_TEXT_COLOR = "#333333"
NSI_COLOR = "#2E7D32"
NSI_COLOR_2 = "#1565C0"
NSI_EXIT_ABOVE_COLLAR_M = 2.0
NSI_BEND_LEFT_M = 0.14
DETONATOR_COLOR = "#C00000"
DETONATOR_EDGE = "#7F0000"
DEPTH_GRID_STEP_M = 0.5


def _charge_color(label: str, name: str) -> str:
    for key, color in CHARGE_COLORS.items():
        if key in label or key in name:
            return color
    return DEFAULT_CHARGE_COLOR


def _booster_depth_m(
    *,
    depth_m: float,
    overdrill_m: float,
    charge_length_m: float,
    nsi_length_m: float,
) -> float:
    """Глубина боевика от забоя: не ниже перебура + 0,5 м."""
    min_depth_m = overdrill_m + 0.5
    from_collar_m = depth_m - nsi_length_m
    return max(min_depth_m, min(from_collar_m, charge_length_m - 0.15))


def _nsi_waveguides(
    x: float,
    width: float,
    depth_m: float,
    overdrill_m: float,
    charge_length_m: float,
    initiation: InitiationConfig,
) -> list[tuple[list[float], list[float], float, str, str]]:
    """Траектории НСИ: (xs, ys, y_booster, label, color)."""
    x_center = x + width / 2
    nsi1_offset = width * 0.012
    nsi2_offset = width * 0.055
    collar_y = depth_m
    top_y = depth_m + NSI_EXIT_ABOVE_COLLAR_M

    specs: list[tuple[float, float, str, str]] = [
        (initiation.nsi_length_1_m, -nsi1_offset, "1", NSI_COLOR),
    ]
    if initiation.nsi_per_hole == 2:
        specs.append((initiation.nsi_length_2_m, nsi2_offset, "2", NSI_COLOR_2))

    guides: list[tuple[list[float], list[float], float, str, str]] = []
    for nsi_length_m, x_shift, label, color in specs:
        x_axis = x_center + x_shift
        bend_x = x_axis - NSI_BEND_LEFT_M
        y_booster = _booster_depth_m(
            depth_m=depth_m,
            overdrill_m=overdrill_m,
            charge_length_m=charge_length_m,
            nsi_length_m=nsi_length_m,
        )
        xs = [bend_x, x_axis, x_axis, x_axis]
        ys = [top_y, top_y, collar_y, y_booster]
        guides.append((xs, ys, y_booster, label, color))
    return guides


def _draw_initiation(
    ax,
    *,
    x: float,
    width: float,
    depth_m: float,
    overdrill_m: float,
    charge_length_m: float,
    initiation: InitiationConfig | None,
) -> None:
    if initiation is None or charge_length_m <= 0:
        return

    waveguides = _nsi_waveguides(
        x,
        width,
        depth_m,
        overdrill_m,
        charge_length_m,
        initiation,
    )
    for xs, ys, y_booster, label, color in waveguides:
        ax.plot(
            xs,
            ys,
            color=color,
            linewidth=2.0,
            solid_capstyle="round",
            solid_joinstyle="round",
            zorder=4,
        )
        ax.scatter(
            [xs[0]],
            [ys[0]],
            s=14,
            color=color,
            edgecolors="white",
            linewidths=0.6,
            zorder=5,
        )
        ax.text(
            xs[1] + width * 0.12,
            (ys[2] + y_booster) / 2,
            label,
            ha="left",
            va="center",
            fontsize=5.5,
            color=color,
            fontweight="bold",
            zorder=6,
        )

    booster_points = sorted(
        ((guide[0][2], guide[2], guide[3]) for guide in waveguides),
        key=lambda item: item[1],
        reverse=True,
    )
    if initiation.intermediate_detonators_per_hole == 1:
        booster_points = booster_points[-1:]
    else:
        booster_points = booster_points[: initiation.intermediate_detonators_per_hole]

    det_height = min(0.22, charge_length_m * 0.08)
    for idx, (det_x, y_center, _label) in enumerate(booster_points, start=1):
        y_center = max(0.0, min(y_center, charge_length_m - det_height / 2))
        det = plt.Rectangle(
            (det_x - width * 0.18, y_center - det_height / 2),
            width * 0.36,
            det_height,
            facecolor=DETONATOR_COLOR,
            edgecolor=DETONATOR_EDGE,
            linewidth=0.8,
            zorder=5,
        )
        ax.add_patch(det)
        ax.text(
            det_x,
            y_center,
            f"Д{idx}",
            ha="center",
            va="center",
            fontsize=5,
            color="white",
            fontweight="bold",
            zorder=6,
        )


def _draw_depth_grid(
    ax,
    *,
    x: float,
    width: float,
    y_max: float,
    y_min: float = 0.0,
) -> None:
    """Тонкая горизонтальная сетка глубины с шагом 0,5 м."""
    x_left = x + width * 0.04
    x_right = x + width * 0.96
    depth = y_min
    while depth <= y_max + 1e-9:
        is_meter = abs(depth * 2 - round(depth * 2)) < 1e-9
        ax.plot(
            [x_left, x_right],
            [depth, depth],
            color="#FFFFFF",
            linewidth=0.55 if is_meter else 0.35,
            alpha=0.32 if is_meter else 0.2,
            zorder=3,
            solid_capstyle="butt",
        )
        depth += DEPTH_GRID_STEP_M


def draw_hole_section(
    result: HoleChargeResult,
    *,
    title: str = "",
    initiation: InitiationConfig | None = None,
) -> Figure:
    """Рисует вертикальный столбик скважины и возвращает Figure."""
    fig, ax = plt.subplots(figsize=(1.65, 4.0))
    fig.patch.set_facecolor(HOLE_BG_COLOR)
    ax.set_facecolor(HOLE_BG_COLOR)

    x = 0.15
    width = 0.16
    charge_color = _charge_color(result.explosive_label, result.explosive_name)

    # Фон скважины на всю глубину
    ax.bar(
        x,
        result.depth_m,
        width,
        color=HOLE_BG_COLOR,
        edgecolor="white",
        linewidth=1.5,
        zorder=1,
    )

    # Недозаряд (верх)
    if result.undercharge_m > 0:
        ax.bar(
            x,
            result.undercharge_m,
            width,
            bottom=result.charge_length_m,
            color=STEMMING_COLOR,
            edgecolor="white",
            linewidth=1.5,
            zorder=2,
        )
        ax.text(
            x + width / 20, # центрируем текст по горизонтали
            result.charge_length_m + result.undercharge_m / 2, # центрируем текст по вертикали
            f"{result.undercharge_m:.1f}", # текст недозаряда
            ha="center", # центрируем текст по горизонтали
            va="center", # центрируем текст по вертикали
            color="white",
            fontsize=7,
            fontweight="normal", # жирный текст
        )

    # Заряд (низ)
    ax.bar(
        x,
        result.charge_length_m,
        width,
        color=charge_color,
        edgecolor="white",
        linewidth=1.5,
        zorder=2,
    )
    mass_x = x + width + 0.035 if initiation else x + width / 20
    mass_ha = "left" if initiation else "center"
    ax.text(
        mass_x,
        result.charge_length_m / 2,
        f"{result.charge_mass_kg:.0f}",
        ha=mass_ha,
        va="center",
        color=CHARGE_MASS_TEXT_COLOR,
        fontsize=7 if not initiation else 6,
        fontweight="normal",
        zorder=3,
    )
    ax.text(
        x + width / 20,
        -0.35,
        f"{result.charge_length_m:.1f}",
        ha="center",
        va="top",
        fontsize=7,
        color="#333333",
    )

    y_top = result.depth_m + NSI_EXIT_ABOVE_COLLAR_M if initiation else result.depth_m
    _draw_depth_grid(
        ax,
        x=x,
        width=width,
        y_max=y_top,
    )

    _draw_initiation(
        ax,
        x=x,
        width=width,
        depth_m=result.depth_m,
        overdrill_m=result.overdrill_m,
        charge_length_m=result.charge_length_m,
        initiation=initiation,
    )

    # Глубина слева
    ax.annotate(
        "",
        xy=(-0.05, 0),
        xytext=(-0.05, result.depth_m),
        arrowprops=dict(arrowstyle="<->", color="#333333", lw=1.2),
    )
    ax.text(
        -0.12,
        result.depth_m / 2,
        f"{result.depth_m:.1f}",
        ha="right",
        va="center",
        fontsize=7,
        fontweight="normal",
    )

    y_top = result.depth_m + NSI_EXIT_ABOVE_COLLAR_M if initiation else result.depth_m + 0.4
    ax.set_xlim(-0.38 if initiation else -0.25, 0.52 if initiation else 0.48)
    ax.set_ylim(-0.6, y_top + 0.35)
    ax.set_xticks([])
    ax.set_yticks([])
    for spine in ax.spines.values():
        spine.set_visible(False)

    if title:
        ax.set_title(title.upper(), fontsize=7, pad=8)

    fig.tight_layout()
    return fig


def metrics_table_rows(result: HoleChargeResult, block=None) -> list[tuple[str, str]]:
    """Строки таблицы показателей для Streamlit."""
    return geometry_table_rows(result, block)
