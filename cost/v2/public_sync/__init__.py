"""Обмен справочников blastex со схемой ``public`` (журнал project1).

Пакет знает только о данных: чтение таблиц журнала (``reader``),
сопоставление их с разделами справочников (``mapping``), разница с
черновиком (``delta``), обратный план записи в журнал (``push``) и
зеркала разделов, у которых аналога в журнале нет (``mirror``). Об
интерфейсе и HTTP здесь ничего нет; применение разницы к черновику — за
пользователем, уровнем выше.
"""
from __future__ import annotations

from cost.v2.public_sync.delta import (
    DeltaEntry,
    FieldChange,
    PublicDelta,
    compute_delta,
)
from cost.v2.public_sync.mapping import (
    MACHINE_KINDS,
    TABLES,
    Proposal,
    PublicRow,
    PublicSnapshot,
    build_proposals,
    kind_for_machine_type,
    normalize_legal_name,
    public_code,
)
from cost.v2.public_sync.mirror import (
    MirrorColumn,
    create_table_sql,
    ensure_mirror,
    mirror_columns,
    mirror_table_name,
    mirror_value,
    sync_mirror,
)
from cost.v2.public_sync.push import (
    PublicInsert,
    PublicUpdate,
    PublicWritePlan,
    plan_public_writes,
    public_constraint_issues,
)
from cost.v2.public_sync.reader import (
    PublicReader,
    PublicUnavailable,
    SqlPublicReader,
    StaticPublicReader,
)
from cost.v2.public_sync.writer import PublicWriteError, SqlPublicWriter

__all__ = [
    "MACHINE_KINDS",
    "DeltaEntry",
    "FieldChange",
    "MirrorColumn",
    "Proposal",
    "PublicDelta",
    "PublicInsert",
    "PublicReader",
    "PublicRow",
    "PublicSnapshot",
    "PublicUnavailable",
    "PublicUpdate",
    "PublicWriteError",
    "PublicWritePlan",
    "SqlPublicReader",
    "SqlPublicWriter",
    "StaticPublicReader",
    "TABLES",
    "build_proposals",
    "compute_delta",
    "create_table_sql",
    "ensure_mirror",
    "kind_for_machine_type",
    "mirror_columns",
    "mirror_table_name",
    "mirror_value",
    "normalize_legal_name",
    "plan_public_writes",
    "public_code",
    "public_constraint_issues",
    "sync_mirror",
]
