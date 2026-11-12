"""Наряд-путёвка ↔ MagEX: разрешение, очередь повтора, отмена, исполнение (TASK-018, PR 7, §5, §7).

- «Разрешить» (`approve`): содержимое (`design.magex.naryad_payload`) → новая
  версия (`ver` + 1 под блокировкой слоя) → ревизия слоя со снимком `magex`
  (строка JWS — она же QR) → `PUT /naryads/{id}`. `200` — версия принята, печать
  открыта; `409`/`422`/`404`/`401`/`403` — версия отклонена, ревизия убирается
  (отказ ничего не оставляет); `503` и сеть — версия ждёт в очереди повтора,
  печать закрыта.
- Та же выписка без изменений — повтор принятой строки, а не новая версия.
- После выдачи ВМ (`issued` и дальше) склад, взрывник, дата выписки, позиции и
  количества не меняются: нужна новая наряд-путёвка.
- Очередь (`process_due`) — та же строка, отступ 30 с … 60 мин; принятая
  версия на повтор отвечает `200` «без изменений».
"""
from __future__ import annotations

import base64
import json
import logging
import threading
import time
import zlib
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Mapping, Sequence

from api.services import magex_settings as settings_module
from api.services.magex_client import MagexAuthError, MagexClient, MagexError, MagexRejected, MagexUnavailable, Transport
from design.magex import jws as jws_module
from design.magex.naryad_payload import MagexContext, blaster_ref, build_naryad_payload, magex_lines, qty_text

__all__ = [
    "ISSUED_STATUSES",
    "LOCKED_PAYLOAD_KEYS",
    "MagexValidationError",
    "approve",
    "availability",
    "blaster_options",
    "blaster_status",
    "cancel",
    "catalog",
    "client_for",
    "layer_state",
    "locked_issue",
    "process_due",
    "refresh_execution",
    "retry_now",
    "warehouse_options",
]

log = logging.getLogger(__name__)

# Статусы MagEX, после которых ВМ выданы: склад, взрывник, дата, позиции — заблокированы.
ISSUED_STATUSES = frozenset({"issued", "returned", "consumption_by_photo", "closed"})
STATUS_LABELS = {
    "approved": "разрешена",
    "issued": "ВМ выданы",
    "returned": "возвращено",
    "consumption_by_photo": "расход по фото",
    "closed": "закрыта",
    "cancelled": "отменена",
}
# Поля ручного ввода наряда, которые после выдачи ВМ не меняются (§7): склад, взрывник,
# дата выписки, запас (меняет количества), а также № и подтверждение допусков — бумага на руках.
LOCKED_PAYLOAD_KEYS = (
    "magex_warehouse_id", "blaster_code", "blaster_index", "issue_date", "reserve", "number", "admissions_confirmed",
)
RETRY_STEPS_S = (30, 60, 120, 300, 600, 1800, 3600)
# После ротации ключа MagEX до 330 с может не знать новый kid (контракт, разд. 5).
ROTATION_GRACE_S = 330
LEASE_S = 120
_CATALOG_TTL_S = 60
_catalog_cache: dict[str, tuple[float, list[dict[str, Any]]]] = {}
_catalog_lock = threading.Lock()


class MagexValidationError(ValueError):
    """Разрешить нельзя: замечания с `path` к полям окна."""

    def __init__(self, issues: Sequence[Mapping[str, str]]) -> None:
        self.issues = [dict(item) for item in issues]
        super().__init__("Наряд-путёвку нельзя разрешить: " + "; ".join(item["message"] for item in self.issues))


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def _retry_delay(attempts: int) -> int:
    return RETRY_STEPS_S[min(max(attempts, 1), len(RETRY_STEPS_S)) - 1]


# Подменяется в тестах: транспорт MagEX (по умолчанию — `requests`).
TRANSPORT: Transport | None = None


def client_for(organization_id: str, transport: Transport | None = None) -> MagexClient:
    """Клиент MagEX организации; интеграция не настроена — ValueError с причиной."""

    reason = settings_module.offline_reason(organization_id)
    if reason:
        raise ValueError(f"Наряд-путёвка вне учёта MagEX: {reason}")
    settings = settings_module.magex_settings()
    assert settings.signing_key is not None
    return MagexClient(
        settings.api_url, settings.organizations[organization_id], settings.signing_key, transport or TRANSPORT,
    )


