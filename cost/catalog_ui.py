"""UI: справочник номенклатуры и цен."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from cost.catalog import (
    DEFAULT_CATALOG,
    CatalogItem,
    catalog_from_records,
    catalog_to_records,
    items_by_category,
)
from cost.drilling_ui import render_drilling_price_readonly


def _init_catalog_state() -> None:
    if "cost_catalog_records" not in st.session_state:
        st.session_state["cost_catalog_records"] = catalog_to_records(DEFAULT_CATALOG)


def get_active_catalog() -> list[CatalogItem]:
    _init_catalog_state()
    return catalog_from_records(st.session_state["cost_catalog_records"])


def _edit_category(
    *,
    title: str,
    category: str,
    unit: str,
    catalog: list[CatalogItem],
    editor_key: str,
    show_mass: bool = False,
    show_length: bool = False,
) -> list[dict]:
    if title:
        st.markdown(f"**{title}**")
    rows = catalog_to_records(items_by_category(catalog, category))
    if not rows and category == "explosive":
        rows = [{"id": "", "name": "", "category": category, "unit": unit, "price": 0.0, "note": ""}]

    column_config = {
        "id": st.column_config.TextColumn("Код", required=True, width="small"),
        "name": st.column_config.TextColumn("Наименование", required=True, width="large"),
        "category": None,
        "unit": None,
        "price": st.column_config.NumberColumn("Цена, руб", min_value=0.0, format="%.2f"),
        "note": st.column_config.TextColumn("Примечание", width="medium"),
    }
    if show_mass:
        column_config["mass_kg"] = st.column_config.NumberColumn(
            "Масса патрона, кг", min_value=0.0, format="%.3f"
        )
    else:
        column_config["mass_kg"] = None
    if show_length:
        column_config["length_m"] = st.column_config.NumberColumn(
            "Длина, м", min_value=0.0, format="%.1f"
        )
    else:
        column_config["length_m"] = None

    edited = st.data_editor(
        pd.DataFrame(rows),
        use_container_width=True,
        hide_index=True,
        num_rows="dynamic",
        column_config=column_config,
        key=editor_key,
    )
    out = edited.to_dict("records")
    for row in out:
        row["category"] = category
        row["unit"] = unit
    return out


def render_catalog_tab() -> None:
    _init_catalog_state()
    st.subheader("Справочник номенклатуры и цен")
    st.caption(
        "Цены без НДС. Номенклатура подбирается автоматически по техническому расчёту; "
        "здесь можно править наименования и цены."
    )

    col_reset, _ = st.columns([1, 3])
    with col_reset:
        if st.button("Сбросить к Excel-смете", key="catalog_reset"):
            st.session_state["cost_catalog_records"] = catalog_to_records(DEFAULT_CATALOG)
            st.rerun()

    catalog = get_active_catalog()
    merged: list[dict] = []

    with st.expander("ВВ — взрывчатые вещества", expanded=True):
        merged.extend(
            _edit_category(
                title="",
                category="explosive",
                unit="кг",
                catalog=catalog,
                editor_key="catalog_editor_explosive",
            )
        )
    with st.expander("СВ — промежуточные детонаторы", expanded=True):
        merged.extend(
            _edit_category(
                title="",
                category="detonator",
                unit="кг",
                catalog=catalog,
                editor_key="catalog_editor_detonator",
                show_mass=True,
            )
        )
    with st.expander("СИ — НСИ скважинное (Искра-С, Rionel)", expanded=True):
        merged.extend(
            _edit_category(
                title="",
                category="downhole_nsi",
                unit="шт",
                catalog=catalog,
                editor_key="catalog_editor_downhole_nsi",
                show_length=True,
            )
        )
    with st.expander("СИ — НСИ поверхностное и стартовое", expanded=False):
        merged.extend(
            _edit_category(
                title="Поверхностное НСИ (Искра-П)",
                category="surface_nsi",
                unit="шт",
                catalog=catalog,
                editor_key="catalog_editor_surface_nsi",
            )
        )
        merged.extend(
            _edit_category(
                title="Стартовое НСИ (Искра-Старт)",
                category="start_nsi",
                unit="шт",
                catalog=catalog,
                editor_key="catalog_editor_start_nsi",
            )
        )

    st.session_state["cost_catalog_records"] = merged
    st.divider()
    render_drilling_price_readonly()
