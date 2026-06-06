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
from cost.depreciation_data import (
    DEFAULT_DEPRECIATION_ASSETS,
    calculate_depreciation_per_shift_rub,
    depreciation_assets_to_records,
    format_rub_amount,
    parse_rub_amount,
)
from cost.explosive_data import DEFAULT_EXPLOSIVES, explosives_to_records
from cost.rock_data import DEFAULT_ROCKS, rocks_to_records
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


def _rocks_dataframe() -> pd.DataFrame:
    from cost.references_store import get_rocks

    rocks = get_rocks(st.session_state)
    rows = [
        {
            "name": rock.name,
            "density_t_m3": rock.density_t_m3,
            "ucs_mpa": rock.ucs_mpa,
            "fissuring_ff": rock.fissuring_ff,
        }
        for rock in rocks
    ]
    return pd.DataFrame(rows)


def render_rocks_section() -> None:
    init_references_state(st.session_state)
    st.markdown("**Горные породы**")
    st.caption(
        "Плотность, прочность и трещиноватость используются в технологическом расчёте БВР "
        "на вкладке «Расчёт»."
    )

    col_reset, _ = st.columns([1, 3])
    with col_reset:
        if can_edit_references() and st.button("Сбросить породы", key="rocks_reset"):
            st.session_state["rock_records"] = rocks_to_records(DEFAULT_ROCKS)
            st.rerun()

    if require_admin_or_readonly(
        readonly_message="Справочник пород доступен только для просмотра. Войдите как администратор."
    ):
        edited = st.data_editor(
            _rocks_dataframe(),
            use_container_width=True,
            hide_index=True,
            num_rows="dynamic",
            column_config={
                "name": st.column_config.TextColumn("Порода", required=True, width="large"),
                "density_t_m3": st.column_config.NumberColumn(
                    "Плотность, т/м³", min_value=0.1, format="%.2f"
                ),
                "ucs_mpa": st.column_config.NumberColumn(
                    "Прочность UCS, МПа", min_value=0.0, format="%.0f"
                ),
                "fissuring_ff": st.column_config.NumberColumn(
                    "Трещиноватость, 1/м", min_value=0.0, format="%.1f"
                ),
            },
            key="rocks_editor",
        )
        st.session_state["rock_records"] = edited.to_dict("records")
    else:
        st.dataframe(_rocks_dataframe(), use_container_width=True, hide_index=True)


def _explosives_dataframe() -> pd.DataFrame:
    from cost.references_store import get_explosives

    items = get_explosives(st.session_state)
    rows = [
        {
            "key": item.key,
            "name": item.name,
            "density_t_m3": item.density_t_m3,
            "power_mj_kg": item.power_mj_kg,
            "chart_label": item.chart_label,
        }
        for item in items
    ]
    return pd.DataFrame(rows)


def render_explosives_section() -> None:
    init_references_state(st.session_state)
    st.markdown("**Взрывчатые вещества**")
    st.caption(
        "Плотность заряжания и теплота взрыва используются в технологическом расчёте БВР "
        "на вкладке «Расчёт»."
    )

    col_reset, _ = st.columns([1, 3])
    with col_reset:
        if can_edit_references() and st.button("Сбросить ВВ", key="explosives_reset"):
            st.session_state["explosive_records"] = explosives_to_records(DEFAULT_EXPLOSIVES)
            st.rerun()

    if require_admin_or_readonly(
        readonly_message="Справочник ВВ доступен только для просмотра. Войдите как администратор."
    ):
        edited = st.data_editor(
            _explosives_dataframe(),
            use_container_width=True,
            hide_index=True,
            num_rows="dynamic",
            column_config={
                "key": st.column_config.TextColumn(
                    "Ключ в UI", required=True, width="medium",
                    help="Подпись в выпадающем списке на вкладке «Расчёт».",
                ),
                "name": st.column_config.TextColumn(
                    "Наименование", required=True, width="medium",
                    help="Имя для BlastEngine.",
                ),
                "density_t_m3": st.column_config.NumberColumn(
                    "Плотность, т/м³", min_value=0.01, format="%.2f"
                ),
                "power_mj_kg": st.column_config.NumberColumn(
                    "Теплота, МДж/кг", min_value=0.01, format="%.2f"
                ),
                "chart_label": st.column_config.TextColumn(
                    "Подпись на схеме", width="small",
                    help="Краткая подпись на схеме заряда; пусто — имя заглавными.",
                ),
            },
            key="explosives_editor",
        )
        st.session_state["explosive_records"] = edited.to_dict("records")
    else:
        st.dataframe(_explosives_dataframe(), use_container_width=True, hide_index=True)