def catalog(organization_id: str, client: MagexClient | None = None, *, fresh: bool = False) -> list[dict[str, Any]]:
    """Номенклатура MagEX организации (кэш 60 с)."""

    with _catalog_lock:
        cached = _catalog_cache.get(organization_id)
        if cached and not fresh and time.monotonic() - cached[0] < _CATALOG_TTL_S:
            return cached[1]
    items = (client or client_for(organization_id)).materials()
    with _catalog_lock:
        _catalog_cache[organization_id] = (time.monotonic(), items)
    return items


def material_options(organization_id: str) -> list[dict[str, str]]:
    """Список позиций MagEX для формы справочника материалов: значение и подпись."""

    unit_labels = {"kg": "кг", "pcs": "шт", "m": "м"}
    result = []
    for item in catalog(organization_id, fresh=True):
        name = str(item.get("short_name") or "")
        pvm = str(item.get("pvm_name") or "")
        unit = unit_labels.get(str(item.get("accounting_unit") or ""), str(item.get("accounting_unit") or ""))
        label = f"{name} — {pvm}" if pvm and pvm != name else name
        result.append({"value": str(item["id"]), "label": f"{label}, {unit}" if unit else label})
    return sorted(result, key=lambda item: item["label"])


def _current_snapshot(economics_repository: Any, organization_id: str) -> Any:
    if economics_repository is None:
        return None
    try:
        return economics_repository.get_reference_snapshot(organization_id)
    except Exception:  # noqa: BLE001 — без справочника сопоставления нет: замечание, а не 500
        return None


def _materials_map(snapshot: Any) -> dict[str, str]:
    if snapshot is None:
        return {}
    result = {}
    for item in snapshot.active_items("materials"):
        value = item.payload.get("magex_material_id")
        if value:
            result[str(item.code)] = str(value)
    return result


def _blasters(snapshot: Any) -> list[Any]:
    return [] if snapshot is None else list(snapshot.active_items("blasters"))


def blaster_options(economics_repository: Any, organization_id: str) -> list[dict[str, str]]:
    """Взрывники справочника для выбора в наряде: код и подпись «ФИО — индекс»."""

    return [
        {"value": str(item.code), "label": f"{item.name} — {item.payload.get('blaster_index', '')}"}
        for item in _blasters(_current_snapshot(economics_repository, organization_id))
    ]


def warehouse_options(economics_repository: Any, organization_id: str) -> list[dict[str, str]]:
    """Склады MagEX, указанные у объектов организации (служебного списка складов в MagEX пока нет)."""

    snapshot = _current_snapshot(economics_repository, organization_id)
    if snapshot is None:
        return []
    found: dict[str, str] = {}
    for item in snapshot.active_items("mass_blast_sites"):
        value = str(item.payload.get("magex_warehouse_id") or "")
        if value and value not in found:
            found[value] = str(item.payload.get("warehouse") or "") or f"склад объекта {item.payload.get('site_code', '')}"
    return [{"value": key, "label": label} for key, label in found.items()]


def _resolve_blaster(snapshot: Any, organization_id: str, payload: Mapping[str, Any], seed: Mapping[str, Any]) -> tuple[dict[str, Any] | None, str]:
    """Взрывник наряда: выбранный в наряде, иначе — по ФИО взрывника персонала проекта."""

    blasters = _blasters(snapshot)
    code = str(payload.get("blaster_code") or "")
    item = next((entry for entry in blasters if str(entry.code) == code), None) if code else None
    source = "MANUAL"
    if item is None and not code:
        name = str(((seed.get("people") or {}).get("blaster") or {}).get("name") or "").strip().casefold()
        matches = [entry for entry in blasters if name and str(entry.name).strip().casefold() == name]
        item = matches[0] if len(matches) == 1 else None
        source = "PROJECT"
    if item is None:
        return None, ""
    index = str(item.payload.get("blaster_index") or "")
    return {
        "code": str(item.code), "name": str(item.name), "index": index,
        "ref": blaster_ref(organization_id, index, item.payload.get("employee_ref")),
    }, source


