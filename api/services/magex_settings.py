"""Настройки интеграции с MagEX: ключ подписи, открытый набор, организации (TASK-018, PR 7, §2).

Читаются один раз (кэш процесса) и проверяются при старте API: ключ — EC
P-256 с закрытой частью; в `BLASTEX_JWKS_EXTRA` нет `d` и повторов `kid`;
тестовый ключ MagEX (по отпечатку RFC 7638) — только с `BLASTEX_ALLOW_TEST_KEY`.
Ошибка настройки — отказ старта, а не 500 на половине запросов.
"""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any

from api import config
from design.magex.jws import (
    TEST_KEY_THUMBPRINT,
    SigningKey,
    SigningKeyError,
    jwk_thumbprint,
    load_signing_key,
    parse_public_jwk,
)

__all__ = [
    "MagexSettings",
    "magex_mode",
    "magex_settings",
    "offline_reason",
    "reset_magex_settings",
]


@dataclass(frozen=True)
class MagexSettings:
    signing_key: SigningKey | None
    published_keys: tuple[dict[str, str], ...]
    organizations: dict[str, str] = field(default_factory=dict)
    api_url: str = ""
    max_length: int = 2000

    @property
    def jwks(self) -> dict[str, Any]:
        return {"keys": [dict(item) for item in self.published_keys]}


def _organizations(raw: str) -> dict[str, str]:
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except ValueError as exc:
        raise RuntimeError(f"{config.MAGEX_ORGANIZATIONS_ENV}: не JSON") from exc
    if not isinstance(data, dict):
        raise RuntimeError(f"{config.MAGEX_ORGANIZATIONS_ENV}: нужен объект {{организация BlastEX: UUID MagEX}}")
    result = {}
    for key, value in data.items():
        try:
            result[str(key)] = str(uuid.UUID(str(value)))
        except ValueError as exc:
            raise RuntimeError(f"{config.MAGEX_ORGANIZATIONS_ENV}: у «{key}» не UUID") from exc
    return result


def _extra_keys(raw: str) -> list[dict[str, str]]:
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except ValueError as exc:
        raise RuntimeError(f"{config.JWKS_EXTRA_ENV}: не JSON") from exc
    keys = data.get("keys") if isinstance(data, dict) else None
    if not isinstance(keys, list):
        raise RuntimeError(f"{config.JWKS_EXTRA_ENV}: нужен набор {{\"keys\": [...]}}")
    try:
        return [parse_public_jwk(item) for item in keys]
    except SigningKeyError as exc:
        raise RuntimeError(f"{config.JWKS_EXTRA_ENV}: {exc}") from exc


def load_magex_settings() -> MagexSettings:
    """Настройки из окружения; ошибка настройки — RuntimeError (API не стартует)."""

    pem, kid = config.signing_key_pem(), config.signing_kid()
    key = None
    if pem or kid:
        try:
            key = load_signing_key(pem, kid)
        except SigningKeyError as exc:
            raise RuntimeError(f"{config.SIGNING_KEY_ENV}: {exc}") from exc
    extra = _extra_keys(config.jwks_extra_raw())
    published = ([key.public_jwk] if key else []) + extra
    kids = [item["kid"] for item in published]
    if len(kids) != len(set(kids)):
        raise RuntimeError(f"{config.JWKS_EXTRA_ENV}: kid повторяется")
    allow_test = config.allow_test_key()
    if not allow_test and any(jwk_thumbprint(item) == TEST_KEY_THUMBPRINT for item in published):
        raise RuntimeError(
            "Тестовый ключ MagEX (TEST-ONLY-magex-fixture) — только тесты и локальный стенд: "
            f"задайте свой ключ или {config.ALLOW_TEST_KEY_ENV}=true на стенде."
        )
    return MagexSettings(
        signing_key=key,
        published_keys=tuple(published),
        organizations=_organizations(config.magex_organizations_raw()),
        api_url=config.magex_api_url(),
        max_length=config.magex_jws_max_length(),
    )


@lru_cache(maxsize=1)
def magex_settings() -> MagexSettings:
    return load_magex_settings()


def reset_magex_settings() -> None:
    """Сбросить кэш (тесты меняют окружение)."""

    magex_settings.cache_clear()


def offline_reason(organization_id: str) -> str:
    """Почему наряд «вне учёта MagEX»; пусто — интеграция работает."""

    settings = magex_settings()
    if not settings.api_url:
        return f"Не задан адрес MagEX ({config.MAGEX_API_URL_ENV})."
    if settings.signing_key is None:
        return f"Не задан ключ подписи BlastEX ({config.SIGNING_KEY_ENV})."
    if organization_id not in settings.organizations:
        return f"Организация не сопоставлена с MagEX ({config.MAGEX_ORGANIZATIONS_ENV})."
    return ""


def magex_mode(organization_id: str) -> str | None:
    """`ONLINE` — выписка в MagEX; `OFFLINE` — флаг включён, но не настроено; None — флаг выключен."""

    if not config.magex_integration_enabled():
        return None
    return "OFFLINE" if offline_reason(organization_id) else "ONLINE"
