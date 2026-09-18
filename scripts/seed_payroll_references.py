"""Справочники методики ФОТ по файлу владельца поверх текущей ревизии (TASK-010).

По умолчанию — сухой прогон: печатает отчёт, ошибки и предупреждения проверки
и ничего не пишет; публикация новой ревизии — с `--publish`, только если
ошибок нет. Правила сида — в `cost/v2/payroll_defaults.py`.
Локально: PYTHONPATH=. BLASTEX_DATABASE_URL=... python scripts/seed_payroll_references.py
На проде: docker exec -w /app -e PYTHONPATH=/app blastex-api python scripts/seed_payroll_references.py --publish
"""
from __future__ import annotations

import argparse
import json
import os

from cost.v2.db_repository import PostgresEconomicsRepository
from cost.v2.payroll_defaults import seed_payroll_references
from cost.v2.references import has_validation_errors, validate_reference_sections


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--organization", default="default")
    parser.add_argument("--publish", action="store_true", help="опубликовать новую ревизию")
    parser.add_argument("--comment", default="Справочники методики ФОТ по файлу «Расчёт заработной платы» 2026")
    args = parser.parse_args()

    database_url = os.getenv("BLASTEX_DATABASE_URL", "").strip()
    if not database_url:
        raise SystemExit("Задайте BLASTEX_DATABASE_URL для базы project1.")

    repository = PostgresEconomicsRepository(database_url)
    current = repository.get_reference_snapshot(args.organization)
    sections, report = seed_payroll_references(current)
    issues = validate_reference_sections(sections)
    output = {
        "base_revision": current.revision_id,
        "report": report.to_dict(),
        "valid": not has_validation_errors(issues),
        "issues": [issue.to_dict() for issue in issues if issue.level == "error"],
        "warnings": [issue.to_dict() for issue in issues if issue.level == "warning"],
    }
    if args.publish and output["valid"]:
        published = repository.publish_references(
            args.organization,
            "seed_payroll_references",
            current.revision_id,
            {name: [item.to_dict() for item in items] for name, items in sections.items()},
            args.comment,
        )
        output["published_revision"] = published.revision_id
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