def _context(
    organization_id: str, layer: Mapping[str, Any], payload: Mapping[str, Any], snapshot: Any,
    items: Sequence[Mapping[str, Any]],
) -> MagexContext:
    settings = settings_module.magex_settings()
    seed = layer["seed"]
    project = seed.get("project") or {}
    blaster, _ = _resolve_blaster(snapshot, organization_id, payload, seed)
    return MagexContext(
        organization=settings.organizations.get(organization_id, ""),
        organization_id=organization_id,
        site_code=str(project.get("site_code") or ""),
        site_name=str(project.get("object_name") or ""),
        warehouse_id=str(payload.get("magex_warehouse_id") or ""),
        materials=_materials_map(snapshot),
        catalog={str(item["id"]): item for item in items},
        blaster=blaster,
        approver=(seed.get("people") or {}).get("site_manager"),
        admissions_confirmed=bool(payload.get("admissions_confirmed")),
    )


def _semantic_sha(content: Mapping[str, Any]) -> str:
    """Хэш выписки без `iat`, `ver` и момента разрешения: «то же самое» для повтора."""

    approved = {key: value for key, value in (content.get("approved") or {}).items() if key != "at"}
    return jws_module.content_sha256({**{k: v for k, v in content.items() if k != "ver"}, "approved": approved})


def decode_content(token: str) -> dict[str, Any]:
    """Содержимое своей же строки (подпись не проверяется — строку подписал BlastEX)."""

    body = token.split(".")[1]
    raw = base64.urlsafe_b64decode(body + "=" * (-len(body) % 4))
    return json.loads(zlib.decompress(raw, -15).decode("utf-8"))


def _accepted(versions: Sequence[Mapping[str, Any]]) -> dict[str, Any] | None:
    accepted = [item for item in versions if item["status"] == "ACCEPTED"]
    return dict(max(accepted, key=lambda item: item["ver"])) if accepted else None


def locked_issue(previous: Mapping[str, Any], content: Mapping[str, Any]) -> list[dict[str, str]]:
    """Что после выдачи ВМ менять нельзя: склад, взрывник, дата выписки, состав и количества."""

    problems = []
    if previous.get("wh") != content.get("wh"):
        problems.append(("payload.magex_warehouse_id", "склад выдачи"))
    if (previous.get("blaster") or {}).get("ref") != (content.get("blaster") or {}).get("ref"):
        problems.append(("payload.blaster_code", "взрывник"))
    if previous.get("on") != content.get("on"):
        problems.append(("payload.issue_date", "дата выписки"))
    before = {line["material_id"]: line["qty"] for line in previous.get("lines") or []}
    after = {line["material_id"]: line["qty"] for line in content.get("lines") or []}
    if before != after:
        problems.append(("lines", "позиции и количества ВМ"))
    return [
        {
            "level": "error", "code": "magex_field_locked",
            "message": f"ВМ уже выданы — {what} не меняются: если нужно больше ВМ, заведите новую наряд-путёвку.",
            "path": path,
        }
        for path, what in problems
    ]


def _issued(repository: Any, organization_id: str, layer_id: str) -> bool:
    stored = repository.magex_execution(organization_id, layer_id)
    return bool(stored) and stored["status"] in ISSUED_STATUSES


def _rejection(error: MagexError) -> dict[str, Any]:
    return {"code": error.code, "message": str(error), "details": error.details if isinstance(error.details, (dict, list)) else {}}


