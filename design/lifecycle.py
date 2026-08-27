"""Formal BlastDesign lifecycle (BDX-025).

Statuses are independent of DATA_ROLES (designed / executed / predicted /
measured). A transition is human-gated. Overlays, optimisation and ML never
change status and never rewrite an approved or closed passport.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterable

# Same literals as design.models.DATA_ROLES — lifecycle must not import models.
ROLE_DESIGNED = "designed"
ROLE_EXECUTED = "executed"
ROLE_PREDICTED = "predicted"
ROLE_MEASURED = "measured"

STATUS_DRAFT = "draft"
STATUS_IN_REVIEW = "in_review"
STATUS_APPROVED = "approved"
STATUS_EXECUTED = "executed"
STATUS_CLOSED = "closed"

LIFECYCLE_STATUSES = (
    STATUS_DRAFT,
    STATUS_IN_REVIEW,
    STATUS_APPROVED,
    STATUS_EXECUTED,
    STATUS_CLOSED,
)

# Sequential review chain. The only backward step is withdrawing a review.
ALLOWED_TRANSITIONS: dict[str, tuple[str, ...]] = {
    STATUS_DRAFT: (STATUS_IN_REVIEW,),
    STATUS_IN_REVIEW: (STATUS_DRAFT, STATUS_APPROVED),
    STATUS_APPROVED: (STATUS_EXECUTED,),
    STATUS_EXECUTED: (STATUS_CLOSED,),
    STATUS_CLOSED: (),
}

KIND_CREATED = "created"
KIND_REVISE = "revise"
KIND_RECORD_EXECUTION = "record_execution"
KIND_RECORD_MEASURED = "record_measured"
KIND_RENAME = "rename"
KIND_TRANSITION = "transition"
KIND_FORK = "fork"

MUTATION_DESIGNED = "designed"
MUTATION_EXECUTION = "execution"
MUTATION_MEASURED = "measured"
MUTATION_METADATA = "metadata"

ALLOWED_MUTATIONS: dict[str, frozenset[str]] = {
    STATUS_DRAFT: frozenset(
        {MUTATION_DESIGNED, MUTATION_EXECUTION, MUTATION_MEASURED, MUTATION_METADATA}
    ),
    STATUS_IN_REVIEW: frozenset({MUTATION_METADATA}),
    STATUS_APPROVED: frozenset({MUTATION_EXECUTION, MUTATION_MEASURED, MUTATION_METADATA}),
    STATUS_EXECUTED: frozenset({MUTATION_EXECUTION, MUTATION_MEASURED, MUTATION_METADATA}),
    STATUS_CLOSED: frozenset(),
}

DELETABLE_STATUSES = frozenset({STATUS_DRAFT, STATUS_IN_REVIEW})

AUTO_ACTORS = frozenset({"", "auto", "system", "scheduler", "cron", "pipeline", "ci"})

STATUS_LABELS = {
    STATUS_DRAFT: "черновик",
    STATUS_IN_REVIEW: "на проверке",
    STATUS_APPROVED: "утверждён",
    STATUS_EXECUTED: "выполнен",
    STATUS_CLOSED: "закрыт",
}

DATA_ROLES = {
    "designed": ROLE_DESIGNED,
    "executed": ROLE_EXECUTED,
    "predicted": ROLE_PREDICTED,
    "measured": ROLE_MEASURED,
}

DESIGNED_PAYLOAD_KEYS = (
    "contour",
    "holes",
    "loads",
    "network",
    "pattern_params",
    "charge_rules",
    "rock_name",
    "explosive_key",
    "coordinate_system",
    "surfaces",
    "domains",
    "water_table_z_m",
    "receptors",
    "vibration_models",
)

EXECUTION_PAYLOAD_KEYS = (
    "as_drilled_holes",
    "as_charged_holes",
    "as_fired_holes",
)

MEASURED_PAYLOAD_KEYS = (
    "vibration_measurements",
    "blast_result",
)


class InvalidLifecycleError(ValueError):
    """A status change was missing a human gate or broke the lifecycle."""


class FrozenDesignError(ValueError):
    """The passport is frozen against this class of mutation."""


@dataclass
class LifecycleEvent:
    """One audit record. Transitions are never inferred by ML or overlays."""

    kind: str
    at: str = ""
    actor: str = ""
    from_status: str = ""
    to_status: str = ""
    note: str = ""
    confirm: bool = False
    revision: int = 0
    designed_sha256: str = ""
    mutations: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "at": self.at,
            "actor": self.actor,
            "from_status": self.from_status,
            "to_status": self.to_status,
            "note": self.note,
            "confirm": bool(self.confirm),
            "revision": int(self.revision),
            "designed_sha256": self.designed_sha256,
            "mutations": list(self.mutations),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> LifecycleEvent:
        payload = data or {}
        mutations = payload.get("mutations") or []
        return cls(
            kind=str(payload.get("kind", "") or ""),
            at=str(payload.get("at", "") or ""),
            actor=str(payload.get("actor", "") or ""),
            from_status=str(payload.get("from_status", "") or ""),
            to_status=str(payload.get("to_status", "") or ""),
            note=str(payload.get("note", "") or ""),
            confirm=bool(payload.get("confirm", False)),
            revision=int(payload.get("revision", 0) or 0),
            designed_sha256=str(payload.get("designed_sha256", "") or ""),
            mutations=[str(item) for item in mutations],
        )


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def normalize_status(value: Any, default: str = STATUS_DRAFT) -> str:
    text = str(value or default).strip().lower().replace("-", "_")
    aliases = {
        "inreview": STATUS_IN_REVIEW,
        "review": STATUS_IN_REVIEW,
        "reviewed": STATUS_IN_REVIEW,
        "approve": STATUS_APPROVED,
        "approval": STATUS_APPROVED,
        "done": STATUS_EXECUTED,
        "fired": STATUS_EXECUTED,
        "complete": STATUS_CLOSED,
        "close": STATUS_CLOSED,
        "frozen": STATUS_CLOSED,
    }
    if text in LIFECYCLE_STATUSES:
        return text
    if text in aliases:
        return aliases[text]
    if not text:
        return default
    raise InvalidLifecycleError(
        f"Неизвестный статус паспорта «{value}». "
        f"Допустимы: {', '.join(LIFECYCLE_STATUSES)}."
    )


def allowed_transitions(status: str) -> list[str]:
    return list(ALLOWED_TRANSITIONS.get(normalize_status(status), ()))


def listed_statuses() -> list[dict[str, Any]]:
    return [
        {
            "name": status,
            "label": STATUS_LABELS[status],
            "allowed_transitions": list(ALLOWED_TRANSITIONS[status]),
            "allowed_mutations": sorted(ALLOWED_MUTATIONS[status]),
            "frozen_designed": not designed_mutable(status),
            "frozen_record": is_record_frozen(status),
        }
        for status in LIFECYCLE_STATUSES
    ]


def designed_mutable(status: str) -> bool:
    return MUTATION_DESIGNED in ALLOWED_MUTATIONS.get(normalize_status(status), frozenset())


def is_record_frozen(status: str) -> bool:
    return normalize_status(status) == STATUS_CLOSED


def can_delete(status: str) -> bool:
    return normalize_status(status) in DELETABLE_STATUSES


def allow_mutation(status: str, kind: str) -> bool:
    return kind in ALLOWED_MUTATIONS.get(normalize_status(status), frozenset())


def _as_dict(design: Any) -> dict[str, Any]:
    if hasattr(design, "to_dict"):
        return design.to_dict()
    return dict(design)


def slice_payload(design: Any, keys: Iterable[str]) -> dict[str, Any]:
    data = _as_dict(design)
    return {key: data.get(key) for key in keys}


def designed_payload(design: Any) -> dict[str, Any]:
    return slice_payload(design, DESIGNED_PAYLOAD_KEYS)


def execution_payload(design: Any) -> dict[str, Any]:
    return slice_payload(design, EXECUTION_PAYLOAD_KEYS)


def measured_payload(design: Any) -> dict[str, Any]:
    return slice_payload(design, MEASURED_PAYLOAD_KEYS)


def designed_sha256(design: Any) -> str:
    encoded = json.dumps(
        designed_payload(design),
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def classify_mutations(stored: Any, incoming: Any) -> list[str]:
    kinds: list[str] = []
    if designed_payload(stored) != designed_payload(incoming):
        kinds.append(MUTATION_DESIGNED)
    if execution_payload(stored) != execution_payload(incoming):
        kinds.append(MUTATION_EXECUTION)
    if measured_payload(stored) != measured_payload(incoming):
        kinds.append(MUTATION_MEASURED)
    stored_name = stored.name if hasattr(stored, "name") else _as_dict(stored).get("name", "")
    incoming_name = incoming.name if hasattr(incoming, "name") else _as_dict(incoming).get("name", "")
    if stored_name != incoming_name:
        kinds.append(MUTATION_METADATA)
    return kinds


def assert_mutations_allowed(status: str, mutations: Iterable[str]) -> None:
    current = normalize_status(status)
    blocked = [kind for kind in mutations if not allow_mutation(current, kind)]
    if not blocked:
        return
    if current == STATUS_CLOSED:
        raise FrozenDesignError(
            "Закрытый паспорт заморожен: любая правка запрещена, в том числе "
            "сценарии, оптимизация и ML-оверлеи."
        )
    if MUTATION_DESIGNED in blocked:
        raise FrozenDesignError(
            f"Паспорт в статусе «{current}»: проектная часть (DESIGNED) заморожена. "
            "Сценарии, оптимизация и ML не имеют права её переписывать."
        )
    raise FrozenDesignError(
        f"Паспорт в статусе «{current}»: изменения «{', '.join(blocked)}» запрещены."
    )


def require_actor(actor: str) -> str:
    text = str(actor or "").strip()
    if text.lower() in AUTO_ACTORS:
        raise InvalidLifecycleError(
            "Смену статуса паспорта подтверждает человек: нужен идентификатор, "
            "системные акторы и автопереходы запрещены."
        )
    return text


def require_confirm(confirm: bool) -> None:
    if confirm is not True:
        raise InvalidLifecycleError(
            "Смена статуса паспорта требует явного confirm=true. Автоперехода нет."
        )


def assert_transition(from_status: str, to_status: str) -> tuple[str, str]:
    current = normalize_status(from_status)
    target = normalize_status(to_status)
    if current == target:
        raise InvalidLifecycleError(
            f"Паспорт уже в статусе «{current}». Повторный переход не требуется."
        )
    allowed = ALLOWED_TRANSITIONS.get(current, ())
    if target not in allowed:
        if not allowed:
            raise InvalidLifecycleError(
                f"Статус «{current}» терминальный: дальнейшие переходы запрещены."
            )
        raise InvalidLifecycleError(
            f"Переход {current} → {target} запрещён. "
            f"Допустимы: {', '.join(allowed) or 'нет'}."
        )
    return current, target


def plan_transition(
    *,
    from_status: str,
    to_status: str,
    actor: str,
    confirm: bool,
    note: str = "",
    revision: int = 0,
    content_sha256: str = "",
) -> LifecycleEvent:
    """Validate a human-gated status change. Does not persist."""
    require_confirm(confirm)
    who = require_actor(actor)
    current, target = assert_transition(from_status, to_status)
    return LifecycleEvent(
        kind=KIND_TRANSITION,
        at=utc_now_iso(),
        actor=who,
        from_status=current,
        to_status=target,
        note=str(note or "").strip(),
        confirm=True,
        revision=int(revision),
        designed_sha256=content_sha256,
        mutations=[],
    )


def make_event(
    *,
    kind: str,
    actor: str = "",
    from_status: str = "",
    to_status: str = "",
    note: str = "",
    confirm: bool = False,
    revision: int = 0,
    content_sha256: str = "",
    mutations: Iterable[str] | None = None,
) -> LifecycleEvent:
    return LifecycleEvent(
        kind=kind,
        at=utc_now_iso(),
        actor=str(actor or "").strip(),
        from_status=from_status,
        to_status=to_status,
        note=str(note or "").strip(),
        confirm=confirm,
        revision=int(revision),
        designed_sha256=content_sha256,
        mutations=list(mutations or []),
    )
