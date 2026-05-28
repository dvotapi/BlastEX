"""UI: вкладка «Справочники» с подразделами."""
from __future__ import annotations

import streamlit as st

from cost.catalog_ui import render_nomenclature_section
from cost.drilling_ui import render_drilling_price_readonly
from cost.fixed_costs_ui import render_fixed_costs_editor
from cost.references_ui import (
    render_depreciation_assets_section,
    render_drill_rigs_section,
    render_explosives_section,
    render_rocks_section,
    render_work_objects_section,
)


def render_references_tab() -> None:
    st.subheader("Справочники")
    st.caption(
        "Технические и сметные справочники. Редактирование доступно администратору "
        "(см. боковую панель). Изменения сохраняются кнопкой «Сохранить» в панели над вкладками."
    )

    tab_rocks, tab_explosives, tab_depreciation, tab_ops, tab_catalog, tab_fixed = st.tabs(
        [
            "Горные породы",
            "Взрывчатые вещества",
            "Амортизация ОС",
            "Объекты и станки",
            "Номенклатура и цены",
            "Постоянные расходы",
        ]
    )

    with tab_rocks:
        render_rocks_section()

    with tab_explosives:
        render_explosives_section()

    with tab_depreciation:
        render_depreciation_assets_section()

    with tab_ops:
        render_work_objects_section()
        st.divider()
        render_drill_rigs_section()
        st.divider()
        render_drilling_price_readonly()

    with tab_catalog:
        render_nomenclature_section()

    with tab_fixed:
        render_fixed_costs_editor()
