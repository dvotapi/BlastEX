"""
BlastEX — веб-интерфейс расчёта параметров взрывания (Streamlit).
"""
import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt

from Blast import (
    RockProperties,
    ExplosiveProperties,
    TargetParams,
    BlastEngine,
)
from cost.geometry import (
    DETONATOR_DELAY_MS_OPTIONS,
    NSI_LENGTH_OPTIONS_M,
    block_geometry_table_rows,
    calculate_block_geometry,
    calculate_hole_geometry,
    hole_geometry_table_rows,
    normalize_initiation_config,
)
from cost.catalog import items_by_category
from cost.catalog_ui import get_active_catalog, render_catalog_tab
from cost.drilling_ui import get_drilling_price_per_m, render_drilling_tab
from cost.drilling import calculate_drilling_cost, drilling_table_rows
from cost.materials import (
    MaterialsSelection,
    auto_materials_selection,
    calculate_variable_materials,
)
from blast_hole_viz import draw_hole_section

# --- Справочники ВВ и пород ---

EXPLOSIVES = {
    "ПВВ Гранулит-РП": ExplosiveProperties("Гранулит-РП", 0.85, 3.76),
    "ПЭВВ ЭВЕРСИН Э-100": ExplosiveProperties("ЭВЕРСИН Э-100", 1.12, 2.99),
}

# Короткие подписи на схеме заряда
EXPLOSIVE_LABELS = {
    "ПВВ Гранулит-РП": "ГРАНУЛИТ-РП",
    "ПЭВВ ЭВЕРСИН Э-100": "ЭВЕРСИН",
}

ROCKS = {
    "Габбро-диабаз": RockProperties("Габбро-диабаз", 2.9, 168, 2.2),
    "Гранит": RockProperties("Гранит", 2.65, 150, 2.0),
    "Известняк": RockProperties("Известняк", 2.5, 80, 1.5),
    "Песчаник": RockProperties("Песчаник", 2.4, 100, 1.8),
}

CROWNS_MM = [130, 140, 152, 165]


def _inject_hole_viz_styles() -> None:
    st.markdown(
        """
<style>
div[data-testid="stHorizontalBlock"]:has(.hole-viz-tables) {
    gap: 1.1rem !important;
    align-items: flex-start !important;
}
div[data-testid="stHorizontalBlock"]:has(.hole-viz-tables) > div[data-testid="column"]:first-child {
    flex: 0 0 42% !important;
    width: 42% !important;
    display: flex !important;
    justify-content: flex-end !important;
    padding-right: 0.15rem !important;
}
div[data-testid="stHorizontalBlock"]:has(.hole-viz-tables) > div[data-testid="column"]:last-child {
    flex: 1 1 auto !important;
    width: auto !important;
    padding-left: 0.15rem !important;
}
.hole-viz-tables h4 {
    font-size: 14px;
    margin: 0.4rem 0 0.2rem;
    font-weight: 600;
}
.hole-viz-tables h4:first-child {
    margin-top: 0;
}
.hole-metrics-table {
    width: 100%;
    border-collapse: collapse;
    font-size: 14px;
    line-height: 1.4;
}
.hole-metrics-table th,
.hole-metrics-table td {
    padding: 0.22rem 0.4rem;
    border-bottom: 1px solid rgba(49, 51, 63, 0.12);
    vertical-align: top;
}
.hole-metrics-table th {
    font-weight: 600;
    text-align: left;
}
.hole-metrics-table td:last-child {
    text-align: right;
    white-space: nowrap;
}
</style>
        """,
        unsafe_allow_html=True,
    )


def _metrics_table_html(rows: list[tuple[str, str]]) -> str:
    body = "".join(
        f"<tr><td>{label}</td><td>{value}</td></tr>"
        for label, value in rows
    )
    return (
        "<table class='hole-metrics-table'>"
        "<thead><tr><th>Показатель</th><th>Значение</th></tr></thead>"
        f"<tbody>{body}</tbody></table>"
    )


