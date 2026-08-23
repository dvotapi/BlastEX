"""Human-gated status transitions. Never auto-deploy."""
from __future__ import annotations

from intelligence.registry.types import (
    AUTO_ACTORS,
    ALLOWED_TRANSITIONS,
    PromotionEvent,
    allowed_transitions,
    normalize_status,
    utc_now_iso,
)


class InvalidPromotionError(ValueError):
    """A status change was missing a human gate or broke the lifecycle."""


def require_actor(actor: str) -> str:
    text = str(actor or "").strip()
    if text.lower() in AUTO_ACTORS:
        raise InvalidPromotionError(
            "Продвижение модели только вручную: нужен идентификатор человека, "
            "автодеплой и системные акторы запрещены."
        )
    return text


def require_confirm(confirm: bool) -> None:
    if confirm is not True:
        raise InvalidPromotionError(
            "Продвижение модели требует явного confirm=true. Автодеплоя нет."
        )


def assert_transition(from_status: str, to_status: str) -> tuple[str, str]:
    current = normalize_status(from_status)
    target = normalize_status(to_status)
    if current == target:
        raise InvalidPromotionError(
            f"Модель уже в статусе «{current}». Повторное продвижение не требуется."
        )
    allowed = ALLOWED_TRANSITIONS.get(current, ())
    if target not in allowed:
        if not allowed:
            raise InvalidPromotionError(
                f"Статус «{current}» терминальный: дальнейшие переходы запрещены."
            )
        raise InvalidPromotionError(
            f"Переход {current} → {target} запрещён. "
            f"Допустимы: {', '.join(allowed) or 'нет'}."
        )
    return current, target


def plan_promotion(
    *,
    from_status: str,
    to_status: str,
    actor: str,
    confirm: bool,
    note: str = "",
) -> PromotionEvent:
    """Validate a human-gated transition. Does not persist or train."""
    require_confirm(confirm)
    who = require_actor(actor)
    current, target = assert_transition(from_status, to_status)
    return PromotionEvent(
        from_status=current,
        to_status=target,
        actor=who,
        at=utc_now_iso(),
        note=str(note or "").strip(),
        confirm=True,
        auto_deployed=False,
    )


def next_statuses(status: str) -> list[str]:
    return allowed_transitions(status)
