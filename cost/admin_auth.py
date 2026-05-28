"""Простая admin-авторизация для редактирования справочников."""
from __future__ import annotations

import hmac
import os
from pathlib import Path

import streamlit as st


def _project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _secrets_toml_path() -> Path:
    return _project_root() / ".streamlit" / "secrets.toml"


def _configured_admin_password() -> str | None:
    env_password = os.environ.get("BLASTEX_ADMIN_PASSWORD", "").strip()
    if env_password:
        return env_password
    try:
        secret = st.secrets.get("blastex", {}).get("admin_password")
        if secret:
            return str(secret).strip()
    except (AttributeError, FileNotFoundError, KeyError):
        pass
    return None


def _admin_setup_hint() -> str:
    secrets_path = _secrets_toml_path()
    example_path = secrets_path.with_suffix(".toml.example")
    if not secrets_path.exists() and example_path.exists():
        return (
            "Редактирование справочников отключено: нет файла "
            f"`{secrets_path.relative_to(_project_root())}`. "
            f"Скопируйте `{example_path.relative_to(_project_root())}` "
            "и задайте пароль, затем **перезапустите** Streamlit."
        )
    return (
        "Редактирование справочников отключено. "
        "Задайте переменную окружения `BLASTEX_ADMIN_PASSWORD` "
        "или `[blastex].admin_password` в `.streamlit/secrets.toml`, "
        "затем перезапустите Streamlit."
    )


def is_admin_authenticated() -> bool:
    return bool(st.session_state.get("admin_authenticated"))


def admin_editing_enabled() -> bool:
    return _configured_admin_password() is not None


def can_edit_references() -> bool:
    return admin_editing_enabled() and is_admin_authenticated()


def render_admin_panel() -> None:
    """Блок входа администратора в боковой панели."""
    with st.sidebar:
        st.markdown("### Администрирование")

        if not admin_editing_enabled():
            st.caption(_admin_setup_hint())
            return

        if is_admin_authenticated():
            st.success("Режим администратора")
            if st.button("Выйти", key="admin_logout"):
                st.session_state["admin_authenticated"] = False
                st.rerun()
            return

        with st.form("admin_login_form", clear_on_submit=False):
            password = st.text_input("Пароль администратора", type="password")
            submitted = st.form_submit_button("Войти")
            if submitted:
                expected = _configured_admin_password() or ""
                if hmac.compare_digest(password, expected):
                    st.session_state["admin_authenticated"] = True
                    st.rerun()
                else:
                    st.error("Неверный пароль")


def require_admin_or_readonly(*, readonly_message: str) -> bool:
    """True — можно редактировать, False — только просмотр."""
    if can_edit_references():
        return True
    st.info(readonly_message)
    return False