def _render_hole_figure_and_tables(hole, block, *, label: str, initiation) -> None:
    fig_col, table_col = st.columns([0.44, 0.56], gap="medium")
    with fig_col:
        fig = draw_hole_section(hole, title=label, initiation=initiation)
        st.pyplot(fig, use_container_width=False)
        plt.close(fig)
    with table_col:
        st.markdown(
            f"""
<div class="hole-viz-tables">
  <h4>Скважина</h4>
  {_metrics_table_html(hole_geometry_table_rows(hole, initiation=initiation))}
  <h4>Блок</h4>
  {_metrics_table_html(block_geometry_table_rows(block))}
</div>
            """,
            unsafe_allow_html=True,
        )


def _render_hole_panel(
    *,
    panel_key: str,
    grid_a_m: float,
    grid_b_m: float,
    depth_m: float,
    overdrill_m: float,
    crown_mm: float,
    hole_oversize_coeff: float,
    block_volume_m3: float,
    additional_holes_pct: float,
    default_explosive_key: str,
    default_undercharge_m: float,
) -> None:
    """Одна колонка схемы: выбор ВВ, недозаряд, рисунок слева и таблица справа."""
    explosive_options = list(EXPLOSIVES.keys())
    default_idx = explosive_options.index(default_explosive_key)

    explosive_key = st.selectbox(
        "Тип ВВ",
        options=explosive_options,
        index=default_idx,
        key=f"viz_exp_{panel_key}",
    )
    undercharge_m = st.slider(
        "Недозаряд (верх скважины), м",
        min_value=0.0,
        max_value=max(0.0, depth_m - 0.5),
        value=min(default_undercharge_m, max(0.0, depth_m - 0.5)),
        step=0.1,
        key=f"viz_uc_{panel_key}",
    )

    si_col1, si_col2 = st.columns(2)
    with si_col1:
        intermediate_detonators_per_hole = st.selectbox(
            "Пром. детонаторы, шт/скв",
            options=[1, 2],
            index=0,
            key=f"viz_id_{panel_key}",
        )
    with si_col2:
        nsi_per_hole = st.selectbox(
            "Скважинное НСИ (дублирование)",
            options=[1, 2],
            index=0,
            format_func=lambda x: "1 устройство/скв" if x == 1 else "2 устройства/скв (дублирование)",
            key=f"viz_nsi_{panel_key}",
        )

    nsi_len_col1, nsi_len_col2 = st.columns(2)
    with nsi_len_col1:
        nsi_length_1_m = st.selectbox(
            "Длина скважинного НСИ-1, м",
            options=NSI_LENGTH_OPTIONS_M,
            index=NSI_LENGTH_OPTIONS_M.index(12.0),
            format_func=lambda x: f"{x:g}",
            key=f"viz_nsi_len1_{panel_key}",
        )
    with nsi_len_col2:
        if nsi_per_hole == 2:
            nsi_length_2_m = st.selectbox(
                "Длина скважинного НСИ-2, м",
                options=NSI_LENGTH_OPTIONS_M,
                index=NSI_LENGTH_OPTIONS_M.index(6.0),
                format_func=lambda x: f"{x:g}",
                key=f"viz_nsi_len2_{panel_key}",
            )
        else:
            nsi_length_2_m = 6.0

    detonator_delay_ms = st.selectbox(
        "Замедление, мс",
        options=DETONATOR_DELAY_MS_OPTIONS,
        index=DETONATOR_DELAY_MS_OPTIONS.index(500),
        key=f"viz_delay_{panel_key}",
    )

    initiation = normalize_initiation_config(
        intermediate_detonators_per_hole=intermediate_detonators_per_hole,
        nsi_per_hole=nsi_per_hole,
        nsi_length_1_m=nsi_length_1_m,
        nsi_length_2_m=nsi_length_2_m,
        detonator_delay_ms=detonator_delay_ms,
    )

    explosive = EXPLOSIVES[explosive_key]
    label = EXPLOSIVE_LABELS.get(explosive_key, explosive.name)
    hole = calculate_hole_geometry(
        grid_a_m=grid_a_m,
        grid_b_m=grid_b_m,
        depth_m=depth_m,
        overdrill_m=overdrill_m,
        undercharge_m=undercharge_m,
        crown_mm=crown_mm,
        hole_oversize_coeff=hole_oversize_coeff,
        explosive=explosive,
        explosive_label=label,
    )
    block = calculate_block_geometry(
        block_volume_m3=block_volume_m3,
        hole=hole,
        additional_holes_pct=additional_holes_pct,
        initiation=initiation,
    )

    _render_hole_figure_and_tables(hole, block, label=label, initiation=initiation)
    _render_variable_costs_panel(
        panel_key=panel_key,
        variant_title=label,
        explosive_key=explosive_key,
        block=block,
        initiation=initiation,
        hole_depth_m=depth_m,
    )


