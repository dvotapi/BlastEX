"""Проверить и при явном флаге опубликовать справочники Cost V1 в project1."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from cost.v2.db_repository import PostgresEconomicsRepository
from cost.v2.import_v1 import build_import_sections
from cost.v2.references import has_validation_errors, validate_reference_sections


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--team", default="default")
    parser.add_argument("--organization", default="default")
    parser.add_argument("--publish", action="store_true")
    parser.add_argument("--comment", default="Импорт справочников Cost V1")
    args = parser.parse_args()

    database_url = os.getenv("BLASTEX_DATABASE_URL", "").strip()
    if not database_url:
        raise SystemExit("Задайте BLASTEX_DATABASE_URL для базы project1.")
    repository = PostgresEconomicsRepository(database_url)
    current = repository.get_reference_snapshot(args.organization)
    sections, report = build_import_sections(
        Path(__file__).resolve().parent.parent,
        args.team,
        current,
    )
    issues = validate_reference_sections(sections)
    output = {
        "report": report.to_dict(),
        "base_revision": current.revision_id,
        "valid": not has_validation_errors(issues),
        "issues": [issue.to_dict() for issue in issues],
        "published": False,
    }
    if args.publish:
        if has_validation_errors(issues):
            print(json.dumps(output, ensure_ascii=False, indent=2))
            raise SystemExit("Публикация отменена из-за ошибок валидации.")
        published = repository.publish_references(
            organization_id=args.organization,
            user_id="v1-import-script",
            base_revision=current.revision_id,
            sections=sections,
            comment=args.comment,
        )
        output["published"] = True
        output["revision_id"] = published.revision_id
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
