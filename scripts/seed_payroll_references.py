"""Справочники методики ФОТ по файлу владельца поверх текущей ревизии (TASK-010).

По умолчанию — сухой прогон: печатает отчёт сида, ошибки и предупреждения
проверки и ревизию не публикует. Организация обязательна: для неизвестной
организации уже чтение снимка заводит ревизию справочников по умолчанию, и
опечатка в коде создала бы в базе новую организацию.

`--publish` публикует новую ревизию, только если проверка прошла без ошибок и
в справочнике нашлась хотя бы одна из должностей, сопоставленных владельцем
(иначе это, вероятно, не та организация); в обоих отказах код выхода 1. Если
добавлять и заполнять нечего, ревизия не публикуется, код выхода 0. Правила
сида — в `cost/v2/payroll_defaults.py`.

Локально: PYTHONPATH=. BLASTEX_DATABASE_URL=... python scripts/seed_payroll_references.py --organization <организация>
На проде: docker exec -w /app -e PYTHONPATH=/app blastex-api python scripts/seed_payroll_references.py --organization <организация> --publish
"""
from __future__ import annotations

import argparse
import json
import os
from typing import Any

from cost.v2.db_repository import PostgresEconomicsRepository
from cost.v2.payroll_defaults import MAPPED_POSITIONS, seed_payroll_references
from cost.v2.references import has_validation_errors, validate_reference_sections
from cost.v2.repository import EconomicsRepository


def run(
    repository: EconomicsRepository, organization: str, *, publish: bool, comment: str
) -> tuple[dict[str, Any], int]:
    """Отчёт сида и код выхода; с `publish` — публикация, если есть что и куда."""

    current = repository.get_reference_snapshot(organization)
    sections, report = seed_payroll_references(current)
    issues = validate_reference_sections(sections)
    output: dict[str, Any] = {
        "organization": organization,
        "base_revision": current.revision_id,
        "matched_positions": {
            "found": len(report.matched_positions),
            "of": len(MAPPED_POSITIONS),
            "codes": list(report.matched_positions),
        },
        "report": report.to_dict(),
        "valid": not has_validation_errors(issues),
        "issues": [issue.to_dict() for issue in issues if issue.level == "error"],
        "warnings": [issue.to_dict() for issue in issues if issue.level == "warning"],
    }
    if not publish:
        return output, 0
    if not output["valid"]:
        output["message"] = "Проверка нашла ошибки: ревизия не опубликована."
        return output, 1
    if not report.matched_positions:
        output["message"] = (
            "Ни одной из должностей, сопоставленных владельцем, нет в справочнике организации: "
            "вероятно, не та организация. Ревизия не опубликована."
        )
        return output, 1
    if not report.added and not report.filled:
        output["message"] = "Изменений нет: ревизия не опубликована."
        return output, 0
    published = repository.publish_references(
        organization,
        "seed_payroll_references",
        current.revision_id,
        {name: [item.to_dict() for item in items] for name, items in sections.items()},
        comment,
    )
    output["published_revision"] = published.revision_id
    return output, 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Справочники методики ФОТ по файлу владельца")
    parser.add_argument("--organization", required=True, help="организация, в справочники которой дописывается сид")
    parser.add_argument("--publish", action="store_true", help="опубликовать новую ревизию")
    parser.add_argument("--comment", default="Справочники методики ФОТ по файлу «Расчёт заработной платы» 2026")
    args = parser.parse_args()

    database_url = os.getenv("BLASTEX_DATABASE_URL", "").strip()
    if not database_url:
        raise SystemExit("Задайте BLASTEX_DATABASE_URL для базы project1.")

    output, code = run(
        PostgresEconomicsRepository(database_url), args.organization, publish=args.publish, comment=args.comment
    )
    print(json.dumps(output, ensure_ascii=False, indent=2))
    raise SystemExit(code)


if __name__ == "__main__":
    main()
