"""PACKAGE проекта МВ v2: ZIP с документами комплекта и общим PDF (TASK-018 §2).

Порядок — таблица документов TASK-018 §2: титул, техрасчёт, таблица
параметров, распорядок (графика Г.1–Г.5 — PR 4), акт готовности, уведомления,
наряд-путёвки, талон-допуск, акт приёмки. `00_Комплект.pdf` — всё подряд,
двусторонне (пустые обороты, сквозная нумерация проекта, своя — у слоёв);
рядом — каждый документ отдельно (без пустых оборотов) и `manifest.json`.
Время записей ZIP постоянное: та же ревизия и те же слои — те же байты.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping, Sequence

from design.reporting.drill.archive import build_zip
from design.reporting.mass_blast import frame
from design.reporting.mass_blast.layers import LAYER_DOCUMENTS, layer_part
from design.reporting.mass_blast.project import project_parts

# Порядок слоёв в комплекте (TASK-018 §2, документы 6–10) и номера файлов.
LAYER_ORDER = ("READINESS_ACT", "NOTIFICATION", "NARYAD", "TALON", "ACCEPTANCE_ACT")
LAYER_NUMBERS = {"READINESS_ACT": "06", "NOTIFICATION": "07", "NARYAD": "08", "TALON": "09", "ACCEPTANCE_ACT": "10"}
PROJECT_NUMBERS = {"title": "01", "techcalc": "02", "table": "03", "schedule": "04"}


def _file_name(number: str, label: str, suffix: str = "") -> str:
    name = label.replace(" · ", "_").replace(" ", "_")
    return f"{number}_{name}{suffix}.pdf"


def _unique_names(entries: list[tuple[str, bytes]]) -> list[tuple[str, bytes]]:
    """Одинаковые имена (два блока с одним кодом на разных горизонтах) — с номером:
    иначе при распаковке второй файл затрёт первый."""

    seen: dict[str, int] = {}
    result: list[tuple[str, bytes]] = []
    for name, data in entries:
        seen[name] = seen.get(name, 0) + 1
        if seen[name] > 1:
            stem = name[: -len(".pdf")] if name.endswith(".pdf") else name
            name = f"{stem}_{seen[name]}.pdf"
        result.append((name, data))
    return result


def ordered_layers(layers: Sequence[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    """Ревизии слоёв в порядке комплекта; внутри вида — как пришли (по дате создания)."""

    rank = {kind: index for index, kind in enumerate(LAYER_ORDER)}
    return sorted(layers, key=lambda item: rank.get(str(item.get("kind")), len(rank)))


def render_package(
    context: Mapping[str, Any],
    layers: Sequence[Mapping[str, Any]],
    *,
    manifest: Mapping[str, Any],
) -> bytes:
    """ZIP комплекта. `layers` — ревизии слоёв: `{"kind", "revision_no", "context"}`."""

    parts = project_parts(context)
    layer_items = ordered_layers(layers)
    layer_parts = [layer_part(item["context"]) for item in layer_items]
    entries: list[tuple[str, bytes]] = []
    title = "Комплект проекта массового взрыва"
    combined = frame.render(parts + layer_parts, title=title, duplex=True)
    entries.append(("00_Комплект.pdf", combined))
    for part in parts:
        kind = part.key.split(":")[0]
        entries.append((_file_name(PROJECT_NUMBERS[kind], part.label), frame.render([part], title=part.label, duplex=False)))
    seen: dict[str, int] = {}
    for item, part in zip(layer_items, layer_parts):
        kind = str(item.get("kind"))
        seen[kind] = seen.get(kind, 0) + 1
        suffix = f"_{seen[kind]}" if sum(1 for other in layer_items if other.get("kind") == kind) > 1 else ""
        label = LAYER_DOCUMENTS[kind][0]
        entries.append((_file_name(LAYER_NUMBERS[kind], label, suffix), frame.render([part], title=label, duplex=False)))
    entries = _unique_names(entries)
    files = [{"name": name, "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)} for name, data in entries]
    document = {**dict(manifest), "files": files}
    entries.append(("manifest.json", json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8")))
    return build_zip(entries)


__all__ = ["LAYER_ORDER", "ordered_layers", "render_package"]
