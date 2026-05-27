"""UI: команда, сценарий, сохранение справочников."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from cost.drilling_data import DEFAULT_OBJECT_NAME, DEFAULT_WORK_OBJECTS
from cost.engine import CostEngine
from cost.persistence import (
    DEFAULT_TEAM_ID,
    bootstrap_team_scenarios,
    is_snapshot_dirty,
    load_team_settings,
    load_workspace_scenario,
    save_current_workspace,
    save_team_settings,
)
from cost.scenarios import DEFAULT_SCENARIO_ID, get_scenario_calc_profile, get_scenario_template, list_scenario_templates


def get_active_scenario_id() -> str:
    return str(st.session_state.get("active_scenario_id", DEFAULT_SCENARIO_ID))


def get_scenario_phase_overrides() -> dict[str, bool]:
    return dict(st.session_state.get("scenario_phase_overrides", {}))


def is_module_enabled_for_scenario(module: str) -> bool:
    return CostEngine().scenario_supports_module(st.session_state, module)


def init_workspace() -> None:
    if st.session_state.get("workspace_bootstrapped"):
        return

    team_id = DEFAULT_TEAM_ID
    bootstrap_team_scenarios(team_id)
    settings = load_team_settings(team_id)
    load_workspace_scenario(
        st.session_state,
        team_id=team_id,
        scenario_id=settings.active_scenario_id,
    )
    st.session_state["active_work_object_name"] = settings.active_work_object_name
    st.session_state["workspace_team_name"] = settings.team_name
    st.session_state["workspace_bootstrapped"] = True


def _switch_scenario(team_id: str, scenario_id: str) -> None:
    load_workspace_scenario(st.session_state, team_id=team_id, scenario_id=scenario_id)
    settings = load_team_settings(team_id)
    settings.active_scenario_id = scenario_id
    save_team_settings(settings)
    st.session_state.pop("scenario_pending_switch", None)


def render_workspace_toolbar() -> None:
    init_workspace()

    templates = list_scenario_templates()
    template_ids = [template.id for template in templates]
    template_labels = {template.id: template.name for template in templates}

    team_id = str(st.session_state.get("workspace_team_id", DEFAULT_TEAM_ID))
    team_name = str(st.session_state.get("workspace_team_name", team_id))
    active_scenario_id = get_active_scenario_id()
    dirty = is_snapshot_dirty(st.session_state)

    pending_switch = st.session_state.get("scenario_pending_switch")
    if pending_switch and pending_switch != active_scenario_id:
        st.warning(
            f"Есть несохранённые изменения. Сохраните их или отмените переключение на "
            f"«{template_labels.get(pending_switch, pending_switch)}»."
        )
        warn_col1, warn_col2, warn_col3 = st.columns([1, 1, 2])
        with warn_col1:
            if st.button("Сохранить и переключить", key="workspace_save_and_switch"):
                save_current_workspace(st.session_state)
                _switch_scenario(team_id, str(pending_switch))
                st.rerun()
        with warn_col2:
            if st.button("Переключить без сохранения", key="workspace_discard_and_switch"):
                _switch_scenario(team_id, str(pending_switch))
                st.rerun()
        with warn_col3:
            if st.button("Отменить переключение", key="workspace_cancel_switch"):
                st.session_state.pop("scenario_pending_switch", None)
                st.session_state["scenario_selector"] = active_scenario_id
                st.rerun()

    bar1, bar2, bar3, bar4, bar5 = st.columns([1.1, 1.4, 1.6, 0.9, 1.2])
    with bar1:
        st.markdown(f"**Команда:** {team_name}")
    with bar2:
        object_names = [obj.name for obj in DEFAULT_WORK_OBJECTS]
        current_object = str(st.session_state.get("active_work_object_name", DEFAULT_OBJECT_NAME))
        st.selectbox(
            "Объект работ",
            options=object_names,
            index=object_names.index(current_object) if current_object in object_names else 0,
            key="active_work_object_name",
        )
    with bar3:
        selected_scenario = st.selectbox(
            "Сценарий",
            options=template_ids,
            index=template_ids.index(active_scenario_id)
            if active_scenario_id in template_ids
            else 0,
            format_func=lambda scenario_id: template_labels.get(scenario_id, scenario_id),
            key="scenario_selector",
        )
        if selected_scenario != active_scenario_id and pending_switch is None:
            if dirty:
                st.session_state["scenario_pending_switch"] = selected_scenario
                st.rerun()
            _switch_scenario(team_id, selected_scenario)
            st.rerun()
    with bar4:
        status = "есть несохранённые изменения" if dirty else "сохранено"
        st.caption(f"Статус: **{status}**")
    with bar5:
        save_col, reload_col = st.columns(2)
        with save_col:
            if st.button("Сохранить", type="primary", key="workspace_save"):
                path = save_current_workspace(st.session_state)
                st.success(f"Сохранено: `{path.name}`")
                st.session_state.pop("scenario_pending_switch", None)
        with reload_col:
            if st.button("Загрузить", key="workspace_reload"):
                load_workspace_scenario(
                    st.session_state,
                    team_id=team_id,
                    scenario_id=active_scenario_id,
                )
                st.session_state.pop("scenario_pending_switch", None)
                st.rerun()

    active_template = get_scenario_template(active_scenario_id)
    calc_profile = get_scenario_calc_profile(active_scenario_id)
    if active_template:
        overrides = get_scenario_phase_overrides()
        enabled_phases = [
            phase.name
            for phase in active_template.phases
            if overrides.get(phase.id, phase.enabled)
        ]
        modules = sorted(active_template.enabled_modules(overrides))
        st.caption(
            f"{calc_profile.ui_caption} "
            f"Подэтапы: {', '.join(enabled_phases) or '—'}. "
            f"Модули: {', '.join(modules) or '—'}."
        )

        if len(active_template.phases) > 1:
            with st.expander("Подэтапы сценария", expanded=False):
                phase_rows = []
                for phase in active_template.phases:
                    enabled = overrides.get(phase.id, phase.enabled)
                    phase_rows.append({
                        "id": phase.id,
                        "name": phase.name,
                        "enabled": enabled,
                        "modules": ", ".join(phase.modules),
                    })
                edited = st.data_editor(
                    pd.DataFrame(phase_rows),
                    use_container_width=True,
                    hide_index=True,
                    column_config={
                        "id": None,
                        "name": st.column_config.TextColumn("Подэтап", disabled=True),
                        "enabled": st.column_config.CheckboxColumn("Включён"),
                        "modules": st.column_config.TextColumn("Модули", disabled=True),
                    },
                    key=f"scenario_phases_{active_scenario_id}",
                )
                new_overrides = {
                    str(row["id"]): bool(row["enabled"]) for row in edited.to_dict("records")
                }
                if new_overrides != overrides:
                    st.session_state["scenario_phase_overrides"] = new_overrides

    st.divider()
