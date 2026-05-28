"""UI: справочники объектов работ и буровых станков."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from cost.admin_auth import can_edit_references, require_admin_or_readonly
from cost.drilling_data import (
    DEFAULT_DRILL_RIGS,
    DEFAULT_WORK_OBJECTS,
    drill_rigs_to_records,
    work_objects_to_records,
)
from cost.references_store import get_drill_rigs, get_work_objects, init_references_state


def _work_objects_dataframe() -> pd.DataFrame:
    objects = get_work_objects(st.session_state)
    rows = [
        {
            "name": obj.name,
            "mobilization_km": obj.mobilization_km,
            "diesel_price_ton_rub": obj.diesel_price_ton_rub,
        }
        for obj in objects
    ]
    return pd.DataFrame(rows)


def _drill_rigs_dataframe() -> pd.DataFrame:
    rigs = get_drill_rigs(st.session_state)
    rows = [
        {
            "name": rig.name,
            "depreciation_per_shift_rub": rig.depreciation_per_shift_rub,
            "fuel_l_per_h": rig.fuel_l_per_h,
        }
        for rig in rigs
    ]
    return pd.DataFrame(rows)


def render_work_objects_section() -> None:
    init_references_state(st.session_state)
    st.markdown("**Объекты работ (карьеры / месторождения)**")
    st.caption(
        "Мобилизация и цена ДТ подставляются в расчёт бурения для выбранного объекта."
    )

    col_reset, _ = st.columns([1, 3])
    with col_reset:
        if can_edit_references() and st.button("Сбросить объекты", key="work_objects_reset"):
            st.session_state["work_object_records"] = work_objects_to_records(DEFAULT_WORK_OBJECTS)
            st.rerun()

    if require_admin_or_readonly(
        readonly_message="Объекты работ доступны только для просмотра. Войдите как администратор."
    ):
        edited = st.data_editor(
            _work_objects_dataframe(),
            use_container_width=True,
            hide_index=True,
            num_rows="dynamic",
            column_config={
                "name": st.column_config.TextColumn("Объект работ", required=True, width="large"),
                "mobilization_km": st.column_config.NumberColumn(
                    "Мобилизация, км", min_value=0.0, format="%.0f"
                ),
                "diesel_price_ton_rub": st.column_config.NumberColumn(
                    "Цена ДТ, руб/т",
                    min_value=0.0,
                    format="%.0f",
                    help="Пустое значение — цена по умолчанию из калькулятора бурения.",
                ),
            },
            key="work_objects_editor",
        )
        records = edited.to_dict("records")
        for row in records:
            diesel = row.get("diesel_price_ton_rub")
            if diesel is not None and (pd.isna(diesel) or float(diesel) <= 0):
                row["diesel_price_ton_rub"] = None
        st.session_state["work_object_records"] = records
    else:
        st.dataframe(_work_objects_dataframe(), use_container_width=True, hide_index=True)


def render_drill_rigs_section() -> None:
    init_references_state(st.session_state)
    st.markdown("**Буровые станки**")
    st.caption("Амортизация и расход топлива используются в калькуляторе бурения.")

    col_reset, _ = st.columns([1, 3])
    with col_reset:
        if can_edit_references() and st.button("Сбросить станки", key="drill_rigs_reset"):
            st.session_state["drill_rig_records"] = drill_rigs_to_records(DEFAULT_DRILL_RIGS)
            st.rerun()

    if require_admin_or_readonly(
        readonly_message="Справочник станков доступен только для просмотра. Войдите как администратор."
    ):
        edited = st.data_editor(
            _drill_rigs_dataframe(),
            use_container_width=True,
            hide_index=True,
            num_rows="dynamic",
            column_config={
                "name": st.column_config.TextColumn("Станок", required=True, width="large"),
                "depreciation_per_shift_rub": st.column_config.NumberColumn(
                    "Амортизация, руб/смена", min_value=0.0, format="%.2f"
                ),
                "fuel_l_per_h": st.column_config.NumberColumn(
                    "Расход, л/ч", min_value=0.0, format="%.1f"
                ),
            },
            key="drill_rigs_editor",
        )
        st.session_state["drill_rig_records"] = edited.to_dict("records")
    else:
        st.dataframe(_drill_rigs_dataframe(), use_container_width=True, hide_index=True)
