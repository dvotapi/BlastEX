"""Совместимый интерфейс проверки прав редактора справочников."""
from __future__ import annotations

import streamlit as st
from cost.auth import can_edit_references as _can_edit_references
from cost.auth import current_user, render_user_panel


def is_admin_authenticated() -> bool:
    user = current_user()
    return bool(user and user.role == "admin")


def admin_editing_enabled() -> bool:
    return current_user() is not None


def can_edit_references() -> bool:
    return _can_edit_references()


def render_admin_panel() -> None:
    render_user_panel()


def require_admin_or_readonly(*, readonly_message: str) -> bool:
    """True — можно редактировать, False — только просмотр."""
    if can_edit_references():
        return True
    st.info(readonly_message)
    return False
