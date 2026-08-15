#!/usr/bin/env python3
"""Интерактивная генерация хеша пароля для конфигурации BlastEX."""
from __future__ import annotations

import getpass
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cost.auth import hash_password


def main() -> None:
    password = getpass.getpass("Пароль: ")
    confirmation = getpass.getpass("Повторите пароль: ")
    if password != confirmation:
        raise SystemExit("Пароли не совпадают.")
    print(hash_password(password))


if __name__ == "__main__":
    main()
