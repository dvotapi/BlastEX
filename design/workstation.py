"""Engineering workstation UI contract (BDX-026).

Hardens the design editor around the BDX-025 lifecycle. No new physics or ML:
the workstation only labels existing overlays, orders existing panels, and
blocks silent edits of an approved or closed passport.
"""
from __future__ import annotations

from typing import Any

from design.lifecycle import (
    ALLOWED_MUTATIONS,
    ALLOWED_TRANSITIONS,
    DATA_ROLES,
    LIFECYCLE_STATUSES,
    MUTATION_DESIGNED,
    MUTATION_EXECUTION,
    MUTATION_MEASURED,
    MUTATION_METADATA,
    ROLE_DESIGNED,
    ROLE_EXECUTED,
    ROLE_MEASURED,
    ROLE_PREDICTED,
    STATUS_LABELS,
    allow_mutation,
    can_delete,
    designed_mutable,
    is_record_frozen,
    listed_statuses,
    normalize_status,
)

# English role codes stay uppercase in the UI so DESIGNED never looks like EXECUTED.
ROLE_CODES = {
    ROLE_DESIGNED: "DESIGNED",
    ROLE_EXECUTED: "EXECUTED",
    ROLE_PREDICTED: "PREDICTED",
    ROLE_MEASURED: "MEASURED",
}

ROLE_LABELS_RU = {
    ROLE_DESIGNED: "проект",
    ROLE_EXECUTED: "исполнение",
    ROLE_PREDICTED: "прогноз",
    ROLE_MEASURED: "замер",
}

ROLE_LABELS_EN = {
    ROLE_DESIGNED: "designed",
    ROLE_EXECUTED: "executed",
    ROLE_PREDICTED: "predicted",
    ROLE_MEASURED: "measured",
}

# Display units as stored. The workstation never converts kg↔t or mm↔m.
DISPLAY_UNITS = {
    "length": "м",
    "diameter": "мм",
    "mass": "кг",
    "volume": "м³",
    "powder_factor": "кг/м³",
    "ppv": "мм/с",
    "fragment_size": "мм",
    "time": "мс",
    "angle": "°",
    "money": "₽",
}

TRANSITION_LABELS = {
    ("draft", "in_review"): "На проверку",
    ("in_review", "draft"): "Вернуть в черновик",
    ("in_review", "approved"): "Утвердить",
    ("approved", "executed"): "Отметить выполненным",
    ("executed", "closed"): "Закрыть паспорт",
}

# Survey → geology → pattern → charge → timing → simulation → execution →
# intelligence → scenarios → report. Stage ids are stable for the frontend.
WORKFLOW_STAGES: tuple[dict[str, Any], ...] = (
    {
        "id": "survey",
        "label": "Съёмка",
        "role": ROLE_DESIGNED,
        "mutation": MUTATION_DESIGNED,
        "panels": ["surfaces"],
    },
    {
        "id": "geology",
        "label": "Геология",
        "role": ROLE_DESIGNED,
        "mutation": MUTATION_DESIGNED,
        "panels": ["geology"],
    },
    {
        "id": "pattern",
        "label": "Сетка",
        "role": ROLE_DESIGNED,
        "mutation": MUTATION_DESIGNED,
        "panels": ["pattern"],
    },
    {
        "id": "charge",
        "label": "Заряд",
        "role": ROLE_DESIGNED,
        "mutation": MUTATION_DESIGNED,
        "panels": ["charge"],
    },
    {
        "id": "timing",
        "label": "Тайминг",
        "role": ROLE_DESIGNED,
        "mutation": MUTATION_DESIGNED,
        "panels": ["tie", "timing"],
    },
    {
        "id": "simulation",
        "label": "Симуляция",
        "role": ROLE_PREDICTED,
        "mutation": "",
        "panels": ["fragmentation", "vibration", "movement"],
    },
    {
        "id": "execution",
        "label": "Исполнение",
        "role": ROLE_EXECUTED,
        "mutation": MUTATION_EXECUTION,
        "panels": ["as_drilled", "as_charged", "as_fired", "execution_compare", "post_blast"],
    },
    {
        "id": "intelligence",
        "label": "Интеллект",
        "role": ROLE_PREDICTED,
        "mutation": "",
        "panels": ["dataset", "calibration", "outcomes", "learning", "registry", "spatial", "drift"],
    },
    {
        "id": "scenarios",
        "label": "Сценарии",
        "role": ROLE_PREDICTED,
        "mutation": "",
        "panels": ["scenarios", "optimization", "recommendation"],
    },
    {
        "id": "report",
        "label": "Отчёт",
        "role": ROLE_DESIGNED,
        "mutation": MUTATION_METADATA,
        "panels": ["passport", "cost"],
    },
)

