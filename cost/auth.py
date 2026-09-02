"""Внутренние учётные записи BlastEX без внешнего провайдера идентификации.

Модуль только читает и проверяет учётные записи: интерфейс входа живёт в
React, сессии — в `api/security.py`.
"""
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
    """Создать переносимый PBKDF2-SHA256 хеш для файла или BLASTEX_USERS_JSON."""
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


def _users_file() -> Path:
    """Файл с учётными записями.

    Основной способ — переменная `BLASTEX_USERS_JSON`. Путь к файлу задаётся
    `BLASTEX_USERS_FILE`; старый `.streamlit/secrets.toml` читается как
    совместимость для уже развёрнутых установок.
    """

    configured = os.getenv("BLASTEX_USERS_FILE", "").strip()
    if configured:
        return Path(configured)
    return Path(__file__).resolve().parent.parent / ".streamlit" / "secrets.toml"


def _records_from_config() -> list[dict[str, Any]]:
    env_value = os.getenv("BLASTEX_USERS_JSON", "").strip()
    if env_value:
        try:
            value = json.loads(env_value)
            return list(value) if isinstance(value, list) else []
        except json.JSONDecodeError:
            return []
    try:
        secrets_path = _users_file()
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
