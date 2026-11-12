"""Ключ подписи BlastEX для MagEX (TASK-018, PR 7, §2.5): ES256, кривая P-256.

    python scripts/magex_signing_key.py --kid blastex-2026-11 --out /secure/blastex-signing.pem

Пишет закрытый ключ PEM в файл с правами 600 (файл не должен существовать) и
печатает только открытый JWK — его кладут в `BLASTEX_JWKS_EXTRA` при ротации.
Закрытая часть в вывод не попадает. Порядок выкладки и ротации —
`Docs/MAGEX_INTEGRATION.md`.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cryptography.hazmat.primitives import serialization  # noqa: E402
from cryptography.hazmat.primitives.asymmetric import ec  # noqa: E402

from design.magex.jws import load_signing_key  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--kid", required=True, help="идентификатор ключа (BLASTEX_SIGNING_KID), например blastex-2026-11")
    parser.add_argument("--out", required=True, type=Path, help="файл закрытого ключа PEM (создаётся с правами 600)")
    args = parser.parse_args(argv)
    if args.out.exists():
        parser.error(f"{args.out} уже есть: ключ не перезаписывается")
    pem = ec.generate_private_key(ec.SECP256R1()).private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
    )
    descriptor = os.open(args.out, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(pem)
    key = load_signing_key(pem.decode("ascii"), args.kid)
    print(json.dumps({"keys": [key.public_jwk]}, ensure_ascii=False, indent=2))
    print(f"Закрытый ключ: {args.out} (права 600). kid: {args.kid}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