def _render_variable_costs_panel(
    *,
    panel_key: str,
    variant_title: str,
    explosive_key: str,
    block,
    initiation,
    hole_depth_m: float,
) -> None:
    st.markdown("**Переменные расходы**")

    catalog = get_active_catalog()
    materials_total = 0.0
    materials_per_m3 = 0.0

    st.markdown("**1.1 — ВВ, детонаторы, НСИ**")
    if not catalog:
        st.warning("Справочник пуст. Заполните вкладку «Справочник номенклатуры и цен».")
    else:
        auto = auto_materials_selection(
            catalog=catalog,
            explosive_key=explosive_key,
            initiation=initiation,
        )

        explosives = items_by_category(catalog, "explosive")
        detonators = items_by_category(catalog, "detonator")
        downhole_nsi_items = items_by_category(catalog, "downhole_nsi")
        surface_nsi_items = items_by_category(catalog, "surface_nsi")
        start_nsi_items = items_by_category(catalog, "start_nsi")

        sel_col1, sel_col2 = st.columns(2)
        with sel_col1:
            explosive_id = st.selectbox(
                "Номенклатура ВВ",
                options=[i.id for i in explosives],
                index=max(0, [i.id for i in explosives].index(auto.explosive_id))
                if auto.explosive_id in [i.id for i in explosives]
                else 0,
                format_func=lambda i: next(x.name for x in explosives if x.id == i),
                key=f"mat_vv_{panel_key}",
            )
            detonator_id = st.selectbox(
                "Пром. детонатор",
                options=[i.id for i in detonators],
                index=max(0, [i.id for i in detonators].index(auto.detonator_id))
                if auto.detonator_id in [i.id for i in detonators]
                else 0,
                format_func=lambda i: next(x.name for x in detonators if x.id == i),
                key=f"mat_det_{panel_key}",
            )
        with sel_col2:
            downhole_nsi1_id = st.selectbox(
                "НСИ скважинное",
                options=[i.id for i in downhole_nsi_items],
                index=max(0, [i.id for i in downhole_nsi_items].index(auto.downhole_nsi1_id))
                if auto.downhole_nsi1_id in [i.id for i in downhole_nsi_items]
                else 0,
                format_func=lambda i: next(x.name for x in downhole_nsi_items if x.id == i),
                key=f"mat_dh_nsi1_{panel_key}",
            )
            if initiation.nsi_per_hole == 2:
                nsi2_default = auto.downhole_nsi2_id or auto.downhole_nsi1_id
                downhole_nsi2_id = st.selectbox(
                    "НСИ скважинное (дубль)",
                    options=[i.id for i in downhole_nsi_items],
                    index=max(0, [i.id for i in downhole_nsi_items].index(nsi2_default))
                    if nsi2_default in [i.id for i in downhole_nsi_items]
                    else 0,
                    format_func=lambda i: next(x.name for x in downhole_nsi_items if x.id == i),
                    key=f"mat_dh_nsi2_{panel_key}",
                )
            else:
                downhole_nsi2_id = None

        surf_col1, surf_col2 = st.columns(2)
        with surf_col1:
            if surface_nsi_items:
                surface_nsi_id = st.selectbox(
                    "НСИ поверхностное",
                    options=[i.id for i in surface_nsi_items],
                    index=max(0, [i.id for i in surface_nsi_items].index(auto.surface_nsi_id))
                    if auto.surface_nsi_id in [i.id for i in surface_nsi_items]
                    else 0,
                    format_func=lambda i: next(x.name for x in surface_nsi_items if x.id == i),
                    key=f"mat_surface_nsi_{panel_key}",
                )
            else:
                surface_nsi_id = ""
        with surf_col2:
            if start_nsi_items:
                start_nsi_id = st.selectbox(
                    "НСИ стартовое",
                    options=[i.id for i in start_nsi_items],
                    index=max(0, [i.id for i in start_nsi_items].index(auto.start_nsi_id))
                    if auto.start_nsi_id in [i.id for i in start_nsi_items]
                    else 0,
                    format_func=lambda i: next(x.name for x in start_nsi_items if x.id == i),
                    key=f"mat_start_nsi_{panel_key}",
                )
            else:
                start_nsi_id = ""

        selection = MaterialsSelection(
            explosive_id=explosive_id,
            detonator_id=detonator_id,
            downhole_nsi1_id=downhole_nsi1_id,
            downhole_nsi2_id=downhole_nsi2_id,
            surface_nsi_id=surface_nsi_id,
            start_nsi_id=start_nsi_id,
        )
        result = calculate_variable_materials(
            block=block,
            initiation=initiation,
            catalog=catalog,
            selection=selection,
        )

        if not result.lines:
            st.info("Нет строк для расчёта переменных расходов 1.1.")
        else:
            table_rows = []
            for line in result.lines:
                qty = (
                    int(line.quantity)
                    if line.unit == "шт"
                    else round(line.quantity, 2)
                )
                table_rows.append({
                    "Раздел": line.section,
                    "Наименование": line.nomenclature,
                    "Кол-во": qty,
                    "Ед.": line.unit,
                    "Цена": round(line.price, 2),
                    "Сумма, руб": round(line.amount, 0),
                    "Источник кол-ва": line.source,
                })
            st.dataframe(pd.DataFrame(table_rows), use_container_width=True, hide_index=True)
            materials_total = result.total_amount
            materials_per_m3 = (
                materials_total / block.block_volume_m3 if block.block_volume_m3 > 0 else 0.0
            )
            st.caption(
                f"Итого 1.1: **{materials_total:,.0f} руб** ({materials_per_m3:.2f} руб/м³)"
            )

    st.markdown("**1.2 — бурение**")
    st.caption(
        "Потребность в п.м. из технического расчёта блока. "
        "Цена за п.м. — на вкладке «Расчёт стоимости бурения»."
    )
    drilling = calculate_drilling_cost(
        block=block,
        hole_depth_m=hole_depth_m,
        price_per_m=get_drilling_price_per_m(),
    )
    drill_rows = [{"Показатель": k, "Значение": v} for k, v in drilling_table_rows(drilling)]
    st.dataframe(pd.DataFrame(drill_rows), use_container_width=True, hide_index=True)
    drilling_per_m3 = (
        drilling.amount / block.block_volume_m3 if block.block_volume_m3 > 0 else 0.0
    )

    variable_total = materials_total + drilling.amount
    variable_per_m3 = (
        variable_total / block.block_volume_m3 if block.block_volume_m3 > 0 else 0.0
    )
    st.caption(
        f"**{variant_title}** — переменные расходы: "
        f"1.1 **{materials_total:,.0f} руб** + 1.2 **{drilling.amount:,.0f} руб** = "
        f"**{variable_total:,.0f} руб** ({variable_per_m3:.2f} руб/м³)"
    )


