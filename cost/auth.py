"""Внутренняя авторизация Streamlit без внешнего провайдера идентификации."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import streamlit as st


PBKDF2_ITERATIONS = 600_000
ALLOWED_ROLES = {"admin", "reference_editor", "user"}


@dataclass(frozen=True)
class AuthUser:
    email: str
    password_hash: str
    role: str
    display_name: str = ""
    organization_id: str = "default"
    organization_name: str = "Внутренняя организация"
    active: bool = True


def hash_password(password: str, *, salt: bytes | None = None) -> str:
    """Создать переносимый PBKDF2-SHA256 хеш для secrets.toml."""
    if not password:
        raise ValueError("Пароль не может быть пустым.")
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS
    )
    return "$".join(
        (
            "pbkdf2_sha256",
            str(PBKDF2_ITERATIONS),
            base64.urlsafe_b64encode(salt).decode("ascii"),
            base64.urlsafe_b64encode(digest).decode("ascii"),
        )
    )


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, iterations_raw, salt_raw, digest_raw = encoded.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        iterations = int(iterations_raw)
        if iterations < 100_000 or iterations > 2_000_000:
            return False
        salt = base64.urlsafe_b64decode(salt_raw.encode("ascii"))
        expected = base64.urlsafe_b64decode(digest_raw.encode("ascii"))
    except (ValueError, TypeError):
        return False
    actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return hmac.compare_digest(actual, expected)


def _records_from_config() -> list[dict[str, Any]]:
    env_value = os.getenv("BLASTEX_USERS_JSON", "").strip()
    if env_value:
        try:
            value = json.loads(env_value)
            return list(value) if isinstance(value, list) else []
        except json.JSONDecodeError:
            return []
    try:
        secrets_path = Path(__file__).resolve().parent.parent / ".streamlit" / "secrets.toml"
        if secrets_path.exists():
            config = tomllib.loads(secrets_path.read_text(encoding="utf-8")).get(
                "blastex", {}
            )
        else:
            config = {}
        value = config.get("users", [])
        records = [dict(item) for item in value]
        if records:
            return records
        # Переходный режим для уже установленного BLASTEX_ADMIN_PASSWORD.
        legacy_password = os.getenv("BLASTEX_ADMIN_PASSWORD", "").strip() or str(
            config.get("admin_password", "")
        ).strip()
        if legacy_password:
            legacy_email = os.getenv("BLASTEX_ADMIN_EMAIL", "admin@localhost").strip()
            return [
                {
                    "email": legacy_email,
                    "password_hash": hash_password(
                        legacy_password, salt=b"blastex-legacy-v1"
                    ),
                    "role": "admin",
                    "display_name": "Администратор",
                    "organization_id": "default",
                    "organization_name": "Внутренняя организация",
                }
            ]
        return []
    except (AttributeError, FileNotFoundError, KeyError, TypeError, tomllib.TOMLDecodeError):
        return []


def configured_users() -> list[AuthUser]:
    users: list[AuthUser] = []
    for item in _records_from_config():
        email = str(item.get("email", "")).strip().casefold()
        password_hash = str(item.get("password_hash", "")).strip()
        role = str(item.get("role", "user")).strip()
        if not email or not password_hash or role not in ALLOWED_ROLES:
            continue
        users.append(
            AuthUser(
                email=email,
                password_hash=password_hash,
                role=role,
                display_name=str(item.get("display_name", "")).strip(),
                organization_id=str(item.get("organization_id", "default")).strip()
                or "default",
                organization_name=str(
                    item.get("organization_name", "Внутренняя организация")
                ).strip()
                or "Внутренняя организация",
                active=bool(item.get("active", True)),
            )
        )
    return users


def current_user() -> AuthUser | None:
    payload = st.session_state.get("auth_user")
    if not isinstance(payload, dict):
        return None
    try:
        user = AuthUser(**payload)
    except TypeError:
        return None
    return user if user.active else None


def is_authenticated() -> bool:
    return current_user() is not None


def can_edit_references() -> bool:
    user = current_user()
    return bool(user and user.role in {"admin", "reference_editor"})


def _login(email: str, password: str) -> bool:
    normalized_email = email.strip().casefold()
    user = next(
        (item for item in configured_users() if item.email == normalized_email and item.active),
        None,
    )
    if user is None or not verify_password(password, user.password_hash):
        return False
    st.session_state["auth_user"] = user.__dict__.copy()
    st.session_state["admin_authenticated"] = user.role == "admin"
    return True


def render_login_gate() -> bool:
    """Показать форму входа. Возвращает True только для вошедшего пользователя."""
    if is_authenticated():
        return True

    st.title("💥 BlastEX")
    st.caption("Внутренний сервис расчёта параметров буровзрывных работ")
    users = configured_users()
    if not users:
        st.error(
            "Доступ не настроен. Добавьте внутренние учётные записи в "
            "`.streamlit/secrets.toml` или `BLASTEX_USERS_JSON`."
        )
    with st.form("internal_login_form"):
        email = st.text_input("Email", disabled=not users)
        password = st.text_input("Пароль", type="password", disabled=not users)
        submitted = st.form_submit_button("Войти", disabled=not users)
        if submitted:
            if _login(email, password):
                st.rerun()
            st.error("Неверный email или пароль.")

    st.divider()
    st.subheader("Доступ для внешних организаций")
    st.info(
        "Подключение внешних организаций пока недоступно. "
        "Сейчас BlastEX работает только для сотрудников компании."
    )
    st.button("Подать заявку на подключение", disabled=True)
    return False


def render_user_panel() -> None:
    user = current_user()
    if user is None:
        return
    role_labels = {
        "admin": "Администратор",
        "reference_editor": "Редактор справочников",
        "user": "Пользователь",
    }
    with st.sidebar:
        st.markdown("### Пользователь")
        st.write(user.display_name or user.email)
        st.caption(f"{role_labels[user.role]} · {user.organization_name}")
        st.caption("Внешние организации: подключение закрыто")
        if st.button("Выйти", key="auth_logout"):
            for key in list(st.session_state.keys()):
                del st.session_state[key]
            st.rerun()
