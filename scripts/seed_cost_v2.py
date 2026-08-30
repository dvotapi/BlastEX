"""Создать начальную ревизию Cost V2 для организации, если её ещё нет."""
from __future__ import annotations

import argparse
import json
import os

from cost.v2.db_repository import PostgresEconomicsRepository


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--organization", default="default")
    args = parser.parse_args()
    database_url = os.getenv("BLASTEX_DATABASE_URL", "").strip()
    if not database_url:
        raise SystemExit("Задайте BLASTEX_DATABASE_URL для базы project1.")
    snapshot = PostgresEconomicsRepository(database_url).get_reference_snapshot(
        args.organization
    )
    print(
        json.dumps(
            {
                "organization": args.organization,
                "revision_id": snapshot.revision_id,
                "published_at": snapshot.published_at.isoformat()
                if snapshot.published_at
                else None,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