def _render_hole_visualization(
    *,
    selected: dict,
    target: TargetParams,
    overdrill_m: float,
    hole_oversize_coeff: float,
) -> None:
    st.subheader("Схема заряда скважины")
    _inject_hole_viz_styles()
    st.caption(
        "Сравнение вариантов заряжания при подобранной сетке. "
        "Меняйте тип ВВ, недозаряд, число промежуточных детонаторов и НСИ — пересчёт мгновенный."
    )

    crown_mm = selected["Коронка (мм)"]
    grid_parts = selected["Сетка a×b (м)"].split("×")
    grid_a_m = float(grid_parts[0].strip())
    grid_b_m = float(grid_parts[1].strip())
    depth_m = target.bench_height_m + overdrill_m

    param_col1, param_col2 = st.columns(2)
    with param_col1:
        block_volume_m3 = st.number_input(
            "Объём блока, м³",
            min_value=1000.0,
            max_value=500_000.0,
            value=30_000.0,
            step=1000.0,
            key="viz_block_volume",
        )
    with param_col2:
        additional_holes_pct = st.number_input(
            "Доп. скважины, %",
            min_value=0.0,
            max_value=20.0,
            value=3.0,
            step=0.5,
            key="viz_additional_holes_pct",
        ) / 100.0

    col_left, col_right = st.columns(2)
    with col_left:
        st.markdown("**Вариант 1**")
        _render_hole_panel(
            panel_key="left",
            grid_a_m=grid_a_m,
            grid_b_m=grid_b_m,
            depth_m=depth_m,
            overdrill_m=overdrill_m,
            crown_mm=crown_mm,
            hole_oversize_coeff=hole_oversize_coeff,
            block_volume_m3=block_volume_m3,
            additional_holes_pct=additional_holes_pct,
            default_explosive_key="ПВВ Гранулит-РП",
            default_undercharge_m=3.1,
        )
    with col_right:
        st.markdown("**Вариант 2**")
        _render_hole_panel(
            panel_key="right",
            grid_a_m=grid_a_m,
            grid_b_m=grid_b_m,
            depth_m=depth_m,
            overdrill_m=overdrill_m,
            crown_mm=crown_mm,
            hole_oversize_coeff=hole_oversize_coeff,
            block_volume_m3=block_volume_m3,
            additional_holes_pct=additional_holes_pct,
            default_explosive_key="ПЭВВ ЭВЕРСИН Э-100",
            default_undercharge_m=2.0,
        )


