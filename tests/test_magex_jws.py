"""Подпись наряд-путёвки и служебный токен по контракту MagEX (TASK-018 PR 7, §2, §10)."""
from __future__ import annotations

import json
import zlib

import pytest

from design.magex import jws
from tests.magex_contract import FIXTURES, ContractError, b64url_decode, inflate, fixture_keys, verify, verify_service_token

VECTORS = json.loads((FIXTURES / "vectors" / "index.json").read_text())


def _test_key() -> jws.SigningKey:
    return jws.load_signing_key((FIXTURES / "keys" / "TEST-ONLY-private.pem").read_text(), "TEST-ONLY-magex-fixture")


def test_contract_has_19_vectors():
    assert len(VECTORS["vectors"]) == 19


@pytest.mark.parametrize("vector", VECTORS["vectors"], ids=lambda vector: vector["id"])
def test_vectors_give_expected_result(vector):
    """Проверка тестов совпадает с серверной проверкой MagEX на всех 19 векторах."""

    token = (FIXTURES / "vectors" / vector["file"]).read_text()
    if vector["expected"] == "ok":
        payload = verify(token, max_length=VECTORS["max_length"])
        if vector.get("payload"):
            assert payload == json.loads((FIXTURES / "vectors" / vector["payload"]).read_text())
        return
    with pytest.raises(ContractError) as caught:
        verify(token, max_length=VECTORS["max_length"])
    assert caught.value.code == vector["expected"]


def test_sample_jws_inflates_to_sample_json():
    token = (FIXTURES / "naryads" / "sample.jws").read_text()
    content = inflate(b64url_decode(token.split(".")[1]))
    assert json.loads(content) == json.loads((FIXTURES / "naryads" / "sample.json").read_text())


@pytest.mark.parametrize("name", ["sample", "minimal", "typical-v1", "typical-v2", "large"])
def test_our_signature_passes_server_check(name):
    payload = json.loads((FIXTURES / "naryads" / f"{name}.json").read_text())
    token = jws.sign_naryad(payload, _test_key())
    assert verify(token) == payload
    # Та же длина, что у фикстуры MagEX: запись содержимого та же (подпись — 64 байта при любом подписании).
    assert len(token) == len((FIXTURES / "naryads" / f"{name}.jws").read_text())


def test_content_is_utf8_without_escapes_and_raw_deflate():
    payload = json.loads((FIXTURES / "naryads" / "sample.json").read_text())
    token = jws.sign_naryad(payload, _test_key())
    raw = zlib.decompress(b64url_decode(token.split(".")[1]), -15)
    assert "Трегубов".encode() in raw and b"\\u04" not in raw
    header = json.loads(b64url_decode(token.split(".")[0]))
    assert header == {"alg": "ES256", "kid": "TEST-ONLY-magex-fixture", "typ": "naryad-v1"}
    assert len(b64url_decode(token.split(".")[2])) == 64


def test_resigned_version_keeps_content_hash():
    payload = json.loads((FIXTURES / "naryads" / "sample.json").read_text())
    first, second = jws.sign_naryad(payload, _test_key()), jws.sign_naryad({**payload, "iat": payload["iat"] + 60}, _test_key())
    assert first != second
    assert jws.content_sha256(payload) == jws.content_sha256({**payload, "iat": payload["iat"] + 60})


def test_test_key_is_recognized_by_thumbprint_not_kid():
    key = jws.load_signing_key((FIXTURES / "keys" / "TEST-ONLY-private.pem").read_text(), "renamed")
    assert key.is_test_key
    assert key.thumbprint == jws.TEST_KEY_THUMBPRINT
    assert jws.jwk_thumbprint(json.loads((FIXTURES / "keys" / "jwks.json").read_text())["keys"][0]) == jws.TEST_KEY_THUMBPRINT


def test_service_token_by_contract():
    key = _test_key()
    token = jws.service_token("00000000-0000-4000-8000-00000000d0e1", key, now=1_800_000_000)
    claims = verify_service_token(token, fixture_keys(), now=1_800_000_000)
    assert claims == {
        "iss": "blastex", "aud": "magex", "org": "00000000-0000-4000-8000-00000000d0e1",
        "iat": 1_800_000_000, "exp": 1_800_000_120,
    }
    header = json.loads(b64url_decode(token.split(".")[0]))
    assert header["typ"] == "blastex-service"
    # Строку наряд-путёвки за токен не выдать.
    with pytest.raises(ContractError):
        verify(token)
    with pytest.raises(ValueError):
        jws.service_token("org", key, now=0, ttl_s=301)


def test_public_jwk_has_no_private_part():
    jwk = _test_key().public_jwk
    assert "d" not in jwk
    assert jwk == {**json.loads((FIXTURES / "keys" / "jwks.json").read_text())["keys"][0]}
    with pytest.raises(jws.SigningKeyError):
        jws.parse_public_jwk({**jwk, "d": "x"})
    assert jws.parse_public_jwk(jwk) == jwk


def test_rejects_non_p256_key():
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ec

    pem = ec.generate_private_key(ec.SECP384R1()).private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
    ).decode()
    with pytest.raises(jws.SigningKeyError):
        jws.load_signing_key(pem, "k")
    with pytest.raises(jws.SigningKeyError):
        jws.load_signing_key("not a key", "k")
