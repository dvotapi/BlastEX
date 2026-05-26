"""UI: калькулятор «Расчет стоимости бурения»."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from cost.drilling import (
    DrillingUnitCostInput,
    calculate_drilling_unit_cost,
    unit_cost_summary_rows,
)
from cost.drilling_data import (
    DEFAULT_DRILL_RIGS,
    DEFAULT_OBJECT_NAME,
    DEFAULT_RIG_NAME,
    DEFAULT_WORK_OBJECTS,
    find_object,
)


def _init_drilling_calculator_state() -> None:
    if "drilling_calculator_input" not in st.session_state:
        st.session_state["drilling_calculator_input"] = DrillingUnitCostInput().__dict__
    if "drilling_price_per_m" not in st.session_state:
        default_result = calculate_drilling_unit_cost(DrillingUnitCostInput())
        st.session_state["drilling_price_per_m"] = default_result.price_per_m
        st.session_state["drilling_unit_cost_result"] = default_result


def get_drilling_price_per_m() -> float:
    _init_drilling_calculator_state()
    _sync_drilling_price()
    return float(st.session_state["drilling_price_per_m"])


def _sync_drilling_price() -> None:
    params = DrillingUnitCostInput(**st.session_state["drilling_calculator_input"])
    result = calculate_drilling_unit_cost(params)
    st.session_state["drilling_price_per_m"] = result.price_per_m
    st.session_state["drilling_unit_cost_result"] = result


def _save_input(**kwargs) -> None:
    data = dict(st.session_state["drilling_calculator_input"])
    data.update(kwargs)
    st.session_state["drilling_calculator_input"] = data
    _sync_drilling_price()


def _apply_bvr_context() -> None:
    ctx = st.session_state.get("blast_context")
    rows = st.session_state.get("blast_results")
    if not ctx or not rows:
        return

    from cost.geometry import calculate_block_geometry, calculate_hole_geometry, normalize_initiation_config
    from Blast import ExplosiveProperties

    selected_idx = st.session_state.get("viz_crown_select", 0)
    selected = rows[min(selected_idx, len(rows) - 1)]
    grid_a, grid_b = [float(x.strip()) for x in selected["Сетка a×b (м)"].split("×")]
    depth_m = ctx["target"].bench_height_m + ctx["overdrill_m"]
    crown_mm = float(selected["Коронка (мм)"])
    explosive = ExplosiveProperties("Гранулит-РП", 0.85, 3.76)
    block_volume_m3 = float(st.session_state.get("viz_block_volume", 30_000.0))
    additional_holes_pct = float(st.session_state.get("viz_additional_holes_pct", 3.0)) / 100.0

    hole = calculate_hole_geometry(
        grid_a_m=grid_a,
        grid_b_m=grid_b,
        depth_m=depth_m,
        overdrill_m=ctx["overdrill_m"],
        undercharge_m=0.0,
        crown_mm=crown_mm,
        hole_oversize_coeff=ctx["hole_oversize_coeff"],
        explosive=explosive,
        explosive_label=explosive.name,
    )
    block = calculate_block_geometry(
        block_volume_m3=block_volume_m3,
        hole=hole,
        additional_holes_pct=additional_holes_pct,
        initiation=normalize_initiation_config(),
    )
    _save_input(volume_m=block.drilling_footage_m, crown_mm=crown_mm)


def render_drilling_tab() -> None:
    _init_drilling_calculator_state()
    params_dict = st.session_state["drilling_calculator_input"]
    params = DrillingUnitCostInput(**params_dict)

    st.subheader("Расчёт стоимости бурения")
    st.caption(
        "Калькулятор по листу Excel «Расчет стоимости бурения». "
        "Итоговая **цена за 1 п.м.** (ячейка D41) подставляется в переменные расходы 1.2 на вкладке «Расчёт»."
    )

    btn_col1, btn_col2 = st.columns([1, 1])
    with btn_col1:
        if st.button("Подставить объём из расчёта БВР", key="drill_apply_bvr"):
            if "blast_results" in st.session_state:
                _apply_bvr_context()
                st.rerun()
            else:
                st.warning("Сначала выполните расчёт на вкладке «Расчёт».")
    with btn_col2:
        if st.button("Сбросить к Excel-смете", key="drill_reset"):
            st.session_state["drilling_calculator_input"] = DrillingUnitCostInput().__dict__
            _sync_drilling_price()
            st.rerun()

    left, right = st.columns([1, 1.2])

    with left:
        st.markdown("**Исходные данные**")
        object_names = [o.name for o in DEFAULT_WORK_OBJECTS]
        object_idx = object_names.index(params.object_name) if params.object_name in object_names else 0

        object_name = st.selectbox(
            "Объект",
            options=object_names,
            index=object_idx,
            key="drill_object",
        )
        obj = find_object(object_name)
        default_km = obj.mobilization_km if obj else 300.0
        default_diesel = obj.diesel_price_ton_rub if obj and obj.diesel_price_ton_rub else 80_000.0

        volume_m = st.number_input(
            "Объём буровых работ, п.м.",
            min_value=1.0,
            value=float(params.volume_m),
            step=10.0,
            key="drill_volume",
        )
        crown_mm = st.number_input(
            "Диаметр коронки, мм",
            min_value=100.0,
            max_value=250.0,
            value=float(params.crown_mm),
            step=1.0,
            key="drill_crown_mm",
        )

        rig_names = [r.name for r in DEFAULT_DRILL_RIGS]
        rig_idx = rig_names.index(params.rig_name) if params.rig_name in rig_names else rig_names.index(DEFAULT_RIG_NAME)
        rig_name = st.selectbox("Тип буровой установки", options=rig_names, index=rig_idx, key="drill_rig")

        tech_speed = st.number_input(
            "Технологическая скорость, м/ч",
            min_value=1.0,
            value=float(params.tech_speed_m_h),
            step=0.5,
            key="drill_tech_speed",
        )
        nonprod = st.number_input(
            "Непроизводительное время в смену, ч",
            min_value=0.0,
            max_value=10.0,
            value=float(params.nonproductive_h_per_shift),
            step=0.5,
            key="drill_nonprod",
        )

        st.markdown("**Буровой инструмент**")
        tool_col1, tool_col2 = st.columns(2)
        with tool_col1:
            crown_m = st.number_input("Коронка, м/шт", min_value=1.0, value=float(params.crown_m_per_piece), key="drill_crown_m")
            ppu_m = st.number_input("ППУ, м/шт", min_value=1.0, value=float(params.ppu_m_per_piece), key="drill_ppu_m")
            rig_tools_m = st.number_input(
                "Оснастка, м/компл.",
                min_value=1.0,
                value=float(params.rig_tools_m_per_set),
                key="drill_rig_tools_m",
            )
            casing_ratio = st.number_input(
                "Обсадка, м/п.м.",
                min_value=0.0,
                value=float(params.casing_m_per_drill_m),
                step=0.01,
                format="%.2f",
                key="drill_casing_ratio",
            )
        with tool_col2:
            crown_price = st.number_input(
                "Цена коронки, руб",
                min_value=0.0,
                value=float(params.crown_price_rub),
                step=1000.0,
                key="drill_crown_price",
            )
            ppu_price = st.number_input(
                "Цена ППУ, руб",
                min_value=0.0,
                value=float(params.ppu_price_rub),
                step=1000.0,
                key="drill_ppu_price",
            )
            rig_tools_price = st.number_input(
                "Цена комплекта оснастки, руб",
                min_value=0.0,
                value=float(params.rig_tools_set_price_rub),
                step=1000.0,
                key="drill_rig_tools_price",
            )
            casing_price = st.number_input(
                "Цена обсадки, руб/м",
                min_value=0.0,
                value=float(params.casing_price_rub_per_m),
                step=10.0,
                key="drill_casing_price",
            )

        st.markdown("**Смены и прочие расходы**")
        shift_col1, shift_col2 = st.columns(2)
        with shift_col1:
            shifts_toir = st.number_input("Смены на ТОиР", min_value=0.0, value=float(params.shifts_toir), key="drill_toir")
            shifts_clean = st.number_input(
                "Смены на прочистку",
                min_value=0.0,
                value=float(params.shifts_cleaning),
                key="drill_clean",
            )
            fot_pm = st.number_input(
                "ФОТ, руб/п.м. (до НДФЛ)",
                min_value=0.0,
                value=float(params.fot_rub_per_m),
                key="drill_fot",
            )
        with shift_col2:
            spares_pm = st.number_input("Запчасти, руб/п.м.", min_value=0.0, value=float(params.spares_rub_per_m), key="drill_spares")
            consumables_pm = st.number_input(
                "Расходники, руб/п.м.",
                min_value=0.0,
                value=float(params.consumables_rub_per_m),
                key="drill_consumables",
            )
            profit_factor = st.number_input(
                "Коэфф. наценки (D41/D40)",
                min_value=1.0,
                max_value=2.0,
                value=float(params.profit_factor),
                step=0.05,
                key="drill_profit",
            )

        mob_km = st.number_input(
            "Расстояние мобилизации, км",
            min_value=0.0,
            value=float(params.mobilization_km if params.mobilization_km is not None else default_km),
            key="drill_mob_km",
        )
        diesel_price = st.number_input(
            "Цена ДТ, руб/т (без НДС)",
            min_value=0.0,
            value=float(params.diesel_price_ton_rub if params.diesel_price_ton_rub is not None else default_diesel),
            step=1000.0,
            key="drill_diesel",
        )
        oh_col1, oh_col2 = st.columns(2)
        with oh_col1:
            overhead_prod = st.number_input(
                "Общепроизводственные, руб",
                min_value=0.0,
                value=float(params.overhead_production_rub),
                step=10_000.0,
                key="drill_oh_prod",
            )
        with oh_col2:
            overhead_admin = st.number_input(
                "Накладные, руб",
                min_value=0.0,
                value=float(params.overhead_admin_rub),
                step=10_000.0,
                key="drill_oh_admin",
            )

        _save_input(
            object_name=object_name,
            volume_m=volume_m,
            crown_mm=crown_mm,
            rig_name=rig_name,
            tech_speed_m_h=tech_speed,
            nonproductive_h_per_shift=nonprod,
            crown_m_per_piece=crown_m,
            crown_price_rub=crown_price,
            ppu_m_per_piece=ppu_m,
            ppu_price_rub=ppu_price,
            rig_tools_m_per_set=rig_tools_m,
            rig_tools_set_price_rub=rig_tools_price,
            casing_m_per_drill_m=casing_ratio,
            casing_price_rub_per_m=casing_price,
            shifts_toir=shifts_toir,
            shifts_cleaning=shifts_clean,
            spares_rub_per_m=spares_pm,
            consumables_rub_per_m=consumables_pm,
            fot_rub_per_m=fot_pm,
            mobilization_km=mob_km,
            diesel_price_ton_rub=diesel_price,
            overhead_production_rub=overhead_prod,
            overhead_admin_rub=overhead_admin,
            profit_factor=profit_factor,
        )
        result = st.session_state["drilling_unit_cost_result"]

    with right:
        metric_col1, metric_col2 = st.columns(2)
        with metric_col1:
            st.metric("Себестоимость", f"{result.cost_per_m:,.2f} руб/п.м.")
        with metric_col2:
            st.metric("Цена (D41)", f"{result.price_per_m:,.2f} руб/п.м.")

        st.markdown("**Сводка расчёта**")
        summary_df = pd.DataFrame(
            [{"Показатель": k, "Значение": v} for k, v in unit_cost_summary_rows(result)]
        )
        st.dataframe(summary_df, use_container_width=True, hide_index=True)

        st.markdown("**Структура цены за 1 п.м.**")
        breakdown_rows = []
        for line in result.lines:
            breakdown_rows.append(
                {
                    "Раздел": line.section,
                    "Статья": line.name,
                    "Кол-во": round(line.quantity, 4) if line.quantity is not None else None,
                    "Ед.": line.unit,
                    "Сумма, руб": round(line.total_rub, 0) if line.total_rub is not None else None,
                    "руб/п.м.": round(line.price_per_m, 2),
                    "Примечание": line.note,
                }
            )
        st.dataframe(pd.DataFrame(breakdown_rows), use_container_width=True, hide_index=True)

        st.info(
            f"На вкладке «Расчёт» в блоке **1.2 — бурение** используется цена "
            f"**{result.price_per_m:,.2f} руб/п.м.**"
        )


def render_drilling_price_readonly() -> None:
    """Краткая справка о текущей цене бурения (для вкладки справочника)."""
    _init_drilling_calculator_state()
    price = get_drilling_price_per_m()
    st.markdown("**Стоимость бурения**")
    st.metric("Цена бурения, руб/п.м.", f"{price:,.2f}")
    st.caption("Рассчитывается на вкладке «Расчёт стоимости бурения».")
