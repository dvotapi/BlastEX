"""Production entrypoint: применить расширяющие миграции и запустить API."""
from __future__ import annotations

import os
import subprocess


def main() -> None:
    if os.getenv("BLASTEX_DATABASE_URL", "").strip():
        subprocess.run(["alembic", "upgrade", "head"], check=True)
    os.execvp(
        "uvicorn",
        ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"],
    )


if __name__ == "__main__":
    main()
