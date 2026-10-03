"""У отслеживаемых миграций Alembic нет повторяющихся `revision`.

Две ветки могут независимо взять один номер (так случилось у TASK-013 PR 4 и
Kuz-Ram #106: обе `20261002_0011` от `20261001_0010`). Слияние такие файлы не
конфликтует, а Alembic только предупреждает и молча оставляет одну ревизию —
на проде вторая миграция не применится никогда.
"""
from __future__ import annotations

import re
import subprocess
from collections import Counter
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
_REVISION = re.compile(r'^revision\s*=\s*"([^"]+)"', re.MULTILINE)


def _tracked_migrations() -> list[Path]:
    try:
        result = subprocess.run(
            ["git", "ls-files", "migrations/versions"], cwd=REPO, capture_output=True, text=True, check=True
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        pytest.skip("нет git — список отслеживаемых миграций не получить")
    return [REPO / line for line in result.stdout.splitlines() if line.endswith(".py")]


def test_tracked_migrations_have_unique_revisions():
    revisions = Counter()
    for path in _tracked_migrations():
        match = _REVISION.search(path.read_text(encoding="utf-8"))
        if match:
            revisions[match.group(1)] += 1

    assert {revision: count for revision, count in revisions.items() if count > 1} == {}
