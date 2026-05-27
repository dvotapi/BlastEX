"""UI: справочник постоянных расходов (блок 2)."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from cost.fixed_costs import (
    DEFAULT_FIXED_COSTS,
    SECTION_ORDER,
    SECTION_TITLES,
    FixedCostItem,
    fixed_costs_from_records,
    fixed_costs_to_records,
)


def _init_fixed_costs_state() -> None:
    if "fixed_cost_records" not in st.session_state:
        st.session_state["fixed_cost_records"] = fixed_costs_to_records(DEFAULT_FIXED_COSTS)


def get_active_fixed_costs() -> list[FixedCostItem]:
    _init_fixed_costs_state()
    return fixed_costs_from_records(st.session_state["fixed_cost_records"])


def _edit_section(*, section: str, items: list[FixedCostItem], editor_key: str) -> list[dict]:
    section_items = [i for i in items if i.section == section]
    rows = fixed_costs_to_records(section_items)
    if not rows:
        rows = [{
            "id": "",
            "section": section,
            "name": "",
            "amount_rub": 0.0,
            "note": "",
            "enabled": True,
        }]

    edited = st.data_editor(
        pd.DataFrame(rows),
        use_container_width=True,
        hide_index=True,
        num_rows="dynamic",
        column_config={
            "id": st.column_config.TextColumn("Код", required=True, width="small"),
            "section": None,
            "name": st.column_config.TextColumn("Наименование", required=True, width="large"),
            "amount_rub": st.column_config.NumberColumn(
                "Сумма, руб на блок", min_value=0.0, format="%.2f"
            ),
            "note": st.column_config.TextColumn("Примечание", width="medium"),
            "enabled": st.column_config.CheckboxColumn("Учитывать", default=True),
        },
        key=editor_key,
    )
    out = edited.to_dict("records")
    for row in out:
        row["section"] = section
    return out


def render_fixed_costs_editor() -> None:
    _init_fixed_costs_state()
    st.markdown("**Постоянные расходы (блок 2)**")
    st.caption(
        "Суммы на блок для текущего сценария (эталон — Excel, колонка S, «БВР сухие»). "
        "Удельная стоимость пересчитывается при изменении объёма блока."
    )

    col_reset, _ = st.columns([1, 3])
    with col_reset:
        if st.button("Сбросить постоянные расходы", key="fixed_costs_reset"):
            st.session_state["fixed_cost_records"] = fixed_costs_to_records(DEFAULT_FIXED_COSTS)
            st.rerun()

    items = get_active_fixed_costs()
    merged: list[dict] = []
    for section in SECTION_ORDER:
        with st.expander(f"{section} — {SECTION_TITLES[section]}", expanded=section in ("2.1", "2.3")):
            merged.extend(
                _edit_section(
                    section=section,
                    items=items,
                    editor_key=f"fixed_cost_editor_{section.replace('.', '_')}",
                )
            )

    st.session_state["fixed_cost_records"] = merged
