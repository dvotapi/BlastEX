"""
BlastEX — веб-интерфейс расчёта параметров взрывания (Streamlit).
"""
import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt

from Blast import (
    TargetParams,
    BlastEngine,
    CROWNS_MM,
)
from cost.geometry import (
    DETONATOR_DELAY_MS_OPTIONS,
    NSI_LENGTH_OPTIONS_M,
    block_geometry_table_rows,
    build_manual_block_input,
    calculate_block_geometry,
    calculate_hole_geometry,
    contour_hole_table_rows,
    drilling_block_table_rows,
    drilling_hole_table_rows,
    hole_geometry_table_rows,
    normalize_initiation_config,
)
from cost.catalog import items_by_category
from cost.admin_auth import render_admin_panel
from cost.catalog_ui import get_active_catalog
from cost.references_tab_ui import render_references_tab
from cost.references_store import get_explosives_dict, get_rocks_dict
from cost.explosive_data import DEFAULT_EXPLOSIVE_KEY
from cost.rock_data import DEFAULT_ROCK_NAME
from cost.drilling_ui import render_drilling_tab
from cost.drilling import drilling_table_rows
from cost.engine import CostEngine
from cost.materials import MaterialsSelection, auto_materials_selection
from cost.fixed_costs import SECTION_ORDER
from cost.labor_ui import render_labor_tab
from cost.models import BlockCalculationInput
from cost.persistence_ui import get_active_scenario_id, init_workspace, render_workspace_toolbar
from cost.scenarios import DEFAULT_SCENARIO_ID, ScenarioCalcProfile, get_scenario_calc_profile, get_scenario_template
from blast_hole_viz import draw_hole_section

# --- Справочники ВВ (см. вкладку «Справочники») ---

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


