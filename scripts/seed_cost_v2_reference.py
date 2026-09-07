"""Эталонная ревизия справочников для модели блока: достроить недостающее.

Роли номенклатуры, условия бурения и нормы станков, основные средства машин,
правила затрат логистики, СИЗ, суточные — по тому, что уже есть в базе.
Числа демонстрационные (источник `seed`), сметчик правит их в справочнике.

По умолчанию — сухой прогон с отчётом; публикация ревизии — с `--publish`.
Локально: PYTHONPATH=. BLASTEX_DATABASE_URL=... python scripts/seed_cost_v2_reference.py
На проде: docker exec -w /app -e PYTHONPATH=/app blastex-api python scripts/seed_cost_v2_reference.py --publish
"""
from __future__ import annotations

import argparse
import json
import os

from cost.v2.db_repository import PostgresEconomicsRepository
from cost.v2.references import has_validation_errors, validate_reference_sections
from cost.v2.seed_defaults import seed_reference


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--organization", default="default")
    parser.add_argument("--publish", action="store_true", help="опубликовать новую ревизию")
    parser.add_argument("--comment", default="Эталонная ревизия для модели блока (seed)")
    args = parser.parse_args()

    database_url = os.getenv("BLASTEX_DATABASE_URL", "").strip()
    if not database_url:
        raise SystemExit("Задайте BLASTEX_DATABASE_URL для базы project1.")

    repository = PostgresEconomicsRepository(database_url)
    current = repository.get_reference_snapshot(args.organization)
    sections, report = seed_reference(current)
    issues = validate_reference_sections(sections)
    output = {
        "base_revision": current.revision_id,
        "report": report.to_dict(),
        "valid": not has_validation_errors(issues),
        "issues": [issue.to_dict() for issue in issues if issue.level == "error"],
    }
    if args.publish and output["valid"]:
        published = repository.publish_references(
            args.organization,
            "seed_cost_v2_reference",
            current.revision_id,
            {name: [item.to_dict() for item in items] for name, items in sections.items()},
            args.comment,
        )
        output["published_revision"] = published.revision_id
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
