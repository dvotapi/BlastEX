"""Перенос данных Cost V1 из `data/teams/` в PostgreSQL.

Переносятся справочники (в поля схем Cost V2), настройки рабочего
пространства и сценарии сметы. По умолчанию — сухой прогон: скрипт печатает
отчёт и ничего не пишет; запись выполняется с `--publish`.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from cost.v2.db_repository import PostgresEconomicsRepository
from cost.v2.import_v1 import build_import_sections
from cost.v2.references import has_validation_errors, validate_reference_sections


def _team_dir(root: Path, team_id: str) -> Path:
    return root / "data" / "teams" / team_id


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _legacy_scenarios(team_dir: Path) -> dict[str, dict[str, Any]]:
    directory = team_dir / "scenarios"
    if not directory.is_dir():
        return {}
    return {path.stem: _read_json(path) for path in sorted(directory.glob("*.json"))}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--team", default="default")
    parser.add_argument("--organization", default="default")
    parser.add_argument("--publish", action="store_true", help="записать данные в базу")
    parser.add_argument("--comment", default="Импорт справочников Cost V1")
    parser.add_argument(
        "--sections",
        default="",
        help="публиковать только перечисленные разделы через запятую, например sites,rocks",
    )
    args = parser.parse_args()

    database_url = os.getenv("BLASTEX_DATABASE_URL", "").strip()
    if not database_url:
        raise SystemExit("Задайте BLASTEX_DATABASE_URL для базы project1.")
    root = Path(__file__).resolve().parent.parent
    team_dir = _team_dir(root, args.team)

    repository = PostgresEconomicsRepository(database_url)
    current = repository.get_reference_snapshot(args.organization)
    sections, report = build_import_sections(root, args.team, current)
    only = {name.strip() for name in args.sections.split(",") if name.strip()}
    if only:
        unknown = only - set(sections)
        if unknown:
            raise SystemExit(f"Неизвестные разделы: {', '.join(sorted(unknown))}")
        sections = {
            key: (values if key in only else tuple(current.sections.get(key, ())))
            for key, values in sections.items()
        }
        output_sections = sorted(only)
    else:
        output_sections = sorted(sections)
    issues = validate_reference_sections(sections)

    settings = _read_json(team_dir / "settings.json")
    scenarios = _legacy_scenarios(team_dir)

    output: dict[str, Any] = {
        "team_dir": str(team_dir),
        "report": report.to_dict(),
        "base_revision": current.revision_id,
        "valid": not has_validation_errors(issues),
        "issues": [issue.to_dict() for issue in issues],
        "workspace_settings": bool(settings),
        "scenarios": sorted(scenarios),
        "published": False,
        "sections_published": output_sections,
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

        if settings:
            repository.import_legacy_workspace(
                args.organization,
                "v1-import-script",
                team_name=str(settings.get("team_name", args.team)),
                active_scenario_id=str(settings.get("active_scenario_id", "")),
                active_work_object_name=str(settings.get("active_work_object_name", "")),
                reference_revision_id=published.revision_id,
            )
        if scenarios:
            output["imported_scenarios"] = repository.import_legacy_scenarios(
                args.organization,
                "v1-import-script",
                scenarios,
                reference_revision_id=published.revision_id,
            )

    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
