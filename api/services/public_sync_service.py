"""Сервис разницы журнала ``public`` с черновиком справочников и связей.

Разница считается на лету, ничего не сохраняя: страница «Справочники»
показывает предложения, а применяет их пользователь. Единственная запись в
базу здесь — сохранённая связь ``public_links`` (см. маршруты в
``api/routers/economics.py``).
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Sequence

from fastapi import Depends
from pydantic import ValidationError

from api.schemas.economics import PublicSyncSettingsRequest, ReferenceItemSchema
from api.services.economics_service import get_economics_repository
from cost.v2.models import ReferenceItem
from cost.v2.public_sync import (
    DeltaEntry,
    FieldChange,
    PublicReader,
    PublicSnapshot,
    PublicUnavailable,
    SqlPublicReader,
    StaticPublicReader,
    compute_delta,
    public_constraint_issues,
)
from cost.v2.public_sync.mapping import TABLES
from cost.v2.public_sync.settings import MAPPED_SECTIONS, PublicSyncSettings, mirrorable_sections
from cost.v2.references import ValidationIssue, validate_reference_sections
from cost.v2.repository import EconomicsRepository, PublicLink
from cost.v2.schemas import SECTION_SCHEMAS

__all__ = [
    "get_public_reader",
    "public_delta_payload",
    "public_link_payload",
    "public_settings_payload",
    "reference_issues",
    "settings_from_request",
]

# Разница без записей журнала: используется, когда падать некуда (реальную
# ошибку недоступности отдаёт сам ``reader.read()``).
_EMPTY_COUNTS = {"new": 0, "changed": 0, "deactivated": 0}

# Журнал ответил, но не отдал ни одной строки. Отдельная причина, а не
# «всё совпадает»: при включённом RLS без политик для роли BlastEX `SELECT`
# возвращает ноль строк и не падает — разница вышла бы нулевой, плашка
# спряталась бы, и рассинхронизацию никто бы не заметил.
EMPTY_JOURNAL_ERROR = (
    "project1 отвечает, но не отдал ни одной записи: вероятно, у роли BlastEX "
    "нет прав или политик RLS на схему public."
)


def get_public_reader(
    repository: EconomicsRepository = Depends(get_economics_repository),
) -> PublicReader:
    """Читалка ``public``: для боевого репозитория — та же база blastex.

    ``PostgresEconomicsRepository`` держит открытый ``engine`` — по нему и
    читается схема public (это одна база, просто другая схема). У
    репозиториев без ``engine`` (тесты, in-memory) читать неоткуда, поэтому
    возвращается пустой статический снимок; тесты API переопределяют эту
    зависимость на свой ``StaticPublicReader`` со снимком журнала.
    """

    engine = getattr(repository, "engine", None)
    if engine is not None:
        return SqlPublicReader(engine)
    return StaticPublicReader(PublicSnapshot(rows={}))


def public_settings_payload(settings: PublicSyncSettings) -> dict[str, Any]:
    """Настройки обмена для страницы «Справочники»: состояние и списки разделов.

    ``mirror_sections`` перечисляет все разделы, которые можно зеркалировать,
    — включённые и выключенные: фронт рисует переключатели по этому словарю и
    сам о разделах ничего не знает.
    """

    sections = mirrorable_sections()
    return {
        "exchange_enabled": settings.exchange_enabled,
        "mirror_sections": {section: section in settings.mirror_sections for section in sections},
        "mirrorable_sections": list(sections),
        "mapped_sections": list(MAPPED_SECTIONS),
    }


def settings_from_request(request: PublicSyncSettingsRequest) -> PublicSyncSettings:
    """Запрос настроек в доменный вид: раздела нет или он `false` — зеркало выключено."""

    return PublicSyncSettings(
        exchange_enabled=request.exchange_enabled,
        mirror_sections=frozenset(
            section for section, enabled in request.mirror_sections.items() if enabled
        ),
    )


def reference_issues(
    reader: PublicReader,
    repository: EconomicsRepository,
    organization_id: str,
    sections: dict[str, list[ReferenceItem]],
    pending_links: Sequence[PublicLink] = (),
) -> list[ValidationIssue]:
    """Замечания справочников: общие проверки, а при включённом обмене — и журнала.

    Ограничения ``public`` проверяются до записи, иначе публикация упала бы
    ошибкой чужой схемы (502) уже в транзакции. Недоступность журнала проверку
    не отменяет: без снимка не найти только конфликты уникальных ключей, а
    пустой ИНН или объект без заказчика видно и так. Саму публикацию
    недоступный журнал не блокирует — если писать всё же понадобится и не
    выйдет, ответ будет 502.
    """

    issues = validate_reference_sections(sections)
    if not repository.get_public_sync_settings(organization_id).exchange_enabled:
        return issues
    links = _merged_links(repository.list_public_links(organization_id), pending_links)
    try:
        snapshot: PublicSnapshot | None = reader.read()
    except PublicUnavailable:
        snapshot = None
    issues.extend(public_constraint_issues(sections, links, snapshot))
    return issues


def public_delta_payload(
    reader: PublicReader,
    repository: EconomicsRepository,
    organization_id: str,
    sections: dict[str, list[ReferenceItemSchema]],
    pending_links: Sequence[PublicLink] = (),
) -> dict[str, Any]:
    """Разница журнала с переданным черновиком в виде JSON-совместимого словаря.

    Недоступность public — не ошибка API: ``PublicUnavailable`` превращается
    в ``available: false`` с текстом причины, а не в HTTP-код, чтобы страница
    «Справочники» продолжала работать без журнала. Пустой ответ журнала —
    тоже недоступность (см. ``EMPTY_JOURNAL_ERROR``).

    Отдельные записи журнала с недопустимыми значениями пропускаются: разница
    остаётся доступной, а их число попадает в ``error``.

    ``pending_links`` — связи, выбранные в черновике и ещё не опубликованные:
    они считаются наравне с сохранёнными и перекрывают их (§4.3).
    """

    draft = {
        section: [item.to_domain() for item in items] for section, items in sections.items()
    }
    try:
        snapshot = reader.read()
    except PublicUnavailable as exc:
        return {
            "available": False,
            "error": str(exc),
            "counts": dict(_EMPTY_COUNTS),
            "entries": [],
        }
    if _is_empty(snapshot):
        return {
            "available": False,
            "error": EMPTY_JOURNAL_ERROR,
            "counts": dict(_EMPTY_COUNTS),
            "entries": [],
        }
    links = _merged_links(repository.list_public_links(organization_id), pending_links)
    delta = compute_delta(snapshot, links, draft)

    entries: list[dict[str, Any]] = []
    counts = dict(_EMPTY_COUNTS)
    skipped = 0
    for entry in delta.entries:
        payload = _entry_payload(entry)
        if payload is None:
            # Значение журнала не проходит проверки справочника (например,
            # наименование длиннее 300 символов). Одна такая строка не должна
            # лишать пользователя всей разницы — она пропускается со счётом.
            skipped += 1
            continue
        counts[entry.kind] += 1
        entries.append(payload)

    error = (
        f"Пропущено записей с недопустимыми значениями: {skipped}" if skipped else ""
    )
    return {
        "available": True,
        "error": error,
        "counts": counts,
        "entries": entries,
    }


def _merged_links(
    stored: Sequence[PublicLink], pending: Sequence[PublicLink]
) -> list[PublicLink]:
    """Сохранённые связи плюс связи черновика; черновик главнее.

    Сохранённая связь уступает связи черновика по любому из двух ключей:
    пользователь мог перенести строку журнала на другую запись справочника
    или, наоборот, связать запись с другой строкой. Обе связи сразу дали бы
    два предложения по одной и той же строке.

    Этим же правилом связь идёт за изменённым кодом записи (§4.3): фронт
    присылает её под новым кодом, сохранённая связь со старым кодом уходит по
    ключу строки журнала, и переименованная запись проверяется как связанная,
    а не как несвязанный дубль записи журнала.
    """

    codes = {(link.section, link.code) for link in pending}
    rows = {(link.public_table, link.public_id) for link in pending}
    merged = [
        link
        for link in stored
        if (link.section, link.code) not in codes
        and (link.public_table, link.public_id) not in rows
    ]
    merged.extend(pending)
    return merged


def _is_empty(snapshot: PublicSnapshot) -> bool:
    """Ни одной строки ни в одной таблице журнала."""

    return all(not snapshot.rows.get(table) for table in TABLES)


def public_link_payload(link: PublicLink) -> dict[str, Any]:
    return {
        "section": link.section,
        "code": link.code,
        "public_table": link.public_table,
        "public_id": link.public_id,
        "synced_at": link.synced_at.isoformat() if link.synced_at else None,
    }


def _entry_payload(entry: DeltaEntry) -> dict[str, Any] | None:
    """Предложение в виде словаря; ``None`` — запись не прошла проверку схемы.

    Проверяются оба слоя: общая обёртка записи справочника и payload по схеме
    раздела. Без второй проверки отрицательное замедление или лишний ключ из
    журнала доходили бы до черновика и падали бы только при публикации —
    ошибкой, которую пользователь не вносил и не может исправить.
    """

    try:
        item = ReferenceItemSchema.model_validate(entry.item)
    except ValidationError:
        return None
    schema = SECTION_SCHEMAS.get(entry.section)
    if schema is not None:
        try:
            schema.model_validate(item.payload)
        except ValidationError:
            return None
    return {
        "kind": entry.kind,
        "section": entry.section,
        "public_table": entry.public_table,
        "public_id": entry.public_id,
        "code": entry.code,
        "name": entry.name,
        "item": item,
        "changes": [_change_payload(change) for change in entry.changes],
    }


def _change_payload(change: FieldChange) -> dict[str, Any]:
    return {"key": change.key, "old": _json_safe(change.old), "new": _json_safe(change.new)}


def _json_safe(value: Any) -> Any:
    """Значение диффа в виде, пригодном для JSON: даты — ISO-строкой, Decimal — строкой."""

    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    return value