OVERLAY_ROLES = {
    "pattern_map": ROLE_DESIGNED,
    "as_drilled": ROLE_EXECUTED,
    "as_charged": ROLE_EXECUTED,
    "as_fired": ROLE_EXECUTED,
    "fragmentation": ROLE_PREDICTED,
    "vibration_prediction": ROLE_PREDICTED,
    "vibration_measurement": ROLE_MEASURED,
    "movement": ROLE_PREDICTED,
    "spatial": ROLE_PREDICTED,
    "post_blast": ROLE_MEASURED,
    "passport": (ROLE_DESIGNED, ROLE_EXECUTED, ROLE_PREDICTED, ROLE_MEASURED),
}

AUTO_TRANSITION = False
SILENT_UNIT_CONVERSION = False


def listed_roles() -> list[dict[str, str]]:
    return [
        {
            "name": role,
            "code": ROLE_CODES[role],
            "label_ru": ROLE_LABELS_RU[role],
            "label_en": ROLE_LABELS_EN[role],
        }
        for role in (ROLE_DESIGNED, ROLE_EXECUTED, ROLE_PREDICTED, ROLE_MEASURED)
    ]


def listed_stages() -> list[dict[str, Any]]:
    return [
        {
            "id": stage["id"],
            "label": stage["label"],
            "role": stage["role"],
            "role_code": ROLE_CODES[stage["role"]],
            "mutation": stage["mutation"],
            "panels": list(stage["panels"]),
            "order": index + 1,
        }
        for index, stage in enumerate(WORKFLOW_STAGES)
    ]


def listed_transitions() -> list[dict[str, str]]:
    return [
        {
            "from_status": current,
            "to_status": target,
            "label": TRANSITION_LABELS[(current, target)],
        }
        for current, targets in ALLOWED_TRANSITIONS.items()
        for target in targets
    ]


def ui_can_edit(status: str, mutation: str) -> bool:
    """Workstation gate. Matches the API freeze, never infers a status."""
    return allow_mutation(status, mutation)


def ui_can_edit_designed(status: str) -> bool:
    return designed_mutable(status)


def ui_can_edit_execution(status: str) -> bool:
    return allow_mutation(status, MUTATION_EXECUTION)


def ui_can_edit_measured(status: str) -> bool:
    return allow_mutation(status, MUTATION_MEASURED)


def ui_can_edit_metadata(status: str) -> bool:
    return allow_mutation(status, MUTATION_METADATA)


def ui_can_delete(status: str) -> bool:
    return can_delete(status)


def ui_can_save(status: str) -> bool:
    return not is_record_frozen(status)


def freeze_message(status: str, mutation: str = MUTATION_DESIGNED) -> str:
    current = normalize_status(status)
    if is_record_frozen(current):
        return (
            "Паспорт закрыт: проект, исполнение и замер заморожены. "
            "Создайте ревизию (fork), чтобы продолжить работу."
        )
    if mutation == MUTATION_DESIGNED:
        return (
            f"Паспорт в статусе «{STATUS_LABELS[current]}»: слой DESIGNED заморожен. "
            "Сетку, заряд и тайминг нельзя править. Сценарии и ML остаются оверлеями."
        )
    if mutation == MUTATION_EXECUTION:
        return (
            f"Паспорт в статусе «{STATUS_LABELS[current]}»: слой EXECUTED сейчас нельзя менять."
        )
    if mutation == MUTATION_MEASURED:
        return (
            f"Паспорт в статусе «{STATUS_LABELS[current]}»: слой MEASURED сейчас нельзя менять."
        )
    return f"Паспорт в статусе «{STATUS_LABELS[current]}»: это изменение запрещено."


def workstation_meta() -> dict[str, Any]:
    return {
        "workflow": [stage["id"] for stage in WORKFLOW_STAGES],
        "stages": listed_stages(),
        "statuses": listed_statuses(),
        "status_labels": dict(STATUS_LABELS),
        "transitions": listed_transitions(),
        "data_roles": dict(DATA_ROLES),
        "role_codes": dict(ROLE_CODES),
        "role_labels_ru": dict(ROLE_LABELS_RU),
        "role_labels_en": dict(ROLE_LABELS_EN),
        "roles": listed_roles(),
        "overlay_roles": {
            name: list(value) if isinstance(value, tuple) else value
            for name, value in OVERLAY_ROLES.items()
        },
        "display_units": dict(DISPLAY_UNITS),
        "mutations": {
            status: sorted(ALLOWED_MUTATIONS[status]) for status in LIFECYCLE_STATUSES
        },
        "auto_transition": AUTO_TRANSITION,
        "silent_unit_conversion": SILENT_UNIT_CONVERSION,
    }
