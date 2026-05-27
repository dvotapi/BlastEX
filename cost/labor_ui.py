"""UI: расчёт ФОТ производственного персонала."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from cost.labor import (
    DEFAULT_LABOR_ASSIGNMENTS,
    DEFAULT_LABOR_CATALOG,
    LaborFOTSettings,
    calculate_labor_fot,
    get_default_labor_assignments,
    get_default_labor_catalog,
    labor_assignments_from_records,
    labor_assignments_to_records,
    labor_catalog_from_records,
    labor_catalog_to_records,
    labor_summary_rows,
    labor_table_rows,
)


def _init_labor_state() -> None:
    if "labor_catalog_records" not in st.session_state:
        st.session_state["labor_catalog_records"] = labor_catalog_to_records(
            get_default_labor_catalog()
        )
    if "labor_assignment_records" not in st.session_state:
        st.session_state["labor_assignment_records"] = labor_assignments_to_records(
            get_default_labor_assignments()
        )
    if "labor_shifts_per_month" not in st.session_state:
        st.session_state["labor_shifts_per_month"] = 5.0


def get_active_labor_catalog():
    _init_labor_state()
    return labor_catalog_from_records(st.session_state["labor_catalog_records"])


def get_active_labor_assignments():
    _init_labor_state()
    return labor_assignments_from_records(st.session_state["labor_assignment_records"])


def get_labor_fot_settings() -> LaborFOTSettings:
    _init_labor_state()
    return LaborFOTSettings(
        shifts_per_month=float(st.session_state["labor_shifts_per_month"]),
    )


def _apply_bvr_context_to_assignments() -> None:
    ctx = st.session_state.get("blast_context")
    rows = st.session_state.get("blast_results")
    if not ctx or not rows:
        st.warning("Сначала выполните расчёт на вкладке «Расчёт».")
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

    records = labor_assignments_to_records(get_default_labor_assignments())
    for row in records:
        if row["position_id"] in ("labor_master", "labor_blasters", "labor_driller", "labor_assistant"):
            row["volume_m3"] = block.block_volume_m3
        elif row["position_id"] in ("labor_driver_szm", "labor_driver_del"):
            row["volume_m3"] = block.drilling_footage_m

    st.session_state["labor_assignment_records"] = records
    st.rerun()


def render_labor_tab() -> None:
    _init_labor_state()
    st.subheader("Расчёт ФОТ производственного персонала")
    st.caption(
        "Окладная часть = (оклад / смен в месяце) × смены сотрудника; "
        "сдельная = объём × расценка. Итог по строке умножается на число ставок."
    )

    col_reset, col_apply, _ = st.columns([1, 1, 2])
    with col_reset:
        if st.button("Сбросить ФОТ к Excel-смете", key="labor_reset"):
            st.session_state["labor_catalog_records"] = labor_catalog_to_records(
                DEFAULT_LABOR_CATALOG
            )
            st.session_state["labor_assignment_records"] = labor_assignments_to_records(
                DEFAULT_LABOR_ASSIGNMENTS
            )
            st.session_state["labor_shifts_per_month"] = 5.0
            st.rerun()
    with col_apply:
        if st.button("Подставить объёмы из расчёта", key="labor_apply_context"):
            _apply_bvr_context_to_assignments()

    st.markdown("**Общие параметры**")
    st.number_input(
        "Количество рабочих смен в месяце",
        min_value=1.0,
        max_value=31.0,
        value=float(st.session_state["labor_shifts_per_month"]),
        step=1.0,
        key="labor_shifts_per_month",
    )

    st.markdown("**Справочник должностей**")
    catalog_edited = st.data_editor(
        pd.DataFrame(st.session_state["labor_catalog_records"]),
        use_container_width=True,
        hide_index=True,
        num_rows="dynamic",
        column_config={
            "id": st.column_config.TextColumn("Код", required=True, width="small"),
            "name": st.column_config.TextColumn("Должность", required=True, width="large"),
            "fixed_salary_monthly": st.column_config.NumberColumn(
                "Оклад, руб/мес", min_value=0.0, format="%.2f"
            ),
            "piece_rate_per_m3": st.column_config.NumberColumn(
                "Сдельная, руб/м³", min_value=0.0, format="%.4f"
            ),
        },
        key="labor_catalog_editor",
    )
    st.session_state["labor_catalog_records"] = catalog_edited.to_dict("records")
    catalog = labor_catalog_from_records(st.session_state["labor_catalog_records"])
    position_ids = [p.id for p in catalog if p.id]

    st.markdown("**Штатное расписание на блок**")
    assignment_rows = st.session_state["labor_assignment_records"]
    if not assignment_rows:
        assignment_rows = [{"id": "la_1", "position_id": "", "headcount": 1.0, "volume_m3": 0.0, "employee_shifts": 1.0}]

    assignments_df = pd.DataFrame(assignment_rows)
    if "position_id" in assignments_df.columns and position_ids:
        assignments_edited = st.data_editor(
            assignments_df,
            use_container_width=True,
            hide_index=True,
            num_rows="dynamic",
            column_config={
                "id": st.column_config.TextColumn("Код строки", required=True, width="small"),
                "position_id": st.column_config.SelectboxColumn(
                    "Должность",
                    options=position_ids,
                    required=True,
                    width="large",
                ),
                "headcount": st.column_config.NumberColumn(
                    "Ставки", min_value=0.0, step=0.5, format="%.1f"
                ),
                "volume_m3": st.column_config.NumberColumn(
                    "Объём работ, м³", min_value=0.0, format="%.1f"
                ),
                "employee_shifts": st.column_config.NumberColumn(
                    "Смены сотрудника", min_value=0.0, step=1.0, format="%.1f"
                ),
            },
            key="labor_assignments_editor",
        )
    else:
        st.warning("Добавьте хотя бы одну должность в справочник.")
        assignments_edited = assignments_df

    st.session_state["labor_assignment_records"] = assignments_edited.to_dict("records")
    assignments = labor_assignments_from_records(st.session_state["labor_assignment_records"])

    settings = get_labor_fot_settings()
    result = calculate_labor_fot(catalog=catalog, assignments=assignments, settings=settings)

    st.divider()
    st.markdown("**Расчёт ФОТ**")
    if not result.lines:
        st.info("Добавьте строки сотрудников и выберите должности из справочника.")
        return

    table_df = pd.DataFrame(labor_table_rows(result))
    for col in ("Ставки", "Смены сотр."):
        if col in table_df.columns:
            table_df[col] = table_df[col].map(
                lambda x: int(x) if float(x).is_integer() else x
            )

    st.dataframe(table_df, use_container_width=True, hide_index=True)

    summary_df = pd.DataFrame(
        [{"Показатель": k, "Значение": v} for k, v in labor_summary_rows(result)]
    )
    st.dataframe(summary_df, use_container_width=True, hide_index=True)

    if result.settings.shifts_per_month > 0 and result.total_fot > 0:
        block_volume = float(st.session_state.get("viz_block_volume", 30_000.0))
        if block_volume > 0:
            st.caption(
                f"Удельный ФОТ: **{result.total_fot / block_volume:.2f} руб/м³** "
                f"(объём блока {block_volume:,.0f} м³ с вкладки «Расчёт»)"
            )
