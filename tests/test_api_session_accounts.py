"""Сессия действует, пока действует учётка, и несёт её текущую роль.

Cookie ``blastex_session`` подписан на 12 часов и хранит роль и организацию
на момент входа. Раньше API верил им до истечения срока: отключённая,
удалённая или переведённая учётка продолжала работать со старыми правами.
Решение владельца: роль берётся из текущей записи учётки, а перенос в другую
организацию гасит сессию — человек входит заново. Внутренний ключ от учёток
не зависит.
"""
from __future__ import annotations

import hashlib
import json
import uuid
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from api.routers import auth
from api.security import require_admin, require_internal_access
from cost.auth import configured_users, find_active_user, hash_password
from tests.session_fixtures import session_client

EMAIL = "engineer@example.ru"


@pytest.fixture(autouse=True)
def _secrets(monkeypatch) -> None:
    monkeypatch.setenv("BLASTEX_API_KEY", "test-api-key")
    monkeypatch.setenv("BLASTEX_SESSION_SECRET", "test-session-secret")


def _accounts(monkeypatch, *records: dict) -> None:
    """Учётки в том виде, в каком их задаёт `BLASTEX_USERS_JSON` на проде."""

    monkeypatch.setenv(
        "BLASTEX_USERS_JSON",
        json.dumps([{"password_hash": "pbkdf2_sha256$1$x$y", **record} for record in records]),
    )


def _app() -> FastAPI:
    app = FastAPI()
    app.include_router(auth.router, prefix="/api/v1")

    @app.get("/api/v1/probe")
    def probe(session: dict = Depends(require_internal_access)) -> dict:
        return session

    @app.get("/api/v1/admin-probe")
    def admin_probe(session: dict = Depends(require_admin)) -> dict:
        return session

    return app


def _signed_in(email: str = EMAIL, role: str = "admin", organization_id: str = "default") -> TestClient:
    return session_client(_app(), email, role, organization_id)


def test_active_account_session_carries_account_identity(monkeypatch) -> None:
    _accounts(monkeypatch, {"email": EMAIL, "role": "admin", "organization_id": "default"})
    response = _signed_in().get("/api/v1/probe")
    assert response.status_code == 200
    assert {key: response.json()[key] for key in ("sub", "role", "org")} == {
        "sub": EMAIL, "role": "admin", "org": "default",
    }


def test_disabled_account_session_is_rejected(monkeypatch) -> None:
    _accounts(monkeypatch, {"email": EMAIL, "role": "admin", "organization_id": "default", "active": False})
    assert _signed_in().get("/api/v1/probe").status_code == 401


def test_removed_account_session_is_rejected(monkeypatch) -> None:
    _accounts(monkeypatch, {"email": "other@example.ru", "role": "admin", "organization_id": "default"})
    assert _signed_in().get("/api/v1/probe").status_code == 401


def test_demoted_account_loses_admin_rights_at_once(monkeypatch) -> None:
    _accounts(monkeypatch, {"email": EMAIL, "role": "user", "organization_id": "default"})
    client = _signed_in(role="admin")
    assert client.get("/api/v1/probe").json()["role"] == "user"
    assert client.get("/api/v1/admin-probe").status_code == 403


def test_promoted_account_gets_admin_rights_without_relogin(monkeypatch) -> None:
    _accounts(monkeypatch, {"email": EMAIL, "role": "admin", "organization_id": "default"})
    assert _signed_in(role="user").get("/api/v1/admin-probe").status_code == 200


def test_moved_account_session_is_rejected(monkeypatch) -> None:
    _accounts(monkeypatch, {"email": EMAIL, "role": "admin", "organization_id": "org-b"})
    client = _signed_in(organization_id="org-a")
    assert client.get("/api/v1/probe").status_code == 401
    assert client.get("/api/v1/auth/me").status_code == 401


def test_service_key_works_without_accounts(monkeypatch) -> None:
    _accounts(monkeypatch)
    client = TestClient(_app(), headers={"X-API-Key": "test-api-key"})
    response = client.get("/api/v1/probe")
    assert response.status_code == 200
    assert response.json() == {"sub": "api-key", "role": "service", "org": "default"}


def test_cookie_cannot_claim_service_actor(monkeypatch) -> None:
    _accounts(monkeypatch, {"email": EMAIL, "role": "admin", "organization_id": "default"})
    assert _signed_in(email="api-key", role="service").get("/api/v1/probe").status_code == 401


