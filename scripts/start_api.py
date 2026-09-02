"""Production entrypoint: применить миграции и запустить API.

Хранилище одно — PostgreSQL, поэтому миграции применяются всегда: запуск без
`BLASTEX_DATABASE_URL` невозможен по определению.
"""
from __future__ import annotations

import os
import subprocess


def main() -> None:
    if not os.getenv("BLASTEX_DATABASE_URL", "").strip():
        raise SystemExit(
            "BLASTEX_DATABASE_URL не задан: BlastEX хранит данные только в "
            "PostgreSQL. Укажите строку подключения к базе project1."
        )
    subprocess.run(["alembic", "upgrade", "head"], check=True)
    os.execvp(
        "uvicorn",
        ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"],
    )


if __name__ == "__main__":
    main()