def approve(
    repository: Any,
    economics_repository: Any,
    organization_id: str,
    actor: str,
    layer_id: str,
    expected_version: int,
    *,
    transport: Transport | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """«Разрешить» (§5.2). Возвращает состояние MagEX слоя и исход отправки."""

    from api.services import mass_blast_layers_service as layers_service

    now = now or _now()
    if settings_module.magex_mode(organization_id) != "ONLINE":
        raise ValueError("Интеграция с MagEX не включена или не настроена: наряд выпускается без MagEX.")
    viewed = layers_service.get_layer(repository, economics_repository, organization_id, layer_id)
    if viewed["kind"] != "NARYAD":
        raise ValueError("Разрешить можно только наряд-путёвку.")
    if int(viewed["version"]) != int(expected_version):
        from design.mass_blast_repository import MassBlastConflictError

        raise MassBlastConflictError("Слой изменён другим пользователем. Обновите данные.")
    errors = [item for item in viewed["issues"] if item["level"] == "error"]
    if viewed.get("stale"):
        errors.append({"level": "error", "code": "layer_stale", "message": "Проект перевыпущен: перенесите данные заново.", "path": "project_revision_id"})
    if errors:
        raise MagexValidationError(errors)
    payload = layers_service.effective_payload(viewed)
    client = client_for(organization_id, transport)
    try:
        items = catalog(organization_id, client, fresh=True)
    except MagexError as exc:
        # Нет связи — номенклатура последнего чтения (окно наряда читает её при открытии):
        # версия соберётся и встанет в очередь повтора. Не читали ни разу — собрать нечем.
        with _catalog_lock:
            cached = _catalog_cache.get(organization_id)
        if cached is None:
            raise ValueError(f"Номенклатура MagEX недоступна: {exc}. Повторите позже.") from None
        items = cached[1]
    snapshot = _current_snapshot(economics_repository, organization_id)
    ctx = _context(organization_id, viewed, payload, snapshot, items)
    lines = (viewed.get("view") or {}).get("lines") or []
    settings = settings_module.magex_settings()
    key = settings.signing_key
    if key is None:  # client_for уже проверил: без ключа сюда не попасть
        raise ValueError("Не задан ключ подписи BlastEX.")

    def content_for(ver: int, short: bool = False) -> tuple[dict[str, Any], list[dict[str, str]]]:
        return build_naryad_payload(
            layer_id, viewed["seed"], payload, lines, ctx, ver=ver, iat=int(now.timestamp()), approved_at=now,
            short_block_names=short,
        )

    content, issues = content_for(1)
    blocking = [item for item in issues if item["level"] == "error"]
    if blocking:
        raise MagexValidationError(blocking)
    short = len(jws_module.sign_naryad(content, key)) > settings.max_length
    if short:
        content, _ = content_for(1, short=True)
        if len(jws_module.sign_naryad(content, key)) > settings.max_length:
            raise MagexValidationError([{
                "level": "error", "code": "magex_jws_too_long",
                "message": f"Наряд-путёвка не помещается в QR (строка длиннее {settings.max_length} знаков): "
                           "уменьшите число блоков или позиций — разделите на две наряд-путёвки.",
                "path": "lines",
            }])
    versions = repository.list_magex_versions(organization_id, layer_id)
    accepted = _accepted(versions)
    if accepted is not None:
        previous = decode_content(accepted["jws"])
        # Версия новее принятой ещё в пути (очередь): возврат к принятой выписке — тоже новая
        # версия, иначе ожидающая ушла бы позже и перезаписала её.
        in_flight = any(item["ver"] > accepted["ver"] and item["status"] in ("PENDING", "SENDING") for item in versions)
        if _semantic_sha(previous) == _semantic_sha(content) and not in_flight:
            # Без изменений — повтор принятой строки, а не новая версия (§5.5). Изменилось то, что
            # не подписывается (исполнение после взрыва, подписи), — новая ревизия для печати с той же
            # строкой: архивная копия наряда печатает графы «после взрыва» (§2.2 задачи).
            accepted_snapshot = (repository.get_layer_revision(organization_id, accepted["layer_revision_id"]).get("context") or {}).get("magex")
            result = _resend(repository, organization_id, layer_id, accepted, client)
            if accepted_snapshot:
                current = viewed.get("current_revision_id")
                revision = layers_service.issue_layer(
                    repository, economics_repository, organization_id, actor, layer_id, expected_version,
                    magex=accepted_snapshot, skip_if_same=True,
                )
                result = {**result, **layer_state(repository, organization_id, layer_id), "outcome": result["outcome"],
                          "reprinted": revision["id"] != current}
            return result
        try:
            # Выдачу на складе BlastEX узнаёт только из исполнения: перед проверкой запретов — свежее.
            repository.save_magex_execution(organization_id, layer_id, client.get_naryad(layer_id))
        except MagexError:
            pass
        if _issued(repository, organization_id, layer_id):
            locked = locked_issue(previous, content)
            if locked:
                raise MagexValidationError(locked)

    def build(ver: int) -> tuple[str, str, str]:
        versioned, _ = content_for(ver, short)
        return jws_module.sign_naryad(versioned, key), key.kid, _semantic_sha(versioned)

    version = repository.create_magex_version(organization_id, actor, layer_id, build, expected_version=expected_version)
    signed = decode_content(version["jws"])
    merged, _ = magex_lines(lines, ctx.materials, ctx.catalog)
    magex_snapshot = {
        # Округление кг → целые патроны (решение В6): «Выписано» в печати — как в выписке.
        "issue_overrides": _rounded_issue(lines, merged, ctx.catalog),
        "mode": "ONLINE",
        "ver": version["ver"],
        "kid": version["kid"],
        "jws": version["jws"],
        "wh": signed["wh"],
        "num": signed["num"],
        "lines": [{"material_id": row["material_id"], "qty": qty_text(row["qty"]), "keys": row["keys"], "unit": row["unit"]} for row in merged],
        # Что печатается в форме 4 из подписанной выписки (взрывник — из справочника «Взрывники»).
        "print": {"blaster_name": signed["blaster"]["name"], "blaster_index": signed["blaster"]["index"]},
    }
    try:
        revision = layers_service.issue_layer(
            repository, economics_repository, organization_id, actor, layer_id, expected_version, magex=magex_snapshot,
        )
    except Exception:
        repository.update_magex_version(version["id"], status="SUPERSEDED")
        raise
    # В очередь — только вместе с ревизией и со сроком аренды: упадёт процесс до ответа MagEX —
    # отправит очередь; версия без ревизии (сбой выпуска) остаётся SENDING и в очередь не попадает.
    version = repository.activate_magex_version(version["id"], revision["id"], now + timedelta(seconds=LEASE_S))
    warnings = [item for item in issues if item["level"] == "warning"]
    return {**_send(repository, organization_id, actor, layer_id, version, client, now), "warnings": warnings}


def _rounded_issue(
    lines: Sequence[Mapping[str, Any]], merged: Sequence[Mapping[str, Any]], catalog: Mapping[str, Mapping[str, Any]],
) -> dict[str, float]:
    """Строки наряда в кг, выписанные штуками MagEX: «к выдаче» после округления до целых, кг."""

    by_key = {str(line.get("key")): line for line in lines}
    result: dict[str, float] = {}
    for row in merged:
        unit_mass = (catalog.get(row["material_id"]) or {}).get("unit_mass_kg")
        keys = [key for key in row["keys"] if (by_key.get(key) or {}).get("unit") == "кг"]
        if row["unit"] != "pcs" or not unit_mass or not keys:
            continue
        mass = float(unit_mass)
        total = round(float(row["qty"]) * mass, 3)
        # Плановое — по всем строкам позиции: кг как есть, штуки — в кг по массе патрона.
        planned = sum(
            float((by_key.get(key) or {}).get("issue_qty") or 0.0) * (1.0 if (by_key.get(key) or {}).get("unit") == "кг" else mass)
            for key in row["keys"]
        )
        if abs(total - planned) > 1e-6:
            # Излишек округления — на первую строку в кг (запас), остальные — как были.
            result[keys[0]] = round(float(by_key[keys[0]].get("issue_qty") or 0.0) + total - planned, 3)
    return result


def _send(
    repository: Any, organization_id: str, actor: str, layer_id: str, version: Mapping[str, Any], client: MagexClient,
    now: datetime, *, retry: bool = False,
) -> dict[str, Any]:
    attempts = int(version.get("attempts") or 0) + 1
    try:
        response = client.put_naryad(layer_id, version["jws"])
    except MagexUnavailable as exc:
        repository.update_magex_version(
            version["id"], status="PENDING", attempts=attempts, response_code=exc.status or None,
            response=_rejection(exc), next_attempt_at=now + timedelta(seconds=_retry_delay(attempts)),
        )
        return {"outcome": "PENDING", **layer_state(repository, organization_id, layer_id)}
    except (MagexRejected, MagexAuthError) as exc:
        created = datetime.fromisoformat(str(version["created_at"]))
        if retry and exc.code == "NARYAD_SIGNATURE_INVALID" and (now - created).total_seconds() < 2 * ROTATION_GRACE_S:
            # Только что опубликованный ключ MagEX мог ещё не увидеть: повтор не раньше 330 с.
            repository.update_magex_version(
                version["id"], status="PENDING", attempts=attempts, response_code=exc.status, response=_rejection(exc),
                next_attempt_at=created + timedelta(seconds=ROTATION_GRACE_S + 30),
            )
            return {"outcome": "PENDING", **layer_state(repository, organization_id, layer_id)}
        repository.update_magex_version(
            version["id"], status="REJECTED", attempts=attempts, response_code=exc.status, response=_rejection(exc),
            next_attempt_at=None,
        )
        if version.get("layer_revision_id"):
            # Отказ ничего не оставляет: ревизии с непринятой строкой нет.
            repository.discard_layer_revision(organization_id, actor, layer_id, version["layer_revision_id"])
        return {"outcome": "REJECTED", "rejection": _rejection(exc), **layer_state(repository, organization_id, layer_id)}
    repository.update_magex_version(
        version["id"], status="ACCEPTED", attempts=attempts, response_code=200, response={}, next_attempt_at=None,
        accepted_at=now,
    )
    if isinstance(response, dict) and response:
        repository.save_magex_execution(organization_id, layer_id, response)
    return {"outcome": "ACCEPTED", **layer_state(repository, organization_id, layer_id)}


def _resend(
    repository: Any, organization_id: str, layer_id: str, accepted: Mapping[str, Any], client: MagexClient,
) -> dict[str, Any]:
    try:
        response = client.put_naryad(layer_id, accepted["jws"])
    except MagexError as exc:
        return {"outcome": "UNCHANGED_UNREACHABLE", "rejection": _rejection(exc), **layer_state(repository, organization_id, layer_id)}
    if isinstance(response, dict) and response:
        repository.save_magex_execution(organization_id, layer_id, response)
    return {"outcome": "UNCHANGED", **layer_state(repository, organization_id, layer_id)}


def retry_now(repository: Any, organization_id: str, actor: str, layer_id: str, *, transport: Transport | None = None) -> dict[str, Any]:
    """«Повторить сейчас»: версия в очереди повтора уходит сразу."""

    pending = [item for item in repository.list_magex_versions(organization_id, layer_id) if item["status"] == "PENDING"]
    if not pending:
        # Очередь уже отправила версию (или её заменили) — показать текущее состояние.
        return {"outcome": "NOTHING_PENDING", **layer_state(repository, organization_id, layer_id)}
    return _send(repository, organization_id, actor, layer_id, pending[-1], client_for(organization_id, transport), _now(), retry=True)


def process_due(repository: Any, *, transport: Transport | None = None, now: datetime | None = None) -> int:
    """Один проход очереди повтора: отправить версии со сроком попытки. Возвращает число отправленных."""

    now = now or _now()
    sent = 0
    for version in repository.claim_due_magex_versions(now, LEASE_S):
        organization_id = str(version["organization_id"])
        if not version.get("layer_revision_id"):
            # Строка без ревизии слоя напечатана не будет — не отправлять, заменить.
            repository.update_magex_version(version["id"], status="SUPERSEDED", next_attempt_at=None)
            continue
        try:
            client = client_for(organization_id, transport)
        except ValueError:
            continue
        try:
            _send(repository, organization_id, "magex-retry", version["layer_id"], version, client, now, retry=True)
            sent += 1
        except Exception:  # noqa: BLE001 — очередь не падает из-за одной версии
            log.exception("Очередь MagEX: версия %s не отправлена", version["id"])
    return sent


def cancel(
    repository: Any, organization_id: str, actor: str, layer_id: str, reason: str, *, transport: Transport | None = None,
) -> dict[str, Any]:
    """Отмена наряда в MagEX до выдачи ВМ (§5.4)."""

    reason = str(reason or "").replace("\x00", "").strip()
    if not reason:
        raise ValueError("Укажите причину отмены.")
    if len(reason) > 500:
        raise ValueError("Причина отмены — не длиннее 500 знаков.")
    accepted = _accepted(repository.list_magex_versions(organization_id, layer_id))
    if accepted is None:
        raise ValueError("Наряд-путёвка в MagEX не принята — отменять нечего.")
    try:
        response = client_for(organization_id, transport).cancel_naryad(layer_id, accepted["ver"], reason)
    except MagexRejected as exc:
        if exc.code == "NARYAD_ALREADY_ISSUED":
            raise ValueError("ВМ уже выданы: наряд-путёвка закрывается на складе (полный возврат, расход 0).") from None
        raise ValueError(f"MagEX не отменил наряд-путёвку: {exc}") from None
    except MagexError as exc:
        raise ValueError(f"MagEX недоступен: {exc}. Повторите позже.") from None
    if isinstance(response, dict) and response:
        repository.save_magex_execution(organization_id, layer_id, response)
    return layer_state(repository, organization_id, layer_id)


def refresh_execution(repository: Any, organization_id: str, layer_id: str, *, transport: Transport | None = None) -> dict[str, Any]:
    """«Обновить»: исполнение из MagEX (`GET /naryads/{id}`); нет связи — последнее известное."""

    state_error = ""
    if _accepted(repository.list_magex_versions(organization_id, layer_id)) is not None:
        try:
            response = client_for(organization_id, transport).get_naryad(layer_id)
            repository.save_magex_execution(organization_id, layer_id, response)
        except MagexError as exc:
            state_error = str(exc)
    state = layer_state(repository, organization_id, layer_id)
    if state_error:
        state["refresh_error"] = state_error
    return state


def _accepted_lines(
    repository: Any, organization_id: str, accepted: Mapping[str, Any] | None,
) -> tuple[dict[str, str], list[dict[str, Any]]]:
    """Строки выписки принятой версии и наименования позиций MagEX (одно чтение ревизии)."""

    if not accepted or not accepted.get("layer_revision_id"):
        return {}, []
    try:
        context = repository.get_layer_revision(organization_id, accepted["layer_revision_id"]).get("context") or {}
    except Exception:  # noqa: BLE001 — без снимка таблица покажет позицию MagEX
        return {}, []
    lines = list((context.get("magex") or {}).get("lines") or [])
    names = {str(line.get("key")): str(line.get("name") or "") for line in (context.get("view") or {}).get("lines") or []}
    return {
        str(row.get("material_id")): ", ".join(names.get(str(key), str(key)) for key in row.get("keys") or [])
        for row in lines
    }, lines


def layer_state(repository: Any, organization_id: str, layer_id: str) -> dict[str, Any]:
    """Состояние наряда в MagEX для окна: версии, последнее исполнение, режим."""

    mode = settings_module.magex_mode(organization_id)
    state: dict[str, Any] = {"mode": mode}
    if mode is None:
        return state
    if mode == "OFFLINE":
        state["reason"] = settings_module.offline_reason(organization_id)
    versions = repository.list_magex_versions(organization_id, layer_id)
    state["versions"] = [
        {key: item[key] for key in ("ver", "status", "response_code", "response", "attempts", "next_attempt_at",
                                     "created_at", "created_by", "accepted_at", "layer_revision_id")}
        for item in versions
    ]
    latest = versions[-1] if versions else None
    state["latest"] = state["versions"][-1] if latest else None
    accepted = _accepted(versions)
    state["accepted_ver"] = accepted["ver"] if accepted else None
    names, accepted_lines = _accepted_lines(repository, organization_id, accepted)
    state["material_names"] = names
    # Строки выписки принятой версии (позиция MagEX → ключи строк наряда): графы после взрыва.
    state["accepted_lines"] = accepted_lines
    stored = repository.magex_execution(organization_id, layer_id)
    if stored:
        execution = stored["execution"]
        state["execution"] = {
            **execution,
            "status_label": STATUS_LABELS.get(str(execution.get("status") or ""), str(execution.get("status") or "")),
            "fetched_at": stored["fetched_at"],
        }
        state["issued"] = stored["status"] in ISSUED_STATUSES
    else:
        state["issued"] = False
    state["locked_fields"] = list(LOCKED_PAYLOAD_KEYS) if state["issued"] else []
    return state


def availability(
    repository: Any, economics_repository: Any, organization_id: str, layer_id: str, *, transport: Transport | None = None,
) -> dict[str, Any]:
    """Графа «Доступно на складе»: по строкам наряда в их единице и нехватка по позиции MagEX."""

    from api.services import mass_blast_layers_service as layers_service

    viewed = layers_service.get_layer(repository, economics_repository, organization_id, layer_id)
    payload = layers_service.effective_payload(viewed)
    warehouse = str(payload.get("magex_warehouse_id") or "")
    if not warehouse:
        return {"items": {}, "error": "Не выбран склад MagEX."}
    client = client_for(organization_id, transport)
    snapshot = _current_snapshot(economics_repository, organization_id)
    try:
        items = catalog(organization_id, client)
    except MagexError as exc:
        return {"items": {}, "error": f"MagEX недоступен: {exc}"}
    by_id = {str(item["id"]): item for item in items}
    materials = _materials_map(snapshot)
    lines = (viewed.get("view") or {}).get("lines") or []
    merged, _ = magex_lines(lines, materials, by_id)
    ids = [row["material_id"] for row in merged]
    if not ids:
        return {"items": {}, "error": ""}
    try:
        answer = client.availability(warehouse, ids[:100])
    except MagexRejected as exc:
        if exc.status == 404:
            return {"items": {}, "error": "Склад MagEX не найден: проверьте «Склад MagEX» объекта.", "code": "magex_warehouse_unknown"}
        return {"items": {}, "error": str(exc)}
    except MagexError as exc:
        return {"items": {}, "error": f"MagEX недоступен: {exc}"}
    available = {str(item["material_id"]): item for item in answer.get("items") or []}
    result: dict[str, dict[str, Any]] = {}
    shortages = []
    for row in merged:
        item = available.get(row["material_id"])
        if item is None:
            continue
        free = float(item.get("available") or 0)
        short = float(row["qty"]) > free + 1e-9
        catalog_item = by_id.get(row["material_id"]) or {}
        if short:
            shortages.append({
                "material": str(catalog_item.get("short_name") or row["material_id"]),
                "required": float(row["qty"]), "available": free, "unit": row["unit"],
            })
        for key in row["keys"]:
            line = next((entry for entry in lines if entry.get("key") == key), {})
            value = free
            unit_mass = catalog_item.get("unit_mass_kg")
            if line.get("unit") == "кг" and row["unit"] == "pcs" and unit_mass:
                value = free * float(unit_mass)
            elif line.get("unit") == "шт" and row["unit"] == "kg" and line.get("unit_mass_kg"):
                value = free / float(line["unit_mass_kg"])
            result[key] = {"available": round(value, 3), "short": short, "shared": len(row["keys"]) > 1,
                           "material_id": row["material_id"]}
    return {
        "items": result, "shortages": shortages, "calculated_at": answer.get("calculated_at"),
        "warehouse_id": warehouse, "error": "",
    }


def blaster_status(
    repository: Any, economics_repository: Any, organization_id: str, layer_id: str, *, transport: Transport | None = None,
) -> dict[str, Any]:
    """Отчитался ли взрывник наряда (`GET /blasters/{ref}/report-status`): предупреждение, не запрет."""

    from api.services import mass_blast_layers_service as layers_service

    viewed = layers_service.get_layer(repository, economics_repository, organization_id, layer_id)
    payload = layers_service.effective_payload(viewed)
    blaster, source = _resolve_blaster(
        _current_snapshot(economics_repository, organization_id), organization_id, payload, viewed["seed"],
    )
    if blaster is None:
        return {"blaster": None, "reported": None}
    try:
        answer = client_for(organization_id, transport).report_status(blaster["ref"])
    except MagexError as exc:
        return {"blaster": blaster, "source": source, "reported": None, "error": str(exc)}
    return {"blaster": blaster, "source": source, "reported": bool(answer.get("reported", True)),
            "pending": list(answer.get("pending") or [])}


def resolved_blaster(snapshot: Any, organization_id: str, layer: Mapping[str, Any], payload: Mapping[str, Any]) -> dict[str, Any] | None:
    """Взрывник наряда по текущему справочнику (выбранный или найденный по ФИО персонала проекта)."""

    blaster, source = _resolve_blaster(snapshot, organization_id, payload, layer["seed"])
    return {**blaster, "source": source} if blaster else None


def start_worker(repository_factory: Callable[[], Any], interval_s: int = 30) -> threading.Event:
    """Фоновая очередь повтора в процессе API (решение В9): раз в `interval_s` — `process_due`."""

    stop = threading.Event()

    def loop() -> None:
        while not stop.wait(interval_s):
            try:
                process_due(repository_factory())
            except Exception:  # noqa: BLE001 — очередь живёт, пока живёт API
                log.exception("Очередь MagEX: проход не выполнен")

    threading.Thread(target=loop, name="magex-retry", daemon=True).start()
    return stop
