"""Ситуация карьера (TASK-013) по ссылкам проекта блока — общая для документов.

Паспорт на бурение рисует её на плане (TASK-015, PR 3), проект массового
взрыва берёт из неё охраняемые объекты (TASK-018, PR 2). Чтение и упрощение
ситуации большого чертежа — секунды, поэтому слои кэшируются по версии
источника: переимпорт файла меняет `revision`, и ключ устаревает.

База чертежей и чтение источника передаются вызывающим: так каждый сервис
подменяет их в своих тестах, а кэш один.
"""
from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from threading import Lock
from typing import Any, Callable, Iterable, Mapping

from design.spatial.cad.repository import CadSourceNotFound

__all__ = ["SITUATION_CACHE", "SituationProblem", "design_situation", "situation_refs"]

SITUATION_CACHE: OrderedDict[tuple[str, str, int], tuple[list[dict[str, Any]], list[str]]] = OrderedDict()
_CACHE_SIZE = 8
_CACHE_LOCK = Lock()


@dataclass(frozen=True)
class SituationProblem:
    """Что не так с одной версией ситуации: вызывающий сам решает, каким кодом сказать."""

    kind: str  # "unavailable" — база или файл не читаются; "missing" — версия удалена; "capped" — не все слои
    title: str
    layers: tuple[str, ...] = ()


def situation_refs(cad: Mapping[str, Any] | None) -> list[Mapping[str, Any]]:
    """Ссылки `contour.cad.situation` без повторов источника."""

    refs: list[Mapping[str, Any]] = []
    seen: set[str] = set()
    for ref in (cad or {}).get("situation") or ():
        source_id = str(ref.get("source_id") or "")
        if source_id and source_id not in seen:
            seen.add(source_id)
            refs.append(ref)
    return refs


def _layers(reader: Callable[..., Any], repository: Any, organization_id: str, source_id: str, revision: int):
    key = (organization_id, source_id, int(revision))
    with _CACHE_LOCK:
        if key in SITUATION_CACHE:
            SITUATION_CACHE.move_to_end(key)
            return SITUATION_CACHE[key]
    geometry = reader(repository, organization_id, source_id)
    value = (
        [
            {
                "name": layer.name,
                "kind": layer.kind,
                "lines": [{"points": line.points, "closed": line.closed} for line in layer.lines],
                # Подписи плана карьера («ДСК», «КПП»); у чертежа блока их нет.
                "labels": [{"text": label.text, "point": list(label.point)} for label in getattr(layer, "labels", ())],
            }
            for layer in geometry.layers
            if layer.lines or getattr(layer, "labels", ())
        ],
        [layer.name for layer in geometry.layers if layer.omitted],
    )
    with _CACHE_LOCK:
        SITUATION_CACHE[key] = value
        while len(SITUATION_CACHE) > _CACHE_SIZE:
            SITUATION_CACHE.popitem(last=False)
    return value


def design_situation(
    organization_id: str,
    refs: Iterable[Mapping[str, Any]],
    *,
    repository_factory: Callable[[], Any],
    reader: Callable[..., Any],
    on_error: Callable[[str], None] | None = None,
) -> tuple[list[dict[str, Any]], list[SituationProblem]]:
    """Слои ситуации `{"name", "kind", "lines", "labels"}` по ссылкам и проблемы по версиям.

    Без ссылок база чертежей не открывается. Слои кэша только читаются —
    вызывающий не должен их менять.
    """

    refs = list(refs)
    if not refs:
        return [], []
    layers: list[dict[str, Any]] = []
    problems: list[SituationProblem] = []
    try:
        repository = repository_factory()
    except Exception:  # noqa: BLE001 — ситуация не главное: без неё документ выпускается
        if on_error:
            on_error("")
        repository = None
    for ref in refs:
        source_id = str(ref["source_id"])
        title = str(ref.get("title") or source_id)
        if repository is None:
            problems.append(SituationProblem("unavailable", title))
            continue
        try:
            record = repository.get_source(organization_id, source_id)
            if record is None:
                raise CadSourceNotFound(source_id)
            source_layers, capped = _layers(reader, repository, organization_id, source_id, record.revision)
        except CadSourceNotFound:
            problems.append(SituationProblem("missing", title))
            continue
        except Exception:  # noqa: BLE001 — повреждённый чертёж не должен ронять проверку документа
            if on_error:
                on_error(source_id)
            problems.append(SituationProblem("unavailable", title))
            continue
        if capped:
            problems.append(SituationProblem("capped", title, tuple(capped)))
        layers += source_layers
    return layers, problems