def _render_hole_figure_and_tables(
    hole,
    block,
    *,
    label: str,
    initiation,
    show_charge_design: bool = True,
    explosive_basis: str = "per_m3",
) -> None:
    if show_charge_design:
        fig_col, table_col = st.columns([0.44, 0.56], gap="medium")
        with fig_col:
            fig = draw_hole_section(hole, title=label, initiation=initiation)
            st.pyplot(fig, use_container_width=False)
            plt.close(fig)
        with table_col:
            if explosive_basis == "per_m":
                hole_rows = contour_hole_table_rows(hole, initiation=initiation)
            else:
                hole_rows = hole_geometry_table_rows(hole, initiation=initiation)
            st.markdown(
                f"""
<div class="hole-viz-tables">
  <h4>Скважина</h4>
  {_metrics_table_html(hole_rows)}
  <h4>Блок</h4>
  {_metrics_table_html(block_geometry_table_rows(block))}
</div>
                """,
                unsafe_allow_html=True,
            )
    else:
        st.markdown(
            f"""
<div class="hole-viz-tables">
  <h4>Скважина</h4>
  {_metrics_table_html(drilling_hole_table_rows(hole))}
  <h4>Блок</h4>
  {_metrics_table_html(drilling_block_table_rows(block))}
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
    show_charge_design: bool = True,
    explosive_basis: str = "per_m3",
    show_cost_panel: bool = True,
) -> None:
    """Одна колонка: опционально схема заряда и смета."""
    explosive_key = default_explosive_key
    undercharge_m = min(default_undercharge_m, max(0.0, depth_m - 0.5))

    if show_charge_design:
        explosives = get_explosives_dict(st.session_state)
        explosive_options = list(explosives.keys())
        default_idx = (
            explosive_options.index(default_explosive_key)
            if default_explosive_key in explosive_options
            else 0
        )

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
    else:
        initiation = normalize_initiation_config(
            intermediate_detonators_per_hole=1,
            nsi_per_hole=1,
            nsi_length_1_m=12.0,
            nsi_length_2_m=6.0,
            detonator_delay_ms=500,
        )
        undercharge_m = max(0.0, depth_m - 0.5)

    explosive_item = get_explosives_dict(st.session_state)[explosive_key]
    explosive = explosive_item.properties
    label = explosive_item.label
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

    _render_hole_figure_and_tables(
        hole,
        block,
        label=label,
        initiation=initiation,
        show_charge_design=show_charge_design,
        explosive_basis=explosive_basis,
    )
    if show_cost_panel:
        _render_variable_costs_panel(
            panel_key=panel_key,
            variant_title=label if show_charge_design else "Бурение",
            explosive_key=explosive_key,
            hole=hole,
            block=block,
            initiation=initiation,
            hole_depth_m=depth_m,
        )


def _render_variable_costs_panel(
    *,
    panel_key: str,
    variant_title: str,
    explosive_key: str,
    hole,
    block,
    initiation,
    hole_depth_m: float,
    block_data_override: BlockCalculationInput | None = None,
) -> None:
    engine = CostEngine()
    scenario_id = st.session_state.get("active_scenario_id", DEFAULT_SCENARIO_ID)
    scenario = get_scenario_template(scenario_id)
    scenario_name = scenario.name if scenario else "—"
    work_object_name = st.session_state.get("active_work_object_name", "")

    show_materials = engine.scenario_supports_module(st.session_state, "materials")
    show_drilling = engine.scenario_supports_module(st.session_state, "drilling")
    show_fixed = engine.scenario_supports_module(st.session_state, "fixed")
    show_manufacturing = engine.scenario_supports_module(st.session_state, "manufacturing")
    show_labor = engine.scenario_supports_module(st.session_state, "labor")

    st.markdown(f"**Смета затрат — сценарий «{scenario_name}»**")
    if work_object_name:
        st.caption(f"Объект работ: **{work_object_name}** (мобилизация и цена ДТ учитываются в бурении).")

    production_tons = 0.0
    if show_manufacturing:
        production_tons = st.number_input(
            "Объём производства ЭВВ, т",
            min_value=0.0,
            value=float(st.session_state.get(f"production_tons_{panel_key}", 100.0)),
            step=10.0,
            key=f"production_tons_{panel_key}",
        )

    catalog = get_active_catalog()
    selection: MaterialsSelection | None = None

    if show_materials and catalog:
        st.markdown("**1.1 — ВВ, детонаторы, НСИ**")
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
            surface_nsi_id = ""
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
        with surf_col2:
            start_nsi_id = ""
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

        selection = MaterialsSelection(
            explosive_id=explosive_id,
            detonator_id=detonator_id,
            downhole_nsi1_id=downhole_nsi1_id,
            downhole_nsi2_id=downhole_nsi2_id,
            surface_nsi_id=surface_nsi_id,
            start_nsi_id=start_nsi_id,
        )
    elif show_materials:
        st.warning("Справочник пуст. Заполните вкладку «Справочник номенклатуры и цен».")

    block_data = None
    if block_data_override is not None:
        block_data = BlockCalculationInput(
            hole=block_data_override.hole,
            block=block_data_override.block,
            initiation=block_data_override.initiation,
            explosive_key=block_data_override.explosive_key or explosive_key,
            hole_depth_m=block_data_override.hole_depth_m,
            materials_selection=selection or block_data_override.materials_selection,
            production_volume_tons=(
                production_tons if show_manufacturing else block_data_override.production_volume_tons
            ),
        )
        hole = block_data.hole
        block = block_data.block
    elif not show_manufacturing or show_drilling or (show_materials and not show_manufacturing):
        block_data = BlockCalculationInput(
            hole=hole,
            block=block,
            initiation=initiation,
            explosive_key=explosive_key,
            hole_depth_m=hole_depth_m,
            materials_selection=selection,
            production_volume_tons=production_tons,
        )
    elif show_manufacturing:
        block_data = BlockCalculationInput(
            hole=hole,
            block=block,
            initiation=initiation,
            explosive_key=explosive_key,
            hole_depth_m=hole_depth_m,
            materials_selection=selection,
            production_volume_tons=production_tons,
        )

    cost_result = engine.calculate(
        session_state=st.session_state,
        block_data=block_data,
        materials_selection=selection,
        production_volume_tons=production_tons,
        explosive_id=selection.explosive_id if selection else None,
    )

    if show_manufacturing and cost_result.materials_cost:
        st.markdown("**Материалы производства ЭВВ**")
        mat_rows = []
        for line in cost_result.materials_cost.lines:
            mat_rows.append({
                "Раздел": line.section,
                "Наименование": line.nomenclature,
                "Кол-во": round(line.quantity, 1),
                "Ед.": line.unit,
                "Сумма, руб": round(line.amount, 0),
            })
        st.dataframe(pd.DataFrame(mat_rows), use_container_width=True, hide_index=True)

    if show_materials and not show_manufacturing and cost_result.materials_cost:
        st.markdown("**1.1 — ВВ, детонаторы, НСИ**")
        if not cost_result.materials_cost.lines:
            st.info("Нет строк для расчёта переменных расходов 1.1.")
        else:
            table_rows = []
            for line in cost_result.materials_cost.lines:
                qty = int(line.quantity) if line.unit == "шт" else round(line.quantity, 2)
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
            per_m3 = (
                cost_result.materials_cost.total_amount / block.block_volume_m3
                if block.block_volume_m3 > 0
                else 0.0
            )
            st.caption(
                f"Итого 1.1: **{cost_result.materials_cost.total_amount:,.0f} руб** "
                f"({per_m3:.2f} руб/м³)"
            )
    elif show_materials and not show_manufacturing:
        st.info("Раздел 1.1 отключён или нет данных.")

    if show_drilling and cost_result.drilling_total_cost:
        st.markdown("**1.2 — бурение**")
        st.caption(
            "Цена за п.м. пересчитана с учётом объекта работ "
            f"({work_object_name or '—'}): мобилизация и ДТ."
        )
        drill_rows = [
            {"Показатель": k, "Значение": v}
            for k, v in drilling_table_rows(cost_result.drilling_total_cost)
        ]
        st.dataframe(pd.DataFrame(drill_rows), use_container_width=True, hide_index=True)
        if cost_result.drilling_unit_cost:
            st.caption(
                f"Калькулятор бурения: **{cost_result.drilling_unit_cost.price_per_m:.2f} руб/п.м.** "
                f"(доля ДТ {cost_result.drilling_unit_cost.diesel_share * 100:.1f}%)"
            )
    elif show_drilling:
        st.info("Раздел 1.2 отключён для текущего сценария.")

    variable_parts = []
    if cost_result.materials_cost and (show_materials or show_manufacturing):
        variable_parts.append(f"материалы **{cost_result.materials_cost.total_amount:,.0f} руб**")
    if cost_result.drilling_total_cost and show_drilling:
        variable_parts.append(f"1.2 **{cost_result.drilling_total_cost.amount:,.0f} руб**")
    if variable_parts and block.block_volume_m3 > 0:
        st.caption(
            f"**{variant_title}** — переменные: {' + '.join(variable_parts)} = "
            f"**{cost_result.variable_total_rub:,.0f} руб** "
            f"({cost_result.variable_total_rub / block.block_volume_m3:.2f} руб/м³)"
        )

    if show_labor and cost_result.labor_fot:
        st.markdown("**2.3 — ФОТ**")
        st.caption(f"Итого ФОТ: **{cost_result.labor_fot.total_fot:,.0f} руб**")

    if show_fixed:
        st.divider()
        st.markdown("**Постоянные расходы**")
        if cost_result.fixed_costs and cost_result.fixed_costs.lines:
            vol = block.block_volume_m3 if block.block_volume_m3 > 0 else 1.0
            fixed_rows = []
            for line in cost_result.fixed_costs.lines:
                fixed_rows.append({
                    "Раздел": f"{line.section} — {line.section_title}",
                    "Наименование": line.name,
                    "Сумма, руб": round(line.amount, 0),
                    "руб/м³": round(line.amount / vol, 2),
                })
            st.dataframe(pd.DataFrame(fixed_rows), use_container_width=True, hide_index=True)
            summary_parts = []
            for section in SECTION_ORDER:
                section_total = cost_result.fixed_costs.section_totals.get(section, 0.0)
                if section_total <= 0:
                    continue
                section_per_m3 = section_total / vol if block.block_volume_m3 > 0 else 0.0
                summary_parts.append(
                    f"{section} **{section_total:,.0f} руб** ({section_per_m3:.2f} руб/м³)"
                )
            if summary_parts:
                st.caption("По разделам: " + " · ".join(summary_parts))
            st.caption(
                f"Итого постоянные: **{cost_result.fixed_total_rub:,.0f} руб** "
                f"({cost_result.fixed_costs.total_per_m3:.2f} руб/м³)"
            )
        else:
            st.info("Нет активных статей постоянных расходов.")

    total_caption = (
        f"**{variant_title}** — итого по сценарию: **{cost_result.total_amount_rub:,.0f} руб**"
    )
    if cost_result.cost_per_m3 > 0:
        total_caption += f" ({cost_result.cost_per_m3:.2f} руб/м³)"
    if cost_result.cost_per_ton > 0 and show_manufacturing:
        total_caption += f", {cost_result.cost_per_ton:.2f} руб/т"
    st.caption(total_caption)

    if cost_result.child_results:
        with st.expander("Состав композитного расчёта", expanded=False):
            for child in cost_result.child_results:
                st.markdown(
                    f"- `{child.scenario_id}`: переменные {child.variable_total_rub:,.0f} руб"
                )


def _render_hole_visualization(
    *,
    selected: dict,
    target: TargetParams,
    overdrill_m: float,
    hole_oversize_coeff: float,
    profile: ScenarioCalcProfile,
) -> None:
    show_charge = profile.needs_charge_design
    if profile.mode == "contour_bvr":
        st.subheader("Схема заряда контура")
        st.caption(
            "Сравнение вариантов заряжания при подобранной сетке. "
            "Удельный расход ВВ — на погонный метр скважины (кг/п.м.)."
        )
    elif show_charge:
        st.subheader("Схема заряда скважины")
        st.caption(
            "Сравнение вариантов заряжания при подобранной сетке. "
            "Меняйте тип ВВ, недозаряд, число промежуточных детонаторов и НСИ — пересчёт мгновенный."
        )
    else:
        st.subheader("Геометрия блока")
        st.caption("Сетка, глубина и погонаж бурения без расчёта заряда.")
    _inject_hole_viz_styles()

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
            show_charge_design=show_charge,
            explosive_basis=profile.explosive_basis,
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
            show_charge_design=show_charge,
            explosive_basis=profile.explosive_basis,
        )


def _render_drilling_geometry_page() -> None:
    """Сценарий «Буровые работы»: сетка и погонаж без ВВ."""
    st.subheader("Параметры сетки бурения")
    _inject_hole_viz_styles()

    col1, col2, col3 = st.columns(3)
    with col1:
        grid_a_m = st.number_input(
            "Шаг a, м",
            min_value=1.0,
            max_value=20.0,
            value=5.0,
            step=0.25,
            key="drill_grid_a",
        )
        grid_b_m = st.number_input(
            "Шаг b, м",
            min_value=1.0,
            max_value=20.0,
            value=4.0,
            step=0.25,
            key="drill_grid_b",
        )
    with col2:
        bench_height_m = st.number_input(
            "Высота уступа, м",
            min_value=5.0,
            max_value=25.0,
            value=10.0,
            step=0.5,
            key="drill_bench_height",
        )
        overdrill_m = st.number_input(
            "Перебур, м",
            min_value=0.0,
            max_value=3.0,
            value=1.0,
            step=0.1,
            key="drill_overdrill",
        )
    with col3:
        crown_mm = st.selectbox(
            "Коронка, мм",
            options=CROWNS_MM,
            index=min(2, len(CROWNS_MM) - 1),
            key="drill_crown",
        )
        hole_oversize_coeff = st.number_input(
            "Коэффициент разбуривания",
            min_value=1.0,
            max_value=1.15,
            value=1.05,
            step=0.01,
            key="drill_oversize",
        )

    depth_m = bench_height_m + overdrill_m

    param_col1, param_col2 = st.columns(2)
    with param_col1:
        block_volume_m3 = st.number_input(
            "Объём блока, м³",
            min_value=1000.0,
            max_value=500_000.0,
            value=30_000.0,
            step=1000.0,
            key="drill_block_volume",
        )
    with param_col2:
        additional_holes_pct = st.number_input(
            "Доп. скважины, %",
            min_value=0.0,
            max_value=20.0,
            value=3.0,
            step=0.5,
            key="drill_additional_holes_pct",
        ) / 100.0

    _render_hole_panel(
        panel_key="drilling",
        grid_a_m=grid_a_m,
        grid_b_m=grid_b_m,
        depth_m=depth_m,
        overdrill_m=overdrill_m,
        crown_mm=crown_mm,
        hole_oversize_coeff=hole_oversize_coeff,
        block_volume_m3=block_volume_m3,
        additional_holes_pct=additional_holes_pct,
        default_explosive_key="ПВВ Гранулит-РП",
        default_undercharge_m=0.0,
        show_charge_design=False,
    )


def _render_manual_scenario_page(profile: ScenarioCalcProfile) -> None:
    """Сценарии без геометрии БВР: ПВВ, ЭВВ, RC."""
    st.subheader("Входные данные")
    manual_type = profile.manual_type
    block_data: BlockCalculationInput | None = None
    variant_title = "Сценарий"
    explosive_key = "ПВВ Гранулит-РП"

    if manual_type == "pvv":
        col1, col2, col3 = st.columns(3)
        with col1:
            pvv_mass_kg = st.number_input(
                "Масса ВВ, кг",
                min_value=0.0,
                value=10_000.0,
                step=100.0,
                key="manual_pvv_mass",
            )
        with col2:
            pvv_holes = st.number_input(
                "Число скважин",
                min_value=0,
                value=100,
                step=1,
                key="manual_pvv_holes",
            )
        with col3:
            block_volume_m3 = st.number_input(
                "Объём блока, м³ (для руб/м³)",
                min_value=0.0,
                value=30_000.0,
                step=1000.0,
                key="manual_pvv_volume",
            )
        block_data = build_manual_block_input(
            block_volume_m3=block_volume_m3,
            total_holes=int(pvv_holes),
            total_charge_mass_kg=pvv_mass_kg,
            explosive_key=explosive_key,
        )
        variant_title = "Поставка ПВВ"

    elif manual_type == "evv":
        block_data = build_manual_block_input()
        variant_title = "Производство ЭВВ"
        st.caption("Объём производства задаётся в блоке сметы ниже.")

    elif manual_type == "rc":
        rc_footage_m = st.number_input(
            "Погонаж RC-бурения, п.м.",
            min_value=0.0,
            value=1000.0,
            step=50.0,
            key="manual_rc_footage",
        )
        block_data = build_manual_block_input(drilling_footage_m=rc_footage_m)
        variant_title = "RC-бурение"

    if block_data is None:
        st.warning("Неизвестный тип ручного сценария.")
        return

    st.divider()
    _render_variable_costs_panel(
        panel_key=f"manual_{manual_type}",
        variant_title=variant_title,
        explosive_key=explosive_key,
        hole=block_data.hole,
        block=block_data.block,
        initiation=block_data.initiation,
        hole_depth_m=0.0,
        block_data_override=block_data,
    )


def _render_full_bvr_calc_page(profile: ScenarioCalcProfile) -> None:
    """Оптимизация q и схема заряда для сценариев с геометрией БВР."""

    col1, col2, col3 = st.columns(3)

    with col1:
        st.subheader("Взрывчатое вещество (ВВ)")
        explosives = get_explosives_dict(st.session_state)
        explosive_keys = list(explosives.keys())
        default_explosive_idx = (
            explosive_keys.index(DEFAULT_EXPLOSIVE_KEY)
            if DEFAULT_EXPLOSIVE_KEY in explosive_keys
            else 0
        )
        explosive_key = st.selectbox(
            "ВВ",
            options=explosive_keys,
            index=default_explosive_idx,
            key="explosive",
        )
        explosive = explosives[explosive_key].properties
        with st.expander("Параметры выбранного ВВ"):
            st.write(f"**{explosive.name}**")
            st.write(f"- Плотность заряжания: {explosive.density_t_m3} т/м³")
            st.write(f"- Теплота взрыва: {explosive.power_mj_kg} МДж/кг")

    with col2:
        st.subheader("Порода")
        rocks = get_rocks_dict(st.session_state)
        rock_names = list(rocks.keys())
        default_rock_idx = (
            rock_names.index(DEFAULT_ROCK_NAME)
            if DEFAULT_ROCK_NAME in rock_names
            else 0
        )
        rock_key = st.selectbox(
            "Порода",
            options=rock_names,
            index=default_rock_idx,
            key="rock",
        )
        rock = rocks[rock_key]
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
        q_label = "Уд. расход (кг/п.м.)" if profile.explosive_basis == "per_m" else "Уд. расход (кг/м³)"
        crown_labels = [
            f"Ø {r['Коронка (мм)']} мм — сетка {r['Сетка a×b (м)']} — q={r[q_label] if q_label in r else r['Уд. расход (кг/м³)']}"
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
            profile=profile,
        )


def _render_calc_page() -> None:
    profile = get_scenario_calc_profile(get_active_scenario_id())
    st.caption(profile.ui_caption)

    if profile.is_manual_input:
        _render_manual_scenario_page(profile)
    elif profile.mode == "drilling_geometry":
        _render_drilling_geometry_page()
    else:
        _render_full_bvr_calc_page(profile)


def main():
    st.set_page_config(page_title="BlastEX", page_icon="💥", layout="wide")
    init_workspace()
    render_admin_panel()
    st.title("💥 BlastEX — расчёт параметров взрывания")
    render_workspace_toolbar()

    tab_calc, tab_drilling, tab_labor, tab_catalog = st.tabs(
        ["Расчёт", "Расчёт стоимости бурения", "Расчёт ФОТ", "Справочники"]
    )
    with tab_catalog:
        render_references_tab()
    with tab_drilling:
        render_drilling_tab()
    with tab_labor:
        render_labor_tab()
    with tab_calc:
        _render_calc_page()


if __name__ == "__main__":
    main()
