"""Строка наряд-путёвки и служебный токен BlastEX по контракту MagEX (разд. 1, 4, 5).

- Строка — JWS в компактной форме: заголовок `{"alg":"ES256","kid":…,"typ":"naryad-v1"}`,
  содержимое — JSON в UTF-8 без `\\uXXXX` (ключи по алфавиту, без пробелов), сжатый
  raw DEFLATE (RFC 1951, без заголовка zlib) **до** подписи, подпись ECDSA P-256
  SHA-256 в виде R‖S (64 байта, не DER), base64url без `=`.
- Служебный токен — JWT тем же ключом, `typ` = `blastex-service` в заголовке,
  `iss` = `blastex`, `aud` = `magex` (строкой), `org`, `iat`, `exp` (≤ 300 с).
- Тестовый ключ MagEX узнаётся по отпечатку RFC 7638, а не по `kid`.

Подпись ECDSA при каждом подписании другая, поэтому версии сравниваются по
хэшу содержимого без `iat` (`content_sha256`), а не по строке.
"""
from __future__ import annotations

import base64
import hashlib
import json
import zlib
from dataclasses import dataclass
from typing import Any, Mapping

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature

__all__ = [
    "ALG",
    "JWS_TYP",
    "MAX_JWS_LENGTH",
    "SERVICE_TOKEN_TTL_S",
    "SERVICE_TYP",
    "TEST_KEY_THUMBPRINT",
    "SigningKeyError",
    "SigningKey",
    "b64url",
    "content_sha256",
    "encode_content",
    "jwk_thumbprint",
    "load_signing_key",
    "parse_public_jwk",
    "service_token",
    "sign_naryad",
]

ALG = "ES256"
JWS_TYP = "naryad-v1"
SERVICE_TYP = "blastex-service"
SERVICE_TOKEN_TTL_S = 120
# Предел длины строки на стороне MagEX по умолчанию (`VM_NARYAD_JWS_MAX_LENGTH`).
MAX_JWS_LENGTH = 2000
# Отпечаток RFC 7638 тестового ключа MagEX (`kid` = TEST-ONLY-magex-fixture,
# `MagEX/backend/core/config.py::BLASTEX_TEST_KEY_THUMBPRINT`).
TEST_KEY_THUMBPRINT = "l5OFc6eDQCwJT1wnoNZFBEG6Nhg08ae4QnC2DWPiMKE"
_COORDINATE_BYTES = 32


class SigningKeyError(ValueError):
    """Ключ не годится для ES256 (не EC P-256, нет закрытой части, лишняя `d` и т. п.)."""


def b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_bytes(text: str) -> bytes:
    if not isinstance(text, str) or not text or "=" in text:
        raise SigningKeyError("Координата ключа — не base64url")
    try:
        return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))
    except (ValueError, TypeError) as exc:
        raise SigningKeyError("Координата ключа — не base64url") from exc


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def encode_content(payload: Mapping[str, Any]) -> bytes:
    """Содержимое строки: канонический JSON в UTF-8, сжатый raw DEFLATE уровня 9."""

    packer = zlib.compressobj(9, zlib.DEFLATED, -15)
    return packer.compress(_canonical(payload)) + packer.flush()


def content_sha256(payload: Mapping[str, Any]) -> str:
    """Хэш содержимого без `iat`: одна и та же версия, подписанная заново, — тот же хэш."""

    return hashlib.sha256(_canonical({key: value for key, value in payload.items() if key != "iat"})).hexdigest()


def jwk_thumbprint(jwk: Mapping[str, Any]) -> str | None:
    """Отпечаток RFC 7638 ключа EC (`crv`, `kty`, `x`, `y` в канонической записи); не EC — None."""

    if jwk.get("kty") != "EC" or not isinstance(jwk.get("crv"), str):
        return None
    try:
        x, y = (b64url(_b64url_bytes(str(jwk.get(name) or ""))) for name in ("x", "y"))
    except SigningKeyError:
        return None
    canonical = json.dumps({"crv": jwk["crv"], "kty": "EC", "x": x, "y": y}, separators=(",", ":"))
    return b64url(hashlib.sha256(canonical.encode()).digest())


def _public_jwk(public_key: ec.EllipticCurvePublicKey, kid: str) -> dict[str, str]:
    numbers = public_key.public_numbers()
    return {
        "kty": "EC",
        "crv": "P-256",
        "x": b64url(numbers.x.to_bytes(_COORDINATE_BYTES, "big")),
        "y": b64url(numbers.y.to_bytes(_COORDINATE_BYTES, "big")),
        "kid": kid,
        "use": "sig",
        "alg": ALG,
    }