def test_legacy_admin_password_is_hashed_once(monkeypatch, tmp_path: Path) -> None:
    """Учётки читаются на каждом запросе: PBKDF2 на 600 000 итераций — один раз."""

    monkeypatch.delenv("BLASTEX_USERS_JSON", raising=False)
    monkeypatch.setenv("BLASTEX_USERS_FILE", str(tmp_path / "missing.toml"))
    # Свой пароль на каждый прогон: кеш хеша живёт весь процесс.
    monkeypatch.setenv("BLASTEX_ADMIN_PASSWORD", f"legacy-{uuid.uuid4()}")
    with patch("cost.auth.hashlib.pbkdf2_hmac", wraps=hashlib.pbkdf2_hmac) as pbkdf2:
        first = configured_users()
        second = configured_users()
    assert [user.email for user in first] == [user.email for user in second] == ["admin@localhost"]
    assert pbkdf2.call_count == 1


def test_account_lookup_ignores_case_and_spaces(monkeypatch) -> None:
    """Вход и сверка сессии ищут учётку одинаково: email без учёта регистра."""

    _accounts(monkeypatch, {"email": "Engineer@Example.RU", "role": "user", "organization_id": "default"})
    user = find_active_user("  ENGINEER@example.ru ")
    assert user is not None and user.email == EMAIL


@pytest.mark.parametrize("flag", ["false", "False", "0", "no", 0])
def test_account_disabled_by_written_flag_has_no_session(monkeypatch, flag) -> None:
    """`"active":"false"` в кавычках отключает учётку так же, как `false`."""

    _accounts(monkeypatch, {"email": EMAIL, "role": "admin", "organization_id": "default", "active": flag})
    assert _signed_in().get("/api/v1/probe").status_code == 401


def test_broken_accounts_entry_fails_closed(monkeypatch) -> None:
    """Битая запись в списке учёток — 401 для cookie, а не 500 во всём API; ключ работает."""

    monkeypatch.setenv("BLASTEX_USERS_JSON", json.dumps([EMAIL]))
    assert _signed_in().get("/api/v1/probe").status_code == 401
    key_client = TestClient(_app(), headers={"X-API-Key": "test-api-key"})
    assert key_client.get("/api/v1/probe").status_code == 200


def test_unreadable_accounts_file_fails_closed(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.delenv("BLASTEX_USERS_JSON", raising=False)
    monkeypatch.delenv("BLASTEX_ADMIN_PASSWORD", raising=False)
    broken = tmp_path / "secrets.toml"
    broken.write_bytes(b"\xff\xfe[blastex]")
    monkeypatch.setenv("BLASTEX_USERS_FILE", str(broken))
    assert _signed_in().get("/api/v1/probe").status_code == 401


def test_login_opens_session_of_current_account(monkeypatch) -> None:
    """Вход выдаёт cookie, `/auth/me` и API видят учётку; после отключения — 401."""

    record = {
        "email": "Engineer@Example.ru",
        "password_hash": hash_password("верный пароль", salt=b"session-account-t"),
        "role": "reference_editor",
        "display_name": "Инженер",
        "organization_id": "default",
        "organization_name": "Карьер",
    }
    monkeypatch.setenv("BLASTEX_USERS_JSON", json.dumps([record]))
    # Клиент тестов ходит по http: cookie с Secure он не вернул бы.
    monkeypatch.setenv("BLASTEX_COOKIE_SECURE", "false")
    client = TestClient(_app())

    assert client.post("/api/v1/auth/login", json={"email": EMAIL, "password": "неверный"}).status_code == 401
    login = client.post("/api/v1/auth/login", json={"email": " ENGINEER@example.ru", "password": "верный пароль"})
    assert login.status_code == 200
    me = client.get("/api/v1/auth/me").json()
    assert me == {
        "email": EMAIL,
        "display_name": "Инженер",
        "role": "reference_editor",
        "organization_id": "default",
        "organization_name": "Карьер",
    }
    assert client.get("/api/v1/probe").json()["role"] == "reference_editor"

    monkeypatch.setenv("BLASTEX_USERS_JSON", json.dumps([{**record, "active": False}]))
    assert client.get("/api/v1/auth/me").status_code == 401
    assert client.get("/api/v1/probe").status_code == 401
