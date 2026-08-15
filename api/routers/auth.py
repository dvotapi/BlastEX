"""Авторизация внутреннего web-интерфейса."""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Cookie, HTTPException, Response, status
from pydantic import BaseModel, Field

from api.security import SESSION_COOKIE, create_session_token, read_session_token
from cost.auth import configured_users, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    email: str = Field(..., min_length=3, max_length=254)
    password: str = Field(..., min_length=1, max_length=1024)


class CurrentUserResponse(BaseModel):
    email: str
    display_name: str
    role: str
    organization_id: str
    organization_name: str


def _response_for_email(email: str) -> CurrentUserResponse:
    user = next(
        (item for item in configured_users() if item.email == email.casefold() and item.active),
        None,
    )
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Сессия недействительна.")
    return CurrentUserResponse(
        email=user.email,
        display_name=user.display_name or user.email,
        role=user.role,
        organization_id=user.organization_id,
        organization_name=user.organization_name,
    )


@router.post("/login", response_model=CurrentUserResponse)
def login(payload: LoginRequest, response: Response) -> CurrentUserResponse:
    email = payload.email.strip().casefold()
    user = next((item for item in configured_users() if item.email == email and item.active), None)
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Неверный email или пароль.")
    expires = datetime.now(timezone.utc) + timedelta(hours=12)
    token = create_session_token(user.email, user.role, user.organization_id, int(expires.timestamp()))
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=12 * 60 * 60,
        httponly=True,
        secure=os.getenv("BLASTEX_COOKIE_SECURE", "true").lower() not in {"0", "false", "no"},
        samesite="lax",
        path="/",
    )
    return _response_for_email(user.email)


@router.get("/me", response_model=CurrentUserResponse)
def me(blastex_session: str | None = Cookie(default=None)) -> CurrentUserResponse:
    payload = read_session_token(blastex_session)
    if payload is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Требуется вход.")
    return _response_for_email(str(payload["sub"]))


@router.post("/logout", status_code=204)
def logout(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE, path="/")
