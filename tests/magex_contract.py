"""Проверка строки наряд-путёвки так, как её проверяет MagEX (контракт, разд. 1 и 2).

Только для тестов: порт `MagEX/backend/core/security/naryad_jws.py::verify_naryad_jws`
на `cryptography` и `jsonschema` (PyJWT в BlastEX нет). Порядок шагов строгий:
длина → заголовок → ключ → подпись → распаковка ≤ 64 КиБ → JSON без повторов
ключей → схема `naryad.v1.schema.json` → правила, которых в схеме нет. 19
векторов контракта (`tests/fixtures/magex/vectors/`) дают ожидаемые коды —
значит, проверка верна, и ей можно проверять строки BlastEX.
"""
from __future__ import annotations

import base64
import json
import re
import zlib
from datetime import date, datetime
from pathlib import Path
from typing import Any, Mapping

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import encode_dss_signature

FIXTURES = Path(__file__).parent / "fixtures" / "magex"
MAX_DECOMPRESSED = 65_536
_B64URL = re.compile(r"[A-Za-z0-9_-]*")


class ContractError(Exception):
    def __init__(self, code: str, message: str = "", errors: list[dict[str, str]] | None = None) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.errors = errors or []


def _no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Ключ {key} повторяется")
        result[key] = value
    return result


def _no_constants(name: str) -> Any:
    raise ValueError(f"{name} — не JSON")


def strict_json(data: bytes) -> Any:
    return json.loads(data.decode("utf-8"), object_pairs_hook=_no_duplicates, parse_constant=_no_constants)


def b64url_decode(segment: str) -> bytes:
    if not _B64URL.fullmatch(segment) or len(segment) % 4 == 1:
        raise ContractError("NARYAD_SIGNATURE_INVALID", "не base64url")
    data = base64.urlsafe_b64decode(segment + "=" * (-len(segment) % 4))
    if base64.urlsafe_b64encode(data).rstrip(b"=").decode() != segment:
        raise ContractError("NARYAD_SIGNATURE_INVALID", "неканонический base64url")
    return data


def public_keys(jwks: Mapping[str, Any]) -> dict[str, ec.EllipticCurvePublicKey]:
    keys = {}
    for jwk in jwks["keys"]:
        x, y = (int.from_bytes(b64url_decode(jwk[name]), "big") for name in ("x", "y"))
        keys[jwk["kid"]] = ec.EllipticCurvePublicNumbers(x, y, ec.SECP256R1()).public_key()
    return keys


def fixture_keys() -> dict[str, ec.EllipticCurvePublicKey]:
    return public_keys(json.loads((FIXTURES / "keys" / "jwks.json").read_text()))


def check_header(token: str, typ: str) -> tuple[str, list[str]]:
    segments = token.split(".")
    if len(segments) != 3:
        raise ContractError("NARYAD_SIGNATURE_INVALID", "не три части")
    try:
        header = strict_json(b64url_decode(segments[0]))
    except (ValueError, RecursionError) as exc:
        raise ContractError("NARYAD_SIGNATURE_INVALID", "заголовок не разбирается") from exc
    if not isinstance(header, dict) or header.get("alg") != "ES256" or header.get("typ") != typ:
        raise ContractError("NARYAD_SIGNATURE_INVALID", f"заголовок {header!r}")
    kid = header.get("kid")
    if not isinstance(kid, str) or not kid or "crit" in header:
        raise ContractError("NARYAD_SIGNATURE_INVALID", "kid или crit")
    return kid, segments


def verified_content(token: str, typ: str, keys: Mapping[str, ec.EllipticCurvePublicKey]) -> bytes:
    kid, segments = check_header(token, typ)
    if kid not in keys:
        raise ContractError("NARYAD_SIGNATURE_INVALID", "неизвестный kid")
    signature = b64url_decode(segments[2])
    if len(signature) != 64:
        raise ContractError("NARYAD_SIGNATURE_INVALID", "подпись не R‖S")
    der = encode_dss_signature(int.from_bytes(signature[:32], "big"), int.from_bytes(signature[32:], "big"))
    try:
        keys[kid].verify(der, f"{segments[0]}.{segments[1]}".encode("ascii"), ec.ECDSA(hashes.SHA256()))
    except InvalidSignature as exc:
        raise ContractError("NARYAD_SIGNATURE_INVALID", "подпись неверна") from exc
    return b64url_decode(segments[1])