@dataclass(frozen=True)
class SigningKey:
    """Закрытый ключ ES256 BlastEX и его `kid`."""

    kid: str
    private_key: ec.EllipticCurvePrivateKey

    @property
    def public_jwk(self) -> dict[str, str]:
        return _public_jwk(self.private_key.public_key(), self.kid)

    @property
    def thumbprint(self) -> str:
        return str(jwk_thumbprint(self.public_jwk))

    @property
    def is_test_key(self) -> bool:
        return self.thumbprint == TEST_KEY_THUMBPRINT

    def sign(self, signing_input: bytes) -> bytes:
        """Подпись ES256 в виде R‖S (по 32 байта, big-endian), а не DER."""

        der = self.private_key.sign(signing_input, ec.ECDSA(hashes.SHA256()))
        r, s = decode_dss_signature(der)
        return r.to_bytes(_COORDINATE_BYTES, "big") + s.to_bytes(_COORDINATE_BYTES, "big")


def load_signing_key(pem: str, kid: str) -> SigningKey:
    """Закрытый ключ из PEM; только EC P-256 и непустой `kid`."""

    kid = str(kid or "").strip()
    if not kid:
        raise SigningKeyError("Не задан kid ключа подписи (BLASTEX_SIGNING_KID)")
    try:
        key = serialization.load_pem_private_key(str(pem).encode("utf-8"), password=None)
    except (ValueError, TypeError) as exc:
        raise SigningKeyError("Ключ подписи не читается: нужен закрытый ключ EC P-256 в PEM без пароля") from exc
    if not isinstance(key, ec.EllipticCurvePrivateKey) or not isinstance(key.curve, ec.SECP256R1):
        raise SigningKeyError("Ключ подписи — не EC P-256 (ES256)")
    return SigningKey(kid=kid, private_key=key)


def parse_public_jwk(jwk: Mapping[str, Any]) -> dict[str, str]:
    """Открытый ключ для публикации: EC P-256, есть `kid`, нет закрытой части `d`."""

    if not isinstance(jwk, Mapping):
        raise SigningKeyError("Ключ набора — не объект")
    if "d" in jwk:
        raise SigningKeyError(f"В открытом ключе {jwk.get('kid', '')!s} есть закрытая часть (d)")
    kid = str(jwk.get("kid") or "").strip()
    if not kid:
        raise SigningKeyError("У ключа набора нет kid")
    if jwk.get("kty") != "EC" or jwk.get("crv") != "P-256":
        raise SigningKeyError(f"Ключ {kid} — не EC P-256")
    x, y = (_b64url_bytes(str(jwk.get(name) or "")) for name in ("x", "y"))
    try:
        public = ec.EllipticCurvePublicNumbers(
            int.from_bytes(x, "big"), int.from_bytes(y, "big"), ec.SECP256R1()
        ).public_key()
    except ValueError as exc:
        raise SigningKeyError(f"Ключ {kid}: точка не на кривой P-256") from exc
    return _public_jwk(public, kid)


def _compact(header: Mapping[str, Any], content: bytes, key: SigningKey) -> str:
    head = b64url(json.dumps(dict(header), separators=(",", ":")).encode("ascii"))
    body = b64url(content)
    signing_input = f"{head}.{body}".encode("ascii")
    return f"{head}.{body}.{b64url(key.sign(signing_input))}"


def sign_naryad(payload: Mapping[str, Any], key: SigningKey) -> str:
    """Строка наряд-путёвки (`typ` = naryad-v1): содержимое сжато до подписи."""

    return _compact({"alg": ALG, "kid": key.kid, "typ": JWS_TYP}, encode_content(payload), key)


def service_token(organization: str, key: SigningKey, now: int, ttl_s: int = SERVICE_TOKEN_TTL_S) -> str:
    """Служебный токен BlastEX для MagEX: `typ` в заголовке, `aud` строкой, срок ≤ 300 с."""

    if not 0 < ttl_s <= 300:
        raise ValueError("Срок служебного токена — от 1 до 300 с")
    claims = {"iss": "blastex", "aud": "magex", "org": str(organization), "iat": int(now), "exp": int(now) + ttl_s}
    content = json.dumps(claims, separators=(",", ":"), sort_keys=True).encode("ascii")
    return _compact({"alg": ALG, "kid": key.kid, "typ": SERVICE_TYP}, content, key)