def _depreciation_assets_dataframe(*, formatted: bool = False) -> pd.DataFrame:
    from cost.references_store import get_depreciation_assets

    assets = get_depreciation_assets(st.session_state)
    rows = []
    for asset in assets:
        row = {
            "name": asset.name,
            "initial_cost_rub": (
                format_rub_amount(asset.initial_cost_rub, decimals=0)
                if formatted
                else asset.initial_cost_rub
            ),
            "useful_life_months": asset.useful_life_months,
            "productive_shifts_per_month": asset.productive_shifts_per_month,
            "depreciation_per_shift_rub": (
                format_rub_amount(asset.calculated_depreciation_per_shift_rub, decimals=2)
                if formatted
                else asset.calculated_depreciation_per_shift_rub
            ),
        }
        rows.append(row)
    return pd.DataFrame(rows)


def _depreciation_editor_column_config(*, formatted: bool) -> dict:
    money_column = st.column_config.TextColumn if formatted else st.column_config.NumberColumn
    initial_cost_kwargs = (
        {"help": "Можно вводить с пробелами: 21 903 000"}
        if formatted
        else {"min_value": 0.0, "format": "%.0f"}
    )
    return {
        "name": st.column_config.TextColumn("Наименование ОС", required=True, width="large"),
        "initial_cost_rub": money_column(
            "Первоначальная стоимость, руб",
            **initial_cost_kwargs,
        ),
        "useful_life_months": st.column_config.NumberColumn(
            "СПИ, мес.",
            min_value=1.0,
            format="%.0f",
            help="Срок полезного использования в месяцах.",
        ),
        "productive_shifts_per_month": st.column_config.NumberColumn(
            "Смен в месяц",
            min_value=0.1,
            format="%.1f",
            help="Количество производительных смен в месяц.",
        ),
        "depreciation_per_shift_rub": st.column_config.TextColumn(
            "Норма амортизации, руб/смена",
            disabled=True,
            help="Рассчитывается автоматически: стоимость ÷ СПИ ÷ смен в месяц.",
        ),
    }


def _depreciation_records_from_editor(rows: list[dict]) -> list[dict]:
    records: list[dict] = []
    for row in rows:
        name = str(row.get("name", "")).strip()
        if not name:
            continue
        initial_cost_rub = parse_rub_amount(row.get("initial_cost_rub"))
        useful_life_months = float(row.get("useful_life_months", 0) or 0)
        productive_shifts_per_month = float(row.get("productive_shifts_per_month", 0) or 0)
        records.append(
            {
                "name": name,
                "initial_cost_rub": initial_cost_rub,
                "useful_life_months": useful_life_months,
                "productive_shifts_per_month": productive_shifts_per_month,
                "depreciation_per_shift_rub": calculate_depreciation_per_shift_rub(
                    initial_cost_rub,
                    useful_life_months,
                    productive_shifts_per_month,
                ),
            }
        )
    return records


def render_depreciation_assets_section() -> None:
    init_references_state(st.session_state)
    st.markdown("**Нормы амортизации основных средств**")
    st.caption(
        "Справочник для расчёта амортизации ОС. Норма в смену рассчитывается автоматически: "
        "первоначальная стоимость ÷ СПИ, мес. ÷ смен в месяц."
    )

    if can_edit_references() and st.button("Сбросить ОС", key="depreciation_assets_reset"):
        st.session_state["depreciation_asset_records"] = depreciation_assets_to_records(
            DEFAULT_DEPRECIATION_ASSETS
        )
        st.rerun()

    if require_admin_or_readonly(
        readonly_message=(
            "Справочник амортизации ОС доступен только для просмотра. "
            "Войдите как администратор."
        )
    ):
        edited = st.data_editor(
            _depreciation_assets_dataframe(formatted=True),
            use_container_width=True,
            hide_index=True,
            num_rows="dynamic",
            column_config=_depreciation_editor_column_config(formatted=True),
            key="depreciation_assets_editor",
        )
        st.session_state["depreciation_asset_records"] = _depreciation_records_from_editor(
            edited.to_dict("records")
        )
    else:
        st.dataframe(
            _depreciation_assets_dataframe(formatted=True),
            use_container_width=True,
            hide_index=True,
            column_config=_depreciation_editor_column_config(formatted=True),
        )