def inflate(content: bytes) -> bytes:
    inflater = zlib.decompressobj(-15)
    try:
        data = inflater.decompress(content, MAX_DECOMPRESSED + 1)
    except zlib.error as exc:
        raise ContractError("NARYAD_SCHEMA_INVALID", "не raw DEFLATE") from exc
    if len(data) > MAX_DECOMPRESSED:
        raise ContractError("NARYAD_PAYLOAD_TOO_LARGE", "больше 64 КиБ")
    if not inflater.eof or inflater.unused_data:
        raise ContractError("NARYAD_SCHEMA_INVALID", "обрыв или хвост потока")
    return data


def _schema_validator():
    import jsonschema

    schema = json.loads((FIXTURES / "naryad.v1.schema.json").read_text())
    return jsonschema.Draft202012Validator(schema, format_checker=jsonschema.Draft202012Validator.FORMAT_CHECKER)


_TEXT_KEYS = ("name", "position", "number", "num", "project", "code", "horizon", "index", "plate", "model")


def _server_rules(payload: Mapping[str, Any]) -> list[dict[str, str]]:
    """Правила разд. 2, которых нет в схеме."""

    errors = []
    for index, line in enumerate(payload.get("lines") or []):
        if float(line["qty"]) <= 0:
            errors.append({"field": f"lines.{index}.qty", "message": "не больше нуля"})
    ids = [line["material_id"].lower() for line in payload.get("lines") or []]
    if len(ids) != len(set(ids)):
        errors.append({"field": "lines", "message": "позиции повторяются"})
    codes = [block["code"].strip() for block in payload.get("blocks") or []]
    if len(codes) != len(set(codes)):
        errors.append({"field": "blocks", "message": "коды блоков повторяются"})
    if payload.get("blast_on") and date.fromisoformat(payload["blast_on"]) < date.fromisoformat(payload["on"]):
        errors.append({"field": "blast_on", "message": "раньше on"})
    approved_at = datetime.fromisoformat(str((payload.get("approved") or {}).get("at", "")).replace("Z", "+00:00"))
    if approved_at.tzinfo is None:
        errors.append({"field": "approved.at", "message": "без пояса"})

    def texts(value: Any, path: str) -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                if isinstance(item, str) and key in _TEXT_KEYS and (not item.strip() or "\x00" in item or item != item.strip()):
                    errors.append({"field": f"{path}{key}", "message": "пустой текст, NUL или пробелы по краям"})
                texts(item, f"{path}{key}.")
        elif isinstance(value, list):
            for index, item in enumerate(value):
                texts(item, f"{path}{index}.")

    texts(payload, "")
    return errors


def verify(token: str, keys: Mapping[str, ec.EllipticCurvePublicKey] | None = None, max_length: int = 2000) -> dict[str, Any]:
    """Строка → содержимое; отказ — ContractError с кодом MagEX."""

    keys = fixture_keys() if keys is None else keys
    if len(token) > max_length:
        raise ContractError("NARYAD_PAYLOAD_TOO_LARGE", f"длиннее {max_length}")
    data = inflate(verified_content(token, "naryad-v1", keys))
    try:
        payload = strict_json(data)
    except (ValueError, RecursionError) as exc:
        raise ContractError("NARYAD_SCHEMA_INVALID", str(exc)) from exc
    schema_errors = [
        {"field": ".".join(str(part) for part in error.absolute_path), "message": error.message}
        for error in _schema_validator().iter_errors(payload)
    ]
    if schema_errors:
        raise ContractError("NARYAD_SCHEMA_INVALID", "схема", schema_errors)
    rules = _server_rules(payload)
    if rules:
        raise ContractError("NARYAD_SCHEMA_INVALID", "правила разд. 2", rules)
    return payload


def verify_service_token(token: str, keys: Mapping[str, ec.EllipticCurvePublicKey], now: int) -> dict[str, Any]:
    """Служебный токен (разд. 4): `typ`, `iss`, `aud` строкой, `org`, срок ≤ 300 с, допуск часов 30 с."""

    claims = strict_json(verified_content(token, "blastex-service", keys))
    if claims.get("iss") != "blastex" or claims.get("aud") != "magex" or not isinstance(claims.get("org"), str):
        raise ContractError("TOKEN_INVALID", "поля")
    iat, exp = claims.get("iat"), claims.get("exp")
    if not isinstance(iat, int) or not isinstance(exp, int) or exp <= iat or exp - iat > 300:
        raise ContractError("TOKEN_INVALID", "срок")
    if exp <= now - 30 or iat > now + 30:
        raise ContractError("TOKEN_EXPIRED", "часы")
    return claims
