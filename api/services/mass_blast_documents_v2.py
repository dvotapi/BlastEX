"""Печать проекта МВ v2 и документов дня взрыва (TASK-018, PR 3).

Документы v2 печатаются на лету из неизменяемых ревизий (решение владельца
11.11.2026, В2): та же ревизия — те же байты, файлы не хранятся. Ревизии v1 —
по-прежнему `POST /{project_id}/documents` и прежний рендер.
"""
from __future__ import annotations

from typing import Any, Mapping

from cost.v2.repository import EconomicsRepository
from design.mass_blast_repository import MassBlastConflictError, PostgresMassBlastRepository
from design.reporting.mass_blast.layers import render_layer_document
from design.reporting.mass_blast.graphics import has_graphics
from design.reporting.mass_blast.package import render_package
from design.reporting.mass_blast.project import DOCUMENTS, render_project_document

__all__ = [
    "PRINTABLE_STATUSES",
    "PreviewError",
    "layer_document",
    "layer_preview",
    "project_document",
    "project_package",
    "project_preview",
]

PRINTABLE_STATUSES = {"approved", "executed", "closed"}
PROJECT_DOCUMENTS = (*DOCUMENTS, "project")


class PreviewError(ValueError):
    """Черновик с ошибками проверки: предпросмотр не строится (422)."""


def _v2_revision(repository: PostgresMassBlastRepository, organization_id: str, revision_id: str) -> tuple[dict, dict]:
    revision = repository.get_revision(organization_id, revision_id)
    context = revision.get("context") or {}
    if int(context.get("document_context_version") or 1) < 2:
        raise MassBlastConflictError(
            "Ревизия проекта по прежней форме (контекст v1): документы выпускаются через «Документы» проекта."
        )
    project = repository.get_project(organization_id, revision["project_id"])
    if project["lifecycle_status"] not in PRINTABLE_STATUSES:
        raise MassBlastConflictError("Документы выпускаются только после утверждения ревизии.")
    return revision, context


def project_document(
    repository: PostgresMassBlastRepository, organization_id: str, revision_id: str, document: str
) -> tuple[bytes, str]:
    """PDF документа проекта (`title`, `technical-calculation`, `parameter-table`, `schedule`, `graphics`, `project`)."""

    if document not in PROJECT_DOCUMENTS:
        raise ValueError(f"Неизвестный документ проекта МВ: {document}.")
    revision, context = _v2_revision(repository, organization_id, revision_id)
    if document == "graphics" and not has_graphics(context):
        raise MassBlastConflictError("Ревизия выпущена до графической части Г.1–Г.5: данных графики в ней нет.")
    return render_project_document(context, document), _file_name(context, revision, document, ".pdf")


def _file_name(context: Mapping[str, Any], revision: Mapping[str, Any], what: str, suffix: str) -> str:
    project = context.get("project") or {}
    base = f"{project.get('site_code') or 'site'}_{project.get('blast_date') or ''}_r{revision.get('revision_no')}_{what}"
    clean = "".join(char if char.isalnum() or char in "-_" else "_" for char in base).strip("_")
    return f"{clean or 'mass_blast'}{suffix}"


def _package_layers(
    repository: PostgresMassBlastRepository, organization_id: str, revision: Mapping[str, Any]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Слои комплекта: последняя выпущенная ревизия каждого слоя на этой ревизии
    проекта (решение В8); остальные — в «не вошло» с причиной."""

    included: list[dict[str, Any]] = []
    omitted: list[dict[str, Any]] = []
    for layer in repository.list_layers(organization_id, revision["project_id"]):
        entry = {"layer_id": layer["id"], "kind": layer["kind"]}
        if not layer.get("current_revision_id"):
            omitted.append({**entry, "reason": "слой не выпущен"})
            continue
        layer_revision = repository.latest_layer_revision(organization_id, layer["id"], revision["id"])
        if layer_revision is None:
            omitted.append({**entry, "reason": "выпущен по другой ревизии проекта"})
            continue
        included.append({
            **entry, "revision_id": layer_revision["id"], "revision_no": layer_revision["revision_no"],
            "content_sha256": layer_revision["content_sha256"], "context": layer_revision["context"],
        })
    return included, omitted


def project_package(
    repository: PostgresMassBlastRepository, organization_id: str, revision_id: str
) -> tuple[bytes, str]:
    revision, context = _v2_revision(repository, organization_id, revision_id)
    included, omitted = _package_layers(repository, organization_id, revision)
    manifest = {
        "project_id": revision["project_id"],
        "revision_id": revision["id"],
        "revision_no": revision.get("revision_no"),
        "content_sha256": revision.get("content_sha256"),
        "document_context_version": context.get("document_context_version"),
        "document_template_version": revision.get("document_template_version"),
        "layers": [{key: item[key] for key in ("layer_id", "kind", "revision_id", "revision_no", "content_sha256")}
                   for item in included],
        "omitted_layers": omitted,
    }
    if not has_graphics(context):
        manifest["omitted_documents"] = [
            {"document": "graphics", "reason": "ревизия выпущена до графической части Г.1–Г.5 (PR 4): данных графики в ней нет"}
        ]
    data = render_package(context, included, manifest=manifest)
    return data, _file_name(context, revision, "package", ".zip")


def layer_document(
    repository: PostgresMassBlastRepository, organization_id: str, layer_revision_id: str
) -> tuple[bytes, str]:
    revision = repository.get_layer_revision(organization_id, layer_revision_id)
    context = revision["context"]
    kind = str(context.get("kind") or revision.get("kind") or "layer").lower()
    return render_layer_document(context), f"{kind}_r{revision['revision_no']}.pdf"


def project_preview(
    repository: PostgresMassBlastRepository,
    economics_repository: EconomicsRepository,
    organization_id: str,
    project_id: str,
    document: str,
) -> bytes:
    """Предпросмотр черновика проекта v2 с пометкой «ЧЕРНОВИК» (для PR 6)."""

    from api.services.mass_blast_service import is_v2, validate_project

    if document not in PROJECT_DOCUMENTS:
        raise ValueError(f"Неизвестный документ проекта МВ: {document}.")
    project = repository.get_project(organization_id, project_id)
    if not is_v2(project):
        raise MassBlastConflictError("Предпросмотр документов — только у проекта по форме ВМ.09.03 (контекст v2).")
    result = validate_project(repository, organization_id, project_id, economics_repository=economics_repository)
    errors = [issue["message"] for issue in result["issues"] if issue.get("level") == "error"]
    if errors:
        raise PreviewError("Предпросмотр недоступен: " + "; ".join(errors))
    return render_project_document(result["context"], document, draft=True)


def layer_preview(
    repository: PostgresMassBlastRepository,
    economics_repository: EconomicsRepository | None,
    organization_id: str,
    layer_id: str,
) -> bytes:
    """Предпросмотр слоя по текущим данным (до выпуска) с пометкой «ЧЕРНОВИК»."""

    from api.services import mass_blast_layers_service as layers_service

    layer = layers_service.get_layer(repository, economics_repository, organization_id, layer_id)
    errors = [issue["message"] for issue in layer.get("issues") or [] if issue.get("level") == "error"]
    if errors:
        raise PreviewError("Предпросмотр недоступен: " + "; ".join(errors))
    revision = {
        "kind": layer["kind"], "seed": layer["seed"], "payload": layers_service.effective_payload(layer),
        "view": {key: value for key, value in (layer.get("view") or {}).items() if key not in ("defaults", "rememberable")},
    }
    return render_layer_document(revision, draft=True)
