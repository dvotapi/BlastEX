"""Вход в тестах API: действующая учётка и cookie её сессии.

API сверяет cookie с текущими учётками (`api/security.py::read_user_session`),
поэтому сессия без учётки в `BLASTEX_USERS_JSON` ничего не открывает.
"""
from __future__ import annotations

import json
import os
import time

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.security import SESSION_COOKIE, create_session_token


def add_account(
    monkeypatch: pytest.MonkeyPatch, email: str, role: str, organization_id: str = "default"
) -> None:
    """Добавить действующую учётку в `BLASTEX_USERS_JSON`; запись с тем же email заменяется."""

    records = [
        record
        for record in json.loads(os.getenv("BLASTEX_USERS_JSON", "") or "[]")
        if record.get("email") != email
    ]
    records.append(
        {
            "email": email,
            "password_hash": "pbkdf2_sha256$1$x$y",
            "role": role,
            "organization_id": organization_id,
        }
    )
    monkeypatch.setenv("BLASTEX_USERS_JSON", json.dumps(records))


def signed_in_client(
    app: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
    email: str,
    role: str,
    organization_id: str = "default",
) -> TestClient:
    """Клиент вошедшей учётки — без внутреннего ключа."""

    add_account(monkeypatch, email, role, organization_id)
    token = create_session_token(email, role, organization_id, int(time.time()) + 3600)
    client = TestClient(app)
    client.cookies.set(SESSION_COOKIE, token)
    return client