def _render_calc_page() -> None:
    st.caption("Выбор ВВ, породы и целевых параметров. Оптимизация удельного расхода по порогу негабарита.")

    col1, col2, col3 = st.columns(3)

    with col1:
        st.subheader("Взрывчатое вещество (ВВ)")
        explosive_key = st.selectbox(
            "ВВ",
            options=list(EXPLOSIVES.keys()),
            index=0,
            key="explosive",
        )
        explosive = EXPLOSIVES[explosive_key]
        with st.expander("Параметры выбранного ВВ"):
            st.write(f"**{explosive.name}**")
            st.write(f"- Плотность заряжания: {explosive.density_t_m3} т/м³")
            st.write(f"- Теплота взрыва: {explosive.power_mj_kg} МДж/кг")

    with col2:
        st.subheader("Порода")
        rock_key = st.selectbox(
            "Порода",
            options=list(ROCKS.keys()),
            index=0,
            key="rock",
        )
        rock = ROCKS[rock_key]
        with st.expander("Параметры выбранной породы"):
            st.write(f"**{rock.name}**")
            st.write(f"- Плотность: {rock.density_t_m3} т/м³")
            st.write(f"- Предел прочности на сжатие: {rock.ucs_mpa} МПа")
            st.write(f"- Трещиноватость: {rock.fissuring_ff}")

    with col3:
        st.subheader("Целевые параметры (TargetParams)")
        with st.expander("Настройки цели", expanded=True):
            lump_size_mm = st.number_input(
                "Кондиционный размер куска (негабарит), мм",
                min_value=100,
                max_value=1200,
                value=400,
                step=50,
            )
            bench_height_m = st.number_input(
                "Высота уступа, м",
                min_value=5.0,
                max_value=25.0,
                value=10.0,
                step=0.5,
            )
            overdrill_m = st.number_input(
                "Перебур, м",
                min_value=0.0,
                max_value=3.0,
                value=1.0,
                step=0.1,
            )
            hole_oversize_coeff = st.number_input(
                "Коэффициент разбуривания",
                min_value=1.0,
                max_value=1.15,
                value=1.05,
                step=0.01,
            )
            spacing_coeff_m = st.number_input(
                "Коэффициент сетки (a/W)",
                min_value=1.0,
                max_value=2.0,
                value=1.25,
                step=0.05,
            )
        target = TargetParams(
            lump_size_mm=lump_size_mm,
            hole_diameter_mm=0,
            overdrill_m=overdrill_m,
            hole_oversize_coeff=hole_oversize_coeff,
            spacing_coeff_m=spacing_coeff_m,
            bench_height_m=bench_height_m,
        )

    st.divider()

    max_oversize = st.slider(
        "Порог негабарита, % (целевой максимум)",
        min_value=1.0,
        max_value=15.0,
        value=5.0,
        step=0.5,
    )
    crowns = st.multiselect(
        "Диаметры коронок, мм",
        options=CROWNS_MM,
        default=CROWNS_MM,
    )

    if st.button("Рассчитать", type="primary"):
        if not crowns:
            st.warning("Выберите хотя бы один диаметр коронки.")
        else:
            engine = BlastEngine(rock, explosive, target)
            rows = []
            for d in sorted(crowns):
                res = engine.optimize_blast(d, max_oversize_threshold=max_oversize)
                a_m = round(target.spacing_coeff_m * res["W_m"], 2)
                b_m = res["W_m"]
                rows.append({
                    "Коронка (мм)": d,
                    "Уд. расход (кг/м³)": res["q"],
                    "ЛНС W (м)": res["W_m"],
                    "Сетка a×b (м)": f"{a_m} × {b_m}",
                    "x50 (мм)": res["x50_mm"],
                    "Негабарит (%)": res["oversize_pct"],
                })
            df = pd.DataFrame(rows)
            st.session_state["blast_results"] = rows
            st.session_state["blast_context"] = {
                "target": target,
                "overdrill_m": overdrill_m,
                "hole_oversize_coeff": hole_oversize_coeff,
                "rock_name": rock.name,
                "explosive_name": explosive.name,
                "max_oversize": max_oversize,
            }

    if "blast_results" in st.session_state:
        ctx = st.session_state["blast_context"]
        rows = st.session_state["blast_results"]
        df = pd.DataFrame(rows)

        st.subheader("Результаты оптимизации")
        st.dataframe(df, use_container_width=True, hide_index=True)
        st.caption(
            f"Порог негабарита: < {ctx['max_oversize']}%. "
            f"ВВ оптимизации: {ctx['explosive_name']}, порода: {ctx['rock_name']}."
        )

        st.divider()
        crown_labels = [
            f"Ø {r['Коронка (мм)']} мм — сетка {r['Сетка a×b (м)']} — q={r['Уд. расход (кг/м³)']}"
            for r in rows
        ]
        selected_idx = st.selectbox(
            "Вариант для схемы заряда",
            options=range(len(rows)),
            format_func=lambda i: crown_labels[i],
            key="viz_crown_select",
        )
        _render_hole_visualization(
            selected=rows[selected_idx],
            target=ctx["target"],
            overdrill_m=ctx["overdrill_m"],
            hole_oversize_coeff=ctx["hole_oversize_coeff"],
        )


def main():
    st.set_page_config(page_title="BlastEX", page_icon="💥", layout="wide")
    st.title("💥 BlastEX — расчёт параметров взрывания")

    tab_calc, tab_drilling, tab_catalog = st.tabs(
        ["Расчёт", "Расчёт стоимости бурения", "Справочник номенклатуры и цен"]
    )
    with tab_catalog:
        render_catalog_tab()
    with tab_drilling:
        render_drilling_tab()
    with tab_calc:
        _render_calc_page()


if __name__ == "__main__":
    main()
