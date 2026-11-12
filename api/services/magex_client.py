"""Клиент MagEX: маршруты `/integrations/blastex/*` контракта (разд. 6) под служебным токеном.

Ответы разбираются по контракту: ошибки — `{"code", "message", "details"}`.
Виды отказа:

- `MagexUnavailable` — сеть, тайм-аут, `5xx`, `503 BLASTEX_KEYS_UNAVAILABLE`:
  повторить позже (повтор той же версии идемпотентен);
- `MagexRejected` — `404`, `409`, `422`: ответ по существу, повтор без правки бесполезен;
- `MagexAuthError` — `401`, `403`: MagEX не принял вход BlastEX (ключ, организация).

Строка JWS и токен в журнал и в текст ошибок не попадают.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Sequence

from design.magex.jws import SigningKey, service_token

__all__ = [
    "MagexAuthError",
    "MagexClient",
    "MagexError",
    "MagexRejected",
    "MagexUnavailable",
    "Transport",
]

TIMEOUT_S = 10
INTEGRATION_PATH = "/integrations/blastex"
# (метод, адрес, заголовки, параметры, тело) → (код, тело ответа JSON или None).
Transport = Callable[[str, str, Mapping[str, str], Sequence[tuple[str, str]], Any], tuple[int, Any]]


@dataclass(eq=False)
class MagexError(Exception):
    status: int
    code: str = ""
    message: str = ""
    details: Any = field(default_factory=dict)

    def __str__(self) -> str:
        return self.message or self.code or f"MagEX ответил {self.status}"


class MagexUnavailable(MagexError):
    """Повторить позже."""


class MagexRejected(MagexError):
    """Отказ по существу (404, 409, 422)."""


class MagexAuthError(MagexError):
    """401 или 403: вход BlastEX не принят."""


def requests_transport(method: str, url: str, headers: Mapping[str, str], params: Sequence[tuple[str, str]], body: Any) -> tuple[int, Any]:
    import requests

    try:
        response = requests.request(
            method, url, headers=dict(headers), params=list(params) or None, json=body, timeout=TIMEOUT_S,
        )
    except requests.RequestException as exc:
        raise MagexUnavailable(0, "NETWORK", f"MagEX недоступен: {type(exc).__name__}") from None
    try:
        data = response.json()
    except ValueError:
        data = None
    return response.status_code, data


class MagexClient:
    def __init__(
        self,
        api_url: str,
        organization: str,
        key: SigningKey,
        transport: Transport | None = None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.base = api_url.rstrip("/") + INTEGRATION_PATH
        self.organization = organization
        self.key = key
        self.transport = transport or requests_transport
        self.clock = clock

    def _call(self, method: str, path: str, *, params: Sequence[tuple[str, str]] = (), body: Any = None) -> Any:
        token = service_token(self.organization, self.key, now=int(self.clock()))
        headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
        try:
            status, data = self.transport(method, self.base + path, headers, params, body)
        except MagexError:
            raise
        except Exception as exc:  # noqa: BLE001 — любой сбой транспорта — «недоступен», повтор позже
            raise MagexUnavailable(0, "NETWORK", f"MagEX недоступен: {type(exc).__name__}") from None
        if 200 <= status < 300:
            return data
        error = data if isinstance(data, dict) else {}
        code = str(error.get("code") or "")
        message = str(error.get("message") or "")
        details = error.get("details") or {}
        if status in (401, 403):
            raise MagexAuthError(status, code, message or "MagEX не принял вход BlastEX: проверьте ключ и организацию.", details)
        if status in (404, 409, 422):
            raise MagexRejected(status, code, message, details)
        raise MagexUnavailable(status, code or "UNAVAILABLE", message or f"MagEX недоступен (ответ {status}).", details)

    def materials(self) -> list[dict[str, Any]]:
        return list((self._call("GET", "/materials") or {}).get("items") or [])

    def availability(self, warehouse_id: str, material_ids: Sequence[str]) -> dict[str, Any]:
        params = [("warehouse_id", warehouse_id), *[("material_id", item) for item in material_ids]]
        return self._call("GET", "/availability", params=params) or {}

    def report_status(self, blaster_ref: str) -> dict[str, Any]:
        return self._call("GET", f"/blasters/{blaster_ref}/report-status") or {}

    def put_naryad(self, naryad_id: str, jws: str) -> dict[str, Any]:
        return self._call("PUT", f"/naryads/{naryad_id}", body={"jws": jws}) or {}

    def cancel_naryad(self, naryad_id: str, ver: int, reason: str) -> dict[str, Any]:
        return self._call("POST", f"/naryads/{naryad_id}/cancel", body={"ver": int(ver), "reason": reason}) or {}

    def get_naryad(self, naryad_id: str) -> dict[str, Any]:
        return self._call("GET", f"/naryads/{naryad_id}") or {}
