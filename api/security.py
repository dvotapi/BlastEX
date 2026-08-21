"""Fail-closed защита внутреннего REST API."""
from __future__ import annotations

import hmac
import hashlib
import json
import os
from base64 import urlsafe_b64decode, urlsafe_b64encode
from datetime import datetime, timezone

from fastapi import Cookie, Depends, Header, HTTPException, status

SESSION_COOKIE = "blastex_session"


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
    session = read_session_token(blastex_session)
    if session is not None:
        return session
    expected = os.getenv("BLASTEX_API_KEY", "").strip()
    if expected and x_api_key and hmac.compare_digest(x_api_key, expected):
        return {"sub": "api-key", "role": "service", "org": "default"}
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Требуется вход во внутренний сервис.",
    )


def current_team_id(session: dict[str, object] = Depends(require_internal_access)) -> str:
    """ID команды текущего пользователя (или дефолтная команда для service-ключа)."""
    org = session.get("org")
    return str(org) if org else "default"


def require_reference_editor(
    session: dict[str, object] = Depends(require_internal_access),
) -> dict[str, object]:
    """Только admin / reference_editor (и внутренний service-ключ) могут писать справочники."""
    role = str(session.get("role", ""))
    if role in {"admin", "reference_editor", "service"}:
        return session
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Редактирование справочников доступно администратору или редактору.",
    )
