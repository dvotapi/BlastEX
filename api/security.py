"""Fail-closed защита внутреннего REST API."""
from __future__ import annotations

import hmac
import hashlib
import json
import os
from base64 import urlsafe_b64decode, urlsafe_b64encode
from datetime import datetime, timezone

from fastapi import Cookie, Depends, Header, HTTPException, status

from cost.auth import ALLOWED_ROLES, AuthUser, find_active_user

SESSION_COOKIE = "blastex_session"
# От этого имени действует внутренний ключ. Доменные шлюзы «подтверждает
# человек» держат его в своих AUTO_ACTORS.
SERVICE_ACTOR = "api-key"


def _session_secret() -> str:
    return os.getenv("BLASTEX_SESSION_SECRET", "").strip()


def create_session_token(email: str, role: str, organization_id: str, expires_at: int) -> str:
    secret = _session_secret()
    if not secret:
        raise RuntimeError("BLASTEX_SESSION_SECRET is not configured")
    payload = json.dumps(
        {"sub": email, "role": role, "org": organization_id, "exp": expires_at},
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    encoded = urlsafe_b64encode(payload).rstrip(b"=").decode("ascii")
    signature = hmac.new(secret.encode("utf-8"), encoded.encode("ascii"), hashlib.sha256).digest()
    return f"{encoded}.{urlsafe_b64encode(signature).rstrip(b'=').decode('ascii')}"


def read_session_token(token: str | None) -> dict[str, object] | None:
    secret = _session_secret()
    if not token or not secret or "." not in token:
        return None
    encoded, signature_raw = token.split(".", 1)
    expected = hmac.new(secret.encode("utf-8"), encoded.encode("ascii"), hashlib.sha256).digest()
    try:
        actual = urlsafe_b64decode(signature_raw + "=" * (-len(signature_raw) % 4))
        if not hmac.compare_digest(actual, expected):
            return None
        payload = json.loads(
            urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)).decode("utf-8")
        )
        if int(payload.get("exp", 0)) <= int(datetime.now(timezone.utc).timestamp()):
            return None
        return payload
    except (ValueError, TypeError, json.JSONDecodeError):
        return None


def session_account(token: str | None) -> AuthUser | None:
    """Учётка сессии: подписанный cookie и действующая сейчас запись.

    Cookie живёт 12 часов и помнит роль и организацию на момент входа.
    Права дальше берутся из возвращённой записи — понижение роли действует
    сразу. Отключённая, удалённая или перенесённая в другую организацию
    учётка сессии не имеет: человек входит заново.
    """
    payload = read_session_token(token)
    if payload is None:
        return None
    user = find_active_user(str(payload.get("sub", "")))
    if user is None or user.organization_id != str(payload.get("org", "")):
        return None
    return user


def require_internal_api_key(x_api_key: str | None = Header(default=None)) -> None:
    expected = os.getenv("BLASTEX_API_KEY", "").strip()
    if not expected:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Внутренний API не настроен.",
        )
    if x_api_key is None or not hmac.compare_digest(x_api_key, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Требуется действительный внутренний API-ключ.",
            headers={"WWW-Authenticate": "ApiKey"},
        )


def require_internal_access(
    x_api_key: str | None = Header(default=None),
    blastex_session: str | None = Cookie(default=None),
) -> dict[str, object]:
    user = session_account(blastex_session)
    if user is not None:
        return {"sub": user.email, "role": user.role, "org": user.organization_id}
    expected = os.getenv("BLASTEX_API_KEY", "").strip()
    if expected and x_api_key and hmac.compare_digest(x_api_key, expected):
        return {"sub": SERVICE_ACTOR, "role": "service", "org": "default"}
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Требуется вход во внутренний сервис.",
    )


def current_team_id(session: dict[str, object] = Depends(require_internal_access)) -> str:
    """ID команды текущего пользователя (или дефолтная команда для service-ключа)."""
    org = session.get("org")
    return str(org) if org else "default"


ADMIN_ROLES = {"admin", "service"}
REFERENCE_EDITOR_ROLES = {"admin", "reference_editor", "service"}
# Роли учёток людей; у внутреннего ключа роль service.
HUMAN_ROLES = frozenset(ALLOWED_ROLES)


def is_reference_editor(session: dict[str, object]) -> bool:
    return str(session.get("role", "")) in REFERENCE_EDITOR_ROLES


def require_reference_editor(
    session: dict[str, object] = Depends(require_internal_access),
) -> dict[str, object]:
    """Только admin / reference_editor (и внутренний service-ключ) могут писать справочники."""
    if is_reference_editor(session):
        return session
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Редактирование справочников доступно администратору или редактору.",
    )


def require_human(
    session: dict[str, object] = Depends(require_internal_access),
) -> dict[str, object]:
    """Утверждение, согласование и смену статуса подтверждает вошедший человек.

    Внутренний ключ видит организацию default целиком, но решение, принятое
    им, ни за кем не числится — поэтому статусы он не меняет.
    """
    if str(session.get("role", "")) in HUMAN_ROLES:
        return session
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail=(
            "Утверждение, согласование и смену статуса подтверждает "
            "пользователь под своей учётной записью, а не внутренний ключ."
        ),
    )


def require_admin(
    session: dict[str, object] = Depends(require_internal_access),
) -> dict[str, object]:
    """Настройки организации меняет только администратор (или service-ключ).

    Редактор справочников сюда не входит: обмен со схемой ``public`` — это
    доступ к чужой системе, а не правка данных.
    """
    if str(session.get("role", "")) in ADMIN_ROLES:
        return session
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Настройки обмена с project1 доступны только администратору.",
    )
