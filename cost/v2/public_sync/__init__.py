"""Обмен справочников blastex со схемой ``public`` (журнал project1).

Пакет знает только о данных: чтение таблиц журнала (``reader``),
сопоставление их с разделами справочников (``mapping``) и разница с
черновиком (``delta``). Об интерфейсе и HTTP здесь ничего нет; применение
разницы к черновику — за пользователем, уровнем выше.
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
from cost.v2.public_sync.reader import (
    PublicReader,
    PublicUnavailable,
    SqlPublicReader,
    StaticPublicReader,
)

__all__ = [
    "MACHINE_KINDS",
    "DeltaEntry",
    "FieldChange",
    "Proposal",
    "PublicDelta",
    "PublicReader",
    "PublicRow",
    "PublicSnapshot",
    "PublicUnavailable",
    "SqlPublicReader",
    "StaticPublicReader",
    "TABLES",
    "build_proposals",
    "compute_delta",
    "kind_for_machine_type",
    "normalize_legal_name",
    "public_code",
]
